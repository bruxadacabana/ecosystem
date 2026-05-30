"""
Testes para GET /fetch?url= em routers/search.py.

Cobre:
  - fetch bem-sucedido: retorna url, title, content_md, word_count
  - HTTP 404: error preenchido, campos vazios
  - Erro de rede (RequestError): error preenchido, campos vazios
  - Paridade com POST /fetch: mesma lógica, entrada diferente
  - max_words padrão (2000) é repassado para fetch_and_extract
  - max_words customizado é respeitado
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@dataclass
class _FakePage:
    url:        str
    title:      str
    content_md: str
    word_count: int
    author:     str       = field(default="")
    language:   str       = field(default="")
    pub_date:   str       = field(default="")
    description: str      = field(default="")
    sitename:   str       = field(default="")
    keywords:   list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_page(url: str, title: str, content: str) -> _FakePage:
    return _FakePage(
        url=url,
        title=title,
        content_md=content,
        word_count=len(content.split()),
    )


# ---------------------------------------------------------------------------
# Testes da lógica do endpoint (sem inicializar o app completo)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_get_success():
    """Fetch bem-sucedido: todos os campos corretos."""
    from routers.search import fetch_get

    page = _make_fake_page(
        "https://example.com/article",
        "Título do Artigo",
        "Lorem ipsum dolor sit amet consectetur adipiscing",
    )
    with patch("routers.search.fetch_and_extract", new=AsyncMock(return_value=page)):
        resp = await fetch_get(url="https://example.com/article")

    assert resp.url == "https://example.com/article"
    assert resp.title == "Título do Artigo"
    assert resp.content_md == page.content_md
    assert resp.word_count == page.word_count
    assert resp.error is None


@pytest.mark.asyncio
async def test_fetch_get_http_404():
    """HTTP 404 → error preenchido, word_count=0."""
    from routers.search import fetch_get

    http_error = httpx.HTTPStatusError(
        "404 Not Found",
        request=MagicMock(),
        response=MagicMock(status_code=404),
    )
    with patch("routers.search.fetch_and_extract", new=AsyncMock(side_effect=http_error)):
        resp = await fetch_get(url="https://example.com/notfound")

    assert resp.url == "https://example.com/notfound"
    assert resp.title == ""
    assert resp.content_md == ""
    assert resp.word_count == 0
    assert resp.error == "HTTP 404"


@pytest.mark.asyncio
async def test_fetch_get_request_error():
    """Erro de rede → error preenchido, word_count=0."""
    from routers.search import fetch_get

    req_error = httpx.RequestError("Connection refused", request=MagicMock())
    with patch("routers.search.fetch_and_extract", new=AsyncMock(side_effect=req_error)):
        resp = await fetch_get(url="https://unreachable.example.com/")

    assert resp.url == "https://unreachable.example.com/"
    assert resp.word_count == 0
    assert resp.error is not None
    assert "Erro de rede" in resp.error


@pytest.mark.asyncio
async def test_fetch_get_passes_default_max_words():
    """max_words padrão (2000) é repassado a fetch_and_extract."""
    from routers.search import fetch_get

    mock_fetch = AsyncMock(return_value=_make_fake_page("https://x.com", "T", "word"))
    with patch("routers.search.fetch_and_extract", new=mock_fetch):
        await fetch_get(url="https://x.com")

    mock_fetch.assert_awaited_once_with("https://x.com", max_words=2000)


@pytest.mark.asyncio
async def test_fetch_get_respects_custom_max_words():
    """max_words customizado é repassado corretamente."""
    from routers.search import fetch_get

    mock_fetch = AsyncMock(return_value=_make_fake_page("https://x.com", "T", "word"))
    with patch("routers.search.fetch_and_extract", new=mock_fetch):
        await fetch_get(url="https://x.com", max_words=500)

    mock_fetch.assert_awaited_once_with("https://x.com", max_words=500)


@pytest.mark.asyncio
async def test_fetch_get_and_post_produce_same_output():
    """GET e POST /fetch devem produzir o mesmo resultado para a mesma URL."""
    from routers.search import fetch_get, fetch, _FetchBody

    page = _make_fake_page("https://equal.com/", "Igual", "mesmo conteúdo aqui")
    mock = AsyncMock(return_value=page)

    with patch("routers.search.fetch_and_extract", new=mock):
        resp_get  = await fetch_get(url="https://equal.com/")
        resp_post = await fetch(_FetchBody(url="https://equal.com/"))

    assert resp_get.url        == resp_post.url
    assert resp_get.title      == resp_post.title
    assert resp_get.content_md == resp_post.content_md
    assert resp_get.word_count == resp_post.word_count
    assert resp_get.error      == resp_post.error
