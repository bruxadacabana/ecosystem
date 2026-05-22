"""
AKASHA — Freshness decay como sinal de ranking

Aplica desconto de antiguidade somente em queries com termos temporais explícitos.
Fórmula: freshness = 1.0 / (1.0 + ln(1 + dias_desde_publicacao))
  - Documento de hoje → fator ≈ 1.0
  - Documento de 1 ano → fator ≈ 0.145
  - Documento sem data → fator 1.0 (neutro)

O re-ranking combina o ranking original (w=0.7) com um ranking por frescor (w=0.3)
via Reciprocal Rank Fusion — nunca descarta resultados, só ajusta a ordem.
"""
from __future__ import annotations

import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiosqlite

from config import DB_PATH

# ---------------------------------------------------------------------------
# Termos temporais que ativam o sinal de frescor
# ---------------------------------------------------------------------------

_TEMPORAL_TERMS: frozenset[str] = frozenset({
    # Português
    "hoje", "agora", "recente", "recentes", "novo", "novos", "nova", "novas",
    "último", "últimos", "última", "últimas", "atual", "atuais",
    "semana", "semanas", "mês", "meses", "ontem",
    # Inglês
    "today", "now", "latest", "recent", "new", "current", "yesterday",
    "week", "weeks", "month", "months",
    # Anos recentes
    "2026", "2025", "2024",
})


def is_temporal_query(query: str) -> bool:
    """True se a query contém ao menos um termo temporal explícito."""
    tokens = set(re.findall(r'\w+', query.lower()))
    return bool(tokens & _TEMPORAL_TERMS)


# ---------------------------------------------------------------------------
# Frescor
# ---------------------------------------------------------------------------

def _days_since(date_str: str) -> float | None:
    """Converte string de data para dias desde hoje.

    Suporta dois formatos:
    - Float string (Unix timestamp): de local_index_meta.mtime
    - ISO datetime string: de crawl_pages.last_modified_at

    Retorna None se date_str for vazio ou não parseável (→ fator 1.0 neutro).
    """
    if not date_str:
        return None
    now = time.time()

    # Tenta float Unix timestamp (local_index_meta.mtime)
    try:
        ts = float(date_str)
        return max(0.0, (now - ts) / 86400)
    except ValueError:
        pass

    # Tenta ISO datetime string (crawl_pages.last_modified_at)
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %Z",  # HTTP Last-Modified
    ):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
        except ValueError:
            continue

    try:
        dt = datetime.fromisoformat(date_str.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
    except (ValueError, TypeError):
        pass

    return None


def freshness_factor(days: float | None) -> float:
    """Retorna fator de frescor no intervalo (0, 1].

    days=None (sem data) ou days=0 (hoje) → 1.0 (neutro/máximo).
    Quanto mais antigo, mais próximo de 0.
    """
    if days is None:
        return 1.0
    return 1.0 / (1.0 + math.log(1.0 + max(0.0, days)))


# ---------------------------------------------------------------------------
# Lookup de datas no banco
# ---------------------------------------------------------------------------

def _url_to_path(url: str) -> str | None:
    """Converte file:// URL para path absoluto do sistema. None se não for file://."""
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    raw = unquote(parsed.path)
    if sys.platform == "win32" and raw.startswith("/"):
        raw = raw[1:]
    try:
        return str(Path(raw))
    except Exception:
        return None


async def get_dates_for_urls(urls: list[str]) -> dict[str, str]:
    """Retorna dict url → date_str para os URLs fornecidos.

    - file:// → local_index_meta.mtime (float timestamp string)
    - http(s):// → crawl_pages.last_modified_at (ISO date string)
    URLs sem registro no banco não aparecem no dict (caller usa '' como fallback).
    """
    if not urls:
        return {}

    result: dict[str, str] = {}
    file_pairs: list[tuple[str, str]] = []   # (url, path)
    http_urls: list[str] = []

    for u in urls:
        if u.startswith("file://"):
            path = _url_to_path(u)
            if path:
                file_pairs.append((u, path))
        elif u.startswith("http://") or u.startswith("https://"):
            http_urls.append(u)

    async with aiosqlite.connect(DB_PATH) as db:
        # Arquivos locais: mtime de local_index_meta
        if file_pairs:
            paths = [p for _, p in file_pairs]
            ph = ", ".join("?" * len(paths))
            rows = await (await db.execute(
                f"SELECT path, mtime FROM local_index_meta WHERE path IN ({ph})",
                paths,
            )).fetchall()
            path_to_mtime = {row[0]: row[1] for row in rows}
            for url, path in file_pairs:
                if path in path_to_mtime:
                    result[url] = path_to_mtime[path]

        # Páginas crawleadas: last_modified_at de crawl_pages
        if http_urls:
            ph = ", ".join("?" * len(http_urls))
            rows = await (await db.execute(
                f"SELECT url, last_modified_at FROM crawl_pages WHERE url IN ({ph})",
                http_urls,
            )).fetchall()
            for url, last_mod in rows:
                if last_mod:
                    result[url] = last_mod

    return result


# ---------------------------------------------------------------------------
# Re-ranking por frescor (RRF ponderado)
# ---------------------------------------------------------------------------

def apply_freshness_rerank(
    original: list,
    date_map: dict[str, str],
    w_freshness: float = 0.3,
    k: int = 60,
) -> list:
    """Combina ranking original (w=0.7) + freshness ranking (w=0.3) via RRF.

    Resultados sem data em date_map recebem fator 1.0 (neutro), então são
    ordenados no topo do freshness_ranked — não penalizados.
    Retorna a lista original inalterada se não houver dados de data.
    """
    if not original:
        return original

    # Verifica se há ao menos uma data real (fator != 1.0) para fazer valer a pena
    has_real_dates = any(
        _days_since(date_map.get(r.url, "")) is not None
        for r in original
    )
    if not has_real_dates:
        return original

    w_orig = 1.0 - w_freshness

    # Ordena por frescor (factor mais alto = mais recente primeiro)
    freshness_ordered = sorted(
        original,
        key=lambda r: freshness_factor(_days_since(date_map.get(r.url, ""))),
        reverse=True,
    )

    scores: dict[str, float] = {}
    by_url: dict[str, object] = {}

    for rank, r in enumerate(original):
        key = r.url.lower().rstrip("/")
        scores[key] = scores.get(key, 0.0) + w_orig / (k + rank + 1)
        by_url[key] = r

    for rank, r in enumerate(freshness_ordered):
        key = r.url.lower().rstrip("/")
        scores[key] = scores.get(key, 0.0) + w_freshness / (k + rank + 1)
        by_url[key] = r

    ordered = sorted(scores, key=scores.__getitem__, reverse=True)
    return [by_url[key] for key in ordered]
