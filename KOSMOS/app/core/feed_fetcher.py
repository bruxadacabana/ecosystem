"""Orquestrador de fetch: escolhe o fetcher correto pelo tipo de feed.

Fase 2: delega para RSSFetcher (RSS, YouTube, Tumblr, Substack, Mastodon).
Fase 5: adicionará RedditFetcher para feeds do tipo 'reddit'.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.rss_fetcher import FetchResult, RSSFetcher

if TYPE_CHECKING:
    from app.core.models import Feed

log = logging.getLogger("kosmos.feed_fetcher")

_RSS_TYPES = frozenset({"rss", "youtube", "tumblr", "substack", "mastodon"})


class FeedFetcher:
    """Ponto único de entrada para buscar qualquer tipo de feed."""

    def __init__(self) -> None:
        self._rss = RSSFetcher()

    def fetch(self, feed: "Feed") -> FetchResult:
        """Busca um feed e retorna FetchResult.

        Args:
            feed: objeto Feed (detached) com url, feed_type, etag, last_modified.

        Returns:
            FetchResult com artigos e metadados de cache.
        """
        if feed.feed_type in _RSS_TYPES:
            return self._rss.fetch(
                url           = feed.url,
                etag          = feed.etag,
                last_modified = feed.last_modified,
                feed_type     = feed.feed_type,
            )

        if feed.feed_type == "reddit":
            # Reddit via praw — implementado na Fase 5
            log.warning("Reddit fetcher ainda não implementado (Fase 5).")
            return FetchResult(articles=[], error="Reddit não disponível nesta versão.")

        log.warning("Tipo de feed desconhecido: %r", feed.feed_type)
        return FetchResult(articles=[], error=f"Tipo desconhecido: {feed.feed_type}")
