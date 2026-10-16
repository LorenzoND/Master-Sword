"""Coleta de sensores numa thread própria, 1x por segundo.

Na v1 a leitura (NVML + LibreHardwareMonitor + powercfg) rodava dentro do loop de
renderização da janela, então qualquer leitura lenta travava a UI. Aqui a thread produz
um Snapshot e guarda o histórico; a UI e o overlay só leem o último Snapshot.
"""

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

import psutil

from core.controller import Controller
from core.cpu import CpuLimits, CpuSensors
from core.ec import MsiEc
from core.gpu import GpuController
from core.logsetup import log_throttled
from core.rtss import Rtss

log = logging.getLogger("master_sword.sampler")

INTERVAL_S = 1.0
HISTORY_LEN = 900  # 15 min a 1 Hz
BOOST_REFRESH_S = 10.0
NAN = math.nan

HISTORY_KEYS = (
    "t", "gpu_temp", "cpu_temp", "gpu_clock", "cpu_clock", "gpu_power", "cpu_power",
    "cpu_fan", "gpu_fan", "gpu_therm", "gpu_pwr", "cpu_therm", "cpu_pwr", "fps",
)


@dataclass
class Snapshot:
    t: float
    gpu: Optional[dict] = None
    cpu: dict = field(default_factory=dict)
    cpu_limits: Optional[dict] = None
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    ec: Optional[dict] = None
    game: Optional[dict] = None
    boost_mode: Optional[int] = None

    @property
    def gpu_temp(self) -> Optional[float]:
        if self.gpu:
            return self.gpu["temp_c"]
        return self.ec["gpu_temp_c"] if self.ec else None

    @property
    def cpu_temp(self) -> Optional[float]:
        if self.cpu.get("temp_c") is not None:
            return self.cpu["temp_c"]
        return self.ec["cpu_temp_c"] if self.ec else None


def _num(value) -> float:
    return NAN if value is None else float(value)


class Sampler(threading.Thread):
    def __init__(self, gpu: GpuController, cpu: Optional[CpuSensors], cpu_limits: Optional[CpuLimits],
                 ec: Optional[MsiEc], rtss: Rtss, controller: Controller):
        super().__init__(name="sampler", daemon=True)
        self.gpu = gpu
        self.cpu = cpu
        self.cpu_limits = cpu_limits
        self.ec = ec
        self.rtss = rtss
        self.controller = controller
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest: Optional[Snapshot] = None
        self._history = {k: deque(maxlen=HISTORY_LEN) for k in HISTORY_KEYS}
        self._listeners: list[Callable[[Snapshot], None]] = []
        self._last_boost_refresh = 0.0

    def add_listener(self, fn: Callable[[Snapshot], None]):
        self._listeners.append(fn)

    @property
    def latest(self) -> Optional[Snapshot]:
        with self._lock:
            return self._latest

    def history(self) -> dict[str, list[float]]:
        with self._lock:
            return {k: list(v) for k, v in self._history.items()}

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                snap = self._collect()
                self._publish(snap)
            except Exception:
                log_throttled("sampler", "Falha na coleta de sensores", level=logging.ERROR, exc_info=True)
            self._stop_event.wait(max(0.05, INTERVAL_S - (time.monotonic() - started)))

    def _collect(self) -> Snapshot:
        snap = Snapshot(t=time.time())
        snap.gpu = self.gpu.read_stats()

        if self.cpu is not None:
            try:
                snap.cpu = self.cpu.read_stats()
            except Exception:
                log_throttled("cpu_read", "Leitura da CPU falhou", exc_info=True)
        if self.cpu_limits is not None:
            try:
                snap.cpu_limits = self.cpu_limits.read()
            except Exception:
                log_throttled("cpu_limits", "Leitura do motivo de limite da CPU falhou", exc_info=True)

        mem = psutil.virtual_memory()
        snap.ram_used_gb = (mem.total - mem.available) / 1024 ** 3
        snap.ram_total_gb = mem.total / 1024 ** 3

        if self.ec is not None:
            try:
                snap.ec = self.ec.read_state()
            except Exception:
                log_throttled("ec_read", "Leitura do EC falhou", exc_info=True)

        try:
            snap.game = self.rtss.game_stats()
        except Exception:
            log_throttled("rtss_read", "Leitura do RTSS falhou", exc_info=True)

        now = time.monotonic()
        if now - self._last_boost_refresh >= BOOST_REFRESH_S:
            self._last_boost_refresh = now
            self.controller.refresh_boost()
        snap.boost_mode = self.controller.boost_mode
        return snap

    def _publish(self, snap: Snapshot):
        g = snap.gpu or {}
        lim = snap.cpu_limits or {}
        ec = snap.ec or {}
        row = {
            "t": snap.t,
            "gpu_temp": _num(snap.gpu_temp),
            "cpu_temp": _num(snap.cpu_temp),
            "gpu_clock": _num(g.get("clock_mhz")),
            "cpu_clock": _num(snap.cpu.get("clock_mhz")),
            "gpu_power": _num(g.get("power_w")),
            "cpu_power": _num(snap.cpu.get("power_w")),
            "cpu_fan": _num(ec.get("cpu_fan_pct")),
            "gpu_fan": _num(ec.get("gpu_fan_pct")),
            "gpu_therm": 1.0 if g.get("thermal_limited") else 0.0,
            "gpu_pwr": 1.0 if g.get("power_limited") else 0.0,
            "cpu_therm": 1.0 if lim.get("thermal_limited") else 0.0,
            "cpu_pwr": 1.0 if lim.get("power_limited") else 0.0,
            "fps": _num(snap.game["fps"]) if snap.game else NAN,
        }
        with self._lock:
            first = self._latest is None
            self._latest = snap
            for k, v in row.items():
                self._history[k].append(v)
        if first:
            # diagnóstico de uma linha: mostra no log o que cada fonte de sensor entregou
            log.info("Primeira leitura: GPU=%s | CPU temp=%s power=%s | CPU limites=%s | EC=%s | RTSS jogo=%s | boost=%s",
                     "ok" if snap.gpu else "indisponível", snap.cpu.get("temp_c"), snap.cpu.get("power_w"),
                     snap.cpu_limits, snap.ec, snap.game, snap.boost_mode)
        for fn in self._listeners:
            try:
                fn(snap)
            except Exception:
                log_throttled(f"listener_{getattr(fn, '__qualname__', fn)}", "Listener do sampler falhou",
                              level=logging.ERROR, exc_info=True)
