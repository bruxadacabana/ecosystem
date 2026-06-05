"""
Testes de contrato: Mnemosyne → LOGOS /v1/embeddings via _embed_batch.

Todos os cenários que envolvem rede usam httpx.MockTransport ou patch de
httpx.post — sem servidor real, sem LOGOS ativo.

Cenários:
  1. _embed_batch com modelo remoto → chama /v1/embeddings, retorna vetores
  2. _embed_batch com potion-multilingual-128M → usa model2vec local, nunca rede
  3. Timeout na primeira tentativa → retenta e retorna na segunda
  4. Timeout em todas as tentativas → levanta EmbedTimeoutError
  5. 429 na primeira tentativa → retenta e retorna na segunda
  6. 429 em todas as tentativas → levanta EmbedTimeoutError
  7. 501 Not Implemented → raise_for_status propaga HTTPStatusError
  8. _InferenceEmbeddings.embed_documents → chama _embed_batch corretamente
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_BASE = "http://logos-test:7072"
_FAKE_MODEL = "test-embed-model"
_FAKE_VECTOR = [0.1, 0.2, 0.3, 0.4]
_FAKE_REQUEST = httpx.Request("POST", f"{_FAKE_BASE}/v1/embeddings")


def _ok_response(vectors: list[list[float]]) -> httpx.Response:
    data = [{"embedding": v, "index": i, "object": "embedding"} for i, v in enumerate(vectors)]
    resp = httpx.Response(200, json={"object": "list", "data": data, "model": _FAKE_MODEL})
    resp.request = _FAKE_REQUEST
    return resp


def _error_response(status: int) -> httpx.Response:
    resp = httpx.Response(status, json={"error": f"HTTP {status}"})
    resp.request = _FAKE_REQUEST
    return resp


class _SequentialResponder:
    """Retorna respostas/exceções em sequência, uma por chamada a httpx.post."""

    def __init__(self, items: list) -> None:
        self._iter: Iterator = iter(items)

    def __call__(self, url: str, **kwargs) -> httpx.Response:
        item = next(self._iter)
        if isinstance(item, Exception):
            raise item
        return item


# ---------------------------------------------------------------------------
# 1. Chamada bem-sucedida retorna vetores corretos
# ---------------------------------------------------------------------------

def test_embed_batch_success_returns_vectors():
    from core.indexer import _embed_batch

    responder = _SequentialResponder([_ok_response([_FAKE_VECTOR])])
    with patch("httpx.post", side_effect=responder):
        result = _embed_batch(["texto de teste"], model=_FAKE_MODEL, base_url=_FAKE_BASE)

    assert result == [_FAKE_VECTOR]


def test_embed_batch_multiple_texts():
    from core.indexer import _embed_batch

    vecs = [[0.1, 0.2], [0.3, 0.4]]
    responder = _SequentialResponder([_ok_response(vecs)])
    with patch("httpx.post", side_effect=responder):
        result = _embed_batch(["texto 1", "texto 2"], model=_FAKE_MODEL, base_url=_FAKE_BASE)

    assert result == vecs


# ---------------------------------------------------------------------------
# (POTION/model2vec removido — embedding é sempre bge-m3 via LOGOS, BUG-031)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 3. Timeout na primeira tentativa → retenta e retorna na segunda
# ---------------------------------------------------------------------------

def test_embed_batch_timeout_retries_and_succeeds():
    from core.indexer import _embed_batch, _EMBED_RETRY_WAITS

    responder = _SequentialResponder([
        httpx.TimeoutException("timeout"),
        _ok_response([_FAKE_VECTOR]),
    ])
    with patch("httpx.post", side_effect=responder):
        with patch("time.sleep"):  # sem espera real nos testes
            result = _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)

    assert result == [_FAKE_VECTOR]


# ---------------------------------------------------------------------------
# 4. Timeout em todas as tentativas → levanta EmbedTimeoutError
# ---------------------------------------------------------------------------

def test_embed_batch_timeout_all_raises():
    from core.indexer import _embed_batch, _EMBED_RETRY_WAITS, EmbedTimeoutError

    n_attempts = 1 + len(_EMBED_RETRY_WAITS)
    timeouts = [httpx.TimeoutException("timeout")] * n_attempts
    responder = _SequentialResponder(timeouts)

    with patch("httpx.post", side_effect=responder):
        with patch("time.sleep"):
            with pytest.raises(EmbedTimeoutError):
                _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)


# ---------------------------------------------------------------------------
# 5. 429 na primeira tentativa → retenta e retorna na segunda
# ---------------------------------------------------------------------------

def test_embed_batch_429_retries_and_succeeds():
    from core.indexer import _embed_batch

    responder = _SequentialResponder([
        _error_response(429),
        _ok_response([_FAKE_VECTOR]),
    ])
    with patch("httpx.post", side_effect=responder):
        with patch("time.sleep"):
            result = _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)

    assert result == [_FAKE_VECTOR]


# ---------------------------------------------------------------------------
# 6. 429 em todas as tentativas → levanta EmbedTimeoutError
# ---------------------------------------------------------------------------

def test_embed_batch_429_all_raises():
    from core.indexer import _embed_batch, _EMBED_RETRY_WAITS, EmbedTimeoutError

    n_attempts = 1 + len(_EMBED_RETRY_WAITS)
    responses = [_error_response(429)] * n_attempts
    responder = _SequentialResponder(responses)

    with patch("httpx.post", side_effect=responder):
        with patch("time.sleep"):
            with pytest.raises(EmbedTimeoutError):
                _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)


# ---------------------------------------------------------------------------
# 7. 501 Not Implemented → raise_for_status levanta HTTPStatusError
# ---------------------------------------------------------------------------

def test_embed_batch_501_raises_http_status_error():
    from core.indexer import _embed_batch

    responder = _SequentialResponder([_error_response(501)])
    with patch("httpx.post", side_effect=responder):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)

    assert exc_info.value.response.status_code == 501


# ---------------------------------------------------------------------------
# 7b. BUG-020: 500/503 transientes → retry com backoff (mesma branch do 429)
# ---------------------------------------------------------------------------

def test_embed_batch_500_retries_and_succeeds():
    from core.indexer import _embed_batch

    responder = _SequentialResponder([
        _error_response(500),
        _ok_response([_FAKE_VECTOR]),
    ])
    with patch("httpx.post", side_effect=responder):
        with patch("time.sleep"):
            result = _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)

    assert result == [_FAKE_VECTOR]


def test_embed_batch_503_retries_and_succeeds():
    from core.indexer import _embed_batch

    responder = _SequentialResponder([
        _error_response(503),
        _ok_response([_FAKE_VECTOR]),
    ])
    with patch("httpx.post", side_effect=responder):
        with patch("time.sleep"):
            result = _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)

    assert result == [_FAKE_VECTOR]


def test_embed_batch_500_all_raises_after_3_attempts():
    from core.indexer import _embed_batch, _EMBED_RETRY_WAITS, EmbedTimeoutError

    n_attempts = 1 + len(_EMBED_RETRY_WAITS)
    responses = [_error_response(500)] * n_attempts
    responder = _SequentialResponder(responses)

    with patch("httpx.post", side_effect=responder):
        with patch("time.sleep"):
            with pytest.raises(EmbedTimeoutError):
                _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)


def test_embed_batch_500_logs_warning_per_attempt(caplog):
    from core.indexer import _embed_batch, _EMBED_RETRY_WAITS, EmbedTimeoutError

    n_attempts = 1 + len(_EMBED_RETRY_WAITS)
    responses = [_error_response(503)] * n_attempts
    responder = _SequentialResponder(responses)

    with patch("httpx.post", side_effect=responder):
        with patch("time.sleep"):
            with caplog.at_level("WARNING"):
                with pytest.raises(EmbedTimeoutError):
                    _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"
                and "_embed_batch" in r.getMessage()]
    assert len(warnings) == n_attempts


def test_embed_batch_500_no_retry_on_success_first_try():
    """Sucesso na 1ª tentativa não dispara retry nem sleep."""
    from core.indexer import _embed_batch

    responder = _SequentialResponder([_ok_response([_FAKE_VECTOR])])
    with patch("httpx.post", side_effect=responder):
        with patch("time.sleep") as mock_sleep:
            result = _embed_batch(["texto"], model=_FAKE_MODEL, base_url=_FAKE_BASE)

    assert result == [_FAKE_VECTOR]
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# 8. _InferenceEmbeddings.embed_documents → chama _embed_batch com modelo correto
# ---------------------------------------------------------------------------

def test_inference_embeddings_embed_documents_calls_embed_batch():
    from core.indexer import _InferenceEmbeddings
    import core.indexer as _idx

    mock_vecs = [[0.1, 0.2, 0.3]]
    with patch.object(_idx, "_embed_batch", return_value=mock_vecs) as mock_eb:
        emb = _InferenceEmbeddings("my-embed-model")
        result = emb.embed_documents(["texto"])

    mock_eb.assert_called_once_with(["texto"], "my-embed-model")
    assert result == mock_vecs


def test_inference_embeddings_embed_query_returns_single_vector():
    from core.indexer import _InferenceEmbeddings
    import core.indexer as _idx

    mock_vec = [0.5, 0.6]
    with patch.object(_idx, "_embed_batch", return_value=[mock_vec]):
        emb = _InferenceEmbeddings("my-embed-model")
        result = emb.embed_query("consulta única")

    assert result == mock_vec
