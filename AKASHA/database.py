"""
AKASHA — Banco de dados SQLite
Schema, migrations e função de inicialização.
"""
from __future__ import annotations

import json

import aiosqlite

from config import DB_PATH

# ---------------------------------------------------------------------------
# Versão do schema — incrementar a cada migration
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 33

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
    source UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

_CREATE_LOCAL_META = """
CREATE TABLE IF NOT EXISTS local_index_meta (
    path   TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    mtime  TEXT NOT NULL,
    lang   TEXT NOT NULL DEFAULT ''
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
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id       INTEGER NOT NULL REFERENCES crawl_sites(id) ON DELETE CASCADE,
    url           TEXT    NOT NULL UNIQUE,
    title         TEXT    NOT NULL DEFAULT '',
    content_md    TEXT    NOT NULL DEFAULT '',
    content_hash  TEXT    NOT NULL DEFAULT '',
    http_status   INTEGER NOT NULL DEFAULT 0,
    etag          TEXT    NOT NULL DEFAULT '',
    last_modified TEXT    NOT NULL DEFAULT '',
    crawled_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_IDX_CRAWL_PAGES_HASH = """
CREATE INDEX IF NOT EXISTS idx_crawl_pages_hash
    ON crawl_pages(content_hash) WHERE content_hash != '';
"""

_CREATE_CRAWL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS crawl_fts USING fts5(
    site_id    UNINDEXED,
    url        UNINDEXED,
    title,
    content_md,
    prefix   = '2 3',
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

_CREATE_IDX_CRAWL_PAGES_SITE = """
CREATE INDEX IF NOT EXISTS idx_crawl_pages_site ON crawl_pages(site_id);
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

_CREATE_LOCAL_VEC_PATHS = """
CREATE TABLE IF NOT EXISTS local_vec_paths (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT    NOT NULL UNIQUE
);
"""

_CREATE_ARCHIVE_SIMHASHES = """
CREATE TABLE IF NOT EXISTS archive_simhashes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    simhash INTEGER NOT NULL,
    path    TEXT    NOT NULL UNIQUE,
    url     TEXT    NOT NULL
);
"""

_CREATE_ARCHIVE_DOIS = """
CREATE TABLE IF NOT EXISTS archive_dois (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    doi       TEXT    NOT NULL UNIQUE,
    arxiv_id  TEXT,
    path      TEXT    NOT NULL,
    url       TEXT    NOT NULL
);
"""

_CREATE_SEARCH_PROFILE = """
CREATE TABLE IF NOT EXISTS search_profile (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_PAGE_KNOWLEDGE = """
CREATE TABLE IF NOT EXISTS page_knowledge (
    url          TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT '',
    summary      TEXT NOT NULL DEFAULT '',
    topics       TEXT NOT NULL DEFAULT '[]',
    entities     TEXT NOT NULL DEFAULT '[]',
    source_type  TEXT NOT NULL DEFAULT '',
    processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_TOPIC_INTEREST_PROFILE = """
CREATE TABLE IF NOT EXISTS topic_interest_profile (
    topic        TEXT PRIMARY KEY,
    score        REAL NOT NULL DEFAULT 1.0,
    query_count  INTEGER NOT NULL DEFAULT 1,
    last_updated TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_ENTITY_GRAPH = """
CREATE TABLE IF NOT EXISTS entity_graph (
    entity     TEXT NOT NULL,
    co_entity  TEXT NOT NULL,
    weight     REAL NOT NULL DEFAULT 1.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (entity, co_entity)
);
"""

_CREATE_TAG_PAIRS = """
CREATE TABLE IF NOT EXISTS tag_pairs (
    tag_a TEXT NOT NULL,
    tag_b TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (tag_a, tag_b)
);
"""

_CREATE_IDX_ARCHIVE_SIMHASHES = """
CREATE INDEX IF NOT EXISTS idx_archive_simhashes ON archive_simhashes(simhash);
"""

_CREATE_DOC_ACCESSES = """
CREATE TABLE IF NOT EXISTS doc_accesses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT    NOT NULL,
    accessed_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_IDX_DOC_ACCESSES_URL = """
CREATE INDEX IF NOT EXISTS idx_doc_accesses_url ON doc_accesses(url);
"""

_CREATE_HIGHLIGHTS = """
CREATE TABLE IF NOT EXISTS highlights (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT    NOT NULL,
    exact      TEXT    NOT NULL,
    prefix     TEXT    NOT NULL DEFAULT '',
    suffix     TEXT    NOT NULL DEFAULT '',
    note       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_HIGHLIGHTS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS highlights_fts USING fts5(
    exact,
    note,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

_CREATE_IDX_HIGHLIGHTS_URL = """
CREATE INDEX IF NOT EXISTS idx_highlights_url ON highlights(url);
"""

_CREATE_SEARCH_HISTORY = """
CREATE TABLE IF NOT EXISTS search_history (
    query     TEXT    NOT NULL UNIQUE,
    count     INTEGER NOT NULL DEFAULT 1,
    last_used TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_IDX_SEARCH_HISTORY = """
CREATE INDEX IF NOT EXISTS idx_search_history_last ON search_history(last_used DESC);
"""

_CREATE_LENSES = """
CREATE TABLE IF NOT EXISTS lenses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    domains       TEXT    NOT NULL DEFAULT '',
    tags          TEXT    NOT NULL DEFAULT '',
    content_types TEXT    NOT NULL DEFAULT '',
    date_from     TEXT    NOT NULL DEFAULT '',
    date_to       TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_DOC_CITATIONS = """
CREATE TABLE IF NOT EXISTS doc_citations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    citing_url  TEXT    NOT NULL,
    cited_doi   TEXT    NOT NULL,
    cited_title TEXT    NOT NULL DEFAULT '',
    UNIQUE(citing_url, cited_doi)
);
"""

_CREATE_IDX_DOC_CITATIONS_DOI = """
CREATE INDEX IF NOT EXISTS idx_doc_citations_doi ON doc_citations(cited_doi);
"""

_CREATE_PERSONAL_MEMORY = """
CREATE TABLE IF NOT EXISTS personal_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    type       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    tags       TEXT    NOT NULL DEFAULT '[]',
    feedback   TEXT             DEFAULT NULL
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
        await db.execute(
            "INSERT INTO local_fts(local_fts, rank) VALUES('rank', 'bm25(0, 10.0, 1.0, 0)')"
        )
        await db.execute(_CREATE_LOCAL_META)
        await db.execute(_CREATE_BLOCKED_DOMAINS)
        await db.execute(_CREATE_FAVORITE_DOMAINS)
        await db.execute(_CREATE_CRAWL_SITES)
        await db.execute(_CREATE_CRAWL_PAGES)
        await db.execute(_CREATE_CRAWL_FTS)
        await db.execute(
            "INSERT INTO crawl_fts(crawl_fts, rank) VALUES('rank', 'bm25(0, 0, 10.0, 1.0)')"
        )
        await db.execute(_CREATE_IDX_CRAWL_PAGES_SITE)
        await db.execute(_CREATE_IDX_CRAWL_PAGES_HASH)
        await db.execute(_CREATE_WATCH_LATER)
        await db.execute(_CREATE_WATCH_LATER_FTS)
        await db.execute(_CREATE_ACTIVITY_LOG)
        await db.execute(_CREATE_IDX_ACTIVITY_LOG)
        await db.execute(_CREATE_LOCAL_VEC_PATHS)
        await db.execute(_CREATE_ARCHIVE_SIMHASHES)
        await db.execute(_CREATE_IDX_ARCHIVE_SIMHASHES)
        await db.execute(_CREATE_DOC_ACCESSES)
        await db.execute(_CREATE_IDX_DOC_ACCESSES_URL)
        await db.execute(_CREATE_HIGHLIGHTS)
        await db.execute(_CREATE_HIGHLIGHTS_FTS)
        await db.execute(_CREATE_IDX_HIGHLIGHTS_URL)
        await db.execute(_CREATE_SEARCH_HISTORY)
        await db.execute(_CREATE_IDX_SEARCH_HISTORY)
        await db.execute(_CREATE_LENSES)
        await db.execute(_CREATE_DOC_CITATIONS)
        await db.execute(_CREATE_IDX_DOC_CITATIONS_DOI)
        await db.execute(_CREATE_SEARCH_PROFILE)
        await db.execute(_CREATE_PAGE_KNOWLEDGE)
        await db.execute(_CREATE_TOPIC_INTEREST_PROFILE)
        await db.execute(_CREATE_ENTITY_GRAPH)
        # personal_memory agora vive em arquivo separado — ver init_pm_db()

        # Verifica versão atual do schema
        row = await (await db.execute(
            "SELECT value FROM settings WHERE key = 'schema_version'"
        )).fetchone()
        current = int(row[0]) if row else 0

        if current < SCHEMA_VERSION:
            await _migrate(db, current)

        await populate_from_user_data(db)
        await db.commit()

    from services import personal_memory as _pm
    await _pm.init_pm_db()


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
        # idx_library_diffs_url omitido: library_diffs nunca existe em fresh install
        # (fase 7 foi substituída pela fase 10 antes do primeiro commit público);
        # a migration < 13 remove qualquer vestígio em bancos mais antigos.

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

    if from_version < 13:
        # Fase 7 (URL monitoring com diffs) foi substituída pela Fase 10 (crawler BFS).
        # As tabelas nunca foram populadas; removê-las elimina dead schema e o índice órfão.
        await db.execute("DROP TABLE IF EXISTS library_diffs")
        await db.execute("DROP TABLE IF EXISTS library_urls")
        await db.execute("DROP TABLE IF EXISTS library_fts")
        await db.execute("DROP INDEX IF EXISTS idx_library_diffs_url")

    if from_version < 14:
        # Recriar local_fts com tokenizer unicode61 remove_diacritics=2.
        # FTS5 não suporta ALTER TABLE — drop + recreate é o único caminho.
        # local_index_meta é limpo para forçar reindexação completa no próximo startup.
        await db.execute("DROP TABLE IF EXISTS local_fts")
        await db.execute("""
            CREATE VIRTUAL TABLE local_fts USING fts5(
                path   UNINDEXED,
                title,
                body,
                source UNINDEXED,
                tokenize = 'unicode61 remove_diacritics 2'
            )
        """)
        await db.execute("DELETE FROM local_index_meta")

    if from_version < 15:
        # Adiciona colunas HTTP cache e índice para deduplicação por hash.
        try:
            await db.execute("ALTER TABLE crawl_pages ADD COLUMN etag TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # coluna já existe em banco recém-criado
        try:
            await db.execute("ALTER TABLE crawl_pages ADD COLUMN last_modified TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_crawl_pages_hash "
            "ON crawl_pages(content_hash) WHERE content_hash != ''"
        )

    if from_version < 16:
        # Configura pesos BM25 persistentes nas tabelas FTS5.
        # local_fts: title×10 > body×1 (path e source são UNINDEXED → peso 0).
        # crawl_fts: title×10 > content_md×1 (site_id e url são UNINDEXED → peso 0).
        # Permite usar ORDER BY rank nos SELECTs em vez de repetir bm25(...) em cada query.
        await db.execute(
            "INSERT INTO local_fts(local_fts, rank) VALUES('rank', 'bm25(0, 10.0, 1.0, 0)')"
        )
        await db.execute(
            "INSERT INTO crawl_fts(crawl_fts, rank) VALUES('rank', 'bm25(0, 0, 10.0, 1.0)')"
        )

    if from_version < 17:
        # Recriar crawl_fts com tokenizer unicode61 remove_diacritics=2.
        # Garante que buscar "pagina" encontre "página", "cafe" encontre "café", etc.
        # FTS5 não suporta ALTER TABLE — drop + recreate + repopulate.
        await db.execute("DROP TABLE IF EXISTS crawl_fts")
        await db.execute("""
            CREATE VIRTUAL TABLE crawl_fts USING fts5(
                site_id    UNINDEXED,
                url        UNINDEXED,
                title,
                content_md,
                prefix   = '2 3',
                tokenize = 'unicode61 remove_diacritics 2'
            )
        """)
        await db.execute("""
            INSERT INTO crawl_fts (site_id, url, title, content_md)
            SELECT CAST(site_id AS TEXT), url, title, substr(content_md, 1, 12000)
            FROM crawl_pages
            WHERE content_md != ''
        """)
        await db.execute(
            "INSERT INTO crawl_fts(crawl_fts, rank) VALUES('rank', 'bm25(0, 0, 10.0, 1.0)')"
        )

    if from_version < 18:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS archive_simhashes (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                simhash INTEGER NOT NULL,
                path    TEXT    NOT NULL UNIQUE,
                url     TEXT    NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_archive_simhashes ON archive_simhashes(simhash)"
        )

    if from_version < 19:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS local_vec_paths (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT    NOT NULL UNIQUE
            )
        """)

    if from_version < 20:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS doc_accesses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT    NOT NULL,
                accessed_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_doc_accesses_url ON doc_accesses(url)"
        )

    if from_version < 21:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS highlights (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                url        TEXT    NOT NULL,
                exact      TEXT    NOT NULL,
                prefix     TEXT    NOT NULL DEFAULT '',
                suffix     TEXT    NOT NULL DEFAULT '',
                note       TEXT    NOT NULL DEFAULT '',
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS highlights_fts USING fts5(
                exact,
                note,
                tokenize = 'unicode61 remove_diacritics 2'
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_highlights_url ON highlights(url)"
        )

    if from_version < 22:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                query     TEXT    NOT NULL UNIQUE,
                count     INTEGER NOT NULL DEFAULT 1,
                last_used TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_search_history_last ON search_history(last_used DESC)"
        )

    if from_version < 23:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lenses (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                domains       TEXT    NOT NULL DEFAULT '',
                tags          TEXT    NOT NULL DEFAULT '',
                content_types TEXT    NOT NULL DEFAULT '',
                date_from     TEXT    NOT NULL DEFAULT '',
                date_to       TEXT    NOT NULL DEFAULT '',
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if from_version < 24:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS doc_citations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                citing_url  TEXT    NOT NULL,
                cited_doi   TEXT    NOT NULL,
                cited_title TEXT    NOT NULL DEFAULT '',
                UNIQUE(citing_url, cited_doi)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_doc_citations_doi ON doc_citations(cited_doi)"
        )

    if from_version < 25:
        await db.execute(_CREATE_ARCHIVE_DOIS)

    if from_version < 26:
        await db.execute(_CREATE_TAG_PAIRS)

    if from_version < 27:
        from services.user_data import (
            SITES_FILE,
            save_sites, save_blocked_domains,
            save_favorites, save_lenses, save_watch_later,
        )
        # Migração única: exporta DB existente → JSON na primeira abertura.
        # Condição: sites.json não existe (proxy para "JSONs ainda não criados").
        if not SITES_FILE.exists():
            rows = await (await db.execute(
                "SELECT base_url, label, crawl_depth, subdomains_json, created_at "
                "FROM crawl_sites"
            )).fetchall()
            save_sites([{
                "base_url": r[0], "label": r[1], "crawl_depth": r[2],
                "subdomains": json.loads(r[3] or "[]"), "created_at": r[4],
            } for r in rows])

            rows = await (await db.execute(
                "SELECT domain, added_at FROM blocked_domains"
            )).fetchall()
            save_blocked_domains([{"domain": r[0], "added_at": r[1]} for r in rows])

            rows = await (await db.execute(
                "SELECT domain, label, priority_score, added_at FROM favorite_domains"
            )).fetchall()
            save_favorites([{
                "domain": r[0], "label": r[1], "priority_score": r[2], "added_at": r[3],
            } for r in rows])

            rows = await (await db.execute(
                "SELECT name, domains, tags, content_types, date_from, date_to, created_at "
                "FROM lenses"
            )).fetchall()
            save_lenses([{
                "name": r[0], "domains": r[1], "tags": r[2],
                "content_types": r[3], "date_from": r[4], "date_to": r[5], "created_at": r[6],
            } for r in rows])

            rows = await (await db.execute(
                "SELECT url, title, snippet, notes, added_at FROM watch_later"
            )).fetchall()
            save_watch_later([{
                "url": r[0], "title": r[1], "snippet": r[2],
                "notes": r[3], "added_at": r[4],
            } for r in rows])

        # Índice UNIQUE em lenses.name — necessário para INSERT OR IGNORE funcionar.
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_lenses_name ON lenses(name)"
        )

    if from_version < 28:
        # Adiciona coluna lang ao índice local para suporte multilíngue (pt/en/zh).
        try:
            await db.execute(
                "ALTER TABLE local_index_meta ADD COLUMN lang TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass  # coluna já existe em banco criado com este schema

    if from_version < 29:
        await db.execute(_CREATE_SEARCH_PROFILE)

    if from_version < 30:
        await db.execute(_CREATE_PAGE_KNOWLEDGE)
        await db.execute(_CREATE_TOPIC_INTEREST_PROFILE)

    if from_version < 31:
        await db.execute(_CREATE_PERSONAL_MEMORY)

    if from_version < 32:
        try:
            await db.execute(
                "ALTER TABLE personal_memory ADD COLUMN feedback TEXT DEFAULT NULL"
            )
        except Exception:
            pass  # coluna já existe em DBs novos criados com o DDL atualizado

    if from_version < 33:
        import asyncio as _asyncio
        from services import personal_memory as _pm
        # Copia dados existentes do main DB para personal_memory.db separado
        try:
            rows = await (await db.execute(
                "SELECT id, created_at, type, content, tags, feedback FROM personal_memory"
            )).fetchall()
        except Exception:
            rows = []
        if rows:
            pm_path = _pm._get_pm_db()
            pm_path.parent.mkdir(parents=True, exist_ok=True)

            def _do_migrate(path: str, data: list) -> None:
                import sqlite3
                con = sqlite3.connect(path)
                con.execute("""CREATE TABLE IF NOT EXISTS personal_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    feedback TEXT DEFAULT NULL
                )""")
                con.executemany(
                    "INSERT OR IGNORE INTO personal_memory "
                    "(id, created_at, type, content, tags, feedback) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    data,
                )
                con.commit()
                con.close()

            await _asyncio.to_thread(_do_migrate, str(pm_path), rows)
        # Remove a tabela do DB principal (agora vive em arquivo separado)
        await db.execute("DROP TABLE IF EXISTS personal_memory")

    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )

# ---------------------------------------------------------------------------
# População a partir dos JSONs de dados do usuário
# ---------------------------------------------------------------------------

async def populate_from_user_data(db: aiosqlite.Connection) -> None:
    """Sincroniza DB com os JSONs de dados do usuário (fonte de verdade).

    Chamado a cada startup, após migrations. INSERT OR IGNORE em todas as
    entidades garante idempotência — nunca cria duplicatas se os dados já
    estiverem no banco. Lê de .backup/akasha/ se disponível, senão de userdata/.
    """
    from services.list_sync import (
        load_sites, load_blocked_domains, load_favorites,
        load_lenses, load_watch_later, load_highlights, load_papers,
    )

    for site in load_sites():
        await db.execute(
            "INSERT OR IGNORE INTO crawl_sites "
            "(base_url, label, crawl_depth, subdomains_json) VALUES (?, ?, ?, ?)",
            (
                site["base_url"], site.get("label", ""), site.get("crawl_depth", 2),
                json.dumps(site.get("subdomains", [])),
            ),
        )

    for item in load_blocked_domains():
        await db.execute(
            "INSERT OR IGNORE INTO blocked_domains (domain) VALUES (?)",
            (item["domain"],),
        )

    for item in load_favorites():
        await db.execute(
            "INSERT OR IGNORE INTO favorite_domains (domain, label, priority_score) "
            "VALUES (?, ?, ?)",
            (item["domain"], item.get("label", ""), item.get("priority_score", 10)),
        )

    for lens in load_lenses():
        await db.execute(
            "INSERT OR IGNORE INTO lenses "
            "(name, domains, tags, content_types, date_from, date_to) VALUES (?, ?, ?, ?, ?, ?)",
            (
                lens["name"], lens.get("domains", ""), lens.get("tags", ""),
                lens.get("content_types", ""), lens.get("date_from", ""), lens.get("date_to", ""),
            ),
        )

    for item in load_watch_later():
        cursor = await db.execute(
            "INSERT OR IGNORE INTO watch_later (url, title, snippet, notes) VALUES (?, ?, ?, ?)",
            (item["url"], item.get("title", ""), item.get("snippet", ""), item.get("notes", "")),
        )
        if cursor.lastrowid:
            await db.execute(
                "INSERT INTO watch_later_fts (id, url, title, notes) VALUES (?, ?, ?, ?)",
                (cursor.lastrowid, item["url"], item.get("title", ""), item.get("notes", "")),
            )

    for item in load_highlights():
        cursor = await db.execute(
            "INSERT OR IGNORE INTO highlights (url, exact, prefix, suffix, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                item["url"], item["exact"],
                item.get("prefix", ""), item.get("suffix", ""), item.get("note", ""),
            ),
        )
        if cursor.lastrowid:
            await db.execute(
                "INSERT INTO highlights_fts (rowid, exact, note) VALUES (?, ?, ?)",
                (cursor.lastrowid, item["exact"], item.get("note", "")),
            )

    for item in load_papers():
        await db.execute(
            "INSERT OR IGNORE INTO archive_dois (doi, arxiv_id, path, url) VALUES (?, ?, ?, ?)",
            (item["doi"], item.get("arxiv_id"), item.get("path", ""), item.get("url", "")),
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


# ---------------------------------------------------------------------------
# SimHash helpers (archive deduplication)
# ---------------------------------------------------------------------------

async def find_near_duplicate(simhash_val: int, threshold: int = 3) -> tuple[str, str] | None:
    """
    Busca near-duplicate por distância de Hamming entre SimHashes.
    Retorna (url, path) do primeiro documento arquivado dentro do threshold, ou None.
    Distância de Hamming: número de bits diferentes entre os dois hashes de 64 bits.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                "SELECT simhash, url, path FROM archive_simhashes"
            )).fetchall()
        for stored_hash, stored_url, stored_path in rows:
            if bin(simhash_val ^ stored_hash).count("1") <= threshold:
                return stored_url, stored_path
    except Exception:
        pass
    return None


async def store_archive_simhash(simhash_val: int, path: str, url: str) -> None:
    """Armazena ou atualiza o SimHash de um documento arquivado."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO archive_simhashes (simhash, path, url) VALUES (?, ?, ?)",
            (simhash_val, path, url),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# DOI helpers (archive deduplication by DOI/arXiv ID)
# ---------------------------------------------------------------------------

async def find_archive_by_doi(doi: str) -> tuple[str, str] | None:
    """
    Retorna (path, url) do documento arquivado com esse DOI, ou None.
    Usado para deduplicação antes de baixar artigos científicos.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            row = await (await db.execute(
                "SELECT path, url FROM archive_dois WHERE doi = ?", (doi,)
            )).fetchone()
        return (row[0], row[1]) if row else None
    except Exception:
        return None


async def store_archive_doi(doi: str, arxiv_id: str | None, path: str, url: str) -> None:
    """Armazena o mapeamento DOI → arquivo arquivado."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO archive_dois (doi, arxiv_id, path, url) VALUES (?, ?, ?, ?)",
                (doi, arxiv_id, path, url),
            )
            await db.commit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tag co-occurrence helpers
# ---------------------------------------------------------------------------

async def store_tag_pairs(tags: list[str]) -> None:
    """
    Registra todas as co-ocorrências entre as tags de um documento.
    Armazena (a, b) e (b, a) para que qualquer tag sirva como chave de busca.
    """
    if len(tags) < 2:
        return
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(tags):
        for b in tags[i + 1:]:
            pairs.append((a, b))
            pairs.append((b, a))
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            for tag_a, tag_b in pairs:
                await db.execute(
                    """INSERT INTO tag_pairs (tag_a, tag_b, count) VALUES (?, ?, 1)
                       ON CONFLICT(tag_a, tag_b) DO UPDATE SET count = count + 1""",
                    (tag_a, tag_b),
                )
            await db.commit()
    except Exception:
        pass


async def get_suggested_tags(active_tag: str, limit: int = 8) -> list[str]:
    """Retorna tags que mais co-ocorrem com active_tag, ordenadas por frequência."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                "SELECT tag_b FROM tag_pairs WHERE tag_a = ? ORDER BY count DESC LIMIT ?",
                (active_tag, limit),
            )).fetchall()
        return [row[0] for row in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Doc accesses helpers (usage-based ranking)
# ---------------------------------------------------------------------------

async def record_doc_access(url: str) -> None:
    """Registra abertura de documento. Chamado fire-and-forget no /open-file."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO doc_accesses (url) VALUES (?)", (url,))
        await db.commit()


async def get_access_stats(urls: list[str]) -> dict[str, tuple[int, str]]:
    """Retorna {url: (access_count, last_accessed_iso)} para os URLs fornecidos."""
    if not urls:
        return {}
    placeholders = ",".join("?" * len(urls))
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            f"SELECT url, COUNT(*) AS cnt, MAX(accessed_at) AS last "
            f"FROM doc_accesses WHERE url IN ({placeholders}) GROUP BY url",
            urls,
        )).fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


# ---------------------------------------------------------------------------
# Highlights helpers (W3C Web Annotation Data Model — TextQuoteSelector)
# ---------------------------------------------------------------------------

async def add_highlight(
    url: str,
    exact: str,
    prefix: str = "",
    suffix: str = "",
    note: str = "",
) -> int:
    """Cria highlight e indexa no FTS5. Retorna id do novo registro."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO highlights (url, exact, prefix, suffix, note) VALUES (?, ?, ?, ?, ?)",
            (url, exact, prefix, suffix, note),
        )
        highlight_id = cur.lastrowid or 0
        if highlight_id:
            await db.execute(
                "INSERT INTO highlights_fts (rowid, exact, note) VALUES (?, ?, ?)",
                (highlight_id, exact, note),
            )
        await db.commit()
    return highlight_id


async def get_highlights_for_url(url: str) -> list[tuple]:
    """Retorna highlights de um documento: (id, exact, prefix, suffix, note, created_at)."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT id, exact, prefix, suffix, note, created_at "
            "FROM highlights WHERE url = ? ORDER BY created_at",
            (url,),
        )).fetchall()
    return list(rows)


async def delete_highlight(highlight_id: int) -> None:
    """Remove highlight e sua entrada no FTS5."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM highlights_fts WHERE rowid = ?", (highlight_id,))
        await db.execute("DELETE FROM highlights WHERE id = ?", (highlight_id,))
        await db.commit()


async def search_highlights(query: str, limit: int = 20) -> list[tuple]:
    """Busca FTS5 em highlights. Retorna (highlight_id, url, exact, note)."""
    import re
    cleaned = re.sub(r'["\'\(\)\*\:\^]', " ", query).strip()
    if not cleaned:
        return []
    fts_q = " ".join(f"{t}*" for t in cleaned.split() if t)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                """SELECT h.id, h.url, h.exact, h.note
                   FROM highlights_fts f
                   JOIN highlights h ON h.id = f.rowid
                   WHERE highlights_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_q, limit),
            )).fetchall()
        return list(rows)
    except Exception:
        return []


async def count_highlights_for_url(url: str) -> int:
    """Conta highlights de um documento (usado para annotation density)."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT COUNT(*) FROM highlights WHERE url = ?", (url,)
        )).fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Search history helpers (autocomplete)
# ---------------------------------------------------------------------------

async def record_search_query(query: str) -> None:
    """Registra ou incrementa query no histórico de buscas (para autocomplete)."""
    query = query.strip()
    if not query:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO search_history (query, count, last_used)
               VALUES (?, 1, datetime('now'))
               ON CONFLICT(query) DO UPDATE SET
                   count    = count + 1,
                   last_used = datetime('now')""",
            (query,),
        )
        await db.commit()


async def get_query_suggestions(prefix: str, limit: int = 10) -> list[str]:
    """Retorna queries do histórico que começam com prefix, ordenadas por frequência."""
    if not prefix.strip():
        return []
    pattern = f"{prefix.strip()}%"
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT query FROM search_history "
            "WHERE query LIKE ? "
            "ORDER BY count DESC, last_used DESC "
            "LIMIT ?",
            (pattern, limit),
        )).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Co-reading patterns helpers
# ---------------------------------------------------------------------------

async def get_highlight_counts(urls: list[str]) -> dict[str, int]:
    """Retorna {url: highlight_count} para os URLs fornecidos (batch query)."""
    if not urls:
        return {}
    placeholders = ",".join("?" * len(urls))
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            f"SELECT url, COUNT(*) FROM highlights WHERE url IN ({placeholders}) GROUP BY url",
            urls,
        )).fetchall()
    return {row[0]: row[1] for row in rows}


async def get_coread_urls(
    url: str,
    window_seconds: int = 7200,
    limit: int = 8,
) -> list[tuple[str, str, int]]:
    """Retorna documentos lidos na mesma janela temporal que url.

    Usa self-join em doc_accesses: dois acessos são "co-leitura" quando a
    diferença absoluta de tempo entre eles é menor que window_seconds (padrão 2h).
    Retorna lista de (url, display_name, co_count) ordenada por co_count DESC.
    """
    from urllib.parse import unquote
    from pathlib import PurePosixPath

    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            """SELECT a2.url, COUNT(*) AS co_count
               FROM doc_accesses a1
               JOIN doc_accesses a2
                 ON ABS(strftime('%s', a1.accessed_at) - strftime('%s', a2.accessed_at)) < ?
                AND a2.url != a1.url
               WHERE a1.url = ?
               GROUP BY a2.url
               ORDER BY co_count DESC
               LIMIT ?""",
            (window_seconds, url, limit),
        )).fetchall()

    result: list[tuple[str, str, int]] = []
    for row_url, count in rows:
        raw = unquote(row_url)
        name = PurePosixPath(raw).name or raw
        result.append((row_url, name, count))
    return result


# ---------------------------------------------------------------------------
# Lenses helpers (filtros nomeados persistentes)
# ---------------------------------------------------------------------------

def _row_to_lens(row: tuple) -> dict:
    return {
        "id": row[0], "name": row[1], "domains": row[2],
        "tags": row[3], "content_types": row[4],
        "date_from": row[5], "date_to": row[6], "created_at": row[7],
    }


async def create_lens(
    name: str,
    domains: str = "",
    tags: str = "",
    content_types: str = "",
    date_from: str = "",
    date_to: str = "",
) -> int:
    """Cria uma nova lens. Retorna o id gerado."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO lenses (name, domains, tags, content_types, date_from, date_to) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, domains, tags, content_types, date_from, date_to),
        )
        await db.commit()
        return cur.lastrowid or 0


async def list_lenses() -> list[dict]:
    """Retorna todas as lenses ordenadas da mais recente para a mais antiga."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT id, name, domains, tags, content_types, date_from, date_to, created_at "
            "FROM lenses ORDER BY created_at DESC"
        )).fetchall()
    return [_row_to_lens(r) for r in rows]


async def get_lens(lens_id: int) -> dict | None:
    """Retorna uma lens por id, ou None se não existir."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT id, name, domains, tags, content_types, date_from, date_to, created_at "
            "FROM lenses WHERE id = ?",
            (lens_id,),
        )).fetchone()
    return _row_to_lens(row) if row else None


async def update_lens(
    lens_id: int,
    name: str,
    domains: str = "",
    tags: str = "",
    content_types: str = "",
    date_from: str = "",
    date_to: str = "",
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE lenses SET name=?, domains=?, tags=?, content_types=?, date_from=?, date_to=? "
            "WHERE id=?",
            (name, domains, tags, content_types, date_from, date_to, lens_id),
        )
        await db.commit()


async def delete_lens(lens_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM lenses WHERE id = ?", (lens_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# Citation graph helpers (bibliographic coupling)
# ---------------------------------------------------------------------------

async def store_citations(path: str, dois: list[tuple[str, str]]) -> None:
    """Armazena DOIs encontrados num documento arquivado.

    path: caminho de filesystem do arquivo (mesmo formato que local_fts.path).
    dois: lista de (doi, title) — title pode ser vazio se CrossRef não respondeu.
    Usa INSERT OR IGNORE para ser idempotente em re-arquivamentos.
    """
    if not dois:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR IGNORE INTO doc_citations (citing_url, cited_doi, cited_title) "
            "VALUES (?, ?, ?)",
            [(path, doi, title) for doi, title in dois],
        )
        await db.commit()


async def get_coupled_docs(
    path: str, limit: int = 5
) -> list[tuple[str, str, int]]:
    """Documentos do arquivo que citam os mesmos trabalhos que path (bibliographic coupling).

    Retorna lista de (path, title, shared_doi_count) ordenada por shared_doi_count desc.
    Apenas documentos com pelo menos 1 DOI em comum.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            """SELECT dc2.citing_url, COUNT(dc2.cited_doi) AS shared
               FROM doc_citations dc1
               JOIN doc_citations dc2 ON dc1.cited_doi = dc2.cited_doi
               WHERE dc1.citing_url = ? AND dc2.citing_url != ?
               GROUP BY dc2.citing_url
               ORDER BY shared DESC
               LIMIT ?""",
            (path, path, limit),
        )).fetchall()
    if not rows:
        return []
    results: list[tuple[str, str, int]] = []
    async with aiosqlite.connect(DB_PATH) as db:
        for (coupled_path, shared) in rows:
            title_row = await (await db.execute(
                "SELECT title FROM local_fts WHERE path = ? LIMIT 1",
                (coupled_path,),
            )).fetchone()
            title = title_row[0] if title_row else coupled_path
            results.append((coupled_path, title, shared))
    return results


# ---------------------------------------------------------------------------
# More-from-source helpers ("Mais deste domínio")
# ---------------------------------------------------------------------------

async def get_more_from_source(path: str, n: int = 5) -> list[tuple[str, str]]:
    """Documentos arquivados do mesmo domínio, ordenados por data de arquivamento.

    Usa archive_simhashes (tem URL original + path) para descobrir o netloc do
    documento atual, depois busca outros docs com mesmo netloc na URL original.
    Retorna lista de (path, title).
    """
    from urllib.parse import urlparse

    async with aiosqlite.connect(DB_PATH) as db:
        # Descobre URL original do documento atual
        row = await (await db.execute(
            "SELECT url FROM archive_simhashes WHERE path = ?",
            (path,),
        )).fetchone()
    if not row:
        return []

    netloc = urlparse(row[0]).netloc
    if not netloc:
        return []

    # Busca outros arquivamentos excluindo o atual (limite conservador para pessoal)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            """SELECT asim.path, lf.title, asim.url
               FROM archive_simhashes asim
               LEFT JOIN local_fts lf ON lf.path = asim.path
               WHERE asim.path != ?
               ORDER BY asim.id DESC
               LIMIT 300""",
            (path,),
        )).fetchall()

    return [
        (r[0], r[1] or r[0])
        for r in rows
        if urlparse(r[2]).netloc == netloc
    ][:n]


# ---------------------------------------------------------------------------
# Perfil persistente de preferências de busca
# ---------------------------------------------------------------------------

async def get_profile_value(key: str, default: str = "") -> str:
    """Lê um valor do perfil de preferências de busca."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT value FROM search_profile WHERE key = ?", (key,)
        )).fetchone()
    return row[0] if row else default


async def set_profile_value(key: str, value: str) -> None:
    """Escreve um valor no perfil de preferências de busca."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO search_profile (key, value, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (key, value),
        )
        await db.commit()


async def get_full_profile() -> dict[str, str]:
    """Retorna o perfil completo como dicionário {key: value}."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT key, value FROM search_profile"
        )).fetchall()
    return {r[0]: r[1] for r in rows}


# ---------------------------------------------------------------------------
# KnowledgeWorker helpers (page_knowledge + topic_interest_profile)
# ---------------------------------------------------------------------------

async def save_page_knowledge(
    url: str,
    title: str,
    summary: str,
    topics: list[str],
    entities: list[str],
    source_type: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO page_knowledge
               (url, title, summary, topics, entities, source_type, processed_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (url, title, summary, json.dumps(topics), json.dumps(entities), source_type),
        )
        await db.commit()


async def get_page_knowledge(url: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT url, title, summary, topics, entities, source_type, processed_at "
            "FROM page_knowledge WHERE url = ?",
            (url,),
        )).fetchone()
    if not row:
        return None
    return {
        "url": row[0], "title": row[1], "summary": row[2],
        "topics": json.loads(row[3] or "[]"),
        "entities": json.loads(row[4] or "[]"),
        "source_type": row[5], "processed_at": row[6],
    }


async def get_page_knowledge_batch(urls: list[str]) -> dict[str, dict]:
    """Retorna {url: knowledge_dict} para os URLs fornecidos."""
    if not urls:
        return {}
    placeholders = ",".join("?" * len(urls))
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            f"SELECT url, topics FROM page_knowledge WHERE url IN ({placeholders})",
            urls,
        )).fetchall()
    return {r[0]: json.loads(r[1] or "[]") for r in rows}


async def update_topic_score(topic: str, delta: float = 1.0) -> None:
    """Incrementa score de um tópico no perfil de interesse."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO topic_interest_profile (topic, score, query_count, last_updated)
               VALUES (?, ?, 1, datetime('now'))
               ON CONFLICT(topic) DO UPDATE SET
                   score        = score + ?,
                   query_count  = query_count + 1,
                   last_updated = datetime('now')""",
            (topic, delta, delta),
        )
        await db.commit()


async def get_topic_score(topic: str) -> float | None:
    """Retorna o score atual de um tópico, ou None se não existir."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT score FROM topic_interest_profile WHERE topic = ?", (topic,)
        )).fetchone()
    return row[0] if row else None


async def get_top_topics(n: int = 10) -> list[tuple[str, float]]:
    """Retorna os N tópicos com maior score, em ordem decrescente."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT topic, score FROM topic_interest_profile "
            "ORDER BY score DESC LIMIT ?",
            (n,),
        )).fetchall()
    return [(r[0], r[1]) for r in rows]


async def get_recent_page_knowledge(n: int = 10) -> list[dict]:
    """Retorna os N registros de page_knowledge mais recentes."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT url, title, summary, topics FROM page_knowledge "
            "ORDER BY processed_at DESC LIMIT ?",
            (n,),
        )).fetchall()
    return [
        {
            "url": r[0], "title": r[1], "summary": r[2],
            "topics": json.loads(r[3] or "[]"),
        }
        for r in rows
    ]


async def get_recent_search_history(n: int = 20) -> list[dict]:
    """Retorna as N queries mais recentes do histórico de buscas."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT query, count, last_used FROM search_history "
            "ORDER BY last_used DESC LIMIT ?",
            (n,),
        )).fetchall()
    return [{"query": r[0], "count": r[1], "last_used": r[2]} for r in rows]


async def decay_old_topic_scores(days_inactive: int = 7, factor: float = 0.97) -> int:
    """Aplica decaimento EMA em tópicos sem atualização há mais de `days_inactive` dias.

    Remove tópicos com score abaixo de 0.01 para evitar acúmulo de ruído.
    Retorna o número de tópicos afetados.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            f"""UPDATE topic_interest_profile
                SET score = score * ?
                WHERE last_updated < datetime('now', '-{days_inactive} days')""",
            (factor,),
        )
        affected = cur.rowcount
        await db.execute(
            "DELETE FROM topic_interest_profile WHERE score < 0.01"
        )
        await db.commit()
    return affected


async def upsert_entity_pair(entity: str, co_entity: str, delta: float = 1.0) -> None:
    """Incrementa peso do par (entity, co_entity) no entity_graph.

    Garante ordem canônica (alfabética) para evitar pares duplicados invertidos.
    """
    a, b = sorted([entity.strip().lower(), co_entity.strip().lower()])
    if a == b:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO entity_graph (entity, co_entity, weight, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(entity, co_entity) DO UPDATE SET
                   weight     = weight + ?,
                   updated_at = datetime('now')""",
            (a, b, delta, delta),
        )
        await db.commit()


async def get_entity_neighbors(entity: str, n: int = 10) -> list[tuple[str, float]]:
    """Retorna os N co-entes com maior peso associados a `entity`."""
    e = entity.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            """SELECT co_entity, weight FROM entity_graph WHERE entity = ?
               UNION ALL
               SELECT entity, weight FROM entity_graph WHERE co_entity = ?
               ORDER BY weight DESC LIMIT ?""",
            (e, e, n),
        )).fetchall()
    return [(r[0], r[1]) for r in rows]


async def count_page_knowledge() -> int:
    """Número total de registros em page_knowledge."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM page_knowledge")).fetchone()
    return row[0] if row else 0
