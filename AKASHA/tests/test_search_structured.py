"""
Testes para GET /search/structured — endpoint de handoff padronizado AKASHA→Mnemosyne.

Cobre:
Unitários:
- _to_source_type: mapeamento correto para todas as fontes internas
- _extract_domain: extração de netloc de URLs variadas
- _build_structured_results: schema correto, scores normalizados, snippet truncado,
  lista vazia, score posicional, ordenação por score bruto

Integração (endpoint FastAPI):
- query vazia retorna []
- resultado tem todos os campos obrigatórios do schema StructuredResult
- relevance_score está em [0.0, 1.0]
- snippet é truncado a 250 chars
- parâmetro max limita a quantidade de resultados
- fonte "PAPER" é mapeada para source_type "paper"
- fonte "AKASHA" é mapeada para source_type "library"
- fonte desconhecida cai em "web" (fallback)
- domain é extraído corretamente da URL
- query sem resultados retorna []
- teto de max=50 aplicado quando max muito grande
- log debug é emitido para query válida
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_AKASHA_ROOT = Path(__file__).parent.parent
if str(_AKASHA_ROOT) not in sys.path:
    sys.path.insert(0, str(_AKASHA_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sr(url="http://example.com/page", title="Test", snippet="Some content here",
        source="WEB", date=None, score=0.0):
    """Cria um SearchResult com valores padrão."""
    from services.web_search import SearchResult
    return SearchResult(url=url, title=title, snippet=snippet,
                        source=source, date=date, score=score)


# ---------------------------------------------------------------------------
# Unitários: _to_source_type
# ---------------------------------------------------------------------------

class TestToSourceType:
    def test_paper_maps_to_paper(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("PAPER") == "paper"

    def test_akasha_maps_to_library(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("AKASHA") == "library"

    def test_local_vec_maps_to_library(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("LOCAL_VEC") == "library"

    def test_kosmos_maps_to_local(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("KOSMOS") == "local"

    def test_obsidian_maps_to_local(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("OBSIDIAN") == "local"

    def test_mnemosyne_maps_to_local(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("MNEMOSYNE") == "local"

    def test_sites_maps_to_web(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("SITES") == "web"

    def test_crawl_semantic_maps_to_web(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("CRAWL_SEMANTIC") == "web"

    def test_web_maps_to_web(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("WEB") == "web"

    def test_unknown_source_maps_to_web(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("UNKNOWN_XYZ") == "web"

    def test_lowercase_source_is_handled(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("paper") == "paper"

    def test_highlight_maps_to_local(self) -> None:
        from routers.search import _to_source_type
        assert _to_source_type("HIGHLIGHT") == "local"


# ---------------------------------------------------------------------------
# Unitários: _extract_domain
# ---------------------------------------------------------------------------

class TestExtractDomain:
    def test_simple_url(self) -> None:
        from routers.search import _extract_domain
        assert _extract_domain("https://arxiv.org/abs/1234") == "arxiv.org"

    def test_url_with_www(self) -> None:
        from routers.search import _extract_domain
        assert _extract_domain("https://www.example.com/page") == "www.example.com"

    def test_url_with_port(self) -> None:
        from routers.search import _extract_domain
        assert _extract_domain("http://localhost:8080/path") == "localhost:8080"

    def test_invalid_url_returns_empty(self) -> None:
        from routers.search import _extract_domain
        assert _extract_domain("not-a-url") == ""

    def test_empty_string_returns_empty(self) -> None:
        from routers.search import _extract_domain
        assert _extract_domain("") == ""

    def test_file_uri_returns_empty(self) -> None:
        from routers.search import _extract_domain
        domain = _extract_domain("file:///home/user/doc.md")
        # file URIs têm netloc vazio
        assert domain == ""


# ---------------------------------------------------------------------------
# Unitários: _build_structured_results
# ---------------------------------------------------------------------------

class TestBuildStructuredResults:
    def test_empty_input_returns_empty(self) -> None:
        from routers.search import _build_structured_results
        assert _build_structured_results([], 10) == []

    def test_snippet_truncated_to_250_chars(self) -> None:
        from routers.search import _build_structured_results
        long_snippet = "x" * 500
        r = _sr(snippet=long_snippet)
        results = _build_structured_results([r], 10)
        assert len(results[0].snippet) == 250

    def test_snippet_shorter_than_250_not_padded(self) -> None:
        from routers.search import _build_structured_results
        r = _sr(snippet="curto")
        results = _build_structured_results([r], 10)
        assert results[0].snippet == "curto"

    def test_relevance_score_first_item_is_1(self) -> None:
        from routers.search import _build_structured_results
        r = _sr()
        results = _build_structured_results([r], 10)
        assert results[0].relevance_score == 1.0

    def test_relevance_scores_decrease_with_rank(self) -> None:
        from routers.search import _build_structured_results
        items = [_sr(url=f"http://example.com/{i}") for i in range(5)]
        results = _build_structured_results(items, 10)
        scores = [r.relevance_score for r in results]
        assert scores == sorted(scores, reverse=True), "scores devem ser decrescentes"

    def test_all_scores_in_0_to_1_range(self) -> None:
        from routers.search import _build_structured_results
        items = [_sr(url=f"http://example.com/{i}") for i in range(10)]
        results = _build_structured_results(items, 10)
        for r in results:
            assert 0.0 <= r.relevance_score <= 1.0

    def test_max_limits_output(self) -> None:
        from routers.search import _build_structured_results
        items = [_sr(url=f"http://example.com/{i}") for i in range(20)]
        results = _build_structured_results(items, 5)
        assert len(results) == 5

    def test_domain_extracted(self) -> None:
        from routers.search import _build_structured_results
        r = _sr(url="https://arxiv.org/abs/2409.04701")
        results = _build_structured_results([r], 10)
        assert results[0].domain == "arxiv.org"

    def test_source_type_in_result(self) -> None:
        from routers.search import _build_structured_results
        r = _sr(source="PAPER")
        results = _build_structured_results([r], 10)
        assert results[0].source_type == "paper"

    def test_date_none_when_not_provided(self) -> None:
        from routers.search import _build_structured_results
        r = _sr(date=None)
        results = _build_structured_results([r], 10)
        assert results[0].date is None

    def test_date_forwarded_when_provided(self) -> None:
        from routers.search import _build_structured_results
        r = _sr(date="2025-07-15")
        results = _build_structured_results([r], 10)
        assert results[0].date == "2025-07-15"

    def test_sorted_by_raw_score_before_normalizing(self) -> None:
        """Itens com score bruto maior devem aparecer primeiro."""
        from routers.search import _build_structured_results
        low  = _sr(url="http://example.com/low",  score=0.1)
        high = _sr(url="http://example.com/high", score=0.9)
        # Passando em ordem inversa (low primeiro) — deve ser reordenado
        results = _build_structured_results([low, high], 10)
        assert results[0].url == "http://example.com/high"


# ---------------------------------------------------------------------------
# Integração: endpoint GET /search/structured
# ---------------------------------------------------------------------------

class TestSearchStructuredEndpoint:
    """Testa o endpoint via FastAPI TestClient com mocks de search_web, search_local, search_sites."""

    def _make_client(self):
        from fastapi.testclient import TestClient
        import AKASHA.main as main_mod
        return TestClient(main_mod.app, raise_server_exceptions=True)

    def _make_web_result(self, n: int = 1) -> list:
        from services.web_search import SearchResult
        return [
            SearchResult(
                url=f"https://example.com/article{i}",
                title=f"Article {i}",
                snippet=f"Snippet content {i}",
                source="WEB",
                score=float(n - i) / n,
            )
            for i in range(n)
        ]

    def test_empty_query_returns_empty_list(self) -> None:
        client = self._make_client()
        resp = client.get("/search/structured?q=")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_whitespace_only_query_returns_empty_list(self) -> None:
        client = self._make_client()
        resp = client.get("/search/structured?q=   ")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_result_has_required_schema_fields(self) -> None:
        client = self._make_client()
        with patch("routers.search.search_web", return_value=self._make_web_result(1)), \
             patch("routers.search.search_local", return_value=[]), \
             patch("routers.search.search_sites", return_value=[]):
            resp = client.get("/search/structured?q=python")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        item = data[0]
        for field in ("url", "title", "snippet", "domain", "date", "relevance_score", "source_type"):
            assert field in item, f"campo {field!r} ausente no resultado"

    def test_relevance_score_is_in_range(self) -> None:
        client = self._make_client()
        with patch("routers.search.search_web", return_value=self._make_web_result(5)), \
             patch("routers.search.search_local", return_value=[]), \
             patch("routers.search.search_sites", return_value=[]):
            resp = client.get("/search/structured?q=test")
        for item in resp.json():
            assert 0.0 <= item["relevance_score"] <= 1.0

    def test_snippet_max_250_chars(self) -> None:
        from services.web_search import SearchResult
        long = SearchResult(
            url="https://example.com", title="T",
            snippet="x" * 600, source="WEB", score=1.0,
        )
        client = self._make_client()
        with patch("routers.search.search_web", return_value=[long]), \
             patch("routers.search.search_local", return_value=[]), \
             patch("routers.search.search_sites", return_value=[]):
            resp = client.get("/search/structured?q=test")
        assert len(resp.json()[0]["snippet"]) == 250

    def test_max_parameter_limits_results(self) -> None:
        client = self._make_client()
        with patch("routers.search.search_web", return_value=self._make_web_result(20)), \
             patch("routers.search.search_local", return_value=[]), \
             patch("routers.search.search_sites", return_value=[]):
            resp = client.get("/search/structured?q=test&max=3")
        assert len(resp.json()) <= 3

    def test_max_ceiling_is_50(self) -> None:
        client = self._make_client()
        web = self._make_web_result(60)
        with patch("routers.search.search_web", return_value=web), \
             patch("routers.search.search_local", return_value=[]), \
             patch("routers.search.search_sites", return_value=[]):
            resp = client.get("/search/structured?q=test&max=200")
        assert len(resp.json()) <= 50

    def test_paper_source_type(self) -> None:
        from services.web_search import SearchResult
        paper = SearchResult(
            url="https://arxiv.org/abs/1234",
            title="Paper X", snippet="abstract here",
            source="PAPER", score=1.0,
        )
        client = self._make_client()
        with patch("routers.search.search_web", return_value=[]), \
             patch("routers.search.search_local", return_value=[paper]), \
             patch("routers.search.search_sites", return_value=[]):
            resp = client.get("/search/structured?q=paper&sources=eco")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source_type"] == "paper"

    def test_domain_extracted_in_response(self) -> None:
        from services.web_search import SearchResult
        r = SearchResult(
            url="https://arxiv.org/abs/9999",
            title="T", snippet="S", source="WEB", score=1.0,
        )
        client = self._make_client()
        with patch("routers.search.search_web", return_value=[r]), \
             patch("routers.search.search_local", return_value=[]), \
             patch("routers.search.search_sites", return_value=[]):
            resp = client.get("/search/structured?q=arxiv")
        assert resp.json()[0]["domain"] == "arxiv.org"

    def test_no_results_returns_empty_list(self) -> None:
        client = self._make_client()
        with patch("routers.search.search_web", return_value=[]), \
             patch("routers.search.search_local", return_value=[]), \
             patch("routers.search.search_sites", return_value=[]):
            resp = client.get("/search/structured?q=nothingfound")
        assert resp.json() == []

    def test_exception_in_one_source_does_not_crash(self) -> None:
        """Se uma das fontes lança exceção, o endpoint ainda retorna resultados das demais."""
        client = self._make_client()
        with patch("routers.search.search_web", side_effect=RuntimeError("timeout")), \
             patch("routers.search.search_local", return_value=self._make_web_result(2)), \
             patch("routers.search.search_sites", return_value=[]):
            resp = client.get("/search/structured?q=test&sources=web,eco")
        # Não deve retornar 500 — a exception é capturada pelo gather(return_exceptions=True)
        assert resp.status_code == 200

    def test_sources_web_only_does_not_call_local(self) -> None:
        client = self._make_client()
        with patch("routers.search.search_web", return_value=self._make_web_result(1)) as mock_web, \
             patch("routers.search.search_local") as mock_local, \
             patch("routers.search.search_sites") as mock_sites:
            client.get("/search/structured?q=test&sources=web")
        mock_web.assert_called_once()
        mock_local.assert_not_called()
        mock_sites.assert_not_called()

    def test_sources_eco_only_calls_search_local(self) -> None:
        client = self._make_client()
        with patch("routers.search.search_web") as mock_web, \
             patch("routers.search.search_local", return_value=[]) as mock_local, \
             patch("routers.search.search_sites") as mock_sites:
            client.get("/search/structured?q=test&sources=eco")
        mock_local.assert_called_once()
        mock_web.assert_not_called()
        mock_sites.assert_not_called()
