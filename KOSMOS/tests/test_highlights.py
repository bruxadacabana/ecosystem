"""
Testes de app/core/highlights.py — destaques/anotações (Fase 8).

Cobre: criar (texto vazio → None; tipo inválido → generic); listar (ordem por
posição); editar nota; mudar tipo (inválido → False); remover.
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.core.highlights import (
    add_highlight,
    delete_highlight,
    export_highlights_md,
    highlights_for_feed,
    highlights_for_investigation,
    list_highlights,
    set_highlight_type,
    update_highlight_note,
)

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


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    fid = conn.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("https://f.com/rss", "F")).lastrowid
    aid = conn.execute(
        "INSERT INTO articles (feed_id, url, title) VALUES (?, ?, ?)",
        (fid, f"https://j.com/a{next(_counter)}", "Artigo"),
    ).lastrowid
    conn.commit()
    yield conn, aid
    conn.close()


def test_add_returns_id(db):
    conn, aid = db
    hid = add_highlight(aid, "um trecho", "citation", conn=conn)
    assert hid is not None
    row = conn.execute("SELECT text, highlight_type FROM highlights WHERE id=?", (hid,)).fetchone()
    assert row["text"] == "um trecho" and row["highlight_type"] == "citation"


def test_add_empty_text_none(db):
    conn, aid = db
    assert add_highlight(aid, "   ", "fact", conn=conn) is None


def test_add_invalid_type_becomes_generic(db):
    conn, aid = db
    hid = add_highlight(aid, "x", "inventado", conn=conn)
    t = conn.execute("SELECT highlight_type FROM highlights WHERE id=?", (hid,)).fetchone()[0]
    assert t == "generic"


def test_list_ordered_by_position(db):
    conn, aid = db
    add_highlight(aid, "segundo", "fact", position_hint=50, conn=conn)
    add_highlight(aid, "primeiro", "fact", position_hint=10, conn=conn)
    texts = [h["text"] for h in list_highlights(aid, conn=conn)]
    assert texts == ["primeiro", "segundo"]


def test_update_note(db):
    conn, aid = db
    hid = add_highlight(aid, "x", "question", conn=conn)
    assert update_highlight_note(hid, "minha nota", conn=conn) is True
    assert conn.execute("SELECT note FROM highlights WHERE id=?", (hid,)).fetchone()[0] == "minha nota"


def test_set_type(db):
    conn, aid = db
    hid = add_highlight(aid, "x", "generic", conn=conn)
    assert set_highlight_type(hid, "contradiction", conn=conn) is True
    assert set_highlight_type(hid, "xxx", conn=conn) is False   # tipo inválido
    assert conn.execute("SELECT highlight_type FROM highlights WHERE id=?", (hid,)).fetchone()[0] == "contradiction"


def test_delete(db):
    conn, aid = db
    hid = add_highlight(aid, "x", "fact", conn=conn)
    assert delete_highlight(hid, conn=conn) is True
    assert list_highlights(aid, conn=conn) == []


# ---------------------------------------------------------------------------
# Exportação (item 2)
# ---------------------------------------------------------------------------

class TestExport:
    def test_for_feed_and_md_structure(self, db):
        conn, aid = db
        fid = conn.execute("SELECT feed_id FROM articles WHERE id=?", (aid,)).fetchone()[0]
        add_highlight(aid, "uma citação", "citation", note="importante", conn=conn)
        add_highlight(aid, "um dado", "fact", conn=conn)
        hs = highlights_for_feed(fid, conn=conn)
        assert len(hs) == 2
        md = export_highlights_md(hs, "Meu Feed")
        assert md.startswith("# Destaques — Meu Feed")
        assert "## Citação" in md and "uma citação" in md
        assert "## Dado verificável" in md and "um dado" in md
        assert "Nota: importante" in md

    def test_for_investigation(self, db):
        conn, aid = db
        inv = conn.execute("INSERT INTO investigations (name) VALUES ('Caso')").lastrowid
        conn.execute("INSERT INTO investigation_articles (investigation_id, article_id) VALUES (?, ?)", (inv, aid))
        conn.commit()
        add_highlight(aid, "trecho da pasta", "question", conn=conn)
        hs = highlights_for_investigation(inv, conn=conn)
        assert len(hs) == 1 and hs[0]["text"] == "trecho da pasta"

    def test_groups_by_type(self, db):
        conn, aid = db
        fid = conn.execute("SELECT feed_id FROM articles WHERE id=?", (aid,)).fetchone()[0]
        add_highlight(aid, "c1", "citation", conn=conn)
        add_highlight(aid, "c2", "citation", conn=conn)
        add_highlight(aid, "contra", "contradiction", conn=conn)
        md = export_highlights_md(highlights_for_feed(fid, conn=conn), "F")
        assert md.count("## Citação") == 1   # agrupado, não repetido
        assert "c1" in md and "c2" in md and "## Contradição" in md

    def test_empty_export(self):
        md = export_highlights_md([], "Vazio")
        assert md.startswith("# Destaques — Vazio")
        assert "0 destaque(s)" in md
