"""GPU NVIDIA via NVML (o mesmo backend do nvidia-smi): leitura, motivo de limite e lock de clock.

Reconexão automática: o log da v1 tinha ~43 mil `NVMLError_Unknown` seguidos (um surto
durou 12h) porque o handle da GPU morria (suspensão / reset do driver) e nunca era
recriado. Aqui qualquer erro de leitura derruba a sessão NVML e ela é refeita com backoff.
"""

import logging
import threading
import time
from typing import Callable, Optional

import psutil
import pynvml as nvml

log = logging.getLogger("master_sword.gpu")

# Motivos de limite de clock (bitmask do NVML) que importam pra quem joga.
# Ociosa / clock de aplicação / sync boost não são "limite", então ficam de fora.
_LIMIT_REASONS = [
    (nvml.nvmlClocksEventReasonSwThermalSlowdown, "Térmico"),
    (nvml.nvmlClocksEventReasonHwThermalSlowdown, "Térmico"),
    (nvml.nvmlClocksEventReasonSwPowerCap, "Power"),
    (nvml.nvmlClocksEventReasonHwPowerBrakeSlowdown, "Power"),
    (nvml.nvmlClocksEventReasonHwSlowdown, "Hardware"),
]
_THERMAL_MASK = nvml.nvmlClocksEventReasonSwThermalSlowdown | nvml.nvmlClocksEventReasonHwThermalSlowdown
_POWER_MASK = nvml.nvmlClocksEventReasonSwPowerCap | nvml.nvmlClocksEventReasonHwPowerBrakeSlowdown

DEFAULT_SLOWDOWN_C = 93  # valor lido da RTX 2060 do GS66; usado só se a leitura falhar


class GpuControlError(RuntimeError):
    pass


def limit_labels(reasons: int) -> list[str]:
    labels: list[str] = []
    for bit, label in _LIMIT_REASONS:
        if reasons & bit and label not in labels:
            labels.append(label)
    return labels


class GpuController:
    def __init__(self, index: int = 0):
        self._index = index
        self._lock = threading.RLock()
        self._handle = None
        self._inited = False
        self._retry_at = 0.0
        self._retry_delay = 2.0
        self.available = False
        self.name = "GPU NVIDIA"
        self.slowdown_temp_c = DEFAULT_SLOWDOWN_C
        self.max_clock_mhz = 2100
        self.on_reconnect: Optional[Callable[[], None]] = None
        self._ever_connected = False
        self._connect()

    # ---------- sessão NVML ----------

    def _connect(self) -> bool:
        try:
            nvml.nvmlInit()
            self._inited = True
            h = nvml.nvmlDeviceGetHandleByIndex(self._index)
            self.name = nvml.nvmlDeviceGetName(h)
            try:
                self.slowdown_temp_c = nvml.nvmlDeviceGetTemperatureThreshold(
                    h, nvml.NVML_TEMPERATURE_THRESHOLD_SLOWDOWN)
            except nvml.NVMLError:
                pass
            try:
                self.max_clock_mhz = nvml.nvmlDeviceGetMaxClockInfo(h, nvml.NVML_CLOCK_GRAPHICS)
            except nvml.NVMLError:
                pass
        except nvml.NVMLError as exc:
            self._shutdown()
            self._retry_at = time.monotonic() + self._retry_delay
            self._retry_delay = min(self._retry_delay * 2, 30.0)
            if not self._ever_connected:
                log.warning("NVML indisponível (%s) — tentando de novo em background", exc)
            return False

        reconnect = self._ever_connected
        self._handle = h
        self.available = True
        self._retry_delay = 2.0
        self._ever_connected = True
        if reconnect:
            log.info("NVML reconectado à GPU")
            if self.on_reconnect:
                try:
                    self.on_reconnect()
                except Exception:
                    log.exception("Falha ao reaplicar estado depois da reconexão")
        return True

    def _shutdown(self):
        if self._inited:
            try:
                nvml.nvmlShutdown()
            except nvml.NVMLError:
                pass
            self._inited = False
        self._handle = None

    def _drop(self, exc: Exception):
        log.warning("NVML perdeu a GPU (%s) — reconectando com backoff", exc)
        self.available = False
        self._shutdown()
        self._retry_at = time.monotonic() + self._retry_delay

    def ensure(self) -> bool:
        with self._lock:
            if self.available:
                return True
            if time.monotonic() < self._retry_at:
                return False
            return self._connect()

    def close(self):
        with self._lock:
            self.available = False
            self._shutdown()

    # ---------- leitura ----------

    def read_stats(self) -> Optional[dict]:
        """Snapshot da GPU, ou None se a GPU está indisponível (reconectando)."""
        if not self.ensure():
            return None
        with self._lock:
            h = self._handle
            try:
                mem = nvml.nvmlDeviceGetMemoryInfo(h)
                util = nvml.nvmlDeviceGetUtilizationRates(h)
                reasons = nvml.nvmlDeviceGetCurrentClocksEventReasons(h)
                stats = {
                    "temp_c": nvml.nvmlDeviceGetTemperature(h, nvml.NVML_TEMPERATURE_GPU),
                    "clock_mhz": nvml.nvmlDeviceGetClockInfo(h, nvml.NVML_CLOCK_GRAPHICS),
                    "clock_mem_mhz": nvml.nvmlDeviceGetClockInfo(h, nvml.NVML_CLOCK_MEM),
                    "power_w": nvml.nvmlDeviceGetPowerUsage(h) / 1000,
                    "mem_used_mb": mem.used // (1024 * 1024),
                    "mem_total_mb": mem.total // (1024 * 1024),
                    "util_pct": util.gpu,
                    "limits": limit_labels(reasons),
                    "thermal_limited": bool(reasons & _THERMAL_MASK),
                    "power_limited": bool(reasons & _POWER_MASK),
                }
            except nvml.NVMLError as exc:
                self._drop(exc)
                return None
            return stats

    # ---------- controle (precisa de admin) ----------

    def _call(self, fn, *args):
        if not self.ensure():
            raise GpuControlError("GPU indisponível no momento (NVML reconectando).")
        with self._lock:
            try:
                return fn(self._handle, *args)
            except nvml.NVMLError_NoPermission as exc:
                raise GpuControlError("Sem permissão pra alterar a GPU: o app precisa rodar como admin.") from exc
            except nvml.NVMLError_NotSupported as exc:
                raise GpuControlError("A GPU/driver não suporta esse controle.") from exc
            except nvml.NVMLError as exc:
                raise GpuControlError(f"NVML recusou o comando: {exc}") from exc

    def set_locked_clocks(self, min_mhz: int, max_mhz: int):
        """Equivalente a `nvidia-smi -lgc min,max`. Persiste no driver até soltar ou reiniciar."""
        if min_mhz > max_mhz:
            min_mhz, max_mhz = max_mhz, min_mhz
        self._call(nvml.nvmlDeviceSetGpuLockedClocks, min_mhz, max_mhz)

    def reset_locked_clocks(self):
        self._call(nvml.nvmlDeviceResetGpuLockedClocks)

    def list_processes(self) -> list[dict]:
        """Uso de VRAM por processo — o que o Gerenciador de Tarefas não mostra direito."""
        if not self.ensure():
            return []
        procs: dict[int, int] = {}
        with self._lock:
            h = self._handle
            for getter in (nvml.nvmlDeviceGetComputeRunningProcesses,
                           nvml.nvmlDeviceGetGraphicsRunningProcesses):
                try:
                    for p in getter(h):
                        procs[p.pid] = (p.usedGpuMemory or 0) // (1024 * 1024)
                except nvml.NVMLError:
                    pass
        result = []
        for pid, mem_mb in procs.items():
            try:
                name = psutil.Process(pid).name()
            except psutil.Error:
                name = "?"
            result.append({"pid": pid, "name": name, "gpu_mem_mb": mem_mb})
        return sorted(result, key=lambda r: r["gpu_mem_mb"], reverse=True)
