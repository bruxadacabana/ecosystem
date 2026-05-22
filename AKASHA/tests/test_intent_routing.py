"""
Testes para _get_intent_routing e _diversify_by_domain em routers/search.py.

Cobre:
  - _get_intent_routing: cada IntentTypeLexical → flag correta ativada
  - _get_intent_routing: informational + query curta (1 token) → wiki=False
  - _get_intent_routing: navigational → nenhuma flag ativa
  - _get_intent_routing: exploratory → nenhuma flag ativa
  - _diversify_by_domain: resultados do mesmo domínio → cortados em max_per_domain
  - _diversify_by_domain: domínios distintos → nenhum resultado removido
  - _diversify_by_domain: lista vazia → lista vazia
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace


def _route(intent: str, query: str) -> dict:
    from routers.search import _get_intent_routing
    return _get_intent_routing(intent, query)


def _diversify(results, max_per_domain: int = 2):
    from routers.search import _diversify_by_domain
    return _diversify_by_domain(results, max_per_domain)


def _make_result(url: str) -> SimpleNamespace:
    return SimpleNamespace(url=url, title="t", snippet="s", score=0.0)


# ---------------------------------------------------------------------------
# _get_intent_routing — flags de roteamento
# ---------------------------------------------------------------------------

class TestGetIntentRouting:

    def test_informational_two_tokens_wiki_true(self):
        r = _route("informational", "what is python")
        assert r["wiki"] is True
        assert r["images"] is False
        assert r["weather"] is False
        assert r["translation"] is False
        assert r["video"] is False

    def test_informational_one_token_wiki_false(self):
        """Query com 1 token → wiki=False (ambígua demais para Wikipedia card)."""
        r = _route("informational", "python")
        assert r["wiki"] is False

    def test_visual_images_true(self):
        r = _route("visual", "python logo image")
        assert r["images"] is True
        assert r["wiki"] is False

    def test_weather_flag_true(self):
        r = _route("weather", "tempo em Lisboa")
        assert r["weather"] is True
        assert r["images"] is False

    def test_translation_flag_true(self):
        r = _route("translation", "como se diz hello em português")
        assert r["translation"] is True
        assert r["video"] is False

    def test_video_flag_true(self):
        r = _route("video", "python tutorial youtube")
        assert r["video"] is True
        assert r["wiki"] is False

    def test_navigational_no_flags(self):
        """navigational → nenhum widget vertical ativado."""
        r = _route("navigational", "github.com")
        assert not any(r.values())

    def test_exploratory_no_flags(self):
        """exploratory → nenhum widget vertical ativado."""
        r = _route("exploratory", "best practices web development modern")
        assert not any(r.values())

    def test_returns_all_expected_keys(self):
        """O dict deve ter exatamente as 5 chaves esperadas."""
        r = _route("informational", "what is machine learning")
        assert set(r.keys()) == {"wiki", "images", "weather", "translation", "video"}

    def test_empty_query_informational_wiki_false(self):
        """Query vazia → wiki=False (0 tokens)."""
        r = _route("informational", "")
        assert r["wiki"] is False

    def test_exactly_two_tokens_wiki_true(self):
        """Exatamente 2 tokens → wiki=True para informational."""
        r = _route("informational", "what is")
        assert r["wiki"] is True

    def test_only_one_flag_per_intent(self):
        """Cada intent ativa no máximo uma flag."""
        for intent, query in [
            ("visual",      "foto gato"),
            ("weather",     "clima amanhã"),
            ("translation", "traduzir hello"),
            ("video",       "assistir tutorial"),
        ]:
            r = _route(intent, query)
            active = sum(1 for v in r.values() if v)
            assert active == 1, f"intent={intent} ativou {active} flags: {r}"


# ---------------------------------------------------------------------------
# _diversify_by_domain — diversidade de fontes
# ---------------------------------------------------------------------------

class TestDiversifyByDomain:

    def test_empty_list_returns_empty(self):
        assert _diversify([]) == []

    def test_all_distinct_domains_unchanged(self):
        """Todos de domínios distintos → nenhum removido."""
        results = [
            _make_result("https://alpha.com/page"),
            _make_result("https://beta.com/page"),
            _make_result("https://gamma.com/page"),
        ]
        out = _diversify(results)
        assert len(out) == 3

    def test_same_domain_capped_at_max(self):
        """Mais de max_per_domain resultados do mesmo domínio → cortados."""
        results = [_make_result(f"https://example.com/page{i}") for i in range(5)]
        out = _diversify(results, max_per_domain=2)
        assert len(out) == 2

    def test_default_max_is_two(self):
        results = [_make_result(f"https://example.com/p{i}") for i in range(4)]
        out = _diversify(results)
        assert len(out) == 2

    def test_mixed_domains_keeps_up_to_max_each(self):
        """2 domínios, 3 results cada, max=2 → 4 results total."""
        results = (
            [_make_result(f"https://alpha.com/p{i}") for i in range(3)]
            + [_make_result(f"https://beta.com/p{i}") for i in range(3)]
        )
        out = _diversify(results, max_per_domain=2)
        assert len(out) == 4

    def test_www_prefix_stripped(self):
        """www.example.com e example.com são tratados como o mesmo domínio."""
        results = [
            _make_result("https://www.example.com/p1"),
            _make_result("https://example.com/p2"),
            _make_result("https://example.com/p3"),
        ]
        out = _diversify(results, max_per_domain=1)
        assert len(out) == 1

    def test_order_preserved(self):
        """Ordem original deve ser mantida (primeiros resultados têm prioridade)."""
        results = [
            _make_result("https://alpha.com/first"),
            _make_result("https://beta.com/first"),
            _make_result("https://alpha.com/second"),
            _make_result("https://gamma.com/first"),
        ]
        out = _diversify(results, max_per_domain=1)
        urls = [r.url for r in out]
        assert "https://alpha.com/first" in urls
        assert "https://alpha.com/second" not in urls
        assert "https://beta.com/first" in urls
        assert "https://gamma.com/first" in urls

    def test_custom_max_per_domain(self):
        results = [_make_result(f"https://site.com/p{i}") for i in range(10)]
        out = _diversify(results, max_per_domain=3)
        assert len(out) == 3
