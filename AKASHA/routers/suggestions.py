"""
AKASHA — Router de sugestões automáticas de domínios para a Biblioteca.
GET  /suggestions               → lista sugestões pendentes
POST /suggestions/run           → (re)calcula sugestões agora
POST /suggestions/{domain}/approve  → adiciona à Biblioteca + status approved
POST /suggestions/{domain}/ignore   → status ignored (pode reaparecer na próxima rodada)
POST /suggestions/{domain}/block    → status blocked (nunca mais sugerido)
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote_plus

import aiosqlite
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config import DB_PATH
from database import add_crawl_site
from services.suggester import (
    compute_suggestions,
    get_pending_suggestions,
    set_suggestion_status,
    update_wiki_citation_counts,
)

router = APIRouter()
log = logging.getLogger("akasha.suggestions")

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@router.get("/suggestions", response_class=HTMLResponse)
async def suggestions_page(request: Request):
    async with aiosqlite.connect(DB_PATH) as db:
        pending = await get_pending_suggestions(db)
    return templates.TemplateResponse(
        "suggestions.html",
        {"request": request, "suggestions": pending},
    )


@router.post("/suggestions/run", response_class=HTMLResponse)
async def run_suggestions(request: Request):
    """Recalcula sugestões e retorna o fragmento HTMX atualizado."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Atualiza contagens de citações Wikipedia antes de calcular sugestões
        try:
            await update_wiki_citation_counts(db)
        except Exception as exc:
            log.warning("run_suggestions: update_wiki_citation_counts falhou: %s", exc)
        await compute_suggestions(db)
        await db.commit()
        pending = await get_pending_suggestions(db)
    return templates.TemplateResponse(
        "suggestions.html",
        {"request": request, "suggestions": pending},
    )


@router.post("/suggestions/{domain:path}/approve", response_class=HTMLResponse)
async def approve_suggestion(request: Request, domain: str):
    """Adiciona o domínio à Biblioteca e marca como approved."""
    base_url = f"https://{domain}"
    try:
        await add_crawl_site(base_url, label=domain, crawl_depth=2, subdomains_json="[]")
    except Exception as exc:
        log.warning("approve_suggestion: add_crawl_site falhou para %s: %s", domain, exc)
    async with aiosqlite.connect(DB_PATH) as db:
        await set_suggestion_status(db, domain, "approved")
        await db.commit()
        pending = await get_pending_suggestions(db)
    return templates.TemplateResponse(
        "suggestions.html",
        {"request": request, "suggestions": pending},
    )


@router.post("/suggestions/{domain:path}/ignore", response_class=HTMLResponse)
async def ignore_suggestion(request: Request, domain: str):
    """Marca como ignored — pode reaparecer na próxima rodada de compute_suggestions."""
    async with aiosqlite.connect(DB_PATH) as db:
        await set_suggestion_status(db, domain, "ignored")
        await db.commit()
        pending = await get_pending_suggestions(db)
    return templates.TemplateResponse(
        "suggestions.html",
        {"request": request, "suggestions": pending},
    )


@router.post("/suggestions/{domain:path}/block", response_class=HTMLResponse)
async def block_suggestion(request: Request, domain: str):
    """Bloqueia permanentemente — nunca mais aparecerá como sugestão."""
    async with aiosqlite.connect(DB_PATH) as db:
        await set_suggestion_status(db, domain, "blocked")
        await db.commit()
        pending = await get_pending_suggestions(db)
    return templates.TemplateResponse(
        "suggestions.html",
        {"request": request, "suggestions": pending},
    )
