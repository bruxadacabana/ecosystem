"""Item de feed na sidebar — nome + badge de não lidos."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget,
)

from app.ui.widgets.unread_badge import UnreadBadge


class FeedItem(QWidget):
    """Widget de um feed na sidebar.

    Sinais:
        clicked(feed_id)
        context_requested(feed_id, global_pos)
    """

    clicked           = pyqtSignal(int)
    context_requested = pyqtSignal(int, object)

    def __init__(self, feed_id: int, name: str, unread: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._feed_id = feed_id
        self._active  = False

        self.setObjectName("feedItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 8, 0)
        layout.setSpacing(4)

        # Nome do feed
        self._name_lbl = QLabel(name)
        self._name_lbl.setObjectName("feedItemName")
        font = QFont("Courier Prime")
        if not font.exactMatch():
            font = QFont("Courier New")
        font.setPointSize(12)
        self._name_lbl.setFont(font)
        self._name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._name_lbl.setMaximumWidth(160)
        layout.addWidget(self._name_lbl)

        # Badge de não lidos
        self._badge = UnreadBadge(unread)
        layout.addWidget(self._badge)

    # ------------------------------------------------------------------
    # Atualização
    # ------------------------------------------------------------------

    def set_unread(self, count: int) -> None:
        self._badge.set_count(count)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._feed_id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        self.context_requested.emit(self._feed_id, event.globalPos())

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
