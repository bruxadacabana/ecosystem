"""
article_webview.py — Corpo do artigo renderizado em QWebEngineView (leitor antigo).

O corpo do artigo é desenhado como HTML com o CSS sépia/serifado do leitor antigo
(``reader_{theme}.css``: tipografia IM Fell English, campo estelar de fundo,
regras de destaque). Isso recupera a leitura bonita do KOSMOS pré-v3.

Destaques (highlights): a seleção de texto + menu de contexto criam um destaque.
Lemos ``page().selectedText()`` no ``contextMenuEvent`` e emitimos
``highlight_requested(texto, tipo)`` — a coloração inline é feita server-side
(HTML com ``<mark class='hl-...'>`` montado em Python), sem JavaScript custom.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMenu, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView

from app.core.highlights import TYPE_LABELS, VALID_TYPES
from app.theme.theme_manager import reader_css

log = logging.getLogger("kosmos.reader_webview")

# Tipos oferecidos no menu de marcação (exclui 'generic', que é só fallback).
_MARK_TYPES = ("citation", "question", "fact", "contradiction")

_DOC_TEMPLATE = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<style>{css}</style></head><body>{body}</body></html>"
)


class ArticleWebView(QWebEngineView):
    """Corpo do artigo em QWebEngineView com o CSS do leitor antigo."""

    highlight_requested = Signal(str, str)  # (texto_selecionado, tipo)

    def __init__(self, theme: str = "day", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("reader_webview")
        self._theme = theme
        self.show_empty()

    def set_theme(self, theme: str) -> None:
        self._theme = theme

    def set_body(self, body_html: str) -> None:
        """Renderiza o corpo (fragmento HTML já escapado/com marcas) com o CSS do tema."""
        doc = _DOC_TEMPLATE.format(css=reader_css(self._theme), body=body_html or "")
        self.setHtml(doc)

    def show_empty(self) -> None:
        self.setHtml(_DOC_TEMPLATE.format(css=reader_css(self._theme), body=""))

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """Menu de contexto: marca o trecho selecionado como um tipo de destaque."""
        page = self.page()
        if page is None or not page.hasSelection():
            return  # sem seleção → sem menu (evita o menu padrão do Chromium)
        selected = page.selectedText()
        menu = QMenu(self)
        sub = menu.addMenu("Marcar como")
        for t in _MARK_TYPES:
            act = sub.addAction(TYPE_LABELS.get(t, t))
            act.setData(t)
        chosen = menu.exec(event.globalPos())
        if chosen is not None and chosen.data() in VALID_TYPES:
            log.debug("Destaque solicitado no webview (tipo=%s).", chosen.data())
            self.highlight_requested.emit(selected, str(chosen.data()))
