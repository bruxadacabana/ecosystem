"""
Testes de app/ui/views/investigation_view.py — pastas de investigação (Fase 7, item 3).

Cobre: lista; estado vazio; criar (via QInputDialog mockado); detalhe (notas +
artigos); seleção; salvar notas da pasta; nota por artigo; remover artigo; exportar
dossiê para arquivo; duplo-clique emite article_selected. `investigations.get_conn`
é patchado para o DB de teste.
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

import app.core.investigations as inv_mod
from app.core.investigations import add_article, create_investigation
from app.ui.views.investigation_view import InvestigationView

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


def _article(conn, fid, *, title="T", published_at="2026-06-01T00:00:00Z") -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, published_at) VALUES (?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", title, published_at),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def view(qapp, tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    fid = conn.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("https://f.com/rss", "Feed")).lastrowid
    conn.commit()
    import app.core.highlights as hl_mod
    with patch.object(inv_mod, "get_conn", lambda: _open_db(db_file)), \
         patch.object(hl_mod, "get_conn", lambda: _open_db(db_file)):
        v = InvestigationView()
        yield v, conn, fid, tmp_path
    conn.close()


def test_empty_state(view):
    v, *_ = view
    assert v.load_investigations() == 0
    assert "Nenhuma investigação" in v._header.text()


def test_load_lists(view):
    v, conn, _, _ = view
    create_investigation("Caso A", conn=conn)
    assert v.load_investigations() == 1
    assert "Caso A" in v._inv_list.item(0).text()


def test_create_via_dialog(view):
    v, *_ = view
    with patch("app.ui.views.investigation_view.QInputDialog.getText", return_value=("Nova Pasta", True)):
        v._on_new()
    assert v._inv_list.count() == 1
    assert "Nova Pasta" in v._inv_list.item(0).text()
    assert v._current_inv_id is not None   # selecionada após criar


def test_show_investigation_detail(view):
    v, conn, fid, _ = view
    inv = create_investigation("X", "minhas notas", conn=conn)
    add_article(inv, _article(conn, fid, title="Artigo 1"), conn=conn)
    v.load_investigations()
    v.show_investigation(inv)
    assert v._desc_edit.toPlainText() == "minhas notas"
    assert v._articles.count() == 1
    assert "Artigo 1" in v._articles.item(0).text()


def test_select_row_shows_detail(view):
    v, conn, fid, _ = view
    inv = create_investigation("X", conn=conn)
    add_article(inv, _article(conn, fid), conn=conn)
    v.load_investigations()
    v._inv_list.setCurrentRow(0)
    assert v._current_inv_id == inv
    assert v._articles.count() == 1


def test_save_description(view):
    v, conn, _, _ = view
    inv = create_investigation("X", conn=conn)
    v.load_investigations()
    v.show_investigation(inv)
    v._desc_edit.setPlainText("atualizado")
    v._on_save_desc()
    assert conn.execute("SELECT description FROM investigations WHERE id=?", (inv,)).fetchone()[0] == "atualizado"


def test_article_note_save(view):
    v, conn, fid, _ = view
    inv = create_investigation("X", conn=conn)
    aid = _article(conn, fid)
    add_article(inv, aid, conn=conn)
    v.load_investigations()
    v.show_investigation(inv)
    v._articles.setCurrentRow(0)            # seleciona o artigo
    v._note_edit.setPlainText("nota do artigo")
    v._on_save_note()
    note = conn.execute(
        "SELECT notes FROM investigation_articles WHERE investigation_id=? AND article_id=?",
        (inv, aid)).fetchone()[0]
    assert note == "nota do artigo"


def test_remove_article(view):
    v, conn, fid, _ = view
    inv = create_investigation("X", conn=conn)
    add_article(inv, _article(conn, fid), conn=conn)
    v.load_investigations()
    v.show_investigation(inv)
    v._articles.setCurrentRow(0)
    v._on_remove_article()
    assert v._articles.count() == 0


def test_export_to_writes_file(view):
    v, conn, fid, tmp = view
    inv = create_investigation("Dossiê", "desc", conn=conn)
    add_article(inv, _article(conn, fid, title="Fato"), conn=conn)
    v.load_investigations()
    v.show_investigation(inv)
    out = tmp / "dossie.md"
    assert v.export_to(str(out)) is True
    text = out.read_text(encoding="utf-8")
    assert "# Dossiê" in text and "### Fato" in text


def test_export_highlights_to_writes_file(view):
    from app.core.highlights import add_highlight
    v, conn, fid, tmp = view
    inv = create_investigation("Caso", conn=conn)
    aid = _article(conn, fid, title="Artigo")
    add_article(inv, aid, conn=conn)
    add_highlight(aid, "trecho marcado", "citation", conn=conn)
    v.load_investigations()
    v.show_investigation(inv)
    out = tmp / "destaques.md"
    assert v.export_highlights_to(str(out)) is True
    text = out.read_text(encoding="utf-8")
    assert "## Citação" in text and "trecho marcado" in text


def test_double_click_emits_article_selected(view):
    v, conn, fid, _ = view
    inv = create_investigation("X", conn=conn)
    aid = _article(conn, fid)
    add_article(inv, aid, conn=conn)
    v.load_investigations()
    v.show_investigation(inv)
    got = []
    v.article_selected.connect(got.append)
    v._on_article_double_clicked(v._articles.item(0))
    assert got == [aid]
