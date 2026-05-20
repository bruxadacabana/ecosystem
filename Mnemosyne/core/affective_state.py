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
import math
import sqlite3
from pathlib import Path

log = logging.getLogger("mnemosyne.affective_state")

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
_MOOD_SCALE = 0.6   # humor é 60% menos intenso que emoções episódicas (ALMA)


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
    try:
        con.execute(_MIGRATION_DECAY)
        con.commit()
    except Exception:
        pass  # coluna já existe
    return con


def _weighted_agg(rows: list, max_age: float | None = None) -> tuple[dict[str, float] | None, int]:
    """Agrega rows com ponderação exp(-t/half_life). Retorna (dict, count) ou (None, 0)."""
    total_w = wv = wa = wn = wp = wg = wc = 0.0
    count = 0
    for r in rows:
        age = r["age_hours"]
        if max_age is not None and age > max_age:
            continue
        t = max(0.0, age)
        w = math.exp(-t / r["decay_half_life_hours"])
        total_w += w
        wv += r["valence"] * w
        wa += r["arousal"] * w
        wn += (r["novelty"]          or 0.5) * w
        wp += (r["pleasantness"]     or 0.5) * w
        wg += (r["goal_relevance"]   or 0.5) * w
        wc += (r["coping_potential"] or 0.5) * w
        count += 1
    if total_w < 0.01:
        return None, 0
    return {
        "valence":          round(wv / total_w, 4),
        "arousal":          round(wa / total_w, 4),
        "novelty":          round(wn / total_w, 4),
        "pleasantness":     round(wp / total_w, 4),
        "goal_relevance":   round(wg / total_w, 4),
        "coping_potential": round(wc / total_w, 4),
    }, count


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

def record_appraisal(
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
    try:
        with _conn() as con:
            con.execute(
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
        log.debug(
            "appraisal [%s]: N=%.2f P=%.2f R=%.2f C=%.2f → V=%.3f A=%.3f hl=%.1fh",
            event_type, novelty, pleasantness, goal_relevance, coping_potential,
            valence, arousal, half_life,
        )
    except Exception as exc:
        log.debug("record_appraisal: %s", exc)


def _get_feedback_stats(recent_n: int = 20) -> dict[str, int]:
    """Contagens de feedback recente e histórico longo — base para o momentum."""
    try:
        con = sqlite3.connect(_get_db())
        rows = con.execute(
            """SELECT feedback FROM personal_memory
               WHERE feedback IN ('confirmed', 'dismissed')
               ORDER BY id DESC LIMIT ?""",
            (recent_n,),
        ).fetchall()
        recent_total     = len(rows)
        recent_confirmed = sum(1 for r in rows if r[0] == "confirmed")
        row = con.execute(
            """SELECT
                 SUM(CASE WHEN feedback='confirmed' THEN 1 ELSE 0 END),
                 COUNT(*)
               FROM personal_memory
               WHERE feedback IN ('confirmed', 'dismissed')""",
        ).fetchone()
        con.close()
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


def record_approval_momentum(recent_n: int = 20) -> None:
    """Calcula approval momentum e registra appraisal se threshold atingido.

    Lockwood et al. (PNAS 2022): autoestima funcional derivada do momentum
    (taxa de mudança do feedback), não da média cumulativa.
    Versão síncrona — idêntica à AKASHA/services/affective_state.py.
    """
    stats = _get_feedback_stats(recent_n)
    if stats["recent_total"] < 5:
        return
    ratio_recent   = stats["recent_confirmed"] / stats["recent_total"]
    ratio_baseline = (
        stats["all_confirmed"] / stats["all_total"]
        if stats["all_total"] > 0 else 0.5
    )
    momentum  = ratio_recent - ratio_baseline
    intensity = abs(momentum)
    # Threshold ajustado pelo humor (ALMA: mood positivo → buffer para emoções negativas)
    threshold = 0.15
    try:
        state = get_current_state()
        mood_v = state.get("mood_valence", 0.0)
        if momentum < 0 and mood_v > 0.3:
            threshold += mood_v * 0.1
        elif momentum > 0 and mood_v < -0.3:
            threshold += abs(mood_v) * 0.1
    except Exception:
        pass
    if intensity < threshold:
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
    record_appraisal(
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


def record_query_appraisal(query_text: str, event_ref: str | None = None) -> None:
    """Registra appraisal gerado por query da usuária, usando topic_interest_profile.

    Calcula pleasantness e coping_potential a partir da familiaridade com os
    tópicos da query. Análogo a _record_doc_appraisal no AKASHA/knowledge_worker.
    A apprisação deve acontecer ANTES de atualizar o perfil de interesse (bulk_update_from_text),
    para refletir o estado do conhecimento antes da query.
    """
    try:
        from core.topic_profile import extract_keywords, get_topic_scores_for_list
        keywords = extract_keywords(query_text)
        if not keywords:
            return
        scores = get_topic_scores_for_list(keywords)
        known_scores = [v for v in scores.values() if v > 0]
        avg_score = sum(known_scores) / len(known_scores) if known_scores else 0.0
        familiarity = min(1.0, avg_score / 20.0)
        pleasantness      = round(familiarity, 4)
        coping_potential  = round(len(known_scores) / len(keywords), 4)
        novelty           = round(1.0 - familiarity, 4)
        goal_relevance    = 1.0   # query direta da usuária = relevância máxima
        record_appraisal(
            "user_query", novelty, pleasantness, goal_relevance, coping_potential,
            event_ref=event_ref,
        )
    except Exception as exc:
        log.debug("record_query_appraisal: %s", exc)


def get_current_state(
    episodic_hours: float = 12.0,
    mood_hours:     float = 48.0,
) -> dict[str, float]:
    """Estado afetivo em duas camadas: episódico (recente) + humor/mood (acumulado).

    ALMA (Gebhard 2005): emoções episódicas alimentam humor de fundo de menor
    intensidade (_MOOD_SCALE). O humor modula thresholds para novas emoções —
    humor positivo dificulta registrar negativos; humor negativo dificulta positivos.

    Retorna valence/arousal/... (episódico) + mood_valence/mood_arousal (humor).
    """
    _baseline = {
        "valence": 0.0, "arousal": 0.0,
        "novelty": 0.5, "pleasantness": 0.5,
        "goal_relevance": 0.5, "coping_potential": 0.5,
        "sample_count": 0,
        "mood_valence": 0.0, "mood_arousal": 0.0,
    }
    try:
        con = _conn()
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT valence, arousal, novelty, pleasantness,
                      goal_relevance, coping_potential, decay_half_life_hours,
                      (julianday('now') - julianday(created_at)) * 24.0 AS age_hours
               FROM affective_state
               WHERE created_at >= datetime('now', ?)
                 AND decay_half_life_hours > 0""",
            (f"-{int(mood_hours)} hours",),
        ).fetchall()
        con.close()

        if not rows:
            return _baseline

        epi, epi_count = _weighted_agg(rows, max_age=episodic_hours)
        mood_raw, _    = _weighted_agg(rows)

        result = dict(_baseline)
        if epi:
            result.update(epi)
            result["sample_count"] = epi_count
        if mood_raw:
            result["mood_valence"] = round(mood_raw["valence"] * _MOOD_SCALE, 4)
            result["mood_arousal"] = round(mood_raw["arousal"] * _MOOD_SCALE, 4)
        return result
    except Exception as exc:
        log.debug("get_current_state: %s", exc)
    return _baseline
