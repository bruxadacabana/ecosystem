"""
Testes da comparação de enquadramento (Fase 7, item 5).

Cobre:
  - get_entity_framing: agrupa por espectro político (ai_bias.espectro); contagem,
    sentimento, entidades co-citadas e manchetes por espectro; ai_bias ausente →
    'indefinido'; ordem canônica esquerda→direita; entidade sem artigos → {}.
  - FramingView (view): estado vazio sem entidades; uma coluna por espectro presente.

get_entity_framing / list_entities abrem conexão própria — passamos a de teste.
"""
from __future__ import annotations

import itertools
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.core.entities import get_entity_framing, materialize_entity_links

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


def _article(conn, fid, *, title="T", espectro=None, sentiment=None, entities=None) -> int:
    ai_bias = json.dumps({"espectro": espectro}) if espectro is not None else None
    ai_entities = json.dumps(entities) if entities else None
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, published_at, ai_sentiment, ai_bias, ai_entities) "
        "VALUES (?,?,?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", title, "2026-06-01T00:00:00Z",
         sentiment, ai_bias, ai_entities),
    )
    conn.commit()
    aid = cur.lastrowid
    if entities:
        materialize_entity_links(aid, entities, conn=conn)
    return aid


def _eid(conn, name) -> int:
    return conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()[0]


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    yield conn
    conn.close()


_LULA = [{"nome": "Lula", "tipo": "pessoa"}]


# ---------------------------------------------------------------------------
# get_entity_framing
# ---------------------------------------------------------------------------

class TestGetEntityFraming:
    def test_groups_by_spectrum(self, db):
        fa = _feed(db, "Esq")
        fb = _feed(db, "Dir")
        _article(db, fa, espectro="esquerda", sentiment="positivo", entities=_LULA)
        _article(db, fb, espectro="direita", sentiment="negativo", entities=_LULA)
        fr = get_entity_framing(_eid(db, "Lula"), conn=db)
        assert set(fr.keys()) == {"esquerda", "direita"}
        assert fr["esquerda"]["count"] == 1
        assert fr["esquerda"]["sentiment"]["positivo"] == 1
        assert fr["direita"]["sentiment"]["negativo"] == 1

    def test_missing_bias_is_indefinido(self, db):
        fa = _feed(db)
        _article(db, fa, espectro=None, entities=_LULA)  # sem ai_bias
        fr = get_entity_framing(_eid(db, "Lula"), conn=db)
        assert "indefinido" in fr
        assert fr["indefinido"]["count"] == 1

    def test_canonical_order(self, db):
        fa = _feed(db)
        _article(db, fa, espectro="direita", entities=_LULA)
        _article(db, fa, espectro="esquerda", entities=_LULA)
        _article(db, fa, espectro="centro", entities=_LULA)
        fr = get_entity_framing(_eid(db, "Lula"), conn=db)
        assert list(fr.keys()) == ["esquerda", "centro", "direita"]

    def test_co_entities_per_spectrum(self, db):
        fa = _feed(db)
        _article(db, fa, espectro="esquerda",
                 entities=[{"nome": "Lula", "tipo": "pessoa"}, {"nome": "STF", "tipo": "org"}])
        fr = get_entity_framing(_eid(db, "Lula"), conn=db)
        co_names = [n for n, _c in fr["esquerda"]["co_entities"]]
        assert "STF" in co_names

    def test_headlines_present(self, db):
        fa = _feed(db, "Jornal")
        _article(db, fa, title="Manchete X", espectro="centro", entities=_LULA)
        fr = get_entity_framing(_eid(db, "Lula"), conn=db)
        titles = [h["title"] for h in fr["centro"]["headlines"]]
        assert "Manchete X" in titles

    def test_entity_without_articles(self, db):
        # entidade existe mas sem vínculos → {}
        db.execute("INSERT INTO entities (name, entity_type) VALUES (?, ?)", ("Solo", "topic"))
        db.commit()
        assert get_entity_framing(_eid(db, "Solo"), conn=db) == {}


# ---------------------------------------------------------------------------
# FramingView
# ---------------------------------------------------------------------------

class TestFramingView:
    def test_empty_state_without_entities(self, db, qapp):
        from app.ui.views.framing_view import FramingView
        view = FramingView()
        view.reload(conn=db)
        assert not view._info.isHidden()
        assert view._entity_combo.count() == 0

    def test_one_column_per_spectrum(self, db, qapp):
        from app.ui.views.framing_view import FramingView
        fa = _feed(db, "A")
        _article(db, fa, espectro="esquerda", entities=_LULA)
        _article(db, fa, espectro="direita", entities=_LULA)

        view = FramingView()
        view.reload(conn=db)

        assert view._entity_combo.count() == 1
        # 2 espectros presentes → 2 colunas
        assert len(view._columns) == 2
