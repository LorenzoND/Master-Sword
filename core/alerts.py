"""Alertas de temperatura com histerese: entra no limite, sai só 3 °C abaixo (sem piscar)."""

import time
from typing import Callable

from core.sampler import Snapshot
from core.settings import Settings

HYSTERESIS_C = 3
COOLDOWN_S = 120


class Alerts:
    def __init__(self, settings: Settings, notify: Callable[[str, str], None]):
        self.settings = settings
        self._notify = notify  # (título, mensagem)
        self.gpu_hot = False
        self.cpu_hot = False
        self._last_notified = {"gpu": 0.0, "cpu": 0.0}

    def _check(self, key: str, temp, limit: int, currently: bool) -> bool:
        if temp is None:
            return False
        hot = temp >= limit if not currently else temp > limit - HYSTERESIS_C
        if hot and not currently and self.settings.alerts_enabled:
            now = time.monotonic()
            if now - self._last_notified[key] >= COOLDOWN_S:
                self._last_notified[key] = now
                self._notify(f"{key.upper()} quente: {temp:.0f} °C",
                             f"Passou do limite de alerta ({limit} °C).")
        return hot

    def update(self, snap: Snapshot):
        self.gpu_hot = self._check("gpu", snap.gpu_temp, self.settings.alert_gpu_temp, self.gpu_hot)
        self.cpu_hot = self._check("cpu", snap.cpu_temp, self.settings.alert_cpu_temp, self.cpu_hot)
