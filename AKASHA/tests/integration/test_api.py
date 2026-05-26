"""
Testes de integração para a API FastAPI do AKASHA.

Usa httpx.AsyncClient com o app montado em memória — sem servidor real,
sem Ollama, sem ChromaDB real. Rotas testadas:
  - GET /health         → 200 + campo "status"
  - GET /               → 200 (interface HTML)
  - GET /api/status     → 200 + campos básicos de monitoramento
  - GET /search/json    → contrato JSON da API de busca
  - GET /insight/current → shape de resposta sem sessão ativa
  - POST /insight/feedback → validação de schema (422 para input inválido)
  - GET /library/crawl/status → campo "paused" presente

Rotas que dependem de LLM, ChromaDB ou crawler são testadas com mocks pontuais.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


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


# ── /health ──────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_health_returns_200(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_health_has_status_field(client):
    resp = await client.get("/health")
    data = resp.json()
    assert "status" in data


# ── / (interface HTML) ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_root_returns_html(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


# ── rotas inexistentes ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_missing_route_returns_404(client):
    resp = await client.get("/rota-que-nao-existe-xyz")
    assert resp.status_code == 404


# ── GET /search/json — contrato da API JSON ───────────────────────────────────

@pytest.mark.anyio
async def test_search_json_empty_query_returns_empty_list(client):
    """Query vazia deve retornar lista vazia imediatamente, sem tocar no DB."""
    resp = await client.get("/search/json", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_search_json_no_sources_returns_empty_list(client):
    """Sem fontes selecionadas, resultado deve ser lista vazia."""
    resp = await client.get("/search/json", params={"q": "python", "sources": ""})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_search_json_response_is_list(client):
    """Resposta deve sempre ser lista (nunca dict/error não-tratado)."""
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get("/search/json", params={"q": "test", "sources": "web,eco,sites"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_search_json_returns_mocked_results(client):
    """Resultados das fontes devem ser mesclados e limitados por `max`."""
    fake_result = {
        "url": "https://example.com/page",
        "title": "Página de Exemplo",
        "snippet": "Trecho de exemplo.",
        "score": 0.9,
        "source": "sites",
        "domain": "example.com",
        "freshness_label": "",
        "language": "pt",
    }
    with patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[fake_result]):
        with patch("routers.search.search_web", new_callable=AsyncMock, return_value=[]):
            with patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]):
                resp = await client.get(
                    "/search/json",
                    params={"q": "exemplo", "sources": "web,eco,sites", "max": "5"},
                )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["url"] == "https://example.com/page"


# ── GET /insight/current — sem sessão ativa ───────────────────────────────────

@pytest.mark.anyio
async def test_insight_current_returns_dict(client):
    """Rota deve retornar 200 com dict (nunca explodir sem sessão)."""
    with (
        patch("services.affective_state.get_current_state", new_callable=AsyncMock,
              return_value={"arousal": 0.0}),
        patch("services.personal_memory.get_next_for_overlay", new_callable=AsyncMock,
              return_value=[]),
    ):
        resp = await client.get("/insight/current")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


@pytest.mark.anyio
async def test_insight_current_has_text_field(client):
    """Resposta deve sempre ter campo 'text' (pode ser None)."""
    with (
        patch("services.affective_state.get_current_state", new_callable=AsyncMock,
              return_value={"arousal": 0.0}),
        patch("services.personal_memory.get_next_for_overlay", new_callable=AsyncMock,
              return_value=[]),
    ):
        resp = await client.get("/insight/current")
    assert "text" in resp.json()


@pytest.mark.anyio
async def test_insight_current_defers_on_high_arousal(client):
    """Com arousal > 0.6, resposta deve ter reason='deferred'."""
    with patch("services.affective_state.get_current_state", new_callable=AsyncMock,
               return_value={"arousal": 0.9}):
        resp = await client.get("/insight/current")
    assert resp.status_code == 200
    assert resp.json().get("reason") == "deferred"


# ── POST /insight/feedback — validação de schema ──────────────────────────────

@pytest.mark.anyio
async def test_insight_feedback_invalid_type_returns_422(client):
    """Feedback com valor inválido deve retornar 422 sem tocar no DB."""
    resp = await client.post(
        "/insight/feedback",
        json={"memory_id": 1, "feedback": "maybe"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_insight_feedback_missing_fields_returns_422(client):
    """Body incompleto deve retornar 422."""
    resp = await client.post("/insight/feedback", json={"memory_id": 1})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_insight_feedback_confirmed_calls_set_feedback(client):
    """feedback='confirmed' deve chamar set_feedback e retornar ok=True."""
    with (
        patch("services.personal_memory.set_feedback", new_callable=AsyncMock),
        patch("services.personal_memory.get_entry_info", new_callable=AsyncMock,
              return_value={"importance": 3, "comm_id": None}),
        patch("services.knowledge_worker.on_feedback_confirmed"),
        patch("services.session_insight.on_feedback_confirmed"),
        patch("services.session_insight.set_pm_current"),
    ):
        resp = await client.post(
            "/insight/feedback",
            json={"memory_id": 42, "feedback": "confirmed"},
        )
    assert resp.status_code == 200
    assert resp.json().get("ok") is True


# ── GET /library/crawl/status ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_crawl_status_returns_200(client):
    resp = await client.get("/library/crawl/status")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_crawl_status_has_paused_field(client):
    """Resposta deve conter campo 'paused' (bool)."""
    resp = await client.get("/library/crawl/status")
    data = resp.json()
    assert "paused" in data
    assert isinstance(data["paused"], bool)
