"""
AKASHA — Store de memória pessoal.

Memória interna da AKASHA: observações, conexões, surpresas e reflexões.
Isolada — nunca exposta por API pública, nunca indexada no vectorstore.
Arquivo separado do DB principal: {ai_private_dir}/akasha/personal_memory.db.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import aiosqlite

_VALID_TYPES = {"observation", "connection", "surprise", "reflection"}

_PM_DDL = """
CREATE TABLE IF NOT EXISTS personal_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    type       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    tags       TEXT    NOT NULL DEFAULT '[]',
    feedback   TEXT             DEFAULT NULL
);
"""


def _get_pm_db() -> Path:
    """Retorna caminho para personal_memory.db, em .ai_private se disponível."""
    try:
        _root = str(Path(__file__).parent.parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from ecosystem_client import get_ai_private_dir
        d = get_ai_private_dir()
        if d is not None:
            target = d / "akasha"
            target.mkdir(parents=True, exist_ok=True)
            return target / "personal_memory.db"
    except Exception:
        pass
    fallback = Path.home() / ".local" / "share" / "akasha"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / "personal_memory.db"


async def init_pm_db() -> None:
    """Inicializa personal_memory.db com o schema. Chamado por database.init_db()."""
    db_path = _get_pm_db()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_PM_DDL)
        await db.commit()


async def save_memory(
    type: str,
    content: str,
    tags: list[str] | None = None,
) -> int:
    """Salva entrada de memória pessoal. Retorna o id da nova entrada."""
    if type not in _VALID_TYPES:
        type = "observation"
    if tags is None:
        tags = []
    async with aiosqlite.connect(_get_pm_db()) as db:
        cur = await db.execute(
            "INSERT INTO personal_memory (type, content, tags) VALUES (?, ?, ?)",
            (type, content, json.dumps(tags, ensure_ascii=False)),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def get_recent(n: int = 10) -> list[dict]:
    """Retorna as N entradas mais recentes."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback "
            "FROM personal_memory ORDER BY id DESC LIMIT ?",
            (n,),
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5],
        }
        for r in rows
    ]


async def get_all() -> list[dict]:
    """Retorna todas as entradas em ordem decrescente."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback "
            "FROM personal_memory ORDER BY id DESC",
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5],
        }
        for r in rows
    ]


async def set_feedback(memory_id: int, feedback: str | None) -> None:
    """Registra feedback da usuária para uma entrada de memória."""
    if feedback not in {None, "confirmed", "dismissed"}:
        return
    async with aiosqlite.connect(_get_pm_db()) as db:
        await db.execute(
            "UPDATE personal_memory SET feedback = ? WHERE id = ?",
            (feedback, memory_id),
        )
        await db.commit()


async def get_by_id(memory_id: int) -> dict | None:
    """Retorna uma entrada pelo id, ou None se não encontrada."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        row = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback "
            "FROM personal_memory WHERE id = ?",
            (memory_id,),
        )).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "created_at": row[1], "type": row[2],
        "content": row[3], "tags": json.loads(row[4] or "[]"),
        "feedback": row[5],
    }


async def get_context_memories(n: int = 8) -> list[dict]:
    """Memórias para uso como contexto em reflexões.

    Ordem: confirmed primeiro, depois neutral; dismissed excluídos.
    """
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback "
            "FROM personal_memory "
            "WHERE feedback IS NULL OR feedback = 'confirmed' "
            "ORDER BY CASE WHEN feedback = 'confirmed' THEN 0 ELSE 1 END, id DESC "
            "LIMIT ?",
            (n,),
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5],
        }
        for r in rows
    ]


async def clear_all() -> None:
    """Apaga toda a memória pessoal — irreversível."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        await db.execute("DELETE FROM personal_memory")
        await db.commit()
