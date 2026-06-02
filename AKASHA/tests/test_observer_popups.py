"""
Testes para services/observer_popups.py — pop-ups proativos da Akasha observadora.

Cobre (item 1 — zona morta de busca):
  - check_search_dead_ends: query repetida sem cliques locais + domínios web → sugestão criada
  - query com cliques locais suficientes → sem sugestão
  - cooldown: query sugerida recentemente → não re-sugerida
  - sem domínios web fora da Biblioteca → sem sugestão
  - query antiga (> 7 dias) → não é candidata
  - get_next_for_overlay inclui entradas search_dead_end
  - _get_library_domains: extrai netloc normalizado de crawl_sites
  - _get_domain_suggestions_for_query: filtra Biblioteca e deduplica
  - _apply_insight_confirmation_action: confirmar search_dead_end adiciona domínios à Biblioteca
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ddgs pode faltar no Python do sistema — guarda-mock (ignorado sob `uv run`)
if "ddgs" not in sys.modules:
    _fake = types.ModuleType("ddgs")
    _fake.DDGS = object  # type: ignore
    sys.modules["ddgs"] = _fake


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture: akasha.db + personal_memory.db isolados
# ---------------------------------------------------------------------------

@pytest.fixture()
def dbs(tmp_path):
    import database as _db
    import services.personal_memory as _pm
    import services.observer_popups as _obs

    pm_path = tmp_path / "personal_memory.db"

    orig_db   = _db.DB_PATH
    orig_kdb  = _db.KNOWLEDGE_DB_PATH
    orig_get  = _pm._get_pm_db
    orig_obs  = _obs.DB_PATH

    _db.DB_PATH = tmp_path / "akasha.db"
    _db.KNOWLEDGE_DB_PATH = tmp_path / "akasha_knowledge.db"
    _pm._get_pm_db = lambda: pm_path
    _obs.DB_PATH = _db.DB_PATH

    _run(_db.init_db())
    _run(_pm.init_pm_db())

    yield _db, pm_path

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb
    _pm._get_pm_db = orig_get
    _obs.DB_PATH = orig_obs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_search(db, query: str, count: int, days_ago: int = 0):
    con = sqlite3.connect(str(db.DB_PATH))
    con.execute(
        "INSERT OR REPLACE INTO search_history (query, count, last_used) "
        "VALUES (?, ?, datetime('now', ?))",
        (query, count, f"-{days_ago} days"),
    )
    con.commit()
    con.close()


def _insert_clicks(db, domain: str, query_norm: str, count: int = 1):
    con = sqlite3.connect(str(db.DB_PATH))
    for _ in range(count):
        con.execute(
            "INSERT INTO click_log (domain, url, query_norm) VALUES (?, ?, ?)",
            (domain, f"https://{domain}/page", query_norm),
        )
    con.commit()
    con.close()


def _insert_site(db, base_url: str):
    _run(db.add_crawl_site(base_url, base_url, 2, "[]"))


def _pm_entries(pm_db: Path) -> list[dict]:
    con = sqlite3.connect(str(pm_db))
    rows = con.execute("SELECT type, tags, content FROM personal_memory").fetchall()
    con.close()
    return [{"type": r[0], "tags": json.loads(r[1] or "[]"), "content": r[2]} for r in rows]


class _R:
    def __init__(self, url: str):
        self.url = url


def _mock_web(domains: list[str]):
    return AsyncMock(return_value=[_R(f"https://{d}/article") for d in domains])


# ---------------------------------------------------------------------------
# check_search_dead_ends
# ---------------------------------------------------------------------------

def test_dead_end_creates_suggestion(dbs):
    db, pm_db = dbs
    _insert_search(db, "craftivism history", count=4)

    import services.observer_popups as obs
    with patch("services.web_search.search_web", _mock_web(["craftblog.net", "indiezine.org"])):
        n = _run(obs.check_search_dead_ends())

    assert n == 1
    entries = _pm_entries(pm_db)
    assert len(entries) == 1
    assert entries[0]["type"] == "search_dead_end"
    assert "craftivism history" in entries[0]["tags"]
    assert "craftblog.net" in entries[0]["tags"]
    assert "indiezine.org" in entries[0]["tags"]


def test_enough_local_clicks_no_suggestion(dbs):
    db, pm_db = dbs
    from services.click_log import _normalize_query
    q = "amigurumi patterns"
    qnorm = _normalize_query(q)
    _insert_search(db, q, count=5)
    _insert_site(db, "https://yarnspirations.com")
    # 3 cliques locais (domínio na Biblioteca) > max_local_clicks (1)
    _insert_clicks(db, "yarnspirations.com", qnorm, count=3)

    import services.observer_popups as obs
    with patch("services.web_search.search_web", _mock_web(["x.com"])):
        n = _run(obs.check_search_dead_ends())

    assert n == 0
    assert _pm_entries(pm_db) == []


def test_cooldown_blocks_resuggest(dbs):
    db, pm_db = dbs
    import services.personal_memory as _pm
    q = "zine making"
    _insert_search(db, q, count=3)
    # sugestão prévia recente para a mesma query
    _run(_pm.save_memory(
        type="search_dead_end", content="prévia",
        tags=["search_dead_end", q, "old.net"], importance=6,
    ))

    import services.observer_popups as obs
    with patch("services.web_search.search_web", _mock_web(["novo.org"])):
        n = _run(obs.check_search_dead_ends())

    assert n == 0
    # continua só a entrada prévia
    assert len(_pm_entries(pm_db)) == 1


def test_no_web_domains_no_suggestion(dbs):
    db, pm_db = dbs
    _insert_search(db, "obscure topic", count=3)
    _insert_site(db, "https://jaindexado.com")

    import services.observer_popups as obs
    # search_web só devolve domínio já na Biblioteca → nada a sugerir
    with patch("services.web_search.search_web", _mock_web(["jaindexado.com"])):
        n = _run(obs.check_search_dead_ends())

    assert n == 0
    assert _pm_entries(pm_db) == []


def test_old_search_not_candidate(dbs):
    db, pm_db = dbs
    _insert_search(db, "stale query", count=10, days_ago=30)  # fora da janela de 7 dias

    import services.observer_popups as obs
    with patch("services.web_search.search_web", _mock_web(["a.com"])):
        n = _run(obs.check_search_dead_ends())

    assert n == 0


def test_below_threshold_not_candidate(dbs):
    db, pm_db = dbs
    _insert_search(db, "rare query", count=2)  # < threshold 3

    import services.observer_popups as obs
    with patch("services.web_search.search_web", _mock_web(["a.com"])):
        n = _run(obs.check_search_dead_ends())

    assert n == 0


# ---------------------------------------------------------------------------
# Integração com personal_memory / overlay
# ---------------------------------------------------------------------------

def test_get_next_for_overlay_includes_dead_end(dbs):
    db, pm_db = dbs
    import services.personal_memory as _pm
    _run(_pm.save_memory(
        type="search_dead_end", content="overlay test",
        tags=["search_dead_end", "q", "dom.com"], importance=8,
    ))
    candidates = _run(_pm.get_next_for_overlay(10))
    assert any(c["type"] == "search_dead_end" for c in candidates)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def test_library_domains_extraction(dbs):
    db, _ = dbs
    _insert_site(db, "https://www.exemplo.com")
    _insert_site(db, "https://outro.org")

    import services.observer_popups as obs
    domains = _run(obs._get_library_domains())
    assert "exemplo.com" in domains   # www. removido
    assert "outro.org" in domains


def test_domain_suggestions_filters_library_and_dedups(dbs):
    db, _ = dbs
    _insert_site(db, "https://indexado.com")

    import services.observer_popups as obs
    with patch(
        "services.web_search.search_web",
        _mock_web(["indexado.com", "novo.net", "novo.net", "outro.org"]),
    ):
        out = _run(obs._get_domain_suggestions_for_query("q", max_suggestions=5))

    assert "indexado.com" not in out      # filtrado (já na Biblioteca)
    assert out.count("novo.net") == 1     # deduplicado
    assert "outro.org" in out


# ---------------------------------------------------------------------------
# Ação de confirmação (routers/search.py)
# ---------------------------------------------------------------------------

def test_confirm_adds_domains_to_library(dbs):
    db, _ = dbs

    async def _go():
        from routers import search as _search
        entry = {
            "type": "search_dead_end",
            "tags": ["search_dead_end", "craftivism history", "blog-a.net", "blog-b.org"],
        }
        with patch.object(_search, "_bg_crawl_site", AsyncMock()):
            await _search._apply_insight_confirmation_action(entry)
        await asyncio.sleep(0)  # drena tasks agendadas

    _run(_go())

    con = sqlite3.connect(str(db.DB_PATH))
    rows = [r[0] for r in con.execute(
        "SELECT base_url FROM crawl_sites WHERE deleted = 0"
    ).fetchall()]
    con.close()
    assert any("blog-a.net" in u for u in rows)
    assert any("blog-b.org" in u for u in rows)
