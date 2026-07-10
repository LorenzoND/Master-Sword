"""Estado compartilhado entre o dashboard principal e o overlay (processo separado).

Write atômico (escreve em .tmp e renomeia) pra o overlay nunca ler um JSON pela metade.
"""

import json
import time
from pathlib import Path
from typing import Optional

STATE_PATH = Path(__file__).resolve().parent.parent / "_live_stats.json"


def write(stats: dict):
    """Escreve os stats de forma atômica.

    No Windows, `Path.replace` levanta PermissionError [WinError 5] se o destino
    estiver aberto por outro processo — e o overlay lê este mesmo arquivo a cada
    ~1s. Quando as janelas de leitura/escrita coincidem, o replace falha. Um frame
    de stats perdido é inofensivo, então tentamos algumas vezes e desistimos em
    silêncio em vez de deixar a exceção subir e derrubar o app inteiro.
    """
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(stats), encoding="utf-8")
    for attempt in range(5):
        try:
            tmp.replace(STATE_PATH)
            return
        except PermissionError:
            time.sleep(0.02)
    # Última tentativa falhou; limpa o .tmp pra não acumular lixo e segue a vida.
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass


def read() -> Optional[dict]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
