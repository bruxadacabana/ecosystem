"""
AKASHA — Sugestão automática de novos domínios para a Biblioteca.

Cruza 3 sinais para identificar domínios relevantes não ainda indexados:
  1. search_cache  — domínios que aparecem em resultados de busca salvos
  2. click_log     — domínios clicados pelo usuário (ponderado por 1/log2(2+pos))
  3. page_links    — domínios referenciados nas páginas já crawleadas

Domínios já em crawl_sites ou com status='blocked' são descartados.
Resultado salvo em site_suggestions (upsert por domain, preserva status blocked).
"""
from __future__ import annotations

import json
import logging
import math
import time
from collections import defaultdict
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    import aiosqlite

log = logging.getLogger("akasha.suggester")


def _netloc(url: str) -> str:
    """Extrai netloc limpo de uma URL. Retorna '' se inválida."""
    try:
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return parsed.netloc.lstrip("www.")
        return ""
    except Exception:
        return ""


async def compute_suggestions(
    db: "aiosqlite.Connection",
    min_score: float = 1.0,
    limit: int = 50,
) -> int:
    """Calcula e persiste sugestões de domínios em site_suggestions.

    Retorna número de domínios inseridos/atualizados (excluindo bloqueados).
    """
    # Domínios já na biblioteca
    existing_rows = await (await db.execute(
        "SELECT base_url FROM crawl_sites WHERE deleted = 0"
    )).fetchall()
    existing_domains: set[str] = {_netloc(r[0]) for r in existing_rows if r[0]}

    # Domínios bloqueados (não devem ser re-sugeridos)
    blocked_rows = await (await db.execute(
        "SELECT domain FROM site_suggestions WHERE status = 'blocked'"
    )).fetchall()
    blocked_domains: set[str] = {r[0] for r in blocked_rows}

    skip = existing_domains | blocked_domains

    # ── Sinal 1: aparições em search_cache ───────────────────────────────────
    cache_count: dict[str, int] = defaultdict(int)
    cache_rows = await (await db.execute(
        "SELECT results_json FROM search_cache ORDER BY created_at DESC LIMIT 500"
    )).fetchall()
    for (results_json,) in cache_rows:
        try:
            results = json.loads(results_json)
            for item in results:
                url = item.get("url", "")
                domain = _netloc(url)
                if domain and domain not in skip:
                    cache_count[domain] += 1
        except Exception:
            pass

    # ── Sinal 2: cliques ponderados por posição (click_log) ──────────────────
    click_score: dict[str, float] = defaultdict(float)
    try:
        click_rows = await (await db.execute(
            """SELECT url, position_clicked FROM click_log
               WHERE timestamp >= strftime('%s', 'now', '-90 days')"""
        )).fetchall()
        for (url, pos) in click_rows:
            domain = _netloc(url)
            if domain and domain not in skip:
                # peso inversamente proporcional à posição: pos 1 → 1.0, pos 3 → ~0.50
                click_score[domain] += 1.0 / math.log2(2 + (pos or 0))
    except Exception:
        pass  # click_log ainda não existe (item implementado separadamente)

    # ── Sinal 3: domínios externos referenciados em page_links ───────────────
    link_count: dict[str, int] = defaultdict(int)
    try:
        link_rows = await (await db.execute(
            "SELECT target_url FROM page_links"
        )).fetchall()
        for (target_url,) in link_rows:
            domain = _netloc(target_url)
            if domain and domain not in skip:
                link_count[domain] += 1
    except Exception:
        pass

    # ── Score composto ────────────────────────────────────────────────────────
    all_domains = set(cache_count) | set(click_score) | set(link_count)
    scores: list[tuple[str, float, str]] = []
    for domain in all_domains:
        s1 = cache_count.get(domain, 0)
        s2 = click_score.get(domain, 0.0)
        s3 = link_count.get(domain, 0)
        score = float(s1) * 1.0 + s2 * 3.0 + float(s3) * 0.5
        if score < min_score:
            continue

        parts: list[str] = []
        if s1:
            parts.append(f"apareceu em {s1} busca{'s' if s1 != 1 else ''}")
        if s2 > 0:
            parts.append(f"clicado {s2:.1f}× (ponderado por posição)")
        if s3:
            parts.append(f"referenciado em {s3} página{'s' if s3 != 1 else ''}")
        reason = ", ".join(parts)
        scores.append((domain, score, reason))

    # Ordena por score desc, limita
    scores.sort(key=lambda x: x[1], reverse=True)
    scores = scores[:limit]

    if not scores:
        return 0

    now = int(time.time())
    # Upsert: atualiza score/reason se já existir com status pending/ignored;
    # não altera status blocked (já filtrado em skip).
    await db.executemany(
        """INSERT INTO site_suggestions (domain, score, reason, status, updated_at)
           VALUES (?, ?, ?, 'pending', ?)
           ON CONFLICT(domain) DO UPDATE SET
               score      = excluded.score,
               reason     = excluded.reason,
               updated_at = excluded.updated_at
           WHERE status != 'blocked'""",
        [(domain, score, reason, now) for domain, score, reason in scores],
    )
    log.info("compute_suggestions: %d domínios atualizados em site_suggestions", len(scores))
    return len(scores)


async def get_pending_suggestions(
    db: "aiosqlite.Connection",
    limit: int = 30,
) -> list[dict]:
    """Retorna sugestões com status='pending', ordenadas por score desc."""
    rows = await (await db.execute(
        """SELECT domain, score, reason, status, updated_at
           FROM site_suggestions
           WHERE status = 'pending'
           ORDER BY score DESC
           LIMIT ?""",
        (limit,),
    )).fetchall()
    return [
        {
            "domain":     r[0],
            "score":      r[1],
            "reason":     r[2],
            "status":     r[3],
            "updated_at": r[4],
        }
        for r in rows
    ]


async def set_suggestion_status(
    db: "aiosqlite.Connection",
    domain: str,
    status: str,
) -> None:
    """Atualiza o status de uma sugestão. Sem commit — caller responsável."""
    await db.execute(
        "UPDATE site_suggestions SET status = ?, updated_at = ? WHERE domain = ?",
        (status, int(time.time()), domain),
    )
