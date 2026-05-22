"""
Testes unitários para AKASHA/services/session_insight.py.

Cobre gerenciamento de estado em memória sem rede nem DB:
  - get_current: retorna None se ausente ou expirado
  - dismiss: limpa _pm_current mesmo sem session_id
  - set_pm_current / get_pm_current: round-trip de estado de overlay
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture(autouse=True)
def reset_state():
    """Limpa estado global do módulo antes de cada teste."""
    import services.session_insight as si
    si._current.clear()
    si._last_gen.clear()
    si._pm_current = None
    yield
    si._current.clear()
    si._last_gen.clear()
    si._pm_current = None


class TestGetCurrent:
    def test_returns_none_when_empty(self):
        from services.session_insight import get_current
        assert get_current("sessao-abc") is None

    def test_returns_entry_when_present(self):
        import services.session_insight as si
        si._current["s1"] = {
            "text": "observação de teste",
            "memory_id": 42,
            "generated_at": time.time(),
        }
        result = si.get_current("s1")
        assert result is not None
        assert result["text"] == "observação de teste"
        assert result["memory_id"] == 42

    def test_returns_none_after_expiry(self):
        import services.session_insight as si
        si._current["s2"] = {
            "text": "antigo",
            "memory_id": None,
            "generated_at": time.time() - si._INSIGHT_MAX_AGE_S - 1,
        }
        assert si.get_current("s2") is None

    def test_removes_expired_entry_from_dict(self):
        import services.session_insight as si
        si._current["s3"] = {
            "text": "expirado",
            "memory_id": None,
            "generated_at": time.time() - si._INSIGHT_MAX_AGE_S - 1,
        }
        si.get_current("s3")
        assert "s3" not in si._current

    def test_returns_text_and_memory_id_keys(self):
        import services.session_insight as si
        si._current["s4"] = {
            "text": "insight",
            "memory_id": 7,
            "generated_at": time.time(),
        }
        result = si.get_current("s4")
        assert set(result.keys()) == {"text", "memory_id"}


class TestDismiss:
    def test_dismiss_clears_session_current(self):
        import services.session_insight as si
        si._current["s1"] = {
            "text": "x", "memory_id": None, "generated_at": time.time()
        }
        si.dismiss("s1")
        assert "s1" not in si._current

    def test_dismiss_clears_pm_current(self):
        import services.session_insight as si
        si._pm_current = {"content": "overlay visível", "id": 1}
        si.dismiss("s1")
        assert si._pm_current is None

    def test_dismiss_without_session_still_clears_pm_current(self):
        import services.session_insight as si
        si._pm_current = {"content": "sem cookie", "id": 2}
        si.dismiss("")  # sem session_id (extensão sem cookie)
        assert si._pm_current is None

    def test_dismiss_when_pm_current_already_none_does_not_crash(self):
        from services.session_insight import dismiss
        dismiss("sessao-inexistente")  # não deve levantar

    def test_dismiss_unknown_session_does_not_crash(self):
        import services.session_insight as si
        si._pm_current = None
        si.dismiss("nao-existe")  # nenhum estado para limpar


class TestPmCurrentRoundtrip:
    def test_set_and_get(self):
        from services.session_insight import set_pm_current, get_pm_current
        entry = {"content": "pensamento", "id": 99}
        set_pm_current(entry)
        assert get_pm_current() == entry

    def test_set_none_clears(self):
        from services.session_insight import set_pm_current, get_pm_current
        set_pm_current({"content": "algo"})
        set_pm_current(None)
        assert get_pm_current() is None
