from __future__ import annotations

import logging
import sqlite3

from app.utils.paths import DB_PATH

log = logging.getLogger("kosmos.database")

# ---------------------------------------------------------------------------
# DDL — schema completo incluindo campos de IA (relevância, sentimento, etc.)
# para não precisar de migration na Fase 4
# ---------------------------------------------------------------------------
_DDL = """
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    position   INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feeds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id   INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    name          TEXT    NOT NULL,
    url           TEXT    NOT NULL,
    feed_type     TEXT    NOT NULL DEFAULT 'rss',
    favicon_path  TEXT,
    etag          TEXT,
    last_modified TEXT,
    last_fetched  DATETIME,
    last_error    TEXT,
    position      INTEGER DEFAULT 0,
    active        INTEGER DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id          INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    guid             TEXT    NOT NULL,
    title            TEXT    NOT NULL,
    title_translated TEXT,
    url              TEXT,
    author           TEXT,
    published_at     DATETIME,
    fetched_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    summary          TEXT,
    content_full     TEXT,
    content_type     TEXT    DEFAULT 'html',
    scrape_status    TEXT    DEFAULT 'none',
    integrity        TEXT    DEFAULT 'unknown',
    relevance_score  REAL,
    sentiment        TEXT,
    is_clickbait     INTEGER DEFAULT 0,
    is_read          INTEGER DEFAULT 0,
    is_saved         INTEGER DEFAULT 0,
    read_at          DATETIME,
    saved_at         DATETIME,
    extra_json       TEXT,
    UNIQUE(feed_id, guid)
);

CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#8B7355'
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    tag_id     INTEGER REFERENCES tags(id)     ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);

CREATE TABLE IF NOT EXISTS read_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id   INTEGER REFERENCES articles(id) ON DELETE SET NULL,
    feed_id      INTEGER REFERENCES feeds(id)    ON DELETE SET NULL,
    started_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    duration_sec INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_articles USING fts5(
    title,
    content,
    content='articles',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS fts_articles_insert
    AFTER INSERT ON articles BEGIN
        INSERT INTO fts_articles(rowid, title, content)
        VALUES (new.id, new.title, COALESCE(new.content_full, new.summary, ''));
    END;

CREATE TRIGGER IF NOT EXISTS fts_articles_update
    AFTER UPDATE ON articles BEGIN
        UPDATE fts_articles
           SET title   = new.title,
               content = COALESCE(new.content_full, new.summary, '')
         WHERE rowid = new.id;
    END;

CREATE TRIGGER IF NOT EXISTS fts_articles_delete
    AFTER DELETE ON articles BEGIN
        DELETE FROM fts_articles WHERE rowid = old.id;
    END;
"""


def init_db() -> None:
    """Cria tabelas, triggers e FTS5 se não existirem. Idempotente."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_DDL)
            log.info("Banco inicializado em %s.", DB_PATH)
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        log.critical("Falha ao inicializar banco: %s", exc)
        raise


def get_conn() -> sqlite3.Connection:
    """Retorna conexão configurada com foreign_keys e WAL. Caller é responsável por fechar."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
    except sqlite3.OperationalError as exc:
        log.error("Falha ao conectar ao banco: %s", exc)
        raise
