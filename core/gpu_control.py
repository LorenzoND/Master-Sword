"""Controle e leitura da GPU NVIDIA via NVML (o mesmo backend do nvidia-smi)."""

import pynvml as nvml
import psutil


class GpuControlError(RuntimeError):
    pass


def _require_admin(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except nvml.NVMLError_NoPermission as exc:
            raise GpuControlError(
                "Sem permissão pra alterar a GPU — rode o Master-Sword como administrador."
            ) from exc
        except nvml.NVMLError_NotSupported as exc:
            raise GpuControlError(
                "A GPU/driver não suporta esse controle (comum em GPU de notebook, "
                "o power limit costuma vir travado pelo vBIOS do fabricante)."
            ) from exc
    return wrapper


class GpuController:
    def __init__(self, index: int = 0):
        nvml.nvmlInit()
        self._handle = nvml.nvmlDeviceGetHandleByIndex(index)
        self._closed = False
        # NVML não expõe leitura do lock atual — só temos o que a gente mesmo aplicou nesta sessão.
        self.locked_clock_range: tuple[int, int] | None = None

    def close(self):
        if not self._closed:
            nvml.nvmlShutdown()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    @property
    def name(self) -> str:
        return nvml.nvmlDeviceGetName(self._handle)

    def read_stats(self) -> dict:
        h = self._handle
        mem = nvml.nvmlDeviceGetMemoryInfo(h)
        util = nvml.nvmlDeviceGetUtilizationRates(h)
        try:
            power_limit_w = nvml.nvmlDeviceGetPowerManagementLimit(h) / 1000
        except nvml.NVMLError:
            power_limit_w = None

        return {
            "temp_c": nvml.nvmlDeviceGetTemperature(h, nvml.NVML_TEMPERATURE_GPU),
            "clock_graphics_mhz": nvml.nvmlDeviceGetClockInfo(h, nvml.NVML_CLOCK_GRAPHICS),
            "clock_sm_mhz": nvml.nvmlDeviceGetClockInfo(h, nvml.NVML_CLOCK_SM),
            "clock_mem_mhz": nvml.nvmlDeviceGetClockInfo(h, nvml.NVML_CLOCK_MEM),
            "power_w": nvml.nvmlDeviceGetPowerUsage(h) / 1000,
            "power_limit_w": power_limit_w,
            "mem_used_mb": mem.used // (1024 * 1024),
            "mem_total_mb": mem.total // (1024 * 1024),
            "util_gpu_pct": util.gpu,
            "util_mem_pct": util.memory,
            "locked_clock_min_mhz": self.locked_clock_range[0] if self.locked_clock_range else None,
            "locked_clock_max_mhz": self.locked_clock_range[1] if self.locked_clock_range else None,
        }

    def power_limit_range_w(self) -> tuple[float, float]:
        min_mw, max_mw = nvml.nvmlDeviceGetPowerManagementLimitConstraints(self._handle)
        return min_mw / 1000, max_mw / 1000

    @_require_admin
    def set_locked_clocks(self, min_mhz: int, max_mhz: int):
        """Equivalente a `nvidia-smi -lgc min,max`."""
        nvml.nvmlDeviceSetGpuLockedClocks(self._handle, min_mhz, max_mhz)
        self.locked_clock_range = (min_mhz, max_mhz)

    @_require_admin
    def reset_locked_clocks(self):
        nvml.nvmlDeviceResetGpuLockedClocks(self._handle)
        self.locked_clock_range = None

    @_require_admin
    def set_power_limit_w(self, watts: float):
        nvml.nvmlDeviceSetPowerManagementLimit(self._handle, int(watts * 1000))

    def list_processes(self) -> list[dict]:
        """Uso de GPU por processo — o que o Task Manager não mostra direito."""
        h = self._handle
        procs: dict[int, dict] = {}

        try:
            for p in nvml.nvmlDeviceGetComputeRunningProcesses(h):
                procs.setdefault(p.pid, {})["gpu_mem_mb"] = (p.usedGpuMemory or 0) // (1024 * 1024)
        except nvml.NVMLError:
            pass

        try:
            for p in nvml.nvmlDeviceGetGraphicsRunningProcesses(h):
                procs.setdefault(p.pid, {})["gpu_mem_mb"] = (p.usedGpuMemory or 0) // (1024 * 1024)
        except nvml.NVMLError:
            pass

        try:
            for s in nvml.nvmlDeviceGetProcessUtilization(h, 0):
                if s.pid in procs:
                    procs[s.pid]["sm_pct"] = s.smUtil
        except nvml.NVMLError:
            pass

        result = []
        for pid, data in procs.items():
            try:
                name = psutil.Process(pid).name()
            except psutil.NoSuchProcess:
                name = "?"
            result.append({"pid": pid, "name": name, "sm_pct": 0, **data})

        return sorted(result, key=lambda r: r.get("gpu_mem_mb", 0), reverse=True)
