"""Estado aplicado que precisa sobreviver ao fechamento do app.

O lock de clock da GPU fica no driver depois que o app fecha, e o NVML não tem como ler
o lock atual. Por isso registramos aqui o que o app aplicou e em qual boot: se o PC
reiniciou desde então, o driver já soltou o lock e o registro é descartado.
"""

import json
import logging
import threading
from dataclasses import asdict, dataclass
from typing import Optional

import psutil

from core.paths import STATE_PATH

log = logging.getLogger("master_sword.state")


@dataclass
class AppliedState:
    boot_time: float = 0.0
    gpu_lock: Optional[list[int]] = None  # [min, max] aplicado por nós neste boot
    active_profile: Optional[str] = None
    profile_modified: bool = False  # mexeu em algo manualmente depois de aplicar o perfil


class StateStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.state = self._load()

    def _load(self) -> AppliedState:
        state = AppliedState()
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            state = AppliedState(**{k: v for k, v in data.items() if k in AppliedState.__annotations__})
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("state.json ilegível — começando do zero")

        boot = psutil.boot_time()
        if abs(state.boot_time - boot) > 5:
            # reiniciou: o driver soltou o lock; o perfil ativo não está mais inteiro aplicado
            if state.gpu_lock is not None and state.active_profile:
                state.profile_modified = True
            state.gpu_lock = None
            state.boot_time = boot
        return state

    def save(self):
        with self._lock:
            tmp = STATE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self.state), indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(STATE_PATH)

    def update(self, **changes):
        for key, value in changes.items():
            setattr(self.state, key, value)
        self.save()
