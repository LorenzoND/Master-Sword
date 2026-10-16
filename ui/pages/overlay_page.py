"""Fase 3 — overlay: modo (RTSS in-game / desktop / desligado), itens, cor, posição, atalho."""

import dearpygui.dearpygui as dpg

from core import osd
from core.hotkey import HOTKEY_CHOICES
from core.rtss import install_path
from core.sampler import Snapshot
from core.settings import OVERLAY_ITEMS, OVERLAY_POSITIONS, save_settings
from ui import theme
from ui.context import Ctx
from ui.widgets import Segmented, card, chip, muted, primary_button, section, set_chip, title

MODES = {"rtss": "In-game (RTSS)", "desktop": "Desktop", "off": "Desligado"}


class OverlayPage:
    key = "overlay"
    label = "Overlay"

    def __init__(self, ctx: Ctx, on_hotkey_changed):
        self.ctx = ctx
        self.on_hotkey_changed = on_hotkey_changed

    def build(self):
        s = self.ctx.settings
        title("Overlay")
        with dpg.group(horizontal=True, horizontal_spacing=theme.px(6)):
            chip("RTSS --", "muted", tag="ov_chip_rtss")
            chip("--", "muted", tag="ov_chip_visible")
        dpg.add_spacer(height=theme.px(4))

        with dpg.group(horizontal=True, horizontal_spacing=theme.px(16)):
            with dpg.group(width=theme.px(560)):
                with card():
                    section("Modo")
                    self.mode_seg = Segmented(MODES, self._mode_changed, s.overlay_mode)
                    muted("", tag="ov_mode_help", wrap=theme.px(520))
                    with dpg.group(horizontal=True, tag="ov_rtss_row"):
                        primary_button("Abrir RTSS", self._start_rtss, tag="ov_rtss_btn")
                        muted("", tag="ov_rtss_path")

                with card():
                    section("O que mostrar")
                    keys = list(OVERLAY_ITEMS)
                    half = (len(keys) + 1) // 2
                    with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchSame):
                        dpg.add_table_column()
                        dpg.add_table_column()
                        for i in range(half):
                            with dpg.table_row():
                                for key in (keys[i], keys[i + half] if i + half < len(keys) else None):
                                    if key:
                                        dpg.add_checkbox(label=OVERLAY_ITEMS[key], default_value=s.overlay_items[key],
                                                         callback=self._item_changed, user_data=key)
                                    else:
                                        dpg.add_spacer()

                with card():
                    section("Aparência e atalho")
                    with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp):
                        dpg.add_table_column(init_width_or_weight=0.35)
                        dpg.add_table_column(init_width_or_weight=0.65)
                        with dpg.table_row():
                            dpg.add_text("Cor")
                            r, g, b = (int(s.overlay_color[i:i + 2], 16) for i in (0, 2, 4))
                            dpg.add_color_edit((r, g, b, 255), no_alpha=True, width=theme.px(220),
                                               callback=self._color_changed)
                        with dpg.table_row():
                            dpg.add_text("Posição (desktop)")
                            dpg.add_combo(list(OVERLAY_POSITIONS.values()), width=-1,
                                          default_value=OVERLAY_POSITIONS.get(s.overlay_position),
                                          callback=self._position_changed)
                        with dpg.table_row():
                            dpg.add_text("Mostrar/esconder")
                            dpg.add_combo(HOTKEY_CHOICES, width=-1, default_value=s.overlay_hotkey,
                                          callback=self._hotkey_changed)
                    muted("No modo RTSS a posição e o tamanho da fonte seguem as configurações do próprio RTSS.",
                          wrap=theme.px(520))

            with dpg.group(width=-1):
                with card():
                    section("Prévia")
                    muted("Atualiza a cada segundo com os valores reais.")
                    with dpg.child_window(height=theme.px(260), border=False, tag="ov_preview_box",
                                          always_use_window_padding=True):
                        theme.apply("ov_preview_box", "preview")
                        with dpg.group(tag="ov_preview"):
                            pass
        self._refresh_mode_help()

    # ---------- ações ----------

    def _save(self):
        save_settings(self.ctx.settings)

    def _mode_changed(self, mode):
        self.ctx.settings.overlay_mode = mode
        self.ctx.settings.overlay_visible = True
        self._save()
        self._refresh_mode_help()

    def _item_changed(self, sender, value, key):
        self.ctx.settings.overlay_items[key] = bool(value)
        self._save()

    def _color_changed(self, sender, value):
        rgb = [int(round(v * 255)) if isinstance(v, float) and v <= 1.0 else int(v) for v in value[:3]]
        self.ctx.settings.overlay_color = "".join(f"{max(0, min(255, c)):02X}" for c in rgb)
        self._save()

    def _position_changed(self, sender, label):
        self.ctx.settings.overlay_position = next(k for k, v in OVERLAY_POSITIONS.items() if v == label)
        self._save()

    def _hotkey_changed(self, sender, combo):
        self.ctx.settings.overlay_hotkey = combo
        self._save()
        self.on_hotkey_changed()

    def _start_rtss(self):
        if self.ctx.overlay.start_rtss():
            self.ctx.controller.notify("RTSS iniciado")
        else:
            self.ctx.controller.notify("RTSS não encontrado — instale o RivaTuner Statistics Server", True)

    def _refresh_mode_help(self):
        mode = self.ctx.settings.overlay_mode
        help_text = {
            "rtss": "Desenhado pelo RTSS dentro do jogo: transparente, não pega clique e funciona em tela "
                    "cheia exclusiva. Mostra FPS e frametime do jogo. Precisa do RTSS aberto (o Afterburner "
                    "pode ficar fechado).",
            "desktop": "Janelinha semitransparente sempre no topo, que não pega clique. Funciona em jogos em "
                       "janela ou tela cheia sem borda; não mostra FPS sem o RTSS.",
            "off": "Overlay desligado.",
        }[mode]
        dpg.set_value("ov_mode_help", help_text)
        dpg.configure_item("ov_rtss_row", show=mode == "rtss")
        exe = install_path()
        dpg.set_value("ov_rtss_path", str(exe) if exe else "RTSS não instalado")

    # ---------- ciclo ----------

    def on_show(self):
        self._refresh_mode_help()

    def update(self, snap: Snapshot):
        s = self.ctx.settings
        running = self.ctx.overlay.rtss_running
        set_chip("ov_chip_rtss", "RTSS rodando" if running else "RTSS fechado", "ok" if running else "muted")
        hk = s.overlay_hotkey if s.overlay_hotkey != "Desligado" else "sem atalho"
        set_chip("ov_chip_visible", f"Visível ({hk})" if s.overlay_visible else f"Escondido ({hk})",
                 "blue" if s.overlay_visible else "muted")
        dpg.configure_item("ov_rtss_btn", show=not running)

        lines = osd.plain_lines(snap, s, self.ctx.overlay.alerts.gpu_hot, self.ctx.overlay.alerts.cpu_hot)
        dpg.delete_item("ov_preview", children_only=True)
        color = tuple(int(s.overlay_color[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
        alert = tuple(int(osd.ALERT_COLOR[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
        for text, is_alert in lines:
            t = dpg.add_text(text, parent="ov_preview", color=alert if is_alert else color)
            theme.font(t, "mono")
