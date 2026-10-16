"""EC (embedded controller) do MSI GS66 Stealth 10SE: temperatura, fans, Cooler Boost, modos.

Acesso pelas portas padrão do ACPI EC (0x62 dados / 0x66 comando) através do módulo
LpcACPIEC do PawnIO (o mesmo driver que o LibreHardwareMonitor já usa — nada novo instalado).

Mapa de registradores: projeto msi-ec (Linux), config CONF_G1_3, que lista exatamente o
firmware deste notebook (16V1EMS1.118). Os endereços da curva de fan vêm do ECTweaker /
OpenFreezeCenter e são marcados como experimentais.

Segurança:
- Nada é escrito se o firmware lido do EC não estiver na lista conhecida.
- Toda escrita é confirmada lendo o registrador de volta.
- O acesso usa o mutex global "Global\\Access_EC", a convenção que LHM/HWiNFO usam pra não
  atropelar outra ferramenta no meio de uma transação.
"""

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from typing import Optional

log = logging.getLogger("master_sword.ec")

EC_DATA = 0x62
EC_CMD = 0x66
EC_OBF = 0x01  # output buffer cheio (dado pronto pra ler)
EC_IBF = 0x02  # input buffer cheio (EC ainda não consumiu o que mandamos)
RD_EC = 0x80
WR_EC = 0x81

FW_VERSION_ADDR = 0xA0
FW_VERSION_LEN = 12

# CONF_G1_3 do msi-ec ("GS66 Stealth 10SE" está nesta lista)
ALLOWED_FW = {
    "1541EMS1.113", "1542EMS1.101", "1542EMS1.102", "1542EMS1.104", "16Q2EMS1.105",
    "16Q2EMS1.106", "16Q2EMS1.107", "16Q2EMS1.T40", "16Q3EMS1.104", "16Q4EMS1.108",
    "16Q4EMS1.109", "16Q4EMS1.110", "16V1EMS1.109", "16V1EMS1.111", "16V1EMS1.112",
    "16V1EMS1.116", "16V1EMS1.118", "16V3EMS1.106", "17K2EMS1.104",
}

ADDR_CPU_TEMP = 0x68
ADDR_CPU_FAN = 0x71
ADDR_GPU_TEMP = 0x80
ADDR_GPU_FAN = 0x89
ADDR_COOLER_BOOST = 0x98
COOLER_BOOST_BIT = 7
ADDR_SHIFT_MODE = 0xF2
ADDR_FAN_MODE = 0xF4

# Tacômetro (experimental): 2 bytes big-endian, RPM = 478000 / valor
ADDR_CPU_TACH = 0xC8
ADDR_GPU_TACH = 0xCA

FAN_MODES = {"auto": 0x0D, "silent": 0x1D, "advanced": 0x8D}
FAN_MODE_LABELS = {"auto": "Automático", "silent": "Silencioso", "advanced": "Avançado (curva)"}
SHIFT_MODES = {"turbo": 0xC4, "sport": 0xC0, "comfort": 0xC1, "eco": 0xC2}
SHIFT_MODE_LABELS = {"turbo": "Turbo", "sport": "Sport", "comfort": "Comfort", "eco": "Eco"}

# Curva (experimental): 6 pontos de temperatura e 7 velocidades (%) por fan.
CURVE = {
    "cpu": {"temps": 0x6A, "speeds": 0x72},
    "gpu": {"temps": 0x82, "speeds": 0x8A},
}
CURVE_TEMPS = 6
CURVE_SPEEDS = 7
CURVE_MAX_SPEED = 150


class EcError(RuntimeError):
    pass


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

WAIT_OBJECT_0 = 0
WAIT_ABANDONED = 0x80


class _GlobalEcMutex:
    def __init__(self):
        self._handle = _kernel32.CreateMutexW(None, False, "Global\\Access_EC")
        self._local = threading.Lock()

    def __enter__(self):
        self._local.acquire()
        if self._handle:
            result = _kernel32.WaitForSingleObject(self._handle, 500)
            if result not in (WAIT_OBJECT_0, WAIT_ABANDONED):
                self._local.release()
                raise EcError("EC ocupado por outro programa (mutex Access_EC)")
        return self

    def __exit__(self, *exc):
        if self._handle:
            _kernel32.ReleaseMutex(self._handle)
        self._local.release()

    def close(self):
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


class MsiEc:
    def __init__(self):
        from HardwareMonitor.PawnIo import LpcAcpiEc

        self._io = LpcAcpiEc()
        self._mutex = _GlobalEcMutex()
        self.firmware = self._read_firmware()
        if not self.firmware:
            self.close()
            raise EcError("EC não respondeu (app sem admin ou driver PawnIO ausente)")
        self.supported = self.firmware in ALLOWED_FW
        log.info("EC firmware %s (%s)", self.firmware, "reconhecido" if self.supported else "NÃO reconhecido")

    def close(self):
        try:
            self._io.Close()
        except Exception:
            pass
        self._mutex.close()

    # ---------- protocolo ACPI EC ----------

    def _inb(self, port: int) -> int:
        from System import Byte
        return int(self._io.ReadPort(Byte(port)))

    def _outb(self, port: int, value: int):
        from System import Byte
        self._io.WritePort(Byte(port), Byte(value))

    def _wait(self, mask: int, want_set: bool):
        deadline = time.perf_counter() + 0.05
        while time.perf_counter() < deadline:
            status = self._inb(EC_CMD)
            if bool(status & mask) == want_set:
                return
        raise EcError("EC não respondeu a tempo")

    def _read_raw(self, addr: int) -> int:
        self._wait(EC_IBF, False)
        self._outb(EC_CMD, RD_EC)
        self._wait(EC_IBF, False)
        self._outb(EC_DATA, addr)
        self._wait(EC_OBF, True)
        return self._inb(EC_DATA)

    def _write_raw(self, addr: int, value: int):
        self._wait(EC_IBF, False)
        self._outb(EC_CMD, WR_EC)
        self._wait(EC_IBF, False)
        self._outb(EC_DATA, addr)
        self._wait(EC_IBF, False)
        self._outb(EC_DATA, value)
        self._wait(EC_IBF, False)

    def _read_with_retry(self, addr: int) -> int:
        last: Optional[Exception] = None
        for _ in range(3):
            try:
                return self._read_raw(addr)
            except EcError as exc:
                last = exc
        raise last  # type: ignore[misc]

    def read_bytes(self, addrs: list[int]) -> dict[int, int]:
        with self._mutex:
            return {a: self._read_with_retry(a) for a in addrs}

    def read_byte(self, addr: int) -> int:
        return self.read_bytes([addr])[addr]

    def write_byte(self, addr: int, value: int):
        """Escreve e confirma lendo de volta. Só funciona com firmware reconhecido."""
        if not self.supported:
            raise EcError(f"Firmware do EC ({self.firmware}) não está na lista conhecida — escrita bloqueada.")
        with self._mutex:
            for _ in range(3):
                self._write_raw(addr, value)
                if self._read_with_retry(addr) == value:
                    log.info("EC[%#04x] <- %#04x (confirmado)", addr, value)
                    return
        raise EcError(f"EC não confirmou a escrita em {addr:#04x}")

    def _read_firmware(self) -> str:
        try:
            raw = self.read_bytes(list(range(FW_VERSION_ADDR, FW_VERSION_ADDR + FW_VERSION_LEN)))
        except EcError:
            return ""
        text = "".join(chr(raw[a]) for a in sorted(raw))
        return text if text.isprintable() and text.strip("\x00 ") else ""

    # ---------- leitura de alto nível ----------

    @staticmethod
    def _rpm(hi: int, lo: int) -> Optional[int]:
        value = (hi << 8) | lo
        if value <= 0:
            return 0
        rpm = 478000 // value
        return rpm if 300 <= rpm <= 9000 else None

    def read_state(self) -> dict:
        addrs = [ADDR_CPU_TEMP, ADDR_CPU_FAN, ADDR_GPU_TEMP, ADDR_GPU_FAN, ADDR_COOLER_BOOST,
                 ADDR_SHIFT_MODE, ADDR_FAN_MODE, ADDR_CPU_TACH, ADDR_CPU_TACH + 1,
                 ADDR_GPU_TACH, ADDR_GPU_TACH + 1]
        b = self.read_bytes(addrs)
        fan_mode = next((k for k, v in FAN_MODES.items() if v == b[ADDR_FAN_MODE]), None)
        shift_mode = next((k for k, v in SHIFT_MODES.items() if v == b[ADDR_SHIFT_MODE]), None)
        return {
            "cpu_temp_c": b[ADDR_CPU_TEMP],
            "gpu_temp_c": b[ADDR_GPU_TEMP],
            "cpu_fan_pct": b[ADDR_CPU_FAN],
            "gpu_fan_pct": b[ADDR_GPU_FAN],
            "cpu_fan_rpm": self._rpm(b[ADDR_CPU_TACH], b[ADDR_CPU_TACH + 1]),
            "gpu_fan_rpm": self._rpm(b[ADDR_GPU_TACH], b[ADDR_GPU_TACH + 1]),
            "cooler_boost": bool(b[ADDR_COOLER_BOOST] >> COOLER_BOOST_BIT & 1),
            "fan_mode": fan_mode,
            "fan_mode_raw": b[ADDR_FAN_MODE],
            "shift_mode": shift_mode,
            "shift_mode_raw": b[ADDR_SHIFT_MODE],
        }

    def read_curve(self) -> dict:
        out = {}
        for fan, base in CURVE.items():
            temps = [base["temps"] + i for i in range(CURVE_TEMPS)]
            speeds = [base["speeds"] + i for i in range(CURVE_SPEEDS)]
            b = self.read_bytes(temps + speeds)
            out[fan] = {"temps": [b[a] for a in temps], "speeds": [b[a] for a in speeds]}
        return out

    @staticmethod
    def curve_looks_valid(curve: dict) -> bool:
        """Sanidade antes de liberar a edição: temperaturas crescentes num intervalo realista."""
        for fan in curve.values():
            temps, speeds = fan["temps"], fan["speeds"]
            if any(not 30 <= t <= 105 for t in temps) or temps != sorted(temps):
                return False
            if any(s > CURVE_MAX_SPEED for s in speeds):
                return False
        return True

    def dump(self) -> list[int]:
        with self._mutex:
            return [self._read_with_retry(a) for a in range(256)]

    # ---------- escrita de alto nível ----------

    def set_cooler_boost(self, on: bool):
        current = self.read_byte(ADDR_COOLER_BOOST)
        new = current | (1 << COOLER_BOOST_BIT) if on else current & ~(1 << COOLER_BOOST_BIT)
        if new != current:
            self.write_byte(ADDR_COOLER_BOOST, new)

    def set_fan_mode(self, mode: str):
        if mode not in FAN_MODES:
            raise ValueError(mode)
        self.write_byte(ADDR_FAN_MODE, FAN_MODES[mode])

    def set_shift_mode(self, mode: str):
        if mode not in SHIFT_MODES:
            raise ValueError(mode)
        self.write_byte(ADDR_SHIFT_MODE, SHIFT_MODES[mode])

    def set_curve_speeds(self, fan: str, speeds: list[int]):
        """Grava só as velocidades (as temperaturas dos pontos ficam as do fabricante).

        Regras pra não dar pra criar uma curva perigosa: 7 pontos, 0–150%, nunca
        decrescente e o último ponto (temperatura mais alta) no mínimo 80%.
        """
        if fan not in CURVE or len(speeds) != CURVE_SPEEDS:
            raise ValueError("curva inválida")
        if any(not 0 <= s <= CURVE_MAX_SPEED for s in speeds) or speeds != sorted(speeds):
            raise EcError("A curva precisa ser crescente e ficar entre 0 e 150%.")
        if speeds[-1] < 80:
            raise EcError("O último ponto da curva precisa ser pelo menos 80% (segurança térmica).")
        base = CURVE[fan]["speeds"]
        for i, s in enumerate(speeds):
            self.write_byte(base + i, s)


def try_create_ec() -> Optional[MsiEc]:
    try:
        return MsiEc()
    except Exception as exc:
        log.info("EC indisponível: %s", exc)
        return None
