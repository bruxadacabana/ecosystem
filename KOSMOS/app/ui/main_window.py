"""Janela principal do KOSMOS."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout, QMainWindow,
    QSplitter, QStackedWidget, QWidget,
)

if TYPE_CHECKING:
    from app.core.background_updater import BackgroundUpdater
    from app.core.feed_manager import FeedManager
    from app.utils.config import Config
    from app.theme.theme_manager import ThemeManager

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

        # Carregar feeds na sidebar e stats do dashboard
        self._sidebar.refresh_feeds()
        self._dashboard.load(self._fm)

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
        from app.ui.views.archive_view       import ArchiveView
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

        self._archive = ArchiveView(self._fm)
        self._stack.addWidget(self._archive)

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
            "archive":    self._archive,
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
        self._sidebar.refresh_requested.connect(self._updater.trigger_now)

        # Saved view
        self._saved.back_requested.connect(self._on_back)
        self._saved.article_clicked.connect(self._on_saved_article_clicked)

        # Archive view
        self._archive.back_requested.connect(self._on_back)

        # Stats view
        self._stats.back_requested.connect(self._on_back)

        # Feed list view (acesso direto a um feed específico)
        self._feed_list.back_requested.connect(self._on_back)
        self._feed_list.article_clicked.connect(self._on_article_clicked)
        self._feed_list.unread_changed.connect(self._sidebar.update_badge)

        # Unified feed view
        self._unified_feed.back_requested.connect(self._on_back)
        self._unified_feed.article_clicked.connect(self._on_unified_article_clicked)
        self._unified_feed.unread_changed.connect(self._sidebar.update_all_badges)

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
        elif widget is self._archive:
            self._archive.load()
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
        self._stack.setCurrentWidget(self._reader_source)

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

    def _on_update_error(self, feed_id: int, message: str) -> None:
        log.warning("Erro ao atualizar feed %d: %s", feed_id, message)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._updater.stop()
        super().closeEvent(event)
