"""
AKASHA — Arquivação de páginas web no formato KOSMOS estendido
Fetch via httpx; extração delegada ao ecosystem_scraper (cascata compartilhada).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import trafilatura

# Módulo compartilhado do ecossistema
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ecosystem_scraper import extract as _cascade_extract, get_fetch_url as _get_fetch_url

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
# Tipos
# ---------------------------------------------------------------------------

@dataclass
class FetchedPage:
    """Resultado de fetch + extração de conteúdo, sem persistência."""
    url: str
    title: str
    content_md: str
    word_count: int
    author: str = field(default="")
    language: str = field(default="")


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
    content_md: str = field(default="")


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

async def fetch_and_extract(url: str, max_words: int = 0) -> FetchedPage:
    """
    Faz fetch de uma URL e extrai conteúdo em Markdown (sem salvar em disco).
    Inclui fallback Jina Reader se a cascata retornar < 100 palavras.
    max_words=0 significa sem limite de truncamento.

    Levanta:
        httpx.HTTPStatusError — status HTTP >= 400
        httpx.RequestError    — falha de rede
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AKASHA-archiver/1.0)"},
    ) as client:
        response = await client.get(_get_fetch_url(url))
        response.raise_for_status()
        html = response.text

        metadata = trafilatura.extract_metadata(html, default_url=url)
        title:    str = (metadata and metadata.title)                      or _url_fallback_title(url)
        author:   str = (metadata and metadata.author)                     or ""
        language: str = (metadata and getattr(metadata, "language", ""))   or ""

        content: str = _cascade_extract(html, url, output_format="markdown")

        if len(content.split()) < 100:
            try:
                jina_resp = await client.get(
                    f"https://r.jina.ai/{url}",
                    headers={"Accept": "text/plain", "X-Return-Format": "markdown"},
                    timeout=20,
                )
                jina_resp.raise_for_status()
                jina_text = jina_resp.text.strip()
                if len(jina_text.split()) > len(content.split()):
                    content = jina_text
            except Exception:
                pass  # Jina indisponível — mantém resultado local

    words = content.split()
    if max_words > 0 and len(words) > max_words:
        content = " ".join(words[:max_words])

    return FetchedPage(
        url=url,
        title=title,
        content_md=content,
        word_count=len(words),
        author=author,
        language=language,
    )


async def archive_pdf(
    *,
    content_md:  str,
    title:       str,
    authors:     str,
    year:        int | None,
    doi:         str | None,
    arxiv_id:    str | None,
    source_url:  str,
    archive_path: str,
) -> Path:
    """
    Salva Markdown extraído de um PDF em:
        {archive_path}/Papers/{YYYY-MM-DD}_{slug}.md

    Levanta:
        OSError — falha ao gravar no disco.
    """
    now      = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")

    frontmatter = (
        f'---\n'
        f'title: "{_yaml_str(title)}"\n'
        f'source: "paper"\n'
        f'date: {date_str}\n'
        f'author: "{_yaml_str(authors)}"\n'
        f'url: {source_url}\n'
        f'language: \n'
        f'word_count: {len(content_md.split())}\n'
        f'type: paper\n'
    )
    if doi:
        frontmatter += f'doi: "{_yaml_str(doi)}"\n'
    if arxiv_id:
        frontmatter += f'arxiv_id: {arxiv_id}\n'
    if year:
        frontmatter += f'year: {year}\n'
    frontmatter += 'tags: []\nnotes: ""\n---\n\n'

    body = frontmatter + f'# {title}\n\n'
    if authors:
        body += f'*{authors}*\n\n'
    body += content_md

    dest_dir = Path(archive_path) / "Papers"
    dest_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = now.strftime("%Y-%m-%d")
    slug        = _slugify(title)
    dest_path   = dest_dir / f"{date_prefix}_{slug}.md"
    counter = 1
    while dest_path.exists():
        dest_path = dest_dir / f"{date_prefix}_{slug}_{counter}.md"
        counter += 1

    dest_path.write_text(body, encoding="utf-8")
    return dest_path


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

    page = await fetch_and_extract(url)  # sem truncamento — arquivo completo

    now      = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")
    domain   = urlparse(url).netloc

    body = (
        f'---\n'
        f'title: "{_yaml_str(page.title)}"\n'
        f'source: "{_yaml_str(domain)}"\n'
        f'date: {date_str}\n'
        f'author: "{_yaml_str(page.author)}"\n'
        f'url: {url}\n'
        f'language: {page.language}\n'
        f'word_count: {page.word_count}\n'
        f'tags: {_yaml_tags(tags)}\n'
        f'notes: "{_yaml_str(notes)}"\n'
        f'---\n\n'
        f'# {page.title}\n\n'
        f'{page.content_md}'
    )

    dest_dir = Path(archive_path) / "Web"
    dest_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = now.strftime("%Y-%m-%d")
    slug        = _slugify(page.title)
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
        title=page.title, source=domain, author=page.author, date=date_str,
        url=url, language=page.language, word_count=page.word_count,
        tags=tags, notes=notes, path=dest_path, content_md=page.content_md,
    )
