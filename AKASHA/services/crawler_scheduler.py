"""
AKASHA — Frequência adaptativa de crawl.

Classifica domínios em daily/weekly/monthly com base em sinais de URL e
taxa de mudança de conteúdo. Calcula quando o próximo crawl deve ocorrer.

Critérios de classificação (em ordem de prioridade):
  1. URL contém padrão de site dinâmico (news/blog/feed…) → 'daily'
  2. >3 páginas do site mudaram o hash nos últimos 14 dias  → 'daily'
  3. URL contém padrão de documentação estática            → 'monthly'
  4. Default                                               → 'weekly'
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import aiosqlite

CrawlFrequency = Literal["daily", "weekly", "monthly"]

_FREQ_DAYS: dict[str, int] = {
    "daily":   1,
    "weekly":  7,
    "monthly": 30,
}

_VALID_FREQUENCIES = frozenset(_FREQ_DAYS)

# Padrões de URL que indicam alta frequência de atualização
_URL_DAILY = frozenset({
    "news", "blog", "feed", "rss", "noticias", "artigos", "post",
    "updates", "changelog", "releases", "twitter", "mastodon",
})

# Padrões de URL que indicam documentação estática (baixa frequência)
_URL_MONTHLY = frozenset({
    "docs", "doc", "documentation", "wiki", "reference",
    "manual", "handbook", "spec", "api-ref",
})

# Janela para contagem de alterações recentes (em segundos)
_RECENT_WINDOW_SECONDS = 14 * 86400  # 14 dias


def classify_frequency(base_url: str, recent_changes: int) -> CrawlFrequency:
    """Determina a frequência de crawl para um domínio.

    Args:
        base_url:       URL base do site (ex: 'https://news.example.com')
        recent_changes: número de páginas que mudaram o hash nos últimos 14 dias

    Returns:
        'daily', 'weekly' ou 'monthly'
    """
    url_lower = base_url.lower()

    if any(p in url_lower for p in _URL_DAILY):
        return "daily"

    if recent_changes > 3:
        return "daily"

    if any(p in url_lower for p in _URL_MONTHLY):
        return "monthly"

    return "weekly"


def compute_next_crawl_at(last_checked_epoch: float, freq: CrawlFrequency) -> int:
    """Retorna o timestamp Unix quando o próximo crawl deve ocorrer.

    next_crawl_at = last_checked_epoch + interval_days * 86400

    Args:
        last_checked_epoch: timestamp Unix de quando o último crawl foi concluído
        freq:               frequência ('daily', 'weekly', 'monthly')

    Returns:
        Timestamp Unix (int) do próximo crawl agendado.
    """
    days = _FREQ_DAYS.get(freq, 7)
    return int(last_checked_epoch + days * 86400)


async def update_site_schedule(
    site_id: int,
    db: "aiosqlite.Connection",
) -> CrawlFrequency:
    """Atualiza crawl_frequency e next_crawl_at de um site com base na taxa de mudança.

    Conta páginas cujo last_modified_at está dentro dos últimos 14 dias para
    classificar a frequência automaticamente. Não faz commit — o caller é responsável.

    Returns:
        A nova frequência atribuída ('daily', 'weekly' ou 'monthly').
    """
    from datetime import datetime, timezone

    row = await (await db.execute(
        "SELECT base_url FROM crawl_sites WHERE id = ?", (site_id,)
    )).fetchone()
    if not row:
        return "weekly"

    base_url = row[0]
    cutoff_epoch = time.time() - _RECENT_WINDOW_SECONDS
    cutoff_str = datetime.fromtimestamp(cutoff_epoch, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    count_row = await (await db.execute(
        """SELECT COUNT(*) FROM crawl_pages
           WHERE site_id = ?
             AND last_modified_at != ''
             AND last_modified_at >= ?""",
        (site_id, cutoff_str),
    )).fetchone()
    recent_changes = count_row[0] if count_row else 0

    freq = classify_frequency(base_url, recent_changes)
    next_at = compute_next_crawl_at(time.time(), freq)

    await db.execute(
        "UPDATE crawl_sites SET crawl_frequency = ?, next_crawl_at = ? WHERE id = ?",
        (freq, next_at, site_id),
    )
    return freq


async def get_sites_due(
    db: "aiosqlite.Connection",
    now: int | None = None,
) -> list[int]:
    """Retorna IDs dos sites prontos para crawl (next_crawl_at ≤ now e status = 'idle').

    Sites com next_crawl_at = 0 (nunca agendados) são considerados imediatamente devidos.
    Sites marcados como deleted = 1 são ignorados.
    """
    if now is None:
        now = int(time.time())

    rows = await (await db.execute(
        """SELECT id FROM crawl_sites
           WHERE status = 'idle'
             AND deleted = 0
             AND (next_crawl_at = 0 OR next_crawl_at <= ?)""",
        (now,),
    )).fetchall()
    return [r[0] for r in rows]
