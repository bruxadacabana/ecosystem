"""
Testes para embed_and_index() — Local 1.

Cobre:
  - LOGOS mockado retornando vetor float32 → insere em vec_items + local_vec_paths
  - LOGOS offline (ConnectError / retorno None) → retorna False sem lançar exceção
  - _EmbedError (timeout, modelo não carregado) → retorna False sem lançar exceção
  - sqlite-vec indisponível → retorna False silenciosamente
  - Erro de banco de dados → retorna False silenciosamente
  - Segundo embed do mesmo path → upsert (não duplica linha em local_vec_paths)
  - Log de debug aparece em cada embedding gerado com sucesso
  - Log de debug aparece em cada falha (LOGOS offline, erros)
  - Conteúdo truncado a 2000 chars antes de enviar ao LOGOS
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent))

import services.local_search as ls


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Banco de dados temporário e fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Banco SQLite temporário com vec_items (virtual) e local_vec_paths criados.

    Usa a extensão sqlite-vec real para criar vec_items como virtual table,
    permitindo testar INSERT/SELECT realistas sem o banco de produção.
    """
    import sqlite_vec
    import sqlite3

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(ls, "DB_PATH", db_path)
    monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", True)

    # Cria tabelas com a extensão real — vec_items é virtual table (sqlite-vec)
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS local_vec_paths "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL)"
    )
    # Usa mesma dimensão que os testes — 384 para all-MiniLM / teste padrão
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(embedding FLOAT[384])"
    )
    conn.commit()
    conn.close()

    return db_path


def _make_vec(dims: int = 384) -> list[float]:
    """Gera vetor float normalizado de teste."""
    return [1.0 / dims] * dims


def _mock_embed_logos(vecs: list[list[float]]):
    """Retorna patch de _embed_via_logos que retorna vecs."""
    return patch.object(ls, "_embed_via_logos", return_value=vecs)


def _mock_embed_logos_none():
    """Retorna patch de _embed_via_logos que retorna None (LOGOS offline)."""
    return patch.object(ls, "_embed_via_logos", return_value=None)


def _mock_embed_logos_error(exc: Exception):
    """Retorna patch de _embed_via_logos que levanta exceção."""
    def _raise(*a, **kw):
        raise exc
    return patch.object(ls, "_embed_via_logos", side_effect=_raise)


def _mock_serialize(vec: list[float]) -> bytes:
    """Serialização float32 simples para testes sem sqlite-vec real."""
    import struct
    return struct.pack(f"{len(vec)}f", *vec)


# ---------------------------------------------------------------------------
# Sucesso básico
# ---------------------------------------------------------------------------

class TestEmbedAndIndexSuccess:

    def test_returns_true_on_success(self, tmp_db, monkeypatch):
        """Retorna True quando LOGOS responde e inserção no banco funciona."""
        vec = _make_vec(384)
        with _mock_embed_logos([vec]):
            result = run(ls.embed_and_index("/test/file.md", "conteúdo de teste"))

        assert result is True

    def test_inserts_into_local_vec_paths(self, tmp_db, monkeypatch):
        """Cria entrada em local_vec_paths para o path fornecido."""
        import sqlite3
        import sqlite_vec
        vec = _make_vec(384)
        with _mock_embed_logos([vec]):
            run(ls.embed_and_index("/test/document.md", "texto"))

        conn = sqlite3.connect(tmp_db)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        row = conn.execute(
            "SELECT id FROM local_vec_paths WHERE path = ?", ("/test/document.md",)
        ).fetchone()
        conn.close()
        assert row is not None, "local_vec_paths deve ter entrada para o path"

    def test_inserts_into_vec_items(self, tmp_db, monkeypatch):
        """Cria entrada em vec_items com embedding (verifica presença, não bytes exatos)."""
        import sqlite3, sqlite_vec
        vec = _make_vec(384)
        with _mock_embed_logos([vec]):
            run(ls.embed_and_index("/test/doc.md", "texto"))

        conn = sqlite3.connect(tmp_db)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        row = conn.execute(
            "SELECT lp.id FROM local_vec_paths lp "
            "JOIN vec_items vi ON vi.rowid = lp.id "
            "WHERE lp.path = ?",
            ("/test/doc.md",),
        ).fetchone()
        conn.close()
        assert row is not None, "vec_items deve ter embedding para o path"

    def test_upsert_on_second_call(self, tmp_db, monkeypatch):
        """Segundo call com mesmo path atualiza vec_items sem duplicar local_vec_paths."""
        import sqlite3, sqlite_vec
        vec1 = _make_vec(384)
        vec2 = [2.0 / 384] * 384

        with _mock_embed_logos([vec1]):
            run(ls.embed_and_index("/test/doc.md", "primeira versão"))
        with _mock_embed_logos([vec2]):
            run(ls.embed_and_index("/test/doc.md", "segunda versão"))

        conn = sqlite3.connect(tmp_db)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        count_paths = conn.execute(
            "SELECT COUNT(*) FROM local_vec_paths WHERE path = ?", ("/test/doc.md",)
        ).fetchone()[0]
        row = conn.execute(
            "SELECT lp.id FROM local_vec_paths lp "
            "JOIN vec_items vi ON vi.rowid = lp.id "
            "WHERE lp.path = ?",
            ("/test/doc.md",),
        ).fetchone()
        conn.close()
        assert count_paths == 1, "local_vec_paths não deve duplicar entradas"
        assert row is not None, "vec_items deve ter entrada após dois calls"

    def test_truncates_content_to_2000_chars(self, monkeypatch, tmp_db):
        """Envia no máximo 2000 chars do conteúdo ao LOGOS."""
        captured_texts = []

        def _fake_embed(texts, model=None, **kw):
            captured_texts.extend(texts)
            return [[0.0] * 384]

        monkeypatch.setattr(ls, "_embed_via_logos", _fake_embed)

        long_content = "x" * 5000
        run(ls.embed_and_index("/test/long.md", long_content))

        assert captured_texts, "LOGOS deve ter sido chamado"
        assert len(captured_texts[0]) <= 2000, (
            f"Conteúdo enviado ao LOGOS excede 2000 chars: {len(captured_texts[0])}"
        )


# ---------------------------------------------------------------------------
# LOGOS offline e erros
# ---------------------------------------------------------------------------

class TestEmbedAndIndexFailures:

    def test_returns_false_when_logos_offline(self, tmp_db, monkeypatch):
        """Retorna False sem exceção quando LOGOS não está disponível (None)."""
        with _mock_embed_logos_none():
            result = run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert result is False, "LOGOS offline deve retornar False, não levantar exceção"

    def test_returns_false_on_embed_error(self, tmp_db, monkeypatch):
        """Retorna False quando _embed_via_logos levanta _EmbedError (timeout/501)."""
        with _mock_embed_logos_error(ls._EmbedError("timeout")):
            result = run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert result is False

    def test_returns_false_on_generic_exception(self, tmp_db, monkeypatch):
        """Retorna False para qualquer exceção inesperada do LOGOS."""
        with _mock_embed_logos_error(RuntimeError("conexão recusada")):
            result = run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert result is False

    def test_returns_false_when_sqlite_vec_unavailable(self, monkeypatch, tmp_db):
        """Retorna False quando sqlite-vec não está disponível."""
        monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", False)
        # _embed_via_logos não deve nem ser chamado neste caso
        logos_called = []

        def _fake_embed(texts, **kw):
            logos_called.append(texts)
            return [[0.0] * 384]

        monkeypatch.setattr(ls, "_embed_via_logos", _fake_embed)

        result = run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert result is False
        assert not logos_called, "LOGOS não deve ser chamado quando sqlite-vec indisponível"

    def test_returns_false_on_serialization_error(self, tmp_db, monkeypatch):
        """Retorna False se a serialização do vetor falhar."""
        import types
        vec = _make_vec(384)
        # Substitui _sqlite_vec com namespace que tem serialize_float32 falhando
        bad_sqlite_vec = types.SimpleNamespace(
            serialize_float32=MagicMock(side_effect=ValueError("dimensão inválida")),
            loadable_path=lambda: ls._sqlite_vec.loadable_path(),  # type: ignore
        )
        monkeypatch.setattr(ls, "_sqlite_vec", bad_sqlite_vec)

        with _mock_embed_logos([vec]):
            result = run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert result is False

    def test_returns_false_on_db_error(self, tmp_db, monkeypatch):
        """Retorna False se a inserção no banco falhar."""
        vec = _make_vec(384)
        monkeypatch.setattr(ls, "_sqlite_vec", MagicMock(
            serialize_float32=lambda v: _mock_serialize(v)
        ))
        # Força falha no banco corrompendo o DB_PATH
        monkeypatch.setattr(ls, "DB_PATH", Path("/nonexistent/path/test.db"))
        monkeypatch.setattr(ls, "_load_vec_ext", lambda conn: None)

        with _mock_embed_logos([vec]):
            result = run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert result is False

    def test_does_not_raise_exception_in_any_failure(self, tmp_db, monkeypatch):
        """embed_and_index NUNCA deve levantar exceção — sempre retorna bool."""
        scenarios = [
            _mock_embed_logos_none(),
            _mock_embed_logos_error(ls._EmbedError("timeout")),
            _mock_embed_logos_error(RuntimeError("inesperado")),
        ]
        for scenario in scenarios:
            with scenario:
                try:
                    result = run(ls.embed_and_index("/test/file.md", "conteúdo"))
                    assert isinstance(result, bool), f"Deve retornar bool, obteve {type(result)}"
                except Exception as exc:
                    pytest.fail(f"embed_and_index levantou exceção inesperada: {exc}")


# ---------------------------------------------------------------------------
# Logs de debug
# ---------------------------------------------------------------------------

class TestEmbedAndIndexLogs:

    def test_debug_log_on_success(self, tmp_db, monkeypatch, caplog):
        """Log de debug deve aparecer quando embedding é gerado com sucesso."""
        vec = _make_vec(384)
        with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
            with _mock_embed_logos([vec]):
                run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert any("embed_and_index" in r.message and "gerado" in r.message
                   for r in caplog.records), (
            "Esperava log de debug indicando embedding gerado com sucesso"
        )

    def test_debug_log_on_logos_offline(self, tmp_db, monkeypatch, caplog):
        """Log de debug deve aparecer quando LOGOS está offline."""
        with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
            with _mock_embed_logos_none():
                run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert any("embed_and_index" in r.message for r in caplog.records), (
            "Esperava log de debug quando LOGOS offline"
        )

    def test_debug_log_on_embed_error(self, tmp_db, monkeypatch, caplog):
        """Log de debug deve aparecer quando _EmbedError é levantado."""
        with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
            with _mock_embed_logos_error(ls._EmbedError("timeout")):
                run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert any("embed_and_index" in r.message for r in caplog.records)

    def test_debug_log_includes_dims(self, tmp_db, monkeypatch, caplog):
        """Log de debug deve incluir a dimensão do vetor gerado."""
        vec = _make_vec(384)
        with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
            with _mock_embed_logos([vec]):
                run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert any("384" in r.message for r in caplog.records), (
            "Esperava log indicando dimensão do vetor (384)"
        )

    def test_debug_log_includes_path(self, tmp_db, monkeypatch, caplog):
        """Log de debug deve incluir o path do arquivo."""
        vec = _make_vec(384)
        with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
            with _mock_embed_logos([vec]):
                run(ls.embed_and_index("/test/specific_file.md", "conteúdo"))

        assert any("specific_file.md" in r.message for r in caplog.records), (
            "Esperava log incluindo o path do arquivo"
        )

    def test_no_sqlite_vec_log(self, monkeypatch, tmp_db, caplog):
        """Log de debug aparece quando sqlite-vec indisponível."""
        monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", False)

        with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
            run(ls.embed_and_index("/test/file.md", "conteúdo"))

        assert any("sqlite-vec" in r.message for r in caplog.records), (
            "Esperava log indicando sqlite-vec indisponível"
        )
