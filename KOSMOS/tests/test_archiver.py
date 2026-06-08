"""
Testes para app/core/archiver.py (KOSMOS v3, Fase 5).

Cobre:
  - helpers: _slugify, _abnt_author, _abnt_date, _detect_doi;
  - frontmatter: archived_by/title/source/url/date/author/language/tags/type;
  - kosmos_analysis: true só quando há análise; ausente caso contrário;
  - corpo usa content_text; fallback para content_excerpt;
  - seção "## Análise do KOSMOS" presente com campos AI; ausente sem análise;
  - ABNT: documento eletrônico (sem DOI) e artigo científico (URL com DOI);
  - dual-language: translated_text → has_translation + 2 seções;
  - gravação em {archive_path}/Web/{data}_{slug}.md; is_saved=1; nome único;
  - ValueError quando artigo não existe.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Banco
# ---------------------------------------------------------------------------

def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _init_db_at(path: Path) -> None:
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


def _insert_feed(conn: sqlite3.Connection, title: str = "Jornal Teste") -> int:
    cur = conn.execute(
        "INSERT INTO feeds (url, title) VALUES (?, ?)",
        ("https://jornal.com/rss", title),
    )
    conn.commit()
    return cur.lastrowid


def _insert_article(conn: sqlite3.Connection, feed_id: int, **kw) -> int:
    fields = {
        "url": "https://jornal.com/materia",
        "title": "Título da Matéria",
        "author": None,
        "published_at": "2026-06-01T10:00:00Z",
        "article_type": "news",
        "language_detected": "pt",
        "content_excerpt": "Resumo do feed.",
        "content_text": None,
        "ai_tags": None,
        "ai_sentiment": None,
        "ai_language": None,
        "ai_five_ws": None,
        "ai_entities": None,
        "ai_bias": None,
    }
    fields.update(kw)
    cols = ", ".join(["feed_id", *fields.keys()])
    ph = ", ".join(["?"] * (1 + len(fields)))
    cur = conn.execute(
        f"INSERT INTO articles ({cols}) VALUES ({ph})",
        (feed_id, *fields.values()),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def env(tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    feed_id = _insert_feed(conn)
    archive = tmp_path / "archive"
    yield conn, feed_id, str(archive)
    conn.close()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers unitários
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_slugify_ascii_and_hyphens(self):
        from app.core.archiver import _slugify
        assert _slugify("Educação: a Crise Política!") == "educacao-a-crise-politica"

    def test_slugify_empty_fallback(self):
        from app.core.archiver import _slugify
        assert _slugify("") == "artigo"

    def test_abnt_author_person(self):
        from app.core.archiver import _abnt_author
        assert _abnt_author("Maria Silva Souza", "Jornal") == "SOUZA, Maria Silva"

    def test_abnt_author_corporate_when_empty(self):
        from app.core.archiver import _abnt_author
        assert _abnt_author(None, "Folha") == "FOLHA"

    def test_abnt_date(self):
        from app.core.archiver import _abnt_date, _parse_dt
        assert _abnt_date(_parse_dt("2026-06-01T10:00:00Z")) == "1 jun. 2026"

    def test_detect_doi_true(self):
        from app.core.archiver import _detect_doi
        doi, is_doi = _detect_doi("https://doi.org/10.1000/xyz123")
        assert is_doi is True
        assert doi == "10.1000/xyz123"

    def test_detect_doi_arxiv(self):
        from app.core.archiver import _detect_doi
        doi, is_doi = _detect_doi("https://arxiv.org/abs/2506.01234")
        assert is_doi is False
        assert doi == "arXiv:2506.01234"

    def test_detect_doi_none(self):
        from app.core.archiver import _detect_doi
        assert _detect_doi("https://news.com/x") == (None, False)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_basic_frontmatter(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, author="João Lima",
                              content_text="Corpo limpo do artigo.")
        path = archive_article(aid, archive, conn=conn)
        text = _read(path)
        assert "archived_by: kosmos" in text
        assert 'title: "Título da Matéria"' in text
        assert 'source: "Jornal Teste"' in text
        assert 'url: "https://jornal.com/materia"' in text
        assert 'date: "2026-06-01"' in text
        assert 'author: "João Lima"' in text
        assert 'language: "pt"' in text
        assert 'type: "news"' in text

    def test_tags_rendered(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, ai_tags=json.dumps(["política", "economia"]),
                              content_text="x" * 50)
        text = _read(archive_article(aid, archive, conn=conn))
        assert 'tags: ["política", "economia"]' in text

    def test_no_analysis_no_flag(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, content_text="Sem análise.")
        text = _read(archive_article(aid, archive, conn=conn))
        assert "kosmos_analysis" not in text

    def test_analysis_sets_flag(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, content_text="Com análise.",
                              ai_sentiment="neutro")
        text = _read(archive_article(aid, archive, conn=conn))
        assert "kosmos_analysis: true" in text


# ---------------------------------------------------------------------------
# Corpo e análise
# ---------------------------------------------------------------------------

class TestBody:
    def test_uses_content_text(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, content_text="TEXTO COMPLETO AQUI",
                              content_excerpt="resumo")
        text = _read(archive_article(aid, archive, conn=conn))
        assert "TEXTO COMPLETO AQUI" in text

    def test_falls_back_to_excerpt(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, content_text=None,
                              content_excerpt="APENAS RESUMO")
        text = _read(archive_article(aid, archive, conn=conn))
        assert "APENAS RESUMO" in text

    def test_analysis_section_present(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(
            conn, fid, content_text="corpo",
            ai_sentiment="negativo",
            ai_five_ws=json.dumps({"quem": "Governo", "o_que": "reforma",
                                   "quando": "2026", "onde": "Brasil", "por_que": "déficit"}),
            ai_entities=json.dumps([{"nome": "Lula", "tipo": "pessoa"},
                                    {"nome": "STF", "tipo": "organização"}]),
            ai_bias=json.dumps({"espectro": "centro-esquerda",
                                "marcadores": ["adjetivação"],
                                "qualidade_apuracao": "alta"}),
        )
        text = _read(archive_article(aid, archive, conn=conn))
        assert "## Análise do KOSMOS" in text
        assert "análise computacional" in text.lower()
        assert "**Sentimento:** negativo" in text
        assert "Quem: Governo" in text
        assert "Lula (pessoa)" in text
        assert "espectro centro-esquerda" in text

    def test_no_analysis_section_when_absent(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, content_text="corpo")
        text = _read(archive_article(aid, archive, conn=conn))
        assert "## Análise do KOSMOS" not in text


# ---------------------------------------------------------------------------
# ABNT
# ---------------------------------------------------------------------------

class TestAbnt:
    def test_electronic_document_format(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, author="Ana Costa", content_text="corpo")
        text = _read(archive_article(aid, archive, conn=conn))
        assert "documento eletrônico" in text
        assert "COSTA, Ana." in text
        assert "Disponível em: https://jornal.com/materia." in text
        assert "Acesso em:" in text
        assert "DOI:" not in text

    def test_scientific_with_doi(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, url="https://doi.org/10.1000/abc.def",
                              content_text="corpo")
        text = _read(archive_article(aid, archive, conn=conn))
        assert "artigo científico" in text
        assert "DOI: 10.1000/abc.def." in text


# ---------------------------------------------------------------------------
# Dual-language
# ---------------------------------------------------------------------------

class TestDualLanguage:
    def test_translation_adds_sections_and_flag(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, language_detected="en",
                              content_text="Original english body.")
        text = _read(archive_article(
            aid, archive, conn=conn,
            translated_text="Corpo traduzido em português.", translated_lang="pt",
        ))
        assert "has_translation: true" in text
        assert 'languages: ["en", "pt"]' in text
        assert "## Texto original" in text
        assert "Original english body." in text
        assert "## Tradução (pt)" in text
        assert "Corpo traduzido em português." in text

    def test_no_translation_single_version(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, content_text="Só original.")
        text = _read(archive_article(aid, archive, conn=conn))
        assert "has_translation" not in text
        assert "## Tradução" not in text

    def test_auto_dual_language_from_db(self, env):
        """Se content_text_translated existe no banco, arquiva dual-language sem param."""
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, content_text="Original body.")
        conn.execute(
            "UPDATE articles SET content_text_translated = ? WHERE id = ?",
            ("Corpo traduzido.", aid),
        )
        conn.commit()
        text = _read(archive_article(aid, archive, conn=conn))  # sem translated_text
        assert "has_translation: true" in text
        assert "Original body." in text
        assert "Corpo traduzido." in text


# ---------------------------------------------------------------------------
# Gravação, is_saved, colisão, erro
# ---------------------------------------------------------------------------

class TestWriteAndState:
    def test_file_in_web_dir_with_date_slug(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, title="A Crise", content_text="corpo")
        path = archive_article(aid, archive, conn=conn)
        assert path.parent == Path(archive) / "Web"
        assert path.name == "2026-06-01_a-crise.md"
        assert path.exists()

    def test_sets_is_saved(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        aid = _insert_article(conn, fid, content_text="corpo")
        archive_article(aid, archive, conn=conn)
        saved = conn.execute("SELECT is_saved FROM articles WHERE id = ?", (aid,)).fetchone()[0]
        assert saved == 1

    def test_unique_path_on_collision(self, env):
        conn, fid, archive = env
        from app.core.archiver import archive_article
        a1 = _insert_article(conn, fid, title="Mesmo", url="https://j.com/1", content_text="a")
        a2 = _insert_article(conn, fid, title="Mesmo", url="https://j.com/2", content_text="b")
        p1 = archive_article(a1, archive, conn=conn)
        p2 = archive_article(a2, archive, conn=conn)
        assert p1 != p2
        assert p2.name == "2026-06-01_mesmo-2.md"

    def test_missing_article_raises(self, env):
        conn, _, archive = env
        from app.core.archiver import archive_article
        with pytest.raises(ValueError):
            archive_article(99999, archive, conn=conn)
