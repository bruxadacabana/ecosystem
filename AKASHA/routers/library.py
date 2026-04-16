"""
AKASHA — Router da Biblioteca de URLs
"""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from services.library import (
    LibraryEntry,
    add_url,
    delete_entry,
    get_diffs,
    list_entries,
    scrape_and_store,
    update_entry,
)

router = APIRouter()

_BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@router.get("/library", response_class=HTMLResponse)
async def library_page(
    request: Request,
    tag: str = "",
    lang: str = "",
) -> HTMLResponse:
    entries = await list_entries(tag=tag, lang=lang)

    # Coleta tags e idiomas disponíveis para filtros
    all_tags:  list[str] = sorted({t for e in entries for t in e.tags})
    all_langs: list[str] = sorted({e.language for e in entries if e.language})

    return templates.TemplateResponse(
        "library.html",
        {
            "request":    request,
            "entries":    entries,
            "all_tags":   all_tags,
            "all_langs":  all_langs,
            "filter_tag": tag,
            "filter_lang": lang,
            "active_tab": "library",
        },
    )


@router.post("/library/add")
async def library_add(
    request: Request,
    url:           str = Form(...),
    interval_days: int = Form(7),
    tags:          str = Form(""),
    notes:         str = Form(""),
) -> HTMLResponse:
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    try:
        await add_url(url, interval_days=interval_days, tags=tag_list, notes=notes)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Erro HTTP: {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Falha de rede: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Retorna a lista atualizada para HTMX substituir o conteúdo
    entries   = await list_entries()
    all_tags  = sorted({t for e in entries for t in e.tags})
    all_langs = sorted({e.language for e in entries if e.language})
    return templates.TemplateResponse(
        "library.html",
        {
            "request":     request,
            "entries":     entries,
            "all_tags":    all_tags,
            "all_langs":   all_langs,
            "filter_tag":  "",
            "filter_lang": "",
            "active_tab":  "library",
        },
    )


@router.post("/library/refresh/{entry_id}")
async def library_refresh(entry_id: int) -> Response:
    try:
        await scrape_and_store(entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return Response(status_code=200)


@router.patch("/library/{entry_id}")
async def library_update(
    entry_id:      int,
    notes:         str | None = Form(None),
    tags:          str | None = Form(None),
    interval_days: int | None = Form(None),
) -> Response:
    tag_list = (
        [t.strip() for t in tags.split(",") if t.strip()]
        if tags is not None else None
    )
    await update_entry(entry_id, notes=notes, tags=tag_list, interval_days=interval_days)
    return Response(status_code=200)


@router.delete("/library/{entry_id}")
async def library_delete(entry_id: int) -> Response:
    await delete_entry(entry_id)
    return Response(status_code=200)
