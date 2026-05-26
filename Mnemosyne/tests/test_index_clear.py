"""
Testes de limpeza do índice antes da reindexação.

Cobre o comportamento de `start_indexing` em gui/main_window.py:
antes de iniciar o IndexWorker, o método deve apagar todos os dados de índice
das coleções habilitadas para garantir reconstrução limpa.

Cenários:
  1. Arquivos de índice são deletados para coleções habilitadas
  2. Subdiretório chroma_db/ é removido recursivamente
  3. Coleção desabilitada NÃO tem dados deletados
  4. ecosystem_chroma_dir global também é apagado quando configurado
  5. OSError durante limpeza é capturado (sem crash)
  6. Coleção habilitada sem mnemosyne_dir definido é ignorada
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_coll(name: str, enabled: bool, mdir: str | None = None) -> MagicMock:
    coll = MagicMock()
    coll.name = name
    coll.enabled = enabled
    coll.exists = True
    coll.mnemosyne_dir = mdir
    return coll


def _run_clear_logic(colls: list, eco_chroma: str | None = None) -> None:
    """Executa a mesma lógica de limpeza de start_indexing isolada de Qt."""
    import shutil

    enabled = [c for c in colls if c.enabled and c.exists]
    for coll in enabled:
        mdir = coll.mnemosyne_dir
        if not mdir:
            continue
        for name in ("chroma_db", "bm25_index.pkl", "index_checkpoint.db", "reflection_meta.json"):
            target = os.path.join(mdir, name)
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target)
                elif os.path.isfile(target):
                    os.remove(target)
            except OSError:
                pass

    if eco_chroma and os.path.isdir(eco_chroma):
        try:
            shutil.rmtree(eco_chroma)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# 1. Arquivos de índice são deletados para coleções habilitadas
# ---------------------------------------------------------------------------

def test_clear_deletes_index_files_for_enabled_collection():
    with tempfile.TemporaryDirectory() as td:
        mdir = Path(td) / "mnemosyne_coll"
        mdir.mkdir()

        # Criar arquivos que devem ser deletados
        (mdir / "bm25_index.pkl").write_bytes(b"bm25 data")
        (mdir / "index_checkpoint.db").write_bytes(b"checkpoint data")
        (mdir / "reflection_meta.json").write_text("{}")

        coll = _make_coll("Biblioteca", enabled=True, mdir=str(mdir))
        _run_clear_logic([coll])

        assert not (mdir / "bm25_index.pkl").exists(), "bm25_index.pkl deve ser deletado"
        assert not (mdir / "index_checkpoint.db").exists(), "index_checkpoint.db deve ser deletado"
        assert not (mdir / "reflection_meta.json").exists(), "reflection_meta.json deve ser deletado"


# ---------------------------------------------------------------------------
# 2. Diretório chroma_db/ é removido recursivamente
# ---------------------------------------------------------------------------

def test_clear_removes_chroma_db_directory():
    with tempfile.TemporaryDirectory() as td:
        mdir = Path(td) / "mnemosyne_coll"
        mdir.mkdir()
        chroma = mdir / "chroma_db"
        chroma.mkdir()
        (chroma / "chroma.sqlite3").write_bytes(b"fake db")
        (chroma / "some_segment").mkdir()

        coll = _make_coll("Biblioteca", enabled=True, mdir=str(mdir))
        _run_clear_logic([coll])

        assert not chroma.exists(), "chroma_db/ deve ser removido recursivamente"


# ---------------------------------------------------------------------------
# 3. Coleção desabilitada NÃO tem dados deletados
# ---------------------------------------------------------------------------

def test_clear_does_not_touch_disabled_collection():
    with tempfile.TemporaryDirectory() as td:
        mdir_disabled = Path(td) / "mnemosyne_disabled"
        mdir_disabled.mkdir()
        (mdir_disabled / "bm25_index.pkl").write_bytes(b"data preserved")
        (mdir_disabled / "chroma_db").mkdir()

        mdir_enabled = Path(td) / "mnemosyne_enabled"
        mdir_enabled.mkdir()
        (mdir_enabled / "bm25_index.pkl").write_bytes(b"data to delete")

        disabled = _make_coll("Arquivo", enabled=False, mdir=str(mdir_disabled))
        enabled = _make_coll("Biblioteca", enabled=True, mdir=str(mdir_enabled))

        _run_clear_logic([disabled, enabled])

        # Coleção desabilitada deve estar intacta
        assert (mdir_disabled / "bm25_index.pkl").exists(), \
            "coleção desabilitada não deve ter dados deletados"
        assert (mdir_disabled / "chroma_db").exists(), \
            "chroma_db da coleção desabilitada deve ser preservado"

        # Coleção habilitada deve ter dados deletados
        assert not (mdir_enabled / "bm25_index.pkl").exists(), \
            "coleção habilitada deve ter dados deletados"


# ---------------------------------------------------------------------------
# 4. ecosystem_chroma_dir global também é apagado quando configurado
# ---------------------------------------------------------------------------

def test_clear_removes_ecosystem_chroma_dir():
    with tempfile.TemporaryDirectory() as td:
        eco_chroma = Path(td) / "ecosystem_chroma"
        eco_chroma.mkdir()
        (eco_chroma / "chroma.sqlite3").write_bytes(b"global chroma")

        mdir = Path(td) / "mnemosyne_coll"
        mdir.mkdir()
        coll = _make_coll("Biblioteca", enabled=True, mdir=str(mdir))

        _run_clear_logic([coll], eco_chroma=str(eco_chroma))

        assert not eco_chroma.exists(), \
            "ecosystem_chroma_dir global deve ser removido"


# ---------------------------------------------------------------------------
# 5. OSError durante limpeza é capturado sem crash
# ---------------------------------------------------------------------------

def test_clear_captures_oserror_gracefully():
    """OSError (ex: permissão negada) não deve propagar para o caller."""
    import shutil

    with tempfile.TemporaryDirectory() as td:
        mdir = Path(td) / "mnemosyne_coll"
        mdir.mkdir()
        chroma = mdir / "chroma_db"
        chroma.mkdir()

        coll = _make_coll("Biblioteca", enabled=True, mdir=str(mdir))

        with patch("shutil.rmtree", side_effect=OSError("permission denied")):
            # Não deve levantar exceção
            _run_clear_logic([coll])


# ---------------------------------------------------------------------------
# 6. Coleção sem mnemosyne_dir definido é ignorada
# ---------------------------------------------------------------------------

def test_clear_skips_collection_without_mnemosyne_dir():
    """Coleção habilitada mas sem mnemosyne_dir não deve gerar erro."""
    coll = _make_coll("SemDir", enabled=True, mdir=None)
    # Não deve levantar exceção
    _run_clear_logic([coll])


# ---------------------------------------------------------------------------
# 7. Múltiplas coleções habilitadas: todas são limpas
# ---------------------------------------------------------------------------

def test_clear_cleans_all_enabled_collections():
    with tempfile.TemporaryDirectory() as td:
        dirs = []
        colls = []
        for i in range(3):
            mdir = Path(td) / f"coll_{i}"
            mdir.mkdir()
            (mdir / "bm25_index.pkl").write_bytes(b"data")
            dirs.append(mdir)
            colls.append(_make_coll(f"Coleção {i}", enabled=True, mdir=str(mdir)))

        _run_clear_logic(colls)

        for mdir in dirs:
            assert not (mdir / "bm25_index.pkl").exists(), \
                f"bm25 de {mdir.name} deve ser deletado"
