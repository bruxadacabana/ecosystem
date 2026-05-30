"""
Testes para throttle_domain() em ecosystem_scraper.py.

Cobre:
  - Primeira requisição a um domínio: sem wait (executa imediatamente)
  - Segunda requisição dentro do delay: aguarda a diferença
  - Segunda requisição após o delay: executa imediatamente
  - Domínios diferentes: sem interferência entre eles
  - CRAWL_DELAY exportado e com valor correto
  - throttle_domain atualiza timestamp mesmo após wait=0
  - delay=0 nunca espera (comportamento de bypass)
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent.parent  # raiz do ecossistema
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _clear_domain_cache() -> None:
    """Limpa o cache de timestamps entre testes para isolamento."""
    import ecosystem_scraper
    ecosystem_scraper._domain_timestamps.clear()


# ---------------------------------------------------------------------------
# Testes de throttle_domain
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_request_no_wait():
    """Primeira requisição a um domínio não espera."""
    _clear_domain_cache()
    from ecosystem_scraper import throttle_domain

    t0 = time.monotonic()
    await throttle_domain("https://example.com/page1", delay=1.0)
    elapsed = time.monotonic() - t0

    assert elapsed < 0.1, f"Esperou {elapsed:.3f}s na primeira requisição (devia ser 0)"


@pytest.mark.asyncio
async def test_second_request_waits_remaining():
    """Segunda requisição dentro do delay espera a diferença."""
    _clear_domain_cache()
    from ecosystem_scraper import throttle_domain

    # Primeira requisição — marca timestamp
    await throttle_domain("https://example.com/page1", delay=0.3)
    # Segunda requisição imediatamente — deve esperar ~0.3s
    t0 = time.monotonic()
    await throttle_domain("https://example.com/page2", delay=0.3)
    elapsed = time.monotonic() - t0

    assert elapsed >= 0.25, f"Não esperou o delay (elapsed={elapsed:.3f}s)"
    assert elapsed < 0.55, f"Esperou mais que o necessário ({elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_second_request_after_delay_no_wait():
    """Segunda requisição após o delay decorrido não espera."""
    _clear_domain_cache()
    from ecosystem_scraper import throttle_domain

    await throttle_domain("https://example.com/p1", delay=0.1)
    await asyncio.sleep(0.15)  # espera o delay acabar

    t0 = time.monotonic()
    await throttle_domain("https://example.com/p2", delay=0.1)
    elapsed = time.monotonic() - t0

    assert elapsed < 0.05, f"Esperou {elapsed:.3f}s desnecessariamente"


@pytest.mark.asyncio
async def test_different_domains_no_interference():
    """Domínios diferentes têm throttles independentes."""
    _clear_domain_cache()
    from ecosystem_scraper import throttle_domain

    # Marca domínio A
    await throttle_domain("https://domain-a.com/page", delay=1.0)

    # Domínio B deve ser imediato (não sofre throttle do A)
    t0 = time.monotonic()
    await throttle_domain("https://domain-b.com/page", delay=1.0)
    elapsed = time.monotonic() - t0

    assert elapsed < 0.1, f"Domínio B sofreu throttle do A ({elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_subdomains_throttled_independently():
    """Subdomínios são tratados como domínios distintos (comportamento esperado pelo urlparse)."""
    _clear_domain_cache()
    from ecosystem_scraper import throttle_domain

    await throttle_domain("https://blog.example.com/a", delay=1.0)

    t0 = time.monotonic()
    await throttle_domain("https://shop.example.com/a", delay=1.0)
    elapsed = time.monotonic() - t0

    # blog.example.com e shop.example.com são hostnomes distintos
    assert elapsed < 0.1, f"Subdomínios interferem entre si ({elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_delay_zero_never_waits():
    """delay=0 nunca espera, útil para bypass em testes."""
    _clear_domain_cache()
    from ecosystem_scraper import throttle_domain

    await throttle_domain("https://fast.com/p1", delay=0)

    t0 = time.monotonic()
    await throttle_domain("https://fast.com/p2", delay=0)
    elapsed = time.monotonic() - t0

    assert elapsed < 0.05, f"delay=0 ainda esperou {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_timestamp_updated_even_when_no_wait():
    """O timestamp é atualizado mesmo quando não há espera."""
    _clear_domain_cache()
    import ecosystem_scraper
    from ecosystem_scraper import throttle_domain

    await throttle_domain("https://ts-check.com/p", delay=0.5)
    ts1 = ecosystem_scraper._domain_timestamps.get("ts-check.com", 0.0)

    await asyncio.sleep(0.6)  # passa o delay completo
    await throttle_domain("https://ts-check.com/p2", delay=0.5)
    ts2 = ecosystem_scraper._domain_timestamps.get("ts-check.com", 0.0)

    assert ts2 > ts1, "Timestamp não foi atualizado na segunda chamada"


def test_crawl_delay_exported():
    """CRAWL_DELAY está exportado com valor razoável (≥1s)."""
    from ecosystem_scraper import CRAWL_DELAY

    assert isinstance(CRAWL_DELAY, float)
    assert CRAWL_DELAY >= 1.0, f"CRAWL_DELAY muito pequeno: {CRAWL_DELAY}s"
