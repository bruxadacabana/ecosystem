"""
Testes de app/ui/views/feed_sidebar.py — foco no emit de exportação de destaques (Fase 8).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest
from PySide6.QtCore import Qt

from app.ui.views.feed_sidebar import ALL_FEEDS_ID, FeedSidebar


def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db_at(path: Path) -> None:
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


def _find_feed_item(tree, feed_id):
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        for j in range(top.childCount()):
            child = top.child(j)
            if child.data(0, Qt.ItemDataRole.UserRole) == feed_id:
                return child
    return None


@pytest.fixture
def sidebar(qapp, tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    fid = conn.execute(
        "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
        ("https://f.com/rss", "Meu Feed", "Geral"),
    ).lastrowid
    conn.commit()
    sb = FeedSidebar()
    sb.load_feeds(conn=conn)
    yield sb, conn, fid
    conn.close()


def test_request_export_emits_feed_id(sidebar):
    sb, conn, fid = sidebar
    item = _find_feed_item(sb._tree, fid)
    assert item is not None
    got = []
    sb.export_highlights_requested.connect(got.append)
    sb._request_export_highlights(item)
    assert got == [fid]


def test_request_export_ignores_all_feeds(sidebar):
    sb, _, _ = sidebar
    # item "Todos os feeds" (UserRole = ALL_FEEDS_ID) não deve emitir
    all_item = sb._tree.topLevelItem(0)
    assert all_item.data(0, Qt.ItemDataRole.UserRole) == ALL_FEEDS_ID
    got = []
    sb.export_highlights_requested.connect(got.append)
    sb._request_export_highlights(all_item)
    assert got == []
