"""
Smoke tests para services/local_search.py.

Cobre:
  - Importação sem NameError (regressão do bug: log não definido)
  - Funções puras que não dependem de DB ou Ollama
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Importação — regressão do NameError em log
# ---------------------------------------------------------------------------

class TestImport:
    def test_module_imports_without_error(self):
        """Garante que 'log' está definido — regressão do NameError que abortava buscas."""
        import services.local_search as ls
        assert hasattr(ls, "log"), "log deve estar definido no módulo"

    def test_log_is_logger_instance(self):
        import logging
        import services.local_search as ls
        assert isinstance(ls.log, logging.Logger)


# ---------------------------------------------------------------------------
# _sanitize_fts — função pura, sem IO
# ---------------------------------------------------------------------------

class TestSanitizeFts:
    def _sanitize(self, q: str) -> str:
        from services.local_search import _sanitize_fts
        return _sanitize_fts(q)

    def test_plain_query_unchanged(self):
        assert self._sanitize("python linguística") == "python linguística"

    def test_strips_parens_and_colons(self):
        # _sanitize_fts remove ( ) : ^ mas preserva palavras como AND/OR/NOT
        result = self._sanitize("(python) tutorial:avançado")
        assert "(" not in result
        assert ")" not in result
        assert ":" not in result
        assert "python"   in result
        assert "tutorial" in result

    def test_empty_string_returns_empty(self):
        assert self._sanitize("") == ""

    def test_does_not_crash_on_special_chars(self):
        self._sanitize("(parênteses) [colchetes] {chaves} *asterisco*")


# ---------------------------------------------------------------------------
# _plain_tokens — função pura, sem IO
# ---------------------------------------------------------------------------

class TestPlainTokens:
    def _tokens(self, text: str) -> list[str]:
        from services.local_search import _plain_tokens
        return _plain_tokens(text)

    def test_splits_on_whitespace(self):
        assert self._tokens("hello world") == ["hello", "world"]

    def test_preserves_case(self):
        # _plain_tokens não lowercaseia — preserva casing original
        result = self._tokens("Python LINGUÍSTICA")
        assert "Python"     in result
        assert "LINGUÍSTICA" in result

    def test_empty_string_returns_empty_list(self):
        assert self._tokens("") == []

    def test_preserves_short_tokens(self):
        # _plain_tokens não filtra tokens curtos
        result = self._tokens("a bb ccc")
        assert "a"   in result
        assert "bb"  in result
        assert "ccc" in result


# ---------------------------------------------------------------------------
# _rrf — combinação de listas de resultados, sem IO
# ---------------------------------------------------------------------------

class TestRrf:
    def _make_results(self, urls: list[str]):
        from services.web_search import SearchResult
        return [
            SearchResult(url=u, title=u, snippet="", score=1.0, source="test")
            for u in urls
        ]

    def test_empty_lists_returns_empty(self):
        from services.local_search import _rrf
        assert _rrf([[], []]) == []

    def test_deduplicates_by_url(self):
        from services.local_search import _rrf
        a = self._make_results(["http://x.com", "http://y.com"])
        b = self._make_results(["http://x.com", "http://z.com"])
        result = _rrf([a, b])
        urls = [r.url for r in result]
        assert len(urls) == len(set(urls)), "URLs duplicadas devem ser removidas"

    def test_result_length_bounded_by_unique_urls(self):
        from services.local_search import _rrf
        a = self._make_results(["http://a.com"])
        b = self._make_results(["http://b.com"])
        result = _rrf([a, b])
        assert len(result) == 2
