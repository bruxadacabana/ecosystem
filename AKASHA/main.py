"""
AKASHA — Ponto de entrada
FastAPI app + lifespan: inicializa DB e registra no ecossistema.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import database
from routers import search as search_router
from routers import library as library_router
from routers import system as system_router
from routers import domains as domains_router
from routers import crawler as crawler_router
from services.local_search import index_local_files
from services.library import check_overdue, scrape_and_store
from services.crawler import crawl_pending_sites

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background: monitoramento de URLs da biblioteca
# ---------------------------------------------------------------------------

async def _monitor_library() -> None:
    """Acorda a cada hora: re-scrape URLs vencidas + crawla sites pendentes."""
    while True:
        await asyncio.sleep(3600)
        try:
            overdue = await check_overdue()
        except Exception as exc:
            _log.warning("library monitor: erro ao listar vencidas: %s", exc)
            overdue = []
        for entry in overdue:
            try:
                await scrape_and_store(entry.id)
            except Exception as exc:
                _log.warning("library monitor: erro ao re-scrape %s: %s", entry.url, exc)
        try:
            await crawl_pending_sites()
        except Exception as exc:
            _log.warning("library monitor: erro ao crawlar sites pendentes: %s", exc)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.init_db()
    config.register_akasha()
    await index_local_files()
    asyncio.get_event_loop().create_task(_monitor_library())
    yield
    # Shutdown — nada a liberar por enquanto

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AKASHA",
    description="Buscador pessoal local do ecossistema",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
)

_BASE_DIR = Path(__file__).parent

app.mount("/static", StaticFiles(directory=_BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

app.include_router(search_router.router)
app.include_router(library_router.router)
app.include_router(system_router.router)
app.include_router(domains_router.router)
app.include_router(crawler_router.router)

# ---------------------------------------------------------------------------
# Rotas principais (Fase 1 — estrutura)
# As rotas de busca, downloads e torrents serão adicionadas nas próximas fases.
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    recent = await database.recent_searches()
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "web_results": [],
            "local_results": [],
            "query": "",
            "sources": "all",
            "recent": recent,
            "error": None,
            "active_tab": "search",
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "AKASHA", "port": str(config.AKASHA_PORT)}


# ---------------------------------------------------------------------------
# Entrypoint direto (uv run main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.AKASHA_PORT,
        reload=False,
    )
