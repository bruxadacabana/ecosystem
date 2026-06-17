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

    # Espelho no store compartilhado (sync_root) — best-effort, não bloqueia.
    try:
        import asyncio
        import shared_history  # type: ignore
        await asyncio.to_thread(shared_history.record_click, url, query, position)
    except Exception:
        pass


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


async def get_search_sessions(
    db: aiosqlite.Connection,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Retorna sessões de busca agrupadas por session_id, mais recentes primeiro.

    Cada sessão contém as queries distintas feitas e os links clicados.
    Sessões sem session_id são ignoradas.
    """
    session_rows = await (await db.execute(
        """SELECT session_id, MIN(timestamp) AS t_start, MAX(timestamp) AS t_end,
                  COUNT(*) AS click_count
           FROM click_log
           WHERE session_id != ''
           GROUP BY session_id
           ORDER BY t_end DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    )).fetchall()

    if not session_rows:
        return []

    sessions = []
    for sid, t_start, t_end, click_count in session_rows:
        click_rows = await (await db.execute(
            """SELECT url, query_norm, timestamp, position_clicked
               FROM click_log
               WHERE session_id = ?
               ORDER BY timestamp ASC""",
            (sid,),
        )).fetchall()

        seen_set: set[str] = set()
        queries: list[str] = []
        clicks: list[dict] = []
        for url, qnorm, ts, pos in click_rows:
            if qnorm and qnorm not in seen_set:
                queries.append(qnorm)
                seen_set.add(qnorm)
            clicks.append({"url": url, "query_norm": qnorm, "timestamp": ts, "position": pos})

        sessions.append({
            "session_id":    sid,
            "session_start": t_start,
            "session_end":   t_end,
            "queries":       queries,
            "clicks":        clicks,
            "click_count":   click_count,
        })

    return sessions


async def count_search_sessions(db: aiosqlite.Connection) -> int:
    """Conta sessões distintas com session_id não-vazio."""
    row = await (await db.execute(
        "SELECT COUNT(DISTINCT session_id) FROM click_log WHERE session_id != ''"
    )).fetchone()
    return row[0] if row else 0


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
