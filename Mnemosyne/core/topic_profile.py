"""
Mnemosyne — Perfil de interesse incremental da usuária por tópico.

Delega para shared_topic_profile (store compartilhado em sync_root) com
source='mnemosyne'. Sinais de engajamento:
  1. Queries da usuária no notebook (AskWorker)           — +0.5 por keyword
  2. Feedback confirmado em insights (FeedbackWorker)     — +1.0 por keyword

Normalização de idioma: queries e textos de insights são gerados em
português (prompts LLM com instrução explícita de idioma), portanto
keywords extraídas já chegam em PT. extract_keywords() aplica
lowercase + remoção de stopwords PT/EN.
"""
from __future__ import annotations

import logging

log = logging.getLogger("mnemosyne.topic_profile")

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


# ── API pública ──────────────────────────────────────────────────────────────

def update_topic_score(topic: str, delta: float, source: str = "query") -> None:
    """Incrementa o score de interesse de um tópico no store compartilhado."""
    if not topic or not topic.strip():
        return
    try:
        import shared_topic_profile as _stp
        _stp.update_score(topic, delta, "mnemosyne")
    except Exception as exc:
        log.debug("update_topic_score(%s): %s", topic, exc)


def bulk_update_from_text(text: str, delta: float, source: str = "query") -> None:
    """Extrai keywords de `text` e atualiza todas de uma vez."""
    keywords = extract_keywords(text)
    if not keywords:
        return
    try:
        import shared_topic_profile as _stp
        _stp.update_scores(keywords, delta, "mnemosyne")
    except Exception as exc:
        log.debug("bulk_update_from_text: %s", exc)


def get_topic_scores_for_list(topics: list[str]) -> dict[str, float]:
    """Retorna {topic: score} para os tópicos solicitados. Ausentes retornam 0.0."""
    if not topics:
        return {}
    try:
        import shared_topic_profile as _stp
        return _stp.get_scores(topics)
    except Exception as exc:
        log.debug("get_topic_scores_for_list: %s", exc)
        return {t.strip().lower(): 0.0 for t in topics if t and t.strip()}


def get_top_topics(n: int = 20) -> list[tuple[str, float]]:
    """Retorna os `n` tópicos com maior score acumulado."""
    try:
        import shared_topic_profile as _stp
        return _stp.get_top_topics(n)
    except Exception as exc:
        log.debug("get_top_topics: %s", exc)
        return []


def apply_interest_seeds() -> int:
    """Inicializa tópicos de interests.json no store compartilhado.

    Só insere tópicos sem histórico acumulado — nunca sobrescreve scores existentes.
    Retorna número de seeds aplicados.
    """
    try:
        from ecosystem_client import get_interests  # type: ignore
        interests = get_interests()
    except Exception as exc:
        log.debug("apply_interest_seeds: get_interests falhou: %s", exc)
        return 0

    if not interests:
        return 0

    seeds = [e for e in interests if not e.get("excluded")]
    if not seeds:
        return 0

    try:
        import shared_topic_profile as _stp
        count = _stp.apply_seed_topics(seeds)
        if count:
            log.info("apply_interest_seeds: %d tópico(s) importados.", count)
        return count
    except Exception as exc:
        log.debug("apply_interest_seeds: %s", exc)
        return 0
