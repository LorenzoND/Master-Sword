"""Peças de interface reutilizadas pelas páginas: cartão, chip, título, controle segmentado."""

from contextlib import contextmanager
from typing import Callable, Optional

import dearpygui.dearpygui as dpg

from ui import theme


@contextmanager
def card(height: int = 0, width: int = -1, tag=0):
    with dpg.child_window(height=height, width=width, border=False, tag=tag, always_use_window_padding=True,
                          no_scrollbar=True, auto_resize_y=height == 0) as item:
        theme.apply(item, "card")
        yield item


def title(text: str, tag=0):
    item = dpg.add_text(text, tag=tag)
    theme.font(item, "title")
    return item


def section(text: str, tag=0):
    item = dpg.add_text(text, tag=tag)
    theme.font(item, "section")
    return item


def muted(text: str, tag=0, wrap: int = -1, small: bool = True):
    item = dpg.add_text(text, tag=tag, color=theme.rgba(theme.MUTED), wrap=wrap)
    if small:
        theme.font(item, "small")
    return item


def chip(label: str, kind: str = "muted", tag=0):
    item = dpg.add_button(label=label, tag=tag, small=False)
    theme.apply(item, f"chip_{kind}")
    theme.font(item, "small")
    return item


def set_chip(tag, label: str, kind: str):
    dpg.configure_item(tag, label=label)
    theme.apply(tag, f"chip_{kind}")


def primary_button(label: str, callback: Callable, width: int = 0, tag=0):
    item = dpg.add_button(label=label, callback=callback, width=width, tag=tag)
    theme.apply(item, "primary")
    return item


def danger_button(label: str, callback: Callable, width: int = 0, tag=0):
    item = dpg.add_button(label=label, callback=callback, width=width, tag=tag)
    theme.apply(item, "danger")
    return item


class Segmented:
    """Botões lado a lado onde só um fica ativo (substitui radio button, mais legível)."""

    def __init__(self, options: dict, callback: Optional[Callable] = None, value=None, width: int = 0):
        self.options = options  # valor -> rótulo
        self.callback = callback
        self.value = value
        self._buttons = {}
        with dpg.group(horizontal=True, horizontal_spacing=theme.px(4)) as self.group:
            for key, label in options.items():
                self._buttons[key] = dpg.add_button(label=label, width=width,
                                                    callback=lambda s, a, u: self._clicked(u), user_data=key)
        self._paint()

    def _clicked(self, key):
        self.set(key)
        if self.callback:
            self.callback(key)

    def set(self, key):
        self.value = key
        self._paint()

    def _paint(self):
        for key, btn in self._buttons.items():
            theme.apply(btn, "segment_active" if key == self.value else "segment")

    def enable(self, on: bool):
        for btn in self._buttons.values():
            (dpg.enable_item if on else dpg.disable_item)(btn)


def level_for(temp: Optional[float], warn: float, hot: float) -> str:
    if temp is None:
        return "muted"
    if temp >= hot:
        return "hot"
    if temp >= warn:
        return "warn"
    return "ok"


def fmt(value, spec: str = ".0f", unit: str = "", none: str = "--") -> str:
    if value is None:
        return none
    return f"{format(value, spec)}{unit}"
