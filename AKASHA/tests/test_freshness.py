"""
Testes para services/freshness.py.

Cobre:
  - is_temporal_query: detecção de termos temporais
  - _days_since: parsing de float string e ISO datetime
  - freshness_factor: fórmula e casos especiais (None → 1.0)
  - apply_freshness_rerank: query temporal reordena por frescor; sem dados → sem mudança
  - get_dates_for_urls: lookup em local_index_meta e crawl_pages
"""
from __future__ import annotations

import asyncio
import math
import time
from pathlib import Path

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture: DB completo com schema AKASHA
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
    import services.freshness as _fr
    monkeypatch.setattr(_fr, "DB_PATH", main_path)
    return main_path


# ---------------------------------------------------------------------------
# is_temporal_query
# ---------------------------------------------------------------------------

def test_temporal_query_hoje():
    from services.freshness import is_temporal_query
    assert is_temporal_query("noticias de hoje") is True


def test_temporal_query_latest():
    from services.freshness import is_temporal_query
    assert is_temporal_query("latest python release") is True


def test_temporal_query_year():
    from services.freshness import is_temporal_query
    assert is_temporal_query("novidades 2026") is True


def test_non_temporal_query():
    from services.freshness import is_temporal_query
    assert is_temporal_query("machine learning tutorial") is False


def test_non_temporal_query_definition():
    from services.freshness import is_temporal_query
    assert is_temporal_query("o que é recursão") is False


# ---------------------------------------------------------------------------
# _days_since
# ---------------------------------------------------------------------------

def test_days_since_empty():
    from services.freshness import _days_since
    assert _days_since("") is None


def test_days_since_float_timestamp():
    from services.freshness import _days_since
    ts_7_days_ago = str(time.time() - 7 * 86400)
    result = _days_since(ts_7_days_ago)
    assert result is not None
    assert abs(result - 7.0) < 0.01


def test_days_since_iso_datetime():
    from services.freshness import _days_since
    # 30 days ago in ISO format
    from datetime import datetime, timezone, timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=30)
    result = _days_since(dt.strftime("%Y-%m-%d %H:%M:%S"))
    assert result is not None
    assert abs(result - 30.0) < 0.1


def test_days_since_invalid():
    from services.freshness import _days_since
    assert _days_since("not-a-date") is None


def test_days_since_zero():
    """Timestamp de agora → 0 dias."""
    from services.freshness import _days_since
    ts_now = str(time.time())
    result = _days_since(ts_now)
    assert result is not None
    assert result < 0.01


# ---------------------------------------------------------------------------
# freshness_factor
# ---------------------------------------------------------------------------

def test_freshness_factor_none():
    """Sem data → fator neutro 1.0."""
    from services.freshness import freshness_factor
    assert freshness_factor(None) == pytest.approx(1.0)


def test_freshness_factor_today():
    """Publicado hoje (0 dias) → 1.0."""
    from services.freshness import freshness_factor
    assert freshness_factor(0.0) == pytest.approx(1.0)


def test_freshness_factor_one_year():
    """Publicado há 365 dias → fator < 0.2."""
    from services.freshness import freshness_factor
    f = freshness_factor(365.0)
    expected = 1.0 / (1.0 + math.log(1.0 + 365.0))
    assert f == pytest.approx(expected, rel=1e-6)
    assert f < 0.2


def test_freshness_factor_decreasing():
    """Quanto mais antigo, menor o fator."""
    from services.freshness import freshness_factor
    f_recent = freshness_factor(1.0)
    f_old    = freshness_factor(365.0)
    assert f_recent > f_old


# ---------------------------------------------------------------------------
# apply_freshness_rerank
# ---------------------------------------------------------------------------

def _make_result(url: str, title: str = ""):
    from services.web_search import SearchResult
    return SearchResult(title=title or url, url=url, snippet="")


def test_freshness_rerank_temporal_promotes_recent():
    """Com query temporal, resultado recente deve subir no ranking."""
    from services.freshness import apply_freshness_rerank

    # Resultado 1: antigo (posição 0)
    # Resultado 2: recente (posição 1)
    results = [
        _make_result("https://old.com/", "Artigo de 2 anos atrás"),
        _make_result("https://new.com/", "Artigo de ontem"),
    ]

    ts_2yr = str(time.time() - 730 * 86400)
    ts_yesterday = str(time.time() - 1 * 86400)
    date_map = {
        "https://old.com/": ts_2yr,
        "https://new.com/": ts_yesterday,
    }

    reranked = apply_freshness_rerank(results, date_map, w_freshness=0.9)

    # O resultado recente (new.com) deve estar na primeira posição
    assert reranked[0].url == "https://new.com/"


def test_freshness_rerank_no_dates_unchanged():
    """Sem dados de data → lista original inalterada."""
    from services.freshness import apply_freshness_rerank

    results = [_make_result(f"https://a{i}.com/") for i in range(3)]
    original_urls = [r.url for r in results]

    reranked = apply_freshness_rerank(results, {})  # sem datas → has_real_dates=False
    assert [r.url for r in reranked] == original_urls


def test_freshness_rerank_empty_list():
    """Lista vazia → retorna lista vazia."""
    from services.freshness import apply_freshness_rerank
    assert apply_freshness_rerank([], {}) == []


def test_freshness_rerank_no_real_dates_unchanged():
    """Datas vazias (como '') → sem reordenação."""
    from services.freshness import apply_freshness_rerank

    results = [
        _make_result("https://a.com/"),
        _make_result("https://b.com/"),
    ]
    date_map = {"https://a.com/": "", "https://b.com/": ""}  # ambas vazias

    reranked = apply_freshness_rerank(results, date_map)
    assert [r.url for r in reranked] == ["https://a.com/", "https://b.com/"]


# ---------------------------------------------------------------------------
# get_dates_for_urls (integração com DB)
# ---------------------------------------------------------------------------

def test_get_dates_file_url(patched_db, tmp_path):
    """file:// URL com mtime em local_index_meta → retorna mtime."""
    import aiosqlite
    from pathlib import Path as _Path

    fake_path = str(tmp_path / "note.md")
    mtime_str = str(time.time() - 10 * 86400)  # 10 dias atrás

    async def _run():
        async with aiosqlite.connect(patched_db) as db:
            await db.execute(
                "INSERT INTO local_index_meta (path, source, mtime) VALUES (?, ?, ?)",
                (fake_path, "AKASHA", mtime_str),
            )
            await db.commit()

        file_url = _Path(fake_path).as_uri()
        from services.freshness import get_dates_for_urls
        return await get_dates_for_urls([file_url])

    result = run(_run())
    file_url = Path(fake_path).as_uri()
    assert file_url in result
    assert float(result[file_url]) == pytest.approx(float(mtime_str), rel=1e-6)


def test_get_dates_http_url(patched_db):
    """https:// URL com last_modified_at em crawl_pages → retorna data."""
    import aiosqlite

    page_url = "https://example.com/article"
    last_mod = "2026-01-01 00:00:00"

    async def _run():
        async with aiosqlite.connect(patched_db) as db:
            # Primeiro precisamos de um crawl_site pai
            await db.execute(
                "INSERT INTO crawl_sites (base_url) VALUES (?)",
                ("https://example.com",),
            )
            site_id = (await (await db.execute(
                "SELECT id FROM crawl_sites WHERE base_url = ?",
                ("https://example.com",),
            )).fetchone())[0]
            await db.execute(
                "INSERT INTO crawl_pages (site_id, url, last_modified_at) VALUES (?, ?, ?)",
                (site_id, page_url, last_mod),
            )
            await db.commit()

        from services.freshness import get_dates_for_urls
        return await get_dates_for_urls([page_url])

    result = run(_run())
    assert result.get(page_url) == last_mod


def test_get_dates_unknown_url(patched_db):
    """URL sem registro no banco → não aparece no dict."""
    async def _run():
        from services.freshness import get_dates_for_urls
        return await get_dates_for_urls(["https://unknown.example.com/page"])

    result = run(_run())
    assert "https://unknown.example.com/page" not in result
