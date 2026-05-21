"""Exporta interesses de engajamento do KOSMOS para o shared_topic_profile.

Fontes de sinal (peso decrescente):
  - Tags manuais da usuária (tabela tags)    → +5.0 — intenção explícita
  - Artigos salvos (is_saved=1) + ai_tags    → +3.0 — relevância confirmada

Artigos apenas lidos não entram no perfil compartilhado — sinal fraco demais.
Cooldown de 1 hora evita I/O excessivo quando feed_updated dispara por feed.
interests.json continua sendo atualizado como seed de inicialização.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("kosmos.interest_exporter")

_COOLDOWN_S: float = 3600.0
_W_TAG:   float    = 5.0
_W_SAVED: float    = 3.0

_last_export_at: float       = 0.0
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
    import json
    import sqlite3

    _root = str(Path(__file__).parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import shared_topic_profile as _stp  # type: ignore

    if not db_path.exists():
        log.debug("kosmos.db não encontrado — skip export")
        return

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()

        # Tags manuais — intenção explícita da usuária
        c.execute("SELECT DISTINCT name FROM tags")
        for (name,) in c.fetchall():
            t = str(name).strip().lower()
            if t:
                _stp.update_score(t, _W_TAG, "kosmos")

        # Artigos salvos com ai_tags
        c.execute(
            "SELECT ai_tags FROM articles WHERE is_saved=1 AND ai_tags IS NOT NULL"
        )
        for (tags_json,) in c.fetchall():
            _accumulate_to_shared(tags_json, _W_SAVED, _stp)

    finally:
        conn.close()

    # Mantém interests.json atualizado como seed de inicialização para novas máquinas
    _export_seed(db_path)

    log.info("Interesses exportados para shared_topic_profile (kosmos).")


def _accumulate_to_shared(tags_json: str, weight: float, stp: object) -> None:
    import json
    try:
        tags = json.loads(tags_json)
        if isinstance(tags, list):
            topics = [str(tag).strip().lower() for tag in tags if str(tag).strip()]
            if topics:
                stp.update_scores(topics, weight, "kosmos")  # type: ignore[attr-defined]
    except (json.JSONDecodeError, TypeError):
        pass


def _export_seed(db_path: Path) -> None:
    """Atualiza interests.json com top tópicos do shared store (seed para novas máquinas)."""
    try:
        from ecosystem_client import update_interests  # type: ignore
        import shared_topic_profile as _stp  # type: ignore
        top = _stp.get_top_topics(20)
        if not top:
            return
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
    except Exception as exc:
        log.debug("_export_seed falhou: %s", exc)
