"""
Testes para get_related_indexed_pages em database.py e integração em routers/search.py.

Cobre:
  - sem página indexada → lista vazia, sem erro
  - com tópicos → candidatos ordenados por sobreposição decrescente
  - exclusão de current_url e exclude_urls
  - sem sobreposição → lista vazia
  - n limita o número de resultados
  - topics vazia → lista vazia
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rows(*entries: tuple[str, str, list[str]]) -> list[tuple]:
    """Gera linhas (url, title, topics_json) para mock de fetchall."""
    return [(url, title, json.dumps(topics)) for url, title, topics in entries]


# ---------------------------------------------------------------------------
# get_related_indexed_pages — lógica de sobreposição
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_related_empty_when_no_topics():
    """topics vazia → retorna lista vazia sem abrir o banco."""
    import database as db
    result = await db.get_related_indexed_pages("https://a.com", [])
    assert result == []


@pytest.mark.anyio
async def test_related_empty_when_no_rows(monkeypatch):
    """Banco sem nenhum doc → lista vazia."""
    import aiosqlite
    import database as db

    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)

    with patch.object(aiosqlite, "connect", return_value=mock_conn):
        result = await db.get_related_indexed_pages("https://a.com", ["python"])
    assert result == []


@pytest.mark.anyio
async def test_related_excludes_current_url(monkeypatch):
    """current_url não aparece nos resultados mesmo com tópico igual."""
    import aiosqlite
    import database as db

    rows = _make_rows(
        ("https://current.com", "Current", ["python"]),
        ("https://other.com",   "Other",   ["python"]),
    )
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=rows)

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)

    with patch.object(aiosqlite, "connect", return_value=mock_conn):
        result = await db.get_related_indexed_pages("https://current.com", ["python"])

    assert len(result) == 1
    assert result[0]["url"] == "https://other.com"


@pytest.mark.anyio
async def test_related_excludes_extra_urls(monkeypatch):
    """URLs em exclude_urls são ignoradas."""
    import aiosqlite
    import database as db

    rows = _make_rows(
        ("https://a.com", "A", ["python"]),
        ("https://b.com", "B", ["python"]),
        ("https://c.com", "C", ["python"]),
    )
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=rows)

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)

    with patch.object(aiosqlite, "connect", return_value=mock_conn):
        result = await db.get_related_indexed_pages(
            "https://a.com", ["python"],
            exclude_urls=["https://b.com"],
        )

    urls = [r["url"] for r in result]
    assert "https://b.com" not in urls
    assert "https://c.com" in urls


@pytest.mark.anyio
async def test_related_sorted_by_overlap(monkeypatch):
    """Candidatos com mais sobreposição aparecem primeiro."""
    import aiosqlite
    import database as db

    rows = _make_rows(
        ("https://low.com",  "Low",  ["python"]),
        ("https://high.com", "High", ["python", "decorators", "closures"]),
        ("https://mid.com",  "Mid",  ["python", "decorators"]),
    )
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=rows)

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)

    with patch.object(aiosqlite, "connect", return_value=mock_conn):
        result = await db.get_related_indexed_pages(
            "https://current.com",
            ["python", "decorators", "closures"],
        )

    assert result[0]["url"] == "https://high.com"
    assert result[1]["url"] == "https://mid.com"
    assert result[2]["url"] == "https://low.com"


@pytest.mark.anyio
async def test_related_no_overlap_returns_empty(monkeypatch):
    """Docs sem nenhum tópico em comum → lista vazia."""
    import aiosqlite
    import database as db

    rows = _make_rows(
        ("https://unrelated.com", "Unrelated", ["javascript", "react"]),
    )
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=rows)

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)

    with patch.object(aiosqlite, "connect", return_value=mock_conn):
        result = await db.get_related_indexed_pages(
            "https://current.com", ["python", "decorators"]
        )

    assert result == []


@pytest.mark.anyio
async def test_related_respects_n_limit(monkeypatch):
    """Retorna no máximo n resultados."""
    import aiosqlite
    import database as db

    rows = _make_rows(*[
        (f"https://site{i}.com", f"Site {i}", ["python"])
        for i in range(10)
    ])
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=rows)

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)

    with patch.object(aiosqlite, "connect", return_value=mock_conn):
        result = await db.get_related_indexed_pages(
            "https://current.com", ["python"], n=3
        )

    assert len(result) == 3


@pytest.mark.anyio
async def test_related_overlap_field_present(monkeypatch):
    """Cada resultado tem campo 'overlap' com o número de tópicos em comum."""
    import aiosqlite
    import database as db

    rows = _make_rows(
        ("https://doc.com", "Doc", ["python", "typing"]),
    )
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=rows)

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)

    with patch.object(aiosqlite, "connect", return_value=mock_conn):
        result = await db.get_related_indexed_pages(
            "https://current.com", ["python", "typing", "closures"]
        )

    assert result[0]["overlap"] == 2


@pytest.mark.anyio
async def test_related_case_insensitive(monkeypatch):
    """Comparação de tópicos é case-insensitive."""
    import aiosqlite
    import database as db

    rows = _make_rows(
        ("https://doc.com", "Doc", ["Python", "DECORATORS"]),
    )
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=rows)

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)

    with patch.object(aiosqlite, "connect", return_value=mock_conn):
        result = await db.get_related_indexed_pages(
            "https://current.com", ["python", "decorators"]
        )

    assert len(result) == 1
    assert result[0]["overlap"] == 2


# ---------------------------------------------------------------------------
# Integração com routers/search.py — related_indexed no template context
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_search_router_includes_related_indexed(monkeypatch):
    """Quando get_page_knowledge retorna tópicos e há docs relacionados,
    related_indexed chega ao contexto do template."""
    import routers.search as _rs

    # Mock get_page_knowledge → retorna tópicos
    async def _mock_get_pk(url: str):
        return {"topics": ["python", "typing"]}

    # Mock get_related_indexed_pages → retorna 2 docs
    async def _mock_related(current_url, topics, exclude_urls=None, n=3):
        return [
            {"url": "https://a.com", "title": "A", "overlap": 2},
            {"url": "https://b.com", "title": "B", "overlap": 1},
        ]

    import database as db
    monkeypatch.setattr(db, "get_page_knowledge", _mock_get_pk)
    monkeypatch.setattr(db, "get_related_indexed_pages", _mock_related)

    # Simular que a busca produziu um resultado com url
    from services.web_search import SearchResult
    fake_result = SearchResult(title="T", url="https://first.com", snippet="s")

    ctx: dict = {}

    # Patch templates.TemplateResponse para capturar o contexto
    class _FakeResp:
        def __init__(self, *a, **kw): pass
        def set_cookie(self, *a, **kw): pass

    original_tr = _rs.templates.TemplateResponse

    def _capture_ctx(request, name, context, **kw):
        ctx.update(context)
        return _FakeResp()

    monkeypatch.setattr(_rs.templates, "TemplateResponse", _capture_ctx)

    # Patch todas as dependências externas que a busca chama
    monkeypatch.setattr(_rs, "search_local",  AsyncMock(return_value=[fake_result]))
    monkeypatch.setattr(_rs, "search_web",    AsyncMock(return_value=[]))
    monkeypatch.setattr(_rs, "search_sites",  AsyncMock(return_value=[]))
    monkeypatch.setattr(_rs, "search_papers", AsyncMock(return_value=[]))
    monkeypatch.setattr(_rs, "search_kosmos", AsyncMock(return_value=[]))
    monkeypatch.setattr(db, "save_search",        AsyncMock())
    monkeypatch.setattr(db, "record_search_query", AsyncMock())
    monkeypatch.setattr(db, "log_activity",        AsyncMock())
    monkeypatch.setattr(db, "recent_searches",     AsyncMock(return_value=[]))
    monkeypatch.setattr(db, "get_all_crawl_sites", AsyncMock(return_value=[]))
    monkeypatch.setattr(db, "get_favorite_domains", AsyncMock(return_value=set()))
    monkeypatch.setattr(db, "get_top_topics",       AsyncMock(return_value=[]))
    monkeypatch.setattr(_rs, "suggest_related_docs",    AsyncMock(return_value=[]))
    monkeypatch.setattr(_rs, "suggest_related_queries", lambda *a, **kw: [])
    monkeypatch.setattr(_rs, "get_inference_status", lambda: False)
    monkeypatch.setattr(_rs, "classify_intent_lexical", lambda q: "informational")

    from unittest.mock import MagicMock
    mock_request = MagicMock()
    mock_request.cookies.get = lambda k, d=None: None

    # Também mockar session_svc e knowledge_worker para não explodir
    import services.search_session as _ss
    monkeypatch.setattr(_ss, "get_session", lambda sid: None)
    monkeypatch.setattr(_ss, "update_session", lambda *a, **kw: MagicMock(queries=[]))

    import services.session_insight as _si
    monkeypatch.setattr(_si, "maybe_schedule", lambda *a, **kw: None)

    import services.knowledge_worker as _kw
    monkeypatch.setattr(_kw, "schedule_search_update", lambda *a, **kw: None)

    from services.search_profile import SearchProfile
    monkeypatch.setattr(_rs, "load_profile", AsyncMock(return_value=SearchProfile()))
    monkeypatch.setattr(_rs, "_apply_profile", lambda *a: ("on", "on", "on", "", False))
    monkeypatch.setattr(_rs, "_db_search_wl", AsyncMock(return_value=[]))

    await _rs.search(mock_request, q="python typing")

    assert "related_indexed" in ctx
    assert len(ctx["related_indexed"]) == 2
    assert ctx["related_indexed"][0]["url"] == "https://a.com"
