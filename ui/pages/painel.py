"""Painel: números grandes, motivo de limite, gráfico com escala fixa e controles rápidos."""

import math
import time

import dearpygui.dearpygui as dpg

from core.cpu import BOOST_MODES
from core.osd import fan_mode_label
from core.sampler import Snapshot
from ui import theme
from ui.context import Ctx
from ui.widgets import Segmented, card, chip, fmt, level_for, muted, primary_button, section, set_chip, title

TABS = {"temp": "Temperatura", "clock": "Clock", "power": "Energia", "fan": "Fans"}
WINDOWS = {60: "1 min", 300: "5 min", 900: "15 min"}

# escala fixa por aba: o eixo não "pula" e uma variação de 1 °C não parece um abismo
Y_RANGE = {"temp": (30, 105), "clock": (0, 5000), "power": (0, 120), "fan": (0, 150)}
Y_UNIT = {"temp": "°C", "clock": "MHz", "power": "W", "fan": "%"}
SERIES = {
    "temp": ("gpu_temp", "cpu_temp"),
    "clock": ("gpu_clock", "cpu_clock"),
    "power": ("gpu_power", "cpu_power"),
    "fan": ("gpu_fan", "cpu_fan"),
}
LIMIT_FLAGS = {"temp": ("gpu_therm", "cpu_therm"), "power": ("gpu_pwr", "cpu_pwr")}
GPU_PRESETS = (800, 900, 1200)


class PainelPage:
    key = "painel"
    label = "Painel"

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.tab = "temp"
        self.window_s = ctx.settings.history_window_s if ctx.settings.history_window_s in WINDOWS else 300
        self._last_t = 0.0
        self._hist: dict = {}

    # ---------- construção ----------

    def build(self):
        title("Painel")
        with dpg.group(horizontal=True, horizontal_spacing=theme.px(6)):
            chip("Perfil: --", "muted", tag="pn_chip_profile")
            chip("GPU sem lock", "muted", tag="pn_chip_lock")
            chip("Boost --", "muted", tag="pn_chip_boost")
            chip("GPU --", "muted", tag="pn_chip_gpu_lim")
            chip("CPU --", "muted", tag="pn_chip_cpu_lim")
        dpg.add_spacer(height=theme.px(4))

        with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchSame, borders_innerV=False,
                       borders_outerV=False, borders_innerH=False, borders_outerH=False, pad_outerX=False):
            for _ in range(4):
                dpg.add_table_column()
            with dpg.table_row():
                for key, label in (("gpu", f"GPU · {self.ctx.gpu.name.replace('NVIDIA GeForce ', '')}"),
                                   ("cpu", f"CPU · {self.ctx.cpu_name.replace('Intel Core ', '')}"),
                                   ("fan", "Fans"), ("sys", "Memória")):
                    with card(height=theme.px(132)):
                        muted(label)
                        big = dpg.add_text("--", tag=f"pn_{key}_big")
                        theme.font(big, "big")
                        muted("", tag=f"pn_{key}_sub")

        dpg.add_spacer(height=theme.px(2))
        with card():
            with dpg.group(horizontal=True):
                self.tabs = Segmented(TABS, self._set_tab, self.tab)
                dpg.add_spacer(width=theme.px(24))
                self.windows = Segmented(WINDOWS, self._set_window, self.window_s)
            with dpg.plot(tag="pn_plot", height=theme.px(250), width=-1, no_menus=True, no_box_select=True,
                          no_mouse_pos=True, no_title=True):
                dpg.add_plot_legend(location=dpg.mvPlot_Location_North, horizontal=True, no_buttons=True, outside=True)
                self.x_axis = dpg.add_plot_axis(dpg.mvXAxis, no_gridlines=True, lock_min=True, lock_max=True)
                self.y_axis = dpg.add_plot_axis(dpg.mvYAxis, lock_min=True, lock_max=True)
                y = self.y_axis
                self.s_zone = dpg.add_shade_series([0.0], [0.0], y2=[0.0], label="Zona de alerta", parent=y)
                self.s_limit = dpg.add_shade_series([0.0], [0.0], y2=[0.0], label="Limitado", parent=y)
                self.s_ref = dpg.add_inf_line_series([0.0], horizontal=True, label="##ref", parent=y)
                self.s_gpu = dpg.add_line_series([], [], label="GPU", parent=y)
                self.s_cpu = dpg.add_line_series([], [], label="CPU", parent=y)
                theme.apply(self.s_zone, "shade_zone")
                theme.apply(self.s_limit, "shade_warn")
                theme.apply(self.s_ref, "line_hot")
                theme.apply(self.s_gpu, "line_gpu")
                theme.apply(self.s_cpu, "line_cpu")
            muted("Passe o mouse no gráfico pra ver os valores de cada instante.", tag="pn_hover")

        dpg.add_spacer(height=theme.px(2))
        with card():
            section("Controles rápidos")
            with dpg.group(horizontal=True):
                dpg.add_text("Lock da GPU")
                dpg.add_input_int(tag="pn_gpu_min", width=theme.px(110), default_value=900, step=0,
                                  min_value=210, max_value=self.ctx.gpu.max_clock_mhz, min_clamped=True, max_clamped=True)
                dpg.add_text("a")
                dpg.add_input_int(tag="pn_gpu_max", width=theme.px(110), default_value=900, step=0,
                                  min_value=210, max_value=self.ctx.gpu.max_clock_mhz, min_clamped=True, max_clamped=True)
                dpg.add_text("MHz")
                primary_button("Travar", self._apply_lock)
                dpg.add_button(label="Soltar", callback=lambda: self.ctx.controller.release_gpu_lock())
                dpg.add_spacer(width=theme.px(12))
                for mhz in GPU_PRESETS:
                    b = dpg.add_button(label=str(mhz), callback=lambda s, a, u: self._preset(u), user_data=mhz)
                    theme.apply(b, "ghost")
            muted("O lock fica no driver até você soltar ou reiniciar o PC, mesmo com o app fechado.")
            with dpg.group(horizontal=True):
                dpg.add_text("Boost da CPU")
                dpg.add_combo(list(BOOST_MODES.values()), tag="pn_boost", width=theme.px(260),
                              callback=self._boost_changed)

        lock = self.ctx.controller.state.gpu_lock
        if lock:
            dpg.set_value("pn_gpu_min", lock[0])
            dpg.set_value("pn_gpu_max", lock[1])

    # ---------- ações ----------

    def _apply_lock(self):
        self.ctx.controller.set_gpu_lock(dpg.get_value("pn_gpu_min"), dpg.get_value("pn_gpu_max"))

    def _preset(self, mhz: int):
        dpg.set_value("pn_gpu_min", mhz)
        dpg.set_value("pn_gpu_max", mhz)
        self.ctx.controller.set_gpu_lock(mhz, mhz)

    def _boost_changed(self, sender, label):
        mode = next(k for k, v in BOOST_MODES.items() if v == label)
        self.ctx.controller.set_boost(mode)

    def _set_tab(self, tab):
        self.tab = tab
        self._redraw_chart()

    def _set_window(self, window_s):
        self.window_s = window_s
        self.ctx.settings.history_window_s = window_s
        self._redraw_chart()

    # ---------- atualização ----------

    def on_show(self):
        self._redraw_chart()

    def update(self, snap: Snapshot):
        self._update_chips(snap)
        self._update_tiles(snap)
        if snap.t != self._last_t:
            self._last_t = snap.t
            self._hist = self.ctx.sampler.history()
            self._redraw_chart()
        self._update_hover()

    def _update_chips(self, snap: Snapshot):
        st = self.ctx.controller.state
        if st.active_profile:
            set_chip("pn_chip_profile", f"Perfil: {st.active_profile}{' (alterado)' if st.profile_modified else ''}",
                     "warn" if st.profile_modified else "blue")
        else:
            set_chip("pn_chip_profile", "Sem perfil ativo", "muted")
        lock = st.gpu_lock
        if lock:
            text = f"GPU travada {lock[1]} MHz" if lock[0] == lock[1] else f"GPU {lock[0]}–{lock[1]} MHz"
            set_chip("pn_chip_lock", text, "blue")
        else:
            set_chip("pn_chip_lock", "GPU sem lock", "muted")
        boost = snap.boost_mode
        set_chip("pn_chip_boost", f"Boost {BOOST_MODES.get(boost, '--').lower()}", "gold" if boost else "muted")
        if dpg.get_value("pn_boost") != BOOST_MODES.get(boost) and boost is not None:
            dpg.set_value("pn_boost", BOOST_MODES[boost])

        if snap.gpu is None:
            set_chip("pn_chip_gpu_lim", "GPU reconectando", "warn")
        elif snap.gpu["limits"]:
            set_chip("pn_chip_gpu_lim", f"GPU limitada: {', '.join(snap.gpu['limits'])}", "hot")
        else:
            set_chip("pn_chip_gpu_lim", "GPU sem limite", "ok")
        if snap.cpu_limits is None:
            set_chip("pn_chip_cpu_lim", "CPU limite: n/d", "muted")
        elif snap.cpu_limits["limits"]:
            set_chip("pn_chip_cpu_lim", f"CPU limitada: {', '.join(snap.cpu_limits['limits'])}", "hot")
        else:
            set_chip("pn_chip_cpu_lim", "CPU sem limite", "ok")

    def _update_tiles(self, snap: Snapshot):
        s = self.ctx.settings
        g = snap.gpu
        gpu_t = snap.gpu_temp
        dpg.set_value("pn_gpu_big", fmt(gpu_t, unit=" °C"))
        dpg.configure_item("pn_gpu_big", color=theme.rgba(theme.LEVEL_COLORS[
            level_for(gpu_t, s.alert_gpu_temp - 7, s.alert_gpu_temp)]))
        dpg.set_value("pn_gpu_sub", f"{fmt(g['clock_mhz'])} MHz · {fmt(g['power_w'])} W · {fmt(g['util_pct'])}% uso"
                      if g else "GPU indisponível — reconectando")

        c = snap.cpu
        cpu_t = snap.cpu_temp
        dpg.set_value("pn_cpu_big", fmt(cpu_t, unit=" °C"))
        dpg.configure_item("pn_cpu_big", color=theme.rgba(theme.LEVEL_COLORS[
            level_for(cpu_t, s.alert_cpu_temp - 10, s.alert_cpu_temp)]))
        clock = c.get("clock_mhz")
        dpg.set_value("pn_cpu_sub", f"{fmt(clock / 1000 if clock else None, '.1f')} GHz · "
                                    f"{fmt(c.get('power_w'))} W · {fmt(c.get('load_pct'))}% uso")

        e = snap.ec
        if e:
            rpm_c, rpm_g = e.get("cpu_fan_rpm"), e.get("gpu_fan_rpm")
            big = f"{rpm_c} / {rpm_g}" if rpm_c and rpm_g else f"{e['cpu_fan_pct']}% / {e['gpu_fan_pct']}%"
            dpg.set_value("pn_fan_big", big)
            dpg.set_value("pn_fan_sub", f"CPU / GPU · {fan_mode_label(snap)}"
                                        f"{' · Cooler Boost' if e.get('cooler_boost') else ''}")
        else:
            dpg.set_value("pn_fan_big", "--")
            dpg.set_value("pn_fan_sub", "EC indisponível (precisa de admin)")

        dpg.set_value("pn_sys_big", f"{snap.ram_used_gb:.1f} GB")
        vram = f"VRAM {g['mem_used_mb'] / 1024:.1f}/{g['mem_total_mb'] / 1024:.0f} GB" if g else "VRAM --"
        fps = f" · {snap.game['fps']:.0f} FPS" if snap.game else ""
        dpg.set_value("pn_sys_sub", f"de {snap.ram_total_gb:.0f} GB · {vram}{fps}")

    # ---------- gráfico ----------

    def _redraw_chart(self):
        h = self._hist
        if not h or not h.get("t"):
            return
        now = h["t"][-1]
        start = now - self.window_s
        idx = next((i for i, t in enumerate(h["t"]) if t >= start), 0)
        xs = [t - now for t in h["t"][idx:]]
        ymin, ymax = Y_RANGE[self.tab]
        gpu_key, cpu_key = SERIES[self.tab]
        gpu_y = h[gpu_key][idx:]
        cpu_y = h[cpu_key][idx:]
        if self.tab == "fan" and all(math.isnan(v) or v <= 100 for v in gpu_y + cpu_y):
            ymax = 100

        dpg.set_value(self.s_gpu, [xs, gpu_y])
        dpg.set_value(self.s_cpu, [xs, cpu_y])

        # faixa de alerta e linha de referência
        s = self.ctx.settings
        if self.tab == "temp":
            zone_lo = min(s.alert_gpu_temp, s.alert_cpu_temp)
            dpg.set_value(self.s_zone, [[-self.window_s, 0.0], [zone_lo, zone_lo], [ymax, ymax]])
            dpg.configure_item(self.s_zone, show=True)
            dpg.set_value(self.s_ref, [[float(self.ctx.gpu.slowdown_temp_c)]])
            dpg.configure_item(self.s_ref, show=True, label=f"GPU segura o clock em {self.ctx.gpu.slowdown_temp_c} °C")
        elif self.tab == "clock" and self.ctx.controller.state.gpu_lock:
            dpg.configure_item(self.s_zone, show=False)
            dpg.set_value(self.s_ref, [[float(self.ctx.controller.state.gpu_lock[1])]])
            dpg.configure_item(self.s_ref, show=True, label="Lock da GPU")
        else:
            dpg.configure_item(self.s_zone, show=False)
            dpg.configure_item(self.s_ref, show=False)

        # faixas verticais onde GPU ou CPU estavam sendo seguradas
        flags = LIMIT_FLAGS.get(self.tab)
        if flags:
            limited = [max(a, b) for a, b in zip(h[flags[0]][idx:], h[flags[1]][idx:])]
            dpg.set_value(self.s_limit, [xs, [ymin] * len(xs), [ymax if f else ymin for f in limited]])
            label = "Limitado por temperatura" if self.tab == "temp" else "Limitado por power"
            dpg.configure_item(self.s_limit, show=any(limited), label=label)
        else:
            dpg.configure_item(self.s_limit, show=False)

        dpg.set_axis_limits(self.x_axis, -self.window_s, 0)
        dpg.set_axis_limits(self.y_axis, ymin, ymax)
        step = self.window_s // 5
        ticks = [(("agora" if t == 0 else (f"-{t // 60} min" if self.window_s > 60 else f"-{t} s")), float(-t))
                 for t in range(self.window_s, -1, -step)]
        dpg.set_axis_ticks(self.x_axis, tuple(ticks))
        dpg.configure_item(self.y_axis, label=Y_UNIT[self.tab])

    def _update_hover(self):
        h = self._hist
        if not h or not h.get("t") or not dpg.is_item_hovered("pn_plot"):
            dpg.set_value("pn_hover", "Passe o mouse no gráfico pra ver os valores de cada instante.")
            return
        mx = dpg.get_plot_mouse_pos()[0]
        now = h["t"][-1]
        target = now + mx
        i = min(range(len(h["t"])), key=lambda k: abs(h["t"][k] - target))
        unit = Y_UNIT[self.tab]
        gk, ck = SERIES[self.tab]
        ago = int(round(now - h["t"][i]))

        def v(key):
            val = h[key][i]
            return "--" if math.isnan(val) else f"{val:.0f} {unit}"

        extra = ""
        flags = LIMIT_FLAGS.get(self.tab)
        if flags and (h[flags[0]][i] or h[flags[1]][i]):
            who = [n for n, k in (("GPU", flags[0]), ("CPU", flags[1])) if h[k][i]]
            extra = f" · limitado: {', '.join(who)}"
        when = "agora" if ago <= 0 else f"há {ago} s"
        dpg.set_value("pn_hover", f"{when} ({time.strftime('%H:%M:%S', time.localtime(h['t'][i]))}) · "
                                  f"GPU {v(gk)} · CPU {v(ck)}{extra}")
