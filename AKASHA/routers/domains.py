"""
AKASHA — Lista negra de domínios
GET  /domains                  : página com lista de domínios bloqueados
POST /domains/block            : bloqueia domínio extraído de uma URL
DELETE /domains/block/{domain} : desbloqueia
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from database import add_blocked_domain, get_blocked_domains, remove_blocked_domain

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


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


@router.post("/domains/block")
async def block_domain(url: str = Form(...)) -> Response:
    domain = _extract_domain(url)
    if not domain:
        raise HTTPException(status_code=400, detail="URL inválida")
    await add_blocked_domain(domain)
    return Response(status_code=200)


@router.delete("/domains/block/{domain}")
async def unblock_domain(domain: str) -> Response:
    await remove_blocked_domain(domain)
    return Response(status_code=200)
