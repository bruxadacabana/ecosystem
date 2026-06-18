"""
Testes de app/core/feeds_admin.py — gerenciamento de feeds (Fase Config).

Cobre: add (id, idempotência, url vazia, categoria default); list (ordem); delete
(cascade); update; import OPML (planos, aninhados, duplicados, inválido).
Tudo com `conn` explícito → não exporta sources.json no sync_root real.
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.core.feeds_admin import add_feed, delete_feed, import_opml, list_feeds, update_feed

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
    db_file = tmp_path / "kosmos.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    yield conn
    conn.close()


def test_add_returns_id(db):
    fid = add_feed("https://a.com/rss", "Feed A", "Geral", conn=db)
    assert fid is not None
    row = db.execute("SELECT url, title, category FROM feeds WHERE id=?", (fid,)).fetchone()
    assert row["url"] == "https://a.com/rss" and row["title"] == "Feed A" and row["category"] == "Geral"


def test_add_idempotent(db):
    a = add_feed("https://a.com/rss", conn=db)
    b = add_feed("https://a.com/rss", conn=db)
    assert a == b
    assert db.execute("SELECT COUNT(*) FROM feeds").fetchone()[0] == 1


def test_add_empty_url_none(db):
    assert add_feed("   ", conn=db) is None


def test_add_default_category(db):
    fid = add_feed("https://a.com/rss", conn=db)
    assert db.execute("SELECT category FROM feeds WHERE id=?", (fid,)).fetchone()[0] == "Sem categoria"


def test_list_order(db):
    add_feed("https://z.com", "Zeta", "Beta", conn=db)
    add_feed("https://a.com", "Alfa", "Alfa", conn=db)
    feeds = list_feeds(conn=db)
    assert [f["category"] for f in feeds] == ["Alfa", "Beta"]   # por categoria


def test_delete_cascades_articles(db):
    fid = add_feed("https://a.com/rss", conn=db)
    db.execute("INSERT INTO articles (feed_id, url, title) VALUES (?, 'https://a.com/1', 'T')", (fid,))
    db.commit()
    delete_feed(fid, conn=db)
    assert db.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0


def test_update(db):
    fid = add_feed("https://a.com/rss", "Velho", "X", conn=db)
    assert update_feed(fid, title="Novo", category="Y", enabled=False, conn=db) is True
    row = db.execute("SELECT title, category, enabled FROM feeds WHERE id=?", (fid,)).fetchone()
    assert row["title"] == "Novo" and row["category"] == "Y" and row["enabled"] == 0


_OPML = """<?xml version="1.0"?>
<opml version="1.0"><body>
  <outline text="Tecnologia">
    <outline type="rss" text="Feed Tech" xmlUrl="https://tech.com/rss"/>
  </outline>
  <outline type="rss" text="Feed Solto" xmlUrl="https://solto.com/rss"/>
</body></opml>"""


def test_import_opml(db):
    n = import_opml(_OPML, conn=db)
    assert n == 2
    feeds = {f["url"]: f for f in list_feeds(conn=db)}
    assert feeds["https://tech.com/rss"]["category"] == "Tecnologia"  # categoria do outline pai
    assert feeds["https://solto.com/rss"]["category"] == "Sem categoria"


def test_import_opml_skips_duplicates(db):
    add_feed("https://tech.com/rss", conn=db)
    n = import_opml(_OPML, conn=db)   # tech.com já existe
    assert n == 1                      # só o solto é novo


def test_import_invalid_opml(db):
    assert import_opml("isto não é xml", conn=db) == 0
