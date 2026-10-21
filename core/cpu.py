"""CPU Intel: boost via Power Plan do Windows, sensores via LibreHardwareMonitor e motivo de limite via MSR.

- Boost (powercfg) não precisa de admin nem driver.
- Temperatura/clock/power e os MSRs precisam do driver PawnIO + processo elevado.
"""

import logging
import re
import subprocess
from typing import Optional

from core.logsetup import log_throttled

log = logging.getLogger("master_sword.cpu")

SUB_PROCESSOR = "SUB_PROCESSOR"
PERFBOOSTMODE = "PERFBOOSTMODE"

# índice do PERFBOOSTMODE -> nome em português
BOOST_MODES = {
    0: "Desligado",
    1: "Ligado",
    2: "Agressivo",
    3: "Eficiente",
    4: "Eficiente agressivo",
    5: "Agressivo garantido",
    6: "Eficiente agressivo garantido",
}


class CpuControlError(RuntimeError):
    pass


# ---------- boost (powercfg) ----------

def _powercfg(*args) -> str:
    result = subprocess.run(
        ["powercfg", *args], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
    )
    if result.returncode != 0:
        raise CpuControlError((result.stderr or result.stdout).strip() or "powercfg falhou")
    return result.stdout


def _ensure_boost_setting_visible():
    # PERFBOOSTMODE fica escondido por padrão; sem isso o /query não retorna nada pra ele.
    _powercfg("-attributes", SUB_PROCESSOR, PERFBOOSTMODE, "-ATTRIB_HIDE")


def _query_boost_values() -> list[str]:
    out = _powercfg("/query", "SCHEME_CURRENT", SUB_PROCESSOR, PERFBOOSTMODE)
    # A saída do powercfg vem traduzida conforme o idioma do Windows, então em vez de
    # procurar "Current AC Power Setting Index" pegamos os dois últimos índices hex (AC, DC).
    return re.findall(r":\s*0x([0-9a-fA-F]{8})\s*$", out, flags=re.MULTILINE)


def get_boost_mode() -> int:
    values = _query_boost_values()
    if len(values) < 2:
        _ensure_boost_setting_visible()
        values = _query_boost_values()
    if len(values) < 2:
        raise CpuControlError("Não consegui ler o modo de boost atual.")
    return int(values[-2], 16)


def set_boost_mode(index: int):
    """0 = desligado (o que o ThrottleStop fazia), 1 = ligado, 2 = agressivo, etc. Vale pra tomada e bateria."""
    if index not in BOOST_MODES:
        raise ValueError(f"modo de boost inválido: {index}")
    _ensure_boost_setting_visible()
    _powercfg("/setacvalueindex", "SCHEME_CURRENT", SUB_PROCESSOR, PERFBOOSTMODE, str(index))
    _powercfg("/setdcvalueindex", "SCHEME_CURRENT", SUB_PROCESSOR, PERFBOOSTMODE, str(index))
    _powercfg("/setactive", "SCHEME_CURRENT")


# ---------- sensores (LibreHardwareMonitor) ----------

class CpuSensors:
    """Wrapper do LibreHardwareMonitorLib (via pythonnet). Load funciona sempre;
    temperatura/clock/power precisam do PawnIO + admin."""

    def __init__(self):
        import HardwareMonitor.Hardware as Hardware

        self._computer = Hardware.Computer()
        self._computer.IsCpuEnabled = True
        self._computer.Open()
        self._cpu = next((hw for hw in self._computer.Hardware if str(hw.HardwareType) == "Cpu"), None)
        self.name = str(self._cpu.Name) if self._cpu is not None else "CPU"
        self._closed = False

    def close(self):
        if not self._closed:
            self._computer.Close()
            self._closed = True

    def read_stats(self) -> dict:
        stats = {"temp_c": None, "clock_mhz": None, "power_w": None, "load_pct": None, "core_loads": []}
        if self._cpu is None:
            return stats
        self._cpu.Update()
        core_loads: list[tuple[int, float]] = []
        clocks: list[float] = []
        for sensor in self._cpu.Sensors:
            kind = str(sensor.SensorType)
            name = str(sensor.Name)
            value = sensor.Value
            if value is None:
                continue
            value = float(value)
            if kind == "Load" and name == "CPU Total":
                stats["load_pct"] = value
            elif kind == "Load" and name.startswith("CPU Core #"):
                m = re.match(r"CPU Core #(\d+)(?: Thread #(\d+))?", name)
                if m:
                    core_loads.append((int(m.group(1)) * 10 + int(m.group(2) or 0), value))
            elif kind == "Temperature" and name == "CPU Package":
                stats["temp_c"] = value
            elif kind == "Clock" and name.startswith("CPU Core #"):
                clocks.append(value)
            elif kind == "Power" and name == "CPU Package" and value > 0:  # 0 = sensor sem acesso (sem admin)
                stats["power_w"] = value
        if clocks:
            stats["clock_mhz"] = max(clocks)
        stats["core_loads"] = [v for _, v in sorted(core_loads)]
        return stats


# ---------- motivo de limite (MSR via PawnIO) ----------

MSR_IA32_PACKAGE_THERM_STATUS = 0x1B1
MSR_PKG_PERF_STATUS = 0x613  # contador de tempo em que o pacote foi segurado por limite de power (RAPL)


class CpuLimits:
    """Lê se a CPU está sendo segurada por temperatura ou por limite de power (PL1/PL2).

    O registrador ideal (0x64F, "limit reasons" do ThrottleStop) é bloqueado pelo módulo
    IntelMSR do PawnIO, então usamos dois que ele libera pra leitura:
    - 0x1B1 bit 0: thermal monitor ativo (throttle térmico / PROCHOT)
    - 0x613: contador de throttle por power — se andou desde a última leitura, está limitado
    Só leitura; nada é escrito em MSR.
    """

    def __init__(self):
        from HardwareMonitor.PawnIo import IntelMsr

        self._msr = IntelMsr()
        self._last_perf: Optional[int] = None
        # Sem admin o PawnIO não carrega e o wrapper devolve 0 em vez de erro. O 0x1B1 nunca é 0
        # de verdade (bits 16-22 = distância até o TjMax), então 0 = acesso não funcionou.
        if self._read_msr(MSR_IA32_PACKAGE_THERM_STATUS) == 0:
            raise CpuControlError("PawnIO não respondeu (app sem admin ou driver ausente)")
        self.read()

    def _read_msr(self, index: int) -> int:
        from System import UInt32, UInt64

        try:
            ok, value = self._msr.ReadMsr(UInt32(index), UInt64(0))
            value = int(value)
        except TypeError:
            ok, lo, hi = self._msr.ReadMsr(UInt32(index), UInt32(0), UInt32(0))
            value = int(lo) | (int(hi) << 32)
        if not ok:
            raise CpuControlError(f"leitura do MSR {index:#x} falhou")
        return value

    def read(self) -> dict:
        therm = self._read_msr(MSR_IA32_PACKAGE_THERM_STATUS)
        perf = self._read_msr(MSR_PKG_PERF_STATUS) & 0xFFFFFFFF
        power_limited = self._last_perf is not None and perf != self._last_perf
        self._last_perf = perf
        thermal = bool(therm & 0x1)
        limits = []
        if thermal:
            limits.append("Térmico")
        if power_limited:
            limits.append("Power")
        return {"limits": limits, "thermal_limited": thermal, "power_limited": power_limited}

    def close(self):
        try:
            self._msr.Close()
        except Exception:
            pass


def try_create_limits() -> Optional[CpuLimits]:
    try:
        return CpuLimits()
    except Exception as exc:
        log_throttled("cpu_limits_init", "Motivo de limite da CPU indisponível (%s)", exc, level=logging.INFO)
        return None
