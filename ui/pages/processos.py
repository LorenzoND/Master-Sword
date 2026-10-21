"""Processos: quem está consumindo CPU/RAM/VRAM, baixar prioridade ou encerrar (com confirmação).

A varredura agora roda numa thread — na v1 ela dormia 0,3 s dentro da interface e congelava a janela.
"""

import threading

import dearpygui.dearpygui as dpg

from core.scan import ScanError, kill_process, lower_priority, scan
from ui import theme
from ui.context import Ctx
from ui.widgets import card, danger_button, muted, primary_button, title

MAX_ROWS = 60


class ProcessosPage:
    key = "processos"
    label = "Processos"

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self._rows: dict[int, int] = {}  # pid -> checkbox
        self._names: dict[int, str] = {}
        self._scanning = False

    def build(self):
        title("Processos")
        muted("Baixar prioridade é reversível e não fecha nada (estilo Process Lasso). Encerrar sempre pede "
              "confirmação.", small=False)
        dpg.add_spacer(height=theme.px(4))
        with card():
            with dpg.group(horizontal=True):
                primary_button("Escanear", self.do_scan)
                dpg.add_button(label="Baixar prioridade dos marcados", callback=self._lower)
                danger_button("Encerrar marcados", self._ask_kill)
                muted("", tag="pr_status")
            with dpg.table(tag="pr_table", header_row=True, row_background=True, borders_innerH=False,
                           borders_outerH=False, borders_innerV=False, borders_outerV=False, scrollY=True,
                           height=-1, policy=dpg.mvTable_SizingStretchProp):
                dpg.add_table_column(label="", width_fixed=True, init_width_or_weight=theme.px(28))
                dpg.add_table_column(label="Nome", init_width_or_weight=1.0)
                dpg.add_table_column(label="PID", width_fixed=True, init_width_or_weight=theme.px(70))
                dpg.add_table_column(label="CPU %", width_fixed=True, init_width_or_weight=theme.px(70))
                dpg.add_table_column(label="RAM MB", width_fixed=True, init_width_or_weight=theme.px(80))
                dpg.add_table_column(label="VRAM MB", width_fixed=True, init_width_or_weight=theme.px(85))
                dpg.add_table_column(label="Janela", width_fixed=True, init_width_or_weight=theme.px(65))

        with dpg.window(tag="pr_confirm", modal=True, show=False, no_title_bar=True, no_resize=True,
                        width=theme.px(440)):
            dpg.add_text("", tag="pr_confirm_text", wrap=theme.px(400))
            dpg.add_spacer(height=theme.px(6))
            with dpg.group(horizontal=True):
                danger_button("Encerrar mesmo assim", self._kill)
                dpg.add_button(label="Cancelar", callback=lambda: dpg.configure_item("pr_confirm", show=False))

    def on_show(self):
        if not self._rows and not self._scanning:
            self.do_scan()

    def update(self, snap):
        pass

    def do_scan(self):
        if self._scanning:
            return
        self._scanning = True
        dpg.set_value("pr_status", "Escaneando...")

        def work():
            try:
                results = scan(self.ctx.gpu)
            except Exception as exc:
                msg = f"Falhou: {exc}"
                self.ctx.run_on_ui(lambda: dpg.set_value("pr_status", msg))
            else:
                self.ctx.run_on_ui(lambda: self._fill(results))
            finally:
                self._scanning = False

        threading.Thread(target=work, name="scan", daemon=True).start()

    def _fill(self, results: list[dict]):
        for row in dpg.get_item_children("pr_table", slot=1) or []:
            dpg.delete_item(row)
        self._rows.clear()
        self._names.clear()
        for r in results[:MAX_ROWS]:
            pid = r["pid"]
            with dpg.table_row(parent="pr_table"):
                self._rows[pid] = dpg.add_checkbox()
                self._names[pid] = r["name"]
                dpg.add_text(r["name"])
                dpg.add_text(str(pid))
                dpg.add_text(f"{r['cpu_pct']:.1f}")
                dpg.add_text(str(r["ram_mb"]))
                dpg.add_text(str(r["gpu_mem_mb"]) if r["gpu_mem_mb"] else "")
                dpg.add_text("sim" if r["has_window"] else "")
        dpg.set_value("pr_status", f"{len(results)} processos (mostrando os {min(MAX_ROWS, len(results))} que mais consomem)")

    def _selected(self) -> list[int]:
        return [pid for pid, cb in self._rows.items() if dpg.get_value(cb)]

    def _lower(self):
        pids = self._selected()
        if not pids:
            self.ctx.controller.notify("Nenhum processo marcado", True)
            return
        errors = []
        for pid in pids:
            try:
                lower_priority(pid)
            except ScanError as exc:
                errors.append(str(exc))
        self.ctx.controller.notify(" | ".join(errors) if errors else f"Prioridade baixada em {len(pids)} processo(s)",
                                   bool(errors))

    def _ask_kill(self):
        pids = self._selected()
        if not pids:
            self.ctx.controller.notify("Nenhum processo marcado", True)
            return
        names = ", ".join(self._names.get(p, str(p)) for p in pids)
        dpg.set_value("pr_confirm_text", f"Encerrar {len(pids)} processo(s)?\n\n{names}\n\n"
                                         "Trabalho não salvo nesses programas será perdido.")
        w, h = dpg.get_viewport_client_width(), dpg.get_viewport_client_height()
        dpg.configure_item("pr_confirm", show=True, pos=(w // 2 - theme.px(220), h // 2 - theme.px(100)))

    def _kill(self):
        dpg.configure_item("pr_confirm", show=False)
        pids = self._selected()
        errors = []
        for pid in pids:
            try:
                kill_process(pid)
            except ScanError as exc:
                errors.append(str(exc))
        self.ctx.controller.notify(" | ".join(errors) if errors else f"{len(pids)} processo(s) encerrado(s)",
                                   bool(errors))
        self.do_scan()
