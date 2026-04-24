"""
AKASHA — Domínios favoritos (P2 na priorização de busca)
GET    /favorites                        : página com lista + formulário
POST   /favorites/add                    : adiciona domínio
DELETE /favorites/{domain}               : remove favorito
POST   /favorites/{domain}/to-blacklist  : move para lista negra
POST   /favorites/{domain}/to-library    : adiciona à biblioteca (crawl)
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from database import (
    add_favorite_domain,
    remove_favorite_domain,
    list_favorite_domains,
    add_blocked_domain,
    add_crawl_site,
)

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


def _extract_domain(url: str) -> str:
    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return (urlparse(raw).hostname or "").removeprefix("www.").lower()


@router.get("/favorites", response_class=HTMLResponse)
async def favorites_page(request: Request) -> HTMLResponse:
    rows = await list_favorite_domains()
    return templates.TemplateResponse(
        request,
        "favorites.html",
        {"favorites": rows, "active_tab": "favorites"},
    )


@router.post("/favorites/add", response_class=HTMLResponse)
async def favorites_add(
    request: Request,
    url:   str = Form(...),
    label: str = Form(""),
) -> HTMLResponse:
    domain = _extract_domain(url)
    if not domain:
        raise HTTPException(status_code=400, detail="URL ou domínio inválido")
    await add_favorite_domain(domain, label=label.strip())
    rows = await list_favorite_domains()
    return templates.TemplateResponse(request, "_favorites_list.html", {"favorites": rows})


@router.delete("/favorites/{domain}", response_class=HTMLResponse)
async def favorites_remove(request: Request, domain: str) -> HTMLResponse:
    await remove_favorite_domain(domain)
    rows = await list_favorite_domains()
    return templates.TemplateResponse(request, "_favorites_list.html", {"favorites": rows})


@router.post("/favorites/{domain}/to-blacklist", response_class=HTMLResponse)
async def favorites_to_blacklist(request: Request, domain: str) -> HTMLResponse:
    await add_blocked_domain(domain)
    await remove_favorite_domain(domain)
    rows = await list_favorite_domains()
    return templates.TemplateResponse(request, "_favorites_list.html", {"favorites": rows})


@router.post("/favorites/{domain}/to-library")
async def favorites_to_library(domain: str) -> Response:
    import asyncio
    from services.crawler import crawl_site
    site_id = await add_crawl_site(
        f"https://{domain}", domain, crawl_depth=2, subdomains_json="[]"
    )
    if site_id:
        async def _bg(sid: int) -> None:
            import logging
            try:
                await crawl_site(sid)
            except Exception as exc:
                logging.getLogger("akasha.favorites").warning("crawl %d: %s", sid, exc)
        asyncio.get_running_loop().create_task(_bg(site_id))
    return Response(status_code=200)
