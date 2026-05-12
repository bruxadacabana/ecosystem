"""
AKASHA — Router de highlights
POST /highlights        — cria highlight (W3C TextQuoteSelector)
GET  /highlights?url=   — lista highlights de um documento
DELETE /highlights/{id} — remove highlight
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import database

router = APIRouter(prefix="/highlights", tags=["highlights"])


class HighlightIn(BaseModel):
    url:    str
    exact:  str
    prefix: str = ""
    suffix: str = ""
    note:   str = ""


@router.post("")
async def create_highlight(body: HighlightIn) -> dict:
    if not body.exact.strip():
        raise HTTPException(status_code=422, detail="exact não pode ser vazio")
    hid = await database.add_highlight(
        url=body.url,
        exact=body.exact,
        prefix=body.prefix,
        suffix=body.suffix,
        note=body.note,
    )
    return {"id": hid}


@router.get("")
async def list_highlights(url: str = "") -> list[dict]:
    if not url:
        raise HTTPException(status_code=422, detail="url obrigatória")
    rows = await database.get_highlights_for_url(url)
    return [
        {"id": r[0], "exact": r[1], "prefix": r[2], "suffix": r[3], "note": r[4], "created_at": r[5]}
        for r in rows
    ]


@router.delete("/{highlight_id}")
async def delete_highlight(highlight_id: int) -> dict:
    await database.delete_highlight(highlight_id)
    return {"ok": True}
