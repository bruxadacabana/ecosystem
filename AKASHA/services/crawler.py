"""Fase 10 — Buscador de Sites Pessoais: crawler BFS + busca FTS5."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

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

        _ = base_parsed  # mantém referência; filtro de domínio fica no crawl_site
        if clean not in seen:
            seen.add(clean)
            links.append(clean)

    return links
