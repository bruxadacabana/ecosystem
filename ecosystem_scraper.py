"""
ecosystem_scraper.py — Extrator de conteúdo web compartilhado.

Utilizado pelo KOSMOS e pelo AKASHA. Recebe HTML já baixado pelo chamador
(sem I/O próprio) e retorna texto extraído no formato solicitado.

Cascata: newspaper4k → trafilatura → readability-lxml → inscriptis → BeautifulSoup
Limiar : primeiro extrator a retornar ≥ 100 palavras vence.
Fallback: resultado mais longo entre os parciais, ou string vazia.

Todos os imports de extratores são opcionais — ImportError é silenciado
para que cada app instale apenas o subconjunto que funciona no seu ambiente.
"""
from __future__ import annotations

import re

_WORD_THRESHOLD = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _word_count(text: str) -> int:
    """Conta palavras ignorando tags HTML."""
    return len(re.sub(r"<[^>]+>", " ", text).split())


def _text_to_html(text: str) -> str:
    """Converte texto puro em parágrafos HTML."""
    paras = [f"<p>{p.strip()}</p>" for p in text.split("\n\n") if p.strip()]
    return "\n".join(paras)


# ---------------------------------------------------------------------------
# Extratores individuais
# Assinatura uniforme: (html, url?, output_format) → str
# Retornam "" em qualquer falha (ImportError ou erro de parse).
# ---------------------------------------------------------------------------

def _ext_newspaper(html: str, url: str, output_format: str) -> str:
    try:
        from newspaper import Article  # newspaper4k
        art = Article(url)
        art.set_html(html)
        art.parse()
        text = (art.text or "").strip()
        if not text:
            return ""
        if output_format == "html":
            return getattr(art, "article_html", None) or _text_to_html(text)
        return text
    except Exception:
        return ""


def _ext_trafilatura(html: str, url: str, output_format: str) -> str:
    try:
        import trafilatura
        fmt = "html" if output_format == "html" else "markdown"
        result = trafilatura.extract(
            html,
            include_formatting=True,
            output_format=fmt,
            no_fallback=False,
            favor_recall=True,
            url=url,
        )
        return result or ""
    except Exception:
        return ""


def _ext_readability(html: str, output_format: str) -> str:
    try:
        from readability import Document
        doc = Document(html)
        content_html = doc.summary(html_partial=True) or ""
        if not content_html:
            return ""
        if output_format == "html":
            return content_html
        from markdownify import markdownify as md
        return md(content_html, heading_style="ATX")
    except Exception:
        return ""


def _ext_inscriptis(html: str, output_format: str) -> str:
    try:
        from inscriptis import get_text
        text = get_text(html)
        if not text:
            return ""
        if output_format == "html":
            return _text_to_html(text)
        return text
    except Exception:
        return ""


def _ext_bs4(html: str, output_format: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["nav", "footer", "script", "style", "aside", "header", "noscript"]):
            tag.decompose()
        article = (
            soup.find("article")
            or soup.find(attrs={"role": "main"})
            or soup.find("main")
            or soup.find("body")
        )
        if article is None:
            return ""
        if output_format == "html":
            return str(article)
        from markdownify import markdownify as md
        return md(str(article), heading_style="ATX")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def extract(html: str, url: str, output_format: str = "markdown") -> str:
    """Extrai conteúdo de HTML via cascata de 5 extratores.

    Args:
        html:          HTML bruto da página (já obtido pelo chamador).
        url:           URL original — usada por extratores que precisam dela.
        output_format: "markdown" (padrão) | "html" | "text"

    Returns:
        Texto extraído. String vazia se todos os extratores falharem.
    """
    if not html:
        return ""

    extractors = [
        lambda: _ext_newspaper(html, url, output_format),
        lambda: _ext_trafilatura(html, url, output_format),
        lambda: _ext_readability(html, output_format),
        lambda: _ext_inscriptis(html, output_format),
        lambda: _ext_bs4(html, output_format),
    ]

    partial: list[str] = []
    for ext in extractors:
        try:
            text = ext()
            if not text:
                continue
            if _word_count(text) >= _WORD_THRESHOLD:
                return text
            partial.append(text)
        except Exception:
            continue

    return max(partial, key=_word_count, default="")
