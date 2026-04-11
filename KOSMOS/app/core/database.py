"""Inicialização do banco de dados SQLite via SQLAlchemy 2.0."""

from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.base import Base
from app.utils.paths import Paths

log = logging.getLogger("kosmos.database")

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


class DatabaseError(Exception):
    """Erro genérico de banco de dados."""


def init_database() -> None:
    """Cria o engine, aplica PRAGMAs, registra modelos e cria as tabelas.

    Deve ser chamado uma única vez na inicialização da aplicação.

    Raises:
        DatabaseError: se a criação do banco falhar.
    """
    global _engine, _SessionLocal

    db_path = Paths.DB

    try:
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
    except Exception as exc:
        raise DatabaseError(f"Não foi possível criar o engine SQLite: {exc}") from exc

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.close()

    # Importar modelos para registrá-los no metadata do Base
    from app.core import models  # noqa: F401

    try:
        Base.metadata.create_all(engine)
        _setup_fts(engine)
        _migrate(engine)
    except SQLAlchemyError as exc:
        raise DatabaseError(f"Erro ao criar tabelas: {exc}") from exc

    _engine = engine
    _SessionLocal = sessionmaker(bind=engine)
    log.info("Banco de dados pronto: %s", db_path)


def get_session() -> Session:
    """Retorna uma nova sessão SQLAlchemy.

    Raises:
        DatabaseError: se o banco não foi inicializado.
    """
    if _SessionLocal is None:
        raise DatabaseError(
            "Banco não inicializado. Chame init_database() antes."
        )
    return _SessionLocal()


def session_scope() -> Generator[Session, None, None]:
    """Context manager que faz commit automático ou rollback em caso de erro.

    Uso::

        with session_scope() as session:
            session.add(obj)
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _migrate(engine: Engine) -> None:
    """Aplica migrações incrementais. Cada ALTER TABLE é idempotente."""
    migrations = [
        "ALTER TABLE articles ADD COLUMN scroll_pos INTEGER DEFAULT 0",
        "ALTER TABLE articles ADD COLUMN duplicate_of INTEGER REFERENCES articles(id) ON DELETE SET NULL",
        "ALTER TABLE articles ADD COLUMN language TEXT",
        # FASE F — IA local
        "ALTER TABLE articles ADD COLUMN ai_summary TEXT",
        "ALTER TABLE articles ADD COLUMN ai_tags TEXT",
        "ALTER TABLE articles ADD COLUMN embedding BLOB",
        "ALTER TABLE articles ADD COLUMN ai_relevance REAL",
        "ALTER TABLE articles ADD COLUMN ai_5ws TEXT",
        "ALTER TABLE articles ADD COLUMN ai_sentiment REAL",
        "ALTER TABLE articles ADD COLUMN ai_clickbait REAL",
        "ALTER TABLE articles ADD COLUMN ai_entities TEXT",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # coluna já existe


def _setup_fts(engine: Engine) -> None:
    """Cria a tabela FTS5 e os triggers de sincronização."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_articles
            USING fts5(title, content)
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS articles_ai
            AFTER INSERT ON articles BEGIN
                INSERT INTO fts_articles(rowid, title, content)
                VALUES (new.id, new.title,
                        COALESCE(new.content_full, new.summary, ''));
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS articles_au
            AFTER UPDATE ON articles BEGIN
                UPDATE fts_articles
                SET title   = new.title,
                    content = COALESCE(new.content_full, new.summary, '')
                WHERE rowid = new.id;
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS articles_ad
            AFTER DELETE ON articles BEGIN
                DELETE FROM fts_articles WHERE rowid = old.id;
            END
        """))
        conn.commit()
