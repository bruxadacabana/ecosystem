"""
AKASHA — Arquivação de páginas web no formato KOSMOS estendido
Fetch via httpx; extração delegada ao ecosystem_scraper (cascata compartilhada).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import trafilatura

# Módulo compartilhado do ecossistema
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ecosystem_scraper import extract as _cascade_extract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# Resultado
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
    Faz fetch da URL, extrai conteúdo via cascata compartilhada e salva em:
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

    # ── Metadados (trafilatura) ───────────────────────────────────────────
    metadata  = trafilatura.extract_metadata(html, default_url=url)
    title:    str = (metadata and metadata.title)              or _url_fallback_title(url)
    author:   str = (metadata and metadata.author)             or ""
    language: str = (metadata and getattr(metadata, "language", "")) or ""
    domain:   str = urlparse(url).netloc

    # ── Extração em cascata compartilhada ─────────────────────────────────
    content: str = _cascade_extract(html, url, output_format="markdown")

    now      = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")
    wc       = len(content.split())

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
