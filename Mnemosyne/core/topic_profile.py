"""
Mnemosyne — Perfil de interesse incremental da usuária por tópico.

Equivalente ao `topic_interest_profile` da AKASHA, mas alimentado por dois
sinais de engajamento genuíno da Mnemosyne:
  1. Queries da usuária no notebook (AskWorker) — +0.5 por keyword
  2. Feedback confirmado em insights (FeedbackReflectionWorker) — +1.0 por keyword

A tabela fica em personal_memory.db (dados privados da IA), junto com
affective_state. Nunca exposta ao RAG de coleções.

Uso::

    from core.topic_profile import update_topic_score, get_topic_scores_for_list

    update_topic_score("machine learning", 0.5)
    scores = get_topic_scores_for_list(["machine learning", "python"])
    # → {"machine learning": 3.0, "python": 0.0}
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("mnemosyne.topic_profile")

_DDL = """
CREATE TABLE IF NOT EXISTS topic_interest_profile (
    topic          TEXT    PRIMARY KEY,
    score          REAL    NOT NULL DEFAULT 0.0,
    query_count    INTEGER NOT NULL DEFAULT 0,
    feedback_count INTEGER NOT NULL DEFAULT 0,
    last_updated   TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""
_IDX = "CREATE INDEX IF NOT EXISTS idx_topic_score ON topic_interest_profile(score DESC);"

# Stopwords PT + EN básicas — palavras de função que não carregam interesse temático
_STOPWORDS: frozenset[str] = frozenset({
    # PT
    "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos",
    "que", "para", "por", "com", "uma", "uns", "umas", "como",
    "mas", "ou", "se", "já", "mais", "muito", "são", "foi", "ser",
    "ele", "ela", "eles", "elas", "isso", "este", "esta", "estes",
    "estas", "esse", "essa", "esses", "essas", "qual", "quais",
    "quando", "onde", "sobre", "entre", "após", "antes", "até",
    "também", "não", "sim", "ter", "tem", "tinha", "teve", "vai",
    "vem", "pode", "deve", "está", "estão", "esteve", "havia",
    "num", "numa", "pelo", "pela", "pelos", "pelas", "seu", "sua",
    "seus", "suas", "meu", "minha", "meus", "minhas", "todo", "toda",
    "todos", "todas", "algum", "alguma", "alguns", "algumas",
    # EN
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "her", "was", "one", "our", "out", "day", "get", "has", "him",
    "his", "how", "its", "now", "old", "see", "two", "who", "did",
    "she", "use", "way", "may", "what", "this", "that", "with",
    "have", "from", "they", "will", "been", "your", "when", "there",
    "which", "would", "could", "about", "these", "those", "then",
    "than", "some", "into", "more", "also", "after", "over", "such",
    "just", "even", "most", "both", "does", "were", "only", "well",
    "very", "each", "made", "need", "like", "know", "want", "here",
    "any", "new", "other", "said", "time",
})


def extract_keywords(text: str) -> list[str]:
    """Extrai keywords de texto plano.

    Tokeniza por espaços/pontuação, normaliza para lowercase, remove
    stopwords e mantém apenas tokens com ≥ 3 caracteres.
    """
    import re
    tokens = re.split(r"[\s\.,;:!?\"'()\[\]{}\-–—/\\]+", text.lower())
    return [
        t for t in tokens
        if len(t) >= 3 and t not in _STOPWORDS and t.isalpha()
    ]


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

def update_topic_score(topic: str, delta: float, source: str = "query") -> None:
    """Incrementa o score de interesse de um tópico.

    Args:
        topic:  String do tópico (já normalizado — lowercase recomendado).
        delta:  Incremento de score (+0.5 para queries, +1.0 para feedback confirmado).
        source: "query" ou "feedback" — controla qual contador incremental é atualizado.
    """
    if not topic or not topic.strip():
        return
    topic = topic.strip().lower()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    query_inc    = 1 if source == "query"    else 0
    feedback_inc = 1 if source == "feedback" else 0
    try:
        with _conn() as con:
            con.execute(
                """INSERT INTO topic_interest_profile
                       (topic, score, query_count, feedback_count, last_updated)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(topic) DO UPDATE SET
                       score          = score + excluded.score,
                       query_count    = query_count    + excluded.query_count,
                       feedback_count = feedback_count + excluded.feedback_count,
                       last_updated   = excluded.last_updated""",
                (topic, round(delta, 4), query_inc, feedback_inc, now),
            )
    except Exception as exc:
        log.debug("update_topic_score(%s): %s", topic, exc)


def bulk_update_from_text(text: str, delta: float, source: str = "query") -> None:
    """Extrai keywords de `text` e atualiza todos de uma vez."""
    for kw in extract_keywords(text):
        update_topic_score(kw, delta, source=source)


def get_topic_scores_for_list(topics: list[str]) -> dict[str, float]:
    """Retorna {topic: score} para os tópicos solicitados.

    Tópicos ausentes retornam 0.0.
    """
    if not topics:
        return {}
    normalized = [t.strip().lower() for t in topics if t and t.strip()]
    if not normalized:
        return {}
    try:
        placeholders = ",".join("?" * len(normalized))
        con = _conn()
        rows = con.execute(
            f"SELECT topic, score FROM topic_interest_profile WHERE topic IN ({placeholders})",
            normalized,
        ).fetchall()
        con.close()
        result = {t: 0.0 for t in normalized}
        for topic, score in rows:
            result[topic] = score
        return result
    except Exception as exc:
        log.debug("get_topic_scores_for_list: %s", exc)
        return {t: 0.0 for t in topics}


def get_top_topics(n: int = 20) -> list[tuple[str, float]]:
    """Retorna os `n` tópicos com maior score acumulado."""
    try:
        con = _conn()
        rows = con.execute(
            "SELECT topic, score FROM topic_interest_profile ORDER BY score DESC LIMIT ?",
            (n,),
        ).fetchall()
        con.close()
        return [(r[0], r[1]) for r in rows]
    except Exception as exc:
        log.debug("get_top_topics: %s", exc)
        return []


def apply_interest_seeds() -> int:
    """Importa tópicos de interests.json para topic_interest_profile.

    Lê {sync_root}/interests.json via ecosystem_client. Tópicos excluídos são
    ignorados. Só inicializa tópicos ainda sem score — nunca sobrescreve
    histórico acumulado por queries ou feedback confirmado.

    Retorna o número de seeds aplicados (0 se nenhum novo tópico encontrado).
    """
    try:
        from ecosystem_client import get_interests  # type: ignore
        interests = get_interests()
    except Exception as exc:
        log.debug("apply_interest_seeds: get_interests falhou: %s", exc)
        return 0

    if not interests:
        return 0

    names = [
        (entry.get("name") or "").strip().lower()
        for entry in interests
        if not entry.get("excluded")
    ]
    names = [n for n in names if len(n) >= 3]
    if not names:
        return 0

    existing = get_topic_scores_for_list(names)
    count = 0
    for entry in interests:
        if entry.get("excluded"):
            continue
        name = (entry.get("name") or "").strip().lower()
        if len(name) < 3:
            continue
        if existing.get(name, 0.0) > 0.0:
            continue  # já tem histórico acumulado — não sobrescrever
        weight = max(0.1, float(entry.get("weight") or 1.0))
        update_topic_score(name, weight, source="seed")
        count += 1

    if count:
        log.info("apply_interest_seeds: %d tópico(s) importados de interests.json.", count)
    return count
