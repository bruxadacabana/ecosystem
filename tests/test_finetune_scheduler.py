"""
Testes para logos/finetune_scheduler.py.

Cobre:
  - FinetuneState: serialização/desserialização, campos padrão
  - read_state() / _write_state(): persistência atômica
  - _acquire_lock() / _release_lock(): exclusão mútua
  - is_running(): lê lock file
  - should_auto_trigger(): detecção de crescimento >20%
  - trigger_manual(): dispara thread, retorna False se já em andamento
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _set_eco_env(monkeypatch, tmp_path):
    """Garante que ecosystem_path() resolve para tmp_path em qualquer OS."""
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


from logos.finetune_scheduler import (
    FinetuneState,
    _acquire_lock,
    _count_chroma_chunks,
    _lock_path,
    _release_lock,
    _state_path,
    _update_state,
    _write_state,
    is_running,
    read_state,
    should_auto_trigger,
    trigger_manual,
)


# ─── FinetuneState ────────────────────────────────────────────────────────────

def test_finetune_state_defaults():
    s = FinetuneState()
    assert s.running is False
    assert s.corpus_chunks_at_last_train == 0
    assert s.current_step == ""


def test_finetune_state_roundtrip():
    s = FinetuneState(
        corpus_chunks_at_last_train=500,
        current_model="mnemosyne-ft-v3",
        running=True,
    )
    d = s.to_dict()
    s2 = FinetuneState.from_dict(d)
    assert s2.corpus_chunks_at_last_train == 500
    assert s2.current_model == "mnemosyne-ft-v3"
    assert s2.running is True


def test_finetune_state_ignores_unknown_keys():
    s = FinetuneState.from_dict({"corpus_chunks_at_last_train": 10, "unknown_field": "x"})
    assert s.corpus_chunks_at_last_train == 10


# ─── read_state / _write_state ────────────────────────────────────────────────

def test_read_state_returns_default_if_missing(tmp_path):
    state = read_state(str(tmp_path))
    assert state.corpus_chunks_at_last_train == 0


def test_read_state_returns_default_if_corrupted(tmp_path):
    (tmp_path / "logos").mkdir()
    (tmp_path / "logos" / "finetune_state.json").write_text("{bad json")
    state = read_state(str(tmp_path))
    assert isinstance(state, FinetuneState)


def test_write_and_read_roundtrip(tmp_path):
    original = FinetuneState(corpus_chunks_at_last_train=250, current_model="mnemosyne-ft-v1")
    _write_state(original, str(tmp_path))
    recovered = read_state(str(tmp_path))
    assert recovered.corpus_chunks_at_last_train == 250
    assert recovered.current_model == "mnemosyne-ft-v1"


def test_update_state_merges(tmp_path):
    _write_state(FinetuneState(corpus_chunks_at_last_train=100), str(tmp_path))
    _update_state(str(tmp_path), current_model="mnemosyne-ft-v2")
    s = read_state(str(tmp_path))
    assert s.corpus_chunks_at_last_train == 100  # preservado
    assert s.current_model == "mnemosyne-ft-v2"  # atualizado


# ─── _acquire_lock / _release_lock ────────────────────────────────────────────

def test_acquire_lock_creates_file(tmp_path):
    assert _acquire_lock(str(tmp_path)) is True
    assert _lock_path(str(tmp_path)).exists()


def test_acquire_lock_fails_if_already_locked(tmp_path):
    _acquire_lock(str(tmp_path))
    assert _acquire_lock(str(tmp_path)) is False


def test_release_lock_removes_file(tmp_path):
    _acquire_lock(str(tmp_path))
    _release_lock(str(tmp_path))
    assert not _lock_path(str(tmp_path)).exists()


def test_release_lock_noop_if_not_locked(tmp_path):
    _release_lock(str(tmp_path))  # não deve levantar


# ─── is_running ───────────────────────────────────────────────────────────────

def test_is_running_false_if_no_lock(tmp_path):
    assert is_running(str(tmp_path)) is False


def test_is_running_true_if_locked(tmp_path):
    _acquire_lock(str(tmp_path))
    assert is_running(str(tmp_path)) is True
    _release_lock(str(tmp_path))


# ─── should_auto_trigger ──────────────────────────────────────────────────────

def test_should_auto_trigger_false_if_running(tmp_path):
    _acquire_lock(str(tmp_path))
    with patch("logos.finetune_scheduler._get_chroma_dir", return_value=""):
        assert should_auto_trigger(str(tmp_path)) is False
    _release_lock(str(tmp_path))


def test_should_auto_trigger_true_if_never_trained_with_data(tmp_path):
    """Nunca treinou + chunks existem → trigger."""
    with patch("logos.finetune_scheduler._get_chroma_dir", return_value="/fake/chroma"), \
         patch("logos.finetune_scheduler._count_chroma_chunks", return_value=50):
        result = should_auto_trigger(str(tmp_path))
    assert result is True


def test_should_auto_trigger_false_if_never_trained_no_data(tmp_path):
    """Nunca treinou + sem chunks → não trigger."""
    with patch("logos.finetune_scheduler._get_chroma_dir", return_value="/fake/chroma"), \
         patch("logos.finetune_scheduler._count_chroma_chunks", return_value=0):
        result = should_auto_trigger(str(tmp_path))
    assert result is False


def test_should_auto_trigger_true_if_corpus_grew_20_pct(tmp_path):
    """Corpus cresceu >20% desde último treino → trigger."""
    _write_state(FinetuneState(corpus_chunks_at_last_train=100), str(tmp_path))
    with patch("logos.finetune_scheduler._get_chroma_dir", return_value="/fake"), \
         patch("logos.finetune_scheduler._count_chroma_chunks", return_value=125):  # +25%
        result = should_auto_trigger(str(tmp_path))
    assert result is True


def test_should_auto_trigger_false_if_corpus_grew_less_than_20_pct(tmp_path):
    """Corpus cresceu <20% → não trigger."""
    _write_state(FinetuneState(corpus_chunks_at_last_train=100), str(tmp_path))
    with patch("logos.finetune_scheduler._get_chroma_dir", return_value="/fake"), \
         patch("logos.finetune_scheduler._count_chroma_chunks", return_value=115):  # +15%
        result = should_auto_trigger(str(tmp_path))
    assert result is False


# ─── _count_chroma_chunks ─────────────────────────────────────────────────────

def test_count_chroma_chunks_returns_0_if_no_chromadb(tmp_path, monkeypatch):
    """Retorna 0 graciosamente se chromadb não instalado."""
    monkeypatch.setitem(sys.modules, "chromadb", None)
    assert _count_chroma_chunks(str(tmp_path / "nonexistent")) == 0


def test_count_chroma_chunks_returns_0_if_dir_missing(tmp_path):
    assert _count_chroma_chunks(str(tmp_path / "nonexistent")) == 0


def test_count_chroma_chunks_sums_collections(tmp_path, monkeypatch):
    """Soma chunks de todas as coleções."""
    fake_chromadb = types.ModuleType("chromadb")

    class FakeColl:
        def __init__(self, n):
            self.name = f"coll{n}"
            self._n = n
        def count(self):
            return self._n

    class FakeClient:
        def __init__(self, path):
            pass
        def list_collections(self):
            return [FakeColl(30), FakeColl(70)]
        def get_collection(self, name):
            return next(c for c in [FakeColl(30), FakeColl(70)] if c.name == name)

    fake_chromadb.PersistentClient = FakeClient
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)

    (tmp_path / "chroma").mkdir()
    total = _count_chroma_chunks(str(tmp_path / "chroma"))
    assert total == 100


# ─── trigger_manual ───────────────────────────────────────────────────────────

def test_trigger_manual_raises_if_no_sync_root(monkeypatch, tmp_path):
    _set_eco_env(monkeypatch, tmp_path)
    # ecosystem.json sem sync_root para garantir o raise
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({}))
    with pytest.raises(RuntimeError, match="sync_root"):
        trigger_manual("")


def test_trigger_manual_returns_false_if_already_running(tmp_path):
    _acquire_lock(str(tmp_path))
    result = trigger_manual(str(tmp_path))
    assert result is False
    _release_lock(str(tmp_path))


def test_trigger_manual_starts_thread(tmp_path):
    """trigger_manual() deve retornar True e iniciar uma thread."""
    cycle_started = threading.Event()

    def fake_run_cycle(sync_root):
        cycle_started.set()
        _release_lock(sync_root)

    with patch("logos.finetune_scheduler._run_cycle", side_effect=fake_run_cycle):
        result = trigger_manual(str(tmp_path))

    assert result is True
    # Thread deve iniciar em < 1 segundo
    assert cycle_started.wait(timeout=1.0), "Thread não iniciada"


def test_trigger_manual_prevents_double_trigger(tmp_path):
    """Duas chamadas simultâneas: apenas uma deve iniciar."""
    started_count = [0]
    barrier = threading.Barrier(2)

    def fake_run_cycle(sync_root):
        started_count[0] += 1
        time.sleep(0.05)
        _release_lock(sync_root)

    with patch("logos.finetune_scheduler._run_cycle", side_effect=fake_run_cycle):
        r1 = trigger_manual(str(tmp_path))
        r2 = trigger_manual(str(tmp_path))

    assert r1 is True
    assert r2 is False
    # Aguardar thread terminar
    time.sleep(0.2)
