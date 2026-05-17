"""
AKASHA — Gerenciamento da memória pessoal.
DELETE /memory/clear — apaga toda a memória pessoal da AKASHA.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/memory", tags=["memory"])


@router.delete("/clear")
async def clear_memory() -> dict:
    """Apaga toda a memória pessoal acumulada. Irreversível."""
    from services.personal_memory import clear_all
    await clear_all()
    return {"ok": True}
