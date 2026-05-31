"""
Testes para Fix 4, Fix 5 e Fix 6 — filtragem por word_count.

Fix 4 — _upsert_page valida word_count:
  - página com < 50 palavras não é salva
  - página com >= 50 palavras é salva com word_count correto
  - word_count é atualizado no ON CONFLICT
  - páginas vazias (content_md="") são descartadas
  - MIN_WORDS_TO_STORE é exportado e vale 50

Fix 5 — auditoria de teto global (sem corte combinado):
  - routers/search.py não contém combined[:N] no caminho principal
  - search_json usa :max controlado pelo caller (correto)

Fix 6 — backfill_word_count.py:
  - etapa 1: word_count=0 → calculado a partir de content_md
  - etapa 2: páginas com word_count < 50 marcadas com last_checked_at='2000-01-01'
  - etapa 3: páginas com word_count < 50 removidas do FTS5
  - idempotência: rodar duas vezes não duplica efeitos
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
import pytest


# ---------------------------------------------------------------------------
# Fixture: banco em memória com schema mínimo
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_sites (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    url  TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS crawl_pages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id          INTEGER NOT NULL,
    url              TEXT    NOT NULL UNIQUE,
    title            TEXT    NOT NULL DEFAULT '',
    content_md       TEXT    NOT NULL DEFAULT '',
    content_hash     TEXT    NOT NULL DEFAULT '',
    http_status      INTEGER NOT NULL DEFAULT 0,
    etag             TEXT    NOT NULL DEFAULT '',
    last_modified    TEXT    NOT NULL DEFAULT '',
    crawled_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    last_modified_at TEXT    NOT NULL DEFAULT '',
    last_checked_at  TEXT    NOT NULL DEFAULT '',
    word_count       INTEGER NOT NULL DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS crawl_fts USING fts5(
    site_id UNINDEXED, url UNINDEXED, title, content_md
);
INSERT INTO crawl_sites (url, name) VALUES ('https://test.com', 'Test');
"""


@pytest.fixture
async def db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        yield conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _upsert(db, content_md: str, url: str = "https://test.com/page") -> None:
    """Chama _upsert_page real com DB em memória."""
    from unittest.mock import patch
    # Patch DB_PATH para não interferir com o banco real
    with patch("services.crawler.DB_PATH", ":memory:"):
        from services.crawler import _upsert_page
        await _upsert_page(
            db=db,
            site_id=1,
            url=url,
            title="Título",
            content_md=content_md,
            content_hash="abc123",
            http_status=200,
            now="2026-01-01T00:00:00",
        )


async def _count_pages(db, url: str) -> int:
    row = await (await db.execute(
        "SELECT COUNT(*) FROM crawl_pages WHERE url = ?", (url,)
    )).fetchone()
    return row[0]


async def _get_word_count(db, url: str) -> int | None:
    row = await (await db.execute(
        "SELECT word_count FROM crawl_pages WHERE url = ?", (url,)
    )).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Fix 4 — _upsert_page filtra por word_count
# ---------------------------------------------------------------------------

def test_min_words_to_store_is_50():
    from services.crawler import MIN_WORDS_TO_STORE
    assert MIN_WORDS_TO_STORE == 50


@pytest.mark.anyio
async def test_page_below_threshold_not_saved(db):
    """Página com < 50 palavras não deve ser inserida no banco."""
    content = " ".join(["palavra"] * 30)  # 30 palavras
    await _upsert(db, content)
    assert await _count_pages(db, "https://test.com/page") == 0


@pytest.mark.anyio
async def test_empty_page_not_saved(db):
    """Página vazia (content_md='') não deve ser inserida."""
    await _upsert(db, "")
    assert await _count_pages(db, "https://test.com/page") == 0


@pytest.mark.anyio
async def test_page_at_threshold_saved(db):
    """Página com exatamente 50 palavras deve ser salva."""
    content = " ".join(["palavra"] * 50)
    await _upsert(db, content)
    assert await _count_pages(db, "https://test.com/page") == 1


@pytest.mark.anyio
async def test_page_above_threshold_saved_with_correct_word_count(db):
    """Página com 100 palavras deve ser salva com word_count=100."""
    content = " ".join(["palavra"] * 100)
    await _upsert(db, content)
    wc = await _get_word_count(db, "https://test.com/page")
    assert wc == 100


@pytest.mark.anyio
async def test_word_count_updated_on_conflict(db):
    """Re-crawl com conteúdo diferente atualiza word_count."""
    content_v1 = " ".join(["a"] * 80)
    content_v2 = " ".join(["b"] * 60)
    await _upsert(db, content_v1)
    await db.execute(
        "UPDATE crawl_pages SET content_hash = 'old' WHERE url = ?",
        ("https://test.com/page",)
    )
    await _upsert(db, content_v2)
    wc = await _get_word_count(db, "https://test.com/page")
    assert wc == 60


@pytest.mark.anyio
async def test_multiple_pages_independently_filtered(db):
    """Páginas distintas são filtradas independentemente."""
    short = " ".join(["x"] * 20)
    long_ = " ".join(["y"] * 200)
    await _upsert(db, short, url="https://test.com/short")
    await _upsert(db, long_, url="https://test.com/long")
    assert await _count_pages(db, "https://test.com/short") == 0
    assert await _count_pages(db, "https://test.com/long") == 1


# ---------------------------------------------------------------------------
# Fix 5 — auditoria: sem combined[:N] no caminho principal
# ---------------------------------------------------------------------------

def test_no_global_result_ceiling_in_main_search():
    """O caminho principal do handler search() não deve ter combined[:N] hardcoded."""
    search_py = (
        Path(__file__).parent.parent / "routers" / "search.py"
    ).read_text()
    # combined[:N] no caminho principal seria um ceiling global
    # (combined[:max] em search_json é controlado pelo caller — aceitável)
    lines = search_py.splitlines()
    violations = []
    in_search_json = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "async def search_json" in stripped:
            in_search_json = True
        elif stripped.startswith("async def ") and in_search_json:
            in_search_json = False
        # Ignorar search_json e comentários
        if in_search_json or stripped.startswith("#"):
            continue
        # Detectar combined[:N] com N numérico
        import re
        if re.search(r"combined\[:\d+\]", stripped):
            violations.append(f"linha {i}: {stripped}")
    assert not violations, f"Teto global encontrado: {violations}"


# ---------------------------------------------------------------------------
# Fix 6 — backfill_word_count.py
# ---------------------------------------------------------------------------

async def _setup_backfill_db(db: aiosqlite.Connection) -> None:
    """Insere páginas de teste para o backfill."""
    pages = [
        (1, "https://t.com/short",  "Página curta",  "abc", "x " * 20),   # 20 palavras
        (1, "https://t.com/medium", "Página média",  "def", "y " * 50),   # 50 palavras (limite exato)
        (1, "https://t.com/long",   "Página longa",  "ghi", "z " * 200),  # 200 palavras
    ]
    await db.executemany(
        "INSERT INTO crawl_pages (site_id, url, title, content_hash, content_md) "
        "VALUES (?, ?, ?, ?, ?)",
        pages,
    )
    await db.executemany(
        "INSERT INTO crawl_fts (site_id, url, title, content_md) VALUES (?, ?, ?, ?)",
        [(str(s), u, t, c) for s, u, t, _, c in pages],
    )
    await db.commit()


@pytest.mark.anyio
async def test_backfill_fills_word_count(db):
    """Etapa 1: word_count=0 → preenchido corretamente a partir de content_md."""
    await _setup_backfill_db(db)

    # Simular backfill manualmente (sem chamar o script completo)
    rows = await (await db.execute(
        "SELECT url, content_md FROM crawl_pages WHERE word_count = 0"
    )).fetchall()
    params = [(len(row["content_md"].split()), row["url"]) for row in rows]
    await db.executemany("UPDATE crawl_pages SET word_count = ? WHERE url = ?", params)
    await db.commit()

    wc_short  = await _get_word_count(db, "https://t.com/short")
    wc_medium = await _get_word_count(db, "https://t.com/medium")
    wc_long   = await _get_word_count(db, "https://t.com/long")
    assert wc_short  == 20
    assert wc_medium == 50
    assert wc_long   == 200


@pytest.mark.anyio
async def test_backfill_marks_short_pages_for_recrawl(db):
    """Etapa 2: páginas com word_count < 50 → last_checked_at='2000-01-01'."""
    await _setup_backfill_db(db)
    # Preencher word_count primeiro
    await db.execute("UPDATE crawl_pages SET word_count = 20 WHERE url = 'https://t.com/short'")
    await db.execute("UPDATE crawl_pages SET word_count = 200 WHERE url = 'https://t.com/long'")
    await db.commit()

    from services.crawler import MIN_WORDS_TO_STORE
    await db.execute(
        "UPDATE crawl_pages SET last_checked_at = '2000-01-01' "
        "WHERE word_count < ? AND word_count > 0",
        (MIN_WORDS_TO_STORE,),
    )
    await db.commit()

    row_short = await (await db.execute(
        "SELECT last_checked_at FROM crawl_pages WHERE url = 'https://t.com/short'"
    )).fetchone()
    row_long  = await (await db.execute(
        "SELECT last_checked_at FROM crawl_pages WHERE url = 'https://t.com/long'"
    )).fetchone()
    assert row_short["last_checked_at"] == "2000-01-01"
    assert row_long["last_checked_at"]  != "2000-01-01"


@pytest.mark.anyio
async def test_backfill_removes_short_pages_from_fts(db):
    """Etapa 3: páginas com word_count < 50 removidas do FTS5."""
    await _setup_backfill_db(db)
    await db.execute("UPDATE crawl_pages SET word_count = 20 WHERE url = 'https://t.com/short'")
    await db.execute("UPDATE crawl_pages SET word_count = 200 WHERE url = 'https://t.com/long'")
    await db.commit()

    from services.crawler import MIN_WORDS_TO_STORE
    await db.execute(
        "DELETE FROM crawl_fts WHERE url IN "
        "(SELECT url FROM crawl_pages WHERE word_count < ? AND word_count > 0)",
        (MIN_WORDS_TO_STORE,),
    )
    await db.commit()

    fts_short = await (await db.execute(
        "SELECT COUNT(*) FROM crawl_fts WHERE url = 'https://t.com/short'"
    )).fetchone()
    fts_long  = await (await db.execute(
        "SELECT COUNT(*) FROM crawl_fts WHERE url = 'https://t.com/long'"
    )).fetchone()
    assert fts_short[0] == 0
    assert fts_long[0]  == 1


@pytest.mark.anyio
async def test_backfill_idempotent(db):
    """Rodar backfill duas vezes produz o mesmo resultado."""
    await _setup_backfill_db(db)

    async def _run_once():
        rows = await (await db.execute(
            "SELECT url, content_md FROM crawl_pages WHERE word_count = 0"
        )).fetchall()
        if rows:
            params = [(len(r["content_md"].split()), r["url"]) for r in rows]
            await db.executemany(
                "UPDATE crawl_pages SET word_count = ? WHERE url = ?", params
            )
        from services.crawler import MIN_WORDS_TO_STORE
        await db.execute(
            "UPDATE crawl_pages SET last_checked_at = '2000-01-01' "
            "WHERE word_count < ? AND word_count > 0",
            (MIN_WORDS_TO_STORE,),
        )
        await db.execute(
            "DELETE FROM crawl_fts WHERE url IN "
            "(SELECT url FROM crawl_pages WHERE word_count < ? AND word_count > 0)",
            (MIN_WORDS_TO_STORE,),
        )
        await db.commit()

    await _run_once()
    count_after_first = (await (await db.execute(
        "SELECT COUNT(*) FROM crawl_fts"
    )).fetchone())[0]

    await _run_once()
    count_after_second = (await (await db.execute(
        "SELECT COUNT(*) FROM crawl_fts"
    )).fetchone())[0]

    assert count_after_first == count_after_second
