"""
Teste de integração: operações reais de DB — inserção, FTS, cascade delete.

Usa banco em tmp_path (nunca o DB de produção). Verifica o fluxo completo:
init_db → inserir feed → inserir artigo → FTS → delete em cascata.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


def _init_and_connect(tmp_path: Path) -> sqlite3.Connection:
    import core.database as db_module

    db_file = tmp_path / "kosmos_test.db"
    with patch.object(db_module, "DB_PATH", db_file):
        db_module.init_db()

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


class TestDbIntegration:
    @pytest.fixture(autouse=True)
    def db_conn(self, tmp_path):
        self.conn = _init_and_connect(tmp_path)
        yield
        self.conn.close()

    def _add_category(self, name: str = "Tecnologia") -> int:
        self.conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _add_feed(self, name: str = "Tech Feed", url: str = "http://tech.com/rss",
                  category_id: int | None = None) -> int:
        self.conn.execute(
            "INSERT INTO feeds (name, url, feed_type, category_id) VALUES (?, ?, 'rss', ?)",
            (name, url, category_id),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _add_article(self, feed_id: int, guid: str, title: str,
                     content: str = "") -> int:
        self.conn.execute(
            "INSERT INTO articles (feed_id, guid, title, content_full) VALUES (?, ?, ?, ?)",
            (feed_id, guid, title, content),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # ── Fluxo completo ──────────────────────────────────────────────────────

    def test_full_flow_category_feed_article(self):
        cat_id  = self._add_category("Ciência")
        feed_id = self._add_feed("Science Daily", "http://sci.com/rss", cat_id)
        art_id  = self._add_article(feed_id, "sci-001", "Estudo sobre buracos negros",
                                     "Pesquisadores descobriram um buraco negro massivo.")

        art = dict(self.conn.execute(
            "SELECT * FROM articles WHERE id=?", (art_id,)
        ).fetchone())
        assert art["title"] == "Estudo sobre buracos negros"
        assert art["feed_id"] == feed_id
        assert art["is_read"] == 0

    def test_fts_search_finds_article(self):
        feed_id = self._add_feed()
        self._add_article(
            feed_id, "fts-001",
            "Machine Learning na Medicina",
            "Algoritmos de aprendizado de máquina detectam doenças precocemente.",
        )

        rows = self.conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'aprendizado'"
        ).fetchall()
        assert len(rows) >= 1

    def test_fts_search_not_found(self):
        feed_id = self._add_feed()
        self._add_article(feed_id, "fts-002", "Culinária Francesa", "Receitas tradicionais.")

        rows = self.conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'programação'"
        ).fetchall()
        assert rows == []

    def test_cascade_delete_feed_removes_articles(self):
        feed_id = self._add_feed()
        self._add_article(feed_id, "g1", "Artigo 1")
        self._add_article(feed_id, "g2", "Artigo 2")

        self.conn.execute("DELETE FROM feeds WHERE id=?", (feed_id,))
        self.conn.commit()

        count = self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        assert count == 0

    def test_tag_article_association(self):
        feed_id = self._add_feed()
        art_id  = self._add_article(feed_id, "tagged-001", "Artigo Tagueado")

        self.conn.execute("INSERT INTO tags (name, color) VALUES ('python', '#3776AB')")
        self.conn.commit()
        tag_id = self.conn.execute("SELECT id FROM tags WHERE name='python'").fetchone()[0]

        self.conn.execute(
            "INSERT INTO article_tags (article_id, tag_id) VALUES (?, ?)",
            (art_id, tag_id),
        )
        self.conn.commit()

        result = self.conn.execute(
            "SELECT t.name FROM tags t "
            "JOIN article_tags at ON at.tag_id = t.id "
            "WHERE at.article_id = ?",
            (art_id,),
        ).fetchall()
        assert len(result) == 1
        assert result[0][0] == "python"

    def test_mark_article_as_read(self):
        feed_id = self._add_feed()
        art_id  = self._add_article(feed_id, "read-001", "Para Ler")

        self.conn.execute(
            "UPDATE articles SET is_read=1, read_at=CURRENT_TIMESTAMP WHERE id=?",
            (art_id,),
        )
        self.conn.commit()

        row = dict(self.conn.execute(
            "SELECT is_read, read_at FROM articles WHERE id=?", (art_id,)
        ).fetchone())
        assert row["is_read"] == 1
        assert row["read_at"] is not None

    def test_etag_last_modified_persisted(self):
        feed_id = self._add_feed()

        self.conn.execute(
            "UPDATE feeds SET etag='W/\"abc123\"', last_modified='Thu, 22 May 2026 10:00:00 GMT' WHERE id=?",
            (feed_id,),
        )
        self.conn.commit()

        row = dict(self.conn.execute(
            "SELECT etag, last_modified FROM feeds WHERE id=?", (feed_id,)
        ).fetchone())
        assert row["etag"] == 'W/"abc123"'
        assert "2026" in row["last_modified"]

    def test_read_session_insert(self):
        feed_id = self._add_feed()
        art_id  = self._add_article(feed_id, "session-001", "Sessão Teste")

        self.conn.execute(
            "INSERT INTO read_sessions (article_id, feed_id, duration_sec) VALUES (?, ?, ?)",
            (art_id, feed_id, 120),
        )
        self.conn.commit()

        row = self.conn.execute(
            "SELECT duration_sec FROM read_sessions WHERE article_id=?", (art_id,)
        ).fetchone()
        assert row[0] == 120
