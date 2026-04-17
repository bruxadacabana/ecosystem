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

SCHEMA_VERSION = 7

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

_CREATE_LIBRARY_URLS = """
CREATE TABLE IF NOT EXISTS library_urls (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    url                 TEXT    NOT NULL UNIQUE,
    title               TEXT    NOT NULL DEFAULT '',
    snippet             TEXT    NOT NULL DEFAULT '',
    content_md          TEXT    NOT NULL DEFAULT '',
    content_hash        TEXT    NOT NULL DEFAULT '',
    language            TEXT    NOT NULL DEFAULT '',
    word_count          INTEGER NOT NULL DEFAULT 0,
    tags_json           TEXT    NOT NULL DEFAULT '[]',
    notes               TEXT    NOT NULL DEFAULT '',
    check_interval_days INTEGER NOT NULL DEFAULT 7,
    last_checked_at     TEXT,
    status              TEXT    NOT NULL DEFAULT 'pending',
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_LIBRARY_DIFFS = """
CREATE TABLE IF NOT EXISTS library_diffs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url_id     INTEGER NOT NULL REFERENCES library_urls(id) ON DELETE CASCADE,
    diff_text  TEXT    NOT NULL,
    scraped_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_LIBRARY_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS library_fts USING fts5(
    url_id UNINDEXED,
    url    UNINDEXED,
    title,
    body
);
"""

_CREATE_BLOCKED_DOMAINS = """
CREATE TABLE IF NOT EXISTS blocked_domains (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    domain     TEXT    NOT NULL UNIQUE,
    added_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_CRAWL_SITES = """
CREATE TABLE IF NOT EXISTS crawl_sites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    base_url        TEXT    NOT NULL UNIQUE,
    label           TEXT    NOT NULL DEFAULT '',
    crawl_depth     INTEGER NOT NULL DEFAULT 2,
    subdomains_json TEXT    NOT NULL DEFAULT '[]',
    page_count      INTEGER NOT NULL DEFAULT 0,
    last_crawled_at TEXT,
    status          TEXT    NOT NULL DEFAULT 'idle',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_CRAWL_PAGES = """
CREATE TABLE IF NOT EXISTS crawl_pages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id      INTEGER NOT NULL REFERENCES crawl_sites(id) ON DELETE CASCADE,
    url          TEXT    NOT NULL UNIQUE,
    title        TEXT    NOT NULL DEFAULT '',
    content_md   TEXT    NOT NULL DEFAULT '',
    content_hash TEXT    NOT NULL DEFAULT '',
    http_status  INTEGER NOT NULL DEFAULT 0,
    crawled_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_CRAWL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS crawl_fts USING fts5(
    site_id  UNINDEXED,
    url      UNINDEXED,
    title,
    content_md
);
"""

# Status válidos para downloads: queued | active | done | error
# Status válidos para crawl_sites: idle | crawling | error

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
        await db.execute(_CREATE_LIBRARY_URLS)
        await db.execute(_CREATE_LIBRARY_DIFFS)
        await db.execute(_CREATE_LIBRARY_FTS)
        await db.execute(_CREATE_BLOCKED_DOMAINS)
        await db.execute(_CREATE_CRAWL_SITES)
        await db.execute(_CREATE_CRAWL_PAGES)
        await db.execute(_CREATE_CRAWL_FTS)

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

    if from_version < 5:
        pass  # Versão 5 — library_urls, library_diffs, library_fts criados acima

    if from_version < 6:
        pass  # Versão 6 — blocked_domains criado acima

    if from_version < 7:
        pass  # Versão 7 — crawl_sites, crawl_pages, crawl_fts criados acima

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


async def get_blocked_domains() -> set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT domain FROM blocked_domains"
        )).fetchall()
    return {r[0] for r in rows}


async def add_blocked_domain(domain: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO blocked_domains (domain) VALUES (?)", (domain,)
        )
        await db.commit()


async def remove_blocked_domain(domain: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM blocked_domains WHERE domain = ?", (domain,))
        await db.commit()


async def recent_searches(limit: int = 10) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT DISTINCT query FROM searches ORDER BY id DESC LIMIT ?",
            (limit,),
        )).fetchall()
        return [r[0] for r in rows]


async def get_all_crawl_sites() -> list[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT * FROM crawl_sites ORDER BY created_at DESC"
        )).fetchall()
    return list(rows)


async def get_crawl_site(site_id: int) -> tuple | None:
    async with aiosqlite.connect(DB_PATH) as db:
        return await (await db.execute(
            "SELECT * FROM crawl_sites WHERE id = ?", (site_id,)
        )).fetchone()
