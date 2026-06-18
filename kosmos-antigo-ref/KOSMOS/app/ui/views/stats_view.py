"""View de estatísticas de leitura com gráficos matplotlib."""

from __future__ import annotations

import calendar
import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from app.theme.theme_manager import ThemeManager

log = logging.getLogger("kosmos.ui.stats")

# Paletas sépia por tema
_PALETTE = {
    "day": {
        "bg":       "#FAF3E8",
        "fg":       "#2C2416",
        "muted":    "#8B7355",
        "bar":      "#8B7355",
        "accent":   "#C8963C",
        "line":     "#C8963C",
        "bar2":     "#B09070",
        "grid":     "#E0D8CC",
        "pos_fill": "#A8C8A8",
        "neg_fill": "#C8A8A8",
        "pos_line": "#5A8A5A",
        "neg_line": "#8A3A2A",
    },
    "night": {
        "bg":       "#1E1A14",
        "fg":       "#E8DFC8",
        "muted":    "#7A6E5A",
        "bar":      "#7A6E5A",
        "accent":   "#D4A844",
        "line":     "#D4A844",
        "bar2":     "#5A5040",
        "grid":     "#2E2820",
        "pos_fill": "#2A4A2A",
        "neg_fill": "#4A2A2A",
        "pos_line": "#6AAA6A",
        "neg_line": "#C07070",
    },
}


class _StatsLoadWorker(QThread):
    """Carrega todos os dados de estatísticas em background (DB + k-means)."""

    finished = pyqtSignal(object)   # dict com todos os dados
    error    = pyqtSignal(str)

    def __init__(self, days: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._days = days

    def run(self) -> None:
        try:
            from app.core.stats import (
                get_article_clusters, get_daily_stats, get_feed_stats,
                get_monthly_stats, get_platform_stats, get_sentiment_trend,
                get_top_ai_tags_read, get_top_entities, get_total_stats,
            )
            days = self._days
            self.finished.emit({
                "days":      days,
                "totals":    get_total_stats(),
                "daily":     get_daily_stats(days=days),
                "feeds":     get_feed_stats(limit=10),
                "monthly":   get_monthly_stats(months=12),
                "platform":  get_platform_stats(),
                "sentiment": get_sentiment_trend(days=days),
                "entities":  get_top_entities(days=days),
                "clusters":  get_article_clusters(days=max(days, 90)),
                "ai_tags":   get_top_ai_tags_read(days=days, limit=20),
            })
        except Exception as exc:
            self.error.emit(str(exc))


class StatsView(QWidget):
    """View de estatísticas com resumo e gráficos matplotlib.

    Sinais:
        back_requested() — voltar ao dashboard.
    """

    back_requested = pyqtSignal()

    def __init__(self, theme_manager: "ThemeManager", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme  = theme_manager
        self._worker: _StatsLoadWorker | None = None
        self.setObjectName("feedListView")
        self._build_ui()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        root.addWidget(sep)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._body = QWidget()
        self._body.setObjectName("cardsContainer")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(32, 24, 32, 32)
        self._body_layout.setSpacing(24)

        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("feedListHeader")
        header.setFixedHeight(52)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        back_btn = QPushButton("←  Dashboard")
        back_btn.setObjectName("backButton")
        back_btn.setFlat(True)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setFont(self._mono(11))
        back_btn.clicked.connect(self.back_requested.emit)
        layout.addWidget(back_btn)

        title = QLabel("Estatísticas")
        title.setObjectName("feedListTitle")
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(16)
        title.setFont(f)
        layout.addWidget(title, 1)

        layout.addWidget(QLabel("Período:", font=self._mono(11)))

        self._period_combo = QComboBox()
        self._period_combo.setFont(self._mono(11))
        self._period_combo.setFixedWidth(130)
        for label, days in [("7 dias", 7), ("14 dias", 14), ("30 dias", 30), ("90 dias", 90)]:
            self._period_combo.addItem(label, days)
        self._period_combo.setCurrentIndex(2)   # 30 dias padrão
        self._period_combo.currentIndexChanged.connect(self._reload_charts)
        layout.addWidget(self._period_combo)

        return header

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load(self) -> None:
        self._reload_charts()

    # ------------------------------------------------------------------
    # Carregamento assíncrono
    # ------------------------------------------------------------------

    def _reload_charts(self) -> None:
        if self._worker and self._worker.isRunning():
            return

        days = self._period_combo.currentData()
        self._period_combo.setEnabled(False)
        self._clear_body()

        loading = QLabel("Carregando estatísticas…")
        loading.setObjectName("cardMeta")
        loading.setFont(self._mono(11))
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body_layout.addWidget(loading)
        self._body_layout.addStretch()

        self._worker = _StatsLoadWorker(days, self)
        self._worker.finished.connect(self._on_data_loaded)
        self._worker.error.connect(self._on_load_error)
        self._worker.start()

    def _on_data_loaded(self, payload: dict[str, Any]) -> None:
        self._period_combo.setEnabled(True)
        self._clear_body()

        days      = payload["days"]
        totals    = payload["totals"]
        daily     = payload["daily"]
        feeds     = payload["feeds"]
        monthly   = payload["monthly"]
        platform  = payload["platform"]
        sentiment = payload["sentiment"]
        entities  = payload["entities"]
        clusters  = payload["clusters"]
        ai_tags   = payload.get("ai_tags", [])

        pal = _PALETTE.get(self._theme.current, _PALETTE["day"])

        self._body_layout.addWidget(self._build_summary_cards(totals, pal))
        self._body_layout.addWidget(self._build_daily_chart(daily, pal, days))
        self._body_layout.addWidget(self._build_sentiment_chart(sentiment, pal, days))

        if ai_tags:
            self._body_layout.addWidget(self._build_ai_tags_chart(ai_tags, pal, days))

        if any(entities.get(t) for t in ("people", "orgs", "places")):
            self._body_layout.addWidget(self._build_entities_section(entities, pal))

        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(self._build_feed_chart(feeds, pal), 1)
        row.addWidget(self._build_monthly_chart(monthly, pal), 1)
        row_w = QWidget()
        row_w.setLayout(row)
        self._body_layout.addWidget(row_w)

        if platform:
            self._body_layout.addWidget(self._build_platform_chart(platform, pal))

        if clusters:
            self._body_layout.addWidget(self._build_clusters_section(clusters, pal))

        self._body_layout.addStretch()

    def _on_load_error(self, msg: str) -> None:
        self._period_combo.setEnabled(True)
        self._clear_body()
        lbl = QLabel(f"Erro ao carregar estatísticas:\n{msg}")
        lbl.setObjectName("cardMeta")
        lbl.setFont(self._mono(11))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        self._body_layout.addWidget(lbl)
        self._body_layout.addStretch()
        log.error("Erro ao carregar stats: %s", msg)

    def _clear_body(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ------------------------------------------------------------------
    # Painel de resumo
    # ------------------------------------------------------------------

    def _build_summary_cards(self, totals, pal: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        cards = [
            ("Artigos",       str(totals.total_articles),    "no acervo"),
            ("Lidos",         str(totals.total_read),         "no total"),
            ("Salvos",        str(totals.total_saved),        "artigos"),
            ("Tempo médio",   f"{totals.avg_daily_minutes} min", "por dia (30 d)"),
        ]
        for label, value, sub in cards:
            card = QFrame()
            card.setObjectName("statCard")
            card.setFrameShape(QFrame.Shape.StyledPanel)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(2)

            lbl = QLabel(label)
            lbl.setObjectName("cardMeta")
            lbl.setFont(self._mono(10))
            cl.addWidget(lbl)

            val = QLabel(value)
            val.setObjectName("feedListTitle")
            vf = QFont("Special Elite")
            if not vf.exactMatch():
                vf = QFont("Courier New")
            vf.setPointSize(22)
            val.setFont(vf)
            cl.addWidget(val)

            sub_lbl = QLabel(sub)
            sub_lbl.setObjectName("cardMeta")
            sub_lbl.setFont(self._mono(9))
            cl.addWidget(sub_lbl)

            layout.addWidget(card, 1)

        return row

    # ------------------------------------------------------------------
    # Gráficos matplotlib
    # ------------------------------------------------------------------

    def _make_canvas(self, figsize: tuple[float, float], pal: dict):
        """Cria Figure + FigureCanvasQTAgg com fundo e eixos sépia."""
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
        except ImportError:
            log.error("matplotlib não disponível")
            return None, None

        import matplotlib
        matplotlib.rcParams.update({
            "font.family":       "monospace",
            "font.size":         9,
            "axes.facecolor":    pal["bg"],
            "figure.facecolor":  pal["bg"],
            "axes.edgecolor":    pal["grid"],
            "axes.labelcolor":   pal["muted"],
            "xtick.color":       pal["muted"],
            "ytick.color":       pal["muted"],
            "grid.color":        pal["grid"],
            "grid.linestyle":    "--",
            "grid.alpha":        0.6,
            "text.color":        pal["fg"],
        })

        fig = Figure(figsize=figsize, tight_layout=True)
        canvas = FigureCanvasQTAgg(fig)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        canvas.setFixedHeight(int(figsize[1] * 72))
        return fig, canvas

    def _build_daily_chart(self, daily, pal: dict, days: int) -> QWidget:
        from app.core.stats import DailyStats
        fig, canvas = self._make_canvas((9, 2.6), pal)
        if canvas is None:
            return QLabel("matplotlib indisponível")

        ax = fig.add_subplot(111)
        labels = [d.date.strftime("%d/%m") for d in daily]
        values = [d.articles_read for d in daily]

        # Mostrar só alguns labels no eixo X para não sobrepor
        step = max(1, len(labels) // 10)
        x = range(len(labels))
        ax.bar(x, values, color=pal["bar"], width=0.7)
        ax.set_xticks([i for i in x if i % step == 0])
        ax.set_xticklabels([labels[i] for i in x if i % step == 0], rotation=30, ha="right")
        ax.set_title(f"Artigos lidos por dia (últimos {days} dias)", color=pal["fg"], pad=8)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)

        canvas.draw()
        return canvas

    def _build_sentiment_chart(self, trend, pal: dict, days: int) -> QWidget:
        fig, canvas = self._make_canvas((9, 2.6), pal)
        if canvas is None:
            return QLabel("matplotlib indisponível")

        ax = fig.add_subplot(111)

        if not trend:
            ax.text(
                0.5, 0.5, "Nenhum artigo com sentimento analisado no período",
                ha="center", va="center", color=pal["muted"],
                transform=ax.transAxes,
            )
            ax.axis("off")
            canvas.draw()
            return canvas

        labels = [d.date.strftime("%d/%m") for d in trend]
        values = [d.avg_sentiment for d in trend]
        x      = list(range(len(labels)))

        ax.axhline(y=0, color=pal["grid"], linewidth=1.2, zorder=1)

        # Preenchimento colorido acima/abaixo de zero
        ax.fill_between(
            x, values, [0] * len(values),
            where=[v >= 0 for v in values],
            color=pal["pos_fill"], alpha=0.6, interpolate=True,
        )
        ax.fill_between(
            x, values, [0] * len(values),
            where=[v < 0 for v in values],
            color=pal["neg_fill"], alpha=0.6, interpolate=True,
        )

        # Linha de tendência com cor dinâmica por segmento
        for i in range(len(x) - 1):
            seg_color = pal["pos_line"] if values[i] >= 0 else pal["neg_line"]
            ax.plot(x[i:i + 2], values[i:i + 2], color=seg_color, linewidth=1.8, zorder=2)
        # Pontos
        pt_colors = [pal["pos_line"] if v >= 0 else pal["neg_line"] for v in values]
        ax.scatter(x, values, c=pt_colors, s=14, zorder=3)

        step = max(1, len(labels) // 10)
        ax.set_xticks([i for i in x if i % step == 0])
        ax.set_xticklabels([labels[i] for i in x if i % step == 0], rotation=30, ha="right")
        ax.set_ylim(-1.1, 1.1)
        ax.set_yticks([-1.0, -0.5, 0.0, 0.5, 1.0])
        ax.set_yticklabels(["−1", "−0.5", "0", "+0.5", "+1"])
        ax.set_title(f"Tendência de sentimento — últimos {days} dias", color=pal["fg"], pad=8)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)

        canvas.draw()
        return canvas

    def _build_entities_section(self, entities: dict, pal: dict) -> QWidget:
        """Três mini-charts horizontais: pessoas, organizações, lugares."""
        section = QWidget()
        layout  = QHBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        labels_map = {
            "people": "Pessoas mencionadas",
            "orgs":   "Organizações",
            "places": "Locais",
        }
        for etype, title in labels_map.items():
            items = entities.get(etype, [])
            fig, canvas = self._make_canvas((3.0, 2.8), pal)
            if canvas is None:
                layout.addWidget(QLabel(title))
                continue

            ax = fig.add_subplot(111)
            if not items:
                ax.text(0.5, 0.5, "Sem dados", ha="center", va="center",
                        color=pal["muted"], transform=ax.transAxes)
                ax.axis("off")
            else:
                names  = [e.name[:24] for e in reversed(items)]
                counts = [e.count     for e in reversed(items)]
                y = range(len(names))
                ax.barh(y, counts, color=pal["bar"])
                ax.set_yticks(list(y))
                ax.set_yticklabels(names, fontsize=8)
                ax.set_title(title, color=pal["fg"], pad=6, fontsize=9)
                ax.xaxis.grid(True)
                ax.set_axisbelow(True)
                ax.spines[["top", "right"]].set_visible(False)
                ax.tick_params(axis="x", labelsize=8)

            canvas.draw()
            layout.addWidget(canvas, 1)

        return section

    def _build_clusters_section(self, clusters: list, pal: dict) -> QWidget:
        """Cards de tópicos identificados por K-means nos embeddings."""
        section = QWidget()
        section.setObjectName("cardsContainer")
        root = QVBoxLayout(section)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QLabel("Tópicos identificados  (por similaridade semântica)")
        header.setObjectName("cardMeta")
        header.setFont(self._mono(10))
        root.addWidget(header)

        grid_w  = QWidget()
        grid    = QHBoxLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        title_font = QFont("Special Elite")
        if not title_font.exactMatch():
            title_font = QFont("Courier New")
        title_font.setPointSize(12)

        sample_font = QFont("IM Fell English")
        if not sample_font.exactMatch():
            sample_font = QFont("Georgia")
        sample_font.setPointSize(11)
        sample_font.setItalic(True)

        for cluster in clusters:
            card = QFrame()
            card.setObjectName("statCard")
            card.setFrameShape(QFrame.Shape.StyledPanel)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 10)
            cl.setSpacing(4)

            lbl_label = QLabel(cluster.label)
            lbl_label.setObjectName("feedListTitle")
            lbl_label.setFont(title_font)
            lbl_label.setWordWrap(True)
            cl.addWidget(lbl_label)

            lbl_count = QLabel(f"{cluster.article_count} artigos")
            lbl_count.setObjectName("cardMeta")
            lbl_count.setFont(self._mono(9))
            cl.addWidget(lbl_count)

            for title in cluster.sample_titles:
                t = title[:70] + "…" if len(title) > 70 else title
                lbl_t = QLabel(t)
                lbl_t.setObjectName("cardSummary")
                lbl_t.setFont(sample_font)
                lbl_t.setWordWrap(True)
                cl.addWidget(lbl_t)

            cl.addStretch()
            grid.addWidget(card, 1)

        root.addWidget(grid_w)
        return section

    def _build_ai_tags_chart(self, ai_tags, pal: dict, days: int) -> QWidget:
        """Gráfico horizontal: tags de IA mais frequentes nos artigos lidos."""
        fig, canvas = self._make_canvas((9, max(2.4, len(ai_tags) * 0.28)), pal)
        if canvas is None:
            return QLabel("matplotlib indisponível")

        ax = fig.add_subplot(111)
        names  = [t.tag[:30]  for t in reversed(ai_tags)]
        counts = [t.count      for t in reversed(ai_tags)]
        y = range(len(names))
        ax.barh(y, counts, color=pal["accent"])
        ax.set_yticks(list(y))
        ax.set_yticklabels(names, fontsize=8)
        ax.set_title(
            f"Tags de IA mais frequentes nos artigos lidos — últimos {days} dias",
            color=pal["fg"], pad=8,
        )
        ax.xaxis.grid(True)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", labelsize=8)

        canvas.draw()
        return canvas

    def _build_feed_chart(self, feeds, pal: dict) -> QWidget:
        fig, canvas = self._make_canvas((4.5, 3.2), pal)
        if canvas is None:
            return QLabel("matplotlib indisponível")

        if not feeds:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "Sem dados", ha="center", va="center", color=pal["muted"])
            ax.axis("off")
            canvas.draw()
            return canvas

        ax = fig.add_subplot(111)
        names  = [f.feed_name[:22] for f in reversed(feeds)]
        values = [f.articles_read for f in reversed(feeds)]
        y = range(len(names))
        ax.barh(y, values, color=pal["bar"])
        ax.set_yticks(list(y))
        ax.set_yticklabels(names)
        ax.set_title("Top feeds lidos", color=pal["fg"], pad=8)
        ax.xaxis.grid(True)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)

        canvas.draw()
        return canvas

    def _build_monthly_chart(self, monthly, pal: dict) -> QWidget:
        fig, canvas = self._make_canvas((4.5, 3.2), pal)
        if canvas is None:
            return QLabel("matplotlib indisponível")

        ax = fig.add_subplot(111)
        labels = [calendar.month_abbr[m.month] for m in monthly]
        saved  = [m.articles_saved for m in monthly]
        read   = [m.articles_read  for m in monthly]

        import numpy as np
        x  = np.arange(len(labels))
        w  = 0.4
        ax.bar(x - w / 2, saved, width=w, label="Salvos",  color=pal["accent"])
        ax.bar(x + w / 2, read,  width=w, label="Lidos",   color=pal["bar2"])
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_title("Salvos e lidos por mês", color=pal["fg"], pad=8)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(facecolor=pal["bg"], edgecolor=pal["grid"], labelcolor=pal["fg"])

        canvas.draw()
        return canvas

    def _build_platform_chart(self, platform, pal: dict) -> QWidget:
        fig, canvas = self._make_canvas((9, 2.2), pal)
        if canvas is None:
            return QLabel("matplotlib indisponível")

        ax = fig.add_subplot(111)
        labels = [p.feed_type for p in platform]
        values = [p.articles_read for p in platform]
        ax.bar(labels, values, color=pal["bar"])
        ax.set_title("Artigos lidos por plataforma", color=pal["fg"], pad=8)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)

        canvas.draw()
        return canvas

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f
