"""
AKASHA — Lista negra de domínios
GET  /domains                  : página com lista de domínios bloqueados
POST /domains/block            : bloqueia domínio extraído de uma URL
DELETE /domains/block/{domain} : desbloqueia
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from database import add_blocked_domain, get_blocked_domains, remove_blocked_domain, list_blocked_domains
from services import user_data as _ud

router = APIRouter()
_log = logging.getLogger("akasha.user_data")

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


async def _snapshot_blocked() -> None:
    try:
        rows = await list_blocked_domains()
        _ud.save_blocked_domains([{"domain": r[0], "added_at": r[1]} for r in rows])
    except Exception as exc:
        _log.warning("save_blocked_domains: %s", exc)


def _extract_domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.").lower()


@router.get("/domains", response_class=HTMLResponse)
async def domains_page(request: Request) -> HTMLResponse:
    domains = sorted(await get_blocked_domains())
    return templates.TemplateResponse(
        request,
        "domains.html",
        {"domains": domains, "active_tab": "domains"},
    )


@router.post("/domains/block", response_class=HTMLResponse)
async def block_domain(request: Request, url: str = Form(...)) -> HTMLResponse:
    domain = _extract_domain(url)
    if not domain:
        raise HTTPException(status_code=400, detail="URL inválida")
    await add_blocked_domain(domain)
    await _snapshot_blocked()
    domains = sorted(await get_blocked_domains())
    return templates.TemplateResponse(request, "_domains_list.html", {"domains": domains})


@router.delete("/domains/block/{domain}", response_class=HTMLResponse)
async def unblock_domain(request: Request, domain: str) -> HTMLResponse:
    await remove_blocked_domain(domain)
    await _snapshot_blocked()
    domains = sorted(await get_blocked_domains())
    return templates.TemplateResponse(request, "_domains_list.html", {"domains": domains})
