"""Visual: paleta azul/dourada da Master Sword, fontes do Windows e temas de componente.

A v1 usava a fonte bitmap padrão do Dear PyGui (ProggyClean 13px) sem DPI awareness —
era o principal motivo de parecer "ferramenta de debug". Aqui: Segoe UI em tamanhos
escalados pelo DPI, cartões arredondados e espaçamento generoso.
"""

import ctypes
from pathlib import Path

import dearpygui.dearpygui as dpg

# ---------- paleta ----------
BG = (12, 16, 24)
SIDEBAR = (16, 21, 32)
CARD = (21, 28, 42)
CARD_HI = (29, 38, 57)
CARD_HOVER = (36, 47, 70)
BORDER = (40, 51, 76)
TEXT = (229, 234, 243)
MUTED = (140, 151, 173)
FAINT = (96, 108, 132)
BLUE = (94, 158, 236)
BLUE_HOVER = (124, 180, 248)
BLUE_DIM = (32, 58, 98)
GOLD = (220, 176, 86)
OK = (76, 195, 138)
WARN = (236, 166, 64)
HOT = (232, 88, 80)

GPU_COLOR = BLUE
CPU_COLOR = GOLD

LEVEL_COLORS = {"ok": TEXT, "warn": WARN, "hot": HOT, "muted": MUTED}

FONTS_DIR = Path(r"C:\Windows\Fonts")
fonts: dict[str, int] = {}
SCALE = 1.0


def rgba(rgb, a=255):
    return (*rgb[:3], a)


def enable_dpi_awareness():
    """Sem isso o Windows estica a janela em telas com escala (125% no notebook) e tudo fica borrado."""
    global SCALE
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        SCALE = ctypes.windll.user32.GetDpiForSystem() / 96
    except Exception:
        SCALE = 1.0


def px(value: float) -> int:
    return int(round(value * SCALE))


def load_fonts():
    regular = FONTS_DIR / "segoeui.ttf"
    semibold = FONTS_DIR / "seguisb.ttf"
    mono = FONTS_DIR / "consola.ttf"
    if not regular.exists():
        return
    if not semibold.exists():
        semibold = regular
    with dpg.font_registry():
        fonts["body"] = dpg.add_font(str(regular), px(17))
        fonts["small"] = dpg.add_font(str(regular), px(14))
        fonts["section"] = dpg.add_font(str(semibold), px(16))
        fonts["title"] = dpg.add_font(str(semibold), px(24))
        fonts["big"] = dpg.add_font(str(semibold), px(36))
        fonts["mono"] = dpg.add_font(str(mono if mono.exists() else regular), px(15))
    dpg.bind_font(fonts["body"])


def font(item, name: str):
    if name in fonts:
        dpg.bind_item_font(item, fonts[name])


def _global_theme() -> int:
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            c = dpg.add_theme_color
            c(dpg.mvThemeCol_WindowBg, rgba(BG))
            c(dpg.mvThemeCol_ChildBg, rgba(CARD))
            c(dpg.mvThemeCol_PopupBg, rgba(CARD_HI))
            c(dpg.mvThemeCol_ModalWindowDimBg, (0, 0, 0, 140))
            c(dpg.mvThemeCol_Text, rgba(TEXT))
            c(dpg.mvThemeCol_TextDisabled, rgba(FAINT))
            c(dpg.mvThemeCol_Border, rgba(BORDER))
            c(dpg.mvThemeCol_FrameBg, rgba(CARD_HI))
            c(dpg.mvThemeCol_FrameBgHovered, rgba(CARD_HOVER))
            c(dpg.mvThemeCol_FrameBgActive, rgba(CARD_HOVER))
            c(dpg.mvThemeCol_Button, rgba(CARD_HI))
            c(dpg.mvThemeCol_ButtonHovered, rgba(CARD_HOVER))
            c(dpg.mvThemeCol_ButtonActive, rgba(BLUE_DIM))
            c(dpg.mvThemeCol_Header, rgba(CARD_HI))
            c(dpg.mvThemeCol_HeaderHovered, rgba(CARD_HOVER))
            c(dpg.mvThemeCol_HeaderActive, rgba(BLUE_DIM))
            c(dpg.mvThemeCol_CheckMark, rgba(BLUE))
            c(dpg.mvThemeCol_SliderGrab, rgba(BLUE))
            c(dpg.mvThemeCol_SliderGrabActive, rgba(BLUE_HOVER))
            c(dpg.mvThemeCol_TitleBg, rgba(CARD))
            c(dpg.mvThemeCol_TitleBgActive, rgba(CARD_HI))
            c(dpg.mvThemeCol_TableHeaderBg, rgba(CARD_HI))
            c(dpg.mvThemeCol_TableBorderStrong, rgba(BORDER))
            c(dpg.mvThemeCol_TableBorderLight, rgba(BORDER, 120))
            c(dpg.mvThemeCol_TableRowBg, (0, 0, 0, 0))
            c(dpg.mvThemeCol_TableRowBgAlt, (255, 255, 255, 6))
            c(dpg.mvThemeCol_Separator, rgba(BORDER))
            c(dpg.mvThemeCol_ScrollbarBg, (0, 0, 0, 0))
            c(dpg.mvThemeCol_ScrollbarGrab, rgba(BORDER))
            c(dpg.mvThemeCol_ScrollbarGrabHovered, rgba(CARD_HOVER))
            c(dpg.mvThemeCol_Tab, rgba(CARD_HI))
            c(dpg.mvThemeCol_TabHovered, rgba(CARD_HOVER))

            c(dpg.mvPlotCol_FrameBg, (0, 0, 0, 0), category=dpg.mvThemeCat_Plots)
            c(dpg.mvPlotCol_PlotBg, (0, 0, 0, 0), category=dpg.mvThemeCat_Plots)
            c(dpg.mvPlotCol_PlotBorder, (0, 0, 0, 0), category=dpg.mvThemeCat_Plots)
            c(dpg.mvPlotCol_LegendBg, rgba(CARD_HI, 230), category=dpg.mvThemeCat_Plots)
            c(dpg.mvPlotCol_LegendBorder, (0, 0, 0, 0), category=dpg.mvThemeCat_Plots)
            c(dpg.mvPlotCol_AxisGrid, rgba(BORDER, 110), category=dpg.mvThemeCat_Plots)
            c(dpg.mvPlotCol_AxisText, rgba(MUTED), category=dpg.mvThemeCat_Plots)

            s = dpg.add_theme_style
            s(dpg.mvStyleVar_WindowPadding, px(20), px(18))
            s(dpg.mvStyleVar_FramePadding, px(10), px(6))
            s(dpg.mvStyleVar_ItemSpacing, px(10), px(10))
            s(dpg.mvStyleVar_ItemInnerSpacing, px(8), px(6))
            s(dpg.mvStyleVar_CellPadding, px(8), px(6))
            s(dpg.mvStyleVar_WindowRounding, px(10))
            s(dpg.mvStyleVar_ChildRounding, px(12))
            s(dpg.mvStyleVar_FrameRounding, px(7))
            s(dpg.mvStyleVar_PopupRounding, px(10))
            s(dpg.mvStyleVar_GrabRounding, px(7))
            s(dpg.mvStyleVar_TabRounding, px(7))
            s(dpg.mvStyleVar_ScrollbarSize, px(10))
            s(dpg.mvStyleVar_ScrollbarRounding, px(6))
            s(dpg.mvStyleVar_ChildBorderSize, 0)
            s(dpg.mvStyleVar_WindowBorderSize, 0)
            s(dpg.mvStyleVar_PopupBorderSize, 0)
            s(dpg.mvStyleVar_FrameBorderSize, 0)
            s(dpg.mvPlotStyleVar_PlotPadding, px(22), px(8), category=dpg.mvThemeCat_Plots)
            s(dpg.mvPlotStyleVar_LineWeight, 2.0 * SCALE, category=dpg.mvThemeCat_Plots)
            s(dpg.mvPlotStyleVar_FillAlpha, 1.0, category=dpg.mvThemeCat_Plots)
    return t


themes: dict[str, int] = {}


def _button_theme(bg, fg, hover, active=None) -> int:
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, rgba(bg) if len(bg) == 3 else bg)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, rgba(hover) if len(hover) == 3 else hover)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, rgba(active or hover) if len(active or hover) == 3 else (active or hover))
            dpg.add_theme_color(dpg.mvThemeCol_Text, rgba(fg))
        with dpg.theme_component(dpg.mvButton, enabled_state=False):
            dpg.add_theme_color(dpg.mvThemeCol_Button, rgba(CARD_HI))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, rgba(CARD_HI))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, rgba(CARD_HI))
            dpg.add_theme_color(dpg.mvThemeCol_Text, rgba(FAINT))
    return t


def _chip_theme(color) -> int:
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            bg = rgba(color, 40)
            dpg.add_theme_color(dpg.mvThemeCol_Button, bg)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, bg)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, bg)
            dpg.add_theme_color(dpg.mvThemeCol_Text, rgba(color))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, px(11))
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, px(10), px(3))
    return t


def _line_theme(color, weight=2.0) -> int:
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Line, rgba(color), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, weight * SCALE, category=dpg.mvThemeCat_Plots)
        with dpg.theme_component(dpg.mvInfLineSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Line, rgba(color, 170), category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, 1.0 * SCALE, category=dpg.mvThemeCat_Plots)
    return t


def _shade_theme(color, alpha) -> int:
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvShadeSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Fill, rgba(color, alpha), category=dpg.mvThemeCat_Plots)
    return t


def setup():
    load_fonts()
    dpg.bind_theme(_global_theme())

    themes["primary"] = _button_theme(BLUE, BG, BLUE_HOVER)
    themes["danger"] = _button_theme(rgba(HOT, 50), HOT, rgba(HOT, 80))
    themes["ghost"] = _button_theme((0, 0, 0, 0), MUTED, CARD_HI)
    themes["nav"] = _button_theme((0, 0, 0, 0), MUTED, CARD_HI)
    themes["nav_active"] = _button_theme(BLUE_DIM, TEXT, BLUE_DIM)
    themes["segment"] = _button_theme(CARD_HI, MUTED, CARD_HOVER)
    themes["segment_active"] = _button_theme(BLUE_DIM, TEXT, BLUE_DIM)
    for name, color in (("blue", BLUE), ("gold", GOLD), ("ok", OK), ("warn", WARN), ("hot", HOT), ("muted", MUTED)):
        themes[f"chip_{name}"] = _chip_theme(color)

    for name, color in (("gpu", GPU_COLOR), ("cpu", CPU_COLOR), ("hot", HOT), ("muted", MUTED)):
        themes[f"line_{name}"] = _line_theme(color)
    themes["shade_hot"] = _shade_theme(HOT, 38)
    themes["shade_warn"] = _shade_theme(WARN, 38)
    themes["shade_zone"] = _shade_theme(HOT, 16)

    with dpg.theme() as sidebar:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, rgba(SIDEBAR))
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(14), px(18))
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, px(6), px(4))
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_style(dpg.mvStyleVar_ButtonTextAlign, 0.0, 0.5)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, px(12), px(8))
    themes["sidebar"] = sidebar

    with dpg.theme() as content:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (0, 0, 0, 0))
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(24), px(20))
    themes["content"] = content

    with dpg.theme() as plain:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (0, 0, 0, 0))
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
    themes["plain"] = plain

    with dpg.theme() as preview:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, rgba(BG))
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(12), px(10))
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, px(6), px(3))
    themes["preview"] = preview

    with dpg.theme() as card:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, rgba(CARD))
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(18), px(14))
    themes["card"] = card

    with dpg.theme() as root:
        with dpg.theme_component(dpg.mvWindowAppItem):
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
    themes["root"] = root


def apply(item, name: str):
    dpg.bind_item_theme(item, themes[name])
