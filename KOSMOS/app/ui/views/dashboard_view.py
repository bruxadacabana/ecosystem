"""
dashboard_view.py — Tela inicial do KOSMOS (design antigo) sobre os dados v3.

Campo estelar de fundo + título "KOSMOS", uma linha de resumo (totais) e painéis
de estatística (Top Fontes, Top Tags) com barrinhas. Os dados vêm das funções puras
de `app/core/stats.py` (top_feeds, top_tags, totals). Sem K-means/embeddings — é um
painel informativo leve (a análise rica de estatística vive na aba Análise → Stats).
"""
from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.stats import top_feeds, top_tags, totals
from app.theme.cosmos_painter import paint_cosmos

log = logging.getLogger("kosmos.dashboard")


def _font(family: str, fallback: str, size: int, *, italic: bool = False) -> QFont:
    f = QFont(family)
    if not f.exactMatch():
        f = QFont(fallback)
    f.setPointSize(size)
    f.setItalic(italic)
    return f


class _StatsPanel(QWidget):
    """Painel com título e lista de pares (nome, contagem) com barrinhas."""

    def __init__(self, title: str, empty_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardPanel")
        self.setFixedWidth(248)
        self._empty_text = empty_text

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(0)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("dashboardPanelTitle")
        title_lbl.setFont(_font("Special Elite", "Courier New", 10))
        root.addWidget(title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("dashboardPanelSep")
        root.addWidget(sep)
        root.addSpacing(6)

        self._content = QVBoxLayout()
        self._content.setSpacing(4)
        root.addLayout(self._content)
        root.addStretch()
        self._show_empty()

    def set_data(self, items: list[tuple[str, int]]) -> None:
        self._clear()
        if not items:
            self._show_empty()
            return
        max_count = max(cnt for _, cnt in items) or 1
        for name, cnt in items:
            row = QHBoxLayout()
            row.setSpacing(8)
            name_lbl = QLabel(name[:28] + ("…" if len(name) > 28 else ""))
            name_lbl.setObjectName("dashboardStatName")
            name_lbl.setFont(_font("Courier Prime", "Courier New", 10))
            row.addWidget(name_lbl, 1)
            count_lbl = QLabel(str(cnt))
            count_lbl.setObjectName("dashboardStatCount")
            count_lbl.setFont(_font("Courier Prime", "Courier New", 10))
            count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            count_lbl.setFixedWidth(36)
            row.addWidget(count_lbl)

            bar = QFrame()
            bar.setObjectName("dashboardStatBar")
            bar.setFixedHeight(2)
            bar.setFixedWidth(max(4, int(80 * cnt / max_count)))

            row_widget = QWidget()
            rl = QVBoxLayout(row_widget)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(2)
            rl.addLayout(row)
            rl.addWidget(bar)
            self._content.addWidget(row_widget)

    def _show_empty(self) -> None:
        lbl = QLabel(self._empty_text)
        lbl.setObjectName("dashboardStatEmpty")
        lbl.setFont(_font("Courier Prime", "Courier New", 10))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setContentsMargins(0, 8, 0, 0)
        self._content.addWidget(lbl)

    def _clear(self) -> None:
        while self._content.count():
            item = self._content.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)   # remove já da árvore (deleteLater é assíncrono)
                w.deleteLater()


class DashboardView(QWidget):
    """Tela inicial do KOSMOS — campo estelar + resumo + painéis de stats (dados v3)."""

    def __init__(self, theme: str = "day", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("dashboardView")
        self._build_ui()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            pix = paint_cosmos(self.width(), self.height(), theme=self._theme)
            painter.drawPixmap(0, 0, pix)
        finally:
            painter.end()
        super().paintEvent(event)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        container = QWidget()
        container.setObjectName("dashboardContainer")
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.setContentsMargins(60, 60, 60, 40)
        layout.setSpacing(0)

        title = QLabel("KOSMOS")
        title.setObjectName("dashboardTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(_font("IM Fell English", "Georgia", 36, italic=True))
        layout.addWidget(title)
        layout.addSpacing(6)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setObjectName("dashboardSummary")
        self._summary_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_lbl.setFont(_font("Courier Prime", "Courier New", 11))
        layout.addWidget(self._summary_lbl)
        layout.addSpacing(28)

        panels_row = QHBoxLayout()
        panels_row.setSpacing(24)
        panels_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fontes_panel = _StatsPanel("TOP FONTES", "nenhuma leitura ainda")
        self._tags_panel = _StatsPanel("TOP TAGS", "nenhuma tag ainda")
        panels_row.addWidget(self._fontes_panel)
        panels_row.addWidget(self._tags_panel)
        layout.addLayout(panels_row)
        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def load(self, conn: sqlite3.Connection | None = None) -> None:
        """Recarrega o resumo + painéis a partir das funções de stats v3."""
        t = totals(conn)
        self._summary_lbl.setText(
            f"{t['total']} artigos  ·  {t['read']} lidos  ·  "
            f"{t['unread']} não-lidos  ·  {t['feeds']} fontes"
        )
        self._fontes_panel.set_data(top_feeds(limit=6, conn=conn))
        self._tags_panel.set_data(top_tags(limit=6, conn=conn))
        log.debug("Dashboard recarregado (%d artigos, %d fontes).", t["total"], t["feeds"])
