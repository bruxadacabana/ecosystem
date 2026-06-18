"""
Testes da integração de destaques no ReaderPane (Fase 8).

Cobre: _body_html (coloração inline, trecho não-casado ignorado, escape, newline→br);
e o fluxo no leitor — abrir artigo com destaque colore o corpo; criar destaque pelo
corpo; selecionar → nota; salvar nota; remover. `highlights.get_conn` é patchado.
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

import app.core.highlights as hl
from app.core.highlights import add_highlight
from app.ui.views.reader_pane import _body_html

_counter = itertools.count()


def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db_at(path: Path) -> None:
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


def _article(conn, fid, content="Corpo do artigo com trecho importante aqui.") -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, content_text, is_scraped) VALUES (?,?,?,?,1)",
        (fid, f"https://j.com/a{next(_counter)}", "Título", content),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def reader(qapp, tmp_path):
    import app.core.database as db_module
    from app.ui.views.reader_pane import ReaderPane
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    fid = conn.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("https://f.com/rss", "F")).lastrowid
    conn.commit()
    with patch.object(db_module, "DB_PATH", db_file), \
         patch.object(hl, "get_conn", lambda: _open_db(db_file)):
        r = ReaderPane()
        yield r, conn, fid
    conn.close()


# ---------------------------------------------------------------------------
# _body_html
# ---------------------------------------------------------------------------

class TestBodyHtml:
    def test_wraps_matched_span(self):
        html = _body_html("foo bar baz", [{"text": "bar", "highlight_type": "citation"}])
        assert '<mark class="hl-citation">bar</mark>' in html

    def test_unmatched_ignored(self):
        assert "<mark" not in _body_html("foo bar", [{"text": "zzz", "highlight_type": "fact"}])

    def test_escapes_html(self):
        html = _body_html("<b>x</b>", [])
        assert "&lt;b&gt;" in html and "<b>" not in html

    def test_newlines_to_br(self):
        assert _body_html("a\nb", []) == "a<br>b"

    def test_longest_first(self):
        # "trecho longo" e "longo" — o longo deve casar inteiro, não quebrado
        html = _body_html("um trecho longo aqui", [
            {"text": "longo", "highlight_type": "fact"},
            {"text": "trecho longo", "highlight_type": "citation"},
        ])
        assert '<mark class="hl-citation">trecho longo</mark>' in html


# ---------------------------------------------------------------------------
# ReaderPane — fluxo de destaques
# ---------------------------------------------------------------------------

class TestReaderHighlights:
    def test_open_with_highlight_colors_body(self, reader):
        r, conn, fid = reader
        aid = _article(conn, fid)
        add_highlight(aid, "trecho importante", "fact", conn=conn)
        r.show_article(aid, conn=conn)
        assert "<mark" in r.current_body_html()
        assert r._highlights_list.count() == 1

    def test_open_without_highlight_plain_body(self, reader):
        r, conn, fid = reader
        aid = _article(conn, fid)
        r.show_article(aid, conn=conn)
        assert "<mark" not in r.current_body_html()
        assert r._highlights_list.count() == 0

    def test_create_highlight_colors_and_lists(self, reader):
        r, conn, fid = reader
        aid = _article(conn, fid)
        r.show_article(aid, conn=conn)
        r._create_highlight("trecho importante", "citation")
        assert r._highlights_list.count() == 1
        assert "<mark" in r.current_body_html()
        # persistiu no banco
        assert conn.execute("SELECT COUNT(*) c FROM highlights WHERE article_id=?", (aid,)).fetchone()["c"] == 1

    def test_select_loads_note_and_save(self, reader):
        r, conn, fid = reader
        aid = _article(conn, fid)
        hid = add_highlight(aid, "trecho importante", "fact", note="nota inicial", conn=conn)
        r.show_article(aid, conn=conn)
        r._highlights_list.setCurrentRow(0)
        assert r._current_highlight_id == hid
        assert r._highlight_note_edit.toPlainText() == "nota inicial"
        r._highlight_note_edit.setPlainText("nota editada")
        r._on_save_highlight_note()
        assert conn.execute("SELECT note FROM highlights WHERE id=?", (hid,)).fetchone()[0] == "nota editada"

    def test_remove_highlight(self, reader):
        r, conn, fid = reader
        aid = _article(conn, fid)
        add_highlight(aid, "trecho importante", "fact", conn=conn)
        r.show_article(aid, conn=conn)
        r._highlights_list.setCurrentRow(0)
        r._on_remove_highlight()
        assert r._highlights_list.count() == 0
        assert "<mark" not in r.current_body_html()   # corpo volta a plano
