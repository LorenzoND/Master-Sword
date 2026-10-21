"""Objeto compartilhado entre as páginas: acesso ao controlador, sampler, configurações etc."""

import queue
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.controller import Controller
from core.ec import MsiEc
from core.gpu import GpuController
from core.overlay import OverlayManager
from core.sampler import Sampler
from core.settings import Settings


@dataclass
class Ctx:
    controller: Controller
    sampler: Sampler
    settings: Settings
    overlay: OverlayManager
    gpu: GpuController
    ec: Optional[MsiEc]
    cpu_name: str
    is_admin: bool
    ui_queue: "queue.Queue[Callable[[], None]]" = field(default_factory=queue.Queue)
    on_profiles_changed: list = field(default_factory=list)

    def run_on_ui(self, fn: Callable[[], None]):
        """Agenda algo pra rodar na thread da interface (bandeja e sampler rodam em outras)."""
        self.ui_queue.put(fn)

    def profiles_changed(self):
        for fn in self.on_profiles_changed:
            fn()
