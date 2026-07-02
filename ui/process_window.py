"""Janela secundária: varredura de processos, baixar prioridade ou encerrar.

Encerrar processo sempre passa por um modal de confirmação — nunca acontece sem o usuário
ver explicitamente quais processos serão mortos e clicar de novo pra confirmar.
"""

import dearpygui.dearpygui as dpg

from core.scan import scan, lower_priority, kill_process, ScanError
from core.gpu_control import GpuController
from ui import theme

WINDOW_TAG = "process_window"
TABLE_TAG = "process_table"
STATUS_TAG = "process_status"
MODAL_TAG = "kill_confirm_modal"
MODAL_TEXT_TAG = "kill_confirm_text"

MAX_ROWS = 60  # corta na UI pros processos que mais consomem — não pesa a tabela à toa


class ProcessWindow:
    def __init__(self, gpu: GpuController):
        self.gpu = gpu
        self._row_checkboxes: dict[int, int] = {}  # pid -> tag do checkbox
        self._row_names: dict[int, str] = {}
        self._built = False

    def build(self):
        if self._built:
            return

        with dpg.window(tag=WINDOW_TAG, label="Processos", width=640, height=480,
                         show=False, pos=(60, 60)):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Escanear", callback=self.do_scan)
                dpg.add_button(label="Baixar prioridade dos selecionados", callback=self.do_lower_selected)
                dpg.add_button(label="Encerrar selecionados", callback=self._confirm_kill_selected)

            dpg.add_text("", tag=STATUS_TAG, color=theme.TEXT_MUTED)
            dpg.add_separator()

            with dpg.table(tag=TABLE_TAG, header_row=True, row_background=True,
                            borders_innerH=True, borders_outerH=True, borders_innerV=True,
                            borders_outerV=True, scrollY=True, height=360):
                dpg.add_table_column(label="", width_fixed=True, init_width_or_weight=28)
                dpg.add_table_column(label="Nome")
                dpg.add_table_column(label="PID", width_fixed=True, init_width_or_weight=60)
                dpg.add_table_column(label="CPU%", width_fixed=True, init_width_or_weight=55)
                dpg.add_table_column(label="RAM MB", width_fixed=True, init_width_or_weight=70)
                dpg.add_table_column(label="VRAM MB", width_fixed=True, init_width_or_weight=70)
                dpg.add_table_column(label="Janela", width_fixed=True, init_width_or_weight=55)

        with dpg.window(tag=MODAL_TAG, modal=True, show=False, no_title_bar=True,
                         pos=(200, 200), width=380):
            dpg.add_text("", tag=MODAL_TEXT_TAG, wrap=340)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Encerrar mesmo assim", callback=self._do_kill_selected)
                dpg.add_button(label="Cancelar", callback=lambda: dpg.configure_item(MODAL_TAG, show=False))

        self._built = True

    def toggle(self):
        self.build()
        was_visible = dpg.get_item_configuration(WINDOW_TAG)["show"]
        dpg.configure_item(WINDOW_TAG, show=not was_visible)
        if not was_visible:
            self.do_scan()

    def set_status(self, msg: str, error: bool = False):
        dpg.set_value(STATUS_TAG, msg)
        dpg.configure_item(STATUS_TAG, color=theme.ERROR if error else theme.TEXT_MUTED)

    def do_scan(self):
        self.set_status("Escaneando...")
        results = scan(self.gpu)

        for row in dpg.get_item_children(TABLE_TAG, slot=1) or []:
            dpg.delete_item(row)
        self._row_checkboxes.clear()
        self._row_names.clear()

        for r in results[:MAX_ROWS]:
            pid = r["pid"]
            with dpg.table_row(parent=TABLE_TAG):
                self._row_checkboxes[pid] = dpg.add_checkbox()
                self._row_names[pid] = r["name"]
                dpg.add_text(r["name"])
                dpg.add_text(str(pid))
                dpg.add_text(f"{r['cpu_pct']:.1f}")
                dpg.add_text(str(r["ram_mb"]))
                dpg.add_text(str(r["gpu_mem_mb"]))
                dpg.add_text("sim" if r["has_window"] else "")

        self.set_status(f"{len(results)} processos no total (mostrando os {min(MAX_ROWS, len(results))} que mais consomem)")

    def _selected_pids(self) -> list[int]:
        return [pid for pid, tag in self._row_checkboxes.items() if dpg.get_value(tag)]

    def do_lower_selected(self):
        pids = self._selected_pids()
        if not pids:
            self.set_status("Nenhum processo selecionado", error=True)
            return
        errors = []
        for pid in pids:
            try:
                lower_priority(pid)
            except ScanError as exc:
                errors.append(str(exc))
        self.set_status(
            " | ".join(errors) if errors else f"Prioridade baixada em {len(pids)} processo(s)",
            error=bool(errors),
        )

    def _confirm_kill_selected(self):
        pids = self._selected_pids()
        if not pids:
            self.set_status("Nenhum processo selecionado", error=True)
            return
        names = ", ".join(self._row_names.get(pid, str(pid)) for pid in pids)
        dpg.set_value(
            MODAL_TEXT_TAG,
            f"Encerrar {len(pids)} processo(s)?\n\n{names}\n\n"
            "Isso pode causar perda de dado não salvo nesses programas.",
        )
        dpg.configure_item(MODAL_TAG, show=True)

    def _do_kill_selected(self):
        dpg.configure_item(MODAL_TAG, show=False)
        pids = self._selected_pids()
        errors = []
        for pid in pids:
            try:
                kill_process(pid)
            except ScanError as exc:
                errors.append(str(exc))
        self.set_status(
            " | ".join(errors) if errors else f"{len(pids)} processo(s) encerrado(s)",
            error=bool(errors),
        )
        self.do_scan()
