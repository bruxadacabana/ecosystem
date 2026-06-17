"""
Schema SQLite do KOSMOS v3.

O banco fica em sync_root/kosmos/ (sincronizado via Syncthing). O caminho
concreto é resolvido em runtime pelo paths.py via ecosystem_client.

Tabelas:
  feeds               — canais RSS/Atom configurados pela usuária
  articles            — artigos recebidos, com campos de análise AI e dados de leitura
  entities            — entidades rastreadas pela usuária (pessoas, orgs, lugares, temas)
  article_entities    — relação artigo ↔ entidade (resultado da análise AI)
  highlights          — trechos marcados pela usuária durante a leitura
  investigations      — pastas de investigação/estudo
  investigation_articles — relação investigação ↔ artigo curado
  fts_articles        — índice FTS5 (título + texto + tags AI)

Triggers FTS5 mantêm o índice sincronizado com a tabela articles
automaticamente em INSERT, UPDATE e DELETE.

Heartbeat timeout: ao inicializar, artigos com analysis_status='running'
por mais de 5 minutos são resetados para 'pending' — evita artigos
eternamente travados após crash ou kill do processo.
"""
from __future__ import annotations

import logging
import sqlite3

from app.utils.paths import DB_PATH

log = logging.getLogger("kosmos.database")

# Versão do schema de análise AI. Incrementar ao mudar prompts ou estrutura
# de campos AI para que artigos com versão antiga sejam re-analisados.
ANALYSIS_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# DDL — schema completo
# ---------------------------------------------------------------------------
_DDL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Canais RSS/Atom configurados pela usuária
CREATE TABLE IF NOT EXISTS feeds (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    url                 TEXT    NOT NULL UNIQUE,
    title               TEXT,
    site_url            TEXT,
    category            TEXT    NOT NULL DEFAULT 'Sem categoria',
    last_fetched_at     TEXT,                           -- ISO8601
    fetch_interval_min  INTEGER NOT NULL DEFAULT 60,
    enabled             INTEGER NOT NULL DEFAULT 1,
    error_count         INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Artigos recebidos dos feeds
CREATE TABLE IF NOT EXISTS articles (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id                 INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    url                     TEXT    NOT NULL UNIQUE,
    title                   TEXT    NOT NULL,
    title_translated        TEXT,                       -- tradução automática para idioma configurado
    content_excerpt         TEXT,                       -- trecho fornecido pelo feed (description)
    content_text            TEXT,                       -- texto completo extraído via scraping
    content_text_translated TEXT,                       -- tradução do corpo (sob demanda, Fase 6)
    published_at            TEXT,                       -- ISO8601
    author                  TEXT,
    estimated_reading_min   INTEGER,                    -- tempo estimado (palavras / 200 wpm)
    article_type            TEXT,                       -- "news"|"opinion"|"analysis"|"press_release"|"scientific"
    language_detected       TEXT,                       -- código ISO do idioma detectado
    -- Status de processamento
    is_scraped              INTEGER NOT NULL DEFAULT 0,
    is_read                 INTEGER NOT NULL DEFAULT 0,
    is_saved                INTEGER NOT NULL DEFAULT 0, -- arquivado como .md no ecossistema
    read_at                 TEXT,                       -- ISO8601
    read_duration_sec       INTEGER,                    -- segundos gastos lendo
    notes                   TEXT,                       -- anotações pessoais da usuária
    -- Campos de análise AI (preenchidos progressivamente pelo AnalysisWorker)
    ai_tags                 TEXT,                       -- JSON array: ["ia", "python", "llm"]
    ai_sentiment            TEXT,                       -- "positivo"|"neutro"|"negativo"
    ai_clickbait_score      REAL,                       -- 0.0–1.0
    ai_summary              TEXT,                       -- 1-2 frases geradas pelo LLM
    ai_language             TEXT,                       -- idioma confirmado pela análise
    ai_five_ws              TEXT,                       -- JSON: {quem, o_que, quando, onde, por_que}
    ai_entities             TEXT,                       -- JSON array: [{nome, tipo}]
    ai_bias                 TEXT,                       -- JSON: {espectro, marcadores, qualidade_apuracao}
    -- Controle da fila de análise
    analysis_status         TEXT    NOT NULL DEFAULT 'pending', -- pending|running|done|failed
    analysis_started_at     TEXT,                       -- ISO8601; heartbeat: resetar se > 5min em running
    analysis_schema_version INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Índice parcial: cobre apenas artigos pendentes/falhos — muito menor que o total
CREATE INDEX IF NOT EXISTS idx_articles_pending_analysis
    ON articles(published_at DESC)
    WHERE analysis_status IN ('pending', 'failed');

-- Entidades rastreadas pela usuária (pessoas, organizações, lugares, temas)
CREATE TABLE IF NOT EXISTS entities (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    entity_type  TEXT    NOT NULL DEFAULT 'topic', -- "person"|"org"|"place"|"topic"
    notes        TEXT,
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(name, entity_type)
);

-- Relação artigo ↔ entidade (extraída pela análise AI)
CREATE TABLE IF NOT EXISTS article_entities (
    article_id  INTEGER NOT NULL REFERENCES articles(id)  ON DELETE CASCADE,
    entity_id   INTEGER NOT NULL REFERENCES entities(id)  ON DELETE CASCADE,
    confidence  REAL    NOT NULL DEFAULT 1.0,             -- 0.0–1.0
    PRIMARY KEY (article_id, entity_id)
);

-- Alertas: palavras-chave e entidades rastreadas que destacam cards (Fase 7)
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,   -- 'keyword' | 'entity'
    term        TEXT    NOT NULL,   -- keyword (texto) | entity_id (como texto) para kind='entity'
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (kind, term)
);

-- Trechos marcados pela usuária durante a leitura
CREATE TABLE IF NOT EXISTS highlights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    text            TEXT    NOT NULL,
    note            TEXT,
    highlight_type  TEXT    NOT NULL DEFAULT 'generic', -- "citation"|"question"|"fact"|"contradiction"|"generic"
    position_hint   TEXT,                               -- identificador de posição no texto
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Pastas de investigação/estudo
CREATE TABLE IF NOT EXISTS investigations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Relação investigação ↔ artigo curado
CREATE TABLE IF NOT EXISTS investigation_articles (
    investigation_id  INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    article_id        INTEGER NOT NULL REFERENCES articles(id)       ON DELETE CASCADE,
    added_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    notes             TEXT,
    PRIMARY KEY (investigation_id, article_id)
);

-- Índice FTS5: busca por título, texto completo e tags AI
CREATE VIRTUAL TABLE IF NOT EXISTS fts_articles USING fts5(
    title,
    content_text,
    ai_tags,
    content=articles,
    content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS fts_articles_insert
    AFTER INSERT ON articles BEGIN
        INSERT INTO fts_articles(rowid, title, content_text, ai_tags)
        VALUES (new.id,
                new.title,
                COALESCE(new.content_text, new.content_excerpt, ''),
                COALESCE(new.ai_tags, ''));
    END;

CREATE TRIGGER IF NOT EXISTS fts_articles_update
    AFTER UPDATE ON articles BEGIN
        INSERT INTO fts_articles(fts_articles, rowid, title, content_text, ai_tags)
        VALUES ('delete', old.id,
                old.title,
                COALESCE(old.content_text, old.content_excerpt, ''),
                COALESCE(old.ai_tags, ''));
        INSERT INTO fts_articles(rowid, title, content_text, ai_tags)
        VALUES (new.id,
                new.title,
                COALESCE(new.content_text, new.content_excerpt, ''),
                COALESCE(new.ai_tags, ''));
    END;

CREATE TRIGGER IF NOT EXISTS fts_articles_delete
    AFTER DELETE ON articles BEGIN
        INSERT INTO fts_articles(fts_articles, rowid, title, content_text, ai_tags)
        VALUES ('delete', old.id,
                old.title,
                COALESCE(old.content_text, old.content_excerpt, ''),
                COALESCE(old.ai_tags, ''));
    END;
"""


def init_db() -> None:
    """Cria tabelas, índices, triggers e FTS5 se não existirem. Idempotente.

    Também executa o heartbeat reset: artigos travados em 'running' por mais
    de 5 minutos são devolvidos para 'pending' para que a fila de análise os
    reprocesse na próxima execução.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _archive_foreign_db_if_any()
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            # Migração ANTES do schema: bancos antigos precisam ganhar as colunas novas
            # (ai_*, analysis_*, etc.) antes que os índices/triggers que as referenciam
            # sejam criados pelo executescript — senão a inicialização aborta.
            _ensure_columns(conn)
            conn.executescript(_DDL)
            _reset_stale_analyses(conn)
            log.info("Banco inicializado em %s.", DB_PATH)
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        log.critical("Falha ao inicializar banco: %s", exc)
        raise


# Colunas adicionadas a `feeds`/`articles` ao longo das fases. Bancos criados em
# fases anteriores não as têm — `CREATE TABLE IF NOT EXISTS` não altera tabela
# existente, então cada coluna ausente é adicionada via ALTER (migração).
_MIGRATION_COLUMNS = {
    "feeds": [
        ("site_url", "TEXT"),
        ("category", "TEXT NOT NULL DEFAULT 'Sem categoria'"),
        ("last_fetched_at", "TEXT"),
        ("fetch_interval_min", "INTEGER NOT NULL DEFAULT 60"),
        ("enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("error_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_error", "TEXT"),
    ],
    "articles": [
        ("title_translated", "TEXT"),
        ("content_text", "TEXT"),
        ("content_text_translated", "TEXT"),
        ("estimated_reading_min", "INTEGER"),
        ("article_type", "TEXT"),
        ("language_detected", "TEXT"),
        ("is_scraped", "INTEGER NOT NULL DEFAULT 0"),
        ("is_read", "INTEGER NOT NULL DEFAULT 0"),
        ("is_saved", "INTEGER NOT NULL DEFAULT 0"),
        ("read_at", "TEXT"),
        ("read_duration_sec", "INTEGER"),
        ("notes", "TEXT"),
        ("ai_tags", "TEXT"),
        ("ai_sentiment", "TEXT"),
        ("ai_clickbait_score", "REAL"),
        ("ai_summary", "TEXT"),
        ("ai_language", "TEXT"),
        ("ai_five_ws", "TEXT"),
        ("ai_entities", "TEXT"),
        ("ai_bias", "TEXT"),
        ("analysis_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("analysis_started_at", "TEXT"),
        ("analysis_schema_version", "INTEGER NOT NULL DEFAULT 0"),
    ],
}


def _archive_foreign_db_if_any() -> None:
    """Arquiva um banco de schema estrangeiro/pré-v3 e deixa o caminho livre para um v3 novo.

    O KOSMOS v3 foi replanejado do zero (2026-06-01); bancos anteriores têm um schema
    incompatível (colunas como `guid`/`content_full`, sem `content_excerpt`) que não
    dá para migrar coluna-a-coluna. A coluna base `content_excerpt` existe em todo
    banco v3 (desde a Fase 1) — se a tabela `articles` existe SEM ela, é um banco
    pré-v3: renomeia para `.pre-v3.bak` (não apaga) e o init cria um v3 limpo.
    Um banco v3 legítimo (qualquer fase) tem `content_excerpt` e segue para a migração.
    """
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.warning("Não foi possível inspecionar o banco existente: %s", exc)
        return
    if cols and "content_excerpt" not in cols:
        backup = DB_PATH.with_name(DB_PATH.name + ".pre-v3.bak")
        DB_PATH.rename(backup)
        for suffix in ("-wal", "-shm"):
            side = DB_PATH.with_name(DB_PATH.name + suffix)
            if side.exists():
                side.rename(backup.with_name(backup.name + suffix))
        log.warning("Banco pré-v3 incompatível detectado — arquivado em %s; criando banco v3 novo.", backup)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Migra bancos pré-existentes: adiciona as colunas novas que faltarem.

    Roda ANTES do `executescript` para que os índices/triggers que referenciam as
    colunas novas (ex.: `analysis_status`) já as encontrem. Introspecciona cada
    tabela: se ela ainda não existe (banco novo), pula — o `executescript` a criará
    completa. Cada ALTER faltante é aplicado e logado; falhas são logadas (sem
    caminho silencioso).
    """
    for table, columns in _MIGRATION_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if not existing:
            continue  # tabela inexistente (banco novo) — executescript cria completa
        for column, coltype in columns:
            if column in existing:
                continue
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
                log.info("Migração: coluna %s.%s adicionada.", table, column)
            except sqlite3.OperationalError as exc:
                log.warning("Migração: ALTER %s.%s falhou: %s", table, column, exc)
    conn.commit()


def _reset_stale_analyses(conn: sqlite3.Connection) -> None:
    """Reseta artigos travados em 'running' por mais de 5 minutos para 'pending'.

    Evita que artigos fiquem presos indefinidamente após crash ou kill do
    processo enquanto uma análise estava em andamento.
    """
    cursor = conn.execute(
        """
        UPDATE articles
           SET analysis_status      = 'pending',
               analysis_started_at  = NULL
         WHERE analysis_status     = 'running'
           AND analysis_started_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-5 minutes')
        """,
    )
    conn.commit()
    if cursor.rowcount:
        log.warning(
            "Heartbeat reset: %d artigo(s) travado(s) em 'running' devolvidos para 'pending'.",
            cursor.rowcount,
        )


def get_conn() -> sqlite3.Connection:
    """Retorna conexão configurada com foreign_keys, WAL e row_factory.

    O caller é responsável por fechar a conexão (use como context manager
    ou chame conn.close() explicitamente).
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
    except sqlite3.OperationalError as exc:
        log.error("Falha ao conectar ao banco: %s", exc)
        raise
