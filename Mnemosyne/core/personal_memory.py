"""
Mnemosyne — Store de memória pessoal.

Memória interna da Mnemosyne: observações, conexões, surpresas e reflexões
geradas a partir do conhecimento processado. Separada do Chroma/BM25 e nunca
indexada no RAG de coleções.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import get_app_data_dir

_DB_PATH: Path | None = None


def _get_db() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = get_app_data_dir() / "personal_memory.db"
    return _DB_PATH


def _conn() -> sqlite3.Connection:
    db = _get_db()
    con = sqlite3.connect(db)
    con.execute("""
        CREATE TABLE IF NOT EXISTS personal_memory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            type       TEXT    NOT NULL,
            content    TEXT    NOT NULL,
            tags       TEXT    NOT NULL DEFAULT '[]'
        )
    """)
    con.commit()
    return con


_VALID_TYPES = {"observation", "connection", "surprise", "reflection"}


def save_memory(
    type: str,
    content: str,
    tags: list[str] | None = None,
) -> None:
    """Salva entrada de memória pessoal."""
    if type not in _VALID_TYPES:
        type = "observation"
    if tags is None:
        tags = []
    with _conn() as con:
        con.execute(
            "INSERT INTO personal_memory (type, content, tags) VALUES (?, ?, ?)",
            (type, content, json.dumps(tags, ensure_ascii=False)),
        )


def get_recent(n: int = 10) -> list[dict]:
    """Retorna as N entradas mais recentes."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags "
            "FROM personal_memory ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "created_at": r[1],
            "type": r[2],
            "content": r[3],
            "tags": json.loads(r[4] or "[]"),
        }
        for r in rows
    ]


def get_all() -> list[dict]:
    """Retorna todas as entradas em ordem decrescente."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags "
            "FROM personal_memory ORDER BY id DESC",
        ).fetchall()
    return [
        {
            "id": r[0],
            "created_at": r[1],
            "type": r[2],
            "content": r[3],
            "tags": json.loads(r[4] or "[]"),
        }
        for r in rows
    ]


def clear_all() -> None:
    """Apaga toda a memória pessoal — irreversível."""
    with _conn() as con:
        con.execute("DELETE FROM personal_memory")
