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
