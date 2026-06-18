"""
Testes da DashboardView (tela inicial — design antigo sobre os dados v3).

Cobre o _StatsPanel (vazio mostra texto; set_data lista nomes/contagens; voltar a
vazio limpa) e o load() do dashboard (resumo de totais + painéis Top Fontes/Top Tags
preenchidos a partir das funções de stats v3).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest
from PySide6.QtWidgets import QLabel

from app.ui.views.dashboard_view import DashboardView, _StatsPanel


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


def _names(panel) -> list[str]:
    return [w.text() for w in panel.findChildren(QLabel) if w.objectName() == "dashboardStatName"]


class TestStatsPanel:
    def test_empty_shows_text(self, qapp):
        p = _StatsPanel("TÍTULO", "nada ainda")
        empties = [w.text() for w in p.findChildren(QLabel) if w.objectName() == "dashboardStatEmpty"]
        assert "nada ainda" in empties

    def test_set_data_lists_names_and_counts(self, qapp):
        p = _StatsPanel("T", "vazio")
        p.set_data([("alpha", 5), ("beta", 2)])
        assert _names(p) == ["alpha", "beta"]
        counts = [w.text() for w in p.findChildren(QLabel) if w.objectName() == "dashboardStatCount"]
        assert counts == ["5", "2"]

    def test_set_data_empty_reverts_to_empty(self, qapp):
        p = _StatsPanel("T", "vazio")
        p.set_data([("a", 1)])
        p.set_data([])
        assert _names(p) == []


class TestDashboardLoad:
    def test_load_summary_and_panels(self, qapp, db):
        conn, fid = db
        conn.execute("INSERT INTO articles (feed_id, url, title, is_read, ai_tags) VALUES (?,?,?,?,?)",
                     (fid, "https://j.com/1", "A", 1, '["ia"]'))
        conn.execute("INSERT INTO articles (feed_id, url, title, is_read) VALUES (?,?,?,?)",
                     (fid, "https://j.com/2", "B", 0))
        conn.commit()
        dash = DashboardView()
        dash.load(conn=conn)
        s = dash._summary_lbl.text()
        assert "2 artigos" in s and "1 lidos" in s and "1 não-lidos" in s and "1 fontes" in s
        assert _names(dash._fontes_panel) == ["Feed A"]   # 1 artigo lido na Feed A
        assert _names(dash._tags_panel) == ["ia"]

    def test_load_empty_db_shows_empty_panels(self, qapp, db):
        conn, _ = db
        dash = DashboardView()
        dash.load(conn=conn)
        assert "0 artigos" in dash._summary_lbl.text()
        assert _names(dash._fontes_panel) == []
        assert _names(dash._tags_panel) == []
