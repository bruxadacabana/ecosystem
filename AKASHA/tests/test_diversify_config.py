"""
Testes para Fix 2 — max_per_domain configurável via ecosystem.json e ?diversity=N.

Cobre:
  - _get_max_per_domain: retorna 5 quando ecosystem_client ausente
  - _get_max_per_domain: lê valor do ecosystem.json via get_akasha_config
  - _get_max_per_domain: retorna 5 se chave ausente no config
  - _get_max_per_domain: retorna 0 se config diz 0 (sem limite)
  - _get_max_per_domain: captura exceções do ecosystem_client sem explodir
  - busca exploratory sem ?diversity usa valor do config (5)
  - busca exploratory com ?diversity=N usa N como override
  - busca exploratory com ?diversity=0 não aplica nenhum corte por domínio
  - busca não-exploratory não é afetada pelo max_per_domain
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.web_search import SearchResult


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


# ---------------------------------------------------------------------------
# _get_max_per_domain — leitura de config
# ---------------------------------------------------------------------------

def test_get_max_per_domain_default_without_ecosystem_client():
    """Sem ecosystem_client disponível, retorna 5."""
    from routers.search import _get_max_per_domain
    with patch.dict("sys.modules", {"ecosystem_client": None}):
        result = _get_max_per_domain()
    assert result == 5


def test_get_max_per_domain_reads_from_config():
    """Lê max_per_domain=3 do ecosystem.json via read_ecosystem."""
    from routers.search import _get_max_per_domain
    mock_ec = MagicMock()
    mock_ec.read_ecosystem.return_value = {"akasha": {"max_per_domain": 3}}
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        result = _get_max_per_domain()
    assert result == 3


def test_get_max_per_domain_missing_key_returns_5():
    """Config sem max_per_domain → retorna 5."""
    from routers.search import _get_max_per_domain
    mock_ec = MagicMock()
    mock_ec.read_ecosystem.return_value = {"akasha": {}}
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        result = _get_max_per_domain()
    assert result == 5


def test_get_max_per_domain_zero_means_no_limit():
    """max_per_domain=0 → retorna 0 (sem limite)."""
    from routers.search import _get_max_per_domain
    mock_ec = MagicMock()
    mock_ec.read_ecosystem.return_value = {"akasha": {"max_per_domain": 0}}
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        result = _get_max_per_domain()
    assert result == 0


def test_get_max_per_domain_handles_exception():
    """Exceção no ecosystem_client → retorna 5 sem explodir."""
    from routers.search import _get_max_per_domain
    mock_ec = MagicMock()
    mock_ec.read_ecosystem.side_effect = RuntimeError("config indisponível")
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        result = _get_max_per_domain()
    assert result == 5


# ---------------------------------------------------------------------------
# Comportamento de busca via endpoint — ?diversity e config
# ---------------------------------------------------------------------------

def _web_same_domain(n: int, domain: str = "single.com") -> list[SearchResult]:
    """N resultados todos do mesmo domínio."""
    return [
        SearchResult(url=f"https://{domain}/page{i}", title=f"Página {i}",
                     snippet="s", score=0.9, source="web")
        for i in range(n)
    ]


def _web_multi_domain(n_per_domain: int, domains: list[str]) -> list[SearchResult]:
    results = []
    for d in domains:
        for i in range(n_per_domain):
            results.append(SearchResult(
                url=f"https://{d}/page{i}", title=f"{d} page {i}",
                snippet="s", score=0.9, source="web",
            ))
    return results


def _count_present(text: str, urls: list[str]) -> int:
    """Conta quantas URLs únicas estão presentes no HTML (≥1 ocorrência cada)."""
    return sum(1 for u in urls if u in text)


@pytest.mark.anyio
async def test_exploratory_default_max_per_domain_is_5(client):
    """Sem ?diversity, exploratory aplica max_per_domain=5 do config."""
    fake = _web_same_domain(10)
    all_urls = [f"single.com/page{i}" for i in range(10)]
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
        patch("routers.search._get_max_per_domain", return_value=5),
        patch("routers.search.classify_intent_lexical", return_value="exploratory"),
    ):
        resp = await client.get(
            "/search",
            params={"q": "python tutorial", "src_web": "on",
                    "src_eco": "off", "src_sites": "off"},
        )
    assert resp.status_code == 200
    present = _count_present(resp.text, all_urls)
    assert present <= 5, f"max_per_domain=5 não foi aplicado: {present}/10 URLs do mesmo domínio"


@pytest.mark.anyio
async def test_diversity_param_overrides_config(client):
    """?diversity=2 → no máximo 2 resultados por domínio, independente do config."""
    fake = _web_same_domain(6)
    all_urls = [f"single.com/page{i}" for i in range(6)]
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
        patch("routers.search._get_max_per_domain", return_value=5),
        patch("routers.search.classify_intent_lexical", return_value="exploratory"),
    ):
        resp = await client.get(
            "/search",
            params={"q": "python tutorial", "src_web": "on",
                    "src_eco": "off", "src_sites": "off", "diversity": "2"},
        )
    assert resp.status_code == 200
    present = _count_present(resp.text, all_urls)
    assert present <= 2, f"?diversity=2 não foi respeitado: {present}/6 URLs do mesmo domínio"


@pytest.mark.anyio
async def test_diversity_zero_no_domain_limit(client):
    """?diversity=0 → sem limite por domínio, todos os resultados aparecem."""
    fake = _web_same_domain(5)
    all_urls = [f"single.com/page{i}" for i in range(5)]
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
        patch("routers.search._get_max_per_domain", return_value=5),
        patch("routers.search.classify_intent_lexical", return_value="exploratory"),
    ):
        resp = await client.get(
            "/search",
            params={"q": "python tutorial", "src_web": "on",
                    "src_eco": "off", "src_sites": "off", "diversity": "0"},
        )
    assert resp.status_code == 200
    present = _count_present(resp.text, all_urls)
    assert present == 5, f"?diversity=0 deve retornar todos os 5, mas retornou {present}"


@pytest.mark.anyio
async def test_non_exploratory_not_affected_by_diversity(client):
    """intent=navigational → diversificação não é aplicada mesmo com ?diversity."""
    fake = _web_same_domain(4)
    all_urls = [f"single.com/page{i}" for i in range(4)]
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.classify_intent_lexical", return_value="navigational"),
    ):
        resp = await client.get(
            "/search",
            params={"q": "github.com", "intent": "navigational", "src_web": "on",
                    "src_eco": "off", "src_sites": "off", "diversity": "1"},
        )
    assert resp.status_code == 200
    # navigational não aplica _diversify_by_domain → todos 4 aparecem
    present = _count_present(resp.text, all_urls)
    assert present == 4, f"intent=navigational não deve aplicar diversificação: {present}/4"
