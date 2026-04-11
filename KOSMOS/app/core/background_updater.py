"""Daemon de atualização automática de feeds em background (QThread)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, pyqtSignal

if TYPE_CHECKING:
    from app.core.feed_fetcher import FeedFetcher
    from app.core.feed_manager import FeedManager
    from app.core.models import Feed
    from app.utils.config import Config

log = logging.getLogger("kosmos.updater")

_INTER_FEED_DELAY = 2   # segundos entre cada feed (respeitar servidores)
_POLL_INTERVAL    = 1   # segundos entre verificações do flag de parada


class BackgroundUpdater(QThread):
    """QThread que atualiza feeds em background num ciclo periódico.

    Sinais emitidos (sempre do thread principal via Qt queued connection):
        feed_updated(feed_id, new_count)  — feed atualizado com sucesso.
        update_error(feed_id, message)    — erro ao atualizar feed.
        cycle_started()                   — início de ciclo de atualização.
        cycle_finished(total_new)         — fim de ciclo com total de artigos novos.
    """

    feed_updated   = pyqtSignal(int, int)   # feed_id, novos artigos
    update_error   = pyqtSignal(int, str)   # feed_id, mensagem de erro
    cycle_started  = pyqtSignal()
    cycle_finished = pyqtSignal(int)        # total de artigos novos

    def __init__(self, config: "Config", feed_manager: "FeedManager") -> None:
        super().__init__()
        self._config  = config
        self._fm      = feed_manager
        self._stop    = False
        self._trigger = False

    # ------------------------------------------------------------------
    # Controle externo
    # ------------------------------------------------------------------

    def trigger_now(self) -> None:
        """Força o início imediato de um ciclo de atualização."""
        self._trigger = True

    def stop(self) -> None:
        """Sinaliza parada e aguarda o thread terminar."""
        self._stop = True
        self.wait(5000)

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    def run(self) -> None:
        log.info("BackgroundUpdater iniciado.")

        from app.core.feed_fetcher import FeedFetcher
        fetcher = FeedFetcher()

        while not self._stop:
            self._trigger = False
            self._run_cycle(fetcher)

            # Aguardar até o próximo ciclo ou trigger manual
            interval = self._config.get("update_interval_minutes", 30) * 60
            waited   = 0
            while waited < interval and not self._stop and not self._trigger:
                time.sleep(_POLL_INTERVAL)
                waited += _POLL_INTERVAL

        log.info("BackgroundUpdater encerrado.")

    def _run_cycle(self, fetcher: "FeedFetcher") -> None:
        feeds = self._fm.get_active_feeds()
        if not feeds:
            return

        self.cycle_started.emit()
        total_new = 0

        for feed in feeds:
            if self._stop:
                break
            new_count = self._fetch_one(fetcher, feed)
            total_new += new_count

            time.sleep(_INTER_FEED_DELAY)

        self.cycle_finished.emit(total_new)
        if total_new:
            log.info("Ciclo concluído: %d artigo(s) novos.", total_new)

    def _fetch_one(self, fetcher: "FeedFetcher", feed: "Feed") -> int:
        """Busca um único feed e persiste os resultados. Retorna novos artigos."""
        try:
            result = fetcher.fetch(feed)
        except Exception as exc:
            log.error("Exceção ao buscar feed %d: %s", feed.id, exc)
            self._fm.update_feed_metadata(feed.id, last_error=str(exc))
            self.update_error.emit(feed.id, str(exc))
            return 0

        if result.error:
            self._fm.update_feed_metadata(feed.id, last_error=result.error)
            self.update_error.emit(feed.id, result.error)
            return 0

        articles_data = [
            {
                "guid":         a.guid,
                "title":        a.title,
                "url":          a.url,
                "author":       a.author,
                "published_at": a.published_at,
                "summary":      a.summary,
                "content":      a.content,
                "extra":        a.extra,
            }
            for a in result.articles
        ]

        new_count = self._fm.save_articles(feed.id, articles_data)
        self._fm.update_feed_metadata(
            feed.id,
            etag          = result.etag,
            last_modified = result.last_modified,
            clear_error   = True,
        )

        if new_count:
            self._fm.deduplicate_recent(feed.id)
            self.feed_updated.emit(feed.id, new_count)

        return new_count
