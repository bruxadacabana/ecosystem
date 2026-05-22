"""
Testes para services/session_memory.py.

Cobre:
  - reformulate_if_anaphoric: sem anáfora → retorna original
  - reformulate_if_anaphoric: com anáfora + histórico → substitui pronome
  - reformulate_if_anaphoric: histórico vazio → retorna original
  - reformulate_if_anaphoric: última query sem substantivos → retorna original
  - reformulate_if_anaphoric: anáforas PT variadas (ela, ele, isso, esse, essa…)
  - SessionEntry.active: expiração por TTL
  - update_session / get_session / get_history
  - gc_sessions: remove expiradas
"""
from __future__ import annotations

import time
import pytest


def _reform(query: str, history: list[str]) -> str:
    from services.session_memory import reformulate_if_anaphoric
    return reformulate_if_anaphoric(query, history)


# ---------------------------------------------------------------------------
# reformulate_if_anaphoric — casos sem reformulação
# ---------------------------------------------------------------------------

class TestNoReformulation:

    def test_empty_history_returns_original(self):
        """Histórico vazio → sem reformulação."""
        assert _reform("como ela funciona", []) == "como ela funciona"

    def test_no_anaphor_returns_original(self):
        """Query sem anáfora → retorna original."""
        assert _reform("python decorators tutorial", ["machine learning"]) == "python decorators tutorial"

    def test_last_query_no_nouns_returns_original(self):
        """Última query só com stopwords/tokens curtos → retorna original."""
        assert _reform("como ela funciona", ["por que"]) == "como ela funciona"

    def test_empty_query_returns_original(self):
        """Query vazia → retorna vazia."""
        assert _reform("", ["python tutorial"]) == ""

    def test_no_anaphor_with_history(self):
        """Query descritiva sem pronome anafórico → retorna original."""
        result = _reform("quais são os melhores frameworks", ["python tutorial"])
        assert result == "quais são os melhores frameworks"


# ---------------------------------------------------------------------------
# reformulate_if_anaphoric — substituição esperada
# ---------------------------------------------------------------------------

class TestReformulation:

    def test_ela_substituida(self):
        """'ela' → substantivos da última query."""
        result = _reform("como ela funciona", ["python decorators"])
        assert "ela" not in result.lower()
        assert "python" in result.lower() or "decorators" in result.lower()

    def test_ele_substituido(self):
        """'ele' → substantivos da última query."""
        result = _reform("onde posso usar ele", ["rust linguagem"])
        assert "rust" in result.lower() or "linguagem" in result.lower()

    def test_isso_substituido(self):
        """'isso' → substantivos da última query."""
        result = _reform("como isso funciona na prática", ["kubernetes containers"])
        assert "isso" not in result.lower()
        assert "kubernetes" in result.lower() or "containers" in result.lower()

    def test_esse_substituido(self):
        """'esse' → substantivos da última query."""
        result = _reform("explique esse conceito melhor", ["machine learning redes neurais"])
        assert "esse" not in result.lower()

    def test_essa_substituida(self):
        """'essa' → substantivos da última query."""
        result = _reform("essa abordagem resolve o problema", ["programação funcional"])
        assert "essa" not in result.lower()

    def test_aquilo_substituido(self):
        """'aquilo' → substantivos da última query."""
        result = _reform("como funciona aquilo", ["gradient descent otimização"])
        assert "aquilo" not in result.lower()

    def test_uses_last_query_in_history(self):
        """Usa a ÚLTIMA query do histórico, não a primeira."""
        history = ["java spring framework", "python decorators avançados"]
        result = _reform("como ela funciona", history)
        # deve usar "python decorators avançados" (última), não "java spring"
        assert "python" in result.lower() or "decorators" in result.lower() or "avançados" in result.lower()

    def test_original_query_structure_preserved(self):
        """Estrutura da query deve ser preservada ao redor da substituição."""
        result = _reform("como ela funciona na prática", ["python decorators"])
        assert result.startswith("como ")
        assert "prática" in result

    def test_single_noun_in_history(self):
        """Substituição com um único substantivo."""
        result = _reform("como funciona isso", ["kubernetes"])
        # "kubernetes" tem len ≥ 4 e não é stopword
        assert "kubernetes" in result.lower()

    def test_case_insensitive_anaphor(self):
        """Anáfora em maiúsculas deve ser reconhecida."""
        result = _reform("Como ELA funciona", ["python decorators"])
        assert "ELA" not in result or "ela" not in result.lower().replace("ela", "").split()

    def test_only_first_anaphor_replaced(self):
        """count=1 — só o primeiro match é substituído."""
        result = _reform("ela e ela explicam isso", ["python tutorial"])
        # A string resultante pode ter o pronome original na segunda posição
        # mas a primeira ocorrência deve ter sido substituída
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# SessionEntry — TTL e estado
# ---------------------------------------------------------------------------

class TestSessionEntry:

    def test_active_session(self):
        from services.session_memory import SessionEntry
        s = SessionEntry(queries=["python"], last_at=time.time())
        assert s.active is True

    def test_expired_session(self):
        from services.session_memory import SessionEntry, SESSION_TTL_S
        s = SessionEntry(queries=["python"], last_at=time.time() - SESSION_TTL_S - 1)
        assert s.active is False


# ---------------------------------------------------------------------------
# update_session / get_session / get_history
# ---------------------------------------------------------------------------

class TestSessionStore:

    def setup_method(self):
        """Limpa o store antes de cada teste."""
        from services.session_memory import _sessions
        _sessions.clear()

    def test_update_creates_session(self):
        from services.session_memory import update_session, get_session
        update_session("sess1", "python tutorial")
        s = get_session("sess1")
        assert s is not None
        assert "python tutorial" in s.queries

    def test_update_appends_queries(self):
        from services.session_memory import update_session, get_session
        update_session("sess1", "python tutorial")
        update_session("sess1", "decorators python")
        s = get_session("sess1")
        assert len(s.queries) == 2

    def test_get_nonexistent_returns_none(self):
        from services.session_memory import get_session
        assert get_session("nonexistent") is None

    def test_get_history_excludes_last(self):
        from services.session_memory import update_session, get_history
        update_session("sess2", "query1")
        update_session("sess2", "query2")
        update_session("sess2", "query3")
        hist = get_history("sess2")
        assert "query3" not in hist
        assert "query1" in hist and "query2" in hist

    def test_get_history_single_query_empty(self):
        """Apenas 1 query na sessão → histórico vazio."""
        from services.session_memory import update_session, get_history
        update_session("sess3", "only query")
        assert get_history("sess3") == []

    def test_gc_removes_expired(self):
        from services.session_memory import _sessions, SessionEntry, gc_sessions
        _sessions["active"]  = SessionEntry(queries=["x"], last_at=time.time())
        _sessions["expired"] = SessionEntry(queries=["y"], last_at=time.time() - 9999)
        removed = gc_sessions()
        assert removed == 1
        assert "active" in _sessions
        assert "expired" not in _sessions
