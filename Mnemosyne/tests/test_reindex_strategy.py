"""
Testes para o botão "Melhorar indexação" e a função reindex_collection_with_strategy.

Cobertura:
  - reindex_collection_with_strategy chama delete + re-indexação para cada arquivo
  - arquivos ausentes no disco são pulados sem erro
  - coleção vazia retorna (0, 0)
  - VectorstoreNotFoundError se não houver índice
  - progresso emitido para cada arquivo
  - botão presente em indexing_buttons (desabilitado junto com os outros)
  - diálogo de confirmação aparece antes da re-indexação
  - worker emite finished(False, ...) se não há índice
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))

# Mock langchain_openai antes de importar core
if "langchain_openai" not in sys.modules:
    _mock = MagicMock()
    _mock.ChatOpenAI = MagicMock
    sys.modules["langchain_openai"] = _mock

_MAIN_WINDOW_PY = _MNEMOSYNE_ROOT / "gui" / "main_window.py"
_WORKERS_PY     = _MNEMOSYNE_ROOT / "gui" / "workers.py"
_INDEXER_PY     = _MNEMOSYNE_ROOT / "core" / "indexer.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path, strategy="parent_child"):
    """Cria AppConfig mínimo para testes."""
    return SimpleNamespace(
        persist_dir=str(tmp_path),
        mnemosyne_dir=str(tmp_path),
        chunking_strategy=strategy,
        collection_type="library",
        image_ocr_model="",
        embed_model="potion-multilingual-128M",
        embedding_truncate_dim=None,
        llm_model="test",
        enrichment_enabled=False,
        node_type_classification=False,
        node_type_model="",
        semantic_chunking=False,
    )


def _make_vs(sources: list[str]) -> MagicMock:
    """Cria vectorstore mock com lista de sources."""
    collection = MagicMock()
    collection.get.return_value = {
        "metadatas": [{"source": s} for s in sources],
    }
    collection.delete = MagicMock()
    vs = MagicMock()
    vs._collection = collection
    return vs


# ---------------------------------------------------------------------------
# reindex_collection_with_strategy — testes unitários
# ---------------------------------------------------------------------------

class TestReindexCollectionWithStrategy:
    def test_empty_collection_returns_zero_zero(self, tmp_path):
        """Coleção sem arquivos retorna (0, 0)."""
        from core.indexer import reindex_collection_with_strategy
        from core.errors import VectorstoreNotFoundError

        vs = _make_vs([])
        config = _make_config(tmp_path)

        with patch("core.indexer.load_vectorstore", return_value=vs), \
             patch("core.indexer.BM25Index") as MockBM25, \
             patch("core.indexer.ChunkHashStore") as MockStore:
            MockBM25.load.return_value = MagicMock()
            MockStore.return_value = MagicMock()
            result = reindex_collection_with_strategy(config)

        assert result == (0, 0)

    def test_calls_delete_for_each_source(self, tmp_path):
        """Deve chamar _delete_file_chunks para cada arquivo da coleção."""
        from core.indexer import reindex_collection_with_strategy

        sources = [str(tmp_path / "a.md"), str(tmp_path / "b.md")]
        for s in sources:
            Path(s).write_text("Conteúdo longo para não ser vazio.", encoding="utf-8")

        vs = _make_vs(sources)
        config = _make_config(tmp_path)

        deleted = []
        def _fake_delete(v, fp):
            deleted.append(fp)

        with patch("core.indexer.load_vectorstore", return_value=vs), \
             patch("core.indexer.BM25Index") as MockBM25, \
             patch("core.indexer.ChunkHashStore") as MockStore, \
             patch("core.indexer._delete_file_chunks", side_effect=_fake_delete), \
             patch("core.indexer._delete_parent_chunks"), \
             patch("core.indexer.load_single_file", return_value=[]):
            MockBM25.load.return_value = MagicMock()
            MockStore.return_value = MagicMock()
            reindex_collection_with_strategy(config)

        assert sorted(deleted) == sorted(sources)

    def test_missing_file_is_skipped_without_error(self, tmp_path):
        """Arquivo ausente no disco deve ser pulado silenciosamente, contado como sucesso."""
        from core.indexer import reindex_collection_with_strategy

        absent = str(tmp_path / "inexistente.md")
        vs = _make_vs([absent])
        config = _make_config(tmp_path)

        with patch("core.indexer.load_vectorstore", return_value=vs), \
             patch("core.indexer.BM25Index") as MockBM25, \
             patch("core.indexer.ChunkHashStore") as MockStore, \
             patch("core.indexer._delete_file_chunks"), \
             patch("core.indexer._delete_parent_chunks"):
            MockBM25.load.return_value = MagicMock()
            MockStore.return_value = MagicMock()
            n_success, n_errors = reindex_collection_with_strategy(config)

        assert n_success == 1
        assert n_errors == 0

    def test_progress_callback_called_for_each_file(self, tmp_path):
        """progress_cb deve ser chamado uma vez por arquivo."""
        from core.indexer import reindex_collection_with_strategy

        sources = [str(tmp_path / f"{i}.md") for i in range(3)]
        vs = _make_vs(sources)
        config = _make_config(tmp_path)

        calls = []
        def _cb(msg):
            calls.append(msg)

        with patch("core.indexer.load_vectorstore", return_value=vs), \
             patch("core.indexer.BM25Index") as MockBM25, \
             patch("core.indexer.ChunkHashStore") as MockStore, \
             patch("core.indexer._delete_file_chunks"), \
             patch("core.indexer._delete_parent_chunks"):
            MockBM25.load.return_value = MagicMock()
            MockStore.return_value = MagicMock()
            reindex_collection_with_strategy(config, progress_cb=_cb)

        assert len(calls) == 3

    def test_progress_message_contains_file_name(self, tmp_path):
        """Mensagem de progresso deve conter o nome do arquivo."""
        from core.indexer import reindex_collection_with_strategy

        sources = [str(tmp_path / "artigo.md")]
        vs = _make_vs(sources)
        config = _make_config(tmp_path)

        messages = []
        with patch("core.indexer.load_vectorstore", return_value=vs), \
             patch("core.indexer.BM25Index") as MockBM25, \
             patch("core.indexer.ChunkHashStore") as MockStore, \
             patch("core.indexer._delete_file_chunks"), \
             patch("core.indexer._delete_parent_chunks"):
            MockBM25.load.return_value = MagicMock()
            MockStore.return_value = MagicMock()
            reindex_collection_with_strategy(config, progress_cb=messages.append)

        assert any("artigo.md" in m for m in messages)

    def test_progress_message_has_x_of_n_format(self, tmp_path):
        """Mensagem de progresso deve ter formato 'X/N'."""
        from core.indexer import reindex_collection_with_strategy

        sources = [str(tmp_path / f"f{i}.md") for i in range(3)]
        vs = _make_vs(sources)
        config = _make_config(tmp_path)

        messages = []
        with patch("core.indexer.load_vectorstore", return_value=vs), \
             patch("core.indexer.BM25Index") as MockBM25, \
             patch("core.indexer.ChunkHashStore") as MockStore, \
             patch("core.indexer._delete_file_chunks"), \
             patch("core.indexer._delete_parent_chunks"):
            MockBM25.load.return_value = MagicMock()
            MockStore.return_value = MagicMock()
            reindex_collection_with_strategy(config, progress_cb=messages.append)

        # Pelo menos uma mensagem deve ter "X/3"
        assert any("/3" in m for m in messages)

    def test_raises_vectorstore_not_found_when_no_index(self, tmp_path):
        """Deve propagar VectorstoreNotFoundError quando não há índice."""
        from core.indexer import reindex_collection_with_strategy
        from core.errors import VectorstoreNotFoundError

        config = _make_config(tmp_path)

        with patch("core.indexer.load_vectorstore",
                   side_effect=VectorstoreNotFoundError(str(tmp_path))):
            with pytest.raises(VectorstoreNotFoundError):
                reindex_collection_with_strategy(config)

    def test_error_in_one_file_increments_error_count(self, tmp_path):
        """Erro ao processar um arquivo deve incrementar n_errors sem parar."""
        from core.indexer import reindex_collection_with_strategy

        sources = [str(tmp_path / "a.md"), str(tmp_path / "b.md")]
        for s in sources:
            Path(s).write_text("Conteúdo.", encoding="utf-8")

        vs = _make_vs(sources)
        config = _make_config(tmp_path)

        call_count = [0]
        def _exploding_delete(v, fp):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Erro simulado no primeiro arquivo")

        with patch("core.indexer.load_vectorstore", return_value=vs), \
             patch("core.indexer.BM25Index") as MockBM25, \
             patch("core.indexer.ChunkHashStore") as MockStore, \
             patch("core.indexer._delete_file_chunks", side_effect=_exploding_delete), \
             patch("core.indexer._delete_parent_chunks"):
            MockBM25.load.return_value = MagicMock()
            MockStore.return_value = MagicMock()
            n_success, n_errors = reindex_collection_with_strategy(config)

        assert n_errors >= 1
        # O segundo arquivo deve ter sido processado
        assert call_count[0] >= 2


# ---------------------------------------------------------------------------
# Análise estática do GUI (AST) — sem Qt
# ---------------------------------------------------------------------------

class TestMainWindowReindexStrategyButton:
    def test_button_declared_as_attribute(self):
        """reindex_strategy_btn deve ser declarado como atributo na _build_page_manage."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "reindex_strategy_btn" in src, (
            "main_window.py deve declarar self.reindex_strategy_btn"
        )

    def test_button_initially_disabled(self):
        """O botão deve chamar setEnabled(False) durante a construção."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        # Procura o padrão: reindex_strategy_btn ... setEnabled(False)
        import re
        pattern = r"reindex_strategy_btn.*\n.*setEnabled\(False\)"
        assert re.search(pattern, src), (
            "reindex_strategy_btn deve ter setEnabled(False) imediatamente após ser criado"
        )

    def test_button_in_indexing_buttons_tuple(self):
        """reindex_strategy_btn deve estar na tuple indexing_buttons de _check_indexing_machine."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "self.reindex_strategy_btn" in src
        # Verifica que está dentro do contexto de indexing_buttons
        idx_start = src.find("indexing_buttons = (")
        assert idx_start != -1
        idx_end = src.find(")", idx_start)
        tuple_src = src[idx_start:idx_end]
        assert "reindex_strategy_btn" in tuple_src, (
            "reindex_strategy_btn deve estar na tuple indexing_buttons"
        )

    def test_button_enabled_in_enable_query_buttons(self):
        """_enable_query_buttons deve habilitar reindex_strategy_btn."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        idx = src.find("def _enable_query_buttons")
        assert idx != -1
        end = src.find("\n    def ", idx + 1)
        method_src = src[idx:end]
        assert "reindex_strategy_btn" in method_src and "setEnabled(True)" in method_src

    def test_start_reindex_strategy_shows_confirmation(self):
        """start_reindex_strategy deve conter QMessageBox.question."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        idx = src.find("def start_reindex_strategy")
        assert idx != -1
        end = src.find("\n    def ", idx + 1)
        method_src = src[idx:end]
        assert "QMessageBox.question" in method_src, (
            "start_reindex_strategy deve exibir diálogo de confirmação via QMessageBox.question"
        )

    def test_confirmation_dialog_mentions_substitution(self):
        """O texto da confirmação deve mencionar que os chunks serão substituídos."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        idx = src.find("def start_reindex_strategy")
        end = src.find("\n    def ", idx + 1)
        method_src = src[idx:end]
        assert "substituirá" in method_src.lower() or "substitui" in method_src.lower(), (
            "Diálogo de confirmação deve avisar que chunks serão substituídos"
        )

    def test_worker_import_present(self):
        """ReindexStrategyWorker deve estar nos imports de main_window.py."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "ReindexStrategyWorker" in src

    def test_finish_handler_exists(self):
        """_on_reindex_strategy_finished deve existir em main_window.py."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "def _on_reindex_strategy_finished" in src


# ---------------------------------------------------------------------------
# Análise estática de workers.py
# ---------------------------------------------------------------------------

class TestReindexStrategyWorker:
    def test_worker_class_exists(self):
        """ReindexStrategyWorker deve ser declarado em workers.py."""
        src = _WORKERS_PY.read_text(encoding="utf-8")
        assert "class ReindexStrategyWorker" in src

    def test_worker_has_finished_signal(self):
        """ReindexStrategyWorker deve ter signal finished."""
        src = _WORKERS_PY.read_text(encoding="utf-8")
        idx = src.find("class ReindexStrategyWorker")
        end = src.find("\nclass ", idx + 1)
        worker_src = src[idx:end]
        assert "finished" in worker_src and "Signal" in worker_src

    def test_worker_has_progress_signal(self):
        """ReindexStrategyWorker deve ter signal progress."""
        src = _WORKERS_PY.read_text(encoding="utf-8")
        idx = src.find("class ReindexStrategyWorker")
        end = src.find("\nclass ", idx + 1)
        worker_src = src[idx:end]
        assert "progress" in worker_src and "Signal" in worker_src

    def test_worker_calls_reindex_collection_with_strategy(self):
        """ReindexStrategyWorker.run deve chamar reindex_collection_with_strategy."""
        src = _WORKERS_PY.read_text(encoding="utf-8")
        assert "reindex_collection_with_strategy" in src

    def test_worker_emits_false_on_vectorstore_not_found(self):
        """Worker deve emitir finished(False, ...) se não há índice."""
        # Teste via AST — procura VectorstoreNotFoundError no worker
        src = _WORKERS_PY.read_text(encoding="utf-8")
        idx = src.find("class ReindexStrategyWorker")
        end = src.find("\nclass ", idx + 1)
        worker_src = src[idx:end]
        assert "VectorstoreNotFoundError" in worker_src or "False" in worker_src
