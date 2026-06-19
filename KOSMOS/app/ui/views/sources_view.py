"""
sources_view.py — Gerência de fontes (feeds), design antigo sobre os feeds v3.

Lista as fontes existentes com status (categoria · última busca · erro), e permite
**pausar/retomar** (toggle `enabled` via `feeds_admin.update_feed`) e **excluir**
(`delete_feed`, com confirmação — apaga os artigos por cascade). Adicionar fontes
continua nas Configurações; aqui é a gestão das existentes.

Emite `feeds_changed` após pausar/excluir para o `main_window` recarregar a
sidebar/lista de artigos.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.database import get_conn
from app.core.feeds_admin import delete_feed, update_feed

log = logging.getLogger("kosmos.sources_view")

_SOURCES_QUERY = """
    SELECT id, url, title, category, enabled, last_fetched_at, last_error, error_count
      FROM feeds
     ORDER BY category COLLATE NOCASE, COALESCE(title, url) COLLATE NOCASE
"""


def _fmt_last(iso: str | None) -> str:
    if not iso:
        return "nunca buscado"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        if diff.days == 0:
            h = diff.seconds // 3600
            return f"há {h}h" if h else "agora há pouco"
        return f"há {diff.days}d"
    except Exception:
        return iso


def _font(family: str, fallback: str, size: int) -> QFont:
    f = QFont(family)
    if not f.exactMatch():
        f = QFont(fallback)
    f.setPointSize(size)
    return f


class _SourceRow(QWidget):
    """Linha de uma fonte: nome, meta (categoria · última busca · erro), pausar, excluir."""

    pause_toggled = Signal(int, bool)   # feed_id, new_enabled
    delete_requested = Signal(int)      # feed_id

    def __init__(self, feed: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sourceRow")
        self._feed_id = int(feed["id"])
        self._enabled = bool(feed["enabled"])
        self._build(feed)

    def _build(self, feed: dict) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._name_lbl = QLabel(feed["title"] or feed["url"])
        self._name_lbl.setObjectName("sourceName")
        self._name_lbl.setFont(_font("Special Elite", "Courier New", 12))
        info.addWidget(self._name_lbl)

        meta_parts = [feed.get("category") or "Sem categoria", _fmt_last(feed.get("last_fetched_at"))]
        if feed.get("last_error"):
            meta_parts.append("⚠ erro")
        self._meta_lbl = QLabel("  ·  ".join(meta_parts))
        self._meta_lbl.setObjectName("sourceMeta")
        self._meta_lbl.setProperty("class", "meta")
        if feed.get("last_error"):
            self._meta_lbl.setToolTip(str(feed["last_error"]))
        info.addWidget(self._meta_lbl)
        layout.addLayout(info, 1)

        self._pause_btn = QPushButton()
        self._pause_btn.setObjectName("sourcePauseBtn")
        self._pause_btn.setFixedWidth(90)
        self._pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pause_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._pause_btn)

        del_btn = QPushButton("Excluir")
        del_btn.setObjectName("sourceDeleteBtn")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._feed_id))
        layout.addWidget(del_btn)

        self._refresh_state()

    def _refresh_state(self) -> None:
        self._pause_btn.setText("Pausar" if self._enabled else "Retomar")
        self._name_lbl.setProperty("paused", not self._enabled)
        self._name_lbl.style().unpolish(self._name_lbl)
        self._name_lbl.style().polish(self._name_lbl)

    def _on_toggle(self) -> None:
        self._enabled = not self._enabled
        self._refresh_state()
        self.pause_toggled.emit(self._feed_id, self._enabled)


class SourcesView(QWidget):
    """Página de gestão de fontes (feeds): status, pausar/retomar, excluir."""

    feeds_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sourcesView")
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("sourcesHeader")
        header.setFixedHeight(52)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 0, 24, 0)
        title = QLabel("Fontes")
        title.setObjectName("sourcesTitle")
        title.setFont(_font("Special Elite", "Courier New", 16))
        hl.addWidget(title)
        hl.addStretch(1)
        self._count_lbl = QLabel("")
        self._count_lbl.setProperty("class", "meta")
        hl.addWidget(self._count_lbl)
        outer.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sourcesSep")
        outer.addWidget(sep)

        self._list = QListWidget()
        self._list.setObjectName("sourcesList")
        outer.addWidget(self._list, 1)

        self._placeholder = QLabel("Nenhuma fonte ainda.\nAdicione feeds nas Configurações.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        outer.addWidget(self._placeholder, 1)
        self._placeholder.hide()

    def load(self, conn: sqlite3.Connection | None = None) -> int:
        """Recarrega a lista de fontes."""
        _conn = conn if conn is not None else get_conn()
        should_close = conn is None
        rows = []
        try:
            rows = _conn.execute(_SOURCES_QUERY).fetchall()
        except sqlite3.Error as exc:
            log.error("SourcesView: falha ao carregar feeds: %s", exc)
        finally:
            if should_close:
                _conn.close()
        self._populate([dict(r) for r in rows])
        self._count_lbl.setText(f"{len(rows)} fonte(s)")
        log.debug("SourcesView: %d fonte(s).", len(rows))
        return len(rows)

    def feed_count(self) -> int:
        return self._list.count()

    def _populate(self, feeds: list[dict]) -> None:
        self._list.clear()
        if not feeds:
            self._list.hide()
            self._placeholder.show()
            return
        self._placeholder.hide()
        self._list.show()
        for feed in feeds:
            row = _SourceRow(feed)
            row.pause_toggled.connect(self._on_pause_toggled)
            row.delete_requested.connect(self._on_delete)
            item = QListWidgetItem(self._list)
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)

    def _on_pause_toggled(self, feed_id: int, enabled: bool) -> None:
        update_feed(feed_id, enabled=enabled)
        log.info("Fonte %d %s.", feed_id, "retomada" if enabled else "pausada")
        self.feeds_changed.emit()

    def _on_delete(self, feed_id: int) -> None:
        """Pede confirmação (exclui os artigos por cascade) antes de excluir."""
        resp = QMessageBox.question(
            self, "Excluir fonte",
            "Excluir esta fonte e todos os seus artigos? Esta ação não pode ser desfeita.",
        )
        if resp == QMessageBox.StandardButton.Yes:
            self._do_delete(feed_id)

    def _do_delete(self, feed_id: int) -> None:
        """Exclui de fato (separado da confirmação, testável)."""
        delete_feed(feed_id)
        log.info("Fonte %d excluída pela view de Fontes.", feed_id)
        self.load()
        self.feeds_changed.emit()
