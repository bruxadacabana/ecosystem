"""Busca em kosmos.db por sobreposição de tags com a query da usuária.

Principio arquitetural: AKASHA é amplificador de pesquisa.
Os artigos do KOSMOS aparecem como resultados suplementares (fator 0.6×)
— aumentam o alcance sem dominar os resultados da biblioteca local.

Silencia completamente se KOSMOS não estiver configurado ou db ausente.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.web_search import SearchResult

log = logging.getLogger("akasha.kosmos_search")

_TOP_K         = 5
_SCORE_FACTOR  = 0.6   # artigos KOSMOS sempre abaixo dos locais
_MIN_OVERLAP   = 1     # mínimo de tokens em comum para aparecer
_STOPWORDS = frozenset({
    "a", "o", "as", "os", "e", "de", "da", "do", "em", "no", "na",
    "um", "uma", "que", "para", "com", "por", "se", "the", "and",
    "of", "in", "to", "is", "it", "on", "at", "or", "an", "as",
})


def _get_db_path() -> Path | None:
    """Retorna caminho para kosmos.db via ecosystem.json. None se não configurado."""
    try:
        _root = str(Path(__file__).parent.parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from ecosystem_client import read_ecosystem  # type: ignore
        eco = read_ecosystem()
        data_path = eco.get("kosmos", {}).get("data_path", "")
        if not data_path:
            return None
        db = Path(data_path) / "kosmos.db"
        return db if db.exists() else None
    except Exception:
        return None


def _tokenize(text: str) -> set[str]:
    """Divide texto em tokens normalizados, filtra stopwords e palavras curtas."""
    tokens = re.findall(r"[a-záéíóúàãõêôâçüñ]+", text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def _search_sync(db_path: Path, query_tokens: set[str], top_k: int) -> list[dict]:
    """Executa query SQLite e retorna lista de dicts com title/url/snippet/score."""
    import sqlite3

    results: list[tuple[float, dict]] = []
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "SELECT title, url, summary, ai_tags, published_at "
            "FROM articles "
            "WHERE ai_tags IS NOT NULL AND title IS NOT NULL AND url IS NOT NULL"
        )
        for title, url, summary, tags_json, pub_at in c.fetchall():
            try:
                tags: list[str] = json.loads(tags_json)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(tags, list):
                continue
            tag_tokens = _tokenize(" ".join(str(t) for t in tags))
            # Também considerar palavras do título para ampliar sobreposição
            title_tokens = _tokenize(title or "")
            overlap = len(query_tokens & (tag_tokens | title_tokens))
            if overlap < _MIN_OVERLAP:
                continue
            score = (overlap / max(len(query_tokens), 1)) * _SCORE_FACTOR
            snippet = (summary or "")[:200].strip()
            results.append((score, {
                "title": title,
                "url": url,
                "snippet": snippet,
                "score": score,
            }))
    finally:
        conn.close()

    results.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in results[:top_k]]


async def search_kosmos(query: str, top_k: int = _TOP_K) -> list["SearchResult"]:
    """Busca assíncrona em kosmos.db — retorna lista de SearchResult."""
    from services.web_search import SearchResult  # import local evita circular

    db_path = _get_db_path()
    if db_path is None:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    try:
        hits = await asyncio.get_event_loop().run_in_executor(
            None, _search_sync, db_path, query_tokens, top_k
        )
    except Exception as exc:
        log.debug("kosmos_search falhou: %s", exc)
        return []

    return [
        SearchResult(
            title=h["title"],
            url=h["url"],
            snippet=h["snippet"],
            source="KOSMOS",
        )
        for h in hits
    ]
