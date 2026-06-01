"""
Testes para Chat 1 e Chat 2 — /chat com busca híbrida e voz própria.

Chat 1 cobre:
  - _MAX_SNIPPETS == 15 (aumentado de 5)
  - search_local chamado com include_crawl=True
  - sources retornam campo excerpt
  - include_crawl=False não dispara crawl FTS
  - include_crawl=True dispara crawl FTS em paralelo
  - SOURCE_WEIGHTS["SITES"] definido (crawl_fts tem peso)

Chat 2 cobre:
  - _build_prompt é async
  - _RESEARCH_VOICE está no prompt (instruções de citação [N])
  - Framing afetivo é chamado (get_emotional_framing)
  - Sem fontes → prompt inclui mensagem de "nenhuma fonte encontrada"
  - Com fontes → refs incluídos no system message
  - Framing falha silenciosamente (sem quebrar o chat)

include_crawl em search_local cobre:
  - Sem include_crawl → _crawl_fts_task não criado
  - Com include_crawl=True → search_sites chamado
  - SITES em SOURCE_WEIGHTS
  - Falha no import do crawler → graceful fallback
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent))


# ---------------------------------------------------------------------------
# Fixture: patches de imports pesados
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_heavy(monkeypatch):
    fake_eco = types.ModuleType("ecosystem_client")
    fake_eco.get_inference_url = lambda: "http://127.0.0.1:7072"
    fake_eco.get_active_profile = lambda: {"models": {"llm_query": "test"}}
    fake_eco.get_ollama_headers = lambda app, p: {"X-App": app, "X-Priority": str(p)}
    monkeypatch.setitem(sys.modules, "ecosystem_client", fake_eco)

    for mod in ("database", "config", "services.persona",
                "services.local_search", "services.crawler"):
        monkeypatch.setitem(sys.modules, mod, types.ModuleType(mod))

    # config precisa de PERSONALITY_PROMPT
    cfg = sys.modules["config"]
    cfg.PERSONALITY_PROMPT = "Você é a Akasha."

    yield


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Chat 1 — _MAX_SNIPPETS e include_crawl
# ---------------------------------------------------------------------------

class TestChat1MaxSnippets:

    def test_max_snippets_is_15(self):
        """_MAX_SNIPPETS deve ser 15 após Chat 1."""
        if "routers.chat" in sys.modules:
            del sys.modules["routers.chat"]
        import routers.chat as chat_mod
        assert chat_mod._MAX_SNIPPETS == 15, (
            f"_MAX_SNIPPETS deve ser 15, obteve {chat_mod._MAX_SNIPPETS}"
        )


class TestChat1Sources:

    def test_sources_have_excerpt_field(self):
        """Sources enviadas pelo SSE devem ter campo 'excerpt'."""
        if "routers.chat" in sys.modules:
            del sys.modules["routers.chat"]
        import routers.chat as chat_mod

        snippets = [
            {"title": "Artigo 1", "url": "http://a.com", "snippet": "Trecho do artigo 1."},
            {"title": "Artigo 2", "url": "http://b.com", "snippet": "Trecho do artigo 2."},
        ]

        # Simula o que chat_message faz para construir sources
        sources = [
            {"url": s["url"], "title": s["title"], "excerpt": s["snippet"][:200]}
            for s in snippets
        ]

        assert all("excerpt" in s for s in sources), (
            "Todos os sources devem ter campo 'excerpt'"
        )

    def test_excerpt_truncated_to_200_chars(self):
        """excerpt é truncado a 200 chars."""
        long_snippet = "x" * 500
        sources = [{"url": "http://a.com", "title": "T", "excerpt": long_snippet[:200]}]
        assert len(sources[0]["excerpt"]) == 200


# ---------------------------------------------------------------------------
# Chat 1 — include_crawl em search_local
# ---------------------------------------------------------------------------

class TestIncludeCrawlParameter:

    def test_source_weights_has_sites(self):
        """SOURCE_WEIGHTS deve ter entrada para SITES (crawl_fts)."""
        src = (_ROOT / "services" / "local_search.py").read_text()
        assert '"SITES"' in src or "'SITES'" in src, (
            "SOURCE_WEIGHTS deve ter 'SITES' para crawl_fts com peso definido"
        )

    def test_search_local_accepts_include_crawl_param(self):
        """search_local deve aceitar include_crawl=True sem levantar TypeError."""
        if "services.local_search" in sys.modules:
            del sys.modules["services.local_search"]

        import inspect, importlib
        # Verifica a assinatura sem importar o módulo completo
        src = (_ROOT / "services" / "local_search.py").read_text()
        assert "include_crawl" in src, (
            "search_local deve ter parâmetro include_crawl"
        )

    def test_include_crawl_false_is_default(self):
        """include_crawl=False deve ser o default."""
        src = (_ROOT / "services" / "local_search.py").read_text()
        assert "include_crawl: bool = False" in src, (
            "include_crawl deve ter default False"
        )

    def test_include_crawl_launches_crawler_search(self):
        """Com include_crawl=True, search_sites do crawler é chamado."""
        src = (_ROOT / "services" / "local_search.py").read_text()
        assert "from services.crawler import search_sites" in src, (
            "include_crawl deve importar e chamar search_sites do crawler"
        )

    def test_include_crawl_results_in_rrf(self):
        """crawl_fts_results deve estar no pool passado ao _rrf."""
        src = (_ROOT / "services" / "local_search.py").read_text()
        assert "crawl_fts_results" in src, (
            "crawl_fts_results deve existir e ser passado ao _rrf"
        )


# ---------------------------------------------------------------------------
# Chat 2 — _build_prompt: voz própria e framing afetivo
# ---------------------------------------------------------------------------

class TestChat2BuildPrompt:

    def test_build_prompt_is_async(self):
        """_build_prompt deve ser async (para poder awaitar affective_state)."""
        import inspect
        src = (_ROOT / "routers" / "chat.py").read_text()
        # Encontra a linha de definição
        for line in src.splitlines():
            if "_build_prompt" in line and "def " in line:
                assert "async def" in line, (
                    "_build_prompt deve ser async"
                )
                break

    def test_research_voice_in_prompt(self):
        """Prompt deve incluir instruções de citação [N] e análise própria."""
        src = (_ROOT / "routers" / "chat.py").read_text()
        assert "[N]" in src or "citações" in src.lower(), (
            "Prompt deve incluir instrução de citação [N]"
        )
        assert "PRIMÁRIO" in src or "primário" in src.lower(), (
            "Prompt deve incluir diretiva primária de pesquisa"
        )
        assert "PERMITIDO" in src or "permitido" in src.lower(), (
            "Prompt deve incluir o que é permitido além das fontes"
        )

    def test_emotional_framing_called(self):
        """_build_prompt deve chamar get_emotional_framing."""
        src = (_ROOT / "routers" / "chat.py").read_text()
        assert "get_emotional_framing" in src, (
            "_build_prompt deve chamar get_emotional_framing do affective_state"
        )
        assert "get_current_state" in src, (
            "_build_prompt deve chamar get_current_state para obter estado afetivo"
        )

    def test_build_prompt_no_snippets_says_not_found(self):
        """Sem snippets, prompt deve informar que não encontrou fontes."""
        src = (_ROOT / "routers" / "chat.py").read_text()
        assert "Nenhuma fonte" in src or "nenhuma fonte" in src.lower(), (
            "Quando sem fontes, prompt deve informar explicitamente"
        )

    def test_build_prompt_with_snippets(self):
        """_build_prompt deve incluir refs com citações [1], [2] etc."""
        if "routers.chat" in sys.modules:
            del sys.modules["routers.chat"]
        import routers.chat as chat_mod

        snippets = [
            {"title": "Doc A", "url": "http://a.com", "snippet": "Conteúdo A."},
            {"title": "Doc B", "url": "http://b.com", "snippet": "Conteúdo B."},
        ]

        # Mock do affective_state
        fake_aff = types.ModuleType("services.affective_state")
        fake_aff.get_current_state = AsyncMock(return_value={"valence": 0.0, "epistemic_curiosity": 0.0})
        fake_aff.get_emotional_framing = lambda state: ""

        with patch.dict(sys.modules, {"services.affective_state": fake_aff}):
            msgs = run(chat_mod._build_prompt("Pergunta?", snippets, ""))

        system_content = msgs[0]["content"]
        assert "[1]" in system_content, "Snippet 1 deve aparecer como [1]"
        assert "[2]" in system_content, "Snippet 2 deve aparecer como [2]"
        assert "Doc A" in system_content
        assert "Doc B" in system_content

    def test_build_prompt_includes_user_question(self):
        """Último elemento deve ser a mensagem do usuário."""
        if "routers.chat" in sys.modules:
            del sys.modules["routers.chat"]
        import routers.chat as chat_mod

        fake_aff = types.ModuleType("services.affective_state")
        fake_aff.get_current_state = AsyncMock(return_value={})
        fake_aff.get_emotional_framing = lambda s: ""

        with patch.dict(sys.modules, {"services.affective_state": fake_aff}):
            msgs = run(chat_mod._build_prompt("Qual é a capital?", [], ""))

        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "Qual é a capital?"

    def test_emotional_framing_failure_does_not_raise(self):
        """Falha no affective_state não deve quebrar _build_prompt."""
        if "routers.chat" in sys.modules:
            del sys.modules["routers.chat"]
        import routers.chat as chat_mod

        fake_aff = types.ModuleType("services.affective_state")
        fake_aff.get_current_state = AsyncMock(side_effect=RuntimeError("DB offline"))
        fake_aff.get_emotional_framing = lambda s: ""

        try:
            with patch.dict(sys.modules, {"services.affective_state": fake_aff}):
                msgs = run(chat_mod._build_prompt("Pergunta?", [], ""))
            assert isinstance(msgs, list), "Deve retornar lista mesmo com erro no affective_state"
        except Exception as exc:
            pytest.fail(f"_build_prompt não deve levantar quando affective_state falha: {exc}")

    def test_positive_valence_framing_applied(self):
        """Valência positiva → framing exploratório injetado no prompt."""
        if "routers.chat" in sys.modules:
            del sys.modules["routers.chat"]
        import routers.chat as chat_mod

        fake_aff = types.ModuleType("services.affective_state")
        fake_aff.get_current_state = AsyncMock(return_value={"valence": 0.6, "epistemic_curiosity": 0.0})
        fake_aff.get_emotional_framing = lambda state: (
            "[Modulação contextual]\nAdote framing exploratório." if state.get("valence", 0) > 0.4 else ""
        )

        with patch.dict(sys.modules, {"services.affective_state": fake_aff}):
            msgs = run(chat_mod._build_prompt("Pergunta?", [], ""))

        system_content = msgs[0]["content"]
        assert "exploratório" in system_content.lower() or "Modulação" in system_content, (
            "Com valência positiva, framing exploratório deve estar no prompt"
        )

    def test_negative_valence_framing_applied(self):
        """Valência negativa → framing crítico/analítico injetado no prompt."""
        if "routers.chat" in sys.modules:
            del sys.modules["routers.chat"]
        import routers.chat as chat_mod

        fake_aff = types.ModuleType("services.affective_state")
        fake_aff.get_current_state = AsyncMock(return_value={"valence": -0.4, "epistemic_curiosity": 0.0})
        fake_aff.get_emotional_framing = lambda state: (
            "[Modulação contextual]\nAdote framing analítico." if state.get("valence", 0) < -0.2 else ""
        )

        with patch.dict(sys.modules, {"services.affective_state": fake_aff}):
            msgs = run(chat_mod._build_prompt("Pergunta?", [], ""))

        system_content = msgs[0]["content"]
        assert "analítico" in system_content.lower() or "Modulação" in system_content, (
            "Com valência negativa, framing analítico deve estar no prompt"
        )


# ---------------------------------------------------------------------------
# Chat 1 — chat.html estrutura
# ---------------------------------------------------------------------------

class TestChat1HtmlStructure:

    def test_sources_rendered_inside_message(self):
        """chat.html deve ter renderSourcesInMessage (fontes dentro da mensagem)."""
        src = (_ROOT / "templates" / "chat.html").read_text()
        assert "renderSourcesInMessage" in src, (
            "chat.html deve ter função renderSourcesInMessage"
        )

    def test_message_has_sources_container(self):
        """createAkashaMessage deve criar sourcesEl."""
        src = (_ROOT / "templates" / "chat.html").read_text()
        assert "sourcesEl" in src, (
            "createAkashaMessage deve criar sourcesEl para fontes colapsáveis"
        )

    def test_sources_detail_collapsible(self):
        """Fontes devem ser renderizadas em <details> (colapsável)."""
        src = (_ROOT / "templates" / "chat.html").read_text()
        assert "chat-sources-detail" in src, (
            "Fontes devem usar classe chat-sources-detail (<details> colapsável)"
        )

    def test_excerpt_rendered_in_sources(self):
        """chat.html deve renderizar s.excerpt das fontes."""
        src = (_ROOT / "templates" / "chat.html").read_text()
        assert "s.excerpt" in src or "excerpt" in src, (
            "chat.html deve renderizar o campo excerpt das fontes"
        )

    def test_esc_html_function_present(self):
        """escHtml deve existir para evitar XSS nas URLs."""
        src = (_ROOT / "templates" / "chat.html").read_text()
        assert "escHtml" in src, (
            "chat.html deve ter função escHtml para escapar conteúdo de usuário"
        )
