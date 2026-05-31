"""
Backfill de word_count para páginas já indexadas antes do Fix 4.

Executa migração em três etapas:
  1. Preenche word_count=0 em todas as linhas onde ainda está 0
  2. Marca para re-crawl (last_checked_at='2000-01-01') as páginas com < 50 palavras
  3. Remove essas páginas do índice FTS5

Rodar manualmente após deploy do Fix 4:
  uv run python scripts/backfill_word_count.py

O script é idempotente — pode ser executado múltiplas vezes sem efeito negativo.
Não remove as linhas de crawl_pages; apenas marca para re-crawl e limpa o FTS.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Garantir que o diretório raiz do projeto está no sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import aiosqlite

from config import DB_PATH
from services.crawler import MIN_WORDS_TO_STORE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("backfill_word_count")

BATCH_SIZE = 500


async def run() -> None:
    log.info("Iniciando backfill de word_count (DB: %s)", DB_PATH)

    async with aiosqlite.connect(DB_PATH) as db:
        # ---------- Etapa 1: preencher word_count onde está 0 ----------
        log.info("Etapa 1: calculando word_count das páginas existentes...")
        rows = await (await db.execute(
            "SELECT url, content_md FROM crawl_pages WHERE word_count = 0"
        )).fetchall()

        log.info("  %d páginas com word_count=0 encontradas", len(rows))
        updated = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            params = [(len(content_md.split()), url) for url, content_md in batch]
            await db.executemany(
                "UPDATE crawl_pages SET word_count = ? WHERE url = ?", params
            )
            await db.commit()
            updated += len(batch)
            log.info("  %d/%d páginas atualizadas...", updated, len(rows))

        log.info("Etapa 1 concluída: %d páginas com word_count preenchido.", updated)

        # ---------- Etapa 2: marcar páginas insuficientes para re-crawl ----------
        log.info(
            "Etapa 2: marcando páginas com word_count < %d para re-crawl...",
            MIN_WORDS_TO_STORE,
        )
        result = await db.execute(
            "UPDATE crawl_pages SET last_checked_at = '2000-01-01' "
            "WHERE word_count < ? AND word_count > 0",
            (MIN_WORDS_TO_STORE,),
        )
        await db.commit()
        marked = result.rowcount
        log.info("Etapa 2 concluída: %d páginas marcadas para re-crawl.", marked)

        # ---------- Etapa 3: remover do índice FTS5 ----------
        log.info("Etapa 3: removendo páginas insuficientes do FTS5...")
        result = await db.execute(
            "DELETE FROM crawl_fts WHERE url IN "
            "(SELECT url FROM crawl_pages WHERE word_count < ? AND word_count > 0)",
            (MIN_WORDS_TO_STORE,),
        )
        await db.commit()
        deleted_fts = result.rowcount
        log.info("Etapa 3 concluída: %d entradas removidas do FTS5.", deleted_fts)

        # ---------- Resumo final ----------
        total_pages = (await (await db.execute(
            "SELECT COUNT(*) FROM crawl_pages"
        )).fetchone())[0]
        pages_below = (await (await db.execute(
            "SELECT COUNT(*) FROM crawl_pages WHERE word_count < ?",
            (MIN_WORDS_TO_STORE,)
        )).fetchone())[0]

        log.info(
            "Backfill concluído. Total de páginas: %d | Abaixo de %d palavras: %d",
            total_pages, MIN_WORDS_TO_STORE, pages_below,
        )


if __name__ == "__main__":
    asyncio.run(run())
