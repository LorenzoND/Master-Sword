"""Fase 4 — fan pelo EC: leitura sempre; escrita só depois de habilitar explicitamente."""

import time

import dearpygui.dearpygui as dpg

from core.ec import FAN_MODE_LABELS, SHIFT_MODE_LABELS, CURVE_SPEEDS, EcError
from core.paths import LOGS_DIR
from core.sampler import Snapshot
from core.settings import save_settings
from ui import theme
from ui.context import Ctx
from ui.widgets import Segmented, card, chip, danger_button, muted, primary_button, section, set_chip, title

COOLER_OPTIONS = {False: "Desligado", True: "Ligado"}
SHIFT_ORDER = {k: SHIFT_MODE_LABELS[k] for k in ("eco", "comfort", "sport", "turbo")}


class FanPage:
    key = "fan"
    label = "Fan"

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.curve = None
        self._hold_until = 0.0  # depois de um clique, não deixa a leitura sobrescrever o botão por 2 s

    def build(self):
        title("Fan")
        with dpg.group(horizontal=True, horizontal_spacing=theme.px(6)):
            chip("EC --", "muted", tag="fn_chip_ec")
            chip("Controle desligado", "muted", tag="fn_chip_ctrl")
        dpg.add_spacer(height=theme.px(4))

        with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchSame, pad_outerX=False):
            for _ in range(3):
                dpg.add_table_column()
            with dpg.table_row():
                for key, label in (("cpu", "Fan da CPU"), ("gpu", "Fan da GPU"), ("mode", "Modo atual")):
                    with card(height=theme.px(122)):
                        muted(label)
                        big = dpg.add_text("--", tag=f"fn_{key}_big")
                        theme.font(big, "big")
                        muted("", tag=f"fn_{key}_sub")

        dpg.add_spacer(height=theme.px(2))
        with card():
            section("Controle")
            with dpg.group(tag="fn_locked"):
                muted("Escrever no EC mexe direto no firmware do notebook. O app só libera isso com o firmware "
                      "reconhecido e confere cada escrita lendo de volta. Na primeira vez, teste com o fan à vista "
                      "(ou ouvindo): ligue o Cooler Boost e veja se o fan dispara.", wrap=theme.px(760), small=False)
                primary_button("Habilitar controle do fan", self._ask_enable, tag="fn_enable_btn")
            with dpg.group(tag="fn_controls", show=False):
                with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp):
                    dpg.add_table_column(init_width_or_weight=0.22)
                    dpg.add_table_column(init_width_or_weight=0.78)
                    with dpg.table_row():
                        dpg.add_text("Modo do fan")
                        self.mode_seg = Segmented(FAN_MODE_LABELS, lambda k: self._do(self.ctx.controller.set_fan_mode, k))
                    with dpg.table_row():
                        dpg.add_text("Cooler Boost")
                        self.cooler_seg = Segmented(COOLER_OPTIONS, lambda k: self._do(self.ctx.controller.set_cooler_boost, k))
                    with dpg.table_row():
                        dpg.add_text("Modo MSI")
                        self.shift_seg = Segmented(SHIFT_ORDER, lambda k: self._do(self.ctx.controller.set_shift_mode, k))
                muted("Modo MSI é o \"shift mode\" do Dragon Center: Eco e Comfort limitam o power de CPU/GPU, "
                      "Sport e Turbo liberam. Se o Dragon Center estiver aberto ele pode trocar isso por conta própria.",
                      wrap=theme.px(760))
                b = dpg.add_button(label="Desabilitar controle do fan", callback=self._disable)
                theme.apply(b, "ghost")

        dpg.add_spacer(height=theme.px(2))
        with card():
            with dpg.group(horizontal=True):
                section("Curva do fan")
                chip("experimental", "warn")
                chip("--", "muted", tag="fn_chip_curve")
            muted("Leitura dos pontos de temperatura → velocidade gravados no EC. A curva só vale no modo "
                  "\"Avançado (curva)\".", wrap=theme.px(760))
            with dpg.plot(height=theme.px(200), width=-1, no_menus=True, no_box_select=True, no_title=True,
                          tag="fn_curve_plot"):
                dpg.add_plot_legend(location=dpg.mvPlot_Location_North, horizontal=True, no_buttons=True, outside=True)
                self.cx = dpg.add_plot_axis(dpg.mvXAxis, label="°C", lock_min=True, lock_max=True)
                self.cy = dpg.add_plot_axis(dpg.mvYAxis, label="%", lock_min=True, lock_max=True)
                self.curve_cpu = dpg.add_line_series([], [], label="CPU", parent=self.cy)
                self.curve_gpu = dpg.add_line_series([], [], label="GPU", parent=self.cy)
                theme.apply(self.curve_cpu, "line_cpu")
                theme.apply(self.curve_gpu, "line_gpu")
            dpg.set_axis_limits(self.cx, 30, 105)
            dpg.set_axis_limits(self.cy, 0, 150)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Ler curva do EC", callback=self._read_curve)
                dpg.add_checkbox(label="Liberar edição (experimental)", tag="fn_curve_unlock",
                                 default_value=self.ctx.settings.fan_curve_enabled, callback=self._curve_unlock)
            with dpg.group(tag="fn_curve_editor", show=False):
                for fan in ("cpu", "gpu"):
                    with dpg.group(horizontal=True):
                        dpg.add_text(fan.upper(), color=theme.rgba(theme.CPU_COLOR if fan == "cpu" else theme.GPU_COLOR))
                        for i in range(CURVE_SPEEDS):
                            dpg.add_input_int(tag=f"fn_{fan}_sp{i}", width=theme.px(62), step=0,
                                              min_value=0, max_value=150, min_clamped=True, max_clamped=True)
                        save_btn = primary_button("Gravar", lambda s, a, u: self._write_curve(u))
                        dpg.set_item_user_data(save_btn, fan)
                muted("Velocidades em % para cada ponto (as temperaturas dos pontos ficam as do fabricante). "
                      "Precisa ser crescente e o último ponto ≥ 80%.", wrap=theme.px(760))

        dpg.add_spacer(height=theme.px(2))
        with card():
            section("Diagnóstico")
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salvar dump do EC", callback=self._dump)
                muted("Grava os 256 registradores em logs/ (só leitura) — útil pra conferir o mapa.")

        with dpg.window(tag="fn_confirm", modal=True, show=False, no_title_bar=True, no_resize=True,
                        width=theme.px(460)):
            dpg.add_text("Habilitar a escrita no EC?", wrap=theme.px(420))
            muted("Recomendado: deixe o Dragon Center fechado e teste primeiro o Cooler Boost (fácil de "
                  "ouvir). Dá pra desabilitar de novo quando quiser.", wrap=theme.px(420), small=False)
            dpg.add_spacer(height=theme.px(6))
            with dpg.group(horizontal=True):
                danger_button("Habilitar", self._enable)
                dpg.add_button(label="Cancelar", callback=lambda: dpg.configure_item("fn_confirm", show=False))

    # ---------- ações ----------

    def _do(self, fn, value):
        self._hold_until = time.monotonic() + 2.0
        fn(value)

    def _ask_enable(self):
        w, h = dpg.get_viewport_client_width(), dpg.get_viewport_client_height()
        dpg.configure_item("fn_confirm", show=True, pos=(w // 2 - theme.px(230), h // 2 - theme.px(90)))

    def _enable(self):
        dpg.configure_item("fn_confirm", show=False)
        self.ctx.settings.fan_control_enabled = True
        save_settings(self.ctx.settings)
        self.ctx.controller.notify("Controle do fan habilitado")
        self.on_show()

    def _disable(self):
        self.ctx.settings.fan_control_enabled = False
        save_settings(self.ctx.settings)
        self.ctx.controller.notify("Controle do fan desabilitado")
        self.on_show()

    def _curve_unlock(self, sender, value):
        self.ctx.settings.fan_curve_enabled = bool(value)
        save_settings(self.ctx.settings)
        self._refresh_curve_editor()

    def _read_curve(self):
        ec = self.ctx.ec
        if ec is None:
            self.ctx.controller.notify("EC indisponível", True)
            return
        try:
            self.curve = ec.read_curve()
        except EcError as exc:
            self.ctx.controller.notify(f"EC: {exc}", True)
            return
        valid = ec.curve_looks_valid(self.curve)
        set_chip("fn_chip_curve", "leitura coerente" if valid else "leitura estranha — edição bloqueada",
                 "ok" if valid else "hot")
        for fan, series in (("cpu", self.curve_cpu), ("gpu", self.curve_gpu)):
            temps, speeds = self.curve[fan]["temps"], self.curve[fan]["speeds"]
            xs = [temps[0] - 10] + temps  # 1º ponto vale abaixo da 1ª temperatura
            dpg.set_value(series, [xs, speeds[:len(xs)]])
            for i, sp in enumerate(speeds):
                dpg.set_value(f"fn_{fan}_sp{i}", sp)
        self._refresh_curve_editor()

    def _refresh_curve_editor(self):
        ok = (self.curve is not None and self.ctx.ec is not None and self.ctx.ec.curve_looks_valid(self.curve)
              and self.ctx.settings.fan_curve_enabled and self.ctx.controller.ec_writable())
        dpg.configure_item("fn_curve_editor", show=ok)

    def _write_curve(self, fan: str):
        speeds = [dpg.get_value(f"fn_{fan}_sp{i}") for i in range(CURVE_SPEEDS)]
        if self.ctx.controller.set_curve_speeds(fan, speeds):
            self._read_curve()

    def _dump(self):
        ec = self.ctx.ec
        if ec is None:
            self.ctx.controller.notify("EC indisponível", True)
            return
        try:
            data = ec.dump()
        except EcError as exc:
            self.ctx.controller.notify(f"EC: {exc}", True)
            return
        LOGS_DIR.mkdir(exist_ok=True)
        path = LOGS_DIR / f"ec_dump_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        lines = [f"firmware: {ec.firmware}", "     " + " ".join(f"{i:02X}" for i in range(16))]
        for row in range(16):
            lines.append(f"{row * 16:02X}:  " + " ".join(f"{b:02X}" for b in data[row * 16:row * 16 + 16]))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.ctx.controller.notify(f"Dump salvo em logs/{path.name}")

    # ---------- ciclo ----------

    def on_show(self):
        ec = self.ctx.ec
        if ec is None:
            set_chip("fn_chip_ec", "EC indisponível (precisa de admin + PawnIO)", "muted")
        elif ec.supported:
            set_chip("fn_chip_ec", f"EC {ec.firmware} reconhecido", "ok")
        else:
            set_chip("fn_chip_ec", f"EC {ec.firmware} não reconhecido — só leitura", "hot")
        writable = self.ctx.controller.ec_writable()
        set_chip("fn_chip_ctrl", "Controle habilitado" if writable else "Controle desligado",
                 "blue" if writable else "muted")
        dpg.configure_item("fn_controls", show=writable)
        dpg.configure_item("fn_locked", show=not writable)
        if ec is None or not ec.supported:
            dpg.disable_item("fn_enable_btn")
        if self.curve is None and ec is not None:
            self._read_curve()
        self._refresh_curve_editor()

    def update(self, snap: Snapshot):
        e = snap.ec
        if not e:
            for key in ("cpu", "gpu", "mode"):
                dpg.set_value(f"fn_{key}_big", "--")
            return
        for key in ("cpu", "gpu"):
            rpm = e.get(f"{key}_fan_rpm")
            dpg.set_value(f"fn_{key}_big", f"{e[f'{key}_fan_pct']}%")
            dpg.set_value(f"fn_{key}_sub", f"{rpm} rpm · {e[f'{key}_temp_c']} °C no EC" if rpm
                          else f"{e[f'{key}_temp_c']} °C no EC")
        mode = FAN_MODE_LABELS.get(e["fan_mode"], f"0x{e['fan_mode_raw']:02X}")
        dpg.set_value("fn_mode_big", mode.split(" ")[0])
        shift = SHIFT_MODE_LABELS.get(e["shift_mode"], f"0x{e['shift_mode_raw']:02X}")
        dpg.set_value("fn_mode_sub", f"Modo MSI {shift} · Cooler Boost {'ligado' if e['cooler_boost'] else 'desligado'}")
        if time.monotonic() >= self._hold_until and dpg.is_item_shown("fn_controls"):
            self.mode_seg.set(e["fan_mode"])
            self.cooler_seg.set(e["cooler_boost"])
            self.shift_seg.set(e["shift_mode"])
