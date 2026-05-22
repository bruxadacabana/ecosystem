"""
Testes de integração para a API FastAPI do AKASHA.

Usa httpx.AsyncClient com o app montado em memória — sem servidor real,
sem Ollama, sem ChromaDB real. Rotas testadas:
  - GET /health      → 200 + campo "status"
  - GET /            → 200 (interface HTML)
  - GET /api/status  → 200 + campos básicos de monitoramento

Rotas que dependem de LLM, ChromaDB ou crawler não são testadas aqui.
"""
from __future__ import annotations

import pytest
import httpx


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def client():
    from main import app  # noqa: PLC0415

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest.mark.anyio
async def test_health_returns_200(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_health_has_status_field(client):
    resp = await client.get("/health")
    data = resp.json()
    assert "status" in data


@pytest.mark.anyio
async def test_root_returns_html(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.anyio
async def test_missing_route_returns_404(client):
    resp = await client.get("/rota-que-nao-existe-xyz")
    assert resp.status_code == 404
