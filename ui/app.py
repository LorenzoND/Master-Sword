"""Janela principal: barra lateral + páginas, loop de renderização e esconder/mostrar na bandeja."""

import ctypes
import logging
import os
import time
from ctypes import wintypes

import dearpygui.dearpygui as dpg

from core.hotkey import Hotkey
from core.launcher import SingleInstance
from ui import theme
from ui.context import Ctx
from ui.icon import ICON_ICO_PATH, ensure_icon_assets
from ui.pages.ajustes import AjustesPage
from ui.pages.fan import FanPage
from ui.pages.overlay_page import OverlayPage
from ui.pages.painel import PainelPage
from ui.pages.perfis import PerfisPage
from ui.pages.processos import ProcessosPage
from ui.tray import TrayApp

log = logging.getLogger("master_sword.ui")

TITLE = "Master-Sword"
VISIBLE_FPS = 30
UI_UPDATE_S = 0.25
STATUS_SECONDS = 8

_u32 = ctypes.WinDLL("user32")
_u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_u32.FindWindowW.restype = wintypes.HWND
_u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.SetForegroundWindow.argtypes = [wintypes.HWND]
_u32.IsIconic.argtypes = [wintypes.HWND]
SW_HIDE, SW_SHOW, SW_RESTORE = 0, 5, 9


class App:
    def __init__(self, ctx: Ctx, instance: SingleInstance, start_minimized: bool):
        self.ctx = ctx
        self.instance = instance
        self.visible = not start_minimized
        self.pages = [
            PainelPage(ctx),
            PerfisPage(ctx),
            FanPage(ctx),
            OverlayPage(ctx, self._restart_hotkey),
            ProcessosPage(ctx),
            AjustesPage(ctx),
        ]
        self.current = os.environ.get("MASTER_SWORD_PAGE", "painel")
        self.hwnd = None
        self.hotkey = None
        self._running = True
        self._status_until = 0.0
        self.tray = TrayApp(ctx, on_open=self.show, on_quit=self.quit)
        ctx.controller.add_listener(lambda msg, err: ctx.run_on_ui(lambda: self._status(msg, err)))
        ctx.on_profiles_changed.append(self.tray.refresh)

    # ---------- construção ----------

    def build(self):
        with dpg.window(tag="root"):
            with dpg.group(horizontal=True, horizontal_spacing=0):
                with dpg.child_window(width=theme.px(220), height=-1, border=False, tag="sidebar",
                                      always_use_window_padding=True):
                    logo = dpg.add_text("MASTER-SWORD", color=theme.rgba(theme.GOLD))
                    theme.font(logo, "section")
                    t = dpg.add_text("controle térmico · GS66", color=theme.rgba(theme.FAINT))
                    theme.font(t, "small")
                    dpg.add_spacer(height=theme.px(18))
                    for page in self.pages:
                        dpg.add_button(label=page.label, width=-1, tag=f"nav_{page.key}",
                                       callback=lambda s, a, u: self.go(u), user_data=page.key)
                    dpg.add_spacer(height=theme.px(24))
                    status = dpg.add_text("", tag="status_line", wrap=theme.px(190))
                    theme.font(status, "small")
                    if not self.ctx.is_admin:
                        w = dpg.add_text("Sem admin: lock, sensores e fan desativados.",
                                         color=theme.rgba(theme.WARN), wrap=theme.px(190))
                        theme.font(w, "small")
                with dpg.child_window(height=-1, border=False, tag="content", always_use_window_padding=True):
                    for page in self.pages:
                        with dpg.group(tag=f"page_{page.key}", show=page.key == self.current):
                            page.build()
        theme.apply("root", "root")
        theme.apply("sidebar", "sidebar")
        theme.apply("content", "content")
        self._paint_nav()

    def _paint_nav(self):
        for page in self.pages:
            theme.apply(f"nav_{page.key}", "nav_active" if page.key == self.current else "nav")

    def go(self, key: str):
        log.debug("navegando para %s", key)
        if key == self.current:
            return
        dpg.configure_item(f"page_{self.current}", show=False)
        dpg.configure_item(f"page_{key}", show=True)
        self.current = key
        self._paint_nav()
        self._page().on_show()
        snap = self.ctx.sampler.latest
        if snap:
            self._page().update(snap)

    def _page(self):
        return next(p for p in self.pages if p.key == self.current)

    def _status(self, msg: str, error: bool):
        dpg.set_value("status_line", msg)
        dpg.configure_item("status_line", color=theme.rgba(theme.HOT if error else theme.OK))
        self._status_until = time.monotonic() + STATUS_SECONDS

    # ---------- janela / bandeja ----------

    def show(self):
        self.visible = True
        if self.hwnd:
            _u32.ShowWindow(self.hwnd, SW_RESTORE if _u32.IsIconic(self.hwnd) else SW_SHOW)
            _u32.SetForegroundWindow(self.hwnd)

    def hide(self):
        """O X da janela esconde na bandeja; sair é pelo menu da bandeja.

        Chamado pela thread de callbacks do Dear PyGui: ShowWindowAsync não espera a thread da
        janela (ShowWindow travava no destroy_context, que também dispara o exit callback)."""
        if not self._running:
            return
        self.visible = False
        if self.hwnd:
            _u32.ShowWindowAsync(self.hwnd, SW_HIDE)

    def quit(self):
        self._running = False
        dpg.stop_dearpygui()

    def _restart_hotkey(self):
        if self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        combo = self.ctx.settings.overlay_hotkey
        if combo and combo != "Desligado":
            self.hotkey = Hotkey(combo, self.ctx.overlay.toggle_visible)
            self.hotkey.start()

    def _tooltip(self) -> str:
        st = self.ctx.controller.state
        parts = ["Master-Sword"]
        if st.active_profile:
            parts.append(st.active_profile)
        if st.gpu_lock:
            parts.append(f"GPU {st.gpu_lock[1]} MHz")
        snap = self.ctx.sampler.latest
        if snap and snap.gpu_temp is not None:
            parts.append(f"GPU {snap.gpu_temp:.0f}°C")
        if snap and snap.cpu_temp is not None:
            parts.append(f"CPU {snap.cpu_temp:.0f}°C")
        return " · ".join(parts)

    # ---------- loop ----------

    def run(self):
        ensure_icon_assets()
        dpg.create_context()
        theme.setup()
        self.build()
        test_pos = os.environ.get("MASTER_SWORD_TEST_POS")  # testes: abre fora da tela
        x, y = (int(v) for v in test_pos.split(",")) if test_pos else (100, 60)
        dpg.create_viewport(title=TITLE, width=theme.px(1280), height=theme.px(900), x_pos=x, y_pos=y,
                            min_width=theme.px(1040), min_height=theme.px(720),
                            small_icon=str(ICON_ICO_PATH), large_icon=str(ICON_ICO_PATH),
                            vsync=False, disable_close=True, clear_color=theme.rgba(theme.BG))
        dpg.set_exit_callback(lambda: self.hide())
        dpg.setup_dearpygui()
        dpg.set_primary_window("root", True)
        dpg.show_viewport(minimized=not self.visible)
        self.hwnd = _u32.FindWindowW(None, TITLE)
        if not self.visible and self.hwnd:
            _u32.ShowWindow(self.hwnd, SW_HIDE)

        self.tray.start()
        self._restart_hotkey()
        self._page().on_show()

        screenshot = os.environ.get("MASTER_SWORD_SCREENSHOT")
        screenshot_at = time.monotonic() + float(os.environ.get("MASTER_SWORD_SCREENSHOT_DELAY", "4"))
        last_ui = last_tip = 0.0
        try:
            while self._running and dpg.is_dearpygui_running():
                started = time.monotonic()
                while not self.ctx.ui_queue.empty():
                    try:
                        self.ctx.ui_queue.get_nowait()()
                    except Exception:
                        log.exception("Ação de interface falhou")
                if self.instance.show_requested():
                    self.show()

                now = time.monotonic()
                if self.visible and now - last_ui >= UI_UPDATE_S:
                    last_ui = now
                    snap = self.ctx.sampler.latest
                    if snap:
                        try:
                            self._page().update(snap)
                        except Exception:
                            log.exception("Falha ao atualizar a página %s", self.current)
                    if self._status_until and now > self._status_until:
                        dpg.set_value("status_line", "")
                        self._status_until = 0.0
                if now - last_tip >= 5:
                    last_tip = now
                    self.tray.set_tooltip(self._tooltip())

                dpg.render_dearpygui_frame()

                if screenshot and now >= screenshot_at:
                    dpg.output_frame_buffer(file=screenshot)
                    dpg.render_dearpygui_frame()
                    dpg.render_dearpygui_frame()
                    break

                budget = (1 / VISIBLE_FPS) if self.visible else 0.2
                elapsed = time.monotonic() - started
                if elapsed < budget:
                    time.sleep(budget - elapsed)
        finally:
            self._running = False
            if self.hotkey:
                self.hotkey.stop()
            self.tray.stop()
            dpg.destroy_context()
