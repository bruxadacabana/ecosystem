"""
Testes para Semântico 4c — fallback vetorial por latência (hardware sem AVX2).

Cobre:
  - Delays [300ms, 280ms, 320ms] → média 300ms → _vector_too_slow=True na 3ª chamada
  - Delays [300ms, 80ms, 100ms] → média 160ms → _vector_too_slow=False
  - Após flag setada, chamada subsequente retorna [] sem executar KNN
  - Média calculada só após 3 amostras (não antes)
  - reset_latency_state() reseta o estado para testes isolados
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_state():
    """Reseta o estado de latência antes de cada teste."""
    from services.semantic_search import reset_latency_state
    reset_latency_state()
    yield
    reset_latency_state()


# ---------------------------------------------------------------------------
# Testes de detecção de latência
# ---------------------------------------------------------------------------

class TestVectorLatencyDetection:

    def _make_slow_db_mock(self, delays_ms: list[float]):
        """Cria mocks de aiosqlite que simulam delays de KNN."""
        call_count = [0]

        class _FakeRows:
            async def fetchall(self):
                return []

        class _FakeCursor:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass

        class _FakeDB:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def enable_load_extension(self, v):
                pass
            async def load_extension(self, p):
                pass
            async def execute(self, sql, params=None):
                # Injeta delay no KNN (não na criação de tabela)
                if "MATCH" in (sql or ""):
                    delay = delays_ms[call_count[0] % len(delays_ms)] / 1000
                    call_count[0] += 1
                    await asyncio.sleep(delay)
                return _FakeRows()

        return _FakeDB(), call_count

    def test_slow_hardware_sets_flag_on_third_call(self, monkeypatch):
        """Delays [300,280,320]ms → média 300ms > 250ms → _vector_too_slow=True na 3ª chamada."""
        import services.semantic_search as _mod

        delays = [0.300, 0.280, 0.320]  # segundos
        call_count = [0]

        async def _fake_embed(text):
            return [0.1] * 768

        monkeypatch.setattr(_mod, "embed_text", _fake_embed)
        monkeypatch.setattr(_mod, "_SQLITE_VEC_AVAILABLE", True)
        monkeypatch.setattr(_mod, "_LATENCY_THRESHOLD_MS", 250.0)
        monkeypatch.setattr(_mod, "_LATENCY_SAMPLES_NEEDED", 3)

        orig_serialize = _mod._sqlite_vec.serialize_float32 if _mod._sqlite_vec else None

        class _FakeRows:
            async def fetchall(self):
                return []

        class _FakeDB:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def enable_load_extension(self, v):
                pass
            async def load_extension(self, p):
                pass
            async def execute(self, sql, params=None):
                if "MATCH" in (sql or ""):
                    delay = delays[call_count[0] % len(delays)]
                    call_count[0] += 1
                    await asyncio.sleep(delay)
                return _FakeRows()

        with patch("services.semantic_search._sqlite_vec") as _sv:
            _sv.serialize_float32 = lambda v: b"\x00" * (len(v) * 4)

            with patch("aiosqlite.connect", return_value=_FakeDB()):
                # 1ª chamada — ainda colhendo amostras
                run(_mod.semantic_search_local("query 1"))
                assert not _mod._vector_too_slow
                assert len(_mod._latency_samples) == 1

                # 2ª chamada
                run(_mod.semantic_search_local("query 2"))
                assert not _mod._vector_too_slow
                assert len(_mod._latency_samples) == 2

                # 3ª chamada — média calculada e flag setada
                run(_mod.semantic_search_local("query 3"))
                assert _mod._vector_too_slow, "Flag deve ser setada após 3 amostras lentas"

    def test_fast_hardware_does_not_set_flag(self, monkeypatch):
        """Delays [300,80,100]ms → média 160ms < 250ms → _vector_too_slow=False."""
        import services.semantic_search as _mod

        delays = [0.300, 0.080, 0.100]
        call_count = [0]

        async def _fake_embed(text):
            return [0.1] * 768

        monkeypatch.setattr(_mod, "embed_text", _fake_embed)
        monkeypatch.setattr(_mod, "_SQLITE_VEC_AVAILABLE", True)
        monkeypatch.setattr(_mod, "_LATENCY_THRESHOLD_MS", 250.0)
        monkeypatch.setattr(_mod, "_LATENCY_SAMPLES_NEEDED", 3)

        class _FakeRows:
            async def fetchall(self):
                return []

        class _FakeDB:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def enable_load_extension(self, v):
                pass
            async def load_extension(self, p):
                pass
            async def execute(self, sql, params=None):
                if "MATCH" in (sql or ""):
                    delay = delays[call_count[0] % len(delays)]
                    call_count[0] += 1
                    await asyncio.sleep(delay)
                return _FakeRows()

        with patch("services.semantic_search._sqlite_vec") as _sv:
            _sv.serialize_float32 = lambda v: b"\x00" * (len(v) * 4)

            with patch("aiosqlite.connect", return_value=_FakeDB()):
                run(_mod.semantic_search_local("q1"))
                run(_mod.semantic_search_local("q2"))
                run(_mod.semantic_search_local("q3"))

        assert not _mod._vector_too_slow, (
            f"Hardware rápido não deve setar a flag (amostras: {_mod._latency_samples})"
        )

    def test_flag_skips_knn_on_subsequent_call(self, monkeypatch):
        """Após _vector_too_slow=True, chamada subsequente retorna [] sem KNN."""
        import services.semantic_search as _mod

        monkeypatch.setattr(_mod, "_vector_too_slow", True)
        monkeypatch.setattr(_mod, "_SQLITE_VEC_AVAILABLE", True)

        knn_called = []

        async def _fake_embed(text):
            return [0.1] * 768

        monkeypatch.setattr(_mod, "embed_text", _fake_embed)

        class _FakeDB:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def enable_load_extension(self, v):
                pass
            async def load_extension(self, p):
                pass
            async def execute(self, sql, params=None):
                if "MATCH" in (sql or ""):
                    knn_called.append(sql)

                class _R:
                    async def fetchall(self):
                        return []
                return _R()

        with patch("aiosqlite.connect", return_value=_FakeDB()):
            result = run(_mod.semantic_search_local("query"))

        assert result == [], "Com flag ativa, resultado deve ser []"
        assert not knn_called, "KNN não deve ser executado quando flag ativa"

    def test_flag_not_set_before_three_samples(self, monkeypatch):
        """Flag não é setada antes de acumular 3 amostras, mesmo se cada uma > threshold."""
        import services.semantic_search as _mod

        async def _fake_embed(text):
            return [0.1] * 768

        monkeypatch.setattr(_mod, "embed_text", _fake_embed)
        monkeypatch.setattr(_mod, "_SQLITE_VEC_AVAILABLE", True)
        monkeypatch.setattr(_mod, "_LATENCY_THRESHOLD_MS", 250.0)
        monkeypatch.setattr(_mod, "_LATENCY_SAMPLES_NEEDED", 3)

        call_count = [0]

        class _FakeRows:
            async def fetchall(self):
                return []

        class _FakeDB:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def enable_load_extension(self, v):
                pass
            async def load_extension(self, p):
                pass
            async def execute(self, sql, params=None):
                if "MATCH" in (sql or ""):
                    call_count[0] += 1
                    await asyncio.sleep(0.400)  # 400ms > threshold
                return _FakeRows()

        with patch("services.semantic_search._sqlite_vec") as _sv:
            _sv.serialize_float32 = lambda v: b"\x00" * (len(v) * 4)

            with patch("aiosqlite.connect", return_value=_FakeDB()):
                # 1ª chamada: 1 amostra — flag não deve estar setada
                run(_mod.semantic_search_local("q1"))
                assert not _mod._vector_too_slow, "Flag não deve ser setada com apenas 1 amostra"

                # 2ª chamada: 2 amostras — flag não deve estar setada
                run(_mod.semantic_search_local("q2"))
                assert not _mod._vector_too_slow, "Flag não deve ser setada com apenas 2 amostras"

    def test_reset_clears_state(self, monkeypatch):
        """reset_latency_state() limpa amostras e flag."""
        import services.semantic_search as _mod

        # Seta estado artificialmente
        monkeypatch.setattr(_mod, "_vector_too_slow", True)
        _mod._latency_samples = [300.0, 280.0, 320.0]

        _mod.reset_latency_state()

        assert not _mod._vector_too_slow
        assert _mod._latency_samples == []

    def test_get_vector_too_slow_reflects_flag(self, monkeypatch):
        """get_vector_too_slow() reflete o estado atual da flag."""
        import services.semantic_search as _mod

        monkeypatch.setattr(_mod, "_vector_too_slow", False)
        assert not _mod.get_vector_too_slow()

        monkeypatch.setattr(_mod, "_vector_too_slow", True)
        assert _mod.get_vector_too_slow()
