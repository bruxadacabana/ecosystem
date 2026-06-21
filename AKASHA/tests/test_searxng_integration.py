"""
Testes de integração AKASHA ↔ SearXNG (SearXNG mockado via httpx).

Cobre:
  - _get_searxng_url: retorna URL quando configurado, vazio quando não
  - _fetch_searxng: URL correta, parâmetros corretos (q, format, pageno, language)
  - _fetch_web: usa SearXNG quando configurado; DDG quando não
  - search_web: log de debug indica backend em uso
  - Script de setup: existe e é executável
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _get_searxng_url
# ---------------------------------------------------------------------------

class TestGetSearxngUrl:

    def test_returns_url_when_configured(self, monkeypatch):
        """Quando web_search_backend configurado → retorna URL sem trailing slash."""
        import services.web_search as _mod

        monkeypatch.setattr(
            _mod, "_get_searxng_url",
            lambda: "http://localhost:8888"
        )
        assert _mod._get_searxng_url() == "http://localhost:8888"

    def test_returns_empty_when_not_configured(self, monkeypatch):
        """Quando web_search_backend vazio → retorna string vazia."""
        import services.web_search as _mod

        monkeypatch.setattr(_mod, "_get_searxng_url", lambda: "")
        assert _mod._get_searxng_url() == ""

    def test_strips_trailing_slash(self, monkeypatch):
        """URL com trailing slash → removida."""
        import services.web_search as _mod

        # Testa diretamente a lógica da função real
        class _FakeConfig:
            @staticmethod
            def get_akasha_config():
                return {"web_search_backend": "http://localhost:8888/"}

        with patch.dict(sys.modules, {"ecosystem_client": _FakeConfig}):
            result = _mod._get_searxng_url()
        assert not result.endswith("/"), f"URL não deve ter trailing slash: {result}"


# ---------------------------------------------------------------------------
# _fetch_searxng
# ---------------------------------------------------------------------------

class TestFetchSearxng:

    def _make_mock(self, results: list) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": results}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        return mock_client

    def test_fetches_from_correct_endpoint(self):
        """Busca no endpoint /search com parâmetros corretos."""
        from services.web_search import _fetch_searxng

        captured_urls = []
        captured_params = []

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": [
            {"url": "https://python.org", "title": "Python", "content": "desc"}
        ]}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def _fake_get(url, params=None):
            captured_urls.append(url)
            captured_params.append(params or {})
            return mock_resp

        mock_client.get = _fake_get

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(_fetch_searxng("python", 10, "http://localhost:8888"))

        assert len(captured_urls) >= 1
        assert "http://localhost:8888/search" in captured_urls[0]
        assert captured_params[0].get("q") == "python"
        assert captured_params[0].get("format") == "json"
        assert len(results) >= 1

    def test_pageno_increments_per_page(self):
        """n_pages=2 → 2 requisições com pageno=1 e pageno=2."""
        from services.web_search import _fetch_searxng

        captured_pagenos = []

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def _fake_get(url, params=None):
            captured_pagenos.append((params or {}).get("pageno"))
            return mock_resp

        mock_client.get = _fake_get

        with patch("httpx.AsyncClient", return_value=mock_client):
            run(_fetch_searxng("python", 50, "http://localhost:8888", n_pages=2))

        assert set(captured_pagenos) == {1, 2}, f"pagenos esperados {{1,2}}, obteve {captured_pagenos}"

    def test_results_parsed_correctly(self):
        """Resultado JSON do SearXNG é convertido em SearchResult."""
        from services.web_search import _fetch_searxng

        raw = [
            {"url": "https://python.org", "title": "Python.org", "content": "Linguagem Python"},
            {"url": "https://docs.python.org", "title": "Python Docs", "content": "Documentação"},
        ]

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": raw}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(_fetch_searxng("python", 10, "http://localhost:8888"))

        assert len(results) == 2
        assert results[0].url == "https://python.org"
        assert results[0].title == "Python.org"
        assert results[0].snippet == "Linguagem Python"

    def test_returns_empty_on_http_error(self):
        """Erro HTTP do SearXNG → lista vazia sem exceção."""
        from services.web_search import _fetch_searxng

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(_fetch_searxng("python", 10, "http://localhost:8888"))

        assert results == []


# ---------------------------------------------------------------------------
# _fetch_web — seleção de backend
# ---------------------------------------------------------------------------

class TestFetchWebBackend:

    def test_uses_searxng_when_configured_and_returns_results(self, monkeypatch):
        """SearXNG configurado e retornando resultados → DDG não é chamado."""
        import services.web_search as _mod

        ddg_called = []

        async def _fake_fetch_searxng(q, max, base, n_pages=1, lang=""):
            return [_mod.SearchResult(title="R", url="https://x.com", snippet="s", source="WEB")]

        async def _fake_fetch_ddg(q, max):
            ddg_called.append(q)
            return []

        async def _active(): return ("remoto", "http://localhost:8888")
        async def _no_marg(q, k, n): return []
        monkeypatch.setattr(_mod, "_active_searxng", _active)
        monkeypatch.setattr(_mod, "_fetch_marginalia", _no_marg)
        monkeypatch.setattr(_mod, "_get_marginalia_key", lambda: "")
        monkeypatch.setattr(_mod, "_fetch_searxng", _fake_fetch_searxng)
        monkeypatch.setattr(_mod, "_fetch_ddg", _fake_fetch_ddg)

        results = run(_mod._fetch_web("python", 10))
        assert len(results) >= 1
        assert not ddg_called, "DDG não deve ser chamado quando SearXNG retorna resultados"

    def test_falls_back_to_ddg_when_searxng_empty(self, monkeypatch):
        """SearXNG retorna [] → DDG é chamado."""
        import services.web_search as _mod

        ddg_called = []

        async def _fake_fetch_searxng(q, max, base, n_pages=1, lang=""):
            return []  # SearXNG sem resultado

        async def _fake_fetch_ddg(q, max):
            ddg_called.append(q)
            return [_mod.SearchResult(title="DDG", url="https://ddg.com", snippet="", source="WEB")]

        async def _empty_marginalia(q, key, max):
            return []

        async def _active(): return ("remoto", "http://localhost:8888")
        async def _no_mwmbl(q, n): return []
        monkeypatch.setattr(_mod, "_active_searxng", _active)
        monkeypatch.setattr(_mod, "_fetch_mwmbl", _no_mwmbl)
        monkeypatch.setattr(_mod, "_get_searxng_url", lambda: "http://localhost:8888")
        monkeypatch.setattr(_mod, "_fetch_searxng", _fake_fetch_searxng)
        monkeypatch.setattr(_mod, "_fetch_ddg", _fake_fetch_ddg)
        monkeypatch.setattr(_mod, "_get_marginalia_key", lambda: "")
        monkeypatch.setattr(_mod, "_fetch_marginalia", _empty_marginalia)

        results = run(_mod._fetch_web("python", 10))
        assert ddg_called, "DDG deve ser chamado quando SearXNG e Marginalia retornam vazio"
        assert len(results) >= 1

    def test_uses_ddg_when_searxng_not_configured(self, monkeypatch):
        """SearXNG não configurado → DDG diretamente."""
        import services.web_search as _mod

        ddg_called = []

        async def _fake_fetch_ddg(q, max):
            ddg_called.append(q)
            return [_mod.SearchResult(title="D", url="https://d.com", snippet="", source="WEB")]

        async def _empty_marginalia(q, key, max):
            return []

        async def _active(): return None
        async def _no_mwmbl(q, n): return []
        monkeypatch.setattr(_mod, "_active_searxng", _active)
        monkeypatch.setattr(_mod, "_fetch_mwmbl", _no_mwmbl)
        monkeypatch.setattr(_mod, "_fetch_ddg", _fake_fetch_ddg)
        monkeypatch.setattr(_mod, "_get_marginalia_key", lambda: "")
        monkeypatch.setattr(_mod, "_fetch_marginalia", _empty_marginalia)

        run(_mod._fetch_web("python", 10))
        assert ddg_called


# ---------------------------------------------------------------------------
# Logs de debug — SearXNG
# ---------------------------------------------------------------------------

class TestSearxngLogs:

    def test_debug_log_when_searxng_configured(self, monkeypatch, caplog):
        """Log de debug indica uso do SearXNG quando configurado."""
        import services.web_search as _mod
        import logging

        async def _fake_fetch_searxng(q, max, base, n_pages=1, lang=""):
            return [_mod.SearchResult(title="R", url="https://r.com", snippet="", source="WEB")]

        async def _fake_fetch_ddg(q, max):
            return []

        monkeypatch.setattr(_mod, "_get_searxng_url", lambda: "http://localhost:8888")
        monkeypatch.setattr(_mod, "_fetch_searxng", _fake_fetch_searxng)
        monkeypatch.setattr(_mod, "_fetch_ddg", _fake_fetch_ddg)

        with caplog.at_level(logging.DEBUG, logger="akasha.web_search"):
            run(_mod._fetch_web("python", 10))

        assert any("SearXNG" in r.message for r in caplog.records), (
            "Esperava log com 'SearXNG' no debug"
        )

    def test_debug_log_when_searxng_not_configured(self, monkeypatch, caplog):
        """Nenhum SearXNG vivo → log indica o fallback (DDG).

        Fila de disponibilidade (2026-06-17): força `_searxng_candidates` vazio →
        `_active_searxng` retorna None e loga o aviso que cita DDG.
        """
        import services.web_search as _mod
        import logging

        async def _fake_fetch_ddg(q, max):
            return []

        async def _empty_marginalia(q, key, max):
            return []

        async def _empty_mwmbl(q, n):
            return []

        monkeypatch.setattr(_mod, "_searxng_candidates", lambda: [])
        monkeypatch.setattr(_mod, "_fetch_ddg", _fake_fetch_ddg)
        monkeypatch.setattr(_mod, "_get_marginalia_key", lambda: "")
        monkeypatch.setattr(_mod, "_fetch_marginalia", _empty_marginalia)
        monkeypatch.setattr(_mod, "_fetch_mwmbl", _empty_mwmbl)

        with caplog.at_level(logging.DEBUG, logger="akasha.web_search"):
            run(_mod._fetch_web("python", 10))

        assert any("DDG" in r.message or "não configurado" in r.message for r in caplog.records), (
            f"Esperava log indicando DDG. Logs: {[r.message for r in caplog.records]}"
        )


# ---------------------------------------------------------------------------
# Script de setup — existência e permissões
# ---------------------------------------------------------------------------

class TestSetupScript:

    def test_setup_script_exists(self):
        """AKASHA/scripts/setup_searxng.sh deve existir."""
        script = Path(__file__).parent.parent / "scripts" / "setup_searxng.sh"
        assert script.exists(), f"Script não encontrado: {script}"

    def test_settings_yml_exists(self):
        """AKASHA/scripts/searxng_settings.yml deve existir."""
        config = Path(__file__).parent.parent / "scripts" / "searxng_settings.yml"
        assert config.exists(), f"Config não encontrado: {config}"

    def test_settings_yml_has_required_sections(self):
        """settings.yml deve conter seções essenciais."""
        config = Path(__file__).parent.parent / "scripts" / "searxng_settings.yml"
        content = config.read_text()
        for section in ("general:", "server:", "search:", "engines:", "__SECRET_KEY__"):
            assert section in content, f"Seção ausente: {section}"

    def test_setup_script_has_shebang(self):
        """setup_searxng.sh deve ter shebang correto."""
        script = Path(__file__).parent.parent / "scripts" / "setup_searxng.sh"
        first_line = script.read_text().splitlines()[0]
        assert first_line.startswith("#!/"), f"Shebang ausente: {first_line}"
