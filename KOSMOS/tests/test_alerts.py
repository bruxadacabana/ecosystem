"""
Testes de alertas de palavras-chave e entidades (Fase 7, item 6).

Cobre:
  - alerts core: add (idempotente por UNIQUE), list (label da entidade), remove,
    is_entity_alerted; get_alerted_article_ids (keyword em título/resumo, entidade,
    combinado, sem alertas).
  - AlertsView: reload popula keywords + entidades (checkáveis); adicionar keyword;
    toggle de entidade vira alerta.
  - ArticleList: card ganha _alerted=True quando o artigo casa com um alerta.

DB_PATH é apontado para o tmp (monkeypatch), então get_conn das mutações da UI atinge
o banco de teste.
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path

import app.utils.paths  # noqa: F401
import pytest

from app.core.alerts import (
    add_alert,
    get_alerted_article_ids,
    is_entity_alerted,
    list_alerts,
    remove_alert,
)
from app.core.entities import materialize_entity_links

_counter = itertools.count()


@pytest.fixture
def db(tmp_path, monkeypatch):
    import app.core.database as db_module
    path = tmp_path / "kosmos_test.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    db_module.init_db()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _feed(conn) -> int:
    cur = conn.execute("INSERT INTO feeds (url, title) VALUES (?, ?)",
                       (f"https://f{next(_counter)}.com/rss", "Feed"))
    conn.commit()
    return cur.lastrowid


def _article(conn, fid, *, title="T", excerpt=None, entities=None) -> int:
    ai_entities = None
    if entities:
        import json
        ai_entities = json.dumps(entities)
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, content_excerpt, ai_entities) VALUES (?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", title, excerpt, ai_entities),
    )
    conn.commit()
    aid = cur.lastrowid
    if entities:
        materialize_entity_links(aid, entities, conn=conn)
    return aid


def _eid(conn, name) -> int:
    return conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()[0]


# ---------------------------------------------------------------------------
# core/alerts
# ---------------------------------------------------------------------------

class TestAlertsCore:
    def test_add_and_list(self, db):
        assert add_alert("keyword", "reforma", conn=db) is True
        kinds = [(a["kind"], a["term"]) for a in list_alerts(db)]
        assert ("keyword", "reforma") in kinds

    def test_add_idempotent(self, db):
        assert add_alert("keyword", "x", conn=db) is True
        assert add_alert("keyword", "x", conn=db) is False
        assert sum(1 for a in list_alerts(db) if a["term"] == "x") == 1

    def test_invalid_ignored(self, db):
        assert add_alert("bogus", "x", conn=db) is False
        assert add_alert("keyword", "  ", conn=db) is False

    def test_remove(self, db):
        add_alert("keyword", "y", conn=db)
        assert remove_alert("keyword", "y", conn=db) is True
        assert all(a["term"] != "y" for a in list_alerts(db))

    def test_entity_alert_label_and_check(self, db):
        fid = _feed(db)
        _article(db, fid, entities=[{"nome": "Lula", "tipo": "pessoa"}])
        eid = _eid(db, "Lula")
        add_alert("entity", str(eid), conn=db)
        assert is_entity_alerted(eid, conn=db) is True
        assert is_entity_alerted(eid + 999, conn=db) is False
        labels = [a["label"] for a in list_alerts(db) if a["kind"] == "entity"]
        assert "Lula" in labels


# ---------------------------------------------------------------------------
# get_alerted_article_ids
# ---------------------------------------------------------------------------

class TestAlertedArticleIds:
    def test_keyword_in_title(self, db):
        fid = _feed(db)
        aid = _article(db, fid, title="Reforma tributária aprovada")
        add_alert("keyword", "reforma", conn=db)
        assert aid in get_alerted_article_ids(db)

    def test_keyword_in_excerpt(self, db):
        fid = _feed(db)
        aid = _article(db, fid, title="Notícia", excerpt="texto sobre amigurumi e crochê")
        add_alert("keyword", "amigurumi", conn=db)
        assert aid in get_alerted_article_ids(db)

    def test_entity_match(self, db):
        fid = _feed(db)
        aid = _article(db, fid, entities=[{"nome": "STF", "tipo": "org"}])
        add_alert("entity", str(_eid(db, "STF")), conn=db)
        assert aid in get_alerted_article_ids(db)

    def test_no_alerts_empty(self, db):
        fid = _feed(db)
        _article(db, fid, title="qualquer")
        assert get_alerted_article_ids(db) == set()

    def test_non_matching_excluded(self, db):
        fid = _feed(db)
        aid = _article(db, fid, title="sobre gatos")
        add_alert("keyword", "cachorro", conn=db)
        assert aid not in get_alerted_article_ids(db)


# ---------------------------------------------------------------------------
# AlertsView
# ---------------------------------------------------------------------------

class TestAlertsView:
    def test_reload_populates(self, db, qapp):
        from PySide6.QtCore import Qt
        from app.ui.views.alerts_view import AlertsView
        fid = _feed(db)
        _article(db, fid, entities=[{"nome": "Lula", "tipo": "pessoa"}])
        add_alert("keyword", "reforma", conn=db)
        view = AlertsView()
        view.reload(conn=db)
        assert view._kw_list.count() == 1
        assert view._entity_list.count() == 1
        assert view._entity_list.item(0).checkState() == Qt.CheckState.Unchecked

    def test_add_keyword(self, db, qapp):
        from app.ui.views.alerts_view import AlertsView
        view = AlertsView()
        view.reload(conn=db)
        view._kw_edit.setText("eleições")
        view._on_add_keyword()
        terms = [a["term"] for a in list_alerts(db) if a["kind"] == "keyword"]
        assert "eleições" in terms

    def test_entity_toggle_creates_alert(self, db, qapp):
        from PySide6.QtCore import Qt
        from app.ui.views.alerts_view import AlertsView
        fid = _feed(db)
        _article(db, fid, entities=[{"nome": "STF", "tipo": "org"}])
        eid = _eid(db, "STF")
        view = AlertsView()
        view.reload(conn=db)
        view._entity_list.item(0).setCheckState(Qt.CheckState.Checked)  # dispara itemChanged
        assert is_entity_alerted(eid, conn=db) is True


# ---------------------------------------------------------------------------
# ArticleList — destaque do card
# ---------------------------------------------------------------------------

def test_article_card_alerted(db, qapp):
    from app.ui.views.article_list import ArticleList
    fid = _feed(db)
    aid = _article(db, fid, title="Reforma tributária")
    add_alert("keyword", "reforma", conn=db)

    lst = ArticleList()
    lst.load_articles(conn=db)

    # localiza o card do artigo e confere o destaque
    found = False
    for i in range(lst._list.count()):
        item = lst._list.item(i)
        if item.data(0x0100) == aid:  # Qt.UserRole
            card = lst._list.itemWidget(item)
            assert card._alerted is True
            assert card._title_lbl.text().startswith("🔔")
            found = True
            break
    assert found
