"""
Testes do retry com backoff em embed_text (BUG-020).

embed_text() chama LOGOS POST /v1/embeddings. Sob concorrência o embed-server
pode retornar HTTP 500/503 transiente; o cliente re-tenta até 3 vezes com
backoff exponencial. Falhas não-transientes (offline, 4xx) não re-tentam.

Cenários cobertos:
  1. Sucesso na 1ª tentativa → sem retry, nenhum sleep
  2. 500 nas 2 primeiras, 200 na 3ª → sucede
  3. 500 sempre → retorna None após 3 tentativas + loga 3 warnings
  4. 503 também dispara retry
  5. 4xx (ex: 400) → não re-tenta, retorna None
  6. LOGOS offline (ConnectError) → retorna None, não re-tenta
  7. Texto vazio → retorna None sem chamada HTTP
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import services.semantic_search as ss


# ---------------------------------------------------------------------------
# Fake AsyncClient — devolve respostas/exceções em sequência, uma por post()
# ---------------------------------------------------------------------------

class _FakeAsyncClient:
    _script: list = []          # sequência de httpx.Response | Exception
    calls: list = []            # registro de chamadas (uma por post)

    def __init__(self, *args, **kwargs) -> None:  # noqa: ARG002
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> bool:  # noqa: ARG002
        return False

    async def post(self, url: str, json=None):  # noqa: ARG002, A002
        idx = len(_FakeAsyncClient.calls)
        _FakeAsyncClient.calls.append(url)
        item = _FakeAsyncClient._script[idx]
        if isinstance(item, Exception):
            raise item
        # Cliente real anexa o request à resposta — necessário p/ raise_for_status.
        item.request = httpx.Request("POST", url)
        return item


def _ok(vec: list[float]) -> httpx.Response:
    return httpx.Response(
        200, json={"object": "list", "data": [{"embedding": vec, "index": 0}]}
    )


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zera waits, fixa URL/modelo e injeta o fake client + script limpo."""
    monkeypatch.setattr(ss, "_EMBED_RETRY_WAITS", (0.0, 0.0, 0.0))
    monkeypatch.setattr(ss, "_get_inference_url", lambda: "http://logos-test")
    monkeypatch.setattr(ss, "_get_embed_model", lambda: "test-embed")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.calls = []
    _FakeAsyncClient._script = []


def _set_script(*items) -> None:
    _FakeAsyncClient._script = list(items)


# ---------------------------------------------------------------------------
# 1. Sucesso imediato
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sucesso_primeira_tentativa_sem_retry() -> None:
    _set_script(_ok([0.1, 0.2, 0.3]))
    result = await ss.embed_text("uma frase")
    assert result == [0.1, 0.2, 0.3]
    assert len(_FakeAsyncClient.calls) == 1  # nenhuma re-tentativa


@pytest.mark.asyncio
async def test_sucesso_nao_chama_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list = []
    import asyncio
    monkeypatch.setattr(asyncio, "sleep", lambda s: slept.append(s) or _noop())
    _set_script(_ok([1.0]))
    await ss.embed_text("x")
    assert slept == []


async def _noop() -> None:
    return None


# ---------------------------------------------------------------------------
# 2. Retry transiente → sucesso
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_500_duas_vezes_depois_sucesso() -> None:
    _set_script(httpx.Response(500), httpx.Response(500), _ok([0.7, 0.8]))
    result = await ss.embed_text("retry me")
    assert result == [0.7, 0.8]
    assert len(_FakeAsyncClient.calls) == 3


# ---------------------------------------------------------------------------
# 3. Falha transiente persistente → None + 3 warnings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_500_sempre_retorna_none_e_loga_3_warnings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    _set_script(httpx.Response(500), httpx.Response(500), httpx.Response(500))
    with caplog.at_level("WARNING", logger="akasha.semantic_search"):
        result = await ss.embed_text("always fail")
    assert result is None
    assert len(_FakeAsyncClient.calls) == 3
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 3


@pytest.mark.asyncio
async def test_503_tambem_dispara_retry() -> None:
    _set_script(httpx.Response(503), _ok([0.42]))
    result = await ss.embed_text("flaky")
    assert result == [0.42]
    assert len(_FakeAsyncClient.calls) == 2


# ---------------------------------------------------------------------------
# 4. Falhas não-transientes → sem retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_400_nao_retenta_retorna_none() -> None:
    # 400 não está em {500, 503}; raise_for_status levanta → capturado → None.
    # Só 1 item no script: se houvesse retry, IndexError explodiria.
    _set_script(httpx.Response(400))
    result = await ss.embed_text("bad request")
    assert result is None
    assert len(_FakeAsyncClient.calls) == 1


@pytest.mark.asyncio
async def test_offline_connect_error_retorna_none_sem_retry() -> None:
    _set_script(httpx.ConnectError("connection refused"))
    result = await ss.embed_text("offline")
    assert result is None
    assert len(_FakeAsyncClient.calls) == 1


# ---------------------------------------------------------------------------
# 5. Texto vazio — curto-circuito antes de qualquer HTTP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_texto_vazio_retorna_none_sem_http() -> None:
    _set_script(_ok([0.0]))  # nunca deve ser consumido
    result = await ss.embed_text("   ")
    assert result is None
    assert len(_FakeAsyncClient.calls) == 0
