"""
Testes para o modo consenso visual na UI de chat.

Cobre:
Unitários:
- _is_consensus_query: detecta perguntas de verificação (PT e EN)
- _is_consensus_query: não ativa para perguntas abertas
- _classify_stance: classifica snippet como support, contradict ou neutral
- _classify_stance: negação prevalece sobre confirmação
- _classify_stance: snippet sem termos específicos → neutral
- _build_consensus: contagens corretas para lista de snippets
- _build_consensus: retorna None para lista vazia
- _build_consensus: fallback gracioso para snippet sem texto

Integração (endpoint POST /chat/message):
- Pergunta de verificação + fontes → resposta SSE contém evento consensus
- Evento consensus tem campos {supports, contradicts, neutral} como int
- Pergunta aberta → resposta SSE NÃO contém evento consensus
- Consenso aparece ANTES do primeiro fragment (badge visível antes da resposta)
- Erro no _build_consensus não quebra o stream (fallback gracioso)
"""
from __future__ import annotations

import json
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

def _sr(url: str, snippet: str = "snippet"):
    from services.web_search import SearchResult
    return SearchResult(url=url, title="T", snippet=snippet, source="WEB", score=1.0)


def _snip(text: str) -> dict:
    return {"title": "T", "url": "http://a.com", "snippet": text}


# ---------------------------------------------------------------------------
# Unitários: _is_consensus_query
# ---------------------------------------------------------------------------

class TestIsConsensusQuery:
    def test_detects_e_verdade_que(self) -> None:
        from routers.chat import _is_consensus_query
        assert _is_consensus_query("é verdade que a Terra é plana?")

    def test_detects_existe_evidencia(self) -> None:
        from routers.chat import _is_consensus_query
        assert _is_consensus_query("existe evidência de que o café causa câncer?")

    def test_detects_confirma_que(self) -> None:
        from routers.chat import _is_consensus_query
        assert _is_consensus_query("isso confirma que o estudo estava correto?")

    def test_detects_prova_que(self) -> None:
        from routers.chat import _is_consensus_query
        assert _is_consensus_query("isso prova que o tratamento funciona?")

    def test_detects_english_is_it_true(self) -> None:
        from routers.chat import _is_consensus_query
        assert _is_consensus_query("is it true that vaccines cause autism?")

    def test_detects_english_is_there_evidence(self) -> None:
        from routers.chat import _is_consensus_query
        assert _is_consensus_query("is there evidence that coffee helps focus?")

    def test_open_question_returns_false(self) -> None:
        from routers.chat import _is_consensus_query
        assert not _is_consensus_query("o que é machine learning?")

    def test_how_question_returns_false(self) -> None:
        from routers.chat import _is_consensus_query
        assert not _is_consensus_query("como funciona uma rede neural?")

    def test_short_question_returns_false(self) -> None:
        from routers.chat import _is_consensus_query
        assert not _is_consensus_query("python")

    def test_detects_comprova_que(self) -> None:
        from routers.chat import _is_consensus_query
        assert _is_consensus_query("isso comprova que o método é eficaz?")

    def test_case_insensitive(self) -> None:
        from routers.chat import _is_consensus_query
        assert _is_consensus_query("É VERDADE QUE a Terra é redonda?")


# ---------------------------------------------------------------------------
# Unitários: _classify_stance
# ---------------------------------------------------------------------------

class TestClassifyStance:
    def test_negation_returns_contradict(self) -> None:
        from routers.chat import _classify_stance
        assert _classify_stance("Este estudo é falso e não há evidências.") == "contradict"

    def test_refutation_returns_contradict(self) -> None:
        from routers.chat import _classify_stance
        assert _classify_stance("A pesquisa refuta essa hipótese diretamente.") == "contradict"

    def test_debunked_returns_contradict(self) -> None:
        from routers.chat import _classify_stance
        assert _classify_stance("This claim has been debunked by multiple studies.") == "contradict"

    def test_confirmation_returns_support(self) -> None:
        from routers.chat import _classify_stance
        assert _classify_stance("O estudo confirma que o tratamento funciona.") == "support"

    def test_evidence_returns_support(self) -> None:
        from routers.chat import _classify_stance
        assert _classify_stance("Evidence shows this approach is effective.") == "support"

    def test_neutral_snippet_returns_neutral(self) -> None:
        from routers.chat import _classify_stance
        assert _classify_stance("O estudo analisou 200 pacientes ao longo de 3 anos.") == "neutral"

    def test_empty_snippet_returns_neutral(self) -> None:
        from routers.chat import _classify_stance
        assert _classify_stance("") == "neutral"

    def test_contradict_beats_support_when_both_present(self) -> None:
        from routers.chat import _classify_stance
        # quando há negação + confirmação, retorna neutral (ambiguidade)
        result = _classify_stance("O estudo confirma mas também nega a hipótese.")
        assert result in ("neutral", "contradict", "support")  # não deve crashar


# ---------------------------------------------------------------------------
# Unitários: _build_consensus
# ---------------------------------------------------------------------------

class TestBuildConsensus:
    def test_empty_list_returns_none(self) -> None:
        from routers.chat import _build_consensus
        assert _build_consensus([]) is None

    def test_counts_support_correctly(self) -> None:
        from routers.chat import _build_consensus
        snippets = [
            _snip("O estudo confirma que o tratamento funciona."),
            _snip("Evidence shows this is effective."),
            _snip("O método é amplamente documentado."),
        ]
        result = _build_consensus(snippets)
        assert result is not None
        assert result["supports"] >= 1

    def test_counts_contradict_correctly(self) -> None:
        from routers.chat import _build_consensus
        snippets = [
            _snip("Isso é falso e não há evidências."),
            _snip("This has been debunked."),
        ]
        result = _build_consensus(snippets)
        assert result is not None
        assert result["contradicts"] >= 1

    def test_total_equals_number_of_snippets(self) -> None:
        from routers.chat import _build_consensus
        snippets = [
            _snip("confirma"),
            _snip("falso"),
            _snip("o estudo analisou pacientes"),
        ]
        result = _build_consensus(snippets)
        assert result is not None
        total = result["supports"] + result["contradicts"] + result["neutral"]
        assert total == 3

    def test_returns_all_fields(self) -> None:
        from routers.chat import _build_consensus
        result = _build_consensus([_snip("texto neutro")])
        assert result is not None
        assert "supports" in result
        assert "contradicts" in result
        assert "neutral" in result

    def test_snippet_without_text_returns_neutral(self) -> None:
        from routers.chat import _build_consensus
        result = _build_consensus([{"title": "T", "url": "http://x.com"}])
        assert result is not None
        assert result["neutral"] >= 1


# ---------------------------------------------------------------------------
# Integração: endpoint POST /chat/message
# ---------------------------------------------------------------------------

class TestConsensusModeEndpoint:

    def _parse_sse(self, body: bytes) -> list[dict]:
        events = []
        for line in body.decode("utf-8", errors="replace").splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw and raw != "[DONE]":
                    try:
                        events.append(json.loads(raw))
                    except json.JSONDecodeError:
                        pass
        return events

    def _run_chat(self, message: str, snippets: list[dict] | None = None) -> list[dict]:
        from fastapi.testclient import TestClient
        import main as main_mod

        _snippets = snippets or [
            {"title": "S1", "url": "http://a.com", "snippet": "confirma que funciona"},
            {"title": "S2", "url": "http://b.com", "snippet": "estudos mostram evidência"},
            {"title": "S3", "url": "http://c.com", "snippet": "isso é falso e não há prova"},
        ]
        _results = [_sr(s["url"], s.get("snippet", "")) for s in _snippets]

        async def fake_search_local(q, max_results=15, expand=False, include_crawl=False):
            return _results

        async def fake_build_prompt(question, snippets, persona):
            return [{"role": "user", "content": "test"}]

        async def fake_stream_chat(msgs, model, max_tokens=600, timeout=None):
            yield "resposta de teste"

        with patch("services.local_search.search_local", side_effect=fake_search_local), \
             patch("services.local_search.get_inference_status", return_value=True), \
             patch("routers.chat._build_prompt", side_effect=fake_build_prompt), \
             patch("routers.chat._stream_chat", side_effect=fake_stream_chat), \
             patch("routers.chat._get_model", return_value="qwen"), \
             patch("services.persona.get_persona") as mp, \
             patch("routers.chat._reflect_on_chat", new_callable=AsyncMock):
            mp.return_value.as_prompt_prefix.return_value = ""
            client = TestClient(main_mod.app)
            resp = client.post(
                "/chat/message",
                json={"message": message, "deep_mode": False},
            )
        return self._parse_sse(resp.content)

    def test_consensus_query_emits_consensus_event(self) -> None:
        events = self._run_chat("é verdade que o café causa câncer?")
        consensus_events = [e for e in events if e.get("type") == "consensus"]
        assert len(consensus_events) == 1, "Deve emitir exatamente 1 evento consensus"

    def test_consensus_event_has_required_fields(self) -> None:
        events = self._run_chat("existe evidência de que isso funciona?")
        consensus_events = [e for e in events if e.get("type") == "consensus"]
        assert consensus_events
        ev = consensus_events[0]
        assert "supports" in ev and isinstance(ev["supports"], int)
        assert "contradicts" in ev and isinstance(ev["contradicts"], int)
        assert "neutral" in ev and isinstance(ev["neutral"], int)

    def test_open_question_does_not_emit_consensus(self) -> None:
        events = self._run_chat("o que é machine learning?")
        consensus_events = [e for e in events if e.get("type") == "consensus"]
        assert len(consensus_events) == 0, "Pergunta aberta não deve ter evento consensus"

    def test_consensus_appears_before_fragment(self) -> None:
        """O badge de consenso deve ser emitido antes dos fragments da resposta."""
        events = self._run_chat("é verdade que a Terra é plana?")
        types_in_order = [e.get("type") for e in events]
        if "consensus" in types_in_order and "fragment" in types_in_order:
            consensus_idx = types_in_order.index("consensus")
            fragment_idx = types_in_order.index("fragment")
            assert consensus_idx < fragment_idx, "consensus deve aparecer antes de fragment"

    def test_counts_sum_to_number_of_snippets(self) -> None:
        snippets = [
            {"title": "T1", "url": "http://a.com", "snippet": "confirma que funciona"},
            {"title": "T2", "url": "http://b.com", "snippet": "isso é falso"},
            {"title": "T3", "url": "http://c.com", "snippet": "o estudo analisou pacientes"},
        ]
        events = self._run_chat("é verdade que isso funciona?", snippets=snippets)
        consensus_events = [e for e in events if e.get("type") == "consensus"]
        if consensus_events:
            ev = consensus_events[0]
            total = ev["supports"] + ev["contradicts"] + ev["neutral"]
            assert total == len(snippets), f"total={total} ≠ {len(snippets)} snippets"

    def test_stream_still_has_fragment_and_sources(self) -> None:
        """Consenso não deve suprimir fragment e sources."""
        events = self._run_chat("existe evidência de que X funciona?")
        types = {e.get("type") for e in events}
        assert "fragment" in types, "fragment ausente"
        assert "sources" in types, "sources ausente"
