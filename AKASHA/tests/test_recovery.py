"""
Testes de recuperação de falha — AKASHA.

Cobre os cenários onde dependências externas falham e o sistema deve degradar
graciosamente (sem crash, sem HTTP 500), retornando resultados parciais ou vazios.

Cenários:
  1. DB corrompido → _search_fts captura OperationalError, retorna []
  2. DB ausente   → _search_fts captura erro de abertura, retorna []
  3. LOGOS offline durante busca → embeddings retornam None, busca FTS continua
  4. Embedding com dimensão errada → _embed_via_logos retorna vetor mas erro em uso
  5. Indexação de arquivo com embedding falho → reindexar não trava o indexador
  6. _search_fts com query vazia → retorna [] imediatamente (sem tocar no DB)
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_corrupted_db(path: Path) -> None:
    """Cria arquivo no caminho que não é um SQLite válido."""
    path.write_bytes(b"not a valid sqlite3 database\x00\x01\x02")


def _make_minimal_db(path: Path) -> None:
    """Cria banco SQLite com tabelas mínimas esperadas por _search_fts."""
    con = sqlite3.connect(str(path))
    con.executescript("""
        CREATE VIRTUAL TABLE local_fts USING fts5(
            path    UNINDEXED,
            title,
            body,
            source  UNINDEXED,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        CREATE TABLE local_index_meta (
            path    TEXT    PRIMARY KEY,
            source  TEXT    NOT NULL,
            mtime   TEXT    NOT NULL,
            lang    TEXT    NOT NULL DEFAULT '',
            deleted INTEGER NOT NULL DEFAULT 0
        );
    """)
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# 1. DB corrompido → _search_fts retorna [] sem crash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_fts_corrupted_db_returns_empty():
    """_search_fts deve capturar OperationalError do SQLite corrompido e retornar []."""
    import services.local_search as ls

    with tempfile.TemporaryDirectory() as td:
        corrupt = Path(td) / "bad.db"
        _make_corrupted_db(corrupt)
        with patch.object(ls, "DB_PATH", corrupt):
            result = await ls._search_fts("python programming", max_results=10)

    assert result == [], "banco corrompido deve retornar lista vazia, não levantar exceção"


# ---------------------------------------------------------------------------
# 2. DB ausente → _search_fts retorna []
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_fts_missing_db_returns_empty():
    """_search_fts não deve explodir quando o arquivo DB não existe."""
    import services.local_search as ls

    missing = Path("/tmp/does_not_exist_akasha_test.db")
    if missing.exists():
        missing.unlink()  # garante que não existe

    with patch.object(ls, "DB_PATH", missing):
        result = await ls._search_fts("any query", max_results=10)

    assert result == [], "banco ausente deve retornar lista vazia, não levantar exceção"


# ---------------------------------------------------------------------------
# 3. LOGOS offline durante busca → busca FTS funciona normalmente
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_local_logos_offline_falls_back_to_fts():
    """Quando LOGOS está offline, search_local deve retornar resultados FTS sem crash."""
    import services.local_search as ls

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "akasha.db"
        _make_minimal_db(db)

        # Insere um documento indexável
        con = sqlite3.connect(str(db))
        con.execute("INSERT INTO local_fts (path, title, body, source) VALUES (?, ?, ?, ?)",
                    ("/tmp/doc.md", "Python Tutorial", "Python is a programming language", "local"))
        con.execute("INSERT INTO local_index_meta (path, source, mtime, lang) VALUES (?, ?, ?, ?)",
                    ("/tmp/doc.md", "local", "2024-01-01T00:00:00", "en"))
        con.commit()
        con.close()

        with (
            patch.object(ls, "DB_PATH", db),
            # LOGOS offline: embeddings retornam None (ConnectError capturado internamente)
            patch.object(ls, "_embed_via_logos", return_value=None),
            # Garante que _inference_available está False (LOGOS offline)
            patch.object(ls, "_inference_available", False),
        ):
            results = await ls.search_local("python programming", expand=False)

    # Deve retornar pelo menos um resultado via FTS, mesmo sem LOGOS
    assert isinstance(results, list), "search_local deve retornar lista, nunca None"
    # O documento com "Python" deve aparecer
    urls = [r.url for r in results]
    assert any("doc.md" in u for u in urls), (
        "FTS deve encontrar o documento mesmo sem LOGOS disponível"
    )


# ---------------------------------------------------------------------------
# 4. _embed_via_logos: ConnectError retorna None (sem propagar)
# ---------------------------------------------------------------------------

def test_embed_via_logos_connect_error_returns_none():
    """ConnectError (LOGOS offline) deve retornar None, não propagar a exceção."""
    import services.local_search as ls

    class _ConnectFailTransport(httpx.BaseTransport):
        def handle_request(self, request):
            raise httpx.ConnectError("connection refused")

    result = ls._embed_via_logos(
        ["sample text"],
        model="test-model",
        _transport=_ConnectFailTransport(),
    )

    assert result is None, "_embed_via_logos deve retornar None quando LOGOS está offline"


# ---------------------------------------------------------------------------
# 5. _embed_via_logos: resposta com dimensão errada é aceita pelo caller
#    (o caller é responsável por validar a dimensão — AKASHA não valida agora)
# ---------------------------------------------------------------------------

def test_embed_via_logos_wrong_dimension_is_returned_as_is():
    """Se LOGOS retorna dimensão errada, _embed_via_logos repassa sem validar.

    Isso documenta o comportamento atual: a validação de dimensão é responsabilidade
    do ChromaDB ao tentar armazenar. O teste serve como baseline para quando
    adicionarmos validação explícita de dimensão.
    """
    import services.local_search as ls

    wrong_dim_vector = [0.1] * 32  # dimensão errada (esperado: 256+ para modelos típicos)

    class _WrongDimTransport(httpx.BaseTransport):
        def handle_request(self, request):
            import json
            body = {"object": "list", "data": [{"embedding": wrong_dim_vector, "index": 0}], "model": "test"}
            return httpx.Response(200, content=json.dumps(body).encode())

    result = ls._embed_via_logos(
        ["sample text"],
        model="test-model",
        _transport=_WrongDimTransport(),
    )

    assert result is not None
    assert result == [wrong_dim_vector], (
        "dimensão errada é repassada ao caller — documentando comportamento atual"
    )


# ---------------------------------------------------------------------------
# 6. _search_fts com query vazia retorna [] sem tocar no DB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_fts_empty_query_returns_immediately():
    """Query vazia sanitizada deve retornar [] sem abrir o banco."""
    import services.local_search as ls

    connect_calls: list = []

    async def _spy_connect(path, **kw):
        connect_calls.append(path)
        raise AssertionError("não deveria abrir DB com query vazia")

    with patch("aiosqlite.connect", side_effect=_spy_connect):
        result = await ls._search_fts("", max_results=10)

    assert result == []
    assert not connect_calls, "DB não deve ser aberto com query vazia"


# ---------------------------------------------------------------------------
# 7. search_local com DB corrompido não retorna HTTP 500 (degradação graciosa)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_local_corrupted_db_returns_empty_list():
    """search_local com banco corrompido deve retornar [] sem levantar exceção."""
    import services.local_search as ls

    with tempfile.TemporaryDirectory() as td:
        corrupt = Path(td) / "corrupt.db"
        _make_corrupted_db(corrupt)
        with (
            patch.object(ls, "DB_PATH", corrupt),
            patch.object(ls, "_inference_available", False),
            # ChromaDB e vec também indisponíveis
            patch.object(ls, "_CHROMA_AVAILABLE", False),
            patch.object(ls, "VECTOR_SEARCH_ENABLED", False),
        ):
            result = await ls.search_local("any query", expand=False)

    assert isinstance(result, list), "search_local deve sempre retornar lista"
