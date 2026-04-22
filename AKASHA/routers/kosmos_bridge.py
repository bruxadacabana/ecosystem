"""
AKASHA — Bridge para o KOSMOS (adicionar fontes)
POST /kosmos/add-source → encaminha para HTTP API local do KOSMOS
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
from fastapi import APIRouter, Form, HTTPException, Response

router = APIRouter()

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _kosmos_base_url() -> str:
    try:
        from ecosystem_client import read_ecosystem
        eco = read_ecosystem()
        port = eco.get("kosmos", {}).get("http_port", 8965)
        return f"http://127.0.0.1:{port}"
    except Exception:
        return "http://127.0.0.1:8965"


@router.post("/kosmos/add-source")
async def kosmos_add_source(
    url:  str = Form(...),
    name: str = Form(""),
) -> Response:
    base = _kosmos_base_url()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{base}/add-source",
                data={"url": url, "name": name or url},
                timeout=5,
            )
            r.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="KOSMOS não está aberto")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"KOSMOS retornou {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return Response(status_code=200)
