"""
AKASHA — Gerenciamento da memória pessoal.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/memory", tags=["memory"])


@router.delete("/clear")
async def clear_memory() -> dict:
    """Apaga toda a memória pessoal acumulada. Irreversível."""
    from services.personal_memory import clear_all
    await clear_all()
    return {"ok": True}


@router.get("/entries")
async def list_entries(n: int = 20) -> list[dict]:
    """Retorna as N entradas mais recentes de personal_memory."""
    from services.personal_memory import get_recent
    return await get_recent(n)


@router.get("/topics")
async def list_topics(n: int = 30) -> list[dict]:
    """Retorna os N tópicos com maior score no perfil de interesses unificado do ecossistema.

    Lê de shared_topic_profile.db — acumula contribuições de AKASHA, Mnemosyne e KOSMOS.
    """
    import database as _db
    rows = await _db.get_top_topics(n)
    return [{"topic": t, "score": s} for t, s in rows]


class _FeedbackBody(BaseModel):
    feedback: str | None  # "confirmed" | "dismissed" | null


@router.patch("/{memory_id}/feedback")
async def set_entry_feedback(memory_id: int, body: _FeedbackBody) -> dict:
    """Define feedback da usuária para uma entrada de memória."""
    if body.feedback not in {None, "confirmed", "dismissed"}:
        raise HTTPException(status_code=422, detail="feedback deve ser 'confirmed', 'dismissed' ou null")
    from services.personal_memory import set_feedback
    await set_feedback(memory_id, body.feedback)
    return {"ok": True}
