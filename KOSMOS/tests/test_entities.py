"""
Testes de app/core/entities.py — ponte e consultas do rastreador (Fase 7, item 2).

Cobre: parse_entities; materialize (upsert, dedup, religa, mapeamento de tipo);
backfill; list_entities (contagem/ordem); timeline (newest-first); sentimento e
feeds acumulados; notas; e a sobrevivência do vínculo ao TTL (ai_entities NULL).
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.core.entities import (
    backfill_entity_links,
    get_entity_feed_breakdown,
    get_entity_sentiment_breakdown,
    get_entity_timeline,
    list_entities,
    materialize_entity_links,
    parse_entities,
    set_entity_notes,
)

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


def _article(conn, fid, *, title="T", published_at="2026-06-01T00:00:00Z",
             ai_sentiment=None, ai_entities=None) -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, published_at, ai_sentiment, ai_entities) "
        "VALUES (?,?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", title, published_at, ai_sentiment, ai_entities),
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


# ---------------------------------------------------------------------------
# parse_entities
# ---------------------------------------------------------------------------

class TestParseEntities:
    def test_valid(self):
        out = parse_entities('[{"nome":"Lula","tipo":"pessoa"},{"nome":"Brasil","tipo":"lugar"}]')
        assert out == [{"nome": "Lula", "tipo": "pessoa"}, {"nome": "Brasil", "tipo": "lugar"}]

    def test_invalid_and_empty(self):
        assert parse_entities("não json") == []
        assert parse_entities(None) == []
        assert parse_entities('{"x":1}') == []          # não-lista

    def test_skips_without_nome(self):
        assert parse_entities('[{"tipo":"tema"},{"nome":"X"}]') == [{"nome": "X", "tipo": ""}]


# ---------------------------------------------------------------------------
# materialize_entity_links
# ---------------------------------------------------------------------------

class TestMaterialize:
    def test_creates_entities_and_links(self, db):
        fid = _feed(db)
        aid = _article(db, fid)
        n = materialize_entity_links(aid, [{"nome": "Lula", "tipo": "pessoa"},
                                           {"nome": "STF", "tipo": "organizacao"}], conn=db)
        assert n == 2
        ents = db.execute("SELECT name, entity_type FROM entities ORDER BY name").fetchall()
        assert (ents[0]["name"], ents[0]["entity_type"]) == ("Lula", "person")
        assert (ents[1]["name"], ents[1]["entity_type"]) == ("STF", "org")
        links = db.execute("SELECT COUNT(*) c FROM article_entities WHERE article_id=?", (aid,)).fetchone()
        assert links["c"] == 2

    def test_dedups_entity_across_articles(self, db):
        fid = _feed(db)
        a1, a2 = _article(db, fid), _article(db, fid)
        materialize_entity_links(a1, [{"nome": "Lula", "tipo": "pessoa"}], conn=db)
        materialize_entity_links(a2, [{"nome": "Lula", "tipo": "pessoa"}], conn=db)
        cnt = db.execute("SELECT COUNT(*) c FROM entities WHERE name='Lula'").fetchone()["c"]
        assert cnt == 1   # mesma entidade reutilizada

    def test_rematerialize_replaces_links(self, db):
        fid = _feed(db)
        aid = _article(db, fid)
        materialize_entity_links(aid, [{"nome": "A", "tipo": "tema"}], conn=db)
        materialize_entity_links(aid, [{"nome": "B", "tipo": "tema"}], conn=db)  # re-análise
        rows = db.execute(
            "SELECT e.name FROM article_entities ae JOIN entities e ON e.id=ae.entity_id "
            "WHERE ae.article_id=?", (aid,)).fetchall()
        assert [r["name"] for r in rows] == ["B"]   # vínculo antigo removido

    def test_type_mapping_default_topic(self, db):
        fid = _feed(db)
        aid = _article(db, fid)
        materialize_entity_links(aid, [{"nome": "X", "tipo": "coisa-desconhecida"}], conn=db)
        t = db.execute("SELECT entity_type FROM entities WHERE name='X'").fetchone()["entity_type"]
        assert t == "topic"


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------

def test_backfill_processes_articles_with_entities(db):
    fid = _feed(db)
    _article(db, fid, ai_entities='[{"nome":"Lula","tipo":"pessoa"}]')
    _article(db, fid, ai_entities='[{"nome":"STF","tipo":"org"}]')
    _article(db, fid, ai_entities=None)   # ignorado
    n = backfill_entity_links(conn=db)
    assert n == 2
    assert db.execute("SELECT COUNT(*) c FROM entities").fetchone()["c"] == 2


# ---------------------------------------------------------------------------
# consultas
# ---------------------------------------------------------------------------

class TestQueries:
    def test_list_entities_count_and_order(self, db):
        fid = _feed(db)
        a1, a2 = _article(db, fid), _article(db, fid)
        materialize_entity_links(a1, [{"nome": "Pop", "tipo": "tema"}, {"nome": "Raro", "tipo": "tema"}], conn=db)
        materialize_entity_links(a2, [{"nome": "Pop", "tipo": "tema"}], conn=db)
        out = list_entities(db)
        assert out[0]["name"] == "Pop" and out[0]["article_count"] == 2   # mais coberta primeiro
        assert out[1]["name"] == "Raro" and out[1]["article_count"] == 1

    def test_timeline_newest_first(self, db):
        fid = _feed(db, "F1")
        old = _article(db, fid, title="Velho", published_at="2026-01-01T00:00:00Z", ai_sentiment="neutro")
        new = _article(db, fid, title="Novo", published_at="2026-06-01T00:00:00Z", ai_sentiment="positivo")
        for aid in (old, new):
            materialize_entity_links(aid, [{"nome": "E", "tipo": "tema"}], conn=db)
        eid = db.execute("SELECT id FROM entities WHERE name='E'").fetchone()["id"]
        tl = get_entity_timeline(eid, db)
        assert [a["title"] for a in tl] == ["Novo", "Velho"]
        assert tl[0]["ai_sentiment"] == "positivo" and tl[0]["feed"] == "F1"

    def test_sentiment_breakdown(self, db):
        fid = _feed(db)
        for s in ("positivo", "positivo", "negativo"):
            aid = _article(db, fid, ai_sentiment=s)
            materialize_entity_links(aid, [{"nome": "E", "tipo": "tema"}], conn=db)
        eid = db.execute("SELECT id FROM entities WHERE name='E'").fetchone()["id"]
        assert get_entity_sentiment_breakdown(eid, db) == {"positivo": 2, "negativo": 1}

    def test_feed_breakdown_desc(self, db):
        f1, f2 = _feed(db, "Mais"), _feed(db, "Menos")
        for _ in range(3):
            materialize_entity_links(_article(db, f1), [{"nome": "E", "tipo": "tema"}], conn=db)
        materialize_entity_links(_article(db, f2), [{"nome": "E", "tipo": "tema"}], conn=db)
        eid = db.execute("SELECT id FROM entities WHERE name='E'").fetchone()["id"]
        fb = get_entity_feed_breakdown(eid, db)
        assert fb[0] == {"feed": "Mais", "n": 3}
        assert fb[1] == {"feed": "Menos", "n": 1}

    def test_notes_roundtrip(self, db):
        fid = _feed(db)
        materialize_entity_links(_article(db, fid), [{"nome": "E", "tipo": "tema"}], conn=db)
        eid = db.execute("SELECT id FROM entities WHERE name='E'").fetchone()["id"]
        assert set_entity_notes(eid, "minha nota", conn=db) is True
        assert db.execute("SELECT notes FROM entities WHERE id=?", (eid,)).fetchone()["notes"] == "minha nota"

    def test_link_survives_ttl_null(self, db):
        # O vínculo materializado persiste mesmo após o TTL zerar ai_entities.
        fid = _feed(db)
        aid = _article(db, fid, title="Antigo", ai_entities='[{"nome":"E","tipo":"tema"}]')
        materialize_entity_links(aid, [{"nome": "E", "tipo": "tema"}], conn=db)
        db.execute("UPDATE articles SET ai_entities=NULL WHERE id=?", (aid,))  # TTL
        db.commit()
        eid = db.execute("SELECT id FROM entities WHERE name='E'").fetchone()["id"]
        assert len(get_entity_timeline(eid, db)) == 1   # timeline ainda completa
