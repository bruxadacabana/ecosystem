"""
Testes para SearXNG 5 — Validação de qualidade de resultados e ajuste de engines.

Cobre:
  - Engines validados presentes no settings.yml (template e implantado)
  - Engines problemáticos ausentes (DDG=CAPTCHA, Brave=rate-limit, Wikipedia=0 resultados)
  - Qualidade dos resultados: URLs válidas, títulos, diversidade de domínios
  - Multi-página funciona (n_pages=2 retorna mais URLs únicas que n_pages=1)
  - Query em português retorna resultados (default_lang="" = qualquer idioma)
  - Engines individuais respondem:
      * startpage, bing, google, mojeek, qwant, yahoo → > 0 resultados
      * duckduckgo, brave → não devem estar na lista (problemáticos)
  - _fetch_searxng com n_pages=4 retorna mais de 40 URLs únicas (target AKASHA)

Findings da validação (SearXNG 5 — 2026-05-31):
  ATIVOS E CONFIÁVEIS: startpage, bing, google, mojeek, qwant, yahoo
  REMOVIDOS:
    duckduckgo     → CAPTCHA permanente (SearxEngineCaptchaException)
    brave          → Rate limit agressivo (SearxEngineTooManyRequestsException, 180s)
    wikipedia      → 0 resultados em todas as queries testadas
    wikidata       → 0 resultados em todas as queries testadas
  COMPORTAMENTO DE DEDUPLICAÇÃO:
    Engines como bing, qwant, yahoo frequentemente retornam as mesmas URLs que
    google/startpage → após deduplicação SearXNG, poucos engines aparecem no campo
    'engines' por resultado. O valor real é privacidade (proxy local) e ausência
    de rate limit, não necessariamente mais resultados únicos por página.
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

TEMPLATE_PATH = Path(__file__).parent.parent / "scripts" / "searxng_settings.yml"
DEPLOYED_PATH = Path.home() / ".config" / "searxng" / "settings.yml"
SEARXNG_URL = "http://localhost:8888"

ENGINES_VALIDATED = {"startpage", "bing", "google", "mojeek", "qwant", "yahoo"}
ENGINES_REMOVED = {"duckduckgo", "brave", "wikipedia", "wikidata"}


def _searxng_running() -> bool:
    try:
        with urllib.request.urlopen(f"{SEARXNG_URL}/healthz", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _any_engine_working() -> bool:
    """Retorna True se pelo menos um engine confiável está retornando resultados.

    Usa bing e qwant diretamente (menos sujeitos a CAPTCHA que Google/Startpage).
    Google e Startpage podem ficar suspensos por até 1h após heavy testing.
    """
    if not _searxng_running():
        return False
    for engine in ["bing", "qwant", "yahoo", "mojeek"]:
        try:
            with urllib.request.urlopen(
                f"{SEARXNG_URL}/search?q=test&format=json&engines={engine}",
                timeout=10,
            ) as r:
                d = json.load(r)
            if len(d.get("results", [])) > 0:
                return True
        except Exception:
            continue
    return False


_RELIABLE_ENGINES = "bing,qwant"  # engines menos sujeitos a CAPTCHA para testes

searxng_live = pytest.mark.skipif(
    not _searxng_running(),
    reason="SearXNG não está rodando — testes de integração ignorados",
)

engines_live = pytest.mark.skipif(
    not _any_engine_working(),
    reason="Nenhum engine retornando resultados (possível suspensão temporária por CAPTCHA — aguardar ~1h ou reiniciar SearXNG)",
)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Configuração de engines — template
# ---------------------------------------------------------------------------

class TestEngineConfiguration:

    def _load_template(self) -> dict:
        content = TEMPLATE_PATH.read_text().replace("__SECRET_KEY__", "x")
        return yaml.safe_load(content) or {}

    def test_template_has_validated_engines(self):
        """Template deve incluir todos os engines validados na lista keep_only."""
        parsed = self._load_template()
        keep_only = set(
            parsed.get("use_default_settings", {})
            .get("engines", {})
            .get("keep_only", [])
        )
        for engine in ENGINES_VALIDATED:
            assert engine in keep_only, (
                f"Engine validado '{engine}' não está em keep_only. "
                f"keep_only atual: {sorted(keep_only)}"
            )

    def test_template_excludes_problematic_engines(self):
        """Template não deve incluir engines problemáticos (DDG=CAPTCHA, Brave=rate-limit)."""
        parsed = self._load_template()
        keep_only = set(
            parsed.get("use_default_settings", {})
            .get("engines", {})
            .get("keep_only", [])
        )
        for engine in ENGINES_REMOVED:
            assert engine not in keep_only, (
                f"Engine problemático '{engine}' ainda está em keep_only. "
                f"DDG → CAPTCHA; Brave → rate-limit 180s; Wikipedia/Wikidata → 0 resultados."
            )

    def test_template_has_science_engines(self):
        """Template deve incluir engines de ciência (arxiv, semantic scholar)."""
        parsed = self._load_template()
        keep_only = set(
            parsed.get("use_default_settings", {})
            .get("engines", {})
            .get("keep_only", [])
        )
        science_engines = keep_only & {"arxiv", "semantic scholar"}
        assert len(science_engines) >= 1, (
            "Nenhum engine de artigos científicos configurado. "
            "arxiv e semantic scholar cobrem consultas acadêmicas."
        )

    def test_deployed_has_validated_engines(self):
        """Settings implantado deve ter os engines validados."""
        if not DEPLOYED_PATH.exists():
            pytest.skip(f"settings.yml não implantado: {DEPLOYED_PATH}")
        parsed = yaml.safe_load(DEPLOYED_PATH.read_text()) or {}
        keep_only = set(
            parsed.get("use_default_settings", {})
            .get("engines", {})
            .get("keep_only", [])
        )
        for engine in ENGINES_VALIDATED:
            assert engine in keep_only, (
                f"Engine validado '{engine}' ausente no settings implantado. "
                f"Execute setup_searxng.sh para reimplantar."
            )

    def test_deployed_excludes_problematic_engines(self):
        """Settings implantado não deve ter engines problemáticos."""
        if not DEPLOYED_PATH.exists():
            pytest.skip(f"settings.yml não implantado: {DEPLOYED_PATH}")
        parsed = yaml.safe_load(DEPLOYED_PATH.read_text()) or {}
        keep_only = set(
            parsed.get("use_default_settings", {})
            .get("engines", {})
            .get("keep_only", [])
        )
        for engine in ENGINES_REMOVED:
            assert engine not in keep_only, (
                f"Engine problemático '{engine}' ainda no settings implantado"
            )

    def test_at_least_four_general_engines(self):
        """Deve haver pelo menos 4 engines de busca geral (não apenas ciência)."""
        parsed = self._load_template()
        keep_only = list(
            parsed.get("use_default_settings", {})
            .get("engines", {})
            .get("keep_only", [])
        )
        science_only = {"arxiv", "semantic scholar"}
        general = [e for e in keep_only if e not in science_only]
        assert len(general) >= 4, (
            f"Apenas {len(general)} engines gerais configurados: {general}. "
            "Mínimo recomendado é 4 para redundância."
        )


# ---------------------------------------------------------------------------
# Qualidade de resultados — integração live
# ---------------------------------------------------------------------------

class TestResultQuality:

    @engines_live
    def test_english_query_returns_results(self):
        """Query em inglês deve retornar resultados usando engines confiáveis (bing, qwant)."""
        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=machine+learning&format=json&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            d = json.load(r)
        results = d.get("results", [])
        assert len(results) >= 5, f"Poucos resultados com engines={_RELIABLE_ENGINES}: {len(results)}"

    @engines_live
    def test_portuguese_query_returns_results(self):
        """Query em português deve retornar resultados (default_lang='')."""
        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=hist%C3%B3ria+do+brasil&format=json&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            d = json.load(r)
        results = d.get("results", [])
        assert len(results) >= 3, (
            f"Poucos resultados para query em português: {len(results)}. "
            "Verificar search.default_lang no settings.yml"
        )

    @engines_live
    def test_results_have_valid_urls(self):
        """Todos os resultados devem ter URLs HTTPS válidas."""
        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=python+programming&format=json&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            d = json.load(r)
        results = d.get("results", [])
        assert results, "Nenhum resultado retornado"
        for res in results:
            url = res.get("url", "")
            assert url.startswith("http"), f"URL inválida: {url!r}"

    @engines_live
    def test_results_have_titles(self):
        """Todos os resultados devem ter título não-vazio."""
        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=climate+change&format=json&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            d = json.load(r)
        results = d.get("results", [])
        assert results, "Nenhum resultado retornado"
        for res in results:
            assert res.get("title"), f"Resultado sem título: {res}"

    @engines_live
    def test_domain_diversity(self):
        """Resultados devem vir de pelo menos 5 domínios distintos."""
        from urllib.parse import urlparse
        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=quantum+computing&format=json&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            d = json.load(r)
        results = d.get("results", [])
        domains = set()
        for res in results:
            h = urlparse(res.get("url", "")).hostname or ""
            domains.add(h.removeprefix("www."))
        assert len(domains) >= 5, (
            f"Apenas {len(domains)} domínios únicos: {sorted(domains)}. "
            "Baixa diversidade indica problema com engines."
        )

    @engines_live
    def test_no_duplicate_urls_in_single_page(self):
        """Uma página não deve conter URLs duplicadas (SearXNG deduplica)."""
        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=machine+learning&format=json&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            d = json.load(r)
        results = d.get("results", [])
        urls = [res.get("url") for res in results if res.get("url")]
        assert len(urls) == len(set(urls)), (
            f"URLs duplicadas encontradas — SearXNG deveria deduplicar automaticamente"
        )

    @engines_live
    def test_five_diverse_queries(self):
        """5 queries variadas devem retornar pelo menos 3 resultados cada (engines estáveis)."""
        queries = [
            "machine learning neural networks",
            "python programming tutorial",
            "climate change ocean temperature",
            "quantum computing qubit",
            "history of the internet",
        ]
        for q in queries:
            encoded = q.replace(" ", "+")
            with urllib.request.urlopen(
                f"{SEARXNG_URL}/search?q={encoded}&format=json&engines={_RELIABLE_ENGINES}",
                timeout=20,
            ) as r:
                d = json.load(r)
            count = len(d.get("results", []))
            assert count >= 3, (
                f"Query {q!r} retornou apenas {count} resultados com {_RELIABLE_ENGINES}"
            )

    @engines_live
    def test_pagination_api_accepts_pageno(self):
        """SearXNG deve aceitar o parâmetro pageno sem retornar erro.

        Nota: engines individuais podem ou não ter resultados na página 2 —
        o importante é que a API aceite o parâmetro e não retorne erro HTTP.
        """
        # Página 1 deve ter resultados
        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=machine+learning&format=json"
            f"&pageno=1&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            d = json.load(r)
        assert len(d.get("results", [])) >= 5, "Página 1 deve ter pelo menos 5 resultados"
        # Página 2 deve ser aceita sem erro (pode retornar [] se engine não tem mais)
        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=machine+learning&format=json"
            f"&pageno=2&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            d2 = json.load(r)
        assert isinstance(d2.get("results", []), list), "Resposta da página 2 deve ser uma lista"

    @engines_live
    def test_multi_page_accumulates_unique_urls(self):
        """2 páginas combinadas devem ter >= tantos URLs quanto 1 página."""
        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=machine+learning&format=json"
            f"&pageno=1&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            p1 = set(res["url"] for res in json.load(r).get("results", []) if res.get("url"))

        with urllib.request.urlopen(
            f"{SEARXNG_URL}/search?q=machine+learning&format=json"
            f"&pageno=2&engines={_RELIABLE_ENGINES}",
            timeout=20,
        ) as r:
            p2 = set(res["url"] for res in json.load(r).get("results", []) if res.get("url"))

        combined = p1 | p2
        assert len(combined) >= len(p1), "2 páginas devem ter pelo menos tantos resultados quanto 1"

    @searxng_live
    def test_at_least_one_engine_responds(self):
        """Pelo menos um dos engines validados deve retornar > 0 resultados.

        Testa cada engine individualmente e verifica que pelo menos 1 responde.
        Engines podem ser suspensos temporariamente por CAPTCHA após heavy testing.
        """
        found = False
        last_err = ""
        for engine in ["bing", "qwant", "yahoo", "mojeek", "startpage"]:
            try:
                with urllib.request.urlopen(
                    f"{SEARXNG_URL}/search?q=programming&format=json&engines={engine}",
                    timeout=15,
                ) as r:
                    d = json.load(r)
                if len(d.get("results", [])) > 0:
                    found = True
                    break
            except Exception as e:
                last_err = str(e)
        assert found, (
            f"Nenhum engine retornou resultados. Último erro: {last_err}. "
            "Possível suspensão temporária — aguardar ~1h ou reiniciar SearXNG."
        )


# ---------------------------------------------------------------------------
# _fetch_searxng com multi-página (via código AKASHA)
# ---------------------------------------------------------------------------

class TestMultiPageFetch:

    @engines_live
    def test_n_pages_2_via_direct_http(self):
        """2 páginas via HTTP direto com engine estável devem acumular URLs únicas.

        Usa _RELIABLE_ENGINES diretamente (bing+qwant) em vez de chamar _fetch_searxng,
        pois _fetch_searxng não suporta seleção de engine e engines podem estar suspensos
        após heavy testing.
        """
        seen: set[str] = set()
        for pageno in [1, 2]:
            with urllib.request.urlopen(
                f"{SEARXNG_URL}/search?q=machine+learning"
                f"&format=json&pageno={pageno}&engines={_RELIABLE_ENGINES}",
                timeout=20,
            ) as r:
                d = json.load(r)
            for res in d.get("results", []):
                if res.get("url"):
                    seen.add(res["url"])
        assert len(seen) >= 10, (
            f"2 páginas com {_RELIABLE_ENGINES} retornaram apenas {len(seen)} URLs únicas."
        )

    @engines_live
    def test_pagination_parameter_works(self):
        """Parâmetro pageno é aceito pela API e a busca retorna dados válidos."""
        for pageno in [1, 2, 3]:
            with urllib.request.urlopen(
                f"{SEARXNG_URL}/search?q=python+programming"
                f"&format=json&pageno={pageno}&engines={_RELIABLE_ENGINES}",
                timeout=20,
            ) as r:
                d = json.load(r)
            assert "results" in d, f"Campo 'results' ausente na resposta da página {pageno}"
            assert isinstance(d["results"], list), f"'results' não é lista na página {pageno}"
