"""Entrada do Master-Sword.

Achado da Fase 1: nem tudo precisa de admin.
- Boost da CPU (powercfg) funciona sem elevação.
- Lock de clock / power limit da GPU (NVML) precisa de admin.
- Sensores completos de CPU (temp/clock/power) precisam do driver PawnIO instalado + admin.
Por isso não forçamos elevação na abertura — cada ação que precisar de admin avisa na hora
(ver GpuControlError/CpuControlError) em vez de interromper o app inteiro.
"""

import ctypes
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main():
    if not is_admin():
        print(
            "Master-Sword rodando sem privilégios de administrador.\n"
            "Lock de clock/power da GPU e sensores completos de CPU vão falhar até você "
            "rodar como admin (use o run_as_admin.bat).\n"
        )

    import dearpygui.dearpygui as dpg
    from ui.dashboard import run
    from ui.tray import TrayApp

    tray = TrayApp(on_quit=dpg.stop_dearpygui)
    tray.start()
    try:
        run()
    finally:
        tray.stop()


if __name__ == "__main__":
    sys.exit(main())
