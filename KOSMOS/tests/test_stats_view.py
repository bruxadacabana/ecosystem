"""
Testes de app/ui/views/stats_view.py — dashboard QtCharts (Fase 8).

Cobre: load() monta os 5 gráficos sem quebrar (com e sem dados); o rótulo de viés
reflete os dados. `load(conn=...)` injeta a conexão de teste em todas as métricas.
"""
from __future__ import annotations

import itertools
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.ui.views.stats_view import StatsView

_counter = itertools.count()
_TODAY = datetime.now(timezone.utc).date().isoformat()


def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db_at(path: Path) -> None:
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


@pytest.fixture
def env(qapp, tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    yield StatsView(), conn
    conn.close()


def _seed(conn):
    fid = conn.execute("INSERT INTO feeds (url, title) VALUES ('https://f.com','F')").lastrowid
    conn.execute(
        "INSERT INTO articles (feed_id, url, title, is_read, read_at, ai_sentiment, ai_bias, published_at) "
        "VALUES (?,?,?,1,?,?,?,?)",
        (fid, "https://j.com/a1", "T", _TODAY + "T10:00:00Z", "positivo",
         '{"espectro":"centro"}', _TODAY + "T09:00:00Z"),
    )
    conn.commit()


def test_load_empty_builds_charts(env):
    view, conn = env
    view.load(conn=conn)            # banco vazio — não deve quebrar
    assert view.chart_count() == 5


def test_load_with_data(env):
    view, conn = env
    _seed(conn)
    view.load(conn=conn)
    assert view.chart_count() == 5
    assert "Viés político médio" in view._bias_label.text()
    assert "centro" in view._bias_label.text()


def test_reload_replaces_charts(env):
    view, conn = env
    view.load(conn=conn)
    view.load(conn=conn)            # recarregar não acumula gráficos
    assert view.chart_count() == 5
