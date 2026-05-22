"""
AKASHA — Log de cliques e Learning to Rank (domain_boost)

Registra cada clique da usuária em resultados de busca e computa um
domain_boost semanal via desconto DCG-style: peso = 1/log2(1+posição).
"""
from __future__ import annotations

import math
import time
from urllib.parse import urlparse

import aiosqlite

from config import DB_PATH

_STOPWORDS: frozenset[str] = frozenset({
    "a", "o", "e", "de", "da", "do", "em", "no", "na", "para", "por", "com",
    "que", "se", "não", "um", "uma", "os", "as", "ao", "dos", "das", "é",
    "the", "and", "or", "of", "to", "in", "is", "it", "for", "on", "at",
    "this", "that", "with", "from", "an", "are", "was", "be", "but", "have",
    "mais", "sua", "seu", "ser", "são", "como", "mas", "foi", "pela", "pelo",
})


def _normalize_query(query: str) -> str:
    """Lowercase + remoção de stopwords para agregar variantes da mesma query."""
    tokens = [t for t in query.lower().split() if t not in _STOPWORDS]
    return " ".join(tokens)


def _domain_of(url: str) -> str:
    """Extrai domínio sem www. Retorna '' para file:// e URLs inválidas."""
    try:
        return (urlparse(url).netloc or "").removeprefix("www.").lower()
    except Exception:
        return ""


async def log_click(
    query: str,
    url: str,
    position: int,
    session_id: str = "",
) -> None:
    """Registra um clique no click_log.

    position: 1-indexed (posição do resultado na lista, começando em 1).
    """
    query_norm = _normalize_query(query)
    domain = _domain_of(url)
    ts = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO click_log
               (timestamp, query_norm, url, domain, position_clicked, session_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ts, query_norm, url, domain, position, session_id),
        )
        await db.commit()


def _click_weight(position: int) -> float:
    """Peso DCG para um clique na posição `position` (1-indexed).

    Fórmula: 1 / log2(1 + position)
    - pos=1 → 1.0 (primeiro resultado merece peso máximo)
    - pos=3 → 0.5 (posição 3 tem metade do peso)
    """
    if position < 1:
        position = 1
    return 1.0 / math.log2(1 + position)


async def compute_domain_boosts(db: aiosqlite.Connection) -> int:
    """Calcula domain_boost[domain] = Σ 1/log2(1+pos) para os últimos 90 dias.

    Armazena resultado em domain_boosts. Retorna número de domínios atualizados.
    Job semanal chamado por main.py.
    """
    cutoff = int(time.time()) - 90 * 86400
    rows = await (await db.execute(
        """SELECT domain, position_clicked
           FROM click_log
           WHERE timestamp >= ? AND domain != ''""",
        (cutoff,),
    )).fetchall()

    boosts: dict[str, float] = {}
    for domain, pos in rows:
        boosts[domain] = boosts.get(domain, 0.0) + _click_weight(pos)

    if not boosts:
        return 0

    ts = int(time.time())
    await db.executemany(
        """INSERT INTO domain_boosts (domain, boost, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(domain) DO UPDATE
           SET boost = excluded.boost, updated_at = excluded.updated_at""",
        [(d, b, ts) for d, b in boosts.items()],
    )
    await db.commit()
    return len(boosts)


async def get_domain_boosts(
    db: aiosqlite.Connection,
    domains: list[str],
) -> dict[str, float]:
    """Retorna dict domain → boost para os domínios solicitados.

    Domínios sem histórico recebem o valor padrão 1.0.
    """
    if not domains:
        return {}
    placeholders = ", ".join("?" * len(domains))
    rows = await (await db.execute(
        f"SELECT domain, boost FROM domain_boosts WHERE domain IN ({placeholders})",
        domains,
    )).fetchall()
    result: dict[str, float] = {d: 1.0 for d in domains}
    for domain, boost in rows:
        result[domain] = boost
    return result
