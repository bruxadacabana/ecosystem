"""cosmos_painter.py — Campo estelar e elementos cósmicos do KOSMOS.

Renderiza via QPainter: nebulosas, campo estelar, constelação, cometa.
Seed baseada na data — padrão consistente ao longo do dia.
"""

import math
import random
from datetime import date

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QPainter, QPen, QPolygonF,
)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def paint_cosmos(
    painter: QPainter,
    width: int,
    height: int,
    theme: str = "day",
    seed: int | None = None,
    density: str = "medium",   # "sparse" | "medium" | "rich"
    avoid_center: bool = False,
) -> None:
    """Pinta campo estelar cósmico no painter fornecido.

    Args:
        painter:       QPainter já ativo.
        width/height:  Dimensões da área.
        theme:         "day" ou "night".
        seed:          Seed do gerador. None = data atual.
        density:       "sparse" (headers, sidebar), "medium" (dashboard),
                       "rich" (splash).
        avoid_center:  Se True, evita ~30% central (para não cobrir texto).
    """
    if seed is None:
        seed = int(date.today().strftime("%Y%m%d"))
    rng = random.Random(seed)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    cfg = _theme_cfg(theme)

    n_nebulae, n_stars, do_const, n_comets = {
        "sparse": (1,  22,  False, 0),
        "medium": (2,  55,  True,  0),
        "rich":   (3,  100, True,  1),
        "cosmic": (6,  90,  True,  4),
    }.get(density, (2, 55, True, 0))

    # 1. Galáxias e nebulosas (elementos de fundo)
    for i in range(n_nebulae):
        # No modo cosmic: alterna galáxia/nebulosa — galáxias nos índices pares
        if density == "cosmic" and i % 2 == 0:
            _draw_galaxy(painter, width, height, cfg, rng, avoid_center)
        else:
            _draw_nebula(painter, width, height, cfg, rng, avoid_center)

    # 2. Campo de estrelas
    for _ in range(n_stars):
        x, y = _random_pos(rng, width, height, avoid_center)
        _draw_star(painter, x, y, cfg, rng)

    # 3. Constelação (pontos conectados por linhas pontilhadas)
    if do_const:
        _draw_constellation(painter, width, height, cfg, rng, avoid_center)

    # 4. Cometas
    for c in range(n_comets):
        _draw_comet(painter, width, height, cfg, rng, index=c)

    painter.restore()


# ---------------------------------------------------------------------------
# Configuração de cores por tema
# ---------------------------------------------------------------------------

def _theme_cfg(theme: str) -> dict:
    if theme == "night":
        return {
            "star":        QColor(232, 223, 200),   # pergaminho
            "star_bright": QColor(255, 248, 220),   # creme quente
            "nebula":      QColor(212, 168, 32),    # ouro de vela
            "const":       QColor(200, 185, 154),   # constelação
            "star_alpha":  (0.18, 0.55),            # (min, max)
            "nebula_alpha": 0.07,
        }
    else:
        return {
            "star":        QColor(92, 78, 58),      # sépia
            "star_bright": QColor(139, 107, 54),    # ouro sépia
            "nebula":      QColor(184, 134, 11),    # ouro dia
            "const":       QColor(139, 107, 54),    # constelação
            "star_alpha":  (0.22, 0.58),
            "nebula_alpha": 0.06,
        }


# ---------------------------------------------------------------------------
# Posicionamento
# ---------------------------------------------------------------------------

def _random_pos(
    rng: random.Random, width: int, height: int, avoid_center: bool
) -> tuple[float, float]:
    for _ in range(30):
        x = rng.uniform(6, width  - 6)
        y = rng.uniform(6, height - 6)
        if avoid_center:
            cx, cy = width / 2, height / 2
            if abs(x - cx) < width * 0.28 and abs(y - cy) < height * 0.28:
                continue
        return x, y
    return rng.uniform(6, width - 6), rng.uniform(6, height - 6)


# ---------------------------------------------------------------------------
# Nebulosa
# ---------------------------------------------------------------------------

def _draw_nebula(
    painter: QPainter, width: int, height: int,
    cfg: dict, rng: random.Random, avoid_center: bool,
) -> None:
    x, y = _random_pos(rng, width, height, avoid_center)
    rx = rng.uniform(50, min(width, height) * 0.45)
    ry = rx * rng.uniform(0.5, 1.0)

    layers = 5
    for i in range(layers):
        t = 1.0 - i / layers
        alpha = cfg["nebula_alpha"] * t * 0.7
        color = QColor(cfg["nebula"])
        color.setAlphaF(alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x, y), rx * t, ry * t)


# ---------------------------------------------------------------------------
# Estrela individual
# ---------------------------------------------------------------------------

def _draw_star(
    painter: QPainter, x: float, y: float,
    cfg: dict, rng: random.Random,
) -> None:
    a_min, a_max = cfg["star_alpha"]
    alpha = rng.uniform(a_min, a_max)
    roll  = rng.random()

    if roll < 0.60:
        # Ponto minúsculo (maioria das estrelas)
        r = rng.uniform(0.4, 1.6)
        color = QColor(cfg["star"])
        color.setAlphaF(alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x, y), r, r)

    elif roll < 0.82:
        # Cruz de 4 pontas
        size = rng.uniform(3, 9)
        color = QColor(cfg["star"])
        color.setAlphaF(alpha)
        pen = QPen(color)
        pen.setWidthF(0.8)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        j = size * 0.07
        for angle in (0, 90, 180, 270):
            rad = math.radians(angle)
            dx, dy = rng.uniform(-j, j), rng.uniform(-j, j)
            painter.drawLine(
                QPointF(x + dx, y + dy),
                QPointF(x + math.cos(rad) * size + dx,
                        y + math.sin(rad) * size + dy),
            )

    elif roll < 0.93:
        # Halo: núcleo brilhante + glow
        size = rng.uniform(2, 7)
        inner = QColor(cfg["star_bright"])
        inner.setAlphaF(min(1.0, alpha * 2.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(inner))
        painter.drawEllipse(QPointF(x, y), size * 0.25, size * 0.25)

        glow = QColor(cfg["star"])
        glow.setAlphaF(alpha * 0.3)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(x, y), size * 0.7, size * 0.7)

    else:
        # Estrela de 6 pontas (rara, maior)
        size = rng.uniform(5, 13)
        color = QColor(cfg["star_bright"])
        color.setAlphaF(alpha * 0.9)
        pen = QPen(color)
        pen.setWidthF(0.9)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        j = size * 0.06
        for angle in (0, 60, 120):
            rad = math.radians(angle)
            dx1, dy1 = rng.uniform(-j, j), rng.uniform(-j, j)
            dx2, dy2 = rng.uniform(-j, j), rng.uniform(-j, j)
            painter.drawLine(
                QPointF(x - math.cos(rad) * size + dx1,
                        y - math.sin(rad) * size + dy1),
                QPointF(x + math.cos(rad) * size + dx2,
                        y + math.sin(rad) * size + dy2),
            )


# ---------------------------------------------------------------------------
# Constelação
# ---------------------------------------------------------------------------

def _draw_constellation(
    painter: QPainter, width: int, height: int,
    cfg: dict, rng: random.Random, avoid_center: bool,
) -> None:
    n_pts = rng.randint(5, 8)
    pts: list[tuple[float, float]] = [
        _random_pos(rng, width, height, avoid_center)
        for _ in range(n_pts)
    ]

    # Linhas pontilhadas
    a_min, a_max = cfg["star_alpha"]
    line_alpha = a_min * 0.8
    color = QColor(cfg["const"])
    color.setAlphaF(line_alpha)
    pen = QPen(color)
    pen.setWidthF(0.7)
    pen.setStyle(Qt.PenStyle.DotLine)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    for i in range(len(pts) - 1):
        painter.drawLine(QPointF(*pts[i]), QPointF(*pts[i + 1]))

    # Pontos nos vértices
    painter.setPen(Qt.PenStyle.NoPen)
    for px, py in pts:
        dot = QColor(cfg["const"])
        dot.setAlphaF(rng.uniform(a_min * 1.2, a_max * 0.7))
        painter.setBrush(QBrush(dot))
        r = rng.uniform(1.0, 2.4)
        painter.drawEllipse(QPointF(px, py), r, r)


# ---------------------------------------------------------------------------
# Galáxia
# ---------------------------------------------------------------------------

def _draw_galaxy(
    painter: QPainter, width: int, height: int,
    cfg: dict, rng: random.Random, avoid_center: bool,
) -> None:
    """Galáxia: núcleo brilhante + disco achatado + braços leves."""
    x, y = _random_pos(rng, width, height, avoid_center)

    rx    = rng.uniform(55, min(width, height) * 0.38)
    ratio = rng.uniform(0.18, 0.40)   # disco muito achatado
    ry    = rx * ratio
    angle = rng.uniform(0, 180)

    # Braços: 3 elipses ligeiramente rotacionadas entre si
    arm_offsets = [-18, 0, 18]
    for offset in arm_offsets:
        rot = angle + offset + rng.uniform(-8, 8)
        ax  = rx * rng.uniform(0.85, 1.15)
        ay  = ry * rng.uniform(0.85, 1.15)
        alpha = cfg["nebula_alpha"] * rng.uniform(0.5, 1.0)
        color = QColor(cfg["nebula"])
        color.setAlphaF(alpha)
        painter.save()
        painter.translate(x, y)
        painter.rotate(rot)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(0, 0), ax, ay)
        painter.restore()

    # Halo difuso externo
    halo = QColor(cfg["nebula"])
    halo.setAlphaF(cfg["nebula_alpha"] * 0.30)
    painter.save()
    painter.translate(x, y)
    painter.rotate(angle)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(halo))
    painter.drawEllipse(QPointF(0, 0), rx * 1.35, ry * 1.35)
    painter.restore()

    # Núcleo brilhante compacto
    core_r = rx * 0.10
    core = QColor(cfg["star_bright"])
    core.setAlphaF(min(1.0, cfg["nebula_alpha"] * 3.5))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(core))
    painter.drawEllipse(QPointF(x, y), core_r, core_r)

    # Brilho intermediário
    mid = QColor(cfg["nebula"])
    mid.setAlphaF(cfg["nebula_alpha"] * 1.8)
    painter.setBrush(QBrush(mid))
    painter.drawEllipse(QPointF(x, y), core_r * 2.2, core_r * 2.2)


# ---------------------------------------------------------------------------
# Cometa
# ---------------------------------------------------------------------------

def _draw_comet(
    painter: QPainter, width: int, height: int,
    cfg: dict, rng: random.Random, index: int = 0,
) -> None:
    # Cada cometa usa uma sub-seed derivada do index para não se sobrepor
    sub_rng = random.Random(rng.randint(0, 2**31) + index * 7919)

    # Ponto de chegada (dentro da tela) — distribuídos por quadrante
    quad_x = [0.15, 0.55, 0.25, 0.65][index % 4]
    quad_y = [0.20, 0.55, 0.65, 0.30][index % 4]
    tip_x = sub_rng.uniform(width  * quad_x, width  * (quad_x + 0.30))
    tip_y = sub_rng.uniform(height * quad_y, height * (quad_y + 0.25))

    # Direção de origem — varia por index para cometas em ângulos diferentes
    base_angles = [230, 190, 260, 215]
    angle  = base_angles[index % 4] + sub_rng.uniform(-20, 20)
    length = sub_rng.uniform(min(width, height) * 0.18, min(width, height) * 0.42)
    rad    = math.radians(angle)
    tail_x = tip_x + math.cos(rad) * length
    tail_y = tip_y + math.sin(rad) * length

    # Cauda principal
    a_min, a_max = cfg["star_alpha"]
    segs = 14
    for i in range(segs):
        t  = i / segs
        t1 = (i + 1) / segs
        ax = tip_x + (tail_x - tip_x) * t
        ay = tip_y + (tail_y - tip_y) * t
        bx = tip_x + (tail_x - tip_x) * t1
        by = tip_y + (tail_y - tip_y) * t1

        alpha = a_max * (1.0 - t) * 0.85
        color = QColor(cfg["star_bright"])
        color.setAlphaF(alpha)
        pen = QPen(color)
        pen.setWidthF(2.0 * (1.0 - t * 0.75))
        painter.setPen(pen)
        painter.drawLine(QPointF(ax, ay), QPointF(bx, by))

    # Cauda secundária (mais larga e difusa)
    for i in range(segs):
        t  = i / segs
        t1 = (i + 1) / segs
        ax = tip_x + (tail_x - tip_x) * t
        ay = tip_y + (tail_y - tip_y) * t
        bx = tip_x + (tail_x - tip_x) * t1
        by = tip_y + (tail_y - tip_y) * t1

        alpha = a_max * (1.0 - t) * 0.25
        color = QColor(cfg["nebula"])
        color.setAlphaF(alpha)
        pen = QPen(color)
        pen.setWidthF(4.5 * (1.0 - t * 0.6))
        painter.setPen(pen)
        painter.drawLine(QPointF(ax, ay), QPointF(bx, by))

    # Núcleo brilhante na ponta
    core = QColor(cfg["star_bright"])
    core.setAlphaF(min(1.0, a_max * 1.6))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(core))
    painter.drawEllipse(QPointF(tip_x, tip_y), 3.0, 3.0)

    # Halo do núcleo
    halo = QColor(cfg["star_bright"])
    halo.setAlphaF(a_max * 0.3)
    painter.setBrush(QBrush(halo))
    painter.drawEllipse(QPointF(tip_x, tip_y), 6.0, 6.0)
