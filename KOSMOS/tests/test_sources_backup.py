"""
Testes de app/core/sources_backup.py — backup/restore das fontes (Fase Config).

Cobre: export escreve as DUAS cópias (kosmos/ + .backup/kosmos/) no formato v3;
restore importa quando o banco está vazio; não restaura por cima de feeds existentes;
cai para a cópia .backup; sem sync_root → no-op. `ecosystem_client.get_sync_root`
é mockado para um tmp.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

import ecosystem_client
from app.core.feeds_admin import add_feed
from app.core.sources_backup import export_sources, restore_sources_if_empty


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
def env(tmp_path):
    db_file = tmp_path / "kosmos.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    sync = tmp_path / "sync"
    sync.mkdir()
    with patch.object(ecosystem_client, "get_sync_root", lambda: str(sync)):
        yield conn, sync
    conn.close()


def _live(sync: Path) -> Path:
    return sync / "kosmos" / "sources.json"


def _backup(sync: Path) -> Path:
    return sync / ".backup" / "kosmos" / "sources.json"


def test_export_writes_both_files(env):
    conn, sync = env
    add_feed("https://a.com/rss", "Feed A", "Geral", conn=conn)
    add_feed("https://b.com/rss", "Feed B", "Tech", conn=conn)
    assert export_sources(conn=conn) == 2
    assert _live(sync).exists() and _backup(sync).exists()
    data = json.loads(_live(sync).read_text(encoding="utf-8"))
    assert {d["url"] for d in data} == {"https://a.com/rss", "https://b.com/rss"}
    assert set(data[0].keys()) == {"url", "title", "category", "enabled"}   # formato v3
    assert _backup(sync).read_text(encoding="utf-8") == _live(sync).read_text(encoding="utf-8")


def test_restore_when_empty(env):
    conn, sync = env
    _live(sync).parent.mkdir(parents=True, exist_ok=True)
    _live(sync).write_text(json.dumps(
        [{"url": "https://x.com", "title": "X", "category": "C", "enabled": True}]), encoding="utf-8")
    assert restore_sources_if_empty(conn=conn) == 1
    row = conn.execute("SELECT url, category FROM feeds").fetchone()
    assert row["url"] == "https://x.com" and row["category"] == "C"


def test_restore_skips_when_feeds_present(env):
    conn, sync = env
    add_feed("https://a.com/rss", conn=conn)
    _live(sync).parent.mkdir(parents=True, exist_ok=True)
    _live(sync).write_text(json.dumps([{"url": "https://other.com"}]), encoding="utf-8")
    assert restore_sources_if_empty(conn=conn) == 0   # não restaura por cima


def test_restore_falls_back_to_backup_copy(env):
    conn, sync = env
    _backup(sync).parent.mkdir(parents=True, exist_ok=True)
    _backup(sync).write_text(json.dumps([{"url": "https://bak.com"}]), encoding="utf-8")
    assert restore_sources_if_empty(conn=conn) == 1
    assert conn.execute("SELECT url FROM feeds").fetchone()[0] == "https://bak.com"


def test_export_no_sync_root_is_noop(tmp_path):
    db_file = tmp_path / "kosmos.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    add_feed("https://a.com/rss", conn=conn)
    with patch.object(ecosystem_client, "get_sync_root", lambda: None):
        assert export_sources(conn=conn) == 0   # sem sync_root, não escreve
    conn.close()
