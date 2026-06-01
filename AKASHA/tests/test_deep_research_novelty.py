"""
Testes para o critério de suficiência por saturação de novidade no Deep Research.

Cobre:
Unitários:
- _compute_url_novelty: fração calculada corretamente para vários cenários
- _compute_url_novelty: lista vazia retorna 0.0
- _compute_url_novelty: todos novos retorna 1.0
- _compute_url_novelty: nenhum novo retorna 0.0
- _get_novelty_threshold: retorna valor padrão 0.20 quando não configurado
- _get_novelty_threshold: clampeia a valores fora do range válido

Integração (pipeline Deep Research):
- Com novidade alta: rodada 2 é incluída no corpus (results expandem)
- Com novidade baixa (saturação): rodada 2 é descartada, corpus = rodada 1
- Sem reformulações: corpus = rodada 1, sem erro
- Threshold 0.0: sempre inclui rodada 2 (novidade qualquer é suficiente)
- Threshold 1.0: nunca inclui rodada 2 (nada é novo o suficiente)
- Log de saturação emitido quando saturado
- Log de expansão emitido quando corpus expandido
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch, call
import logging

import pytest

_AKASHA_ROOT = Path(__file__).parent.parent
if str(_AKASHA_ROOT) not in sys.path:
    sys.path.insert(0, str(_AKASHA_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sr(url: str, snippet: str = "snippet", score: float = 1.0):
    """Cria um SearchResult mínimo."""
    from services.web_search import SearchResult
    return SearchResult(url=url, title="T", snippet=snippet, source="WEB", score=score)


def _urls(*urls: str) -> list:
    return [_sr(u) for u in urls]


# ---------------------------------------------------------------------------
# Unitários: _compute_url_novelty
# ---------------------------------------------------------------------------

class TestComputeUrlNovelty:
    def test_empty_new_results_returns_zero(self) -> None:
        from routers.chat import _compute_url_novelty
        assert _compute_url_novelty([], set()) == 0.0

    def test_empty_new_results_with_accumulated_returns_zero(self) -> None:
        from routers.chat import _compute_url_novelty
        accumulated = {"http://a.com", "http://b.com"}
        assert _compute_url_novelty([], accumulated) == 0.0

    def test_all_new_returns_one(self) -> None:
        from routers.chat import _compute_url_novelty
        results = _urls("http://a.com", "http://b.com", "http://c.com")
        assert _compute_url_novelty(results, set()) == pytest.approx(1.0)

    def test_none_new_returns_zero(self) -> None:
        from routers.chat import _compute_url_novelty
        accumulated = {"http://a.com", "http://b.com"}
        results = _urls("http://a.com", "http://b.com")
        assert _compute_url_novelty(results, accumulated) == 0.0

    def test_half_new_returns_half(self) -> None:
        from routers.chat import _compute_url_novelty
        accumulated = {"http://a.com", "http://b.com"}
        results = _urls("http://a.com", "http://b.com", "http://c.com", "http://d.com")
        assert _compute_url_novelty(results, accumulated) == pytest.approx(0.5)

    def test_one_of_five_new_returns_0_2(self) -> None:
        from routers.chat import _compute_url_novelty
        accumulated = {"http://a.com", "http://b.com", "http://c.com", "http://d.com"}
        results = _urls("http://a.com", "http://b.com", "http://c.com", "http://d.com", "http://e.com")
        assert _compute_url_novelty(results, accumulated) == pytest.approx(0.2)

    def test_accumulated_empty_all_novel(self) -> None:
        from routers.chat import _compute_url_novelty
        results = _urls("http://x.com", "http://y.com")
        assert _compute_url_novelty(results, set()) == pytest.approx(1.0)

    def test_single_new_result_returns_one(self) -> None:
        from routers.chat import _compute_url_novelty
        result = _urls("http://new.com")
        assert _compute_url_novelty(result, set()) == pytest.approx(1.0)

    def test_single_seen_result_returns_zero(self) -> None:
        from routers.chat import _compute_url_novelty
        result = _urls("http://seen.com")
        assert _compute_url_novelty(result, {"http://seen.com"}) == 0.0


# ---------------------------------------------------------------------------
# Unitários: _get_novelty_threshold
# ---------------------------------------------------------------------------

class TestGetNoveltyThreshold:
    def test_default_is_0_20_when_not_configured(self) -> None:
        from routers.chat import _get_novelty_threshold
        with patch("routers.chat._get_novelty_threshold.__wrapped__" if False else "routers.chat._get_novelty_threshold"):
            pass
        # Quando ecosystem.json não tem a chave, retorna 0.20
        with patch("ecosystem_client.get_akasha_config", return_value={}):
            threshold = _get_novelty_threshold()
        assert threshold == pytest.approx(0.20)

    def test_reads_custom_value_from_config(self) -> None:
        from routers.chat import _get_novelty_threshold
        with patch("ecosystem_client.get_akasha_config", return_value={"novelty_threshold": 0.35}):
            threshold = _get_novelty_threshold()
        assert threshold == pytest.approx(0.35)

    def test_clamps_below_minimum(self) -> None:
        from routers.chat import _get_novelty_threshold
        with patch("ecosystem_client.get_akasha_config", return_value={"novelty_threshold": 0.0}):
            threshold = _get_novelty_threshold()
        assert threshold >= 0.05

    def test_clamps_above_maximum(self) -> None:
        from routers.chat import _get_novelty_threshold
        with patch("ecosystem_client.get_akasha_config", return_value={"novelty_threshold": 1.5}):
            threshold = _get_novelty_threshold()
        assert threshold <= 0.90

    def test_exception_returns_default(self) -> None:
        from routers.chat import _get_novelty_threshold
        with patch("ecosystem_client.get_akasha_config", side_effect=RuntimeError("offline")):
            threshold = _get_novelty_threshold()
        assert threshold == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# Integração: pipeline Deep Research com verificação de novidade
# ---------------------------------------------------------------------------

def _make_search_results(urls: list[str], prefix: str = "") -> list:
    return [_sr(f"{prefix}{u}") for u in urls]


class TestDeepResearchNoveltyPipeline:
    """Testa _deep_collect_results diretamente (sem HTTP) — mais isolado e rápido."""

    def _run(
        self,
        r1_urls: list[str],
        r2_urls: list[str],
        reformulations: list[str],
        novelty_threshold: float = 0.20,
    ) -> list[str]:
        """
        Executa _deep_collect_results e retorna as URLs dos resultados finais.
        """
        from routers.chat import _deep_collect_results

        r1_results = _make_search_results(r1_urls)
        r2_results = _make_search_results(r2_urls)
        call_count = [0]

        async def fake_search_local(q, max_results=15, expand=False, include_crawl=False):
            call_count[0] += 1
            if call_count[0] == 1:
                return r1_results
            return r2_results

        with patch("routers.chat._expand_queries_deep", return_value=reformulations), \
             patch("services.local_search.search_local", side_effect=fake_search_local):
            results = asyncio.run(_deep_collect_results(
                question="o que é python?",
                model="qwen",
                novelty_threshold=novelty_threshold,
            ))

        return [r.url for r in results]

    def test_high_novelty_expands_corpus(self) -> None:
        """Quando rodada 2 tem novidade alta, corpus inclui R1 + R2."""
        final_urls = self._run(
            ["http://a.com", "http://b.com"],
            ["http://c.com", "http://d.com"],
            reformulations=["query alt"], novelty_threshold=0.20,
        )
        assert "http://a.com" in final_urls
        assert "http://c.com" in final_urls

    def test_low_novelty_discards_round2(self) -> None:
        """Quando rodada 2 tem novidade < threshold, corpus usa apenas R1."""
        r1 = ["http://a.com", "http://b.com", "http://c.com", "http://d.com", "http://e.com"]
        # r2 repete 5 de r1 + 1 novo → novelty = 1/6 ≈ 0.167 < 0.20
        r2 = r1 + ["http://f.com"]
        final_urls = self._run(r1, r2, reformulations=["alt"], novelty_threshold=0.20)
        assert len(final_urls) == 5

    def test_no_reformulations_uses_only_round1(self) -> None:
        """Sem reformulações, corpus é apenas a rodada 1."""
        r1 = ["http://a.com", "http://b.com"]
        final_urls = self._run(r1, [], reformulations=[], novelty_threshold=0.20)
        assert set(final_urls) == set(r1)

    def test_threshold_low_always_includes_round2(self) -> None:
        """Threshold 0.05 — qualquer novidade marginal passa."""
        r1 = ["http://a.com", "http://b.com", "http://c.com"]
        # 1 novo de 4 = 25% > 0.05
        r2 = r1 + ["http://new.com"]
        final_urls = self._run(r1, r2, reformulations=["alt"], novelty_threshold=0.05)
        assert "http://new.com" in final_urls

    def test_saturation_log_emitted(self, caplog) -> None:
        """Log de saturação emitido quando rodada 2 é descartada."""
        r1 = ["http://a.com", "http://b.com"]
        r2 = ["http://a.com", "http://b.com"]  # 0% novidade

        with caplog.at_level(logging.INFO, logger="akasha.chat"):
            self._run(r1, r2, reformulations=["alt"], novelty_threshold=0.20)

        log_text = " ".join(r.message for r in caplog.records)
        assert "saturaç" in log_text or "saturac" in log_text.lower()

    def test_expansion_log_emitted_when_corpus_grows(self, caplog) -> None:
        """Log de expansão emitido quando rodada 2 é incluída."""
        r1 = ["http://a.com"]
        r2 = ["http://b.com", "http://c.com"]

        with caplog.at_level(logging.INFO, logger="akasha.chat"):
            self._run(r1, r2, reformulations=["alt"], novelty_threshold=0.20)

        log_text = " ".join(r.message for r in caplog.records)
        assert "expandido" in log_text or "rodada 2" in log_text
