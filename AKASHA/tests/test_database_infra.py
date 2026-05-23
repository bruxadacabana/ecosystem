"""
Testes de integração para AKASHA/database.py — infraestrutura de indexação.

Cobre:
  - WAL mode ativado em akasha.db e akasha_knowledge.db após init_db()
  - Acesso concorrente (reader + writer) sem SQLITE_BUSY graças ao WAL
  - FTS5 field weighting: title match > body match em local_fts (peso 10:1)
  - FTS5 field weighting: title match > content_md match em crawl_fts (peso 10:1)

Usa DBs SQLite em arquivo temporário (tmp_path do pytest).
A personal_memory.db é criada em ~/.local/share/akasha/ (efeito colateral idempotente
do init_db() — não interfere nos resultados dos testes).
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest


def run(coro):
    """Executa corrotina em event loop de teste (Python 3.12+ requer asyncio.run)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture: patches database.DB_PATH e database.KNOWLEDGE_DB_PATH
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_paths(tmp_path):
    """Substitui os caminhos de DB do módulo database por temporários e roda init_db()."""
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


# ---------------------------------------------------------------------------
# WAL mode
# ---------------------------------------------------------------------------

class TestWALMode:
    def test_akasha_db_wal_mode(self, db_paths):
        """akasha.db deve usar WAL mode após init_db()."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        row = con.execute("PRAGMA journal_mode").fetchone()
        con.close()
        assert row[0] == "wal", f"akasha.db deve estar em WAL, mas está em '{row[0]}'"

    def test_knowledge_db_wal_mode(self, db_paths):
        """akasha_knowledge.db deve usar WAL mode após init_db()."""
        _, knowledge_path = db_paths
        con = sqlite3.connect(knowledge_path)
        row = con.execute("PRAGMA journal_mode").fetchone()
        con.close()
        assert row[0] == "wal", f"akasha_knowledge.db deve estar em WAL, mas está em '{row[0]}'"

    def test_concurrent_read_write_no_busy_error(self, db_paths):
        """Reader e writer simultâneos não geram SQLITE_BUSY com WAL mode.

        Em modo DELETE (padrão): writer bloqueia readers — SQLITE_BUSY.
        Em modo WAL: readers leem a snapshot anterior enquanto o writer persiste — sem bloqueio.
        """
        main_path, _ = db_paths
        errors: list[str] = []

        async def _run_concurrent():
            import aiosqlite

            async def writer():
                try:
                    async with aiosqlite.connect(main_path) as con:
                        await con.execute(
                            "INSERT OR REPLACE INTO settings(key, value) VALUES('wal_test', '1')"
                        )
                        await asyncio.sleep(0.05)  # segura a transação aberta
                        await con.commit()
                except Exception as exc:
                    errors.append(f"writer: {exc}")

            async def reader():
                try:
                    await asyncio.sleep(0.01)  # começa enquanto writer ainda está ativo
                    async with aiosqlite.connect(main_path) as con:
                        await (await con.execute("SELECT COUNT(*) FROM settings")).fetchone()
                except Exception as exc:
                    errors.append(f"reader: {exc}")

            await asyncio.gather(writer(), reader())

        run(_run_concurrent())
        assert not errors, f"Erros em acesso concorrente: {errors}"


# ---------------------------------------------------------------------------
# FTS5 field weighting
# ---------------------------------------------------------------------------

class TestFTS5FieldWeighting:
    def test_title_match_ranks_above_body_match_local_fts(self, db_paths):
        """Em local_fts, match no título (peso 10.0) deve ranquear acima do match no corpo (peso 1.0)."""
        main_path, _ = db_paths
        term = "termoexclusivo7391"

        con = sqlite3.connect(main_path)
        # Doc A: term apenas no título
        con.execute(
            "INSERT INTO local_fts(path, title, body, source) VALUES (?, ?, ?, ?)",
            ("/a", f"estudo sobre {term} avançado", "texto comum sem o termo aqui", "test"),
        )
        # Doc B: term apenas no corpo
        con.execute(
            "INSERT INTO local_fts(path, title, body, source) VALUES (?, ?, ?, ?)",
            ("/b", "artigo de revisão bibliográfica", f"análise detalhada de {term} no contexto histórico", "test"),
        )
        con.commit()

        rows = con.execute(
            "SELECT path FROM local_fts WHERE local_fts MATCH ? ORDER BY rank",
            (term,),
        ).fetchall()
        con.close()

        paths = [r[0] for r in rows]
        assert len(paths) == 2, f"Esperava 2 resultados FTS, obteve {len(paths)}"
        assert paths[0] == "/a", (
            f"Título (peso 10.0) deve preceder corpo (peso 1.0). Ordem obtida: {paths}"
        )

    def test_title_match_ranks_above_content_crawl_fts(self, db_paths):
        """Em crawl_fts, match no título (peso 10.0) deve ranquear acima de match em content_md (peso 1.0)."""
        main_path, _ = db_paths
        term = "termoexclusivo8502"

        con = sqlite3.connect(main_path)
        # Doc A: term apenas no título
        con.execute(
            "INSERT INTO crawl_fts(site_id, url, title, content_md) VALUES (?, ?, ?, ?)",
            ("1", "https://exemplo.com/a", f"guia sobre {term}", "texto comum sem o termo"),
        )
        # Doc B: term apenas em content_md
        con.execute(
            "INSERT INTO crawl_fts(site_id, url, title, content_md) VALUES (?, ?, ?, ?)",
            ("1", "https://exemplo.com/b", "referência técnica geral", f"seção detalhada sobre {term} no texto"),
        )
        con.commit()

        rows = con.execute(
            "SELECT url FROM crawl_fts WHERE crawl_fts MATCH ? ORDER BY rank",
            (term,),
        ).fetchall()
        con.close()

        urls = [r[0] for r in rows]
        assert len(urls) == 2, f"Esperava 2 resultados FTS, obteve {len(urls)}"
        assert urls[0] == "https://exemplo.com/a", (
            f"Título (peso 10.0) deve preceder content_md (peso 1.0). Ordem obtida: {urls}"
        )

    def test_bm25_rank_config_persists_in_local_fts(self, db_paths):
        """A configuração bm25(0, 10.0, 1.0, 0) deve estar registrada na metadata da local_fts."""
        main_path, _ = db_paths
        con = sqlite3.connect(main_path)
        # FTS5 armazena config na tabela %_config acessível via INSERT especial
        # A forma portável de verificar é checar a tabela sqlite_master para a instrução
        # de rank config, que ficou persistida via "INSERT INTO local_fts(local_fts, rank)"
        row = con.execute(
            "SELECT v FROM local_fts_config WHERE k = 'rank'"
        ).fetchone()
        con.close()
        assert row is not None, "Configuração de rank não encontrada em local_fts_config"
        assert "10.0" in row[0], f"Peso 10.0 não encontrado na config de rank: {row[0]}"
        assert "1.0" in row[0], f"Peso 1.0 não encontrado na config de rank: {row[0]}"


# ---------------------------------------------------------------------------
# Regressão: init_db() em banco pré-v44 (search_cache sem query_hash)
# ---------------------------------------------------------------------------

class TestSearchCacheQueryHashMigration:
    """Regressão para bug: init_db() falhava com 'no such column: query_hash'
    em bancos criados antes da versão 44 do schema.

    Causa: _CREATE_IDX_SEARCH_CACHE_HASH tentava criar índice em query_hash
    antes da migração v44 adicionar a coluna via ALTER TABLE.
    """

    def test_init_db_succeeds_on_pre_v44_database(self, tmp_path):
        """init_db() não deve lançar exceção em banco existente sem query_hash."""
        import database as _db

        main_path = tmp_path / "akasha_old.db"
        knowledge_path = tmp_path / "akasha_knowledge.db"

        # Simula banco pré-v44: search_cache sem query_hash, cached_at, ttl_hours
        con = sqlite3.connect(main_path)
        con.execute("""
            CREATE TABLE search_cache (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                query        TEXT    NOT NULL,
                sources      TEXT    NOT NULL DEFAULT 'web',
                results_json TEXT    NOT NULL,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        # schema_version ausente → init_db trata como versão 0 → aplica todas as migrações
        con.commit()
        con.close()

        orig_db  = _db.DB_PATH
        orig_kdb = _db.KNOWLEDGE_DB_PATH
        _db.DB_PATH = main_path
        _db.KNOWLEDGE_DB_PATH = knowledge_path
        try:
            # Não deve lançar OperationalError: no such column: query_hash
            run(_db.init_db())
        finally:
            _db.DB_PATH = orig_db
            _db.KNOWLEDGE_DB_PATH = orig_kdb

        # Verifica que a migração adicionou query_hash e criou o índice
        con = sqlite3.connect(main_path)
        cols = [row[1] for row in con.execute("PRAGMA table_info(search_cache)").fetchall()]
        assert "query_hash" in cols, "Coluna query_hash deve existir após migração v44"
        indices = [row[1] for row in con.execute(
            "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='search_cache'"
        ).fetchall()]
        assert any("hash" in idx for idx in indices), (
            f"Índice idx_search_cache_hash deve existir. Índices encontrados: {indices}"
        )
        con.close()

    def test_init_db_succeeds_on_fresh_database(self, tmp_path):
        """init_db() em banco novo (sem tabelas) também não deve falhar."""
        import database as _db

        orig_db  = _db.DB_PATH
        orig_kdb = _db.KNOWLEDGE_DB_PATH
        _db.DB_PATH = tmp_path / "akasha_fresh.db"
        _db.KNOWLEDGE_DB_PATH = tmp_path / "akasha_knowledge.db"
        try:
            run(_db.init_db())
        finally:
            _db.DB_PATH = orig_db
            _db.KNOWLEDGE_DB_PATH = orig_kdb
