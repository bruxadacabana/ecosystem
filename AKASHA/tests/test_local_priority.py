"""
Testes para a priorização de índice local sobre busca web (item 10).

Cobre:
  - _local_qualifies_for_priority: contagem e score mínimo
  - 5 resultados locais → web adiada
  - 2 resultados locais → web síncrona
  - score abaixo do threshold → web síncrona
"""
from __future__ import annotations

import pytest


def _make_results(n: int, score: float = 0.0):
    from services.web_search import SearchResult
    return [
        SearchResult(title=f"r{i}", url=f"https://example{i}.com", snippet="", score=score)
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# _local_qualifies_for_priority
# ---------------------------------------------------------------------------

class TestLocalQualifiesForPriority:

    def _q(self, results, **kwargs):
        from routers.search import _local_qualifies_for_priority
        return _local_qualifies_for_priority(results, **kwargs)

    def test_five_results_qualifies(self):
        """5 resultados locais → qualifica (web pode ser adiada)."""
        assert self._q(_make_results(5)) is True

    def test_more_than_five_qualifies(self):
        assert self._q(_make_results(10)) is True

    def test_two_results_does_not_qualify(self):
        """2 resultados locais → não qualifica (web síncrona)."""
        assert self._q(_make_results(2)) is False

    def test_zero_results_does_not_qualify(self):
        assert self._q(_make_results(0)) is False

    def test_exactly_threshold_qualifies(self):
        """Exatamente min_n=5 resultados → qualifica."""
        assert self._q(_make_results(5), min_n=5) is True

    def test_one_below_threshold_does_not_qualify(self):
        assert self._q(_make_results(4), min_n=5) is False

    def test_custom_threshold(self):
        assert self._q(_make_results(3), min_n=3) is True
        assert self._q(_make_results(2), min_n=3) is False

    # --- Score abaixo do threshold → web síncrona ---

    def test_low_score_does_not_qualify(self):
        """5 resultados com score baixo → não qualifica quando min_score definido."""
        results = _make_results(5, score=0.1)
        assert self._q(results, min_n=5, min_score=0.6) is False

    def test_high_score_qualifies(self):
        """5 resultados com score alto → qualifica."""
        results = _make_results(5, score=0.9)
        assert self._q(results, min_n=5, min_score=0.6) is True

    def test_mixed_scores_not_enough_qualifying(self):
        """3 com score alto, 2 com score baixo → não qualifica (min_n=5, min_score=0.6)."""
        from services.web_search import SearchResult
        results = (
            [SearchResult(title=f"h{i}", url=f"https://h{i}.com", snippet="", score=0.9) for i in range(3)]
            + [SearchResult(title=f"l{i}", url=f"https://l{i}.com", snippet="", score=0.2) for i in range(2)]
        )
        assert self._q(results, min_n=5, min_score=0.6) is False

    def test_zero_min_score_ignores_score(self):
        """min_score=0.0 (padrão) → só conta, sem verificar score."""
        results = _make_results(5, score=0.0)  # score mínimo possível
        assert self._q(results, min_score=0.0) is True


# ---------------------------------------------------------------------------
# score field em SearchResult
# ---------------------------------------------------------------------------

def test_search_result_has_score_field():
    """SearchResult deve ter campo score com default 0.0."""
    from services.web_search import SearchResult
    r = SearchResult(title="t", url="https://a.com", snippet="")
    assert hasattr(r, "score")
    assert r.score == 0.0


def test_search_result_score_explicit():
    from services.web_search import SearchResult
    r = SearchResult(title="t", url="https://a.com", snippet="", score=0.75)
    assert r.score == 0.75


def test_search_result_model_dump_includes_score():
    """model_dump() deve incluir score para serialização no cache."""
    from services.web_search import SearchResult
    r = SearchResult(title="t", url="https://a.com", snippet="", score=0.5)
    d = r.model_dump()
    assert "score" in d
    assert d["score"] == 0.5


def test_search_result_backward_compat_no_score():
    """SearchResult criado sem score deve usar default 0.0."""
    from services.web_search import SearchResult
    r = SearchResult(**{"title": "t", "url": "https://a.com", "snippet": ""})
    assert r.score == 0.0


# ---------------------------------------------------------------------------
# _get_local_priority_threshold
# ---------------------------------------------------------------------------

def test_get_local_priority_threshold_default():
    """Retorna 5 como default quando ecosystem_client não disponível."""
    from routers.search import _get_local_priority_threshold
    result = _get_local_priority_threshold()
    assert isinstance(result, int)
    assert result >= 1  # sempre positivo
