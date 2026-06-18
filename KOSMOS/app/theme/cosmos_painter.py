"""Gera QPixmap com estrelas desenhadas a lápis sobre fundo sépia."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPixmap


def _star_path(cx: float, cy: float, size: float, points: int) -> QPainterPath:
    path   = QPainterPath()
    outer  = size / 2
    inner  = outer * 0.42
    step   = math.pi / points
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = i * step - math.pi / 2
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
    path.closeSubpath()
    return path


def paint_cosmos(width: int, height: int, theme: str = "day", seed: int = 42) -> QPixmap:
    """
    Retorna QPixmap (width × height) com fundo sépia e estrelas a lápis.
    seed garante posicionamento reproduzível entre renders.
    """
    rng = random.Random(seed)

    bg_color   = QColor("#f0e8d5") if theme == "day" else QColor("#12161E")
    star_color = QColor("#5C4E3A") if theme == "day" else QColor("#C4B49A")

    pixmap = QPixmap(width, height)
    pixmap.fill(bg_color)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    cx, cy = width * 0.5, height * 0.5
    ex, ey = width * 0.28, height * 0.28  # zona central excluída

    n = rng.randint(45, 65)
    for _ in range(n):
        for _ in range(12):          # tenta posicionar fora do centro
            x = rng.uniform(8, width  - 8)
            y = rng.uniform(8, height - 8)
            if abs(x - cx) > ex or abs(y - cy) > ey:
                break

        size    = rng.uniform(4, 18)
        opacity = rng.uniform(0.15, 0.45)
        points  = rng.choice([4, 5, 6])

        c = QColor(star_color)
        c.setAlphaF(opacity)
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(_star_path(x, y, size, points))

    painter.end()
    return pixmap
