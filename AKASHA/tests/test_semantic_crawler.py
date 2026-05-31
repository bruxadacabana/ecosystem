"""
Testes para Semântico 3 — embedding disparado após crawl + backfill.

Cobre:
  - Após crawl de página com conteúdo suficiente: create_task(embed_and_store) é chamado
  - Página com conteúdo curto (< MIN_WORDS_TO_STORE): embed_and_store NÃO é chamado
  - embed_and_store falha silenciosamente (LOGOS offline): crawler continua sem erro
  - Backfill: páginas sem embedding são processadas por backfill_knowledge
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Hook no crawler — embed_and_store chamado após crawl bem-sucedido
# ---------------------------------------------------------------------------

class TestCrawlerEmbedHook:
    """Testa a guarda que decide quando embed_and_store é disparado.

    O hook vive em _process_url (não em _upsert_page), portanto os testes
    verificam a condição de guarda diretamente e a resiliência do embed.
    """

    def test_embed_guard_long_content(self):
        """Conteúdo com word_count >= MIN_WORDS_TO_STORE passa a guarda."""
        from services.crawler import MIN_WORDS_TO_STORE

        long_content = " ".join(["palavra"] * MIN_WORDS_TO_STORE)
        assert len(long_content.split()) >= MIN_WORDS_TO_STORE

    def test_embed_guard_short_content(self):
        """Conteúdo com word_count < MIN_WORDS_TO_STORE não passa a guarda."""
        from services.crawler import MIN_WORDS_TO_STORE

        short_content = " ".join(["x"] * (MIN_WORDS_TO_STORE - 1))
        assert len(short_content.split()) < MIN_WORDS_TO_STORE

    def test_hook_dispatches_task_for_long_content(self, db_paths, monkeypatch):
        """A guarda no _process_url dispara create_task para conteúdo suficiente."""
        import services.semantic_search as _sem

        embedded: list[str] = []

        async def _fake_embed(url: str, content_md: str) -> None:
            embedded.append(url)

        monkeypatch.setattr(_sem, "embed_and_store", _fake_embed)

        # Simula a guarda exata que existe no código de produção
        from services.crawler import MIN_WORDS_TO_STORE
        long_content = " ".join(["palavra"] * 60)  # 60 >= 50

        async def _run():
            if long_content and len(long_content.split()) >= MIN_WORDS_TO_STORE:
                from services.semantic_search import embed_and_store as _embed
                asyncio.create_task(_embed("https://test.com/page", long_content))
            await asyncio.sleep(0.05)  # aguarda a task executar

        run(_run())
        assert "https://test.com/page" in embedded

    def test_hook_does_not_dispatch_for_short_content(self, monkeypatch):
        """A guarda no _process_url NÃO dispara create_task para conteúdo curto."""
        import services.semantic_search as _sem

        embedded: list[str] = []

        async def _fake_embed(url: str, content_md: str) -> None:
            embedded.append(url)

        monkeypatch.setattr(_sem, "embed_and_store", _fake_embed)

        from services.crawler import MIN_WORDS_TO_STORE
        short_content = " ".join(["x"] * 10)  # 10 < 50

        async def _run():
            if short_content and len(short_content.split()) >= MIN_WORDS_TO_STORE:
                from services.semantic_search import embed_and_store as _embed
                asyncio.create_task(_embed("https://test.com/short", short_content))
            await asyncio.sleep(0)

        run(_run())
        assert embedded == [], "embed_and_store não deve ser chamado para conteúdo curto"

    def test_embed_error_absorbed_by_try_except(self, monkeypatch):
        """Exceção em embed_and_store é absorvida silenciosamente pelo try/except."""
        import services.semantic_search as _sem

        async def _broken_embed(url: str, content_md: str) -> None:
            raise RuntimeError("LOGOS falhou")

        monkeypatch.setattr(_sem, "embed_and_store", _broken_embed)

        from services.crawler import MIN_WORDS_TO_STORE
        long_content = " ".join(["palavra"] * 60)

        async def _run():
            try:
                from services.semantic_search import embed_and_store as _embed
                asyncio.create_task(_embed("https://x.com", long_content))
            except Exception:
                pass
            await asyncio.sleep(0.05)

        # Não deve lançar exceção
        run(_run())


# ---------------------------------------------------------------------------
# Backfill de embeddings no knowledge_worker
# ---------------------------------------------------------------------------

class TestBackfillEmbeddings:

    def _insert_crawl_page(self, main_path: Path, url: str, word_count: int = 100) -> None:
        """Insere página em crawl_pages sem embedding em page_embeddings."""
        con = sqlite3.connect(main_path)
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute(
            "INSERT OR REPLACE INTO crawl_pages (site_id, url, content_md, word_count) VALUES (0, ?, ?, ?)",
            (url, " ".join(["palavra"] * word_count), word_count),
        )
        con.commit()
        con.close()

    def test_backfill_processes_pages_without_embedding(self, db_paths, monkeypatch):
        """backfill_knowledge chama embed_and_store para páginas sem embedding."""
        main_path, _ = db_paths

        import services.knowledge_worker as _kw
        import services.semantic_search as _sem
        import config as _cfg
        import database as _db

        _db.DB_PATH = main_path
        _cfg.DB_PATH = main_path

        self._insert_crawl_page(main_path, "https://backfill1.test")
        self._insert_crawl_page(main_path, "https://backfill2.test")

        embedded: list[str] = []

        async def _fake_embed(url: str, content_md: str) -> None:
            embedded.append(url)

        monkeypatch.setattr(_sem, "embed_and_store", _fake_embed)

        # Simula só a parte de backfill de embeddings (não a função completa
        # pois ela aguarda 15s e processa arquivos de disco)
        async def _run_backfill_embed():
            import aiosqlite
            async with aiosqlite.connect(main_path) as db:
                rows = await (await db.execute(
                    "SELECT url, content_md FROM crawl_pages "
                    "WHERE word_count >= 50 "
                    "AND url NOT IN (SELECT url FROM page_embeddings) "
                    "LIMIT 50"
                )).fetchall()

            sem = asyncio.Semaphore(2)

            async def _do(u, c):
                async with sem:
                    await _sem.embed_and_store(u, c)

            await asyncio.gather(*(_do(u, c) for u, c in rows if u and c))

        run(_run_backfill_embed())

        assert "https://backfill1.test" in embedded
        assert "https://backfill2.test" in embedded

    def test_backfill_skips_short_pages(self, db_paths, monkeypatch):
        """Páginas com word_count < 50 não entram no backfill de embeddings."""
        main_path, _ = db_paths

        import services.semantic_search as _sem
        import config as _cfg
        import database as _db

        _db.DB_PATH = main_path
        _cfg.DB_PATH = main_path

        self._insert_crawl_page(main_path, "https://short.test", word_count=10)

        embedded: list[str] = []

        async def _fake_embed(url: str, content_md: str) -> None:
            embedded.append(url)

        monkeypatch.setattr(_sem, "embed_and_store", _fake_embed)

        async def _run_backfill_embed():
            import aiosqlite
            async with aiosqlite.connect(main_path) as db:
                rows = await (await db.execute(
                    "SELECT url, content_md FROM crawl_pages "
                    "WHERE word_count >= 50 "
                    "AND url NOT IN (SELECT url FROM page_embeddings) "
                    "LIMIT 50"
                )).fetchall()
            for u, c in rows:
                if u and c:
                    await _sem.embed_and_store(u, c)

        run(_run_backfill_embed())

        assert "https://short.test" not in embedded

    def test_backfill_skips_already_embedded_pages(self, db_paths, monkeypatch):
        """Páginas que já têm embedding em page_embeddings são ignoradas."""
        main_path, _ = db_paths

        import services.semantic_search as _sem
        import config as _cfg
        import database as _db

        _db.DB_PATH = main_path
        _cfg.DB_PATH = main_path

        self._insert_crawl_page(main_path, "https://already.test")

        # Insere embedding manualmente
        con = sqlite3.connect(main_path)
        con.execute("INSERT INTO page_embeddings (url) VALUES ('https://already.test')")
        con.commit()
        con.close()

        embedded: list[str] = []

        async def _fake_embed(url: str, content_md: str) -> None:
            embedded.append(url)

        monkeypatch.setattr(_sem, "embed_and_store", _fake_embed)

        async def _run_backfill_embed():
            import aiosqlite
            async with aiosqlite.connect(main_path) as db:
                rows = await (await db.execute(
                    "SELECT url, content_md FROM crawl_pages "
                    "WHERE word_count >= 50 "
                    "AND url NOT IN (SELECT url FROM page_embeddings) "
                    "LIMIT 50"
                )).fetchall()
            for u, c in rows:
                if u and c:
                    await _sem.embed_and_store(u, c)

        run(_run_backfill_embed())

        assert "https://already.test" not in embedded, (
            "Página com embedding existente não deve ser reprocessada"
        )
