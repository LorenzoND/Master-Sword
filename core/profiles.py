"""Perfis: um conjunto de ajustes (GPU, CPU, fan) aplicado de uma vez.

Cada campo tem um "não mexer" explícito: um perfil só altera o que ele define.
Formato v2; perfis da v1 são convertidos na primeira leitura (o original vai pra
profiles/_v1_backup).
"""

import json
import logging
import re
import shutil
from dataclasses import asdict, dataclass
from typing import Optional

from core.cpu import BOOST_MODES
from core.ec import FAN_MODE_LABELS, SHIFT_MODE_LABELS
from core.paths import PROFILES_DIR

log = logging.getLogger("master_sword.profiles")

GPU_KEEP = "manter"
GPU_LOCK = "travar"
GPU_RELEASE = "soltar"

SCHEMA = 2


@dataclass
class Profile:
    name: str
    gpu_action: str = GPU_KEEP
    gpu_min_mhz: int = 900
    gpu_max_mhz: int = 900
    cpu_boost_mode: Optional[int] = None  # None = não mexer
    fan_mode: Optional[str] = None  # chave de core.ec.FAN_MODES
    cooler_boost: Optional[bool] = None
    shift_mode: Optional[str] = None  # chave de core.ec.SHIFT_MODES
    schema: int = SCHEMA

    def summary(self) -> str:
        parts = []
        if self.gpu_action == GPU_LOCK:
            if self.gpu_min_mhz == self.gpu_max_mhz:
                parts.append(f"GPU travada em {self.gpu_max_mhz} MHz")
            else:
                parts.append(f"GPU {self.gpu_min_mhz}–{self.gpu_max_mhz} MHz")
        elif self.gpu_action == GPU_RELEASE:
            parts.append("GPU sem lock")
        if self.cpu_boost_mode is not None:
            parts.append(f"boost {BOOST_MODES.get(self.cpu_boost_mode, '?').lower()}")
        if self.fan_mode:
            parts.append(f"fan {FAN_MODE_LABELS.get(self.fan_mode, self.fan_mode).lower()}")
        if self.cooler_boost is not None:
            parts.append("Cooler Boost ligado" if self.cooler_boost else "Cooler Boost desligado")
        if self.shift_mode:
            parts.append(f"modo {SHIFT_MODE_LABELS.get(self.shift_mode, self.shift_mode)}")
        return " · ".join(parts) if parts else "Não altera nada"

    def uses_ec(self) -> bool:
        return any(v is not None for v in (self.fan_mode, self.cooler_boost, self.shift_mode))

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        if data.get("schema", 1) < 2:
            return cls._from_v1(data)
        known = cls.__annotations__.keys()
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def _from_v1(cls, data: dict) -> "Profile":
        p = cls(name=data["name"])
        if data.get("gpu_clock_min_mhz") is not None and data.get("gpu_clock_max_mhz") is not None:
            p.gpu_action = GPU_LOCK
            p.gpu_min_mhz = int(data["gpu_clock_min_mhz"])
            p.gpu_max_mhz = int(data["gpu_clock_max_mhz"])
        elif data.get("gpu_reset_clocks"):
            p.gpu_action = GPU_RELEASE
        p.cpu_boost_mode = data.get("cpu_boost_mode")
        return p


def _slug(name: str) -> str:
    slug = re.sub(r"[^\w\- ]", "_", name, flags=re.UNICODE).strip(" .")
    return slug or "perfil"


def _path_for(name: str):
    return PROFILES_DIR / f"{_slug(name)}.json"


def list_profiles() -> list[Profile]:
    PROFILES_DIR.mkdir(exist_ok=True)
    profiles = []
    for path in PROFILES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = Profile.from_dict(data)
        except Exception:
            log.exception("Perfil ilegível ignorado: %s", path.name)
            continue
        if data.get("schema", 1) < SCHEMA:
            _migrate_v1_file(path, profile)
        profiles.append(profile)
    return sorted(profiles, key=lambda p: p.name.lower())


def _migrate_v1_file(path, profile: Profile):
    backup_dir = PROFILES_DIR / "_v1_backup"
    backup_dir.mkdir(exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)
    path.unlink()
    save_profile(profile)
    log.info("Perfil '%s' convertido pro formato v2", profile.name)


def get_profile(name: str) -> Optional[Profile]:
    return next((p for p in list_profiles() if p.name == name), None)


def exists(name: str) -> bool:
    return any(p.name.lower() == name.lower() for p in list_profiles())


def save_profile(profile: Profile, original_name: Optional[str] = None):
    """Salva. Se o perfil foi renomeado no editor, apaga o arquivo do nome antigo."""
    PROFILES_DIR.mkdir(exist_ok=True)
    if original_name and original_name != profile.name:
        delete_profile(original_name)
    profile.schema = SCHEMA
    path = _path_for(profile.name)
    path.write_text(json.dumps(asdict(profile), indent=2, ensure_ascii=False), encoding="utf-8")


def delete_profile(name: str):
    for path in PROFILES_DIR.glob("*.json"):
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("name") == name:
                path.unlink()
        except Exception:
            continue


DEFAULT_PROFILES = [
    Profile(name="Jogo - térmico", gpu_action=GPU_LOCK, gpu_min_mhz=900, gpu_max_mhz=900, cpu_boost_mode=0),
    Profile(name="Desempenho máximo", gpu_action=GPU_RELEASE, cpu_boost_mode=2),
]


def seed_default_profiles():
    """Cria os perfis padrão só se ainda não existir nenhum."""
    if list_profiles():
        return
    for profile in DEFAULT_PROFILES:
        save_profile(profile)
