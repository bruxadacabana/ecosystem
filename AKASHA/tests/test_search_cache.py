"""
Testes para o cache dois níveis em services/web_search.py.

Cobre:
  - _MemCache: get/set/expiração/LRU/clear
  - _get_db_cache / _set_db_cache: armazenamento e expiração no SQLite
  - _get_ttl_hours: frequência ≥3/semana → 24h, demais → 1h
  - search_web: segunda busca retorna do cache sem chamar _fetch_ddg;
                expiração → re-busca com chamada a _fetch_ddg
"""
from __future__ import annotations

import asyncio
import time

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture: DB completo
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_paths(tmp_path):
    import database as _db

    main_path = tmp_path / "akasha.db"
    knowledge_path = tmp_path / "akasha_knowledge.db"

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH
    _db.DB_PATH           = main_path
    _db.KNOWLEDGE_DB_PATH = knowledge_path

    import config as _cfg
    orig_cfg_db = _cfg.DB_PATH
    _cfg.DB_PATH = main_path

    run(_db.init_db())

    yield main_path, knowledge_path

    _db.DB_PATH           = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb
    _cfg.DB_PATH          = orig_cfg_db


@pytest.fixture()
def patched_db(db_paths, monkeypatch):
    main_path, _ = db_paths
    import services.web_search as _ws
    monkeypatch.setattr(_ws, "DB_PATH", main_path)
    _ws._mem_cache.clear()  # garante cache limpo entre testes
    yield main_path
    _ws._mem_cache.clear()


# ---------------------------------------------------------------------------
# Testes unitários do _MemCache
# ---------------------------------------------------------------------------

def test_mem_cache_miss():
    from services.web_search import _MemCache
    c = _MemCache()
    assert c.get("absent") is None


def test_mem_cache_hit():
    from services.web_search import _MemCache
    c = _MemCache()
    c.set("k", [1, 2, 3], ttl_s=3600)
    assert c.get("k") == [1, 2, 3]


def test_mem_cache_expiry():
    from services.web_search import _MemCache
    c = _MemCache()
    c.set("k", [1], ttl_s=0)  # TTL=0 → expira imediatamente
    assert c.get("k") is None


def test_mem_cache_lru_eviction():
    from services.web_search import _MemCache
    c = _MemCache(maxsize=2)
    c.set("a", [1], ttl_s=3600)
    c.set("b", [2], ttl_s=3600)
    c.set("c", [3], ttl_s=3600)  # evicta "a" (LRU)
    assert c.get("a") is None
    assert c.get("b") == [2]
    assert c.get("c") == [3]


def test_mem_cache_lru_access_updates_order():
    """Acessar 'a' promove ao topo; 'b' é evictado quando 'c' entra."""
    from services.web_search import _MemCache
    c = _MemCache(maxsize=2)
    c.set("a", [1], ttl_s=3600)
    c.set("b", [2], ttl_s=3600)
    c.get("a")                   # acessa 'a', move para topo
    c.set("c", [3], ttl_s=3600)  # evicta 'b' (LRU agora)
    assert c.get("a") == [1]
    assert c.get("b") is None
    assert c.get("c") == [3]


# ---------------------------------------------------------------------------
# Testes do _query_hash
# ---------------------------------------------------------------------------

def test_query_hash_deterministic():
    from services.web_search import _query_hash
    assert _query_hash("python") == _query_hash("python")


def test_query_hash_distinct():
    from services.web_search import _query_hash
    assert _query_hash("python") != _query_hash("javascript")


# ---------------------------------------------------------------------------
# Testes do cache SQLite
# ---------------------------------------------------------------------------

def test_db_cache_miss(patched_db):
    from services.web_search import _get_db_cache, _query_hash

    async def _run():
        return await _get_db_cache(_query_hash("never cached query xyz"))

    assert run(_run()) is None


def test_db_cache_hit(patched_db):
    from services.web_search import (
        _get_db_cache, _set_db_cache, _query_hash, SearchResult,
    )

    results = [SearchResult(title="A", url="https://a.com", snippet="s")]

    async def _run():
        qh = _query_hash("my query")
        await _set_db_cache("my query", qh, results, ttl_hours=1)
        return await _get_db_cache(qh)

    cached = run(_run())
    assert cached is not None
    assert cached[0].url == "https://a.com"


def test_db_cache_expiry(patched_db, monkeypatch):
    """Entrada expirada não é retornada."""
    import aiosqlite
    from services.web_search import _get_db_cache, _query_hash, SearchResult

    results = [SearchResult(title="B", url="https://b.com", snippet="")]

    async def _run():
        import services.web_search as _ws
        qh = _query_hash("expired query")
        ts_expired = int(time.time()) - 7200  # inserido há 2h com TTL=1h → expirado
        async with aiosqlite.connect(patched_db) as db:
            await db.execute(
                "INSERT INTO search_cache (query, sources, results_json, query_hash, cached_at, ttl_hours) "
                "VALUES (?, 'web', ?, ?, ?, ?)",
                ("expired query",
                 __import__("json").dumps([r.model_dump() for r in results]),
                 qh, ts_expired, 1),
            )
            await db.commit()
        return await _get_db_cache(qh)

    assert run(_run()) is None


# ---------------------------------------------------------------------------
# Testes do TTL dinâmico
# ---------------------------------------------------------------------------

def test_ttl_low_frequency(patched_db):
    """Query com <3 buscas na semana → TTL 1h."""
    from services.web_search import _get_ttl_hours

    async def _run():
        return await _get_ttl_hours("rare query")

    assert run(_run()) == 1


def test_ttl_high_frequency(patched_db):
    """Query com ≥3 buscas na semana → TTL 24h."""
    import aiosqlite
    from services.web_search import _get_ttl_hours

    async def _run():
        async with aiosqlite.connect(patched_db) as db:
            for _ in range(3):
                await db.execute(
                    "INSERT INTO searches (query, sources, result_count) VALUES (?, 'web', 5)",
                    ("popular query",),
                )
            await db.commit()
        return await _get_ttl_hours("popular query")

    assert run(_run()) == 24


# ---------------------------------------------------------------------------
# Testes end-to-end de search_web (com mock de _fetch_ddg)
# ---------------------------------------------------------------------------

def test_search_web_cache_hit_no_refetch(patched_db, monkeypatch):
    """Segunda busca retorna do cache sem chamar _fetch_ddg."""
    import services.web_search as _ws
    from services.web_search import SearchResult

    call_count = {"n": 0}

    # Mocka _fetch_web (ponto de despacho SearXNG/DDG) — robusto ao backend configurado.
    async def _mock_fetch(query, max_results, n_pages=1, lang=""):
        call_count["n"] += 1
        return [SearchResult(title="R", url="https://r.com", snippet="")]

    async def _mock_blocked():
        return []

    monkeypatch.setattr(_ws, "_fetch_web", _mock_fetch)
    monkeypatch.setattr(_ws, "get_blocked_domains", _mock_blocked)

    async def _run():
        r1 = await _ws.search_web("test query")
        r2 = await _ws.search_web("test query")
        return r1, r2, call_count["n"]

    r1, r2, n_calls = run(_run())
    assert n_calls == 1         # DDG chamado apenas 1 vez
    assert r1 == r2             # ambas as buscas retornam os mesmos resultados


def test_search_web_expired_cache_refetches(patched_db, monkeypatch):
    """Cache expirado → nova chamada a _fetch_ddg."""
    import aiosqlite
    import json
    import services.web_search as _ws
    from services.web_search import SearchResult, _query_hash

    call_count = {"n": 0}

    async def _mock_fetch(query, max_results, n_pages=1, lang=""):
        call_count["n"] += 1
        return [SearchResult(title="Fresh", url="https://fresh.com", snippet="")]

    async def _mock_blocked():
        return []

    monkeypatch.setattr(_ws, "_fetch_web", _mock_fetch)
    monkeypatch.setattr(_ws, "get_blocked_domains", _mock_blocked)

    async def _run():
        # Insere entrada expirada no SQLite (2h atrás, TTL=1h).
        # A chave deve espelhar o formato do search_web: "<q>::lang=::p=<n_pages>".
        qh = _query_hash("expired search::lang=::p=1")
        ts_expired = int(time.time()) - 7200
        old_results = [SearchResult(title="Old", url="https://old.com", snippet="")]
        async with aiosqlite.connect(patched_db) as db:
            await db.execute(
                "INSERT INTO search_cache (query, sources, results_json, query_hash, cached_at, ttl_hours) "
                "VALUES (?, 'web', ?, ?, ?, ?)",
                ("expired search", json.dumps([r.model_dump() for r in old_results]),
                 qh, ts_expired, 1),
            )
            await db.commit()

        result = await _ws.search_web("expired search")
        return result, call_count["n"]

    result, n_calls = run(_run())
    assert n_calls == 1                         # re-buscou
    assert result[0].url == "https://fresh.com"  # retornou resultado novo


# ---------------------------------------------------------------------------
# BUG-025: a chave de cache deve incluir n_pages
# (buscas leves de 1 página não podem envenenar o cache das de 10 páginas)
# ---------------------------------------------------------------------------

def _patch_fetch_web(monkeypatch):
    """Substitui _fetch_web por um mock que devolve n_pages resultados distintos
    e registra os n_pages com que foi chamado. Isola o teste do backend real."""
    import services.web_search as _ws
    from services.web_search import SearchResult

    calls: list[int] = []

    async def _mock_fetch_web(query, max_results, n_pages=1, lang=""):
        calls.append(n_pages)
        return [
            SearchResult(title=f"r{i}", url=f"https://d{i}.example", snippet="")
            for i in range(n_pages)
        ]

    async def _mock_blocked():
        return []

    monkeypatch.setattr(_ws, "_fetch_web", _mock_fetch_web)
    monkeypatch.setattr(_ws, "get_blocked_domains", _mock_blocked)
    return calls


def test_cache_separates_by_n_pages(patched_db, monkeypatch):
    """n_pages diferentes NÃO compartilham cache: cada um re-busca e mantém seu volume."""
    import services.web_search as _ws
    calls = _patch_fetch_web(monkeypatch)

    async def _run():
        r1  = await _ws.search_web("mesma query", max_results=0, n_pages=1)
        r10 = await _ws.search_web("mesma query", max_results=0, n_pages=10)
        return r1, r10

    r1, r10 = run(_run())
    assert calls == [1, 10]      # ambas buscaram — sem cache compartilhado
    assert len(r1) == 1          # n_pages=1 → 1 resultado
    assert len(r10) == 10        # n_pages=10 → 10 (NÃO os 1 do cache anterior)


def test_cache_n_pages_one_does_not_poison_ten(patched_db, monkeypatch):
    """Reproduz o BUG-025: busca leve (1 página) ANTES não deve limitar a de 10."""
    import services.web_search as _ws
    _patch_fetch_web(monkeypatch)

    async def _run():
        await _ws.search_web("craftivism", max_results=0, n_pages=1)   # leve, primeiro
        full = await _ws.search_web("craftivism", max_results=0, n_pages=10)  # real
        return full

    full = run(_run())
    assert len(full) == 10       # antes do fix retornava 1 (cache envenenado)


def test_cache_same_n_pages_hits_cache(patched_db, monkeypatch):
    """Mesmo n_pages: segunda busca vem do cache (uma só chamada a _fetch_web)."""
    import services.web_search as _ws
    calls = _patch_fetch_web(monkeypatch)

    async def _run():
        r1 = await _ws.search_web("repetida", max_results=0, n_pages=10)
        r2 = await _ws.search_web("repetida", max_results=0, n_pages=10)
        return r1, r2

    r1, r2 = run(_run())
    assert calls == [10]         # só a primeira buscou; a segunda foi cache
    assert [x.url for x in r1] == [x.url for x in r2]


def test_cache_separates_by_lang(patched_db, monkeypatch):
    """lang diferente continua separando o cache (regressão do comportamento prévio)."""
    import services.web_search as _ws
    calls = _patch_fetch_web(monkeypatch)

    async def _run():
        await _ws.search_web("q", max_results=0, n_pages=5, lang="pt")
        await _ws.search_web("q", max_results=0, n_pages=5, lang="en")
        return calls

    out = run(_run())
    assert out == [5, 5]         # lang distinto → ambas buscaram
