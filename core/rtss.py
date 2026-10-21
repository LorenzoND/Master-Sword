"""Integração com o RivaTuner Statistics Server (RTSS) pela memória compartilhada oficial.

É o mesmo caminho que o MSI Afterburner e o HWiNFO usam pra desenhar o OSD dentro do jogo:
o app escreve o texto num "slot" da memória compartilhada `RTSSSharedMemoryV2` e o RTSS
desenha por cima do jogo — transparente, sem pegar clique, funcionando em tela cheia
exclusiva. Também lemos daqui o FPS/frametime do jogo em primeiro plano.

Layout das structs: RTSSSharedMemory.h do SDK que vem com o RTSS instalado.
"""

import ctypes
import logging
import struct
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Optional

log = logging.getLogger("master_sword.rtss")

MAPPING_NAME = "RTSSSharedMemoryV2"
SIGNATURE = 0x52545353  # 'RTSS'
GRAPH_SIGNATURE = 0x47523030  # 'GR00'
OWNER = b"Master-Sword"

GRAPH_FLAG_FILLED = 1
GRAPH_FLAG_FRAMETIME = 4

# RTSS_SHARED_MEMORY
OFF_SIGNATURE = 0
OFF_VERSION = 4
OFF_APP_ENTRY_SIZE = 8
OFF_APP_ARR_OFFSET = 12
OFF_APP_ARR_SIZE = 16
OFF_OSD_ENTRY_SIZE = 20
OFF_OSD_ARR_OFFSET = 24
OFF_OSD_ARR_SIZE = 28
OFF_OSD_FRAME = 32
OFF_BUSY = 36
OFF_LAST_FOREGROUND_PID = 68  # v2.16+

# RTSS_SHARED_MEMORY_OSD_ENTRY
OSD_OWNER = 256
OSD_TEXT_EX = 512
OSD_TEXT_EX_SIZE = 4096
OSD_BUFFER = 4608

# RTSS_SHARED_MEMORY_APP_ENTRY
APP_PID = 0
APP_NAME = 4
APP_TIME0 = 268
APP_TIME1 = 272
APP_FRAMES = 276
APP_FRAMETIME = 280

FILE_MAP_ALL_ACCESS = 0xF001F

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenFileMappingW.restype = wintypes.HANDLE
_k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
_k32.MapViewOfFile.restype = ctypes.c_void_p
_k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]

_u32 = ctypes.WinDLL("user32")
_u32.GetForegroundWindow.restype = wintypes.HWND
_u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]


def _u32_at(addr: int) -> ctypes.c_uint32:
    return ctypes.c_uint32.from_address(addr)


def install_path() -> Optional[Path]:
    for base in (Path(r"C:\Program Files (x86)\RivaTuner Statistics Server"),
                 Path(r"C:\Program Files\RivaTuner Statistics Server")):
        exe = base / "RTSS.exe"
        if exe.exists():
            return exe
    return None


def _foreground_pid() -> int:
    pid = wintypes.DWORD()
    hwnd = _u32.GetForegroundWindow()
    if hwnd:
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


class Rtss:
    """Abre e fecha a memória compartilhada a cada operação (1x/s): se o RTSS fechar e
    abrir de novo, a gente não fica segurando um mapeamento órfão."""

    def __init__(self):
        self._has_slot = False

    @contextmanager
    def _view(self):
        handle = _k32.OpenFileMappingW(FILE_MAP_ALL_ACCESS, False, MAPPING_NAME)
        if not handle:
            yield None
            return
        base = _k32.MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, 0)
        try:
            if not base or _u32_at(base + OFF_SIGNATURE).value != SIGNATURE \
                    or _u32_at(base + OFF_VERSION).value < 0x00020000:
                yield None
            else:
                yield base
        finally:
            if base:
                _k32.UnmapViewOfFile(base)
            _k32.CloseHandle(handle)

    def is_running(self) -> bool:
        with self._view() as base:
            return base is not None

    def _find_slot(self, base: int, claim: bool) -> Optional[int]:
        entry_size = _u32_at(base + OFF_OSD_ENTRY_SIZE).value
        arr = base + _u32_at(base + OFF_OSD_ARR_OFFSET).value
        count = _u32_at(base + OFF_OSD_ARR_SIZE).value
        # o slot 0 é reservado pro cliente principal (Afterburner); terceiros começam do 1
        for passo in (0, 1):
            for i in range(1, count):
                entry = arr + i * entry_size
                owner = ctypes.string_at(entry + OSD_OWNER, 256).split(b"\0", 1)[0]
                if owner == OWNER:
                    return entry
                if passo == 1 and claim and not owner:
                    ctypes.memmove(entry + OSD_OWNER, OWNER + b"\0", len(OWNER) + 1)
                    return entry
        return None

    def update_osd(self, text: str, frametime_graph: bool = False) -> bool:
        with self._view() as base:
            if base is None:
                self._has_slot = False
                return False
            version = _u32_at(base + OFF_VERSION).value
            entry = self._find_slot(base, claim=True)
            if entry is None:
                return False

            if frametime_graph and version >= 0x0002000C:
                # gráfico nativo de frametime do RTSS: sem dados nossos, ele usa o histórico dele
                graph = struct.pack("<IIiiiIffI", GRAPH_SIGNATURE, 36, -32, -3, 1,
                                    GRAPH_FLAG_FRAMETIME | GRAPH_FLAG_FILLED, 0.0, 50000.0, 0)
                ctypes.memmove(entry + OSD_BUFFER, graph, len(graph))

            data = text.encode("cp1252", errors="replace")[:OSD_TEXT_EX_SIZE - 1] + b"\0"
            busy = _u32_at(base + OFF_BUSY) if version >= 0x0002000E else None
            if busy is not None and busy.value & 1:
                return True  # outro cliente escrevendo agora — pula este frame
            if busy is not None:
                busy.value |= 1
            try:
                ctypes.memmove(entry + OSD_TEXT_EX, data, len(data))
            finally:
                if busy is not None:
                    busy.value &= ~1
            frame = _u32_at(base + OFF_OSD_FRAME)
            frame.value = (frame.value + 1) & 0xFFFFFFFF
            self._has_slot = True
            return True

    def release(self):
        """Libera o slot (some o nosso texto do jogo)."""
        if not self._has_slot:
            return
        with self._view() as base:
            if base is not None:
                entry = self._find_slot(base, claim=False)
                if entry is not None:
                    ctypes.memset(entry, 0, _u32_at(base + OFF_OSD_ENTRY_SIZE).value)
                    frame = _u32_at(base + OFF_OSD_FRAME)
                    frame.value = (frame.value + 1) & 0xFFFFFFFF
        self._has_slot = False

    def game_stats(self) -> Optional[dict]:
        """FPS/frametime do app 3D em primeiro plano (o que o RTSS está desenhando agora)."""
        with self._view() as base:
            if base is None:
                return None
            version = _u32_at(base + OFF_VERSION).value
            entry_size = _u32_at(base + OFF_APP_ENTRY_SIZE).value
            arr = base + _u32_at(base + OFF_APP_ARR_OFFSET).value
            count = _u32_at(base + OFF_APP_ARR_SIZE).value
            wanted = {_foreground_pid()}
            if version >= 0x00020010:
                wanted.add(_u32_at(base + OFF_LAST_FOREGROUND_PID).value)
            wanted.discard(0)
            for i in range(count):
                entry = arr + i * entry_size
                pid = _u32_at(entry + APP_PID).value
                if pid == 0 or pid not in wanted:
                    continue
                t0 = _u32_at(entry + APP_TIME0).value
                t1 = _u32_at(entry + APP_TIME1).value
                frames = _u32_at(entry + APP_FRAMES).value
                frametime_us = _u32_at(entry + APP_FRAMETIME).value
                if t1 <= t0 or frames == 0:
                    continue
                name = ctypes.string_at(entry + APP_NAME, 260).split(b"\0", 1)[0].decode("cp1252", "replace")
                return {
                    "fps": 1000.0 * frames / (t1 - t0),
                    "frametime_ms": frametime_us / 1000.0,
                    "app": Path(name).name,
                }
            return None
