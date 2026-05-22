"""
Testes unitários para app/core/database.py.

Todos os testes usam bancos SQLite in-memory ou em tmp_path — sem tocar no
DB de produção em ~/.local/share/kosmos/.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_db(path: Path) -> sqlite3.Connection:
    """Abre o DB em path com row_factory e foreign keys ativados."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _init_db_at(path: Path) -> None:
    """Chama init_db() redirecionando DB_PATH para path."""
    import core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


# ---------------------------------------------------------------------------
# init_db — criação de schema
# ---------------------------------------------------------------------------

class TestInitDb:
    def test_creates_file(self, tmp_path):
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)
        assert db_file.exists()

    def test_idempotent(self, tmp_path):
        """Chamar init_db duas vezes não deve falhar."""
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)
        _init_db_at(db_file)  # segunda chamada — idempotente
        assert db_file.exists()

    def test_creates_all_tables(self, tmp_path):
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)

        conn = _open_db(db_file)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        conn.close()

        expected = {"categories", "feeds", "articles", "tags", "article_tags", "read_sessions"}
        assert expected.issubset(tables), f"tabelas ausentes: {expected - tables}"

    def test_creates_fts5_table(self, tmp_path):
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)

        conn = _open_db(db_file)
        fts = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fts_articles'"
        ).fetchone()
        conn.close()

        assert fts is not None, "tabela FTS5 fts_articles não criada"

    def test_creates_fts_triggers(self, tmp_path):
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)

        conn = _open_db(db_file)
        triggers = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        conn.close()

        expected_triggers = {
            "fts_articles_insert",
            "fts_articles_update",
            "fts_articles_delete",
        }
        assert expected_triggers.issubset(triggers), (
            f"triggers ausentes: {expected_triggers - triggers}"
        )

    def test_wal_mode(self, tmp_path):
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)

        conn = _open_db(db_file)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()

        assert mode == "wal"

    def test_foreign_keys_on(self, tmp_path):
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)

        conn = _open_db(db_file)
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()

        assert fk == 1

    def test_raises_on_invalid_path(self, tmp_path):
        """Diretório sem permissão de escrita deve lançar OperationalError."""
        import core.database as db_module

        no_write = tmp_path / "no_write" / "sub" / "kosmos.db"
        # Cria o diretório pai somente-leitura (simula erro de permissão)
        parent = tmp_path / "no_write"
        parent.mkdir()
        parent.chmod(0o444)

        try:
            with patch.object(db_module, "DB_PATH", no_write):
                with pytest.raises((sqlite3.OperationalError, OSError)):
                    db_module.init_db()
        finally:
            parent.chmod(0o755)  # restaura para não travar cleanup do tmp_path


# ---------------------------------------------------------------------------
# Schema — constraints e tipos
# ---------------------------------------------------------------------------

class TestSchema:
    @pytest.fixture(autouse=True)
    def db(self, tmp_path):
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)
        self.conn = _open_db(db_file)
        yield
        self.conn.close()

    def _insert_feed(self, name: str = "Feed Teste", url: str = "http://example.com/feed") -> int:
        self.conn.execute(
            "INSERT INTO feeds (name, url, feed_type) VALUES (?, ?, 'rss')",
            (name, url),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def test_article_guid_unique_per_feed(self):
        feed_id = self._insert_feed()
        self.conn.execute(
            "INSERT INTO articles (feed_id, guid, title) VALUES (?, 'g1', 'Artigo A')",
            (feed_id,),
        )
        self.conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO articles (feed_id, guid, title) VALUES (?, 'g1', 'Artigo B')",
                (feed_id,),
            )
            self.conn.commit()

    def test_same_guid_different_feeds_allowed(self):
        feed1 = self._insert_feed("F1", "http://f1.com/rss")
        feed2 = self._insert_feed("F2", "http://f2.com/rss")

        self.conn.execute(
            "INSERT INTO articles (feed_id, guid, title) VALUES (?, 'guid_dup', 'T1')",
            (feed1,),
        )
        self.conn.execute(
            "INSERT INTO articles (feed_id, guid, title) VALUES (?, 'guid_dup', 'T2')",
            (feed2,),
        )
        self.conn.commit()

        count = self.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE guid='guid_dup'"
        ).fetchone()[0]
        assert count == 2

    def test_cascade_delete_articles_on_feed_delete(self):
        feed_id = self._insert_feed()
        self.conn.execute(
            "INSERT INTO articles (feed_id, guid, title) VALUES (?, 'g1', 'A')",
            (feed_id,),
        )
        self.conn.commit()

        self.conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
        self.conn.commit()

        count = self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        assert count == 0

    def test_article_defaults(self):
        feed_id = self._insert_feed()
        self.conn.execute(
            "INSERT INTO articles (feed_id, guid, title) VALUES (?, 'g_def', 'Título')",
            (feed_id,),
        )
        self.conn.commit()

        row = dict(
            self.conn.execute("SELECT * FROM articles WHERE guid='g_def'").fetchone()
        )
        assert row["is_read"] == 0
        assert row["is_saved"] == 0
        assert row["is_clickbait"] == 0
        assert row["scrape_status"] == "none"
        assert row["integrity"] == "unknown"

    def test_fts_indexed_on_insert(self):
        feed_id = self._insert_feed()
        self.conn.execute(
            "INSERT INTO articles (feed_id, guid, title, content_full) "
            "VALUES (?, 'fts1', 'Linguística Computacional', 'Processamento de linguagem natural')",
            (feed_id,),
        )
        self.conn.commit()

        rows = self.conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'linguística'"
        ).fetchall()
        assert len(rows) >= 1

    def test_fts_updated_on_article_update(self):
        feed_id = self._insert_feed()
        self.conn.execute(
            "INSERT INTO articles (feed_id, guid, title, content_full) "
            "VALUES (?, 'fts2', 'Título Original', 'conteúdo original aqui')",
            (feed_id,),
        )
        self.conn.commit()
        article_id = self.conn.execute(
            "SELECT id FROM articles WHERE guid='fts2'"
        ).fetchone()[0]

        self.conn.execute(
            "UPDATE articles SET title='Título Atualizado', content_full='conteúdo atualizado aqui' WHERE id=?",
            (article_id,),
        )
        self.conn.commit()

        rows = self.conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'atualizado'"
        ).fetchall()
        assert len(rows) >= 1

    def test_fts_removed_on_article_delete(self):
        feed_id = self._insert_feed()
        self.conn.execute(
            "INSERT INTO articles (feed_id, guid, title) VALUES (?, 'fts3', 'Artigo Deletável')",
            (feed_id,),
        )
        self.conn.commit()
        article_id = self.conn.execute(
            "SELECT id FROM articles WHERE guid='fts3'"
        ).fetchone()[0]

        self.conn.execute("DELETE FROM articles WHERE id=?", (article_id,))
        self.conn.commit()

        rows = self.conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'Deletável'"
        ).fetchall()
        assert len(rows) == 0
