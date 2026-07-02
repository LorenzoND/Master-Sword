"""Varredura de processos: quem tá consumindo CPU/RAM/GPU, e ação em cima disso.

Baixar prioridade é a ação padrão seguível (reversível, estilo Process Lasso/ProBalance).
Encerrar processo (kill) existe, mas é sempre uma ação explícita e manual — nunca deve ser
chamada automaticamente por um perfil ou por qualquer lógica que não seja o usuário clicando.
"""

import ctypes
import time
from typing import Optional

import psutil

from core.gpu_control import GpuController

user32 = ctypes.windll.user32
_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumWindows.argtypes = [_EnumWindowsProc, ctypes.c_void_p]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]


class ScanError(RuntimeError):
    pass


def _visible_window_pids() -> set[int]:
    """PIDs que possuem pelo menos uma janela visível com título — heurística de
    'está em primeiro plano / é um app de verdade', não só um processo de fundo."""
    pids: set[int] = set()

    def callback(hwnd, lparam):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pids.add(pid.value)
        return True

    user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return pids


# pseudo-processos do kernel — não são acionáveis (não dá pra baixar prioridade/matar) e
# "System Idle Process" reporta uso de CPU invertido (mostra tempo ocioso, não consumo real)
_SKIP_PIDS = {0, 4}


def scan(gpu: Optional[GpuController] = None, sample_window_s: float = 0.3) -> list[dict]:
    """Snapshot de processos ordenado por consumo (CPU desc, depois RAM desc)."""
    visible = _visible_window_pids()

    gpu_by_pid: dict[int, dict] = {}
    if gpu is not None:
        for p in gpu.list_processes():
            gpu_by_pid[p["pid"]] = p

    procs = list(psutil.process_iter(["pid", "name"]))
    for p in procs:
        try:
            p.cpu_percent(None)  # primeira chamada estabelece a baseline (psutil warm-up)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(sample_window_s)

    results = []
    for p in procs:
        if p.pid in _SKIP_PIDS:
            continue
        try:
            name = p.name()
            cpu_pct = p.cpu_percent(None)
            ram_mb = p.memory_info().rss // (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

        pid = p.pid
        gpu_info = gpu_by_pid.get(pid)
        results.append({
            "pid": pid,
            "name": name,
            "cpu_pct": round(cpu_pct, 1),
            "ram_mb": ram_mb,
            "gpu_mem_mb": gpu_info["gpu_mem_mb"] if gpu_info else 0,
            "has_window": pid in visible,
        })

    return sorted(results, key=lambda r: (r["cpu_pct"], r["ram_mb"]), reverse=True)


def lower_priority(pid: int):
    try:
        psutil.Process(pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        raise ScanError(f"Não consegui baixar a prioridade do PID {pid}: {exc}") from exc


def restore_priority(pid: int):
    try:
        psutil.Process(pid).nice(psutil.NORMAL_PRIORITY_CLASS)
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        raise ScanError(f"Não consegui restaurar a prioridade do PID {pid}: {exc}") from exc


def kill_process(pid: int, force: bool = False):
    """Encerra um processo. SEMPRE deve ser chamada só em resposta a um clique explícito
    do usuário, com confirmação prévia na UI — nunca em lógica automática/perfil."""
    try:
        proc = psutil.Process(pid)
        proc.kill() if force else proc.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        raise ScanError(f"Não consegui encerrar o PID {pid}: {exc}") from exc
