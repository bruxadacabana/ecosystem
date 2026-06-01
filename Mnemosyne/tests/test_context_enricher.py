"""
Testes para ContextEnricher e prefix_context_summary.

Cobertura:
  - enriquecimento salva context_summary no metadata
  - enriquecimento desativado não altera metadata
  - erro no LLM não interrompe indexação básica
  - chunks já enriquecidos são ignorados (idempotência)
  - fallback silencioso se ChromaDB inacessível
  - prefix_context_summary formata corretamente
  - _maybe_enrich despacha thread quando habilitado
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))

# Mock langchain_openai antes de qualquer import de core
if "langchain_openai" not in sys.modules:
    _mock = MagicMock()
    _mock.ChatOpenAI = MagicMock
    sys.modules["langchain_openai"] = _mock

from core.context_enricher import ContextEnricher, prefix_context_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(enrichment_enabled: bool = True, llm_model: str = "gemma2:2b") -> SimpleNamespace:
    return SimpleNamespace(
        enrichment_enabled=enrichment_enabled,
        llm_model=llm_model,
    )


def _make_vs(chunks: list[dict] | None = None) -> MagicMock:
    """Cria vectorstore mock com _collection.get() retornando chunks simulados."""
    chunks = chunks or []
    ids   = [c["id"]   for c in chunks]
    metas = [c["meta"] for c in chunks]
    docs  = [c["text"] for c in chunks]

    collection = MagicMock()
    collection.get.return_value = {"ids": ids, "metadatas": metas, "documents": docs}
    collection.update = MagicMock()

    vs = MagicMock()
    vs._collection = collection
    return vs


# ---------------------------------------------------------------------------
# prefix_context_summary
# ---------------------------------------------------------------------------

class TestPrefixContextSummary:
    def test_prefixes_summary_to_text(self):
        result = prefix_context_summary("Texto do chunk.", "Este é o contexto.")
        assert "[Contexto: Este é o contexto.]" in result
        assert "Texto do chunk." in result

    def test_returns_original_when_summary_empty(self):
        assert prefix_context_summary("texto", "") == "texto"

    def test_returns_original_when_summary_whitespace(self):
        assert prefix_context_summary("texto", "   ") == "texto"

    def test_format_has_double_newline_separator(self):
        result = prefix_context_summary("conteúdo", "sumário")
        assert "\n\n" in result

    def test_summary_comes_before_text(self):
        result = prefix_context_summary("TEXTO", "SUMÁRIO")
        assert result.index("SUMÁRIO") < result.index("TEXTO")


# ---------------------------------------------------------------------------
# ContextEnricher.enrich_file
# ---------------------------------------------------------------------------

class TestContextEnricher:
    def test_enrichment_saves_context_summary(self):
        """enrich_file deve salvar context_summary nos metadados do chunk."""
        vs = _make_vs([{"id": "c1", "meta": {"source": "/f.md"}, "text": "Texto longo do chunk."}])
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        with patch.object(enricher, "_call_logos", return_value="Sumário contextual gerado."):
            n = enricher.enrich_file("/f.md", vs)

        assert n == 1
        vs._collection.update.assert_called_once()
        call_kwargs = vs._collection.update.call_args
        new_meta = call_kwargs.kwargs.get("metadatas", call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
        if new_meta is None:
            new_meta = call_kwargs[1][1] if len(call_kwargs[1]) > 1 else call_kwargs[0][1]
        assert new_meta[0]["context_summary"] == "Sumário contextual gerado."

    def test_disabled_does_not_alter_metadata(self):
        """enrichment_enabled=False → update nunca é chamado."""
        vs = _make_vs([{"id": "c1", "meta": {"source": "/f.md"}, "text": "Texto."}])
        config = _make_config(enrichment_enabled=False)
        enricher = ContextEnricher(config)

        n = enricher.enrich_file("/f.md", vs)

        assert n == 0
        vs._collection.update.assert_not_called()

    def test_llm_error_does_not_raise(self):
        """Erro no LLM não deve propagar — enrich_file retorna 0 silenciosamente."""
        vs = _make_vs([{"id": "c1", "meta": {"source": "/f.md"}, "text": "Texto."}])
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        with patch.object(enricher, "_call_logos", side_effect=Exception("LOGOS offline")):
            n = enricher.enrich_file("/f.md", vs)

        assert n == 0
        vs._collection.update.assert_not_called()

    def test_llm_returns_empty_string_skips_update(self):
        """LOGOS retorna string vazia → chunk não é atualizado."""
        vs = _make_vs([{"id": "c1", "meta": {"source": "/f.md"}, "text": "Texto."}])
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        with patch.object(enricher, "_call_logos", return_value=""):
            n = enricher.enrich_file("/f.md", vs)

        assert n == 0
        vs._collection.update.assert_not_called()

    def test_already_enriched_chunk_is_skipped(self):
        """Chunk com context_summary já preenchido não deve ser re-enriquecido."""
        vs = _make_vs([{
            "id": "c1",
            "meta": {"source": "/f.md", "context_summary": "Já existe."},
            "text": "Texto.",
        }])
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        with patch.object(enricher, "_call_logos", return_value="Novo sumário") as mock_call:
            n = enricher.enrich_file("/f.md", vs)

        assert n == 0
        mock_call.assert_not_called()
        vs._collection.update.assert_not_called()

    def test_partial_enrichment_some_already_done(self):
        """Apenas chunks sem context_summary devem ser enriquecidos."""
        vs = _make_vs([
            {"id": "c1", "meta": {"source": "/f.md", "context_summary": "Existente"}, "text": "A"},
            {"id": "c2", "meta": {"source": "/f.md"}, "text": "B"},
            {"id": "c3", "meta": {"source": "/f.md"}, "text": "C"},
        ])
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        with patch.object(enricher, "_call_logos", return_value="Sumário"):
            n = enricher.enrich_file("/f.md", vs)

        assert n == 2
        assert vs._collection.update.call_count == 2

    def test_chromadb_error_does_not_raise(self):
        """Falha ao acessar ChromaDB deve ser capturada silenciosamente."""
        vs = MagicMock()
        vs._collection.get.side_effect = RuntimeError("DB locked")
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        n = enricher.enrich_file("/f.md", vs)
        assert n == 0

    def test_update_error_on_single_chunk_does_not_stop_others(self):
        """Falha ao atualizar um chunk não deve impedir os demais."""
        vs = _make_vs([
            {"id": "c1", "meta": {"source": "/f.md"}, "text": "A"},
            {"id": "c2", "meta": {"source": "/f.md"}, "text": "B"},
        ])
        call_count = [0]
        def _update_side_effect(**kwargs):
            if kwargs.get("ids") == ["c1"]:
                raise RuntimeError("DB write error")
            call_count[0] += 1

        vs._collection.update.side_effect = _update_side_effect
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        with patch.object(enricher, "_call_logos", return_value="Sumário"):
            n = enricher.enrich_file("/f.md", vs)

        # c2 deve ter sido enriquecido mesmo com c1 falhando
        assert n == 1
        assert call_count[0] == 1

    def test_no_chunks_returns_zero(self):
        """Arquivo sem chunks no ChromaDB retorna 0."""
        vs = _make_vs([])
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        with patch.object(enricher, "_call_logos", return_value="Sumário"):
            n = enricher.enrich_file("/f.md", vs)

        assert n == 0
        vs._collection.update.assert_not_called()

    def test_return_count_matches_enriched_chunks(self):
        """Retorno deve ser o número exato de chunks atualizados."""
        vs = _make_vs([
            {"id": f"c{i}", "meta": {"source": "/f.md"}, "text": f"Texto {i}"}
            for i in range(5)
        ])
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        with patch.object(enricher, "_call_logos", return_value="Sumário"):
            n = enricher.enrich_file("/f.md", vs)

        assert n == 5
        assert vs._collection.update.call_count == 5

    def test_metadata_preserved_after_enrichment(self):
        """Metadados existentes devem ser preservados ao adicionar context_summary."""
        original_meta = {"source": "/f.md", "title": "Artigo", "author": "Autor"}
        vs = _make_vs([{"id": "c1", "meta": dict(original_meta), "text": "Texto."}])
        config = _make_config(enrichment_enabled=True)
        enricher = ContextEnricher(config)

        with patch.object(enricher, "_call_logos", return_value="Novo sumário"):
            enricher.enrich_file("/f.md", vs)

        call_kwargs = vs._collection.update.call_args
        new_meta = (
            call_kwargs.kwargs.get("metadatas")
            or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs[0][1])
        )
        assert new_meta[0]["title"] == "Artigo"
        assert new_meta[0]["author"] == "Autor"
        assert new_meta[0]["context_summary"] == "Novo sumário"


# ---------------------------------------------------------------------------
# ContextEnricher._call_logos
# ---------------------------------------------------------------------------

class TestCallLogos:
    def test_empty_text_returns_empty_string(self):
        config = _make_config()
        enricher = ContextEnricher(config)
        result = enricher._call_logos("")
        assert result == ""

    def test_whitespace_only_returns_empty_string(self):
        config = _make_config()
        enricher = ContextEnricher(config)
        result = enricher._call_logos("   \n  ")
        assert result == ""

    def test_httpx_error_returns_empty_string(self):
        config = _make_config()
        enricher = ContextEnricher(config)
        with patch("httpx.post", side_effect=Exception("Connection refused")):
            result = enricher._call_logos("Texto do chunk.")
        assert result == ""

    def test_successful_call_returns_content(self):
        config = _make_config()
        enricher = ContextEnricher(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "  Sumário gerado.  "}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            with patch("ecosystem_client.get_inference_url", return_value="http://localhost:7072"):
                result = enricher._call_logos("Texto.")

        assert result == "Sumário gerado."

    def test_call_uses_p3_priority_header(self):
        config = _make_config()
        enricher = ContextEnricher(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "sumário"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            with patch("ecosystem_client.get_inference_url", return_value="http://localhost:7072"):
                enricher._call_logos("Texto.")

        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers") or {}
        assert headers.get("X-Priority") == "3"

    def test_text_truncated_to_max_chars(self):
        """Texto longo deve ser truncado antes de enviar ao LOGOS."""
        from core.context_enricher import _MAX_TEXT_CHARS
        long_text = "a" * (_MAX_TEXT_CHARS * 2)
        config = _make_config()
        enricher = ContextEnricher(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            with patch("ecosystem_client.get_inference_url", return_value="http://localhost:7072"):
                enricher._call_logos(long_text)

        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or {}
        prompt = body.get("messages", [{}])[0].get("content", "")
        # O prompt contém o texto truncado
        assert len(prompt) <= _MAX_TEXT_CHARS + 200  # margem para o prefixo do prompt


# ---------------------------------------------------------------------------
# _maybe_enrich (integração com indexer)
# ---------------------------------------------------------------------------

class TestMaybeEnrich:
    def test_dispatches_thread_when_enabled(self):
        """_maybe_enrich deve criar thread daemon quando enrichment_enabled=True."""
        from core.indexer import _maybe_enrich

        config = SimpleNamespace(enrichment_enabled=True, llm_model="test")
        vs = MagicMock()

        threads_created = []
        original_thread_init = threading.Thread.__init__

        with patch("threading.Thread") as mock_thread_class:
            mock_thread_instance = MagicMock()
            mock_thread_class.return_value = mock_thread_instance

            _maybe_enrich(config, "/f.md", vs)

            mock_thread_class.assert_called_once()
            mock_thread_instance.start.assert_called_once()
            # Deve ser daemon=True
            call_kwargs = mock_thread_class.call_args.kwargs
            assert call_kwargs.get("daemon") is True

    def test_does_nothing_when_disabled(self):
        """_maybe_enrich não deve criar thread quando enrichment_enabled=False."""
        from core.indexer import _maybe_enrich

        config = SimpleNamespace(enrichment_enabled=False, llm_model="test")
        vs = MagicMock()

        with patch("threading.Thread") as mock_thread_class:
            _maybe_enrich(config, "/f.md", vs)
            mock_thread_class.assert_not_called()

    def test_enrich_file_background_catches_exceptions(self):
        """_enrich_file_background não deve propagar exceções."""
        from core.indexer import _enrich_file_background

        config = SimpleNamespace(enrichment_enabled=True, llm_model="test")
        vs = MagicMock()

        # ContextEnricher é importado lazy dentro de _enrich_file_background
        with patch("core.context_enricher.ContextEnricher") as MockEnricher:
            MockEnricher.return_value.enrich_file.side_effect = RuntimeError("falha grave")
            # Não deve lançar exceção
            _enrich_file_background(config, "/f.md", vs)
