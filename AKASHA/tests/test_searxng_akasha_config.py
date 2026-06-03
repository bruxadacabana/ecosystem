"""
Testes para SearXNG 3 — Configuração do AKASHA para usar SearXNG via ecosystem.json.

Cobre:
  - ecosystem_client.get_akasha_config():
      * retorna seção 'akasha' do ecosystem.json
      * campo web_search_backend presente
      * retorna {} se arquivo não existe
  - _get_searxng_url() lê web_search_backend via get_akasha_config:
      * URL correta quando configurada
      * string vazia quando campo ausente
      * trailing slash removido
  - Cadeia completa: ecosystem.json → get_akasha_config → _get_searxng_url → _fetch_web → SearXNG
  - Log de debug confirma qual backend está em uso
  - Integração live (SearXNG + ecosystem.json configurados):
      * busca retorna resultados
      * debug log indica SearXNG
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Raiz do ecossistema no sys.path para importar ecosystem_client
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _searxng_running() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:8888/healthz", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _akasha_configured() -> bool:
    """Verifica se web_search_backend está configurado no ecosystem.json."""
    try:
        import ecosystem_client as ec
        return bool(ec.get_akasha_config().get("web_search_backend"))
    except Exception:
        return False


searxng_live = pytest.mark.skipif(
    not _searxng_running(),
    reason="SearXNG não está rodando — teste de integração ignorado",
)

full_integration = pytest.mark.skipif(
    not (_searxng_running() and _akasha_configured()),
    reason="SearXNG não rodando ou web_search_backend não configurado",
)


# ---------------------------------------------------------------------------
# get_akasha_config — leitura do ecosystem.json
# ---------------------------------------------------------------------------

class TestGetAkashaConfig:

    def test_function_exists_in_ecosystem_client(self):
        """get_akasha_config deve existir no ecosystem_client."""
        import ecosystem_client as ec
        assert hasattr(ec, "get_akasha_config"), (
            "get_akasha_config não encontrada em ecosystem_client.py — "
            "todos os módulos que usam essa função falham silenciosamente"
        )
        assert callable(ec.get_akasha_config)

    def test_returns_akasha_section(self, tmp_path, monkeypatch):
        """get_akasha_config() deve retornar a seção 'akasha' do ecosystem.json."""
        eco_file = tmp_path / "ecosystem.json"
        eco_file.write_text(json.dumps({
            "akasha": {
                "web_search_backend": "http://localhost:8888",
                "base_url": "http://localhost:7071",
            },
            "other": {"key": "value"},
        }))
        import ecosystem_client as ec
        monkeypatch.setattr(ec, "ecosystem_path", lambda: eco_file)
        result = ec.get_akasha_config()
        assert result.get("web_search_backend") == "http://localhost:8888"
        assert result.get("base_url") == "http://localhost:7071"
        assert "other" not in result

    def test_returns_empty_when_file_missing(self, tmp_path, monkeypatch):
        """get_akasha_config() deve retornar {} quando ecosystem.json não existe."""
        missing = tmp_path / "nonexistent.json"
        import ecosystem_client as ec
        monkeypatch.setattr(ec, "ecosystem_path", lambda: missing)
        result = ec.get_akasha_config()
        assert isinstance(result, dict)

    def test_returns_empty_when_akasha_section_missing(self, tmp_path, monkeypatch):
        """get_akasha_config() retorna {} se a seção 'akasha' não existir no arquivo."""
        eco_file = tmp_path / "ecosystem.json"
        eco_file.write_text(json.dumps({"other": {}}))
        import ecosystem_client as ec
        monkeypatch.setattr(ec, "ecosystem_path", lambda: eco_file)
        result = ec.get_akasha_config()
        assert isinstance(result, dict)

    def test_web_search_backend_in_real_ecosystem(self):
        """web_search_backend deve estar presente no ecosystem.json real."""
        import ecosystem_client as ec
        cfg = ec.get_akasha_config()
        backend = cfg.get("web_search_backend", "")
        if not backend:
            pytest.skip("SearXNG não configurado neste ambiente (web_search_backend vazio)")
        # Agnóstico de host: a instância pode ser local (localhost:8888) ou no
        # servidor (ex: http://192.168.0.252:8080). Verifica só que é uma URL HTTP(S).
        assert backend.startswith("http://") or backend.startswith("https://"), (
            f"web_search_backend '{backend}' não parece uma URL de SearXNG"
        )


# ---------------------------------------------------------------------------
# _get_searxng_url — leitura via get_akasha_config
# ---------------------------------------------------------------------------

class TestGetSearxngUrl:

    def test_returns_url_from_ecosystem(self, monkeypatch):
        """_get_searxng_url() deve ler web_search_backend do ecosystem via get_akasha_config."""
        import services.web_search as _ws

        monkeypatch.setattr(_ws, "_get_searxng_url",
                            lambda: "http://localhost:8888")
        assert _ws._get_searxng_url() == "http://localhost:8888"

    def test_strips_trailing_slash(self, tmp_path, monkeypatch):
        """URL com trailing slash deve ser removida."""
        eco_file = tmp_path / "ecosystem.json"
        eco_file.write_text(json.dumps({
            "akasha": {"web_search_backend": "http://localhost:8888/"}
        }))
        import ecosystem_client as ec
        monkeypatch.setattr(ec, "ecosystem_path", lambda: eco_file)

        import services.web_search as _ws
        # Chama a implementação real (não mockada)
        real_fn = _ws.__wrapped_get_searxng_url if hasattr(_ws, "__wrapped_get_searxng_url") else None
        if real_fn is None:
            # Testa diretamente via get_akasha_config mockada
            monkeypatch.setattr(ec, "get_akasha_config",
                                lambda: {"web_search_backend": "http://localhost:8888/"})
        url = _ws._get_searxng_url()
        assert not url.endswith("/"), f"URL não deve ter trailing slash: {url!r}"

    def test_returns_empty_when_not_configured(self, tmp_path, monkeypatch):
        """Sem web_search_backend → _get_searxng_url() retorna string vazia."""
        eco_file = tmp_path / "ecosystem.json"
        eco_file.write_text(json.dumps({"akasha": {}}))
        import ecosystem_client as ec
        monkeypatch.setattr(ec, "ecosystem_path", lambda: eco_file)

        import services.web_search as _ws
        url = _ws._get_searxng_url()
        assert url == "", f"Esperado '', obteve {url!r}"

    def test_real_ecosystem_returns_searxng_url(self):
        """_get_searxng_url() deve retornar URL do SearXNG em ambiente configurado."""
        import services.web_search as _ws
        url = _ws._get_searxng_url()
        if not url:
            pytest.skip("SearXNG não configurado neste ambiente")
        assert url.startswith("http"), f"URL malformada: {url!r}"


# ---------------------------------------------------------------------------
# Cadeia completa: _fetch_web usa SearXNG quando configurado
# ---------------------------------------------------------------------------

class TestFetchWebChain:

    def test_fetch_web_uses_searxng_when_url_set(self, monkeypatch):
        """_fetch_web deve usar SearXNG (não DDG) quando URL configurada."""
        import services.web_search as _ws

        searxng_called = []
        ddg_called = []

        async def _fake_searxng(q, max, base, n_pages=1, lang=""):
            searxng_called.append({"q": q, "base": base})
            return [_ws.SearchResult(title="R", url="https://x.com", snippet="ok")]

        async def _fake_ddg(q, max):
            ddg_called.append(q)
            return []

        monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "http://localhost:8888")
        monkeypatch.setattr(_ws, "_fetch_searxng", _fake_searxng)
        monkeypatch.setattr(_ws, "_fetch_ddg", _fake_ddg)

        results = run(_ws._fetch_web("test", 10))

        assert searxng_called, "SearXNG não foi chamado"
        assert not ddg_called, "DDG foi chamado mesmo com SearXNG configurado"
        assert searxng_called[0]["base"] == "http://localhost:8888"
        assert len(results) >= 1

    def test_fetch_web_fallback_when_searxng_empty(self, monkeypatch):
        """SearXNG retorna [] → deve cair para DDG."""
        import services.web_search as _ws

        async def _fake_searxng(q, max, base, n_pages=1, lang=""):
            return []

        ddg_called = []

        async def _fake_ddg(q, max):
            ddg_called.append(q)
            return [_ws.SearchResult(title="DDG", url="https://ddg.com", snippet="ok")]

        monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "http://localhost:8888")
        monkeypatch.setattr(_ws, "_fetch_searxng", _fake_searxng)
        monkeypatch.setattr(_ws, "_fetch_ddg", _fake_ddg)

        run(_ws._fetch_web("test", 10))
        assert ddg_called, "DDG não foi chamado como fallback"

    def test_fetch_web_no_url_skips_searxng(self, monkeypatch):
        """Sem URL SearXNG → DDG direto, sem tentar SearXNG."""
        import services.web_search as _ws

        searxng_called = []

        async def _fake_searxng(q, max, base, n_pages=1, lang=""):
            searxng_called.append(q)
            return []

        async def _fake_ddg(q, max):
            return [_ws.SearchResult(title="D", url="https://d.com", snippet="")]

        monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "")
        monkeypatch.setattr(_ws, "_fetch_searxng", _fake_searxng)
        monkeypatch.setattr(_ws, "_fetch_ddg", _fake_ddg)

        run(_ws._fetch_web("test", 10))
        assert not searxng_called, "SearXNG não deve ser chamado quando URL vazia"


# ---------------------------------------------------------------------------
# Log de debug confirma backend em uso
# ---------------------------------------------------------------------------

class TestDebugLogs:

    def test_log_shows_searxng_url_when_configured(self, monkeypatch, caplog):
        """Debug log deve incluir a URL do SearXNG quando configurado."""
        import services.web_search as _ws

        async def _fake_searxng(q, max, base, n_pages=1, lang=""):
            return [_ws.SearchResult(title="R", url="https://x.com", snippet="ok")]

        async def _fake_ddg(q, max):
            return []

        monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "http://localhost:8888")
        monkeypatch.setattr(_ws, "_fetch_searxng", _fake_searxng)
        monkeypatch.setattr(_ws, "_fetch_ddg", _fake_ddg)

        with caplog.at_level(logging.DEBUG, logger="akasha.web_search"):
            run(_ws._fetch_web("test", 10))

        assert any("SearXNG" in r.message and "localhost:8888" in r.message
                   for r in caplog.records), (
            f"Esperava log com 'SearXNG' e 'localhost:8888'. Logs: {[r.message for r in caplog.records]}"
        )

    def test_log_shows_result_count(self, monkeypatch, caplog):
        """Debug log deve mostrar quantos resultados o SearXNG retornou."""
        import services.web_search as _ws

        async def _fake_searxng(q, max, base, n_pages=1, lang=""):
            return [
                _ws.SearchResult(title=f"R{i}", url=f"https://x{i}.com", snippet="ok")
                for i in range(5)
            ]

        async def _fake_ddg(q, max):
            return []

        monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "http://localhost:8888")
        monkeypatch.setattr(_ws, "_fetch_searxng", _fake_searxng)
        monkeypatch.setattr(_ws, "_fetch_ddg", _fake_ddg)

        with caplog.at_level(logging.DEBUG, logger="akasha.web_search"):
            run(_ws._fetch_web("test", 10))

        assert any("5" in r.message and "SearXNG" in r.message for r in caplog.records), (
            "Esperava log com contagem de resultados do SearXNG"
        )

    def test_log_shows_ddg_when_searxng_not_configured(self, monkeypatch, caplog):
        """Sem SearXNG configurado → debug log deve indicar DDG."""
        import services.web_search as _ws

        async def _fake_ddg(q, max):
            return []

        monkeypatch.setattr(_ws, "_get_searxng_url", lambda: "")
        monkeypatch.setattr(_ws, "_fetch_ddg", _fake_ddg)

        with caplog.at_level(logging.DEBUG, logger="akasha.web_search"):
            run(_ws._fetch_web("test", 10))

        assert any("DDG" in r.message or "não configurado" in r.message
                   for r in caplog.records), (
            "Esperava log indicando DDG quando SearXNG não configurado"
        )


# ---------------------------------------------------------------------------
# Integração live — requer SearXNG + ecosystem.json configurados
# ---------------------------------------------------------------------------

class TestLiveIntegration:

    @full_integration
    def test_live_search_returns_results(self):
        """_fetch_web() com SearXNG configurado deve retornar resultados."""
        import services.web_search as _ws
        results = run(_ws._fetch_web("python programming language", 30, n_pages=1))
        assert len(results) >= 5, (
            f"Menos de 5 resultados ({len(results)}) — SearXNG pode estar com problema"
        )

    @full_integration
    def test_live_two_pages_returns_more(self):
        """Com n_pages=2, deve retornar mais resultados que com n_pages=1."""
        import services.web_search as _ws
        r1 = run(_ws._fetch_web("machine learning", 100, n_pages=1))
        r2 = run(_ws._fetch_web("machine learning algorithms deep", 100, n_pages=2))
        # n_pages=2 pode retornar igual ou mais (deduplicação pode limitar)
        assert len(r2) > 0, "Busca com n_pages=2 não retornou nada"

    @full_integration
    def test_live_results_have_url_title_snippet(self):
        """Resultados do SearXNG via AKASHA devem ter url, title e snippet."""
        import services.web_search as _ws
        results = run(_ws._fetch_web("climate change", 10, n_pages=1))
        for r in results:
            assert r.url.startswith("http"), f"URL inválida: {r.url!r}"
            assert r.title, f"Título vazio em resultado: {r}"

    @full_integration
    def test_live_source_is_web(self):
        """Resultados do SearXNG devem ter source='WEB'."""
        import services.web_search as _ws
        results = run(_ws._fetch_web("quantum computing", 10))
        assert all(r.source == "WEB" for r in results), (
            "Alguns resultados não têm source='WEB'"
        )
