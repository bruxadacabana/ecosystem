"""
AKASHA — Controles do servidor
POST /shutdown: encerra o processo uvicorn com SIGTERM.
"""
from __future__ import annotations

import asyncio
import os
import signal

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()


@router.post("/shutdown")
async def shutdown() -> Response:
    """Encerra o AKASHA graciosamente após enviar a resposta."""
    async def _do_shutdown() -> None:
        await asyncio.sleep(0.4)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_do_shutdown())
    return Response(content="ok", status_code=200)
