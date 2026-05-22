"""
AKASHA — Busca web via DuckDuckGo
Cache dois níveis: memória (LRU, max 100 entradas) + SQLite (TTL variável).
- Queries com ≥3 buscas/semana → TTL 24h; demais → TTL 1h
- Camada transparente: memória → SQLite → DDG
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
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
    score: float = 0.0  # BM25/relevância; 0.0 = não calculado


# ---------------------------------------------------------------------------
# Camada 1 — cache em memória (LRU, max 100 entradas, TTL por entrada)
# ---------------------------------------------------------------------------

class _MemCache:
    """Dict LRU com TTL por entrada. Thread-safe o suficiente para asyncio."""

    def __init__(self, maxsize: int = 100) -> None:
        self._store: OrderedDict[str, tuple[list, float]] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> list | None:
        if key not in self._store:
            return None
        val, expires_at = self._store[key]
        if time.time() >= expires_at:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return val

    def set(self, key: str, val: list, ttl_s: int) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (val, time.time() + ttl_s)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)  # descarta LRU (mais antigo)

    def clear(self) -> None:
        self._store.clear()


_mem_cache = _MemCache(maxsize=100)


def _query_hash(query: str) -> str:
    return hashlib.md5(query.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Camada 2 — cache SQLite (tabela search_cache)
# ---------------------------------------------------------------------------

async def _get_db_cache(query_hash: str) -> list[SearchResult] | None:
    """Busca no cache SQLite. None se expirado ou ausente."""
    ts_now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            """SELECT results_json, cached_at, ttl_hours
               FROM search_cache
               WHERE query_hash = ?""",
            (query_hash,),
        )).fetchone()
    if row is None:
        return None
    results_json, cached_at, ttl_hours = row
    if ts_now > cached_at + ttl_hours * 3600:
        return None  # expirado
    return [SearchResult(**r) for r in json.loads(results_json)]


async def _set_db_cache(
    query: str,
    query_hash: str,
    results: list[SearchResult],
    ttl_hours: int,
) -> None:
    """Armazena no cache SQLite (upsert por query_hash)."""
    ts_now = int(time.time())
    results_json = json.dumps([r.model_dump() for r in results])
    async with aiosqlite.connect(DB_PATH) as db:
        # Delete anterior (se existir) + Insert — simples e seguro com partial UNIQUE INDEX
        await db.execute(
            "DELETE FROM search_cache WHERE query_hash = ?",
            (query_hash,),
        )
        await db.execute(
            """INSERT INTO search_cache
               (query, sources, results_json, query_hash, cached_at, ttl_hours)
               VALUES (?, 'web', ?, ?, ?, ?)""",
            (query, results_json, query_hash, ts_now, ttl_hours),
        )
        await db.commit()


async def _get_ttl_hours(query: str) -> int:
    """Retorna TTL em horas baseado na frequência da query na última semana.

    ≥3 buscas/semana → 24h (query popular, cache mais duradouro).
    Demais → 1h (padrão).
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            row = await (await db.execute(
                """SELECT COUNT(*) FROM searches
                   WHERE query = ?
                   AND created_at > datetime('now', '-7 days')""",
                (query,),
            )).fetchone()
        if row and row[0] >= 3:
            return 24
    except Exception:
        pass
    return 1


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


async def search_web(
    query: str,
    max_results: int = 10,
    offset: int = 0,
    filetype: str = "",
) -> list[SearchResult]:
    """Busca via DuckDuckGo com cache dois níveis (memória LRU + SQLite TTL variável).

    Pipeline:
    1. Verifica cache de memória (TTL por entrada)
    2. Verifica cache SQLite (query_hash + cached_at + ttl_hours)
    3. Executa busca DDG; determina TTL pelo histórico de frequência
    4. Armazena em memória + SQLite

    filetype: acrescenta "filetype:{ext}" à query efetiva se não vazio.
    """
    effective_query = f"{query} filetype:{filetype}" if filetype else query
    qhash = _query_hash(effective_query)

    # 1. Cache de memória
    cached = _mem_cache.get(qhash)
    if cached is not None:
        return (await _filter_blocked(cached))[offset: offset + max_results]

    # 2. Cache SQLite
    db_cached = await _get_db_cache(qhash)
    if db_cached is not None:
        ttl_hours = await _get_ttl_hours(effective_query)
        _mem_cache.set(qhash, db_cached, ttl_hours * 3600)
        return (await _filter_blocked(db_cached))[offset: offset + max_results]

    # 3. Busca real
    results = await _fetch_ddg(effective_query, _CACHE_SIZE)
    results = _deduplicate(results)

    # 4. Armazena em ambas as camadas
    ttl_hours = await _get_ttl_hours(effective_query)
    _mem_cache.set(qhash, results, ttl_hours * 3600)
    await _set_db_cache(effective_query, qhash, results, ttl_hours)

    return (await _filter_blocked(results))[offset: offset + max_results]
