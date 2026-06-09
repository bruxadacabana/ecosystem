"""
article_list.py — Painel central: lista de artigos em cards.

Cada card mostra título, feed de origem, data relativa, tipo e tempo de leitura.
Artigos não-lidos têm título em negrito. Artigos lidos ficam em tom mais suave.

Emite article_selected(int) quando a usuária clica num card (article_id).

Fase 2 — cards básicos: sem dados de análise AI (sentimento, tags, clickbait).
Esses campos chegam na Fase 4 (AnalysisWorker). A estrutura do card já prevê
slots para eles, mas não os exibe ainda.

O load_articles é sempre full-refresh, limitado a 200 artigos. Quando o
FetchWorker emite feed_done, on_feed_updated decide se recarga ou não.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.database import get_conn
from app.ui.views.feed_sidebar import ALL_FEEDS_ID

log = logging.getLogger("kosmos.article_list")

_MAX_ARTICLES = 200


def _fmt_date(iso: str | None) -> str:
    """Converte ISO8601 UTC para data relativa legível (agora / Xh / Xd / dd/mm)."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        if diff.days == 0:
            hours = diff.seconds // 3600
            return f"{hours}h atrás" if hours else "agora"
        if diff.days < 7:
            return f"{diff.days}d atrás"
        return dt.strftime("%d/%m")
    except Exception:
        return ""


class ArticleCard(QFrame):
    """Widget de card para um artigo. Exibido dentro de ArticleList."""

    def __init__(self, data: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("article_card")
        self._article_id: int = data["id"]
        self._setup_ui(data)

    def _setup_ui(self, data: dict) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)

        # Título — prefere a tradução (no idioma da usuária) quando disponível;
        # negrito se não-lido.
        title_lbl = QLabel(data.get("title_translated") or data.get("title") or "(sem título)")
        title_lbl.setWordWrap(True)
        title_lbl.setObjectName("card_title")
        if not data.get("is_read"):
            font = title_lbl.font()
            font.setBold(True)
            title_lbl.setFont(font)
        layout.addWidget(title_lbl)
        self._title_lbl = title_lbl

        # Linha de metadados: feed · data · tipo · tempo leitura
        meta_parts: list[str] = []
        if data.get("feed_title"):
            meta_parts.append(data["feed_title"])
        date_str = _fmt_date(data.get("published_at"))
        if date_str:
            meta_parts.append(date_str)
        art_type = data.get("article_type") or "news"
        if art_type != "news":
            meta_parts.append(art_type.upper())
        reading = data.get("estimated_reading_min")
        if reading:
            meta_parts.append(f"{reading} min")

        meta_lbl = QLabel(" · ".join(meta_parts))
        meta_lbl.setProperty("class", "meta")
        meta_lbl.setObjectName("card_meta")
        layout.addWidget(meta_lbl)

    @property
    def article_id(self) -> int:
        return self._article_id

    def set_title(self, text: str) -> None:
        """Atualiza o texto do título (usado ao receber a tradução ao vivo)."""
        if text:
            self._title_lbl.setText(text)


class ArticleList(QWidget):
    """Painel central: lista de cards de artigos para o feed selecionado."""

    article_selected = Signal(int)  # article_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_feed_id: int = ALL_FEEDS_ID
        self._setup_ui()
        log.debug("ArticleList inicializada.")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setSpacing(0)
        self._list.setUniformItemSizes(False)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

        self._placeholder = QLabel("Selecione um feed para ver os artigos.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        layout.addWidget(self._placeholder)
        self._placeholder.hide()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load_articles(
        self,
        feed_id: int = ALL_FEEDS_ID,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """Carrega (ou recarrega) artigos para o feed dado.

        Args:
            feed_id: feed_id ou ALL_FEEDS_ID (-1) para todos.
            conn:    conexão existente (testes); None → cria e fecha própria.

        Returns:
            Número de artigos carregados.
        """
        self._current_feed_id = feed_id
        _conn = conn if conn is not None else get_conn()
        should_close = conn is None
        rows = []
        try:
            if feed_id == ALL_FEEDS_ID:
                rows = _conn.execute(
                    """
                    SELECT a.id, a.title, a.title_translated, a.published_at, a.article_type,
                           a.estimated_reading_min, a.is_read,
                           COALESCE(f.title, f.url) AS feed_title
                      FROM articles a
                      JOIN feeds f ON f.id = a.feed_id
                     ORDER BY a.published_at DESC, a.created_at DESC
                     LIMIT ?
                    """,
                    (_MAX_ARTICLES,),
                ).fetchall()
            else:
                rows = _conn.execute(
                    """
                    SELECT a.id, a.title, a.title_translated, a.published_at, a.article_type,
                           a.estimated_reading_min, a.is_read,
                           COALESCE(f.title, f.url) AS feed_title
                      FROM articles a
                      JOIN feeds f ON f.id = a.feed_id
                     WHERE a.feed_id = ?
                     ORDER BY a.published_at DESC, a.created_at DESC
                     LIMIT ?
                    """,
                    (feed_id, _MAX_ARTICLES),
                ).fetchall()
        except sqlite3.Error as exc:
            log.error("Falha ao carregar artigos (feed_id=%s): %s", feed_id, exc)
        finally:
            if should_close:
                _conn.close()

        self._populate(rows)
        log.info("ArticleList: %d artigo(s) para feed_id=%s.", len(rows), feed_id)
        return len(rows)

    def on_feed_updated(self, feed_id: int, new_count: int) -> None:
        """Chamado pelo FetchWorker (via MainWindow) quando um feed tem novos artigos.

        Recarrega a lista apenas se o feed atualizado é o que está sendo exibido
        (ou se o modo "todos" está ativo).
        """
        if self._current_feed_id in (feed_id, ALL_FEEDS_ID):
            log.debug("Feed %d atualizado (%d novos) — recarregando lista.", feed_id, new_count)
            self.load_articles(self._current_feed_id)

    def on_title_translated(self, article_id: int, translated_title: str) -> None:
        """Slot: TranslationWorker traduziu um título — atualiza o card ao vivo."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == article_id:
                card = self._list.itemWidget(item)
                if card is not None:
                    card.set_title(translated_title)
                break

    def article_count(self) -> int:
        """Retorna o número de itens atualmente na lista."""
        return self._list.count()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

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

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        article_id = item.data(Qt.ItemDataRole.UserRole)
        if article_id is not None:
            log.debug("Artigo selecionado: id=%d", article_id)
            self.article_selected.emit(article_id)
