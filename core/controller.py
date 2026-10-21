"""Ponto único por onde passa toda ação que muda o hardware (UI, bandeja e perfis).

Mantém o registro do que foi aplicado (state.json) e avisa a UI por `notify`.
Thread-safe: a bandeja chama daqui da thread dela, a UI da thread principal.
"""

import logging
import threading
from typing import Callable, Optional

from core import profiles as profiles_mod
from core.cpu import BOOST_MODES, CpuControlError, get_boost_mode, set_boost_mode
from core.ec import FAN_MODE_LABELS, SHIFT_MODE_LABELS, EcError, MsiEc
from core.gpu import GpuControlError, GpuController
from core.profiles import GPU_LOCK, GPU_RELEASE, Profile
from core.settings import Settings, save_settings
from core.state import StateStore

log = logging.getLogger("master_sword.controller")

Notify = Callable[[str, bool], None]  # (mensagem, é_erro)


class Controller:
    def __init__(self, gpu: GpuController, ec: Optional[MsiEc], settings: Settings, store: StateStore):
        self.gpu = gpu
        self.ec = ec
        self.settings = settings
        self.store = store
        self._lock = threading.RLock()
        self._listeners: list[Notify] = []
        self.boost_mode: Optional[int] = None
        self.gpu.on_reconnect = self._reapply_after_reconnect
        self.refresh_boost()

    # ---------- avisos ----------

    def add_listener(self, fn: Notify):
        self._listeners.append(fn)

    def notify(self, msg: str, error: bool = False):
        (log.warning if error else log.info)("%s", msg)
        for fn in self._listeners:
            try:
                fn(msg, error)
            except Exception:
                log.exception("listener de aviso falhou")

    # ---------- estado ----------

    @property
    def state(self):
        return self.store.state

    def refresh_boost(self):
        try:
            self.boost_mode = get_boost_mode()
        except CpuControlError as exc:
            log.warning("Não consegui ler o boost: %s", exc)

    def _manual_change(self):
        if self.state.active_profile and not self.state.profile_modified:
            self.store.update(profile_modified=True)

    def ec_writable(self) -> bool:
        return self.ec is not None and self.ec.supported and self.settings.fan_control_enabled

    # ---------- GPU ----------

    def set_gpu_lock(self, min_mhz: int, max_mhz: int, manual: bool = True) -> bool:
        with self._lock:
            try:
                self.gpu.set_locked_clocks(min_mhz, max_mhz)
            except GpuControlError as exc:
                self.notify(str(exc), True)
                return False
            lo, hi = sorted((min_mhz, max_mhz))
            self.store.update(gpu_lock=[lo, hi])
            if manual:
                self._manual_change()
                self.notify(f"GPU travada em {hi} MHz" if lo == hi else f"GPU travada em {lo}–{hi} MHz")
            return True

    def release_gpu_lock(self, manual: bool = True) -> bool:
        with self._lock:
            try:
                self.gpu.reset_locked_clocks()
            except GpuControlError as exc:
                self.notify(str(exc), True)
                return False
            self.store.update(gpu_lock=None)
            if manual:
                self._manual_change()
                self.notify("Lock da GPU solto")
            return True

    def _reapply_after_reconnect(self):
        # reset do driver / volta da suspensão pode ter soltado o lock: reaplica o que estava valendo
        lock = self.state.gpu_lock
        if lock:
            try:
                self.gpu.set_locked_clocks(*lock)
                log.info("Lock da GPU reaplicado depois da reconexão: %s", lock)
            except GpuControlError as exc:
                log.warning("Não consegui reaplicar o lock depois da reconexão: %s", exc)

    # ---------- CPU ----------

    def set_boost(self, mode: int, manual: bool = True) -> bool:
        with self._lock:
            try:
                set_boost_mode(mode)
            except (CpuControlError, ValueError) as exc:
                self.notify(f"Boost da CPU: {exc}", True)
                return False
            self.boost_mode = mode
            if manual:
                self._manual_change()
                self.notify(f"Boost da CPU: {BOOST_MODES[mode].lower()}")
            return True

    # ---------- EC (fan) ----------

    def _ec_call(self, fn, *args, ok_msg: str, manual: bool = True) -> bool:
        with self._lock:
            if not self.ec_writable():
                self.notify("Controle do fan desligado — habilite na página Fan.", True)
                return False
            try:
                fn(*args)
            except (EcError, ValueError) as exc:
                self.notify(f"EC: {exc}", True)
                return False
            if manual:
                self._manual_change()
                self.notify(ok_msg)
            return True

    def set_fan_mode(self, mode: str, manual: bool = True) -> bool:
        return self._ec_call(self.ec.set_fan_mode, mode, ok_msg=f"Fan: {FAN_MODE_LABELS.get(mode, mode).lower()}", manual=manual)

    def set_cooler_boost(self, on: bool, manual: bool = True) -> bool:
        return self._ec_call(self.ec.set_cooler_boost, on,
                             ok_msg="Cooler Boost ligado" if on else "Cooler Boost desligado", manual=manual)

    def set_shift_mode(self, mode: str, manual: bool = True) -> bool:
        return self._ec_call(self.ec.set_shift_mode, mode, ok_msg=f"Modo MSI: {SHIFT_MODE_LABELS.get(mode, mode)}", manual=manual)

    def set_curve_speeds(self, fan: str, speeds: list[int]) -> bool:
        if not self.settings.fan_curve_enabled:
            self.notify("Edição de curva desligada (experimental).", True)
            return False
        return self._ec_call(self.ec.set_curve_speeds, fan, speeds, ok_msg=f"Curva do fan da {fan.upper()} gravada")

    # ---------- perfis ----------

    def apply_profile(self, name: str) -> bool:
        profile = profiles_mod.get_profile(name)
        if profile is None:
            self.notify(f"Perfil '{name}' não existe mais", True)
            return False
        with self._lock:
            failures: list[str] = []
            if profile.gpu_action == GPU_LOCK:
                if not self.set_gpu_lock(profile.gpu_min_mhz, profile.gpu_max_mhz, manual=False):
                    failures.append("lock da GPU")
            elif profile.gpu_action == GPU_RELEASE:
                if not self.release_gpu_lock(manual=False):
                    failures.append("soltar GPU")
            if profile.cpu_boost_mode is not None and not self.set_boost(profile.cpu_boost_mode, manual=False):
                failures.append("boost")
            if profile.uses_ec():
                if not self.ec_writable():
                    failures.append("fan (controle desligado)")
                else:
                    if profile.fan_mode and not self.set_fan_mode(profile.fan_mode, manual=False):
                        failures.append("modo do fan")
                    if profile.cooler_boost is not None and not self.set_cooler_boost(profile.cooler_boost, manual=False):
                        failures.append("Cooler Boost")
                    if profile.shift_mode and not self.set_shift_mode(profile.shift_mode, manual=False):
                        failures.append("modo de energia")

            self.store.update(active_profile=profile.name, profile_modified=bool(failures))
            if failures:
                self.notify(f"Perfil '{profile.name}' aplicado com falhas: {', '.join(failures)}", True)
            else:
                self.notify(f"Perfil '{profile.name}' aplicado")
            return not failures

    def capture_current(self, name: str) -> Profile:
        """Perfil a partir do estado REAL aplicado agora (não dos campos da tela)."""
        p = Profile(name=name)
        lock = self.state.gpu_lock
        if lock:
            p.gpu_action, p.gpu_min_mhz, p.gpu_max_mhz = GPU_LOCK, lock[0], lock[1]
        else:
            p.gpu_action = GPU_RELEASE
        p.cpu_boost_mode = self.boost_mode
        if self.ec is not None:
            try:
                ec_state = self.ec.read_state()
                p.fan_mode = ec_state["fan_mode"]
                p.cooler_boost = ec_state["cooler_boost"]
                p.shift_mode = ec_state["shift_mode"]
            except EcError:
                pass
        return p

    def on_profile_renamed(self, old: str, new: str):
        if self.state.active_profile == old:
            self.store.update(active_profile=new)
        if self.settings.start_profile == old:
            self.settings.start_profile = new
            save_settings(self.settings)

    def on_profile_deleted(self, name: str):
        if self.state.active_profile == name:
            self.store.update(active_profile=None, profile_modified=False)
        if self.settings.start_profile == name:
            self.settings.start_profile = None
            save_settings(self.settings)

    # ---------- ciclo de vida ----------

    def startup(self):
        if self.settings.start_profile:
            self.apply_profile(self.settings.start_profile)

    def shutdown(self):
        if self.settings.release_lock_on_exit and self.state.gpu_lock:
            self.release_gpu_lock(manual=False)
