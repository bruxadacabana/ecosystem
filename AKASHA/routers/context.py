"""
AKASHA — Router de contexto em tempo real
POST /context/push  — extensão informa URL que a usuária está lendo agora
POST /context/time  — extensão reporta tempo de leitura de uma página
GET  /context/status — estado de uma URL no índice AKASHA
"""
from __future__ import annotations

import asyncio
import logging
from math import log1p
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
    body_text:     str | None = None
    selected_text: str | None = None
    source:        str = "extension"


class ContextTimeBody(BaseModel):
    url:     str
    time_ms: int


@router.post("/context/push")
async def context_push(body: ContextPushBody) -> dict:
    """
    Registra a URL que a usuária está lendo agora.
    - Se a página já estiver indexada: appraisal de leitura ativa + boost de tópicos.
    - Se não estiver indexada e body_text presente: agenda extração de conhecimento
      (schedule_page com source_type "visited") para construir o perfil da página.
    """
    _ctx.push(body.url, body.title, body.selected_text, body.source)

    page = await database.get_page_knowledge(body.url)
    loop = asyncio.get_running_loop()

    if page:
        topics: list[str] = page.get("topics") or []
        if topics:
            loop.create_task(_record_active_reading_appraisal(topics, body.url))
            loop.create_task(_boost_topic_scores(topics))
    elif body.body_text:
        # Página ainda não indexada — agenda pipeline de conhecimento em background
        from services.knowledge_worker import schedule_page as _schedule_page
        _schedule_page(body.url, body.title, body.body_text.strip()[:3000], "visited")

    return {"ok": True}


@router.post("/context/time")
async def context_time(body: ContextTimeBody) -> dict:
    """
    Registra o tempo de leitura visível de uma página aberta via extensão.

    O delta de boost é logarítmico — satura em ~3.0 por volta de 20 min:
      delta = min(3.0, log1p(time_ms / 60_000))

    - delta >= 0.05: boost proporcional nos tópicos da página.
    - delta >= 0.1:  appraisal "active_reading" com goal_relevance e
                     coping_potential escalados pelo tempo.
    - time_ms >= 2 min: salva memória "Li '[título]' por N min".
    """
    time_ms = max(0, body.time_ms)
    delta   = min(3.0, log1p(time_ms / 60_000))

    if delta < 0.01:
        return {"ok": True}

    page    = await database.get_page_knowledge(body.url)
    topics  = (page.get("topics") or []) if page else []
    title   = (page.get("title")  or body.url) if page else body.url

    loop = asyncio.get_running_loop()

    if topics and delta >= 0.05:
        loop.create_task(_boost_reading_time_scores(topics, delta))

    if delta >= 0.1:
        gr = min(1.0, 0.5 + delta * 0.15)
        cp = min(1.0, 0.5 + delta * 0.15)
        loop.create_task(_record_reading_time_appraisal(body.url, gr, cp))

    if time_ms >= 120_000:
        minutes = round(time_ms / 60_000, 1)
        loop.create_task(_save_reading_memory(body.url, title, minutes))

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


async def _boost_reading_time_scores(topics: list[str], delta: float) -> None:
    """Boost proporcional ao tempo de leitura (delta já calculado pelo caller)."""
    try:
        for topic in topics:
            await database.update_topic_score(topic, delta=delta)
    except Exception as exc:
        _log.debug("_boost_reading_time_scores: %s", exc)


async def _record_reading_time_appraisal(url: str, goal_relevance: float, coping_potential: float) -> None:
    try:
        from services.affective_state import record_appraisal
        await record_appraisal(
            "active_reading", novelty=0.4, pleasantness=0.7,
            goal_relevance=goal_relevance, coping_potential=coping_potential,
            event_ref=url,
        )
    except Exception as exc:
        _log.debug("_record_reading_time_appraisal: %s", exc)


async def _save_reading_memory(url: str, title: str, minutes: float) -> None:
    try:
        from services.personal_memory import save_memory
        content = f"Li '{title}' por {minutes} min — leitura com engajamento real."
        await save_memory(
            type="reading", content=content,
            tags=["leitura_ativa", "extensão"], importance=2,
        )
    except Exception as exc:
        _log.debug("_save_reading_memory: %s", exc)
