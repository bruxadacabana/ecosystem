"""
AKASHA — Gerenciamento de sessão de pesquisa.

Agrupa queries consecutivas em sessão quando:
  - Gap temporal entre queries < SESSION_GAP_S segundos
  - Similaridade léxica (Jaccard de palavras) com o histórico ≥ SIMILARITY_THRESHOLD

Estado em memória por session_id (cookie). Sem persistência em disco — sessões expiram
ao reiniciar o servidor ou após SESSION_GAP_S de inatividade.
A sessão é o contexto para reescrita conversacional de queries (item #10).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

SESSION_GAP_S:        int   = 1800   # 30 min sem atividade → nova sessão automática
SIMILARITY_THRESHOLD: float = 0.25   # Jaccard — tolerante o bastante para variações de formulação
MAX_QUERIES:          int   = 10     # queries acumuladas por sessão
MAX_RESULT_URLS:      int   = 20     # URLs de resultado acumuladas (contexto para RAG futuro)


@dataclass
class SearchSession:
    queries:              list[str] = field(default_factory=list)
    result_urls:          list[str] = field(default_factory=list)
    last_at:              float     = field(default_factory=time.time)
    asked_clarification:  bool      = False   # máx 1 pergunta de clarificação por sessão

    @property
    def active(self) -> bool:
        return (time.time() - self.last_at) < SESSION_GAP_S

    @property
    def query_count(self) -> int:
        return len(self.queries)

    def context_queries(self, current: str) -> list[str]:
        """Queries anteriores à atual (últimas 5), para reescrita conversacional."""
        return [q for q in self.queries if q != current][-5:]


_sessions: dict[str, SearchSession] = {}


def _words(text: str) -> set[str]:
    """Extrai tokens ≥3 chars (Latin e CJK) do texto."""
    return set(re.findall(r"[\w一-鿿]{3,}", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def get_session(session_id: str) -> SearchSession | None:
    """Retorna sessão ativa ou None se expirada/inexistente."""
    s = _sessions.get(session_id)
    if s is None or not s.active:
        return None
    return s


def update_session(session_id: str, query: str, result_urls: list[str]) -> SearchSession:
    """Atualiza ou inicia sessão para session_id.

    Abre nova sessão quando: timeout expirou OU similaridade léxica com as últimas 3
    queries < SIMILARITY_THRESHOLD (mudança de tema detectada automaticamente).
    Retorna a sessão atualizada.
    """
    now = time.time()
    existing = _sessions.get(session_id)

    start_new = True
    if existing is not None and existing.active and existing.queries:
        history_words = _words(" ".join(existing.queries[-3:]))
        sim = _jaccard(_words(query), history_words)
        start_new = sim < SIMILARITY_THRESHOLD

    if start_new:
        _sessions[session_id] = SearchSession(
            queries=[query],
            result_urls=result_urls[:MAX_RESULT_URLS],
            last_at=now,
        )
    else:
        s = existing  # type: ignore[assignment]
        s.last_at = now
        if query not in s.queries:
            s.queries = (s.queries + [query])[-MAX_QUERIES:]
        seen = set(s.result_urls)
        for url in result_urls:
            if url not in seen and len(s.result_urls) < MAX_RESULT_URLS:
                s.result_urls.append(url)
                seen.add(url)

    return _sessions[session_id]


def clear_session(session_id: str) -> None:
    """Encerra a sessão manualmente (botão 'encerrar' na UI)."""
    _sessions.pop(session_id, None)


def gc_sessions() -> int:
    """Remove sessões expiradas da memória. Retorna quantidade removida."""
    expired = [sid for sid, s in _sessions.items() if not s.active]
    for sid in expired:
        del _sessions[sid]
    return len(expired)
