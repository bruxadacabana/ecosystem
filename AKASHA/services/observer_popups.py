"""
AKASHA — Akasha observadora: pop-ups proativos baseados em comportamento.

Detectores que rodam em background (camada assistente, P3) e criam entradas de
personal_memory que o overlay do browser exibe. Cada tipo de entrada tem uma ação
própria no botão de confirmação (ver routers/search.py:insight_feedback):

  - search_dead_end                  → "Adicionar à Biblioteca" os domínios sugeridos
  - unarchived_frequent_visit        → "Arquivar" a URL
  - stale_domain_with_recent_interest→ "Recrawlear" o site

Nenhum detector bloqueia a ferramenta de busca — falhas são suprimidas (graceful).
Bancos: lê akasha.db (comportamento) e escreve em personal_memory.db (sugestões).
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

import aiosqlite

import services.personal_memory as _pm
from config import DB_PATH
from services.click_log import _normalize_query

log = logging.getLogger("akasha.observer_popups")


# ---------------------------------------------------------------------------
# Helpers compartilhados
# ---------------------------------------------------------------------------

async def _get_library_domains() -> set[str]:
    """Domínios já indexados na Biblioteca (crawl_sites não deletados, sem www.)."""
    domains: set[str] = set()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                "SELECT base_url FROM crawl_sites WHERE deleted = 0"
            )).fetchall()
    except Exception:
        return domains
    for (base_url,) in rows:
        try:
            netloc = (urlparse(base_url).netloc or "").removeprefix("www.").lower()
            if netloc:
                domains.add(netloc)
        except Exception:
            pass
    return domains


async def _recently_suggested(entry_type: str, tag: str, hours: int) -> bool:
    """True se já existe sugestão `entry_type` com `tag` criada nas últimas `hours`.

    "Recente" cobre tanto sugestões pendentes (feedback NULL) quanto já respondidas,
    para respeitar o cooldown independente da resposta da usuária.
    """
    try:
        async with aiosqlite.connect(_pm._get_pm_db()) as db:
            rows = await (await db.execute(
                """
                SELECT tags FROM personal_memory
                WHERE type = ?
                  AND created_at >= datetime('now', ?)
                """,
                (entry_type, f"-{int(hours)} hours"),
            )).fetchall()
    except Exception:
        return False
    for (tags_raw,) in rows:
        try:
            if tag in json.loads(tags_raw or "[]"):
                return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# 1. Zona morta de busca (search_dead_end)
# ---------------------------------------------------------------------------

async def _find_dead_end_queries(
    search_threshold: int, max_local_clicks: int,
) -> list[tuple[str, int]]:
    """Queries buscadas >= search_threshold na última semana com poucos cliques locais.

    "Clique local" = clique cujo domínio está na Biblioteca. Uma query repetida que
    raramente leva a um clique em conteúdo indexado é uma lacuna do índice local.
    Retorna lista de (query_original, count).
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            sh_rows = await (await db.execute(
                """
                SELECT query, count FROM search_history
                WHERE count >= ?
                  AND last_used >= datetime('now', '-7 days')
                ORDER BY count DESC
                LIMIT 20
                """,
                (search_threshold,),
            )).fetchall()
            if not sh_rows:
                return []

            library = await _get_library_domains()
            out: list[tuple[str, int]] = []
            for query, count in sh_rows:
                qnorm = _normalize_query(query)
                if not qnorm:
                    continue
                click_rows = await (await db.execute(
                    "SELECT domain FROM click_log WHERE query_norm = ?",
                    (qnorm,),
                )).fetchall()
                local_clicks = sum(
                    1 for (d,) in click_rows
                    if (d or "").removeprefix("www.") in library
                )
                if local_clicks <= max_local_clicks:
                    out.append((query, count))
            return out
    except Exception as exc:
        log.debug("observer: _find_dead_end_queries erro: %s", exc)
        return []


async def _get_domain_suggestions_for_query(query: str, max_suggestions: int = 3) -> list[str]:
    """Busca web leve e extrai domínios dos top resultados, fora da Biblioteca.

    Camada assistente: usa a busca web da ferramenta apenas como fonte de candidatos.
    Falha graciosamente (LOGOS/SearXNG offline → lista vazia).
    """
    try:
        from services.web_search import search_web
        results = await search_web(query, max_results=10)
    except Exception as exc:
        log.debug("observer: busca web para sugestão falhou (%s): %s", query, exc)
        return []

    library = await _get_library_domains()
    seen: set[str] = set()
    out: list[str] = []
    for r in results or []:
        url = getattr(r, "url", "") or ""
        domain = (urlparse(url).netloc or "").removeprefix("www.").lower()
        if not domain or domain in library or domain in seen:
            continue
        seen.add(domain)
        out.append(domain)
        if len(out) >= max_suggestions:
            break
    return out


async def check_search_dead_ends(
    search_threshold: int = 3,
    max_local_clicks: int = 1,
    cooldown_hours: int = 24,
    max_suggestions: int = 3,
) -> int:
    """Detecta zonas mortas de busca e cria sugestões de indexação. Retorna nº criadas."""
    candidates = await _find_dead_end_queries(search_threshold, max_local_clicks)
    if not candidates:
        return 0

    created = 0
    for query, count in candidates:
        if await _recently_suggested("search_dead_end", query, cooldown_hours):
            continue
        domains = await _get_domain_suggestions_for_query(query, max_suggestions)
        if not domains:
            continue
        lista = ", ".join(domains)
        content = (
            f"Você buscou '{query}' {count} "
            f"{'vez' if count == 1 else 'vezes'} sem encontrar muito no índice local — "
            f"posso indexar estes domínios sobre o assunto? {lista}"
        )
        try:
            mid = await _pm.save_memory(
                type="search_dead_end",
                content=content,
                tags=["search_dead_end", query, *domains],
                importance=6,
            )
            log.info(
                "observer: zona morta '%s' (%d buscas) → sugeridos %s (id=%s)",
                query, count, lista, mid,
            )
            created += 1
        except Exception as exc:
            log.warning("observer: falha ao salvar sugestão de zona morta '%s': %s", query, exc)
    return created


# ---------------------------------------------------------------------------
# 2. Página visitada frequentemente sem arquivo (unarchived_frequent_visit)
# ---------------------------------------------------------------------------

async def _find_unarchived_frequent_visits(
    visit_threshold: int,
) -> list[tuple[str, str, int]]:
    """URLs visitadas >= visit_threshold (activity_log type='visit') e não arquivadas.

    "Não arquivada" = url ausente de archive_simhashes. Páginas que a usuária revisita
    mas nunca salvou são candidatas a desaparecer — vale oferecer arquivamento.
    Retorna lista de (url, title, visit_count).
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                """
                SELECT url, MAX(title) AS title, COUNT(*) AS visits
                FROM activity_log
                WHERE type = 'visit' AND url LIKE 'http%'
                GROUP BY url
                HAVING visits >= ?
                ORDER BY visits DESC
                LIMIT 20
                """,
                (visit_threshold,),
            )).fetchall()
            if not rows:
                return []
            out: list[tuple[str, str, int]] = []
            for url, title, visits in rows:
                archived = await (await db.execute(
                    "SELECT 1 FROM archive_simhashes WHERE url = ? LIMIT 1", (url,)
                )).fetchone()
                if archived:
                    continue
                out.append((url, (title or "").strip() or url, int(visits)))
            return out
    except Exception as exc:
        log.debug("observer: _find_unarchived_frequent_visits erro: %s", exc)
        return []


async def check_unarchived_frequent_visits(
    visit_threshold: int = 3,
    cooldown_hours: int = 24,
) -> int:
    """Detecta páginas revisitadas mas não arquivadas e oferece arquivamento.

    Cria entradas `unarchived_frequent_visit` em personal_memory (ação de confirmação:
    arquivar a URL — ver routers/search.py). Retorna nº de sugestões criadas.
    """
    candidates = await _find_unarchived_frequent_visits(visit_threshold)
    if not candidates:
        return 0

    created = 0
    for url, title, visits in candidates:
        if await _recently_suggested("unarchived_frequent_visit", url, cooldown_hours):
            continue
        label = title if title and title != url else url
        content = (
            f"Você visita '{label}' com frequência ({visits} "
            f"{'vez' if visits == 1 else 'vezes'}) mas essa página não está no seu "
            f"arquivo — salvar agora?"
        )
        try:
            mid = await _pm.save_memory(
                type="unarchived_frequent_visit",
                content=content,
                tags=["unarchived_frequent_visit", url],
                importance=6,
            )
            log.info(
                "observer: visita frequente sem arquivo '%s' (%d) (id=%s)",
                url, visits, mid,
            )
            created += 1
        except Exception as exc:
            log.warning(
                "observer: falha ao salvar sugestão de arquivo '%s': %s", url, exc
            )
    return created


# ---------------------------------------------------------------------------
# 3. Domínio indexado desatualizado com interesse recente
#    (stale_domain_with_recent_interest)
# ---------------------------------------------------------------------------

async def _domain_has_recent_interest(
    db: aiosqlite.Connection, domain: str, recent_days: int,
) -> bool:
    """True se houve visita (activity_log) ou clique (click_log) no domínio recentemente.

    Freshness guiada por comportamento: só vale recrawlear o que a usuária ainda usa.
    """
    visit = await (await db.execute(
        """
        SELECT 1 FROM activity_log
        WHERE type = 'visit' AND url LIKE ?
          AND created_at >= datetime('now', ?)
        LIMIT 1
        """,
        (f"%//{domain}%", f"-{int(recent_days)} days"),
    )).fetchone()
    if visit:
        return True
    click = await (await db.execute(
        """
        SELECT 1 FROM click_log
        WHERE (domain = ? OR domain = ?)
          AND timestamp >= strftime('%s', 'now', ?)
        LIMIT 1
        """,
        (domain, f"www.{domain}", f"-{int(recent_days)} days"),
    )).fetchone()
    return bool(click)


async def _find_stale_domains_with_interest(
    stale_days: int, recent_days: int,
) -> list[tuple[int, str, int]]:
    """Sites crawleados há > stale_days mas com interesse recente (< recent_days).

    Retorna lista de (site_id, domain, age_days). "Interesse recente" = visita ou
    clique no domínio dentro da janela recent_days.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                """
                SELECT id, base_url,
                       CAST(julianday('now') - julianday(last_crawled_at) AS INTEGER) AS age_days
                FROM crawl_sites
                WHERE deleted = 0
                  AND last_crawled_at IS NOT NULL
                  AND last_crawled_at < datetime('now', ?)
                ORDER BY age_days DESC
                LIMIT 20
                """,
                (f"-{int(stale_days)} days",),
            )).fetchall()
            if not rows:
                return []

            out: list[tuple[int, str, int]] = []
            for site_id, base_url, age_days in rows:
                domain = (urlparse(base_url).netloc or "").removeprefix("www.").lower()
                if not domain:
                    continue
                if await _domain_has_recent_interest(db, domain, recent_days):
                    out.append((int(site_id), domain, int(age_days or stale_days)))
            return out
    except Exception as exc:
        log.debug("observer: _find_stale_domains_with_interest erro: %s", exc)
        return []


async def check_stale_domains_with_interest(
    stale_days: int = 45,
    recent_days: int = 14,
    cooldown_hours: int = 24,
) -> int:
    """Detecta domínios indexados desatualizados que a usuária ainda usa e oferece recrawl.

    Cria entradas `stale_domain_with_recent_interest` em personal_memory (ação de
    confirmação: recrawlear o site — ver routers/search.py). Retorna nº criadas.
    """
    candidates = await _find_stale_domains_with_interest(stale_days, recent_days)
    if not candidates:
        return 0

    created = 0
    for site_id, domain, age_days in candidates:
        if await _recently_suggested("stale_domain_with_recent_interest", domain, cooldown_hours):
            continue
        content = (
            f"O site {domain} foi indexado há {age_days} dias e você o visita "
            f"bastante — recrawlear para atualizar o índice?"
        )
        try:
            mid = await _pm.save_memory(
                type="stale_domain_with_recent_interest",
                content=content,
                tags=["stale_domain_with_recent_interest", str(site_id), domain],
                importance=6,
            )
            log.info(
                "observer: domínio desatualizado '%s' (%dd, site=%d) (id=%s)",
                domain, age_days, site_id, mid,
            )
            created += 1
        except Exception as exc:
            log.warning(
                "observer: falha ao salvar sugestão de recrawl '%s': %s", domain, exc
            )
    return created
