"""Log em arquivo com rotação + captura de exceção não tratada (main thread e threads).

O app roda via pythonw (sem console), então o log é o único rastro de qualquer erro.
O log antigo crescia sem limite (chegou a 37MB repetindo o mesmo traceback do NVML);
aqui ele roda em 3 arquivos de 1MB, e `log_throttled` evita repetir o mesmo erro a cada ciclo.
"""

import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from core.paths import LOGS_DIR

LOG_PATH = LOGS_DIR / "master-sword.log"

log = logging.getLogger("master_sword")

_last_logged: dict[str, float] = {}
_last_lock = threading.Lock()


def setup_logging():
    LOGS_DIR.mkdir(exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
    ]
    if sys.stdout is not None:  # pythonw não tem stdout
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )

    def _excepthook(exc_type, exc, tb):
        log.critical("Exceção não tratada — app encerrando", exc_info=(exc_type, exc, tb))

    def _thread_excepthook(args):
        log.error("Exceção não tratada na thread %s", args.thread.name if args.thread else "?",
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook


def log_throttled(key: str, msg: str, *args, level=logging.WARNING, every_s: float = 300, exc_info=False):
    """Loga no máximo uma vez a cada `every_s` segundos por chave."""
    now = time.monotonic()
    with _last_lock:
        if now - _last_logged.get(key, -1e9) < every_s:
            return
        _last_logged[key] = now
    log.log(level, msg, *args, exc_info=exc_info)
