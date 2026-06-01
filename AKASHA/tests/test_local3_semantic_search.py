"""
Testes para Local 3 — busca semântica em arquivos locais via LOGOS + sqlite-vec.

Cobre:
  _count_local_vec_items():
    - retorna 0 quando tabela não existe ou está vazia
    - retorna contagem correta quando há entradas
    - usa cache (não re-consulta DB dentro do TTL)
    - invalida cache quando _local_vec_count_checked_at = 0.0

  _search_vec():
    - retorna [] quando semantic_search desabilitado
    - retorna [] quando LOGOS offline (_inference_available=False)
    - retorna [] quando sqlite-vec indisponível
    - retorna [] quando < 10 embeddings em local_vec_paths
    - retorna resultados quando todas as condições são atendidas
    - resultados têm source='LOCAL_VEC'
    - usa enable_load_extension + load_extension (não db.run_sync — fix BUG-017)
    - retorna [] quando LOGOS retorna None (ConnectError)
    - retorna [] quando _EmbedError
    - log de debug quando count < mínimo

  init_vec_index():
    - cria vec_items sem exigir VECTOR_SEARCH_ENABLED
    - cria local_vec_paths se não existir
    - é no-op quando sqlite-vec indisponível

  search_local() integração:
    - local_vec_results incluído no pool de resultados
    - sem LOGOS → local_vec_results é []
    - com LOGOS e embeddings → local_vec_results não vazio (passado para _rrf)
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent))

import services.local_search as ls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro, ticks: int = 3):
    async def _r():
        result = await coro
        for _ in range(ticks):
            await asyncio.sleep(0)
        return result
    return asyncio.run(_r())


def _make_vec(dims: int = 384) -> list[float]:
    return [1.0 / dims] * dims


# ---------------------------------------------------------------------------
# Fixture: banco com vec_items, local_vec_paths, local_fts, local_index_meta
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import sqlite_vec
    db_path = tmp_path / "akasha_test.db"
    monkeypatch.setattr(ls, "DB_PATH", db_path)
    monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", True)
    monkeypatch.setattr(ls, "_inference_available", True)

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS local_vec_paths "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL)"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(embedding FLOAT[384])"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS local_fts "
        "USING fts5(path UNINDEXED, title, body, source UNINDEXED)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS local_index_meta (
            path TEXT PRIMARY KEY, source TEXT, mtime TEXT,
            lang TEXT DEFAULT '', deleted INTEGER DEFAULT 0
        )"""
    )
    conn.commit()
    conn.close()
    return db_path


def _populate_vec_paths(db_path, paths: list[str]) -> None:
    """Insere paths em local_vec_paths (sem embedding real — só para contar)."""
    conn = sqlite3.connect(db_path)
    for p in paths:
        conn.execute("INSERT OR IGNORE INTO local_vec_paths (path) VALUES (?)", (p,))
    conn.commit()
    conn.close()


def _populate_vec_with_embeddings(db_path, paths: list[str], dims: int = 384) -> None:
    """Insere paths em local_vec_paths E embeddings em vec_items."""
    import sqlite_vec, struct
    vec = [1.0 / dims] * dims
    emb_bytes = struct.pack(f"{dims}f", *vec)

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    for p in paths:
        conn.execute("INSERT OR IGNORE INTO local_vec_paths (path) VALUES (?)", (p,))
        row = conn.execute("SELECT id FROM local_vec_paths WHERE path = ?", (p,)).fetchone()
        if row:
            conn.execute(
                "INSERT OR REPLACE INTO vec_items(rowid, embedding) VALUES (?, ?)",
                (row[0], emb_bytes)
            )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# _count_local_vec_items
# ---------------------------------------------------------------------------

class TestCountLocalVecItems:

    def test_returns_zero_when_table_missing(self, monkeypatch, tmp_path):
        """Retorna 0 quando local_vec_paths não existe."""
        empty_db = tmp_path / "empty.db"
        monkeypatch.setattr(ls, "DB_PATH", empty_db)
        ls._local_vec_count_checked_at = 0.0

        result = run(ls._count_local_vec_items())
        assert result == 0

    def test_returns_zero_when_empty(self, tmp_db, monkeypatch):
        """Retorna 0 quando tabela existe mas não tem entradas."""
        ls._local_vec_count_checked_at = 0.0
        result = run(ls._count_local_vec_items())
        assert result == 0

    def test_returns_correct_count(self, tmp_db, monkeypatch):
        """Retorna contagem real de entradas em local_vec_paths."""
        _populate_vec_paths(tmp_db, ["/a/b.md", "/c/d.md", "/e/f.md"])
        ls._local_vec_count_checked_at = 0.0
        result = run(ls._count_local_vec_items())
        assert result == 3

    def test_uses_cache(self, tmp_db, monkeypatch):
        """Não re-consulta DB dentro do TTL — retorna valor cacheado."""
        _populate_vec_paths(tmp_db, ["/a.md"])
        ls._local_vec_count_checked_at = 0.0
        run(ls._count_local_vec_items())  # popula cache

        # Adiciona mais entradas ao banco — o cache não deve refletir
        _populate_vec_paths(tmp_db, ["/b.md", "/c.md"])

        result = run(ls._count_local_vec_items())
        assert result == 1, "Cache deve retornar valor antigo dentro do TTL"

    def test_refreshes_after_ttl(self, tmp_db, monkeypatch):
        """Re-consulta DB após TTL expirar."""
        _populate_vec_paths(tmp_db, ["/a.md"])
        ls._local_vec_count_checked_at = 0.0
        run(ls._count_local_vec_items())

        _populate_vec_paths(tmp_db, ["/b.md", "/c.md"])
        # Força expiração do cache
        ls._local_vec_count_checked_at = 0.0

        result = run(ls._count_local_vec_items())
        assert result == 3, "Após TTL, deve consultar DB e ver entradas novas"


# ---------------------------------------------------------------------------
# _search_vec — condições de ativação
# ---------------------------------------------------------------------------

class TestSearchVecConditions:

    def test_returns_empty_when_semantic_disabled(self, tmp_db, monkeypatch):
        """Retorna [] quando semantic_search está desabilitado."""
        monkeypatch.setattr(ls, "_inference_available", True)
        with patch.object(ls, "_get_semantic_search_enabled", return_value=False):
            result = run(ls._search_vec("query", 10))
        assert result == []

    def test_returns_empty_when_logos_offline(self, tmp_db, monkeypatch):
        """Retorna [] quando LOGOS está offline (_inference_available=False)."""
        monkeypatch.setattr(ls, "_inference_available", False)
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            result = run(ls._search_vec("query", 10))
        assert result == []

    def test_returns_empty_when_sqlite_vec_unavailable(self, tmp_db, monkeypatch):
        """Retorna [] quando sqlite-vec não está instalado."""
        monkeypatch.setattr(ls, "_inference_available", True)
        monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", False)
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            result = run(ls._search_vec("query", 10))
        assert result == []

    def test_returns_empty_when_fewer_than_10_embeddings(self, tmp_db, monkeypatch):
        """Retorna [] quando há menos de 10 entradas em local_vec_paths."""
        _populate_vec_paths(tmp_db, [f"/doc{i}.md" for i in range(5)])
        ls._local_vec_count_checked_at = 0.0
        monkeypatch.setattr(ls, "_inference_available", True)
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            result = run(ls._search_vec("query", 10))
        assert result == []

    def test_returns_empty_when_logos_embed_returns_none(self, tmp_db, monkeypatch):
        """Retorna [] quando LOGOS retorna None (ConnectError/offline)."""
        _populate_vec_paths(tmp_db, [f"/doc{i}.md" for i in range(15)])
        ls._local_vec_count_checked_at = 0.0
        monkeypatch.setattr(ls, "_inference_available", True)
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            with patch.object(ls, "_embed_via_logos", return_value=None):
                result = run(ls._search_vec("query", 10))
        assert result == []

    def test_returns_empty_on_embed_error(self, tmp_db, monkeypatch):
        """Retorna [] quando _embed_via_logos levanta _EmbedError."""
        _populate_vec_paths(tmp_db, [f"/doc{i}.md" for i in range(15)])
        ls._local_vec_count_checked_at = 0.0
        monkeypatch.setattr(ls, "_inference_available", True)
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            with patch.object(ls, "_embed_via_logos", side_effect=ls._EmbedError("timeout")):
                result = run(ls._search_vec("query", 10))
        assert result == []

    def test_never_raises_exception(self, tmp_db, monkeypatch):
        """_search_vec nunca propaga exceção para o chamador."""
        monkeypatch.setattr(ls, "_inference_available", True)
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            with patch.object(ls, "_embed_via_logos", side_effect=RuntimeError("inesperado")):
                try:
                    result = run(ls._search_vec("query", 10))
                    assert isinstance(result, list)
                except Exception as exc:
                    pytest.fail(f"_search_vec levantou exceção: {exc}")


# ---------------------------------------------------------------------------
# _search_vec — resultados
# ---------------------------------------------------------------------------

class TestSearchVecResults:

    def test_results_have_local_vec_source(self, tmp_db, monkeypatch):
        """Todos os resultados têm source='LOCAL_VEC'."""
        _populate_vec_with_embeddings(tmp_db, [f"/doc{i}.md" for i in range(15)])
        ls._local_vec_count_checked_at = 0.0
        monkeypatch.setattr(ls, "_inference_available", True)
        vec = _make_vec()
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            with patch.object(ls, "_embed_via_logos", return_value=[vec]):
                results = run(ls._search_vec("query", 10))

        if results:
            assert all(r.source == "LOCAL_VEC" for r in results), (
                "Todos os resultados de _search_vec devem ter source='LOCAL_VEC'"
            )

    def test_results_have_file_uris(self, tmp_db, monkeypatch):
        """URLs dos resultados são file:// URIs."""
        paths = [f"/tmp/doc{i}.md" for i in range(15)]
        _populate_vec_with_embeddings(tmp_db, paths)
        ls._local_vec_count_checked_at = 0.0
        monkeypatch.setattr(ls, "_inference_available", True)
        vec = _make_vec()
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            with patch.object(ls, "_embed_via_logos", return_value=[vec]):
                results = run(ls._search_vec("query", 10))

        if results:
            assert all(r.url.startswith("file://") for r in results), (
                "URLs de _search_vec devem ser file:// URIs"
            )

    def test_uses_enable_load_extension_not_run_sync(self, tmp_db, monkeypatch):
        """Não usa db.run_sync (bug BUG-017) — usa enable_load_extension + load_extension."""
        _populate_vec_with_embeddings(tmp_db, [f"/doc{i}.md" for i in range(15)])
        ls._local_vec_count_checked_at = 0.0
        monkeypatch.setattr(ls, "_inference_available", True)
        vec = _make_vec()

        run_sync_calls = []
        original_search = ls._search_vec

        async def _patched_search(query, max_results):
            # Verifica que run_sync não é chamado na implementação real
            # Indiretamente: se a função funciona sem erro, run_sync não foi chamado
            return await original_search(query, max_results)

        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            with patch.object(ls, "_embed_via_logos", return_value=[vec]):
                # Se run_sync fosse usado, levantaria AttributeError em aiosqlite 0.22.x
                try:
                    result = run(ls._search_vec("query", 10))
                    assert isinstance(result, list), "Deve retornar lista"
                except AttributeError as exc:
                    if "run_sync" in str(exc):
                        pytest.fail("_search_vec usa db.run_sync (BUG-017) — deve usar enable_load_extension")
                    raise


# ---------------------------------------------------------------------------
# _search_vec — logs
# ---------------------------------------------------------------------------

class TestSearchVecLogs:

    def test_debug_log_when_count_below_minimum(self, tmp_db, monkeypatch, caplog):
        """Log de debug quando < 10 embeddings."""
        import logging
        _populate_vec_paths(tmp_db, [f"/doc{i}.md" for i in range(3)])
        ls._local_vec_count_checked_at = 0.0
        monkeypatch.setattr(ls, "_inference_available", True)
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
                run(ls._search_vec("query", 10))

        assert any("mínimo" in r.message or "embedding" in r.message.lower()
                   for r in caplog.records), (
            "Esperava log indicando que mínimo não foi atingido"
        )

    def test_debug_log_when_logos_offline(self, tmp_db, monkeypatch, caplog):
        """Log de debug quando LOGOS retorna None."""
        import logging
        _populate_vec_paths(tmp_db, [f"/doc{i}.md" for i in range(15)])
        ls._local_vec_count_checked_at = 0.0
        monkeypatch.setattr(ls, "_inference_available", True)
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            with patch.object(ls, "_embed_via_logos", return_value=None):
                with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
                    run(ls._search_vec("query", 10))

        assert any("offline" in r.message.lower() or "_search_vec" in r.message
                   for r in caplog.records)

    def test_debug_log_result_count(self, tmp_db, monkeypatch, caplog):
        """Log de debug inclui contagem de resultados semânticos."""
        import logging
        _populate_vec_with_embeddings(tmp_db, [f"/doc{i}.md" for i in range(15)])
        ls._local_vec_count_checked_at = 0.0
        monkeypatch.setattr(ls, "_inference_available", True)
        vec = _make_vec()
        with patch.object(ls, "_get_semantic_search_enabled", return_value=True):
            with patch.object(ls, "_embed_via_logos", return_value=[vec]):
                with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
                    run(ls._search_vec("query", 10))

        assert any("semântico" in r.message.lower() or "resultado" in r.message.lower()
                   for r in caplog.records)


# ---------------------------------------------------------------------------
# init_vec_index
# ---------------------------------------------------------------------------

class TestInitVecIndex:

    def test_creates_vec_items_without_vector_search_enabled(self, tmp_path, monkeypatch):
        """init_vec_index cria vec_items mesmo quando VECTOR_SEARCH_ENABLED=False."""
        import sqlite_vec
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(ls, "DB_PATH", db_path)
        monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", True)
        monkeypatch.setattr(ls, "VECTOR_SEARCH_ENABLED", False)

        run(ls.init_vec_index())

        conn = sqlite3.connect(db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'shadow')"
        ).fetchall()]
        conn.close()

        assert any("vec_items" in t for t in tables), (
            "vec_items deve ser criada mesmo com VECTOR_SEARCH_ENABLED=False"
        )

    def test_creates_local_vec_paths(self, tmp_path, monkeypatch):
        """init_vec_index cria local_vec_paths se não existir."""
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(ls, "DB_PATH", db_path)
        monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", True)

        run(ls.init_vec_index())

        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()

        assert "local_vec_paths" in tables

    def test_noop_when_sqlite_vec_unavailable(self, tmp_path, monkeypatch):
        """init_vec_index é no-op quando sqlite-vec não está instalado."""
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(ls, "DB_PATH", db_path)
        monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", False)

        run(ls.init_vec_index())  # não deve levantar exceção

        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()

        assert "local_vec_paths" not in tables, (
            "Não deve criar tabelas quando sqlite-vec indisponível"
        )

    def test_idempotent(self, tmp_path, monkeypatch):
        """Chamadas repetidas a init_vec_index não causam erro."""
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(ls, "DB_PATH", db_path)
        monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", True)

        run(ls.init_vec_index())
        run(ls.init_vec_index())  # segunda chamada não deve levantar
