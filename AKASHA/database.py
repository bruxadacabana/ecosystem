"""
AKASHA — Banco de dados SQLite
Schema, migrations e função de inicialização.
"""
from __future__ import annotations

import aiosqlite

from config import DB_PATH

# ---------------------------------------------------------------------------
# Versão do schema — incrementar a cada migration
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 3

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_CREATE_SEARCHES = """
CREATE TABLE IF NOT EXISTS searches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    query      TEXT    NOT NULL,
    sources    TEXT    NOT NULL DEFAULT 'web',
    result_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_DOWNLOADS = """
CREATE TABLE IF NOT EXISTS downloads (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    url              TEXT    NOT NULL,
    filename         TEXT    NOT NULL DEFAULT '',
    dest_dir         TEXT    NOT NULL DEFAULT '',
    size_bytes       INTEGER NOT NULL DEFAULT 0,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
    status           TEXT    NOT NULL DEFAULT 'queued',
    started_at       TEXT,
    finished_at      TEXT,
    error_msg        TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_SEARCH_CACHE = """
CREATE TABLE IF NOT EXISTS search_cache (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    query        TEXT    NOT NULL,
    sources      TEXT    NOT NULL DEFAULT 'web',
    results_json TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_IDX_CACHE = """
CREATE INDEX IF NOT EXISTS idx_cache_lookup
    ON search_cache(query, sources, created_at);
"""

_CREATE_LOCAL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS local_fts USING fts5(
    path   UNINDEXED,
    title,
    body,
    source UNINDEXED
);
"""

_CREATE_LOCAL_META = """
CREATE TABLE IF NOT EXISTS local_index_meta (
    path   TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    mtime  TEXT NOT NULL
);
"""

# Status válidos para downloads: queued | active | done | error

# ---------------------------------------------------------------------------
# Inicialização e migrations
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Cria tabelas e aplica migrations necessárias."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(_CREATE_SETTINGS)
        await db.execute(_CREATE_SEARCHES)
        await db.execute(_CREATE_DOWNLOADS)
        await db.execute(_CREATE_SEARCH_CACHE)
        await db.execute(_CREATE_IDX_CACHE)
        await db.execute(_CREATE_LOCAL_FTS)
        await db.execute(_CREATE_LOCAL_META)

        # Verifica versão atual do schema
        row = await (await db.execute(
            "SELECT value FROM settings WHERE key = 'schema_version'"
        )).fetchone()
        current = int(row[0]) if row else 0

        if current < SCHEMA_VERSION:
            await _migrate(db, current)

        await db.commit()


async def _migrate(db: aiosqlite.Connection, from_version: int) -> None:
    """Aplica migrations incrementais."""
    if from_version < 1:
        pass  # Versão 1 — schema inicial criado pelas CREATE TABLE IF NOT EXISTS acima

    if from_version < 2:
        pass  # Versão 2 — search_cache criado pelas CREATE TABLE IF NOT EXISTS acima

    if from_version < 3:
        pass  # Versão 3 — local_fts + local_index_meta criados acima

    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )

# ---------------------------------------------------------------------------
# Helpers de acesso (usados pelos routers)
# ---------------------------------------------------------------------------

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )).fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def save_search(query: str, sources: str, result_count: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO searches (query, sources, result_count) VALUES (?, ?, ?)",
            (query, sources, result_count),
        )
        await db.commit()


async def recent_searches(limit: int = 10) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT DISTINCT query FROM searches ORDER BY id DESC LIMIT ?",
            (limit,),
        )).fetchall()
        return [r[0] for r in rows]
