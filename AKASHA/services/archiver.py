"""
AKASHA — Arquivação de páginas web no formato KOSMOS estendido
Extração em cascata: newspaper4k → trafilatura → readability-lxml → inscriptis → BeautifulSoup
HTML baixado uma vez; primeiro extrator a retornar ≥ 100 palavras vence.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import trafilatura

# ---------------------------------------------------------------------------
# Constante e helpers de texto
# ---------------------------------------------------------------------------

_WORD_THRESHOLD = 100


def _word_count(text: str) -> int:
    return len(text.split())


def _slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "_", text)
    return text[:max_len].strip("_") or "pagina"


def _yaml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _yaml_tags(tags: list[str]) -> str:
    if not tags:
        return "[]"
    items = ", ".join(t.strip() for t in tags if t.strip())
    return f"[{items}]"


def _url_fallback_title(url: str) -> str:
    parsed = urlparse(url)
    segment = parsed.path.rstrip("/").split("/")[-1]
    if segment:
        return segment.replace("-", " ").replace("_", " ").title()
    return parsed.netloc


# ---------------------------------------------------------------------------
# Extratores individuais — todos silenciosos em falha ou lib ausente
# ---------------------------------------------------------------------------

def _ext_newspaper(html: str, url: str) -> str:
    try:
        from newspaper import Article  # newspaper4k
        art = Article(url)
        art.set_html(html)
        art.parse()
        return art.text or ""
    except Exception:
        return ""


def _ext_trafilatura(html: str) -> str:
    try:
        result = trafilatura.extract(
            html,
            include_formatting=True,
            output_format="markdown",
            no_fallback=False,
            favor_recall=True,
        )
        return result or ""
    except Exception:
        return ""


def _ext_readability(html: str) -> str:
    try:
        from markdownify import markdownify as md
        from readability import Document
        doc = Document(html)
        return md(doc.summary(), heading_style="ATX")
    except Exception:
        return ""


def _ext_inscriptis(html: str) -> str:
    try:
        from inscriptis import get_text
        return get_text(html)
    except Exception:
        return ""


def _ext_bs4(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        from markdownify import markdownify as md
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["nav", "footer", "script", "style", "aside", "header"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.find("body")
        if article is None:
            return ""
        return md(str(article), heading_style="ATX")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Cascata de extração
# ---------------------------------------------------------------------------

def _extract_cascade(html: str, url: str) -> str:
    """Tenta extratores em ordem; retorna o primeiro com ≥ 100 palavras.
    Se nenhum atingir o limiar, retorna o mais longo dos resultados parciais."""
    extractors = [
        lambda: _ext_newspaper(html, url),
        lambda: _ext_trafilatura(html),
        lambda: _ext_readability(html),
        lambda: _ext_inscriptis(html),
        lambda: _ext_bs4(html),
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


# ---------------------------------------------------------------------------
# Resultado da arquivação
# ---------------------------------------------------------------------------

@dataclass
class ArchivedPage:
    title:      str
    source:     str
    author:     str
    date:       str
    url:        str
    language:   str
    word_count: int
    tags:       list[str]
    notes:      str
    path:       Path


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------

async def archive_url(
    url: str,
    archive_path: str,
    tags: list[str] | None = None,
    notes: str = "",
) -> ArchivedPage:
    """
    Faz fetch da URL, extrai conteúdo via cascata e salva em:
        {archive_path}/Web/{YYYY-MM-DD}_{slug}.md

    Levanta:
        httpx.HTTPStatusError — status HTTP >= 400
        httpx.RequestError    — falha de rede
        RuntimeError          — erro ao salvar
    """
    tags = tags or []

    # ── Fetch ────────────────────────────────────────────────────────────
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AKASHA-archiver/1.0)"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    # ── Metadados (trafilatura extrai de qualquer forma) ──────────────────
    metadata  = trafilatura.extract_metadata(html, default_url=url)
    title:    str = (metadata and metadata.title)              or _url_fallback_title(url)
    author:   str = (metadata and metadata.author)             or ""
    language: str = (metadata and getattr(metadata, "language", "")) or ""
    domain:   str = urlparse(url).netloc

    # ── Extração em cascata ───────────────────────────────────────────────
    content: str = _extract_cascade(html, url)

    now        = datetime.now()
    date_str   = now.strftime("%Y-%m-%d %H:%M")
    wc         = _word_count(content)

    # ── Frontmatter KOSMOS estendido ──────────────────────────────────────
    body = (
        f'---\n'
        f'title: "{_yaml_str(title)}"\n'
        f'source: "{_yaml_str(domain)}"\n'
        f'date: {date_str}\n'
        f'author: "{_yaml_str(author)}"\n'
        f'url: {url}\n'
        f'language: {language}\n'
        f'word_count: {wc}\n'
        f'tags: {_yaml_tags(tags)}\n'
        f'notes: "{_yaml_str(notes)}"\n'
        f'---\n\n'
        f'# {title}\n\n'
        f'{content}'
    )

    # ── Salvar ────────────────────────────────────────────────────────────
    dest_dir = Path(archive_path) / "Web"
    dest_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = now.strftime("%Y-%m-%d")
    slug        = _slugify(title)
    dest_path   = dest_dir / f"{date_prefix}_{slug}.md"

    counter = 1
    while dest_path.exists():
        dest_path = dest_dir / f"{date_prefix}_{slug}_{counter}.md"
        counter += 1

    try:
        dest_path.write_text(body, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Não foi possível salvar o arquivo: {exc}") from exc

    return ArchivedPage(
        title=title, source=domain, author=author, date=date_str,
        url=url, language=language, word_count=wc,
        tags=tags, notes=notes, path=dest_path,
    )
