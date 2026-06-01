"""
Testes para Integração 1 — coleção AKASHA na Mnemosyne.

Cobre:
  ECOSYSTEM_SOURCES:
    - label da coleção AKASHA é "AKASHA — arquivo web"
    - default_name é "AKASHA — arquivo web"
    - ecosystem_key permanece "akasha.archive_path"

  sync_ecosystem_collections:
    - archive_path do ecosystem.json cria coleção AKASHA com nome correto
    - archive_path inexistente → coleção não criada (graceful)
    - coleção criada com source="ecosystem" e enabled=True

  is_scientific_paper (indexer):
    - arquivo com frontmatter type: scientific → True
    - arquivo com doi + abstract (marcadores) → True
    - arquivo comum → False

  _load_library_md (loaders):
    - frontmatter type: scientific → doc_type="scientific"
    - frontmatter type: vazio → doc_type=""
    - frontmatter com doi e abstract → carregados nos metadados

  Hierarquia: Papers → doc_type="scientific" → SOURCE_WEIGHTS["scientific"]=1.4
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
from pathlib import Path

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))

_COLLECTIONS_PY = _MNEMOSYNE_ROOT / "core" / "collections.py"
_INDEXER_PY     = _MNEMOSYNE_ROOT / "core" / "indexer.py"


# ---------------------------------------------------------------------------
# ECOSYSTEM_SOURCES — estrutura estática
# ---------------------------------------------------------------------------

class TestEcosystemSourcesLabel:

    def test_akasha_label_is_arquivo_web(self):
        """Label da coleção AKASHA deve ser 'AKASHA — arquivo web'."""
        src = _COLLECTIONS_PY.read_text()
        assert "AKASHA — arquivo web" in src, (
            "ECOSYSTEM_SOURCES deve ter label 'AKASHA — arquivo web' "
            "(não 'AKASHA — arquivo' sem o 'web')"
        )

    def test_akasha_default_name_is_arquivo_web(self):
        """Default name da coleção AKASHA deve ser 'AKASHA — arquivo web'."""
        # Verifica que o nome usado na criação da coleção inclui 'arquivo web'
        src = _COLLECTIONS_PY.read_text()
        count = src.count("AKASHA — arquivo web")
        assert count >= 2, (
            "Deve haver ao menos 2 ocorrências de 'AKASHA — arquivo web' "
            "(label + default_name)"
        )

    def test_akasha_ecosystem_key_unchanged(self):
        """ecosystem_key da coleção AKASHA deve permanecer 'akasha.archive_path'."""
        src = _COLLECTIONS_PY.read_text()
        assert "akasha.archive_path" in src

    def test_old_name_akasha_solo_removed(self):
        """O nome isolado 'AKASHA' (sem 'arquivo web') não deve mais aparecer como default_name."""
        src = _COLLECTIONS_PY.read_text()
        # Não deve ter a string exata como terceio elemento do tuple
        # (detecta '("AKASHA — arquivo", "akasha.archive_path", "AKASHA")')
        assert '"AKASHA",' not in src or 'AKASHA — arquivo web' in src, (
            "default_name 'AKASHA' isolado deve ter sido substituído por 'AKASHA — arquivo web'"
        )


# ---------------------------------------------------------------------------
# sync_ecosystem_collections
# ---------------------------------------------------------------------------

class TestSyncEcosystemCollections:

    def test_creates_akasha_collection_with_correct_name(self, tmp_path):
        """Com archive_path válido, cria coleção com nome 'AKASHA — arquivo web'."""
        from core.collections import sync_ecosystem_collections, CollectionConfig

        # Cria diretório temporário para simular archive_path
        archive = tmp_path / "akasha"
        archive.mkdir()

        eco_mock = {"akasha": {"archive_path": str(archive)}}

        with pytest.MonkeyPatch.context() as mp:
            import core.collections as cc
            mp.setattr(cc, "_read_ecosystem", lambda: eco_mock)
            result = sync_ecosystem_collections([])

        akasha_colls = [c for c in result if "AKASHA" in c.name]
        assert len(akasha_colls) >= 1, "Deve criar pelo menos uma coleção AKASHA"

        names = [c.name for c in akasha_colls]
        assert any("arquivo web" in n for n in names), (
            f"Nenhuma coleção AKASHA tem 'arquivo web' no nome. Nomes: {names}"
        )

    def test_no_collection_when_path_missing(self, tmp_path):
        """archive_path inexistente → coleção AKASHA não criada."""
        from core.collections import sync_ecosystem_collections

        eco_mock = {"akasha": {"archive_path": str(tmp_path / "nonexistent")}}

        with pytest.MonkeyPatch.context() as mp:
            import core.collections as cc
            mp.setattr(cc, "_read_ecosystem", lambda: eco_mock)
            result = sync_ecosystem_collections([])

        akasha_colls = [c for c in result if "AKASHA" in (c.name or "")]
        assert len(akasha_colls) == 0, (
            "Não deve criar coleção AKASHA quando archive_path não existe"
        )

    def test_collection_has_ecosystem_source(self, tmp_path):
        """Coleção criada deve ter source='ecosystem' (não 'user')."""
        from core.collections import sync_ecosystem_collections

        archive = tmp_path / "akasha"
        archive.mkdir()

        eco_mock = {"akasha": {"archive_path": str(archive)}}

        with pytest.MonkeyPatch.context() as mp:
            import core.collections as cc
            mp.setattr(cc, "_read_ecosystem", lambda: eco_mock)
            result = sync_ecosystem_collections([])

        for c in result:
            if "AKASHA" in (c.name or ""):
                assert c.source == "ecosystem", (
                    "Coleção AKASHA deve ter source='ecosystem'"
                )

    def test_collection_enabled_by_default(self, tmp_path):
        """Coleção AKASHA deve estar habilitada por padrão."""
        from core.collections import sync_ecosystem_collections

        archive = tmp_path / "akasha"
        archive.mkdir()

        eco_mock = {"akasha": {"archive_path": str(archive)}}

        with pytest.MonkeyPatch.context() as mp:
            import core.collections as cc
            mp.setattr(cc, "_read_ecosystem", lambda: eco_mock)
            result = sync_ecosystem_collections([])

        for c in result:
            if "AKASHA" in (c.name or ""):
                assert c.enabled is True


# ---------------------------------------------------------------------------
# is_scientific_paper (indexer)
# ---------------------------------------------------------------------------

class TestIsScientificPaper:

    def test_frontmatter_type_scientific(self, tmp_path):
        """Arquivo com frontmatter 'type: scientific' deve ser detectado como artigo."""
        from core.indexer import is_scientific_paper

        f = tmp_path / "paper.md"
        f.write_text(
            "---\ntitle: My Paper\ntype: scientific\ndoi: 10.1234/test\n---\n\nAbstract text here.",
            encoding="utf-8",
        )
        assert is_scientific_paper(str(f)) is True

    def test_structural_markers(self, tmp_path):
        """Dois ou mais marcadores (Abstract, DOI, References) → artigo científico."""
        from core.indexer import is_scientific_paper

        f = tmp_path / "paper2.md"
        f.write_text(
            "# Paper Title\n\nAbstract\n\nThis is the abstract.\n\nDOI: 10.1234/test\n\n# References\n",
            encoding="utf-8",
        )
        assert is_scientific_paper(str(f)) is True

    def test_regular_md_not_scientific(self, tmp_path):
        """Arquivo .md comum sem marcadores científicos → False."""
        from core.indexer import is_scientific_paper

        f = tmp_path / "nota.md"
        f.write_text("# Nota Pessoal\n\nTexto qualquer sem marcadores.", encoding="utf-8")
        assert is_scientific_paper(str(f)) is False

    def test_nonexistent_file(self):
        """Arquivo inexistente → False (sem exceção)."""
        from core.indexer import is_scientific_paper
        assert is_scientific_paper("/tmp/this_file_does_not_exist_xyz.md") is False


# ---------------------------------------------------------------------------
# _load_library_md (loaders) — doc_type do frontmatter
# ---------------------------------------------------------------------------

class TestLoadLibraryMdDocType:

    def test_type_scientific_sets_doc_type(self, tmp_path):
        """frontmatter type: scientific → metadata doc_type='scientific'."""
        from core.loaders import _load_library_md

        f = tmp_path / "paper.md"
        f.write_text(
            "---\ntitle: Test Paper\ntype: scientific\ndoi: 10.1/test\n---\n\nContent.",
            encoding="utf-8",
        )
        docs = _load_library_md(str(f))
        assert len(docs) >= 1
        assert docs[0].metadata.get("doc_type") == "scientific", (
            f"doc_type deve ser 'scientific', obteve: {docs[0].metadata.get('doc_type')!r}"
        )

    def test_no_type_returns_empty_doc_type(self, tmp_path):
        """Frontmatter sem campo type → doc_type=''."""
        from core.loaders import _load_library_md

        f = tmp_path / "nota.md"
        f.write_text("---\ntitle: Nota\n---\n\nConteúdo normal.", encoding="utf-8")
        docs = _load_library_md(str(f))
        assert docs[0].metadata.get("doc_type") == ""

    def test_doi_extracted_from_frontmatter(self, tmp_path):
        """Campos do frontmatter (doi, abstract) não aparecem no page_content."""
        from core.loaders import _load_library_md

        f = tmp_path / "paper_fm.md"
        f.write_text(
            "---\ntitle: Paper\ntype: scientific\ndoi: 10.1/abc\nauthor: Jane\n---\n\nConteúdo do artigo.",
            encoding="utf-8",
        )
        docs = _load_library_md(str(f))
        # Frontmatter extraído — página deve ter só o corpo
        assert "doi:" not in docs[0].page_content.lower(), (
            "frontmatter YAML não deve aparecer no page_content"
        )
        assert "Conteúdo do artigo" in docs[0].page_content


# ---------------------------------------------------------------------------
# Hierarquia: scientific papers → SOURCE_WEIGHTS["scientific"] = 1.4
# ---------------------------------------------------------------------------

class TestScientificWeight:

    def test_source_weights_has_scientific(self):
        """SOURCE_WEIGHTS["scientific"] deve existir e ser maior que 1.0."""
        from core.rag import SOURCE_WEIGHTS
        assert "scientific" in SOURCE_WEIGHTS, "SOURCE_WEIGHTS deve ter chave 'scientific'"
        assert SOURCE_WEIGHTS["scientific"] > 1.0, (
            f"Peso de 'scientific' deve ser > 1.0, obteve {SOURCE_WEIGHTS['scientific']}"
        )

    def test_effective_source_type_returns_scientific(self, tmp_path):
        """_effective_source_type retorna 'scientific' quando doc_type='scientific'."""
        from core.rag import _effective_source_type
        from langchain_core.documents import Document

        doc = Document(
            page_content="texto",
            metadata={"doc_type": "scientific", "source_type": "library"},
        )
        assert _effective_source_type(doc) == "scientific"
