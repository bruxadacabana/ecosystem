"""
Mnemosyne — Estado afetivo bidimensional (valência + arousal).

Mesma interface que AKASHA/services/affective_state.py, versão síncrona.
A tabela affective_state fica em personal_memory.db (dados privados da IA).

As dimensões são calculadas pelo chamador (indexer) com os dados disponíveis
em cada contexto; este módulo faz apenas o mapeamento VA e a persistência.

M1: decaimento exponencial por meia-vida diferenciada por tipo de evento e valência.
M2 (ALMA Gebhard 2005): duas camadas temporais.
  • Episódico  — evento específico, alta intensidade, janela 6 h, half-life armazenada.
  • Humor/mood — EWA das últimas 48 h com smoothing de 24 h, intensidade 0.5×,
                 clamped a ±0.5. Representa o contexto afetivo de fundo do dia.
O mood modula thresholds de novos episódicos: eventos que alinham com o humor
são levemente amplificados (+15%); eventos que se opõem são amortecidos (−25%).

Uso::

    from core.affective_state import record_appraisal, get_current_state

    record_appraisal("doc_indexed", novelty, pleasantness,
                     goal_relevance, coping_potential)
    state = get_current_state()
    # {"valence": 0.3, "arousal": 0.5,
    #  "episodic_valence": 0.3, "episodic_arousal": 0.5,
    #  "mood_valence": 0.1, "mood_arousal": 0.3, ...}
"""
from __future__ import annotations

import logging
import math
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("mnemosyne.affective_state")

# ── Parâmetros ALMA ──────────────────────────────────────────────────────────

_EPISODIC_WINDOW_H:  float = 6.0
_MOOD_WINDOW_H:      float = 48.0
_MOOD_SMOOTHING_HL:  float = 24.0
_MOOD_DAMPEN:        float = 0.5
_MOOD_MAX_ABS:       float = 0.5
_MOOD_CACHE_TTL_S:   float = 600.0

_mood_cache:    dict[str, float] = {"valence": 0.0, "arousal": 0.0}
_mood_cache_at: float = 0.0


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

_BASELINE: dict[str, float] = {
    "valence":          0.0,
    "arousal":          0.0,
    "episodic_valence": 0.0,
    "episodic_arousal": 0.0,
    "mood_valence":     0.0,
    "mood_arousal":     0.0,
    "novelty":          0.5,
    "pleasantness":     0.5,
    "goal_relevance":   0.5,
    "coping_potential": 0.5,
    "sample_count":     0,
}


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


def _assign_half_life(event_type: str, valence: float) -> float:
    """Meia-vida em horas por tipo de evento e valência (WASABI/ALMA/EILS)."""
    if event_type == "user_query":
        return 3.0
    if event_type == "approval_momentum":
        return 3.0 if valence >= 0 else 16.0
    if event_type == "doc_indexed":
        return 4.0 if valence >= 0 else 12.0
    return 6.0


# ── Modulação de threshold por humor (ALMA M2) ───────────────────────────────

def _apply_mood_modulation(valence: float) -> float:
    """Modula nova emoção episódica pelo humor de fundo (ALMA threshold effect).

    Humor positivo → emoções positivas amplificadas (+15%), negativas amortecidas (−25%).
    Humor negativo → emoções negativas amplificadas, positivas amortecidas.
    """
    mv = _mood_cache.get("valence", 0.0)
    if abs(mv) < 0.05:
        return valence
    if mv * valence > 0:
        return round(valence * (1.0 + abs(mv) * 0.15), 4)
    else:
        return round(valence * (1.0 - abs(mv) * 0.25), 4)


def _weighted_va(rows: list, smoothing_hl: float | None, dampen: float) -> tuple[float, float]:
    """Média ponderada exponencial de (valence, arousal) sobre rows."""
    total_w = wv = wa = 0.0
    for r in rows:
        t  = max(0.0, r["age_hours"])
        hl = smoothing_hl if smoothing_hl is not None else r["decay_half_life_hours"]
        w  = math.exp(-t / hl)
        total_w += w
        wv += r["valence"] * w
        wa += r["arousal"] * w
    if total_w < 0.01:
        return 0.0, 0.0
    return round((wv / total_w) * dampen, 4), round((wa / total_w) * dampen, 4)


# ── API pública ──────────────────────────────────────────────────────────────

def record_appraisal(
    event_type:       str,
    novelty:          float,
    pleasantness:     float,
    goal_relevance:   float,
    coping_potential: float,
    event_ref:        str | None = None,
) -> None:
    """Calcula VA + meia-vida de decaimento e persiste em affective_state.

    Aplica modulação de threshold pelo humor de fundo (M2): eventos que alinham
    com o humor são levemente amplificados; os que se opõem são amortecidos.
    """
    valence, arousal = compute_va(novelty, pleasantness, goal_relevance, coping_potential)
    half_life = _assign_half_life(event_type, valence)
    valence   = _apply_mood_modulation(valence)  # M2: threshold via mood
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
            "appraisal [%s]: N=%.2f P=%.2f R=%.2f C=%.2f → V=%.3f A=%.3f hl=%.1fh (mood=%.2f)",
            event_type, novelty, pleasantness, goal_relevance, coping_potential,
            valence, arousal, half_life, _mood_cache.get("valence", 0.0),
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
    if intensity < 0.15:
        return
    if momentum > 0:
        pleasantness     = min(1.0, 0.5 + intensity)
        coping_potential = min(1.0, 0.6 + intensity * 0.4)
        goal_relevance   = 0.7
        novelty          = 0.2
    else:
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
    tópicos da query. A appraisal deve acontecer ANTES de atualizar o perfil de
    interesse (bulk_update_from_text), para refletir o estado antes da query.
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
        goal_relevance    = 1.0
        record_appraisal(
            "user_query", novelty, pleasantness, goal_relevance, coping_potential,
            event_ref=event_ref,
        )
    except Exception as exc:
        log.debug("record_query_appraisal: %s", exc)


def get_current_state() -> dict[str, float]:
    """Estado afetivo atual com duas camadas temporais (M2/ALMA).

    Episódico (episodic_valence/arousal):
        Eventos das últimas 6 h com decaimento exponencial por meia-vida
        armazenada. Alta intensidade — reflete eventos recentes específicos.

    Humor (mood_valence/arousal):
        EWA das últimas 48 h com smoothing de 24 h, dampened 0.5×.
        Clamped a ±0.5. Representa o contexto afetivo de fundo.

    valence/arousal são aliases para episodic_valence/arousal (retrocompatibilidade).
    Atualiza o cache de humor usado por record_appraisal para modulação de threshold.
    """
    global _mood_cache, _mood_cache_at
    try:
        con = _conn()
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT valence, arousal, novelty, pleasantness,
                      goal_relevance, coping_potential, decay_half_life_hours,
                      (julianday('now') - julianday(created_at)) * 24.0 AS age_hours
               FROM affective_state
               WHERE created_at >= datetime('now', ?)
                 AND decay_half_life_hours > 0
               ORDER BY created_at""",
            (f"-{int(_MOOD_WINDOW_H)} hours",),
        ).fetchall()
        con.close()

        if not rows:
            return dict(_BASELINE)

        # Episódico: apenas eventos recentes (últimas 6 h)
        episodic_rows = [r for r in rows if r["age_hours"] <= _EPISODIC_WINDOW_H]
        if episodic_rows:
            ev, ea = _weighted_va(episodic_rows, smoothing_hl=None, dampen=1.0)
        else:
            ev, ea = 0.0, 0.0

        # Humor: todos os eventos nas últimas 48 h, suavização 24 h, intensidade 0.5×
        mv, ma = _weighted_va(rows, smoothing_hl=_MOOD_SMOOTHING_HL, dampen=_MOOD_DAMPEN)
        mv = round(max(-_MOOD_MAX_ABS, min(_MOOD_MAX_ABS, mv)), 4)
        ma = round(max(0.0, min(1.0, ma)), 4)

        _mood_cache    = {"valence": mv, "arousal": ma}
        _mood_cache_at = time.monotonic()

        # Dimensões CPM do episódico
        total_w = wn = wp = wg = wc = 0.0
        for r in episodic_rows or rows[:1]:
            t = max(0.0, r["age_hours"])
            w = math.exp(-t / r["decay_half_life_hours"])
            total_w += w
            wn += (r["novelty"]          or 0.5) * w
            wp += (r["pleasantness"]     or 0.5) * w
            wg += (r["goal_relevance"]   or 0.5) * w
            wc += (r["coping_potential"] or 0.5) * w
        if total_w > 0:
            wn /= total_w; wp /= total_w; wg /= total_w; wc /= total_w
        else:
            wn = wp = wg = wc = 0.5

        log.debug(
            "get_current_state: episodic(V=%.3f A=%.3f) mood(V=%.3f A=%.3f) "
            "n_events=%d n_episodic=%d",
            ev, ea, mv, ma, len(rows), len(episodic_rows),
        )

        return {
            "valence":          ev,
            "arousal":          ea,
            "episodic_valence": ev,
            "episodic_arousal": ea,
            "mood_valence":     mv,
            "mood_arousal":     ma,
            "novelty":          round(wn, 4),
            "pleasantness":     round(wp, 4),
            "goal_relevance":   round(wg, 4),
            "coping_potential": round(wc, 4),
            "sample_count":     len(rows),
        }
    except Exception as exc:
        log.debug("get_current_state: %s", exc)
    return dict(_BASELINE)
