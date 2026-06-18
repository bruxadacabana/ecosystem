"""
Testes da SavedView (lista de salvos/arquivados — is_saved=1).

Cobre: load lista só os is_saved=1; vazio mostra placeholder; clique emite
article_selected com o id correto.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest
from PySide6.QtCore import Qt

from app.ui.views.saved_view import SavedView


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
    fid = conn.execute("INSERT INTO feeds (url, title) VALUES (?, ?)",
                       ("https://f.com/rss", "Feed A")).lastrowid
    conn.commit()
    yield conn, fid
    conn.close()


def test_load_lists_only_saved(qapp, db):
    conn, fid = db
    conn.execute("INSERT INTO articles (feed_id, url, title, is_saved) VALUES (?,?,?,1)",
                 (fid, "https://j.com/1", "Salvo"))
    conn.execute("INSERT INTO articles (feed_id, url, title, is_saved) VALUES (?,?,?,0)",
                 (fid, "https://j.com/2", "NaoSalvo"))
    conn.commit()
    v = SavedView()
    assert v.load(conn=conn) == 1
    assert v.article_count() == 1


def test_empty_shows_placeholder(qapp, db):
    conn, _ = db
    v = SavedView()
    assert v.load(conn=conn) == 0
    assert not v._placeholder.isHidden()


def test_click_emits_article_selected(qapp, db):
    conn, fid = db
    conn.execute("INSERT INTO articles (feed_id, url, title, is_saved) VALUES (?,?,?,1)",
                 (fid, "https://j.com/1", "Salvo"))
    conn.commit()
    v = SavedView()
    v.load(conn=conn)
    got = []
    v.article_selected.connect(got.append)
    aid = v._list.item(0).data(Qt.ItemDataRole.UserRole)
    v._on_item_clicked(v._list.item(0))
    assert got == [aid]
