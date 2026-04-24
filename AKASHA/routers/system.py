"""
AKASHA — Controles do servidor
POST /shutdown: encerra o processo uvicorn com SIGTERM.
GET  /open-file: abre arquivo local com o app padrão do OS.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Query
from fastapi.responses import Response

router = APIRouter()
_log = logging.getLogger(__name__)


@router.post("/shutdown")
async def shutdown() -> Response:
    """Encerra o AKASHA graciosamente após enviar a resposta."""
    async def _do_shutdown() -> None:
        await asyncio.sleep(0.4)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_do_shutdown())
    return Response(content="ok", status_code=200)


@router.get("/open-file")
async def open_file(url: str = Query(...)) -> Response:
    """Abre um arquivo local com o aplicativo padrão do OS.

    Recebe a URL file:// gerada pelo local_search e usa o app padrão do sistema
    para abrir o arquivo (Explorer no Windows, xdg-open no Linux).
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme != "file":
            return Response(content="URL inválida (não é file://)", status_code=400)
        # Path.from_uri() disponível em Python 3.13+; fallback manual para compatibilidade
        raw = unquote(parsed.path)
        if sys.platform == "win32" and raw.startswith("/"):
            raw = raw[1:]  # /D:/path → D:/path
        path = Path(raw)
        if not path.exists():
            return Response(content="Arquivo não encontrado", status_code=404)
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return Response(content="ok", status_code=200)
    except Exception as exc:
        _log.error("open-file falhou: %s", exc)
        return Response(content=str(exc), status_code=500)
