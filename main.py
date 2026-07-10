"""Entrada do Master-Sword.

Achado da Fase 1: nem tudo precisa de admin.
- Boost da CPU (powercfg) funciona sem elevação.
- Lock de clock / power limit da GPU (NVML) precisa de admin.
- Sensores completos de CPU (temp/clock/power) precisam do driver PawnIO instalado + admin.
Por isso não forçamos elevação na abertura — cada ação que precisar de admin avisa na hora
(ver GpuControlError/CpuControlError) em vez de interromper o app inteiro.
"""

import ctypes
import logging
import sys
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / "master-sword.log"


def _setup_logging():
    """Loga em arquivo + captura qualquer exceção não tratada.

    O app é lançado por um atalho que roda o powershell minimizado (WindowStyle=7),
    então um traceback impresso no console pisca e some junto com a janela — foi por
    isso que os crashes vinham 'sem aviso'. Aqui garantimos que todo crash deixe
    rastro em master-sword.log.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    def _excepthook(exc_type, exc, tb):
        logging.getLogger("master_sword").critical(
            "Exceção não tratada — app encerrando", exc_info=(exc_type, exc, tb)
        )
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _excepthook


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main():
    _setup_logging()
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
