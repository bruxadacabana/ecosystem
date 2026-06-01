"""
Testes Collab 3 — Mnemosyne: ciclo FAIR-RAG → shared_topic_profile + appraisal emocional.

Unitários:
- _extract_topics_from_text: filtragem de stopwords, comprimento mínimo, deduplica, máximo 10
- _update_shared_topic_profile: chama update_scores com delta correto; silencioso sem docs
- _notify_akasha_url_feedback: envia para URLs http, ignora locais, silencioso offline
- apply_source_feedback positivo chama _update_shared_topic_profile e _notify_akasha_url_feedback
- apply_source_feedback negativo chama _update_shared_topic_profile, não chama _notify_akasha_url_feedback
- apply_source_feedback retorna count correto

Integração:
- Ciclo completo positivo: feedback → shared_topic_profile atualizado + AKASHA notificada
- Ciclo completo negativo: feedback → shared_topic_profile atualizado, AKASHA não notificada
- Fallback se shared_topic_profile indisponível: apply_source_feedback não lança
- Fallback se AKASHA offline: apply_source_feedback não lança
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

_MNEM_ROOT = Path(__file__).parent.parent
_ECO_ROOT = Path(__file__).parent.parent.parent
for _p in (str(_MNEM_ROOT), str(_ECO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vs(docs_text: list[str] = None, n: int = 2) -> MagicMock:
    """Vectorstore mock com chunks de texto fixo."""
    texts = docs_text or ["python machine learning neural networks"] * n
    vs = MagicMock()
    vs._collection = MagicMock()
    vs._collection.get.return_value = {
        "ids": [f"id{i}" for i in range(len(texts))],
        "metadatas": [{"boost": 1.0, "source": f"/doc{i}.md"} for i in range(len(texts))],
        "documents": texts,
    }
    return vs


# ---------------------------------------------------------------------------
# _extract_topics_from_text
# ---------------------------------------------------------------------------

class TestExtractTopicsFromText:
    def test_returns_up_to_10_topics(self) -> None:
        from core.rag import _extract_topics_from_text
        text = " ".join([f"palavra{i}" for i in range(20)])
        result = _extract_topics_from_text(text)
        assert len(result) <= 10

    def test_filters_stopwords(self) -> None:
        from core.rag import _extract_topics_from_text
        text = "the and python machine learning neural networks"
        result = _extract_topics_from_text(text)
        assert "the" not in result
        assert "and" not in result
        assert "python" in result

    def test_min_length_4(self) -> None:
        from core.rag import _extract_topics_from_text
        text = "go io ok python"
        result = _extract_topics_from_text(text)
        assert "go" not in result
        assert "io" not in result
        assert "python" in result

    def test_deduplicates(self) -> None:
        from core.rag import _extract_topics_from_text
        text = "python python python machine learning"
        result = _extract_topics_from_text(text)
        assert result.count("python") == 1

    def test_empty_text_returns_empty(self) -> None:
        from core.rag import _extract_topics_from_text
        assert _extract_topics_from_text("") == []

    def test_returns_list_type(self) -> None:
        from core.rag import _extract_topics_from_text
        result = _extract_topics_from_text("python machine learning")
        assert isinstance(result, list)
        assert all(isinstance(t, str) for t in result)


# ---------------------------------------------------------------------------
# _update_shared_topic_profile
# ---------------------------------------------------------------------------

class TestUpdateSharedTopicProfile:

    def test_calls_update_scores_with_positive_delta(self) -> None:
        from core import rag
        import shared_topic_profile as stp

        vs = _make_vs(["Python machine learning neural networks transformer"])
        stores = [(vs, None)]

        with patch.object(stp, "update_scores") as mock_update:
            rag._update_shared_topic_profile(["http://x.com"], is_positive=True, stores_to_update=stores)

        assert mock_update.called
        args = mock_update.call_args
        assert args[0][1] == 1.0   # delta positivo
        assert args[0][2] == "mnemosyne"

    def test_calls_update_scores_with_negative_delta(self) -> None:
        from core import rag
        import shared_topic_profile as stp

        vs = _make_vs(["Python machine learning neural networks"])
        stores = [(vs, None)]

        with patch.object(stp, "update_scores") as mock_update:
            rag._update_shared_topic_profile(["http://x.com"], is_positive=False, stores_to_update=stores)

        assert mock_update.called
        delta = mock_update.call_args[0][1]
        assert delta == -0.5

    def test_silent_when_no_docs(self) -> None:
        from core import rag
        import shared_topic_profile as stp

        vs = MagicMock()
        vs._collection = MagicMock()
        vs._collection.get.return_value = {"documents": [], "ids": [], "metadatas": []}
        stores = [(vs, None)]

        with patch.object(stp, "update_scores") as mock_update:
            rag._update_shared_topic_profile(["http://x.com"], is_positive=True, stores_to_update=stores)

        mock_update.assert_not_called()

    def test_silent_on_import_error(self) -> None:
        from core import rag

        vs = _make_vs(["texto relevante sobre python"])
        stores = [(vs, None)]

        with patch.dict("sys.modules", {"shared_topic_profile": None}):
            # não deve lançar exceção
            rag._update_shared_topic_profile(["http://x.com"], is_positive=True, stores_to_update=stores)

    def test_uses_first_store_with_data(self) -> None:
        """Deve usar apenas o primeiro store que tem docs para aquele path."""
        from core import rag
        import shared_topic_profile as stp

        vs1 = MagicMock()
        vs1._collection = MagicMock()
        vs1._collection.get.return_value = {"documents": [], "ids": [], "metadatas": []}

        vs2 = _make_vs(["python machine learning"])
        stores = [(vs1, None), (vs2, None)]

        with patch.object(stp, "update_scores") as mock_update:
            rag._update_shared_topic_profile(["/doc.md"], is_positive=True, stores_to_update=stores)

        # update_scores deve ter sido chamado a partir do vs2
        assert mock_update.called


# ---------------------------------------------------------------------------
# _notify_akasha_url_feedback
# ---------------------------------------------------------------------------

class TestNotifyAkashaUrlFeedback:

    def test_sends_feedback_for_http_url(self) -> None:
        from core import rag as rag_mod
        with patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            rag_mod._notify_akasha_url_feedback(["http://example.com/page"])
            MockAkasha.return_value.send_feedback.assert_called_once_with(
                "http://example.com/page", is_positive=True
            )

    def test_sends_feedback_for_https_url(self) -> None:
        from core import rag as rag_mod
        with patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            rag_mod._notify_akasha_url_feedback(["https://secure.example.com/page"])
            MockAkasha.return_value.send_feedback.assert_called_once()

    def test_ignores_local_paths(self) -> None:
        from core import rag as rag_mod
        with patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            rag_mod._notify_akasha_url_feedback(["/local/path/file.md"])
            MockAkasha.return_value.send_feedback.assert_not_called()

    def test_silent_when_offline(self) -> None:
        from core import rag as rag_mod
        with patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = False
            rag_mod._notify_akasha_url_feedback(["http://x.com"])
            MockAkasha.return_value.send_feedback.assert_not_called()

    def test_silent_on_exception(self) -> None:
        from core import rag as rag_mod
        with patch("core.akasha_client.AkashaClient", side_effect=RuntimeError("oops")):
            rag_mod._notify_akasha_url_feedback(["http://x.com"])  # não deve lançar

    def test_handles_multiple_urls(self) -> None:
        from core import rag as rag_mod
        with patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            rag_mod._notify_akasha_url_feedback(["http://a.com", "http://b.com", "/local.md"])
            assert MockAkasha.return_value.send_feedback.call_count == 2

    def test_empty_list_does_not_call_akasha(self) -> None:
        from core import rag as rag_mod
        with patch("core.akasha_client.AkashaClient") as MockAkasha:
            rag_mod._notify_akasha_url_feedback([])
            MockAkasha.assert_not_called()


# ---------------------------------------------------------------------------
# apply_source_feedback — integração Collab 3
# ---------------------------------------------------------------------------

class TestApplySourceFeedbackCollab3:

    def test_positive_feedback_calls_shared_profile(self) -> None:
        from core import rag
        import shared_topic_profile as stp

        vs = _make_vs()

        with patch.object(stp, "update_scores") as mock_stp, \
             patch.object(rag, "_notify_akasha_url_feedback"):
            rag.apply_source_feedback(vs, ["/local/doc.md"], is_positive=True)

        assert mock_stp.called

    def test_negative_feedback_calls_shared_profile(self) -> None:
        from core import rag
        import shared_topic_profile as stp

        vs = _make_vs()

        with patch.object(stp, "update_scores") as mock_stp, \
             patch.object(rag, "_notify_akasha_url_feedback"):
            rag.apply_source_feedback(vs, ["/local/doc.md"], is_positive=False)

        assert mock_stp.called

    def test_positive_feedback_url_calls_notify_akasha(self) -> None:
        from core import rag

        vs = _make_vs()

        with patch.object(rag, "_update_shared_topic_profile"), \
             patch.object(rag, "_notify_akasha_url_feedback") as mock_notify:
            rag.apply_source_feedback(vs, ["http://example.com/doc"], is_positive=True)

        mock_notify.assert_called_once_with(["http://example.com/doc"])

    def test_negative_feedback_does_not_call_notify_akasha(self) -> None:
        from core import rag

        vs = _make_vs()

        with patch.object(rag, "_update_shared_topic_profile"), \
             patch.object(rag, "_notify_akasha_url_feedback") as mock_notify:
            rag.apply_source_feedback(vs, ["http://example.com/doc"], is_positive=False)

        mock_notify.assert_not_called()

    def test_returns_updated_count(self) -> None:
        from core import rag

        vs = _make_vs(n=3)

        with patch.object(rag, "_update_shared_topic_profile"), \
             patch.object(rag, "_notify_akasha_url_feedback"):
            count = rag.apply_source_feedback(vs, ["/doc.md"], is_positive=True)

        assert count == 3


# ---------------------------------------------------------------------------
# Integração — ciclo completo Collab 3
# ---------------------------------------------------------------------------

class TestCollab3IntegrationCycle:
    """Testes de integração: verifica o ciclo completo feedback → shared_topic_profile + AKASHA."""

    def test_positive_cycle_updates_profile_and_notifies_akasha(self) -> None:
        """Ciclo completo positivo: ChromaDB atualizado + shared_topic_profile + AKASHA notificada."""
        from core import rag
        import shared_topic_profile as stp

        vs = _make_vs(docs_text=["python machine learning transformers deep neural"])

        stp_calls: list[tuple] = []
        akasha_calls: list[tuple] = []

        def _fake_update_scores(topics: list[str], delta: float, source: str) -> None:
            stp_calls.append((topics, delta, source))

        with patch.object(stp, "update_scores", side_effect=_fake_update_scores), \
             patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            MockAkasha.return_value.send_feedback.side_effect = (
                lambda url, is_positive: akasha_calls.append((url, is_positive))
            )
            rag.apply_source_feedback(vs, ["http://example.com/article"], is_positive=True)

        assert len(stp_calls) > 0, "shared_topic_profile.update_scores não foi chamado"
        assert stp_calls[0][1] == 1.0, "delta deve ser +1.0 para feedback positivo"
        assert stp_calls[0][2] == "mnemosyne"

        assert ("http://example.com/article", True) in akasha_calls, \
            "AKASHA não foi notificada do feedback positivo"

    def test_negative_cycle_updates_profile_does_not_notify_akasha(self) -> None:
        """Ciclo completo negativo: shared_topic_profile atualizado, AKASHA não notificada."""
        from core import rag
        import shared_topic_profile as stp

        vs = _make_vs(docs_text=["python machine learning transformers"])

        stp_calls: list[tuple] = []

        def _fake_update_scores(topics: list[str], delta: float, source: str) -> None:
            stp_calls.append((topics, delta, source))

        with patch.object(stp, "update_scores", side_effect=_fake_update_scores), \
             patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            rag.apply_source_feedback(vs, ["http://example.com/article"], is_positive=False)

        assert len(stp_calls) > 0
        assert stp_calls[0][1] == -0.5, "delta deve ser -0.5 para feedback negativo"
        MockAkasha.return_value.send_feedback.assert_not_called()

    def test_cycle_survives_shared_topic_profile_unavailable(self) -> None:
        """Se shared_topic_profile não estiver disponível, apply_source_feedback não deve lançar."""
        from core import rag

        vs = _make_vs()

        with patch.dict("sys.modules", {"shared_topic_profile": None}), \
             patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            # não deve lançar
            rag.apply_source_feedback(vs, ["http://example.com/doc"], is_positive=True)

    def test_cycle_survives_akasha_offline(self) -> None:
        """Se AKASHA estiver offline, apply_source_feedback não deve lançar."""
        from core import rag
        import shared_topic_profile as stp

        vs = _make_vs()

        with patch.object(stp, "update_scores"), \
             patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = False
            rag.apply_source_feedback(vs, ["http://example.com/doc"], is_positive=True)
            MockAkasha.return_value.send_feedback.assert_not_called()

    def test_local_path_does_not_notify_akasha(self) -> None:
        """Documentos locais (não-URL) não devem disparar notificação ao AKASHA."""
        from core import rag
        import shared_topic_profile as stp

        vs = _make_vs()

        with patch.object(stp, "update_scores"), \
             patch("core.akasha_client.AkashaClient") as MockAkasha:
            MockAkasha.return_value.is_available.return_value = True
            rag.apply_source_feedback(vs, ["/home/user/docs/arquivo.pdf"], is_positive=True)
            MockAkasha.return_value.send_feedback.assert_not_called()
