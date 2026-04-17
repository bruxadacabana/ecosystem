"""Fase 10 — Buscador de Sites Pessoais: crawler BFS + busca FTS5."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiosqlite
import httpx

from config import DB_PATH

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ecosystem_scraper import extract as _cascade_extract

log = logging.getLogger("akasha.crawler")

_CRAWL_CONCURRENCY = 4
_CRAWL_TIMEOUT = 20

_ASSET_EXTS = re.compile(
    r"\.(css|js|png|jpg|jpeg|gif|svg|webp|ico|woff2?|ttf|eot|pdf|zip|gz|tar"
    r"|mp3|mp4|avi|mov|mkv|exe|dmg|apk)$",
    re.IGNORECASE,
)
_ALLOWED_SCHEMES = {"http", "https"}


def extract_links(html: str, base_url: str) -> list[str]:
    """Extrai links absolutos de `html`, normalizados com `base_url`.

    Descarta: âncoras (#), assets estáticos, esquemas não-http(s),
    parâmetros de fragmento e duplicatas.
    """
    base_parsed = urlparse(base_url)
    seen: set[str] = set()
    links: list[str] = []

    for match in re.finditer(r'href=["\']([^"\'>\s]+)["\']', html, re.IGNORECASE):
        raw = match.group(1).strip()

        # Descarta âncoras puras e javascript:
        if not raw or raw.startswith("#") or raw.lower().startswith("javascript:"):
            continue

        absolute = urljoin(base_url, raw)
        parsed = urlparse(absolute)

        # Esquema não permitido
        if parsed.scheme not in _ALLOWED_SCHEMES:
            continue

        # Remove fragmento, normaliza
        clean = parsed._replace(fragment="").geturl()

        # Assets estáticos
        path_no_qs = parsed.path.split("?")[0]
        if _ASSET_EXTS.search(path_no_qs):
            continue

        # Garante que o host existe (evita links malformados)
        if not parsed.netloc:
            continue

        _ = base_parsed  # filtro de domínio fica no crawl_site
        if clean not in seen:
            seen.add(clean)
            links.append(clean)

    return links


def _root_domain(host: str) -> str:
    """Retorna as duas últimas partes do hostname (domínio raiz sem subdomínio)."""
    parts = host.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


async def discover_subdomains(base_url: str) -> list[str]:
    """Descobre subdomínios vinculados ao mesmo domínio raiz de `base_url`.

    Faz GET na homepage e tenta /sitemap.xml; coleta hosts distintos que
    compartilhem o mesmo domínio raiz e retorna como URLs-base (scheme+host).
    """
    parsed = urlparse(base_url)
    root = _root_domain(parsed.hostname or "")
    found: set[str] = set()

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AKASHA-crawler/1.0)"},
    ) as client:
        for target in [base_url, f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"]:
            try:
                resp = await client.get(target)
                resp.raise_for_status()
                html = resp.text
            except Exception as exc:
                log.debug("discover_subdomains: falha em %s — %s", target, exc)
                continue

            for link in extract_links(html, target):
                lp = urlparse(link)
                host = lp.hostname or ""
                if host and _root_domain(host) == root and host != parsed.hostname:
                    found.add(f"{lp.scheme}://{lp.netloc}")

    return sorted(found)


# ---------------------------------------------------------------------------
# crawl_site
# ---------------------------------------------------------------------------

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


async def _fetch_page(client: httpx.AsyncClient, url: str) -> tuple[str, int]:
    """Retorna (html, http_status). html vazio em caso de erro."""
    try:
        resp = await client.get(url)
        return resp.text, resp.status_code
    except Exception as exc:
        log.debug("crawl fetch error %s: %s", url, exc)
        return "", 0


async def _upsert_page(
    db: aiosqlite.Connection,
    site_id: int,
    url: str,
    title: str,
    content_md: str,
    content_hash: str,
    http_status: int,
    now: str,
) -> None:
    await db.execute(
        """INSERT INTO crawl_pages
               (site_id, url, title, content_md, content_hash, http_status, crawled_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(url) DO UPDATE SET
               title=excluded.title, content_md=excluded.content_md,
               content_hash=excluded.content_hash, http_status=excluded.http_status,
               crawled_at=excluded.crawled_at""",
        (site_id, url, title, content_md, content_hash, http_status, now),
    )
    # Sync FTS5 manualmente
    await db.execute("DELETE FROM crawl_fts WHERE url = ?", (url,))
    if content_md:
        await db.execute(
            "INSERT INTO crawl_fts (site_id, url, title, content_md) VALUES (?, ?, ?, ?)",
            (str(site_id), url, title, content_md[:12000]),
        )


async def crawl_site(site_id: int) -> int:
    """BFS async sobre `base_url` + subdomínios; indexa páginas no FTS5.

    Respeita `crawl_depth` e fica restrito aos hosts permitidos (base + subdomínios).
    Retorna o número de páginas novas ou atualizadas.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT * FROM crawl_sites WHERE id = ?", (site_id,)
        )).fetchone()
    if not row:
        raise ValueError(f"Site {site_id} não encontrado")

    # Índices: id(0) base_url(1) label(2) crawl_depth(3) subdomains_json(4)
    base_url: str         = row[1]
    max_depth: int        = row[3]
    subdomains: list[str] = json.loads(row[4] or "[]")

    allowed_hosts: set[str] = {urlparse(base_url).netloc}
    for sub in subdomains:
        allowed_hosts.add(urlparse(sub).netloc)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE crawl_sites SET status='crawling' WHERE id=?", (site_id,)
        )
        await db.commit()

    sem = asyncio.Semaphore(_CRAWL_CONCURRENCY)
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(base_url, 0)])
    pages_saved = 0

    async def _process_url(
        client: httpx.AsyncClient, url: str, depth: int
    ) -> list[tuple[str, int]]:
        """Baixa, indexa e retorna links novos com depth+1."""
        async with sem:
            html, status = await _fetch_page(client, url)
        if not html:
            return []

        content_md = _cascade_extract(html, url, output_format="markdown")
        t = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        title = t.group(1).strip() if t else urlparse(url).path or url
        chash = _hash(content_md)

        async with aiosqlite.connect(DB_PATH) as db:
            await _upsert_page(db, site_id, url, title, content_md, chash, status, now)
            await db.commit()

        if depth >= max_depth:
            return []
        return [
            (link, depth + 1)
            for link in extract_links(html, url)
            if urlparse(link).netloc in allowed_hosts and link not in visited
        ]

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=_CRAWL_TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AKASHA-crawler/1.0)"},
    ) as client:
        while queue:
            batch: list[tuple[str, int]] = []
            while queue and len(batch) < _CRAWL_CONCURRENCY:
                url, depth = queue.popleft()
                if url in visited:
                    continue
                visited.add(url)
                batch.append((url, depth))

            if not batch:
                continue

            results = await asyncio.gather(
                *(_process_url(client, u, d) for u, d in batch)
            )
            pages_saved += len(batch)

            for new_links in results:
                for link, link_depth in new_links:
                    if link not in visited:
                        queue.append((link, link_depth))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE crawl_sites
               SET status='idle', last_crawled_at=?, page_count=(
                   SELECT COUNT(*) FROM crawl_pages WHERE site_id=?
               )
               WHERE id=?""",
            (now, site_id, site_id),
        )
        await db.commit()

    return pages_saved


# ---------------------------------------------------------------------------
# search_sites
# ---------------------------------------------------------------------------

def _sanitize_fts(query: str) -> str:
    cleaned = re.sub(r'["\'\(\)\*\:\^]', " ", query)
    return " ".join(cleaned.split())


async def search_sites(query: str, max_results: int = 20) -> list:
    """Busca FTS5 em crawl_fts; retorna list[SearchResult] com source='SITES'."""
    from services.web_search import SearchResult

    fts_query = _sanitize_fts(query)
    if not fts_query:
        return []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                """SELECT url, title,
                          snippet(crawl_fts, 3, '', '', '…', 40)
                   FROM crawl_fts
                   WHERE crawl_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, max_results),
            )).fetchall()
        return [
            SearchResult(title=row[1], url=row[0], snippet=row[2], source="SITES")
            for row in rows
        ]
    except Exception as exc:
        log.warning("search_sites FTS erro: %s", exc)
        return []
