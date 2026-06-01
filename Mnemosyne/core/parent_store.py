"""
ParentStore — armazena o texto dos parent chunks para o Parent-Child Retrieval.

Arquitetura:
  - Indexação: cada arquivo é dividido em parent chunks (grandes, ~1024 chars)
    e child chunks (pequenos, ~256 chars). Os child chunks são armazenados no
    ChromaDB para retrieval preciso; os parent chunks ficam aqui.
  - Recuperação: ao obter um child chunk do ChromaDB, o campo metadata["parent_id"]
    aponta para o parent chunk correspondente. O RAG usa o texto do parent como
    contexto para o LLM, garantindo mais contexto sem sacrificar a precisão do retrieval.
  - Fallback: se parent_id ausente ou ParentStore offline, usa o texto do child.

Schema SQLite: parent_chunks(chunk_id TEXT PK, source TEXT, text TEXT)
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger("mnemosyne.parent_store")

_DB_FILENAME = "parent_chunks.db"


class ParentStore:
    """SQLite store para parent chunks do Parent-Child Retrieval.

    Uso típico:
        store = ParentStore(config.persist_dir)
        store.delete_by_source(file_path)          # limpa antes de re-indexar
        for parent_id, source, text in records:
            store.save(parent_id, source, text)
        store.close()

    Na recuperação (rag.py):
        store = ParentStore(config.persist_dir)
        parent_text = store.get(parent_id)          # None se não encontrado
        store.close()
    """

    def __init__(self, persist_dir: str) -> None:
        db_path = Path(persist_dir) / _DB_FILENAME
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS parent_chunks (
                chunk_id TEXT PRIMARY KEY,
                source   TEXT NOT NULL,
                text     TEXT NOT NULL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_parent_source ON parent_chunks(source)"
        )
        self._conn.commit()

    def save(self, chunk_id: str, source: str, text: str) -> None:
        """Insere ou substitui um parent chunk."""
        self._conn.execute(
            "INSERT OR REPLACE INTO parent_chunks (chunk_id, source, text) VALUES (?, ?, ?)",
            (chunk_id, source, text),
        )
        self._conn.commit()

    def save_batch(self, records: list[tuple[str, str, str]]) -> None:
        """Insere múltiplos parent chunks de uma vez: [(chunk_id, source, text)]."""
        self._conn.executemany(
            "INSERT OR REPLACE INTO parent_chunks (chunk_id, source, text) VALUES (?, ?, ?)",
            records,
        )
        self._conn.commit()
        log.debug("parent_store: %d parent chunks salvos", len(records))

    def get(self, chunk_id: str) -> str | None:
        """Recupera o texto de um parent chunk pelo ID. Retorna None se não encontrado."""
        row = self._conn.execute(
            "SELECT text FROM parent_chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        return row[0] if row else None

    def delete_by_source(self, source: str) -> None:
        """Remove todos os parent chunks de um arquivo — chamado antes de re-indexar."""
        self._conn.execute("DELETE FROM parent_chunks WHERE source = ?", (source,))
        self._conn.commit()

    def count(self) -> int:
        """Retorna o número total de parent chunks armazenados."""
        row = self._conn.execute("SELECT COUNT(*) FROM parent_chunks").fetchone()
        return row[0] if row else 0

    def count_for_source(self, source: str) -> int:
        """Retorna o número de parent chunks para um arquivo específico."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM parent_chunks WHERE source = ?", (source,)
        ).fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """Fecha a conexão com o banco."""
        try:
            self._conn.close()
        except Exception:
            pass
