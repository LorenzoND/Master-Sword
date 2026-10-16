"""Caminhos do projeto — tudo que o app grava fica dentro da pasta dele."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
PROFILES_DIR = ROOT / "profiles"
LOGS_DIR = ROOT / "logs"
STATE_PATH = ROOT / "state.json"
SETTINGS_PATH = ROOT / "settings.json"

TASK_NAME = "Master-Sword"
LOGON_TASK_NAME = "Master-Sword (logon)"
