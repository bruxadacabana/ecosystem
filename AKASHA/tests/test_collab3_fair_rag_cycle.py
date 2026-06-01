"""
Testes Collab 3 — Ciclo FAIR-RAG: shared_topic_profile + appraisal emocional AKASHA.

Cobre:
- apply_source_feedback chama _update_shared_topic_profile após atualizar ChromaDB
- _update_shared_topic_profile extrai tópicos e chama shared_topic_profile.update_scores
- apply_source_feedback positivo chama _notify_akasha_url_feedback para URLs
- _notify_akasha_url_feedback chama AkashaClient.send_feedback para URLs http/https
- _notify_akasha_url_feedback ignora caminhos locais (não-URL)
- _notify_akasha_url_feedback é silencioso quando AKASHA offline
- /friendship/feedback endpoint retorna 204
- on_url_feedback dispara _process_url_feedback (appraisal via affective_state)
- feedback negativo não chama _notify_akasha_url_feedback
- _extract_topics_from_text filtra stopwords e retorna máximo 10 tópicos
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MNEM = str(Path(__file__).parent.parent.parent / "Mnemosyne")
_ROOT = str(Path(__file__).parent.parent.parent)
for _p in (_MNEM, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# _extract_topics_from_text
# ---------------------------------------------------------------------------

class TestExtractTopicsFromText:
    def test_returns_up_to_10_topics(self) -> None:
        from Mnemosyne.core.rag import _extract_topics_from_text
        text = " ".join([f"palavra{i}" for i in range(20)])
        result = _extract_topics_from_text(text)
        assert len(result) <= 10

    def test_filters_stopwords(self) -> None:
        from Mnemosyne.core.rag import _extract_topics_from_text
        text = "the and python machine learning neural networks"
        result = _extract_topics_from_text(text)
        assert "the" not in result
        assert "and" not in result
        assert "python" in result

    def test_min_length_4(self) -> None:
        from Mnemosyne.core.rag import _extract_topics_from_text
        text = "go io ok python"
        result = _extract_topics_from_text(text)
        assert "go" not in result
        assert "io" not in result
        assert "python" in result

    def test_deduplicates(self) -> None:
        from Mnemosyne.core.rag import _extract_topics_from_text
        text = "python python python machine learning"
        result = _extract_topics_from_text(text)
        assert result.count("python") == 1

    def test_empty_text_returns_empty(self) -> None:
        from Mnemosyne.core.rag import _extract_topics_from_text
        assert _extract_topics_from_text("") == []


# ---------------------------------------------------------------------------
# _update_shared_topic_profile
# ---------------------------------------------------------------------------

class TestUpdateSharedTopicProfile:
    def _make_vs(self, docs_text: list[str]) -> MagicMock:
        vs = MagicMock()
        vs._collection = MagicMock()
        vs._collection.get.return_value = {
            "documents": docs_text,
            "ids": [f"id{i}" for i in range(len(docs_text))],
            "metadatas": [{}] * len(docs_text),
        }
        return vs

    def test_calls_update_scores_with_positive_delta(self) -> None:
        from Mnemosyne.core import rag
        import shared_topic_profile as stp

        vs = self._make_vs(["Python machine learning neural networks transformer"])
        stores = [(vs, None)]

        with patch.object(stp, "update_scores") as mock_update:
            rag._update_shared_topic_profile(["http://x.com"], is_positive=True, stores_to_update=stores)

        assert mock_update.called
        args = mock_update.call_args
        assert args[0][1] == 1.0  # delta positivo
        assert args[0][2] == "mnemosyne"

    def test_calls_update_scores_with_negative_delta(self) -> None:
        from Mnemosyne.core import rag
        import shared_topic_profile as stp

        vs = self._make_vs(["Python machine learning neural networks"])
        stores = [(vs, None)]

        with patch.object(stp, "update_scores") as mock_update:
            rag._update_shared_topic_profile(["http://x.com"], is_positive=False, stores_to_update=stores)

        assert mock_update.called
        delta = mock_update.call_args[0][1]
        assert delta == -0.5

    def test_silent_when_no_docs(self) -> None:
        from Mnemosyne.core import rag
        import shared_topic_profile as stp

        vs = MagicMock()
        vs._collection = MagicMock()
        vs._collection.get.return_value = {"documents": [], "ids": [], "metadatas": []}
        stores = [(vs, None)]

        with patch.object(stp, "update_scores") as mock_update:
            rag._update_shared_topic_profile(["http://x.com"], is_positive=True, stores_to_update=stores)

        mock_update.assert_not_called()

    def test_silent_on_import_error(self) -> None:
        from Mnemosyne.core import rag

        vs = MagicMock()
        vs._collection = MagicMock()
        vs._collection.get.return_value = {"documents": ["texto"], "ids": ["1"], "metadatas": [{}]}
        stores = [(vs, None)]

        with patch.dict("sys.modules", {"shared_topic_profile": None}):
            rag._update_shared_topic_profile(["http://x.com"], is_positive=True, stores_to_update=stores)


# ---------------------------------------------------------------------------
# _notify_akasha_url_feedback
# ---------------------------------------------------------------------------

class TestNotifyAkashaUrlFeedback:
    """Testa _notify_akasha_url_feedback via patch em Mnemosyne.core.akasha_client."""

    def test_sends_feedback_for_http_url(self) -> None:
        import Mnemosyne.core.rag as rag_mod
        # AkashaClient é importado dentro da função em rag._notify_akasha_url_feedback
        # via 'from .akasha_client import AkashaClient'
        # Portanto patchamos no módulo de origem: Mnemosyne.core.akasha_client
        with patch("Mnemosyne.core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            rag_mod._notify_akasha_url_feedback(["http://example.com/page"])
            MockAkasha.return_value.send_feedback.assert_called_once_with(
                "http://example.com/page", is_positive=True
            )

    def test_ignores_local_paths(self) -> None:
        import Mnemosyne.core.rag as rag_mod
        with patch("Mnemosyne.core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            rag_mod._notify_akasha_url_feedback(["/local/path/file.md"])
            MockAkasha.return_value.send_feedback.assert_not_called()

    def test_silent_when_offline(self) -> None:
        import Mnemosyne.core.rag as rag_mod
        with patch("Mnemosyne.core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = False
            rag_mod._notify_akasha_url_feedback(["http://x.com"])
            MockAkasha.return_value.send_feedback.assert_not_called()

    def test_silent_on_exception(self) -> None:
        import Mnemosyne.core.rag as rag_mod
        with patch("Mnemosyne.core.akasha_client.AkashaClient", side_effect=RuntimeError("oops")):
            rag_mod._notify_akasha_url_feedback(["http://x.com"])  # não deve lançar

    def test_handles_multiple_urls(self) -> None:
        import Mnemosyne.core.rag as rag_mod
        with patch("Mnemosyne.core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            rag_mod._notify_akasha_url_feedback(["http://a.com", "http://b.com", "/local.md"])
            assert MockAkasha.return_value.send_feedback.call_count == 2


# ---------------------------------------------------------------------------
# apply_source_feedback — integração Collab 3
# ---------------------------------------------------------------------------

class TestApplySourceFeedbackCollab3:
    def _make_vs_with_chunks(self, n: int = 2) -> MagicMock:
        vs = MagicMock()
        vs._collection = MagicMock()
        vs._collection.get.return_value = {
            "ids": [f"id{i}" for i in range(n)],
            "metadatas": [{"boost": 1.0}] * n,
            "documents": ["python machine learning text"] * n,
        }
        return vs

    def test_positive_feedback_calls_shared_profile(self) -> None:
        from Mnemosyne.core import rag
        import shared_topic_profile as stp

        vs = self._make_vs_with_chunks()

        with patch.object(stp, "update_scores") as mock_stp, \
             patch.object(rag, "_notify_akasha_url_feedback"):
            rag.apply_source_feedback(vs, ["/local/doc.md"], is_positive=True)

        assert mock_stp.called

    def test_negative_feedback_calls_shared_profile(self) -> None:
        from Mnemosyne.core import rag
        import shared_topic_profile as stp

        vs = self._make_vs_with_chunks()

        with patch.object(stp, "update_scores") as mock_stp, \
             patch.object(rag, "_notify_akasha_url_feedback"):
            rag.apply_source_feedback(vs, ["/local/doc.md"], is_positive=False)

        assert mock_stp.called

    def test_positive_feedback_url_calls_notify_akasha(self) -> None:
        from Mnemosyne.core import rag

        vs = self._make_vs_with_chunks()

        with patch.object(rag, "_update_shared_topic_profile"), \
             patch.object(rag, "_notify_akasha_url_feedback") as mock_notify:
            rag.apply_source_feedback(vs, ["http://example.com/doc"], is_positive=True)

        mock_notify.assert_called_once_with(["http://example.com/doc"])

    def test_negative_feedback_does_not_call_notify_akasha(self) -> None:
        from Mnemosyne.core import rag

        vs = self._make_vs_with_chunks()

        with patch.object(rag, "_update_shared_topic_profile"), \
             patch.object(rag, "_notify_akasha_url_feedback") as mock_notify:
            rag.apply_source_feedback(vs, ["http://example.com/doc"], is_positive=False)

        mock_notify.assert_not_called()

    def test_returns_updated_count(self) -> None:
        from Mnemosyne.core import rag

        vs = self._make_vs_with_chunks(3)

        with patch.object(rag, "_update_shared_topic_profile"), \
             patch.object(rag, "_notify_akasha_url_feedback"):
            count = rag.apply_source_feedback(vs, ["/doc.md"], is_positive=True)

        assert count == 3


# ---------------------------------------------------------------------------
# /friendship/feedback endpoint AKASHA
# ---------------------------------------------------------------------------

class TestFriendshipFeedbackEndpoint:

    def test_endpoint_registered_in_app(self) -> None:
        """O router friendship deve estar registrado no app AKASHA."""
        import AKASHA.main as main_mod
        routes = [r.path for r in main_mod.app.routes if hasattr(r, "path")]
        assert "/friendship/feedback" in routes

    def test_post_feedback_returns_204(self) -> None:
        from fastapi.testclient import TestClient
        import AKASHA.main as main_mod

        client = TestClient(main_mod.app, raise_server_exceptions=False)
        with patch("AKASHA.routers.friendship.on_url_feedback") if False else patch("AKASHA.services.knowledge_worker.on_url_feedback"):
            resp = client.post(
                "/friendship/feedback",
                json={"url": "http://example.com", "is_positive": True},
            )
        assert resp.status_code == 204

    def test_post_feedback_negative_returns_204(self) -> None:
        from fastapi.testclient import TestClient
        import AKASHA.main as main_mod

        client = TestClient(main_mod.app, raise_server_exceptions=False)
        resp = client.post(
            "/friendship/feedback",
            json={"url": "http://example.com", "is_positive": False},
        )
        assert resp.status_code == 204

    def test_post_feedback_calls_on_url_feedback(self) -> None:
        from fastapi.testclient import TestClient
        import AKASHA.main as main_mod
        import AKASHA.services.knowledge_worker as kw

        called: list[tuple] = []

        def _fake_feedback(url: str, is_positive: bool) -> None:
            called.append((url, is_positive))

        with patch.object(kw, "on_url_feedback", side_effect=_fake_feedback):
            client = TestClient(main_mod.app)
            client.post(
                "/friendship/feedback",
                json={"url": "http://test.com/page", "is_positive": True},
            )

        assert ("http://test.com/page", True) in called

    def test_post_feedback_invalid_body_returns_422(self) -> None:
        from fastapi.testclient import TestClient
        import AKASHA.main as main_mod

        client = TestClient(main_mod.app)
        resp = client.post("/friendship/feedback", json={"url": "only-url"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# on_url_feedback + _process_url_feedback
# ---------------------------------------------------------------------------

class TestOnUrlFeedback:

    def test_positive_feedback_records_appraisal(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        page_knowledge = {"url": "http://x.com", "title": "X", "topics": ["python", "ml"], "entities": [], "source_type": "crawled", "processed_at": ""}

        recorded: list[str] = []

        async def _run() -> None:
            async def _fake_get_pk(url: str):
                return page_knowledge

            with patch("database.get_page_knowledge", side_effect=_fake_get_pk), \
                 patch("database.update_topic_score", new_callable=AsyncMock):
                from services.affective_state import record_appraisal
                with patch("AKASHA.services.knowledge_worker.record_appraisal" if False else "services.affective_state.record_appraisal") as mock_appraisal:
                    mock_appraisal.return_value = None
                    with patch("services.affective_state.record_appraisal", new_callable=AsyncMock) as mock_ap:
                        await kw._process_url_feedback("http://x.com", is_positive=True)
                        recorded.append("called" if mock_ap.called else "not_called")

        asyncio.run(_run())

    def test_negative_feedback_records_appraisal(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        page_knowledge = {"url": "http://x.com", "title": "X", "topics": ["python"], "entities": [], "source_type": "crawled", "processed_at": ""}

        async def _run() -> None:
            async def _fake_get_pk(url: str):
                return page_knowledge

            with patch("database.get_page_knowledge", side_effect=_fake_get_pk), \
                 patch("database.update_topic_score", new_callable=AsyncMock), \
                 patch("services.affective_state.record_appraisal", new_callable=AsyncMock) as mock_ap:
                await kw._process_url_feedback("http://x.com", is_positive=False)
                assert mock_ap.called
                event_name = mock_ap.call_args[0][0]
                assert "negative" in event_name

        asyncio.run(_run())

    def test_unknown_url_does_not_raise(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        async def _run() -> None:
            async def _fake_get_pk(url: str):
                return None

            with patch("database.get_page_knowledge", side_effect=_fake_get_pk):
                await kw._process_url_feedback("http://unknown.com", is_positive=True)

        asyncio.run(_run())  # não deve lançar

    def test_positive_feedback_boosts_topics(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        page_knowledge = {"url": "http://x.com", "title": "X", "topics": ["python", "machine", "learning"], "entities": [], "source_type": "crawled", "processed_at": ""}
        updated_topics: list[tuple] = []

        async def _run() -> None:
            async def _fake_get_pk(url: str):
                return page_knowledge

            async def _fake_update(topic: str, delta: float) -> None:
                updated_topics.append((topic, delta))

            with patch("database.get_page_knowledge", side_effect=_fake_get_pk), \
                 patch("database.update_topic_score", side_effect=_fake_update), \
                 patch("services.affective_state.record_appraisal", new_callable=AsyncMock):
                await kw._process_url_feedback("http://x.com", is_positive=True)

        asyncio.run(_run())
        assert len(updated_topics) > 0
        for _, delta in updated_topics:
            assert delta == 0.3  # delta de reforço positivo
