"""Atalho global de teclado (RegisterHotKey do Windows) numa thread com fila de mensagens própria."""

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable, Optional

log = logging.getLogger("master_sword.hotkey")

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32")
_u32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_u32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_u32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

HOTKEY_CHOICES = ["Ctrl+Shift+O", "Ctrl+Alt+O", "Alt+Shift+O", "Ctrl+Shift+F10", "Ctrl+Alt+F12", "Desligado"]


def parse(combo: str) -> Optional[tuple[int, int]]:
    mods, vk = MOD_NOREPEAT, None
    for part in combo.split("+"):
        p = part.strip().lower()
        if p == "ctrl":
            mods |= MOD_CONTROL
        elif p == "alt":
            mods |= MOD_ALT
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p == "win":
            mods |= MOD_WIN
        elif len(p) == 1 and p.isalnum():
            vk = ord(p.upper())
        elif p.startswith("f") and p[1:].isdigit():
            vk = 0x70 + int(p[1:]) - 1
    return (mods, vk) if vk else None


class Hotkey(threading.Thread):
    def __init__(self, combo: str, callback: Callable[[], None]):
        super().__init__(name="hotkey", daemon=True)
        self.combo = combo
        self.callback = callback
        self._thread_id = 0
        self.ok = False

    def run(self):
        parsed = parse(self.combo)
        if not parsed:
            return
        self._thread_id = _k32.GetCurrentThreadId()
        if not _u32.RegisterHotKey(None, 1, parsed[0], parsed[1]):
            log.warning("Atalho %s já está em uso por outro programa", self.combo)
            return
        self.ok = True
        msg = wintypes.MSG()
        while _u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    self.callback()
                except Exception:
                    log.exception("callback do atalho falhou")
        _u32.UnregisterHotKey(None, 1)

    def stop(self):
        if self._thread_id:
            _u32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
