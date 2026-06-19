"""
discover_feeds_dialog.py — Diálogo "Descobrir feeds de um site" (design antigo).

Cola-se o endereço de um site; o diálogo descobre os feeds (via
`core.feed_discovery`, em thread para não travar a UI) e mostra os candidatos com
um botão **Adicionar** cada (grava via `feeds_admin.add_feed`). Emite `feeds_changed`
sempre que um feed é adicionado, para o chamador recarregar suas listas.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.feed_discovery import discover_feeds
from app.core.feeds_admin import add_feed

log = logging.getLogger("kosmos.ui.discover")


class _DiscoverWorker(QThread):
    """Roda discover_feeds em background."""

    done = Signal(list)    # list[FeedCandidate]
    failed = Signal(str)

    def __init__(self, site_url: str) -> None:
        super().__init__()
        self._url = site_url

    def run(self) -> None:
        try:
            self.done.emit(discover_feeds(self._url))
        except Exception as exc:  # noqa: BLE001 — qualquer falha vira mensagem
            log.error("Descoberta de feeds falhou: %s", exc)
            self.failed.emit(str(exc))


class _CandidateRow(QWidget):
    """Linha de um candidato: título + URL + botão Adicionar."""

    add_requested = Signal(str, str)   # url, title

    def __init__(self, candidate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("discoveryCard")
        self._url = candidate.url
        self._title = candidate.title or candidate.url
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        info = QVBoxLayout()
        info.setSpacing(2)
        title = QLabel(self._title)
        title.setObjectName("discoveryTitle")
        tf = QFont("Special Elite")
        if not tf.exactMatch():
            tf = QFont("Courier New")
        tf.setPointSize(12)
        title.setFont(tf)
        info.addWidget(title)
        url = QLabel(self._url)
        url.setObjectName("discoveryMeta")
        url.setProperty("class", "meta")
        info.addWidget(url)
        layout.addLayout(info, 1)
        self._add_btn = QPushButton("Adicionar")
        self._add_btn.setObjectName("discoveryAddBtn")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.clicked.connect(lambda: self.add_requested.emit(self._url, self._title))
        layout.addWidget(self._add_btn)

    def mark_added(self) -> None:
        self._add_btn.setText("Adicionado ✓")
        self._add_btn.setEnabled(False)


class DiscoverFeedsDialog(QDialog):
    """Diálogo de descoberta de feeds a partir da URL de um site."""

    feeds_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Descobrir feeds de um site")
        self.setObjectName("discoverDialog")
        self.resize(560, 480)
        self._worker: _DiscoverWorker | None = None
        self._added = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("Endereço do site (ex.: g1.globo.com)")
        self._url_edit.returnPressed.connect(self._on_search)
        row.addWidget(self._url_edit, 1)
        self._search_btn = QPushButton("Buscar")
        self._search_btn.clicked.connect(self._on_search)
        row.addWidget(self._search_btn)
        outer.addLayout(row)

        self._status = QLabel("")
        self._status.setProperty("class", "meta")
        self._status.setWordWrap(True)
        outer.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._results = QWidget()
        self._results_layout = QVBoxLayout(self._results)
        self._results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._results_layout.setSpacing(6)
        scroll.setWidget(self._results)
        outer.addWidget(scroll, 1)

    def _on_search(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            return
        self._search_btn.setEnabled(False)
        self._status.setText("Procurando feeds…")
        self._clear_results()
        self._worker = _DiscoverWorker(url)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, candidates: list) -> None:
        self._search_btn.setEnabled(True)
        self._populate(candidates)

    def _on_failed(self, msg: str) -> None:
        self._search_btn.setEnabled(True)
        self._status.setText(f"Falha na busca: {msg}")

    def _populate(self, candidates: list) -> None:
        """Mostra os candidatos (separado do worker, testável)."""
        self._clear_results()
        if not candidates:
            self._status.setText("Nenhum feed encontrado neste site.")
            return
        self._status.setText(f"{len(candidates)} feed(s) encontrado(s).")
        for c in candidates:
            row = _CandidateRow(c)
            row.add_requested.connect(lambda u, t, r=row: self._on_add(u, t, r))
            self._results_layout.addWidget(row)

    def _on_add(self, url: str, title: str, row: _CandidateRow | None = None) -> None:
        """Adiciona o feed escolhido (separado do clique, testável)."""
        fid = add_feed(url, title or "", "Sem categoria")
        if fid is not None:
            self._added += 1
            if row is not None:
                row.mark_added()
            self.feeds_changed.emit()
            log.info("Feed adicionado pela descoberta: %s", url)

    def _clear_results(self) -> None:
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
