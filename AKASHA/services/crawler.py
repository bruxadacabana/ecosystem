"""Fase 10 — Buscador de Sites Pessoais: crawler BFS + busca FTS5."""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

log = logging.getLogger("akasha.crawler")

_ASSET_EXTS = re.compile(
    r"\.(css|js|png|jpg|jpeg|gif|svg|webp|ico|woff2?|ttf|eot|pdf|zip|gz|tar"
    r"|mp3|mp4|avi|mov|mkv|exe|dmg|apk)$",
    re.IGNORECASE,
)
_ALLOWED_SCHEMES = {"http", "https"}


def extract_links(html: str, base_url: str) -> list[str]:
    """Extrai links absolutos de `html`, normalizados com `base_url`.

    Descarta: âncoras (#), assets estáticos, esquemas não-http(s),
    parâmetros de fragmento e duplicatas.
    """
    base_parsed = urlparse(base_url)
    seen: set[str] = set()
    links: list[str] = []

    for match in re.finditer(r'href=["\']([^"\'>\s]+)["\']', html, re.IGNORECASE):
        raw = match.group(1).strip()

        # Descarta âncoras puras e javascript:
        if not raw or raw.startswith("#") or raw.lower().startswith("javascript:"):
            continue

        absolute = urljoin(base_url, raw)
        parsed = urlparse(absolute)

        # Esquema não permitido
        if parsed.scheme not in _ALLOWED_SCHEMES:
            continue

        # Remove fragmento, normaliza
        clean = parsed._replace(fragment="").geturl()

        # Assets estáticos
        path_no_qs = parsed.path.split("?")[0]
        if _ASSET_EXTS.search(path_no_qs):
            continue

        # Garante que o host existe (evita links malformados)
        if not parsed.netloc:
            continue

        _ = base_parsed  # filtro de domínio fica no crawl_site
        if clean not in seen:
            seen.add(clean)
            links.append(clean)

    return links


def _root_domain(host: str) -> str:
    """Retorna as duas últimas partes do hostname (domínio raiz sem subdomínio)."""
    parts = host.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


async def discover_subdomains(base_url: str) -> list[str]:
    """Descobre subdomínios vinculados ao mesmo domínio raiz de `base_url`.

    Faz GET na homepage e tenta /sitemap.xml; coleta hosts distintos que
    compartilhem o mesmo domínio raiz e retorna como URLs-base (scheme+host).
    """
    parsed = urlparse(base_url)
    root = _root_domain(parsed.hostname or "")
    found: set[str] = set()

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AKASHA-crawler/1.0)"},
    ) as client:
        for target in [base_url, f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"]:
            try:
                resp = await client.get(target)
                resp.raise_for_status()
                html = resp.text
            except Exception as exc:
                log.debug("discover_subdomains: falha em %s — %s", target, exc)
                continue

            for link in extract_links(html, target):
                lp = urlparse(link)
                host = lp.hostname or ""
                if host and _root_domain(host) == root and host != parsed.hostname:
                    found.add(f"{lp.scheme}://{lp.netloc}")

    return sorted(found)
