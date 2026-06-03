"""
scraper_worker.py — ScraperWorker: QThread para extração de texto completo.

Duas prioridades, um só worker:
  - **P1 (sob demanda):** quando a usuária abre um artigo e pede o texto completo
    ("Carregar texto completo"), a GUI chama `request_scrape(article_id, url)`.
    Esses pedidos entram numa fila prioritária e são processados ANTES do batch,
    e também preemptam o batch entre um artigo e outro.
  - **P2 (batch em background):** enquanto ocioso, o worker varre artigos com
    `is_scraped = 0` (newest-first) e extrai o texto de cada um.

O scraping em si (rede + parsing) vive em `article_scraper.scrape_and_save`, que
nunca propaga exceção e já faz throttle por domínio. Este worker só orquestra a
ordem (P1 > P2), emite sinais para a GUI e dorme de forma interruptível quando
não há trabalho.

Não passa pelo LOGOS — scraping é I/O de rede, sem LLM envolvido.
"""
from __future__ import annotations

import logging
import queue
import sqlite3

from PySide6.QtCore import QThread, Signal

from app.core.article_scraper import scrape_and_save
from app.core.database import get_conn

log = logging.getLogger("kosmos.scraper_worker")

_BATCH_SIZE = 10          # nº de artigos pendentes processados por ciclo de batch
_IDLE_INTERVAL_SEC = 30   # pausa entre ciclos quando não há nada a fazer


def get_pending_articles(
    limit: int = _BATCH_SIZE,
    conn: sqlite3.Connection | None = None,
) -> list[tuple[int, str]]:
    """Retorna artigos ainda não scrapeados (is_scraped = 0), mais novos primeiro.

    Ignora artigos já scrapeados (1) e os que falharam definitivamente (-1), além
    de URLs vazias. Ordena por data de publicação desc (fallback id desc) para
    priorizar o conteúdo mais recente. Em erro de banco, retorna lista vazia.

    Args:
        limit: nº máximo de artigos retornados.
        conn:  conexão existente (testes); None → cria e fecha própria.

    Returns:
        Lista de (article_id, url).
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT id, url FROM articles
             WHERE is_scraped = 0
               AND url IS NOT NULL
               AND url != ''
             ORDER BY COALESCE(published_at, '') DESC, id DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [(row["id"], row["url"]) for row in rows]
    except sqlite3.Error as exc:
        log.error("Falha ao consultar artigos pendentes de scraping: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()


class ScraperWorker(QThread):
    """QThread P1/P2: extrai texto completo de artigos.

    Sinais:
        scrape_started(int)       — article_id cujo scraping foi iniciado
        scrape_done(int, bool)    — (article_id, sucesso) ao terminar um artigo
        cycle_done(int)           — nº de artigos processados no ciclo
    """

    scrape_started = Signal(int)
    scrape_done    = Signal(int, bool)
    cycle_done     = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_flag: bool = False
        self._priority_q: "queue.Queue[tuple[int, str]]" = queue.Queue()
        self._batch_size: int = _BATCH_SIZE
        self._idle_interval_sec: int = _IDLE_INTERVAL_SEC

    # ------------------------------------------------------------------
    # API pública (chamada da thread da GUI)
    # ------------------------------------------------------------------

    def request_scrape(self, article_id: int, url: str) -> None:
        """Enfileira um scraping prioritário (P1) — artigo aberto pela usuária."""
        if not url:
            log.debug("request_scrape ignorado: artigo %d sem URL.", article_id)
            return
        self._priority_q.put((article_id, url))
        log.info("Scraping P1 solicitado: artigo %d.", article_id)

    def stop(self) -> None:
        """Solicita parada. Encerra após o item atual ou o próximo tick ocioso."""
        self._stop_flag = True
        log.info("ScraperWorker: parada solicitada.")

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        log.info(
            "ScraperWorker iniciado (batch=%d, idle=%ds).",
            self._batch_size, self._idle_interval_sec,
        )
        self._stop_flag = False
        while not self._stop_flag:
            processed = self._run_cycle()
            self.cycle_done.emit(processed)
            if processed == 0:
                # Nada a fazer — dorme de forma interruptível (acorda em stop ou novo P1)
                for _ in range(self._idle_interval_sec):
                    if self._stop_flag or not self._priority_q.empty():
                        break
                    self.msleep(1000)
        log.info("ScraperWorker encerrado.")

    def _drain_priority(self) -> list[tuple[int, str]]:
        """Esvazia a fila prioritária (P1) sem bloquear."""
        items: list[tuple[int, str]] = []
        while True:
            try:
                items.append(self._priority_q.get_nowait())
            except queue.Empty:
                break
        return items

    def _scrape_one(self, article_id: int, url: str) -> bool:
        """Scrapeia um artigo, emitindo os sinais de início/fim."""
        self.scrape_started.emit(article_id)
        ok = scrape_and_save(article_id, url)
        self.scrape_done.emit(article_id, ok)
        return ok

    def _run_cycle(self) -> int:
        """Um ciclo: P1 (fila prioritária) primeiro, depois um batch P2.

        P1 preempta o batch entre artigos. Retorna o nº de artigos processados.
        """
        processed = 0

        # 1. P1 — pedidos sob demanda têm prioridade absoluta
        for article_id, url in self._drain_priority():
            if self._stop_flag:
                return processed
            self._scrape_one(article_id, url)
            processed += 1

        # 2. P2 — batch de pendentes (newest-first)
        for article_id, url in get_pending_articles(self._batch_size):
            if self._stop_flag:
                break
            # Preempção: se chegou um P1 enquanto rodava o batch, atende-o antes
            for p_id, p_url in self._drain_priority():
                if self._stop_flag:
                    return processed
                self._scrape_one(p_id, p_url)
                processed += 1
            self._scrape_one(article_id, url)
            processed += 1

        return processed
