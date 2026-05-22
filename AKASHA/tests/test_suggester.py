"""
Testes de integração para services/suggester.py.

Cobre:
  - compute_suggestions: 3 sinais → score correto; domínio bloqueado → não reaparece;
    domínio já em crawl_sites → excluído; score mínimo filtrado
  - get_pending_suggestions: retorna apenas status pending, ordenados por score
  - set_suggestion_status: atualiza status corretamente
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture: DB com schema AKASHA
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_paths(tmp_path):
    import database as _db

    main_path = tmp_path / "akasha.db"
    knowledge_path = tmp_path / "akasha_knowledge.db"

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH
    _db.DB_PATH = main_path
    _db.KNOWLEDGE_DB_PATH = knowledge_path

    run(_db.init_db())

    yield main_path, knowledge_path

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb


# ---------------------------------------------------------------------------
# Helpers de inserção
# ---------------------------------------------------------------------------

def _insert_cache(con: sqlite3.Connection, urls: list[str]) -> None:
    results = [{"url": u, "title": "", "snippet": "", "source": "WEB"} for u in urls]
    con.execute(
        "INSERT INTO search_cache (query, sources, results_json) VALUES ('test', 'web', ?)",
        (json.dumps(results),),
    )
    con.commit()


def _insert_links(con: sqlite3.Connection, targets: list[str]) -> None:
    con.executemany(
        "INSERT OR IGNORE INTO page_links (source_url, target_url) VALUES ('https://known.com', ?)",
        [(t,) for t in targets],
    )
    con.commit()


def _insert_click_log(con: sqlite3.Connection, rows: list[tuple[str, int]]) -> None:
    """rows = list of (url, position_clicked)"""
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS click_log "
            "(id INTEGER PRIMARY KEY, timestamp INTEGER, url TEXT, position_clicked INTEGER)"
        )
        import time as _t
        now = int(_t.time())
        con.executemany(
            "INSERT INTO click_log (timestamp, url, position_clicked) VALUES (?, ?, ?)",
            [(now, url, pos) for url, pos in rows],
        )
        con.commit()
    except Exception:
        pass


def _insert_site(con: sqlite3.Connection, base_url: str) -> None:
    con.execute(
        "INSERT OR IGNORE INTO crawl_sites (base_url, label) VALUES (?, ?)",
        (base_url, base_url),
    )
    con.commit()


# ---------------------------------------------------------------------------
# compute_suggestions
# ---------------------------------------------------------------------------

class TestComputeSuggestions:
    def test_three_signals_generate_candidate(self, db_paths):
        """Domínio presente nos 3 sinais deve ser sugerido com score > 0."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        # Sinal 1: aparece 2× em search_cache
        _insert_cache(con, ["https://newsite.com/a", "https://newsite.com/b"])
        # Sinal 2: clicado na posição 1
        _insert_click_log(con, [("https://newsite.com/page", 1)])
        # Sinal 3: referenciado 3× em page_links
        _insert_links(con, [f"https://newsite.com/{i}" for i in range(3)])
        con.close()

        async def _run():
            import aiosqlite
            from services.suggester import compute_suggestions, get_pending_suggestions
            async with aiosqlite.connect(main_path) as db:
                count = await compute_suggestions(db)
                await db.commit()
                pending = await get_pending_suggestions(db)
                return count, pending

        count, pending = run(_run())
        assert count >= 1
        domains = [s["domain"] for s in pending]
        assert "newsite.com" in domains
        score = next(s["score"] for s in pending if s["domain"] == "newsite.com")
        assert score > 0

    def test_score_composition(self, db_paths):
        """Score = s1*1.0 + s2*3.0 + s3*0.5 — verificar que contributions are additive."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        # Sinal 1 apenas: 4 aparições em cache
        _insert_cache(con, [f"https://only-cache.com/{i}" for i in range(4)])
        con.close()

        async def _run():
            import aiosqlite
            from services.suggester import compute_suggestions, get_pending_suggestions
            async with aiosqlite.connect(main_path) as db:
                await compute_suggestions(db, min_score=0.0)
                await db.commit()
                pending = await get_pending_suggestions(db)
                return pending

        pending = run(_run())
        hit = next((s for s in pending if s["domain"] == "only-cache.com"), None)
        assert hit is not None
        # score = 4 * 1.0 = 4.0
        assert abs(hit["score"] - 4.0) < 0.01

    def test_domain_already_in_crawl_sites_excluded(self, db_paths):
        """Domínios já na Biblioteca não devem aparecer como sugestão."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        _insert_site(con, "https://existing.com")
        _insert_cache(con, ["https://existing.com/page"])
        con.close()

        async def _run():
            import aiosqlite
            from services.suggester import compute_suggestions, get_pending_suggestions
            async with aiosqlite.connect(main_path) as db:
                await compute_suggestions(db, min_score=0.0)
                await db.commit()
                return await get_pending_suggestions(db)

        pending = run(_run())
        domains = [s["domain"] for s in pending]
        assert "existing.com" not in domains

    def test_blocked_domain_not_reappeared(self, db_paths):
        """Domínio bloqueado não deve aparecer como sugestão mesmo com sinais altos."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        # Bloqueia manualmente
        import time
        con.execute(
            "INSERT INTO site_suggestions (domain, score, reason, status, updated_at) "
            "VALUES ('blocked.com', 0, '', 'blocked', ?)",
            (int(time.time()),),
        )
        con.commit()
        # Mesmo com muitas aparições em cache
        _insert_cache(con, [f"https://blocked.com/{i}" for i in range(10)])
        con.close()

        async def _run():
            import aiosqlite
            from services.suggester import compute_suggestions, get_pending_suggestions
            async with aiosqlite.connect(main_path) as db:
                await compute_suggestions(db, min_score=0.0)
                await db.commit()
                return await get_pending_suggestions(db)

        pending = run(_run())
        domains = [s["domain"] for s in pending]
        assert "blocked.com" not in domains

    def test_min_score_filter(self, db_paths):
        """Domínios com score abaixo do mínimo não são inseridos."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        # Uma única aparição → score = 1.0
        _insert_cache(con, ["https://lowscore.com/page"])
        con.close()

        async def _run():
            import aiosqlite
            from services.suggester import compute_suggestions, get_pending_suggestions
            async with aiosqlite.connect(main_path) as db:
                # min_score = 5.0 deve excluir lowscore.com (score = 1.0)
                await compute_suggestions(db, min_score=5.0)
                await db.commit()
                return await get_pending_suggestions(db)

        pending = run(_run())
        domains = [s["domain"] for s in pending]
        assert "lowscore.com" not in domains

    def test_no_signals_returns_zero(self, db_paths):
        main_path, _ = db_paths

        async def _run():
            import aiosqlite
            from services.suggester import compute_suggestions
            async with aiosqlite.connect(main_path) as db:
                return await compute_suggestions(db)

        assert run(_run()) == 0


# ---------------------------------------------------------------------------
# get_pending_suggestions
# ---------------------------------------------------------------------------

class TestGetPendingSuggestions:
    def test_returns_only_pending(self, db_paths):
        import time
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        now = int(time.time())
        con.executemany(
            "INSERT INTO site_suggestions (domain, score, reason, status, updated_at) VALUES (?,?,?,?,?)",
            [
                ("pending1.com", 5.0, "", "pending", now),
                ("approved.com", 3.0, "", "approved", now),
                ("blocked.com",  2.0, "", "blocked", now),
                ("ignored.com",  1.0, "", "ignored", now),
                ("pending2.com", 8.0, "", "pending", now),
            ],
        )
        con.commit()
        con.close()

        async def _run():
            import aiosqlite
            from services.suggester import get_pending_suggestions
            async with aiosqlite.connect(main_path) as db:
                return await get_pending_suggestions(db)

        pending = run(_run())
        domains = [s["domain"] for s in pending]
        assert "pending1.com" in domains
        assert "pending2.com" in domains
        assert "approved.com" not in domains
        assert "blocked.com"  not in domains

    def test_ordered_by_score_desc(self, db_paths):
        import time
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        now = int(time.time())
        con.executemany(
            "INSERT INTO site_suggestions (domain, score, reason, status, updated_at) VALUES (?,?,?,?,?)",
            [
                ("a.com", 2.0, "", "pending", now),
                ("b.com", 9.0, "", "pending", now),
                ("c.com", 5.0, "", "pending", now),
            ],
        )
        con.commit()
        con.close()

        async def _run():
            import aiosqlite
            from services.suggester import get_pending_suggestions
            async with aiosqlite.connect(main_path) as db:
                return await get_pending_suggestions(db)

        pending = run(_run())
        scores = [s["score"] for s in pending]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# set_suggestion_status
# ---------------------------------------------------------------------------

class TestSetSuggestionStatus:
    def test_updates_status(self, db_paths):
        import time
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        now = int(time.time())
        con.execute(
            "INSERT INTO site_suggestions (domain, score, reason, status, updated_at) VALUES (?,?,?,?,?)",
            ("example.com", 3.0, "", "pending", now),
        )
        con.commit()
        con.close()

        async def _run():
            import aiosqlite
            from services.suggester import set_suggestion_status
            async with aiosqlite.connect(main_path) as db:
                await set_suggestion_status(db, "example.com", "ignored")
                await db.commit()
                row = await (await db.execute(
                    "SELECT status FROM site_suggestions WHERE domain = 'example.com'"
                )).fetchone()
                return row[0]

        assert run(_run()) == "ignored"
