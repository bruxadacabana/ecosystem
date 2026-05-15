"""
FlashcardsDialog — estuda flashcards gerados pelo Studio com progresso persistente.

Cada card tem frente (pergunta) e verso (resposta). O usuário avança marcando
Acertei ✓ / Errei ✗. A cada resposta o progresso é salvo no StudioOutput via
StudioStore, persistindo entre sessões sem re-gerar os cards.
"""
from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.studio_output import StudioOutput
    from core.studio_store import StudioStore

_STATUS_COLORS = {
    "correct": "#4caf50",
    "wrong":   "#ef5350",
    "unseen":  "",
}


class FlashcardsDialog(QDialog):
    """Diálogo de estudo de flashcards com progresso persistente."""

    def __init__(
        self,
        output: "StudioOutput",
        store: "StudioStore | None",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(output.title or "Flashcards")
        self.resize(580, 440)
        self._output = output
        self._store  = store

        try:
            data = json.loads(output.content)
            self._cards: list[dict]     = data.get("cards", [])
            self._progress: dict[str, str] = data.get("progress", {})
        except (json.JSONDecodeError, AttributeError, TypeError):
            self._cards    = []
            self._progress = {}

        # Garante entrada de progresso para todos os cards
        for c in self._cards:
            self._progress.setdefault(c["id"], "unseen")

        self._deck: list[dict] = list(self._cards)
        self._index = 0

        self._build_ui()
        self._refresh_deck()

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, max(len(self._cards), 1))
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%v / %m acertados")
        toolbar.addWidget(self._progress_bar, 1)

        self._only_errors_cb = QCheckBox("Só erros")
        self._only_errors_cb.toggled.connect(self._on_filter_changed)
        toolbar.addWidget(self._only_errors_cb)

        shuffle_btn = QPushButton("Embaralhar")
        shuffle_btn.clicked.connect(self._on_shuffle)
        toolbar.addWidget(shuffle_btn)

        vl.addLayout(toolbar)

        # ── Card Stack ──
        # Índice 0 = frente (pergunta), índice 1 = verso (resposta)
        self._card_stack = QStackedWidget()
        self._card_stack.setMinimumHeight(200)

        front_w = QWidget()
        fl = QVBoxLayout(front_w)
        fl.setContentsMargins(24, 16, 24, 16)
        side_lbl_f = QLabel("PERGUNTA")
        side_lbl_f.setObjectName("flashcardSide")
        side_lbl_f.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fl.addWidget(side_lbl_f)
        self._front_text = QLabel()
        self._front_text.setWordWrap(True)
        self._front_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._front_text.setObjectName("flashcardFront")
        fl.addWidget(self._front_text, 1)
        self._card_stack.addWidget(front_w)

        back_w = QWidget()
        bl = QVBoxLayout(back_w)
        bl.setContentsMargins(24, 16, 24, 16)
        side_lbl_b = QLabel("RESPOSTA")
        side_lbl_b.setObjectName("flashcardSide")
        side_lbl_b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(side_lbl_b)
        self._back_text = QLabel()
        self._back_text.setWordWrap(True)
        self._back_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._back_text.setObjectName("flashcardBack")
        bl.addWidget(self._back_text, 1)
        self._card_stack.addWidget(back_w)

        vl.addWidget(self._card_stack, 1)

        # ── Flip button ──
        self._flip_btn = QPushButton("▶  Ver resposta")
        self._flip_btn.setObjectName("flipBtn")
        self._flip_btn.clicked.connect(self._flip)
        vl.addWidget(self._flip_btn)

        # ── Botões de resposta (visíveis apenas no verso) ──
        self._answer_row = QWidget()
        ar = QHBoxLayout(self._answer_row)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.setSpacing(12)
        self._wrong_btn   = QPushButton("✗  Errei")
        self._wrong_btn.setObjectName("wrongBtn")
        self._wrong_btn.clicked.connect(lambda: self._record("wrong"))
        self._correct_btn = QPushButton("✓  Acertei")
        self._correct_btn.setObjectName("correctBtn")
        self._correct_btn.clicked.connect(lambda: self._record("correct"))
        ar.addStretch()
        ar.addWidget(self._wrong_btn)
        ar.addWidget(self._correct_btn)
        ar.addStretch()
        self._answer_row.setVisible(False)
        vl.addWidget(self._answer_row)

        # ── Rodapé ──
        footer = QHBoxLayout()
        self._counter_lbl = QLabel()
        self._counter_lbl.setObjectName("flashcardCounter")
        footer.addWidget(self._counter_lbl)
        footer.addStretch()
        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        vl.addLayout(footer)

    # ------------------------------------------------------------------
    # Lógica
    # ------------------------------------------------------------------

    def _refresh_deck(self) -> None:
        """Recomputa deck a partir do filtro ativo e exibe o card atual."""
        only_errors = self._only_errors_cb.isChecked()
        if only_errors:
            self._deck = [c for c in self._cards
                          if self._progress.get(c["id"]) == "wrong"]
        else:
            self._deck = list(self._cards)
        self._index = 0
        self._show_card()

    def _show_card(self) -> None:
        card = self._current_card()
        if not card:
            self._front_text.setText(
                "Nenhum card disponível."
                if not self._deck else "Todos os cards vistos."
            )
            self._back_text.setText("")
            self._flip_btn.setEnabled(False)
            self._answer_row.setVisible(False)
            self._counter_lbl.setText("0 / 0")
            self._card_stack.setCurrentIndex(0)
            return

        self._front_text.setText(card["front"])
        self._back_text.setText(card["back"])
        self._card_stack.setCurrentIndex(0)       # mostra frente
        self._flip_btn.setVisible(True)
        self._flip_btn.setEnabled(True)
        self._answer_row.setVisible(False)
        self._counter_lbl.setText(
            f"Card {self._index + 1} de {len(self._deck)}"
        )
        self._refresh_progress_bar()

    def _current_card(self) -> dict | None:
        if self._deck and 0 <= self._index < len(self._deck):
            return self._deck[self._index]
        return None

    def _flip(self) -> None:
        self._card_stack.setCurrentIndex(1)   # mostra verso
        self._flip_btn.setVisible(False)
        self._answer_row.setVisible(True)

    def _record(self, result: str) -> None:
        card = self._current_card()
        if card:
            self._progress[card["id"]] = result
            self._save_progress()
        # Avança para o próximo card (wrap)
        self._index = (self._index + 1) % max(len(self._deck), 1)
        self._show_card()

    def _refresh_progress_bar(self) -> None:
        correct = sum(1 for v in self._progress.values() if v == "correct")
        self._progress_bar.setValue(correct)
        self._progress_bar.setMaximum(max(len(self._cards), 1))

    def _save_progress(self) -> None:
        if not self._store:
            return
        try:
            data = json.loads(self._output.content)
            data["progress"] = self._progress
            self._output.content = json.dumps(data, ensure_ascii=False, indent=2)
            self._store.save(self._output)
        except Exception:
            pass  # não crasha a UI em falha de salvamento

    def _on_filter_changed(self, _: bool) -> None:
        self._refresh_deck()

    def _on_shuffle(self) -> None:
        random.shuffle(self._deck)
        self._index = 0
        self._show_card()
