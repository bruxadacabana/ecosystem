"""
stats_view.py — dashboard de estudo (Fase 8) com gráficos QtCharts.

Mostra: artigos lidos por dia, feeds mais consumidos, sentimento ao longo do tempo,
viés político médio (indicador de bolha editorial) e cobertura por entidade
rastreada. Os dados vêm de `core/stats.py` (funções puras); aqui é só renderização.
Botão "Atualizar" recomputa tudo.
"""
from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.stats import (
    articles_read_per_day,
    bias_balance,
    coverage_by_entity,
    sentiment_over_time,
    top_feeds,
)

log = logging.getLogger("kosmos.stats_view")

_FG = "#E8D9BE"
_MUTED = "#7A6E58"
_ACCENT = "#A08860"
_SENT_COLORS = {"positivo": "#6E8B5A", "neutro": "#7A6E58", "negativo": "#B5793F"}


def _short(text: str, n: int = 16) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1] + "…"


def _short_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m")
    except Exception:
        return iso[5:] if len(iso) >= 10 else iso


def _styled_chart(title: str) -> QChart:
    chart = QChart()
    chart.setTitle(title)
    chart.setTitleBrush(QColor(_FG))
    chart.setBackgroundVisible(False)
    chart.setMargins(QMargins(4, 4, 4, 4))
    chart.legend().setLabelColor(QColor(_MUTED))
    return chart


def _chart_view(chart: QChart) -> QChartView:
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setMinimumHeight(220)
    return view


def bar_chart_view(title: str, pairs: list[tuple[str, int]], color: str = _ACCENT) -> QChartView:
    """Gráfico de barras a partir de (categoria, valor)."""
    chart = _styled_chart(title)
    bar_set = QBarSet("")
    cats: list[str] = []
    for label, value in pairs:
        bar_set.append(float(value))
        cats.append(str(label))
    bar_set.setColor(QColor(color))
    series = QBarSeries()
    series.append(bar_set)
    chart.addSeries(series)
    chart.legend().hide()

    axis_x = QBarCategoryAxis()
    axis_x.append(cats or [""])
    axis_x.setLabelsColor(QColor(_MUTED))
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(axis_x)

    axis_y = QValueAxis()
    axis_y.setLabelsColor(QColor(_MUTED))
    axis_y.setRange(0, max((v for _, v in pairs), default=1) or 1)
    axis_y.setLabelFormat("%d")
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(axis_y)
    return _chart_view(chart)


def sentiment_line_view(title: str, series_data: list[dict]) -> QChartView:
    """Gráfico de linhas: positivo/neutro/negativo por dia (x = índice do dia)."""
    chart = _styled_chart(title)
    n = len(series_data)
    max_y = 1
    for sentiment in ("positivo", "neutro", "negativo"):
        line = QLineSeries()
        line.setName(sentiment)
        line.setColor(QColor(_SENT_COLORS[sentiment]))
        for i, day in enumerate(series_data):
            v = day.get(sentiment, 0)
            line.append(i, v)
            max_y = max(max_y, v)
        chart.addSeries(line)

    axis_x = QValueAxis()
    axis_x.setRange(0, max(1, n - 1))
    axis_x.setLabelFormat("%d")
    axis_x.setTitleText(f"últimos {n} dias (recente →)")
    axis_x.setTitleBrush(QColor(_MUTED))
    axis_x.setLabelsColor(QColor(_MUTED))
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    axis_y = QValueAxis()
    axis_y.setRange(0, max_y)
    axis_y.setLabelFormat("%d")
    axis_y.setLabelsColor(QColor(_MUTED))
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    for s in chart.series():
        s.attachAxis(axis_x)
        s.attachAxis(axis_y)
    return _chart_view(chart)


class StatsView(QWidget):
    """Dashboard com os gráficos de estudo do KOSMOS."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        log.debug("StatsView inicializada.")

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        self._refresh_btn = QPushButton("Atualizar")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(lambda: self.load())
        outer.addWidget(self._refresh_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._vbox = QVBoxLayout(self._container)
        scroll.setWidget(self._container)
        outer.addWidget(scroll)

    def _clear(self) -> None:
        while self._vbox.count():
            item = self._vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def load(self, conn=None) -> None:
        """Recomputa as métricas e reconstrói os gráficos."""
        self._clear()
        self._vbox.addWidget(bar_chart_view(
            "Artigos lidos por dia (14 dias)",
            [(_short_date(d), n) for d, n in articles_read_per_day(14, conn)],
        ))
        self._vbox.addWidget(bar_chart_view(
            "Feeds mais consumidos",
            [(_short(f), n) for f, n in top_feeds(8, conn)],
        ))
        self._vbox.addWidget(sentiment_line_view(
            "Sentimento ao longo do tempo", sentiment_over_time(14, conn),
        ))

        bias = bias_balance(conn)
        self._bias_label = QLabel(
            f"Viés político médio (bolha editorial): {bias['label']}  ·  {bias['n']} artigo(s) analisado(s)"
        )
        self._bias_label.setObjectName("stats_bias_label")
        self._vbox.addWidget(self._bias_label)
        self._vbox.addWidget(bar_chart_view(
            "Distribuição por espectro político",
            sorted(bias["distribution"].items()),
        ))
        self._vbox.addWidget(bar_chart_view(
            "Cobertura por entidade rastreada",
            [(_short(name), c) for name, c in coverage_by_entity(10, conn)],
        ))
        self._vbox.addStretch(1)
        log.info("StatsView: dashboard recarregado.")

    def chart_count(self) -> int:
        """Nº de gráficos atualmente montados (para testes)."""
        return sum(1 for i in range(self._vbox.count())
                   if isinstance(self._vbox.itemAt(i).widget(), QChartView))
