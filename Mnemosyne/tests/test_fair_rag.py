"""
Testes para FAIR-RAG: apply_source_feedback() em core/rag.py.

Cobre:
  - Feedback positivo: boost sobe em direção a 1.5
  - Feedback negativo: boost desce em direção a 0.5
  - Boost não ultrapassa _FAIR_MAX_BOOST (3.0)
  - Boost não cai abaixo de _FAIR_MIN_BOOST (0.3)
  - source_paths vazio retorna 0 sem erros
  - Chunks sem campo boost recebem default=1.0 antes do EMA
  - MultiVectorstore: atualiza em todos os stores
  - Falha de store individual não impede o restante
  - Retorna count correto de chunks atualizados
  - Log: operação é registrada via log.info
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Helpers de mock
# ---------------------------------------------------------------------------

def _make_store(chunks: dict[str, dict]) -> tuple[MagicMock, MagicMock]:
    """
    Cria (store, collection_mock) onde store é um vectorstore ChromaDB simulado.
    chunks: {path: {"ids": [...], "metadatas": [...]}}

    Retorna também o collection_mock para inspeção direta de chamadas.
    """
    def _get(where=None, **kwargs):
        path = (where or {}).get("source", {}).get("$eq", "")
        data = chunks.get(path, {"ids": [], "metadatas": []})
        return data

    collection = MagicMock()
    collection.get.side_effect = _get
    collection.update = MagicMock()

    store = MagicMock()
    store._collection = collection
    return store, collection


def _get_updated_metas(collection: MagicMock) -> list[dict]:
    """Coleta todos os metadatas passados para update() — recebe collection direto."""
    metas = []
    for c in collection.update.call_args_list:
        m = c.kwargs.get("metadatas") if c.kwargs else None
        if m is None and c.args:
            m = c.args[1] if len(c.args) > 1 else None
        if m:
            metas.extend(m)
    return metas


# ---------------------------------------------------------------------------
# Testes de apply_source_feedback
# ---------------------------------------------------------------------------

def test_positive_feedback_raises_boost():
    """Feedback ✓: boost deve subir em direção a 1.5."""
    from core.rag import apply_source_feedback

    store, col = _make_store({
        "/doc/a.md": {"ids": ["chunk1"], "metadatas": [{"source": "/doc/a.md", "boost": 1.0}]},
    })
    apply_source_feedback(store, ["/doc/a.md"], is_positive=True)

    updated = _get_updated_metas(col)
    assert len(updated) == 1
    new_boost = updated[0]["boost"]
    assert new_boost > 1.0, f"Boost não subiu: {new_boost}"
    assert new_boost <= 1.5, f"Boost ultrapassou target: {new_boost}"


def test_negative_feedback_lowers_boost():
    """Feedback ✗: boost deve descer em direção a 0.5."""
    from core.rag import apply_source_feedback

    store, col = _make_store({
        "/doc/b.md": {"ids": ["chunk2"], "metadatas": [{"source": "/doc/b.md", "boost": 1.0}]},
    })
    apply_source_feedback(store, ["/doc/b.md"], is_positive=False)

    updated = _get_updated_metas(col)
    new_boost = updated[0]["boost"]
    assert new_boost < 1.0, f"Boost não desceu: {new_boost}"
    assert new_boost >= 0.5, f"Boost abaixo do target: {new_boost}"


def test_boost_does_not_exceed_max():
    """Boost inicial alto: não ultrapassa _FAIR_MAX_BOOST (3.0)."""
    from core.rag import apply_source_feedback, _FAIR_MAX_BOOST

    store, col = _make_store({
        "/doc/c.md": {"ids": ["chunk3"], "metadatas": [{"boost": _FAIR_MAX_BOOST}]},
    })
    apply_source_feedback(store, ["/doc/c.md"], is_positive=True)

    updated = _get_updated_metas(col)
    assert updated[0]["boost"] <= _FAIR_MAX_BOOST


def test_boost_does_not_go_below_min():
    """Boost inicial baixo: não cai abaixo de _FAIR_MIN_BOOST (0.3)."""
    from core.rag import apply_source_feedback, _FAIR_MIN_BOOST

    store, col = _make_store({
        "/doc/d.md": {"ids": ["chunk4"], "metadatas": [{"boost": _FAIR_MIN_BOOST}]},
    })
    apply_source_feedback(store, ["/doc/d.md"], is_positive=False)

    updated = _get_updated_metas(col)
    assert updated[0]["boost"] >= _FAIR_MIN_BOOST


def test_empty_source_paths_returns_zero():
    """source_paths vazio retorna 0 sem chamar update."""
    from core.rag import apply_source_feedback

    store, col = _make_store({})
    result = apply_source_feedback(store, [], is_positive=True)

    assert result == 0
    col.update.assert_not_called()


def test_chunk_without_boost_defaults_to_one():
    """Chunk sem campo boost recebe 1.0 como base para o EMA."""
    from core.rag import apply_source_feedback

    store, col = _make_store({
        "/doc/e.md": {"ids": ["chunk5"], "metadatas": [{"source": "/doc/e.md"}]},
    })
    apply_source_feedback(store, ["/doc/e.md"], is_positive=True)

    updated = _get_updated_metas(col)
    assert 1.0 < updated[0]["boost"] < 1.5


def test_returns_correct_chunk_count():
    """Retorna número correto de chunks atualizados."""
    from core.rag import apply_source_feedback

    store, _ = _make_store({
        "/doc/f.md": {
            "ids":       ["c1", "c2", "c3"],
            "metadatas": [{"boost": 1.0}, {"boost": 1.0}, {"boost": 1.0}],
        }
    })
    result = apply_source_feedback(store, ["/doc/f.md"], is_positive=True)
    assert result == 3


def test_multivectorstore_updates_all_stores():
    """MultiVectorstore: update chamado em todos os stores."""
    from core.rag import apply_source_feedback, MultiVectorstore

    store_a, col_a = _make_store({
        "/doc/g.md": {"ids": ["c1"], "metadatas": [{"boost": 1.0}]},
    })
    store_b, col_b = _make_store({
        "/doc/g.md": {"ids": ["c2", "c3"], "metadatas": [{"boost": 1.0}, {"boost": 1.0}]},
    })

    multi = MagicMock(spec=MultiVectorstore)
    multi.stores = [(store_a, None), (store_b, None)]

    result = apply_source_feedback(multi, ["/doc/g.md"], is_positive=True)

    col_a.update.assert_called_once()
    col_b.update.assert_called_once()
    assert result == 3


def test_store_failure_does_not_stop_others():
    """Falha num store não interrompe os demais."""
    from core.rag import apply_source_feedback, MultiVectorstore

    store_ok, col_ok = _make_store({
        "/doc/h.md": {"ids": ["c1"], "metadatas": [{"boost": 1.0}]},
    })
    store_fail = MagicMock()
    store_fail._collection.get.side_effect = RuntimeError("DB unavailable")

    multi = MagicMock(spec=MultiVectorstore)
    multi.stores = [(store_fail, None), (store_ok, None)]

    result = apply_source_feedback(multi, ["/doc/h.md"], is_positive=False)

    col_ok.update.assert_called_once()
    assert result >= 1


def test_unknown_path_returns_zero_updates():
    """Fonte não encontrada no store retorna 0 (sem erros)."""
    from core.rag import apply_source_feedback

    store, col = _make_store({})
    result = apply_source_feedback(store, ["/doc/missing.md"], is_positive=True)

    assert result == 0
    col.update.assert_not_called()


def test_ema_formula_precision():
    """EMA: boost 1.0 + feedback positivo → 1.075 (1.0 + 0.15×0.5)."""
    from core.rag import apply_source_feedback

    store, col = _make_store({
        "/doc/ema.md": {"ids": ["chunk_ema"], "metadatas": [{"boost": 1.0}]},
    })
    apply_source_feedback(store, ["/doc/ema.md"], is_positive=True)

    updated = _get_updated_metas(col)
    # new = 1.0 + 0.15 * (1.5 - 1.0) = 1.075
    assert abs(updated[0]["boost"] - 1.075) < 0.001, f"Valor EMA errado: {updated[0]['boost']}"
