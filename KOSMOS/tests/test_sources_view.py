"""
Testes da SourcesView (gestão de fontes — design antigo sobre os feeds v3).

Cobre: load lista feeds; vazio mostra placeholder; toggle de pausa chama update_feed
e emite feeds_changed; _do_delete chama delete_feed, recarrega e emite; o _SourceRow
alterna o rótulo Pausar/Retomar e emite pause_toggled.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.ui.views.sources_view import SourcesView, _SourceRow


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
    fid = conn.execute("INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
                       ("https://f.com/rss", "Feed A", "Geral")).lastrowid
    conn.commit()
    yield conn, fid
    conn.close()


def test_load_lists_feeds(qapp, db):
    conn, _ = db
    v = SourcesView()
    assert v.load(conn=conn) == 1
    assert v.feed_count() == 1


def test_empty_shows_placeholder(qapp, db):
    conn, _ = db
    conn.execute("DELETE FROM feeds")
    conn.commit()
    v = SourcesView()
    assert v.load(conn=conn) == 0
    assert not v._placeholder.isHidden()


def test_pause_toggled_calls_update_and_emits(qapp, db):
    conn, fid = db
    v = SourcesView()
    v.load(conn=conn)
    got = []
    v.feeds_changed.connect(lambda: got.append(1))
    with patch("app.ui.views.sources_view.update_feed") as mupd:
        v._on_pause_toggled(fid, False)
    mupd.assert_called_once_with(fid, enabled=False)
    assert got == [1]


def test_do_delete_calls_reloads_and_emits(qapp, db):
    conn, fid = db
    v = SourcesView()
    v.load(conn=conn)
    got = []
    v.feeds_changed.connect(lambda: got.append(1))
    with patch("app.ui.views.sources_view.delete_feed") as mdel, \
         patch.object(v, "load") as mload:
        v._do_delete(fid)
    mdel.assert_called_once_with(fid)
    mload.assert_called_once()
    assert got == [1]


def test_source_row_toggle_emits_and_relabels(qapp):
    row = _SourceRow({"id": 5, "url": "u", "title": "T", "category": "C", "enabled": 1})
    assert row._pause_btn.text() == "Pausar"
    got = []
    row.pause_toggled.connect(lambda fid, en: got.append((fid, en)))
    row._on_toggle()
    assert got == [(5, False)]
    assert row._pause_btn.text() == "Retomar"


def test_source_row_starts_paused(qapp):
    row = _SourceRow({"id": 1, "url": "u", "title": "T", "category": "C", "enabled": 0})
    assert row._pause_btn.text() == "Retomar"
    assert row._name_lbl.property("paused") is True
