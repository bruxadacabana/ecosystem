"""
AKASHA — Busca de vídeos via Invidious.

Instância configurada via akasha.invidious_instance no ecosystem.json.
Se a instância primária falhar, tenta instâncias públicas de fallback
em sequência com timeout de 5s cada. Se todas falharem, retorna lista vazia.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("akasha.invidious")

_DEFAULT_INSTANCE = "https://inv.nadeko.net"
_API_TIMEOUT      = 8.0   # timeout para instância primária (sem concorrência)
_INSTANCE_TIMEOUT = 5.0   # timeout por instância de fallback

# Instâncias públicas de fallback — tentadas em ordem quando a primária falha.
# A instância primária (ecosystem.json) tem prioridade e nunca é repetida.
_FALLBACK_INSTANCES: list[str] = [
    "https://invidious.jotoma.de",
    "https://inv.nadeko.net",
    "https://yt.drgnz.club",
]


def _get_instance() -> str:
    """Lê invidious_instance do ecosystem.json; retorna _DEFAULT_INSTANCE se ausente."""
    try:
        import ecosystem_client as _ec  # type: ignore
        cfg = (_ec.get_akasha_config() or {})
        instance = cfg.get("invidious_instance", "").strip().rstrip("/")
        if instance:
            return instance
    except Exception:
        pass
    return _DEFAULT_INSTANCE


def _format_duration(seconds: int) -> str:
    """Converte segundos em MM:SS ou HH:MM:SS."""
    if seconds <= 0:
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _pick_thumbnail(thumbnails: list[dict]) -> str:
    """Escolhe a melhor thumbnail disponível (medium > default > primeira)."""
    for quality in ("medium", "default", "high"):
        for t in thumbnails:
            if t.get("quality") == quality and t.get("url"):
                return t["url"]
    for t in thumbnails:
        if t.get("url"):
            return t["url"]
    return ""


def _parse_items(items: list, max_results: int, instance: str) -> list[dict]:
    """Converte items da API Invidious em dicts normalizados."""
    results: list[dict] = []
    for item in items[:max_results]:
        try:
            video_id = item.get("videoId", "")
            if not video_id:
                continue
            duration_s = item.get("lengthSeconds", 0) or 0
            results.append({
                "video_id":      video_id,
                "title":         item.get("title", ""),
                "author":        item.get("author", ""),
                "duration":      _format_duration(int(duration_s)),
                "thumbnail_url": _pick_thumbnail(item.get("videoThumbnails") or []),
                "view_count":    item.get("viewCount", 0),
                "invidious_url": f"{instance}/watch?v={video_id}",
            })
        except Exception:
            continue
    return results


async def _try_instance(
    instance: str,
    query: str,
    max_results: int,
    timeout: float,
) -> tuple[list[dict] | None, str | None]:
    """Tenta buscar vídeos em uma instância específica.

    Retorna (results, None) em sucesso ou (None, error_str) em falha.
    Nunca lança exceção — erros são retornados como segundo elemento.
    """
    import httpx

    url = f"{instance}/api/v1/search"
    params = {"q": query, "type": "video"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            items = resp.json()
        return _parse_items(items, max_results, instance), None
    except httpx.TimeoutException:
        log.debug("invidious: timeout em %s (%.1fs)", instance, timeout)
        return None, f"timeout em {instance}"
    except Exception as exc:
        log.debug("invidious: erro em %s: %s", instance, exc)
        return None, str(exc)


async def search_videos_quick(query: str, max: int = 4) -> list[dict]:
    """Versão leve para painel inline na página de busca principal.

    Chama search_videos e retorna no máximo `max` resultados.
    Silenciosa em qualquer falha — retorna [].
    """
    if not query.strip():
        return []
    try:
        results, _ = await search_videos(query, max_results=max)
        log.debug("search_videos_quick: %d resultados q=%r", len(results), query)
        return results[:max]
    except Exception as exc:
        log.debug("search_videos_quick: erro silencioso: %s", exc)
        return []


async def search_videos(
    query: str,
    max_results: int = 15,
) -> tuple[list[dict], Optional[str]]:
    """Busca vídeos com fallback automático entre instâncias Invidious.

    Ordem de tentativa:
      1. Instância configurada em ecosystem.json (timeout _API_TIMEOUT)
      2. Instâncias de _FALLBACK_INSTANCES não-duplicadas (timeout _INSTANCE_TIMEOUT cada)

    Retorna (results, error_message). error_message é None em sucesso.
    """
    primary = _get_instance()

    # Instâncias a tentar: primária + fallbacks que não sejam a primária
    instances = [primary] + [i for i in _FALLBACK_INSTANCES if i.rstrip("/") != primary.rstrip("/")]

    last_error: str | None = None
    for i, inst in enumerate(instances):
        timeout = _API_TIMEOUT if i == 0 else _INSTANCE_TIMEOUT
        results, error = await _try_instance(inst, query, max_results, timeout)
        if results is not None:
            if i > 0:
                log.debug("invidious: sucesso via fallback %s", inst)
            return results, None
        last_error = error
        if i < len(instances) - 1:
            log.debug("invidious: %s falhou (%s) — tentando próxima instância", inst, error)

    log.warning("invidious: todas as instâncias falharam para q=%r (%s)", query, last_error)
    return [], f"Todas as instâncias Invidious indisponíveis. Último erro: {last_error}"
