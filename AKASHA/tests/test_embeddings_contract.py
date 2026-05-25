"""
Testes de contrato: _embed_via_logos → LOGOS /v1/embeddings.

Todos os cenários usam httpx.MockTransport (sem servidor real).
O módulo services.local_search é importado com _inference_base_url
apontando para "http://logos-test" para que as URLs montadas sejam
determinísticas nos asserts.

Cenários cobertos:
  1. Chamada bem-sucedida → retorna lista de vetores por texto
  2. Timeout na primeira tentativa → retenta e retorna na segunda
  3. Timeout em todas as tentativas → levanta _EmbedError
  4. 429 na primeira tentativa → retenta e retorna na segunda
  5. 429 em todas as tentativas → levanta _EmbedError
  6. 501 Not Implemented → levanta _EmbedError imediatamente (sem retry)
  7. ConnectError (LOGOS offline) → retorna None, não propaga
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import httpx
import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import services.local_search as ls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_response(vectors: list[list[float]]) -> httpx.Response:
    """Resposta 200 com payload OpenAI-compatível."""
    data = [{"embedding": v, "index": i, "object": "embedding"} for i, v in enumerate(vectors)]
    return httpx.Response(200, json={"object": "list", "data": data, "model": "test-embed"})


class _SequentialTransport(httpx.BaseTransport):
    """Retorna respostas/exceções em sequência, uma por chamada."""

    def __init__(self, items: list) -> None:
        self._items: Iterator = iter(items)

    def handle_request(self, request: httpx.Request) -> httpx.Response:  # noqa: ARG002
        item = next(self._items)
        if isinstance(item, Exception):
            raise item
        return item


def _transport(*items) -> _SequentialTransport:
    return _SequentialTransport(list(items))


# ---------------------------------------------------------------------------
# Fixture — zera os waits de retry para que testes não durmam
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ls, "_LOGOS_EMBED_RETRY_WAITS", (0, 0))
    monkeypatch.setattr(ls, "_inference_base_url", "http://logos-test")


# ---------------------------------------------------------------------------
# 1. Chamada bem-sucedida
# ---------------------------------------------------------------------------

class TestSuccess:
    def test_returns_vectors(self) -> None:
        vecs = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        t = _transport(_ok_response(vecs))
        result = ls._embed_via_logos(["texto A", "texto B"], model="bge-m3", _transport=t)
        assert result == vecs

    def test_single_text(self) -> None:
        vecs = [[1.0, 0.0]]
        t = _transport(_ok_response(vecs))
        result = ls._embed_via_logos(["única frase"], model="bge-m3", _transport=t)
        assert result == vecs

    def test_url_uses_inference_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Confirma que a URL montada aponta ao _inference_base_url."""
        captured: list[str] = []

        class _CapturingTransport(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                captured.append(str(request.url))
                return _ok_response([[0.0]])

        ls._embed_via_logos(["x"], model="m", _transport=_CapturingTransport())
        assert captured == ["http://logos-test/v1/embeddings"]


# ---------------------------------------------------------------------------
# 2. Timeout → retry, sucesso na segunda tentativa
# ---------------------------------------------------------------------------

class TestTimeoutRetry:
    def test_timeout_then_success(self) -> None:
        vecs = [[0.9, 0.1]]
        t = _transport(httpx.TimeoutException("timed out"), _ok_response(vecs))
        result = ls._embed_via_logos(["q"], model="m", _transport=t)
        assert result == vecs

    def test_all_timeouts_raise_embed_error(self) -> None:
        # 1 tentativa inicial + 2 retries = 3 TimeoutExceptions
        t = _transport(
            httpx.TimeoutException("t1"),
            httpx.TimeoutException("t2"),
            httpx.TimeoutException("t3"),
        )
        with pytest.raises(ls._EmbedError, match="timeout"):
            ls._embed_via_logos(["q"], model="m", _transport=t)

    def test_embed_error_message_contains_model(self) -> None:
        t = _transport(
            httpx.TimeoutException("t"),
            httpx.TimeoutException("t"),
            httpx.TimeoutException("t"),
        )
        with pytest.raises(ls._EmbedError) as exc_info:
            ls._embed_via_logos(["q"], model="meu-modelo", _transport=t)
        assert "meu-modelo" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. 429 → retry, sucesso na segunda tentativa
# ---------------------------------------------------------------------------

class TestRateLimitRetry:
    def test_429_then_success(self) -> None:
        vecs = [[0.5, 0.5]]
        t = _transport(httpx.Response(429), _ok_response(vecs))
        result = ls._embed_via_logos(["q"], model="m", _transport=t)
        assert result == vecs

    def test_all_429_raise_embed_error(self) -> None:
        t = _transport(httpx.Response(429), httpx.Response(429), httpx.Response(429))
        with pytest.raises(ls._EmbedError):
            ls._embed_via_logos(["q"], model="m", _transport=t)

    def test_429_retry_count_matches_waits(self) -> None:
        """Número de tentativas = 1 + len(_LOGOS_EMBED_RETRY_WAITS)."""
        calls: list[int] = []

        class _CountTransport(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                calls.append(1)
                return httpx.Response(429)

        with pytest.raises(ls._EmbedError):
            ls._embed_via_logos(["q"], model="m", _transport=_CountTransport())

        expected_calls = 1 + len(ls._LOGOS_EMBED_RETRY_WAITS)
        assert len(calls) == expected_calls


# ---------------------------------------------------------------------------
# 4. 501 Not Implemented → levanta _EmbedError imediatamente, sem retry
# ---------------------------------------------------------------------------

class TestNotImplemented:
    def test_501_raises_embed_error(self) -> None:
        # Apenas 1 item na sequência — se houvesse retry, StopIteration explodiria
        t = _transport(httpx.Response(501))
        with pytest.raises(ls._EmbedError, match="501"):
            ls._embed_via_logos(["q"], model="m", _transport=t)

    def test_501_no_retry(self) -> None:
        """Verifica que só há 1 chamada HTTP (sem retry)."""
        calls: list[int] = []

        class _CountTransport(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                calls.append(1)
                return httpx.Response(501)

        with pytest.raises(ls._EmbedError):
            ls._embed_via_logos(["q"], model="m", _transport=_CountTransport())

        assert len(calls) == 1

    def test_501_error_message_mentions_model(self) -> None:
        t = _transport(httpx.Response(501))
        with pytest.raises(ls._EmbedError) as exc_info:
            ls._embed_via_logos(["q"], model="meu-embed-model", _transport=t)
        assert "meu-embed-model" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 5. ConnectError (LOGOS offline) → retorna None, não propaga
# ---------------------------------------------------------------------------

class TestOffline:
    def test_connect_error_returns_none(self) -> None:
        t = _transport(httpx.ConnectError("connection refused"))
        result = ls._embed_via_logos(["q"], model="m", _transport=t)
        assert result is None

    def test_connect_error_does_not_raise(self) -> None:
        t = _transport(httpx.ConnectError("offline"))
        try:
            ls._embed_via_logos(["q"], model="m", _transport=t)
        except Exception as exc:
            pytest.fail(f"ConnectError não deveria propagar, mas levantou: {exc!r}")

    def test_offline_result_is_not_empty_list(self) -> None:
        """None ≠ [] — caller distingue 'offline' de 'nenhum resultado'."""
        t = _transport(httpx.ConnectError("offline"))
        result = ls._embed_via_logos(["q"], model="m", _transport=t)
        assert result is None
        assert result != []
