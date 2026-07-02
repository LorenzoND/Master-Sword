"""Boost/turbo da CPU via Power Plan do Windows + leitura de sensores via LibreHardwareMonitor."""

import subprocess

SUB_PROCESSOR = "SUB_PROCESSOR"
PERFBOOSTMODE = "PERFBOOSTMODE"

BOOST_MODES = {
    0: "Disabled",
    1: "Enabled",
    2: "Aggressive",
    3: "Efficient Enabled",
    4: "Efficient Aggressive",
    5: "Aggressive At Guaranteed",
    6: "Efficient Aggressive At Guaranteed",
}


class CpuControlError(RuntimeError):
    pass


def _powercfg(*args) -> str:
    result = subprocess.run(
        ["powercfg", *args], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
    )
    if result.returncode != 0:
        raise CpuControlError((result.stderr or result.stdout).strip())
    return result.stdout


def _ensure_boost_setting_visible():
    # PERFBOOSTMODE fica escondido por padrão do powercfg; sem isso /query não retorna nada pra ele.
    _powercfg("-attributes", SUB_PROCESSOR, PERFBOOSTMODE, "-ATTRIB_HIDE")


def get_boost_mode_index() -> int:
    _ensure_boost_setting_visible()
    out = _powercfg("/query", "SCHEME_CURRENT", SUB_PROCESSOR, PERFBOOSTMODE)
    for line in out.splitlines():
        if "Current AC Power Setting Index" in line:
            return int(line.strip().split(":")[1].strip(), 16)
    raise CpuControlError("Não consegui ler o boost mode atual (setting ausente no /query).")


def is_boost_enabled() -> bool:
    return get_boost_mode_index() != 0


def set_boost_mode(index: int):
    """0 = Disabled (equivalente ao boost off do ThrottleStop), 1 = Enabled, 2 = Aggressive, etc."""
    if index not in BOOST_MODES:
        raise ValueError(f"index de boost mode inválido: {index}")
    _ensure_boost_setting_visible()
    _powercfg("/setacvalueindex", "SCHEME_CURRENT", SUB_PROCESSOR, PERFBOOSTMODE, str(index))
    _powercfg("/setdcvalueindex", "SCHEME_CURRENT", SUB_PROCESSOR, PERFBOOSTMODE, str(index))
    _powercfg("/setactive", "SCHEME_CURRENT")


def set_boost_enabled(enabled: bool):
    set_boost_mode(1 if enabled else 0)


class CpuSensors:
    """Wrapper do LibreHardwareMonitorLib (via pythonnet). Load funciona sempre;
    Temperature/Clock/Power precisam do driver PawnIO instalado + processo elevado."""

    def __init__(self):
        import HardwareMonitor.Hardware as Hardware

        self._computer = Hardware.Computer()
        self._computer.IsCpuEnabled = True
        self._computer.IsMemoryEnabled = True
        self._computer.Open()
        self._closed = False

    def close(self):
        if not self._closed:
            self._computer.Close()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def read_stats(self) -> dict:
        stats = {
            "temp_package_c": None,
            "clock_max_mhz": None,
            "power_package_w": None,
            "load_total_pct": None,
        }
        for hw in self._computer.Hardware:
            if str(hw.HardwareType) != "Cpu":
                continue
            hw.Update()
            for sensor in hw.Sensors:
                sensor_type = str(sensor.SensorType)
                name = str(sensor.Name)
                value = sensor.Value

                if sensor_type == "Load" and name == "CPU Total":
                    stats["load_total_pct"] = value
                elif sensor_type == "Temperature" and name == "CPU Package":
                    stats["temp_package_c"] = value
                elif sensor_type == "Clock" and name.startswith("CPU Core") and value is not None:
                    stats["clock_max_mhz"] = max(stats["clock_max_mhz"] or 0, value)
                elif sensor_type == "Power" and name == "CPU Package":
                    stats["power_package_w"] = value

        return stats
