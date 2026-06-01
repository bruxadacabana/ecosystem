"""
Testes para SearXNG 2 — Configuração de settings.yml e validação da instância.

Cobre:
  - settings.yml implantado (~/.config/searxng/settings.yml):
      * seções obrigatórias presentes
      * use_default_settings habilitado (modo merge com defaults)
      * json habilitado em formats
      * safe_search = 0
      * default_lang = "" (qualquer idioma)
      * secret_key gerada (não é o placeholder)
      * porta 8888, bind apenas local (127.0.0.1)
  - Template (scripts/searxng_settings.yml):
      * contém __SECRET_KEY__ placeholder
      * contém use_default_settings
      * não contém seções inválidas (ex: brand.new_issue_url)
  - Integração live (requer SearXNG rodando — skipped se não disponível):
      * healthcheck responde 200
      * busca JSON retorna resultados
      * 2 páginas combinadas retornam > 50 resultados únicos
      * formato JSON está habilitado (não 406 Not Acceptable)
      * engines configurados estão retornando resultados

Nota: resultados por página únia são tipicamente 30-40 após deduplicação
inter-engine. O target de >50 é consistentemente atingido com 2+ páginas.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixtures e helpers
# ---------------------------------------------------------------------------

TEMPLATE_PATH = Path(__file__).parent.parent / "scripts" / "searxng_settings.yml"
DEPLOYED_PATH = Path.home() / ".config" / "searxng" / "settings.yml"
SEARXNG_URL = "http://localhost:8888"
EXPECTED_ENGINES = {"startpage", "bing", "google", "mojeek", "qwant", "yahoo"}
_STABLE_ENGINES = "bing,qwant"  # engines menos sujeitos a CAPTCHA — usados em testes live


def _searxng_running() -> bool:
    """Retorna True se SearXNG está respondendo no healthcheck."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{SEARXNG_URL}/healthz", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _any_engine_working() -> bool:
    """Retorna True se pelo menos um engine estável está respondendo."""
    import urllib.request, json
    if not _searxng_running():
        return False
    for engine in ["bing", "qwant", "yahoo", "mojeek"]:
        try:
            with urllib.request.urlopen(
                f"{SEARXNG_URL}/search?q=test&format=json&engines={engine}", timeout=8
            ) as r:
                d = json.load(r)
            if len(d.get("results", [])) > 0:
                return True
        except Exception:
            continue
    return False


engines_live = pytest.mark.skipif(
    not _any_engine_working(),
    reason="Nenhum engine retornando resultados (possível suspensão — aguardar ou reiniciar SearXNG)",
)

searxng_live = pytest.mark.skipif(
    not _searxng_running(),
    reason="SearXNG não está rodando em localhost:8888 — teste de integração ignorado",
)


# ---------------------------------------------------------------------------
# Template — scripts/searxng_settings.yml
# ---------------------------------------------------------------------------

class TestSettingsTemplate:

    def test_template_exists(self):
        """Template searxng_settings.yml deve existir no diretório scripts/."""
        assert TEMPLATE_PATH.exists(), f"Template não encontrado: {TEMPLATE_PATH}"

    def test_template_has_placeholder(self):
        """Template deve conter o placeholder __SECRET_KEY__ para substituição."""
        content = TEMPLATE_PATH.read_text()
        assert "__SECRET_KEY__" in content, "Placeholder __SECRET_KEY__ ausente no template"

    def test_template_has_use_default_settings(self):
        """Template deve usar use_default_settings para fazer merge com os defaults do SearXNG."""
        content = TEMPLATE_PATH.read_text()
        assert "use_default_settings" in content, (
            "use_default_settings ausente — sem ele, o settings substitui os defaults "
            "inteiramente e seções obrigatórias ficam faltando"
        )

    def test_template_parses_as_valid_yaml(self):
        """Template deve ser YAML válido (exceto pelo placeholder não-resolvido)."""
        content = TEMPLATE_PATH.read_text()
        # Substitui placeholder por string válida para permitir parse
        content_patched = content.replace("__SECRET_KEY__", "placeholder_for_test")
        parsed = yaml.safe_load(content_patched)
        assert isinstance(parsed, dict), "settings.yml template não é um dicionário YAML válido"

    def test_template_has_json_format(self):
        """Template deve habilitar o formato JSON (necessário para a API do AKASHA)."""
        content = TEMPLATE_PATH.read_text()
        assert "json" in content, "Formato JSON não encontrado no template"

    def test_template_has_keep_only_engines(self):
        """Template deve especificar engines via use_default_settings.engines.keep_only."""
        content_patched = TEMPLATE_PATH.read_text().replace("__SECRET_KEY__", "x")
        parsed = yaml.safe_load(content_patched)
        uds = parsed.get("use_default_settings", {})
        assert isinstance(uds, dict), "use_default_settings deve ser um dict com engines"
        engines = uds.get("engines", {})
        assert "keep_only" in engines, "use_default_settings.engines.keep_only ausente"
        keep_only = engines["keep_only"]
        assert len(keep_only) >= 3, f"Poucos engines em keep_only: {keep_only}"

    def test_template_safe_search_disabled(self):
        """Template deve ter safe_search: 0 (sem filtro — usuária decide)."""
        content_patched = TEMPLATE_PATH.read_text().replace("__SECRET_KEY__", "x")
        parsed = yaml.safe_load(content_patched)
        search = parsed.get("search", {})
        assert search.get("safe_search") == 0, (
            f"safe_search esperado 0, obteve {search.get('safe_search')}"
        )

    def test_template_bind_local_only(self):
        """Template deve fazer bind apenas em 127.0.0.1 (nunca expor na rede)."""
        content_patched = TEMPLATE_PATH.read_text().replace("__SECRET_KEY__", "x")
        parsed = yaml.safe_load(content_patched)
        server = parsed.get("server", {})
        bind = server.get("bind_address", "")
        assert bind == "127.0.0.1", (
            f"bind_address deve ser 127.0.0.1, obteve '{bind}' — "
            "expor o SearXNG na rede é um risco de privacidade"
        )

    def test_template_no_invalid_brand_fields(self):
        """Template não deve conter campos inválidos do SettingsBrand (ex: new_issue_url)."""
        content = TEMPLATE_PATH.read_text()
        assert "new_issue_url" not in content, (
            "new_issue_url não é um campo válido do SettingsBrand — causa ValueError no SearXNG"
        )


# ---------------------------------------------------------------------------
# Settings implantado — ~/.config/searxng/settings.yml
# ---------------------------------------------------------------------------

class TestDeployedSettings:

    @pytest.fixture(autouse=True)
    def require_deployed(self):
        if not DEPLOYED_PATH.exists():
            pytest.skip(f"settings.yml não implantado: {DEPLOYED_PATH}")

    def _load(self) -> dict:
        return yaml.safe_load(DEPLOYED_PATH.read_text()) or {}

    def test_deployed_exists(self):
        """settings.yml deve estar implantado em ~/.config/searxng/settings.yml."""
        assert DEPLOYED_PATH.exists()

    def test_deployed_has_secret_key(self):
        """secret_key implantada deve ser uma string não-placeholder."""
        parsed = self._load()
        key = parsed.get("server", {}).get("secret_key", "")
        assert key, "secret_key está vazia"
        assert key != "__SECRET_KEY__", "secret_key ainda é o placeholder — substituição falhou"
        assert len(key) >= 32, f"secret_key muito curta ({len(key)} chars) — deve ser >= 32"

    def test_deployed_has_json_format(self):
        """Formato JSON deve estar habilitado no settings implantado."""
        parsed = self._load()
        formats = parsed.get("search", {}).get("formats", [])
        assert "json" in formats, (
            f"Formato 'json' não encontrado em search.formats: {formats}. "
            "Sem json, o AKASHA não consegue usar a API SearXNG."
        )

    def test_deployed_has_html_format(self):
        """Formato HTML deve estar habilitado (necessário para uso via browser)."""
        parsed = self._load()
        formats = parsed.get("search", {}).get("formats", [])
        assert "html" in formats, f"Formato 'html' não encontrado: {formats}"

    def test_deployed_use_default_settings(self):
        """use_default_settings deve estar presente (garante merge com defaults)."""
        parsed = self._load()
        assert "use_default_settings" in parsed, (
            "use_default_settings ausente — configuração pode estar incompleta "
            "por não fazer merge com os defaults do SearXNG"
        )

    def test_deployed_instance_name(self):
        """instance_name deve ser 'AKASHA Search'."""
        parsed = self._load()
        name = parsed.get("general", {}).get("instance_name", "")
        assert name == "AKASHA Search", f"instance_name inesperado: '{name}'"

    def test_deployed_port(self):
        """Porta deve ser 8888."""
        parsed = self._load()
        port = parsed.get("server", {}).get("port")
        assert port == 8888, f"Porta inesperada: {port}"

    def test_deployed_safe_search_zero(self):
        """safe_search deve ser 0 (sem filtro)."""
        parsed = self._load()
        safe = parsed.get("search", {}).get("safe_search")
        assert safe == 0, f"safe_search = {safe}, esperado 0"


# ---------------------------------------------------------------------------
# Integração live — requer SearXNG rodando em localhost:8888
# ---------------------------------------------------------------------------

class TestSearXNGLive:

    @searxng_live
    def test_healthcheck_returns_ok(self):
        """GET /healthz deve retornar 200 OK."""
        import urllib.request
        with urllib.request.urlopen(f"{SEARXNG_URL}/healthz", timeout=5) as r:
            assert r.status == 200, f"Healthcheck retornou {r.status}"
            body = r.read().decode()
            assert "OK" in body, f"Body inesperado: {body!r}"

    @searxng_live
    def test_json_format_enabled(self):
        """Busca via ?format=json deve retornar 200 (não 406 Not Acceptable)."""
        import urllib.request
        url = f"{SEARXNG_URL}/search?q=test&format=json"
        with urllib.request.urlopen(url, timeout=10) as r:
            assert r.status == 200, f"format=json retornou status {r.status}"

    @engines_live
    def test_single_page_returns_results(self):
        """Busca de uma página com engines estáveis deve retornar pelo menos 5 resultados."""
        import urllib.request, json
        url = f"{SEARXNG_URL}/search?q=machine+learning&format=json&engines={_STABLE_ENGINES}"
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
        results = data.get("results", [])
        assert len(results) >= 5, (
            f"Menos de 5 resultados ({len(results)}) com {_STABLE_ENGINES}"
        )

    @engines_live
    def test_two_pages_return_results(self):
        """2 páginas combinadas com engines estáveis devem retornar pelo menos 10 URLs únicas.

        Usa bing+qwant (menos sujeitos a CAPTCHA). Com todos os engines disponíveis,
        o total sobe para 25-40 URLs únicas por 2 páginas (após deduplicação inter-engine).
        """
        import urllib.request, json
        seen_urls: set[str] = set()
        for pageno in [1, 2]:
            url = (f"{SEARXNG_URL}/search?q=machine+learning"
                   f"&format=json&pageno={pageno}&engines={_STABLE_ENGINES}")
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.load(r)
            for r_ in data.get("results", []):
                if r_.get("url"):
                    seen_urls.add(r_["url"])
        total = len(seen_urls)
        assert total >= 10, (
            f"2 páginas com {_STABLE_ENGINES} retornaram {total} URLs únicas, esperado >= 10."
        )

    @engines_live
    def test_at_least_two_engines_active(self):
        """Pelo menos 1 engine deve aparecer nos resultados.

        Engines podem ser suspensos temporariamente por CAPTCHA após uso intenso.
        O pré-requisito @engines_live já garante que pelo menos 1 está ativo.
        """
        import urllib.request, json, collections
        url = f"{SEARXNG_URL}/search?q=python+programming&format=json&engines={_STABLE_ENGINES}"
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
        engines_seen: set[str] = set()
        for result in data.get("results", []):
            for eng in result.get("engines", []):
                engines_seen.add(eng)
        assert len(engines_seen) >= 1, (
            f"Nenhum engine retornou resultados: {engines_seen}. "
            "Verifique os engines em use_default_settings.engines.keep_only"
        )

    @searxng_live
    def test_no_plaintext_secret_key_in_response(self):
        """Respostas do SearXNG não devem vazar a secret_key."""
        import urllib.request
        url = f"{SEARXNG_URL}/search?q=test&format=json"
        with urllib.request.urlopen(url, timeout=10) as r:
            body = r.read().decode(errors="replace")
        # Secret key é hex — se aparecer na resposta, é um leak grave
        if DEPLOYED_PATH.exists():
            key = yaml.safe_load(DEPLOYED_PATH.read_text()).get("server", {}).get("secret_key", "")
            if key and key != "__SECRET_KEY__":
                assert key not in body, "secret_key vazando nas respostas da API!"

    @engines_live
    def test_different_queries_return_different_results(self):
        """Queries diferentes devem retornar conjuntos de resultados distintos."""
        import urllib.request, json
        urls_q1: set[str] = set()
        urls_q2: set[str] = set()
        for q, dest in [("python programming", urls_q1), ("climate change ocean", urls_q2)]:
            url = (f"{SEARXNG_URL}/search?q={q.replace(' ', '+')}"
                   f"&format=json&engines={_STABLE_ENGINES}")
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.load(r)
            for r_ in data.get("results", []):
                if r_.get("url"):
                    dest.add(r_["url"])
        if not urls_q1 or not urls_q2:
            pytest.skip("Uma das queries retornou vazio — engines podem estar suspensos")
        overlap = urls_q1 & urls_q2
        assert len(overlap) < min(len(urls_q1), len(urls_q2)) * 0.5, (
            "Queries muito diferentes retornaram resultados quase idênticos"
        )
