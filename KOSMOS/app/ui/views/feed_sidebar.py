"""
feed_sidebar.py — Painel esquerdo: feeds agrupados por categoria com contagem de não-lidos.

Emite feed_selected(int) quando a usuária clica em um feed:
  - valor -1 → "Todos os feeds"
  - valor >= 1 → feed_id específico

Clicar numa categoria (nó-pai) não emite sinal — apenas os feeds filhos.
A recarga (load_feeds) é sempre full-refresh: simples e correto para N pequeno
de feeds (dezenas, não milhares).
"""
from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.database import get_conn

log = logging.getLogger("kosmos.feed_sidebar")

ALL_FEEDS_ID = -1  # sentinel para "todos os feeds"


class FeedSidebar(QWidget):
    """Painel lateral: árvore de feeds por categoria, com contadores de não-lidos."""

    feed_selected = Signal(int)  # feed_id ou ALL_FEEDS_ID
    export_highlights_requested = Signal(int)  # feed_id — exportar destaques do feed (menu de contexto)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        self._setup_ui()
        log.debug("FeedSidebar inicializada.")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("FEEDS")
        header.setObjectName("sidebar_header")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFixedHeight(36)
        layout.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.setIndentation(16)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._tree)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load_feeds(self, conn: sqlite3.Connection | None = None) -> None:
        """Carrega todos os feeds habilitados do banco e reconstrói a árvore.

        A árvore é sempre reconstruída do zero — correto para N ≤ centenas
        de feeds. Preserva expansão de categorias.
        """
        _conn = conn if conn is not None else get_conn()
        should_close = conn is None
        rows = []
        try:
            rows = _conn.execute(
                """
                SELECT f.id,
                       COALESCE(f.title, f.url)                        AS title,
                       f.category,
                       COUNT(CASE WHEN a.is_read = 0 THEN 1 END)       AS unread
                  FROM feeds f
                  LEFT JOIN articles a ON a.feed_id = f.id
                 WHERE f.enabled = 1
                 GROUP BY f.id
                 ORDER BY f.category, title COLLATE NOCASE
                """
            ).fetchall()
        except sqlite3.Error as exc:
            log.error("Falha ao carregar feeds: %s", exc)
        finally:
            if should_close:
                _conn.close()

        self._rebuild_tree(rows)
        log.info("FeedSidebar: %d feed(s) carregado(s).", len(rows))

    def update_unread_count(self, feed_id: int, delta: int = 0) -> None:
        """Recarrega a árvore após novos artigos de um feed chegarem."""
        self.load_feeds()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _rebuild_tree(self, rows: list) -> None:
        self._tree.clear()

        # "Todos os feeds" — sempre presente no topo
        all_item = QTreeWidgetItem(self._tree, ["Todos os feeds"])
        all_item.setData(0, Qt.ItemDataRole.UserRole, ALL_FEEDS_ID)
        _bold(all_item)

        if not rows:
            hint = QTreeWidgetItem(self._tree, ["Adicione feeds no botão ⚙ Configurações"])
            hint.setData(0, Qt.ItemDataRole.UserRole, None)
            hint.setDisabled(True)
            return

        categories: dict[str, QTreeWidgetItem] = {}
        for row in rows:
            cat = row["category"] or "Sem categoria"
            if cat not in categories:
                cat_item = QTreeWidgetItem(self._tree, [cat])
                cat_item.setData(0, Qt.ItemDataRole.UserRole, None)
                cat_item.setExpanded(True)
                _bold(cat_item)
                categories[cat] = cat_item

            unread = row["unread"] or 0
            label = row["title"]
            if unread:
                label = f"{label}  ({unread})"

            feed_item = QTreeWidgetItem(categories[cat], [label])
            feed_item.setData(0, Qt.ItemDataRole.UserRole, row["id"])
            if unread:
                _bold(feed_item)

        self._tree.expandAll()

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        feed_id = item.data(0, Qt.ItemDataRole.UserRole)
        if feed_id is None:
            return  # clique em categoria — ignora
        log.debug("Feed selecionado: id=%s", feed_id)
        self.feed_selected.emit(feed_id)

    def _on_context_menu(self, pos) -> None:
        """Menu de contexto num feed: 'Exportar destaques deste feed' → emite o sinal."""
        item = self._tree.itemAt(pos)
        if item is None:
            return
        feed_id = item.data(0, Qt.ItemDataRole.UserRole)
        if feed_id is None or feed_id == ALL_FEEDS_ID:
            return  # categoria ou "Todos" — sem exportação por feed
        menu = QMenu(self)
        act = menu.addAction("Exportar destaques deste feed…")
        if menu.exec(self._tree.viewport().mapToGlobal(pos)) is act:
            self._request_export_highlights(item)

    def _request_export_highlights(self, item: QTreeWidgetItem) -> None:
        """Resolve o feed_id do item e emite o sinal (separado do exec, testável)."""
        feed_id = item.data(0, Qt.ItemDataRole.UserRole)
        if feed_id is not None and feed_id != ALL_FEEDS_ID:
            self.export_highlights_requested.emit(int(feed_id))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _bold(item: QTreeWidgetItem) -> None:
    font = item.font(0)
    font.setBold(True)
    item.setFont(0, font)
