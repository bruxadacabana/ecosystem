"""
Testes unitários para app/core/database.py (KOSMOS v3).

Todos os testes usam bancos SQLite em tmp_path — sem tocar no DB de produção.
Cobre: schema completo, triggers FTS5, heartbeat reset, cascade deletes,
partial index, defaults, e idempotência.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_db(path: Path) -> sqlite3.Connection:
    """Abre o DB com row_factory e foreign_keys ativados."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _init_db_at(path: Path) -> None:
    """Chama init_db() redirecionando DB_PATH para path."""
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        db_module.init_db()


def _reset_stale_at(path: Path, conn: sqlite3.Connection) -> int:
    """Chama _reset_stale_analyses() e retorna rowcount."""
    import app.core.database as db_module
    with patch.object(db_module, "DB_PATH", path):
        cursor = conn.execute(
            """
            UPDATE articles
               SET analysis_status = 'pending', analysis_started_at = NULL
             WHERE analysis_status = 'running'
               AND analysis_started_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-5 minutes')
            """
        )
        conn.commit()
        return cursor.rowcount


@pytest.fixture
def db(tmp_path):
    """Fixture: banco inicializado + conexão aberta. Fecha ao final."""
    db_file = tmp_path / "kosmos_test.db"
    _init_db_at(db_file)
    conn = _open_db(db_file)
    yield db_file, conn
    conn.close()


def _insert_feed(conn: sqlite3.Connection, url: str = "http://example.com/feed",
                 title: str = "Feed Teste") -> int:
    conn.execute(
        "INSERT INTO feeds (url, title) VALUES (?, ?)", (url, title)
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_article(conn: sqlite3.Connection, feed_id: int, url: str,
                    title: str = "Artigo Teste") -> int:
    conn.execute(
        "INSERT INTO articles (feed_id, url, title) VALUES (?, ?, ?)",
        (feed_id, url, title),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ---------------------------------------------------------------------------
# init_db — estrutura básica
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
        _init_db_at(db_file)
        assert db_file.exists()

    def test_creates_all_tables(self, tmp_path):
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)
        conn = _open_db(db_file)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        conn.close()
        expected = {
            "feeds", "articles", "entities", "article_entities",
            "highlights", "investigations", "investigation_articles",
        }
        assert expected.issubset(tables), f"tabelas ausentes: {expected - tables}"

    def test_old_tables_absent(self, tmp_path):
        """Tabelas do schema v2 (categories, tags, etc.) não devem existir."""
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)
        conn = _open_db(db_file)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        conn.close()
        old = {"categories", "tags", "article_tags", "read_sessions"}
        assert old.isdisjoint(tables), f"tabelas legadas presentes: {old & tables}"

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
        triggers = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )}
        conn.close()
        expected_triggers = {
            "fts_articles_insert", "fts_articles_update", "fts_articles_delete",
        }
        assert expected_triggers.issubset(triggers), (
            f"triggers ausentes: {expected_triggers - triggers}"
        )

    def test_creates_partial_index(self, tmp_path):
        """Índice parcial para fila de análise deve existir."""
        db_file = tmp_path / "kosmos.db"
        _init_db_at(db_file)
        conn = _open_db(db_file)
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_articles_pending_analysis'"
        ).fetchone()
        conn.close()
        assert idx is not None, "partial index idx_articles_pending_analysis não criado"

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

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="chmod de diretório não restringe escrita no Windows (POSIX only)",
    )
    def test_raises_on_invalid_path(self, tmp_path):
        """Diretório sem permissão de escrita deve lançar OperationalError (POSIX only)."""
        import app.core.database as db_module
        no_write = tmp_path / "no_write" / "sub" / "kosmos.db"
        parent = tmp_path / "no_write"
        parent.mkdir()
        parent.chmod(0o444)
        try:
            with patch.object(db_module, "DB_PATH", no_write):
                with pytest.raises((sqlite3.OperationalError, OSError)):
                    db_module.init_db()
        finally:
            parent.chmod(0o755)


# ---------------------------------------------------------------------------
# Schema feeds — constraints e defaults
# ---------------------------------------------------------------------------

class TestFeedsSchema:
    def test_url_unique(self, db):
        _, conn = db
        conn.execute("INSERT INTO feeds (url) VALUES ('http://a.com/rss')")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO feeds (url) VALUES ('http://a.com/rss')")
            conn.commit()

    def test_defaults(self, db):
        _, conn = db
        conn.execute("INSERT INTO feeds (url) VALUES ('http://b.com/rss')")
        conn.commit()
        row = dict(conn.execute(
            "SELECT * FROM feeds WHERE url='http://b.com/rss'"
        ).fetchone())
        assert row["category"] == "Sem categoria"
        assert row["fetch_interval_min"] == 60
        assert row["enabled"] == 1
        assert row["error_count"] == 0
        assert row["created_at"] is not None

    def test_url_required(self, db):
        _, conn = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO feeds (title) VALUES ('Sem URL')")
            conn.commit()


# ---------------------------------------------------------------------------
# Schema articles — constraints, defaults e campos AI
# ---------------------------------------------------------------------------

class TestArticlesSchema:
    def test_url_unique(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title) VALUES (?, 'http://x.com/a', 'T')",
            (fid,),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO articles (feed_id, url, title) VALUES (?, 'http://x.com/a', 'T2')",
                (fid,),
            )
            conn.commit()

    def test_defaults(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title) VALUES (?, 'http://x.com/1', 'X')",
            (fid,),
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM articles WHERE url='http://x.com/1'").fetchone())
        assert row["is_read"] == 0
        assert row["is_saved"] == 0
        assert row["is_scraped"] == 0
        assert row["analysis_status"] == "pending"
        assert row["analysis_schema_version"] == 0
        assert row["ai_tags"] is None
        assert row["ai_sentiment"] is None
        assert row["ai_five_ws"] is None
        assert row["ai_entities"] is None
        assert row["ai_bias"] is None
        assert row["created_at"] is not None

    def test_ai_fields_json_stored_as_text(self, db):
        """Campos JSON são armazenados como TEXT e recuperados intactos."""
        import json
        _, conn = db
        fid = _insert_feed(conn)
        tags = json.dumps(["ia", "python"])
        five_ws = json.dumps({"quem": "Google", "o_que": "lança modelo"})
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, ai_tags, ai_five_ws) "
            "VALUES (?, 'http://x.com/2', 'Y', ?, ?)",
            (fid, tags, five_ws),
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM articles WHERE url='http://x.com/2'").fetchone())
        assert json.loads(row["ai_tags"]) == ["ia", "python"]
        assert json.loads(row["ai_five_ws"])["quem"] == "Google"

    def test_cascade_delete_on_feed_delete(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        _insert_article(conn, fid, "http://x.com/del")
        conn.execute("DELETE FROM feeds WHERE id = ?", (fid,))
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        assert count == 0

    def test_feed_id_required(self, db):
        _, conn = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO articles (feed_id, url, title) VALUES (999, 'http://x.com/3', 'Z')"
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Heartbeat reset
# ---------------------------------------------------------------------------

class TestHeartbeatReset:
    def test_running_stale_reset_to_pending(self, db):
        """Artigo em 'running' há >5min deve ser resetado para 'pending' no startup."""
        db_file, conn = db
        fid = _insert_feed(conn)
        # Inserir artigo com analysis_started_at no passado (10 minutos atrás)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, analysis_status, analysis_started_at) "
            "VALUES (?, 'http://x.com/stale', 'Stale', 'running', "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-10 minutes'))",
            (fid,),
        )
        conn.commit()

        # Simular o heartbeat reset que init_db() executa
        import app.core.database as db_module
        db_module._reset_stale_analyses(conn)

        row = dict(conn.execute(
            "SELECT analysis_status, analysis_started_at FROM articles WHERE url='http://x.com/stale'"
        ).fetchone())
        assert row["analysis_status"] == "pending"
        assert row["analysis_started_at"] is None

    def test_running_recent_not_reset(self, db):
        """Artigo em 'running' há < 5min não deve ser resetado."""
        _, conn = db
        fid = _insert_feed(conn)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, analysis_status, analysis_started_at) "
            "VALUES (?, 'http://x.com/recent', 'Recent', 'running', "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-1 minutes'))",
            (fid,),
        )
        conn.commit()

        import app.core.database as db_module
        db_module._reset_stale_analyses(conn)

        row = dict(conn.execute(
            "SELECT analysis_status FROM articles WHERE url='http://x.com/recent'"
        ).fetchone())
        assert row["analysis_status"] == "running"

    def test_pending_not_affected(self, db):
        """Artigos em 'pending' não devem ser tocados pelo heartbeat reset."""
        _, conn = db
        fid = _insert_feed(conn)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, analysis_status) "
            "VALUES (?, 'http://x.com/pend', 'Pending', 'pending')",
            (fid,),
        )
        conn.commit()

        import app.core.database as db_module
        db_module._reset_stale_analyses(conn)

        row = dict(conn.execute(
            "SELECT analysis_status FROM articles WHERE url='http://x.com/pend'"
        ).fetchone())
        assert row["analysis_status"] == "pending"

    def test_done_not_affected(self, db):
        """Artigos com status 'done' não devem ser tocados."""
        _, conn = db
        fid = _insert_feed(conn)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, analysis_status, analysis_started_at) "
            "VALUES (?, 'http://x.com/done', 'Done', 'done', "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-10 minutes'))",
            (fid,),
        )
        conn.commit()

        import app.core.database as db_module
        db_module._reset_stale_analyses(conn)

        row = dict(conn.execute(
            "SELECT analysis_status FROM articles WHERE url='http://x.com/done'"
        ).fetchone())
        assert row["analysis_status"] == "done"


# ---------------------------------------------------------------------------
# FTS5 — indexação e busca
# ---------------------------------------------------------------------------

class TestFts5:
    def test_indexed_on_insert(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, content_text) "
            "VALUES (?, 'http://x.com/fts1', 'Linguística Computacional', "
            "'Processamento de linguagem natural')",
            (fid,),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'linguística'"
        ).fetchall()
        assert len(rows) >= 1

    def test_searches_content_text(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, content_text) "
            "VALUES (?, 'http://x.com/fts2', 'Título Genérico', 'aprendizado por reforço')",
            (fid,),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'reforço'"
        ).fetchall()
        assert len(rows) >= 1

    def test_searches_ai_tags(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, ai_tags) "
            "VALUES (?, 'http://x.com/fts3', 'Sobre IA', '[\"machine-learning\", \"nlp\"]')",
            (fid,),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'nlp'"
        ).fetchall()
        assert len(rows) >= 1

    def test_updated_on_article_update(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        aid = _insert_article(conn, fid, "http://x.com/fts4", "Título Original")
        conn.execute(
            "UPDATE articles SET title='Título Atualizado', content_text='conteúdo novo' WHERE id=?",
            (aid,),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'atualizado'"
        ).fetchall()
        assert len(rows) >= 1

    def test_removed_on_article_delete(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        aid = _insert_article(conn, fid, "http://x.com/fts5", "Artigo Deletável")
        conn.execute("DELETE FROM articles WHERE id=?", (aid,))
        conn.commit()
        rows = conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'deletável'"
        ).fetchall()
        assert len(rows) == 0

    def test_falls_back_to_excerpt_when_no_content_text(self, db):
        """FTS5 usa content_excerpt quando content_text é NULL."""
        _, conn = db
        fid = _insert_feed(conn)
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, content_excerpt) "
            "VALUES (?, 'http://x.com/fts6', 'Título', 'trecho exclusivo do feed')",
            (fid,),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'exclusivo'"
        ).fetchall()
        assert len(rows) >= 1


# ---------------------------------------------------------------------------
# entities + article_entities
# ---------------------------------------------------------------------------

class TestEntities:
    def test_entity_unique_by_name_and_type(self, db):
        _, conn = db
        conn.execute(
            "INSERT INTO entities (name, entity_type) VALUES ('Lula', 'person')"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO entities (name, entity_type) VALUES ('Lula', 'person')"
            )
            conn.commit()

    def test_same_name_different_type_allowed(self, db):
        _, conn = db
        conn.execute("INSERT INTO entities (name, entity_type) VALUES ('Meta', 'org')")
        conn.execute("INSERT INTO entities (name, entity_type) VALUES ('Meta', 'topic')")
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE name='Meta'"
        ).fetchone()[0]
        assert count == 2

    def test_article_entity_cascade_delete_on_article(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        aid = _insert_article(conn, fid, "http://x.com/ent1")
        conn.execute("INSERT INTO entities (name) VALUES ('Pessoa X')")
        conn.commit()
        eid = conn.execute(
            "SELECT id FROM entities WHERE name='Pessoa X'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO article_entities (article_id, entity_id) VALUES (?, ?)",
            (aid, eid),
        )
        conn.commit()

        conn.execute("DELETE FROM articles WHERE id=?", (aid,))
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM article_entities").fetchone()[0]
        assert count == 0

    def test_entity_default_type(self, db):
        _, conn = db
        conn.execute("INSERT INTO entities (name) VALUES ('inteligência artificial')")
        conn.commit()
        row = dict(conn.execute(
            "SELECT entity_type FROM entities WHERE name='inteligência artificial'"
        ).fetchone())
        assert row["entity_type"] == "topic"


# ---------------------------------------------------------------------------
# highlights
# ---------------------------------------------------------------------------

class TestHighlights:
    def test_cascade_delete_on_article(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        aid = _insert_article(conn, fid, "http://x.com/hl1")
        conn.execute(
            "INSERT INTO highlights (article_id, text) VALUES (?, 'trecho importante')",
            (aid,),
        )
        conn.commit()

        conn.execute("DELETE FROM articles WHERE id=?", (aid,))
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM highlights").fetchone()[0]
        assert count == 0

    def test_default_type(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        aid = _insert_article(conn, fid, "http://x.com/hl2")
        conn.execute(
            "INSERT INTO highlights (article_id, text) VALUES (?, 'texto')",
            (aid,),
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM highlights").fetchone())
        assert row["highlight_type"] == "generic"

    def test_custom_type_stored(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        aid = _insert_article(conn, fid, "http://x.com/hl3")
        conn.execute(
            "INSERT INTO highlights (article_id, text, highlight_type) "
            "VALUES (?, 'contradição encontrada', 'contradiction')",
            (aid,),
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM highlights").fetchone())
        assert row["highlight_type"] == "contradiction"


# ---------------------------------------------------------------------------
# investigations + investigation_articles
# ---------------------------------------------------------------------------

class TestInvestigations:
    def test_investigation_created(self, db):
        _, conn = db
        conn.execute(
            "INSERT INTO investigations (name, description) VALUES ('Op. Fantasma', 'Investigação X')"
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM investigations").fetchone())
        assert row["name"] == "Op. Fantasma"
        assert row["created_at"] is not None
        assert row["updated_at"] is not None

    def test_article_added_to_investigation(self, db):
        _, conn = db
        fid = _insert_feed(conn)
        aid = _insert_article(conn, fid, "http://x.com/inv1")
        conn.execute("INSERT INTO investigations (name) VALUES ('Inv. Teste')")
        conn.commit()
        iid = conn.execute("SELECT id FROM investigations").fetchone()[0]
        conn.execute(
            "INSERT INTO investigation_articles (investigation_id, article_id) VALUES (?, ?)",
            (iid, aid),
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM investigation_articles").fetchone()[0]
        assert count == 1

    def test_cascade_delete_investigation(self, db):
        """Deletar investigação deve remover investigation_articles, mas não os artigos."""
        _, conn = db
        fid = _insert_feed(conn)
        aid = _insert_article(conn, fid, "http://x.com/inv2")
        conn.execute("INSERT INTO investigations (name) VALUES ('Inv. Deletável')")
        conn.commit()
        iid = conn.execute("SELECT id FROM investigations").fetchone()[0]
        conn.execute(
            "INSERT INTO investigation_articles (investigation_id, article_id) VALUES (?, ?)",
            (iid, aid),
        )
        conn.commit()

        conn.execute("DELETE FROM investigations WHERE id=?", (iid,))
        conn.commit()

        ia_count = conn.execute("SELECT COUNT(*) FROM investigation_articles").fetchone()[0]
        art_count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        assert ia_count == 0, "investigation_articles não foram removidos com a investigação"
        assert art_count == 1, "artigos não devem ser removidos ao deletar investigação"

    def test_cascade_delete_article_from_investigation(self, db):
        """Deletar artigo deve remover sua entrada de investigation_articles."""
        _, conn = db
        fid = _insert_feed(conn)
        aid = _insert_article(conn, fid, "http://x.com/inv3")
        conn.execute("INSERT INTO investigations (name) VALUES ('Inv. X')")
        conn.commit()
        iid = conn.execute("SELECT id FROM investigations").fetchone()[0]
        conn.execute(
            "INSERT INTO investigation_articles (investigation_id, article_id) VALUES (?, ?)",
            (iid, aid),
        )
        conn.commit()

        conn.execute("DELETE FROM articles WHERE id=?", (aid,))
        conn.commit()

        ia_count = conn.execute("SELECT COUNT(*) FROM investigation_articles").fetchone()[0]
        assert ia_count == 0


# ---------------------------------------------------------------------------
# get_conn
# ---------------------------------------------------------------------------

class TestGetConn:
    def test_returns_connection_with_row_factory(self, tmp_path):
        db_file = tmp_path / "kosmos_gc.db"
        _init_db_at(db_file)

        import app.core.database as db_module
        with patch.object(db_module, "DB_PATH", db_file):
            conn = db_module.get_conn()

        try:
            _insert_feed(conn)
            row = conn.execute("SELECT * FROM feeds").fetchone()
            assert isinstance(row, sqlite3.Row)
        finally:
            conn.close()

    def test_raises_on_missing_parent(self, tmp_path):
        import app.core.database as db_module
        bad_path = tmp_path / "nonexistent" / "db.db"
        with patch.object(db_module, "DB_PATH", bad_path):
            with pytest.raises(sqlite3.OperationalError):
                db_module.get_conn()
