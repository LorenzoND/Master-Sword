"""Ajustes: iniciar com o Windows, perfil ao iniciar, soltar lock ao fechar, alertas, diagnóstico."""

import os

import dearpygui.dearpygui as dpg

from core import profiles as profiles_mod
from core.launcher import set_autostart, task_exists
from core.paths import LOGON_TASK_NAME, LOGS_DIR, TASK_NAME
from core.settings import save_settings
from ui import theme
from ui.context import Ctx
from ui.widgets import card, muted, section, title

NONE = "Nenhum"


class AjustesPage:
    key = "ajustes"
    label = "Ajustes"

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        ctx.on_profiles_changed.append(self._refresh_profiles)

    def build(self):
        s = self.ctx.settings
        title("Ajustes")
        with card():
            section("Inicialização")
            dpg.add_checkbox(label="Iniciar com o Windows (minimizado na bandeja)", tag="aj_autostart",
                             callback=self._autostart)
            with dpg.group(horizontal=True):
                dpg.add_text("Perfil ao iniciar")
                dpg.add_combo([], tag="aj_start_profile", width=theme.px(280), callback=self._start_profile)
            muted("Útil porque o lock da GPU se perde quando o PC reinicia.")
            dpg.add_checkbox(label="Soltar o lock da GPU ao sair do app", default_value=s.release_lock_on_exit,
                             callback=lambda sd, v: self._set("release_lock_on_exit", bool(v)))
            muted("Desligado = o lock continua valendo com o app fechado (comportamento do nvidia-smi).")

        with card():
            section("Alertas de temperatura")
            dpg.add_checkbox(label="Avisar (notificação do Windows + overlay em vermelho)",
                             default_value=s.alerts_enabled, callback=lambda sd, v: self._set("alerts_enabled", bool(v)))
            with dpg.group(horizontal=True):
                dpg.add_text("GPU a partir de")
                dpg.add_slider_int(default_value=s.alert_gpu_temp, min_value=70, max_value=95, width=theme.px(240),
                                   format="%d °C", callback=lambda sd, v: self._set("alert_gpu_temp", v))
            with dpg.group(horizontal=True):
                dpg.add_text("CPU a partir de ")
                dpg.add_slider_int(default_value=s.alert_cpu_temp, min_value=75, max_value=100, width=theme.px(240),
                                   format="%d °C", callback=lambda sd, v: self._set("alert_cpu_temp", v))
            muted(f"Referência: a RTX 2060 começa a segurar o clock em {self.ctx.gpu.slowdown_temp_c} °C; "
                  "a i7-10750H em 100 °C.")

        with card():
            section("Sistema")
            muted("", tag="aj_sys", wrap=theme.px(760), small=False)
            dpg.add_button(label="Abrir pasta de logs", callback=lambda: os.startfile(LOGS_DIR))

        self._refresh_profiles()

    def _set(self, key, value):
        setattr(self.ctx.settings, key, value)
        save_settings(self.ctx.settings)

    def _autostart(self, sender, value):
        ok, err = set_autostart(bool(value))
        if not ok:
            dpg.set_value("aj_autostart", not value)
            self.ctx.controller.notify(f"Não consegui mudar o início automático: {err or 'erro desconhecido'}", True)
        else:
            self.ctx.controller.notify("Vai iniciar com o Windows" if value else "Início automático removido")

    def _start_profile(self, sender, label):
        self._set("start_profile", None if label == NONE else label)
        self.ctx.profiles_changed()

    def _refresh_profiles(self):
        if not dpg.does_item_exist("aj_start_profile"):
            return
        names = [p.name for p in profiles_mod.list_profiles()]
        dpg.configure_item("aj_start_profile", items=[NONE] + names)
        dpg.set_value("aj_start_profile", self.ctx.settings.start_profile or NONE)

    def on_show(self):
        dpg.set_value("aj_autostart", task_exists(LOGON_TASK_NAME))
        ec = self.ctx.ec
        lines = [
            f"Rodando como administrador: {'sim' if self.ctx.is_admin else 'NÃO — lock e sensores vão falhar'}",
            f"Tarefa de abertura sem UAC ('{TASK_NAME}'): {'instalada' if task_exists(TASK_NAME) else 'não instalada — rode install.ps1'}",
            f"GPU: {self.ctx.gpu.name} · NVML {'ok' if self.ctx.gpu.available else 'reconectando'}",
            f"CPU: {self.ctx.cpu_name}",
            f"EC: {ec.firmware + (' (reconhecido)' if ec.supported else ' (não reconhecido)') if ec else 'indisponível'}",
        ]
        dpg.set_value("aj_sys", "\n".join(lines))

    def update(self, snap):
        pass
