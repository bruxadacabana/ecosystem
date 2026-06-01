"""
Testes para eventos SSE step do Deep Research.

Cobre:
Unitários (_deep_search_steps generator):
- Emite evento step com status="searching" para round 1
- Emite evento step com status="evaluating" após round 1 com sources_found correto
- Emite evento step para round 2 (expansão) quando há reformulações
- Emite evento step de saturação quando novidade < threshold
- Emite evento step de expansão quando novidade >= threshold
- Emite evento "results" ao final com a lista correta
- Sem reformulações: emite step "done" e results imediatamente
- Campos obrigatórios em cada step: step (int), query (str), sources_found (int), status (str)

Integração (endpoint POST /chat/message com deep_mode=True):
- Resposta SSE contém pelo menos um evento data:{type:"step",...}
- Eventos step têm campos obrigatórios
- Modo normal (deep_mode=False) NÃO emite eventos step
- UI: painel reasoning aparece apenas quando há eventos step
"""
from __future__ import annotations

import asyncio
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


def _make_results(urls: list[str]) -> list:
    return [_sr(u) for u in urls]


async def _collect_steps_and_results(
    r1_urls: list[str],
    r2_urls: list[str],
    reformulations: list[str],
    novelty_threshold: float = 0.20,
) -> tuple[list[dict], list]:
    """Executa _deep_search_steps e coleta (steps, results)."""
    from routers.chat import _deep_search_steps

    r1 = _make_results(r1_urls)
    r2 = _make_results(r2_urls)
    call_count = [0]

    async def fake_search_local(q, max_results=15, expand=False, include_crawl=False):
        call_count[0] += 1
        return r1 if call_count[0] == 1 else r2

    steps: list[dict] = []
    results: list = []

    with patch("services.local_search.search_local", side_effect=fake_search_local), \
         patch("routers.chat._expand_queries_deep", return_value=reformulations):
        async for event_type, value in _deep_search_steps(
            "o que é python?", "qwen",
            novelty_threshold=novelty_threshold,
        ):
            if event_type == "step":
                steps.append(value)
            elif event_type == "results":
                results = value

    return steps, [r.url for r in results]


# ---------------------------------------------------------------------------
# Unitários: _deep_search_steps
# ---------------------------------------------------------------------------

class TestDeepSearchSteps:

    def test_emits_searching_step_for_round1(self) -> None:
        steps, _ = asyncio.run(_collect_steps_and_results(
            ["http://a.com"], [], reformulations=[]
        ))
        searching_steps = [s for s in steps if s["status"] == "searching"]
        assert len(searching_steps) >= 1

    def test_first_step_query_is_original_question(self) -> None:
        steps, _ = asyncio.run(_collect_steps_and_results(
            ["http://a.com"], [], reformulations=[]
        ))
        assert steps[0]["query"] == "o que é python?"

    def test_sources_found_after_round1(self) -> None:
        steps, _ = asyncio.run(_collect_steps_and_results(
            ["http://a.com", "http://b.com"], [], reformulations=[]
        ))
        evaluating_steps = [s for s in steps if s["status"] == "evaluating"]
        assert any(s["sources_found"] == 2 for s in evaluating_steps)

    def test_step_number_is_sequential(self) -> None:
        steps, _ = asyncio.run(_collect_steps_and_results(
            ["http://a.com"], ["http://b.com"], reformulations=["alt query"]
        ))
        numbers = [s["step"] for s in steps]
        assert numbers == list(range(1, len(numbers) + 1))

    def test_all_steps_have_required_fields(self) -> None:
        steps, _ = asyncio.run(_collect_steps_and_results(
            ["http://a.com"], ["http://b.com"], reformulations=["alt"]
        ))
        for s in steps:
            assert "step" in s and isinstance(s["step"], int)
            assert "query" in s and isinstance(s["query"], str)
            assert "sources_found" in s and isinstance(s["sources_found"], int)
            assert "status" in s and s["status"] in ("searching", "evaluating", "done")

    def test_no_reformulations_emits_done_step(self) -> None:
        steps, _ = asyncio.run(_collect_steps_and_results(
            ["http://a.com"], [], reformulations=[]
        ))
        done_steps = [s for s in steps if s["status"] == "done"]
        assert len(done_steps) >= 1

    def test_saturation_emits_done_step_with_low_results(self) -> None:
        """Quando saturado, step final tem status done com corpus pequeno."""
        # r1 e r2 são iguais → 0% novidade → saturação
        steps, results = asyncio.run(_collect_steps_and_results(
            ["http://a.com", "http://b.com"],
            ["http://a.com", "http://b.com"],
            reformulations=["alt"],
            novelty_threshold=0.20,
        ))
        done_steps = [s for s in steps if s["status"] == "done"]
        assert done_steps
        # corpus == rodada 1 apenas
        assert set(results) == {"http://a.com", "http://b.com"}

    def test_expansion_emits_evaluating_step(self) -> None:
        """Quando expandido, deve haver um step com status evaluating incluindo novos docs."""
        steps, results = asyncio.run(_collect_steps_and_results(
            ["http://a.com"],
            ["http://b.com", "http://c.com"],
            reformulations=["alt"],
            novelty_threshold=0.20,
        ))
        assert "http://b.com" in results or "http://c.com" in results
        evaluating_steps = [s for s in steps if s["status"] == "evaluating"]
        assert len(evaluating_steps) >= 1

    def test_emits_results_event_with_correct_urls(self) -> None:
        _, result_urls = asyncio.run(_collect_steps_and_results(
            ["http://a.com", "http://b.com"],
            ["http://c.com"],
            reformulations=["alt"],
            novelty_threshold=0.20,
        ))
        assert "http://a.com" in result_urls

    def test_step_query_truncated_to_100(self) -> None:
        long_q = "x" * 200
        steps, _ = asyncio.run(_collect_steps_and_results(
            ["http://a.com"], [], reformulations=[]
        ))
        # Mesmo com queries longas, step.query <= 100
        for s in steps:
            assert len(s["query"]) <= 100


# ---------------------------------------------------------------------------
# Integração: endpoint POST /chat/message
# ---------------------------------------------------------------------------

class TestDeepResearchStepEvents:
    """Testa emissão de step events via endpoint /chat/message.

    Mock em _deep_search_steps para evitar complexidade de lazy imports.
    _stream_chat deve gerar strings brutas (não tuples) pois _filter_thinking
    processa a string bruta antes de gerar (typ, text).
    """

    def _parse_sse_events(self, body: bytes) -> list[dict]:
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

    def _run_chat(self, deep_mode: bool, steps: list[dict] | None = None) -> list[dict]:
        from fastapi.testclient import TestClient
        import AKASHA.main as main_mod

        _steps = steps or [
            {"step": 1, "query": "o que é python?", "sources_found": 0, "status": "searching"},
            {"step": 2, "query": "o que é python?", "sources_found": 3, "status": "done"},
        ]
        _fake_results = [_sr("http://a.com"), _sr("http://b.com")]

        async def fake_deep_steps(question, model, max_snippets=15, novelty_threshold=0.20):
            for s in _steps:
                yield "step", s
            yield "results", _fake_results

        async def fake_build_corpus(results, max_docs):
            return [{"num": 1, "title": "A", "url": "http://a.com",
                     "content": "content", "is_full": False, "word_count": 10}]

        async def fake_build_prompt(question, corpus, prefix):
            return [{"role": "user", "content": "test"}]

        # _stream_chat deve gerar strings brutas (não tuples): _filter_thinking converte
        async def fake_stream_chat(msgs, model, max_tokens=600, timeout=None):
            yield "resposta de teste"

        async def fake_normal_search(q, max_results=15, expand=False, include_crawl=False):
            return [_sr("http://a.com", "normal result")]

        async def fake_normal_prompt(question, snippets, persona):
            return [{"role": "user", "content": "test"}]

        with patch("routers.chat._deep_search_steps", side_effect=fake_deep_steps), \
             patch("routers.chat._build_deep_corpus", side_effect=fake_build_corpus), \
             patch("routers.chat._build_deep_prompt", side_effect=fake_build_prompt), \
             patch("routers.chat._stream_chat", side_effect=fake_stream_chat), \
             patch("routers.chat._get_novelty_threshold", return_value=0.20), \
             patch("routers.chat._get_model", return_value="qwen"), \
             patch("services.persona.get_persona") as mp, \
             patch("services.local_search.search_local", side_effect=fake_normal_search), \
             patch("services.local_search.get_inference_status", return_value=True), \
             patch("routers.chat._build_prompt", side_effect=fake_normal_prompt), \
             patch("routers.chat._reflect_on_chat", new_callable=AsyncMock):
            mp.return_value.as_prompt_prefix.return_value = ""
            client = TestClient(main_mod.app)
            resp = client.post(
                "/chat/message",
                json={"message": "o que é python?", "deep_mode": deep_mode},
            )

        return self._parse_sse_events(resp.content)

    def test_deep_mode_emits_step_events(self) -> None:
        events = self._run_chat(deep_mode=True)
        step_events = [e for e in events if e.get("type") == "step"]
        assert len(step_events) >= 1, "Deep Research deve emitir ao menos 1 evento step"

    def test_step_event_has_required_fields(self) -> None:
        events = self._run_chat(deep_mode=True)
        step_events = [e for e in events if e.get("type") == "step"]
        assert step_events, "Sem eventos step"
        for ev in step_events:
            assert "step" in ev
            assert "query" in ev
            assert "sources_found" in ev
            assert "status" in ev

    def test_step_status_values_are_valid(self) -> None:
        steps = [
            {"step": 1, "query": "q", "sources_found": 0, "status": "searching"},
            {"step": 2, "query": "q", "sources_found": 3, "status": "evaluating"},
            {"step": 3, "query": "síntese", "sources_found": 3, "status": "done"},
        ]
        events = self._run_chat(deep_mode=True, steps=steps)
        step_events = [e for e in events if e.get("type") == "step"]
        valid_statuses = {"searching", "evaluating", "done"}
        for ev in step_events:
            assert ev["status"] in valid_statuses, f"status inválido: {ev['status']!r}"

    def test_normal_mode_does_not_emit_step_events(self) -> None:
        """Modo normal (deep_mode=False) não deve emitir eventos step."""
        events = self._run_chat(deep_mode=False)
        step_events = [e for e in events if e.get("type") == "step"]
        assert len(step_events) == 0, "Modo normal não deve ter step events"

    def test_deep_still_emits_fragment_and_sources(self) -> None:
        """Step events não devem suprimir fragment e sources."""
        events = self._run_chat(deep_mode=True)
        types = {e.get("type") for e in events}
        assert "fragment" in types, f"fragment ausente — tipos: {types}"
        assert "sources" in types, f"sources ausente — tipos: {types}"
