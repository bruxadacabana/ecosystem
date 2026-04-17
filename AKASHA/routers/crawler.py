"""
AKASHA — Router de Sites Pessoais (Fase 10)
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from database import add_crawl_site, delete_crawl_site, get_all_crawl_sites
from services.crawler import crawl_site, discover_subdomains

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Modelo local (evita raw tuples nos templates)
# ---------------------------------------------------------------------------

@dataclass
class CrawlSite:
    id:              int
    base_url:        str
    label:           str
    crawl_depth:     int
    subdomains:      list[str]
    page_count:      int
    last_crawled_at: str | None
    status:          str
    created_at:      str


def _row_to_site(row: tuple) -> CrawlSite:
    import json
    return CrawlSite(
        id=row[0], base_url=row[1], label=row[2], crawl_depth=row[3],
        subdomains=json.loads(row[4] or "[]"),
        page_count=row[5], last_crawled_at=row[6],
        status=row[7], created_at=row[8],
    )


# ---------------------------------------------------------------------------
# GET /sites
# ---------------------------------------------------------------------------

@router.get("/sites", response_class=HTMLResponse)
async def sites_page(request: Request) -> HTMLResponse:
    rows = await get_all_crawl_sites()
    sites = [_row_to_site(r) for r in rows]
    return templates.TemplateResponse(
        request,
        "sites.html",
        {"sites": sites, "active_tab": "sites"},
    )


# ---------------------------------------------------------------------------
# POST /sites/discover
# ---------------------------------------------------------------------------

@router.post("/sites/discover", response_class=HTMLResponse)
async def sites_discover(request: Request, url: str = Form(...)) -> HTMLResponse:
    """Descobre subdomínios e retorna fragment HTMX com checkboxes."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL inválida")

    base_url   = f"{parsed.scheme}://{parsed.netloc}"
    subdomains = await discover_subdomains(base_url)

    return templates.TemplateResponse(
        request,
        "_sites_discover.html",
        {"base_url": base_url, "subdomains": subdomains},
    )


# ---------------------------------------------------------------------------
# POST /sites
# ---------------------------------------------------------------------------

@router.post("/sites", response_class=HTMLResponse)
async def sites_add(
    request: Request,
    url:         str  = Form(...),
    label:       str  = Form(""),
    crawl_depth: int  = Form(2),
    subdomains:  list[str] = Form(default=[]),
) -> HTMLResponse:
    """Cria site e dispara crawl em background; retorna lista atualizada."""
    import json
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL inválida")

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    site_id  = await add_crawl_site(
        base_url, label or base_url, crawl_depth, json.dumps(subdomains)
    )
    if site_id:
        asyncio.get_event_loop().create_task(_bg_crawl(site_id))

    rows  = await get_all_crawl_sites()
    sites = [_row_to_site(r) for r in rows]
    return templates.TemplateResponse(
        request,
        "_sites_list.html",
        {"sites": sites},
    )


# ---------------------------------------------------------------------------
# DELETE /sites/{site_id}
# ---------------------------------------------------------------------------

@router.delete("/sites/{site_id}")
async def sites_delete(site_id: int) -> Response:
    """Remove site e todas as páginas indexadas (cascade)."""
    await delete_crawl_site(site_id)
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# POST /sites/{site_id}/crawl — re-crawl manual
# ---------------------------------------------------------------------------

@router.post("/sites/{site_id}/crawl")
async def sites_crawl(site_id: int) -> Response:
    """Dispara re-crawl manual em background; retorna 200 imediatamente."""
    from database import get_crawl_site
    if not await get_crawl_site(site_id):
        raise HTTPException(status_code=404, detail="Site não encontrado")
    asyncio.get_event_loop().create_task(_bg_crawl(site_id))
    return Response(status_code=200)


async def _bg_crawl(site_id: int) -> None:
    import logging
    log = logging.getLogger("akasha.crawler")
    try:
        await crawl_site(site_id)
    except Exception as exc:
        log.warning("bg crawl %d: %s", site_id, exc)
