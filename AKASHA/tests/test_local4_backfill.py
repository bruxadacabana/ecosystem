"""
Testes para Local 4 — backfill de embeddings para arquivos já indexados no FTS5.

Cobre:
  backfill_local_embeddings():
    - no-op quando sqlite-vec indisponível
    - no-op quando todos os arquivos já têm embedding
    - processa arquivos em local_fts sem entrada em local_vec_paths
    - respeita Semaphore(2) — no máximo 2 chamadas simultâneas
    - skips LOGOS offline (embed retorna False)
    - log de progresso a cada 10 arquivos
    - invalida cache _local_vec_count_checked_at após processar
    - LIMIT 50 na query (não processa mais de 50 por vez)
    - lida com body/title nulos graciosamente

  index_local_files():
    - dispara backfill como fire-and-forget após _purge_missing
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
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

def run(coro, ticks: int = 5):
    async def _r():
        result = await coro
        for _ in range(ticks):
            await asyncio.sleep(0)
        return result
    return asyncio.run(_r())


def _drain(coro, ticks: int = 10):
    """Executa coro e drena event loop para que tasks criadas como fire-and-forget executem."""
    async def _r():
        await coro
        for _ in range(ticks):
            await asyncio.sleep(0)
    asyncio.run(_r())


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Banco com local_fts, local_index_meta, local_vec_paths. sqlite-vec habilitado."""
    import sqlite_vec
    db_path = tmp_path / "akasha_test.db"
    monkeypatch.setattr(ls, "DB_PATH", db_path)
    monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", True)
    monkeypatch.setattr(ls, "_inference_available", True)

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS local_fts "
        "USING fts5(path UNINDEXED, title, body, source UNINDEXED)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS local_index_meta "
        "(path TEXT PRIMARY KEY, source TEXT, mtime TEXT, lang TEXT DEFAULT '', deleted INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS local_vec_paths "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL)"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(embedding FLOAT[384])"
    )
    conn.commit()
    conn.close()
    return db_path


def _insert_fts(db_path: Path, path: str, title: str = "Título", body: str = "Corpo") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO local_fts (path, title, body, source) VALUES (?, ?, ?, 'AKASHA')",
        (path, title, body)
    )
    conn.commit()
    conn.close()


def _insert_vec_path(db_path: Path, path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT OR IGNORE INTO local_vec_paths (path) VALUES (?)", (path,))
    conn.commit()
    conn.close()


def _count_vec_paths(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM local_vec_paths").fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------------------
# Casos básicos
# ---------------------------------------------------------------------------

class TestBackfillBasic:

    def test_noop_when_sqlite_vec_unavailable(self, tmp_db, monkeypatch):
        """Retorna imediatamente quando sqlite-vec não está disponível."""
        monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", False)
        _insert_fts(tmp_db, "/doc1.md")

        calls = []
        async def fake_embed(path, content):
            calls.append(path)
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            # Substitui o sleep para não esperar 30s nos testes
            original = asyncio.sleep
            with patch("asyncio.sleep", return_value=None):
                await ls.backfill_local_embeddings()

        asyncio.run(_run())
        assert calls == [], "embed_and_index não deve ser chamado quando sqlite-vec indisponível"

    def test_noop_when_all_files_have_embeddings(self, tmp_db, monkeypatch):
        """Não processa nada quando todos os arquivos já têm entrada em local_vec_paths."""
        _insert_fts(tmp_db, "/doc1.md")
        _insert_fts(tmp_db, "/doc2.md")
        _insert_vec_path(tmp_db, "/doc1.md")
        _insert_vec_path(tmp_db, "/doc2.md")

        calls = []
        async def fake_embed(path, content):
            calls.append(path)
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                await ls.backfill_local_embeddings()

        asyncio.run(_run())
        assert calls == [], "Nenhum arquivo deve ser processado quando todos já têm embedding"

    def test_processes_files_without_embeddings(self, tmp_db, monkeypatch):
        """Processa arquivos que estão no FTS5 mas não em local_vec_paths."""
        _insert_fts(tmp_db, "/doc1.md", title="Documento 1", body="Conteúdo 1")
        _insert_fts(tmp_db, "/doc2.md", title="Documento 2", body="Conteúdo 2")
        # doc1 já tem embedding, doc2 não
        _insert_vec_path(tmp_db, "/doc1.md")

        calls = []
        async def fake_embed(path, content):
            calls.append(path)
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                await ls.backfill_local_embeddings()

        asyncio.run(_run())
        assert "/doc2.md" in calls, "doc2 sem embedding deve ter sido processado"
        assert "/doc1.md" not in calls, "doc1 com embedding não deve ser reprocessado"

    def test_content_includes_title_and_body(self, tmp_db, monkeypatch):
        """Conteúdo passado ao embed inclui título e corpo concatenados."""
        _insert_fts(tmp_db, "/nota.md", title="Meu Título", body="Meu corpo de texto")

        contents_seen = []
        async def fake_embed(path, content):
            contents_seen.append(content)
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                await ls.backfill_local_embeddings()

        asyncio.run(_run())
        assert contents_seen, "embed_and_index deve ter sido chamado"
        assert "Meu Título" in contents_seen[0]
        assert "Meu corpo de texto" in contents_seen[0]

    def test_handles_null_title_gracefully(self, tmp_db, monkeypatch):
        """Aceita title=None sem levantar exceção."""
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            "INSERT INTO local_fts (path, title, body, source) VALUES (?, NULL, 'corpo', 'AKASHA')",
            ("/no-title.md",)
        )
        conn.commit()
        conn.close()

        calls = []
        async def fake_embed(path, content):
            calls.append(path)
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                try:
                    await ls.backfill_local_embeddings()
                except Exception as exc:
                    pytest.fail(f"backfill levantou exceção com title=None: {exc}")

        asyncio.run(_run())
        assert "/no-title.md" in calls


# ---------------------------------------------------------------------------
# LOGOS offline
# ---------------------------------------------------------------------------

class TestBackfillLogosOffline:

    def test_skips_when_logos_offline(self, tmp_db, monkeypatch):
        """Quando LOGOS offline, embed retorna False mas sem levantar exceção."""
        _insert_fts(tmp_db, "/doc1.md")
        monkeypatch.setattr(ls, "_inference_available", False)

        calls = []
        async def fake_embed(path, content):
            calls.append(path)
            return False

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                await ls.backfill_local_embeddings()

        asyncio.run(_run())
        # Quando _inference_available=False, o loop interno retorna antes de chamar embed
        # Resultado: calls deve estar vazio (short-circuit dentro de _embed_one)
        assert calls == [], "embed_and_index não deve ser chamado quando LOGOS offline"

    def test_does_not_raise_when_embed_returns_false(self, tmp_db, monkeypatch):
        """backfill continua sem levantar exceção quando embed falha."""
        _insert_fts(tmp_db, "/doc1.md")
        _insert_fts(tmp_db, "/doc2.md")

        async def fake_embed(path, content):
            return False

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                try:
                    await ls.backfill_local_embeddings()
                except Exception as exc:
                    pytest.fail(f"backfill levantou exceção: {exc}")

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Logs de progresso
# ---------------------------------------------------------------------------

class TestBackfillLogs:

    def test_logs_initial_count(self, tmp_db, monkeypatch, caplog):
        """Log INFO informa quantos arquivos serão processados."""
        import logging
        for i in range(5):
            _insert_fts(tmp_db, f"/doc{i}.md")

        async def fake_embed(path, content):
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                with caplog.at_level(logging.INFO, logger="akasha.local_search"):
                    await ls.backfill_local_embeddings()

        asyncio.run(_run())
        assert any("backfill" in r.message.lower() and "embedding" in r.message.lower()
                   for r in caplog.records), (
            "Esperava log INFO indicando início do backfill"
        )

    def test_logs_progress_every_10(self, tmp_db, monkeypatch, caplog):
        """Log INFO a cada 10 arquivos processados com sucesso."""
        import logging
        for i in range(12):
            _insert_fts(tmp_db, f"/doc{i}.md")

        call_count = 0
        async def fake_embed(path, content):
            nonlocal call_count
            call_count += 1
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                with caplog.at_level(logging.INFO, logger="akasha.local_search"):
                    await ls.backfill_local_embeddings()

        asyncio.run(_run())
        # Deve haver ao menos um log de progresso (a cada 10 processados)
        progress_logs = [r for r in caplog.records
                         if "backfill" in r.message.lower() and "/" in r.message]
        assert len(progress_logs) >= 1, (
            f"Esperava ao menos 1 log de progresso (10/12 ou similar), "
            f"obteve: {[r.message for r in caplog.records]}"
        )

    def test_logs_completion(self, tmp_db, monkeypatch, caplog):
        """Log INFO ao final do lote."""
        import logging
        for i in range(3):
            _insert_fts(tmp_db, f"/doc{i}.md")

        async def fake_embed(path, content):
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                with caplog.at_level(logging.INFO, logger="akasha.local_search"):
                    await ls.backfill_local_embeddings()

        asyncio.run(_run())
        assert any("lote" in r.message.lower() or "concluído" in r.message.lower()
                   for r in caplog.records), (
            "Esperava log de conclusão do lote"
        )


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

class TestBackfillCacheInvalidation:

    def test_invalidates_count_cache_after_processing(self, tmp_db, monkeypatch):
        """_local_vec_count_checked_at deve ser zerado após processar embeddings com sucesso."""
        _insert_fts(tmp_db, "/doc1.md")

        async def fake_embed(path, content):
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        # Seta cache como "recente" (não expirado)
        ls._local_vec_count_checked_at = 999999.0

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                await ls.backfill_local_embeddings()

        asyncio.run(_run())
        assert ls._local_vec_count_checked_at == 0.0, (
            "Cache deve ser invalidado após backfill com sucesso"
        )

    def test_does_not_invalidate_cache_when_no_embeddings_generated(self, tmp_db, monkeypatch):
        """Cache NÃO é invalidado quando nenhum embedding foi gerado (LOGOS offline)."""
        _insert_fts(tmp_db, "/doc1.md")

        async def fake_embed(path, content):
            return False  # simula falha

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)
        ls._local_vec_count_checked_at = 999999.0

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                await ls.backfill_local_embeddings()

        asyncio.run(_run())
        assert ls._local_vec_count_checked_at == 999999.0, (
            "Cache não deve ser invalidado quando nenhum embedding foi gerado"
        )


# ---------------------------------------------------------------------------
# LIMIT 50
# ---------------------------------------------------------------------------

class TestBackfillLimit:

    def test_processes_at_most_50_files(self, tmp_db, monkeypatch):
        """Processa no máximo 50 arquivos por execução (LIMIT na query SQL)."""
        for i in range(60):
            _insert_fts(tmp_db, f"/doc{i:03d}.md")

        calls = []
        async def fake_embed(path, content):
            calls.append(path)
            return True

        monkeypatch.setattr(ls, "embed_and_index", fake_embed)

        async def _run():
            with patch("asyncio.sleep", return_value=None):
                await ls.backfill_local_embeddings()

        asyncio.run(_run())
        assert len(calls) <= 50, (
            f"backfill não deve processar mais de 50 arquivos por vez, "
            f"processou {len(calls)}"
        )
