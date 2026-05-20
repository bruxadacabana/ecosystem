"""
AKASHA — Estado afetivo bidimensional (valência + arousal).

Implementa appraisal via 4 dimensões do CPM de Scherer usando dados já
disponíveis em akasha.db / akasha_knowledge.db como proxies:

  • Novelty          — familiaridade dos tópicos no topic_interest_profile
  • Pleasantness     — alinhamento com interesses estabelecidos (mesmo proxy)
  • Goal relevance   — sobreposição com queries recentes em search_history
  • Coping potential — fração dos tópicos já conhecidos no profile

A dimensão de feedback/momentum (item [J]) é adicionada quando implementada.
A tabela affective_state fica em personal_memory.db (dados privados da IA).

Uso::

    from services.affective_state import record_appraisal, get_current_state

    await record_appraisal("doc_indexed", novelty, pleasantness,
                            goal_relevance, coping_potential)
    state = await get_current_state()   # {"valence": 0.3, "arousal": 0.5, ...}
"""
from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

log = logging.getLogger("akasha.affective_state")

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

    Valência:
      - pleasantness é driver primário
      - novelty × coping_potential determina o sinal da novidade:
        alta novelty + alto coping → curiosidade (+);
        alta novelty + baixo coping → confusão (−)
      - goal_relevance: leve boost positivo quando relevante

    Arousal:
      - novelty é driver primário (inesperado = ativação)
      - baixo coping amplifica (incerteza)
      - alta relevância = engajamento ativo
    """
    novelty_sign = 2.0 * coping_potential - 1.0        # ∈ [−1, 1]
    valence_raw = (
        (pleasantness    - 0.5) * 1.0    # [−0.5, 0.5]
        + novelty * novelty_sign * 0.3   # [−0.3, 0.3]
        + (goal_relevance - 0.5) * 0.2  # [−0.1, 0.1]
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
    from services.personal_memory import _get_pm_db
    return _get_pm_db()


async def _ensure_schema(conn: aiosqlite.Connection) -> None:
    await conn.execute(_DDL)
    await conn.execute(_IDX)


# ── API pública ──────────────────────────────────────────────────────────────

async def record_appraisal(
    event_type:       str,
    novelty:          float,
    pleasantness:     float,
    goal_relevance:   float,
    coping_potential: float,
    event_ref:        str | None = None,
) -> None:
    """Calcula VA a partir das dimensões CPM e persiste em affective_state."""
    valence, arousal = compute_va(novelty, pleasantness, goal_relevance, coping_potential)
    async with aiosqlite.connect(_get_db()) as conn:
        await _ensure_schema(conn)
        await conn.execute(
            """INSERT INTO affective_state
               (event_type, event_ref, novelty, pleasantness,
                goal_relevance, coping_potential, valence, arousal)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, event_ref,
             round(novelty, 4), round(pleasantness, 4),
             round(goal_relevance, 4), round(coping_potential, 4),
             valence, arousal),
        )
        await conn.commit()
    log.debug(
        "appraisal [%s]: N=%.2f P=%.2f R=%.2f C=%.2f → V=%.3f A=%.3f",
        event_type, novelty, pleasantness, goal_relevance, coping_potential,
        valence, arousal,
    )


async def get_current_state(hours: float = 24.0) -> dict[str, float]:
    """Estado afetivo atual — média simples das últimas `hours` horas.

    Placeholder até [M1] implementar decaimento exponencial por tipo de emoção.
    Retorna valores neutros se não houver entradas recentes.
    """
    try:
        async with aiosqlite.connect(_get_db()) as conn:
            await _ensure_schema(conn)
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """SELECT AVG(valence) v, AVG(arousal) a,
                          AVG(novelty) n, AVG(pleasantness) p,
                          AVG(goal_relevance) g, AVG(coping_potential) c,
                          COUNT(*) cnt
                   FROM affective_state
                   WHERE created_at >= datetime('now', ?)""",
                (f"-{int(hours)} hours",),
            )
            row = await cur.fetchone()
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
