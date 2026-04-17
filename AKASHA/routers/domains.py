"""
AKASHA — Lista negra de domínios
POST /domains/block : bloqueia domínio extraído de uma URL
DELETE /domains/block/{domain} : desbloqueia
"""
from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import Response

from database import add_blocked_domain, remove_blocked_domain

router = APIRouter()


def _extract_domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.").lower()


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
