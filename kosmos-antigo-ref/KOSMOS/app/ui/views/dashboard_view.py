"""Tela inicial do KOSMOS — dashboard com cosmos, estatísticas e tópicos em tempo real."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager
    from app.core.stats import ArticleCluster
    from app.theme.theme_manager import ThemeManager

log = logging.getLogger("kosmos.ui.dashboard")


class _StatsPanel(QWidget):
    """Card sépia com título e lista de pares (nome, contagem)."""

    def __init__(self, title: str, empty_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardPanel")
        self.setFixedWidth(248)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(0)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("dashboardPanelTitle")
        title_lbl.setFont(self._special_elite(10))
        root.addWidget(title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("dashboardPanelSep")
        root.addWidget(sep)
        root.addSpacing(6)

        self._content = QVBoxLayout()
        self._content.setSpacing(4)
        self._empty_text = empty_text
        root.addLayout(self._content)
        root.addStretch()

        self._show_empty()

    def set_data(self, items: list[tuple[str, int]]) -> None:
        self._clear()
        if not items:
            self._show_empty()
            return
        max_count = max(cnt for _, cnt in items)
        for name, cnt in items:
            row = QHBoxLayout()
            row.setSpacing(8)

            name_lbl = QLabel(name[:28] + ("…" if len(name) > 28 else ""))
            name_lbl.setObjectName("dashboardStatName")
            name_lbl.setFont(self._courier(10))
            row.addWidget(name_lbl, 1)

            count_lbl = QLabel(str(cnt))
            count_lbl.setObjectName("dashboardStatCount")
            count_lbl.setFont(self._courier(10))
            count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            count_lbl.setFixedWidth(36)
            row.addWidget(count_lbl)

            bar = QFrame()
            bar.setObjectName("dashboardStatBar")
            bar.setFixedHeight(2)
            bar.setFixedWidth(max(4, int(80 * cnt / max_count)))

            row_widget = QWidget()
            row_widget.setObjectName("dashboardStatRow")
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            row_layout.addLayout(row)
            row_layout.addWidget(bar)

            self._content.addWidget(row_widget)

    def _show_empty(self) -> None:
        lbl = QLabel(self._empty_text)
        lbl.setObjectName("dashboardStatEmpty")
        lbl.setFont(self._courier(10))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setContentsMargins(0, 8, 0, 0)
        self._content.addWidget(lbl)

    def _clear(self) -> None:
        while self._content.count():
            item = self._content.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    @staticmethod
    def _special_elite(size: int) -> QFont:
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f

    @staticmethod
    def _courier(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f


class _ClusterWorker(QThread):
    """Executa K-means de clustering em background para não travar a UI."""

    done   = pyqtSignal(list)   # list[ArticleCluster]
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            from app.core.stats import get_article_clusters
            clusters = get_article_clusters(days=90)
            self.done.emit(clusters)
        except Exception as exc:
            log.error("ClusterWorker falhou: %s", exc)
            self.failed.emit(str(exc))


class DashboardView(QWidget):
    """Tela inicial do KOSMOS — campo estelar com estatísticas e tópicos."""

    article_clicked = pyqtSignal(int)   # usuário clicou num título de tópico

    def __init__(self, theme_manager: "ThemeManager", parent=None) -> None:
        super().__init__(parent)
        self._theme = theme_manager
        self._cluster_worker: _ClusterWorker | None = None
        self.setObjectName("dashboardView")
        self._build_ui()

        # Timer de debounce — 8 s após o último analysis_done
        self._cluster_timer = QTimer(self)
        self._cluster_timer.setSingleShot(True)
        self._cluster_timer.setInterval(8000)
        self._cluster_timer.timeout.connect(self._run_cluster_worker)

    # ------------------------------------------------------------------
    # Pintura do fundo cósmico
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        from app.ui.widgets.cosmos_painter import paint_cosmos
        paint_cosmos(
            painter,
            self.width(),
            self.height(),
            theme=self._theme.current,
            density="cosmic",
            avoid_center=True,
        )
        painter.end()
        super().paintEvent(event)

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Área rolável para acomodar tópicos sem encolher o cosmos
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

        # Título principal
        title = QLabel("KOSMOS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("dashboardTitle")
        tf = QFont("IM Fell English")
        if not tf.exactMatch():
            tf = QFont("Georgia")
        tf.setPointSize(36)
        tf.setItalic(True)
        title.setFont(tf)
        layout.addWidget(title)

        layout.addSpacing(6)

        # Linha de resumo
        self._summary_lbl = QLabel("")
        self._summary_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_lbl.setObjectName("dashboardSummary")
        sf = QFont("Courier Prime")
        if not sf.exactMatch():
            sf = QFont("Courier New")
        sf.setPointSize(11)
        self._summary_lbl.setFont(sf)
        layout.addWidget(self._summary_lbl)

        layout.addSpacing(28)

        # Painéis Top Fontes / Top Tags
        panels_row = QHBoxLayout()
        panels_row.setSpacing(24)
        panels_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._fontes_panel = _StatsPanel("TOP FONTES", "nenhuma leitura ainda")
        self._tags_panel   = _StatsPanel("TOP TAGS",   "nenhuma tag ainda")

        panels_row.addWidget(self._fontes_panel)
        panels_row.addWidget(self._tags_panel)
        layout.addLayout(panels_row)

        layout.addSpacing(32)

        # Seção de tópicos (cluster cards)
        self._topics_section = QWidget()
        self._topics_section.setObjectName("dashboardTopicsSection")
        self._topics_section.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        topics_v = QVBoxLayout(self._topics_section)
        topics_v.setContentsMargins(0, 0, 0, 0)
        topics_v.setSpacing(10)

        topics_title = QLabel("TÓPICOS EM DESTAQUE")
        topics_title.setObjectName("dashboardSectionTitle")
        tf2 = QFont("Special Elite")
        if not tf2.exactMatch():
            tf2 = QFont("Courier New")
        tf2.setPointSize(10)
        topics_title.setFont(tf2)
        topics_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        topics_v.addWidget(topics_title)

        self._topics_status = QLabel("calculando tópicos…")
        self._topics_status.setObjectName("dashboardStatEmpty")
        sf2 = QFont("Courier Prime")
        if not sf2.exactMatch():
            sf2 = QFont("Courier New")
        sf2.setPointSize(10)
        self._topics_status.setFont(sf2)
        self._topics_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        topics_v.addWidget(self._topics_status)

        # Grade de cards — preenchida em _rebuild_topics
        self._clusters_grid = QWidget()
        self._clusters_grid.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._clusters_layout = QHBoxLayout(self._clusters_grid)
        self._clusters_layout.setContentsMargins(0, 0, 0, 0)
        self._clusters_layout.setSpacing(12)
        self._clusters_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        topics_v.addWidget(self._clusters_grid)

        self._topics_section.setVisible(False)
        layout.addWidget(self._topics_section)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load(self, fm: "FeedManager") -> None:
        """Atualiza dados do dashboard e inicia clustering inicial."""
        summary = fm.get_stats_summary()
        parts = []
        if summary["active_feeds"]:
            parts.append(f"{summary['active_feeds']} feed(s) ativo(s)")
        if summary["total_read"]:
            parts.append(f"{summary['total_read']:,} artigo(s) lido(s)")
        if summary["total_saved"]:
            parts.append(f"{summary['total_saved']} salvo(s)")
        self._summary_lbl.setText("  ·  ".join(parts) if parts else "bem-vindo ao KOSMOS")

        top_feeds = fm.get_top_feeds_by_reads(limit=5)
        self._fontes_panel.set_data([(f.name, cnt) for f, cnt in top_feeds])

        top_tags = fm.get_top_tags(limit=5)
        self._tags_panel.set_data([(t.name, cnt) for t, cnt in top_tags])

        # Clustering inicial (sem debounce)
        self._run_cluster_worker()

    def schedule_cluster_refresh(self) -> None:
        """Agenda re-clustering com debounce de 8 s (chamado ao receber analysis_done)."""
        self._cluster_timer.start()   # reinicia se já estava correndo

    # ------------------------------------------------------------------
    # Clustering em background
    # ------------------------------------------------------------------

    def _run_cluster_worker(self) -> None:
        if self._cluster_worker and self._cluster_worker.isRunning():
            return
        self._cluster_worker = _ClusterWorker(self)
        self._cluster_worker.done.connect(self._on_clusters_done)
        self._cluster_worker.failed.connect(self._on_clusters_failed)
        self._cluster_worker.start()

    def _on_clusters_done(self, clusters: list) -> None:
        self._rebuild_topics(clusters)

    def _on_clusters_failed(self, msg: str) -> None:
        self._topics_status.setText("tópicos indisponíveis")
        self._topics_status.setVisible(True)
        self._clusters_grid.setVisible(False)
        self._topics_section.setVisible(True)

    def _rebuild_topics(self, clusters: list) -> None:
        # Limpar cards antigos
        while self._clusters_layout.count():
            item = self._clusters_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not clusters:
            self._topics_status.setText("embeddings insuficientes para agrupar tópicos")
            self._topics_status.setVisible(True)
            self._clusters_grid.setVisible(False)
            self._topics_section.setVisible(True)
            return

        self._topics_status.setVisible(False)
        self._clusters_grid.setVisible(True)

        cf = QFont("Courier Prime")
        if not cf.exactMatch():
            cf = QFont("Courier New")
        cf.setPointSize(10)

        lf = QFont("Special Elite")
        if not lf.exactMatch():
            lf = QFont("Courier New")
        lf.setPointSize(10)

        for cluster in clusters:
            card = QWidget()
            card.setObjectName("dashboardClusterCard")
            card.setFixedWidth(180)
            card.setCursor(Qt.CursorShape.ArrowCursor)
            card_v = QVBoxLayout(card)
            card_v.setContentsMargins(12, 10, 12, 10)
            card_v.setSpacing(4)

            # Rótulo do cluster
            lbl = QLabel(cluster.label)
            lbl.setObjectName("dashboardClusterLabel")
            lbl.setFont(lf)
            lbl.setWordWrap(True)
            card_v.addWidget(lbl)

            # Contagem
            count_lbl = QLabel(f"{cluster.article_count} artigo(s)")
            count_lbl.setObjectName("dashboardClusterCount")
            count_lbl.setFont(cf)
            card_v.addWidget(count_lbl)

            # Títulos de exemplo (clicáveis)
            for i, title_text in enumerate(cluster.sample_titles[:3]):
                article_id = cluster.article_ids[i] if i < len(cluster.article_ids) else None
                title_lbl = QLabel(title_text[:60] + ("…" if len(title_text) > 60 else ""))
                title_lbl.setObjectName("dashboardClusterTitle")
                title_lbl.setFont(cf)
                title_lbl.setWordWrap(True)
                if article_id is not None:
                    title_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
                    _id = article_id
                    title_lbl.mousePressEvent = (  # type: ignore[method-assign]
                        lambda _e, aid=_id: self.article_clicked.emit(aid)
                    )
                card_v.addWidget(title_lbl)

            card_v.addStretch()
            self._clusters_layout.addWidget(card)

        self._topics_section.setVisible(True)
