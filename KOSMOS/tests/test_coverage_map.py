"""
Testes do mapa de cobertura (Fase 7, item 4).

Cobre:
  - get_entity_coverage: janela de dias; feeds ativos (≥1 artigo) como linhas;
    contagem por (feed, dia); feed ativo sem menção aparece sem contagem (silêncio);
    artigo fora da janela é ignorado.
  - CoverageMap (view): estado vazio sem entidades; grade feed×dia com dimensões
    corretas; célula reflete a contagem.

get_entity_coverage / list_entities abrem conexão própria — passamos a conexão de
teste (DB_PATH não é alterado permanentemente).
"""
from __future__ import annotations

import itertools
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401  (garante program files no sys.path)
import pytest

from app.core.entities import get_entity_coverage, materialize_entity_links

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


def _article(conn, fid, *, day: str, ai_entities=None) -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, published_at, ai_entities) VALUES (?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", "T", f"{day}T12:00:00Z", ai_entities),
    )
    conn.commit()
    return cur.lastrowid


def _entity_id(conn, name="Lula") -> int:
    return conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()[0]


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    yield conn
    conn.close()


def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


# ---------------------------------------------------------------------------
# get_entity_coverage
# ---------------------------------------------------------------------------

class TestGetEntityCoverage:
    def test_window_length_and_today_last(self, db):
        cov = get_entity_coverage(1, days=7, conn=db)
        assert len(cov["days"]) == 7
        assert cov["days"][-1] == _today()      # hoje é a última coluna
        assert cov["days"][0] == _days_ago(6)   # mais antigo primeiro

    def test_counts_mention_by_feed_day(self, db):
        fid = _feed(db, "Jornal A")
        ents = '[{"nome":"Lula","tipo":"pessoa"}]'
        aid = _article(db, fid, day=_today(), ai_entities=ents)
        materialize_entity_links(aid, [{"nome": "Lula", "tipo": "pessoa"}], conn=db)
        eid = _entity_id(db, "Lula")

        cov = get_entity_coverage(eid, days=14, conn=db)
        assert {"id": fid, "title": "Jornal A"} in cov["feeds"]
        assert cov["counts"][(fid, _today())] == 1

    def test_active_feed_without_mention_is_silent(self, db):
        # Feed B publica (artigo qualquer) mas nunca menciona a entidade → linha zerada
        fa = _feed(db, "A")
        fb = _feed(db, "B")
        aid = _article(db, fa, day=_today(), ai_entities='[{"nome":"X","tipo":"tema"}]')
        materialize_entity_links(aid, [{"nome": "X", "tipo": "tema"}], conn=db)
        _article(db, fb, day=_today())  # B ativo, sem menção
        eid = _entity_id(db, "X")

        cov = get_entity_coverage(eid, days=14, conn=db)
        feed_ids = {f["id"] for f in cov["feeds"]}
        assert fa in feed_ids and fb in feed_ids        # ambos ativos = linhas
        assert (fb, _today()) not in cov["counts"]      # B em silêncio

    def test_article_outside_window_ignored(self, db):
        fid = _feed(db, "A")
        old = _article(db, fid, day=_days_ago(40), ai_entities='[{"nome":"Y","tipo":"tema"}]')
        materialize_entity_links(old, [{"nome": "Y", "tipo": "tema"}], conn=db)
        eid = _entity_id(db, "Y")

        cov = get_entity_coverage(eid, days=14, conn=db)
        assert cov["counts"] == {}                       # fora da janela
        assert cov["feeds"] == []                        # nenhum feed ativo na janela

    def test_two_mentions_same_day(self, db):
        fid = _feed(db, "A")
        for _ in range(2):
            aid = _article(db, fid, day=_today(), ai_entities='[{"nome":"Z","tipo":"tema"}]')
            materialize_entity_links(aid, [{"nome": "Z", "tipo": "tema"}], conn=db)
        eid = _entity_id(db, "Z")
        cov = get_entity_coverage(eid, days=14, conn=db)
        assert cov["counts"][(fid, _today())] == 2


# ---------------------------------------------------------------------------
# CoverageMap (view)
# ---------------------------------------------------------------------------

class TestCoverageMapView:
    def test_empty_state_without_entities(self, db, qapp):
        from app.ui.views.coverage_map import CoverageMap
        view = CoverageMap()
        view.reload(conn=db)
        assert not view._info.isHidden()          # aviso de vazio visível
        assert view._entity_combo.count() == 0

    def test_grid_dimensions_and_cell(self, db, qapp):
        from app.ui.views.coverage_map import CoverageMap
        fid = _feed(db, "Jornal A")
        aid = _article(db, fid, day=_today(), ai_entities='[{"nome":"Lula","tipo":"pessoa"}]')
        materialize_entity_links(aid, [{"nome": "Lula", "tipo": "pessoa"}], conn=db)

        view = CoverageMap()
        view.reload(conn=db)

        assert view._entity_combo.count() == 1
        assert view._table.columnCount() == 14          # janela padrão
        assert view._table.rowCount() == 1              # 1 feed ativo
        # última coluna = hoje → célula deve mostrar "1"
        cell = view._table.item(0, 13)
        assert cell is not None and cell.text() == "1"
