"""Overlay leve, always-on-top: mostra os stats mais recentes lidos do dashboard principal.

Roda como processo separado (não como segunda janela do mesmo processo) porque o Dear PyGui
não suporta múltiplos viewports OS-level num único processo. A comunicação é por um arquivo
JSON (core/live_state.py) que o dashboard principal escreve a cada ciclo de poll.

Limitação conhecida: esta versão do Dear PyGui (2.3.1) não expõe transparência/clickthrough
de viewport (as funções set_viewport_transparency/set_viewport_clickthrough não existem aqui,
só em builds mais recentes). Por isso o overlay é uma janela pequena, sem borda, sempre no
topo, mas opaca — não "flutua" por cima do jogo de forma transparente.
"""

import ctypes
import os
import time

import dearpygui.dearpygui as dpg

from core.live_state import read as read_live_state
from ui import theme
from ui.icon import ICON_ICO_PATH, ensure_icon_assets

WIDTH, HEIGHT = 230, 130
POLL_INTERVAL_S = 1.0


def _top_right_pos() -> tuple[int, int]:
    try:
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        return screen_w - WIDTH - 20, 20
    except Exception:
        return 100, 100


def build_ui():
    with dpg.window(tag="overlay_window", no_title_bar=True, no_resize=True,
                     no_collapse=True, no_scrollbar=True):
        dpg.add_text("Master-Sword", color=theme.GOLD)
        dpg.add_separator()
        dpg.add_text("GPU  aguardando dados...", tag="lbl_gpu")
        dpg.add_text("CPU  aguardando dados...", tag="lbl_cpu")
        dpg.add_text("Boost: --", tag="lbl_boost")


def poll():
    stats = read_live_state()
    if not stats:
        dpg.set_value("lbl_gpu", "GPU sem dados — abra o dashboard principal")
        dpg.set_value("lbl_cpu", "")
        return

    gpu_power = stats.get("gpu_power_w") or 0.0
    dpg.set_value(
        "lbl_gpu",
        f"GPU {stats.get('gpu_temp_c', '--')}C  {stats.get('gpu_clock_mhz', '--')}MHz  {gpu_power:.1f}W",
    )

    cpu_temp = stats.get("cpu_temp_c")
    cpu_load = stats.get("cpu_load_pct") or 0
    cpu_line = f"CPU {cpu_temp:.0f}C  {cpu_load:.0f}% load" if cpu_temp else f"CPU --C  {cpu_load:.0f}% load"
    dpg.set_value("lbl_cpu", cpu_line)

    dpg.set_value("lbl_boost", f"Boost: {'ligado' if stats.get('boost_enabled') else 'desligado'}")


def run():
    ensure_icon_assets()
    dpg.create_context()
    theme.apply_global()
    build_ui()
    x, y = _top_right_pos()
    dpg.create_viewport(
        title="Master-Sword overlay", width=WIDTH, height=HEIGHT,
        x_pos=x, y_pos=y, decorated=False, always_on_top=True, resizable=False,
        clear_color=theme.BG_DARK, small_icon=str(ICON_ICO_PATH), large_icon=str(ICON_ICO_PATH),
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("overlay_window", True)

    test_frames = os.environ.get("MASTER_SWORD_TEST_FRAMES")
    frame_count = 0
    last_poll = 0.0
    try:
        while dpg.is_dearpygui_running():
            now = time.time()
            if now - last_poll >= POLL_INTERVAL_S:
                poll()
                last_poll = now
            dpg.render_dearpygui_frame()
            frame_count += 1
            if test_frames and frame_count >= int(test_frames):
                break
    finally:
        dpg.destroy_context()


if __name__ == "__main__":
    run()
