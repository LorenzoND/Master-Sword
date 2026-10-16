"""Gerencia o overlay (RTSS in-game ou janela de desktop) a cada snapshot do sampler."""

import logging
import subprocess
from typing import Optional

from core import osd
from core.alerts import Alerts
from core.rtss import Rtss, install_path
from core.sampler import Snapshot
from core.settings import Settings, save_settings
from ui.desktop_overlay import DesktopOverlay

log = logging.getLogger("master_sword.overlay")


class OverlayManager:
    def __init__(self, settings: Settings, rtss: Rtss, alerts: Alerts):
        self.settings = settings
        self.rtss = rtss
        self.alerts = alerts
        self._desktop: Optional[DesktopOverlay] = None
        self.rtss_running = False

    def on_snapshot(self, snap: Snapshot):
        self.alerts.update(snap)
        s = self.settings
        active = s.overlay_visible and s.overlay_mode != "off"

        if active and s.overlay_mode == "rtss":
            self.rtss_running = self.rtss.update_osd(
                osd.rtss_text(snap, s, self.alerts.gpu_hot, self.alerts.cpu_hot),
                frametime_graph=s.overlay_items["frametime_graph"])
        else:
            self.rtss.release()
            self.rtss_running = self.rtss.is_running()

        if active and s.overlay_mode == "desktop":
            if self._desktop is None or not self._desktop.is_alive():
                self._desktop = DesktopOverlay(s.overlay_color, osd.ALERT_COLOR, s.overlay_position)
                self._desktop.start()
            self._desktop.configure(s.overlay_color, s.overlay_position)
            self._desktop.set_lines(osd.plain_lines(snap, s, self.alerts.gpu_hot, self.alerts.cpu_hot))
            self._desktop.set_visible(True)
        elif self._desktop is not None:
            self._desktop.set_visible(False)

    def toggle_visible(self):
        self.settings.overlay_visible = not self.settings.overlay_visible
        save_settings(self.settings)

    def start_rtss(self) -> bool:
        exe = install_path()
        if exe is None:
            return False
        subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=subprocess.DETACHED_PROCESS)
        return True

    def shutdown(self):
        self.rtss.release()
        if self._desktop is not None:
            self._desktop.stop()
