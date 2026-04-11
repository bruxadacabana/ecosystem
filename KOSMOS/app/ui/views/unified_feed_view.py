"""Vista unificada de feeds — exibe artigos de todas as fontes com filtros."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from app.ui.widgets.article_card import ArticleCard

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager
    from app.core.models import Article
    from app.utils.config import Config

log = logging.getLogger("kosmos.ui.unified_feed")


class UnifiedFeedView(QWidget):
    """View unificada com artigos de todos os feeds e barra de filtros.

    Sinais:
        article_clicked(article_id)   — artigo clicado para leitura.
        back_requested()              — voltar ao dashboard.
        unread_changed()              — contagem de não lidos mudou.
    """

    article_clicked = pyqtSignal(int)
    back_requested  = pyqtSignal()
    unread_changed  = pyqtSignal()

    def __init__(self, feed_manager: "FeedManager", config: "Config", parent=None) -> None:
        super().__init__(parent)
        self._fm     = feed_manager
        self._cfg    = config
        self._feeds: dict[int, str] = {}   # feed_id → feed_name
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._load_articles)
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

        root.addWidget(self._build_filter_bar())

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("listSeparator")
        root.addWidget(sep2)

        # Área rolável de cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._cards_widget = QWidget()
        self._cards_widget.setObjectName("cardsContainer")
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(0)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._cards_widget)
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

        title = QLabel("Feeds")
        title.setObjectName("feedListTitle")
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(16)
        title.setFont(f)
        layout.addWidget(title, 1)

        self._mark_all_btn = QPushButton("Marcar todos como lidos")
        self._mark_all_btn.setObjectName("markAllBtn")
        self._mark_all_btn.setFont(self._mono(11))
        self._mark_all_btn.clicked.connect(self._on_mark_all_read)
        layout.addWidget(self._mark_all_btn)

        return header

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("filterBar")

        root = QVBoxLayout(bar)
        root.setContentsMargins(16, 6, 16, 6)
        root.setSpacing(6)

        mono = self._mono(11)
        _exp = QSizePolicy.Policy.Expanding
        _fix = QSizePolicy.Policy.Fixed

        # Linha 1: Fonte · Categoria · Busca
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        row1.addWidget(QLabel("Fonte:", font=mono))
        self._source_combo = QComboBox()
        self._source_combo.setFont(mono)
        self._source_combo.setMinimumWidth(100)
        self._source_combo.setSizePolicy(_exp, _fix)
        self._source_combo.currentIndexChanged.connect(self._on_filter_changed)
        row1.addWidget(self._source_combo, 2)

        row1.addWidget(QLabel("Categoria:", font=mono))
        self._cat_combo = QComboBox()
        self._cat_combo.setFont(mono)
        self._cat_combo.setMinimumWidth(90)
        self._cat_combo.setSizePolicy(_exp, _fix)
        self._cat_combo.currentIndexChanged.connect(self._on_filter_changed)
        row1.addWidget(self._cat_combo, 2)

        self._search_edit = QLineEdit()
        self._search_edit.setFont(mono)
        self._search_edit.setPlaceholderText("Buscar…")
        self._search_edit.setMinimumWidth(100)
        self._search_edit.setSizePolicy(_exp, _fix)
        self._search_edit.textChanged.connect(self._on_search_changed)
        row1.addWidget(self._search_edit, 3)

        root.addLayout(row1)

        # Linha 2: Idioma · checkboxes
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        row2.addWidget(QLabel("Idioma:", font=mono))
        self._lang_combo = QComboBox()
        self._lang_combo.setFont(mono)
        self._lang_combo.setMinimumWidth(90)
        self._lang_combo.setSizePolicy(_exp, _fix)
        self._lang_combo.currentIndexChanged.connect(self._on_filter_changed)
        row2.addWidget(self._lang_combo, 2)

        row2.addStretch(3)

        self._unread_check = QCheckBox("Não lidos")
        self._unread_check.setFont(mono)
        self._unread_check.stateChanged.connect(self._on_filter_changed)
        row2.addWidget(self._unread_check)

        row2.addSpacing(10)

        self._dedup_check = QCheckBox("Ocultar duplicatas")
        self._dedup_check.setFont(mono)
        self._dedup_check.setChecked(True)
        self._dedup_check.stateChanged.connect(self._on_filter_changed)
        row2.addWidget(self._dedup_check)

        root.addLayout(row2)

        return bar

    # ------------------------------------------------------------------
    # Carregamento de dados públicos
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Recarrega combos (feeds/categorias) e artigos — chamar ao entrar na view."""
        self._rebuild_combos()
        self._load_articles()

    def refresh(self) -> None:
        """Recarrega artigos sem resetar os filtros."""
        self._load_articles()

    def get_article_ids(self) -> list[int]:
        ids: list[int] = []
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), ArticleCard):
                ids.append(item.widget()._article_id)  # type: ignore
        return ids

    def get_article_index(self, article_id: int) -> int:
        return next(
            (i for i, aid in enumerate(self.get_article_ids()) if aid == article_id),
            -1,
        )

    def mark_card_read(self, article_id: int) -> None:
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), ArticleCard):
                card: ArticleCard = item.widget()  # type: ignore
                if card._article_id == article_id:
                    card.mark_read()
                    break

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _rebuild_combos(self) -> None:
        feeds      = self._fm.get_feeds()
        categories = self._fm.get_categories()
        languages  = self._fm.get_distinct_languages()

        self._feeds = {f.id: f.name for f in feeds}

        # Source combo
        self._source_combo.blockSignals(True)
        prev_feed = self._source_combo.currentData()
        self._source_combo.clear()
        self._source_combo.addItem("Todos os feeds", None)
        for feed in feeds:
            self._source_combo.addItem(feed.name, feed.id)
        if prev_feed is not None:
            for i in range(self._source_combo.count()):
                if self._source_combo.itemData(i) == prev_feed:
                    self._source_combo.setCurrentIndex(i)
                    break
        self._source_combo.blockSignals(False)

        # Category combo
        self._cat_combo.blockSignals(True)
        prev_cat = self._cat_combo.currentData()
        self._cat_combo.clear()
        self._cat_combo.addItem("Todas as categorias", None)
        for cat in categories:
            self._cat_combo.addItem(cat.name, cat.id)
        if prev_cat is not None:
            for i in range(self._cat_combo.count()):
                if self._cat_combo.itemData(i) == prev_cat:
                    self._cat_combo.setCurrentIndex(i)
                    break
        self._cat_combo.blockSignals(False)

        # Language combo
        self._lang_combo.blockSignals(True)
        prev_lang = self._lang_combo.currentData()
        self._lang_combo.clear()
        self._lang_combo.addItem("Todos os idiomas", None)
        from app.core.translator import LANGUAGE_NAMES
        for code in languages:
            label = LANGUAGE_NAMES.get(code, code.upper())
            self._lang_combo.addItem(label, code)
        if prev_lang is not None:
            for i in range(self._lang_combo.count()):
                if self._lang_combo.itemData(i) == prev_lang:
                    self._lang_combo.setCurrentIndex(i)
                    break
        self._lang_combo.blockSignals(False)

    def _load_articles(self) -> None:
        feed_id    = self._source_combo.currentData()
        cat_id     = self._cat_combo.currentData()
        search     = self._search_edit.text()
        unread_only = self._unread_check.isChecked()

        feed_ids     = [feed_id] if feed_id is not None else None
        category_ids = [cat_id]  if cat_id  is not None else None
        language     = self._lang_combo.currentData()

        date_from        = self._get_date_limit()
        blocked_keywords = self._cfg.get("keyword_blocklist", [])
        hide_duplicates  = self._dedup_check.isChecked()

        articles = self._fm.get_articles_filtered(
            feed_ids=feed_ids,
            category_ids=category_ids,
            search=search if search.strip() else None,
            unread_only=unread_only,
            date_from=date_from,
            blocked_keywords=blocked_keywords if blocked_keywords else None,
            hide_duplicates=hide_duplicates,
            language=language,
        )
        self._populate_cards(articles)

    def _get_date_limit(self) -> datetime | None:
        days = self._cfg.get("dev_article_age_days", 0)
        if days and days > 0:
            return datetime.utcnow() - timedelta(days=days)
        return None

    def _populate_cards(self, articles: list["Article"]) -> None:
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not articles:
            empty = QLabel("Nenhum artigo encontrado.")
            empty.setObjectName("emptyLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 40, 0, 0)
            self._cards_layout.insertWidget(0, empty)
            return

        show_badge      = bool(self._cfg.get("ai_relevance_badge",   False))
        show_sentiment  = bool(self._cfg.get("ai_sentiment_border",  False))
        show_clickbait  = bool(self._cfg.get("ai_clickbait_badge",   False))
        for article in articles:
            feed_name = self._feeds.get(article.feed_id)
            relevance = article.ai_relevance if show_badge     else None
            sentiment = article.ai_sentiment  if show_sentiment else None
            clickbait = article.ai_clickbait  if show_clickbait else None
            card = ArticleCard(
                article,
                feed_name    = feed_name,
                ai_relevance = relevance,
                ai_sentiment = sentiment,
                ai_clickbait = clickbait,
            )
            card.clicked.connect(self._on_card_clicked)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setObjectName("cardSeparator")

            idx = self._cards_layout.count() - 1
            self._cards_layout.insertWidget(idx, card)
            self._cards_layout.insertWidget(idx + 1, sep)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_filter_changed(self) -> None:
        self._load_articles()

    def _on_search_changed(self) -> None:
        self._search_timer.start(350)

    def _on_card_clicked(self, article_id: int) -> None:
        self._fm.mark_as_read(article_id)
        self.mark_card_read(article_id)
        self.unread_changed.emit()
        self.article_clicked.emit(article_id)

    def _on_mark_all_read(self) -> None:
        ids = self.get_article_ids()
        self._fm.mark_articles_as_read(ids)
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), ArticleCard):
                item.widget().mark_read()  # type: ignore
        self.unread_changed.emit()

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
