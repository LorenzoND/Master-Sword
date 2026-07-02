"""Perfis: aplica várias configs (GPU + CPU) de uma vez, com um clique."""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from core.gpu_control import GpuController, GpuControlError
from core.cpu_control import set_boost_mode, CpuControlError

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


@dataclass
class Profile:
    name: str
    gpu_clock_min_mhz: Optional[int] = None
    gpu_clock_max_mhz: Optional[int] = None
    gpu_reset_clocks: bool = False  # True = solta qualquer lock existente (usado por perfis "sem limite")
    gpu_power_limit_w: Optional[float] = None
    cpu_boost_mode: Optional[int] = None  # índice em core.cpu_control.BOOST_MODES

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        return cls(**data)


def list_profiles() -> list[str]:
    PROFILES_DIR.mkdir(exist_ok=True)
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def save_profile(profile: Profile):
    PROFILES_DIR.mkdir(exist_ok=True)
    path = PROFILES_DIR / f"{profile.name}.json"
    path.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_profile(name: str) -> Profile:
    path = PROFILES_DIR / f"{name}.json"
    return Profile.from_dict(json.loads(path.read_text(encoding="utf-8")))


def delete_profile(name: str):
    (PROFILES_DIR / f"{name}.json").unlink(missing_ok=True)


def apply_profile(profile: Profile, gpu: GpuController) -> list[str]:
    """Aplica o perfil. Retorna lista de avisos não-fatais (ex: falta de admin) —
    um item do perfil falhar não impede os outros de serem aplicados."""
    warnings: list[str] = []

    if profile.gpu_clock_min_mhz is not None and profile.gpu_clock_max_mhz is not None:
        try:
            gpu.set_locked_clocks(profile.gpu_clock_min_mhz, profile.gpu_clock_max_mhz)
        except GpuControlError as exc:
            warnings.append(f"Clock da GPU: {exc}")
    elif profile.gpu_reset_clocks:
        try:
            gpu.reset_locked_clocks()
        except GpuControlError as exc:
            warnings.append(f"Reset de clock da GPU: {exc}")

    if profile.gpu_power_limit_w is not None:
        try:
            gpu.set_power_limit_w(profile.gpu_power_limit_w)
        except GpuControlError as exc:
            warnings.append(f"Power limit da GPU: {exc}")

    if profile.cpu_boost_mode is not None:
        try:
            set_boost_mode(profile.cpu_boost_mode)
        except CpuControlError as exc:
            warnings.append(f"Boost da CPU: {exc}")

    return warnings


DEFAULT_PROFILES = [
    Profile(name="Jogo - termico", gpu_clock_min_mhz=900, gpu_clock_max_mhz=900, cpu_boost_mode=0),
    Profile(name="Max Performance", gpu_reset_clocks=True, cpu_boost_mode=2),
]


def seed_default_profiles():
    """Cria os perfis padrão só se ainda não existir nenhum perfil salvo."""
    if list_profiles():
        return
    for profile in DEFAULT_PROFILES:
        save_profile(profile)
