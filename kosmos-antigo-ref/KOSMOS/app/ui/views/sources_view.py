"""Vista de gerenciamento de fontes — lista, pausa e exclusão de feeds."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager
    from app.core.models import Feed

log = logging.getLogger("kosmos.ui.sources")

_TYPE_LABELS = {
    "rss":       "RSS",
    "youtube":   "YouTube",
    "reddit":    "Reddit",
    "tumblr":    "Tumblr",
    "substack":  "Substack",
    "mastodon":  "Mastodon",
}


def _fmt_last_fetched(dt: datetime | None) -> str:
    if dt is None:
        return "nunca atualizado"
    from app.utils.time_utils import time_ago
    return time_ago(dt) or dt.strftime("%d/%m %H:%M")


# ------------------------------------------------------------------
# Linha de feed
# ------------------------------------------------------------------

class _FeedRow(QWidget):
    """Uma linha na lista de fontes com controles de pausa e exclusão."""

    pause_toggled = pyqtSignal(int, bool)   # feed_id, new_active
    delete_requested = pyqtSignal(int)       # feed_id

    def __init__(self, feed: "Feed", parent=None) -> None:
        super().__init__(parent)
        self._feed_id = feed.id
        self._active  = bool(feed.active)
        self.setObjectName("sourceRow")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build(feed)

    def _build(self, feed: "Feed") -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        # Indicador de status (bolinha colorida)
        self._dot = QLabel()
        self._dot.setObjectName("sourceStatusDot")
        self._dot.setFixedSize(10, 10)
        layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        # Info central
        info = QVBoxLayout()
        info.setSpacing(2)
        info.setContentsMargins(0, 0, 0, 0)

        self._name_lbl = QLabel(feed.name)
        self._name_lbl.setObjectName("sourceName")
        self._name_lbl.setFont(self._serif(14))
        self._name_lbl.setWordWrap(False)
        info.addWidget(self._name_lbl)

        meta_parts = [
            _TYPE_LABELS.get(feed.feed_type, feed.feed_type.upper()),
            _fmt_last_fetched(feed.last_fetched),
        ]
        if feed.last_error:
            meta_parts.append("⚠ erro")
        meta = QLabel("  ·  ".join(meta_parts))
        meta.setObjectName("sourceMeta")
        meta.setFont(self._mono(10))
        info.addWidget(meta)

        layout.addLayout(info, 1)

        # Botão pausar/retomar
        self._pause_btn = QPushButton()
        self._pause_btn.setObjectName("sourcePauseBtn")
        self._pause_btn.setFont(self._mono(10))
        self._pause_btn.setFixedWidth(80)
        self._pause_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._pause_btn)

        # Botão excluir
        del_btn = QPushButton("Excluir")
        del_btn.setObjectName("sourceDeleteBtn")
        del_btn.setFont(self._mono(10))
        del_btn.setFixedWidth(70)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._feed_id))
        layout.addWidget(del_btn)

        self._refresh_state()

    # ------------------------------------------------------------------

    def _refresh_state(self) -> None:
        self._dot.setProperty("active", self._active)
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)
        if self._active:
            self._pause_btn.setText("Pausar")
            self._name_lbl.setProperty("paused", False)
        else:
            self._pause_btn.setText("Retomar")
            self._name_lbl.setProperty("paused", True)
        self._name_lbl.style().unpolish(self._name_lbl)
        self._name_lbl.style().polish(self._name_lbl)

    def set_active(self, active: bool) -> None:
        self._active = active
        self._refresh_state()

    def _on_toggle(self) -> None:
        self._active = not self._active
        self._refresh_state()
        self.pause_toggled.emit(self._feed_id, self._active)

    @staticmethod
    def _serif(size: int) -> QFont:
        f = QFont("IM Fell English")
        if not f.exactMatch():
            f = QFont("Georgia")
        f.setPointSize(size)
        f.setItalic(True)
        return f

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f


# ------------------------------------------------------------------
# Vista principal
# ------------------------------------------------------------------

class SourcesView(QWidget):
    """Vista de gerenciamento de fontes cadastradas.

    Sinais:
        feeds_changed()           — feed adicionado, removido ou pausado.
        back_requested()
    """

    feeds_changed  = pyqtSignal()
    back_requested = pyqtSignal()

    def __init__(self, feed_manager: "FeedManager", parent=None) -> None:
        super().__init__(parent)
        self._fm = feed_manager
        self.setObjectName("sourcesView")
        self._rows: dict[int, _FeedRow] = {}
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

        root.addWidget(self._build_toolbar())

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("listSeparator")
        root.addWidget(sep2)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._list_widget = QWidget()
        self._list_widget.setObjectName("sourcesContainer")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
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

        title = QLabel("Fontes")
        title.setObjectName("feedListTitle")
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(16)
        title.setFont(f)
        layout.addWidget(title, 1)

        return header

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("sourcesToolbar")
        bar.setFixedHeight(44)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        discover_btn = QPushButton("⊕  Descobrir novas fontes…")
        discover_btn.setObjectName("discoverBtn")
        discover_btn.setFont(self._mono(11))
        discover_btn.clicked.connect(self._on_discover)
        layout.addWidget(discover_btn)

        layout.addStretch()

        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("cardMeta")
        self._count_lbl.setFont(self._mono(10))
        layout.addWidget(self._count_lbl)

        return bar

    # ------------------------------------------------------------------
    # Carregamento
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Reconstrói a lista de feeds a partir do banco."""
        self._rows.clear()
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        feeds = self._fm.get_feeds()
        self._count_lbl.setText(f"{len(feeds)} fonte{'s' if len(feeds) != 1 else ''}")

        if not feeds:
            empty = QLabel("Nenhuma fonte cadastrada. Clique em Descobrir para adicionar.")
            empty.setObjectName("emptyLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 40, 0, 0)
            self._list_layout.insertWidget(0, empty)
            return

        for feed in feeds:
            self._add_row(feed)

    def _add_row(self, feed: "Feed") -> None:
        row = _FeedRow(feed)
        row.pause_toggled.connect(self._on_pause_toggled)
        row.delete_requested.connect(self._on_delete)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("cardSeparator")

        idx = self._list_layout.count() - 1
        self._list_layout.insertWidget(idx, row)
        self._list_layout.insertWidget(idx + 1, sep)
        self._rows[feed.id] = row

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_pause_toggled(self, feed_id: int, active: bool) -> None:
        try:
            self._fm.set_feed_active(feed_id, active)
            self.feeds_changed.emit()
        except Exception as exc:
            log.warning("Erro ao pausar feed %d: %s", feed_id, exc)
            # Reverter visual
            row = self._rows.get(feed_id)
            if row:
                row.set_active(not active)

    def _on_delete(self, feed_id: int) -> None:
        row = self._rows.get(feed_id)
        name = row._name_lbl.text() if row else f"feed {feed_id}"

        reply = QMessageBox.question(
            self,
            "Excluir fonte",
            f'Excluir "{name}" e todos os seus artigos?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._fm.delete_feed(feed_id)
            self.load()
            self.feeds_changed.emit()
        except Exception as exc:
            log.warning("Erro ao excluir feed %d: %s", feed_id, exc)
            QMessageBox.warning(self, "Erro", f"Não foi possível excluir:\n{exc}")

    def _on_discover(self) -> None:
        from app.ui.dialogs.discover_feeds_dialog import DiscoverFeedsDialog
        dlg = DiscoverFeedsDialog(self._fm, parent=self)
        dlg.exec()
        self.load()
        self.feeds_changed.emit()

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f
