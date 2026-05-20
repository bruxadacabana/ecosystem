"""
Mnemosyne — Estado afetivo bidimensional (valência + arousal).

Mesma interface que AKASHA/services/affective_state.py, versão síncrona.
A tabela affective_state fica em personal_memory.db (dados privados da IA).

As dimensões são calculadas pelo chamador (indexer) com os dados disponíveis
em cada contexto; este módulo faz apenas o mapeamento VA e a persistência.

Uso::

    from core.affective_state import record_appraisal, get_current_state

    record_appraisal("doc_indexed", novelty, pleasantness,
                     goal_relevance, coping_potential)
    state = get_current_state()   # {"valence": 0.3, "arousal": 0.5, ...}
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger("mnemosyne.affective_state")

_DDL = """
CREATE TABLE IF NOT EXISTS affective_state (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    event_type        TEXT    NOT NULL,
    event_ref         TEXT             DEFAULT NULL,
    novelty           REAL             DEFAULT NULL,
    pleasantness      REAL             DEFAULT NULL,
    goal_relevance    REAL             DEFAULT NULL,
    coping_potential  REAL             DEFAULT NULL,
    valence           REAL    NOT NULL,
    arousal           REAL    NOT NULL
);
"""
_IDX = "CREATE INDEX IF NOT EXISTS idx_affstate_created ON affective_state(created_at);"


# ── Mapeamento CPM → VA ──────────────────────────────────────────────────────

def compute_va(
    novelty:          float,
    pleasantness:     float,
    goal_relevance:   float,
    coping_potential: float,
) -> tuple[float, float]:
    """Mapeia 4 dimensões CPM de Scherer para (valence ∈ [−1,1], arousal ∈ [0,1]).

    Idêntica à função em AKASHA/services/affective_state.py.
    """
    novelty_sign = 2.0 * coping_potential - 1.0
    valence_raw = (
        (pleasantness    - 0.5) * 1.0
        + novelty * novelty_sign * 0.3
        + (goal_relevance - 0.5) * 0.2
    )
    valence = max(-1.0, min(1.0, valence_raw * 1.5))
    arousal = min(1.0,
        novelty               * 0.50
        + (1.0 - coping_potential) * 0.25
        + goal_relevance      * 0.25
    )
    return round(valence, 4), round(arousal, 4)


# ── DB ───────────────────────────────────────────────────────────────────────

def _get_db() -> Path:
    from core.personal_memory import _get_db as _pm_db
    return _pm_db()


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(_get_db())
    con.execute(_DDL)
    con.execute(_IDX)
    return con


# ── API pública ──────────────────────────────────────────────────────────────

def record_appraisal(
    event_type:       str,
    novelty:          float,
    pleasantness:     float,
    goal_relevance:   float,
    coping_potential: float,
    event_ref:        str | None = None,
) -> None:
    """Calcula VA a partir das dimensões CPM e persiste em affective_state."""
    valence, arousal = compute_va(novelty, pleasantness, goal_relevance, coping_potential)
    try:
        with _conn() as con:
            con.execute(
                """INSERT INTO affective_state
                   (event_type, event_ref, novelty, pleasantness,
                    goal_relevance, coping_potential, valence, arousal)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_type, event_ref,
                 round(novelty, 4), round(pleasantness, 4),
                 round(goal_relevance, 4), round(coping_potential, 4),
                 valence, arousal),
            )
        log.debug(
            "appraisal [%s]: N=%.2f P=%.2f R=%.2f C=%.2f → V=%.3f A=%.3f",
            event_type, novelty, pleasantness, goal_relevance, coping_potential,
            valence, arousal,
        )
    except Exception as exc:
        log.debug("record_appraisal: %s", exc)


def get_current_state(hours: float = 24.0) -> dict[str, float]:
    """Estado afetivo atual — média simples das últimas `hours` horas.

    Placeholder até [M1] implementar decaimento exponencial por tipo de emoção.
    """
    try:
        con = _conn()
        con.row_factory = sqlite3.Row
        row = con.execute(
            """SELECT AVG(valence) v, AVG(arousal) a,
                      AVG(novelty) n, AVG(pleasantness) p,
                      AVG(goal_relevance) g, AVG(coping_potential) c,
                      COUNT(*) cnt
               FROM affective_state
               WHERE created_at >= datetime('now', ?)""",
            (f"-{int(hours)} hours",),
        ).fetchone()
        con.close()
        if row and row["cnt"]:
            return {
                "valence":          round(row["v"] or 0.0, 4),
                "arousal":          round(row["a"] or 0.0, 4),
                "novelty":          round(row["n"] or 0.5, 4),
                "pleasantness":     round(row["p"] or 0.5, 4),
                "goal_relevance":   round(row["g"] or 0.5, 4),
                "coping_potential": round(row["c"] or 0.5, 4),
                "sample_count":     row["cnt"],
            }
    except Exception as exc:
        log.debug("get_current_state: %s", exc)
    return {
        "valence": 0.0, "arousal": 0.0,
        "novelty": 0.5, "pleasantness": 0.5,
        "goal_relevance": 0.5, "coping_potential": 0.5,
        "sample_count": 0,
    }
