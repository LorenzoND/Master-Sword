"""Ícone na bandeja: abrir a janela, trocar de perfil, overlay, soltar lock, sair."""

import threading
from typing import Callable

import pystray

from core import profiles as profiles_mod
from ui.context import Ctx
from ui.icon import load_tray_image


class TrayApp:
    def __init__(self, ctx: Ctx, on_open: Callable[[], None], on_quit: Callable[[], None]):
        self.ctx = ctx
        self._on_open = on_open
        self._on_quit = on_quit
        self._icon = pystray.Icon("master-sword", load_tray_image(), "Master-Sword", menu=self._menu())

    def _menu(self) -> pystray.Menu:
        c = self.ctx
        return pystray.Menu(
            pystray.MenuItem("Abrir Master-Sword", lambda: c.run_on_ui(self._on_open), default=True),
            pystray.MenuItem("Perfis", pystray.Menu(self._profile_items)),
            pystray.MenuItem("Overlay visível", lambda: c.overlay.toggle_visible(),
                             checked=lambda _: c.settings.overlay_visible and c.settings.overlay_mode != "off"),
            pystray.MenuItem("Soltar lock da GPU", lambda: c.controller.release_gpu_lock(),
                             enabled=lambda _: c.controller.state.gpu_lock is not None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", lambda: c.run_on_ui(self._on_quit)),
        )

    def _profile_items(self):
        active = self.ctx.controller.state.active_profile
        items = []
        for p in profiles_mod.list_profiles():
            items.append(pystray.MenuItem(
                p.name, self._apply_cb(p.name), checked=lambda _, n=p.name: n == active, radio=True))
        return items or [pystray.MenuItem("Nenhum perfil", None, enabled=False)]

    def _apply_cb(self, name: str):
        def apply(icon, item):
            self.ctx.controller.apply_profile(name)
            self.ctx.run_on_ui(self.ctx.profiles_changed)
        return apply

    def refresh(self):
        self._icon.update_menu()

    def set_tooltip(self, text: str):
        self._icon.title = text[:127]

    def notify(self, title: str, message: str):
        try:
            self._icon.notify(message, title)
        except Exception:
            pass

    def start(self):
        threading.Thread(target=self._icon.run, name="tray", daemon=True).start()

    def stop(self):
        self._icon.stop()
