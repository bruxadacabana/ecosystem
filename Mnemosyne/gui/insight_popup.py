"""
Mnemosyne — Pop-up de insight espontâneo.

QDialog frameless posicionado no canto inferior direito da tela.
Mostra um pensamento gerado pela Mnemosyne com botões de feedback.
Permanece visível até a usuária interagir (✓ / ✗ / ✎).

Quando importance ≥ 7 e a usuária dispensa (✗), o popup transforma seu
conteúdo num painel de motivo: exibe o texto original acima e oferece
opções rápidas + campo livre. O sinal dismissed_with_reason é emitido
com o motivo coletado antes de fechar.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("mnemosyne.insight_popup")

_POPUP_MAX_WIDTH = 380
_MARGIN = 20

_DISMISS_REASONS = ["já sabia disso", "irrelevante agora", "incorreto", "outro"]


class InsightPopup(QDialog):
    """Pop-up de insight espontâneo no canto inferior direito da tela.

    Sinais:
        confirmed(memory_id)              — usuária marcou como interessante
        dismissed(memory_id)              — usuária dispensou (importance < 7)
        dismissed_with_reason(memory_id, reason) — dispensou com motivo (importance ≥ 7)
        replied(text)                     — usuária quer continuar no notebook
    """

    confirmed             = Signal(int)
    dismissed             = Signal(int)
    dismissed_with_reason = Signal(int, str)
    replied               = Signal(str)

    def __init__(
        self,
        text: str,
        memory_id: int,
        importance: int | None = None,
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
        self._importance = importance or 0
        self._build(text)

    def _build(self, text: str) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget(self)
        self._card.setObjectName("insightCard")
        self._card_lay = QVBoxLayout(self._card)
        self._card_lay.setContentsMargins(16, 14, 16, 12)
        self._card_lay.setSpacing(10)

        eyebrow = QLabel("✦  Mnemosyne", self._card)
        eyebrow.setObjectName("insightEyebrow")

        text_label = QLabel(text, self._card)
        text_label.setObjectName("insightText")
        text_label.setWordWrap(True)
        text_label.setMaximumWidth(_POPUP_MAX_WIDTH - 40)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setContentsMargins(0, 0, 0, 0)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        confirm_btn = QPushButton("✓", self._card)
        confirm_btn.setObjectName("insightBtnConfirm")
        confirm_btn.setToolTip("Interessante")
        confirm_btn.setFixedSize(28, 28)
        confirm_btn.clicked.connect(self._on_confirm)

        dismiss_btn = QPushButton("✗", self._card)
        dismiss_btn.setObjectName("insightBtnDismiss")
        dismiss_btn.setToolTip("Dispensar")
        dismiss_btn.setFixedSize(28, 28)
        dismiss_btn.clicked.connect(self._on_dismiss)

        reply_btn = QPushButton("✎", self._card)
        reply_btn.setObjectName("insightBtnReply")
        reply_btn.setToolTip("Continuar no notebook")
        reply_btn.setFixedSize(28, 28)
        reply_btn.clicked.connect(self._on_reply)

        btn_row.addWidget(spacer)
        btn_row.addWidget(confirm_btn)
        btn_row.addWidget(dismiss_btn)
        btn_row.addWidget(reply_btn)

        self._card_lay.addWidget(eyebrow)
        self._card_lay.addWidget(text_label)
        self._card_lay.addLayout(btn_row)
        outer.addWidget(self._card)

    def _clear_card(self) -> None:
        """Remove todos os widgets do card para substituir pelo painel de motivo."""
        while self._card_lay.count():
            item = self._card_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Limpa layouts aninhados
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

    def _show_reason_panel(self) -> None:
        """Substitui o conteúdo do card pelo painel de motivo de dismiss."""
        self._clear_card()

        # Texto original em caixa cinza
        original_box = QLabel(self._text, self._card)
        original_box.setObjectName("insightOriginalText")
        original_box.setWordWrap(True)
        original_box.setMaximumWidth(_POPUP_MAX_WIDTH - 40)

        question_lbl = QLabel("o que estava errado?", self._card)
        question_lbl.setObjectName("insightReasonQuestion")

        # Botões de opção rápida
        reason_row = QHBoxLayout()
        reason_row.setSpacing(4)
        reason_row.setContentsMargins(0, 0, 0, 0)
        self._selected_reason: str = _DISMISS_REASONS[0]

        def _make_reason_btn(label: str) -> QPushButton:
            btn = QPushButton(label, self._card)
            btn.setObjectName("insightReasonBtn")
            btn.setCheckable(True)
            btn.setChecked(label == self._selected_reason)
            btn.clicked.connect(lambda checked, l=label: self._select_reason(l))
            return btn

        self._reason_btns: list[QPushButton] = []
        for r in _DISMISS_REASONS:
            b = _make_reason_btn(r)
            self._reason_btns.append(b)
            reason_row.addWidget(b)

        # Campo de detalhe opcional
        self._detail_edit = QLineEdit(self._card)
        self._detail_edit.setPlaceholderText("detalhe opcional…")
        self._detail_edit.setObjectName("insightReasonDetail")

        # Botão confirmar motivo
        confirm_reason_btn = QPushButton("confirmar", self._card)
        confirm_reason_btn.setObjectName("insightBtnConfirm")
        confirm_reason_btn.clicked.connect(self._on_reason_confirmed)

        self._card_lay.addWidget(original_box)
        self._card_lay.addWidget(question_lbl)
        self._card_lay.addLayout(reason_row)
        self._card_lay.addWidget(self._detail_edit)
        self._card_lay.addWidget(confirm_reason_btn)

        self.adjustSize()
        self._reposition()

    def _select_reason(self, reason: str) -> None:
        self._selected_reason = reason
        for btn in self._reason_btns:
            btn.setChecked(btn.text() == reason)

    def _on_reason_confirmed(self) -> None:
        detail = self._detail_edit.text().strip()
        full_reason = f"{self._selected_reason}: {detail}" if detail else self._selected_reason
        self.dismissed_with_reason.emit(self._memory_id, full_reason)
        self._close_anim()

    def _reposition(self) -> None:
        screen = self.screen()
        if screen is None:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            x = geom.right() - self.width() - _MARGIN
            y = geom.bottom() - self.height() - _MARGIN
            self.move(x, y)

    def show_in_corner(self) -> None:
        """Posiciona no canto inferior direito da tela e exibe com fade-in."""
        self.adjustSize()
        self._reposition()
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
        if self._importance >= 7:
            # Transforma o popup no painel de motivo antes de fechar
            self._show_reason_panel()
        else:
            self.dismissed.emit(self._memory_id)
            self._close_anim()

    def _on_reply(self) -> None:
        self.replied.emit(self._text)
        self._close_anim()
