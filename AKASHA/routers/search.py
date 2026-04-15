"""
AKASHA — Router de busca
GET /search?q=&sources=all|web|local → renderiza search.html
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import database
from services.web_search import SearchResult, search_web
from services.local_search import rank_combined, search_local

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = "",
    sources: str = "all",
) -> HTMLResponse:
    results: list[SearchResult] = []
    error: str | None = None

    if q:
        try:
            web: list[SearchResult] = []
            local: list[SearchResult] = []

            if sources in ("web", "all"):
                web = await search_web(q)
            if sources in ("local", "all"):
                local = await search_local(q)

            if sources == "all":
                results = rank_combined(web + local, q)
            else:
                results = web + local
        except RuntimeError as exc:
            error = str(exc)

        await database.save_search(q, sources, len(results))

    recent = await database.recent_searches()

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "results": results,
            "query": q,
            "sources": sources,
            "recent": recent,
            "error": error,
            "active_tab": "search",
        },
    )
