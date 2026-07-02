"""Estado compartilhado entre o dashboard principal e o overlay (processo separado).

Write atômico (escreve em .tmp e renomeia) pra o overlay nunca ler um JSON pela metade.
"""

import json
from pathlib import Path
from typing import Optional

STATE_PATH = Path(__file__).resolve().parent.parent / "_live_stats.json"


def write(stats: dict):
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(stats), encoding="utf-8")
    tmp.replace(STATE_PATH)


def read() -> Optional[dict]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
