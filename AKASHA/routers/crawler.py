"""
AKASHA — Router da Biblioteca (crawler de domínios)
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

import markdown as _md

from database import (
    add_crawl_site, delete_crawl_site, get_all_crawl_sites,
    get_crawl_page_by_id, get_crawl_page_by_url, get_crawl_pages_by_site,
    get_crawl_site, update_crawl_site,
)
from services.crawler import crawl_site, discover_subdomains, is_crawl_paused, set_crawl_paused
from services import list_sync as _ls

router = APIRouter()
_log = logging.getLogger("akasha.user_data")

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Modelo local (evita raw tuples nos templates)
# ---------------------------------------------------------------------------

@dataclass
class CrawlSite:
    id:                  int
    base_url:            str
    label:               str
    crawl_depth:         int
    subdomains:          list[str]
    page_count:          int
    last_crawled_at:     str | None
    status:              str
    created_at:          str
    crawl_interval_days: int = 7
    crawl_frequency:     str = "weekly"


def _row_to_site(row: tuple) -> CrawlSite:
    import json
    return CrawlSite(
        id=row[0], base_url=row[1], label=row[2], crawl_depth=row[3],
        subdomains=json.loads(row[4] or "[]"),
        page_count=row[5], last_crawled_at=row[6],
        status=row[7], created_at=row[8],
        crawl_interval_days=row[9] if len(row) > 9 else 7,
        crawl_frequency=row[12] if len(row) > 12 else "weekly",
    )


# ---------------------------------------------------------------------------
# GET /library
# ---------------------------------------------------------------------------

@router.get("/library", response_class=HTMLResponse)
async def library_page(request: Request) -> HTMLResponse:
    rows = await get_all_crawl_sites()
    sites = [_row_to_site(r) for r in rows]
    return templates.TemplateResponse(
        request,
        "library.html",
        {"sites": sites, "active_tab": "library"},
    )


# ---------------------------------------------------------------------------
# POST /library/discover
# ---------------------------------------------------------------------------

@router.post("/library/discover", response_class=HTMLResponse)
async def library_discover(request: Request, url: str = Form(...)) -> HTMLResponse:
    """Descobre subdomínios e retorna fragment HTMX com checkboxes."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL inválida")

    base_url   = f"{parsed.scheme}://{parsed.netloc}"
    subdomains = await discover_subdomains(base_url)

    return templates.TemplateResponse(
        request,
        "_library_discover.html",
        {"base_url": base_url, "subdomains": subdomains},
    )


# ---------------------------------------------------------------------------
# POST /library
# ---------------------------------------------------------------------------

@router.post("/library", response_class=HTMLResponse)
async def library_add(
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
        asyncio.get_running_loop().create_task(_bg_crawl(site_id))
        asyncio.create_task(_ls.write_json("sites"))

    rows  = await get_all_crawl_sites()
    sites = [_row_to_site(r) for r in rows]
    return templates.TemplateResponse(
        request,
        "_library_list.html",
        {"sites": sites},
    )


# ---------------------------------------------------------------------------
# POST /library/add-quick — adiciona domínio a partir de uma URL de resultado
# ---------------------------------------------------------------------------

@router.post("/library/add-quick")
async def library_add_quick(url: str = Form(...)) -> Response:
    """Adiciona domínio base de uma URL à biblioteca com defaults."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL inválida")
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    site_id = await add_crawl_site(base_url, base_url, crawl_depth=2, subdomains_json="[]")
    if site_id:
        asyncio.get_running_loop().create_task(_bg_crawl(site_id))
        asyncio.create_task(_ls.write_json("sites"))
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# GET /library/crawl/status · POST /library/crawl/pause · /resume
# ---------------------------------------------------------------------------

@router.get("/library/crawl/status")
async def crawl_status_api() -> dict:
    return {"paused": is_crawl_paused()}


@router.post("/library/crawl/pause")
async def crawl_pause_api() -> dict:
    set_crawl_paused(True)
    _log.info("crawling pausado pela usuária.")
    return {"paused": True}


@router.post("/library/crawl/resume")
async def crawl_resume_api() -> dict:
    set_crawl_paused(False)
    _log.info("crawling retomado pela usuária.")
    return {"paused": False}


# ---------------------------------------------------------------------------
# PATCH /library/{site_id} — atualiza configurações do site
# ---------------------------------------------------------------------------

@router.patch("/library/{site_id}", response_class=HTMLResponse)
async def library_update(
    request: Request,
    site_id: int,
    label:               str = Form(...),
    crawl_depth:         int = Form(2),
    crawl_interval_days: int = Form(7),
    crawl_frequency:     str = Form(""),
) -> HTMLResponse:
    """Atualiza label, profundidade, intervalo e frequência de recrawl de um site."""
    _valid_freqs = {"daily", "weekly", "monthly"}
    crawl_depth         = max(1, min(crawl_depth, 10))
    crawl_interval_days = max(1, min(crawl_interval_days, 365))
    freq = crawl_frequency if crawl_frequency in _valid_freqs else None
    await update_crawl_site(site_id, label, crawl_depth, crawl_interval_days, freq)
    asyncio.create_task(_ls.write_json("sites"))
    rows  = await get_all_crawl_sites()
    sites = [_row_to_site(r) for r in rows]
    return templates.TemplateResponse(request, "_library_list.html", {"sites": sites})


# ---------------------------------------------------------------------------
# DELETE /library/{site_id}
# ---------------------------------------------------------------------------

@router.delete("/library/{site_id}")
async def library_delete(site_id: int) -> Response:
    """Remove site e todas as páginas indexadas (cascade)."""
    await delete_crawl_site(site_id)
    asyncio.create_task(_ls.write_json("sites"))
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# POST /library/{site_id}/crawl — re-crawl manual
# ---------------------------------------------------------------------------

@router.post("/library/{site_id}/crawl")
async def library_crawl(site_id: int) -> Response:
    """Dispara re-crawl manual em background; retorna 200 imediatamente."""
    from database import get_crawl_site
    if not await get_crawl_site(site_id):
        raise HTTPException(status_code=404, detail="Site não encontrado")
    asyncio.get_running_loop().create_task(_bg_crawl(site_id))
    return Response(status_code=200)


_PAGES_SIZE = 20


@router.get("/library/{site_id}/pages", response_class=HTMLResponse)
async def library_site_pages(
    request: Request,
    site_id: int,
    q: str = "",
    page: int = 1,
) -> HTMLResponse:
    """Fragment HTMX: lista paginada de páginas crawleadas de um site."""
    offset = (page - 1) * _PAGES_SIZE
    rows = await get_crawl_pages_by_site(site_id, limit=_PAGES_SIZE + 1, offset=offset, q=q)
    has_more = len(rows) > _PAGES_SIZE
    return templates.TemplateResponse(
        request,
        "_site_pages.html",
        {
            "site_id":  site_id,
            "pages":    rows[:_PAGES_SIZE],
            "page":     page,
            "q":        q,
            "has_more": has_more,
        },
    )


@router.get("/library/reader", response_class=HTMLResponse)
async def library_reader(request: Request, url: str = "") -> HTMLResponse:
    """Reader mode: abre o conteúdo de uma crawl_page pelo URL."""
    if not url:
        raise HTTPException(status_code=400, detail="Parâmetro url é obrigatório")
    page = await get_crawl_page_by_url(url)
    if not page:
        raise HTTPException(status_code=404, detail="Página não encontrada no índice")
    # row: id(0) site_id(1) url(2) title(3) content_md(4) http_status(5) crawled_at(6)
    content_html = _md.markdown(page[4], extensions=["extra", "toc"]) if page[4] else ""
    return templates.TemplateResponse(
        request,
        "page_reader.html",
        {
            "title":        page[3] or page[2],
            "url":          page[2],
            "crawled_at":   page[6],
            "http_status":  page[5],
            "content_html": content_html,
            "active_tab":   "library",
        },
    )


@router.post("/library/{site_id}/pages/{page_id}/archive", response_class=HTMLResponse)
async def library_archive_page(site_id: int, page_id: int) -> HTMLResponse:
    """Arquiva conteúdo de uma página crawleada em disco como HTML."""
    from urllib.parse import urlparse
    import re
    from config import ARCHIVE_PATH

    page = await get_crawl_page_by_id(page_id)
    if not page:
        return HTMLResponse('<span style="color:var(--error)">Não encontrado</span>', status_code=404)

    # row: id(0) site_id(1) url(2) title(3) content_md(4) http_status(5) crawled_at(6)
    url      = page[2]
    title    = page[3] or url
    content_md = page[4] or ""

    parsed = urlparse(url)
    domain = parsed.netloc or "unknown"
    path_part = (parsed.path or "index").strip("/").replace("/", "_") or "index"
    slug = re.sub(r"[^\w\-]", "_", path_part)[:80]

    content_html = _md.markdown(content_md, extensions=["extra", "toc"])
    html_doc = (
        "<!DOCTYPE html><html><head>"
        f'<meta charset="utf-8"><title>{title}</title>'
        "</head><body>"
        f"<h1>{title}</h1>"
        f'<p><a href="{url}">{url}</a></p>'
        f"{content_html}"
        "</body></html>"
    )

    dest_dir = ARCHIVE_PATH / "sites" / domain
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{slug}.html"
        dest_file.write_text(html_doc, encoding="utf-8")
    except OSError as exc:
        _log.warning("archive page %d: %s", page_id, exc)
        return HTMLResponse('<span style="color:var(--error)">Erro ao salvar</span>')

    return HTMLResponse('<span style="color:var(--success);font-size:11px;">✓</span>')


async def _bg_crawl(site_id: int) -> None:
    import logging
    log = logging.getLogger("akasha.crawler")
    try:
        await crawl_site(site_id)
    except Exception as exc:
        log.warning("bg crawl %d: %s", site_id, exc)
