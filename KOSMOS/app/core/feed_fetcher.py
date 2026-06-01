"""
feed_fetcher.py — Busca e parsing de feeds RSS/Atom.

Baixa o XML do feed via requests com throttle de 2s por domínio, parseia
entradas com feedparser, extrai metadados enriquecidos (tipo de artigo,
idioma estimado, tempo de leitura) e persiste artigos novos no banco.

Este módulo é inteiramente síncrono — o caller (FetchWorker) é responsável
por chamar em QThread separada.

Deduplicação: artigos com URL já existente são ignorados silenciosamente
(INSERT OR IGNORE). A chave de unicidade é a URL do artigo.

Idioma detectado aqui é uma estimativa por stop-words. A análise AI
(Call A no AnalysisWorker) confirma o idioma definitivamente.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests

from app.core.database import get_conn

log = logging.getLogger("kosmos.feed_fetcher")

# ---------------------------------------------------------------------------
# Throttle síncrono por domínio (QThread não usa asyncio)
# ---------------------------------------------------------------------------
THROTTLE_DELAY: float = 2.0  # segundos mínimos entre requisições ao mesmo domínio
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
# Tempo de leitura estimado
# ---------------------------------------------------------------------------
_WPM = 200  # palavras por minuto — leitura confortável média


def estimate_reading_min(text: str) -> int:
    """Estima tempo de leitura em minutos (200 ppm). Mínimo: 1 minuto."""
    words = len(re.sub(r"\s+", " ", text.strip()).split())
    return max(1, round(words / _WPM))


# ---------------------------------------------------------------------------
# Detecção de idioma por stop-words (sem dependência pesada)
# ---------------------------------------------------------------------------
_LANG_VOCAB: dict[str, frozenset[str]] = {
    "pt": frozenset({
        "de", "da", "do", "que", "em", "uma", "um", "para", "com", "por",
        "não", "se", "são", "mais", "também", "como", "mas", "foi", "há",
        "pelo", "pela", "nos", "nas", "ao", "sua", "seu", "ele", "ela",
    }),
    "es": frozenset({
        "de", "la", "el", "que", "en", "una", "un", "para", "con", "por",
        "no", "se", "son", "más", "también", "como", "pero", "fue", "hay",
        "del", "los", "las", "su", "sus", "al", "este", "esta", "ese",
    }),
    "en": frozenset({
        "the", "is", "are", "was", "that", "this", "with", "for", "have",
        "not", "be", "been", "from", "they", "would", "could", "said",
        "its", "has", "had", "will", "their", "which", "about", "when",
    }),
    "fr": frozenset({
        "le", "la", "les", "de", "des", "du", "un", "une", "que", "qui",
        "dans", "est", "sur", "pour", "pas", "plus", "avec", "par",
        "ce", "se", "son", "sa", "ils", "elle", "nous", "vous",
    }),
}

_STRIP_HTML = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
_NON_ALPHA  = re.compile(r"[^\w\s]")


def detect_language(text: str) -> str:
    """Detecta idioma por heurística de stop-words.

    Retorna código ISO (pt, es, en, fr) se score > 3% das palavras do texto
    baterem no vocabulário do idioma; caso contrário, retorna "".
    """
    clean = _NON_ALPHA.sub(" ", _STRIP_HTML.sub(" ", text.lower()))
    words = set(_WHITESPACE.split(clean))
    words.discard("")
    if not words:
        return ""
    scores = {lang: len(vocab & words) / len(words) for lang, vocab in _LANG_VOCAB.items()}
    best, score = max(scores.items(), key=lambda kv: kv[1])
    return best if score > 0.03 else ""


# ---------------------------------------------------------------------------
# Tipo de artigo — heurística por palavras-chave
# ---------------------------------------------------------------------------
_OPINION_PAT = re.compile(
    r"\b(opinion|editorial|column|colum|coluna|opinião|opiniao|commentary|"
    r"tribune|point of view|ponto de vista)\b",
    re.IGNORECASE,
)
_ANALYSIS_PAT = re.compile(
    r"\b(análise|analise|analysis|explainer|explicação|explicacao|contexto|"
    r"aprofundamento|deep.?dive|investigação|investigacao|investigation|"
    r"special report|especial|reportagem especial)\b",
    re.IGNORECASE,
)


def guess_article_type(title: str, categories: list[str], url: str) -> str:
    """Infere tipo de artigo por palavras-chave em título, categorias e URL.

    Retorna 'opinion', 'analysis' ou 'news' (default). O tipo é refinado
    pela análise AI no Call B — este valor é apenas uma estimativa inicial.
    """
    pool = " ".join([title] + categories + [url])
    if _OPINION_PAT.search(pool):
        return "opinion"
    if _ANALYSIS_PAT.search(pool):
        return "analysis"
    return "news"


# ---------------------------------------------------------------------------
# Normalização de data
# ---------------------------------------------------------------------------

def _parse_entry_date(entry: Any) -> str | None:
    """Extrai data do entry feedparser → ISO8601 UTC, ou None."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------------
# HTTP + feedparser
# ---------------------------------------------------------------------------
_HTTP_TIMEOUT = 15
_HEADERS = {
    "User-Agent": "KOSMOS/3.0 (leitor RSS; ecossistema pessoal local)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


def fetch_feed(feed_url: str) -> tuple[Any, list[dict[str, Any]]]:
    """Baixa e parseia um feed RSS/Atom com throttle de 2s por domínio.

    Args:
        feed_url: URL do feed a ser buscado.

    Returns:
        (feed_obj, entries): feed_obj é feedparser.FeedParserDict.feed;
        entries é lista de dicts normalizados com todos os metadados.

    Raises:
        requests.RequestException: falha de rede irrecuperável.
        ValueError: feed inválido (sem entries parseáveis).
    """
    _throttle(feed_url)
    log.info("Buscando feed: %s", feed_url)

    try:
        resp = requests.get(feed_url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Falha de rede ao buscar %s: %s", feed_url, exc)
        raise

    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        log.warning("Feed inválido ou sem entries: %s.", feed_url)
        raise ValueError(f"Feed inválido ou sem entries: {feed_url}")
    if parsed.bozo:
        log.warning("Feed malformado mas com entries: %s (continuando).", feed_url)

    feed_lang = getattr(parsed.feed, "language", "") or ""
    entries = [_normalize_entry(e, feed_lang) for e in parsed.entries]
    log.info("%d entries parseados de %s.", len(entries), feed_url)
    return parsed.feed, entries


def _normalize_entry(entry: Any, feed_lang: str) -> dict[str, Any]:
    """Converte um entry feedparser em dict com todos os campos normalizados."""
    title = (getattr(entry, "title", "") or "").strip()
    url   = (getattr(entry, "link",  "") or "").strip()

    # Autor: preferir author_detail.name (mais estruturado que entry.author)
    author: str | None = None
    detail = getattr(entry, "author_detail", None)
    if detail and getattr(detail, "name", None):
        author = detail.name.strip() or None
    if not author:
        author = (getattr(entry, "author", "") or "").strip() or None

    # Excerpt: summary tem prioridade; fallback para primeiro content
    raw = ""
    if getattr(entry, "summary", None):
        raw = entry.summary
    elif getattr(entry, "content", None):
        raw = entry.content[0].get("value", "") or ""
    excerpt = _WHITESPACE.sub(" ", _STRIP_HTML.sub(" ", raw).strip())[:2000] or None

    # Idioma: content[].language > feed.language > heurística sobre excerpt
    lang = ""
    if getattr(entry, "content", None):
        lang = entry.content[0].get("language", "") or ""
    if not lang:
        lang = feed_lang
    if not lang and excerpt:
        lang = detect_language(excerpt)

    categories = [getattr(t, "term", "") or "" for t in getattr(entry, "tags", [])]
    pub_date   = _parse_entry_date(entry)
    reading    = estimate_reading_min(excerpt) if excerpt else None
    art_type   = guess_article_type(title, categories, url)

    return {
        "title":                 title,
        "url":                   url,
        "author":                author,
        "content_excerpt":       excerpt,
        "published_at":          pub_date,
        "estimated_reading_min": reading,
        "article_type":          art_type,
        "language_detected":     lang or None,
    }


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def save_new_articles(
    feed_id: int,
    entries: list[dict[str, Any]],
    conn: sqlite3.Connection | None = None,
) -> int:
    """Insere artigos novos no banco. Ignora duplicatas por URL (INSERT OR IGNORE).

    Args:
        feed_id: ID da linha na tabela feeds.
        entries: lista de dicts de _normalize_entry.
        conn:    conexão existente (testes); None → cria e fecha conexão própria.

    Returns:
        Número de artigos efetivamente inseridos (excluindo duplicatas).
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    inserted = 0
    try:
        for art in entries:
            if not art.get("url") or not art.get("title"):
                log.debug("Entry ignorada (sem url/title): %s", art)
                continue
            cur = _conn.execute(
                """
                INSERT OR IGNORE INTO articles (
                    feed_id, url, title, author, content_excerpt,
                    published_at, estimated_reading_min,
                    article_type, language_detected
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feed_id,
                    art["url"],
                    art["title"],
                    art.get("author"),
                    art.get("content_excerpt"),
                    art.get("published_at"),
                    art.get("estimated_reading_min"),
                    art.get("article_type"),
                    art.get("language_detected"),
                ),
            )
            if cur.rowcount:
                inserted += 1
        _conn.commit()
        log.info(
            "Feed %d: %d artigo(s) novo(s) de %d entry(ies).",
            feed_id, inserted, len(entries),
        )
    except sqlite3.Error as exc:
        log.error("Falha ao salvar artigos do feed %d: %s", feed_id, exc)
        raise
    finally:
        if should_close:
            _conn.close()
    return inserted


def update_feed_meta(
    feed_id: int,
    feed_obj: Any,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Atualiza title, site_url e last_fetched_at após fetch bem-sucedido.

    COALESCE garante que valores existentes não sejam sobrescritos por NULL
    caso o feed não forneça esses campos.
    """
    title    = (getattr(feed_obj, "title", "") or "").strip() or None
    site_url = (getattr(feed_obj, "link",  "") or "").strip() or None
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            """
            UPDATE feeds
               SET title           = COALESCE(?, title),
                   site_url        = COALESCE(?, site_url),
                   last_fetched_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                   error_count     = 0,
                   last_error      = NULL
             WHERE id = ?
            """,
            (title, site_url, feed_id),
        )
        _conn.commit()
        log.debug("Metadados do feed %d atualizados (title=%s).", feed_id, title)
    except sqlite3.Error as exc:
        log.error("Falha ao atualizar metadados do feed %d: %s", feed_id, exc)
        raise
    finally:
        if should_close:
            _conn.close()


def record_feed_error(
    feed_id: int,
    error_msg: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Registra falha de fetch: incrementa error_count e salva last_error."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            """
            UPDATE feeds
               SET error_count = error_count + 1,
                   last_error   = ?
             WHERE id = ?
            """,
            (error_msg[:500], feed_id),
        )
        _conn.commit()
        log.warning("Feed %d: erro registrado (%s).", feed_id, error_msg[:80])
    except sqlite3.Error as exc:
        log.error("Falha ao registrar erro do feed %d: %s", feed_id, exc)
    finally:
        if should_close:
            _conn.close()


def fetch_and_save(feed_id: int, feed_url: str) -> int:
    """Pipeline completo: busca, parseia, salva artigos e atualiza metadados do feed.

    Em caso de falha (rede ou feed inválido), registra erro na tabela feeds
    e retorna -1. Nunca propaga exceção — FetchWorker não precisa de try/except
    por feed individual.

    Returns:
        Número de artigos novos inseridos, ou -1 em caso de falha.
    """
    log.info("fetch_and_save: feed_id=%d url=%s", feed_id, feed_url)
    try:
        feed_obj, entries = fetch_feed(feed_url)
    except (requests.RequestException, ValueError) as exc:
        record_feed_error(feed_id, str(exc))
        return -1

    conn = get_conn()
    try:
        count = save_new_articles(feed_id, entries, conn)
        update_feed_meta(feed_id, feed_obj, conn)
    finally:
        conn.close()

    log.info("fetch_and_save concluído: feed_id=%d novos=%d", feed_id, count)
    return count
