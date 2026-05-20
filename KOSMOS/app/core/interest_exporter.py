"""Exporta interesses de engajamento do KOSMOS para o interests.json compartilhado.

Fontes de sinal (peso decrescente):
  - Tags manuais da usuária (tabela tags)    → 5.0 — intenção explícita
  - Artigos salvos (is_saved=1) + ai_tags    → 3.0 — relevância confirmada
  - Artigos lidos (is_read=1) + ai_tags      → 1.0 — engajamento passivo

Cooldown de 1 hora evita I/O excessivo quando feed_updated dispara por feed.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("kosmos.interest_exporter")

_COOLDOWN_S: float = 3600.0   # 1 hora entre exports
_TOP_N: int        = 20
_W_TAG:   float    = 5.0
_W_SAVED: float    = 3.0
_W_READ:  float    = 1.0

_last_export_at: float      = 0.0
_export_lock:    threading.Lock = threading.Lock()


def export_interests(db_path: Path) -> None:
    """Dispara exportação em thread daemon com cooldown de 1 hora."""
    t = threading.Thread(
        target=_guarded_export,
        args=(db_path,),
        daemon=True,
        name="kosmos-interest-export",
    )
    t.start()


def _guarded_export(db_path: Path) -> None:
    global _last_export_at
    now = time.monotonic()
    with _export_lock:
        if now - _last_export_at < _COOLDOWN_S:
            return
        _last_export_at = now
    try:
        _do_export(db_path)
    except Exception as exc:
        log.warning("export_interests falhou: %s", exc)


def _do_export(db_path: Path) -> None:
    import sqlite3

    _root = str(Path(__file__).parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from ecosystem_client import update_interests  # type: ignore

    if not db_path.exists():
        log.debug("kosmos.db não encontrado — skip export")
        return

    scores: dict[str, float] = {}

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()

        # Tags manuais — sinal de intenção explícita da usuária
        c.execute("SELECT DISTINCT name FROM tags")
        for (name,) in c.fetchall():
            t = str(name).strip().lower()
            if t:
                scores[t] = scores.get(t, 0.0) + _W_TAG

        # Artigos salvos com ai_tags
        c.execute(
            "SELECT ai_tags FROM articles WHERE is_saved=1 AND ai_tags IS NOT NULL"
        )
        for (tags_json,) in c.fetchall():
            _accumulate(tags_json, _W_SAVED, scores)

        # Artigos lidos (não salvos) com ai_tags
        c.execute(
            "SELECT ai_tags FROM articles "
            "WHERE is_read=1 AND is_saved=0 AND ai_tags IS NOT NULL"
        )
        for (tags_json,) in c.fetchall():
            _accumulate(tags_json, _W_READ, scores)
    finally:
        conn.close()

    if not scores:
        log.debug("Nenhum sinal de engajamento encontrado — skip export")
        return

    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:_TOP_N]
    max_score = top[0][1]

    topics = [
        {
            "name": name,
            "weight": round(score / max_score, 3),
            "sources": ["kosmos_engagement"],
        }
        for name, score in top
    ]

    update_interests(topics)
    log.info(
        "Interesses exportados: %d tópicos (maior: %s %.2f)",
        len(topics), top[0][0], top[0][1],
    )


def _accumulate(tags_json: str, weight: float, scores: dict[str, float]) -> None:
    try:
        tags = json.loads(tags_json)
        if isinstance(tags, list):
            for tag in tags:
                t = str(tag).strip().lower()
                if t:
                    scores[t] = scores.get(t, 0.0) + weight
    except (json.JSONDecodeError, TypeError):
        pass
