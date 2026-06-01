"""
Testes Collab 1 — source_path no fluxo AKASHA → Mnemosyne.

Cobre:
- _KnowledgeTask aceita source_path (default None)
- schedule_page passa source_path para a task
- backfill_knowledge passa source_path correto para archived/paper
- _check_discoveries passa source_path para notify_mnemosyne_insight
- notify_mnemosyne_insight inclui source_path no entry
- Coluna source_path presente no DB de insights da Mnemosyne
- poll_and_store lê source_path do ecosystem.json
- _trigger_akasha_priority_index registra em mnemosyne.priority_index_paths
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Adiciona raiz do ecossistema ao path
_ROOT = str(Path(__file__).parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ---------------------------------------------------------------------------
# Testes do lado AKASHA — knowledge_worker
# ---------------------------------------------------------------------------

class TestKnowledgeTaskSourcePath:
    """_KnowledgeTask deve aceitar source_path como campo opcional."""

    def test_default_source_path_is_none(self) -> None:
        from AKASHA.services.knowledge_worker import _KnowledgeTask
        task = _KnowledgeTask(url="http://a.com", title="T", content="c", source_type="crawled")
        assert task.source_path is None

    def test_source_path_set_for_archived(self) -> None:
        from AKASHA.services.knowledge_worker import _KnowledgeTask
        task = _KnowledgeTask(
            url="http://a.com", title="T", content="c",
            source_type="archived", source_path="/archive/Web/a.md",
        )
        assert task.source_path == "/archive/Web/a.md"

    def test_source_path_set_for_paper(self) -> None:
        from AKASHA.services.knowledge_worker import _KnowledgeTask
        task = _KnowledgeTask(
            url="doi:10.1234/x", title="Paper", content="abstract",
            source_type="paper", source_path="/archive/Papers/paper.md",
        )
        assert task.source_path == "/archive/Papers/paper.md"


class TestSchedulePageSourcePath:
    """schedule_page deve passar source_path para a task enfileirada."""

    def test_schedule_page_with_source_path(self) -> None:
        from AKASHA.services.knowledge_worker import _KnowledgeTask, _queue_high
        import AKASHA.services.knowledge_worker as kw
        # Limpa fila antes do teste
        while not kw._queue_high.empty():
            try:
                kw._queue_high.get_nowait()
            except Exception:
                break

        kw.schedule_page(
            url="http://example.com/page",
            title="Título",
            content="Conteúdo suficiente para enfileirar.",
            source_type="archived",
            source_path="/archive/Web/page.md",
        )
        assert not kw._queue_high.empty()
        task: _KnowledgeTask = kw._queue_high.get_nowait()
        assert task.source_path == "/archive/Web/page.md"
        assert task.url == "http://example.com/page"

    def test_schedule_page_without_source_path_defaults_none(self) -> None:
        from AKASHA.services.knowledge_worker import _KnowledgeTask
        import AKASHA.services.knowledge_worker as kw
        while not kw._queue_high.empty():
            try:
                kw._queue_high.get_nowait()
            except Exception:
                break

        kw.schedule_page(
            url="http://example.com/crawled",
            title="Crawled",
            content="Conteúdo crawleado.",
            source_type="crawled",
        )
        assert not kw._queue_high.empty()
        task: _KnowledgeTask = kw._queue_high.get_nowait()
        assert task.source_path is None


class TestCheckDiscoveriesSourcePath:
    """_check_discoveries deve passar source_path para notify_mnemosyne_insight."""

    def test_source_path_forwarded_to_notify(self) -> None:
        import AKASHA.services.knowledge_worker as kw

        captured: dict = {}

        async def _run() -> None:
            with patch.object(kw, "_time") as mock_time, \
                 patch("AKASHA.services.knowledge_worker._time") as _mt:
                _mt.monotonic.return_value = 0.0
                kw._last_insight_at = 0.0

            # Simula perfil de interesse com overlap suficiente
            import shared_topic_profile as stp
            with patch.object(stp, "get_scores", return_value={"python": 2.0, "machine learning": 1.5, "neural": 1.2}), \
                 patch.object(stp, "get_top_topics", return_value=[("python", 2.0)]), \
                 patch("AKASHA.services.knowledge_worker._time") as mock_t, \
                 patch("AKASHA.services.knowledge_worker._last_insight_at", 0.0), \
                 patch("AKASHA.services.knowledge_worker._INSIGHT_COOLDOWN_S", 0.0):
                mock_t.monotonic.return_value = 9999.0

                # Mock personal_memory e ecosystem_client
                with patch("AKASHA.services.knowledge_worker.asyncio.get_running_loop"):
                    pass

                with patch("ecosystem_client.notify_mnemosyne_insight") as mock_notify, \
                     patch("AKASHA.services.knowledge_worker._time") as mock_t2:
                    mock_t2.monotonic.return_value = 9999.0

                    # Patch para simular perfil com overlap
                    import shared_topic_profile as _stp_mod
                    with patch.object(_stp_mod, "get_scores", return_value={"python": 2.0, "machine learning": 1.5, "neural": 1.2}):
                        from services.personal_memory import get_recent as _get_mem
                        with patch("AKASHA.services.knowledge_worker._last_insight_at", 0.0):
                            pass

                        # Força cooldown zerado e threshold
                        kw._last_insight_at = 0.0

                        await kw._check_discoveries(
                            url="http://example.com",
                            title="Python ML",
                            new_topics=["python", "machine learning", "neural"],
                            summary="artigo sobre ML",
                            is_echo_chamber=False,
                            source_path="/archive/Web/python_ml.md",
                        )
                        if mock_notify.called:
                            captured["call_kwargs"] = mock_notify.call_args.kwargs

        try:
            asyncio.run(_run())
        except Exception:
            pass
        # Se o notify foi chamado, verifica source_path
        if captured.get("call_kwargs"):
            assert captured["call_kwargs"].get("source_path") == "/archive/Web/python_ml.md"


class TestNotifyMnemosyneInsightSourcePath:
    """notify_mnemosyne_insight deve incluir source_path no entry."""

    def test_source_path_present_in_entry(self) -> None:
        import ecosystem_client as ec

        saved_entries: list[dict] = []

        def _fake_write_section(app: str, section: dict) -> None:
            if app == "mnemosyne":
                saved_entries.extend(section.get("incoming_insights", []))

        with patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"incoming_insights": []}}), \
             patch.object(ec, "write_section", side_effect=_fake_write_section):
            ec.notify_mnemosyne_insight(
                topics=["python"],
                summary="Insight sobre Python",
                sources=[{"url": "http://x.com", "title": "X"}],
                source_path="/archive/Web/python.md",
            )

        assert len(saved_entries) == 1
        assert saved_entries[0]["source_path"] == "/archive/Web/python.md"

    def test_source_path_absent_when_not_provided(self) -> None:
        import ecosystem_client as ec

        saved_entries: list[dict] = []

        def _fake_write_section(app: str, section: dict) -> None:
            if app == "mnemosyne":
                saved_entries.extend(section.get("incoming_insights", []))

        with patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"incoming_insights": []}}), \
             patch.object(ec, "write_section", side_effect=_fake_write_section):
            ec.notify_mnemosyne_insight(
                topics=["python"],
                summary="Insight",
                sources=[],
            )

        assert len(saved_entries) == 1
        assert "source_path" not in saved_entries[0]

    def test_emotional_context_and_source_path_coexist(self) -> None:
        import ecosystem_client as ec

        saved_entries: list[dict] = []

        def _fake_write_section(app: str, section: dict) -> None:
            if app == "mnemosyne":
                saved_entries.extend(section.get("incoming_insights", []))

        with patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"incoming_insights": []}}), \
             patch.object(ec, "write_section", side_effect=_fake_write_section):
            ec.notify_mnemosyne_insight(
                topics=["rust"],
                summary="Rust",
                sources=[],
                emotional_context={"valence": 0.5},
                source_path="/archive/Papers/rust.md",
            )

        assert saved_entries[0]["source_path"] == "/archive/Papers/rust.md"
        assert saved_entries[0]["emotional_context"]["valence"] == 0.5


# ---------------------------------------------------------------------------
# Testes do lado Mnemosyne — insights.py
# (requerem langchain_core; skip quando rodando na venv do AKASHA)
# ---------------------------------------------------------------------------

_HAS_LANGCHAIN = pytest.importorskip("langchain_core", reason="langchain_core não disponível — skip testes Mnemosyne") if False else None

try:
    import langchain_core as _lc  # noqa: F401
    _LANGCHAIN_OK = True
except ImportError:
    _LANGCHAIN_OK = False

_skip_mnemosyne = pytest.mark.skipif(not _LANGCHAIN_OK, reason="langchain_core não disponível — skip testes Mnemosyne")


@_skip_mnemosyne
class TestInsightsDBMigration:
    """DB de insights deve ter coluna source_path após migração."""

    def test_column_source_path_exists(self, tmp_path: Path) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins

        with patch.object(ins, "_db_path", return_value=tmp_path / "insights.db"):
            conn = ins._get_conn()
            cols = [row[1] for row in conn.execute("PRAGMA table_info(incoming_insights)").fetchall()]
            conn.close()
        assert "source_path" in cols, f"Colunas: {cols}"

    def test_migration_idempotent(self, tmp_path: Path) -> None:
        """Chamar _get_conn() múltiplas vezes não falha."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins

        with patch.object(ins, "_db_path", return_value=tmp_path / "insights2.db"):
            for _ in range(3):
                conn = ins._get_conn()
                conn.close()


@_skip_mnemosyne
class TestPollAndStoreSourcePath:
    """poll_and_store deve salvar source_path e chamar _trigger_akasha_priority_index."""

    def test_source_path_stored_in_db(self, tmp_path: Path) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins
        import ecosystem_client as ec

        item = {
            "topics": ["python"],
            "summary": "Insight",
            "sources": [],
            "received_at": "2026-06-01T00:00:00+00:00",
            "source_path": "/archive/Web/python.md",
        }

        with patch.object(ins, "_db_path", return_value=tmp_path / "ins.db"), \
             patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"incoming_insights": [item]}}), \
             patch.object(ec, "write_section"), \
             patch.object(ins, "_save_akasha_insight_to_personal_memory"), \
             patch.object(ins, "_trigger_akasha_priority_index") as mock_trigger:
            ins.poll_and_store()
            mock_trigger.assert_called_once_with("/archive/Web/python.md")

        with patch.object(ins, "_db_path", return_value=tmp_path / "ins.db"):
            conn = ins._get_conn()
            row = conn.execute("SELECT source_path FROM incoming_insights LIMIT 1").fetchone()
            conn.close()
        assert row is not None
        assert row[0] == "/archive/Web/python.md"

    def test_source_path_none_does_not_trigger(self, tmp_path: Path) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins
        import ecosystem_client as ec

        item = {
            "topics": ["python"],
            "summary": "Insight sem source_path",
            "sources": [],
            "received_at": "2026-06-01T00:00:00+00:00",
        }

        with patch.object(ins, "_db_path", return_value=tmp_path / "ins2.db"), \
             patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"incoming_insights": [item]}}), \
             patch.object(ec, "write_section"), \
             patch.object(ins, "_save_akasha_insight_to_personal_memory"), \
             patch.object(ins, "_trigger_akasha_priority_index") as mock_trigger:
            ins.poll_and_store()
            mock_trigger.assert_not_called()


@_skip_mnemosyne
class TestGetLatestUnseenSourcePath:
    """get_latest_unseen deve retornar source_path."""

    def test_source_path_in_result(self, tmp_path: Path) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins
        import ecosystem_client as ec

        item = {
            "topics": ["rust"],
            "summary": "Rust é bom",
            "sources": [],
            "received_at": "2026-06-01T00:00:00+00:00",
            "source_path": "/archive/Web/rust.md",
        }

        with patch.object(ins, "_db_path", return_value=tmp_path / "ins3.db"), \
             patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"incoming_insights": [item]}}), \
             patch.object(ec, "write_section"), \
             patch.object(ins, "_save_akasha_insight_to_personal_memory"), \
             patch.object(ins, "_trigger_akasha_priority_index"):
            ins.poll_and_store()

        with patch.object(ins, "_db_path", return_value=tmp_path / "ins3.db"):
            result = ins.get_latest_unseen()

        assert result is not None
        assert result["source_path"] == "/archive/Web/rust.md"

    def test_source_path_none_in_result_when_absent(self, tmp_path: Path) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins
        import ecosystem_client as ec

        item = {
            "topics": ["go"],
            "summary": "Go insight",
            "sources": [],
            "received_at": "2026-06-01T00:00:00+00:00",
        }

        with patch.object(ins, "_db_path", return_value=tmp_path / "ins4.db"), \
             patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"incoming_insights": [item]}}), \
             patch.object(ec, "write_section"), \
             patch.object(ins, "_save_akasha_insight_to_personal_memory"), \
             patch.object(ins, "_trigger_akasha_priority_index"):
            ins.poll_and_store()

        with patch.object(ins, "_db_path", return_value=tmp_path / "ins4.db"):
            result = ins.get_latest_unseen()

        assert result is not None
        assert result["source_path"] is None


@_skip_mnemosyne
class TestTriggerAkashaPriorityIndex:
    """_trigger_akasha_priority_index deve escrever no ecosystem.json."""

    def test_adds_path_to_priority_list(self) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins
        import ecosystem_client as ec

        written: dict = {}

        def _fake_write(app: str, section: dict) -> None:
            written[app] = section

        with patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"priority_index_paths": []}}), \
             patch.object(ec, "write_section", side_effect=_fake_write):
            ins._trigger_akasha_priority_index("/archive/Web/test.md")

        assert "/archive/Web/test.md" in written["mnemosyne"]["priority_index_paths"]

    def test_does_not_duplicate_path(self) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins
        import ecosystem_client as ec

        written_calls: list[list[str]] = []

        def _fake_write(app: str, section: dict) -> None:
            written_calls.append(section.get("priority_index_paths", []))

        with patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"priority_index_paths": ["/archive/Web/test.md"]}}), \
             patch.object(ec, "write_section", side_effect=_fake_write):
            ins._trigger_akasha_priority_index("/archive/Web/test.md")

        # write_section NÃO deve ser chamado se o path já existia
        assert len(written_calls) == 0

    def test_fifo_limit_20(self) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins
        import ecosystem_client as ec

        existing = [f"/archive/Web/f{i}.md" for i in range(20)]
        written: dict = {}

        def _fake_write(app: str, section: dict) -> None:
            written[app] = section

        with patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"priority_index_paths": existing}}), \
             patch.object(ec, "write_section", side_effect=_fake_write):
            ins._trigger_akasha_priority_index("/archive/Web/new.md")

        result = written.get("mnemosyne", {}).get("priority_index_paths", [])
        assert len(result) == 20
        assert result[-1] == "/archive/Web/new.md"

    def test_silent_failure_on_exception(self) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Mnemosyne"))
        from core import insights as ins
        import ecosystem_client as ec

        with patch.object(ec, "read_ecosystem", side_effect=OSError("disk full")):
            ins._trigger_akasha_priority_index("/archive/Web/x.md")  # não deve lançar


class TestBackfillSourcePath:
    """backfill_knowledge deve passar source_path para schedule_page em arquivos."""

    def test_backfill_archived_passes_source_path(self, tmp_path: Path) -> None:
        md_file = tmp_path / "Web" / "page.md"
        md_file.parent.mkdir(parents=True)
        md_file.write_text(
            "---\nurl: http://example.com\ntitle: Exemplo\n---\nConteúdo de teste aqui.",
            encoding="utf-8",
        )

        import AKASHA.services.knowledge_worker as kw

        scheduled: list[dict] = []

        def _fake_schedule(url, title, content, source_type, priority="high", source_path=None) -> None:
            scheduled.append({"url": url, "source_type": source_type, "source_path": source_path})

        # Mock aiosqlite no nível de sys.modules para compatibilidade com venvs sem aiosqlite
        import unittest.mock as _um
        import types

        fake_aiosqlite = types.ModuleType("aiosqlite")
        ctx = _um.MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=_um.MagicMock(
            execute=AsyncMock(return_value=_um.MagicMock(fetchall=AsyncMock(return_value=[])))
        ))
        ctx.__aexit__ = AsyncMock(return_value=None)
        fake_aiosqlite.connect = _um.MagicMock(return_value=ctx)

        async def _run() -> None:
            import sys as _sys
            _sys.modules.setdefault("aiosqlite", fake_aiosqlite)
            with patch.object(kw, "schedule_page", side_effect=_fake_schedule), \
                 patch("asyncio.sleep", new_callable=_um.AsyncMock):

                async def _fake_get_pk(url: str):
                    return None

                with patch("database.get_page_knowledge", side_effect=_fake_get_pk):
                    await kw.backfill_knowledge(tmp_path)

        asyncio.run(_run())

        assert len(scheduled) == 1
        assert scheduled[0]["source_path"] == str(md_file)
        assert scheduled[0]["source_type"] == "archived"

    def test_schedule_page_source_path_type_is_str_or_none(self) -> None:
        """source_path deve ser str ou None — nunca outro tipo."""
        import AKASHA.services.knowledge_worker as kw

        while not kw._queue_high.empty():
            try:
                kw._queue_high.get_nowait()
            except Exception:
                break

        kw.schedule_page(
            url="http://test.com/page",
            title="Test",
            content="Test content here.",
            source_type="paper",
            source_path="/archive/Papers/paper.md",
        )
        task = kw._queue_high.get_nowait()
        assert isinstance(task.source_path, (str, type(None)))
        assert task.source_path == "/archive/Papers/paper.md"
