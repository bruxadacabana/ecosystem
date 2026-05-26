"""
Contrato AKASHA + Mnemosyne → LOGOS /v1/embeddings.

Ambos os apps devem:
  1. Enviar request JSON com campos "model" e "input" (lista de strings)
  2. Aceitar resposta com campo "data": [{"embedding": [...]}]
  3. Extrair apenas a lista de vetores float da resposta

Qualquer divergência de formato entre os dois callers e o LOGOS quebra
silenciosamente — este arquivo garante que ambos seguem o mesmo contrato.

Também cobre:
  4. get_inference_url() retorna sempre LOGOS (porta 7072)
  5. get_inference_url() não falha em import time (lazy read)
  6. ecosystem_client importa sem erro mesmo sem ecosystem.json presente
  7. Recovery E2E: AKASHA search_local com LOGOS offline retorna lista, não exception
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import httpx
import pytest

_ECO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ECO_ROOT))
_AKASHA_ROOT = _ECO_ROOT / "AKASHA"
sys.path.insert(0, str(_AKASHA_ROOT))


# ---------------------------------------------------------------------------
# Helpers — contrato de formato do request/response
# ---------------------------------------------------------------------------

_LOGOS_EMBEDDINGS_URL_SUFFIX = "/v1/embeddings"

# Shape obrigatória do request OpenAI-embeddings
_VALID_REQUEST_SCHEMA = {
    "required": ["model", "input"],
    "types": {"model": str, "input": list},
}

# Shape obrigatória da resposta
_VALID_RESPONSE_SCHEMA = {
    "required": ["data"],
    "data_item_required": ["embedding"],
}


def _validate_request(payload: dict) -> None:
    """Valida que o payload segue o contrato OpenAI-embeddings."""
    for field in _VALID_REQUEST_SCHEMA["required"]:
        assert field in payload, f"campo '{field}' obrigatório ausente no request"
    for field, expected_type in _VALID_REQUEST_SCHEMA["types"].items():
        assert isinstance(payload[field], expected_type), \
            f"'{field}' deve ser {expected_type.__name__}"
    assert all(isinstance(t, str) for t in payload["input"]), \
        "'input' deve ser lista de strings"


def _validate_response_parsing(result: list[list[float]]) -> None:
    """Valida que o resultado extraído é lista de vetores float."""
    assert isinstance(result, list)
    for vec in result:
        assert isinstance(vec, list)
        assert all(isinstance(v, float) for v in vec)


def _make_logos_response(n_texts: int, dim: int = 4) -> httpx.Response:
    """Cria resposta mock do LOGOS /v1/embeddings."""
    data = [{"embedding": [0.1 * i] * dim, "index": i} for i in range(n_texts)]
    req = httpx.Request("POST", "http://logos-test:7072/v1/embeddings")
    resp = httpx.Response(200, json={"object": "list", "data": data, "model": "test"})
    resp.request = req
    return resp


# ---------------------------------------------------------------------------
# 1. AKASHA: _embed_via_logos envia request com formato correto
# ---------------------------------------------------------------------------

def test_akasha_embed_request_format():
    """_embed_via_logos (AKASHA) deve enviar model + input como lista de strings."""
    try:
        from services.local_search import _embed_via_logos
    except ImportError:
        pytest.skip("AKASHA deps (aiosqlite) não disponíveis neste venv")

    captured_payload: list[dict] = []

    class _CaptureTransport(httpx.BaseTransport):
        def handle_request(self, request):
            captured_payload.append(json.loads(request.content))
            return _make_logos_response(1)

    _embed_via_logos(["texto de busca"], model="test-model", _transport=_CaptureTransport())

    assert len(captured_payload) == 1
    _validate_request(captured_payload[0])


# ---------------------------------------------------------------------------
# 2. AKASHA: _embed_via_logos extrai vetores corretamente da resposta
# ---------------------------------------------------------------------------

def test_akasha_embed_response_parsing():
    """_embed_via_logos deve retornar lista de vetores float."""
    try:
        from services.local_search import _embed_via_logos
    except ImportError:
        pytest.skip("AKASHA deps (aiosqlite) não disponíveis neste venv")

    class _MockTransport(httpx.BaseTransport):
        def handle_request(self, request):
            return _make_logos_response(2, dim=3)

    result = _embed_via_logos(["texto 1", "texto 2"], model="test", _transport=_MockTransport())

    assert result is not None
    _validate_response_parsing(result)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# 3. Mnemosyne: _embed_batch envia request com formato correto
# ---------------------------------------------------------------------------

def test_mnemosyne_embed_request_format():
    """_embed_batch (Mnemosyne) deve enviar model + input como lista de strings."""
    _MNE_ROOT = _ECO_ROOT / "Mnemosyne"
    sys.path.insert(0, str(_MNE_ROOT))

    try:
        from core.indexer import _embed_batch
    except ImportError:
        pytest.skip("Mnemosyne core não disponível")

    captured: list[dict] = []

    def _fake_post(url: str, json: dict, **kw) -> httpx.Response:
        captured.append(json)
        return _make_logos_response(1)

    with patch("httpx.post", side_effect=_fake_post):
        _embed_batch(["texto de indexação"], model="remote-model", base_url="http://logos-test:7072")

    assert len(captured) == 1
    _validate_request(captured[0])


# ---------------------------------------------------------------------------
# 4. Mnemosyne: _embed_batch extrai vetores corretamente
# ---------------------------------------------------------------------------

def test_mnemosyne_embed_response_parsing():
    """_embed_batch deve retornar lista de vetores float."""
    _MNE_ROOT = _ECO_ROOT / "Mnemosyne"
    sys.path.insert(0, str(_MNE_ROOT))

    try:
        from core.indexer import _embed_batch
    except ImportError:
        pytest.skip("Mnemosyne core não disponível")

    def _fake_post(url: str, json: dict, **kw) -> httpx.Response:
        return _make_logos_response(3, dim=8)

    with patch("httpx.post", side_effect=_fake_post):
        result = _embed_batch(
            ["a", "b", "c"],
            model="remote-model",
            base_url="http://logos-test:7072",
        )

    _validate_response_parsing(result)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# 5. get_inference_url() retorna porta LOGOS (7072) — não 11434 nem 8080
# ---------------------------------------------------------------------------

def test_get_inference_url_returns_logos_port():
    """get_inference_url() deve retornar URL com porta 7072 do LOGOS."""
    import ecosystem_client as ec

    url = ec.get_inference_url()
    assert "7072" in url, f"esperado porta 7072, URL: {url}"
    assert "11434" not in url, "11434 é Ollama (legado) — não deve ser retornado"


# ---------------------------------------------------------------------------
# 6. ecosystem_client importa sem erro mesmo sem ecosystem.json
# ---------------------------------------------------------------------------

def test_ecosystem_client_imports_without_ecosystem_json():
    """import ecosystem_client não deve falhar quando ecosystem.json está ausente."""
    with tempfile.TemporaryDirectory() as td:
        # Simula ambiente sem ecosystem.json
        with patch.dict("os.environ", {"APPDATA": td}):
            with patch("ecosystem_client.Path.home", return_value=Path(td)):
                # Re-importar não é seguro em testes; usar a função de leitura diretamente
                import ecosystem_client as ec
                result = ec.read_ecosystem()

    assert isinstance(result, dict), "read_ecosystem() deve retornar dict (pode ser vazio)"


# ---------------------------------------------------------------------------
# 7. Recovery E2E: LOGOS offline → AKASHA search_local retorna lista (não 500)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_akasha_search_local_logos_offline_returns_list():
    """Com LOGOS offline, search_local retorna lista vazia/resultados FTS — nunca propaga exceção."""
    import asyncio
    import tempfile
    import sqlite3 as _sq

    try:
        import services.local_search as ls
    except ImportError:
        pytest.skip("AKASHA deps não disponíveis neste venv")

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "akasha_test.db"
        con = _sq.connect(str(db))
        con.executescript("""
            CREATE VIRTUAL TABLE local_fts USING fts5(
                path UNINDEXED, title, body, source UNINDEXED,
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TABLE local_index_meta(
                path TEXT PRIMARY KEY, source TEXT NOT NULL,
                mtime TEXT NOT NULL, lang TEXT NOT NULL DEFAULT '', deleted INTEGER NOT NULL DEFAULT 0
            );
        """)
        con.commit()
        con.close()

        with (
            patch.object(ls, "DB_PATH", db),
            patch.object(ls, "_inference_available", False),
            patch.object(ls, "_CHROMA_AVAILABLE", False),
            patch.object(ls, "VECTOR_SEARCH_ENABLED", False),
        ):
            result = await ls.search_local("qualquer busca", expand=False)

    assert isinstance(result, list), "search_local deve retornar lista, mesmo com LOGOS offline"
