"""
Testes para services/wiki_card.py.

Cobre:
  - detect_lang: PT diacríticos → 'pt'; palavras PT → 'pt'; texto EN → 'en'
  - get_wiki_card: API retorna JSON válido → card parseado
  - get_wiki_card: API retorna 404 → None
  - get_wiki_card: extract vazio → None
  - get_wiki_card: cache HIT → não faz request HTTP
  - get_wiki_card: exception de rede → None (não propaga)
"""
from __future__ import annotations

import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# detect_lang
# ---------------------------------------------------------------------------

def test_detect_lang_pt_diacritics():
    from services.wiki_card import detect_lang
    assert detect_lang("o que é inteligência artificial") == "pt"


def test_detect_lang_pt_words():
    from services.wiki_card import detect_lang
    assert detect_lang("como funciona machine learning") == "pt"


def test_detect_lang_en_plain():
    from services.wiki_card import detect_lang
    assert detect_lang("machine learning") == "en"


def test_detect_lang_en_caps():
    from services.wiki_card import detect_lang
    assert detect_lang("Python programming language") == "en"


# ---------------------------------------------------------------------------
# get_wiki_card — via mock httpx
# ---------------------------------------------------------------------------

def _make_resp(status_code: int, body: dict | None = None):
    import httpx
    content = json.dumps(body or {}).encode()
    request = httpx.Request("GET", "https://pt.wikipedia.org/api/rest_v1/page/summary/Test")
    return httpx.Response(status_code, content=content, request=request)


@pytest.mark.anyio
async def test_get_wiki_card_parses_json(tmp_path, monkeypatch):
    """API retorna JSON completo → card com todos os campos."""
    import services.wiki_card as _wk
    monkeypatch.setattr(_wk, "DB_PATH", tmp_path / "akasha.db")

    payload = {
        "title": "Python (linguagem de programação)",
        "extract": "Python é uma linguagem de programação.",
        "thumbnail": {"source": "https://upload.wikimedia.org/test.png", "width": 100, "height": 100},
        "content_urls": {"desktop": {"page": "https://pt.wikipedia.org/wiki/Python"}},
    }
    mock_resp = _make_resp(200, payload)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    import httpx
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        card = await _wk.get_wiki_card("Python linguagem programação")

    assert card is not None
    assert card["title"]   == "Python (linguagem de programação)"
    assert "Python" in card["extract"]
    assert card["thumbnail_url"] == "https://upload.wikimedia.org/test.png"
    assert "pt.wikipedia.org" in card["page_url"]


@pytest.mark.anyio
async def test_get_wiki_card_404_returns_none(tmp_path, monkeypatch):
    """API 404 → None (página não existe)."""
    import services.wiki_card as _wk
    monkeypatch.setattr(_wk, "DB_PATH", tmp_path / "akasha.db")

    import httpx
    request = httpx.Request("GET", "https://pt.wikipedia.org/")
    mock_resp = httpx.Response(404, content=b"", request=request)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        result = await _wk.get_wiki_card("xyzzy nonexistent page abc")

    assert result is None


@pytest.mark.anyio
async def test_get_wiki_card_empty_extract_returns_none(tmp_path, monkeypatch):
    """API retorna extract vazio → None."""
    import services.wiki_card as _wk
    monkeypatch.setattr(_wk, "DB_PATH", tmp_path / "akasha.db")

    payload = {
        "title": "Something",
        "extract": "",
        "content_urls": {"desktop": {"page": "https://pt.wikipedia.org/wiki/Something"}},
    }
    mock_resp = _make_resp(200, payload)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    import httpx
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        result = await _wk.get_wiki_card("ambiguous query")

    assert result is None


@pytest.mark.anyio
async def test_get_wiki_card_network_error_returns_none(tmp_path, monkeypatch):
    """Exception de rede → None, sem propagar."""
    import services.wiki_card as _wk
    monkeypatch.setattr(_wk, "DB_PATH", tmp_path / "akasha.db")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=ConnectionError("timeout"))

    import httpx
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        result = await _wk.get_wiki_card("machine learning")

    assert result is None


@pytest.mark.anyio
async def test_get_wiki_card_cache_hit_skips_request(tmp_path, monkeypatch):
    """Cache HIT → retorna dado do cache, não faz request HTTP."""
    import services.wiki_card as _wk
    monkeypatch.setattr(_wk, "DB_PATH", tmp_path / "akasha.db")

    cached_data = {
        "title": "Cached Title",
        "extract": "Cached extract.",
        "thumbnail_url": None,
        "page_url": "https://pt.wikipedia.org/wiki/Cached",
        "lang": "pt",
    }

    async def _fake_get_cache(qhash):
        return cached_data

    monkeypatch.setattr(_wk, "_get_cache", _fake_get_cache)

    http_called: list[bool] = []

    import httpx
    original_client = httpx.AsyncClient

    class _FailClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, *a, **kw):
            http_called.append(True)
            raise AssertionError("HTTP should not be called on cache HIT")

    with patch.object(httpx, "AsyncClient", _FailClient):
        result = await _wk.get_wiki_card("machine learning")

    assert result == cached_data
    assert http_called == []


@pytest.mark.anyio
async def test_get_wiki_card_writes_to_cache(tmp_path, monkeypatch):
    """Após busca bem-sucedida, dado é escrito no cache."""
    import services.wiki_card as _wk
    monkeypatch.setattr(_wk, "DB_PATH", tmp_path / "akasha.db")

    payload = {
        "title": "Test",
        "extract": "Test extract text here.",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Test"}},
    }
    mock_resp = _make_resp(200, payload)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    written: list[dict] = []

    async def _fake_set_cache(qhash, data):
        written.append(data)

    monkeypatch.setattr(_wk, "_set_cache", _fake_set_cache)

    import httpx
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        await _wk.get_wiki_card("test query")

    assert len(written) == 1
    assert written[0]["title"] == "Test"
