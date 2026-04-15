"""
AKASHA — Ponto de entrada
FastAPI app + lifespan: inicializa DB e registra no ecossistema.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import database
from routers import search as search_router
from services.local_search import index_local_files

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.init_db()
    config.register_akasha()
    await index_local_files()
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

# ---------------------------------------------------------------------------
# Rotas principais (Fase 1 — estrutura)
# As rotas de busca, downloads e torrents serão adicionadas nas próximas fases.
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    recent = await database.recent_searches()
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "results": [],
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
