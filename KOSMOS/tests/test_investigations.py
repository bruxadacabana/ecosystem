"""
Testes de app/core/investigations.py — pastas de investigação (Fase 7, item 3).

Cobre: criar (nome vazio → None); listar (contagem + ordem por updated_at);
descrição/rename; add/remove artigo (idempotência); get_articles (cronológico, com
nota); nota por artigo; delete (cascade); export_dossier (estrutura do .md).
"""
from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path
from unittest.mock import patch

import app.utils.paths  # noqa: F401
import pytest

from app.core.investigations import (
    add_article,
    create_investigation,
    delete_investigation,
    export_dossier,
    get_articles,
    list_investigations,
    remove_article,
    rename_investigation,
    set_article_note,
    set_description,
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


def _article(conn, fid, *, title="T", published_at="2026-06-01T00:00:00Z",
             ai_sentiment=None, ai_summary=None) -> int:
    cur = conn.execute(
        "INSERT INTO articles (feed_id, url, title, published_at, ai_sentiment, ai_summary) "
        "VALUES (?,?,?,?,?,?)",
        (fid, f"https://j.com/a{next(_counter)}", title, published_at, ai_sentiment, ai_summary),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    cur = conn.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("https://f.com/rss", "Feed X"))
    conn.commit()
    yield conn, cur.lastrowid
    conn.close()


# ---------------------------------------------------------------------------
# criar / listar
# ---------------------------------------------------------------------------

def test_create_returns_id(db):
    conn, _ = db
    assert create_investigation("Caso A", "desc", conn=conn) is not None

def test_create_empty_name_none(db):
    conn, _ = db
    assert create_investigation("   ", conn=conn) is None

def test_list_counts(db):
    conn, fid = db
    inv = create_investigation("Inv", conn=conn)
    add_article(inv, _article(conn, fid), conn=conn)
    add_article(inv, _article(conn, fid), conn=conn)
    rows = list_investigations(conn)
    assert rows[0]["article_count"] == 2

def test_list_order_by_updated(db):
    conn, _ = db
    a = create_investigation("A", conn=conn)
    create_investigation("B", conn=conn)
    conn.execute("UPDATE investigations SET updated_at='2099-01-01T00:00:00Z' WHERE id=?", (a,))
    conn.commit()
    assert list_investigations(conn)[0]["name"] == "A"   # atualizada mais recente primeiro


# ---------------------------------------------------------------------------
# descrição / rename / delete
# ---------------------------------------------------------------------------

def test_set_description(db):
    conn, _ = db
    inv = create_investigation("X", conn=conn)
    assert set_description(inv, "novas notas", conn=conn) is True
    assert list_investigations(conn)[0]["description"] == "novas notas"

def test_rename(db):
    conn, _ = db
    inv = create_investigation("Velho", conn=conn)
    assert rename_investigation(inv, "Novo", conn=conn) is True
    assert list_investigations(conn)[0]["name"] == "Novo"
    assert rename_investigation(inv, "  ", conn=conn) is False

def test_delete_cascades_links(db):
    conn, fid = db
    inv = create_investigation("X", conn=conn)
    add_article(inv, _article(conn, fid), conn=conn)
    delete_investigation(inv, conn=conn)
    assert list_investigations(conn) == []
    assert conn.execute("SELECT COUNT(*) c FROM investigation_articles").fetchone()["c"] == 0


# ---------------------------------------------------------------------------
# artigos
# ---------------------------------------------------------------------------

def test_add_article_idempotent(db):
    conn, fid = db
    inv = create_investigation("X", conn=conn)
    aid = _article(conn, fid)
    assert add_article(inv, aid, conn=conn) is True
    assert add_article(inv, aid, conn=conn) is False   # já estava

def test_remove_article(db):
    conn, fid = db
    inv = create_investigation("X", conn=conn)
    aid = _article(conn, fid)
    add_article(inv, aid, conn=conn)
    remove_article(inv, aid, conn=conn)
    assert get_articles(inv, conn=conn) == []

def test_get_articles_chronological_with_note(db):
    conn, fid = db
    inv = create_investigation("X", conn=conn)
    new = _article(conn, fid, title="Novo", published_at="2026-06-01T00:00:00Z")
    old = _article(conn, fid, title="Velho", published_at="2026-01-01T00:00:00Z")
    add_article(inv, new, conn=conn)
    add_article(inv, old, conn=conn)
    set_article_note(inv, old, "minha nota", conn=conn)
    arts = get_articles(inv, conn=conn)
    assert [a["title"] for a in arts] == ["Velho", "Novo"]    # cronológico (asc)
    assert arts[0]["note"] == "minha nota"
    assert arts[0]["feed"] == "Feed X"


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_export_dossier_structure(db):
    conn, fid = db
    inv = create_investigation("Caso Teste", "Resumo da investigação.", conn=conn)
    a1 = _article(conn, fid, title="Primeiro fato", published_at="2026-01-01T00:00:00Z",
                  ai_sentiment="negativo", ai_summary="Sumário um.")
    a2 = _article(conn, fid, title="Segundo fato", published_at="2026-02-01T00:00:00Z")
    add_article(inv, a1, conn=conn)
    add_article(inv, a2, conn=conn)
    set_article_note(inv, a1, "fonte confiável", conn=conn)
    md = export_dossier(inv, conn=conn)
    assert md.startswith("# Caso Teste")
    assert "Resumo da investigação." in md
    assert "### Primeiro fato" in md and "### Segundo fato" in md
    assert "fonte confiável" in md and "Sumário um." in md
    assert "negativo" in md
    # ordem cronológica: primeiro fato antes do segundo
    assert md.index("Primeiro fato") < md.index("Segundo fato")

def test_export_missing_returns_none(db):
    conn, _ = db
    assert export_dossier(99999, conn=conn) is None
