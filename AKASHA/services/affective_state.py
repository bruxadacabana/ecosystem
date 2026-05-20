"""
AKASHA — Estado afetivo bidimensional (valência + arousal).

Implementa appraisal via 4 dimensões do CPM de Scherer usando dados já
disponíveis em akasha.db / akasha_knowledge.db como proxies:

  • Novelty          — familiaridade dos tópicos no topic_interest_profile
  • Pleasantness     — alinhamento com interesses estabelecidos (mesmo proxy)
  • Goal relevance   — sobreposição com queries recentes em search_history
  • Coping potential — fração dos tópicos já conhecidos no profile

Feedback/momentum (item [J]) via record_approval_momentum() em set_feedback().
A tabela affective_state fica em personal_memory.db (dados privados da IA).

Uso::

    from services.affective_state import record_appraisal, get_current_state

    await record_appraisal("doc_indexed", novelty, pleasantness,
                            goal_relevance, coping_potential)
    state = await get_current_state()   # {"valence": 0.3, "arousal": 0.5, ...}
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import aiosqlite

log = logging.getLogger("akasha.affective_state")

_DDL = """
CREATE TABLE IF NOT EXISTS affective_state (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    event_type            TEXT    NOT NULL,
    event_ref             TEXT             DEFAULT NULL,
    novelty               REAL             DEFAULT NULL,
    pleasantness          REAL             DEFAULT NULL,
    goal_relevance        REAL             DEFAULT NULL,
    coping_potential      REAL             DEFAULT NULL,
    valence               REAL    NOT NULL,
    arousal               REAL    NOT NULL,
    decay_half_life_hours REAL    NOT NULL DEFAULT 6.0
);
"""
_IDX = "CREATE INDEX IF NOT EXISTS idx_affstate_created ON affective_state(created_at);"
_MIGRATION_DECAY = (
    "ALTER TABLE affective_state "
    "ADD COLUMN decay_half_life_hours REAL NOT NULL DEFAULT 6.0"
)


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
    try:
        await conn.execute(_MIGRATION_DECAY)
        await conn.commit()
    except Exception:
        pass  # coluna já existe


def _assign_half_life(event_type: str, valence: float) -> float:
    """Meia-vida em horas por tipo de evento e valência (WASABI/ALMA/EILS).

    Emoções positivas → curta (2-6 h). Emoções negativas → longa (8-24 h):
    sinais de problema persistem funcionalmente até resolução.
    """
    if event_type == "user_query":
        return 3.0
    if event_type == "approval_momentum":
        return 3.0 if valence >= 0 else 16.0
    if event_type == "doc_indexed":
        return 4.0 if valence >= 0 else 12.0
    return 6.0


# ── API pública ──────────────────────────────────────────────────────────────

async def record_appraisal(
    event_type:       str,
    novelty:          float,
    pleasantness:     float,
    goal_relevance:   float,
    coping_potential: float,
    event_ref:        str | None = None,
) -> None:
    """Calcula VA + meia-vida de decaimento e persiste em affective_state."""
    valence, arousal = compute_va(novelty, pleasantness, goal_relevance, coping_potential)
    half_life = _assign_half_life(event_type, valence)
    async with aiosqlite.connect(_get_db()) as conn:
        await _ensure_schema(conn)
        await conn.execute(
            """INSERT INTO affective_state
               (event_type, event_ref, novelty, pleasantness,
                goal_relevance, coping_potential, valence, arousal,
                decay_half_life_hours)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, event_ref,
             round(novelty, 4), round(pleasantness, 4),
             round(goal_relevance, 4), round(coping_potential, 4),
             valence, arousal, half_life),
        )
        await conn.commit()
    log.debug(
        "appraisal [%s]: N=%.2f P=%.2f R=%.2f C=%.2f → V=%.3f A=%.3f hl=%.1fh",
        event_type, novelty, pleasantness, goal_relevance, coping_potential,
        valence, arousal, half_life,
    )


async def _get_feedback_stats(recent_n: int = 20) -> dict[str, int]:
    """Contagens de feedback recente e histórico longo — base para o momentum."""
    try:
        from services.personal_memory import _get_pm_db
        async with aiosqlite.connect(_get_pm_db()) as db:
            rows = await (await db.execute(
                """SELECT feedback FROM personal_memory
                   WHERE feedback IN ('confirmed', 'dismissed')
                   ORDER BY id DESC LIMIT ?""",
                (recent_n,),
            )).fetchall()
            recent_total     = len(rows)
            recent_confirmed = sum(1 for r in rows if r[0] == "confirmed")
            row = await (await db.execute(
                """SELECT
                     SUM(CASE WHEN feedback='confirmed' THEN 1 ELSE 0 END),
                     COUNT(*)
                   FROM personal_memory
                   WHERE feedback IN ('confirmed', 'dismissed')""",
            )).fetchone()
        return {
            "recent_confirmed": recent_confirmed,
            "recent_total":     recent_total,
            "all_confirmed":    int(row[0] or 0),
            "all_total":        int(row[1] or 0),
        }
    except Exception as exc:
        log.debug("_get_feedback_stats: %s", exc)
        return {"recent_confirmed": 0, "recent_total": 0,
                "all_confirmed": 0, "all_total": 0}


async def record_approval_momentum(recent_n: int = 20) -> None:
    """Calcula approval momentum e registra appraisal se threshold atingido.

    Lockwood et al. (PNAS 2022): autoestima funcional derivada do momentum
    (taxa de mudança do feedback), não da média cumulativa.
    momentum = ratio_recent(last N) − ratio_baseline(all-time).
    |momentum| < 0.15 → abaixo do threshold, sem evento.
    momentum > 0.15   → contentamento leve.
    momentum < -0.15  → vigilância/remorse leve.
    Intensidade proporcional ao valor absoluto do momentum.
    """
    stats = await _get_feedback_stats(recent_n)
    if stats["recent_total"] < 5:
        return  # dados insuficientes para momentum significativo
    ratio_recent   = stats["recent_confirmed"] / stats["recent_total"]
    ratio_baseline = (
        stats["all_confirmed"] / stats["all_total"]
        if stats["all_total"] > 0 else 0.5
    )
    momentum  = ratio_recent - ratio_baseline
    intensity = abs(momentum)
    if intensity < 0.15:
        return
    if momentum > 0:            # contentamento leve
        pleasantness     = min(1.0, 0.5 + intensity)
        coping_potential = min(1.0, 0.6 + intensity * 0.4)
        goal_relevance   = 0.7
        novelty          = 0.2
    else:                       # vigilância / remorse leve
        pleasantness     = max(0.0, 0.5 - intensity)
        coping_potential = max(0.1, 0.5 - intensity * 0.4)
        goal_relevance   = 0.6
        novelty          = min(1.0, 0.3 + intensity * 0.2)
    await record_appraisal(
        "approval_momentum",
        novelty, pleasantness, goal_relevance, coping_potential,
        event_ref=(
            f"momentum={momentum:+.3f} "
            f"({stats['recent_confirmed']}/{stats['recent_total']} recent)"
        ),
    )
    log.debug(
        "approval_momentum=%.3f (recent %.2f vs baseline %.2f)",
        momentum, ratio_recent, ratio_baseline,
    )


async def get_current_state(hours: float = 72.0) -> dict[str, float]:
    """Estado afetivo atual com decaimento exponencial por meia-vida.

    Substituiu a média simples por soma ponderada exp(-t/half_life),
    onde t é a idade em horas de cada entrada. Emoções positivas
    decaem rápido (2-6 h); negativas persistem (8-24 h).

    Janela padrão de 72 h captura até ~4-5 meia-vidas do estado mais
    persistente (vigilância/remorse: 16 h).
    """
    _baseline: dict[str, float] = {
        "valence": 0.0, "arousal": 0.0,
        "novelty": 0.5, "pleasantness": 0.5,
        "goal_relevance": 0.5, "coping_potential": 0.5,
        "sample_count": 0,
    }
    try:
        async with aiosqlite.connect(_get_db()) as conn:
            await _ensure_schema(conn)
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """SELECT valence, arousal, novelty, pleasantness,
                          goal_relevance, coping_potential, decay_half_life_hours,
                          (julianday('now') - julianday(created_at)) * 24.0 AS age_hours
                   FROM affective_state
                   WHERE created_at >= datetime('now', ?)
                     AND decay_half_life_hours > 0""",
                (f"-{int(hours)} hours",),
            )
            rows = await cur.fetchall()
            if not rows:
                return _baseline

            total_w = wv = wa = wn = wp = wg = wc = 0.0
            for r in rows:
                t = max(0.0, r["age_hours"])
                w = math.exp(-t / r["decay_half_life_hours"])
                total_w += w
                wv += r["valence"] * w
                wa += r["arousal"] * w
                wn += (r["novelty"]          or 0.5) * w
                wp += (r["pleasantness"]     or 0.5) * w
                wg += (r["goal_relevance"]   or 0.5) * w
                wc += (r["coping_potential"] or 0.5) * w

            if total_w < 0.01:
                return _baseline

            return {
                "valence":          round(wv / total_w, 4),
                "arousal":          round(wa / total_w, 4),
                "novelty":          round(wn / total_w, 4),
                "pleasantness":     round(wp / total_w, 4),
                "goal_relevance":   round(wg / total_w, 4),
                "coping_potential": round(wc / total_w, 4),
                "sample_count":     len(rows),
            }
    except Exception as exc:
        log.debug("get_current_state: %s", exc)
    return _baseline
