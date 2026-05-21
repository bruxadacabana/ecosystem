"""
Gera ícones PNG para a extensão AKASHA a partir das definições de cor e forma.
Usa apenas Pillow — sem dependência de inkscape ou cairosvg.

Uso:
    uv run gen_icons.py
    python gen_icons.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent

ACTIVE_FILL   = (212, 168, 32)   # #D4A820
INACTIVE_FILL = (74,  80,  96)   # #4A5060
BG_COLOR      = (18,  22,  30)   # #12161E
SIZES         = [16, 48, 128]


def _hex_color(r: int, g: int, b: int) -> tuple[int, int, int, int]:
    return (r, g, b, 255)


def _hexagon_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    """Vértices de hexágono flat-top (topo e base planos)."""
    return [
        (cx + r * math.cos(math.pi / 3 * i),
         cy + r * math.sin(math.pi / 3 * i))
        for i in range(6)
    ]


def render_icon(size: int, fill: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx = cy = size / 2

    # Fundo com cantos arredondados (simulado com elipse para tamanhos pequenos)
    pad  = max(1, round(size * 0.02))
    rr   = max(2, round(size * 0.19))   # raio do arredondamento
    bg   = _hex_color(*BG_COLOR)

    # rounded-rect via Pillow
    draw.rounded_rectangle([pad, pad, size - pad - 1, size - pad - 1],
                            radius=rr, fill=bg)

    # Hexágono com padding
    r_hex = size * 0.39
    pts   = _hexagon_points(cx, cy, r_hex)
    draw.polygon(pts, fill=_hex_color(*fill))

    return img


def main() -> None:
    pairs = [
        ("icon",          ACTIVE_FILL),
        ("icon_inactive", INACTIVE_FILL),
    ]
    for basename, fill in pairs:
        for size in SIZES:
            img  = render_icon(size, fill)
            name = f"{basename}{size}.png"
            img.save(HERE / name)
            print(f"  {name}")
    print("icons gerados.")


if __name__ == "__main__":
    main()
