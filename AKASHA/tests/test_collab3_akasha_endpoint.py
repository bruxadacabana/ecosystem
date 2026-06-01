"""
Testes Collab 3 — AKASHA endpoint /friendship/feedback + on_url_feedback.

Requer AKASHA venv (fastapi, aiosqlite).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROOT = str(Path(__file__).parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class TestFriendshipFeedbackEndpoint:

    def test_endpoint_registered_in_app(self) -> None:
        import AKASHA.main as main_mod
        routes = [getattr(r, "path", "") for r in main_mod.app.routes]
        assert "/friendship/feedback" in routes

    def test_post_feedback_returns_204(self) -> None:
        from fastapi.testclient import TestClient
        import AKASHA.main as main_mod

        client = TestClient(main_mod.app, raise_server_exceptions=False)
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

        called: list[tuple] = []

        def _fake_feedback(url: str, is_positive: bool) -> None:
            called.append((url, is_positive))

        # friendship.py importa 'from services.knowledge_worker import on_url_feedback'
        # (sem o prefixo AKASHA) — o patch deve ser no mesmo namespace
        with patch("services.knowledge_worker.on_url_feedback", new=_fake_feedback):
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

    def test_friendship_router_prefix(self) -> None:
        """Verifica que o router tem prefix /friendship."""
        from AKASHA.routers.friendship import router
        assert router.prefix == "/friendship"


class TestOnUrlFeedback:

    def test_positive_feedback_records_gratification_appraisal(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        page_knowledge = {
            "url": "http://x.com", "title": "X",
            "topics": ["python", "machine", "learning"],
            "entities": [], "source_type": "crawled", "processed_at": "",
        }

        async def _run() -> None:
            async def _fake_get_pk(url: str):
                return page_knowledge

            with patch("database.get_page_knowledge", side_effect=_fake_get_pk), \
                 patch("database.update_topic_score", new_callable=AsyncMock), \
                 patch("services.affective_state.record_appraisal", new_callable=AsyncMock) as mock_ap:
                await kw._process_url_feedback("http://x.com", is_positive=True)
                assert mock_ap.called
                event_name = mock_ap.call_args[0][0]
                assert "positive" in event_name

        asyncio.run(_run())

    def test_negative_feedback_records_vigilance_appraisal(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        page_knowledge = {
            "url": "http://x.com", "title": "X",
            "topics": ["python"], "entities": [], "source_type": "crawled", "processed_at": "",
        }

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

        asyncio.run(_run())

    def test_positive_feedback_boosts_topics(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        page_knowledge = {
            "url": "http://x.com", "title": "X",
            "topics": ["python", "machine", "learning"],
            "entities": [], "source_type": "crawled", "processed_at": "",
        }
        updated: list[tuple] = []

        async def _run() -> None:
            async def _fake_get_pk(url: str):
                return page_knowledge

            async def _fake_update(topic: str, delta: float) -> None:
                updated.append((topic, delta))

            with patch("database.get_page_knowledge", side_effect=_fake_get_pk), \
                 patch("database.update_topic_score", side_effect=_fake_update), \
                 patch("services.affective_state.record_appraisal", new_callable=AsyncMock):
                await kw._process_url_feedback("http://x.com", is_positive=True)

        asyncio.run(_run())
        assert len(updated) > 0
        for _, delta in updated:
            assert delta == 0.3

    def test_appraisal_pleasantness_differs_positive_vs_negative(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        pk = {"url": "u", "title": "T", "topics": ["topic"], "entities": [], "source_type": "crawled", "processed_at": ""}

        results: dict[str, float] = {}

        async def _run_both() -> None:
            async def _fake_get_pk(url):
                return pk

            with patch("database.get_page_knowledge", side_effect=_fake_get_pk), \
                 patch("database.update_topic_score", new_callable=AsyncMock), \
                 patch("services.affective_state.record_appraisal", new_callable=AsyncMock) as m:
                await kw._process_url_feedback("u", is_positive=True)
                if m.called:
                    # record_appraisal(event, novelty, pleasantness, goal_relevance, coping, event_ref=...)
                    results["pos"] = m.call_args.kwargs.get("pleasantness", m.call_args[0][2] if len(m.call_args[0]) > 2 else 0.0)

            with patch("database.get_page_knowledge", side_effect=_fake_get_pk), \
                 patch("database.update_topic_score", new_callable=AsyncMock), \
                 patch("services.affective_state.record_appraisal", new_callable=AsyncMock) as m:
                await kw._process_url_feedback("u", is_positive=False)
                if m.called:
                    results["neg"] = m.call_args.kwargs.get("pleasantness", m.call_args[0][2] if len(m.call_args[0]) > 2 else 0.0)

        asyncio.run(_run_both())

        if "pos" in results and "neg" in results:
            assert results["pos"] > results["neg"]
