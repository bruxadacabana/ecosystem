"""
AKASHA — Store de memória pessoal.

Memória interna da AKASHA: observações, conexões, surpresas e reflexões.
Isolada — nunca exposta por API pública, nunca indexada no vectorstore.
Arquivo separado do DB principal: {ai_private_dir}/akasha/personal_memory.db.

Cada entrada tem um `type` (subtipo) e uma `category` (gaveta temática).
A category é auto-derivada das tags ao salvar, mas pode ser passada explicitamente.

Categories disponíveis:
  "friendship"   — memórias trocadas com a Mnemosyne ("visitas")
  "about_user"   — observações sobre Jenifer e como ela trabalha
  "interests"    — tópicos que foram marcantes nas pesquisas
  "reflections"  — pensamentos sobre o próprio conhecimento (default)
  "world"        — observações gerais sobre o mundo
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import aiosqlite

_VALID_TYPES = {"observation", "connection", "surprise", "reflection"}
_VALID_CATEGORIES = {"friendship", "about_user", "interests", "reflections", "world"}

# Mapeamento tag → category (primeira tag reconhecida tem prioridade)
_CATEGORY_FROM_TAG: dict[str, str] = {
    "from_mnemosyne":  "friendship",
    "from_akasha":     "friendship",
    "about_user":      "about_user",
    "session_insight": "reflections",
    "loop_periodico":  "reflections",
}

_PM_DDL = """
CREATE TABLE IF NOT EXISTS personal_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    type       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    tags       TEXT    NOT NULL DEFAULT '[]',
    feedback   TEXT             DEFAULT NULL,
    category   TEXT    NOT NULL DEFAULT 'reflections'
);
"""


def _derive_category(tags: list[str]) -> str:
    """Deriva category automaticamente das tags. Default: 'reflections'."""
    for tag in tags:
        cat = _CATEGORY_FROM_TAG.get(tag)
        if cat:
            return cat
    return "reflections"


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
        # Migration: adiciona coluna em DBs anteriores
        try:
            await db.execute(
                "ALTER TABLE personal_memory ADD COLUMN category TEXT NOT NULL DEFAULT 'reflections'"
            )
        except Exception:
            pass  # coluna já existe
        await db.commit()


async def save_memory(
    type: str,
    content: str,
    tags: list[str] | None = None,
    category: str | None = None,
) -> int:
    """Salva entrada de memória pessoal. Retorna o id da nova entrada.

    Se `category` não for passado, é derivado automaticamente das tags.
    """
    if type not in _VALID_TYPES:
        type = "observation"
    if tags is None:
        tags = []
    if category is None or category not in _VALID_CATEGORIES:
        category = _derive_category(tags)
    async with aiosqlite.connect(_get_pm_db()) as db:
        cur = await db.execute(
            "INSERT INTO personal_memory (type, content, tags, category) VALUES (?, ?, ?, ?)",
            (type, content, json.dumps(tags, ensure_ascii=False), category),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def get_recent(n: int = 10) -> list[dict]:
    """Retorna as N entradas mais recentes."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category "
            "FROM personal_memory ORDER BY id DESC LIMIT ?",
            (n,),
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
        }
        for r in rows
    ]


async def get_all() -> list[dict]:
    """Retorna todas as entradas em ordem decrescente."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category "
            "FROM personal_memory ORDER BY id DESC",
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
        }
        for r in rows
    ]


async def get_by_category(category: str, n: int = 50) -> list[dict]:
    """Retorna entradas de uma category específica, mais recentes primeiro."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category "
            "FROM personal_memory WHERE category = ? ORDER BY id DESC LIMIT ?",
            (category, n),
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
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
            "SELECT id, created_at, type, content, tags, feedback, category "
            "FROM personal_memory WHERE id = ?",
            (memory_id,),
        )).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "created_at": row[1], "type": row[2],
        "content": row[3], "tags": json.loads(row[4] or "[]"),
        "feedback": row[5], "category": row[6],
    }


async def get_context_memories(n: int = 8) -> list[dict]:
    """Memórias para uso como contexto em reflexões.

    Ordem: confirmed primeiro, depois neutral; dismissed excluídos.
    """
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category "
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
            "feedback": r[5], "category": r[6],
        }
        for r in rows
    ]


async def clear_all() -> None:
    """Apaga toda a memória pessoal — irreversível."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        await db.execute("DELETE FROM personal_memory")
        await db.commit()
