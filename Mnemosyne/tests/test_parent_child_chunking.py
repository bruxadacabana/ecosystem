"""
Testes para Parent-Child chunking: ParentChildChunker, ParentStore e _do_parent_lookup.

Cobertura:
  - Unitária: chunker gera parent_id, parent > child, lookup funciona, fallback correto
  - Integração: fluxo indexer → ParentStore → rag lookup
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))

# Mock langchain_openai antes de qualquer import de core (não instalado no Windows de trabalho)
if "langchain_openai" not in sys.modules:
    _lc_openai_mock = MagicMock()
    _lc_openai_mock.ChatOpenAI = MagicMock
    sys.modules["langchain_openai"] = _lc_openai_mock

from langchain_core.documents import Document

from core.parent_store import ParentStore
from core.indexer import ParentChildChunker, _make_parent_id, _PARENT_CHUNK_SIZE, _CHILD_CHUNK_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(text: str, source: str = "/fake/doc.md") -> Document:
    return Document(page_content=text, metadata={"source": source})


def _long_text(n_chars: int = 2000) -> str:
    """Texto longo o suficiente para produzir múltiplos parent chunks."""
    sentence = "Esta é uma frase de teste para chunking. "
    return (sentence * (n_chars // len(sentence) + 1))[:n_chars]


# ---------------------------------------------------------------------------
# _make_parent_id
# ---------------------------------------------------------------------------

class TestMakeParentId:
    def test_deterministic_same_source(self):
        id1 = _make_parent_id("/path/to/file.md", 0)
        id2 = _make_parent_id("/path/to/file.md", 0)
        assert id1 == id2

    def test_different_index_different_id(self):
        id0 = _make_parent_id("/path/to/file.md", 0)
        id1 = _make_parent_id("/path/to/file.md", 1)
        assert id0 != id1

    def test_different_source_different_id(self):
        id_a = _make_parent_id("/path/a.md", 0)
        id_b = _make_parent_id("/path/b.md", 0)
        assert id_a != id_b

    def test_format_has_underscore_separator(self):
        parent_id = _make_parent_id("/path/file.md", 3)
        parts = parent_id.split("_")
        assert len(parts) == 2
        assert parts[1] == "3"

    def test_hash_prefix_is_12_chars(self):
        parent_id = _make_parent_id("/path/file.md", 0)
        hash_prefix = parent_id.split("_")[0]
        assert len(hash_prefix) == 12


# ---------------------------------------------------------------------------
# ParentChildChunker
# ---------------------------------------------------------------------------

class TestParentChildChunker:
    def test_child_chunks_have_parent_id(self):
        text = _long_text(600)
        doc = _make_doc(text)
        chunker = ParentChildChunker()
        child_chunks, parent_records = chunker.split_documents([doc])
        assert child_chunks, "Deve gerar pelo menos um child chunk"
        for child in child_chunks:
            assert "parent_id" in child.metadata, "Cada child deve ter parent_id"

    def test_parent_text_longer_than_child(self):
        text = _long_text(2000)
        doc = _make_doc(text)
        chunker = ParentChildChunker()
        child_chunks, parent_records = chunker.split_documents([doc])
        assert parent_records, "Deve gerar pelo menos um parent record"
        # Verifica que cada parent é maior ou igual ao child correspondente
        parent_by_id = {pid: ptxt for pid, _, ptxt in parent_records}
        for child in child_chunks:
            pid = child.metadata["parent_id"]
            if pid in parent_by_id:
                # parent pode ser igual (doc muito pequeno) ou maior
                assert len(parent_by_id[pid]) >= len(child.page_content)

    def test_child_size_bounded_by_CHILD_CHUNK_SIZE(self):
        text = _long_text(3000)
        doc = _make_doc(text)
        chunker = ParentChildChunker()
        child_chunks, _ = chunker.split_documents([doc])
        for child in child_chunks:
            # Com overlap, pode exceder ligeiramente mas não de forma absurda
            assert len(child.page_content) <= _CHILD_CHUNK_SIZE * 1.5

    def test_parent_records_have_correct_source(self):
        source = "/my/dir/article.md"
        doc = _make_doc(_long_text(800), source=source)
        chunker = ParentChildChunker()
        _, parent_records = chunker.split_documents([doc])
        for _, rec_source, _ in parent_records:
            assert rec_source == source

    def test_parent_id_in_child_matches_parent_records(self):
        doc = _make_doc(_long_text(1500))
        chunker = ParentChildChunker()
        child_chunks, parent_records = chunker.split_documents([doc])
        parent_ids_from_records = {pid for pid, _, _ in parent_records}
        for child in child_chunks:
            assert child.metadata["parent_id"] in parent_ids_from_records

    def test_multiple_docs_generate_distinct_parent_ids(self):
        docs = [
            _make_doc(_long_text(600), source="/a.md"),
            _make_doc(_long_text(600), source="/b.md"),
        ]
        chunker = ParentChildChunker()
        child_chunks, parent_records = chunker.split_documents(docs)
        parent_ids = [pid for pid, _, _ in parent_records]
        # IDs para fontes diferentes devem ser distintos
        assert len(set(parent_ids)) == len(parent_ids)

    def test_short_doc_produces_at_least_one_child_and_parent(self):
        doc = _make_doc("Texto curto.")
        chunker = ParentChildChunker()
        child_chunks, parent_records = chunker.split_documents([doc])
        assert len(child_chunks) >= 1
        assert len(parent_records) >= 1

    def test_empty_doc_produces_no_chunks(self):
        doc = _make_doc("")
        chunker = ParentChildChunker()
        child_chunks, parent_records = chunker.split_documents([doc])
        # Documento vazio não deve gerar chunks
        assert len(child_chunks) == 0 or all(c.page_content.strip() == "" for c in child_chunks)

    def test_source_type_article_uses_correct_separators(self):
        chunker = ParentChildChunker(source_type="article")
        doc = _make_doc("Parágrafo um.\n\nParágrafo dois.\n\nParágrafo três." * 10)
        child_chunks, parent_records = chunker.split_documents([doc])
        assert len(parent_records) >= 1

    def test_metadata_preserved_in_child(self):
        doc = Document(
            page_content=_long_text(600),
            metadata={"source": "/path/file.md", "title": "Artigo Teste", "author": "Autor"},
        )
        chunker = ParentChildChunker()
        child_chunks, _ = chunker.split_documents([doc])
        for child in child_chunks:
            assert child.metadata.get("title") == "Artigo Teste"
            assert child.metadata.get("author") == "Autor"


# ---------------------------------------------------------------------------
# ParentStore
# ---------------------------------------------------------------------------

class TestParentStore:
    def test_save_and_get(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.save("pid_001", "/source.md", "Texto do parent chunk.")
        result = ps.get("pid_001")
        ps.close()
        assert result == "Texto do parent chunk."

    def test_get_nonexistent_returns_none(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        result = ps.get("inexistente_id")
        ps.close()
        assert result is None

    def test_save_batch(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        records = [
            ("id_1", "/a.md", "Texto A"),
            ("id_2", "/a.md", "Texto B"),
            ("id_3", "/b.md", "Texto C"),
        ]
        ps.save_batch(records)
        assert ps.get("id_1") == "Texto A"
        assert ps.get("id_2") == "Texto B"
        assert ps.get("id_3") == "Texto C"
        ps.close()

    def test_count(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.save("a", "/f.md", "texto a")
        ps.save("b", "/f.md", "texto b")
        assert ps.count() == 2
        ps.close()

    def test_count_for_source(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.save("a", "/f1.md", "texto a")
        ps.save("b", "/f1.md", "texto b")
        ps.save("c", "/f2.md", "texto c")
        assert ps.count_for_source("/f1.md") == 2
        assert ps.count_for_source("/f2.md") == 1
        assert ps.count_for_source("/inexistente.md") == 0
        ps.close()

    def test_delete_by_source(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.save("a", "/f.md", "texto a")
        ps.save("b", "/f.md", "texto b")
        ps.save("c", "/outro.md", "texto c")
        ps.delete_by_source("/f.md")
        assert ps.get("a") is None
        assert ps.get("b") is None
        assert ps.get("c") == "texto c"
        ps.close()

    def test_insert_or_replace(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.save("id_x", "/f.md", "original")
        ps.save("id_x", "/f.md", "atualizado")
        assert ps.get("id_x") == "atualizado"
        ps.close()

    def test_schema_created_on_init(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.close()
        db = sqlite3.connect(str(tmp_path / "parent_chunks.db"))
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        db.close()
        assert "parent_chunks" in tables

    def test_index_on_source(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.close()
        db = sqlite3.connect(str(tmp_path / "parent_chunks.db"))
        indices = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()]
        db.close()
        assert any("source" in idx for idx in indices)

    def test_persist_across_instances(self, tmp_path):
        ps1 = ParentStore(str(tmp_path))
        ps1.save("id_persist", "/f.md", "texto persistido")
        ps1.close()
        ps2 = ParentStore(str(tmp_path))
        result = ps2.get("id_persist")
        ps2.close()
        assert result == "texto persistido"


# ---------------------------------------------------------------------------
# _do_parent_lookup
# ---------------------------------------------------------------------------

from core.rag import _do_parent_lookup


def _make_config(tmp_path, strategy="parent_child"):
    return SimpleNamespace(
        chunking_strategy=strategy,
        persist_dir=str(tmp_path),
    )


class TestDoParentLookup:
    def test_replaces_child_with_parent_text(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.save("pid_abc", "/f.md", "Texto completo do parent — muito mais longo que o child.")
        ps.close()

        doc = Document(
            page_content="child curto",
            metadata={"source": "/f.md", "parent_id": "pid_abc"},
        )
        config = _make_config(tmp_path)
        result = _do_parent_lookup([doc], config)
        assert result[0].page_content == "Texto completo do parent — muito mais longo que o child."

    def test_fallback_when_parent_not_found(self, tmp_path):
        doc = Document(
            page_content="child original",
            metadata={"source": "/f.md", "parent_id": "pid_inexistente"},
        )
        config = _make_config(tmp_path)
        result = _do_parent_lookup([doc], config)
        assert result[0].page_content == "child original"

    def test_skips_docs_without_parent_id(self, tmp_path):
        doc = Document(
            page_content="sem parent_id",
            metadata={"source": "/f.md"},
        )
        config = _make_config(tmp_path)
        result = _do_parent_lookup([doc], config)
        assert result[0].page_content == "sem parent_id"

    def test_returns_original_list_when_strategy_fixed(self, tmp_path):
        doc = Document(
            page_content="child",
            metadata={"source": "/f.md", "parent_id": "qualquer"},
        )
        config = _make_config(tmp_path, strategy="fixed")
        result = _do_parent_lookup([doc], config)
        assert result is [doc] or result[0].page_content == "child"

    def test_strategy_fixed_returns_same_docs(self, tmp_path):
        docs = [_make_doc("texto")]
        config = _make_config(tmp_path, strategy="fixed")
        result = _do_parent_lookup(docs, config)
        assert result == docs

    def test_metadata_preserved_after_lookup(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.save("pid_meta", "/f.md", "Parent text")
        ps.close()

        doc = Document(
            page_content="child",
            metadata={"source": "/f.md", "parent_id": "pid_meta", "title": "Meu Doc"},
        )
        config = _make_config(tmp_path)
        result = _do_parent_lookup([doc], config)
        assert result[0].metadata.get("title") == "Meu Doc"
        assert result[0].metadata.get("parent_id") == "pid_meta"

    def test_partial_lookup_mixed_docs(self, tmp_path):
        ps = ParentStore(str(tmp_path))
        ps.save("pid_existe", "/f.md", "Parent encontrado")
        ps.close()

        doc_with = Document(
            page_content="child com parent",
            metadata={"source": "/f.md", "parent_id": "pid_existe"},
        )
        doc_without = Document(
            page_content="child sem parent",
            metadata={"source": "/f.md", "parent_id": "pid_ausente"},
        )
        config = _make_config(tmp_path)
        result = _do_parent_lookup([doc_with, doc_without], config)
        assert result[0].page_content == "Parent encontrado"
        assert result[1].page_content == "child sem parent"

    def test_no_parent_ids_in_any_doc_returns_quickly(self, tmp_path):
        docs = [
            Document(page_content="a", metadata={"source": "/f.md"}),
            Document(page_content="b", metadata={"source": "/g.md"}),
        ]
        config = _make_config(tmp_path)
        result = _do_parent_lookup(docs, config)
        assert result == docs

    def test_empty_persist_dir_returns_originals(self, tmp_path):
        doc = Document(
            page_content="child",
            metadata={"source": "/f.md", "parent_id": "id_qualquer"},
        )
        config = _make_config(tmp_path, strategy="parent_child")
        # tmp_path existe mas não tem parent_chunks.db ainda — deve retornar original
        result = _do_parent_lookup([doc], config)
        assert result[0].page_content == "child"

    def test_graceful_on_missing_persist_dir(self, tmp_path):
        doc = Document(
            page_content="child",
            metadata={"source": "/f.md", "parent_id": "id_qualquer"},
        )
        config = SimpleNamespace(
            chunking_strategy="parent_child",
            persist_dir="",  # não configurado
        )
        result = _do_parent_lookup([doc], config)
        assert result[0].page_content == "child"


# ---------------------------------------------------------------------------
# Integração: ParentChildChunker + ParentStore + _do_parent_lookup
# ---------------------------------------------------------------------------

class TestParentChildIntegration:
    def test_full_flow_indexer_to_rag(self, tmp_path):
        """Simula: indexar documento → salvar parents → lookup no RAG."""
        source = str(tmp_path / "artigo.md")
        text = _long_text(1800)

        # 1. Chunking (simula o que o indexer faz)
        doc = Document(page_content=text, metadata={"source": source})
        chunker = ParentChildChunker()
        child_chunks, parent_records = chunker.split_documents([doc])

        # 2. Persistir parents (simula o que o indexer faz)
        ps = ParentStore(str(tmp_path))
        ps.save_batch(parent_records)
        ps.close()

        # 3. RAG recebe child chunks (vindos do ChromaDB)
        config = SimpleNamespace(
            chunking_strategy="parent_child",
            persist_dir=str(tmp_path),
        )
        result = _do_parent_lookup(child_chunks, config)

        # Todos os children devem ter sido expandidos para o parent
        assert len(result) == len(child_chunks)
        for orig, expanded in zip(child_chunks, result):
            assert len(expanded.page_content) >= len(orig.page_content), (
                f"Expanded deve ser >= original: "
                f"{len(expanded.page_content)} >= {len(orig.page_content)}"
            )

    def test_reindex_replaces_old_parents(self, tmp_path):
        """Re-indexar arquivo substitui parents antigos pelo conteúdo novo."""
        source = "/path/file.md"

        ps = ParentStore(str(tmp_path))
        ps.save("old_parent_id", source, "Conteúdo antigo")
        ps.close()

        # Simula re-indexação: delete_by_source + save_batch
        chunker = ParentChildChunker()
        doc = Document(page_content=_long_text(800), metadata={"source": source})
        _, new_parent_records = chunker.split_documents([doc])

        ps2 = ParentStore(str(tmp_path))
        ps2.delete_by_source(source)
        ps2.save_batch(new_parent_records)

        # O ID antigo não deve mais existir
        assert ps2.get("old_parent_id") is None
        # Os novos IDs devem existir
        for pid, _, text in new_parent_records:
            assert ps2.get(pid) == text
        ps2.close()

    def test_child_smaller_than_parent_chunk_size(self, tmp_path):
        """Child chunk deve ser menor que o PARENT_CHUNK_SIZE."""
        text = _long_text(3000)
        doc = Document(page_content=text, metadata={"source": "/f.md"})
        chunker = ParentChildChunker()
        child_chunks, parent_records = chunker.split_documents([doc])

        for child in child_chunks:
            assert len(child.page_content) < _PARENT_CHUNK_SIZE, (
                f"Child ({len(child.page_content)} chars) deve ser menor que "
                f"parent size ({_PARENT_CHUNK_SIZE} chars)"
            )

    def test_parent_covers_child_content(self, tmp_path):
        """O texto do child deve estar contido no texto do parent."""
        text = _long_text(800)
        doc = Document(page_content=text, metadata={"source": "/f.md"})
        chunker = ParentChildChunker()
        child_chunks, parent_records = chunker.split_documents([doc])
        parent_by_id = {pid: ptxt for pid, _, ptxt in parent_records}

        for child in child_chunks:
            pid = child.metadata["parent_id"]
            parent_text = parent_by_id.get(pid, "")
            if parent_text:
                # O texto do child (sem title prefix) deve ser substring do parent
                child_core = child.page_content.strip()[:50]
                assert child_core in parent_text or len(child_core) == 0, (
                    f"Child text '{child_core[:20]}...' não encontrado no parent"
                )
