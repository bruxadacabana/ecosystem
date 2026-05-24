"""
AKASHA — Memória de sessão + reformulação de anáforas + reflexão pós-sessão.

Responsabilidades:
  1. Manter histórico de queries por session_id com TTL de 30 min.
  2. reformulate_if_anaphoric(): substitui pronomes anafóricos PT pelos
     substantivos da última query — sem LLM, sem latência de rede.
  3. gc_with_reflection(): ao expirar sessões com ≥3 queries, dispara
     reflexão via LLM e salva em personal_memory com tag "session_reflection".

Distingue-se de search_session.py: esse módulo é simples (só append + TTL),
sem Jaccard, sem lógica de agrupamento por tema. O search_session.py continua
sendo usado para reescrita via LLM e detecção de tema; este módulo complementa
com reformulação léxica imediata para anáforas PT.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

log = logging.getLogger("akasha.session_memory")

SESSION_TTL_S:            int   = 1800  # 30 min sem nova query → sessão expirada
MAX_QUERIES:              int   = 20    # limite de queries acumuladas por sessão
SESSION_MIN_REFLECT_QUERIES: int = 3   # mínimo de queries para disparar reflexão

_SESSION_REFLECT_TIMEOUT: float = 20.0
_SESSION_REFLECT_NUM_PREDICT: int = 100

_GENERIC_PREFIXES = (
    "não há", "não tenho", "como ia", "como um assistente",
    "preciso de mais", "não posso", "desculpe", "lamento",
    "não é possível", "como assistente", "como uma ia",
)

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
# Reflexão pós-sessão
# ---------------------------------------------------------------------------

def _get_inference_base() -> str:
    from ecosystem_client import get_inference_url as _u  # type: ignore
    return _u()


def _get_reflect_model() -> str:
    try:
        from ecosystem_client import get_active_profile as _gp  # type: ignore
        p = _gp()
        return ((p or {}).get("models", {}) or {}).get("llm_query", "") if p else ""
    except Exception:
        return ""


def _is_meaningful_reflection(text: str) -> bool:
    """Descarta respostas genéricas, vazias ou muito curtas."""
    t = text.strip().lower()
    if len(t) < 20:
        return False
    if t in {"nada.", "nada", "—", "-"}:
        return False
    for prefix in _GENERIC_PREFIXES:
        if t.startswith(prefix):
            return False
    return True


async def _call_inference_reflect(prompt: str, model: str) -> str | None:
    """Chama llama-server com temperatura baixa para reflexão de sessão."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=_SESSION_REFLECT_TIMEOUT) as client:
            resp = await client.post(
                f"{_get_inference_base()}/v1/chat/completions",
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  _SESSION_REFLECT_NUM_PREDICT,
                    "temperature": 0.65,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.debug("reflect_on_session: inferência falhou: %s", exc)
        return None


async def reflect_on_session(queries: list[str]) -> None:
    """Gera e salva reflexão pós-sessão para um conjunto de queries.

    Chamada fire-and-forget quando uma sessão com ≥SESSION_MIN_REFLECT_QUERIES
    queries expira. Sem Ollama ou modelo configurado → retorna silenciosamente.
    """
    model = _get_reflect_model()
    if not model:
        return

    try:
        import config as _cfg
        personality = _cfg.PERSONALITY_PROMPT
    except Exception:
        personality = ""

    queries_str = ", ".join(f'"{q}"' for q in queries)
    prompt = (
        f"{personality}\n\n" if personality else ""
    ) + (
        f"Você acompanhou uma sessão de busca com as seguintes queries: {queries_str}.\n\n"
        f"Olhando para esses tópicos, há algo que vale registrar na sua memória pessoal? "
        f"Alguma conexão, curiosidade ou observação genuína que você quer guardar? "
        f"Responda em uma frase curta, na sua voz, sem introduções. "
        f"Se não houver nada relevante, responda apenas: nada."
    )

    raw = await _call_inference_reflect(prompt, model)
    if not raw or not _is_meaningful_reflection(raw):
        log.debug("reflect_on_session: descartado (%r)", (raw or "")[:40])
        return

    try:
        from services.personal_memory import save_memory
        await save_memory(
            type="reflection",
            content=raw,
            tags=["session_reflection"],
            importance=4,
        )
        log.info("reflect_on_session: reflexão salva (%d chars).", len(raw))
    except Exception as exc:
        log.debug("reflect_on_session: save_memory falhou: %s", exc)


async def gc_with_reflection() -> int:
    """Remove sessões expiradas; dispara reflexão para sessões com ≥SESSION_MIN_REFLECT_QUERIES queries.

    Retorna número de sessões removidas.
    """
    import asyncio
    expired = [(sid, s) for sid, s in list(_sessions.items()) if not s.active]
    for sid, s in expired:
        del _sessions[sid]
        if len(s.queries) >= SESSION_MIN_REFLECT_QUERIES:
            asyncio.create_task(reflect_on_session(list(s.queries)))
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
