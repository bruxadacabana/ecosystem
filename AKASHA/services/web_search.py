"""
AKASHA — Busca web via DuckDuckGo
Cache em SQLite com TTL de 1h; deduplicação por URL normalizada.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import asyncio
from urllib.parse import urlparse

import aiosqlite
from ddgs import DDGS
from pydantic import BaseModel

from config import DB_PATH
from database import get_blocked_domains

# ---------------------------------------------------------------------------
# Modelo de resultado
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source: str = "WEB"
    date: str | None = None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_TTL = 3600  # segundos


def _cutoff_str() -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=_CACHE_TTL)
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")


async def _get_cached(query: str) -> list[SearchResult] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            """SELECT results_json FROM search_cache
               WHERE query = ? AND sources = 'web' AND created_at > ?
               ORDER BY id DESC LIMIT 1""",
            (query, _cutoff_str()),
        )).fetchone()
    if row:
        return [SearchResult(**r) for r in json.loads(row[0])]
    return None


async def _set_cache(query: str, results: list[SearchResult]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO search_cache (query, sources, results_json) VALUES (?, 'web', ?)",
            (query, json.dumps([r.model_dump() for r in results])),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Deduplicação
# ---------------------------------------------------------------------------

def _normalize(url: str) -> str:
    return url.rstrip("/").lower()


def _hostname(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.").lower()


async def _filter_blocked(results: list[SearchResult]) -> list[SearchResult]:
    blocked = await get_blocked_domains()
    if not blocked:
        return results
    return [r for r in results if _hostname(r.url) not in blocked]


def _deduplicate(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        key = _normalize(r.url)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# DuckDuckGo
# ---------------------------------------------------------------------------

async def _fetch_ddg(query: str, max_results: int) -> list[SearchResult]:
    try:
        raw = await asyncio.to_thread(
            lambda: list(DDGS().text(query, max_results=max_results))
        )
    except Exception as exc:
        raise RuntimeError(f"Falha na busca DuckDuckGo: {exc}") from exc
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("href", ""),
            snippet=r.get("body", ""),
            source="WEB",
        )
        for r in raw
        if r.get("href")
    ]


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------

_CACHE_SIZE = 60  # resultados pré-buscados por query — serve até 6 páginas de 10


async def search_web(query: str, max_results: int = 10, offset: int = 0) -> list[SearchResult]:
    """Busca via DuckDuckGo com cache TTL 1h e deduplicação por URL.

    Pré-busca _CACHE_SIZE resultados no primeiro acesso; páginas seguintes
    (offset > 0) servem do mesmo lote em cache sem re-consultar o DDG,
    evitando resultados repetidos ou inconsistências de paginação.
    """
    cached = await _get_cached(query)
    if cached is not None:
        return (await _filter_blocked(cached))[offset : offset + max_results]

    results = await _fetch_ddg(query, _CACHE_SIZE)
    results = _deduplicate(results)
    await _set_cache(query, results)
    return (await _filter_blocked(results))[offset : offset + max_results]
