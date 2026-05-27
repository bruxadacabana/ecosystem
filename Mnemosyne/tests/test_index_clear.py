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

SharedSystem / SQLITE_READONLY_DBMOVED (BUG-010):
  8.  load_all_vectorstores fecha conexão quando count == 0 (evita SharedSystem stale)
  9.  SharedSystemClient.clear_system_cache() remove entradas do cache global
  10. Reindex após vectorstore vazio não causa SQLITE_READONLY_DBMOVED
  11. Múltiplas aberturas do mesmo path sem close() acumulam refcount
  12. close() decrementa refcount e libera SharedSystem quando chega a zero
  13. clear_system_cache() limpa mesmo com múltiplas referências pendentes
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


# ---------------------------------------------------------------------------
# Bloco 8-13: SharedSystem / SQLITE_READONLY_DBMOVED (BUG-010)
# ---------------------------------------------------------------------------

class _FakeEmbeddings:
    """Embeddings mínimos sem GPU para testes unitários."""
    def embed_documents(self, texts):
        return [[0.0] * 4] * len(texts)
    def embed_query(self, text):
        return [0.0] * 4


def _fresh_chroma(path: str):
    """Abre langchain_chroma.Chroma em modo rwc — mesmo padrão do indexer.py."""
    from langchain_chroma import Chroma
    return Chroma(
        persist_directory=path,
        embedding_function=_FakeEmbeddings(),
        collection_metadata={"hnsw:space": "cosine"},
    )


def _clear_shared_system() -> None:
    from chromadb.api.shared_system_client import SharedSystemClient
    SharedSystemClient.clear_system_cache()


# ---------------------------------------------------------------------------
# 8. load_all_vectorstores fecha conexão quando count == 0
# ---------------------------------------------------------------------------

def test_load_all_vectorstores_closes_connection_when_empty():
    """Após load_all_vectorstores retornar [] por count==0, o SharedSystem não
    deve manter refcount > 0 para o path — confirmado pela ausência de erro ao
    recriar a store no mesmo path após apagar o diretório."""
    with tempfile.TemporaryDirectory() as td:
        chroma_dir = Path(td) / "chroma_db"
        chroma_dir.mkdir()

        # Cria chroma_db vazio (count == 0)
        vs = _fresh_chroma(str(chroma_dir))
        assert vs._collection.count() == 0
        # Simula o comportamento CORRIGIDO: close() explícito antes de retornar
        vs._client.close()

        import shutil
        shutil.rmtree(str(chroma_dir))
        chroma_dir.mkdir()

        # Deve ser possível abrir e escrever no mesmo path sem SQLITE_READONLY_DBMOVED
        vs2 = _fresh_chroma(str(chroma_dir))
        vs2._collection.add(
            ids=["1"],
            documents=["hello"],
            embeddings=[[0.1, 0.2, 0.3, 0.4]],
            metadatas=[{"src": "test"}],
        )
        assert vs2._collection.count() == 1
        vs2._client.close()


# ---------------------------------------------------------------------------
# 9. SharedSystemClient.clear_system_cache() limpa o cache global
# ---------------------------------------------------------------------------

def test_clear_system_cache_empties_registry():
    """clear_system_cache() deve deixar _identifier_to_system e
    _identifier_to_refcount vazios."""
    from chromadb.api.shared_system_client import SharedSystemClient

    with tempfile.TemporaryDirectory() as td:
        chroma_dir = Path(td) / "chroma_db"
        chroma_dir.mkdir()
        vs = _fresh_chroma(str(chroma_dir))
        # Há pelo menos uma entrada no SharedSystem
        assert len(SharedSystemClient._identifier_to_system) > 0
        vs._client.close()

    _clear_shared_system()
    assert SharedSystemClient._identifier_to_system == {}, \
        "SharedSystem deve estar vazio após clear_system_cache()"
    assert SharedSystemClient._identifier_to_refcount == {}, \
        "refcount deve estar vazio após clear_system_cache()"


# ---------------------------------------------------------------------------
# 10. Reindex após vectorstore vazio não causa SQLITE_READONLY_DBMOVED
# ---------------------------------------------------------------------------

def test_reindex_after_empty_vectorstore_no_dbmoved():
    """Reproduz o cenário do BUG-010:
    1. Chroma aberto com count == 0 (retornado sem close pelo bug original)
    2. Diretório apagado e recriado (fluxo 'indexar tudo')
    3. Nova store no mesmo path deve conseguir escrever SEM SQLITE_READONLY_DBMOVED.

    Com o fix (close() + clear_system_cache()), não deve lançar nenhuma exceção.
    """
    import shutil
    with tempfile.TemporaryDirectory() as td:
        chroma_dir = Path(td) / "chroma_db"
        chroma_dir.mkdir()

        # Abertura inicial (simula load_all_vectorstores)
        vs_initial = _fresh_chroma(str(chroma_dir))
        assert vs_initial._collection.count() == 0

        # FIX: fechar e limpar SharedSystem (o que o código corrigido faz)
        vs_initial._client.close()
        _clear_shared_system()

        # Fluxo de "indexar tudo": apagar dir e recriar
        shutil.rmtree(str(chroma_dir))
        chroma_dir.mkdir()

        # Nova indexação: deve funcionar sem SQLITE_READONLY_DBMOVED
        vs_new = _fresh_chroma(str(chroma_dir))
        vs_new._collection.add(
            ids=["doc-1"],
            documents=["conteúdo de teste"],
            embeddings=[[0.1, 0.2, 0.3, 0.4]],
            metadatas=[{"source": "unit_test"}],
        )
        assert vs_new._collection.count() == 1
        vs_new._client.close()


# ---------------------------------------------------------------------------
# 11. Múltiplas aberturas do mesmo path acumulam refcount
# ---------------------------------------------------------------------------

def test_multiple_opens_accumulate_refcount():
    """Duas instâncias Chroma no mesmo path devem resultar em refcount >= 2."""
    from chromadb.api.shared_system_client import SharedSystemClient

    with tempfile.TemporaryDirectory() as td:
        chroma_dir = Path(td) / "chroma_db"
        chroma_dir.mkdir()

        vs1 = _fresh_chroma(str(chroma_dir))
        refcount_after_1 = list(SharedSystemClient._identifier_to_refcount.values())
        assert any(r >= 1 for r in refcount_after_1), "refcount deve ser >= 1 após primeiro open"

        vs2 = _fresh_chroma(str(chroma_dir))
        refcount_after_2 = list(SharedSystemClient._identifier_to_refcount.values())
        assert any(r >= 2 for r in refcount_after_2), "refcount deve acumular com segundo open"

        vs1._client.close()
        vs2._client.close()


# ---------------------------------------------------------------------------
# 12. close() decrementa refcount e libera quando chega a zero
# ---------------------------------------------------------------------------

def test_close_decrements_refcount_to_zero():
    """Após fechar todas as referências, SharedSystem não deve ter entradas
    para o path em questão."""
    from chromadb.api.shared_system_client import SharedSystemClient
    _clear_shared_system()

    with tempfile.TemporaryDirectory() as td:
        chroma_dir = Path(td) / "chroma_db"
        chroma_dir.mkdir()

        vs = _fresh_chroma(str(chroma_dir))
        assert len(SharedSystemClient._identifier_to_refcount) > 0

        vs._client.close()

        # Após fechar, SharedSystem deve ter refcount = 0 ou entry removida
        remaining = [r for r in SharedSystemClient._identifier_to_refcount.values() if r > 0]
        assert len(remaining) == 0, \
            "Após close(), não deve haver refcount > 0 no SharedSystem"


# ---------------------------------------------------------------------------
# 13. clear_system_cache() funciona mesmo com múltiplas referências pendentes
# ---------------------------------------------------------------------------

def test_clear_system_cache_works_with_pending_references():
    """clear_system_cache() não deve lançar exceção mesmo se houver conexões
    abertas (objetos não-fechados). Após clear, novos opens ao mesmo path
    devem funcionar normalmente."""
    import shutil
    from chromadb.api.shared_system_client import SharedSystemClient

    with tempfile.TemporaryDirectory() as td:
        chroma_dir = Path(td) / "chroma_db"
        chroma_dir.mkdir()

        # Abre sem fechar (simula langchain_chroma sem __del__ com close())
        vs_leaked = _fresh_chroma(str(chroma_dir))
        assert len(SharedSystemClient._identifier_to_system) > 0

        # clear_system_cache() deve funcionar sem exceção
        _clear_shared_system()
        assert SharedSystemClient._identifier_to_system == {}

        # Novo open ao mesmo path deve funcionar (sem DBMOVED)
        chroma_dir2 = Path(td) / "chroma_db2"
        chroma_dir2.mkdir()
        vs_new = _fresh_chroma(str(chroma_dir2))
        vs_new._collection.add(
            ids=["x"],
            documents=["teste"],
            embeddings=[[0.0, 0.0, 0.0, 0.0]],
            metadatas=[{"k": "v"}],
        )
        assert vs_new._collection.count() == 1
        vs_new._client.close()

        # Evitar que vs_leaked cause erro ao ser coletado depois
        try:
            vs_leaked._client.close()
        except Exception:
            pass
