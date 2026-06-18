"""Badge de contagem de não lidos — aparece ao lado do nome do feed."""

from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel


class UnreadBadge(QLabel):
    """Pill colorido com número de artigos não lidos.

    Fica oculto automaticamente quando a contagem chega a zero.
    """

    def __init__(self, count: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("unreadBadge")
        font = QFont("Courier Prime")
        if not font.exactMatch():
            font = QFont("Courier New")
        font.setPointSize(9)
        self.setFont(font)
        self.set_count(count)

    def set_count(self, count: int) -> None:
        self._count = max(0, count)
        if self._count > 0:
            text = str(self._count) if self._count < 1000 else "999+"
            self.setText(text)
            self.show()
        else:
            self.setText("")
            self.hide()

    @property
    def count(self) -> int:
        return self._count
