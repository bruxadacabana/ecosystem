"""
AKASHA — Router de Sites Pessoais (Fase 10)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from database import get_all_crawl_sites

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
