"""Descoberta de feeds RSS por palavra-chave via API pública do Feedly."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, pyqtSignal

if TYPE_CHECKING:
    pass

log = logging.getLogger("kosmos.discovery")

_FEEDLY_SEARCH = "https://cloud.feedly.com/v3/search/feeds"
_TIMEOUT       = 10  # segundos


@dataclass
class FeedCandidate:
    """Um feed encontrado pela busca."""

    title:       str
    url:         str
    website:     str
    description: str
    subscribers: int
    language:    str

    def __str__(self) -> str:
        return f"{self.title} ({self.url})"


class DiscoveryWorker(QThread):
    """QThread que consulta a API de busca do Feedly em background.

    Sinais:
        results_ready(list[FeedCandidate])  — busca concluída com resultados.
        search_error(str)                   — erro durante a busca.
    """

    results_ready = pyqtSignal(list)   # list[FeedCandidate]
    search_error  = pyqtSignal(str)

    def __init__(self, query: str, count: int = 20) -> None:
        super().__init__()
        self._query = query.strip()
        self._count = count

    def run(self) -> None:
        if not self._query:
            self.results_ready.emit([])
            return

        try:
            import urllib.request
            import urllib.parse

            params = urllib.parse.urlencode({
                "query": self._query,
                "count": self._count,
                "locale": "pt",
            })
            url = f"{_FEEDLY_SEARCH}?{params}"

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; KOSMOS/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            candidates = self._parse_response(data)
            self.results_ready.emit(candidates)

        except Exception as exc:
            log.warning("Erro na busca de feeds: %s", exc)
            self.search_error.emit(str(exc))

    def _parse_response(self, data: dict) -> list[FeedCandidate]:
        results = data.get("results", [])
        candidates: list[FeedCandidate] = []

        for item in results:
            feed_id = item.get("feedId", "")
            # feedId tem formato "feed/https://..."
            url = feed_id[5:] if feed_id.startswith("feed/") else feed_id
            if not url:
                continue

            candidates.append(FeedCandidate(
                title       = item.get("title") or item.get("website") or url,
                url         = url,
                website     = item.get("website", ""),
                description = item.get("description", ""),
                subscribers = item.get("subscribers", 0),
                language    = item.get("language", ""),
            ))

        return candidates
