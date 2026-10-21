"""Entrada do Master-Sword.

Roda com pythonw (sem janela de console). Sem admin, só dispara a tarefa agendada que sobe
o app elevado e sai (ver core/launcher.py). Com admin, inicia o hardware, a thread de
sensores, o overlay e a janela.

Flags: --minimized (começa só na bandeja) · --no-elevate (dev: roda mesmo sem admin)
"""

import logging
import sys

from core.logsetup import setup_logging

log = logging.getLogger("master_sword")


def main() -> int:
    setup_logging()
    minimized = "--minimized" in sys.argv

    from core.launcher import SingleInstance, elevate_via_uac, is_admin, run_task

    admin = is_admin()
    if not admin and "--no-elevate" not in sys.argv:
        if not run_task():
            log.info("Tarefa agendada não encontrada — pedindo elevação via UAC")
            elevate_via_uac()
        return 0

    instance = SingleInstance()
    if instance.already_running:
        instance.signal_existing()
        return 0

    from ui import theme
    theme.enable_dpi_awareness()

    from core import profiles
    from core.alerts import Alerts
    from core.controller import Controller
    from core.cpu import CpuSensors, try_create_limits
    from core.ec import try_create_ec
    from core.gpu import GpuController
    from core.overlay import OverlayManager
    from core.rtss import Rtss
    from core.sampler import Sampler
    from core.settings import load_settings
    from core.state import StateStore
    from ui.app import App
    from ui.context import Ctx

    log.info("Master-Sword iniciando (admin=%s)", admin)
    gpu = GpuController()
    cpu = None
    try:
        cpu = CpuSensors()
    except Exception:
        log.exception("Sensores da CPU indisponíveis")
    cpu_limits = try_create_limits() if admin else None
    ec = try_create_ec() if admin else None

    settings = load_settings()
    store = StateStore()
    profiles.seed_default_profiles()
    profiles.list_profiles()  # converte perfis da v1, se houver

    controller = Controller(gpu, ec, settings, store)
    rtss = Rtss()
    sampler = Sampler(gpu, cpu, cpu_limits, ec, rtss, controller)

    app_ref = {}
    alerts = Alerts(settings, notify=lambda title, msg: app_ref["app"].tray.notify(title, msg))
    overlay = OverlayManager(settings, rtss, alerts)
    sampler.add_listener(overlay.on_snapshot)

    ctx = Ctx(controller=controller, sampler=sampler, settings=settings, overlay=overlay, gpu=gpu, ec=ec,
              cpu_name=cpu.name if cpu else "CPU", is_admin=admin)
    app = App(ctx, instance, minimized)
    app_ref["app"] = app

    controller.startup()
    sampler.start()
    try:
        app.run()
    finally:
        log.info("Master-Sword encerrando")
        sampler.stop()
        sampler.join(timeout=3)
        overlay.shutdown()
        controller.shutdown()
        gpu.close()
        if cpu:
            cpu.close()
        if cpu_limits:
            cpu_limits.close()
        if ec:
            ec.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
