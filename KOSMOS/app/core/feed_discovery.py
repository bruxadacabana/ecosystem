"""
feed_discovery.py — Descoberta e validação de feeds RSS/Atom.

`discover_feeds(site_url)` busca a página do site e acha os feeds anunciados nas tags
`<link rel="alternate" type="application/rss+xml">` (e atom); se nenhum for anunciado,
tenta alguns caminhos comuns (`/feed`, `/rss`…). Devolve candidatos únicos.

`validate_feed(url)` confere se a URL é um feed RSS/Atom válido (via feedparser) e
devolve o título — usado tanto na descoberta quanto na checagem ao adicionar.

Toda rede passa por `_get()` (patchável nos testes). Funções puras, sem Qt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

log = logging.getLogger("kosmos.feed_discovery")

_TIMEOUT = 12
_HEADERS = {"User-Agent": "KOSMOS-feed-discovery/1.0"}
# Caminhos comuns tentados só quando o site não anuncia feeds via <link>.
_COMMON_PATHS = ("/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml")


@dataclass
class FeedCandidate:
    """Um feed encontrado: URL, título e tipo (rss/atom)."""

    url: str
    title: str = ""
    kind: str = "rss"


def _normalize(site_url: str) -> str:
    s = (site_url or "").strip()
    if not s:
        return ""
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def _get(url: str, timeout: int = _TIMEOUT) -> requests.Response:
    """GET com cabeçalho e timeout (ponto único de rede — patchável nos testes)."""
    return requests.get(url, headers=_HEADERS, timeout=timeout)


def validate_feed(url: str) -> tuple[bool, str]:
    """Confere se `url` é um feed RSS/Atom válido. Retorna (ok, título_ou_mensagem_de_erro)."""
    url = _normalize(url)
    if not url:
        return False, "URL vazia."
    try:
        resp = _get(url)
        resp.raise_for_status()
        content = resp.content
    except requests.RequestException as exc:
        log.warning("validate_feed: falha ao buscar %s: %s", url, exc)
        return False, f"Não foi possível acessar o endereço ({exc})."
    parsed = feedparser.parse(content)
    if not parsed.entries and not (parsed.feed and parsed.feed.get("title")):
        return False, "Não parece um feed RSS/Atom válido."
    title = (parsed.feed.get("title") if parsed.feed else "") or url
    return True, str(title).strip()


def discover_feeds(site_url: str) -> list[FeedCandidate]:
    """Descobre os feeds de um site (link rel=alternate; senão, caminhos comuns)."""
    base = _normalize(site_url)
    if not base:
        return []
    candidates: list[FeedCandidate] = []
    seen: set[str] = set()

    # 1) Feeds anunciados na página via <link rel="alternate" type="application/(rss|atom)+xml">
    try:
        resp = _get(base)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("link"):
            rel = " ".join(link.get("rel") or []).lower()
            ltype = (link.get("type") or "").lower()
            if "alternate" not in rel:
                continue
            if not ("rss" in ltype or "atom" in ltype or "xml" in ltype):
                continue
            href = link.get("href")
            if not href:
                continue
            full = urljoin(base, href)
            if full in seen:
                continue
            seen.add(full)
            candidates.append(FeedCandidate(
                url=full,
                title=(link.get("title") or "").strip(),
                kind="atom" if "atom" in ltype else "rss",
            ))
    except requests.RequestException as exc:
        log.warning("discover_feeds: falha ao buscar %s: %s", base, exc)

    # 2) Fallback: caminhos comuns — só se o site não anunciou nenhum feed.
    if not candidates:
        parts = urlparse(base)
        root = f"{parts.scheme}://{parts.netloc}"
        for path in _COMMON_PATHS:
            guess = root + path
            if guess in seen:
                continue
            ok, title = validate_feed(guess)
            if ok:
                seen.add(guess)
                candidates.append(FeedCandidate(url=guess, title=title))

    # Preenche títulos vazios validando o feed.
    for c in candidates:
        if not c.title:
            ok, title = validate_feed(c.url)
            c.title = title if ok else c.url

    log.info("discover_feeds(%s): %d candidato(s).", base, len(candidates))
    return candidates
