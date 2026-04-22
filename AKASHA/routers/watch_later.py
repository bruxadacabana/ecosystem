"""AKASHA — Router Ver Mais Tarde (Fase 12.5)"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from database import (
    add_watch_later,
    delete_watch_later,
    get_all_watch_later,
    update_watch_later_notes,
)

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@router.get("/watch-later", response_class=HTMLResponse)
async def watch_later_page(request: Request) -> HTMLResponse:
    rows = await get_all_watch_later()
    items = [
        {"id": r[0], "url": r[1], "title": r[2] or r[1], "snippet": r[3],
         "notes": r[4], "added_at": r[5]}
        for r in rows
    ]
    return templates.TemplateResponse(
        request, "watch_later.html", {"items": items, "active_tab": "watch_later"}
    )


@router.post("/watch-later/add")
async def watch_later_add(
    url:     str = Form(...),
    title:   str = Form(""),
    snippet: str = Form(""),
) -> Response:
    await add_watch_later(url, title, snippet)
    return Response(status_code=200)


@router.patch("/watch-later/{item_id}/notes")
async def watch_later_notes(item_id: int, notes: str = Form("")) -> Response:
    await update_watch_later_notes(item_id, notes)
    return Response(status_code=200)


@router.delete("/watch-later/{item_id}")
async def watch_later_delete(item_id: int) -> Response:
    await delete_watch_later(item_id)
    return Response(status_code=200)
