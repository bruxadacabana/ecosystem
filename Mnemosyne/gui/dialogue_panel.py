"""
Mnemosyne — Painel de diálogo inter-app AKASHA ↔ Mnemosyne.

Canvas de streaming único onde chegam thought fragments:
  ⬡ AKASHA  → cor fria (#4FC3F7)
  ◇ Mnemosyne → cor quente (#FFB74D)

Sources do AKASHA aparecem como texto colapsável após o fragmento.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# Cores por speaker
_COLOR_AKASHA    = "#4FC3F7"   # azul frio
_COLOR_MNEMOSYNE = "#FFB74D"   # âmbar quente
_COLOR_SOURCES   = "#888888"   # cinza discreto


# ---------------------------------------------------------------------------
# Worker (QThread)
# ---------------------------------------------------------------------------

class _DialogueWorker(QThread):
    fragment_arrived = Signal(str, str)       # (speaker, text)
    sources_arrived  = Signal(str, list)      # (speaker, sources)
    finished_ok      = Signal()

    def __init__(self, question: str, vectorstore, config) -> None:
        super().__init__()
        self._question    = question
        self._vectorstore = vectorstore
        self._config      = config
        self._stop        = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            from core.dialogue import run_dialogue
            run_dialogue(
                question=self._question,
                vectorstore=self._vectorstore,
                config=self._config,
                fragment_cb=lambda spk, txt: self.fragment_arrived.emit(spk, txt),
                sources_cb=lambda spk, srcs: self.sources_arrived.emit(spk, srcs),
                stop_check=lambda: self._stop,
            )
        except Exception:
            pass
        finally:
            self.finished_ok.emit()


# ---------------------------------------------------------------------------
# Widget público
# ---------------------------------------------------------------------------

class DialoguePanel(QWidget):
    """
    Painel de diálogo AKASHA ↔ Mnemosyne.

    Expõe set_context(vectorstore, config) para que main_window injete
    o contexto de RAG antes de iniciar um diálogo.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vectorstore = None
        self._config      = None
        self._worker: _DialogueWorker | None = None
        self._pending_sources: list[dict] = []   # acumula sources do AKASHA corrente

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        header = QLabel("⬡ Diálogo com AKASHA")
        header.setObjectName("sectionLabel")
        layout.addWidget(header)

        self._canvas = QTextEdit()
        self._canvas.setReadOnly(True)
        self._canvas.setPlaceholderText(
            "Inicie um diálogo para ver o AKASHA e a Mnemosyne pensarem juntos…"
        )
        layout.addWidget(self._canvas, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Pergunta inicial…")
        self._input.returnPressed.connect(self._start)
        self._start_btn = QPushButton("Iniciar diálogo")
        self._start_btn.setObjectName("sendBtn")
        self._start_btn.clicked.connect(self._start)
        self._stop_btn = QPushButton("Parar")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(self._start_btn)
        input_row.addWidget(self._stop_btn)
        layout.addLayout(input_row)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def set_context(self, vectorstore, config) -> None:
        self._vectorstore = vectorstore
        self._config      = config

    def start_with_question(self, question: str) -> None:
        """Inicia diálogo programaticamente (ex: a partir de insight do AKASHA)."""
        self._input.setText(question)
        self._start()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _start(self) -> None:
        question = self._input.text().strip()
        if not question:
            return
        if self._vectorstore is None or self._config is None:
            return

        self._canvas.clear()
        self._pending_sources.clear()
        self._input.setEnabled(False)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

        self._worker = _DialogueWorker(question, self._vectorstore, self._config)
        self._worker.fragment_arrived.connect(self._on_fragment)
        self._worker.sources_arrived.connect(self._on_sources)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.start()

    def _stop(self) -> None:
        if self._worker:
            self._worker.stop()

    def _on_finished(self) -> None:
        self._input.setEnabled(True)
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._worker = None
        self._flush_pending_sources()
        self._append_text("\n[Diálogo encerrado]\n", _COLOR_SOURCES)

    def _on_fragment(self, speaker: str, text: str) -> None:
        if speaker == "mnemosyne":
            self._flush_pending_sources()
            self._append_prefix("◇", _COLOR_MNEMOSYNE)
            self._append_text(f" {text}\n", _COLOR_MNEMOSYNE)
        else:  # akasha
            if not self._pending_sources and text:
                self._append_prefix("⬡", _COLOR_AKASHA)
            self._append_text(text, _COLOR_AKASHA)

    def _on_sources(self, speaker: str, sources: list) -> None:
        if speaker == "akasha":
            self._pending_sources = sources
        else:
            self._show_sources(sources, _COLOR_MNEMOSYNE)

    def _flush_pending_sources(self) -> None:
        if self._pending_sources:
            self._append_text("\n", _COLOR_AKASHA)
            self._show_sources(self._pending_sources, _COLOR_AKASHA)
            self._pending_sources.clear()

    def _show_sources(self, sources: list[dict], color: str) -> None:
        if not sources:
            return
        refs = []
        for i, s in enumerate(sources, 1):
            title = s.get("title") or s.get("url") or f"Fonte {i}"
            refs.append(f"[{i}] {title[:60]}")
        self._append_text("  " + " · ".join(refs) + "\n", _COLOR_SOURCES)

    # ------------------------------------------------------------------
    # Renderização
    # ------------------------------------------------------------------

    def _append_prefix(self, prefix: str, color: str) -> None:
        cursor = self._canvas.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        fmt.setFontWeight(700)
        cursor.insertText(prefix, fmt)

    def _append_text(self, text: str, color: str) -> None:
        cursor = self._canvas.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        fmt.setFontWeight(400)
        cursor.insertText(text, fmt)
        self._canvas.setTextCursor(cursor)
        self._canvas.ensureCursorVisible()
