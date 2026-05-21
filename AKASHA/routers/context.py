"""
AKASHA — Router de contexto em tempo real
POST /context/push  — extensão informa URL que a usuária está lendo agora
GET  /context/status — estado de uma URL no índice AKASHA
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel

import database
from services import realtime_context as _ctx

router = APIRouter()
_log = logging.getLogger("akasha.context")


class ContextPushBody(BaseModel):
    url:           str
    title:         str
    selected_text: str | None = None
    source:        str = "extension"


@router.post("/context/push")
async def context_push(body: ContextPushBody) -> dict:
    """
    Registra a URL que a usuária está lendo agora.
    Se a página já estiver indexada, dispara appraisal emocional de leitura ativa
    e incrementa os scores dos tópicos no store compartilhado.
    """
    _ctx.push(body.url, body.title, body.selected_text, body.source)

    page = await database.get_page_knowledge(body.url)
    if page:
        topics: list[str] = page.get("topics") or []
        if topics:
            loop = asyncio.get_running_loop()
            loop.create_task(_record_active_reading_appraisal(topics, body.url))
            loop.create_task(_boost_topic_scores(topics))

    return {"ok": True}


@router.get("/context/status")
async def context_status(url: str) -> dict:
    """
    Retorna o estado de uma URL no ecossistema AKASHA:
    - archived: foi baixada e salva em ARCHIVE_PATH/Web/
    - in_library: domínio está nos sites rastreados (crawl_sites)
    - related_count: páginas indexadas com pelo menos um tópico em comum
    """
    archived = await database.url_is_archived(url)

    domain = (urlparse(url).hostname or "").removeprefix("www.").lower()
    in_library = await database.domain_in_crawl_sites(domain)

    related_count = 0
    page = await database.get_page_knowledge(url)
    if page:
        topics: list[str] = page.get("topics") or []
        if topics:
            related_count = await database.count_related_pages(url, topics)

    return {
        "archived":      archived,
        "in_library":    in_library,
        "related_count": related_count,
    }


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

async def _record_active_reading_appraisal(topics: list[str], url: str) -> None:
    """Appraisal de leitura ativa: goal_relevance e coping_potential fixos em 0.85."""
    try:
        from services.affective_state import record_appraisal

        topic_scores = await database.get_topic_scores_for_list(topics)
        avg_score = sum(topic_scores.get(t, 0.0) for t in topics) / max(len(topics), 1)
        familiarity   = min(1.0, avg_score / 20.0)
        novelty       = round(1.0 - familiarity, 4)
        pleasantness  = round(0.5 + familiarity * 0.5, 4)

        await record_appraisal(
            "active_reading", novelty, pleasantness,
            goal_relevance=0.85, coping_potential=0.85,
            event_ref=url,
        )
    except Exception as exc:
        _log.debug("_record_active_reading_appraisal: %s", exc)


async def _boost_topic_scores(topics: list[str]) -> None:
    """Incrementa +0.3 por tópico — leitura ativa é sinal forte de engajamento."""
    try:
        for topic in topics:
            await database.update_topic_score(topic, delta=0.3)
    except Exception as exc:
        _log.debug("_boost_topic_scores: %s", exc)
