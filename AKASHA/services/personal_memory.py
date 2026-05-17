"""
AKASHA — Store de memória pessoal.

Memória interna da AKASHA: observações, conexões, surpresas e reflexões.
Isolada — nunca exposta por API pública, nunca indexada no vectorstore.
"""
from __future__ import annotations

import json

import aiosqlite

from config import DB_PATH

_VALID_TYPES = {"observation", "connection", "surprise", "reflection"}


async def save_memory(
    type: str,
    content: str,
    tags: list[str] | None = None,
) -> None:
    """Salva entrada de memória pessoal. type deve ser um dos _VALID_TYPES."""
    if type not in _VALID_TYPES:
        type = "observation"
    if tags is None:
        tags = []
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO personal_memory (type, content, tags) VALUES (?, ?, ?)",
            (type, content, json.dumps(tags, ensure_ascii=False)),
        )
        await db.commit()


async def get_recent(n: int = 10) -> list[dict]:
    """Retorna as N entradas mais recentes."""
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE personal_memory SET feedback = ? WHERE id = ?",
            (feedback, memory_id),
        )
        await db.commit()


async def get_context_memories(n: int = 8) -> list[dict]:
    """Memórias para uso como contexto em reflexões.

    Ordem: confirmed primeiro, depois neutral; dismissed excluídos.
    """
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM personal_memory")
        await db.commit()
