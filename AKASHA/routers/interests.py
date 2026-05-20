"""
AKASHA — Endpoint de sincronização de interesses com o HUB.

POST /interests/refresh  — lê interests.json e popula topic_interest_profile
                           com os seeds definidos pela usuária no HUB.
                           Só inicializa tópicos sem histórico; nunca
                           sobrescreve scores acumulados pela AKASHA.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

log = logging.getLogger("akasha.interests")

router = APIRouter(prefix="/interests", tags=["interests"])


@router.post("/refresh")
async def interests_refresh() -> dict:
    """Importa tópicos de interests.json para topic_interest_profile.

    Chamado pelo HUB quando a usuária atualiza o perfil de interesses.
    Tópicos excluídos são ignorados. Score inicial = weight do interests.json,
    mas apenas se o tópico ainda não existir (score = 0 ou ausente).
    """
    try:
        from ecosystem_client import get_interests  # type: ignore
        interests = get_interests()
    except Exception as exc:
        log.warning("interests_refresh: não foi possível ler interests.json: %s", exc)
        return {"imported": 0, "error": str(exc)}

    if not interests:
        return {"imported": 0}

    import database as _db

    count = 0
    for entry in interests:
        if entry.get("excluded"):
            continue
        name = (entry.get("name") or "").strip().lower()
        if not name or len(name) < 3:
            continue
        existing = await _db.get_topic_score(name)
        if existing is not None and existing > 0.0:
            continue  # já tem histórico acumulado — não sobrescrever
        weight = max(0.1, float(entry.get("weight") or 1.0))
        await _db.update_topic_score(name, delta=weight)
        count += 1

    log.info("interests_refresh: %d tópico(s) importados de interests.json.", count)
    return {"imported": count}


@router.get("/topics")
async def get_topics(n: int = 30) -> list[dict]:
    """Retorna os N tópicos com maior score no topic_interest_profile da AKASHA."""
    import database as _db
    rows = await _db.get_top_topics(n)
    return [{"topic": t, "score": round(s, 4)} for t, s in rows]
