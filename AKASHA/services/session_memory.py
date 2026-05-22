"""
AKASHA — Memória de sessão + reformulação de anáforas por regex (sem LLM).

Responsabilidades:
  1. Manter histórico de queries por session_id com TTL de 30 min.
     Usado pelo item 23 (reflexão pós-sessão) via detecção de expiração com ≥ 3 queries.
  2. reformulate_if_anaphoric(): substitui pronomes anafóricos PT pelos
     substantivos da última query — sem LLM, sem latência de rede.

Exemplo:
    history = ["python decorators"]
    query   = "como ela funciona"
    → "como python decorators funciona"

Distingue-se de search_session.py: esse módulo é simples (só append + TTL),
sem Jaccard, sem lógica de agrupamento por tema. O search_session.py continua
sendo usado para reescrita via LLM e detecção de tema; este módulo complementa
com reformulação léxica imediata para anáforas PT.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

SESSION_TTL_S: int = 1800  # 30 min sem nova query → sessão expirada
MAX_QUERIES:   int = 20    # limite de queries acumuladas por sessão

# Regex de anáforas PT — pronomes + locuções pronominais
_ANAPHORA_RE = re.compile(
    r"\b(ela|ele|eles|elas|isso|aquilo|esse|essa|esses|essas"
    r"|o mesmo|a mesma|os mesmos|as mesmas)\b",
    re.IGNORECASE,
)

_STOPWORDS: frozenset[str] = frozenset({
    # PT
    "para", "sobre", "entre", "também", "ainda", "mais",
    "muito", "todo", "toda", "todos", "todas", "pelo", "pela",
    "pelos", "pelas", "pode", "esse", "essa", "esses", "essas",
    "este", "esta", "estes", "estas", "aquele", "aquela",
    "nosso", "nossa", "nossos", "nossas", "vocês", "eles", "elas",
    "isso", "aquilo", "aqui", "então", "pois", "logo", "porque",
    "assim", "após", "cada", "qual", "como", "quando", "onde",
    "quem", "nada", "algo", "alguém", "tudo", "nunca", "sempre",
    "apenas", "mesmo", "seria", "estar", "fazer", "ficar",
    "deve", "sendo", "foram", "será",
    # EN
    "also", "about", "into", "than", "then", "from", "with",
    "this", "that", "they", "them", "what", "when", "where",
    "will", "would", "could", "should", "have", "been", "being",
    "does", "their", "there", "these", "those", "some", "more",
    "most", "both", "each", "other", "very", "just", "only",
    "even", "like", "such", "after", "which", "while", "since",
})

# Tokens válidos para substituição: len ≥ 4, somente letras (inclui acentuados)
_NOUN_RE = re.compile(r"[a-zA-ZÀ-ɏ]{4,}")


# ---------------------------------------------------------------------------
# Store de sessão
# ---------------------------------------------------------------------------

@dataclass
class SessionEntry:
    queries: list[str] = field(default_factory=list)
    last_at: float     = field(default_factory=time.time)

    @property
    def active(self) -> bool:
        return (time.time() - self.last_at) < SESSION_TTL_S


_sessions: dict[str, SessionEntry] = {}


def update_session(session_id: str, query: str) -> SessionEntry:
    """Registra query na sessão (cria nova se inexistente ou expirada)."""
    existing = _sessions.get(session_id)
    now = time.time()
    if existing is None or not existing.active:
        _sessions[session_id] = SessionEntry(queries=[query], last_at=now)
    else:
        existing.last_at = now
        if query not in existing.queries:
            existing.queries = (existing.queries + [query])[-MAX_QUERIES:]
    return _sessions[session_id]


def get_session(session_id: str) -> SessionEntry | None:
    """Retorna sessão ativa ou None se expirada/inexistente."""
    s = _sessions.get(session_id)
    return s if s is not None and s.active else None


def get_history(session_id: str) -> list[str]:
    """Queries da sessão ativa, excluindo a última (usada como histórico anterior)."""
    s = get_session(session_id)
    return s.queries[:-1] if s and len(s.queries) > 1 else []


def gc_sessions() -> int:
    """Remove sessões expiradas da memória. Retorna quantidade removida."""
    expired = [sid for sid, s in list(_sessions.items()) if not s.active]
    for sid in expired:
        del _sessions[sid]
    return len(expired)


# ---------------------------------------------------------------------------
# Reformulação de anáforas
# ---------------------------------------------------------------------------

def _extract_nouns(query: str) -> list[str]:
    """Extrai tokens ≥ 4 chars que não são stopwords (proxy de substantivos)."""
    return [
        t.lower() for t in _NOUN_RE.findall(query)
        if t.lower() not in _STOPWORDS
    ]


def reformulate_if_anaphoric(query: str, history: list[str]) -> str:
    """Reformula query com anáfora PT usando tokens da última query do histórico.

    Substitui o primeiro pronome anafórico encontrado pelos substantivos extraídos
    da última query do histórico. Retorna a query original se:
      - histórico vazio
      - nenhuma anáfora detectada
      - última query não tem substantivos válidos (≥ 4 chars, não stopword)

    Somente o primeiro match de anáfora é substituído (evita reformulações ambíguas).
    """
    if not history or not _ANAPHORA_RE.search(query):
        return query

    last_query = history[-1]
    nouns = _extract_nouns(last_query)
    if not nouns:
        return query

    substitution = " ".join(nouns)
    reformulated = _ANAPHORA_RE.sub(substitution, query, count=1)
    return reformulated.strip()
