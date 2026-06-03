"""
Testes de regressão para Fix 1 — intenção não trunca resultados.

Antes da correção, intent=navigational cortava todas as listas a [:1]
e intent=fact-seeking cortava local_results a [:5]. Esses cortes foram
removidos: intenção afeta apenas apresentação no template, nunca quantidade.

Cobre:
  - navigational com N resultados web → todos N aparecem na resposta
  - navigational com N resultados locais → todos N aparecem na resposta
  - fact-seeking com N resultados locais → todos N aparecem (sem corte em 5)
  - fact-seeking sem src_eco → ainda inclui resultados locais (comportamento mantido)
  - fact-seeking com src_eco → não duplica resultados locais
  - exploratory → resultados inalterados (baseline de comparação)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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


def _fake_web(n: int) -> list[SearchResult]:
    return [
        SearchResult(
            url=f"https://web{i}.example.com/page",
            title=f"Resultado web {i}",
            snippet="Trecho de exemplo.",
            score=0.9,
            source="web",
        )
        for i in range(n)
    ]


def _fake_local(n: int):
    return [
        SimpleNamespace(
            url=f"file:///home/user/docs/local{i}.md",
            title=f"Documento local {i}",
            snippet="Conteúdo local.",
            score=0.8,
            source="local",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# navigational — sem corte de resultados
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_navigational_does_not_truncate_web_results(client):
    """5 resultados web + intent=navigational → todos 5 devem aparecer na resposta."""
    fake = _fake_web(5)
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get(
            "/search",
            params={"q": "github.com", "intent": "navigational",
                    "src_web": "on", "src_eco": "off", "src_sites": "off"},
        )
    assert resp.status_code == 200
    for i in range(5):
        assert f"web{i}.example.com" in resp.text, (
            f"web{i}.example.com ausente — navigational truncou resultados"
        )


@pytest.mark.anyio
async def test_navigational_does_not_truncate_local_results(client):
    """5 resultados locais + intent=navigational → todos 5 devem aparecer na resposta."""
    fake = _fake_local(5)
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get(
            "/search",
            params={"q": "github.com", "intent": "navigational",
                    "src_web": "off", "src_eco": "on", "src_sites": "off"},
        )
    assert resp.status_code == 200
    for i in range(5):
        assert f"local{i}.md" in resp.text, (
            f"local{i}.md ausente — navigational truncou resultados locais"
        )


# ---------------------------------------------------------------------------
# fact-seeking — sem corte em 5, mas mantém busca local forçada
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_fact_seeking_does_not_truncate_local_results_at_five(client):
    """8 resultados locais + intent=fact-seeking → todos 8, não apenas 5."""
    fake = _fake_local(8)
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get(
            "/search",
            params={"q": "como funciona sqlite", "intent": "fact-seeking",
                    "src_web": "off", "src_eco": "on", "src_sites": "off"},
        )
    assert resp.status_code == 200
    for i in range(8):
        assert f"local{i}.md" in resp.text, (
            f"local{i}.md ausente — fact-seeking ainda está truncando em 5"
        )


@pytest.mark.anyio
async def test_fact_seeking_without_src_eco_still_fetches_local(client):
    """fact-seeking sem src_eco → ainda busca local (comportamento mantido)."""
    fake_local = _fake_local(3)
    mock_local = AsyncMock(return_value=fake_local)
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_local", mock_local),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get(
            "/search",
            params={"q": "fato histórico", "intent": "fact-seeking",
                    "src_web": "off", "src_eco": "off", "src_sites": "off"},
        )
    assert resp.status_code == 200
    mock_local.assert_called_once()  # busca local foi disparada mesmo sem src_eco


@pytest.mark.anyio
async def test_fact_seeking_with_src_eco_does_not_duplicate_local(client):
    """fact-seeking com src_eco=on → search_local chamado apenas 1x (não duplica)."""
    fake_local = _fake_local(3)
    mock_local = AsyncMock(return_value=fake_local)
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_local", mock_local),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get(
            "/search",
            params={"q": "fato histórico", "intent": "fact-seeking",
                    "src_web": "off", "src_eco": "on", "src_sites": "off"},
        )
    assert resp.status_code == 200
    assert mock_local.call_count == 1, (
        f"search_local chamado {mock_local.call_count}x — resultados locais duplicados"
    )


# ---------------------------------------------------------------------------
# exploratory — baseline de comparação (sem intent override)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_exploratory_intent_returns_all_results(client):
    """exploratory não limita resultados — baseline para confirmar que fix não quebrou nada."""
    fake = _fake_web(4)
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get(
            "/search",
            params={"q": "melhores práticas desenvolvimento web", "intent": "exploratory",
                    "src_web": "on", "src_eco": "off", "src_sites": "off"},
        )
    assert resp.status_code == 200
    for i in range(4):
        assert f"web{i}.example.com" in resp.text


# ---------------------------------------------------------------------------
# sem intent — padrão não trunca
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_no_intent_override_returns_all_results(client):
    """Sem intent override, resultados chegam sem corte artificial."""
    fake = _fake_web(6)
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get(
            "/search",
            params={"q": "python tutorial", "src_web": "on",
                    "src_eco": "off", "src_sites": "off"},
        )
    assert resp.status_code == 200
    for i in range(6):
        assert f"web{i}.example.com" in resp.text


# ---------------------------------------------------------------------------
# SearXNG 9 — cobertura adicional: volume grande + diversidade desligável
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_navigational_no_hidden_cap_with_large_result_set(client):
    """30 resultados web + navigational → todos 30 (nenhum teto oculto de contagem)."""
    fake = _fake_web(30)
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get(
            "/search",
            params={"q": "github.com", "intent": "navigational",
                    "src_web": "on", "src_eco": "off", "src_sites": "off"},
        )
    assert resp.status_code == 200
    for i in range(30):
        assert f"web{i}.example.com" in resp.text, (
            f"web{i}.example.com ausente — há um teto oculto de contagem"
        )


@pytest.mark.anyio
async def test_exploratory_diversity_off_keeps_all_same_domain(client):
    """exploratory + max_per_domain=0 (config) → 8 resultados do MESMO domínio passam todos.

    A diversidade por domínio é o ÚNICO redutor de contagem ligado à intenção (só
    exploratory) — e é desligável via Settings (`max_per_domain=0`). Garante que dá
    para extrair volume máximo mesmo quando os resultados se concentram num domínio.
    Nota: `?diversity=0` na URL NÃO desliga (0 = "usar config"); só o config 0 desliga.
    """
    fake = [
        SearchResult(
            url=f"https://samedomain.example.com/page{i}",
            title=f"Resultado {i}", snippet="x", score=0.9, source="web",
        )
        for i in range(8)
    ]
    with (
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=fake),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
        patch("routers.search._get_max_per_domain", return_value=0),  # diversidade desligada
    ):
        resp = await client.get(
            "/search",
            params={"q": "tema amplo de pesquisa", "intent": "exploratory",
                    "src_web": "on", "src_eco": "off", "src_sites": "off"},
        )
    assert resp.status_code == 200
    for i in range(8):
        assert f"page{i}" in resp.text, (
            f"page{i} ausente — com max_per_domain=0 nada do mesmo domínio deveria ser cortado"
        )
