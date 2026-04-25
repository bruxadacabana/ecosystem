"""
AKASHA — Router de downloads
POST /download          — inicia download
GET  /downloads         — página de histórico
GET  /downloads/active  — fragmento HTMX com downloads ativos
GET  /downloads/progress/{id} — SSE com progresso em tempo real
POST /downloads/{id}/cancel   — cancela download ativo
"""
from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import database
from services import downloader

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

_PAGE_SIZE = 20


class StartDownloadBody(BaseModel):
    url: str
    dest_dir: str = ""


@router.post("/download", response_class=HTMLResponse)
async def start_download(body: StartDownloadBody, request: Request) -> HTMLResponse:
    dl_id = await database.create_download(body.url, dest_dir=body.dest_dir)
    await downloader.start_download(dl_id, body.url, body.dest_dir)
    return HTMLResponse(
        f'<span class="toast-ok">Download #{dl_id} iniciado</span>',
        status_code=202,
    )


@router.get("/downloads", response_class=HTMLResponse)
async def downloads_page(request: Request, page: int = 1) -> HTMLResponse:
    total = await database.count_downloads()
    rows = await database.list_downloads(page=page, page_size=_PAGE_SIZE)
    active = await database.get_active_downloads()
    total_pages = max(1, math.ceil(total / _PAGE_SIZE))
    return templates.TemplateResponse(
        request,
        "downloads.html",
        {
            "active_tab": "downloads",
            "downloads": [_row_to_dict(r) for r in rows],
            "active_downloads": [_row_to_dict(r) for r in active],
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@router.get("/downloads/active", response_class=HTMLResponse)
async def downloads_active_fragment(request: Request) -> HTMLResponse:
    active = await database.get_active_downloads()
    return templates.TemplateResponse(
        request,
        "_downloads_active.html",
        {"active_downloads": [_row_to_dict(r) for r in active]},
    )


@router.get("/downloads/progress/{download_id}")
async def download_progress_sse(download_id: int) -> StreamingResponse:
    return StreamingResponse(
        _sse_generator(download_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/downloads/{download_id}/cancel", response_class=HTMLResponse)
async def cancel_download(download_id: int) -> HTMLResponse:
    cancelled = await downloader.cancel_download(download_id)
    if cancelled:
        return HTMLResponse('<span class="toast-ok">Download cancelado</span>')
    return HTMLResponse('<span class="toast-err">Download não está ativo</span>', status_code=400)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: tuple) -> dict:
    (dl_id, url, filename, dest_dir, size_bytes, downloaded_bytes,
     status, started_at, finished_at, error_msg, created_at) = row
    pct = 0
    if size_bytes and size_bytes > 0:
        pct = min(100, round(downloaded_bytes * 100 / size_bytes))
    return {
        "id": dl_id,
        "url": url,
        "filename": filename or url.split("/")[-1] or url,
        "dest_dir": dest_dir,
        "size_bytes": size_bytes,
        "downloaded_bytes": downloaded_bytes,
        "status": status,
        "pct": pct,
        "started_at": started_at,
        "finished_at": finished_at,
        "error_msg": error_msg or "",
        "created_at": created_at,
        "size_fmt": _fmt_bytes(size_bytes),
        "downloaded_fmt": _fmt_bytes(downloaded_bytes),
    }


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


async def _sse_generator(download_id: int):
    """Emite eventos SSE com fragmento HTML de progresso enquanto o download está ativo."""
    last_pct = -1
    while True:
        row = await database.get_download(download_id)
        if row is None:
            yield "event: done\ndata: not_found\n\n"
            return

        d = _row_to_dict(row)
        pct = d["pct"]

        if pct != last_pct or d["status"] in ("done", "error"):
            html = _progress_html(d)
            yield f"event: progress\ndata: {html}\n\n"
            last_pct = pct

        if d["status"] in ("done", "error"):
            yield "event: done\ndata: finished\n\n"
            return

        await asyncio.sleep(0.6)


def _progress_html(d: dict) -> str:
    if d["status"] == "done":
        return (
            f'<div class="dl-progress dl-done">'
            f'&#10003; Concluído — {d["filename"]}'
            f'</div>'
        )
    if d["status"] == "error":
        msg = d["error_msg"] or "erro desconhecido"
        return (
            f'<div class="dl-progress dl-error">'
            f'&#10007; {msg}'
            f'</div>'
        )
    pct = d["pct"]
    label = f'{d["downloaded_fmt"]} / {d["size_fmt"]} ({pct}%)'
    return (
        f'<div class="dl-progress">'
        f'<div class="dl-progress-track">'
        f'<div class="dl-progress-fill" style="width:{pct}%"></div>'
        f'</div>'
        f'<span class="dl-progress-label">{label}</span>'
        f'</div>'
    )
