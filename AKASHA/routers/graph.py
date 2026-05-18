"""
AKASHA — Mapa de conexões entre tópicos e entidades.

GET  /graph          → renderiza graph.html
GET  /graph/data     → JSON {nodes, edges} para D3.js
GET  /graph/pages    → fragmento HTMX: páginas relacionadas a um tópico
POST /graph/edge/feedback → define feedback (confirmed/dismissed/null) para aresta
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

router = APIRouter(prefix="/graph", tags=["graph"])

_BASE_DIR  = Path(__file__).parent.parent
templates  = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@router.get("", response_class=HTMLResponse)
async def graph_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "graph.html", {"active_tab": "graph"}
    )


@router.get("/data")
async def graph_data(node_limit: int = 80, edge_limit: int = 250) -> dict:
    """Retorna nós e arestas do entity_graph para D3.js."""
    import database as _db
    return await _db.get_graph_data(node_limit=node_limit, edge_limit=edge_limit)


@router.get("/pages", response_class=HTMLResponse)
async def graph_pages(request: Request, topic: str = "") -> HTMLResponse:
    """Fragmento HTMX: lista de páginas relacionadas ao tópico/entidade clicado."""
    if not topic.strip():
        return HTMLResponse("")
    import database as _db
    pages = await _db.get_pages_for_topic(topic.strip())
    return templates.TemplateResponse(
        request, "_graph_pages.html", {"topic": topic, "pages": pages}
    )


class _FeedbackBody(BaseModel):
    a:        str
    b:        str
    feedback: str | None  # "confirmed" | "dismissed" | null


@router.post("/edge/feedback")
async def edge_feedback(body: _FeedbackBody) -> dict:
    """Define feedback para uma aresta do grafo."""
    if body.feedback not in {None, "confirmed", "dismissed"}:
        return {"ok": False, "error": "feedback inválido"}
    import database as _db
    await _db.set_edge_feedback(body.a, body.b, body.feedback)
    return {"ok": True}
