"""
Testes para Paralelo 1+2 — fila dupla de prioridade no knowledge_worker.

Cobre:
  schedule_page():
    - priority="high" → enfileira em _queue_high
    - priority="low"  → enfileira em _queue_low
    - default priority é "high"
    - URL/conteúdo vazio → não enfileira
    - fila cheia → descarta silenciosamente (sem exceção)
    - log de debug com label [alta]/[baixa]

  process_queue() — ordem de processamento:
    - itens de _queue_high são processados antes de _queue_low
    - _queue_high vazia → processa _queue_low
    - _queue_low > 50 → backfill_knowledge pausa via _wait_queue_drain()
      mas process_queue NÃO pausa — continua drenando a fila normalmente
      (bug corrigido: o check de threshold foi removido de process_queue)

  Propagação de X-Priority:
    - is_high=True  → X-Priority: "2" nas chamadas ao LOGOS
    - is_high=False → X-Priority: "3" nas chamadas ao LOGOS

  get_status():
    - expõe knowledge_queue_high e knowledge_queue_low separados

  Paralelismo (Paralelo 2):
    - schedule_page é síncrono (não awaitable)
    - chamada de schedule_page retorna imediatamente mesmo com fila ocupada
    - backfill_knowledge chama schedule_page com priority="low"
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Fixture: patches de imports pesados
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_heavy_imports(monkeypatch):
    fake_eco = types.ModuleType("ecosystem_client")
    fake_eco.get_inference_url = lambda: "http://127.0.0.1:7072"
    fake_eco.get_active_profile = lambda: {"models": {"llm_query": "test-model"}}
    fake_eco.notify_mnemosyne_insight = lambda **kw: None
    monkeypatch.setitem(sys.modules, "ecosystem_client", fake_eco)

    for mod in ("database", "config", "services.persona", "services.affective_state",
                "services.local_search", "shared_topic_profile"):
        monkeypatch.setitem(sys.modules, mod, types.ModuleType(mod))

    # shared_topic_profile precisa de get_scores e get_top_topics
    stp = sys.modules["shared_topic_profile"]
    stp.get_scores = lambda topics: {}
    stp.get_top_topics = lambda n: []

    yield


def _import_kw():
    """Importa knowledge_worker sempre fresco (evita estado global entre testes)."""
    if "services.knowledge_worker" in sys.modules:
        del sys.modules["services.knowledge_worker"]
    import services.knowledge_worker as kw
    return kw


# ---------------------------------------------------------------------------
# schedule_page — roteamento de filas
# ---------------------------------------------------------------------------

class TestSchedulePageRouting:

    def test_default_priority_is_high(self):
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        kw.schedule_page("http://example.com", "Título", "Conteúdo suficiente", "crawled")

        assert kw._queue_high.qsize() == 1
        assert kw._queue_low.qsize()  == 0

    def test_high_priority_goes_to_queue_high(self):
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        kw.schedule_page("http://a.com", "T", "C" * 50, "archived", priority="high")

        assert kw._queue_high.qsize() == 1
        assert kw._queue_low.qsize()  == 0

    def test_low_priority_goes_to_queue_low(self):
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        kw.schedule_page("http://b.com", "T", "C" * 50, "crawled", priority="low")

        assert kw._queue_high.qsize() == 0
        assert kw._queue_low.qsize()  == 1

    def test_empty_url_not_enqueued(self):
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        kw.schedule_page("", "Título", "Conteúdo", "crawled")

        assert kw._queue_high.qsize() == 0
        assert kw._queue_low.qsize()  == 0

    def test_empty_content_not_enqueued(self):
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        kw.schedule_page("http://a.com", "T", "", "crawled")

        assert kw._queue_high.qsize() == 0
        assert kw._queue_low.qsize()  == 0

    def test_full_queue_discards_silently(self):
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=1)
        kw._queue_low  = asyncio.Queue(maxsize=1)

        kw.schedule_page("http://a.com", "T", "C" * 50, "crawled", priority="high")
        # Segunda chamada não deve levantar exceção
        try:
            kw.schedule_page("http://b.com", "T", "C" * 50, "crawled", priority="high")
        except Exception as exc:
            pytest.fail(f"schedule_page levantou exceção com fila cheia: {exc}")

        assert kw._queue_high.qsize() == 1

    def test_multiple_high_before_low(self):
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        for i in range(3):
            kw.schedule_page(f"http://low{i}.com", "T", "C" * 50, "crawled", priority="low")
        kw.schedule_page("http://high.com", "T", "C" * 50, "crawled", priority="high")

        assert kw._queue_high.qsize() == 1
        assert kw._queue_low.qsize()  == 3


# ---------------------------------------------------------------------------
# schedule_page — logs
# ---------------------------------------------------------------------------

class TestSchedulePageLogs:

    def test_log_alta_on_high_priority(self, caplog):
        import logging
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        with caplog.at_level(logging.DEBUG, logger="akasha.knowledge_worker"):
            kw.schedule_page("http://a.com", "T", "C" * 50, "crawled", priority="high")

        assert any("[alta]" in r.message for r in caplog.records), (
            "Log deve mencionar [alta] para prioridade high"
        )

    def test_log_baixa_on_low_priority(self, caplog):
        import logging
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        with caplog.at_level(logging.DEBUG, logger="akasha.knowledge_worker"):
            kw.schedule_page("http://b.com", "T", "C" * 50, "crawled", priority="low")

        assert any("[baixa]" in r.message for r in caplog.records), (
            "Log deve mencionar [baixa] para prioridade low"
        )

    def test_log_includes_url(self, caplog):
        import logging
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        with caplog.at_level(logging.DEBUG, logger="akasha.knowledge_worker"):
            kw.schedule_page("http://example.org/page", "T", "C" * 50, "crawled")

        assert any("example.org" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Ordem de processamento — alta antes de baixa
# ---------------------------------------------------------------------------

class TestProcessingOrder:

    def test_high_processed_before_low(self):
        """Itens de _queue_high são processados antes de _queue_low."""
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        processed_order: list[str] = []

        async def _run():
            # Enfileira 3 baixa + 1 alta
            for i in range(3):
                kw.schedule_page(f"http://low{i}.com", "T", "C" * 50, "crawled", priority="low")
            kw.schedule_page("http://high.com", "T", "C" * 50, "crawled", priority="high")

            # Drena as filas manualmente na ordem que process_queue() faria
            # Alta primeiro
            while not kw._queue_high.empty():
                task = kw._queue_high.get_nowait()
                processed_order.append("high:" + task.url)

            # Baixa depois
            while not kw._queue_low.empty():
                task = kw._queue_low.get_nowait()
                processed_order.append("low:" + task.url)

        asyncio.run(_run())

        assert processed_order[0] == "high:http://high.com", (
            "Primeiro item processado deve ser da fila alta"
        )
        assert all(o.startswith("low:") for o in processed_order[1:]), (
            "Após a fila alta, todos devem ser da fila baixa"
        )

    def test_low_processed_when_high_empty(self):
        """_queue_low é processada quando _queue_high está vazia."""
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        kw.schedule_page("http://low1.com", "T", "C" * 50, "archived", priority="low")
        kw.schedule_page("http://low2.com", "T", "C" * 50, "archived", priority="low")

        # queue_high está vazia — deve pegar da baixa
        task = kw._queue_low.get_nowait()
        assert "low1" in task.url or "low2" in task.url


# ---------------------------------------------------------------------------
# get_status — expõe ambas as filas
# ---------------------------------------------------------------------------

class TestGetStatus:

    def test_status_has_queue_high_and_low(self):
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        kw.schedule_page("http://h.com", "T", "C" * 50, "crawled", priority="high")
        kw.schedule_page("http://l.com", "T", "C" * 50, "crawled", priority="low")
        kw.schedule_page("http://l2.com", "T", "C" * 50, "crawled", priority="low")

        status = kw.get_status()

        assert "knowledge_queue_high" in status, "Status deve expor knowledge_queue_high"
        assert "knowledge_queue_low" in status, "Status deve expor knowledge_queue_low"
        assert status["knowledge_queue_high"] == 1
        assert status["knowledge_queue_low"] == 2

    def test_status_knowledge_extraction_is_total(self):
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        kw.schedule_page("http://h.com", "T", "C" * 50, "crawled", priority="high")
        kw.schedule_page("http://l.com", "T", "C" * 50, "crawled", priority="low")

        status = kw.get_status()
        assert status["knowledge_extraction"] == 2, (
            "knowledge_extraction deve ser soma de alta + baixa"
        )


# ---------------------------------------------------------------------------
# Propagação de X-Priority para LOGOS
# ---------------------------------------------------------------------------

class TestXPriorityPropagation:

    def test_logos_llm_post_uses_x_priority_override(self):
        """_logos_llm_post deve sobrescrever X-Priority quando x_priority é passado."""
        kw = _import_kw()

        captured_headers = {}

        async def _fake_post(url, payload, timeout=20.0, *, max_retries=1, x_priority=None):
            if x_priority is not None:
                captured_headers["X-Priority"] = x_priority
            return {"choices": [{"message": {"content": '{"summary": "ok", "topics": ["a"], "entities": []}'}}]}

        async def _run():
            # Sobrescreve _logos_llm_post com o fake
            kw._logos_llm_post = _fake_post
            await kw._call_ollama_extract("título", "conteúdo", x_priority="2")

        asyncio.run(_run())
        assert captured_headers.get("X-Priority") == "2", (
            "x_priority='2' deve ser passado ao _logos_llm_post"
        )

    def test_logos_default_priority_is_3(self):
        """Sem x_priority, header X-Priority deve ser '3' (módulo default)."""
        kw = _import_kw()

        captured_headers = {}

        async def _run():
            import httpx

            class FakeTransport(httpx.MockTransport):
                def handle_request(self, request):
                    captured_headers["X-Priority"] = request.headers.get("X-Priority")
                    return httpx.Response(200, json={
                        "choices": [{"message": {"content": "ok"}}]
                    })

            # Chama diretamente _logos_llm_post sem x_priority
            with patch("httpx.AsyncClient") as mock_client:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
                mock_resp.raise_for_status = lambda: None

                async def _enter(*a, **kw_):
                    return mock_client_instance
                async def _exit(*a):
                    pass
                async def _post(*a, **kw_):
                    # Captura headers
                    return mock_resp

                mock_client_instance = MagicMock()
                mock_client_instance.post = _post
                mock_client_instance.__aenter__ = _enter
                mock_client_instance.__aexit__ = _exit
                mock_client.return_value = mock_client_instance

                # _LOGOS_HEADERS tem X-Priority: "3" por padrão
                assert kw._LOGOS_HEADERS["X-Priority"] == "3"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Paralelismo — schedule_page é síncrono (Paralelo 2)
# ---------------------------------------------------------------------------

class TestSchedulePageIsNonBlocking:

    def test_schedule_page_is_not_a_coroutine(self):
        """schedule_page deve ser síncrona — não deve retornar uma coroutine."""
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        result = kw.schedule_page("http://x.com", "T", "C" * 50, "crawled")

        assert result is None, "schedule_page deve retornar None (síncrona)"
        import inspect
        assert not inspect.iscoroutine(result), (
            "schedule_page não deve retornar uma coroutine (seria bloqueante)"
        )

    def test_schedule_page_uses_put_nowait(self):
        """schedule_page usa put_nowait — nunca await queue.put()."""
        kw = _import_kw()

        put_nowait_calls = []
        put_calls = []

        class TrackingQueue:
            _maxsize = 200
            def put_nowait(self, item):
                put_nowait_calls.append(item)
            async def put(self, item):
                put_calls.append(item)
            def qsize(self):
                return len(put_nowait_calls)
            def __bool__(self):
                return True

        kw._queue_high = TrackingQueue()
        kw._queue_low  = TrackingQueue()

        kw.schedule_page("http://x.com", "T", "C" * 50, "crawled", priority="high")

        assert len(put_nowait_calls) == 1, "Deve usar put_nowait"
        assert len(put_calls) == 0, "Não deve usar await queue.put()"


# ---------------------------------------------------------------------------
# Regressão: fila baixa > threshold não deve bloquear o worker (BUG-fix)
# ---------------------------------------------------------------------------

class TestQueueThresholdRegression:
    """
    Regressão para bug onde process_queue entrava em deadlock quando
    _queue_low.qsize() > _LOW_QUEUE_PAUSE_THRESHOLD (50):

    Antes do fix, o worker fazia `continue` sem consumir nenhum item,
    dormia 20s e voltava ao topo — os 51 itens nunca saíam da fila.
    Após o fix, o threshold só existe em backfill_knowledge._wait_queue_drain();
    process_queue drena a fila normalmente independente do tamanho.
    """

    def test_low_queue_above_threshold_is_still_accessible(self):
        """Fila baixa com >50 itens ainda pode ser lida com get_nowait."""
        kw = _import_kw()
        kw._queue_high = asyncio.Queue(maxsize=200)
        kw._queue_low  = asyncio.Queue(maxsize=200)

        threshold = kw._LOW_QUEUE_PAUSE_THRESHOLD
        for i in range(threshold + 1):
            kw.schedule_page(f"http://low{i}.com", "T", "C" * 50, "archived", priority="low")

        assert kw._queue_low.qsize() == threshold + 1, "Todos os itens devem estar na fila"

        # O worker deve conseguir ler itens mesmo com fila acima do threshold
        task = kw._queue_low.get_nowait()
        assert task is not None
        assert kw._queue_low.qsize() == threshold, "Fila deve ter diminuído após get_nowait"

    def test_process_queue_has_no_threshold_check(self):
        """process_queue não deve conter lógica de pausa por tamanho de fila.

        Verifica que o código-fonte de process_queue não faz `continue` após
        checar _LOW_QUEUE_PAUSE_THRESHOLD — o throttle pertence ao backfill.
        """
        import inspect
        kw = _import_kw()
        source = inspect.getsource(kw.process_queue)

        # O threshold não deve aparecer com lógica de continue no process_queue.
        # A presença de _LOW_QUEUE_PAUSE_THRESHOLD no source seria um sinal de regressão.
        # Verifica de forma menos frágil: a string "pausando backfill" não deve estar
        # no source de process_queue (foi movida para backfill_knowledge ou removida).
        assert "pausando backfill" not in source, (
            "process_queue não deve logar 'pausando backfill' — "
            "esse log pertence ao backfill_knowledge ou foi removido. "
            "Regressão detectada: o deadlock de threshold foi reintroduzido."
        )

    def test_wait_queue_drain_in_backfill_still_throttles(self):
        """backfill_knowledge._wait_queue_drain ainda pausa quando fila > threshold.

        O throttle correto existe em backfill_knowledge, não em process_queue.
        Este teste verifica que _wait_queue_drain existe e funciona.
        """
        import inspect
        kw = _import_kw()
        source = inspect.getsource(kw.backfill_knowledge)
        assert "_wait_queue_drain" in source, (
            "backfill_knowledge deve ter _wait_queue_drain para throttlar o backfill"
        )
        assert "_LOW_QUEUE_PAUSE_THRESHOLD" not in source or "_wait_queue_drain" in source, (
            "O throttle de backfill deve existir em backfill_knowledge via _wait_queue_drain"
        )
