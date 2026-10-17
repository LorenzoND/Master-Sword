"""Preferências do usuário (settings.json). Chave desconhecida é ignorada, chave faltando usa o padrão."""

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from typing import Optional

from core.paths import SETTINGS_PATH

log = logging.getLogger("master_sword.settings")

# Itens do overlay. Padrão = o que estava ligado no OSD do MSI Afterburner do Lorenzo,
# trocando os 12 "CPUn usage" por uma linha só de uso total (opcional por núcleo).
OVERLAY_ITEMS = {
    "gpu_temp": "GPU temperatura",
    "gpu_usage": "GPU uso",
    "gpu_clock": "GPU clock",
    "gpu_power": "GPU power",
    "gpu_vram": "GPU VRAM",
    "gpu_limit": "GPU motivo de limite",
    "cpu_temp": "CPU temperatura",
    "cpu_usage": "CPU uso",
    "cpu_clock": "CPU clock",
    "cpu_power": "CPU power",
    "cpu_limit": "CPU motivo de limite",
    "cpu_cores": "CPU uso por núcleo",
    "ram": "RAM",
    "fans": "Fans",
    "fps": "FPS e frametime",
    "frametime_graph": "Gráfico de frametime",
}
_DEFAULT_ITEMS = {k: k != "cpu_cores" for k in OVERLAY_ITEMS}

OVERLAY_POSITIONS = {
    "top-left": "Canto superior esquerdo",
    "top-right": "Canto superior direito",
    "bottom-left": "Canto inferior esquerdo",
    "bottom-right": "Canto inferior direito",
}


@dataclass
class Settings:
    start_profile: Optional[str] = None
    release_lock_on_exit: bool = False
    alerts_enabled: bool = True
    alert_gpu_temp: int = 87
    alert_cpu_temp: int = 95
    history_window_s: int = 300
    overlay_mode: str = "rtss"  # "rtss" | "desktop" | "off"
    overlay_visible: bool = True
    overlay_items: dict = field(default_factory=lambda: dict(_DEFAULT_ITEMS))
    overlay_color: str = "FF8000"  # mesma cor do OSD atual do RTSS
    overlay_position: str = "top-left"
    overlay_hotkey: str = "PageDown"  # mesmo atalho que estava no Afterburner
    fan_control_enabled: bool = False  # trava de segurança: escrita no EC só depois de habilitar
    fan_curve_enabled: bool = False


def load_settings() -> Settings:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except Exception:
        log.exception("settings.json ilegível — usando padrões")
        return Settings()
    known = {f.name for f in fields(Settings)}
    settings = Settings(**{k: v for k, v in data.items() if k in known})
    settings.overlay_items = {**_DEFAULT_ITEMS, **{k: bool(v) for k, v in settings.overlay_items.items()
                                                  if k in OVERLAY_ITEMS}}
    return settings


def save_settings(settings: Settings):
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SETTINGS_PATH)
