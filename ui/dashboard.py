"""Janela principal: gráficos ao vivo (GPU/CPU) + controles de clock, boost e perfis."""

import logging
import os
import time
from collections import deque

import dearpygui.dearpygui as dpg

from core.gpu_control import GpuController, GpuControlError
from core.cpu_control import CpuControlError, get_boost_mode_index, set_boost_mode
from core import profiles as profiles_mod
from core import live_state
from ui.process_window import ProcessWindow
from ui import theme
from ui.icon import ICON_ICO_PATH, ensure_icon_assets

HISTORY_LEN = 120
POLL_INTERVAL_S = 1.5


class Dashboard:
    def __init__(self):
        self.gpu = GpuController()

        self.cpu_sensors = None
        try:
            from core.cpu_control import CpuSensors
            self.cpu_sensors = CpuSensors()
        except Exception:
            pass  # segue sem sensor de CPU (temp/clock/power ficam N/A)

        self.process_window = ProcessWindow(self.gpu)

        self.t0 = time.time()
        self.last_poll = 0.0
        self.boost_enabled = False
        self.history = {k: deque(maxlen=HISTORY_LEN) for k in (
            "t", "gpu_temp", "gpu_clock", "gpu_power", "cpu_temp", "cpu_power",
        )}

    def close(self):
        self.gpu.close()
        if self.cpu_sensors:
            self.cpu_sensors.close()

    # ---------- UI ----------

    def build_ui(self):
        with dpg.window(tag="main_window"):
            with dpg.group(horizontal=True):
                self._build_stat_card("GPU", theme.BLADE_BLUE, [
                    ("lbl_gpu_temp", "Temp"), ("lbl_gpu_clock", "Clock"),
                    ("lbl_gpu_power", "Power"), ("lbl_gpu_mem", "VRAM"),
                ])
                self._build_stat_card("CPU", theme.GOLD, [
                    ("lbl_cpu_temp", "Temp"), ("lbl_cpu_clock", "Clock"),
                    ("lbl_cpu_power", "Power"), ("lbl_cpu_load", "Load"),
                ])

            dpg.add_spacer(height=8)

            with dpg.plot(label="Temperatura (C)", height=160, width=-1):
                dpg.add_plot_legend()
                x1 = dpg.add_plot_axis(dpg.mvXAxis, label="s")
                y1 = dpg.add_plot_axis(dpg.mvYAxis, label="C")
                dpg.add_line_series([], [], label="GPU", parent=y1, tag="series_gpu_temp")
                dpg.add_line_series([], [], label="CPU", parent=y1, tag="series_cpu_temp")
                dpg.bind_item_theme("series_gpu_temp", theme.line_theme(theme.BLADE_BLUE))
                dpg.bind_item_theme("series_cpu_temp", theme.line_theme(theme.GOLD))
                self._temp_axes = (x1, y1)

            with dpg.plot(label="Clock GPU (MHz)", height=160, width=-1):
                dpg.add_plot_legend()
                x2 = dpg.add_plot_axis(dpg.mvXAxis, label="s")
                y2 = dpg.add_plot_axis(dpg.mvYAxis, label="MHz")
                dpg.add_line_series([], [], label="GPU clock", parent=y2, tag="series_gpu_clock")
                dpg.bind_item_theme("series_gpu_clock", theme.line_theme(theme.BLADE_BLUE))
                self._clock_axes = (x2, y2)

            with dpg.plot(label="Power (W)", height=160, width=-1):
                dpg.add_plot_legend()
                x3 = dpg.add_plot_axis(dpg.mvXAxis, label="s")
                y3 = dpg.add_plot_axis(dpg.mvYAxis, label="W")
                dpg.add_line_series([], [], label="GPU", parent=y3, tag="series_gpu_power")
                dpg.add_line_series([], [], label="CPU", parent=y3, tag="series_cpu_power")
                dpg.bind_item_theme("series_gpu_power", theme.line_theme(theme.BLADE_BLUE))
                dpg.bind_item_theme("series_cpu_power", theme.line_theme(theme.GOLD))
                self._power_axes = (x3, y3)

            dpg.add_spacer(height=8)
            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_text("Lock de clock da GPU (MHz):")
                dpg.add_input_int(tag="input_gpu_min", default_value=900, width=90, min_value=0, min_clamped=True)
                dpg.add_text("a")
                dpg.add_input_int(tag="input_gpu_max", default_value=900, width=90, min_value=0, min_clamped=True)
                dpg.add_button(label="Aplicar", callback=self.apply_gpu_lock)
                dpg.add_button(label="Soltar lock", callback=self.reset_gpu_lock)

            with dpg.group(horizontal=True):
                dpg.add_checkbox(label="Boost/Turbo da CPU", tag="chk_boost", callback=self.toggle_boost)
                dpg.add_button(label="Processos...", callback=lambda: self.process_window.toggle())

            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_combo(tag="combo_profiles", width=200)
                dpg.add_button(label="Aplicar perfil", callback=self.apply_selected_profile)
                dpg.add_input_text(tag="input_profile_name", hint="nome do perfil", width=160)
                dpg.add_button(label="Salvar atual como perfil", callback=self.save_current_profile)

            dpg.add_spacer(height=6)
            dpg.add_text("", tag="lbl_status", color=theme.TEXT_MUTED)

    def _build_stat_card(self, title, title_color, fields):
        with dpg.child_window(width=280, height=120):
            dpg.add_text(title, color=title_color)
            dpg.add_separator()
            for tag, label in fields:
                with dpg.group(horizontal=True):
                    dpg.add_text(f"{label}:")
                    dpg.add_text("--", tag=tag)

    # ---------- estado / lógica ----------

    def set_status(self, msg, error=False):
        dpg.set_value("lbl_status", msg)
        dpg.configure_item("lbl_status", color=theme.ERROR if error else theme.TEXT_MUTED)

    def apply_gpu_lock(self):
        min_mhz = dpg.get_value("input_gpu_min")
        max_mhz = dpg.get_value("input_gpu_max")
        try:
            self.gpu.set_locked_clocks(min_mhz, max_mhz)
            self.set_status(f"Clock da GPU travado em {min_mhz}-{max_mhz} MHz")
        except GpuControlError as exc:
            self.set_status(str(exc), error=True)

    def reset_gpu_lock(self):
        try:
            self.gpu.reset_locked_clocks()
            self.set_status("Lock de clock removido")
        except GpuControlError as exc:
            self.set_status(str(exc), error=True)

    def toggle_boost(self, sender, checked):
        try:
            set_boost_mode(1 if checked else 0)
            self.boost_enabled = checked
            self.set_status(f"Boost da CPU {'ligado' if checked else 'desligado'}")
        except CpuControlError as exc:
            dpg.set_value("chk_boost", not checked)
            self.set_status(str(exc), error=True)

    def refresh_profile_list(self):
        items = profiles_mod.list_profiles()
        dpg.configure_item("combo_profiles", items=items)
        if items:
            dpg.set_value("combo_profiles", items[0])

    def save_current_profile(self):
        name = dpg.get_value("input_profile_name").strip()
        if not name:
            self.set_status("Dá um nome pro perfil antes de salvar", error=True)
            return
        profile = profiles_mod.Profile(
            name=name,
            gpu_clock_min_mhz=dpg.get_value("input_gpu_min"),
            gpu_clock_max_mhz=dpg.get_value("input_gpu_max"),
            cpu_boost_mode=1 if dpg.get_value("chk_boost") else 0,
        )
        profiles_mod.save_profile(profile)
        self.refresh_profile_list()
        self.set_status(f"Perfil '{name}' salvo")

    def apply_selected_profile(self):
        name = dpg.get_value("combo_profiles")
        if not name:
            return
        profile = profiles_mod.load_profile(name)
        warnings = profiles_mod.apply_profile(profile, self.gpu)
        self.set_status(" | ".join(warnings) if warnings else f"Perfil '{name}' aplicado", error=bool(warnings))

    # ---------- polling ----------

    def poll(self):
        now = time.time()
        if now - self.last_poll < POLL_INTERVAL_S:
            return
        self.last_poll = now

        gpu_stats = self.gpu.read_stats()
        cpu_stats = self.cpu_sensors.read_stats() if self.cpu_sensors else {}

        t = now - self.t0
        self.history["t"].append(t)
        self.history["gpu_temp"].append(gpu_stats["temp_c"])
        self.history["gpu_clock"].append(gpu_stats["clock_graphics_mhz"])
        self.history["gpu_power"].append(gpu_stats["power_w"])
        self.history["cpu_temp"].append(cpu_stats.get("temp_package_c") or 0)
        self.history["cpu_power"].append(cpu_stats.get("power_package_w") or 0)

        dpg.set_value("lbl_gpu_temp", f"{gpu_stats['temp_c']} C")
        dpg.set_value("lbl_gpu_clock", f"{gpu_stats['clock_graphics_mhz']} MHz")
        dpg.set_value("lbl_gpu_power", f"{gpu_stats['power_w']:.1f} W")
        dpg.set_value("lbl_gpu_mem", f"{gpu_stats['mem_used_mb']} / {gpu_stats['mem_total_mb']} MB")

        cpu_temp = cpu_stats.get("temp_package_c")
        cpu_clock = cpu_stats.get("clock_max_mhz")
        cpu_power = cpu_stats.get("power_package_w")
        cpu_load = cpu_stats.get("load_total_pct")
        dpg.set_value("lbl_cpu_temp", f"{cpu_temp:.0f} C" if cpu_temp else "N/A")
        dpg.set_value("lbl_cpu_clock", f"{cpu_clock:.0f} MHz" if cpu_clock else "N/A")
        dpg.set_value("lbl_cpu_power", f"{cpu_power:.1f} W" if cpu_power else "N/A")
        dpg.set_value("lbl_cpu_load", f"{cpu_load:.0f}%" if cpu_load is not None else "N/A")

        t_list = list(self.history["t"])
        dpg.set_value("series_gpu_temp", [t_list, list(self.history["gpu_temp"])])
        dpg.set_value("series_cpu_temp", [t_list, list(self.history["cpu_temp"])])
        dpg.set_value("series_gpu_clock", [t_list, list(self.history["gpu_clock"])])
        dpg.set_value("series_gpu_power", [t_list, list(self.history["gpu_power"])])
        dpg.set_value("series_cpu_power", [t_list, list(self.history["cpu_power"])])

        for x_axis, y_axis in (self._temp_axes, self._clock_axes, self._power_axes):
            dpg.fit_axis_data(x_axis)
            dpg.fit_axis_data(y_axis)

        live_state.write({
            "gpu_temp_c": gpu_stats["temp_c"],
            "gpu_clock_mhz": gpu_stats["clock_graphics_mhz"],
            "gpu_power_w": gpu_stats["power_w"],
            "cpu_temp_c": cpu_temp,
            "cpu_power_w": cpu_power,
            "cpu_load_pct": cpu_load,
            "boost_enabled": self.boost_enabled,
        })


def run():
    ensure_icon_assets()
    dpg.create_context()
    theme.apply_global()
    board = Dashboard()
    board.build_ui()
    dpg.create_viewport(
        title="Master-Sword", width=780, height=760,
        small_icon=str(ICON_ICO_PATH), large_icon=str(ICON_ICO_PATH),
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main_window", True)

    profiles_mod.seed_default_profiles()
    board.refresh_profile_list()
    board.boost_enabled = get_boost_mode_index() != 0
    dpg.set_value("chk_boost", board.boost_enabled)

    test_frames = os.environ.get("MASTER_SWORD_TEST_FRAMES")
    frame_count = 0
    try:
        while dpg.is_dearpygui_running():
            try:
                board.poll()
            except Exception:
                # Uma leitura de sensor (NVML/LibreHardwareMonitor) ou o write do
                # live_state pode falhar de forma transiente — GPU híbrida dormindo,
                # arquivo travado por outro processo, etc. Registra e segue: um poll
                # perdido não pode derrubar o app inteiro (era a causa do "fecha sozinho").
                logging.getLogger("master_sword").exception("Falha no poll — pulando este ciclo")
            dpg.render_dearpygui_frame()
            frame_count += 1
            if test_frames and frame_count >= int(test_frames):
                break
    finally:
        board.close()
        dpg.destroy_context()


if __name__ == "__main__":
    run()
