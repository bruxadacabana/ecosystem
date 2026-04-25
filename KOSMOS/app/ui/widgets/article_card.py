"""Card de artigo na feed_list_view."""

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from app.utils.time_utils import time_ago

if TYPE_CHECKING:
    from app.core.models import Article


def _strip_html(text: str) -> str:
    """Remove tags HTML e decodifica entidades."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, max_chars: int = 160) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


class ArticleCard(QWidget):
    """Widget de card para exibir um artigo numa lista.

    Sinais:
        clicked(article_id)    — card clicado.
        read_toggled(article_id, is_read)
    """

    clicked      = pyqtSignal(int)
    read_toggled = pyqtSignal(int, bool)

    def __init__(
        self,
        article:       "Article",
        feed_name:     str | None   = None,
        ai_relevance:  float | None = None,
        ai_sentiment:  float | None = None,
        ai_clickbait:  float | None = None,
        user_tags:     "list[str]"  = (),   # type: ignore[assignment]
        parent: "QWidget | None"    = None,
    ) -> None:
        super().__init__(parent)
        self._article_id   = article.id
        self._is_read      = bool(article.is_read)
        self._is_saved     = bool(article.is_saved)
        self._feed_name    = feed_name
        self._ai_relevance = ai_relevance
        self._ai_sentiment = ai_sentiment
        self._ai_clickbait = ai_clickbait
        self._user_tags    = list(user_tags)

        self.setObjectName("articleCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._build(article)
        self._apply_read_style()
        self._apply_sentiment_style()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build(self, article: "Article") -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        # Indicador de lido/não lido (bolinha à esquerda)
        self._dot = QLabel()
        self._dot.setObjectName("readDot")
        self._dot.setFixedSize(8, 8)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignVCenter)

        # Conteúdo principal
        content = QVBoxLayout()
        content.setSpacing(3)
        content.setContentsMargins(0, 0, 0, 0)

        # Título
        self._title_lbl = QLabel(_truncate(article.title, 120))
        self._title_lbl.setObjectName("cardTitle")
        self._title_lbl.setWordWrap(True)
        title_font = QFont("Special Elite")
        if not title_font.exactMatch():
            title_font = QFont("Courier New")
        title_font.setPointSize(13)
        self._title_lbl.setFont(title_font)
        content.addWidget(self._title_lbl)

        # Metadados (fonte · autor · tempo)
        meta_parts: list[str] = []
        if self._feed_name:
            meta_parts.append(self._feed_name)
        if article.author:
            meta_parts.append(article.author)
        meta_parts.append(time_ago(article.published_at) or "")
        meta_text = "  ·  ".join(p for p in meta_parts if p)

        self._meta_lbl = QLabel(meta_text)
        self._meta_lbl.setObjectName("cardMeta")
        meta_font = QFont("Courier Prime")
        if not meta_font.exactMatch():
            meta_font = QFont("Courier New")
        meta_font.setPointSize(10)
        self._meta_lbl.setFont(meta_font)
        content.addWidget(self._meta_lbl)

        # Tags aprovadas pelo usuário
        if self._user_tags:
            tag_font = QFont("Courier Prime")
            if not tag_font.exactMatch():
                tag_font = QFont("Courier New")
            tag_font.setPointSize(9)
            tags_row = QHBoxLayout()
            tags_row.setSpacing(4)
            tags_row.setContentsMargins(0, 2, 0, 0)
            for tag_name in self._user_tags[:6]:
                chip = QLabel(tag_name)
                chip.setObjectName("aiTagChip")
                chip.setFont(tag_font)
                tags_row.addWidget(chip)
            tags_row.addStretch()
            content.addLayout(tags_row)

        # Resumo (snippet do conteúdo)
        raw = article.summary or article.content_full or ""
        snippet = _truncate(_strip_html(raw), 180) if raw else ""
        if snippet:
            self._summary_lbl = QLabel(snippet)
            self._summary_lbl.setObjectName("cardSummary")
            self._summary_lbl.setWordWrap(True)
            sum_font = QFont("IM Fell English")
            if not sum_font.exactMatch():
                sum_font = QFont("Georgia")
            sum_font.setPointSize(12)
            self._summary_lbl.setFont(sum_font)
            content.addWidget(self._summary_lbl)

        outer.addLayout(content, 1)

        # Coluna direita: estrela de salvo + badge de relevância
        right_col = QVBoxLayout()
        right_col.setSpacing(2)
        right_col.setContentsMargins(0, 0, 0, 0)

        if self._is_saved:
            star = QLabel("★")
            star.setObjectName("savedStar")
            star.setFixedWidth(16)
            star.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            right_col.addWidget(star)

        if self._ai_relevance is not None and self._ai_relevance >= 0.65:
            badge = QLabel("◆")
            badge.setObjectName("relevanceBadge")
            badge.setFixedWidth(16)
            badge.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            pct = int(self._ai_relevance * 100)
            badge.setToolTip(f"Relevância estimada: {pct}%")
            right_col.addWidget(badge)

        if self._ai_clickbait is not None and self._ai_clickbait >= 0.6:
            warn = QLabel("⚠")
            warn.setObjectName("clickbaitBadge")
            warn.setFixedWidth(16)
            warn.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            warn.setToolTip(f"Clickbait: {int(self._ai_clickbait * 100)}%")
            right_col.addWidget(warn)

        right_col.addStretch()
        outer.addLayout(right_col, 0)

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def mark_read(self) -> None:
        self._is_read = True
        self._apply_read_style()

    def mark_unread(self) -> None:
        self._is_read = False
        self._apply_read_style()

    def _apply_read_style(self) -> None:
        if self._is_read:
            self._dot.setProperty("read", True)
        else:
            self._dot.setProperty("read", False)
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)

    def _apply_sentiment_style(self) -> None:
        if self._ai_sentiment is None:
            return
        if self._ai_sentiment >= 0.2:
            val = "positive"
        elif self._ai_sentiment <= -0.2:
            val = "negative"
        else:
            val = "neutral"
        self.setProperty("sentiment", val)
        self.style().unpolish(self)
        self.style().polish(self)

    # ------------------------------------------------------------------
    # Eventos de mouse
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._article_id)
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:
        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)
