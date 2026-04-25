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

SCHEMA_VERSION = 12

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

_CREATE_FAVORITE_DOMAINS = """
CREATE TABLE IF NOT EXISTS favorite_domains (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    domain         TEXT    NOT NULL UNIQUE,
    label          TEXT    NOT NULL DEFAULT '',
    priority_score INTEGER NOT NULL DEFAULT 10,
    added_at       TEXT    NOT NULL DEFAULT (datetime('now'))
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
    site_id    UNINDEXED,
    url        UNINDEXED,
    title,
    content_md,
    prefix = '2 3'
);
"""

_CREATE_IDX_CRAWL_PAGES_SITE = """
CREATE INDEX IF NOT EXISTS idx_crawl_pages_site ON crawl_pages(site_id);
"""

_CREATE_IDX_LIBRARY_DIFFS_URL = """
CREATE INDEX IF NOT EXISTS idx_library_diffs_url ON library_diffs(url_id);
"""

_CREATE_WATCH_LATER = """
CREATE TABLE IF NOT EXISTS watch_later (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    url      TEXT    NOT NULL UNIQUE,
    title    TEXT    NOT NULL DEFAULT '',
    snippet  TEXT    NOT NULL DEFAULT '',
    notes    TEXT    NOT NULL DEFAULT '',
    added_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_WATCH_LATER_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS watch_later_fts USING fts5(
    id      UNINDEXED,
    url     UNINDEXED,
    title,
    notes
);
"""

_CREATE_ACTIVITY_LOG = """
CREATE TABLE IF NOT EXISTS activity_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT    NOT NULL,
    title      TEXT    NOT NULL DEFAULT '',
    url        TEXT    NOT NULL DEFAULT '',
    meta_json  TEXT    NOT NULL DEFAULT '{}',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_IDX_ACTIVITY_LOG = """
CREATE INDEX IF NOT EXISTS idx_activity_log_created ON activity_log(created_at DESC);
"""

# Status válidos para downloads: queued | active | done | error
# Status válidos para crawl_sites: idle | crawling | error

# ---------------------------------------------------------------------------
# Inicialização e migrations
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Cria tabelas e aplica migrations necessárias."""
    async with aiosqlite.connect(DB_PATH) as db:
        # WAL mode: reads nunca bloqueiam writes (crítico para crawl + busca simultâneos)
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=-8000")      # 8 MB de page cache
        await db.execute("PRAGMA mmap_size=67108864")    # 64 MB mmap

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
        await db.execute(_CREATE_FAVORITE_DOMAINS)
        await db.execute(_CREATE_CRAWL_SITES)
        await db.execute(_CREATE_CRAWL_PAGES)
        await db.execute(_CREATE_CRAWL_FTS)
        await db.execute(_CREATE_IDX_CRAWL_PAGES_SITE)
        await db.execute(_CREATE_IDX_LIBRARY_DIFFS_URL)
        await db.execute(_CREATE_WATCH_LATER)
        await db.execute(_CREATE_WATCH_LATER_FTS)
        await db.execute(_CREATE_ACTIVITY_LOG)
        await db.execute(_CREATE_IDX_ACTIVITY_LOG)

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

    if from_version < 8:
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_crawl_pages_site ON crawl_pages(site_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_diffs_url ON library_diffs(url_id)"
        )

    if from_version < 9:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS watch_later (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                url      TEXT    NOT NULL UNIQUE,
                title    TEXT    NOT NULL DEFAULT '',
                snippet  TEXT    NOT NULL DEFAULT '',
                notes    TEXT    NOT NULL DEFAULT '',
                added_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS watch_later_fts USING fts5(
                id UNINDEXED, url UNINDEXED, title, notes
            )
        """)

    if from_version < 10:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                type       TEXT    NOT NULL,
                title      TEXT    NOT NULL DEFAULT '',
                url        TEXT    NOT NULL DEFAULT '',
                meta_json  TEXT    NOT NULL DEFAULT '{}',
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_log_created
            ON activity_log(created_at DESC)
        """)

    if from_version < 12:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorite_domains (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                domain         TEXT    NOT NULL UNIQUE,
                label          TEXT    NOT NULL DEFAULT '',
                priority_score INTEGER NOT NULL DEFAULT 10,
                added_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if from_version < 11:
        # Recriar crawl_fts com prefix='2 3' para acelerar buscas de prefixo.
        # FTS5 não suporta ALTER TABLE — drop + recreate + repopulate de crawl_pages.
        await db.execute("DROP TABLE IF EXISTS crawl_fts")
        await db.execute("""
            CREATE VIRTUAL TABLE crawl_fts USING fts5(
                site_id    UNINDEXED,
                url        UNINDEXED,
                title,
                content_md,
                prefix = '2 3'
            )
        """)
        await db.execute("""
            INSERT INTO crawl_fts (site_id, url, title, content_md)
            SELECT CAST(site_id AS TEXT), url, title, substr(content_md, 1, 12000)
            FROM crawl_pages
            WHERE content_md != ''
        """)

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


async def list_blocked_domains() -> list[tuple[str, str]]:
    """Retorna lista de (domain, added_at) ordenada pela data mais recente."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT domain, added_at FROM blocked_domains ORDER BY added_at DESC"
        )).fetchall()
    return [(r[0], r[1]) for r in rows]


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


async def get_favorite_domains() -> set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT domain FROM favorite_domains"
        )).fetchall()
    return {r[0] for r in rows}


async def list_favorite_domains() -> list[tuple]:
    """Retorna lista de (id, domain, label, priority_score, added_at) por score desc."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT id, domain, label, priority_score, added_at "
            "FROM favorite_domains ORDER BY priority_score DESC, added_at DESC"
        )).fetchall()
    return list(rows)


async def add_favorite_domain(domain: str, label: str = "", priority_score: int = 10) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO favorite_domains (domain, label, priority_score) VALUES (?, ?, ?)",
            (domain, label, priority_score),
        )
        await db.commit()


async def remove_favorite_domain(domain: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM favorite_domains WHERE domain = ?", (domain,))
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


async def add_crawl_site(
    base_url: str,
    label: str,
    crawl_depth: int,
    subdomains_json: str,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT OR IGNORE INTO crawl_sites (base_url, label, crawl_depth, subdomains_json)
               VALUES (?, ?, ?, ?)""",
            (base_url, label, crawl_depth, subdomains_json),
        )
        await db.commit()
        return cursor.lastrowid or 0


async def delete_crawl_site(site_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM crawl_fts WHERE site_id = ?", (str(site_id),))
        await db.execute("DELETE FROM crawl_sites WHERE id = ?", (site_id,))
        await db.commit()


async def get_crawl_page_by_url(url: str) -> tuple | None:
    """Retorna a crawl_page completa (com content_md) para o URL dado."""
    async with aiosqlite.connect(DB_PATH) as db:
        return await (await db.execute(
            "SELECT id, site_id, url, title, content_md, http_status, crawled_at "
            "FROM crawl_pages WHERE url = ?",
            (url,),
        )).fetchone()


async def get_crawl_pages_by_site(
    site_id: int,
    limit: int = 20,
    offset: int = 0,
    q: str = "",
) -> list[tuple]:
    """Lista páginas de um site (sem content_md) com filtro opcional por título/url."""
    async with aiosqlite.connect(DB_PATH) as db:
        if q:
            pattern = f"%{q}%"
            rows = await (await db.execute(
                "SELECT id, url, title, http_status, crawled_at "
                "FROM crawl_pages WHERE site_id = ? AND (title LIKE ? OR url LIKE ?) "
                "ORDER BY crawled_at DESC LIMIT ? OFFSET ?",
                (site_id, pattern, pattern, limit, offset),
            )).fetchall()
        else:
            rows = await (await db.execute(
                "SELECT id, url, title, http_status, crawled_at "
                "FROM crawl_pages WHERE site_id = ? "
                "ORDER BY crawled_at DESC LIMIT ? OFFSET ?",
                (site_id, limit, offset),
            )).fetchall()
    return list(rows)


# ---------------------------------------------------------------------------
# Watch Later helpers
# ---------------------------------------------------------------------------

async def add_watch_later(url: str, title: str = "", snippet: str = "") -> int:
    """Adiciona URL à lista Ver Mais Tarde. Ignora silenciosamente se já existir."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO watch_later (url, title, snippet) VALUES (?, ?, ?)",
            (url, title, snippet),
        )
        row_id = cursor.lastrowid or 0
        if row_id:
            await db.execute(
                "INSERT INTO watch_later_fts (id, url, title, notes) VALUES (?, ?, ?, '')",
                (row_id, url, title),
            )
        await db.commit()
        return row_id


async def get_all_watch_later() -> list[tuple]:
    """Retorna todos os itens ordenados do mais recente ao mais antigo."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT id, url, title, snippet, notes, added_at FROM watch_later ORDER BY id DESC"
        )).fetchall()
    return list(rows)


async def update_watch_later_notes(item_id: int, notes: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE watch_later SET notes = ? WHERE id = ?", (notes, item_id))
        await db.execute(
            "UPDATE watch_later_fts SET notes = ? WHERE id = ?", (notes, item_id)
        )
        await db.commit()


async def delete_watch_later(item_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM watch_later_fts WHERE id = ?", (item_id,))
        await db.execute("DELETE FROM watch_later WHERE id = ?", (item_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# Activity Log helpers
# ---------------------------------------------------------------------------

async def log_activity(
    type: str,
    title: str,
    url: str = "",
    meta_json: str = "{}",
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO activity_log (type, title, url, meta_json) VALUES (?, ?, ?, ?)",
            (type, title, url, meta_json),
        )
        await db.commit()


_HISTORY_PAGE_SIZE = 40


async def get_activity_log(
    type_filter: str = "all",
    page: int = 1,
) -> list[tuple]:
    """Retorna página de (id, type, title, url, meta_json, created_at) mais recentes."""
    offset = (page - 1) * _HISTORY_PAGE_SIZE
    async with aiosqlite.connect(DB_PATH) as db:
        if type_filter == "all":
            rows = await (await db.execute(
                "SELECT id, type, title, url, meta_json, created_at "
                "FROM activity_log ORDER BY id DESC LIMIT ? OFFSET ?",
                (_HISTORY_PAGE_SIZE, offset),
            )).fetchall()
        else:
            rows = await (await db.execute(
                "SELECT id, type, title, url, meta_json, created_at "
                "FROM activity_log WHERE type = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (type_filter, _HISTORY_PAGE_SIZE, offset),
            )).fetchall()
    return list(rows)


async def count_activity_log(type_filter: str = "all") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        if type_filter == "all":
            row = await (await db.execute(
                "SELECT COUNT(*) FROM activity_log"
            )).fetchone()
        else:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM activity_log WHERE type = ?", (type_filter,)
            )).fetchone()
    return row[0] if row else 0


async def search_watch_later(query: str, limit: int = 20) -> list[tuple]:
    """Busca FTS5 em watch_later_fts. Retorna (id, url, title, snippet, notes, added_at)."""
    import re
    cleaned = re.sub(r'["\'\(\)\*\:\^]', " ", query).strip()
    if not cleaned:
        return []
    fts_query = " ".join(f"{t}*" for t in cleaned.split() if t)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                """SELECT w.id, w.url, w.title, w.snippet, w.notes, w.added_at
                   FROM watch_later_fts f
                   JOIN watch_later w ON w.id = f.id
                   WHERE watch_later_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, limit),
            )).fetchall()
        return list(rows)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Downloads helpers
# ---------------------------------------------------------------------------

async def create_download(url: str, filename: str = "", dest_dir: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO downloads (url, filename, dest_dir, status) VALUES (?, ?, ?, 'queued')",
            (url, filename, dest_dir),
        )
        await db.commit()
        return cursor.lastrowid or 0


async def update_download_start(
    download_id: int, filename: str, dest_dir: str, size_bytes: int
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE downloads
               SET filename = ?, dest_dir = ?, size_bytes = ?, status = 'active',
                   started_at = datetime('now')
               WHERE id = ?""",
            (filename, dest_dir, size_bytes, download_id),
        )
        await db.commit()


async def update_download_progress(
    download_id: int, downloaded_bytes: int, size_bytes: int
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE downloads SET downloaded_bytes = ?, size_bytes = ? WHERE id = ?",
            (downloaded_bytes, size_bytes, download_id),
        )
        await db.commit()


async def finish_download(
    download_id: int, filename: str, status: str, error_msg: str = ""
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE downloads
               SET filename = ?, status = ?, error_msg = ?, finished_at = datetime('now')
               WHERE id = ?""",
            (filename, status, error_msg, download_id),
        )
        await db.commit()


async def get_download(download_id: int) -> tuple | None:
    async with aiosqlite.connect(DB_PATH) as db:
        return await (await db.execute(
            "SELECT id, url, filename, dest_dir, size_bytes, downloaded_bytes, "
            "status, started_at, finished_at, error_msg, created_at "
            "FROM downloads WHERE id = ?",
            (download_id,),
        )).fetchone()


async def list_downloads(page: int = 1, page_size: int = 20) -> list[tuple]:
    offset = (page - 1) * page_size
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT id, url, filename, dest_dir, size_bytes, downloaded_bytes, "
            "status, started_at, finished_at, error_msg, created_at "
            "FROM downloads ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        )).fetchall()
    return list(rows)


async def count_downloads() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM downloads")).fetchone()
    return row[0] if row else 0


async def get_active_downloads() -> list[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT id, url, filename, dest_dir, size_bytes, downloaded_bytes, "
            "status, started_at, finished_at, error_msg, created_at "
            "FROM downloads WHERE status IN ('queued', 'active') ORDER BY created_at ASC",
        )).fetchall()
    return list(rows)
