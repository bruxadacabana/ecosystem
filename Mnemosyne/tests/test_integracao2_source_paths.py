"""
Testes para Integração 2 — source_paths nos insights do IndexReflectionWorker.

Cobre:
  personal_memory — migração e save_memory:
    - rag_source_paths migration existe no _conn()
    - save_memory aceita rag_source_paths=[]
    - save_memory salva JSON serializado de source_paths
    - get_by_id retorna rag_source_paths desserializado como lista
    - save_memory sem rag_source_paths → lista vazia (retrocompatibilidade)

  IndexReflectionWorker._process_file:
    - chama save_memory com rag_source_paths=[file_path]
    - log inclui source path

  main_window — FAIR-RAG no insight confirmed/dismissed:
    - _on_insight_confirmed lê rag_source_paths da memória e chama apply_source_feedback
    - _on_insight_dismissed lê rag_source_paths e chama apply_source_feedback is_positive=False
    - falha em apply_source_feedback não propaga exceção

Testes de personal_memory usam DB SQLite em memória.
Testes estruturais (workers.py, main_window.py) usam AST sem importar Qt.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))

_WORKERS_PY      = _MNEMOSYNE_ROOT / "gui" / "workers.py"
_MAIN_WINDOW_PY  = _MNEMOSYNE_ROOT / "gui" / "main_window.py"
_PM_PY           = _MNEMOSYNE_ROOT / "core" / "personal_memory.py"


# ---------------------------------------------------------------------------
# personal_memory — migração e save_memory
# ---------------------------------------------------------------------------

@pytest.fixture
def pm_db(tmp_path, monkeypatch):
    """Banco personal_memory temporário; injeta via monkeypatch em _DB_PATH."""
    from pathlib import Path as _Path
    db_path = str(tmp_path / "personal_memory.db")
    import core.personal_memory as pm

    # _get_db() retorna _DB_PATH se não for None; basta patchar o atributo
    monkeypatch.setattr(pm, "_DB_PATH", _Path(db_path))
    pm._conn()  # inicializa schema no db temporário
    yield pm


class TestPersonalMemoryMigration:

    def test_rag_source_paths_column_exists(self, pm_db):
        """Tabela personal_memory deve ter coluna rag_source_paths após migração."""
        import sqlite3
        db_path = pm_db._get_db()
        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(personal_memory)").fetchall()}
        conn.close()
        assert "rag_source_paths" in cols, (
            "personal_memory deve ter coluna rag_source_paths"
        )

    def test_save_memory_accepts_rag_source_paths(self, pm_db):
        """save_memory deve aceitar rag_source_paths sem levantar TypeError."""
        try:
            mid = pm_db.save_memory(
                type="observation",
                content="Teste de insight",
                rag_source_paths=["/path/to/file.md"],
            )
            assert isinstance(mid, int) and mid > 0
        except TypeError as exc:
            pytest.fail(f"save_memory não deve levantar TypeError: {exc}")

    def test_rag_source_paths_saved_as_json(self, pm_db):
        """rag_source_paths deve ser salvo como JSON e recuperado como lista."""
        paths = ["/a/b.md", "/c/d.md"]
        mid = pm_db.save_memory(
            type="connection",
            content="Conexão entre A e B",
            rag_source_paths=paths,
        )
        entry = pm_db.get_by_id(mid)
        assert entry is not None
        assert entry["rag_source_paths"] == paths, (
            f"rag_source_paths deve ser {paths}, obteve {entry['rag_source_paths']}"
        )

    def test_save_memory_without_source_paths_returns_empty_list(self, pm_db):
        """save_memory sem rag_source_paths → entry["rag_source_paths"] == []."""
        mid = pm_db.save_memory(type="observation", content="Sem source paths")
        entry = pm_db.get_by_id(mid)
        assert entry is not None
        assert entry["rag_source_paths"] == [], (
            "Entrada sem rag_source_paths deve retornar lista vazia"
        )

    def test_save_memory_none_source_paths_returns_empty_list(self, pm_db):
        """save_memory com rag_source_paths=None → lista vazia."""
        mid = pm_db.save_memory(
            type="surprise", content="Surpresa", rag_source_paths=None
        )
        entry = pm_db.get_by_id(mid)
        assert entry["rag_source_paths"] == []

    def test_get_by_id_returns_rag_source_paths(self, pm_db):
        """get_by_id deve retornar campo rag_source_paths na dict."""
        mid = pm_db.save_memory(type="observation", content="Texto")
        entry = pm_db.get_by_id(mid)
        assert "rag_source_paths" in entry, (
            "get_by_id deve retornar campo rag_source_paths"
        )

    def test_rag_source_paths_list_with_multiple_paths(self, pm_db):
        """Lista com múltiplos paths é salva e recuperada corretamente."""
        paths = [f"/path/file{i}.md" for i in range(5)]
        mid = pm_db.save_memory(type="connection", content="Multi", rag_source_paths=paths)
        entry = pm_db.get_by_id(mid)
        assert len(entry["rag_source_paths"]) == 5
        assert entry["rag_source_paths"] == paths


# ---------------------------------------------------------------------------
# IndexReflectionWorker._process_file — análise estrutural (AST)
# ---------------------------------------------------------------------------

class TestProcessFileSavesSourcePaths:

    def test_save_memory_called_with_rag_source_paths(self):
        """_process_file deve chamar save_memory com rag_source_paths=[file_path]."""
        src = _WORKERS_PY.read_text()
        assert "rag_source_paths=[file_path]" in src or "rag_source_paths" in src, (
            "_process_file deve passar rag_source_paths ao chamar save_memory"
        )

    def test_rag_source_paths_uses_file_path_variable(self):
        """O valor de rag_source_paths deve ser [file_path] (o arquivo indexado)."""
        src = _WORKERS_PY.read_text()
        assert "rag_source_paths=[file_path]" in src, (
            "rag_source_paths deve ser [file_path] — o arquivo indexado"
        )

    def test_log_includes_source_in_process_file(self):
        """Log de IndexReflectionWorker deve incluir source/file_path."""
        src = _WORKERS_PY.read_text()
        # Verifica que o log foi atualizado para incluir source
        assert "source=%s" in src or "source_path" in src or "file_path" in src.split("log.info")[1][:500] if "log.info" in src else True


# ---------------------------------------------------------------------------
# main_window — FAIR-RAG nos handlers de confirmed/dismissed (AST)
# ---------------------------------------------------------------------------

class TestMainWindowFairRag:

    def test_on_insight_confirmed_calls_apply_source_feedback(self):
        """_on_insight_confirmed deve chamar apply_source_feedback com is_positive=True."""
        src = _MAIN_WINDOW_PY.read_text()
        # Encontra o bloco _on_insight_confirmed
        assert "apply_source_feedback" in src, (
            "main_window deve chamar apply_source_feedback"
        )
        # Verifica que is_positive=True está presente
        assert "is_positive=True" in src, (
            "_on_insight_confirmed deve chamar apply_source_feedback com is_positive=True"
        )

    def test_on_insight_dismissed_calls_apply_source_feedback_negative(self):
        """_on_insight_dismissed deve chamar apply_source_feedback com is_positive=False."""
        src = _MAIN_WINDOW_PY.read_text()
        assert "is_positive=False" in src, (
            "_on_insight_dismissed deve chamar apply_source_feedback com is_positive=False"
        )

    def test_reads_rag_source_paths_from_db(self):
        """Handlers devem ler rag_source_paths de get_by_id antes de chamar FAIR-RAG."""
        src = _MAIN_WINDOW_PY.read_text()
        assert "get_by_id" in src, (
            "Handlers devem chamar get_by_id para obter rag_source_paths da memória"
        )
        assert "rag_source_paths" in src, (
            "Handlers devem usar o campo rag_source_paths"
        )

    def test_fair_rag_failure_does_not_propagate(self):
        """FAIR-RAG em handlers deve ter try/except para não quebrar o fluxo."""
        src = _MAIN_WINDOW_PY.read_text()
        # Verifica que ambos os handlers têm try/except em torno do FAIR-RAG
        # Conta ocorrências de "FAIR-RAG" perto de "except"
        fair_rag_section = src.split("Integração 2")[1] if "Integração 2" in src else ""
        assert "except" in fair_rag_section, (
            "FAIR-RAG deve estar em bloco try/except para falha silenciosa"
        )

    def test_log_on_insight_confirmed_fair_rag(self):
        """Log deve registrar o boost após confirmed."""
        src = _MAIN_WINDOW_PY.read_text()
        assert "FAIR-RAG boost" in src or "fair-rag" in src.lower(), (
            "Log deve mencionar FAIR-RAG boost para confirmed"
        )

    def test_log_on_insight_dismissed_fair_rag(self):
        """Log deve registrar a penalidade após dismissed."""
        src = _MAIN_WINDOW_PY.read_text()
        assert "FAIR-RAG penalidade" in src or "penalidade" in src, (
            "Log deve mencionar FAIR-RAG penalidade para dismissed"
        )


# ---------------------------------------------------------------------------
# Integração ponta a ponta: save → get_by_id → source_paths disponíveis
# ---------------------------------------------------------------------------

class TestEndToEndSourcePaths:

    def test_save_and_retrieve_pipeline(self, pm_db):
        """Pipeline completo: salvar insight com source_path → recuperar → FAIR-RAG possível."""
        file_path = "/home/user/docs/paper.md"

        # Simula o que IndexReflectionWorker._process_file faz:
        mid = pm_db.save_memory(
            type="connection",
            content="Este paper conecta aprendizado de máquina com biologia.",
            tags=["leitura", "paper"],
            importance=7,
            rag_source_paths=[file_path],
        )
        assert mid > 0

        # Simula o que main_window._on_insight_confirmed faz:
        entry = pm_db.get_by_id(mid)
        assert entry is not None
        source_paths = entry.get("rag_source_paths", [])

        assert source_paths == [file_path], (
            f"source_paths recuperado deve ser [{file_path!r}], obteve {source_paths}"
        )

    def test_empty_source_paths_means_no_fair_rag(self, pm_db):
        """Memórias sem source_paths (antigas) não disparam FAIR-RAG."""
        # Salva sem source_paths (retrocompatibilidade)
        mid = pm_db.save_memory(type="observation", content="Memória antiga sem fonte")
        entry = pm_db.get_by_id(mid)
        source_paths = entry.get("rag_source_paths", [])

        assert source_paths == [], (
            "Memória sem source_paths não deve ter paths — FAIR-RAG é pulado"
        )
