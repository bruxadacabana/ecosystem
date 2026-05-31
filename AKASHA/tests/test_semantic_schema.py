"""
Testes de schema para Semântico 1 — tabelas page_embeddings e page_vec.

Cobre:
  - page_embeddings criada pelo init_db com todas as colunas esperadas
  - idx_page_embeddings_url existe
  - ON DELETE CASCADE: deletar crawl_pages remove page_embeddings
  - page_vec (sqlite-vec) criada por _ensure_page_vec_table quando extensão disponível
  - INSERT + KNN query em page_vec retorna resultado correto
"""
from __future__ import annotations

import asyncio
import sqlite3

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# page_embeddings — schema e CASCADE
# ---------------------------------------------------------------------------

class TestPageEmbeddingsSchema:

    def test_table_exists_after_init_db(self, db_paths):
        """page_embeddings deve existir após init_db."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='page_embeddings'"
        ).fetchone()
        con.close()
        assert row is not None, "Tabela page_embeddings não encontrada"

    def test_columns_present(self, db_paths):
        """Colunas obrigatórias devem existir em page_embeddings."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        cols = {row[1] for row in con.execute("PRAGMA table_info(page_embeddings)")}
        con.close()
        for col in ("id", "url", "model", "dim", "updated_at"):
            assert col in cols, f"Coluna '{col}' ausente em page_embeddings"

    def test_index_exists(self, db_paths):
        """idx_page_embeddings_url deve existir."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_page_embeddings_url'"
        ).fetchone()
        con.close()
        assert row is not None, "Índice idx_page_embeddings_url não encontrado"

    def _insert_crawl_page(self, con: sqlite3.Connection, url: str) -> None:
        """Helper: insere um crawl_site + crawl_page mínimos sem FK errors."""
        con.execute("PRAGMA foreign_keys = OFF")  # FKs desligadas — testamos só page_embeddings
        con.execute("INSERT OR IGNORE INTO crawl_pages (site_id, url, word_count) VALUES (0, ?, 100)", (url,))
        con.execute("PRAGMA foreign_keys = ON")

    def test_url_unique_constraint(self, db_paths):
        """Inserir URL duplicada em page_embeddings deve lançar UNIQUE constraint."""
        main_path, _ = db_paths

        con = sqlite3.connect(main_path)
        self._insert_crawl_page(con, "https://ex.com")
        con.execute("INSERT INTO page_embeddings (url) VALUES ('https://ex.com')")
        con.commit()

        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO page_embeddings (url) VALUES ('https://ex.com')")
        con.close()

    def test_cascade_delete_removes_embedding(self, db_paths):
        """Deletar entrada em crawl_pages deve remover page_embeddings via CASCADE."""
        main_path, _ = db_paths

        con = sqlite3.connect(main_path)
        self._insert_crawl_page(con, "https://cascade.example")
        con.execute("INSERT INTO page_embeddings (url) VALUES ('https://cascade.example')")
        con.commit()

        row = con.execute(
            "SELECT id FROM page_embeddings WHERE url = 'https://cascade.example'"
        ).fetchone()
        assert row is not None, "page_embeddings entry não foi criada"

        con.execute("PRAGMA foreign_keys = ON")
        con.execute("DELETE FROM crawl_pages WHERE url = 'https://cascade.example'")
        con.commit()

        row = con.execute(
            "SELECT id FROM page_embeddings WHERE url = 'https://cascade.example'"
        ).fetchone()
        con.close()
        assert row is None, "CASCADE falhou: page_embeddings não foi removida após DELETE em crawl_pages"


# ---------------------------------------------------------------------------
# page_vec — virtual table (sqlite-vec) e KNN query
# ---------------------------------------------------------------------------

class TestPageVecTable:

    def test_ensure_page_vec_creates_table(self, db_paths):
        """_ensure_page_vec_table deve criar page_vec se sqlite-vec disponível."""
        main_path, _ = db_paths

        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            pytest.skip("sqlite_vec não disponível neste ambiente")

        import services.semantic_search as _mod
        import config as _cfg

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            run(_mod._ensure_page_vec_table())
        finally:
            _cfg.DB_PATH = orig_db

        con = sqlite3.connect(main_path)
        con.enable_load_extension(True)
        import sqlite_vec as sv
        sv.load(con)
        con.enable_load_extension(False)
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='page_vec'"
        ).fetchone()
        con.close()
        assert row is not None, "page_vec não foi criada por _ensure_page_vec_table"

    def test_insert_and_knn_query(self, db_paths):
        """Inserir vetor em page_vec e recuperar via KNN deve retornar resultado."""
        main_path, _ = db_paths

        try:
            import sqlite_vec
            import numpy as np
        except ImportError:
            pytest.skip("sqlite_vec ou numpy não disponíveis")

        import services.semantic_search as _mod
        import config as _cfg

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            run(_mod._ensure_page_vec_table())
        finally:
            _cfg.DB_PATH = orig_db

        # Inserir manualmente em page_embeddings + page_vec
        import sqlite_vec as sv
        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        con.enable_load_extension(True)
        sv.load(con)
        con.enable_load_extension(False)

        con.execute(
            "INSERT OR REPLACE INTO crawl_pages (site_id, url, word_count) VALUES (0, 'https://vec.test', 100)"
        )
        cur = con.execute("INSERT INTO page_embeddings (url) VALUES ('https://vec.test')")
        emb_id = cur.lastrowid

        vec = np.ones(768, dtype=np.float32)
        embedding_bytes = sv.serialize_float32(vec.tolist())
        con.execute(
            "INSERT INTO page_vec(rowid, embedding) VALUES (?, ?)", (emb_id, embedding_bytes)
        )
        con.commit()

        # KNN query
        rows = con.execute(
            """SELECT pe.url, pv.distance
               FROM page_vec pv
               JOIN page_embeddings pe ON pe.id = pv.rowid
               WHERE pv.embedding MATCH ? AND k = 1
               ORDER BY pv.distance""",
            (embedding_bytes,)
        ).fetchall()
        con.close()

        assert len(rows) == 1
        assert rows[0][0] == "https://vec.test"
        assert rows[0][1] == pytest.approx(0.0, abs=1e-4)

    def test_cascade_removes_page_embeddings_when_crawl_page_deleted(self, db_paths):
        """Deletar crawl_pages via CASCADE deve remover page_embeddings."""
        main_path, _ = db_paths

        try:
            import sqlite_vec as sv
            import numpy as np
        except ImportError:
            pytest.skip("sqlite_vec ou numpy não disponíveis")

        import services.semantic_search as _mod
        import config as _cfg

        orig_db = _cfg.DB_PATH
        _cfg.DB_PATH = main_path
        try:
            run(_mod._ensure_page_vec_table())
        finally:
            _cfg.DB_PATH = orig_db

        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        con.enable_load_extension(True)
        sv.load(con)
        con.enable_load_extension(False)

        con.execute(
            "INSERT OR REPLACE INTO crawl_pages (site_id, url, word_count) VALUES (0, 'https://casc.vec', 80)"
        )
        cur = con.execute("INSERT INTO page_embeddings (url) VALUES ('https://casc.vec')")
        emb_id = cur.lastrowid
        vec_bytes = sv.serialize_float32(np.zeros(768, dtype=np.float32).tolist())
        con.execute("INSERT INTO page_vec(rowid, embedding) VALUES (?, ?)", (emb_id, vec_bytes))
        con.commit()

        # Confirma inserção
        rows = con.execute("SELECT rowid FROM page_vec WHERE rowid = ?", (emb_id,)).fetchall()
        assert len(rows) == 1

        # Deleta crawl_pages com FK habilitada → CASCADE remove page_embeddings
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("DELETE FROM crawl_pages WHERE url = 'https://casc.vec'")
        con.commit()

        emb = con.execute(
            "SELECT id FROM page_embeddings WHERE url = 'https://casc.vec'"
        ).fetchone()
        con.close()
        assert emb is None, "CASCADE falhou: page_embeddings não removida após DELETE em crawl_pages"
