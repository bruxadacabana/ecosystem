"""
Testes de app/core/stats.py — métricas do dashboard (Fase 8).

Cobre: lidos por dia (preenche zeros), top feeds, distribuição/série de sentimento,
viés médio (bolha editorial) e cobertura por entidade.
"""
from __future__ import annotations

import itertools
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.core.entities import materialize_entity_links
from app.core.stats import (
    articles_read_per_day,
    bias_balance,
    coverage_by_entity,
    sentiment_distribution,
    sentiment_over_time,
    top_feeds,
    top_tags,
    totals,
)

_counter = itertools.count()
_TODAY = datetime.now(timezone.utc).date().isoformat()


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


def _article(conn, fid, *, is_read=0, read_at=None, ai_sentiment=None, ai_bias=None,
             published_at=None) -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, is_read, read_at, ai_sentiment, ai_bias, published_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", "T", is_read, read_at, ai_sentiment, ai_bias,
         published_at or (_TODAY + "T00:00:00Z")),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    yield conn
    conn.close()


def test_read_per_day_fills_zeros(db):
    fid = _feed(db)
    _article(db, fid, is_read=1, read_at=_TODAY + "T10:00:00Z")
    _article(db, fid, is_read=1, read_at=_TODAY + "T11:00:00Z")
    out = articles_read_per_day(7, conn=db)
    assert len(out) == 7                       # 7 dias, com zeros
    assert out[-1] == (_TODAY, 2)              # hoje tem 2 lidos


def test_top_feeds_order(db):
    f1, f2 = _feed(db, "Mais"), _feed(db, "Menos")
    for _ in range(3):
        _article(db, f1, is_read=1)
    _article(db, f2, is_read=1)
    out = top_feeds(conn=db)
    assert out[0] == ("Mais", 3) and out[1] == ("Menos", 1)


def test_top_tags_counts_and_orders(db):
    fid = _feed(db)
    db.execute("INSERT INTO articles (feed_id, url, title, ai_tags) VALUES (?,?,?,?)",
               (fid, "https://j.com/t1", "T", '["ia", "python"]'))
    db.execute("INSERT INTO articles (feed_id, url, title, ai_tags) VALUES (?,?,?,?)",
               (fid, "https://j.com/t2", "T", '["ia"]'))
    db.commit()
    out = top_tags(conn=db)
    assert out[0] == ("ia", 2)
    assert ("python", 1) in out


def test_top_tags_ignores_invalid_json(db):
    fid = _feed(db)
    db.execute("INSERT INTO articles (feed_id, url, title, ai_tags) VALUES (?,?,?,?)",
               (fid, "https://j.com/t3", "T", "não json"))
    db.commit()
    assert top_tags(conn=db) == []


def test_totals(db):
    fid = _feed(db)
    _article(db, fid, is_read=1)
    _article(db, fid, is_read=0)
    t = totals(conn=db)
    assert t == {"total": 2, "read": 1, "unread": 1, "feeds": 1}


def test_sentiment_distribution(db):
    fid = _feed(db)
    for s in ("positivo", "positivo", "negativo"):
        _article(db, fid, ai_sentiment=s)
    assert sentiment_distribution(conn=db) == {"positivo": 2, "neutro": 0, "negativo": 1}


def test_sentiment_over_time_structure(db):
    fid = _feed(db)
    _article(db, fid, ai_sentiment="positivo", published_at=_TODAY + "T09:00:00Z")
    out = sentiment_over_time(5, conn=db)
    assert len(out) == 5
    assert out[-1]["date"] == _TODAY
    assert out[-1]["positivo"] == 1 and out[-1]["negativo"] == 0


def test_bias_balance_mean_and_label(db):
    fid = _feed(db)
    _article(db, fid, ai_bias='{"espectro":"esquerda"}')
    _article(db, fid, ai_bias='{"espectro":"centro"}')
    out = bias_balance(conn=db)
    assert out["n"] == 2
    assert out["mean"] == -1.0                 # (-2 + 0) / 2
    assert out["label"] == "centro-esquerda"
    assert out["distribution"] == {"esquerda": 1, "centro": 1}


def test_bias_balance_empty(db):
    assert bias_balance(conn=db)["mean"] is None


def test_coverage_by_entity(db):
    fid = _feed(db)
    a1, a2 = _article(db, fid), _article(db, fid)
    materialize_entity_links(a1, [{"nome": "Lula", "tipo": "pessoa"}], conn=db)
    materialize_entity_links(a2, [{"nome": "Lula", "tipo": "pessoa"}], conn=db)
    out = coverage_by_entity(conn=db)
    assert ("Lula", 2) in out
