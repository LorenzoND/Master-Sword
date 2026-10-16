"""Perfis: lista com aplicar/editar/duplicar/excluir + editor completo.

Problemas da v1 que isto resolve:
- "Salvar" gravava o que estava digitado nos campos, não o que estava aplicado de verdade
  (dava pra salvar lock de 900 MHz com a GPU solta). Agora "Capturar estado atual" lê o real.
- O boost virava só 0/1 (perdia "Agressivo" etc.), sem power/fan, sem editar nem excluir,
  sobrescrevia sem perguntar e o combo voltava sempre pro primeiro perfil.
"""

from typing import Optional

import dearpygui.dearpygui as dpg

from core import profiles as profiles_mod
from core.cpu import BOOST_MODES
from core.ec import FAN_MODE_LABELS, SHIFT_MODE_LABELS
from core.profiles import GPU_KEEP, GPU_LOCK, GPU_RELEASE, Profile
from ui import theme
from ui.context import Ctx
from ui.widgets import Segmented, card, chip, danger_button, muted, primary_button, section, title

KEEP = "Não mexer"
GPU_OPTIONS = {GPU_KEEP: "Não mexer", GPU_LOCK: "Travar", GPU_RELEASE: "Soltar lock"}
BOOST_ITEMS = [KEEP] + list(BOOST_MODES.values())
FAN_ITEMS = [KEEP] + list(FAN_MODE_LABELS.values())
COOLER_ITEMS = [KEEP, "Ligado", "Desligado"]
SHIFT_ITEMS = [KEEP] + list(SHIFT_MODE_LABELS.values())


def _key_for(label: str, mapping: dict) -> Optional[str]:
    return next((k for k, v in mapping.items() if v == label), None)


class PerfisPage:
    key = "perfis"
    label = "Perfis"

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.editing_original: Optional[str] = None
        ctx.on_profiles_changed.append(self.refresh_list)

    def build(self):
        title("Perfis")
        muted("Um perfil aplica vários ajustes de uma vez. Cada item pode ficar em \"Não mexer\".", small=False)
        dpg.add_spacer(height=theme.px(4))
        with dpg.group(horizontal=True, horizontal_spacing=theme.px(16)):
            with dpg.child_window(width=theme.px(400), height=-1, border=False, tag="pf_list_wrap"):
                theme.apply("pf_list_wrap", "plain")
                with dpg.group(tag="pf_list"):
                    pass
            with dpg.group(width=-1):
                self._build_editor()

        with dpg.window(tag="pf_confirm", modal=True, show=False, no_title_bar=True, no_resize=True,
                        width=theme.px(420)):
            dpg.add_text("", tag="pf_confirm_text", wrap=theme.px(380))
            dpg.add_spacer(height=theme.px(6))
            with dpg.group(horizontal=True):
                danger_button("Confirmar", self._confirm_yes, tag="pf_confirm_yes")
                dpg.add_button(label="Cancelar", callback=lambda: dpg.configure_item("pf_confirm", show=False))
        self._confirm_action = None
        self.refresh_list()
        self._load_into_editor(Profile(name=""), original=None)

    def _build_editor(self):
        with card():
            section("Editor", tag="pf_editor_title")
            dpg.add_input_text(tag="pf_name", hint="Nome do perfil (ex.: Jogo leve)", width=-1)

            dpg.add_spacer(height=theme.px(4))
            dpg.add_text("GPU")
            self.gpu_seg = Segmented(GPU_OPTIONS, self._gpu_action_changed, GPU_KEEP)
            with dpg.group(horizontal=True, tag="pf_gpu_range"):
                dpg.add_input_int(tag="pf_gpu_min", width=theme.px(110), step=0, default_value=900,
                                  min_value=210, max_value=self.ctx.gpu.max_clock_mhz, min_clamped=True, max_clamped=True)
                dpg.add_text("a")
                dpg.add_input_int(tag="pf_gpu_max", width=theme.px(110), step=0, default_value=900,
                                  min_value=210, max_value=self.ctx.gpu.max_clock_mhz, min_clamped=True, max_clamped=True)
                dpg.add_text("MHz")

            dpg.add_spacer(height=theme.px(4))
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp):
                dpg.add_table_column(init_width_or_weight=0.4)
                dpg.add_table_column(init_width_or_weight=0.6)
                for label, tag, items in (("Boost da CPU", "pf_boost", BOOST_ITEMS),
                                          ("Modo do fan", "pf_fan", FAN_ITEMS),
                                          ("Cooler Boost", "pf_cooler", COOLER_ITEMS),
                                          ("Modo MSI (shift)", "pf_shift", SHIFT_ITEMS)):
                    with dpg.table_row():
                        dpg.add_text(label)
                        dpg.add_combo(items, tag=tag, width=-1, default_value=KEEP)
            muted("", tag="pf_fan_note", wrap=theme.px(520))

            dpg.add_spacer(height=theme.px(6))
            with dpg.group(horizontal=True):
                primary_button("Salvar perfil", self._save)
                dpg.add_button(label="Capturar estado atual", callback=self._capture)
                dpg.add_button(label="Limpar", callback=lambda: self._load_into_editor(Profile(name=""), None))
            muted("\"Capturar estado atual\" preenche o editor com o que está aplicado agora no hardware.")

    # ---------- lista ----------

    def refresh_list(self):
        if not dpg.does_item_exist("pf_list"):
            return
        dpg.delete_item("pf_list", children_only=True)
        st = self.ctx.controller.state
        start = self.ctx.settings.start_profile
        profiles = profiles_mod.list_profiles()
        if not profiles:
            dpg.add_text("Nenhum perfil ainda. Monte um no editor ao lado.", parent="pf_list",
                         color=theme.rgba(theme.MUTED))
        for p in profiles:
            with dpg.child_window(parent="pf_list", border=False, auto_resize_y=True, width=-1,
                                  always_use_window_padding=True) as c:
                theme.apply(c, "card")
                with dpg.group(horizontal=True):
                    name = dpg.add_text(p.name)
                    theme.font(name, "section")
                    if st.active_profile == p.name:
                        chip("alterado" if st.profile_modified else "ativo",
                             "warn" if st.profile_modified else "blue")
                    if start == p.name:
                        chip("ao iniciar", "gold")
                muted(p.summary(), wrap=theme.px(330))
                with dpg.group(horizontal=True):
                    apply_btn = primary_button("Aplicar", lambda s, a, u: self._apply(u))
                    dpg.set_item_user_data(apply_btn, p.name)
                    dpg.add_button(label="Editar", callback=lambda s, a, u: self._edit(u), user_data=p.name)
                    dpg.add_button(label="Duplicar", callback=lambda s, a, u: self._duplicate(u), user_data=p.name)
                    b = dpg.add_button(label="Excluir", callback=lambda s, a, u: self._ask_delete(u), user_data=p.name)
                    theme.apply(b, "ghost")
            dpg.add_spacer(height=theme.px(2), parent="pf_list")

    def _apply(self, name: str):
        self.ctx.controller.apply_profile(name)
        self.ctx.profiles_changed()

    def _edit(self, name: str):
        p = profiles_mod.get_profile(name)
        if p:
            self._load_into_editor(p, original=p.name)

    def _duplicate(self, name: str):
        p = profiles_mod.get_profile(name)
        if p:
            p.name = f"{p.name} (cópia)"
            self._load_into_editor(p, original=None)

    def _ask_delete(self, name: str):
        self._confirm(f"Excluir o perfil \"{name}\"? Isso não mexe no hardware.", lambda: self._delete(name))

    def _delete(self, name: str):
        profiles_mod.delete_profile(name)
        self.ctx.controller.on_profile_deleted(name)
        if self.editing_original == name:
            self._load_into_editor(Profile(name=""), None)
        self.ctx.controller.notify(f"Perfil '{name}' excluído")
        self.ctx.profiles_changed()

    # ---------- editor ----------

    def _gpu_action_changed(self, action):
        dpg.configure_item("pf_gpu_range", show=action == GPU_LOCK)

    def _load_into_editor(self, p: Profile, original: Optional[str]):
        self.editing_original = original
        dpg.set_value("pf_editor_title", f"Editando \"{original}\"" if original else "Novo perfil")
        dpg.set_value("pf_name", p.name)
        self.gpu_seg.set(p.gpu_action)
        self._gpu_action_changed(p.gpu_action)
        dpg.set_value("pf_gpu_min", p.gpu_min_mhz)
        dpg.set_value("pf_gpu_max", p.gpu_max_mhz)
        dpg.set_value("pf_boost", BOOST_MODES.get(p.cpu_boost_mode, KEEP) if p.cpu_boost_mode is not None else KEEP)
        dpg.set_value("pf_fan", FAN_MODE_LABELS.get(p.fan_mode, KEEP) if p.fan_mode else KEEP)
        dpg.set_value("pf_cooler", KEEP if p.cooler_boost is None else ("Ligado" if p.cooler_boost else "Desligado"))
        dpg.set_value("pf_shift", SHIFT_MODE_LABELS.get(p.shift_mode, KEEP) if p.shift_mode else KEEP)
        self.on_show()

    def _from_editor(self) -> Profile:
        cooler = dpg.get_value("pf_cooler")
        return Profile(
            name=dpg.get_value("pf_name").strip(),
            gpu_action=self.gpu_seg.value,
            gpu_min_mhz=dpg.get_value("pf_gpu_min"),
            gpu_max_mhz=dpg.get_value("pf_gpu_max"),
            cpu_boost_mode=_key_for(dpg.get_value("pf_boost"), BOOST_MODES),
            fan_mode=_key_for(dpg.get_value("pf_fan"), FAN_MODE_LABELS),
            cooler_boost=None if cooler == KEEP else cooler == "Ligado",
            shift_mode=_key_for(dpg.get_value("pf_shift"), SHIFT_MODE_LABELS),
        )

    def _capture(self):
        name = dpg.get_value("pf_name").strip()
        self._load_into_editor(self.ctx.controller.capture_current(name), self.editing_original)
        self.ctx.controller.notify("Editor preenchido com o estado atual")

    def _save(self):
        p = self._from_editor()
        if not p.name:
            self.ctx.controller.notify("Dê um nome pro perfil antes de salvar", True)
            return
        if p.gpu_min_mhz > p.gpu_max_mhz:
            p.gpu_min_mhz, p.gpu_max_mhz = p.gpu_max_mhz, p.gpu_min_mhz
        renaming_onto_other = p.name.lower() != (self.editing_original or "").lower()
        if renaming_onto_other and profiles_mod.exists(p.name):
            self._confirm(f"Já existe um perfil \"{p.name}\". Substituir?", lambda: self._do_save(p))
            return
        self._do_save(p)

    def _do_save(self, p: Profile):
        original = self.editing_original
        profiles_mod.save_profile(p, original_name=original)
        if original and original != p.name:
            self.ctx.controller.on_profile_renamed(original, p.name)
        self.editing_original = p.name
        dpg.set_value("pf_editor_title", f"Editando \"{p.name}\"")
        self.ctx.controller.notify(f"Perfil '{p.name}' salvo")
        self.ctx.profiles_changed()

    # ---------- confirmação ----------

    def _confirm(self, text: str, action):
        self._confirm_action = action
        dpg.set_value("pf_confirm_text", text)
        w, h = dpg.get_viewport_client_width(), dpg.get_viewport_client_height()
        dpg.configure_item("pf_confirm", show=True, pos=(w // 2 - theme.px(210), h // 2 - theme.px(80)))

    def _confirm_yes(self):
        dpg.configure_item("pf_confirm", show=False)
        if self._confirm_action:
            self._confirm_action()
            self._confirm_action = None

    # ---------- ciclo ----------

    def on_show(self):
        writable = self.ctx.controller.ec_writable()
        for tag in ("pf_fan", "pf_cooler", "pf_shift"):
            (dpg.enable_item if writable else dpg.disable_item)(tag)
        dpg.set_value("pf_fan_note", "" if writable else
                      "Os ajustes de fan ficam bloqueados até você habilitar o controle do fan na página Fan.")

    def update(self, snap):
        pass
