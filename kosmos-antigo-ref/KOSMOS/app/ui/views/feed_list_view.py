"""Lista de artigos de um feed."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from app.ui.widgets.article_card import ArticleCard

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager
    from app.core.models import Article, Feed

log = logging.getLogger("kosmos.ui.feed_list")


class FeedListView(QWidget):
    """View que exibe os artigos de um feed com header e cards.

    Sinais:
        article_clicked(article_id)        — artigo clicado para leitura.
        back_requested()                   — usuário quer voltar ao dashboard.
        unread_changed(feed_id, new_count) — não lidos do feed mudaram.
    """

    article_clicked      = pyqtSignal(int)
    back_requested       = pyqtSignal()
    unread_changed       = pyqtSignal(int, int)
    translation_requested = pyqtSignal(list)  # list[tuple[int, str, str | None]]

    def __init__(self, feed_manager: "FeedManager", config=None, parent=None) -> None:
        super().__init__(parent)
        self._fm         = feed_manager
        self._cfg        = config
        self._feed_id: int | None = None
        self._card_map:  dict[int, "ArticleCard"] = {}  # article_id → card
        self.setObjectName("feedListView")
        self._build_ui()

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Cabeçalho
        self._header = self._build_header()
        root.addWidget(self._header)

        # Linha divisória
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        root.addWidget(sep)

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

        # Botão voltar
        back_btn = QPushButton("←  Dashboard")
        back_btn.setObjectName("backButton")
        back_btn.setFlat(True)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_font = QFont("Courier Prime")
        if not btn_font.exactMatch():
            btn_font = QFont("Courier New")
        btn_font.setPointSize(11)
        back_btn.setFont(btn_font)
        back_btn.clicked.connect(self.back_requested.emit)
        layout.addWidget(back_btn)

        # Título do feed
        self._feed_title = QLabel("")
        self._feed_title.setObjectName("feedListTitle")
        title_font = QFont("Special Elite")
        if not title_font.exactMatch():
            title_font = QFont("Courier New")
        title_font.setPointSize(16)
        self._feed_title.setFont(title_font)
        layout.addWidget(self._feed_title, 1)

        # Botão marcar todos como lidos
        self._mark_all_btn = QPushButton("Marcar todos como lidos")
        self._mark_all_btn.setObjectName("markAllBtn")
        self._mark_all_btn.setFont(btn_font)
        self._mark_all_btn.clicked.connect(self._on_mark_all_read)
        layout.addWidget(self._mark_all_btn)

        return header

    # ------------------------------------------------------------------
    # Carregamento de dados
    # ------------------------------------------------------------------

    def get_article_ids(self) -> list[int]:
        """Retorna a lista de IDs dos artigos atualmente exibidos."""
        ids: list[int] = []
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), ArticleCard):
                ids.append(item.widget()._article_id)  # type: ignore
        return ids

    def get_article_index(self, article_id: int) -> int:
        """Retorna o índice do artigo na lista atual (-1 se não encontrado)."""
        return next(
            (i for i, aid in enumerate(self.get_article_ids()) if aid == article_id),
            -1,
        )

    def load_feed(self, feed: "Feed") -> None:
        """Carrega e exibe os artigos do feed fornecido."""
        self._feed_id = feed.id
        self._feed_title.setText(feed.name)

        articles = self._fm.get_articles(feed.id)
        self._populate_cards(articles)

    def refresh(self) -> None:
        """Recarrega os artigos do feed atual (após update em background)."""
        if self._feed_id is None:
            return
        feed = self._fm.get_feed(self._feed_id)
        if feed:
            self.load_feed(feed)

    # ------------------------------------------------------------------
    # Cards
    # ------------------------------------------------------------------

    def _populate_cards(self, articles: "list[Article]") -> None:
        # Remover cards anteriores (mas não o stretch no final)
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._card_map.clear()

        if not articles:
            empty = QLabel("Nenhum artigo encontrado.")
            empty.setObjectName("emptyLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 40, 0, 0)
            self._cards_layout.insertWidget(0, empty)
            return

        show_badge     = bool(self._cfg.get("ai_relevance_badge",  True)) if self._cfg else True
        show_sentiment = bool(self._cfg.get("ai_sentiment_border", True)) if self._cfg else True
        show_clickbait = bool(self._cfg.get("ai_clickbait_badge",  True)) if self._cfg else True
        tags_by_id = self._fm.get_tags_for_articles([a.id for a in articles])
        translation_items: list[tuple[int, str, "str | None"]] = []
        for article in articles:
            card = ArticleCard(
                article,
                ai_sentiment = article.ai_sentiment if show_sentiment else None,
                ai_clickbait = article.ai_clickbait if show_clickbait else None,
                ai_relevance = article.ai_relevance if show_badge     else None,
                user_tags    = tags_by_id.get(article.id, []),
            )
            card.clicked.connect(self._on_card_clicked)
            self._card_map[article.id] = card
            translation_items.append((article.id, article.title or "", getattr(article, "language", None)))

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setObjectName("cardSeparator")

            idx = self._cards_layout.count() - 1  # before stretch
            self._cards_layout.insertWidget(idx, card)
            self._cards_layout.insertWidget(idx + 1, sep)

        if translation_items:
            self.translation_requested.emit(translation_items)

    # ------------------------------------------------------------------
    # Acções
    # ------------------------------------------------------------------

    def _on_card_clicked(self, article_id: int) -> None:
        self._fm.mark_as_read(article_id)
        self._mark_card_read(article_id)
        self._emit_unread_count()
        self.article_clicked.emit(article_id)

    def _on_card_clicked_external(self, article_id: int) -> None:
        """Chamado pelo reader quando navega para um artigo (sem emitir signal)."""
        self._mark_card_read(article_id)
        self._emit_unread_count()

    def update_card_analysis(self, article_id: int, data: dict) -> None:
        """Atualiza badges do card em tempo real após análise em background."""
        card = self._card_map.get(article_id)
        if card is None:
            return
        show_badge     = bool(self._cfg.get("ai_relevance_badge",  True)) if self._cfg else True
        show_sentiment = bool(self._cfg.get("ai_sentiment_border", True)) if self._cfg else True
        show_clickbait = bool(self._cfg.get("ai_clickbait_badge",  True)) if self._cfg else True
        card.update_analysis(
            sentiment=data.get("sentiment") if show_sentiment else None,
            clickbait=data.get("clickbait") if show_clickbait else None,
            relevance=data.get("relevance") if show_badge     else None,
            tags=data.get("tags", []),
        )

    def update_card_title(self, article_id: int, translated: str) -> None:
        """Substitui o título do card com a versão traduzida."""
        card = self._card_map.get(article_id)
        if card is not None:
            card.update_title(translated)

    def _mark_card_read(self, article_id: int) -> None:
        """Atualiza o visual do card correspondente para 'lido'."""
        card = self._card_map.get(article_id)
        if card is not None:
            card.mark_read()

    def _on_mark_all_read(self) -> None:
        if self._feed_id is None:
            return
        self._fm.mark_feed_as_read(self._feed_id)
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), ArticleCard):
                item.widget().mark_read()  # type: ignore
        self._emit_unread_count()

    def _emit_unread_count(self) -> None:
        if self._feed_id is not None:
            count = self._fm.get_unread_count(self._feed_id)
            self.unread_changed.emit(self._feed_id, count)
