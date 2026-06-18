"""
saved_view.py — Lista de artigos salvos/arquivados (design antigo) sobre os dados v3.

No v3, `is_saved = 1` significa que o artigo foi **arquivado como `.md`** no ecossistema
(via `archiver.py`). Esta página lista esses artigos usando o card do design antigo
(reusado de `article_list.ArticleCard`) e abre o artigo no leitor ao clicar.

Unifica os antigos `saved_view`/`archive_view` — no v3 são o mesmo conceito (is_saved).
"""
from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.database import get_conn
from app.ui.views.article_list import ArticleCard

log = logging.getLogger("kosmos.saved_view")

_SAVED_QUERY = """
    SELECT a.id, a.title, a.title_translated, a.author, a.published_at,
           a.article_type, a.estimated_reading_min, a.is_read,
           a.language_detected, a.content_excerpt,
           a.ai_sentiment, a.ai_clickbait_score, a.ai_tags,
           COALESCE(f.title, f.url) AS feed_title
      FROM articles a JOIN feeds f ON f.id = a.feed_id
     WHERE a.is_saved = 1
     ORDER BY a.read_at DESC, a.published_at DESC
     LIMIT 300
"""


class SavedView(QWidget):
    """Página de artigos salvos/arquivados (is_saved=1)."""

    article_selected = Signal(int)  # article_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("savedView")
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("savedHeader")
        header.setFixedHeight(52)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 0, 24, 0)
        title = QLabel("Salvos")
        title.setObjectName("savedTitle")
        tf = QFont("Special Elite")
        if not tf.exactMatch():
            tf = QFont("Courier New")
        tf.setPointSize(16)
        title.setFont(tf)
        hl.addWidget(title)
        hl.addStretch(1)
        self._count_lbl = QLabel("")
        self._count_lbl.setProperty("class", "meta")
        hl.addWidget(self._count_lbl)
        outer.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("savedSep")
        outer.addWidget(sep)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_item_clicked)
        outer.addWidget(self._list, 1)

        self._placeholder = QLabel("Nenhum artigo salvo ainda.\nArquive um artigo pelo botão no leitor.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        outer.addWidget(self._placeholder, 1)
        self._placeholder.hide()

    def load(self, conn: sqlite3.Connection | None = None) -> int:
        """Recarrega a lista de artigos salvos (is_saved=1)."""
        _conn = conn if conn is not None else get_conn()
        should_close = conn is None
        rows = []
        try:
            rows = _conn.execute(_SAVED_QUERY).fetchall()
        except sqlite3.Error as exc:
            log.error("SavedView: falha ao carregar salvos: %s", exc)
        finally:
            if should_close:
                _conn.close()
        self._populate(rows)
        self._count_lbl.setText(f"{len(rows)} salvo(s)")
        log.debug("SavedView: %d artigo(s) salvos.", len(rows))
        return len(rows)

    def _populate(self, rows: list) -> None:
        self._list.clear()
        if not rows:
            self._list.hide()
            self._placeholder.show()
            return
        self._placeholder.hide()
        self._list.show()
        for row in rows:
            data = dict(row)
            card = ArticleCard(data, self._list)
            item = QListWidgetItem(self._list)
            item.setData(Qt.ItemDataRole.UserRole, data["id"])
            item.setSizeHint(card.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, card)

    def article_count(self) -> int:
        return self._list.count()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        article_id = item.data(Qt.ItemDataRole.UserRole)
        if article_id is not None:
            self.article_selected.emit(int(article_id))
