"""
Testes para preenchimento consistente de page_num e start_char em todos os loaders.

Cobre:
  - _load_pdf: page_num 1-based (não 0-based)
  - _load_epub: page_num = chapter_num (1-based por capítulo)
  - _load_library_md: page_num=None, start_char=0
  - _load_docx: page_num=None, start_char=0
  - _load_vtt: page_num=None, start_char=0
  - _load_obsidian_note: page_num=None, start_char=0
  - _load_image: page_num=None, start_char=0
  - SourceRecord: expõe start_char e page_num no TypedDict
  - _enrich_chunk_offsets: page_num preservado quando já definido pelo loader
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))

# Mock langchain_openai antes de importar core
if "langchain_openai" not in sys.modules:
    _mock = MagicMock()
    _mock.ChatOpenAI = MagicMock
    sys.modules["langchain_openai"] = _mock

from langchain_core.documents import Document

from core.loaders import (
    _load_pdf,
    _load_docx,
    _load_vtt,
    _load_library_md,
    _load_obsidian_note,
    _load_epub,
    _load_image,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf_doc(page: int, text: str = "Texto da página.") -> Document:
    """Simula um Document retornado pelo PyPDFLoader para uma página."""
    return Document(
        page_content=text,
        metadata={"source": "/fake/doc.pdf", "page": page},
    )


# ---------------------------------------------------------------------------
# _load_pdf
# ---------------------------------------------------------------------------

class TestLoadPdfPageNum:
    def test_first_page_is_page_num_1(self):
        """Página 0 (PyPDF) → page_num deve ser 1."""
        mock_docs = [_make_pdf_doc(0, "Texto p1")]
        with patch("core.loaders.PyPDFLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_docs
            docs = _load_pdf("/fake/doc.pdf")
        assert docs[0].metadata["page_num"] == 1

    def test_second_page_is_page_num_2(self):
        """Página 1 (PyPDF) → page_num deve ser 2."""
        mock_docs = [_make_pdf_doc(1, "Texto p2")]
        with patch("core.loaders.PyPDFLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_docs
            docs = _load_pdf("/fake/doc.pdf")
        assert docs[0].metadata["page_num"] == 2

    def test_multiple_pages_have_correct_page_nums(self):
        """Multi-página: page_num segue a ordem 1, 2, 3, ..."""
        mock_docs = [_make_pdf_doc(i, f"Texto p{i+1}") for i in range(5)]
        with patch("core.loaders.PyPDFLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_docs
            docs = _load_pdf("/fake/doc.pdf")
        for i, doc in enumerate(docs):
            assert doc.metadata["page_num"] == i + 1

    def test_page_num_is_not_zero_based(self):
        """page_num nunca deve ser 0 para a primeira página."""
        mock_docs = [_make_pdf_doc(0)]
        with patch("core.loaders.PyPDFLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_docs
            docs = _load_pdf("/fake/doc.pdf")
        assert docs[0].metadata["page_num"] != 0

    def test_pdf_has_start_char_zero(self):
        """PDFs devem ter start_char=0 (âncora começa na página)."""
        mock_docs = [_make_pdf_doc(0)]
        with patch("core.loaders.PyPDFLoader") as MockLoader:
            MockLoader.return_value.load.return_value = mock_docs
            docs = _load_pdf("/fake/doc.pdf")
        assert docs[0].metadata.get("start_char") == 0


# ---------------------------------------------------------------------------
# _load_epub
# ---------------------------------------------------------------------------

class TestLoadEpubPageNum:
    def _mock_epub_book(self, chapters: list[str]):
        """Cria mock do ebooklib.epub para simular capítulos."""
        from unittest.mock import MagicMock
        from bs4 import BeautifulSoup

        book = MagicMock()
        book.get_metadata.return_value = [("Test Book",)]

        items = []
        for text in chapters:
            item = MagicMock()
            item.get_content.return_value = f"<html><body><h1>Cap</h1><p>{text}</p></body></html>".encode()
            items.append(item)

        book.get_items_of_type.return_value = iter(items)
        return book

    def test_first_chapter_has_page_num_1(self):
        """Primeiro capítulo do EPUB → page_num deve ser 1."""
        long_text = "x" * 200
        try:
            import ebooklib
            from ebooklib import epub as epub_mod
        except ImportError:
            pytest.skip("ebooklib não instalado")

        book = self._mock_epub_book([long_text])
        with patch("ebooklib.epub.read_epub", return_value=book):
            docs = _load_epub("/fake/book.epub")

        if docs:
            assert docs[0].metadata["page_num"] == 1

    def test_each_chapter_has_sequential_page_num(self):
        """Capítulos consecutivos: page_num = 1, 2, 3, ..."""
        long_text = "x" * 200
        try:
            import ebooklib
        except ImportError:
            pytest.skip("ebooklib não instalado")

        book = self._mock_epub_book([long_text] * 3)
        with patch("ebooklib.epub.read_epub", return_value=book):
            docs = _load_epub("/fake/book.epub")

        for i, doc in enumerate(docs):
            assert doc.metadata["page_num"] == i + 1

    def test_epub_chapter_has_start_char_zero(self):
        """Cada capítulo do EPUB deve ter start_char=0."""
        long_text = "x" * 200
        try:
            import ebooklib
        except ImportError:
            pytest.skip("ebooklib não instalado")

        book = self._mock_epub_book([long_text])
        with patch("ebooklib.epub.read_epub", return_value=book):
            docs = _load_epub("/fake/book.epub")

        if docs:
            assert docs[0].metadata["start_char"] == 0


# ---------------------------------------------------------------------------
# _load_library_md
# ---------------------------------------------------------------------------

class TestLoadLibraryMd:
    def test_has_page_num_none(self, tmp_path):
        """Arquivo .md da biblioteca deve ter page_num=None."""
        md_file = tmp_path / "artigo.md"
        md_file.write_text("# Título\n\nConteúdo do artigo.", encoding="utf-8")
        docs = _load_library_md(str(md_file))
        assert docs[0].metadata.get("page_num") is None

    def test_has_start_char_zero(self, tmp_path):
        """Arquivo .md da biblioteca deve ter start_char=0."""
        md_file = tmp_path / "artigo.md"
        md_file.write_text("Conteúdo do artigo.", encoding="utf-8")
        docs = _load_library_md(str(md_file))
        assert docs[0].metadata.get("start_char") == 0

    def test_with_frontmatter_still_has_page_num_none(self, tmp_path):
        """MD com frontmatter também deve ter page_num=None."""
        md_file = tmp_path / "artigo.md"
        md_file.write_text(
            "---\ntitle: Teste\nauthor: Autor\n---\nCorpo do artigo.",
            encoding="utf-8",
        )
        docs = _load_library_md(str(md_file))
        assert docs[0].metadata.get("page_num") is None

    def test_with_frontmatter_still_has_start_char_zero(self, tmp_path):
        """MD com frontmatter também deve ter start_char=0."""
        md_file = tmp_path / "artigo.md"
        md_file.write_text(
            "---\ntitle: Teste\n---\nCorpo do artigo.",
            encoding="utf-8",
        )
        docs = _load_library_md(str(md_file))
        assert docs[0].metadata.get("start_char") == 0


# ---------------------------------------------------------------------------
# _load_docx
# ---------------------------------------------------------------------------

class TestLoadDocx:
    def test_docx_has_page_num_none(self, tmp_path):
        """DOCX deve ter page_num=None."""
        with patch("core.loaders.Docx2txtLoader") as MockLoader:
            MockLoader.return_value.load.return_value = [
                Document(page_content="Conteúdo DOCX", metadata={"source": "/f.docx"})
            ]
            docs = _load_docx("/f.docx")
        assert docs[0].metadata.get("page_num") is None

    def test_docx_has_start_char_zero(self, tmp_path):
        """DOCX deve ter start_char=0."""
        with patch("core.loaders.Docx2txtLoader") as MockLoader:
            MockLoader.return_value.load.return_value = [
                Document(page_content="Conteúdo DOCX", metadata={"source": "/f.docx"})
            ]
            docs = _load_docx("/f.docx")
        assert docs[0].metadata.get("start_char") == 0


# ---------------------------------------------------------------------------
# _load_vtt
# ---------------------------------------------------------------------------

class TestLoadVtt:
    def test_vtt_has_page_num_none(self, tmp_path):
        """Arquivo VTT deve ter page_num=None."""
        vtt_file = tmp_path / "transcricao.vtt"
        vtt_file.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nOlá mundo.\n",
            encoding="utf-8",
        )
        docs = _load_vtt(str(vtt_file))
        assert docs[0].metadata.get("page_num") is None

    def test_vtt_has_start_char_zero(self, tmp_path):
        """Arquivo VTT deve ter start_char=0."""
        vtt_file = tmp_path / "transcricao.vtt"
        vtt_file.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nOlá mundo.\n",
            encoding="utf-8",
        )
        docs = _load_vtt(str(vtt_file))
        assert docs[0].metadata.get("start_char") == 0


# ---------------------------------------------------------------------------
# _load_obsidian_note
# ---------------------------------------------------------------------------

class TestLoadObsidianNote:
    def test_obsidian_section_has_page_num_none(self, tmp_path):
        """Seções de nota Obsidian devem ter page_num=None."""
        note = tmp_path / "nota.md"
        note.write_text(
            "---\ntitle: Minha Nota\n---\n\n" + "Conteúdo longo da nota " * 5,
            encoding="utf-8",
        )
        docs = _load_obsidian_note(str(note))
        for doc in docs:
            assert doc.metadata.get("page_num") is None

    def test_obsidian_section_has_start_char_zero(self, tmp_path):
        """Seções de nota Obsidian devem ter start_char=0."""
        note = tmp_path / "nota.md"
        note.write_text(
            "Conteúdo longo da primeira seção que tem mais de 50 chars.",
            encoding="utf-8",
        )
        docs = _load_obsidian_note(str(note))
        for doc in docs:
            assert doc.metadata.get("start_char") == 0


# ---------------------------------------------------------------------------
# _load_image (mocked — pytesseract ou vision)
# ---------------------------------------------------------------------------

class TestLoadImage:
    def test_image_has_page_num_none(self, tmp_path):
        """Imagens devem ter page_num=None."""
        img_file = tmp_path / "img.png"
        img_file.write_bytes(b"\x89PNG\r\n")  # header mínimo

        with patch("pytesseract.image_to_string", return_value="Texto OCR"):
            with patch("PIL.Image.open") as mock_open:
                mock_img = MagicMock()
                mock_img.mode = "RGB"
                mock_open.return_value = mock_img
                docs = _load_image(str(img_file))

        assert docs[0].metadata.get("page_num") is None

    def test_image_has_start_char_zero(self, tmp_path):
        """Imagens devem ter start_char=0."""
        img_file = tmp_path / "img.png"
        img_file.write_bytes(b"\x89PNG\r\n")

        with patch("pytesseract.image_to_string", return_value="Texto OCR"):
            with patch("PIL.Image.open") as mock_open:
                mock_img = MagicMock()
                mock_img.mode = "RGB"
                mock_open.return_value = mock_img
                docs = _load_image(str(img_file))

        assert docs[0].metadata.get("start_char") == 0


# ---------------------------------------------------------------------------
# SourceRecord — campos page_num e start_char no TypedDict
# ---------------------------------------------------------------------------

class TestSourceRecordFields:
    def test_source_record_has_page_num_field(self):
        """SourceRecord TypedDict deve expor page_num."""
        from core.rag import SourceRecord
        hints = SourceRecord.__annotations__
        assert "page_num" in hints, "SourceRecord deve ter campo page_num"

    def test_source_record_has_start_char_field(self):
        """SourceRecord TypedDict deve expor start_char."""
        from core.rag import SourceRecord
        hints = SourceRecord.__annotations__
        assert "start_char" in hints, "SourceRecord deve ter campo start_char"

    def test_source_record_page_num_accepts_none(self):
        """page_num aceita None (formatos sem páginas)."""
        from core.rag import SourceRecord
        record: SourceRecord = {
            "path": "/f.md",
            "excerpt": "texto",
            "score": 1.0,
            "page_num": None,
            "start_char": 0,
        }
        assert record["page_num"] is None

    def test_source_record_page_num_accepts_int(self):
        """page_num aceita int (PDFs, EPUBs)."""
        from core.rag import SourceRecord
        record: SourceRecord = {
            "path": "/f.pdf",
            "excerpt": "texto",
            "score": 1.0,
            "page_num": 3,
            "start_char": 0,
        }
        assert record["page_num"] == 3


# ---------------------------------------------------------------------------
# _enrich_chunk_offsets — page_num preservado quando já definido
# ---------------------------------------------------------------------------

class TestEnrichChunkOffsets:
    def test_preserves_existing_page_num(self):
        """page_num já setado pelo loader não deve ser sobrescrito."""
        from core.indexer import _enrich_chunk_offsets

        source_doc = Document(
            page_content="Texto completo da página.",
            metadata={"source": "/f.pdf"},
        )
        chunk = Document(
            page_content="Texto completo da página.",
            metadata={
                "source": "/f.pdf",
                "page": 2,        # 0-based do PyPDF
                "page_num": 3,    # 1-based já definido pelo loader
                "start_index": 0,
            },
        )
        _enrich_chunk_offsets([chunk], [source_doc])
        # page_num deve permanecer 3 (do loader), não virar 2 ou 3 de page+1
        assert chunk.metadata["page_num"] == 3

    def test_computes_page_num_from_page_when_absent(self):
        """Se page_num ausente mas page presente, computa 1-based."""
        from core.indexer import _enrich_chunk_offsets

        source_doc = Document(
            page_content="Texto da página 0.",
            metadata={"source": "/f.pdf"},
        )
        chunk = Document(
            page_content="Texto da página 0.",
            metadata={
                "source": "/f.pdf",
                "page": 0,   # 0-based, sem page_num
                "start_index": 0,
            },
        )
        _enrich_chunk_offsets([chunk], [source_doc])
        assert chunk.metadata["page_num"] == 1  # 0 + 1

    def test_page_3_maps_to_page_num_4(self):
        """page=3 (4ª página, 0-based) → page_num=4 (1-based)."""
        from core.indexer import _enrich_chunk_offsets

        source_doc = Document(
            page_content="Texto da p4.",
            metadata={"source": "/f.pdf"},
        )
        chunk = Document(
            page_content="Texto da p4.",
            metadata={"source": "/f.pdf", "page": 3, "start_index": 0},
        )
        _enrich_chunk_offsets([chunk], [source_doc])
        assert chunk.metadata["page_num"] == 4

    def test_start_char_set_from_start_index(self):
        """start_char deve ser igual a start_index do splitter."""
        from core.indexer import _enrich_chunk_offsets

        text = "Início. Meio. Fim."
        source_doc = Document(page_content=text, metadata={"source": "/f.md"})
        chunk = Document(
            page_content="Início.",
            metadata={"source": "/f.md", "start_index": 0},
        )
        _enrich_chunk_offsets([chunk], [source_doc])
        assert chunk.metadata["start_char"] == 0

    def test_start_char_mid_document(self):
        """start_char reflete offset correto no meio do documento."""
        from core.indexer import _enrich_chunk_offsets

        text = "Primeira parte. Segunda parte."
        source_doc = Document(page_content=text, metadata={"source": "/f.md"})
        chunk = Document(
            page_content="Segunda parte.",
            metadata={"source": "/f.md", "start_index": 16},
        )
        _enrich_chunk_offsets([chunk], [source_doc])
        assert chunk.metadata["start_char"] == 16
