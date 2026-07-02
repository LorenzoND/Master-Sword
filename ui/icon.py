"""Ícone pixel-art da Master Sword. Gerado uma vez com Pillow (já é dependência do projeto,
nenhuma lib nova) e cacheado em disco — não desenha nada de novo a cada inicialização."""

from pathlib import Path

from PIL import Image

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
ICON_PNG_PATH = ASSETS_DIR / "icon.png"
ICON_ICO_PATH = ASSETS_DIR / "icon.ico"

_SCALE = 8  # desenha em 16x16 "pixels" grandes e amplia pra ficar nítido (nearest-neighbor)

_COLORS = {
    ".": (0, 0, 0, 0),          # transparente
    "b": (94, 158, 232, 255),   # lâmina, azul
    "B": (186, 220, 255, 255),  # lâmina, brilho central
    "G": (206, 164, 82, 255),   # guarda/pomo, dourado
    "g": (150, 116, 56, 255),   # guarda, dourado escuro (sombra)
    "H": (70, 110, 176, 255),   # cabo, azul escuro
    "T": (92, 210, 198, 255),   # gema, verde-azulado
}

# 16x16, simétrico esquerda-direita — lâmina no topo, guarda, cabo, pomo embaixo.
_GRID = [
    ".......bb.......",
    "......bBBb......",
    "......bBBb......",
    ".....bbBBbb.....",
    ".....bbBBbb.....",
    ".....bbBBbb.....",
    ".....bbBBbb.....",
    ".....bbBBbb.....",
    ".....bbBBbb.....",
    ".GGGGGGTTGGGGGG.",
    "..gggggggggggg..",
    "......HHHH......",
    "......HHHH......",
    "......HHHH......",
    ".....GGGGGG.....",
    "......GTTG......",
]


def _build_image() -> Image.Image:
    rows = [row for row in _GRID]
    height = len(rows)
    width = len(rows[0])
    assert all(len(r) == width for r in rows), "linhas do grid do ícone com tamanhos diferentes"

    small = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            small.putpixel((x, y), _COLORS[char])

    return small.resize((width * _SCALE, height * _SCALE), Image.NEAREST)


def ensure_icon_assets() -> None:
    """Gera assets/icon.png e assets/icon.ico se ainda não existirem."""
    if ICON_PNG_PATH.exists() and ICON_ICO_PATH.exists():
        return

    ASSETS_DIR.mkdir(exist_ok=True)
    image = _build_image()
    image.save(ICON_PNG_PATH)
    image.save(ICON_ICO_PATH, sizes=[(16, 16), (32, 32), (64, 64), (128, 128)])


def load_tray_image() -> Image.Image:
    ensure_icon_assets()
    return Image.open(ICON_PNG_PATH)
