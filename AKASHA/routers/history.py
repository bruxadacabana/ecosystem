"""
AKASHA — Router de histórico de atividades
GET /history?type=all|search|archive|download&page=1
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database import count_activity_log, get_activity_log, _HISTORY_PAGE_SIZE

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

_VALID_TYPES = {"all", "search", "archive", "download"}


def _date_label(created_at: str) -> str:
    try:
        dt = datetime.fromisoformat(created_at)
        d = dt.date()
    except ValueError:
        return created_at[:10]
    today = date.today()
    if d == today:
        return "Hoje"
    if d == today - timedelta(days=1):
        return "Ontem"
    return d.strftime("%d/%m/%Y")


def _time_label(created_at: str) -> str:
    try:
        return datetime.fromisoformat(created_at).strftime("%H:%M")
    except ValueError:
        return ""


@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    type: str = "all",
    page: int = 1,
) -> HTMLResponse:
    type_filter = type if type in _VALID_TYPES else "all"
    page = max(1, page)

    rows = await get_activity_log(type_filter, page)
    total = await count_activity_log(type_filter)
    total_pages = max(1, (total + _HISTORY_PAGE_SIZE - 1) // _HISTORY_PAGE_SIZE)

    items = []
    for row in rows:
        id_, rtype, title, url, meta_raw, created_at = row
        try:
            meta = json.loads(meta_raw)
        except Exception:
            meta = {}
        items.append({
            "id":         id_,
            "type":       rtype,
            "title":      title,
            "url":        url,
            "meta":       meta,
            "date_label": _date_label(created_at),
            "time":       _time_label(created_at),
        })

    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "items":       items,
            "type_filter": type_filter,
            "page":        page,
            "total_pages": total_pages,
            "total":       total,
            "active_tab":  "history",
        },
    )
