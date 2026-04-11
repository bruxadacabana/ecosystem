"""Detecta se o conteúdo de um artigo veio completo ou truncado do feed."""

from __future__ import annotations

import re
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    """Extrai texto puro de HTML."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self._parts)


def _extract_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.text


def check_integrity(html: str | None) -> str:
    """Analisa o conteúdo HTML e retorna 'full' | 'truncated' | 'unknown'.

    Args:
        html: conteúdo HTML do artigo (summary ou content_full).

    Returns:
        'full'      — artigo aparenta estar completo.
        'truncated' — artigo definitivamente truncado.
        'unknown'   — não foi possível determinar.
    """
    if not html or not html.strip():
        return "unknown"

    text = _extract_text(html).strip()
    if not text:
        return "unknown"

    lower = text.lower()

    # Truncado: termina com indicador explícito de corte
    if re.search(r"\[?\.\.\.\]?\s*$", text):
        return "truncated"
    if text.rstrip().endswith("…"):
        return "truncated"

    word_count = len(text.split())

    # Truncado: link "read more" + conteúdo curto
    has_read_more = bool(re.search(
        r"(read[\s\-]+more|continue[\s\-]+reading|leia[\s\-]+mais|"
        r"ver[\s\-]+mais|read[\s\-]+the[\s\-]+full|clique[\s\-]+aqui|"
        r"saiba[\s\-]+mais)",
        lower,
    ))
    if has_read_more and word_count < 150:
        return "truncated"

    # Truncado: conteúdo muito curto sem imagens
    if word_count < 50:
        has_image = bool(re.search(r"<img", html, re.IGNORECASE))
        if not has_image:
            return "truncated"

    # Aparenta completo se tem conteúdo substancial
    if word_count >= 200:
        return "full"

    return "unknown"
