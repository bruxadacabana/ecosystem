"""
AKASHA — Router de lenses pessoais
GET  /lenses           → tela de gestão
POST /lenses           → criar lens
PUT  /lenses/{id}      → atualizar lens
DELETE /lenses/{id}    → excluir lens (HTMX swap)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

import database

router = APIRouter()
_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@router.get("/lenses", response_class=HTMLResponse)
async def lenses_page(request: Request) -> HTMLResponse:
    lenses = await database.list_lenses()
    return templates.TemplateResponse(
        request, "lenses.html", {"lenses": lenses, "active_tab": "lenses"}
    )


@router.post("/lenses", response_class=HTMLResponse)
async def create_lens(
    request: Request,
    name:          str = Form(...),
    domains:       str = Form(""),
    tags:          str = Form(""),
    content_types: str = Form(""),
    date_from:     str = Form(""),
    date_to:       str = Form(""),
) -> HTMLResponse:
    if name.strip():
        await database.create_lens(
            name.strip(), domains.strip(), tags.strip(),
            content_types.strip(), date_from.strip(), date_to.strip(),
        )
    lenses = await database.list_lenses()
    return templates.TemplateResponse(
        request, "lenses.html", {"lenses": lenses, "active_tab": "lenses"}
    )


@router.put("/lenses/{lens_id}")
async def update_lens(
    lens_id:       int,
    name:          str = Form(...),
    domains:       str = Form(""),
    tags:          str = Form(""),
    content_types: str = Form(""),
    date_from:     str = Form(""),
    date_to:       str = Form(""),
) -> Response:
    await database.update_lens(
        lens_id, name.strip(), domains.strip(), tags.strip(),
        content_types.strip(), date_from.strip(), date_to.strip(),
    )
    return Response(status_code=200)


@router.delete("/lenses/{lens_id}")
async def delete_lens(lens_id: int) -> Response:
    await database.delete_lens(lens_id)
    return Response(status_code=200)
