"""Web scraping de artigos completos — 4 extratores em cascata sobre HTML único."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("kosmos.scraper")

# Headers de browser realistas — reduz bloqueios por detecção de bot
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
    """Extrai o conteúdo completo de uma URL com quatro extratores em cascata:
    1. newspaper4k   — melhor para sites ocidentais
    2. trafilatura   — algoritmo diferente, complementar ao newspaper4k
    3. readability   — algoritmo do Firefox/Mozilla, detecta artigos por estrutura
    4. BeautifulSoup — fallback simples sem dependências de idioma

    O HTML é baixado uma única vez com headers de browser realistas.
    O primeiro extrator a retornar >= 100 palavras encerra a cadeia.
    Se nenhum atingir 100 palavras, o resultado parcial mais longo é retornado.
    """

    _TIMEOUT = 15

    def scrape(self, url: str) -> ScrapeResult:
        # Busca HTML uma vez — todos os extratores usam o mesmo conteúdo
        raw_html, fetch_error = self._fetch_html(url)

        results: list[ScrapeResult] = []

        # 1. newspaper4k
        r = self._try_newspaper(url, raw_html)
        if r.status == "full":
            return r
        if r.status == "partial":
            results.append(r)

        # 2. trafilatura
        r = self._try_trafilatura(url, raw_html)
        if r.status == "full":
            return r
        if r.status == "partial":
            results.append(r)

        # 3. readability-lxml
        r = self._try_readability(raw_html)
        if r.status == "full":
            return r
        if r.status == "partial":
            results.append(r)

        # 4. BeautifulSoup
        r = self._scrape_bs4_fallback(raw_html)
        if r.status == "full":
            return r
        if r.status == "partial":
            results.append(r)

        if results:
            return max(results, key=lambda x: len(x.content_html))

        return ScrapeResult(
            "", "failed",
            fetch_error or "Todos os extratores falharam.",
        )

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _fetch_html(self, url: str) -> tuple[str | None, str | None]:
        """Baixa o HTML bruto com headers de browser realistas."""
        try:
            import requests
            resp = requests.get(
                url,
                timeout=self._TIMEOUT,
                headers=_HEADERS,
                allow_redirects=True,
            )
            resp.raise_for_status()
            return resp.text, None
        except Exception as exc:
            log.debug("Falha ao baixar %s: %s", url, exc)
            return None, str(exc)

    # ------------------------------------------------------------------
    # Extratores
    # ------------------------------------------------------------------

    def _try_newspaper(self, url: str, html: str | None) -> ScrapeResult:
        try:
            from newspaper import Article  # type: ignore
        except ImportError:
            return ScrapeResult("", "failed", "newspaper4k não instalado.")

        try:
            article = Article(url)
            if html:
                article.set_html(html)
            else:
                article.download()
            article.parse()
        except Exception as exc:
            err = str(exc)
            if any(kw in err.lower() for kw in ("tokenizer", "tinysegmenter", "tokeniser")):
                log.debug("newspaper4k: tokenizador ausente para %s", url)
            else:
                log.debug("newspaper4k falhou para %s: %s", url, exc)
            return ScrapeResult("", "failed", err)

        text = (article.text or "").strip()
        if not text:
            return ScrapeResult("", "failed", "newspaper4k: sem texto extraído.")

        html_out = self._newspaper_to_html(text, article)
        words    = _word_count(html_out)
        status   = "full" if words >= 100 else "partial"
        return ScrapeResult(html_out, status, None)

    def _try_trafilatura(self, url: str, html: str | None) -> ScrapeResult:
        try:
            import trafilatura
        except ImportError:
            return ScrapeResult("", "failed", "trafilatura não instalado.")

        try:
            source = html or trafilatura.fetch_url(url)
            if not source:
                return ScrapeResult("", "failed", "trafilatura: sem conteúdo.")

            html_out = trafilatura.extract(
                source,
                output_format="html",
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_recall=True,
                url=url,
            )
            if not html_out:
                return ScrapeResult("", "failed", "trafilatura: extração vazia.")

            words  = _word_count(html_out)
            status = "full" if words >= 100 else "partial"
            return ScrapeResult(html_out, status, None)
        except Exception as exc:
            log.debug("trafilatura falhou para %s: %s", url, exc)
            return ScrapeResult("", "failed", str(exc))

    def _try_readability(self, html: str | None) -> ScrapeResult:
        if not html:
            return ScrapeResult("", "failed", "readability: sem HTML disponível.")
        try:
            from readability import Document  # type: ignore
        except ImportError:
            return ScrapeResult("", "failed", "readability-lxml não instalado.")

        try:
            doc     = Document(html)
            content = doc.summary(html_partial=True)
            if not content:
                return ScrapeResult("", "failed", "readability: extração vazia.")

            words  = _word_count(content)
            if words < 30:
                return ScrapeResult(content, "partial", None)

            status = "full" if words >= 100 else "partial"
            return ScrapeResult(content, status, None)
        except Exception as exc:
            log.debug("readability falhou: %s", exc)
            return ScrapeResult("", "failed", str(exc))

    def _scrape_bs4_fallback(self, html: str | None) -> ScrapeResult:
        if not html:
            return ScrapeResult("", "failed", "BS4: sem HTML disponível.")
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                tag.decompose()

            body = (
                soup.find("article")
                or soup.find(attrs={"role": "main"})
                or soup.find("main")
                or soup.find("body")
            )
            if body is None:
                return ScrapeResult("", "partial", "BS4: corpo do artigo não encontrado.")

            text  = body.get_text(separator="\n\n", strip=True)
            words = len(text.split())
            if words < 30:
                return ScrapeResult("", "partial", "BS4: conteúdo insuficiente.")

            paragraphs = [
                f"<p>{p.strip()}</p>"
                for p in text.split("\n\n")
                if p.strip() and len(p.split()) > 3
            ]
            status = "full" if words >= 100 else "partial"
            return ScrapeResult("\n".join(paragraphs), status, None)

        except Exception as exc:
            log.warning("BS4 falhou: %s", exc)
            return ScrapeResult("", "failed", str(exc))

    # ------------------------------------------------------------------

    def _newspaper_to_html(self, text: str, article: Any) -> str:
        if getattr(article, "article_html", None):
            return article.article_html

        parts: list[str] = []
        top_image = getattr(article, "top_image", None)
        if top_image:
            parts.append(f'<img src="{top_image}" alt="Imagem do artigo">')

        for para in text.split("\n\n"):
            para = para.strip()
            if para:
                parts.append(f"<p>{para.replace(chr(10), '<br>')}</p>")

        return "\n".join(parts)
