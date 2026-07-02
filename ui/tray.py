"""Ícone na bandeja: liga/desliga o overlay e permite sair do app."""

import sys
import threading
import subprocess
from pathlib import Path
from typing import Optional, Callable

import pystray

from ui.icon import load_tray_image

ROOT = Path(__file__).resolve().parent.parent


class TrayApp:
    def __init__(self, on_quit: Callable[[], None]):
        self._overlay_proc: Optional[subprocess.Popen] = None
        self._on_quit = on_quit
        self._icon = pystray.Icon(
            "master-sword",
            load_tray_image(),
            "Master-Sword",
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Overlay",
                    self._toggle_overlay,
                    checked=lambda item: self._overlay_proc is not None and self._overlay_proc.poll() is None,
                ),
                pystray.MenuItem("Sair", self._quit),
            ),
        )

    def start(self):
        threading.Thread(target=self._icon.run, daemon=True).start()

    def stop(self):
        """Chamado uma vez, no encerramento do app (seja pelo X da janela ou pelo 'Sair')."""
        if self._overlay_proc and self._overlay_proc.poll() is None:
            self._overlay_proc.terminate()
        self._icon.stop()

    def _toggle_overlay(self, icon, item):
        if self._overlay_proc and self._overlay_proc.poll() is None:
            self._overlay_proc.terminate()
            self._overlay_proc = None
        else:
            self._overlay_proc = subprocess.Popen(
                [sys.executable, "-m", "ui.overlay"], cwd=str(ROOT),
            )

    def _quit(self, icon, item):
        self._on_quit()
