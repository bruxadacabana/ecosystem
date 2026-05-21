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

import database
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

router = APIRouter()
_log = logging.getLogger(__name__)
_BASE_DIR = Path(__file__).parent.parent
_templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

# ---------------------------------------------------------------------------
# Estado de re-análise em memória
# ---------------------------------------------------------------------------
_reanalyze_state: dict = {"running": False, "total": 0, "done": 0, "errors": 0}


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
        asyncio.create_task(database.record_doc_access(url))
        return Response(content="ok", status_code=200)
    except asyncio.TimeoutError:
        return Response(content="ok", status_code=200)
    except Exception as exc:
        _log.error("open-file falhou: %s", exc)
        return Response(content=str(exc), status_code=500)


@router.get("/coread", response_class=HTMLResponse)
async def coread(request: Request, url: str = Query(...)) -> HTMLResponse:
    """HTMX fragment: documentos lidos na mesma sessão de pesquisa que url."""
    results = await database.get_coread_urls(url)
    return _templates.TemplateResponse(request, "_coread.html", {"results": results, "doc_url": url})


@router.get("/related", response_class=HTMLResponse)
async def related(request: Request, url: str = Query(...)) -> HTMLResponse:
    """HTMX fragment: documentos relacionados por conteúdo (TF/FTS5) ao url dado."""
    from services.local_search import find_related
    results = await find_related(url)
    return _templates.TemplateResponse(request, "_related.html", {"results": results, "doc_url": url})


def _file_url_to_path(url: str) -> str | None:
    """Converte file:// URI para caminho de filesystem. Retorna None se não for file://."""
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    raw = unquote(parsed.path)
    if sys.platform == "win32" and raw.startswith("/"):
        raw = raw[1:]
    return raw


@router.get("/citations", response_class=HTMLResponse)
async def citations(request: Request, url: str = Query(...)) -> HTMLResponse:
    """HTMX fragment: documentos do arquivo que citam os mesmos trabalhos (bibliographic coupling)."""
    path = _file_url_to_path(url)
    if not path:
        results: list = []
    else:
        raw = await database.get_coupled_docs(path)
        results = [(Path(p).as_uri(), title, shared) for p, title, shared in raw]
    return _templates.TemplateResponse(request, "_citations.html", {"results": results, "doc_url": url})


@router.get("/more-from-source", response_class=HTMLResponse)
async def more_from_source(request: Request, url: str = Query(...)) -> HTMLResponse:
    """HTMX fragment: outros documentos arquivados do mesmo domínio."""
    path = _file_url_to_path(url)
    if not path:
        results_mfs: list = []
    else:
        raw = await database.get_more_from_source(path)
        results_mfs = [(Path(p).as_uri(), title) for p, title in raw]
    return _templates.TemplateResponse(
        request, "_more_from_source.html", {"results": results_mfs, "doc_url": url}
    )


@router.post("/reanalyze")
async def reanalyze_all() -> JSONResponse:
    """Dispara re-análise (appraisal + reflexão) de todos os registros de page_knowledge.

    Roda como background task; retorna imediatamente com total de entradas.
    Use GET /reanalyze/status para acompanhar progresso.
    Idempotente: se já estiver rodando, retorna o estado atual sem iniciar nova task.
    """
    global _reanalyze_state
    if _reanalyze_state["running"]:
        return JSONResponse({"status": "already_running", **_reanalyze_state})

    entries = await database.get_all_page_knowledge()
    if not entries:
        return JSONResponse({"status": "ok", "total": 0, "done": 0, "errors": 0})

    _reanalyze_state = {"running": True, "total": len(entries), "done": 0, "errors": 0}

    async def _run() -> None:
        global _reanalyze_state
        from services.knowledge_worker import (
            _record_doc_appraisal,
            _event_reflection,
        )
        for entry in entries:
            try:
                await _record_doc_appraisal(entry["topics"], entry["url"])
                await _event_reflection(entry["title"], "", entry["topics"])
            except Exception as exc:
                _log.debug("reanalyze: erro em %s — %s", entry["url"][:80], exc)
                _reanalyze_state["errors"] += 1
            _reanalyze_state["done"] += 1
        _reanalyze_state["running"] = False
        _log.info(
            "reanalyze: concluído — %d/%d entradas, %d erros",
            _reanalyze_state["done"], _reanalyze_state["total"], _reanalyze_state["errors"],
        )

    asyncio.create_task(_run())
    return JSONResponse({"status": "started", "total": len(entries)})


@router.get("/reanalyze/status")
async def reanalyze_status() -> JSONResponse:
    """Retorna progresso atual da re-análise."""
    return JSONResponse(_reanalyze_state)


@router.get("/system/logs")
async def get_logs(n: int = Query(default=100, ge=1, le=500)) -> JSONResponse:
    """Retorna as últimas n linhas de log do AKASHA (buffer em memória).

    Usado pelo HUB para exibir logs em tempo real no monitor.
    """
    from services.log_buffer import get_lines
    return JSONResponse({"lines": get_lines(n)})


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
