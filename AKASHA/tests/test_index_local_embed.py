"""
Testes para Local 2 — embed_and_index disparado ao indexar arquivo local.

Cobre:
  - Arquivo novo indexado → embed_and_index é agendado (task criada)
  - Arquivo sem mudança (mtime igual) → embed_and_index NÃO é chamado
  - LOGOS offline (embed_and_index retorna False) → FTS5 continua normalmente
  - Exceção em embed_and_index não se propaga para _index_directory
  - Conteúdo passado ao embed inclui título e corpo
  - Múltiplos arquivos → uma task por arquivo novo/modificado
  - Arquivo modificado (mtime novo) → embed re-agendado
  - Extractor falha → embed NÃO chamado (arquivo não foi indexado)

Nota: fire-and-forget usa create_task(); testes drenam o event loop via
asyncio.sleep(0) após chamar _index_directory para garantir execução das tasks.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent))

import services.local_search as ls


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Banco SQLite temporário com local_fts (FTS5) e local_index_meta.

    VECTOR_SEARCH_ENABLED=False para que _reindex não tente carregar sqlite-vec.
    """
    db_path = tmp_path / "akasha_test.db"
    monkeypatch.setattr(ls, "DB_PATH", db_path)
    monkeypatch.setattr(ls, "VECTOR_SEARCH_ENABLED", False)
    monkeypatch.setattr(ls, "_SQLITE_VEC_AVAILABLE", False)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS local_fts "
        "USING fts5(path UNINDEXED, title, body, source UNINDEXED)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS local_index_meta (
            path    TEXT PRIMARY KEY,
            source  TEXT,
            mtime   TEXT,
            lang    TEXT DEFAULT '',
            deleted INTEGER DEFAULT 0
        )"""
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def md_file(tmp_path):
    """Arquivo .md simples para testes de indexação."""
    f = tmp_path / "nota.md"
    f.write_text("---\ntitle: Nota de Teste\n---\nConteúdo de exemplo para teste.")
    return f


def _drain(coro, ticks: int = 5):
    """Executa coroutine e drena tasks pendentes com N ticks de sleep(0)."""
    async def _runner():
        await coro
        for _ in range(ticks):
            await asyncio.sleep(0)
    asyncio.run(_runner())


def _fake_embed(calls: list):
    """Retorna async mock de embed_and_index que registra chamadas."""
    async def _embed(path: str, content: str) -> bool:
        calls.append({"path": path, "content": content})
        return True
    return _embed


def _fake_embed_offline(calls: list):
    """Simula LOGOS offline: registra chamadas mas retorna False."""
    async def _embed(path: str, content: str) -> bool:
        calls.append({"path": path, "content": content})
        return False
    return _embed


def _fake_embed_raises(calls: list):
    """Simula embed que levanta exceção inesperada."""
    async def _embed(path: str, content: str) -> bool:
        calls.append({"path": path, "content": content})
        raise RuntimeError("falha simulada de embedding")
    return _embed


# ---------------------------------------------------------------------------
# Disparo do embed ao indexar
# ---------------------------------------------------------------------------

class TestEmbedFiredOnIndex:

    def test_embed_task_fired_for_new_file(self, tmp_db, md_file, monkeypatch):
        """Indexar arquivo novo → embed_and_index é chamado exatamente uma vez."""
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed(calls))

        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))

        assert len(calls) == 1, (
            f"Esperava 1 chamada a embed_and_index, obteve {len(calls)}"
        )

    def test_embed_called_with_correct_path(self, tmp_db, md_file, monkeypatch):
        """embed_and_index recebe o path absoluto como string."""
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed(calls))

        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))

        assert calls[0]["path"] == str(md_file), (
            f"Path incorreto: esperava {str(md_file)!r}, obteve {calls[0]['path']!r}"
        )

    def test_embed_content_includes_title(self, tmp_db, md_file, monkeypatch):
        """Conteúdo passado ao embed inclui o título do arquivo."""
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed(calls))

        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))

        assert "Nota de Teste" in calls[0]["content"], (
            "Conteúdo enviado ao embed deve incluir o título extraído"
        )

    def test_embed_content_includes_body(self, tmp_db, md_file, monkeypatch):
        """Conteúdo passado ao embed inclui o corpo do arquivo."""
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed(calls))

        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))

        assert "Conteúdo de exemplo" in calls[0]["content"], (
            "Conteúdo enviado ao embed deve incluir o corpo do arquivo"
        )

    def test_one_task_per_new_file(self, tmp_db, tmp_path, monkeypatch):
        """Múltiplos arquivos novos → uma task embed por arquivo."""
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed(calls))

        for i in range(3):
            f = tmp_path / f"doc{i}.md"
            f.write_text(f"---\ntitle: Doc {i}\n---\nCorpo do documento {i}.")

        _drain(ls._index_directory(
            tmp_path, "AKASHA", "**/*.md", ls._extract_kosmos
        ))

        assert len(calls) == 3, (
            f"Esperava 3 tasks embed (uma por arquivo), obteve {len(calls)}"
        )

    def test_embed_not_called_for_unchanged_file(self, tmp_db, md_file, monkeypatch):
        """Arquivo sem mudança de mtime não gera nova task embed."""
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed(calls))

        # Primeira indexação
        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))
        first_count = len(calls)

        # Segunda indexação — mesmo arquivo, mtime não mudou
        calls.clear()
        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))

        assert len(calls) == 0, (
            "Arquivo sem mudança não deve disparar novo embed "
            f"(disparou {len(calls)} após já ter sido indexado)"
        )
        assert first_count == 1

    def test_embed_fired_again_on_modified_file(self, tmp_db, md_file, monkeypatch):
        """Arquivo modificado (mtime novo) → embed re-agendado."""
        import time as _time
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed(calls))

        # Primeira indexação
        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))
        assert len(calls) == 1

        # Modifica o arquivo (mtime muda)
        _time.sleep(0.05)
        md_file.write_text("---\ntitle: Nota Atualizada\n---\nNovo conteúdo.")

        calls.clear()
        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))

        assert len(calls) == 1, (
            "Arquivo modificado deve disparar novo embed"
        )


# ---------------------------------------------------------------------------
# FTS5 continua normalmente quando embed falha
# ---------------------------------------------------------------------------

class TestFTS5ContinuesWhenEmbedFails:

    def test_fts5_indexed_when_logos_offline(self, tmp_db, md_file, monkeypatch):
        """FTS5 deve ter a entrada mesmo quando LOGOS está offline (embed retorna False)."""
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed_offline(calls))

        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT path FROM local_fts WHERE path = ?", (str(md_file),)
        ).fetchone()
        conn.close()

        assert row is not None, (
            "Entrada FTS5 deve existir mesmo quando LOGOS está offline"
        )
        assert len(calls) == 1, "embed_and_index deve ter sido chamado mesmo offline"

    def test_fts5_indexed_when_embed_raises(self, tmp_db, md_file, monkeypatch):
        """FTS5 deve ter a entrada mesmo quando embed_and_index levanta exceção."""
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed_raises(calls))

        # Não deve levantar exceção
        try:
            _drain(ls._index_directory(
                md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
            ))
        except Exception as exc:
            pytest.fail(
                f"_index_directory não deve propagar exceção de embed_and_index: {exc}"
            )

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT path FROM local_fts WHERE path = ?", (str(md_file),)
        ).fetchone()
        conn.close()

        assert row is not None, "Entrada FTS5 deve existir mesmo com exceção no embed"

    def test_index_directory_never_raises_from_embed(self, tmp_db, md_file, monkeypatch):
        """_index_directory não propaga nenhuma exceção originada em embed_and_index."""
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed_raises([]))

        try:
            _drain(ls._index_directory(
                md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
            ))
        except Exception as exc:
            pytest.fail(f"_index_directory levantou exceção: {exc}")

    def test_fts5_meta_updated_when_logos_offline(self, tmp_db, md_file, monkeypatch):
        """local_index_meta deve ser atualizado mesmo com LOGOS offline."""
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed_offline([]))

        _drain(ls._index_directory(
            md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
        ))

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT mtime FROM local_index_meta WHERE path = ?", (str(md_file),)
        ).fetchone()
        conn.close()

        assert row is not None, "local_index_meta deve registrar o arquivo"
        assert row[0] is not None, "mtime deve estar preenchido"


# ---------------------------------------------------------------------------
# Sem embed para arquivos que falharam no extractor
# ---------------------------------------------------------------------------

class TestNoEmbedOnExtractorFailure:

    def test_embed_not_called_when_extractor_raises(self, tmp_db, tmp_path, monkeypatch):
        """Se extractor lançar exceção, embed_and_index NÃO deve ser chamado."""
        calls: list = []
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed(calls))

        # Extractor que sempre falha
        def _bad_extractor(path):
            raise ValueError("formato inválido")

        # Cria arquivo para que o loop entre nele
        f = tmp_path / "bad.md"
        f.write_text("conteúdo malformado")

        _drain(ls._index_directory(tmp_path, "AKASHA", "**/*.md", _bad_extractor))

        assert len(calls) == 0, (
            "embed_and_index não deve ser chamado quando extractor falha"
        )


# ---------------------------------------------------------------------------
# Logs de debug
# ---------------------------------------------------------------------------

class TestEmbedLogs:

    def test_debug_log_when_embed_scheduled(self, tmp_db, md_file, monkeypatch, caplog):
        """Log de debug deve aparecer indicando que embed foi agendado."""
        import logging
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed([]))

        with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
            _drain(ls._index_directory(
                md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
            ))

        assert any(
            "embed" in r.message.lower() and "agendado" in r.message.lower()
            for r in caplog.records
        ), "Esperava log de debug confirmando agendamento do embed"

    def test_debug_log_includes_filename(self, tmp_db, md_file, monkeypatch, caplog):
        """Log de debug deve mencionar o path do arquivo."""
        import logging
        monkeypatch.setattr(ls, "embed_and_index", _fake_embed([]))

        with caplog.at_level(logging.DEBUG, logger="akasha.local_search"):
            _drain(ls._index_directory(
                md_file.parent, "AKASHA", "**/*.md", ls._extract_kosmos
            ))

        assert any(
            "nota.md" in r.message for r in caplog.records
        ), "Log deve mencionar o nome do arquivo sendo agendado"
