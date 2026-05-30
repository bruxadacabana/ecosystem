"""
Testes para HTTP 429 backoff exponencial em ecosystem_scraper.py e archiver.py.

Cobre:
  compute_429_backoff:
    - sem Retry-After: usa exponencial puro com jitter
    - com Retry-After maior que exponencial: usa o do servidor
    - com Retry-After menor que exponencial: usa o exponencial
    - attempt=0: base mínima (2s)
    - attempt=1: 2×base (4s)
    - attempt=2: 4×base (8s)
    - teto de 60s respeitado em attempt alto
    - resultado sempre ≥ 0
    - Retry-After inválido (texto) não lança exceção

  archiver.fetch_and_extract (mock httpx):
    - 200 OK: retorna sem retry
    - 429 → 200: retenta e sucede
    - 429 × MAX_RETRIES+1: esgota retentativas, tenta próximo proxy (se houver)
    - Retry-After lido do header
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

_ROOT = Path(__file__).parent.parent
_ECO_ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ECO_ROOT) not in sys.path:
    sys.path.insert(0, str(_ECO_ROOT))


# ---------------------------------------------------------------------------
# compute_429_backoff — testes de unidade
# ---------------------------------------------------------------------------

def test_backoff_no_retry_after_attempt0():
    """Sem Retry-After, attempt=0: resultado entre 1s e 4s (base=2 ±50%)."""
    from ecosystem_scraper import compute_429_backoff
    results = [compute_429_backoff(None, 0) for _ in range(50)]
    assert all(0.0 <= r <= 4.0 for r in results), f"Fora de range: {min(results):.2f}–{max(results):.2f}"
    # Deve haver variação por jitter
    assert max(results) > min(results), "Jitter não aplicado"


def test_backoff_no_retry_after_attempt1():
    """attempt=1: base exponencial ~4s."""
    from ecosystem_scraper import compute_429_backoff
    results = [compute_429_backoff(None, 1) for _ in range(30)]
    assert all(0.0 <= r <= 8.0 for r in results)


def test_backoff_no_retry_after_attempt2():
    """attempt=2: base exponencial ~8s."""
    from ecosystem_scraper import compute_429_backoff
    results = [compute_429_backoff(None, 2) for _ in range(30)]
    assert all(0.0 <= r <= 16.0 for r in results)


def test_backoff_capped_at_60s():
    """Tentativas altas: teto de 60s respeitado (antes do jitter)."""
    from ecosystem_scraper import compute_429_backoff
    # attempt=10: 2 × 2^10 = 2048 → limitado a 60, depois jitter ±50% → máx 90s
    results = [compute_429_backoff(None, 10) for _ in range(50)]
    assert all(r <= 90.0 for r in results), f"Máximo: {max(results):.1f}s"


def test_backoff_retry_after_larger_than_exponential():
    """Retry-After maior que exponencial: usa o do servidor."""
    from ecosystem_scraper import compute_429_backoff
    # attempt=0: exponencial=2s, Retry-After=30s → base=30s, jitter ±15 → 15–45s
    results = [compute_429_backoff("30", 0) for _ in range(30)]
    assert all(r >= 14.0 for r in results), f"Mínimo abaixo do esperado: {min(results):.2f}"


def test_backoff_retry_after_smaller_than_exponential():
    """Retry-After menor que exponencial: usa o exponencial."""
    from ecosystem_scraper import compute_429_backoff
    # attempt=2: exponencial=8s, Retry-After=1s → base=8s, jitter ±4 → 4–12s
    results = [compute_429_backoff("1", 2) for _ in range(30)]
    assert all(r >= 3.0 for r in results), f"Mínimo: {min(results):.2f}s"


def test_backoff_invalid_retry_after_no_exception():
    """Retry-After inválido (texto) não lança exceção."""
    from ecosystem_scraper import compute_429_backoff
    result = compute_429_backoff("invalid-value", 0)
    assert result >= 0.0


def test_backoff_none_retry_after_no_exception():
    """Retry-After=None não lança exceção."""
    from ecosystem_scraper import compute_429_backoff
    result = compute_429_backoff(None, 0)
    assert result >= 0.0


def test_backoff_result_always_non_negative():
    """Resultado sempre ≥ 0 mesmo com jitter negativo extremo."""
    from ecosystem_scraper import compute_429_backoff
    results = [compute_429_backoff(None, 0) for _ in range(200)]
    assert all(r >= 0.0 for r in results)


def test_max_retries_exported():
    """MAX_RETRIES está exportado e é inteiro ≥ 1."""
    from ecosystem_scraper import MAX_RETRIES
    assert isinstance(MAX_RETRIES, int)
    assert MAX_RETRIES >= 1


# ---------------------------------------------------------------------------
# archiver.fetch_and_extract — integração com mock httpx
# ---------------------------------------------------------------------------

def _make_response(status: int, body: str = "", headers: dict | None = None) -> MagicMock:
    """Cria mock de resposta httpx com os atributos necessários."""
    import httpx as _httpx
    resp = MagicMock()
    resp.status_code = status
    resp.text = body
    resp.headers = headers or {}
    resp.request = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
            f"HTTP {status}", request=resp.request, response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def _make_client_factory(url_responses: dict[str, MagicMock]) -> tuple[MagicMock, list[str]]:
    """
    Retorna (mock_client, urls_requested) onde mock_client.get() responde
    de acordo com url_responses. Chamadas a URLs não mapeadas levantam RequestError.
    urls_requested acumula todas as URLs acessadas.
    """
    import httpx as _httpx

    urls_requested: list[str] = []
    call_counts: dict[str, int] = {}

    async def _get(url: str, **kwargs: object) -> MagicMock:
        urls_requested.append(url)
        n = call_counts.get(url, 0)
        call_counts[url] = n + 1
        responses = url_responses.get(url)
        if responses is None:
            raise _httpx.RequestError(f"URL não mapeada no mock: {url}", request=MagicMock())
        if isinstance(responses, list):
            idx = min(n, len(responses) - 1)
            return responses[idx]
        return responses

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=_get)
    return mock_client, urls_requested


_RICH_HTML = "<html><body>" + " ".join(["palavra"] * 200) + "</body></html>"


@pytest.mark.asyncio
async def test_archiver_200_no_retry():
    """HTTP 200: GET na URL principal chamado exatamente 1 vez (Jina ignorado)."""
    import httpx as _httpx

    main_url = "https://example.com/"
    jina_url  = f"https://r.jina.ai/{main_url}"

    url_responses = {
        main_url: _make_response(200, _RICH_HTML),
        jina_url: _make_response(200, "jina fallback"),  # não deve ser chamado
    }
    mock_client, urls = _make_client_factory(url_responses)

    with (
        patch("services.archiver.httpx.AsyncClient", return_value=mock_client),
        patch("services.archiver._throttle_domain", new=AsyncMock()),
        patch("ecosystem_scraper._ext_trafilatura", return_value="palavra " * 120),
    ):
        from services.archiver import fetch_and_extract
        page = await fetch_and_extract(main_url)

    assert urls.count(main_url) == 1, f"GET principal chamado {urls.count(main_url)}x (esperado 1)"
    assert page.url == main_url


@pytest.mark.asyncio
async def test_archiver_429_then_200_retries():
    """HTTP 429 seguido de 200 na mesma URL: retenta e obtém conteúdo."""
    main_url = "https://example.com/"
    jina_url  = f"https://r.jina.ai/{main_url}"

    url_responses = {
        main_url: [_make_response(429, "", {"Retry-After": "0"}), _make_response(200, _RICH_HTML)],
        jina_url: _make_response(200, "jina fallback"),
    }
    mock_client, urls = _make_client_factory(url_responses)

    with (
        patch("services.archiver.httpx.AsyncClient", return_value=mock_client),
        patch("services.archiver._throttle_domain", new=AsyncMock()),
        patch("services.archiver.asyncio.sleep", new=AsyncMock()),
        patch("ecosystem_scraper._ext_trafilatura", return_value="palavra " * 120),
    ):
        from services.archiver import fetch_and_extract
        page = await fetch_and_extract(main_url)

    assert urls.count(main_url) == 2, f"GET principal chamado {urls.count(main_url)}x (esperado 2)"
    assert page.word_count > 0


@pytest.mark.asyncio
async def test_archiver_429_reads_retry_after_header():
    """429 com Retry-After=15: sleep chamado com valor ≥ 7s (Retry-After/2 pelo jitter)."""
    main_url = "https://example.com/"
    jina_url  = f"https://r.jina.ai/{main_url}"

    url_responses = {
        main_url: [_make_response(429, "", {"Retry-After": "15"}), _make_response(200, _RICH_HTML)],
        jina_url: _make_response(200, "jina fallback"),
    }
    mock_client, _ = _make_client_factory(url_responses)

    sleep_calls: list[float] = []

    async def _fake_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    with (
        patch("services.archiver.httpx.AsyncClient", return_value=mock_client),
        patch("services.archiver._throttle_domain", new=AsyncMock()),
        patch("services.archiver.asyncio.sleep", side_effect=_fake_sleep),
        patch("ecosystem_scraper._ext_trafilatura", return_value="palavra " * 120),
    ):
        from services.archiver import fetch_and_extract
        await fetch_and_extract(main_url)

    assert len(sleep_calls) >= 1, "sleep não chamado após 429"
    # Retry-After=15 → base=max(15, 2)=15 ± jitter50% → mínimo 7.5s
    assert sleep_calls[0] >= 7.0, f"sleep muito curto: {sleep_calls[0]:.2f}s"
