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
from routers import system as system_router
from routers import domains as domains_router
from routers import favorites as favorites_router
from routers import crawler as crawler_router
from routers import watch_later as watch_later_router
from routers import kosmos_bridge as kosmos_bridge_router
from routers import history as history_router
from routers import papers as papers_router
from services.local_search import index_local_files
from services.crawler import crawl_pending_sites

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background: monitoramento de URLs da biblioteca
# ---------------------------------------------------------------------------

async def _monitor_crawler() -> None:
    """Acorda a cada hora: crawla sites pendentes e limpa search_cache > 24h."""
    while True:
        await asyncio.sleep(3600)
        try:
            await crawl_pending_sites()
        except Exception as exc:
            _log.warning("monitor: erro ao crawlar sites pendentes: %s", exc)
        try:
            import aiosqlite
            from config import DB_PATH
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "DELETE FROM search_cache WHERE created_at < datetime('now', '-1 day')"
                )
                await db.commit()
        except Exception as exc:
            _log.warning("monitor: erro ao limpar search_cache: %s", exc)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.init_db()
    config.register_akasha()
    await index_local_files()
    asyncio.get_running_loop().create_task(_monitor_crawler())
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
app.include_router(system_router.router)
app.include_router(domains_router.router)
app.include_router(favorites_router.router)
app.include_router(crawler_router.router)
app.include_router(watch_later_router.router)
app.include_router(kosmos_bridge_router.router)
app.include_router(history_router.router)
app.include_router(papers_router.router)

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
            "web_results":          [],
            "fav_results":          [],
            "local_results":        [],
            "site_results":         [],
            "watch_later_results":  [],
            "has_more_web":         False,
            "query":     "",
            "src_web":    True,
            "src_eco":    True,
            "src_sites":  False,
            "src_papers": False,
            "filetype":   "",
            "has_sites":  False,
            "paper_results": [],
            "recent":     recent,
            "error":      None,
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
