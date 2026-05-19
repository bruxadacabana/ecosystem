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

import shutil
import sys

from .config import get_app_data_dir

_DB_PATH: Path | None = None


def _resolve_pm_db() -> Path:
    """Resolve caminho de personal_memory.db.

    Prefere {ai_private_dir}/mnemosyne/personal_memory.db quando sync_root
    configurado. Na primeira execução com novo caminho, copia o arquivo
    antigo para o novo local e renomeia o original para .db.bak.
    """
    try:
        _root = str(Path(__file__).parent.parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from ecosystem_client import get_ai_private_dir  # type: ignore
        d = get_ai_private_dir()
        if d is not None:
            new_dir = d / "mnemosyne"
            new_dir.mkdir(parents=True, exist_ok=True)
            new_path = new_dir / "personal_memory.db"
            old_path = get_app_data_dir() / "personal_memory.db"
            if not new_path.exists() and old_path.exists():
                shutil.copy2(str(old_path), str(new_path))
                try:
                    old_path.rename(old_path.with_suffix(".db.bak"))
                except OSError:
                    pass
            return new_path
    except Exception:
        pass
    return get_app_data_dir() / "personal_memory.db"


def _get_db() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _resolve_pm_db()
    return _DB_PATH


def _conn() -> sqlite3.Connection:
    db = _get_db()
    con = sqlite3.connect(db)
    con.execute("""
        CREATE TABLE IF NOT EXISTS personal_memory (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
            type           TEXT    NOT NULL,
            content        TEXT    NOT NULL,
            tags           TEXT    NOT NULL DEFAULT '[]',
            feedback       TEXT             DEFAULT NULL,
            shown_as_popup INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Migrations para DBs anteriores
    cols = {row[1] for row in con.execute("PRAGMA table_info(personal_memory)").fetchall()}
    if "feedback" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN feedback TEXT DEFAULT NULL")
    if "shown_as_popup" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN shown_as_popup INTEGER NOT NULL DEFAULT 0")
    con.commit()
    return con


_VALID_TYPES = {"observation", "connection", "surprise", "reflection"}


def save_memory(
    type: str,
    content: str,
    tags: list[str] | None = None,
) -> int:
    """Salva entrada de memória pessoal. Retorna o ID inserido."""
    if type not in _VALID_TYPES:
        type = "observation"
    if tags is None:
        tags = []
    with _conn() as con:
        cursor = con.execute(
            "INSERT INTO personal_memory (type, content, tags) VALUES (?, ?, ?)",
            (type, content, json.dumps(tags, ensure_ascii=False)),
        )
        return cursor.lastrowid or 0


def get_recent(n: int = 10) -> list[dict]:
    """Retorna as N entradas mais recentes."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback "
            "FROM personal_memory ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5],
        }
        for r in rows
    ]


def get_all() -> list[dict]:
    """Retorna todas as entradas em ordem decrescente."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback "
            "FROM personal_memory ORDER BY id DESC",
        ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5],
        }
        for r in rows
    ]


def set_feedback(memory_id: int, feedback: str | None) -> None:
    """Registra feedback da usuária para uma entrada de memória."""
    if feedback not in {None, "confirmed", "dismissed"}:
        return
    with _conn() as con:
        con.execute(
            "UPDATE personal_memory SET feedback = ? WHERE id = ?",
            (feedback, memory_id),
        )


def get_context_memories(n: int = 8) -> list[dict]:
    """Memórias para uso como contexto em reflexões.

    Ordem: confirmed primeiro, depois neutral; dismissed excluídos.
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback "
            "FROM personal_memory "
            "WHERE feedback IS NULL OR feedback = 'confirmed' "
            "ORDER BY CASE WHEN feedback = 'confirmed' THEN 0 ELSE 1 END, id DESC "
            "LIMIT ?",
            (n,),
        ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5],
        }
        for r in rows
    ]


def get_unshown_popup_entries(n: int = 5) -> list[dict]:
    """Retorna entradas ainda não exibidas como popup, mais recentes primeiro."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback "
            "FROM personal_memory "
            "WHERE shown_as_popup = 0 "
            "ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5],
        }
        for r in rows
    ]


def mark_shown_as_popup(memory_id: int) -> None:
    """Marca uma entrada como já exibida como popup — persiste entre sessões."""
    with _conn() as con:
        con.execute(
            "UPDATE personal_memory SET shown_as_popup = 1 WHERE id = ?",
            (memory_id,),
        )


def clear_all() -> None:
    """Apaga toda a memória pessoal — irreversível."""
    with _conn() as con:
        con.execute("DELETE FROM personal_memory")
