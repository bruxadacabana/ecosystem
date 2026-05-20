"""
Mnemosyne — Pop-up de insight espontâneo.

QDialog frameless posicionado no canto inferior direito da tela.
Mostra um pensamento gerado pela Mnemosyne com botões de feedback.
Permanece visível até a usuária interagir (✓ / ✗ / ✎).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("mnemosyne.insight_popup")

_POPUP_MAX_WIDTH = 360
_MARGIN = 20


class InsightPopup(QDialog):
    """Pop-up de insight espontâneo no canto inferior direito da tela.

    Sinais:
        confirmed(memory_id) — usuária marcou como interessante
        dismissed(memory_id) — usuária dispensou
        replied(text)        — usuária quer continuar no notebook
    """

    confirmed = Signal(int)
    dismissed = Signal(int)
    replied = Signal(str)

    def __init__(
        self,
        text: str,
        memory_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.0)
        self._memory_id = memory_id
        self._text = text
        self._build(text)

    def _build(self, text: str) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget(self)
        card.setObjectName("insightCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(16, 14, 16, 12)
        card_lay.setSpacing(10)

        eyebrow = QLabel("✦  Mnemosyne", card)
        eyebrow.setObjectName("insightEyebrow")

        text_label = QLabel(text, card)
        text_label.setObjectName("insightText")
        text_label.setWordWrap(True)
        text_label.setMaximumWidth(_POPUP_MAX_WIDTH - 40)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setContentsMargins(0, 0, 0, 0)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        confirm_btn = QPushButton("✓", card)
        confirm_btn.setObjectName("insightBtnConfirm")
        confirm_btn.setToolTip("Interessante")
        confirm_btn.setFixedSize(28, 28)
        confirm_btn.clicked.connect(self._on_confirm)

        dismiss_btn = QPushButton("✗", card)
        dismiss_btn.setObjectName("insightBtnDismiss")
        dismiss_btn.setToolTip("Dispensar")
        dismiss_btn.setFixedSize(28, 28)
        dismiss_btn.clicked.connect(self._on_dismiss)

        reply_btn = QPushButton("✎", card)
        reply_btn.setObjectName("insightBtnReply")
        reply_btn.setToolTip("Continuar no notebook")
        reply_btn.setFixedSize(28, 28)
        reply_btn.clicked.connect(self._on_reply)

        btn_row.addWidget(spacer)
        btn_row.addWidget(confirm_btn)
        btn_row.addWidget(dismiss_btn)
        btn_row.addWidget(reply_btn)

        card_lay.addWidget(eyebrow)
        card_lay.addWidget(text_label)
        card_lay.addLayout(btn_row)
        outer.addWidget(card)

    def show_in_corner(self) -> None:
        """Posiciona no canto inferior direito da tela e exibe com fade-in."""
        self.adjustSize()
        screen = self.screen()
        if screen is None:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            x = geom.right() - self.width() - _MARGIN
            y = geom.bottom() - self.height() - _MARGIN
            self.move(x, y)
        self.show()
        self.raise_()
        self._fade_in()

    def _fade_in(self) -> None:
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(250)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _close_anim(self) -> None:
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(300)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.close)
        self._anim.start()

    def _on_confirm(self) -> None:
        self.confirmed.emit(self._memory_id)
        self._close_anim()

    def _on_dismiss(self) -> None:
        self.dismissed.emit(self._memory_id)
        self._close_anim()

    def _on_reply(self) -> None:
        self.replied.emit(self._text)
        self._close_anim()
