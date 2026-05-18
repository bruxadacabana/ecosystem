"""Janela principal do KOSMOS."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout, QMainWindow,
    QSplitter, QStackedWidget, QWidget,
    QStatusBar,
)

if TYPE_CHECKING:
    from app.core.background_updater import BackgroundUpdater
    from app.core.feed_manager import FeedManager
    from app.utils.config import Config
    from app.theme.theme_manager import ThemeManager

from PyQt6.QtCore import pyqtSignal as _pyqtSignal

from app.core.background_analyzer import BackgroundAnalyzer
from app.core.title_translator import TitleTranslator


class _OllamaPoller(QThread):
    """Verificação pontual de disponibilidade do Ollama (não bloqueia a UI)."""

    result = _pyqtSignal(bool)

    def __init__(self, endpoint: str) -> None:
        super().__init__()
        self._endpoint = endpoint

    def run(self) -> None:
        from app.core.ai_bridge import AiBridge
        self.result.emit(AiBridge(endpoint=self._endpoint).is_available())

log = logging.getLogger("kosmos.ui")


class MainWindow(QMainWindow):
    """Janela principal: sidebar + stack de views."""

    def __init__(
        self,
        config: "Config",
        theme_manager: "ThemeManager",
        feed_manager: "FeedManager",
        updater: "BackgroundUpdater",
    ) -> None:
        super().__init__()
        self._config  = config
        self._theme   = theme_manager
        self._fm      = feed_manager
        self._updater = updater

        self.setWindowTitle("KOSMOS")
        self.setMinimumSize(900, 580)
        self.resize(1200, 750)

        self._build_ui()
        self._connect_signals()

        # Barra de status para progresso e erros de background
        self._status_bar = QStatusBar()
        self._status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self._status_bar)
        self._status_clear_timer = QTimer(self)
        self._status_clear_timer.setSingleShot(True)
        self._status_clear_timer.setInterval(6000)
        self._status_clear_timer.timeout.connect(self._status_bar.clearMessage)

        # Badge de status global do Ollama (H.4)
        from PyQt6.QtWidgets import QLabel
        self._ollama_badge = QLabel("○  Ollama")
        self._ollama_badge.setObjectName("ollamaUnknown")
        self._ollama_badge.setContentsMargins(8, 0, 8, 0)
        self._status_bar.addPermanentWidget(self._ollama_badge)
        # Polling leve a cada 60s
        self._ollama_poll_timer = QTimer(self)
        self._ollama_poll_timer.setInterval(60_000)
        self._ollama_poll_timer.timeout.connect(self._poll_ollama_status)
        self._ollama_poll_timer.start()
        self._ollama_poller: _OllamaPoller | None = None
        # Verificação inicial (roda assim que o event loop começa)
        QTimer.singleShot(500, self._poll_ollama_status)

        # Carregar feeds na sidebar e stats do dashboard
        self._sidebar.refresh_feeds()
        self._dashboard.load(self._fm)

        # Migrar artigos já salvos que ainda não têm .md em data/archive/
        self._migrate_saved_to_archive()

        # Iniciar pré-análise em background
        self._bg_analyzer = BackgroundAnalyzer(self._fm, self._config)
        self._bg_analyzer.article_analyzed.connect(self._on_article_analyzed)
        self._bg_analyzer.start()
        # Enfileira artigos sem análise que já existem no banco
        unanalyzed = self._fm.get_unanalyzed_article_ids(limit=100)
        if unanalyzed:
            self._bg_analyzer.enqueue_background(unanalyzed)

        # Retry: re-enfileira pendentes a cada 5 min (cobre caso Ollama offline no startup)
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(5 * 60 * 1000)
        self._retry_timer.timeout.connect(self._on_retry_unanalyzed)
        self._retry_timer.start()

        # Status writer: publica bg_processing no ecosystem.json para o HUB a cada 30s
        self._status_writer_timer = QTimer(self)
        self._status_writer_timer.setInterval(30_000)
        self._status_writer_timer.timeout.connect(self._write_bg_status)
        self._status_writer_timer.start()
        self._write_bg_status()  # escrita inicial imediata

        # Tradutor de títulos dos cards
        self._title_translator = TitleTranslator()
        self._title_translator.title_translated.connect(self._on_title_translated)
        self._title_translator.status_message.connect(self._on_status_message)
        self._bg_analyzer.status_message.connect(self._on_status_message)
        # Carregar idioma configurado (carrega cache do disco)
        lang = str(self._config.get("display_language", ""))
        if lang:
            self._title_translator.set_target_lang(lang)
        self._title_translator.start()

    def _migrate_saved_to_archive(self) -> None:
        """Exporta artigos com is_saved=1 que ainda não têm .md em data/archive/."""
        from app.core.archive_manager import export_article, get_archive_path
        feeds = {f.id: f.name for f in self._fm.get_feeds()}
        articles = self._fm.get_saved_articles(limit=500)
        migrated = 0
        for article in articles:
            feed_name = feeds.get(article.feed_id)
            if not get_archive_path(article, feed_name).exists():
                try:
                    export_article(article, feed_name)
                    migrated += 1
                except Exception as exc:
                    log.warning("Migração: falha ao exportar '%s': %s", article.title, exc)
        if migrated:
            log.info("Migração: %d artigo(s) exportados para data/archive/", migrated)

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setObjectName("mainSplitter")
        splitter.setChildrenCollapsible(False)

        from app.ui.sidebar import Sidebar
        self._sidebar = Sidebar(self._theme, self._fm)
        self._sidebar.setFixedWidth(220)
        splitter.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._stack.setObjectName("centralStack")
        splitter.addWidget(self._stack)

        splitter.setSizes([220, 980])
        root.addWidget(splitter)

        self._setup_views()

        # Overlay de busca global — filho do widget central para cobrir toda a área
        from app.ui.widgets.search_overlay import SearchOverlay
        self._search_overlay = SearchOverlay(self._fm, self._config, parent=central)
        self._search_overlay.article_selected.connect(self._on_search_article_selected)

        shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        shortcut.activated.connect(self._search_overlay.activate)

    def _setup_views(self) -> None:
        from app.ui.views.dashboard_view     import DashboardView
        from app.ui.views.feed_list_view     import FeedListView
        from app.ui.views.unified_feed_view  import UnifiedFeedView
        from app.ui.views.sources_view       import SourcesView
        from app.ui.views.reader_view        import ReaderView
        from app.ui.views.settings_view      import SettingsView
        from app.ui.views.saved_view         import SavedView
        from app.ui.views.stats_view         import StatsView

        self._dashboard = DashboardView(self._theme)
        self._stack.addWidget(self._dashboard)

        self._feed_list = FeedListView(self._fm)
        self._stack.addWidget(self._feed_list)

        self._unified_feed = UnifiedFeedView(self._fm, self._config)
        self._stack.addWidget(self._unified_feed)

        self._sources = SourcesView(self._fm)
        self._stack.addWidget(self._sources)

        self._reader = ReaderView(self._fm, self._theme, self._config)
        self._stack.addWidget(self._reader)

        self._settings = SettingsView(self._config, self._theme, self._fm)
        self._stack.addWidget(self._settings)

        self._saved = SavedView(self._fm)
        self._stack.addWidget(self._saved)

        self._stats = StatsView(self._theme)
        self._stack.addWidget(self._stats)

        # Qual view de lista estava ativa antes de abrir o reader
        self._reader_source: object = self._feed_list

        # Mapeamento de nomes de view → widget
        self._view_map = {
            "dashboard":  self._dashboard,
            "feeds":      self._unified_feed,
            "sources":    self._sources,
            "all_unread": self._dashboard,
            "saved":      self._saved,
            "archive":    self._saved,
            "stats":      self._stats,
            "settings":   self._settings,
        }

    # ------------------------------------------------------------------
    # Sinais
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Sidebar → navegação
        self._sidebar.nav_requested.connect(self._on_navigate)
        self._sidebar.add_feed_requested.connect(self._on_add_feed)
        self._sidebar.refresh_requested.connect(self._on_force_refresh)

        # Saved view
        self._saved.back_requested.connect(self._on_back)
        self._saved.article_clicked.connect(self._on_saved_article_clicked)

        # Stats view
        self._stats.back_requested.connect(self._on_back)

        # Feed list view (acesso direto a um feed específico)
        self._feed_list.back_requested.connect(self._on_back)
        self._feed_list.article_clicked.connect(self._on_article_clicked)
        self._feed_list.unread_changed.connect(self._sidebar.update_badge)
        self._feed_list.translation_requested.connect(self._on_translation_requested)

        # Unified feed view
        self._unified_feed.back_requested.connect(self._on_back)
        self._unified_feed.article_clicked.connect(self._on_unified_article_clicked)
        self._unified_feed.unread_changed.connect(self._sidebar.update_all_badges)
        self._unified_feed.translation_requested.connect(self._on_translation_requested)

        # Reader view
        self._reader.back_requested.connect(self._on_reader_back)
        self._reader.article_changed.connect(self._on_reader_article_changed)
        self._reader.read_toggled.connect(self._on_reader_read_toggled)
        self._reader.saved_toggled.connect(self._on_reader_saved_toggled)
        self._reader.analysis_done.connect(self._dashboard.schedule_cluster_refresh)

        # Dashboard view
        self._dashboard.article_clicked.connect(self._on_dashboard_article_clicked)

        # Sources view
        self._sources.feeds_changed.connect(self._on_sources_changed)
        self._sources.back_requested.connect(self._on_back)

        # Settings view
        self._settings.feeds_refreshed.connect(self._sidebar.refresh_feeds)

        # Background updater
        self._updater.feed_updated.connect(self._on_feed_updated)
        self._updater.update_error.connect(self._on_update_error)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_navigate(self, view: str) -> None:
        widget = self._view_map.get(view, self._dashboard)
        if widget is self._dashboard:
            self._dashboard.load(self._fm)
        elif widget is self._settings:
            self._settings.refresh()
        elif widget is self._unified_feed:
            self._unified_feed.load()
        elif widget is self._sources:
            self._sources.load()
        elif widget is self._saved:
            self._saved.load()
        elif widget is self._stats:
            self._stats.load()
        self._stack.setCurrentWidget(widget)

    def _on_sources_changed(self) -> None:
        """Feed adicionado, removido ou pausado — atualiza views dependentes."""
        if self._stack.currentWidget() is self._unified_feed:
            self._unified_feed.refresh()

    def _on_back(self) -> None:
        self._stack.setCurrentWidget(self._dashboard)

    def _on_unified_article_clicked(self, article_id: int) -> None:
        article = self._fm.get_article(article_id)
        if article is None:
            return
        feed          = self._fm.get_feed(article.feed_id)
        article_ids   = self._unified_feed.get_article_ids()
        current_index = self._unified_feed.get_article_index(article_id)
        self._reader_source = self._unified_feed
        self._title_translator.pause()
        self._reader.open_article(
            article=article,
            feed=feed,
            article_ids=article_ids,
            current_index=max(0, current_index),
        )
        self._stack.setCurrentWidget(self._reader)

    def _on_add_feed(self) -> None:
        categories = self._fm.get_categories()
        from app.ui.dialogs.add_feed_dialog import AddFeedDialog
        dlg = AddFeedDialog(self._fm, categories, parent=self)
        if dlg.exec() and dlg.created_feed:
            # Abrir unified feed filtrado pela nova fonte
            self._unified_feed.load()
            self._stack.setCurrentWidget(self._unified_feed)

    def _on_article_clicked(self, article_id: int) -> None:
        article = self._fm.get_article(article_id)
        if article is None:
            log.warning("Artigo %d não encontrado.", article_id)
            return

        feed          = self._fm.get_feed(article.feed_id)
        article_ids   = self._feed_list.get_article_ids()
        current_index = self._feed_list.get_article_index(article_id)
        self._reader_source = self._feed_list
        self._title_translator.pause()
        self._reader.open_article(
            article=article,
            feed=feed,
            article_ids=article_ids,
            current_index=max(0, current_index),
        )
        self._stack.setCurrentWidget(self._reader)

    def _on_dashboard_article_clicked(self, article_id: int) -> None:
        """Título de tópico clicado no dashboard — abre no reader."""
        article = self._fm.get_article(article_id)
        if article is None:
            return
        feed = self._fm.get_feed(article.feed_id)
        self._reader_source = self._dashboard
        self._reader.open_article(
            article=article,
            feed=feed,
            article_ids=[article_id],
            current_index=0,
        )
        self._stack.setCurrentWidget(self._reader)

    def _on_reader_back(self) -> None:
        self._title_translator.resume()
        self._stack.setCurrentWidget(self._reader_source)
        # Reaplica traduções em cache à view de origem — garante que cards que
        # tiveram seus widgets recriados enquanto o reader estava aberto (ex: ao
        # navegar pela sidebar durante a leitura) mostrem títulos traduzidos
        # imediatamente, sem esperar o worker processar a fila.
        if hasattr(self._reader_source, "get_article_ids"):
            ids = self._reader_source.get_article_ids()
            if ids:
                self._title_translator.reapply_cache(ids)

    def _on_reader_article_changed(self, article_id: int) -> None:
        """Atualiza o card correspondente na lista."""
        if self._reader_source is self._unified_feed:
            self._unified_feed.mark_card_read(article_id)
        else:
            self._feed_list._on_card_clicked_external(article_id)

    def _on_search_article_selected(self, article_id: int) -> None:
        """Resultado de busca clicado — abre direto no reader."""
        article = self._fm.get_article(article_id)
        if article is None:
            return
        feed = self._fm.get_feed(article.feed_id)
        self._reader_source = self._dashboard
        self._reader.open_article(
            article=article,
            feed=feed,
            article_ids=[article_id],
            current_index=0,
        )
        self._stack.setCurrentWidget(self._reader)

    def _on_reader_read_toggled(self, article_id: int, is_read: bool) -> None:
        self._sidebar.update_all_badges()

    def _on_saved_article_clicked(self, article_id: int) -> None:
        article = self._fm.get_article(article_id)
        if article is None:
            return
        feed          = self._fm.get_feed(article.feed_id)
        article_ids   = self._saved.get_article_ids()
        current_index = self._saved.get_article_index(article_id)
        self._reader_source = self._saved
        self._reader.open_article(
            article=article,
            feed=feed,
            article_ids=article_ids,
            current_index=max(0, current_index),
        )
        self._stack.setCurrentWidget(self._reader)

    def _on_reader_saved_toggled(self, article_id: int, is_saved: bool) -> None:
        if not is_saved and self._stack.currentWidget() is self._saved:
            self._saved.mark_card_unsaved(article_id)

    def _on_feed_updated(self, feed_id: int, new_count: int) -> None:
        if self._stack.currentWidget() is self._unified_feed and new_count > 0:
            self._unified_feed.refresh()
        elif (
            self._stack.currentWidget() is self._feed_list
            and self._feed_list._feed_id == feed_id
            and new_count > 0
        ):
            self._feed_list.refresh()

        # Enfileirar novos artigos para análise e tradução em background
        if new_count > 0:
            new_ids = self._fm.get_unanalyzed_article_ids(limit=new_count + 5)
            if new_ids:
                self._bg_analyzer.enqueue_background(new_ids)
            # Tradução: buscar artigos recém-baixados e enfileirar títulos
            lang = str(self._config.get("display_language", ""))
            if lang:
                articles = self._fm.get_articles(feed_id, limit=new_count + 5)
                items = [(a.id, a.title or "", getattr(a, "language", None)) for a in articles]
                if items:
                    self._on_translation_requested(items)

    def _on_force_refresh(self) -> None:
        """Limpa cache de etag de todos os feeds e dispara ciclo imediato.

        Garante que fetches retornem conteúdo completo (sem 304 em cima
        de etags corrompidos por bugs anteriores).
        """
        self._fm.clear_all_etags()
        self._updater.trigger_now()

    def _on_update_error(self, feed_id: int, message: str) -> None:
        log.warning("Erro ao atualizar feed %d: %s", feed_id, message)

    def _on_article_analyzed(self, article_id: int, data: dict) -> None:
        """Atualiza cards em tempo real quando análise em background conclui."""
        self._feed_list.update_card_analysis(article_id, data)
        self._unified_feed.update_card_analysis(article_id, data)

    def _on_retry_unanalyzed(self) -> None:
        """Re-enfileira artigos pendentes (cobre caso Ollama offline no startup)."""
        if not self._config.get("ai_enabled", False):
            return
        pending = self._fm.get_unanalyzed_article_ids(limit=50)
        if pending:
            self._bg_analyzer.enqueue_background(pending)

    def _on_translation_requested(
        self, items: list  # list[tuple[int, str, str | None]]
    ) -> None:
        lang = str(self._config.get("display_language", ""))
        if not lang:
            return
        self._title_translator.set_target_lang(lang)
        self._title_translator.enqueue_batch(items)

    def _on_title_translated(self, article_id: int, translated: str) -> None:
        self._feed_list.update_card_title(article_id, translated)
        self._unified_feed.update_card_title(article_id, translated)

    def _poll_ollama_status(self) -> None:
        if self._ollama_poller and self._ollama_poller.isRunning():
            return
        endpoint = str(self._config.get("ai_endpoint", "http://localhost:7072"))
        self._ollama_poller = _OllamaPoller(endpoint)
        self._ollama_poller.result.connect(self._on_ollama_polled)
        self._ollama_poller.start()

    def _on_ollama_polled(self, available: bool) -> None:
        badge = self._ollama_badge
        if available:
            badge.setText("●  Ollama")
            badge.setObjectName("ollamaOnline")
        else:
            badge.setText("○  Ollama")
            badge.setObjectName("ollamaOffline")
        badge.style().unpolish(badge)
        badge.style().polish(badge)

    def _write_bg_status(self) -> None:
        """Publica estado do bg_analyzer no ecosystem.json para o HUB."""
        try:
            import sys as _sys
            _root = str(__import__("pathlib").Path(__file__).parent.parent.parent.parent)
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from ecosystem_client import write_section  # type: ignore
            write_section("kosmos", {
                "bg_processing": {
                    "pending":       self._bg_analyzer.queue_size(),
                    "worker_active": self._bg_analyzer.isRunning(),
                }
            })
        except Exception:
            pass

    def _on_status_message(self, message: str) -> None:
        self._status_bar.showMessage(message)
        # Mensagens de conclusão (✓) e de progresso simples somem após 6s
        # Mensagens de erro (⚠) ficam até a próxima mensagem
        if not message.startswith("⚠"):
            self._status_clear_timer.start()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._retry_timer.stop()
        self._ollama_poll_timer.stop()
        self._title_translator.save_cache()
        self._updater.stop()
        self._bg_analyzer.stop()
        self._bg_analyzer.wait(2000)
        self._title_translator.stop()
        self._title_translator.wait(2000)
        super().closeEvent(event)
