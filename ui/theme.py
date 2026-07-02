"""Tema visual: paleta azul/dourada inspirada na Master Sword de Zelda.

Só cores e cantos arredondados via API de tema do próprio Dear PyGui — nenhuma imagem,
textura ou dependência nova. Custo de zero no tempo de execução.
"""

import dearpygui.dearpygui as dpg

BG_DARK = (14, 18, 27, 255)          # ceu noturno hylian
BG_PANEL = (22, 28, 42, 255)
BG_PANEL_ALT = (28, 35, 52, 255)
BLADE_BLUE = (86, 154, 232, 255)     # lamina da master sword
BLADE_BLUE_HOVER = (114, 180, 250, 255)
BLADE_BLUE_ACTIVE = (58, 118, 196, 255)
GOLD = (200, 158, 74, 255)           # guarda/pomo
GOLD_DIM = (150, 120, 64, 255)
TEXT = (224, 230, 242, 255)
TEXT_MUTED = (140, 150, 170, 255)
BORDER = (48, 60, 88, 255)
ERROR = (214, 96, 96, 255)


def build_global_theme() -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, BG_DARK)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, BG_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, BG_PANEL_ALT)
            dpg.add_theme_color(dpg.mvThemeCol_Text, TEXT)
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, TEXT_MUTED)
            dpg.add_theme_color(dpg.mvThemeCol_Border, BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, BG_PANEL_ALT)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (36, 46, 68, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (42, 54, 80, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (32, 40, 60, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, BLADE_BLUE_HOVER)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, BLADE_BLUE_ACTIVE)
            dpg.add_theme_color(dpg.mvThemeCol_Header, (32, 40, 60, 255))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, BLADE_BLUE_HOVER)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, BLADE_BLUE_ACTIVE)
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, GOLD)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, BLADE_BLUE)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, BLADE_BLUE_ACTIVE)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, BG_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, BG_PANEL_ALT)
            dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, (32, 40, 60, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderStrong, BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, (18, 23, 35, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Separator, GOLD_DIM)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, BLADE_BLUE)

            dpg.add_theme_color(dpg.mvPlotCol_FrameBg, BG_PANEL, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_PlotBg, BG_DARK, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_PlotBorder, BORDER, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_LegendBg, BG_PANEL, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_AxisGrid, (40, 50, 72, 255), category=dpg.mvThemeCat_Plots)

            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 4)

    return theme


def line_theme(color: tuple) -> int:
    """Tema pequeno pra colorir uma série de linha específica (bind_item_theme por série)."""
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Line, color, category=dpg.mvThemeCat_Plots)
    return theme


def apply_global():
    dpg.bind_theme(build_global_theme())
