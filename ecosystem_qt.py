"""
ecosystem_qt.py — Biblioteca partilhada de componentes PyQt6
Ecossistema local-first · Design Bible v2.0

Importar em qualquer app Python do ecossistema:
    from ecosystem_qt import (
        PAPER, INK, ACCENT,         # paleta
        load_ecosystem_fonts,        # fontes
        build_qss,                   # folha de estilos base
        AlchemyLoaderQt,             # spinner alquímico
        WaxSealQt,                   # selo de cera
        CandleGlowQt,                # brilho de vela
        VignetteWidget,              # vinheta nas bordas
    )
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QRectF, QPointF, pyqtProperty,
)
from PyQt6.QtGui import (
    QColor, QFont, QFontDatabase, QPainter, QPainterPath,
    QRadialGradient, QLinearGradient, QPen, QBrush,
)
from PyQt6.QtWidgets import QWidget, QLabel, QSizePolicy


# ── Paleta (Design Bible v2.0) ────────────────────────────────────────────────
PAPER        = "#F5F0E8"
PAPER_DARK   = "#EDE7D9"
PAPER_DARKER = "#E0D8C8"
INK          = "#2C2416"
INK_LIGHT    = "#5C4E3A"
INK_FAINT    = "#6B5C49"
INK_GHOST    = "#746455"
ACCENT       = "#b8860b"
RIBBON       = "#8B3A2A"
RIBBON_LIGHT = "#B85C4A"
ACCENT_GREEN = "#4A6741"
STAMP        = "#7A5C2E"
RULE         = "#C4B9A8"

# Modo noturno — Atlas Astronômico à Meia-Noite
NIGHT_PAPER        = "#12161E"
NIGHT_PAPER_DARK   = "#181D28"
NIGHT_PAPER_DARKER = "#1E2433"
NIGHT_PAPER_DARKEST= "#252B3A"
NIGHT_INK_GHOST    = "#7C828E"
NIGHT_INK_FAINT    = "#9A9080"
NIGHT_RULE         = "#2A3148"


# ── Fontes do ecossistema ─────────────────────────────────────────────────────
def load_ecosystem_fonts() -> tuple[str, str]:
    """
    Tenta registrar IM Fell English e Special Elite via QFontDatabase.
    Busca nos diretórios de fontes padrão do sistema.
    Retorna (family_display, family_mono) — com fallback se não encontradas.
    """
    search_dirs = [
        Path.home() / ".local/share/fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
    ]
    targets: dict[str, Optional[str]] = {
        "IMFellEnglish-Regular.ttf": None,
        "IMFellEnglish-Italic.ttf":  None,
        "SpecialElite-Regular.ttf":  None,
        "CourierPrime-Regular.ttf":  None,
    }
    for d in search_dirs:
        if not d.exists():
            continue
        for ttf in d.rglob("*.ttf"):
            if ttf.name in targets and targets[ttf.name] is None:
                fid = QFontDatabase.addApplicationFont(str(ttf))
                if fid >= 0:
                    families = QFontDatabase.applicationFontFamilies(fid)
                    if families:
                        targets[ttf.name] = families[0]

    display = targets.get("IMFellEnglish-Regular.ttf") or "Georgia"
    mono    = targets.get("SpecialElite-Regular.ttf")  or "Courier"
    return display, mono


# ── QSS base ─────────────────────────────────────────────────────────────────
def build_qss(display: str, mono: str) -> str:
    """Folha de estilos base do ecossistema. Pode ser complementada por cada app."""
    return f"""
    QMainWindow, QWidget {{
        background: {PAPER};
        color: {INK};
        font-family: '{mono}';
        font-size: 12px;
    }}
    QTabWidget::pane {{
        border: 1px solid {RULE};
        background: {PAPER_DARK};
        border-radius: 2px;
        top: -1px;
    }}
    QTabBar::tab {{
        background: {PAPER_DARKER};
        color: {INK_FAINT};
        font-family: '{mono}';
        font-size: 10px;
        letter-spacing: 2px;
        padding: 6px 20px;
        border: 1px solid {RULE};
        border-bottom: none;
        border-radius: 2px 2px 0 0;
        min-width: 120px;
    }}
    QTabBar::tab:selected {{
        background: {PAPER_DARK};
        color: {INK};
        border-bottom: 1px solid {PAPER_DARK};
    }}
    QTabBar::tab:hover:!selected {{
        background: {PAPER_DARK};
        color: {INK_LIGHT};
    }}
    QLineEdit {{
        background: {PAPER_DARK};
        color: {INK};
        border: 1px solid {RULE};
        border-radius: 2px;
        padding: 7px 11px;
        font-family: '{display}';
        font-style: italic;
        font-size: 13px;
        selection-background-color: rgba(184,134,11,0.25);
    }}
    QLineEdit:focus {{
        border-color: {ACCENT};
        background: {PAPER};
    }}
    QPushButton {{
        background: {PAPER_DARK};
        color: {INK_LIGHT};
        border: 1px solid {RULE};
        border-radius: 2px;
        padding: 5px 14px;
        font-family: '{mono}';
        font-size: 11px;
        letter-spacing: 1px;
    }}
    QPushButton:hover {{
        background: {PAPER_DARKER};
        border-color: {STAMP};
        color: {INK};
    }}
    QPushButton:pressed {{
        background: {PAPER_DARKER};
        padding-top: 6px;
        padding-left: 15px;
    }}
    QPushButton:disabled {{
        color: {INK_GHOST};
        border-color: {RULE};
        background: {PAPER_DARK};
    }}
    QPushButton#primary {{
        background: {INK};
        color: {PAPER};
        border-color: {INK};
        font-size: 12px;
        padding: 7px 20px;
    }}
    QPushButton#primary:hover {{
        background: {INK_LIGHT};
        color: {PAPER};
    }}
    QPushButton#primary:disabled {{
        background: {PAPER_DARKER};
        color: {INK_GHOST};
        border-color: {RULE};
    }}
    QPushButton#danger {{
        background: {RIBBON};
        color: {PAPER};
        border-color: {RIBBON};
    }}
    QPushButton#danger:hover {{
        background: {RIBBON_LIGHT};
        color: {PAPER};
    }}
    QPushButton#danger:disabled {{
        background: {PAPER_DARKER};
        color: {INK_GHOST};
        border-color: {RULE};
    }}
    QComboBox {{
        background: {PAPER_DARK};
        color: {INK};
        border: 1px solid {RULE};
        border-radius: 2px;
        padding: 5px 10px;
        font-family: '{mono}';
        font-size: 11px;
    }}
    QComboBox:focus {{ border-color: {ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox::down-arrow {{ width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{
        background: {PAPER_DARK};
        color: {INK};
        border: 1px solid {RULE};
        selection-background-color: {PAPER_DARKER};
        selection-color: {INK};
        outline: none;
        padding: 2px;
    }}
    QTextEdit {{
        background: {PAPER_DARK};
        color: {INK_LIGHT};
        border: 1px solid {RULE};
        border-radius: 2px;
        padding: 8px;
        font-family: 'Courier Prime', 'Courier New', monospace;
        font-size: 11px;
        selection-background-color: rgba(184,134,11,0.25);
    }}
    QListWidget {{
        background: {PAPER_DARK};
        color: {INK};
        border: 1px solid {RULE};
        border-radius: 2px;
        font-family: '{mono}';
        font-size: 11px;
        outline: none;
    }}
    QListWidget::item {{ padding: 6px 10px; }}
    QListWidget::item:selected {{
        background: rgba(184,134,11,0.15);
        color: {INK};
    }}
    QListWidget::item:hover {{ background: {PAPER_DARKER}; }}
    QProgressBar {{
        background: {PAPER_DARKER};
        border: 1px solid {RULE};
        border-radius: 2px;
        max-height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {ACCENT};
        border-radius: 1px;
    }}
    QScrollBar:vertical {{
        background: {PAPER_DARK};
        width: 6px;
        border-radius: 2px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {RULE};
        border-radius: 2px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {STAMP}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: {PAPER_DARK};
        height: 6px;
        border-radius: 2px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {RULE};
        border-radius: 2px;
        min-width: 20px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {STAMP}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QFrame#rule {{ background: {RULE}; max-height: 1px; border: none; }}
    QLabel#section {{
        color: {INK_FAINT};
        font-family: '{mono}';
        font-size: 9px;
        letter-spacing: 3px;
    }}
    QLabel#title {{
        color: {INK};
        font-family: '{display}';
        font-size: 32px;
        font-style: italic;
    }}
    QLabel#subtitle {{
        color: {INK_FAINT};
        font-family: '{mono}';
        font-size: 9px;
        letter-spacing: 4px;
    }}
    QLabel#meta {{
        color: {INK_FAINT};
        font-family: '{mono}';
        font-size: 10px;
    }}
    """


# ── AlchemyLoaderQt ───────────────────────────────────────────────────────────
ALCHEMY_SYMBOLS = ("☿", "♄", "☉", "⊕", "☾", "✦")

class AlchemyLoaderQt(QLabel):
    """
    Spinner alquímico — rota um símbolo com opacidade pulsante.
    Equivalente Qt do CSS .alchemy-loader.

    Uso:
        loader = AlchemyLoaderQt(symbol="☿", size="md")
        loader.start()
        # …
        loader.stop()
    """

    _SIZES = {"sm": 18, "md": 28, "lg": 42}

    def __init__(
        self,
        symbol: str = "☿",
        size: str = "md",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(symbol, parent)
        px = self._SIZES.get(size, 28)
        font = QFont()
        font.setPointSize(px)
        self.setFont(font)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(px * 2, px * 2)

        self._angle = 0.0
        self._opacity = 0.6

        self._timer = QTimer(self)
        self._timer.setInterval(40)          # ~25 fps
        self._timer.timeout.connect(self._tick)

    # pyqtProperty so QPropertyAnimation can drive it if needed
    @pyqtProperty(float)
    def opacity(self) -> float:  # type: ignore[override]
        return self._opacity

    @opacity.setter  # type: ignore[attr-defined]
    def opacity(self, v: float) -> None:
        self._opacity = v
        self.update()

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        # opacity: 0.6 → 1.0 → 0.6 following angle
        rad = math.radians(self._angle)
        self._opacity = 0.6 + 0.4 * (math.sin(rad) * 0.5 + 0.5)
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        cx, cy = self.width() / 2, self.height() / 2
        painter.translate(cx, cy)
        painter.rotate(self._angle)
        painter.translate(-cx, -cy)
        super().paintEvent(_event)
        painter.end()

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._opacity = 1.0
        self.update()


# ── WaxSealQt ─────────────────────────────────────────────────────────────────
class WaxSealQt(QWidget):
    """
    Selo de cera — aparece com animação de rotação/fade, auto-dispensável.
    Equivalente Qt do CSS .wax-seal.

    Uso:
        seal = WaxSealQt(symbol="✓", variant="gold", parent=container)
        seal.show_seal(dismiss_after=2000)   # ms; 0 = não dispensar
    """

    def __init__(
        self,
        symbol: str = "✦",
        variant: str = "red",   # "red" | "gold"
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.symbol = symbol
        self._color = QColor(RIBBON) if variant == "red" else QColor(ACCENT)
        self._alpha = 0.0
        self._angle = -12.0
        self._scale = 1.3

        size = 64
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)    # ~60 fps
        self._anim_timer.timeout.connect(self._animate_in)
        self._progress = 0.0               # 0.0 → 1.0

    def show_seal(self, dismiss_after: int = 2000) -> None:
        self._progress = 0.0
        self._alpha = 0.0
        self._scale = 1.3
        self.show()
        self._anim_timer.start()
        if dismiss_after > 0:
            QTimer.singleShot(dismiss_after, self._dismiss)

    def _animate_in(self) -> None:
        self._progress = min(1.0, self._progress + 0.05)
        t = self._ease_out(self._progress)
        self._alpha = t * 0.85
        self._scale = 1.3 - 0.3 * t
        self.update()
        if self._progress >= 1.0:
            self._anim_timer.stop()

    @staticmethod
    def _ease_out(t: float) -> float:
        return 1.0 - (1.0 - t) ** 3

    def _dismiss(self) -> None:
        self.hide()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._alpha)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        painter.translate(cx, cy)
        painter.rotate(self._angle)
        painter.scale(self._scale, self._scale)

        # Círculo do selo
        r = self.width() / 2.0 - 4
        self._color.setAlphaF(1.0)
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), r, r)

        # Borda dourada
        border_color = QColor(ACCENT)
        border_color.setAlphaF(0.6)
        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), r - 1, r - 1)

        # Símbolo
        painter.setPen(QPen(QColor(PAPER)))
        font = QFont()
        font.setPointSize(20)
        painter.setFont(font)
        fm = painter.fontMetrics()
        rect = fm.boundingRect(self.symbol)
        painter.drawText(
            QPointF(-rect.width() / 2.0, rect.height() / 4.0),
            self.symbol
        )
        painter.end()


# ── CandleGlowQt ──────────────────────────────────────────────────────────────
class CandleGlowQt(QWidget):
    """
    Reflexo suave de vela no canto inferior direito.
    Widget transparente sobreposto ao parent — liga-se via resizeEvent do parent.

    Uso:
        glow = CandleGlowQt(parent=main_window)
        glow.resize(main_window.size())
        glow.raise_()
        glow.show()
        # No resizeEvent do parent: glow.resize(event.size())
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self._opacity = 0.0
        self._rising = True

        self._timer = QTimer(self)
        self._timer.setInterval(60)         # lento e suave
        self._timer.timeout.connect(self._flicker)
        self._timer.start()

    def _flicker(self) -> None:
        step = 0.015
        if self._rising:
            self._opacity = min(1.0, self._opacity + step)
            if self._opacity >= 1.0:
                self._rising = False
        else:
            self._opacity = max(0.0, self._opacity - step)
            if self._opacity <= 0.0:
                self._rising = True
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        if self._opacity <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        # Gradiente radial do canto inferior direito
        grad = QRadialGradient(w, h, min(w, h) * 0.55)
        warm = QColor(255, 200, 80)
        warm.setAlphaF(0.07 * self._opacity)
        grad.setColorAt(0.0, warm)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.fillRect(self.rect(), QBrush(grad))
        painter.end()


# ── VignetteWidget ────────────────────────────────────────────────────────────
class VignetteWidget(QWidget):
    """
    Vinheta sépia nas bordas da janela — escurece as bordas como papel envelhecido.
    Uso idêntico ao CandleGlowQt.

    Uso:
        vignette = VignetteWidget(parent=main_window)
        vignette.resize(main_window.size())
        vignette.raise_()
        vignette.show()
    """

    def __init__(self, strength: float = 0.18, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.strength = strength
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = math.sqrt(cx**2 + cy**2)

        grad = QRadialGradient(cx, cy, radius)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        edge = QColor(44, 36, 22)               # #2C2416 — ink
        edge.setAlphaF(self.strength)
        grad.setColorAt(0.65, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, edge)

        painter.fillRect(self.rect(), QBrush(grad))
        painter.end()


# ── CosmosLayerQt ─────────────────────────────────────────────────────────────
class CosmosLayerQt(QWidget):
    """
    Camada decorativa de pontos (estrelas) e lua — equivalente do CosmosLayer React.
    Overlay estático ou com animação lenta de paralaxe via mouse tracking.

    Uso:
        cosmos = CosmosLayerQt(n_stars=60, parent=main_window)
        cosmos.resize(main_window.size())
        cosmos.raise_()
        cosmos.show()
    """

    def __init__(
        self,
        n_stars: int = 60,
        dark: bool = True,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.dark = dark
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        import random
        rng = random.Random(42)           # seed fixo — mesmas estrelas sempre
        self._stars = [
            (rng.random(), rng.random(), rng.uniform(0.3, 1.0))
            for _ in range(n_stars)
        ]

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())

        # Estrelas
        star_color = QColor(PAPER) if self.dark else QColor(INK)
        for sx, sy, op in self._stars:
            star_color.setAlphaF(op * 0.4)
            painter.setPen(QPen(star_color, 1.2))
            painter.drawPoint(QPointF(sx * w, sy * h))

        # Lua — canto superior direito
        moon_x = w * 0.85
        moon_y = h * 0.12
        r = 22.0
        moon_col = QColor(PAPER_DARK)
        moon_col.setAlphaF(0.25)
        painter.setBrush(QBrush(moon_col))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(moon_x, moon_y), r, r)

        # Máscara da lua (fase crescente)
        mask_col = QColor(NIGHT_PAPER if self.dark else PAPER)
        mask_col.setAlphaF(1.0)
        painter.setBrush(QBrush(mask_col))
        painter.drawEllipse(QPointF(moon_x + r * 0.35, moon_y), r * 0.85, r * 0.85)

        painter.end()
