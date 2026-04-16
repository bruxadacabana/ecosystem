"""
AKASHA — Router de busca
GET /search?q=&sources=all|web|local → renderiza search.html
"""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

import config
import database
from services.archiver import archive_url
from services.web_search import SearchResult, search_web
from services.local_search import search_local

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@router.post("/archive")
async def archive(
    url: str = Form(...),
    tags: str = Form(""),    # comma-separated, ex: "python, web, referência"
    notes: str = Form(""),
) -> Response:
    """Arquiva uma URL no formato KOSMOS estendido em {archive_path}/Web/."""
    if not config.kosmos_archive:
        raise HTTPException(
            status_code=400,
            detail="KOSMOS archive não configurado. Configure o caminho em /settings.",
        )
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    try:
        await archive_url(url, config.kosmos_archive, tags=tag_list, notes=notes)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Erro HTTP ao buscar URL: {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Falha de rede: {exc}")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return Response(status_code=200)


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = "",
    sources: str = "all",
) -> HTMLResponse:
    web_results: list[SearchResult] = []
    local_results: list[SearchResult] = []
    error: str | None = None

    if q:
        try:
            if sources in ("web", "all"):
                web_results = await search_web(q)
            if sources in ("local", "all"):
                local_results = await search_local(q)
        except RuntimeError as exc:
            error = str(exc)

        total = len(web_results) + len(local_results)
        await database.save_search(q, sources, total)

    recent = await database.recent_searches()

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "web_results": web_results,
            "local_results": local_results,
            "query": q,
            "sources": sources,
            "recent": recent,
            "error": error,
            "active_tab": "search",
        },
    )
