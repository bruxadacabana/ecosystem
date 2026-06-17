"""
Garantia: a AKASHA-ferramenta funciona com a IA DESLIGADA.

Com `get_inference_status()` retornando False, uma busca via `GET /search` deve:
  - retornar resultados (FTS5 local + web) usando só o fallback léxico;
  - NÃO chamar nenhum LLM (classify_intent / rewrite_query / score_ambiguity ficam
    gateados — aqui são substituídos por guardas que falham se chamados);
  - gravar `search_history` + `activity_log('search')`.

Trava contra regressão: se algum dia uma chamada de LLM no caminho de busca deixar
de ser gateada por `get_inference_status()`, este teste falha.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _llm_guard(*_a, **_k):
    raise AssertionError("LLM não pode ser chamado com a IA desligada")


@pytest.mark.anyio
async def test_search_works_without_ia(db_paths):
    main_path, _ = db_paths
    import routers.search as rs
    SR = rs.SearchResult

    local = SR(title="Local FTS5", url="https://local.example/a", snippet="t", source="ECO")
    web   = SR(title="Web result", url="https://web.example/b",   snippet="t", source="WEB")

    with (
        # IA desligada
        patch.object(rs, "get_inference_status", lambda: False),
        # Qualquer LLM chamado → falha (prova que ficam gateados)
        patch.object(rs, "classify_intent", AsyncMock(side_effect=_llm_guard)),
        patch.object(rs, "rewrite_query",   AsyncMock(side_effect=_llm_guard)),
        patch.object(rs, "score_ambiguity", AsyncMock(side_effect=_llm_guard)),
        # Fontes determinísticas (sem rede)
        patch.object(rs, "search_local",        AsyncMock(return_value=[local])),
        patch.object(rs, "_resolve_lang_search", AsyncMock(return_value=[web])),
        patch.object(rs, "_local_qualifies_for_priority", lambda *a, **k: False),
        patch.object(rs, "search_sites",        AsyncMock(return_value=[])),
        patch.object(rs, "search_papers",       AsyncMock(return_value=[])),
        patch.object(rs, "search_kosmos",       AsyncMock(return_value=[])),
        patch.object(rs, "search_images_quick", AsyncMock(return_value=[])),
        patch.object(rs, "search_videos_quick", AsyncMock(return_value=[])),
    ):
        from main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get("/search", params={"q": "amigurumi", "src_web": "on", "src_eco": "on"})

    assert resp.status_code == 200
    body = resp.text
    assert "local.example" in body, "resultado local (FTS5) deve aparecer com IA off"
    assert "web.example" in body, "resultado web deve aparecer com IA off"

    # Histórico gravado mesmo com a IA desligada
    conn = sqlite3.connect(str(main_path))
    try:
        sh = conn.execute(
            "SELECT count FROM search_history WHERE query = ?", ("amigurumi",)
        ).fetchone()
        assert sh is not None and sh[0] >= 1, "search_history deve registrar a query"
        act = conn.execute(
            "SELECT COUNT(*) FROM activity_log WHERE type = 'search'"
        ).fetchone()
        assert act[0] >= 1, "activity_log deve ter um evento 'search'"
    finally:
        conn.close()
