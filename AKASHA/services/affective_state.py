"""
AKASHA — Estado afetivo bidimensional (valência + arousal).

Implementa appraisal via 4 dimensões do CPM de Scherer usando dados já
disponíveis em akasha.db / akasha_knowledge.db como proxies:

  • Novelty          — familiaridade dos tópicos no topic_interest_profile
  • Pleasantness     — alinhamento com interesses estabelecidos (mesmo proxy)
  • Goal relevance   — sobreposição com queries recentes em search_history
  • Coping potential — fração dos tópicos já conhecidos no profile

M1: decaimento exponencial por meia-vida diferenciada por tipo de evento e valência.
M2 (ALMA Gebhard 2005): duas camadas temporais.
  • Episódico  — evento específico, alta intensidade, janela 6 h, half-life armazenada.
  • Humor/mood — EWA das últimas 48 h com smoothing de 24 h, intensidade 0.5×,
                 clamped a ±0.5. Representa o contexto afetivo de fundo do dia.
O mood modula thresholds de novos episódicos: eventos que alinham com o humor
são levemente amplificados (+15%); eventos que se opõem são amortecidos (−25%).
Isso evita que cada evento recente sobrescreva o estado sem acumulação,
preservando o efeito de contexto afetivo.

Feedback/momentum (item [J]) via record_approval_momentum() em set_feedback().
A tabela affective_state fica em personal_memory.db (dados privados da IA).

Uso::

    from services.affective_state import record_appraisal, get_current_state

    await record_appraisal("doc_indexed", novelty, pleasantness,
                            goal_relevance, coping_potential)
    state = await get_current_state()
    # {"valence": 0.3, "arousal": 0.5,
    #  "episodic_valence": 0.3, "episodic_arousal": 0.5,
    #  "mood_valence": 0.1, "mood_arousal": 0.3, ...}
"""
from __future__ import annotations

import logging
import math
import time
from pathlib import Path

import aiosqlite

log = logging.getLogger("akasha.affective_state")

# ── Parâmetros ALMA ──────────────────────────────────────────────────────────

_EPISODIC_WINDOW_H:  float = 2.0    # janela para emoções episódicas (M2) — dentro de uma sessão
_MOOD_WINDOW_H:      float = 24.0   # janela de acumulação do humor — contexto do dia
_MOOD_SMOOTHING_HL:  float = 12.0   # meia-vida de suavização do humor (h)
_MOOD_DAMPEN:        float = 0.5    # humor menos intenso que episódico
_MOOD_MAX_ABS:       float = 0.5    # clamp: humor nunca excede ±0.5
_MOOD_CACHE_TTL_S:   float = 600.0  # TTL do cache de humor em memória (10 min)

# Cache de humor: evita re-leitura de DB a cada record_appraisal
_mood_cache:    dict[str, float] = {"valence": 0.0, "arousal": 0.0}
_mood_cache_at: float = 0.0


_CURIOSITY_HL:       float = 8.0     # meia-vida da curiosidade epistêmica (h)
_CURIOSITY_WINDOW_H: float = 24.0   # janela de acumulação da curiosidade
_CURIOSITY_NOVELTY_THRESHOLD: float = 0.7   # novelty mínima para disparar curiosidade
_CURIOSITY_COPING_MIN:        float = 0.5   # coping mínimo (alta incerteza inibe curiosidade)


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
    decay_half_life_hours REAL    NOT NULL DEFAULT 6.0,
    curiosity_delta       REAL    NOT NULL DEFAULT 0.0
);
"""
_IDX = "CREATE INDEX IF NOT EXISTS idx_affstate_created ON affective_state(created_at);"
_MIGRATION_DECAY = (
    "ALTER TABLE affective_state "
    "ADD COLUMN decay_half_life_hours REAL NOT NULL DEFAULT 6.0"
)
_MIGRATION_CURIOSITY = (
    "ALTER TABLE affective_state "
    "ADD COLUMN curiosity_delta REAL NOT NULL DEFAULT 0.0"
)

_BASELINE: dict[str, float] = {
    "valence":             0.0,
    "arousal":             0.0,
    "episodic_valence":    0.0,
    "episodic_arousal":    0.0,
    "mood_valence":        0.0,
    "mood_arousal":        0.0,
    "epistemic_curiosity": 0.0,
    "novelty":             0.5,
    "pleasantness":        0.5,
    "goal_relevance":      0.5,
    "coping_potential":    0.5,
    "sample_count":        0,
}


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
    for migration in (_MIGRATION_DECAY, _MIGRATION_CURIOSITY):
        try:
            await conn.execute(migration)
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


# ── Modulação de threshold por humor (ALMA M2) ───────────────────────────────

def _apply_mood_modulation(valence: float) -> float:
    """Modula nova emoção episódica pelo humor de fundo (ALMA threshold effect).

    Humor positivo → emoções positivas amplificadas (+15%), negativas amortecidas (−25%).
    Humor negativo → emoções negativas amplificadas, positivas amortecidas.
    Humor próximo de neutro (|mv| < 0.05) → sem efeito.
    """
    mv = _mood_cache.get("valence", 0.0)
    if abs(mv) < 0.05:
        return valence
    if mv * valence > 0:  # mesmo sinal — alinha com humor
        return round(valence * (1.0 + abs(mv) * 0.15), 4)
    else:                 # sinais opostos — vai contra humor
        return round(valence * (1.0 - abs(mv) * 0.25), 4)


def _weighted_va(rows: list, smoothing_hl: float | None, dampen: float) -> tuple[float, float]:
    """Média ponderada exponencial de (valence, arousal) sobre rows.

    smoothing_hl: meia-vida fixa para suavização (humor); None → usa stored half-life.
    dampen: fator de intensidade aplicado ao resultado (0.5 para humor).
    Retorna (0.0, 0.0) se peso total for desprezível.
    """
    total_w = wv = wa = 0.0
    for r in rows:
        t   = max(0.0, r["age_hours"])
        hl  = smoothing_hl if smoothing_hl is not None else r["decay_half_life_hours"]
        w   = math.exp(-t / hl)
        total_w += w
        wv  += r["valence"] * w
        wa  += r["arousal"] * w
    if total_w < 0.01:
        return 0.0, 0.0
    return round((wv / total_w) * dampen, 4), round((wa / total_w) * dampen, 4)


# ── API pública ──────────────────────────────────────────────────────────────

async def record_curiosity_event(delta: float, event_ref: str | None = None) -> None:
    """Persiste um evento de curiosidade epistêmica com meia-vida própria (_CURIOSITY_HL).

    delta > 0: aumento (dismissed inesperado, alta novidade + coping suficiente).
    delta < 0: redução (satisfação epistêmica — insight confirmado após curiosidade).
    Curiosidade não contribui para VA — é armazenada em linha separada com valence=0.
    """
    async with aiosqlite.connect(_get_db()) as conn:
        await _ensure_schema(conn)
        await conn.execute(
            """INSERT INTO affective_state
               (event_type, event_ref, valence, arousal,
                decay_half_life_hours, curiosity_delta)
               VALUES ('curiosity_event', ?, 0.0, 0.0, ?, ?)""",
            (event_ref, _CURIOSITY_HL, round(delta, 4)),
        )
        await conn.commit()
    log.debug("curiosity_event: delta=%.3f ref=%s", delta, event_ref)


async def get_epistemic_curiosity() -> float:
    """Nível atual de curiosidade epistêmica ∈ [0, 1], com decaimento exponencial.

    Soma ponderada dos curiosity_delta das últimas _CURIOSITY_WINDOW_H horas,
    normalizada pelo peso total máximo possível (se todos os deltas fossem +1).
    Clamped a [0, 1].
    """
    try:
        async with aiosqlite.connect(_get_db()) as conn:
            await _ensure_schema(conn)
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """SELECT curiosity_delta, decay_half_life_hours,
                          (julianday('now') - julianday(created_at)) * 24.0 AS age_hours
                   FROM affective_state
                   WHERE curiosity_delta != 0
                     AND created_at >= datetime('now', ?)""",
                (f"-{int(_CURIOSITY_WINDOW_H)} hours",),
            )
            rows = await cur.fetchall()
        if not rows:
            return 0.0
        total_w = wc = 0.0
        for r in rows:
            t = max(0.0, r["age_hours"])
            w = math.exp(-t / r["decay_half_life_hours"])
            total_w += w
            wc += r["curiosity_delta"] * w
        if total_w < 0.01:
            return 0.0
        return round(max(0.0, min(1.0, wc / total_w)), 4)
    except Exception as exc:
        log.debug("get_epistemic_curiosity: %s", exc)
        return 0.0


async def record_appraisal(
    event_type:       str,
    novelty:          float,
    pleasantness:     float,
    goal_relevance:   float,
    coping_potential: float,
    event_ref:        str | None = None,
) -> None:
    """Calcula VA + meia-vida de decaimento e persiste em affective_state.

    Aplica modulação de threshold pelo humor de fundo (M2).
    Dispara curiosidade epistêmica (H) quando novelty > 0.7 e coping > 0.5.
    """
    valence, arousal = compute_va(novelty, pleasantness, goal_relevance, coping_potential)
    half_life = _assign_half_life(event_type, valence)
    valence   = _apply_mood_modulation(valence)  # M2: threshold via mood

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
        "appraisal [%s]: N=%.2f P=%.2f R=%.2f C=%.2f → V=%.3f A=%.3f hl=%.1fh (mood=%.2f)",
        event_type, novelty, pleasantness, goal_relevance, coping_potential,
        valence, arousal, half_life, _mood_cache.get("valence", 0.0),
    )

    # H: alta novidade + coping suficiente → curiosidade epistêmica
    if novelty > _CURIOSITY_NOVELTY_THRESHOLD and coping_potential > _CURIOSITY_COPING_MIN:
        delta = round((novelty - _CURIOSITY_NOVELTY_THRESHOLD)
                      / (1.0 - _CURIOSITY_NOVELTY_THRESHOLD) * 0.4, 4)
        await record_curiosity_event(delta, event_ref=f"high_novelty:{event_type}")


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


async def get_current_state() -> dict[str, float]:
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
        async with aiosqlite.connect(_get_db()) as conn:
            await _ensure_schema(conn)
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """SELECT valence, arousal, novelty, pleasantness,
                          goal_relevance, coping_potential, decay_half_life_hours,
                          (julianday('now') - julianday(created_at)) * 24.0 AS age_hours
                   FROM affective_state
                   WHERE created_at >= datetime('now', ?)
                     AND decay_half_life_hours > 0
                   ORDER BY created_at""",
                (f"-{int(_MOOD_WINDOW_H)} hours",),
            )
            rows = await cur.fetchall()

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

        # Atualiza cache de humor para modulação de threshold em record_appraisal
        _mood_cache    = {"valence": mv, "arousal": ma}
        _mood_cache_at = time.monotonic()

        # Curiosidade epistêmica: soma decaída dos deltas de curiosidade
        curiosity = await get_epistemic_curiosity()

        # Dimensões CPM do episódico (média ponderada da janela curta)
        total_w = wn = wp = wg = wc = 0.0
        for r in episodic_rows or rows[:1]:
            t = max(0.0, r["age_hours"])
            hl = r["decay_half_life_hours"]
            w = math.exp(-t / hl)
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
            "valence":             ev,   # alias episódico (retrocompat)
            "arousal":             ea,
            "episodic_valence":    ev,
            "episodic_arousal":    ea,
            "mood_valence":        mv,
            "mood_arousal":        ma,
            "epistemic_curiosity": curiosity,
            "novelty":             round(wn, 4),
            "pleasantness":        round(wp, 4),
            "goal_relevance":      round(wg, 4),
            "coping_potential":    round(wc, 4),
            "sample_count":        len(rows),
        }
    except Exception as exc:
        log.debug("get_current_state: %s", exc)
    return dict(_BASELINE)
