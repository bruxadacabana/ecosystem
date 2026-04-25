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
            proc = await asyncio.create_subprocess_exec("open", str(path))
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        else:
            err = await _xdg_open(str(path))
            if err:
                return Response(content=err, status_code=500)
        return Response(content="ok", status_code=200)
    except asyncio.TimeoutError:
        return Response(content="ok", status_code=200)
    except Exception as exc:
        _log.error("open-file falhou: %s", exc)
        return Response(content=str(exc), status_code=500)


async def _xdg_open(path: str) -> str | None:
    """Tenta abrir um arquivo com xdg-open; fallback para gio open.
    Retorna mensagem de erro se ambos falharem, ou None se bem-sucedido.
    """
    for cmd in (["xdg-open", path], ["gio", "open", path]):
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            except asyncio.TimeoutError:
                return None  # processo lançou o app e não retornou — considerado OK
            if proc.returncode == 0:
                return None
            last_err = stderr.decode(errors="replace").strip()
        except FileNotFoundError:
            last_err = f"{cmd[0]}: comando não encontrado"
    return last_err or "xdg-open e gio open falharam sem mensagem de erro"
