"""
AKASHA — Banco de dados SQLite
Schema, migrations e função de inicialização.
"""
from __future__ import annotations

import json

import aiosqlite

from config import DB_PATH

# Banco de metadados LLM — separado do banco do crawler por princípio arquitetural.
# akasha.db contém apenas dados do crawler (sites, páginas, fila, DOIs).
# akasha_knowledge.db contém metadados gerados por LLM (topics, entities, interesse).
KNOWLEDGE_DB_PATH = DB_PATH.parent / "akasha_knowledge.db"

# ---------------------------------------------------------------------------
# Versão do schema — incrementar a cada migration
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 49

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
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    query_hash   TEXT,
    cached_at    INTEGER NOT NULL DEFAULT 0,
    ttl_hours    INTEGER NOT NULL DEFAULT 1
);
"""

_CREATE_IDX_CACHE = """
CREATE INDEX IF NOT EXISTS idx_cache_lookup
    ON search_cache(query, sources, created_at);
"""

_CREATE_IDX_SEARCH_CACHE_HASH = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_search_cache_hash
    ON search_cache(query_hash) WHERE query_hash IS NOT NULL;
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
    path    TEXT    PRIMARY KEY,
    source  TEXT    NOT NULL,
    mtime   TEXT    NOT NULL,
    lang    TEXT    NOT NULL DEFAULT '',
    deleted INTEGER NOT NULL DEFAULT 0
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
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    base_url            TEXT    NOT NULL UNIQUE,
    label               TEXT    NOT NULL DEFAULT '',
    crawl_depth         INTEGER NOT NULL DEFAULT 2,
    subdomains_json     TEXT    NOT NULL DEFAULT '[]',
    page_count          INTEGER NOT NULL DEFAULT 0,
    last_crawled_at     TEXT,
    status              TEXT    NOT NULL DEFAULT 'idle',
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    crawl_interval_days INTEGER NOT NULL DEFAULT 7,
    deleted             INTEGER NOT NULL DEFAULT 0,
    crawl_fail_count    INTEGER NOT NULL DEFAULT 0,
    crawl_frequency     TEXT    NOT NULL DEFAULT 'weekly',
    next_crawl_at       INTEGER NOT NULL DEFAULT 0,
    content_hash        TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_CRAWL_PAGES = """
CREATE TABLE IF NOT EXISTS crawl_pages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id          INTEGER NOT NULL REFERENCES crawl_sites(id) ON DELETE CASCADE,
    url              TEXT    NOT NULL UNIQUE,
    title            TEXT    NOT NULL DEFAULT '',
    content_md       TEXT    NOT NULL DEFAULT '',
    content_hash     TEXT    NOT NULL DEFAULT '',
    http_status      INTEGER NOT NULL DEFAULT 0,
    etag             TEXT    NOT NULL DEFAULT '',
    last_modified    TEXT    NOT NULL DEFAULT '',
    crawled_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    last_modified_at TEXT    NOT NULL DEFAULT '',
    last_checked_at  TEXT    NOT NULL DEFAULT ''
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

_CREATE_PAGE_IMAGES = """
CREATE TABLE IF NOT EXISTS page_images (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url   TEXT    NOT NULL,
    img_url    TEXT    NOT NULL UNIQUE,
    alt_text   TEXT    NOT NULL DEFAULT '',
    title      TEXT    NOT NULL DEFAULT '',
    phash      TEXT    NOT NULL DEFAULT '',
    crawled_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_PAGE_IMAGES_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS page_images_fts USING fts5(
    img_url  UNINDEXED,
    page_url UNINDEXED,
    alt_text,
    title,
    phash    UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

_CREATE_IDX_PAGE_IMAGES_PAGE = """
CREATE INDEX IF NOT EXISTS idx_page_images_page ON page_images(page_url);
"""

_CREATE_IDX_PAGE_IMAGES_PHASH = """
CREATE INDEX IF NOT EXISTS idx_page_images_phash ON page_images(phash) WHERE phash != '';
"""


_CREATE_SITE_SUGGESTIONS = """
CREATE TABLE IF NOT EXISTS site_suggestions (
    domain      TEXT PRIMARY KEY,
    score       REAL NOT NULL DEFAULT 0.0,
    reason      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    updated_at  INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_IDX_SITE_SUGGESTIONS_STATUS = """
CREATE INDEX IF NOT EXISTS idx_site_suggestions_status ON site_suggestions(status);
"""


_CREATE_PAGE_LINKS = """
CREATE TABLE IF NOT EXISTS page_links (
    source_url  TEXT NOT NULL,
    target_url  TEXT NOT NULL,
    PRIMARY KEY (source_url, target_url)
);
"""

_CREATE_IDX_PAGE_LINKS_SOURCE = """
CREATE INDEX IF NOT EXISTS idx_page_links_source ON page_links(source_url);
"""

_CREATE_IDX_PAGE_LINKS_TARGET = """
CREATE INDEX IF NOT EXISTS idx_page_links_target ON page_links(target_url);
"""

_CREATE_PAGE_RANK = """
CREATE TABLE IF NOT EXISTS page_rank (
    url         TEXT PRIMARY KEY,
    score       REAL NOT NULL DEFAULT 1.0,
    updated_at  INTEGER NOT NULL DEFAULT 0
);
"""


_CREATE_CLICK_LOG = """
CREATE TABLE IF NOT EXISTS click_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    query_norm       TEXT    NOT NULL DEFAULT '',
    url              TEXT    NOT NULL DEFAULT '',
    domain           TEXT    NOT NULL DEFAULT '',
    position_clicked INTEGER NOT NULL DEFAULT 0,
    session_id       TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_CLICK_LOG_DOMAIN = """
CREATE INDEX IF NOT EXISTS idx_click_log_domain
    ON click_log(domain, timestamp);
"""

_CREATE_IDX_CLICK_LOG_TS = """
CREATE INDEX IF NOT EXISTS idx_click_log_ts ON click_log(timestamp);
"""

_CREATE_DOMAIN_BOOSTS = """
CREATE TABLE IF NOT EXISTS domain_boosts (
    domain     TEXT PRIMARY KEY,
    boost      REAL NOT NULL DEFAULT 1.0,
    updated_at INTEGER NOT NULL DEFAULT 0
);
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

_CREATE_PAGE_EMBEDDINGS = """
CREATE TABLE IF NOT EXISTS page_embeddings (
    id         INTEGER PRIMARY KEY,
    url        TEXT    NOT NULL UNIQUE,
    model      TEXT    NOT NULL DEFAULT '',
    dim        INTEGER NOT NULL DEFAULT 768,
    updated_at TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (url) REFERENCES crawl_pages(url) ON DELETE CASCADE
);
"""

_CREATE_IDX_PAGE_EMBEDDINGS_URL = """
CREATE INDEX IF NOT EXISTS idx_page_embeddings_url ON page_embeddings(url);
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
    -- Tabela de METADADOS DE INDEXAÇÃO — não armazena texto narrativo sintetizado por LLM.
    -- Princípio: AKASHA é amplificador de pesquisa, nunca respondedor.
    -- topics/entities são rótulos estruturados (JSON arrays de strings) usados para roteamento:
    --   topics → autocomplete, topic_interest_profile, knowledge_boost em search_local
    --   entities → entity_graph (grafo de co-ocorrência para busca por entidade)
    -- O campo summary foi removido na migration v38 por violar esse princípio.
    url          TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT '',
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
    feedback   TEXT DEFAULT NULL,
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

_CREATE_WIKI_CACHE = """
CREATE TABLE IF NOT EXISTS wiki_cache (
    query_hash  TEXT    PRIMARY KEY,
    data_json   TEXT    NOT NULL,
    cached_at   INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_GEO_CACHE = """
CREATE TABLE IF NOT EXISTS geo_cache (
    city_key    TEXT    PRIMARY KEY,
    lat         REAL    NOT NULL,
    lon         REAL    NOT NULL,
    cached_at   INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_WIKI_CITATION_COUNTS = """
CREATE TABLE IF NOT EXISTS wiki_citation_counts (
    domain    TEXT    PRIMARY KEY,
    count     INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT    NOT NULL DEFAULT ''
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
        try:
            await db.execute(_CREATE_IDX_SEARCH_CACHE_HASH)
        except Exception:
            pass  # coluna query_hash ausente em banco pré-v44 — migração adiciona a seguir
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
        await db.execute(_CREATE_PAGE_IMAGES)
        await db.execute(_CREATE_PAGE_IMAGES_FTS)
        await db.execute(_CREATE_IDX_PAGE_IMAGES_PAGE)
        await db.execute(_CREATE_IDX_PAGE_IMAGES_PHASH)
        await db.execute(_CREATE_PAGE_LINKS)
        await db.execute(_CREATE_IDX_PAGE_LINKS_SOURCE)
        await db.execute(_CREATE_IDX_PAGE_LINKS_TARGET)
        await db.execute(_CREATE_PAGE_RANK)
        await db.execute(_CREATE_SITE_SUGGESTIONS)
        await db.execute(_CREATE_IDX_SITE_SUGGESTIONS_STATUS)
        await db.execute(_CREATE_CLICK_LOG)
        await db.execute(_CREATE_IDX_CLICK_LOG_DOMAIN)
        await db.execute(_CREATE_IDX_CLICK_LOG_TS)
        await db.execute(_CREATE_DOMAIN_BOOSTS)
        await db.execute(_CREATE_WATCH_LATER)
        await db.execute(_CREATE_WATCH_LATER_FTS)
        await db.execute(_CREATE_ACTIVITY_LOG)
        await db.execute(_CREATE_IDX_ACTIVITY_LOG)
        await db.execute(_CREATE_LOCAL_VEC_PATHS)
        await db.execute(_CREATE_PAGE_EMBEDDINGS)
        await db.execute(_CREATE_IDX_PAGE_EMBEDDINGS_URL)
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
        await db.execute(_CREATE_WIKI_CACHE)
        await db.execute(_CREATE_GEO_CACHE)
        # page_knowledge, topic_interest_profile e entity_graph vivem em
        # akasha_knowledge.db — ver init_knowledge_db() abaixo.

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
    await init_knowledge_db()


async def init_knowledge_db() -> None:
    """Cria akasha_knowledge.db e migra dados legados do banco principal (one-time)."""
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute(_CREATE_PAGE_KNOWLEDGE)
        await db.execute(_CREATE_TOPIC_INTEREST_PROFILE)
        await db.execute(_CREATE_ENTITY_GRAPH)

        # Migração one-time: copia dados do akasha.db se knowledge DB está vazio
        row = await (await db.execute(
            "SELECT COUNT(*) FROM page_knowledge"
        )).fetchone()
        if row and row[0] == 0:
            try:
                import aiosqlite as _aio
                async with _aio.connect(DB_PATH) as src:
                    for table in ("page_knowledge", "topic_interest_profile", "entity_graph"):
                        try:
                            cols_rows = await (await src.execute(
                                f"PRAGMA table_info({table})"
                            )).fetchall()
                            if not cols_rows:
                                continue
                            cols = [r[1] for r in cols_rows]
                            # Filtra colunas que existem no novo DDL
                            dst_cols_rows = await (await db.execute(
                                f"PRAGMA table_info({table})"
                            )).fetchall()
                            dst_cols = {r[1] for r in dst_cols_rows}
                            shared = [c for c in cols if c in dst_cols]
                            col_list = ", ".join(shared)
                            rows = await (await src.execute(
                                f"SELECT {col_list} FROM {table}"
                            )).fetchall()
                            if rows:
                                placeholders = ", ".join("?" * len(shared))
                                await db.executemany(
                                    f"INSERT OR IGNORE INTO {table} ({col_list}) "
                                    f"VALUES ({placeholders})",
                                    rows,
                                )
                        except Exception:
                            pass  # tabela não existe no banco legado — ok para bancos novos
            except Exception:
                pass

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

    # from_version < 30: page_knowledge e topic_interest_profile agora em
    # akasha_knowledge.db — migrados via init_knowledge_db(), não aqui.

    if from_version < 31:
        await db.execute(_CREATE_PERSONAL_MEMORY)

    if from_version < 32:
        try:
            await db.execute(
                "ALTER TABLE personal_memory ADD COLUMN feedback TEXT DEFAULT NULL"
            )
        except Exception:
            pass  # coluna já existe em DBs novos criados com o DDL atualizado

    # from_version < 35: entity_graph agora em akasha_knowledge.db com feedback
    # incluído no DDL desde o início — nenhuma migration necessária aqui.

    if from_version < 38:
        # Remove summary de page_knowledge — texto sintetizado por LLM viola o
        # princípio de que AKASHA é amplificador de pesquisa, não respondedor.
        try:
            await db.execute("ALTER TABLE page_knowledge DROP COLUMN summary")
        except Exception:
            pass  # coluna já removida ou banco novo sem a coluna

    if from_version < 37:
        # Flag de deduplicação desacoplada do conteúdo LLM em page_knowledge.
        # Permite limpar page_knowledge sem perder o controle de quais páginas
        # já foram processadas pelo knowledge_worker.
        try:
            await db.execute(
                "ALTER TABLE crawl_pages "
                "ADD COLUMN knowledge_processed INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # coluna já existe

    if from_version < 36:
        try:
            await db.execute(
                "ALTER TABLE local_index_meta ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass
        try:
            await db.execute(
                "ALTER TABLE crawl_sites ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass
        try:
            await db.execute(
                "ALTER TABLE crawl_sites ADD COLUMN crawl_fail_count INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass

    if from_version < 34:
        try:
            await db.execute(
                "ALTER TABLE crawl_sites ADD COLUMN crawl_interval_days INTEGER NOT NULL DEFAULT 7"
            )
        except Exception:
            pass  # coluna já existe em banco criado com este schema

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

    if from_version < 39:
        # Frequência adaptativa de crawl: classificação automática daily/weekly/monthly.
        # crawl_sites: crawl_frequency (legível) + next_crawl_at (timestamp Unix de próximo crawl)
        #              content_hash (hash da homepage para detecção rápida de mudança)
        # crawl_pages: last_modified_at (quando o conteúdo mudou de fato)
        #              last_checked_at (quando verificamos, mesmo sem mudança)
        for col, ddl in [
            ("crawl_frequency", "ALTER TABLE crawl_sites ADD COLUMN crawl_frequency TEXT NOT NULL DEFAULT 'weekly'"),
            ("next_crawl_at",   "ALTER TABLE crawl_sites ADD COLUMN next_crawl_at   INTEGER NOT NULL DEFAULT 0"),
            ("content_hash",    "ALTER TABLE crawl_sites ADD COLUMN content_hash    TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                await db.execute(ddl)
            except Exception:
                pass  # coluna já existe
        for col, ddl in [
            ("last_modified_at", "ALTER TABLE crawl_pages ADD COLUMN last_modified_at TEXT NOT NULL DEFAULT ''"),
            ("last_checked_at",  "ALTER TABLE crawl_pages ADD COLUMN last_checked_at  TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                await db.execute(ddl)
            except Exception:
                pass

    if from_version < 40:
        # Índice de imagens das páginas crawleadas.
        # pHash 64-bit (hex) para detecção de near-duplicates via distância de Hamming ≤ 10.
        # FTS5 sobre alt_text + title para busca semântica.
        try:
            await db.execute(_CREATE_PAGE_IMAGES)
        except Exception:
            pass
        try:
            await db.execute(_CREATE_PAGE_IMAGES_FTS)
        except Exception:
            pass
        try:
            await db.execute(_CREATE_IDX_PAGE_IMAGES_PAGE)
        except Exception:
            pass
        try:
            await db.execute(_CREATE_IDX_PAGE_IMAGES_PHASH)
        except Exception:
            pass

    if from_version < 41:
        # Grafo de links para Personalized PageRank.
        # page_links: arestas extraídas durante crawling (source → target).
        # page_rank: scores normalizados 0.8–1.2 computados semanalmente.
        for ddl in (
            _CREATE_PAGE_LINKS,
            _CREATE_IDX_PAGE_LINKS_SOURCE,
            _CREATE_IDX_PAGE_LINKS_TARGET,
            _CREATE_PAGE_RANK,
        ):
            try:
                await db.execute(ddl)
            except Exception:
                pass

    if from_version < 42:
        # Sugestões automáticas de domínios para a Biblioteca.
        # score composto de 3 sinais: aparições em search_cache, cliques ponderados, refs em page_links.
        for ddl in (_CREATE_SITE_SUGGESTIONS, _CREATE_IDX_SITE_SUGGESTIONS_STATUS):
            try:
                await db.execute(ddl)
            except Exception:
                pass

    if from_version < 43:
        # Log de cliques para Learning to Rank (domain_boost).
        # click_log: registra cada clique com posição para cálculo de DCG-style boost.
        # domain_boosts: scores semanais computados sobre os últimos 90 dias de cliques.
        for ddl in (
            _CREATE_CLICK_LOG,
            _CREATE_IDX_CLICK_LOG_DOMAIN,
            _CREATE_IDX_CLICK_LOG_TS,
            _CREATE_DOMAIN_BOOSTS,
        ):
            try:
                await db.execute(ddl)
            except Exception:
                pass

    if from_version < 44:
        # Cache dois níveis para busca web: adiciona query_hash (chave de lookup),
        # cached_at (timestamp Unix) e ttl_hours ao search_cache existente.
        # Entradas antigas (sem query_hash) permanecem válidas até expirar pelo TTL legado.
        for col, ddl in [
            ("query_hash", "ALTER TABLE search_cache ADD COLUMN query_hash TEXT"),
            ("cached_at",  "ALTER TABLE search_cache ADD COLUMN cached_at  INTEGER NOT NULL DEFAULT 0"),
            ("ttl_hours",  "ALTER TABLE search_cache ADD COLUMN ttl_hours  INTEGER NOT NULL DEFAULT 1"),
        ]:
            try:
                await db.execute(ddl)
            except Exception:
                pass  # coluna já existe em banco criado com este schema
        try:
            await db.execute(_CREATE_IDX_SEARCH_CACHE_HASH)
        except Exception:
            pass

    if from_version < 45:
        # Wikipedia knowledge card: cache local por 7 dias evita requests repetidos.
        try:
            await db.execute(_CREATE_WIKI_CACHE)
        except Exception:
            pass

    if from_version < 46:
        # Geocoding cache: coordenadas por cidade persistidas por 30 dias.
        try:
            await db.execute(_CREATE_GEO_CACHE)
        except Exception:
            pass

    if from_version < 47:
        # Sinal 4 do suggester: frequência de citação por artigos da Wikipedia.
        try:
            await db.execute(_CREATE_WIKI_CITATION_COUNTS)
        except Exception:
            pass

    if from_version < 48:
        # word_count: número de palavras do content_md — filtra páginas vazias/navegação.
        try:
            await db.execute(
                "ALTER TABLE crawl_pages ADD COLUMN word_count INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # coluna já existe
        try:
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_crawl_pages_word_count "
                "ON crawl_pages(word_count)"
            )
        except Exception:
            pass

    if from_version < 49:
        # page_embeddings: metadados de embedding para páginas crawleadas.
        # page_vec (sqlite-vec virtual table) é criada por semantic_search.py
        # na primeira chamada — requer extensão sqlite-vec carregada.
        try:
            await db.execute(_CREATE_PAGE_EMBEDDINGS)
        except Exception:
            pass  # tabela já existe em bancos migrados
        try:
            await db.execute(_CREATE_IDX_PAGE_EMBEDDINGS_URL)
        except Exception:
            pass

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
            "SELECT * FROM crawl_sites WHERE deleted=0 ORDER BY created_at DESC"
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


async def reset_stuck_crawling_sites() -> int:
    """Reseta sites presos em status='crawling' de uma execução anterior para 'idle'.

    Sites ficam presos quando o processo é encerrado abruptamente durante um crawl.
    Chamado no startup antes de qualquer tarefa de background.
    Retorna o número de sites resetados.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE crawl_sites SET status='idle' WHERE status='crawling'"
        )
        await db.commit()
        return cursor.rowcount


async def update_crawl_site(
    site_id: int,
    label: str,
    crawl_depth: int,
    crawl_interval_days: int,
    crawl_frequency: str | None = None,
) -> None:
    import time as _time
    _FREQ_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}
    async with aiosqlite.connect(DB_PATH) as db:
        if crawl_frequency and crawl_frequency in _FREQ_DAYS:
            next_at = int(_time.time() + _FREQ_DAYS[crawl_frequency] * 86400)
            await db.execute(
                """UPDATE crawl_sites
                   SET label = ?, crawl_depth = ?, crawl_interval_days = ?,
                       crawl_frequency = ?, next_crawl_at = ?
                   WHERE id = ?""",
                (label, crawl_depth, crawl_interval_days, crawl_frequency, next_at, site_id),
            )
        else:
            await db.execute(
                """UPDATE crawl_sites
                   SET label = ?, crawl_depth = ?, crawl_interval_days = ?
                   WHERE id = ?""",
                (label, crawl_depth, crawl_interval_days, site_id),
            )
        await db.commit()


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


async def get_crawl_page_by_id(page_id: int) -> tuple | None:
    """Retorna a crawl_page completa (com content_md) para o ID dado."""
    async with aiosqlite.connect(DB_PATH) as db:
        return await (await db.execute(
            "SELECT id, site_id, url, title, content_md, http_status, crawled_at "
            "FROM crawl_pages WHERE id = ?",
            (page_id,),
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


async def log_visit_dedup(url: str, title: str, window_minutes: int = 60) -> None:
    """Registra visita em activity_log; ignora se a mesma URL já foi registrada na janela."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT id FROM activity_log WHERE type='visit' AND url=?"
            " AND created_at >= datetime('now', ?)",
            (url, f"-{window_minutes} minutes"),
        )).fetchone()
        if row:
            return
        await db.execute(
            "INSERT INTO activity_log (type, title, url, meta_json) VALUES ('visit', ?, ?, '{}')",
            (title or url, url),
        )
        await db.commit()


async def get_recent_visits(n: int = 20) -> list[dict]:
    """Retorna as N visitas mais recentes para alimentar o loop de reflexão."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT title, url, created_at FROM activity_log WHERE type='visit'"
            " ORDER BY id DESC LIMIT ?",
            (n,),
        )).fetchall()
    return [{"title": r[0], "url": r[1], "created_at": r[2]} for r in rows]


async def get_top_visited_domains(n: int = 10) -> list[tuple[str, int]]:
    """Retorna os N domínios mais visitados (domínio, contagem) para análise de interesses."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            """
            SELECT
                LOWER(REPLACE(REPLACE(SUBSTR(url, INSTR(url, '://') + 3),
                    CASE WHEN INSTR(SUBSTR(url, INSTR(url, '://') + 3), '/') > 0
                         THEN SUBSTR(SUBSTR(url, INSTR(url, '://') + 3),
                                     INSTR(SUBSTR(url, INSTR(url, '://') + 3), '/'))
                         ELSE ''
                    END, ''), 'www.', '')) AS domain,
                COUNT(*) AS cnt
            FROM activity_log
            WHERE type = 'visit'
            GROUP BY domain
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (n,),
        )).fetchall()
    return [(r[0], r[1]) for r in rows]


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
    """Armazena o mapeamento DOI → arquivo arquivado e aciona backup JSON."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO archive_dois (doi, arxiv_id, path, url) VALUES (?, ?, ?, ?)",
                (doi, arxiv_id, path, url),
            )
            await db.commit()
    except Exception:
        return
    try:
        import asyncio as _asyncio
        from services.list_sync import write_json as _write_json
        _asyncio.create_task(_write_json("papers"))
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
    """Retorna sugestões de autocomplete combinando histórico e corpus indexado.

    Prioridade:
      1. search_history         — queries já feitas, ordenadas por frequência (akasha.db)
      2. topic_interest_profile — tópicos aprendidos, por score (akasha_knowledge.db)
      3. page_knowledge topics  — tópicos por página, json_each (akasha_knowledge.db)
      4. crawl_pages titles     — títulos de páginas (akasha.db)

    Deduplica (case-insensitive) e limita a `limit` itens totais.
    """
    if not prefix.strip():
        return []
    p_lower   = prefix.strip().lower()
    pattern   = f"{prefix.strip()}%"
    pat_lower = f"{p_lower}%"

    seen: set[str] = set()
    results: list[str] = []

    # 1 e 4: banco principal (search_history + crawl_pages)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT query FROM search_history "
            "WHERE query LIKE ? "
            "ORDER BY count DESC, last_used DESC "
            "LIMIT ?",
            (pattern, limit),
        )).fetchall()
        for (q,) in rows:
            seen.add(q.lower())
            results.append(q)

        crawl_titles: list[str] = []
        if len(results) < limit:
            cap = limit - len(results)
            rows4 = await (await db.execute(
                "SELECT DISTINCT title FROM crawl_pages "
                "WHERE title IS NOT NULL AND LOWER(title) LIKE ? LIMIT ?",
                (pat_lower, cap * 2),
            )).fetchall()
            crawl_titles = [r[0] for r in rows4 if r[0]]

    # 2: topic_interest_profile — shared store
    if len(results) < limit:
        try:
            import shared_topic_profile as _stp
            cap = (limit - len(results)) * 2
            for t in _stp.search_topics(pat_lower.rstrip("%"), cap):
                if len(results) >= limit:
                    break
                if t.lower() not in seen:
                    seen.add(t.lower())
                    results.append(t)
        except Exception:
            pass

    # 3: page_knowledge topics
    try:
        async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as kdb:
            if len(results) < limit:
                cap = (limit - len(results)) * 2
                try:
                    rows3 = await (await kdb.execute(
                        "SELECT DISTINCT value FROM page_knowledge, "
                        "json_each(page_knowledge.topics) "
                        "WHERE LOWER(value) LIKE ? LIMIT ?",
                        (pat_lower, cap),
                    )).fetchall()
                    for (t,) in rows3:
                        if len(results) >= limit:
                            break
                        if t and t.lower() not in seen:
                            seen.add(t.lower())
                            results.append(t)
                except Exception:
                    pass  # json_each indisponível nesta versão do SQLite
    except Exception:
        pass

    # 4 (diferido): adiciona títulos de crawl_pages se ainda há espaço
    for t in crawl_titles:
        if len(results) >= limit:
            break
        if t.lower() not in seen:
            seen.add(t.lower())
            results.append(t)

    return results[:limit]


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
    topics: list[str],
    entities: list[str],
    source_type: str,
) -> None:
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO page_knowledge
               (url, title, topics, entities, source_type, processed_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (url, title, json.dumps(topics), json.dumps(entities), source_type),
        )
        await db.commit()


async def get_page_knowledge(url: str) -> dict | None:
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        row = await (await db.execute(
            "SELECT url, title, topics, entities, source_type, processed_at "
            "FROM page_knowledge WHERE url = ?",
            (url,),
        )).fetchone()
    if not row:
        return None
    return {
        "url": row[0], "title": row[1],
        "topics": json.loads(row[2] or "[]"),
        "entities": json.loads(row[3] or "[]"),
        "source_type": row[4], "processed_at": row[5],
    }


async def get_page_knowledge_batch(urls: list[str]) -> dict[str, dict]:
    """Retorna {url: {"topics": list}} para os URLs fornecidos."""
    if not urls:
        return {}
    placeholders = ",".join("?" * len(urls))
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        rows = await (await db.execute(
            f"SELECT url, topics FROM page_knowledge WHERE url IN ({placeholders})",
            urls,
        )).fetchall()
    return {
        r[0]: {"topics": json.loads(r[1] or "[]")}
        for r in rows
    }


async def update_topic_score(topic: str, delta: float = 1.0) -> None:
    """Incrementa score de um tópico no perfil de interesse compartilhado."""
    import shared_topic_profile as _stp
    _stp.update_score(topic, delta, "akasha")


async def get_topic_score(topic: str) -> float | None:
    """Retorna o score atual de um tópico, ou None se não existir."""
    import shared_topic_profile as _stp
    scores = _stp.get_scores([topic])
    val = scores.get(topic.strip().lower())
    return val if val and val > 0.0 else None


async def get_topic_scores_for_list(topics: list[str]) -> dict[str, float]:
    """Retorna score de cada tópico informado (apenas os com score > 0)."""
    if not topics:
        return {}
    import shared_topic_profile as _stp
    return {k: v for k, v in _stp.get_scores(topics).items() if v > 0.0}


async def get_top_topics(n: int = 10) -> list[tuple[str, float]]:
    """Retorna os N tópicos com maior score, em ordem decrescente."""
    import shared_topic_profile as _stp
    return _stp.get_top_topics(n)


async def get_recent_page_knowledge(n: int = 10) -> list[dict]:
    """Retorna os N registros de page_knowledge mais recentes."""
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT url, title, topics FROM page_knowledge "
            "ORDER BY processed_at DESC LIMIT ?",
            (n,),
        )).fetchall()
    return [
        {
            "url": r[0], "title": r[1],
            "topics": json.loads(r[2] or "[]"),
        }
        for r in rows
    ]


async def get_all_page_knowledge() -> list[dict]:
    """Retorna todos os registros de page_knowledge para re-análise em lote."""
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT url, title, topics FROM page_knowledge ORDER BY processed_at ASC"
        )).fetchall()
    return [
        {
            "url": r[0], "title": r[1],
            "topics": json.loads(r[2] or "[]"),
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


# ---------------------------------------------------------------------------
# Context / status helpers (usados por routers/context.py)
# ---------------------------------------------------------------------------

async def url_is_archived(url: str) -> bool:
    """Retorna True se a URL consta em archive_simhashes (página baixada para ARCHIVE_PATH/Web/)."""
    from urllib.parse import urlparse, urlunparse
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT 1 FROM archive_simhashes WHERE url = ? LIMIT 1",
            (url,),
        )).fetchone()
        if row:
            return True
        # Fallback: compara sem query string (URLs com tracking params)
        parsed = urlparse(url)
        url_no_query = urlunparse(parsed._replace(query="", fragment=""))
        if url_no_query != url:
            row = await (await db.execute(
                "SELECT 1 FROM archive_simhashes WHERE url LIKE ? LIMIT 1",
                (url_no_query + "%",),
            )).fetchone()
            return row is not None
    return False


async def domain_in_crawl_sites(domain: str) -> bool:
    """Retorna True se algum site rastreado pertence ao domínio especificado."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT 1 FROM crawl_sites WHERE deleted=0 "
            "AND (base_url LIKE ? OR base_url LIKE ?) LIMIT 1",
            (f"http://{domain}%", f"https://{domain}%"),
        )).fetchone()
    return row is not None


async def count_related_pages(current_url: str, topics: list[str]) -> int:
    """Conta páginas em page_knowledge com pelo menos um tópico em comum (heurística LIKE)."""
    if not topics:
        return 0
    topic = next((t for t in topics if len(t) > 3), topics[0])
    keyword = topic.lower().replace("'", "").replace('"', "")
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        row = await (await db.execute(
            "SELECT COUNT(*) FROM page_knowledge WHERE url != ? AND lower(topics) LIKE ?",
            (current_url, f"%{keyword}%"),
        )).fetchone()
    return row[0] if row else 0


async def get_related_indexed_pages(
    current_url: str,
    topics: list[str],
    exclude_urls: list[str] | None = None,
    n: int = 3,
) -> list[dict]:
    """Retorna até N páginas do índice com maior sobreposição de tópicos.

    Ordena candidatos por número de tópicos em comum (decrescente).
    Exclui current_url e qualquer URL em exclude_urls.
    Retorna lista de dicts {url, title, overlap}.
    """
    if not topics:
        return []
    excluded = set([current_url] + (exclude_urls or []))
    topics_lower = [t.lower() for t in topics if t]
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT url, title, topics FROM page_knowledge"
        )).fetchall()
    candidates: list[dict] = []
    for url, title, topics_json in rows:
        if url in excluded:
            continue
        doc_topics = {t.lower() for t in json.loads(topics_json or "[]")}
        overlap = sum(1 for t in topics_lower if t in doc_topics)
        if overlap > 0:
            candidates.append({"url": url, "title": title or url, "overlap": overlap})
    candidates.sort(key=lambda x: -x["overlap"])
    return candidates[:n]


async def decay_old_topic_scores(days_inactive: int = 7, factor: float = 0.97) -> int:
    """Aplica decaimento EMA em tópicos sem atualização há mais de `days_inactive` dias.

    Remove tópicos com score abaixo de 0.01 para evitar acúmulo de ruído.
    Retorna o número de tópicos afetados.
    """
    import shared_topic_profile as _stp
    return _stp.decay_scores(factor, days_inactive)


async def upsert_entity_pair(entity: str, co_entity: str, delta: float = 1.0) -> None:
    """Incrementa peso do par (entity, co_entity) no entity_graph.

    Garante ordem canônica (alfabética) para evitar pares duplicados invertidos.
    """
    a, b = sorted([entity.strip().lower(), co_entity.strip().lower()])
    if a == b:
        return
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
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
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        rows = await (await db.execute(
            """SELECT co_entity, weight FROM entity_graph WHERE entity = ?
               UNION ALL
               SELECT entity, weight FROM entity_graph WHERE co_entity = ?
               ORDER BY weight DESC LIMIT ?""",
            (e, e, n),
        )).fetchall()
    return [(r[0], r[1]) for r in rows]


async def get_graph_data(node_limit: int = 80, edge_limit: int = 250) -> dict:
    """Retorna nós e arestas do entity_graph para visualização.

    Nós: top-N entidades por peso total acumulado (soma das arestas).
    Arestas: top-M pares por peso, filtradas para conter apenas nós do conjunto acima.
    """
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        # Nós: peso total = soma de todos os pesos das arestas incidentes
        node_rows = await (await db.execute(
            """SELECT entity, SUM(weight) AS total
               FROM (
                 SELECT entity, weight FROM entity_graph
                 UNION ALL
                 SELECT co_entity AS entity, weight FROM entity_graph
               )
               GROUP BY entity
               ORDER BY total DESC
               LIMIT ?""",
            (node_limit,),
        )).fetchall()

        node_ids = {r[0] for r in node_rows}

        # Scores de interesse para dimensionar nós
        import shared_topic_profile as _stp
        interest: dict[str, float] = _stp.get_all_scores()

        nodes = [
            {
                "id":       r[0],
                "weight":   r[1],
                "interest": interest.get(r[0], 0.0),
            }
            for r in node_rows
        ]

        # Arestas: apenas entre nós no conjunto acima
        edge_rows = await (await db.execute(
            """SELECT entity, co_entity, weight, feedback
               FROM entity_graph
               ORDER BY weight DESC
               LIMIT ?""",
            (edge_limit * 3,),  # busca extra; filtra abaixo
        )).fetchall()

        edges = [
            {
                "source":   r[0],
                "target":   r[1],
                "weight":   r[2],
                "feedback": r[3],
            }
            for r in edge_rows
            if r[0] in node_ids and r[1] in node_ids
        ][:edge_limit]

    return {"nodes": nodes, "edges": edges}


async def get_pages_for_topic(topic: str, limit: int = 12) -> list[dict]:
    """Retorna páginas de crawl_pages cujo page_knowledge menciona o tópico/entidade."""
    t = topic.strip().lower()
    # Passo 1: URLs que têm o tópico/entidade no knowledge DB
    try:
        async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
            url_rows = await (await db.execute(
                """SELECT DISTINCT url FROM page_knowledge
                   WHERE EXISTS (
                       SELECT 1 FROM json_each(topics)   WHERE LOWER(value) = ?
                   ) OR EXISTS (
                       SELECT 1 FROM json_each(entities) WHERE LOWER(value) = ?
                   )
                   LIMIT ?""",
                (t, t, limit),
            )).fetchall()
    except Exception:
        return []

    urls = [r[0] for r in url_rows]
    if not urls:
        return []

    # Passo 2: títulos do banco principal
    placeholders = ",".join("?" * len(urls))
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            title_rows = await (await db.execute(
                f"SELECT url, title FROM crawl_pages WHERE url IN ({placeholders})",
                urls,
            )).fetchall()
    except Exception:
        title_rows = []

    title_map = {r[0]: r[1] for r in title_rows}
    return [{"url": u, "title": title_map.get(u) or u} for u in urls]


async def set_edge_feedback(a: str, b: str, feedback: str | None) -> None:
    """Define feedback (confirmed/dismissed/None) para uma aresta do grafo."""
    na, nb = sorted([a.strip().lower(), b.strip().lower()])
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        await db.execute(
            "UPDATE entity_graph SET feedback = ? WHERE entity = ? AND co_entity = ?",
            (feedback, na, nb),
        )
        await db.commit()


async def count_page_knowledge() -> int:
    """Número total de registros em page_knowledge."""
    async with aiosqlite.connect(KNOWLEDGE_DB_PATH) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM page_knowledge")).fetchone()
    return row[0] if row else 0


async def get_crawl_page_processed(url: str) -> bool:
    """Retorna True se crawl_pages.knowledge_processed = 1 para esta URL."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            row = await (await db.execute(
                "SELECT knowledge_processed FROM crawl_pages WHERE url = ?", (url,)
            )).fetchone()
        return bool(row and row[0])
    except Exception:
        return False


async def set_crawl_page_processed(url: str) -> None:
    """Marca crawl_pages.knowledge_processed = 1 para esta URL."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE crawl_pages SET knowledge_processed = 1 WHERE url = ?", (url,)
            )
            await db.commit()
    except Exception:
        pass
