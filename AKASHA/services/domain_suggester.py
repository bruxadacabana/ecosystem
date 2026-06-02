"""
AKASHA — Domain Suggester: sugestões proativas de indexação via personal_memory.

Detecta domínios clicados frequentemente em resultados de busca mas não indexados
na Biblioteca. Salva uma entrada de personal_memory do tipo "domain_suggestion"
para que o overlay do browser exiba a sugestão.

Cooldown: um domínio só é sugerido novamente se a sugestão anterior tiver
feedback "dismissed" há mais de 30 dias, ou se nunca tiver sido sugerido.
"""
from __future__ import annotations

import json
import logging

import aiosqlite

from config import DB_PATH

log = logging.getLogger("akasha.domain_suggester")

_SUGGESTION_INTERVAL_HOURS = 2   # roda a cada 2 horas


async def _get_already_suggested_domains() -> set[str]:
    """Retorna domínios que já têm sugestão pendente ou recente em personal_memory.

    "Pendente" = feedback IS NULL (aguardando resposta da usuária).
    "Recente"  = feedback = 'dismissed' há menos de 30 dias.
    Domínios com feedback = 'confirmed' podem ser re-sugeridos se viraram
    candidatos novamente (ex: foram removidos da Biblioteca).
    """
    from services.personal_memory import _get_pm_db
    try:
        async with aiosqlite.connect(_get_pm_db()) as db:
            rows = await (await db.execute(
                """
                SELECT tags FROM personal_memory
                WHERE type = 'domain_suggestion'
                AND (
                    feedback IS NULL
                    OR (feedback = 'dismissed'
                        AND created_at >= datetime('now', '-30 days'))
                )
                """
            )).fetchall()
    except Exception as exc:
        log.debug("domain_suggester: erro ao buscar sugestões existentes: %s", exc)
        return set()

    suggested: set[str] = set()
    for (tags_raw,) in rows:
        try:
            tags = json.loads(tags_raw or "[]")
            for tag in tags:
                if tag != "domain_suggestion":
                    suggested.add(tag)
        except Exception:
            pass
    return suggested


async def check_and_suggest(threshold: int = 3) -> int:
    """Detecta domínios frequentes não indexados e cria sugestões em personal_memory.

    Retorna o número de sugestões criadas nesta rodada.
    """
    from database import get_unindexed_frequent_domains
    from services.personal_memory import save_memory

    candidates = await get_unindexed_frequent_domains(threshold=threshold)
    if not candidates:
        log.debug("domain_suggester: nenhum domínio candidato (threshold=%d)", threshold)
        return 0

    already_suggested = await _get_already_suggested_domains()
    created = 0

    for domain, visit_count in candidates:
        if domain in already_suggested:
            log.debug("domain_suggester: %s já sugerido, ignorando", domain)
            continue

        content = (
            f"Notei que você visitou {domain} {visit_count} "
            f"{'vez' if visit_count == 1 else 'vezes'} nos resultados de busca, "
            f"mas esse domínio ainda não está indexado na Biblioteca. "
            f"Posso adicioná-lo para que apareça diretamente nas suas buscas locais?"
        )
        try:
            mid = await save_memory(
                type="domain_suggestion",
                content=content,
                tags=["domain_suggestion", domain],
                importance=6,
            )
            log.info(
                "domain_suggester: sugestão criada para %s (%d visitas) — id=%s",
                domain, visit_count, mid,
            )
            created += 1
        except Exception as exc:
            log.warning("domain_suggester: falha ao salvar sugestão para %s: %s", domain, exc)

    return created
