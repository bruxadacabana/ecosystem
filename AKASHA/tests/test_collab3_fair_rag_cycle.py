"""
Testes Collab 3 — AKASHA: endpoint /friendship/feedback e on_url_feedback.

Cobre (lado AKASHA):
- /friendship/feedback está registrado no app
- POST /friendship/feedback retorna 204 para feedback positivo e negativo
- POST /friendship/feedback chama on_url_feedback com url e is_positive corretos
- POST /friendship/feedback retorna 422 para body inválido
- on_url_feedback positivo dispara appraisal de gratificação e boost de tópicos
- on_url_feedback negativo dispara appraisal de vigilância
- on_url_feedback com URL desconhecida não lança exceção

Os testes do lado Mnemosyne (_extract_topics_from_text, _update_shared_topic_profile,
_notify_akasha_url_feedback, apply_source_feedback) estão em
Mnemosyne/tests/test_collab3_fair_rag_cycle.py.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_AKASHA_ROOT = Path(__file__).parent.parent
if str(_AKASHA_ROOT) not in sys.path:
    sys.path.insert(0, str(_AKASHA_ROOT))


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
        with patch("services.knowledge_worker.on_url_feedback"):
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
        """Verifica que o endpoint chama on_url_feedback com url e is_positive corretos."""
        from fastapi.testclient import TestClient
        import AKASHA.main as main_mod

        called: list[tuple] = []

        def _fake_feedback(url: str, is_positive: bool) -> None:
            called.append((url, is_positive))

        # Patcha o atributo no mesmo módulo que friendship.py usa (_kw = services.knowledge_worker)
        with patch("services.knowledge_worker.on_url_feedback", side_effect=_fake_feedback):
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

        page_knowledge = {
            "url": "http://x.com", "title": "X",
            "topics": ["python", "ml"], "entities": [],
            "source_type": "crawled", "processed_at": "",
        }

        async def _run() -> None:
            with patch("database.get_page_knowledge", return_value=page_knowledge), \
                 patch("database.update_topic_score", new_callable=AsyncMock), \
                 patch("services.affective_state.record_appraisal", new_callable=AsyncMock) as mock_ap:
                await kw._process_url_feedback("http://x.com", is_positive=True)
                assert mock_ap.called
                event_name = mock_ap.call_args[0][0]
                assert "positive" in event_name or "gratif" in event_name

        asyncio.run(_run())

    def test_negative_feedback_records_appraisal(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        page_knowledge = {
            "url": "http://x.com", "title": "X",
            "topics": ["python"], "entities": [],
            "source_type": "crawled", "processed_at": "",
        }

        async def _run() -> None:
            with patch("database.get_page_knowledge", return_value=page_knowledge), \
                 patch("database.update_topic_score", new_callable=AsyncMock), \
                 patch("services.affective_state.record_appraisal", new_callable=AsyncMock) as mock_ap:
                await kw._process_url_feedback("http://x.com", is_positive=False)
                assert mock_ap.called
                event_name = mock_ap.call_args[0][0]
                assert "negative" in event_name or "vigil" in event_name

        asyncio.run(_run())

    def test_unknown_url_does_not_raise(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        async def _run() -> None:
            with patch("database.get_page_knowledge", return_value=None):
                await kw._process_url_feedback("http://unknown.com", is_positive=True)

        asyncio.run(_run())  # não deve lançar

    def test_positive_feedback_boosts_topics(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        page_knowledge = {
            "url": "http://x.com", "title": "X",
            "topics": ["python", "machine", "learning"], "entities": [],
            "source_type": "crawled", "processed_at": "",
        }
        updated_topics: list[tuple] = []

        async def _fake_update(topic: str, delta: float) -> None:
            updated_topics.append((topic, delta))

        async def _run() -> None:
            with patch("database.get_page_knowledge", return_value=page_knowledge), \
                 patch("database.update_topic_score", side_effect=_fake_update), \
                 patch("services.affective_state.record_appraisal", new_callable=AsyncMock):
                await kw._process_url_feedback("http://x.com", is_positive=True)

        asyncio.run(_run())
        assert len(updated_topics) > 0
        for _, delta in updated_topics:
            assert delta == 0.3  # delta de reforço positivo
