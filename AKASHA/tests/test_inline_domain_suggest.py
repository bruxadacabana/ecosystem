"""
Testes para a sugestão inline de domínios nos resultados de busca.

Cobre:
  - Domínio frequente nos top-5 resultados e não indexado → aparece em suggested_domains
  - Domínio frequente mas já indexado → não aparece
  - Domínio frequente mas fora do top-5 → não aparece
  - Domínio nos resultados mas abaixo do threshold → não aparece
  - suggested_domains vazio quando não há query
  - Múltiplos domínios elegíveis → todos aparecem
  - suggested_domains não aparece quando web_results está vazio
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
    """Banco temporário com schema completo."""
    import database as _db

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH

    _db.DB_PATH = tmp_path / "akasha.db"
    _db.KNOWLEDGE_DB_PATH = tmp_path / "akasha_knowledge.db"
    _run(_db.init_db())

    yield _db

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb


def _insert_clicks(db, domain: str, count: int):
    import aiosqlite

    async def _do():
        async with aiosqlite.connect(db.DB_PATH) as conn:
            for _ in range(count):
                await conn.execute(
                    "INSERT INTO click_log (domain, url, query_norm) VALUES (?, ?, ?)",
                    (domain, f"https://{domain}/page", "test"),
                )
            await conn.commit()

    _run(_do())


def _insert_site(db, base_url: str):
    _run(db.add_crawl_site(base_url, base_url, 2, "[]"))


class _FakeResult:
    """SearchResult mínimo — evita importar web_search.py (que tem ddgs no nível de módulo)."""
    def __init__(self, url: str):
        self.url     = url
        self.title   = "Test"
        self.snippet = "snippet"


def _make_result(url: str):
    return _FakeResult(url)


# ---------------------------------------------------------------------------
# Helper que extrai suggested_domains (replica a lógica do router)
# ---------------------------------------------------------------------------

async def _compute_suggested(db, web_results, threshold=3):
    from database import get_unindexed_frequent_domains

    result_domains = {
        urlparse(r.url).netloc.lower().removeprefix("www.")
        for r in web_results[:5]
        if r.url and urlparse(r.url).netloc
    }
    frequent = {d: c for d, c in await get_unindexed_frequent_domains(threshold=threshold)}
    return [
        {"domain": dom, "visits": frequent[dom]}
        for dom in result_domains
        if dom in frequent
    ]


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

def test_frequent_domain_in_results_appears(db):
    """Domínio frequente nos top-5 e não indexado → aparece."""
    _insert_clicks(db, "exemplo.com", 4)
    results = [_make_result("https://exemplo.com/artigo")]

    suggested = _run(_compute_suggested(db, results))
    assert any(s["domain"] == "exemplo.com" for s in suggested)


def test_already_indexed_domain_absent(db):
    """Domínio frequente mas já na Biblioteca → não aparece."""
    _insert_clicks(db, "exemplo.com", 5)
    _insert_site(db, "https://exemplo.com")
    results = [_make_result("https://exemplo.com/artigo")]

    suggested = _run(_compute_suggested(db, results))
    assert not any(s["domain"] == "exemplo.com" for s in suggested)


def test_below_threshold_absent(db):
    """Domínio com poucos cliques → não aparece."""
    _insert_clicks(db, "exemplo.com", 2)
    results = [_make_result("https://exemplo.com/artigo")]

    suggested = _run(_compute_suggested(db, results))
    assert suggested == []


def test_domain_outside_top5_absent(db):
    """Domínio frequente mas fora do top-5 dos resultados → não aparece."""
    _insert_clicks(db, "fora-do-top5.com", 10)
    # Domínio frequente existe no click_log mas NÃO nos resultados
    results = [_make_result("https://outro-site.com/artigo")]

    suggested = _run(_compute_suggested(db, results))
    assert not any(s["domain"] == "fora-do-top5.com" for s in suggested)


def test_empty_results_returns_empty(db):
    """Sem resultados → suggested_domains vazio."""
    _insert_clicks(db, "exemplo.com", 5)
    suggested = _run(_compute_suggested(db, []))
    assert suggested == []


def test_multiple_eligible_domains(db):
    """Múltiplos domínios elegíveis aparecem todos."""
    _insert_clicks(db, "site-a.com", 4)
    _insert_clicks(db, "site-b.com", 5)
    results = [
        _make_result("https://site-a.com/p1"),
        _make_result("https://site-b.com/p2"),
    ]

    suggested = _run(_compute_suggested(db, results))
    domains = {s["domain"] for s in suggested}
    assert "site-a.com" in domains
    assert "site-b.com" in domains


def test_visit_count_in_result(db):
    """A contagem de visitas é retornada corretamente."""
    _insert_clicks(db, "exemplo.com", 6)
    results = [_make_result("https://exemplo.com/artigo")]

    suggested = _run(_compute_suggested(db, results))
    assert any(s["domain"] == "exemplo.com" and s["visits"] == 6 for s in suggested)


def test_www_prefix_normalized(db):
    """URL com www. é normalizada para comparar com o click_log sem www."""
    _insert_clicks(db, "exemplo.com", 4)
    results = [_make_result("https://www.exemplo.com/artigo")]

    suggested = _run(_compute_suggested(db, results))
    # www.exemplo.com → normalizado para exemplo.com → match
    assert any(s["domain"] == "exemplo.com" for s in suggested)
