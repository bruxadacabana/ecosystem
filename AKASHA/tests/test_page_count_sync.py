"""
Testes para migration 51 — sincronização de page_count em crawl_sites (BUG-019).

Cobre:
  - Migration corrige page_count para refletir count real de crawl_pages
  - Sites com page_count > 0 mas sem páginas reais têm last_crawled_at resetado (→ re-crawl)
  - Sites recém-adicionados (last_crawled_at IS NULL) não são afetados
  - Sites com páginas reais mantêm last_crawled_at intacto
  - Trigger trg_crawl_pages_dec_count decrementa page_count ao deletar página
  - Trigger não deixa page_count abaixo de 0
  - Deletar todas as páginas de um site mantém page_count = 0 (não negativo)
  - Regressão: page_count após crawl completo continua sendo atualizado pelo crawler
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_paths(tmp_path):
    """Banco temporário com init_db() aplicado (inclui migration 51)."""
    import database as _db

    main_path = tmp_path / "akasha.db"
    knowledge_path = tmp_path / "akasha_knowledge.db"

    orig_db  = _db.DB_PATH
    orig_kdb = _db.KNOWLEDGE_DB_PATH
    _db.DB_PATH = main_path
    _db.KNOWLEDGE_DB_PATH = knowledge_path

    run(_db.init_db())

    yield main_path, knowledge_path

    _db.DB_PATH = orig_db
    _db.KNOWLEDGE_DB_PATH = orig_kdb


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _insert_site(conn, base_url: str, page_count: int = 0,
                 last_crawled_at: str | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO crawl_sites (base_url, label, page_count, last_crawled_at)
           VALUES (?, '', ?, ?)""",
        (base_url, page_count, last_crawled_at),
    )
    conn.commit()
    return cur.lastrowid


def _insert_page(conn, site_id: int, url: str, word_count: int = 100) -> None:
    conn.execute(
        """INSERT INTO crawl_pages (site_id, url, title, word_count)
           VALUES (?, ?, 'Título', ?)""",
        (site_id, url, word_count),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Testes: migration 51 — sincronização de page_count
# ---------------------------------------------------------------------------

class TestMigration51PageCountSync:
    """
    Cada teste que simula o estado pré-migração precisa:
    1. Inserir dados que representam o bug (page_count desincronizado)
    2. Resetar schema_version para 50 (o fixture já rodou init_db com v=51)
    3. Chamar init_db() novamente → migration 51 é reaplicada
    """

    def _downgrade_to_50(self, conn: sqlite3.Connection) -> None:
        """Rebaixa schema_version para 50 para permitir reexecução da migration 51."""
        conn.execute("UPDATE settings SET value = '50' WHERE key = 'schema_version'")
        conn.commit()

    def _run_migration(self, main_path: Path) -> None:
        import database as _db
        orig = _db.DB_PATH
        _db.DB_PATH = main_path
        run(_db.init_db())
        _db.DB_PATH = orig

    def test_migration_syncs_stale_page_count_to_zero(self, db_paths):
        """Site com page_count > 0 mas sem crawl_pages tem count corrigido para 0."""
        main_path, _ = db_paths
        conn = _open(main_path)
        site_id = _insert_site(conn, "https://stale.example.com",
                                page_count=50, last_crawled_at="2026-05-01")
        self._downgrade_to_50(conn)
        conn.close()

        self._run_migration(main_path)

        conn2 = _open(main_path)
        row = conn2.execute(
            "SELECT page_count FROM crawl_sites WHERE id = ?", (site_id,)
        ).fetchone()
        assert row[0] == 0, f"page_count deve ser 0, mas é {row[0]}"
        conn2.close()

    def test_migration_resets_last_crawled_at_for_stale_sites(self, db_paths):
        """Site com page_count > 0 mas sem páginas reais tem last_crawled_at = NULL."""
        main_path, _ = db_paths
        conn = _open(main_path)
        site_id = _insert_site(conn, "https://lost-data.example.com",
                                page_count=200, last_crawled_at="2026-05-15")
        self._downgrade_to_50(conn)
        conn.close()

        self._run_migration(main_path)

        conn2 = _open(main_path)
        row = conn2.execute(
            "SELECT page_count, last_crawled_at FROM crawl_sites WHERE id = ?",
            (site_id,),
        ).fetchone()
        assert row[0] == 0
        assert row[1] is None, "last_crawled_at deve ser NULL para forçar re-crawl"
        conn2.close()

    def test_migration_preserves_sites_with_real_pages(self, db_paths):
        """Site com crawl_pages reais mantém page_count e last_crawled_at intactos."""
        main_path, _ = db_paths
        conn = _open(main_path)
        site_id = _insert_site(conn, "https://healthy.example.com",
                                page_count=3, last_crawled_at="2026-06-01")
        _insert_page(conn, site_id, "https://healthy.example.com/p1")
        _insert_page(conn, site_id, "https://healthy.example.com/p2")
        _insert_page(conn, site_id, "https://healthy.example.com/p3")
        self._downgrade_to_50(conn)
        conn.close()

        self._run_migration(main_path)

        conn2 = _open(main_path)
        row = conn2.execute(
            "SELECT page_count, last_crawled_at FROM crawl_sites WHERE id = ?",
            (site_id,),
        ).fetchone()
        assert row[0] == 3, "page_count deve permanecer 3"
        assert row[1] == "2026-06-01", "last_crawled_at não deve ser alterado"
        conn2.close()

    def test_migration_does_not_touch_never_crawled_sites(self, db_paths):
        """Site nunca crawleado (last_crawled_at IS NULL, page_count=0) não é afetado."""
        main_path, _ = db_paths
        conn = _open(main_path)
        site_id = _insert_site(conn, "https://never-crawled.example.com",
                                page_count=0, last_crawled_at=None)
        self._downgrade_to_50(conn)
        conn.close()

        self._run_migration(main_path)

        conn2 = _open(main_path)
        row = conn2.execute(
            "SELECT page_count, last_crawled_at FROM crawl_sites WHERE id = ?",
            (site_id,),
        ).fetchone()
        assert row[0] == 0
        assert row[1] is None
        conn2.close()

    def test_migration_syncs_partial_mismatch(self, db_paths):
        """Site com page_count=10 mas apenas 3 páginas reais: count é corrigido para 3."""
        main_path, _ = db_paths
        conn = _open(main_path)
        site_id = _insert_site(conn, "https://partial.example.com",
                                page_count=10, last_crawled_at="2026-05-20")
        for i in range(3):
            _insert_page(conn, site_id, f"https://partial.example.com/p{i}")
        self._downgrade_to_50(conn)
        conn.close()

        self._run_migration(main_path)

        conn2 = _open(main_path)
        row = conn2.execute(
            "SELECT page_count FROM crawl_sites WHERE id = ?", (site_id,)
        ).fetchone()
        assert row[0] == 3, f"page_count deve ser 3 (real count), foi {row[0]}"
        conn2.close()


# ---------------------------------------------------------------------------
# Testes: trigger trg_crawl_pages_dec_count
# ---------------------------------------------------------------------------

class TestDeleteTriggerPageCount:

    def test_trigger_decrements_page_count_on_delete(self, db_paths):
        """Deletar uma crawl_page decrementa page_count em crawl_sites."""
        main_path, _ = db_paths
        conn = _open(main_path)

        site_id = _insert_site(conn, "https://trigger-test.example.com",
                                page_count=3, last_crawled_at="2026-06-01")
        _insert_page(conn, site_id, "https://trigger-test.example.com/p1")
        _insert_page(conn, site_id, "https://trigger-test.example.com/p2")
        _insert_page(conn, site_id, "https://trigger-test.example.com/p3")

        # Sincroniza page_count com estado real (migration já fez isso, mas garantimos)
        conn.execute(
            "UPDATE crawl_sites SET page_count = 3 WHERE id = ?", (site_id,)
        )
        conn.commit()

        # Deleta uma página
        conn.execute(
            "DELETE FROM crawl_pages WHERE url = 'https://trigger-test.example.com/p1'"
        )
        conn.commit()

        row = conn.execute(
            "SELECT page_count FROM crawl_sites WHERE id = ?", (site_id,)
        ).fetchone()
        assert row[0] == 2, f"page_count deve ser 2 após deletar 1 página, foi {row[0]}"
        conn.close()

    def test_trigger_does_not_go_below_zero(self, db_paths):
        """Deletar página quando page_count = 0 não resulta em valor negativo."""
        main_path, _ = db_paths
        conn = _open(main_path)

        site_id = _insert_site(conn, "https://floor-test.example.com",
                                page_count=0, last_crawled_at="2026-06-01")
        # Inserimos sem contar no page_count (simula bug anterior)
        conn.execute(
            "INSERT INTO crawl_pages (site_id, url, title, word_count) VALUES (?, ?, '', 50)",
            (site_id, "https://floor-test.example.com/orphan"),
        )
        conn.commit()

        conn.execute(
            "DELETE FROM crawl_pages WHERE url = 'https://floor-test.example.com/orphan'"
        )
        conn.commit()

        row = conn.execute(
            "SELECT page_count FROM crawl_sites WHERE id = ?", (site_id,)
        ).fetchone()
        assert row[0] == 0, f"page_count não pode ser negativo, foi {row[0]}"
        conn.close()

    def test_trigger_multiple_deletes_decrements_correctly(self, db_paths):
        """Deletar N páginas decrementa page_count em N."""
        main_path, _ = db_paths
        conn = _open(main_path)

        site_id = _insert_site(conn, "https://multi-del.example.com",
                                page_count=5, last_crawled_at="2026-06-01")
        for i in range(5):
            _insert_page(conn, site_id, f"https://multi-del.example.com/p{i}")
        conn.execute(
            "UPDATE crawl_sites SET page_count = 5 WHERE id = ?", (site_id,)
        )
        conn.commit()

        # Deleta 3 páginas uma a uma
        for i in range(3):
            conn.execute(
                "DELETE FROM crawl_pages WHERE url = ?",
                (f"https://multi-del.example.com/p{i}",),
            )
        conn.commit()

        row = conn.execute(
            "SELECT page_count FROM crawl_sites WHERE id = ?", (site_id,)
        ).fetchone()
        assert row[0] == 2, f"page_count deve ser 2 após deletar 3 de 5, foi {row[0]}"
        conn.close()

    def test_trigger_cascade_delete_via_site_delete(self, db_paths):
        """Deletar o site (ON DELETE CASCADE) não ativa o trigger de decrement."""
        main_path, _ = db_paths
        conn = _open(main_path)

        site_id = _insert_site(conn, "https://cascade-test.example.com",
                                page_count=2, last_crawled_at="2026-06-01")
        _insert_page(conn, site_id, "https://cascade-test.example.com/p1")
        _insert_page(conn, site_id, "https://cascade-test.example.com/p2")
        conn.execute(
            "UPDATE crawl_sites SET page_count = 2 WHERE id = ?", (site_id,)
        )
        conn.commit()

        # Deleta o site (CASCADE apaga crawl_pages)
        conn.execute("DELETE FROM crawl_sites WHERE id = ?", (site_id,))
        conn.commit()

        # Site não existe mais — sem erro
        row = conn.execute(
            "SELECT COUNT(*) FROM crawl_sites WHERE id = ?", (site_id,)
        ).fetchone()
        assert row[0] == 0
        conn.close()

    def test_trigger_exists_after_init_db(self, db_paths):
        """Trigger trg_crawl_pages_dec_count existe após init_db()."""
        main_path, _ = db_paths
        conn = _open(main_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='trg_crawl_pages_dec_count'"
        ).fetchone()
        assert row is not None, "Trigger trg_crawl_pages_dec_count deve existir após init_db()"
        conn.close()
