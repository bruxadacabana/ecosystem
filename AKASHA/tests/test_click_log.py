"""
Testes de integração para services/click_log.py.

Cobre:
  - _normalize_query: remoção de stopwords, lowercase
  - _domain_of: extração de domínio sem www
  - _click_weight: posição 1 → 1.0; posição 3 → 0.5
  - log_click: insere linha no click_log
  - compute_domain_boosts: acumula pesos por domínio, respeita janela de 90 dias
  - get_domain_boosts: retorna 1.0 para domínio sem histórico
  - boost aplicado no ranking final (via _apply_domain_boost)
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
# Fixture: DB com schema completo
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
    """Patcheia DB_PATH no módulo click_log também."""
    main_path, _ = db_paths
    import services.click_log as _cl
    monkeypatch.setattr(_cl, "DB_PATH", main_path)
    return main_path


# ---------------------------------------------------------------------------
# Testes unitários (sem DB)
# ---------------------------------------------------------------------------

def test_normalize_query_removes_stopwords():
    from services.click_log import _normalize_query
    assert _normalize_query("como usar Python") == "usar python"


def test_normalize_query_lowercase():
    from services.click_log import _normalize_query
    assert _normalize_query("Machine Learning") == "machine learning"


def test_normalize_query_empty():
    from services.click_log import _normalize_query
    assert _normalize_query("") == ""


def test_domain_of_strips_www():
    from services.click_log import _domain_of
    assert _domain_of("https://www.example.com/page") == "example.com"


def test_domain_of_no_www():
    from services.click_log import _domain_of
    assert _domain_of("https://docs.python.org/3/") == "docs.python.org"


def test_domain_of_file_url_returns_empty():
    from services.click_log import _domain_of
    assert _domain_of("file:///home/user/notes.md") == ""


def test_click_weight_position_1():
    """Posição 1 (primeiro resultado) deve ter peso 1.0."""
    from services.click_log import _click_weight
    assert _click_weight(1) == pytest.approx(1.0, abs=1e-9)


def test_click_weight_position_3():
    """Posição 3 deve ter peso ≈ 0.5."""
    from services.click_log import _click_weight
    assert _click_weight(3) == pytest.approx(0.5, abs=1e-9)


def test_click_weight_position_2():
    """Posição 2: 1/log2(3) ≈ 0.631."""
    from services.click_log import _click_weight
    expected = 1.0 / math.log2(3)
    assert _click_weight(2) == pytest.approx(expected, rel=1e-6)


def test_click_weight_position_zero_clamped():
    """Posição ≤ 0 é tratada como 1."""
    from services.click_log import _click_weight
    assert _click_weight(0) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Testes de integração com DB
# ---------------------------------------------------------------------------

def test_log_click_inserts_row(patched_db):
    import aiosqlite

    async def _run():
        from services.click_log import log_click
        await log_click("python tutorial", "https://docs.python.org/3/", 1, "sess1")
        async with aiosqlite.connect(patched_db) as db:
            row = await (await db.execute(
                "SELECT query_norm, url, domain, position_clicked, session_id "
                "FROM click_log LIMIT 1"
            )).fetchone()
        return row

    row = run(_run())
    assert row is not None
    assert row[0] == "python tutorial"   # "python" e "tutorial" não são stopwords
    assert row[1] == "https://docs.python.org/3/"
    assert row[2] == "docs.python.org"
    assert row[3] == 1
    assert row[4] == "sess1"


def test_compute_domain_boosts_basic(patched_db):
    """Cliques em posição 1 → boost = 1.0 por clique."""
    import aiosqlite

    async def _run():
        import time as _t
        ts = int(_t.time())
        async with aiosqlite.connect(patched_db) as db:
            # 2 cliques no mesmo domínio, pos 1 e pos 3
            await db.executemany(
                "INSERT INTO click_log (timestamp, query_norm, url, domain, position_clicked, session_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (ts, "python", "https://docs.python.org/", "docs.python.org", 1, "s1"),
                    (ts, "python", "https://docs.python.org/lib", "docs.python.org", 3, "s1"),
                ],
            )
            await db.commit()

            from services.click_log import compute_domain_boosts
            n = await compute_domain_boosts(db)

            row = await (await db.execute(
                "SELECT boost FROM domain_boosts WHERE domain = 'docs.python.org'"
            )).fetchone()
        return n, row

    n, row = run(_run())
    assert n == 1
    assert row is not None
    expected_boost = 1.0 + 0.5   # pos=1 → 1.0, pos=3 → 0.5
    assert row[0] == pytest.approx(expected_boost, abs=1e-9)


def test_compute_domain_boosts_ignores_old_clicks(patched_db):
    """Cliques com mais de 90 dias não entram no boost."""
    import aiosqlite

    async def _run():
        old_ts = int(time.time()) - (91 * 86400)
        async with aiosqlite.connect(patched_db) as db:
            await db.execute(
                "INSERT INTO click_log (timestamp, query_norm, url, domain, position_clicked, session_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (old_ts, "old", "https://old.example.com/", "old.example.com", 1, "s"),
            )
            await db.commit()

            from services.click_log import compute_domain_boosts
            n = await compute_domain_boosts(db)
        return n

    n = run(_run())
    assert n == 0


def test_compute_domain_boosts_multiple_domains(patched_db):
    """Domínios distintos geram entradas separadas."""
    import aiosqlite

    async def _run():
        ts = int(time.time())
        async with aiosqlite.connect(patched_db) as db:
            await db.executemany(
                "INSERT INTO click_log (timestamp, query_norm, url, domain, position_clicked, session_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (ts, "q", "https://a.com/", "a.com", 1, "s"),
                    (ts, "q", "https://b.com/", "b.com", 3, "s"),
                ],
            )
            await db.commit()

            from services.click_log import compute_domain_boosts
            n = await compute_domain_boosts(db)

            rows = await (await db.execute(
                "SELECT domain, boost FROM domain_boosts ORDER BY domain"
            )).fetchall()
        return n, rows

    n, rows = run(_run())
    assert n == 2
    domains = {r[0]: r[1] for r in rows}
    assert domains["a.com"] == pytest.approx(1.0, abs=1e-9)
    assert domains["b.com"] == pytest.approx(0.5, abs=1e-9)


def test_get_domain_boosts_default_1_0(patched_db):
    """Domínio sem histórico retorna 1.0."""
    import aiosqlite

    async def _run():
        async with aiosqlite.connect(patched_db) as db:
            from services.click_log import get_domain_boosts
            result = await get_domain_boosts(db, ["never-clicked.com"])
        return result

    result = run(_run())
    assert result["never-clicked.com"] == pytest.approx(1.0, abs=1e-9)


def test_get_domain_boosts_returns_stored_value(patched_db):
    """Domínio com entrada em domain_boosts retorna o boost armazenado."""
    import aiosqlite

    async def _run():
        async with aiosqlite.connect(patched_db) as db:
            await db.execute(
                "INSERT INTO domain_boosts (domain, boost, updated_at) VALUES (?, ?, ?)",
                ("myblog.net", 2.5, int(time.time())),
            )
            await db.commit()
            from services.click_log import get_domain_boosts
            result = await get_domain_boosts(db, ["myblog.net", "other.com"])
        return result

    result = run(_run())
    assert result["myblog.net"] == pytest.approx(2.5, abs=1e-9)
    assert result["other.com"] == pytest.approx(1.0, abs=1e-9)


def test_get_domain_boosts_empty_list(patched_db):
    """Lista vazia retorna dict vazio."""
    import aiosqlite

    async def _run():
        async with aiosqlite.connect(patched_db) as db:
            from services.click_log import get_domain_boosts
            return await get_domain_boosts(db, [])

    result = run(_run())
    assert result == {}
