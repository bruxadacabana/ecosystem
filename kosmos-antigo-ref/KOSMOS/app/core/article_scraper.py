"""Scraping de artigos — delega extração ao ecosystem_scraper (cascata compartilhada)."""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("kosmos.scraper")

# Módulo compartilhado do ecossistema
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ecosystem_scraper import extract as _cascade_extract, get_fetch_url as _get_fetch_url

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Connection":      "keep-alive",
}


@dataclass
class ScrapeResult:
    """Resultado de uma tentativa de scraping."""
    content_html: str
    status: str           # 'full' | 'partial' | 'failed'
    error: str | None = None


def _word_count(html: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", html).split())


class ArticleScraper:
    """Extrai o conteúdo completo de uma URL via ecosystem_scraper (cascata compartilhada).

    newspaper4k → trafilatura → readability-lxml → inscriptis → BeautifulSoup
    O HTML é baixado uma única vez. O primeiro extrator com ≥ 100 palavras vence.
    """

    _TIMEOUT = 15

    def scrape(self, url: str) -> ScrapeResult:
        raw_html, fetch_error = self._fetch_html(url)
        if not raw_html:
            return ScrapeResult("", "failed", fetch_error or "Falha ao baixar página.")

        content_html = _cascade_extract(raw_html, url, output_format="html")

        if not content_html:
            return ScrapeResult("", "failed", "Todos os extratores falharam.")

        words  = _word_count(content_html)
        status = "full" if words >= 100 else "partial"
        return ScrapeResult(content_html, status)

    def _fetch_html(self, url: str) -> tuple[str | None, str | None]:
        """Baixa o HTML bruto com headers de browser realistas."""
        try:
            import requests
            resp = requests.get(
                _get_fetch_url(url),
                timeout=self._TIMEOUT,
                headers=_HEADERS,
                allow_redirects=True,
            )
            resp.raise_for_status()
            return resp.text, None
        except Exception as exc:
            log.debug("Falha ao baixar %s: %s", url, exc)
            return None, str(exc)
