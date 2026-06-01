"""
main_window.py — Janela principal do KOSMOS v3.

Layout 3-painéis horizontal via QSplitter:
  [ FeedSidebar | ArticleList | ReaderPane ]

Ciclo de vida:
  - __init__: constrói UI, carrega feeds, inicia FetchWorker.
  - FetchWorker (P2) roda em background durante toda a sessão.
  - closeEvent: para FetchWorker, salva config, fecha.

Conexões de sinais:
  FeedSidebar.feed_selected  → ArticleList.load_articles
  ArticleList.article_selected → ReaderPane.show_article
  ReaderPane.article_read    → FeedSidebar.update_unread_count
  FetchWorker.feed_done      → ArticleList.on_feed_updated
  FetchWorker.feed_done      → FeedSidebar.update_unread_count
  FetchWorker.feed_error     → statusbar (mensagem de erro)
  FetchWorker.cycle_done     → statusbar (resumo do ciclo)
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QStatusBar,
    QWidget,
)

from app.core.fetch_worker import FetchWorker
from app.ui.views.article_list import ArticleList
from app.ui.views.feed_sidebar import ALL_FEEDS_ID, FeedSidebar
from app.ui.views.reader_pane import ReaderPane
from app.utils.config import KosmosConfig, save_config

log = logging.getLogger("kosmos.main_window")


class MainWindow(QMainWindow):
    def __init__(self, config: KosmosConfig) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle("KOSMOS")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._setup_ui()
        self._connect_signals()
        self._start_worker()

        # Carrega dados iniciais após o event loop iniciar
        QTimer.singleShot(0, self._initial_load)
        log.info("MainWindow inicializada.")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._sidebar = FeedSidebar()
        self._article_list = ArticleList()
        self._reader = ReaderPane()

        splitter.addWidget(self._sidebar)
        splitter.addWidget(self._article_list)
        splitter.addWidget(self._reader)

        # Proporção inicial: sidebar 220 / lista 340 / leitor resto
        splitter.setSizes([220, 340, 720])
        splitter.setStretchFactor(0, 0)   # sidebar: não estica
        splitter.setStretchFactor(1, 1)   # lista: estica um pouco
        splitter.setStretchFactor(2, 3)   # leitor: estica mais

        self.setCentralWidget(splitter)
        self._splitter = splitter

        bar = QStatusBar()
        self.setStatusBar(bar)
        bar.showMessage("KOSMOS pronto.")

    def _connect_signals(self) -> None:
        self._sidebar.feed_selected.connect(self._on_feed_selected)
        self._article_list.article_selected.connect(self._on_article_selected)
        self._reader.article_read.connect(self._on_article_read)

    def _start_worker(self) -> None:
        self._worker = FetchWorker(self)
        self._worker.feed_done.connect(self._article_list.on_feed_updated)
        self._worker.feed_done.connect(
            lambda fid, _n: self._sidebar.update_unread_count(fid)
        )
        self._worker.feed_error.connect(
            lambda fid, msg: self.statusBar().showMessage(
                f"Erro no feed {fid}: {msg}", 5000
            )
        )
        self._worker.cycle_done.connect(
            lambda n: self.statusBar().showMessage(
                f"Feeds atualizados — {n} artigo(s) novo(s)." if n else "Feeds verificados.",
                4000,
            )
        )
        self._worker.start()
        log.info("FetchWorker iniciado.")

    def _initial_load(self) -> None:
        self._sidebar.load_feeds()
        self._article_list.load_articles(ALL_FEEDS_ID)
        log.info("Carga inicial concluída.")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_feed_selected(self, feed_id: int) -> None:
        log.debug("Feed selecionado: %d", feed_id)
        self._article_list.load_articles(feed_id)
        self._reader.clear()

    def _on_article_selected(self, article_id: int) -> None:
        log.debug("Artigo selecionado: %d", article_id)
        self._reader.show_article(article_id)

    def _on_article_read(self, article_id: int) -> None:
        self._sidebar.update_unread_count(-1)  # refresh completo da sidebar

    # ------------------------------------------------------------------
    # Fechamento
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        log.info("Encerrando KOSMOS...")
        if self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        try:
            save_config(self.config)
        except OSError as exc:
            log.error("Falha ao salvar config: %s", exc)
        event.accept()
