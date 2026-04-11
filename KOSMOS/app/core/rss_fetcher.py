"""Busca e parsing de feeds RSS/Atom via feedparser.

Cobre: RSS genérico, YouTube (Atom), Tumblr, Substack, Mastodon.
"""

from __future__ import annotations

import calendar
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import struct_time
from typing import Any

log = logging.getLogger("kosmos.rss_fetcher")

_USER_AGENT = "Mozilla/5.0 (compatible; KOSMOS/1.0)"


@dataclass
class ArticleData:
    """Dados brutos de um artigo extraído do feed."""

    guid:         str
    title:        str
    url:          str | None        = None
    author:       str | None        = None
    published_at: datetime | None   = None
    summary:      str | None        = None
    content:      str | None        = None
    extra:        dict[str, Any]    = field(default_factory=dict)


@dataclass
class FetchResult:
    """Resultado de uma busca de feed."""

    articles:      list[ArticleData]
    etag:          str | None  = None
    last_modified: str | None  = None
    not_modified:  bool        = False
    error:         str | None  = None


class RSSFetchError(Exception):
    """Erro durante fetch de feed RSS."""


class RSSFetcher:
    """Busca feeds RSS/Atom com suporte a ETag, Last-Modified e User-Agent."""

    def fetch(
        self,
        url: str,
        etag: str | None = None,
        last_modified: str | None = None,
        feed_type: str = "rss",
    ) -> FetchResult:
        """Faz o fetch de um feed e retorna os artigos parseados.

        Args:
            url:           URL do feed.
            etag:          ETag da última busca (para cache HTTP 304).
            last_modified: Last-Modified da última busca.
            feed_type:     Tipo do feed ('rss', 'youtube', etc.).

        Returns:
            FetchResult com artigos e metadados de cache.
        """
        try:
            import feedparser
        except ImportError as exc:
            return FetchResult(articles=[], error="feedparser não está instalado.")

        try:
            d = feedparser.parse(
                url,
                etag=etag,
                modified=last_modified,
                request_headers={"User-Agent": _USER_AGENT},
            )
        except Exception as exc:
            return FetchResult(articles=[], error=f"Erro de rede: {exc}")

        # Verifica status HTTP
        status = getattr(d, "status", None)
        if status == 304:
            return FetchResult(articles=[], not_modified=True)
        if status and status >= 400:
            return FetchResult(
                articles=[],
                error=f"HTTP {status} ao buscar feed.",
            )

        # Verifica erro de parsing grave
        if d.get("bozo") and not d.get("entries"):
            exc = d.get("bozo_exception", "feed malformado")
            return FetchResult(articles=[], error=f"Parsing falhou: {exc}")

        articles = self._parse_entries(d.entries, feed_type)

        return FetchResult(
            articles      = articles,
            etag          = d.get("etag"),
            last_modified = d.get("modified"),
        )

    # ------------------------------------------------------------------
    # Parsing de entradas
    # ------------------------------------------------------------------

    def _parse_entries(
        self,
        entries: list,
        feed_type: str,
    ) -> list[ArticleData]:
        result: list[ArticleData] = []
        for entry in entries:
            try:
                article = self._parse_entry(entry, feed_type)
                result.append(article)
            except Exception as exc:
                log.debug("Entrada ignorada por erro de parsing: %s", exc)
        return result

    def _parse_entry(self, entry, feed_type: str) -> ArticleData:
        guid  = self._guid(entry)
        title = self._text(getattr(entry, "title", None)) or "(sem título)"
        url   = getattr(entry, "link", None)

        # Conteúdo: preferir content[0].value sobre summary
        content: str | None = None
        if hasattr(entry, "content") and entry.content:
            content = self._text(entry.content[0].get("value"))
        summary = self._text(getattr(entry, "summary", None))

        author = self._text(getattr(entry, "author", None))
        pub_at = self._parse_date(getattr(entry, "published_parsed", None))

        extra: dict[str, Any] = {}
        if feed_type == "youtube":
            extra = self._youtube_extra(entry)
        elif feed_type == "reddit":
            extra = self._reddit_extra(entry)

        return ArticleData(
            guid         = guid,
            title        = title,
            url          = url,
            author       = author,
            published_at = pub_at,
            summary      = summary,
            content      = content,
            extra        = extra,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _guid(entry: Any) -> str:
        """Extrai o GUID único do entry."""
        return (
            getattr(entry, "id", None)
            or getattr(entry, "link", None)
            or str(time.time())
        )

    @staticmethod
    def _text(value: str | None) -> str | None:
        """Remove espaços extras. Retorna None se vazio."""
        if not value:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @staticmethod
    def _parse_date(parsed_time: struct_time | None) -> datetime | None:
        """Converte struct_time do feedparser para datetime UTC."""
        if parsed_time is None:
            return None
        try:
            ts = calendar.timegm(parsed_time)
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            return None

    @staticmethod
    def _youtube_extra(entry: Any) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        video_id = getattr(entry, "yt_videoid", None)
        if video_id:
            extra["video_id"] = video_id
        thumbnails = getattr(entry, "media_thumbnail", None)
        if thumbnails:
            extra["thumbnail_url"] = thumbnails[0].get("url")
        return extra

    @staticmethod
    def _reddit_extra(entry: Any) -> dict[str, Any]:
        # RSS do Reddit não usa praw — metadados limitados via RSS
        extra: dict[str, Any] = {}
        tags = getattr(entry, "tags", [])
        if tags:
            extra["flair"] = tags[0].get("term", "")
        return extra
