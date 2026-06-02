"""
article_scraper.py — Extração de texto completo de artigos via scraping.

Trafilatura é o método principal: extrai o corpo editorial limpo,
descartando menus, sidebars e publicidade.

Fallback BeautifulSoup: quando trafilatura retorna vazio, texto curto demais
ou falha internamente, tenta extrair parágrafos de containers editoriais
(<article>, <main>, etc.) ou do <body>.

Throttle por domínio: mínimo 2s entre requisições ao mesmo host,
independente do throttle do feed_fetcher.

Este módulo é síncrono — ScraperWorker (QThread) é o caller responsável
por executar em thread separada.

is_scraped: 0 = pendente, 1 = sucesso, -1 = falhou definitivamente.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from urllib.parse import urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

from app.core.database import get_conn

log = logging.getLogger("kosmos.article_scraper")

# ---------------------------------------------------------------------------
# Throttle por domínio (independente do feed_fetcher)
# ---------------------------------------------------------------------------
THROTTLE_DELAY: float = 2.0
_domain_last_fetch: dict[str, float] = {}


def _throttle(url: str) -> None:
    """Impõe delay mínimo entre requisições ao mesmo domínio."""
    try:
        host = urlparse(url).hostname or url
    except Exception:
        host = url
    now = time.monotonic()
    wait = THROTTLE_DELAY - (now - _domain_last_fetch.get(host, 0.0))
    if wait > 0:
        log.debug("Throttle %s: aguardando %.2fs.", host, wait)
        time.sleep(wait)
    _domain_last_fetch[host] = time.monotonic()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
_HTTP_TIMEOUT = 20
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Códigos que indicam conteúdo permanentemente inacessível — não tenta fallback
_HARD_FAIL_CODES = {401, 403, 404, 410, 451}


def _fetch_html(url: str) -> str | None:
    """Baixa o HTML da URL com throttle de domínio.

    Returns:
        HTML como string, ou None em caso de falha de rede ou HTTP de erro.
    """
    _throttle(url)
    log.info("Scraping: %s", url)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
    except requests.RequestException as exc:
        log.warning("Falha de rede ao scraping %s: %s", url, exc)
        return None

    if resp.status_code in _HARD_FAIL_CODES:
        log.warning("HTTP %d para %s — conteúdo inacessível.", resp.status_code, url)
        return None

    if not resp.ok:
        log.warning("HTTP %d para %s.", resp.status_code, url)
        return None

    encoding = resp.apparent_encoding or "utf-8"
    try:
        return resp.content.decode(encoding, errors="replace")
    except Exception:
        return resp.text


# ---------------------------------------------------------------------------
# Extração de texto
# ---------------------------------------------------------------------------
_MULTI_BLANK = re.compile(r"\s{3,}")


def _clean(text: str) -> str:
    """Remove excesso de espaços em branco preservando quebras duplas."""
    return _MULTI_BLANK.sub("\n\n", text.strip())


def _extract_with_trafilatura(html: str, url: str) -> str | None:
    """Extrai texto editorial limpo com trafilatura.

    Returns:
        Texto limpo, ou None se trafilatura não encontrar conteúdo editorial.
    """
    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,
        )
        if text:
            result = _clean(text)
            log.debug("Trafilatura: %d chars extraídos de %s.", len(result), url)
            return result
        log.debug("Trafilatura: resultado vazio para %s.", url)
        return None
    except Exception as exc:
        log.warning("Trafilatura falhou para %s: %s", url, exc)
        return None


# Seletores de container editorial — tentados em ordem de especificidade
_ARTICLE_SELECTORS = [
    "article",
    "main",
    '[role="main"]',
    ".article-body",
    ".post-content",
    ".entry-content",
    ".content-body",
    ".story-body",
    ".article__body",
    "#article-body",
    "#content",
]

# Comprimento mínimo de um parágrafo para ser incluído na extração
_MIN_PARA_LEN = 40


def _extract_with_beautifulsoup(html: str) -> str | None:
    """Fallback: extrai parágrafos de containers editoriais via BeautifulSoup.

    Itera seletores em ordem de especificidade (<article> > <main> > …).
    Coleta <p> com >= _MIN_PARA_LEN chars do melhor container encontrado.

    Returns:
        Texto extraído, ou None se não houver conteúdo útil.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove ruído: scripts, estilos, navegação, rodapé, formulários
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "form", "noscript", "iframe"]):
            tag.decompose()

        container = None
        for sel in _ARTICLE_SELECTORS:
            container = soup.select_one(sel)
            if container:
                log.debug("BeautifulSoup: container '%s' encontrado.", sel)
                break

        if container is None:
            container = soup.find("body")
            log.debug("BeautifulSoup: usando <body> como fallback.")

        if container is None:
            log.debug("BeautifulSoup: nenhum container HTML válido.")
            return None

        paragraphs = [
            p.get_text(separator=" ", strip=True)
            for p in container.find_all("p")
            if len(p.get_text(strip=True)) >= _MIN_PARA_LEN
        ]

        if not paragraphs:
            log.debug("BeautifulSoup: nenhum parágrafo útil encontrado.")
            return None

        text = _clean("\n\n".join(paragraphs))
        log.debug(
            "BeautifulSoup: %d chars extraídos (%d parágrafos).",
            len(text), len(paragraphs),
        )
        return text
    except Exception as exc:
        log.warning("BeautifulSoup falhou: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pipeline de scraping
# ---------------------------------------------------------------------------

# Descarta textos muito curtos — provavelmente cookie banners, paywalls, erros
MIN_TEXT_LENGTH = 200


def scrape_article(url: str) -> str | None:
    """Extrai o texto completo do artigo na URL.

    Pipeline:
    1. Baixa o HTML com throttle de domínio.
    2. Tenta trafilatura; se resultado >= MIN_TEXT_LENGTH, retorna imediatamente.
    3. Se trafilatura falhou ou ficou curto, tenta BeautifulSoup.
    4. Retorna o mais longo dos candidatos válidos (>= MIN_TEXT_LENGTH), ou None.

    Returns:
        Texto limpo, ou None se não foi possível extrair conteúdo suficiente.
    """
    html = _fetch_html(url)
    if not html:
        log.warning("scrape_article: sem HTML para %s.", url)
        return None

    traf_text = _extract_with_trafilatura(html, url)
    if traf_text and len(traf_text) >= MIN_TEXT_LENGTH:
        return traf_text

    bs_text = _extract_with_beautifulsoup(html)

    candidates = [t for t in (traf_text, bs_text) if t and len(t) >= MIN_TEXT_LENGTH]
    if not candidates:
        log.warning(
            "scrape_article: extração falhou (texto insuficiente) para %s.", url
        )
        return None

    best = max(candidates, key=len)
    log.info("scrape_article: %d chars extraídos de %s.", len(best), url)
    return best


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------
_SCRAPE_SUCCESS =  1
_SCRAPE_FAILED  = -1


def save_article_text(
    article_id: int,
    text: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Persiste o texto extraído, marca is_scraped=1 e atualiza tempo de leitura.

    Args:
        article_id: ID do artigo na tabela articles.
        text:       Texto limpo extraído pelo scraper.
        conn:       Conexão existente (testes); None → cria e fecha própria.
    """
    words = len(text.split())
    reading_min = max(1, round(words / 200))

    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            """
            UPDATE articles
               SET content_text          = ?,
                   is_scraped            = ?,
                   estimated_reading_min = ?
             WHERE id = ?
            """,
            (text, _SCRAPE_SUCCESS, reading_min, article_id),
        )
        _conn.commit()
        log.info(
            "Artigo %d: texto salvo (%d palavras, ~%d min leitura).",
            article_id, words, reading_min,
        )
    except sqlite3.Error as exc:
        log.error("Falha ao salvar texto do artigo %d: %s", article_id, exc)
        raise
    finally:
        if should_close:
            _conn.close()


def mark_scrape_failed(
    article_id: int,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Marca is_scraped=-1 para artigos cujo scraping falhou definitivamente.

    Artigos com is_scraped=-1 não são retentados automaticamente.
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            "UPDATE articles SET is_scraped = ? WHERE id = ?",
            (_SCRAPE_FAILED, article_id),
        )
        _conn.commit()
        log.warning("Artigo %d: scraping marcado como falha definitiva.", article_id)
    except sqlite3.Error as exc:
        log.error(
            "Falha ao registrar scraping falho para artigo %d: %s", article_id, exc
        )
        raise
    finally:
        if should_close:
            _conn.close()


def scrape_and_save(article_id: int, url: str) -> bool:
    """Pipeline completo: scraping + persistência no banco.

    Em caso de falha de extração, marca is_scraped=-1 e retorna False.
    Em caso de falha de banco ao salvar, retorna False sem marcar falha
    (para que possa ser retentado).

    Nunca propaga exceção — ScraperWorker não precisa de try/except por artigo.

    Returns:
        True se o texto foi extraído e salvo com sucesso.
    """
    log.info("scrape_and_save: article_id=%d url=%s", article_id, url)
    text = scrape_article(url)
    if not text:
        try:
            mark_scrape_failed(article_id)
        except sqlite3.Error:
            pass
        return False

    try:
        save_article_text(article_id, text)
        return True
    except sqlite3.Error:
        return False
