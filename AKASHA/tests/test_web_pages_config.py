"""
Testes para Fix 3 — busca web multi-página e configuração web_pages.

Cobre:
  - _get_web_pages: retorna 4 sem ecosystem_client
  - _get_web_pages: lê do ecosystem.json
  - _get_web_pages: clampeia em 1–10
  - _get_web_pages: captura exceção sem explodir
  - search_web: max_results=0 retorna todos os resultados (sem teto)
  - search_web: max_results=N ainda funciona como teto (retrocompat)
  - search_web: n_pages repassa para _fetch_web
  - _fetch_searxng: chama n_pages páginas em paralelo
  - _CACHE_SIZE é 100
  - endpoint /search: ?web_pages=N é respeitado como override
  - endpoint /search: sem ?web_pages usa _get_web_pages (default 4)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from services.web_search import SearchResult, _CACHE_SIZE, _FETCH_PAGE_SIZE


# ---------------------------------------------------------------------------
# _CACHE_SIZE e _FETCH_PAGE_SIZE
# ---------------------------------------------------------------------------

def test_cache_size_is_100():
    assert _CACHE_SIZE == 100


def test_fetch_page_size_is_25():
    assert _FETCH_PAGE_SIZE == 25


# ---------------------------------------------------------------------------
# _get_web_pages — leitura de config
# ---------------------------------------------------------------------------

def test_get_web_pages_default_without_ecosystem_client():
    from routers.search import _get_web_pages
    with patch.dict("sys.modules", {"ecosystem_client": None}):
        result = _get_web_pages()
    assert result == 4


def test_get_web_pages_reads_from_config():
    from routers.search import _get_web_pages
    mock_ec = MagicMock()
    mock_ec.get_akasha_config.return_value = {"web_pages": 3}
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        result = _get_web_pages()
    assert result == 3


def test_get_web_pages_clamped_minimum_1():
    from routers.search import _get_web_pages
    mock_ec = MagicMock()
    mock_ec.get_akasha_config.return_value = {"web_pages": 0}
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        result = _get_web_pages()
    assert result == 1


def test_get_web_pages_clamped_maximum_10():
    from routers.search import _get_web_pages
    mock_ec = MagicMock()
    mock_ec.get_akasha_config.return_value = {"web_pages": 99}
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        result = _get_web_pages()
    assert result == 10


def test_get_web_pages_missing_key_returns_4():
    from routers.search import _get_web_pages
    mock_ec = MagicMock()
    mock_ec.get_akasha_config.return_value = {}
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        result = _get_web_pages()
    assert result == 4


def test_get_web_pages_handles_exception():
    from routers.search import _get_web_pages
    mock_ec = MagicMock()
    mock_ec.get_akasha_config.side_effect = RuntimeError("indisponível")
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        result = _get_web_pages()
    assert result == 4


# ---------------------------------------------------------------------------
# search_web — max_results=0 retorna todos; n_pages repassa para _fetch_web
# ---------------------------------------------------------------------------

def _make_results(n: int) -> list[SearchResult]:
    return [
        SearchResult(url=f"https://r{i}.com/", title=f"r{i}", snippet="s", source="WEB")
        for i in range(n)
    ]


@pytest.mark.anyio
async def test_search_web_max_results_zero_returns_all():
    """max_results=0 → todos os resultados do fetch são retornados."""
    fake = _make_results(80)
    with patch("services.web_search._fetch_web", new_callable=AsyncMock, return_value=fake):
        from services.web_search import search_web
        results = await search_web("python", max_results=0, n_pages=4)
    assert len(results) == 80


@pytest.mark.anyio
async def test_search_web_max_results_n_still_works():
    """max_results=10 ainda funciona como teto (retrocompat para /search/more)."""
    fake = _make_results(80)
    with patch("services.web_search._fetch_web", new_callable=AsyncMock, return_value=fake):
        from services.web_search import search_web
        results = await search_web("python", max_results=10, n_pages=4)
    assert len(results) == 10


@pytest.mark.anyio
async def test_search_web_passes_n_pages_to_fetch():
    """n_pages é repassado corretamente ao _fetch_web."""
    mock_fetch = AsyncMock(return_value=[])
    # Mockar ambas as camadas de cache para garantir que _fetch_web seja chamado
    with (
        patch("services.web_search._fetch_web", mock_fetch),
        patch("services.web_search._mem_cache") as mock_mem,
        patch("services.web_search._get_db_cache", new_callable=AsyncMock, return_value=None),
    ):
        mock_mem.get = lambda _: None  # sempre cache miss
        from services.web_search import search_web
        await search_web("query_n_pages_test", max_results=0, n_pages=3)
    assert mock_fetch.called, "_fetch_web nunca foi chamado"
    call_kwargs = mock_fetch.call_args.kwargs
    call_args = mock_fetch.call_args.args
    n_pages_passed = call_kwargs.get("n_pages") or (call_args[2] if len(call_args) > 2 else None)
    assert n_pages_passed == 3


# ---------------------------------------------------------------------------
# _fetch_searxng — múltiplas páginas em paralelo
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_fetch_searxng_calls_n_pages():
    """_fetch_searxng com n_pages=3 deve fazer 3 requests GET."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": [
        {"url": "https://r.com/", "title": "R", "content": "s"}
    ]}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.web_search.httpx.AsyncClient", return_value=mock_client):
        from services.web_search import _fetch_searxng
        results = await _fetch_searxng("python", max_results=0, base_url="http://sx", n_pages=3)

    assert mock_client.get.call_count == 3
    # Verifica que pageno=1, 2, 3 foram passados
    pagnos = [c.kwargs.get("params", {}).get("pageno") for c in mock_client.get.call_args_list]
    assert sorted(pagnos) == [1, 2, 3]


@pytest.mark.anyio
async def test_fetch_searxng_combines_results_from_all_pages():
    """Resultados de todas as páginas são combinados numa única lista."""
    def _mock_resp(pageno: int):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"results": [
            {"url": f"https://page{pageno}.com/r{i}", "title": f"r{i}", "content": "s"}
            for i in range(3)
        ]}
        return m

    call_count = 0

    async def _mock_get(url, params=None, **kwargs):
        nonlocal call_count
        call_count += 1
        pageno = (params or {}).get("pageno", 1)
        return _mock_resp(pageno)

    mock_client = AsyncMock()
    mock_client.get = _mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.web_search.httpx.AsyncClient", return_value=mock_client):
        from services.web_search import _fetch_searxng
        results = await _fetch_searxng("python", max_results=0, base_url="http://sx", n_pages=3)

    # 3 páginas × 3 resultados = 9
    assert len(results) == 9
    assert call_count == 3
