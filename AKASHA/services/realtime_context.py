"""
AKASHA — Contexto em tempo real
Store em memória para a URL que a usuária está lendo agora (via extensão).
TTL: 30 minutos por entrada. Thread-safe para uso com asyncio.
"""
from __future__ import annotations

import time
from typing import TypedDict

_TTL: float = 30 * 60  # 30 minutos em segundos


class ContextEntry(TypedDict):
    url:           str
    title:         str
    selected_text: str | None
    source:        str
    received_at:   float  # time.monotonic()


_store: dict[str, ContextEntry] = {}


def push(url: str, title: str, selected_text: str | None, source: str) -> None:
    _store[url] = ContextEntry(
        url=url,
        title=title,
        selected_text=selected_text,
        source=source,
        received_at=time.monotonic(),
    )
    _evict()


def get_current() -> ContextEntry | None:
    """Retorna a entrada mais recente ainda dentro do TTL, ou None."""
    _evict()
    if not _store:
        return None
    return max(_store.values(), key=lambda e: e["received_at"])


def get_by_url(url: str) -> ContextEntry | None:
    _evict()
    return _store.get(url)


def all_active() -> list[ContextEntry]:
    _evict()
    return sorted(_store.values(), key=lambda e: e["received_at"], reverse=True)


def _evict() -> None:
    now = time.monotonic()
    expired = [k for k, v in _store.items() if now - v["received_at"] > _TTL]
    for k in expired:
        del _store[k]
