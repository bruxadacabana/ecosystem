"""Testes para headers X-App/X-Priority e Retry-After em knowledge_worker.py."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Garante que o diretório do projeto está no path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Importação isolada — evita carregar dependências do AKASHA que não existem
# no ambiente de testes (SQLite, ChromaDB, etc.)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_imports(monkeypatch):
    """Substitui importações problemáticas por mocks antes de importar o módulo."""
    import types

    fake_eco = types.ModuleType("ecosystem_client")
    fake_eco.get_inference_url = lambda: "http://127.0.0.1:7072"  # type: ignore
    fake_eco.get_active_profile = lambda: {"models": {"llm_query": "test-model"}}  # type: ignore
    monkeypatch.setitem(sys.modules, "ecosystem_client", fake_eco)

    for mod in ("database", "config", "services.persona", "services.affective_state",
                "services.local_search"):
        monkeypatch.setitem(sys.modules, mod, types.ModuleType(mod))


# ---------------------------------------------------------------------------
# Helper de resposta mock
# ---------------------------------------------------------------------------

def _make_response(status: int, body: dict | None = None):
    """Cria um mock de httpx.Response."""
    resp = MagicMock()
    resp.status_code = status
    body = body or {}

    def json_fn():
        return body

    resp.json = json_fn
    resp.text = str(body)

    if status >= 400:
        import httpx
        req = MagicMock(spec=httpx.Request)
        req.url = "http://127.0.0.1:7072/v1/chat/completions"
        resp.request = req
        err = httpx.HTTPStatusError(f"HTTP {status}", request=req, response=resp)
        resp.raise_for_status = MagicMock(side_effect=err)
    else:
        resp.raise_for_status = MagicMock()

    return resp


# ---------------------------------------------------------------------------
# Testes de headers X-App e X-Priority
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logos_llm_post_sends_xapp_header():
    """_logos_llm_post deve incluir X-App: akasha em toda chamada."""
    from services import knowledge_worker as kw

    captured_headers: dict = {}

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        nonlocal captured_headers
        captured_headers = dict(headers or {})
        return _make_response(200, {"choices": [{"message": {"content": "ok"}}]})

    mock_client = AsyncMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.knowledge_worker.httpx.AsyncClient", return_value=mock_client):
        result = await kw._logos_llm_post("http://127.0.0.1:7072/v1/chat/completions", {})

    assert captured_headers.get("X-App") == "akasha", \
        f"X-App deve ser 'akasha', recebeu: {captured_headers}"


@pytest.mark.asyncio
async def test_logos_llm_post_sends_xpriority_3_header():
    """_logos_llm_post deve incluir X-Priority: 3 (análise background)."""
    from services import knowledge_worker as kw

    captured_headers: dict = {}

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        nonlocal captured_headers
        captured_headers = dict(headers or {})
        return _make_response(200, {"choices": [{"message": {"content": "ok"}}]})

    mock_client = AsyncMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.knowledge_worker.httpx.AsyncClient", return_value=mock_client):
        await kw._logos_llm_post("http://127.0.0.1:7072/v1/chat/completions", {})

    assert captured_headers.get("X-Priority") == "3", \
        f"X-Priority deve ser '3', recebeu: {captured_headers}"


@pytest.mark.asyncio
async def test_logos_llm_post_returns_json_on_success():
    """Resposta 200 deve retornar o JSON parseado."""
    from services import knowledge_worker as kw

    expected = {"choices": [{"message": {"content": "resultado"}}]}

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        return _make_response(200, expected)

    mock_client = AsyncMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.knowledge_worker.httpx.AsyncClient", return_value=mock_client):
        result = await kw._logos_llm_post("http://x/v1/chat/completions", {})

    assert result == expected


# ---------------------------------------------------------------------------
# Testes de Retry-After (Passo 13)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_knowledge_worker_respects_retry_after_30s():
    """Em 429 com retry_after=30, deve dormir 30s e tentar novamente."""
    from services import knowledge_worker as kw

    call_count = 0
    slept_values: list[float] = []

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_response(429, {"error": "ocupado", "retry_after": 30})
        return _make_response(200, {"choices": [{"message": {"content": "ok"}}]})

    mock_client = AsyncMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_sleep(seconds):
        slept_values.append(seconds)

    with patch("services.knowledge_worker.httpx.AsyncClient", return_value=mock_client), \
         patch("services.knowledge_worker.asyncio.sleep", side_effect=fake_sleep):
        result = await kw._logos_llm_post("http://x/v1/chat/completions", {}, max_retries=1)

    assert call_count == 2, f"Deve ter feito 2 chamadas (1 retry), fez {call_count}"
    assert 30.0 in slept_values, f"Deve ter dormido 30s (retry_after), dormiu: {slept_values}"
    assert result is not None, "Deve retornar resultado após retry bem-sucedido"


@pytest.mark.asyncio
async def test_knowledge_worker_uses_60s_fallback_on_missing_header():
    """Em 429 sem campo retry_after, deve usar fallback de 60s."""
    from services import knowledge_worker as kw

    call_count = 0
    slept_values: list[float] = []

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Resposta 429 sem retry_after (campo ausente)
            return _make_response(429, {"error": "ocupado"})
        return _make_response(200, {"choices": [{"message": {"content": "ok"}}]})

    mock_client = AsyncMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_sleep(seconds):
        slept_values.append(seconds)

    with patch("services.knowledge_worker.httpx.AsyncClient", return_value=mock_client), \
         patch("services.knowledge_worker.asyncio.sleep", side_effect=fake_sleep):
        result = await kw._logos_llm_post("http://x/v1/chat/completions", {}, max_retries=1)

    assert 60.0 in slept_values, f"Deve usar fallback de 60s quando retry_after ausente, dormiu: {slept_values}"


@pytest.mark.asyncio
async def test_knowledge_worker_uses_60s_fallback_on_invalid_json_body():
    """Em 429 com corpo não-JSON, deve usar fallback de 60s."""
    from services import knowledge_worker as kw

    slept_values: list[float] = []

    call_count = 0

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            resp = MagicMock()
            resp.status_code = 429
            resp.json = MagicMock(side_effect=Exception("not json"))
            import httpx
            req = MagicMock(spec=httpx.Request)
            req.url = url
            resp.request = req
            err = httpx.HTTPStatusError("HTTP 429", request=req, response=resp)
            resp.raise_for_status = MagicMock(side_effect=err)
            return resp
        return _make_response(200, {"choices": [{"message": {"content": "ok"}}]})

    mock_client = AsyncMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_sleep(seconds):
        slept_values.append(seconds)

    with patch("services.knowledge_worker.httpx.AsyncClient", return_value=mock_client), \
         patch("services.knowledge_worker.asyncio.sleep", side_effect=fake_sleep):
        result = await kw._logos_llm_post("http://x/v1/chat/completions", {}, max_retries=1)

    assert 60.0 in slept_values, \
        f"Deve usar fallback de 60s quando corpo não é JSON válido, dormiu: {slept_values}"


@pytest.mark.asyncio
async def test_logos_llm_post_503_respects_retry_after():
    """503 também deve respeitar retry_after (não só 429)."""
    from services import knowledge_worker as kw

    slept_values: list[float] = []
    call_count = 0

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_response(503, {"error": "indisponível", "retry_after": 45})
        return _make_response(200, {"choices": [{"message": {"content": "ok"}}]})

    mock_client = AsyncMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_sleep(seconds):
        slept_values.append(seconds)

    with patch("services.knowledge_worker.httpx.AsyncClient", return_value=mock_client), \
         patch("services.knowledge_worker.asyncio.sleep", side_effect=fake_sleep):
        result = await kw._logos_llm_post("http://x/v1/chat/completions", {}, max_retries=1)

    assert 45.0 in slept_values, f"503 com retry_after=45 deve dormir 45s, dormiu: {slept_values}"
    assert result is not None


@pytest.mark.asyncio
async def test_logos_llm_post_returns_none_after_max_retries():
    """Após esgotar max_retries, deve retornar None."""
    from services import knowledge_worker as kw

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        return _make_response(429, {"retry_after": 1})

    mock_client = AsyncMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_sleep(seconds):
        pass  # não espera de verdade

    with patch("services.knowledge_worker.httpx.AsyncClient", return_value=mock_client), \
         patch("services.knowledge_worker.asyncio.sleep", side_effect=fake_sleep):
        result = await kw._logos_llm_post("http://x/v1/chat/completions", {}, max_retries=1)

    assert result is None, "Deve retornar None após esgotar retries"


@pytest.mark.asyncio
async def test_logos_llm_post_connect_error_returns_none():
    """Erro de conexão (LOGOS offline) deve retornar None sem retry."""
    import httpx
    from services import knowledge_worker as kw

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        raise httpx.ConnectError("connection refused")

    mock_client = AsyncMock()
    mock_client.post = fake_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("services.knowledge_worker.httpx.AsyncClient", return_value=mock_client):
        result = await kw._logos_llm_post("http://x/v1/chat/completions", {})

    assert result is None


# ---------------------------------------------------------------------------
# Testes de headers em local_search.py
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_local_search_expand_query_sends_xapp_header():
    """_expand_query_llm em local_search.py deve incluir X-App e X-Priority."""
    # Este teste verifica que os headers foram adicionados ao código
    import ast, inspect

    local_search_path = Path(__file__).parent.parent / "services" / "local_search.py"
    source = local_search_path.read_text()

    # Verifica que X-App está presente nas chamadas de POST
    assert '"X-App": "akasha"' in source or "'X-App': 'akasha'" in source, \
        "local_search.py deve incluir header X-App: akasha nas chamadas de inferência"

    assert '"X-Priority": "3"' in source or "'X-Priority': '3'" in source, \
        "local_search.py deve incluir header X-Priority: 3 nas chamadas de inferência"
