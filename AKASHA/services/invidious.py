"""
AKASHA — Busca de vídeos via Invidious.

Instância configurada via akasha.invidious_instance no ecosystem.json.
Fallback para instância pública quando não configurada.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("akasha.invidious")

_DEFAULT_INSTANCE = "https://inv.nadeko.net"
_API_TIMEOUT = 8.0


def _get_instance() -> str:
    """Lê invidious_instance do ecosystem.json; retorna default se ausente."""
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
    """Busca vídeos na instância Invidious configurada.

    Retorna (results, error_message).
    results é lista de dicts com: video_id, title, author, duration,
    thumbnail_url, view_count, invidious_url.
    error_message é None em caso de sucesso.
    """
    import httpx

    instance = _get_instance()
    url = f"{instance}/api/v1/search"
    params = {"q": query, "type": "video"}

    try:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            items = resp.json()
    except httpx.TimeoutException:
        log.debug("invidious: timeout em %s", instance)
        return [], f"Instância Invidious não respondeu ({instance})"
    except Exception as exc:
        log.debug("invidious: erro: %s", exc)
        return [], f"Invidious indisponível: {instance}"

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

    return results, None
