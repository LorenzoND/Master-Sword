"""Abertura sem console e sem pedir UAC toda vez, com instância única.

Fluxo:
1. O atalho abre `pythonw main.pyw` SEM elevação (nada de janela preta, nada de SmartScreen).
2. Sem admin, ele só dispara a tarefa agendada "Master-Sword" (criada pelo install.ps1 com
   "executar com privilégios mais altos") e sai. O Agendador sobe o app já elevado, sem UAC.
3. O processo elevado pega um mutex nomeado. Se já existe outra instância, ele só manda ela
   aparecer (evento nomeado) e sai — clicar duas vezes no atalho não abre dois apps.
"""

import ctypes
import logging
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from core.paths import LOGON_TASK_NAME, ROOT, TASK_NAME

log = logging.getLogger("master_sword.launcher")

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_k32.CreateMutexW.restype = wintypes.HANDLE
_k32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_k32.CreateEventW.restype = wintypes.HANDLE
_k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenEventW.restype = wintypes.HANDLE
_k32.SetEvent.argtypes = [wintypes.HANDLE]
_k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_k32.WaitForSingleObject.restype = wintypes.DWORD
_k32.CloseHandle.argtypes = [wintypes.HANDLE]

MUTEX_NAME = "Local\\MasterSword.Instance"
SHOW_EVENT_NAME = "Local\\MasterSword.Show"
ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def pythonw() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def run_task() -> bool:
    result = subprocess.run(["schtasks", "/run", "/tn", TASK_NAME], capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode == 0


def elevate_via_uac():
    """Plano B sem a tarefa instalada: eleva o powershell.exe (binário confiável — elevar o
    python.exe do venv direto é barrado pelo SmartScreen) e ele abre o pythonw já elevado."""
    cmd = f"Start-Process -FilePath '{pythonw()}' -ArgumentList '\"{ROOT / 'main.pyw'}\"' -WorkingDirectory '{ROOT}'"
    ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe",
                                        f'-NoProfile -WindowStyle Hidden -Command "{cmd}"', str(ROOT), 0)


class SingleInstance:
    def __init__(self):
        self._mutex = _k32.CreateMutexW(None, False, MUTEX_NAME)
        self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        self._event = None if self.already_running else _k32.CreateEventW(None, False, False, SHOW_EVENT_NAME)

    def signal_existing(self):
        handle = _k32.OpenEventW(EVENT_MODIFY_STATE, False, SHOW_EVENT_NAME)
        if handle:
            _k32.SetEvent(handle)
            _k32.CloseHandle(handle)

    def show_requested(self) -> bool:
        """Não bloqueia: True se outra execução pediu pra janela aparecer."""
        return bool(self._event) and _k32.WaitForSingleObject(self._event, 0) == 0


# ---------- iniciar com o Windows (tarefa no logon) ----------

def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)


def task_exists(name: str = TASK_NAME) -> bool:
    result = subprocess.run(["schtasks", "/query", "/tn", name], capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode == 0


def set_autostart(enabled: bool) -> tuple[bool, str]:
    """Cria/remove a tarefa de logon (precisa do app elevado — e ele sempre está)."""
    if not enabled:
        r = _ps(f"Unregister-ScheduledTask -TaskName '{LOGON_TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue")
        return True, ""
    script = (
        f"$a = New-ScheduledTaskAction -Execute '{pythonw()}' -Argument '\"{ROOT / 'main.pyw'}\" --minimized' "
        f"-WorkingDirectory '{ROOT}';"
        "$t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME;"
        "$p = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest;"
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::Zero);"
        f"Register-ScheduledTask -TaskName '{LOGON_TASK_NAME}' -Action $a -Trigger $t -Principal $p "
        "-Settings $s -Force | Out-Null"
    )
    r = _ps(script)
    return r.returncode == 0, (r.stderr or "").strip()
