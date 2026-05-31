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
import httpx
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
    wiki_cited: bool = False  # domínio citado em artigo Wikipedia relevante


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
# SearXNG — backend primário self-hosted (opcional)
# ---------------------------------------------------------------------------

def _get_searxng_url() -> str:
    """Lê akasha.web_search_backend do ecosystem.json. Vazio = SearXNG desabilitado."""
    try:
        from ecosystem_client import get_akasha_config as _gc  # type: ignore
        return ((_gc() or {}).get("web_search_backend", "") or "").rstrip("/")
    except Exception:
        return ""


_FETCH_PAGE_SIZE = 25   # resultados por página no fetch paralelo
_FETCH_SEMAPHORE = asyncio.Semaphore(2)  # máx 2 páginas SearXNG simultâneas


def _parse_searxng_results(raw: list) -> list[SearchResult]:
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("content") or r.get("snippet", ""),
            source="WEB",
            date=r.get("publishedDate") or r.get("published_date"),
        )
        for r in raw
        if r.get("url")
    ]


async def _fetch_searxng(
    query: str,
    max_results: int,
    base_url: str,
    n_pages: int = 1,
    lang: str = "",
) -> list[SearchResult]:
    """Busca via SearXNG JSON API, com suporte a múltiplas páginas em paralelo.

    lang: código ISO 639-1 (ex: "pt", "en"). Vazio = sem restrição de idioma.
    SearXNG aceita o param `language` para filtrar resultados por idioma.
    """
    async def _one_page(client: httpx.AsyncClient, pageno: int) -> list[SearchResult]:
        async with _FETCH_SEMAPHORE:
            try:
                params: dict = {"q": query, "format": "json", "pageno": pageno}
                if lang:
                    params["language"] = lang
                resp = await client.get(
                    f"{base_url}/search",
                    params=params,
                )
                resp.raise_for_status()
                return _parse_searxng_results(resp.json().get("results") or [])
            except Exception:
                return []

    async with httpx.AsyncClient(timeout=8.0) as client:
        pages = await asyncio.gather(*[_one_page(client, i + 1) for i in range(n_pages)])

    combined: list[SearchResult] = []
    for page in pages:
        combined.extend(page)
    return combined[:max_results] if max_results > 0 else combined


# ---------------------------------------------------------------------------
# DuckDuckGo
# ---------------------------------------------------------------------------

async def _fetch_ddg(query: str, max_results: int) -> list[SearchResult]:
    # DDG não suporta paginação explícita — aumentar max_results coleta mais resultados
    # internamente (a biblioteca faz várias requisições conforme necessário).
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
# Camada de busca — SearXNG primeiro, DDG como fallback
# ---------------------------------------------------------------------------

async def _fetch_web(
    query: str,
    max_results: int,
    n_pages: int = 1,
    lang: str = "",
) -> list[SearchResult]:
    """Tenta SearXNG (com n_pages paralelas); se indisponível ou vazio, cai para DDG.

    Fallover automático em dois estágios:
      1. SearXNG self-hosted (se akasha.web_search_backend configurado)
         → fetcha n_pages em paralelo via asyncio.gather + Semaphore(2)
      2. DuckDuckGo (sempre disponível como fallback)
         → aumenta max_results para n_pages × _FETCH_PAGE_SIZE
    """
    searxng_url = _get_searxng_url()
    if searxng_url:
        try:
            results = await _fetch_searxng(query, max_results, searxng_url, n_pages=n_pages, lang=lang)
            if results:
                return results
        except Exception:
            pass  # fallover para DDG
    # DDG: não suporta filtro de idioma de forma confiável — usa query original
    return await _fetch_ddg(query, max_results)


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------

_CACHE_SIZE = 100  # max resultados a cachear por query


async def _fetch_searxng_images(query: str, max: int, base_url: str) -> list[dict]:
    """Busca imagens via SearXNG JSON API com categories=images.

    Campos do resultado SearXNG para imagens:
      img_src / thumbnail_src — URL direta da imagem
      url                     — página de origem
      title                   — descrição / alt text
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{base_url}/search",
                params={"q": query, "format": "json", "categories": "images"},
            )
            resp.raise_for_status()
            items = resp.json().get("results") or []
    except Exception:
        return []

    results: list[dict] = []
    for r in items:
        img_url = r.get("img_src") or r.get("thumbnail_src") or r.get("thumbnail") or ""
        page_url = r.get("url", "")
        if not img_url:
            continue
        results.append({
            "img_url":  img_url,
            "page_url": page_url,
            "alt_text": r.get("title", ""),
            "title":    r.get("title", ""),
        })
        if len(results) >= max:
            break
    return results


async def search_images_web(query: str, max: int = 20) -> list[dict]:
    """Busca imagens via SearXNG (se configurado) ou DDG Images como fallback.

    Retorna lista de dicts com: img_url, page_url, alt_text, title.
    Silenciosa em caso de falha — retorna [].

    Prioridade:
      1. SearXNG com categories=images (se akasha.web_search_backend configurado)
      2. DDG Images API
    """
    searxng_url = _get_searxng_url()
    if searxng_url:
        try:
            results = await _fetch_searxng_images(query, max, searxng_url)
            if results:
                return results
        except Exception:
            pass

    try:
        raw = await asyncio.to_thread(
            lambda: list(DDGS().images(query, max_results=max))
        )
        return [
            {
                "img_url":  r.get("image", ""),
                "page_url": r.get("url", ""),
                "alt_text": r.get("title", ""),
                "title":    r.get("title", ""),
            }
            for r in raw
            if r.get("image")
        ][:max]
    except Exception:
        return []


async def search_web(
    query: str,
    max_results: int = 0,
    offset: int = 0,
    filetype: str = "",
    n_pages: int = 1,
    lang: str = "",
) -> list[SearchResult]:
    """Busca web com cache dois níveis (memória LRU + SQLite TTL variável).

    Pipeline:
    1. Verifica cache de memória (TTL por entrada)
    2. Verifica cache SQLite (query_hash + cached_at + ttl_hours)
    3. Executa busca SearXNG/DDG com n_pages páginas paralelas
    4. Armazena em memória + SQLite

    max_results: 0 = retorna todos os resultados disponíveis (sem teto).
    n_pages: número de páginas a buscar em paralelo (default 1; configurado pelo router).
    filetype: acrescenta "filetype:{ext}" à query efetiva se não vazio.
    lang: código ISO 639-1 (ex: "pt", "en"). Vazio = sem restrição de idioma.
         Incluído na chave de cache para que buscas com filtros distintos sejam independentes.
    """
    effective_query = f"{query} filetype:{filetype}" if filetype else query
    # Inclui lang na chave de cache: "python::lang=pt" ≠ "python::lang=en" ≠ "python"
    cache_key = f"{effective_query}::lang={lang}" if lang else effective_query
    qhash = _query_hash(cache_key)
    _fetch_max = min(_CACHE_SIZE, n_pages * _FETCH_PAGE_SIZE)

    def _slice(results: list[SearchResult]) -> list[SearchResult]:
        sliced = results[offset:]
        return sliced if max_results == 0 else sliced[:max_results]

    # 1. Cache de memória
    cached = _mem_cache.get(qhash)
    if cached is not None:
        return _slice(await _filter_blocked(cached))

    # 2. Cache SQLite
    db_cached = await _get_db_cache(qhash)
    if db_cached is not None:
        ttl_hours = await _get_ttl_hours(effective_query)
        _mem_cache.set(qhash, db_cached, ttl_hours * 3600)
        return _slice(await _filter_blocked(db_cached))

    # 3. Busca real — SearXNG (n_pages paralelas) → DDG
    results = await _fetch_web(effective_query, _fetch_max, n_pages=n_pages, lang=lang)
    results = _deduplicate(results)

    # 4. Armazena em ambas as camadas
    ttl_hours = await _get_ttl_hours(effective_query)
    _mem_cache.set(qhash, results, ttl_hours * 3600)
    await _set_db_cache(cache_key, qhash, results, ttl_hours)

    return _slice(await _filter_blocked(results))
