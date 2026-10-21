"""Atalho global de teclado por hook de baixo nível (WH_KEYBOARD_LL) que só OBSERVA a tecla.

Não usa RegisterHotKey porque ele sequestra a tecla: com PageDown registrado, o PageDown
pararia de rolar página no navegador e em qualquer outro programa. O hook vê a tecla,
dispara o callback e repassa o evento adiante (como o Afterburner faz com o atalho do OSD).
Com modificador exato: "PageDown" não dispara com Ctrl+PageDown (troca de aba no navegador).
"""

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable, Optional

log = logging.getLogger("master_sword.hotkey")

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32")

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


_u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_u32.SetWindowsHookExW.restype = wintypes.HHOOK
_u32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_u32.CallNextHookEx.restype = LRESULT
_u32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_u32.GetAsyncKeyState.restype = ctypes.c_short
_u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_u32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_k32.GetModuleHandleW.restype = wintypes.HMODULE

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_QUIT = 0x0100, 0x0101, 0x0104, 0x0105, 0x0012
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x11, 0x12, 0x5B, 0x5C

HOTKEY_CHOICES = ["PageDown", "PageUp", "Insert", "Home", "End", "ScrollLock", "Pause",
                  "Ctrl+Shift+O", "Ctrl+Alt+O", "Ctrl+Shift+F10", "Desligado"]

_NAMED_KEYS = {
    "pagedown": 0x22, "pgdn": 0x22, "pageup": 0x21, "pgup": 0x21, "insert": 0x2D, "home": 0x24,
    "end": 0x23, "scrolllock": 0x91, "pause": 0x13, "delete": 0x2E,
}


def parse(combo: str) -> Optional[tuple[frozenset, int]]:
    """'Ctrl+Shift+O' -> ({'ctrl', 'shift'}, vk)."""
    mods, vk = set(), None
    for part in combo.split("+"):
        p = part.strip().lower()
        if p in ("ctrl", "alt", "shift", "win"):
            mods.add(p)
        elif p in _NAMED_KEYS:
            vk = _NAMED_KEYS[p]
        elif len(p) == 1 and p.isalnum():
            vk = ord(p.upper())
        elif p.startswith("f") and p[1:].isdigit():
            vk = 0x70 + int(p[1:]) - 1
    return (frozenset(mods), vk) if vk else None


def _down(vk: int) -> bool:
    return bool(_u32.GetAsyncKeyState(vk) & 0x8000)


def _current_mods() -> frozenset:
    mods = set()
    if _down(VK_CONTROL):
        mods.add("ctrl")
    if _down(VK_MENU):
        mods.add("alt")
    if _down(VK_SHIFT):
        mods.add("shift")
    if _down(VK_LWIN) or _down(VK_RWIN):
        mods.add("win")
    return frozenset(mods)


class Hotkey(threading.Thread):
    def __init__(self, combo: str, callback: Callable[[], None]):
        super().__init__(name="hotkey", daemon=True)
        self.combo = combo
        self.callback = callback
        self._thread_id = 0
        self._parsed = None
        self._held = False  # segurar a tecla gera keydown repetido: dispara uma vez só
        self._proc = HOOKPROC(self._hook)  # referência viva, senão o GC solta o callback
        self.ok = False

    def _hook(self, code, wparam, lparam):
        if code == 0 and self._parsed:
            vk = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
            mods, key = self._parsed
            if vk == key:
                if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if not self._held and _current_mods() == mods:
                        self._held = True
                        # fora do hook: o Windows derruba hooks que demoram pra responder
                        threading.Thread(target=self._fire, daemon=True).start()
                elif wparam in (WM_KEYUP, WM_SYSKEYUP):
                    self._held = False
        return _u32.CallNextHookEx(None, code, wparam, lparam)

    def _fire(self):
        try:
            self.callback()
        except Exception:
            log.exception("callback do atalho falhou")

    def run(self):
        self._parsed = parse(self.combo)
        if not self._parsed:
            return
        self._thread_id = _k32.GetCurrentThreadId()
        hook = _u32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, _k32.GetModuleHandleW(None), 0)
        if not hook:
            log.warning("Não consegui instalar o atalho %s (erro %s)", self.combo, ctypes.get_last_error())
            return
        self.ok = True
        msg = wintypes.MSG()
        while _u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        _u32.UnhookWindowsHookEx(hook)

    def stop(self):
        if self._thread_id:
            _u32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
