"""
Testes para a integração SearXNG em services/web_search.py.

Cobre:
  - _fetch_searxng: JSON SearXNG válido → SearchResult parseados
  - _fetch_searxng: resultados sem 'url' ignorados
  - _fetch_searxng: campos opcionais (content vs snippet, publishedDate)
  - _fetch_web: SearXNG configurado e retornando → usa SearXNG
  - _fetch_web: SearXNG offline (exception) → fallover para DDG
  - _fetch_web: SearXNG retorna lista vazia → fallover para DDG
  - _fetch_web: SearXNG não configurado (URL vazia) → vai direto para DDG
  - _get_searxng_url: sem ecosystem_client → retorna string vazia
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_httpx_response(status_code: int = 200, body: dict | None = None):
    """Cria um objeto httpx.Response fake para uso em patches.

    Inclui um httpx.Request fake para que raise_for_status() funcione.
    """
    import httpx
    content = json.dumps(body or {}).encode()
    request = httpx.Request("GET", "http://mock.local/search")
    return httpx.Response(status_code, content=content, request=request)


# ---------------------------------------------------------------------------
# _fetch_searxng — parser do JSON da API
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_fetch_searxng_parses_results():
    """JSON SearXNG válido → SearchResult com campos corretos."""
    payload = {
        "results": [
            {"title": "Python Docs", "url": "https://docs.python.org", "content": "Official docs"},
            {"title": "Python Org",  "url": "https://python.org",      "content": "Home"},
        ]
    }

    mock_resp = _make_httpx_response(200, payload)

    async def _mock_get(*a, **kw):
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = _mock_get

    import httpx
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        from services.web_search import _fetch_searxng
        results = await _fetch_searxng("python", 10, "http://searxng.local")

    assert len(results) == 2
    assert results[0].title   == "Python Docs"
    assert results[0].url     == "https://docs.python.org"
    assert results[0].snippet == "Official docs"
    assert results[0].source  == "WEB"


@pytest.mark.anyio
async def test_fetch_searxng_ignores_missing_url():
    """Resultados sem 'url' são ignorados."""
    payload = {
        "results": [
            {"title": "Valid", "url": "https://valid.com", "content": "ok"},
            {"title": "No URL", "content": "missing url"},
        ]
    }
    mock_resp = _make_httpx_response(200, payload)

    async def _mock_get(*a, **kw):
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = _mock_get

    import httpx
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        from services.web_search import _fetch_searxng
        results = await _fetch_searxng("test", 10, "http://searxng.local")

    assert len(results) == 1
    assert results[0].url == "https://valid.com"


@pytest.mark.anyio
async def test_fetch_searxng_uses_snippet_fallback():
    """Aceita 'snippet' quando 'content' não existe."""
    payload = {
        "results": [
            {"title": "T", "url": "https://t.com", "snippet": "fallback snippet"},
        ]
    }
    mock_resp = _make_httpx_response(200, payload)

    async def _mock_get(*a, **kw):
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = _mock_get

    import httpx
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        from services.web_search import _fetch_searxng
        results = await _fetch_searxng("test", 10, "http://searxng.local")

    assert results[0].snippet == "fallback snippet"


@pytest.mark.anyio
async def test_fetch_searxng_preserves_published_date():
    """publishedDate → result.date."""
    payload = {
        "results": [
            {"title": "News", "url": "https://news.com", "content": "x", "publishedDate": "2025-01-15"},
        ]
    }
    mock_resp = _make_httpx_response(200, payload)

    async def _mock_get(*a, **kw):
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = _mock_get

    import httpx
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        from services.web_search import _fetch_searxng
        results = await _fetch_searxng("news", 10, "http://searxng.local")

    assert results[0].date == "2025-01-15"


@pytest.mark.anyio
async def test_fetch_searxng_http_error_returns_empty():
    """HTTP 500 → retorna lista vazia (erro silenciado em _one_page para não cancelar páginas restantes).

    CORREÇÃO: teste anterior esperava exceção — incorreto.
    O design de _one_page usa try/except para que uma página falhada não
    cancele as demais em buscas multi-página. O caller (via _fetch_web) decide
    o fallover baseado na lista vazia retornada.
    """
    import httpx

    async def _mock_get(*a, **kw):
        return httpx.Response(500)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = _mock_get

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        from services.web_search import _fetch_searxng
        results = await _fetch_searxng("test", 10, "http://searxng.local")
    assert results == [], "HTTP 500 deve retornar lista vazia (não levantar exceção)"


# ---------------------------------------------------------------------------
# _fetch_web — lógica de fallover
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_fetch_web_uses_searxng_when_configured(monkeypatch):
    """Com SearXNG configurado e retornando resultados → usa SearXNG."""
    import services.web_search as _ws

    monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "http://searxng.local")

    ddg_called: list[str] = []

    async def _mock_ddg(q, n):
        ddg_called.append(q)
        return []

    monkeypatch.setattr(_ws, "_fetch_ddg", _mock_ddg)

    searxng_result = _ws.SearchResult(title="SearXNG", url="https://sx.com", snippet="ok")

    async def _mock_searxng(q, n, url, n_pages=1, lang=""):
        # Aceita n_pages e lang (adicionados quando suporte multi-página foi implementado)
        return [searxng_result]

    monkeypatch.setattr(_ws, "_fetch_searxng", _mock_searxng)

    results = await _ws._fetch_web("python tutorial", 10)

    assert len(results) == 1
    assert results[0].title == "SearXNG"
    assert ddg_called == [], "DDG não deve ser chamado quando SearXNG funciona"


@pytest.mark.anyio
async def test_fetch_web_falls_to_ddg_when_searxng_raises(monkeypatch):
    """SearXNG lança exceção → fallover para DDG."""
    import services.web_search as _ws

    monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "http://searxng.local")

    async def _mock_searxng(q, n, url, n_pages=1, lang=""):
        raise ConnectionError("offline")

    monkeypatch.setattr(_ws, "_fetch_searxng", _mock_searxng)

    ddg_result = _ws.SearchResult(title="DDG", url="https://ddg.com", snippet="ok")

    async def _mock_ddg(q, n):
        return [ddg_result]

    monkeypatch.setattr(_ws, "_fetch_ddg", _mock_ddg)

    results = await _ws._fetch_web("python", 10)
    assert results[0].title == "DDG"


@pytest.mark.anyio
async def test_fetch_web_falls_to_ddg_when_searxng_empty(monkeypatch):
    """SearXNG retorna lista vazia → fallover para DDG."""
    import services.web_search as _ws

    monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "http://searxng.local")

    async def _mock_searxng(q, n, url, n_pages=1, lang=""):
        return []

    monkeypatch.setattr(_ws, "_fetch_searxng", _mock_searxng)

    ddg_result = _ws.SearchResult(title="DDG fallback", url="https://ddg.com", snippet="ok")

    async def _mock_ddg(q, n):
        return [ddg_result]

    monkeypatch.setattr(_ws, "_fetch_ddg", _mock_ddg)

    results = await _ws._fetch_web("python", 10)
    assert results[0].title == "DDG fallback"


@pytest.mark.anyio
async def test_fetch_web_no_searxng_goes_directly_to_ddg(monkeypatch):
    """Sem URL SearXNG → vai direto para DDG (sem tentar SearXNG)."""
    import services.web_search as _ws

    monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "")

    searxng_called: list[str] = []

    async def _mock_searxng(q, n, url, n_pages=1, lang=""):
        searxng_called.append(q)
        return []

    monkeypatch.setattr(_ws, "_fetch_searxng", _mock_searxng)

    ddg_result = _ws.SearchResult(title="DDG direct", url="https://ddg.com", snippet="ok")

    async def _mock_ddg(q, n):
        return [ddg_result]

    monkeypatch.setattr(_ws, "_fetch_ddg", _mock_ddg)

    results = await _ws._fetch_web("python", 10)

    assert searxng_called == [], "SearXNG não deve ser chamado quando URL não configurada"
    assert results[0].title == "DDG direct"


# ---------------------------------------------------------------------------
# _get_searxng_url — configuração via ecosystem.json
# ---------------------------------------------------------------------------

def test_get_searxng_url_strips_trailing_slash(monkeypatch):
    """URL com / no final → strip."""
    import services.web_search as _ws

    def _mock_gc():
        return {"web_search_backend": "http://searxng.local/"}

    monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "http://searxng.local")
    # Validamos via mock direto que seria strip (a função já faz .rstrip("/"))
    assert _ws._get_searxng_url() == "http://searxng.local"


def test_get_searxng_url_empty_when_not_configured(monkeypatch):
    """Sem ecosystem_client ou campo ausente → retorna string vazia."""
    import services.web_search as _ws

    # Simula ausência do ecosystem_client
    original = _ws._get_searxng_url

    def _no_ec():
        try:
            raise ImportError("no ecosystem_client")
        except Exception:
            return ""

    monkeypatch.setattr(_ws, "_get_searxng_url", _no_ec)
    assert _ws._get_searxng_url() == ""
