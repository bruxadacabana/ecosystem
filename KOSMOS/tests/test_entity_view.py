"""
Testes de app/ui/views/entity_view.py — rastreador de entidades (Fase 7, item 2).

Cobre: lista de entidades; estado vazio; detalhe (header/sentimento/feeds/timeline);
seleção pelo rail; refresh (backfill); clique na timeline emite article_selected;
salvar nota. `entities.get_conn` é patchado para o DB de teste.
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

import app.core.entities as ents
from app.core.entities import materialize_entity_links
from app.ui.views.entity_view import EntityView

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


def _feed(conn, title="Feed") -> int:
    cur = conn.execute("INSERT INTO feeds (url, title) VALUES (?, ?)",
                       (f"https://f{next(_counter)}.com/rss", title))
    conn.commit()
    return cur.lastrowid


def _article(conn, fid, *, title="T", ai_sentiment=None, ai_entities=None) -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, published_at, ai_sentiment, ai_entities) "
        "VALUES (?,?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", title, "2026-06-01T00:00:00Z", ai_sentiment, ai_entities),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def view(qapp, tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    with patch.object(ents, "get_conn", lambda: _open_db(db_file)):
        v = EntityView()
        yield v, conn
    conn.close()


def _eid(conn, name) -> int:
    return conn.execute("SELECT id FROM entities WHERE name=?", (name,)).fetchone()["id"]


def test_load_lists_entities(view):
    v, conn = view
    fid = _feed(conn)
    materialize_entity_links(_article(conn, fid), [{"nome": "Lula", "tipo": "pessoa"}], conn=conn)
    assert v.load_entities() == 1
    assert "Lula" in v._entity_list.item(0).text()
    assert "Pessoa" in v._entity_list.item(0).text()


def test_empty_state(view):
    v, _ = view
    assert v.load_entities() == 0
    assert v._entity_list.count() == 0
    assert "Nenhuma entidade" in v._header.text()


def test_show_entity_detail(view):
    v, conn = view
    fid = _feed(conn, "F1")
    a = _article(conn, fid, title="Artigo X", ai_sentiment="positivo")
    materialize_entity_links(a, [{"nome": "E", "tipo": "tema"}], conn=conn)
    v.load_entities()
    v.show_entity(_eid(conn, "E"))
    assert "positivo: 1" in v._sentiment_lbl.text()
    assert "F1" in v._feeds_lbl.text()
    assert v._timeline.count() == 1
    assert "Artigo X" in v._timeline.item(0).text()


def test_select_row_shows_detail(view):
    v, conn = view
    fid = _feed(conn)
    materialize_entity_links(_article(conn, fid, title="A"), [{"nome": "E", "tipo": "tema"}], conn=conn)
    v.load_entities()
    v._entity_list.setCurrentRow(0)   # dispara _on_entity_selected
    assert v._timeline.count() == 1
    assert v._current_entity_id == _eid(conn, "E")


def test_refresh_backfills(view):
    v, conn = view
    fid = _feed(conn)
    _article(conn, fid, ai_entities='[{"nome":"Nova","tipo":"tema"}]')   # não materializado
    assert v.load_entities() == 0
    v.refresh()                       # backfill materializa
    assert v._entity_list.count() == 1
    assert "Nova" in v._entity_list.item(0).text()


def test_timeline_click_emits_article_selected(view):
    v, conn = view
    fid = _feed(conn)
    a = _article(conn, fid, title="Abrir")
    materialize_entity_links(a, [{"nome": "E", "tipo": "tema"}], conn=conn)
    v.load_entities()
    v.show_entity(_eid(conn, "E"))
    got = []
    v.article_selected.connect(got.append)
    v._on_timeline_clicked(v._timeline.item(0))
    assert got == [a]


def test_save_notes_persists(view):
    v, conn = view
    fid = _feed(conn)
    materialize_entity_links(_article(conn, fid), [{"nome": "E", "tipo": "tema"}], conn=conn)
    v.load_entities()
    eid = _eid(conn, "E")
    v.show_entity(eid)
    v._notes_edit.setPlainText("anotação importante")
    v._on_save_notes()
    assert conn.execute("SELECT notes FROM entities WHERE id=?", (eid,)).fetchone()["notes"] == "anotação importante"
