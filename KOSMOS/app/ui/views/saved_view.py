"""View de artigos salvos/favoritados."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.ui.widgets.article_card import ArticleCard

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager

log = logging.getLogger("kosmos.ui.saved")


class SavedView(QWidget):
    """View de artigos marcados como salvos.

    Sinais:
        article_clicked(article_id) — artigo clicado para leitura.
        back_requested()            — voltar ao dashboard.
    """

    article_clicked = pyqtSignal(int)
    back_requested  = pyqtSignal()

    def __init__(self, feed_manager: "FeedManager", parent=None) -> None:
        super().__init__(parent)
        self._fm = feed_manager
        self._feeds: dict[int, str] = {}
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

        root.addWidget(self._build_search_bar())

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("listSeparator")
        root.addWidget(sep2)

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

        title = QLabel("Salvos")
        title.setObjectName("feedListTitle")
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(16)
        title.setFont(f)
        layout.addWidget(title, 1)

        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("cardMeta")
        self._count_lbl.setFont(self._mono(10))
        layout.addWidget(self._count_lbl)

        return header

    def _build_search_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 6, 16, 6)

        self._search_edit = QLineEdit()
        self._search_edit.setFont(self._mono(11))
        self._search_edit.setPlaceholderText("Buscar nos salvos…")
        self._search_edit.textChanged.connect(lambda: self._search_timer.start(300))
        layout.addWidget(self._search_edit)

        return bar

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Recarrega feeds e artigos — chamar ao entrar na view."""
        self._feeds = {f.id: f.name for f in self._fm.get_feeds()}
        self._load_articles()

    def refresh(self) -> None:
        """Recarrega artigos sem resetar a busca."""
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

    def mark_card_unsaved(self, article_id: int) -> None:
        """Remove o card do artigo que foi dessalvo."""
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and isinstance(item.widget(), ArticleCard):
                card: ArticleCard = item.widget()  # type: ignore
                if card._article_id == article_id:
                    card.deleteLater()
                    # Remover também o separador logo após
                    sep_item = self._cards_layout.itemAt(i + 1)
                    if sep_item and sep_item.widget():
                        sep_item.widget().deleteLater()
                    break
        self._update_count()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _load_articles(self) -> None:
        search = self._search_edit.text().strip().lower()
        articles = self._fm.get_saved_articles()
        if search:
            articles = [
                a for a in articles
                if search in (a.title or "").lower()
                or search in (a.summary or "").lower()
            ]
        self._populate_cards(articles)

    def _populate_cards(self, articles) -> None:
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not articles:
            empty = QLabel("Nenhum artigo salvo.")
            empty.setObjectName("emptyLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 40, 0, 0)
            self._cards_layout.insertWidget(0, empty)
            self._count_lbl.setText("")
            return

        for article in articles:
            feed_name = self._feeds.get(article.feed_id)
            card = ArticleCard(article, feed_name=feed_name)
            card.clicked.connect(self._on_card_clicked)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setObjectName("cardSeparator")

            idx = self._cards_layout.count() - 1
            self._cards_layout.insertWidget(idx, card)
            self._cards_layout.insertWidget(idx + 1, sep)

        self._update_count()

    def _update_count(self) -> None:
        ids = self.get_article_ids()
        self._count_lbl.setText(f"{len(ids)} artigo(s)" if ids else "")

    def _on_card_clicked(self, article_id: int) -> None:
        self.article_clicked.emit(article_id)

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f
