"""
Testes para Multilíngue 2 — integração da expansão multilíngue na busca web.

Cobre:
  - search_web: aceita param lang; inclui na chave de cache; passa para SearXNG
  - _fetch_searxng: passa language=lang quando lang não vazio; omite quando vazio
  - _resolve_lang_search:
      lang="" / "all" → usa config (search_languages vazio → query única, sem filtro)
      lang="auto" → expande quando LOGOS disponível
      lang="pt" → filtra SearXNG a pt, sem expansão
      LOGOS offline → fallback para query original
  - Merge de múltiplas variantes: deduplicação por URL; original primeiro
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _fetch_searxng — passa language param
# ---------------------------------------------------------------------------

class TestFetchSearxngLang:

    def _make_searxng_resp(self, results: list) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": results}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        return mock_client

    def test_passes_language_param_when_lang_set(self):
        """lang="pt" → SearXNG recebe language=pt na query."""
        from services.web_search import _fetch_searxng

        captured_params: list = []

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def _fake_get(url, params=None):
            captured_params.append(params or {})
            return mock_resp

        mock_client.get = _fake_get

        with patch("httpx.AsyncClient", return_value=mock_client):
            run(_fetch_searxng("python", 10, "http://localhost:8888", lang="pt"))

        assert len(captured_params) >= 1
        assert captured_params[0].get("language") == "pt"

    def test_omits_language_param_when_lang_empty(self):
        """lang="" → SearXNG não recebe language param."""
        from services.web_search import _fetch_searxng

        captured_params: list = []

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def _fake_get(url, params=None):
            captured_params.append(params or {})
            return mock_resp

        mock_client.get = _fake_get

        with patch("httpx.AsyncClient", return_value=mock_client):
            run(_fetch_searxng("python", 10, "http://localhost:8888", lang=""))

        assert "language" not in captured_params[0]


# ---------------------------------------------------------------------------
# search_web — lang na chave de cache
# ---------------------------------------------------------------------------

class TestSearchWebLang:

    def test_different_lang_gives_different_cache_key(self, monkeypatch):
        """search_web("q", lang="pt") e search_web("q", lang="en") têm caches distintos."""
        import services.web_search as _mod

        hashes_seen: list[str] = []

        orig_hash = _mod._query_hash

        def _spy_hash(key: str) -> str:
            hashes_seen.append(key)
            return orig_hash(key)

        monkeypatch.setattr(_mod, "_query_hash", _spy_hash)

        # Simula cache miss + busca real mocked
        monkeypatch.setattr(_mod._mem_cache, "get", lambda k: None)
        monkeypatch.setattr(_mod, "_get_db_cache", AsyncMock(return_value=None))
        monkeypatch.setattr(_mod, "_fetch_web", AsyncMock(return_value=[]))
        monkeypatch.setattr(_mod, "_set_db_cache", AsyncMock())
        monkeypatch.setattr(_mod, "_get_ttl_hours", AsyncMock(return_value=1))
        monkeypatch.setattr(_mod, "_filter_blocked", AsyncMock(side_effect=lambda x: x))

        run(_mod.search_web("python", lang="pt"))
        run(_mod.search_web("python", lang="en"))
        run(_mod.search_web("python"))

        # Chaves devem ser distintas
        assert len(set(hashes_seen)) == 3, (
            f"Esperava 3 chaves distintas, obteve {len(set(hashes_seen))}: {hashes_seen}"
        )

    def test_lang_passed_to_fetch_web(self, monkeypatch):
        """lang é passado para _fetch_web."""
        import services.web_search as _mod

        fetch_lang_calls: list[str] = []

        async def _fake_fetch(query, max_results, n_pages=1, lang=""):
            fetch_lang_calls.append(lang)
            return []

        monkeypatch.setattr(_mod._mem_cache, "get", lambda k: None)
        monkeypatch.setattr(_mod, "_get_db_cache", AsyncMock(return_value=None))
        monkeypatch.setattr(_mod, "_fetch_web", _fake_fetch)
        monkeypatch.setattr(_mod, "_set_db_cache", AsyncMock())
        monkeypatch.setattr(_mod, "_get_ttl_hours", AsyncMock(return_value=1))
        monkeypatch.setattr(_mod, "_filter_blocked", AsyncMock(side_effect=lambda x: x))

        run(_mod.search_web("query", lang="es"))

        assert "es" in fetch_lang_calls, "lang='es' deve ser passado para _fetch_web"


# ---------------------------------------------------------------------------
# _resolve_lang_search
# ---------------------------------------------------------------------------

class TestResolveLangSearch:

    def _make_search_web_mock(self, results=None):
        """Retorna mock de search_web que captura chamadas."""
        _results = results or []
        calls: list[dict] = []

        async def _mock(query, max_results=0, filetype="", n_pages=1, lang=""):
            calls.append({"query": query, "lang": lang})
            return _results

        return _mock, calls

    def test_no_lang_no_config_uses_original_query(self, monkeypatch):
        """lang="" + search_languages=[] → busca original sem filtro."""
        import services.query_multilang as _qm
        from services.web_search import SearchResult
        from routers.search import _resolve_lang_search

        search_calls: list[dict] = []

        async def _mock_search(query, max_results=0, filetype="", n_pages=1, lang=""):
            search_calls.append({"query": query, "lang": lang})
            return [SearchResult(title="R1", url="https://a.com", snippet="", source="WEB")]

        monkeypatch.setattr("routers.search.search_web", _mock_search)
        monkeypatch.setattr(_qm, "get_search_languages", lambda: [])
        monkeypatch.setattr(_qm, "expand_multilang", AsyncMock(return_value=["original"]))

        result = run(_resolve_lang_search(
            "original", "", inference_available=True,
            max_results=0, filetype="", n_pages=1,
        ))

        assert len(search_calls) == 1
        assert search_calls[0]["query"] == "original"
        assert search_calls[0]["lang"] == ""

    def test_specific_lang_filters_without_expansion(self, monkeypatch):
        """lang="pt" → lang="pt" passado para search_web, sem expansão."""
        import services.query_multilang as _qm
        from services.web_search import SearchResult
        from routers.search import _resolve_lang_search

        search_calls: list[dict] = []

        async def _mock_search(query, max_results=0, filetype="", n_pages=1, lang=""):
            search_calls.append({"query": query, "lang": lang})
            return []

        monkeypatch.setattr("routers.search.search_web", _mock_search)
        monkeypatch.setattr(_qm, "get_search_languages", lambda: [])
        monkeypatch.setattr(_qm, "expand_multilang", AsyncMock(return_value=["original"]))

        run(_resolve_lang_search(
            "pesquisa semântica", "pt", inference_available=False,
            max_results=0, filetype="", n_pages=1,
        ))

        assert len(search_calls) == 1
        assert search_calls[0]["lang"] == "pt"

    def test_logos_offline_falls_back_to_original(self, monkeypatch):
        """LOGOS offline (inference_available=False) → query original sem expansão."""
        import services.query_multilang as _qm
        from services.web_search import SearchResult
        from routers.search import _resolve_lang_search

        search_calls: list[dict] = []

        async def _mock_search(query, max_results=0, filetype="", n_pages=1, lang=""):
            search_calls.append({"query": query, "lang": lang})
            return []

        monkeypatch.setattr("routers.search.search_web", _mock_search)
        monkeypatch.setattr(_qm, "get_search_languages", lambda: ["pt", "en"])
        monkeypatch.setattr(_qm, "expand_multilang", AsyncMock(return_value=["original"]))

        run(_resolve_lang_search(
            "original", "", inference_available=False,
            max_results=0, filetype="", n_pages=1,
        ))

        # Com inference offline e expand_targets → como expand_multilang não é chamado,
        # _variants = [query], uma única chamada
        assert len(search_calls) == 1
        assert search_calls[0]["query"] == "original"

    def test_auto_expands_query_when_logos_online(self, monkeypatch):
        """lang="auto" + LOGOS online → expand_multilang é chamado."""
        import services.query_multilang as _qm
        from routers.search import _resolve_lang_search

        expand_called = []

        async def _fake_expand(query, targets):
            expand_called.append((query, targets))
            return [query, "semantic search"]

        search_calls: list[dict] = []

        async def _mock_search(query, max_results=0, filetype="", n_pages=1, lang=""):
            search_calls.append({"query": query, "lang": lang})
            return []

        monkeypatch.setattr("routers.search.search_web", _mock_search)
        monkeypatch.setattr(_qm, "get_search_languages", lambda: [])
        monkeypatch.setattr(_qm, "expand_multilang", _fake_expand)
        monkeypatch.setattr(_qm, "detect_language", lambda q: "pt")

        run(_resolve_lang_search(
            "pesquisa semântica", "auto", inference_available=True,
            max_results=0, filetype="", n_pages=1,
        ))

        assert len(expand_called) == 1, "expand_multilang deve ser chamado com lang='auto'"

    def test_merge_deduplicates_by_url(self, monkeypatch):
        """Múltiplas variantes com URL duplicada → aparece uma só vez."""
        import services.query_multilang as _qm
        from services.web_search import SearchResult
        from routers.search import _resolve_lang_search

        shared_url = "https://shared.com"

        async def _fake_expand(query, targets):
            return [query, "translated query"]

        call_n = [0]

        async def _mock_search(query, max_results=0, filetype="", n_pages=1, lang=""):
            call_n[0] += 1
            # Ambas as variantes retornam o mesmo URL
            return [SearchResult(
                title=f"Result {call_n[0]}",
                url=shared_url,
                snippet="",
                source="WEB",
            )]

        monkeypatch.setattr("routers.search.search_web", _mock_search)
        monkeypatch.setattr(_qm, "get_search_languages", lambda: ["en"])
        monkeypatch.setattr(_qm, "expand_multilang", _fake_expand)
        monkeypatch.setattr(_qm, "detect_language", lambda q: "pt")

        results = run(_resolve_lang_search(
            "pesquisa", "auto", inference_available=True,
            max_results=0, filetype="", n_pages=1,
        ))

        urls = [r.url for r in results]
        assert urls.count(shared_url) == 1, (
            f"URL duplicada deve aparecer uma só vez; obteve: {urls}"
        )

    def test_no_lang_no_restriction_returns_results(self, monkeypatch):
        """sem ?lang= e sem config → resultados retornados normalmente."""
        import services.query_multilang as _qm
        from services.web_search import SearchResult
        from routers.search import _resolve_lang_search

        async def _mock_search(query, max_results=0, filetype="", n_pages=1, lang=""):
            return [SearchResult(title="T", url="https://x.com", snippet="s", source="WEB")]

        monkeypatch.setattr("routers.search.search_web", _mock_search)
        monkeypatch.setattr(_qm, "get_search_languages", lambda: [])

        results = run(_resolve_lang_search(
            "python", "", inference_available=False,
            max_results=0, filetype="", n_pages=1,
        ))

        assert len(results) == 1
        assert results[0].url == "https://x.com"
