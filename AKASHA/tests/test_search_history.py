"""
Testes para get_search_sessions e count_search_sessions em services/click_log.py.

Cobre:
  - múltiplos cliques numa sessão → agrupados por session_id
  - queries distintas preservadas em ordem de aparição
  - sessões sem session_id ('') excluídas
  - paginação (limit/offset)
  - sessão com único clique
  - contagem de sessões
"""
from __future__ import annotations
import asyncio
import time
import pytest
import aiosqlite


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path):
    """Banco SQLite em memória com esquema mínimo do click_log."""
    db_path = str(tmp_path / "test.db")

    async def _setup():
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("""
                CREATE TABLE click_log (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp        INTEGER NOT NULL DEFAULT 0,
                    query_norm       TEXT    NOT NULL DEFAULT '',
                    url              TEXT    NOT NULL DEFAULT '',
                    domain           TEXT    NOT NULL DEFAULT '',
                    position_clicked INTEGER NOT NULL DEFAULT 0,
                    session_id       TEXT    NOT NULL DEFAULT ''
                )
            """)
            await conn.commit()
        return db_path

    return asyncio.get_event_loop().run_until_complete(_setup())


async def _insert(conn, *, sid, qnorm, url, ts=None, pos=1):
    ts = ts or int(time.time())
    await conn.execute(
        "INSERT INTO click_log (timestamp, query_norm, url, domain, position_clicked, session_id) VALUES (?,?,?,?,?,?)",
        (ts, qnorm, url, "", pos, sid),
    )


# ─── Testes ──────────────────────────────────────────────────────────────────

def test_single_session_grouped(db):
    """Múltiplos cliques numa sessão → retornados como uma única sessão."""
    from services.click_log import get_search_sessions, count_search_sessions

    async def run():
        async with aiosqlite.connect(db) as conn:
            await _insert(conn, sid="sess1", qnorm="python async", url="https://a.com", ts=1000)
            await _insert(conn, sid="sess1", qnorm="python async", url="https://b.com", ts=1010)
            await conn.commit()
            sessions = await get_search_sessions(conn)
            total = await count_search_sessions(conn)
        return sessions, total

    sessions, total = asyncio.get_event_loop().run_until_complete(run())
    assert len(sessions) == 1
    assert total == 1
    s = sessions[0]
    assert s["session_id"] == "sess1"
    assert s["click_count"] == 2
    assert len(s["clicks"]) == 2
    assert s["queries"] == ["python async"]


def test_distinct_queries_in_order(db):
    """Queries distintas preservadas em ordem de aparição dentro da sessão."""
    from services.click_log import get_search_sessions

    async def run():
        async with aiosqlite.connect(db) as conn:
            await _insert(conn, sid="s1", qnorm="primeiro", url="https://a.com", ts=100)
            await _insert(conn, sid="s1", qnorm="segundo",  url="https://b.com", ts=200)
            await _insert(conn, sid="s1", qnorm="primeiro", url="https://c.com", ts=300)
            await conn.commit()
            return await get_search_sessions(conn)

    sessions = asyncio.get_event_loop().run_until_complete(run())
    assert sessions[0]["queries"] == ["primeiro", "segundo"]


def test_empty_session_id_excluded(db):
    """Cliques sem session_id (string vazia) não aparecem nas sessões."""
    from services.click_log import get_search_sessions, count_search_sessions

    async def run():
        async with aiosqlite.connect(db) as conn:
            await _insert(conn, sid="",    qnorm="anon",  url="https://anon.com")
            await _insert(conn, sid="s1",  qnorm="query", url="https://real.com")
            await conn.commit()
            sessions = await get_search_sessions(conn)
            total = await count_search_sessions(conn)
        return sessions, total

    sessions, total = asyncio.get_event_loop().run_until_complete(run())
    assert len(sessions) == 1
    assert total == 1
    assert sessions[0]["session_id"] == "s1"


def test_sessions_ordered_by_most_recent(db):
    """Sessões ordenadas pelo clique mais recente, decrescente."""
    from services.click_log import get_search_sessions

    async def run():
        async with aiosqlite.connect(db) as conn:
            await _insert(conn, sid="old",  qnorm="q", url="https://old.com",  ts=500)
            await _insert(conn, sid="new",  qnorm="q", url="https://new.com",  ts=2000)
            await conn.commit()
            return await get_search_sessions(conn)

    sessions = asyncio.get_event_loop().run_until_complete(run())
    assert sessions[0]["session_id"] == "new"
    assert sessions[1]["session_id"] == "old"


def test_pagination_limit_offset(db):
    """Paginação via limit e offset retorna subconjuntos corretos."""
    from services.click_log import get_search_sessions

    async def run():
        async with aiosqlite.connect(db) as conn:
            for i in range(5):
                await _insert(conn, sid=f"s{i}", qnorm="q", url=f"https://s{i}.com", ts=i * 10)
            await conn.commit()
            first  = await get_search_sessions(conn, limit=2, offset=0)
            second = await get_search_sessions(conn, limit=2, offset=2)
            third  = await get_search_sessions(conn, limit=2, offset=4)
        return first, second, third

    first, second, third = asyncio.get_event_loop().run_until_complete(run())
    assert len(first)  == 2
    assert len(second) == 2
    assert len(third)  == 1


def test_count_search_sessions_no_data(db):
    """count_search_sessions retorna 0 quando não há dados."""
    from services.click_log import count_search_sessions

    async def run():
        async with aiosqlite.connect(db) as conn:
            return await count_search_sessions(conn)

    assert asyncio.get_event_loop().run_until_complete(run()) == 0


def test_session_start_end_timestamps(db):
    """session_start e session_end refletem min e max timestamp da sessão."""
    from services.click_log import get_search_sessions

    async def run():
        async with aiosqlite.connect(db) as conn:
            await _insert(conn, sid="s1", qnorm="q", url="https://a.com", ts=100)
            await _insert(conn, sid="s1", qnorm="q", url="https://b.com", ts=999)
            await conn.commit()
            return await get_search_sessions(conn)

    sessions = asyncio.get_event_loop().run_until_complete(run())
    s = sessions[0]
    assert s["session_start"] == 100
    assert s["session_end"]   == 999
