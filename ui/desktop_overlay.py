"""Overlay de desktop: janelinha sempre no topo, semitransparente e que não pega clique.

Alternativa pra quando o RTSS não está aberto. Funciona por cima de janelas e de jogos em
tela cheia "sem borda"; em tela cheia exclusiva só o modo RTSS aparece.
Roda numa thread própria com Tkinter (já vem com o Python, zero dependência).
"""

import ctypes
import logging
import threading
import tkinter as tk
from ctypes import wintypes
from typing import Optional

log = logging.getLogger("master_sword.desktop_overlay")

_u32 = ctypes.WinDLL("user32")
_u32.GetParent.argtypes = [wintypes.HWND]
_u32.GetParent.restype = wintypes.HWND
_u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_u32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_u32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
SPI_GETWORKAREA = 0x0030

BG = "#0B0F17"
MARGIN = 16


def _work_area() -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    _u32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


class DesktopOverlay(threading.Thread):
    def __init__(self, color: str, alert_color: str, position: str):
        super().__init__(name="desktop-overlay", daemon=True)
        self.color = f"#{color}"
        self.alert_color = f"#{alert_color}"
        self.position = position
        self._lines: list[tuple[str, bool]] = []
        self._visible = True
        self._stopping = False
        self._lock = threading.Lock()
        self._root: Optional[tk.Tk] = None
        self._labels: list[tk.Label] = []

    # chamados de qualquer thread
    def set_lines(self, lines: list[tuple[str, bool]]):
        with self._lock:
            self._lines = list(lines)

    def set_visible(self, visible: bool):
        self._visible = visible

    def configure(self, color: str, position: str):
        self.color = f"#{color}"
        self.position = position

    def stop(self):
        self._stopping = True

    # thread do Tk
    def run(self):
        try:
            root = tk.Tk()
        except Exception:
            log.exception("Não consegui criar o overlay de desktop")
            return
        self._root = root
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.82)
        root.configure(bg=BG)
        self._frame = tk.Frame(root, bg=BG, padx=10, pady=6)
        self._frame.pack()
        root.update_idletasks()
        self._make_clickthrough(root)
        self._tick()
        root.mainloop()
        # Os objetos do Tk precisam morrer nesta thread; se o coletor os pegar na thread
        # principal na saída, o Tcl aborta o processo ("async handler deleted by the wrong thread").
        self._labels.clear()
        self._frame = None
        self._root = None
        del root
        import gc
        gc.collect()

    def _make_clickthrough(self, root: tk.Tk):
        hwnd = _u32.GetParent(root.winfo_id())
        style = _u32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        _u32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
                               | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)

    def _tick(self):
        root = self._root
        if self._stopping:
            root.destroy()
            return
        if not self._visible:
            root.withdraw()
        else:
            with self._lock:
                lines = list(self._lines)
            self._render(lines)
            root.deiconify()
            self._place()
            root.lift()
        root.after(500, self._tick)

    def _render(self, lines: list[tuple[str, bool]]):
        while len(self._labels) < len(lines):
            lbl = tk.Label(self._frame, bg=BG, font=("Consolas", 11, "bold"), anchor="w", justify="left")
            lbl.pack(fill="x")
            self._labels.append(lbl)
        while len(self._labels) > len(lines):
            self._labels.pop().destroy()
        for lbl, (text, alert) in zip(self._labels, lines):
            lbl.configure(text=text, fg=self.alert_color if alert else self.color)

    def _place(self):
        root = self._root
        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        left, top, right, bottom = _work_area()
        x = left + MARGIN if "left" in self.position else right - w - MARGIN
        y = top + MARGIN if "top" in self.position else bottom - h - MARGIN
        root.geometry(f"+{x}+{y}")
