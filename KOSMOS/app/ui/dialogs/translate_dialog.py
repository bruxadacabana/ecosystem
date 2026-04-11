"""Diálogo de tradução de artigos via deep-translator (Google Translate)."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from app.core import translator as tr

log = logging.getLogger("kosmos.ui.translate")


class _TranslateWorker(QThread):
    finished = pyqtSignal(str)
    failed   = pyqtSignal(str)

    def __init__(self, text: str, from_code: str, to_code: str) -> None:
        super().__init__()
        self._text      = text
        self._from_code = from_code
        self._to_code   = to_code

    def run(self) -> None:
        try:
            result = tr.translate_text(self._text, self._from_code, self._to_code)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class TranslateDialog(QDialog):
    """Diálogo para traduzir o conteúdo do artigo aberto."""

    def __init__(self, article_html: str, parent=None) -> None:
        super().__init__(parent)
        self._article_html    = article_html
        self._worker: _TranslateWorker | None = None

        self.setWindowTitle("Traduzir Artigo")
        self.setMinimumSize(580, 520)
        self.resize(640, 580)

        self._build_ui()
        self._prefill_source()
        self._update_btn()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setObjectName("feedListHeader")
        w.setFixedHeight(52)
        layout = QHBoxLayout(w)
        layout.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel("Traduzir Artigo")
        lbl.setObjectName("feedListTitle")
        f = QFont("Special Elite")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(16)
        lbl.setFont(f)
        layout.addWidget(lbl)
        return w

    def _build_body(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        mono = self._mono(11)

        # Seletores de idioma
        lang_row = QHBoxLayout()
        lang_row.setSpacing(10)

        de_lbl = QLabel("De:")
        de_lbl.setFont(mono)
        lang_row.addWidget(de_lbl)

        self._from_combo = QComboBox()
        self._from_combo.setFont(mono)
        self._from_combo.setMinimumWidth(190)
        for code, name in tr.LANGUAGE_NAMES.items():
            self._from_combo.addItem(name, code)
        self._from_combo.currentIndexChanged.connect(self._update_btn)
        lang_row.addWidget(self._from_combo)

        para_lbl = QLabel("Para:")
        para_lbl.setFont(mono)
        lang_row.addWidget(para_lbl)

        self._to_combo = QComboBox()
        self._to_combo.setFont(mono)
        self._to_combo.setMinimumWidth(160)
        for code, name in tr.TARGET_LANGUAGE_NAMES.items():
            self._to_combo.addItem(name, code)
        keys = list(tr.TARGET_LANGUAGE_NAMES.keys())
        if "pt" in keys:
            self._to_combo.setCurrentIndex(keys.index("pt"))
        self._to_combo.currentIndexChanged.connect(self._update_btn)
        lang_row.addWidget(self._to_combo)

        lang_row.addStretch()
        layout.addLayout(lang_row)

        self._status_lbl = QLabel("Tradução via Google Translate (requer internet).")
        self._status_lbl.setObjectName("cardMeta")
        self._status_lbl.setFont(self._mono(10))
        layout.addWidget(self._status_lbl)

        self._translate_btn = QPushButton("Traduzir")
        self._translate_btn.setFont(mono)
        self._translate_btn.clicked.connect(self._on_translate)
        layout.addWidget(self._translate_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("listSeparator")
        layout.addWidget(sep)

        result_lbl = QLabel("Tradução:")
        result_lbl.setObjectName("cardMeta")
        result_lbl.setFont(self._mono(10))
        layout.addWidget(result_lbl)

        self._result_box = QPlainTextEdit()
        self._result_box.setReadOnly(True)
        self._result_box.setFont(self._serif(12))
        self._result_box.setPlaceholderText("A tradução aparecerá aqui…")
        layout.addWidget(self._result_box, 1)

        return w

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setObjectName("feedListHeader")
        w.setFixedHeight(48)
        layout = QHBoxLayout(w)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.addStretch()
        close_btn = QPushButton("Fechar")
        close_btn.setFont(self._mono(11))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        return w

    # ------------------------------------------------------------------
    # Lógica
    # ------------------------------------------------------------------

    def _prefill_source(self) -> None:
        """Tenta detectar o idioma do artigo e pré-selecionar no combo."""
        text     = tr.strip_html(self._article_html)[:2000]
        detected = tr.detect_language(text)
        keys     = list(tr.LANGUAGE_NAMES.keys())
        if detected and detected in keys:
            self._from_combo.setCurrentIndex(keys.index(detected))
        # Caso contrário, mantém "auto"

    def _from_code(self) -> str:
        return self._from_combo.currentData()

    def _to_code(self) -> str:
        return self._to_combo.currentData()

    def _update_btn(self) -> None:
        from_code = self._from_code()
        to_code   = self._to_code()
        same = (from_code != "auto" and from_code == to_code)
        self._translate_btn.setEnabled(not same)
        if same:
            self._status_lbl.setText("Selecione idiomas diferentes.")
        else:
            self._status_lbl.setText("Tradução via Google Translate (requer internet).")

    def _on_translate(self) -> None:
        text = tr.strip_html(self._article_html)
        if not text:
            self._result_box.setPlainText("Sem conteúdo para traduzir.")
            return
        self._translate_btn.setEnabled(False)
        self._status_lbl.setText("Traduzindo…")
        self._result_box.setPlainText("")
        self._worker = _TranslateWorker(text, self._from_code(), self._to_code())
        self._worker.finished.connect(self._on_done)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_done(self, result: str) -> None:
        self._result_box.setPlainText(result)
        self._status_lbl.setText("Tradução concluída.")
        self._translate_btn.setEnabled(True)

    def _on_error(self, error: str) -> None:
        self._status_lbl.setText(f"Erro: {error}")
        self._translate_btn.setEnabled(True)
        log.warning("Erro na tradução: %s", error)

    # ------------------------------------------------------------------
    # Fontes
    # ------------------------------------------------------------------

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f

    @staticmethod
    def _serif(size: int) -> QFont:
        f = QFont("IM Fell English")
        if not f.exactMatch():
            f = QFont("Georgia")
        f.setPointSize(size)
        return f
