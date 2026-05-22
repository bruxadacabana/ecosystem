"""
AKASHA — Wikipedia knowledge card
Busca o resumo REST da Wikipedia para queries informational.
Segunda chamada em paralelo busca fontes citadas via MediaWiki Action API.
Cache em akasha.db por 7 dias (tabela wiki_cache).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

import aiosqlite
import httpx

from config import DB_PATH

_TTL = 7 * 86400  # 7 dias

# Marcadores de português: diacríticos e palavras funcionais
_PT_DIACRITICS = set("áàãâéêíóõôúçÁÀÃÂÉÊÍÓÕÔÚÇ")
_PT_WORDS = {
    "o que", "como", "por que", "onde", "quando", "quem", "qual",
    "são", "está", "foi", "tem", "era",
}


def _query_hash(query: str) -> str:
    return hashlib.md5(query.lower().strip().encode("utf-8")).hexdigest()


def detect_lang(query: str) -> str:
    """Retorna 'pt' se a query parece portuguesa, 'en' caso contrário."""
    if any(c in _PT_DIACRITICS for c in query):
        return "pt"
    q_lower = query.lower()
    if any(w in q_lower for w in _PT_WORDS):
        return "pt"
    return "en"


def _wiki_slug(query: str) -> str:
    slug = query.strip()
    if slug:
        slug = slug[0].upper() + slug[1:]
    return slug.replace(" ", "_")


async def _get_cache(query_hash: str) -> dict | None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            row = await (await db.execute(
                "SELECT data_json, cached_at FROM wiki_cache WHERE query_hash = ?",
                (query_hash,),
            )).fetchone()
        if not row:
            return None
        data_json, cached_at = row
        if time.time() > cached_at + _TTL:
            return None
        return json.loads(data_json)
    except Exception:
        return None


async def _set_cache(query_hash: str, data: dict) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO wiki_cache (query_hash, data_json, cached_at) "
                "VALUES (?, ?, ?)",
                (query_hash, json.dumps(data), int(time.time())),
            )
            await db.commit()
    except Exception:
        pass


_HEADERS = {"User-Agent": "AKASHA/1.0 (personal search engine; contact: local)"}


async def _fetch_cited_sources(slug: str, lang: str) -> list[str]:
    """Busca URLs externas citadas no artigo via MediaWiki Action API.

    Timeout separado de 3s — falha silenciosa (card aparece sem fontes).
    """
    try:
        async with httpx.AsyncClient(timeout=3.0, headers=_HEADERS) as client:
            resp = await client.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "titles": slug.replace("_", " "),
                    "prop":   "extlinks",
                    "ellimit": "20",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        pages = (data.get("query") or {}).get("pages") or {}
        for page_data in pages.values():
            links = page_data.get("extlinks") or []
            return [lnk.get("*", "") for lnk in links if lnk.get("*")]
    except Exception:
        return []
    return []


async def get_wiki_card(query: str) -> dict | None:
    """Busca resumo + fontes citadas da Wikipedia em paralelo.

    Retorna dict com title/extract/thumbnail_url/page_url/cited_sources ou None.
    cited_sources pode ser [] se a chamada de extlinks falhar/expirar.
    """
    qhash = _query_hash(query)
    cached = await _get_cache(qhash)
    if cached is not None:
        return cached

    lang = detect_lang(query)
    slug = _wiki_slug(query)

    async def _fetch_summary() -> dict | None:
        try:
            async with httpx.AsyncClient(
                timeout=5.0, headers=_HEADERS, follow_redirects=True,
            ) as client:
                resp = await client.get(
                    f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{slug}"
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    # Ambas as chamadas correm em paralelo; falha em sources não cancela o card
    summary_result, sources_result = await asyncio.gather(
        _fetch_summary(),
        _fetch_cited_sources(slug, lang),
        return_exceptions=True,
    )

    data: dict | None = summary_result if not isinstance(summary_result, Exception) else None
    sources: list[str] = (
        sources_result if isinstance(sources_result, list) else []
    )

    if not data:
        return None

    extract = data.get("extract", "").strip()
    if not extract:
        return None

    card: dict = {
        "title":         data.get("title", query),
        "extract":       extract,
        "thumbnail_url": (data.get("thumbnail") or {}).get("source"),
        "page_url":      (data.get("content_urls") or {}).get("desktop", {}).get("page", ""),
        "lang":          lang,
        "cited_sources": [s for s in sources if s],
    }
    await _set_cache(qhash, card)
    return card
