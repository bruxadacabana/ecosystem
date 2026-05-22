"""
Testes para services/wiki_card.py.

Cobre:
  - detect_lang: PT diacríticos → 'pt'; palavras PT → 'pt'; texto EN → 'en'
  - get_wiki_card: API retorna JSON válido → card parseado
  - get_wiki_card: API retorna 404 → None
  - get_wiki_card: extract vazio → None
  - get_wiki_card: cache HIT → não faz request HTTP
  - get_wiki_card: exception de rede → None (não propaga)
  - _fetch_cited_sources: MediaWiki retorna extlinks → lista de URLs
  - _fetch_cited_sources: exception → lista vazia
  - get_wiki_card: sources incluídas em cited_sources
  - get_wiki_card: sources timeout → card presente com cited_sources=[]
  - get_wiki_card: cache HIT já inclui cited_sources → retorna sem novo request
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


# ---------------------------------------------------------------------------
# _fetch_cited_sources
# ---------------------------------------------------------------------------

def _make_mediawiki_resp(urls: list[str]) -> object:
    """Cria resposta fake da MediaWiki Action API com extlinks."""
    import httpx
    payload = {
        "query": {
            "pages": {
                "12345": {
                    "extlinks": [{"*": u} for u in urls],
                }
            }
        }
    }
    request = httpx.Request("GET", "https://pt.wikipedia.org/w/api.php")
    return httpx.Response(200, content=json.dumps(payload).encode(), request=request)


@pytest.mark.anyio
async def test_fetch_cited_sources_returns_urls():
    """MediaWiki retorna extlinks → lista de URLs."""
    import httpx
    import services.wiki_card as _wk

    urls = ["https://doi.org/10.1234/test", "https://arxiv.org/abs/1234.5678"]
    mock_resp = _make_mediawiki_resp(urls)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        result = await _wk._fetch_cited_sources("Python", "pt")

    assert result == urls


@pytest.mark.anyio
async def test_fetch_cited_sources_exception_returns_empty():
    """Exception de rede → lista vazia, sem propagar."""
    import httpx
    import services.wiki_card as _wk

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=ConnectionError("timeout"))

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        result = await _wk._fetch_cited_sources("Python", "pt")

    assert result == []


@pytest.mark.anyio
async def test_get_wiki_card_includes_cited_sources(tmp_path, monkeypatch):
    """Card resultante inclui campo cited_sources com URLs das fontes."""
    import httpx
    import services.wiki_card as _wk
    monkeypatch.setattr(_wk, "DB_PATH", tmp_path / "akasha.db")

    summary_payload = {
        "title": "Python",
        "extract": "Python é uma linguagem.",
        "content_urls": {"desktop": {"page": "https://pt.wikipedia.org/wiki/Python"}},
    }
    mw_payload = {
        "query": {"pages": {"1": {"extlinks": [
            {"*": "https://docs.python.org"},
            {"*": "https://peps.python.org"},
        ]}}}
    }

    def _make_route(url, **kw):
        import httpx as _hx
        req = _hx.Request("GET", str(url))
        if "rest_v1" in str(url):
            return _hx.Response(200, content=json.dumps(summary_payload).encode(), request=req)
        return _hx.Response(200, content=json.dumps(mw_payload).encode(), request=req)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=_make_route)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        card = await _wk.get_wiki_card("python linguagem programação")

    assert card is not None
    assert "cited_sources" in card
    assert "https://docs.python.org" in card["cited_sources"]


@pytest.mark.anyio
async def test_get_wiki_card_sources_timeout_card_still_present(tmp_path, monkeypatch):
    """Sources expiram (exception) → card presente com cited_sources=[]."""
    import httpx
    import services.wiki_card as _wk
    monkeypatch.setattr(_wk, "DB_PATH", tmp_path / "akasha.db")

    summary_payload = {
        "title": "Test",
        "extract": "Test extract.",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Test"}},
    }

    call_count = [0]

    def _make_route(url, **kw):
        import httpx as _hx
        call_count[0] += 1
        req = _hx.Request("GET", str(url))
        if "rest_v1" in str(url):
            return _hx.Response(200, content=json.dumps(summary_payload).encode(), request=req)
        raise ConnectionError("extlinks timeout")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=_make_route)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        card = await _wk.get_wiki_card("test query en")

    assert card is not None
    assert card["extract"] == "Test extract."
    assert card["cited_sources"] == []


@pytest.mark.anyio
async def test_get_wiki_card_cache_hit_includes_cited_sources(monkeypatch):
    """Cache HIT com cited_sources → retorna completo sem novo request."""
    import services.wiki_card as _wk

    cached = {
        "title": "Cached",
        "extract": "Cached extract.",
        "thumbnail_url": None,
        "page_url": "https://en.wikipedia.org/wiki/Cached",
        "lang": "en",
        "cited_sources": ["https://nature.com/article"],
    }

    async def _fake_cache(qhash):
        return cached

    monkeypatch.setattr(_wk, "_get_cache", _fake_cache)

    result = await _wk.get_wiki_card("cached query")

    assert result is not None
    assert result["cited_sources"] == ["https://nature.com/article"]
