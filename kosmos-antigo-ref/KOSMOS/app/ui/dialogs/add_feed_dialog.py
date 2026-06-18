"""Diálogo para adicionar um feed (URL + tipo + categoria, ou busca Google News)."""

from __future__ import annotations

import logging
import urllib.parse
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from app.utils.validators import detect_feed_type, is_valid_url

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager
    from app.core.models import Category

log = logging.getLogger("kosmos.ui.add_feed")

# Idiomas/regiões disponíveis para o Google News
_GNEWS_LOCALES = [
    ("Português — Brasil",  "pt-BR", "BR", "pt"),
    ("English — US",        "en-US", "US", "en"),
    ("Español",             "es-419","MX", "es"),
    ("Français",            "fr",    "FR", "fr"),
    ("Deutsch",             "de",    "DE", "de"),
    ("Italiano",            "it",    "IT", "it"),
    ("日本語",               "ja",    "JP", "ja"),
]


# ------------------------------------------------------------------
# Worker thread para validação assíncrona
# ------------------------------------------------------------------

class _ValidateWorker(QThread):
    """Testa o feed em background sem bloquear a UI."""

    finished = pyqtSignal(bool, str, str)  # ok, feed_title, error_msg

    def __init__(self, url: str, feed_type: str) -> None:
        super().__init__()
        self._url       = url
        self._feed_type = feed_type

    def run(self) -> None:
        try:
            import feedparser
            d = feedparser.parse(
                self._url,
                request_headers={"User-Agent": "Mozilla/5.0 (compatible; KOSMOS/1.0)"},
            )
            if d.get("bozo") and not d.get("entries") and not d.get("feed", {}).get("title"):
                self.finished.emit(False, "", f"Feed inválido: {d.get('bozo_exception', 'erro desconhecido')}")
                return
            title = d.feed.get("title", "").strip() or self._url
            self.finished.emit(True, title, "")
        except Exception as exc:
            self.finished.emit(False, "", str(exc))


# ------------------------------------------------------------------
# Diálogo principal
# ------------------------------------------------------------------

class AddFeedDialog(QDialog):
    """Diálogo para adicionar um feed ao KOSMOS.

    Duas abas:
        - "Feed RSS/URL"    — URL direta + tipo + nome + categoria.
        - "Google News"     — termo de busca → URL construída automaticamente.

    Uso::

        dlg = AddFeedDialog(feed_manager, categories, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            feed = dlg.created_feed
    """

    def __init__(
        self,
        feed_manager: "FeedManager",
        categories: "list[Category]",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fm         = feed_manager
        self._categories = categories
        self._worker: _ValidateWorker | None = None
        self.created_feed = None

        self.setWindowTitle("Adicionar Feed")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_url_tab(),    "Feed RSS / URL")
        self._tabs.addTab(self._build_gnews_tab(),  "Google News")
        root.addWidget(self._tabs)

        # Status (compartilhado entre abas)
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("dialogStatusLabel")
        self._status_lbl.setFont(self._mono(11))
        self._status_lbl.setWordWrap(True)
        root.addWidget(self._status_lbl)

        # Botões OK / Cancelar
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self._ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Adicionar")
        root.addWidget(buttons)

    def _build_url_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 16, 12, 8)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # URL
        self._url_input = QLineEdit()
        self._url_input.setFont(self._mono(12))
        self._url_input.setPlaceholderText("https://example.com/feed.xml")
        self._url_input.textChanged.connect(self._on_url_changed)
        form.addRow(self._lbl("URL do feed:"), self._url_input)

        # Tipo (auto-detectado)
        self._type_combo = QComboBox()
        self._type_combo.setFont(self._mono(11))
        self._type_combo.addItems(["rss", "youtube", "tumblr", "substack", "mastodon", "reddit"])
        form.addRow(self._lbl("Tipo:"), self._type_combo)

        # Nome
        self._name_input = QLineEdit()
        self._name_input.setFont(self._mono(12))
        self._name_input.setPlaceholderText("Preenchido automaticamente ao verificar")
        form.addRow(self._lbl("Nome:"), self._name_input)

        # Categoria
        self._cat_combo = self._build_cat_combo()
        form.addRow(self._lbl("Categoria:"), self._cat_combo)

        layout.addLayout(form)

        # Botão verificar
        self._check_btn = QPushButton("Verificar URL")
        self._check_btn.setFont(self._mono(11))
        self._check_btn.clicked.connect(self._on_verify)
        layout.addWidget(self._check_btn)
        layout.addStretch()

        return w

    def _build_gnews_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 16, 12, 8)
        layout.setSpacing(10)

        note = QLabel(
            "Cria um feed RSS a partir de uma busca no Google News.\n"
            "Os artigos são atualizados automaticamente junto com os demais feeds."
        )
        note.setFont(self._mono(10))
        note.setObjectName("cardMeta")
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Termo de busca
        self._gnews_query = QLineEdit()
        self._gnews_query.setFont(self._mono(12))
        self._gnews_query.setPlaceholderText("ex: inteligência artificial, climate change…")
        self._gnews_query.textChanged.connect(self._on_gnews_query_changed)
        form.addRow(self._lbl("Termo de busca:"), self._gnews_query)

        # Idioma/região
        self._gnews_locale = QComboBox()
        self._gnews_locale.setFont(self._mono(11))
        for label, *_ in _GNEWS_LOCALES:
            self._gnews_locale.addItem(label)
        form.addRow(self._lbl("Idioma / Região:"), self._gnews_locale)

        # Nome do feed
        self._gnews_name = QLineEdit()
        self._gnews_name.setFont(self._mono(12))
        self._gnews_name.setPlaceholderText("Gerado automaticamente a partir do termo")
        form.addRow(self._lbl("Nome:"), self._gnews_name)

        # Categoria
        self._gnews_cat_combo = self._build_cat_combo()
        form.addRow(self._lbl("Categoria:"), self._gnews_cat_combo)

        layout.addLayout(form)

        # URL preview
        preview_row = QFormLayout()
        preview_row.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._gnews_url_preview = QLabel("—")
        self._gnews_url_preview.setObjectName("cardMeta")
        self._gnews_url_preview.setFont(self._mono(9))
        self._gnews_url_preview.setWordWrap(True)
        preview_row.addRow(self._lbl("URL gerada:"), self._gnews_url_preview)
        layout.addLayout(preview_row)

        layout.addStretch()
        return w

    # ------------------------------------------------------------------
    # Helpers de widgets
    # ------------------------------------------------------------------

    def _build_cat_combo(self) -> QComboBox:
        cb = QComboBox()
        cb.setFont(self._mono(11))
        cb.addItem("— Sem categoria —", None)
        for cat in self._categories:
            cb.addItem(cat.name, cat.id)
        return cb

    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(12)
        lbl.setFont(f)
        return lbl

    @staticmethod
    def _mono(size: int) -> QFont:
        f = QFont("Courier Prime")
        if not f.exactMatch():
            f = QFont("Courier New")
        f.setPointSize(size)
        return f

    # ------------------------------------------------------------------
    # Lógica — aba URL
    # ------------------------------------------------------------------

    def _on_url_changed(self, text: str) -> None:
        detected = detect_feed_type(text.strip())
        idx = self._type_combo.findText(detected)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._status_lbl.setText("")

    def _on_verify(self) -> None:
        url = self._url_input.text().strip()
        if not is_valid_url(url):
            self._set_status("URL inválida.", error=True)
            return

        self._check_btn.setEnabled(False)
        self._set_status("Verificando…")

        self._worker = _ValidateWorker(url, self._type_combo.currentText())
        self._worker.finished.connect(self._on_verify_done)
        self._worker.start()

    def _on_verify_done(self, ok: bool, title: str, error: str) -> None:
        self._check_btn.setEnabled(True)
        if ok:
            if title and not self._name_input.text().strip():
                self._name_input.setText(title)
            self._set_status(f"Feed encontrado: {title}", error=False)
        else:
            self._set_status(f"Erro: {error}", error=True)

    # ------------------------------------------------------------------
    # Lógica — aba Google News
    # ------------------------------------------------------------------

    def _build_gnews_url(self) -> str:
        query      = self._gnews_query.text().strip()
        locale_idx = self._gnews_locale.currentIndex()
        _, hl, gl, lang = _GNEWS_LOCALES[locale_idx]
        encoded = urllib.parse.quote_plus(query)
        return (
            f"https://news.google.com/rss/search"
            f"?q={encoded}&hl={hl}&gl={gl}&ceid={gl}:{lang}"
        )

    def _on_gnews_query_changed(self, text: str) -> None:
        if text.strip():
            self._gnews_url_preview.setText(self._build_gnews_url())
            if not self._gnews_name.text().strip():
                self._gnews_name.setPlaceholderText(f"Google News: {text.strip()}")
        else:
            self._gnews_url_preview.setText("—")
        self._status_lbl.setText("")

    # ------------------------------------------------------------------
    # Aceitar
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        if self._tabs.currentIndex() == 0:
            self._accept_url_tab()
        else:
            self._accept_gnews_tab()

    def _accept_url_tab(self) -> None:
        url    = self._url_input.text().strip()
        name   = self._name_input.text().strip()
        kind   = self._type_combo.currentText()
        cat_id = self._cat_combo.currentData()

        if not is_valid_url(url):
            self._set_status("URL inválida.", error=True)
            return
        if not name:
            self._set_status("Informe um nome para o feed.", error=True)
            return

        try:
            self.created_feed = self._fm.add_feed(url, name, kind, cat_id)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Erro", f"Não foi possível adicionar o feed:\n{exc}")

    def _accept_gnews_tab(self) -> None:
        query  = self._gnews_query.text().strip()
        cat_id = self._gnews_cat_combo.currentData()

        if not query:
            self._set_status("Informe um termo de busca.", error=True)
            return

        url  = self._build_gnews_url()
        name = self._gnews_name.text().strip() or f"Google News: {query}"

        try:
            self.created_feed = self._fm.add_feed(url, name, "rss", cat_id)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Erro", f"Não foi possível adicionar o feed:\n{exc}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str, error: bool = False) -> None:
        color = "#8B3A2A" if error else "#6B5A3E"
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(f"color: {color};")
