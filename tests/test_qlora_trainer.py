"""
Testes para logos/qlora_trainer.py.

Cobre:
  - _find_latest_training_file(): retorna o JSONL mais recente, None se vazio
  - _load_dataset(): lê JSONL, ignora linhas inválidas, levanta se vazio/ausente
  - check_prerequisites(): detecta pacotes instalados vs. ausentes
  - VramPauseCallback (via _make_vram_pause_callback()):
      não pausa quando VRAM ≤ threshold
      pausa e incrementa counter quando VRAM > threshold
  - TrainerConfig.resolve(): levanta RuntimeError se sync_root vazio, preenche caminhos
  - TrainerResult.__str__(): não levanta exceção
  - train(): smoke test com stack de ML completamente mockado
"""
from __future__ import annotations

import json
import sys
import types
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _set_eco_env(monkeypatch, tmp_path):
    """Garante que ecosystem_path() resolve para tmp_path em qualquer OS."""
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


from logos.qlora_trainer import (
    TrainerConfig,
    TrainerResult,
    _find_latest_training_file,
    check_prerequisites,
    _make_vram_pause_callback,
)


# ─── _find_latest_training_file ───────────────────────────────────────────────

def test_find_latest_returns_none_if_dir_missing(tmp_path):
    result = _find_latest_training_file(str(tmp_path / "nonexistent"))
    assert result is None


def test_find_latest_returns_none_if_dir_empty(tmp_path):
    result = _find_latest_training_file(str(tmp_path))
    assert result is None


def test_find_latest_returns_most_recent(tmp_path):
    (tmp_path / "2026-01-01.jsonl").write_text("{}")
    (tmp_path / "2026-05-23.jsonl").write_text("{}")
    (tmp_path / "2026-03-15.jsonl").write_text("{}")
    result = _find_latest_training_file(str(tmp_path))
    assert result is not None
    assert result.name == "2026-05-23.jsonl"


def test_find_latest_ignores_non_jsonl(tmp_path):
    (tmp_path / "readme.txt").write_text("ignore me")
    result = _find_latest_training_file(str(tmp_path))
    assert result is None


# ─── _load_dataset ────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _make_fake_datasets() -> types.ModuleType:
    """Módulo datasets falso com Dataset.from_list()."""
    fake = types.ModuleType("datasets")

    class FakeDataset:
        def __init__(self, records):
            self._records = records

        def __len__(self):
            return len(self._records)

        @classmethod
        def from_list(cls, lst):
            return cls(lst)

    fake.Dataset = FakeDataset
    return fake


def test_load_dataset_reads_jsonl(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "datasets", _make_fake_datasets())
    f = tmp_path / "2026-05-23.jsonl"
    _write_jsonl(f, [{"messages": [{"role": "user", "content": "Q?"}]}])

    from logos.qlora_trainer import _load_dataset
    ds = _load_dataset(str(tmp_path))
    assert len(ds) == 1


def test_load_dataset_skips_invalid_lines(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "datasets", _make_fake_datasets())
    f = tmp_path / "2026-05-23.jsonl"
    f.write_text('{"messages": []}\n{bad json}\n{"messages": [{"role": "user"}]}\n')

    from logos.qlora_trainer import _load_dataset
    ds = _load_dataset(str(tmp_path))
    assert len(ds) == 2


def test_load_dataset_raises_if_no_file(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "datasets", _make_fake_datasets())
    from logos.qlora_trainer import _load_dataset
    with pytest.raises(FileNotFoundError):
        _load_dataset(str(tmp_path))


def test_load_dataset_raises_if_file_empty(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "datasets", _make_fake_datasets())
    (tmp_path / "2026-05-23.jsonl").write_text("\n\n")
    from logos.qlora_trainer import _load_dataset
    with pytest.raises(ValueError):
        _load_dataset(str(tmp_path))


# ─── check_prerequisites ──────────────────────────────────────────────────────

def test_check_prerequisites_returns_dict():
    result = check_prerequisites()
    assert isinstance(result, dict)
    for pkg in ("unsloth", "bitsandbytes", "transformers", "trl", "peft", "datasets"):
        assert pkg in result
        assert isinstance(result[pkg], bool)


def test_check_prerequisites_detects_missing(monkeypatch):
    """Simula ausência de todos os pacotes de ML."""
    for pkg in ("unsloth", "bitsandbytes", "transformers", "trl", "peft", "datasets"):
        monkeypatch.setitem(sys.modules, pkg, None)  # None → ImportError em __import__
    result = check_prerequisites()
    for pkg in ("unsloth", "bitsandbytes", "transformers", "trl", "peft", "datasets"):
        assert result[pkg] is False


# ─── VramPauseCallback ────────────────────────────────────────────────────────

def _make_fake_transformers() -> types.ModuleType:
    fake = types.ModuleType("transformers")

    class TrainerCallback:
        def on_step_begin(self, args, state, control, **kwargs):
            pass

    fake.TrainerCallback = TrainerCallback
    return fake


def _make_fake_state(step: int = 0) -> object:
    state = MagicMock()
    state.global_step = step
    return state


def test_vram_callback_no_pause_below_threshold(monkeypatch):
    """Não pausa quando VRAM está abaixo do threshold."""
    monkeypatch.setitem(sys.modules, "transformers", _make_fake_transformers())

    from vram_monitor import VramInfo

    pause_counter = [0]
    cb = _make_vram_pause_callback(threshold_pct=85.0, pause_counter=pause_counter)

    low_vram = VramInfo(used_mb=4000, total_mb=8000, used_pct=50.0, source="amd_sysfs")
    with patch("vram_monitor.get_vram_info", return_value=low_vram):
        cb.on_step_begin(args=None, state=_make_fake_state(), control=None)

    assert pause_counter[0] == 0


def test_vram_callback_pauses_above_threshold(monkeypatch):
    """Incrementa pause_counter e aguarda quando VRAM > threshold."""
    monkeypatch.setitem(sys.modules, "transformers", _make_fake_transformers())

    from vram_monitor import VramInfo

    pause_counter = [0]
    cb = _make_vram_pause_callback(threshold_pct=85.0, pause_counter=pause_counter)

    high_vram = VramInfo(used_mb=7200, total_mb=8000, used_pct=90.0, source="amd_sysfs")
    low_vram  = VramInfo(used_mb=4000, total_mb=8000, used_pct=50.0, source="amd_sysfs")

    # Retorna VRAM alta uma vez, depois baixa → callback deve parar de esperar
    call_results = iter([high_vram, high_vram, low_vram])

    with patch("vram_monitor.get_vram_info", side_effect=call_results), \
         patch("time.sleep"):  # não dormir de verdade no teste
        cb.on_step_begin(args=None, state=_make_fake_state(step=5), control=None)

    assert pause_counter[0] == 1


def test_vram_callback_timeout_continues(monkeypatch):
    """Após timeout, continua mesmo com VRAM alta (não trava infinitamente)."""
    monkeypatch.setitem(sys.modules, "transformers", _make_fake_transformers())

    from vram_monitor import VramInfo
    import logos.qlora_trainer as qt

    # Zera o timeout máximo antes de criar o callback (classe captura globals do módulo)
    monkeypatch.setattr(qt, "_PAUSE_MAX_WAIT", 0.0)
    monkeypatch.setattr(qt, "_VRAM_CHECK_INTERVAL", 0.0)

    pause_counter = [0]
    cb = _make_vram_pause_callback(threshold_pct=85.0, pause_counter=pause_counter)

    high_vram = VramInfo(used_mb=7200, total_mb=8000, used_pct=90.0, source="amd_sysfs")

    with patch("vram_monitor.get_vram_info", return_value=high_vram):
        cb.on_step_begin(args=None, state=_make_fake_state(step=3), control=None)

    # Não deve levantar exceção; contador incrementado
    assert pause_counter[0] == 1


# ─── TrainerConfig.resolve ────────────────────────────────────────────────────

def test_resolve_raises_if_sync_root_empty(monkeypatch, tmp_path):
    _set_eco_env(monkeypatch, tmp_path)
    # ecosystem.json existe mas sem sync_root para garantir o raise
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({}))
    cfg = TrainerConfig()
    with pytest.raises(RuntimeError, match="sync_root"):
        cfg.resolve()


def test_resolve_fills_checkpoint_dir(monkeypatch, tmp_path):
    fake_sync = str(tmp_path / "sync")
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": fake_sync}))
    _set_eco_env(monkeypatch, tmp_path)

    cfg = TrainerConfig().resolve()
    assert "logos" in cfg.checkpoint_dir
    assert "checkpoints" in cfg.checkpoint_dir


def test_resolve_respects_explicit_paths(monkeypatch, tmp_path):
    fake_sync = str(tmp_path / "sync")
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": fake_sync}))
    _set_eco_env(monkeypatch, tmp_path)

    explicit_ckpt = str(tmp_path / "my_ckpts")
    cfg = TrainerConfig(checkpoint_dir=explicit_ckpt).resolve()
    assert cfg.checkpoint_dir == explicit_ckpt


# ─── TrainerResult.__str__ ────────────────────────────────────────────────────

def test_trainer_result_str():
    r = TrainerResult(steps_completed=100, pauses=2, elapsed_seconds=300.0, checkpoint_dir="/tmp/ckpt")
    s = str(r)
    assert "steps=100" in s
    assert "pauses=2" in s
    assert "300.0" in s


# ─── train() — smoke test com ML stack mockado ─────────────────────────────────

def _build_ml_mocks(tmp_path: Path, fake_datasets_module: types.ModuleType) -> dict:
    """Constrói módulos falsos para todo o stack de ML."""
    # unsloth
    fake_unsloth = types.ModuleType("unsloth")
    fake_model = MagicMock()
    fake_tokenizer = MagicMock()
    fake_lora_model = MagicMock()
    fake_unsloth.FastLanguageModel = MagicMock()
    fake_unsloth.FastLanguageModel.from_pretrained = MagicMock(
        return_value=(fake_model, fake_tokenizer)
    )
    fake_unsloth.FastLanguageModel.get_peft_model = MagicMock(return_value=fake_lora_model)

    # transformers
    fake_transformers = _make_fake_transformers()

    # trl
    fake_trl = types.ModuleType("trl")
    fake_train_output = MagicMock()
    fake_train_output.global_step = 50
    fake_trainer_instance = MagicMock()
    fake_trainer_instance.train.return_value = fake_train_output
    fake_trl.SFTTrainer = MagicMock(return_value=fake_trainer_instance)

    fake_sft_config = MagicMock()
    fake_trl.SFTConfig = MagicMock(return_value=fake_sft_config)

    # peft / bitsandbytes
    fake_peft = types.ModuleType("peft")
    fake_bitsandbytes = types.ModuleType("bitsandbytes")

    return {
        "unsloth": fake_unsloth,
        "transformers": fake_transformers,
        "trl": fake_trl,
        "peft": fake_peft,
        "bitsandbytes": fake_bitsandbytes,
        "datasets": fake_datasets_module,
    }


def test_train_smoke(tmp_path, monkeypatch):
    """Smoke test: train() com stack de ML mockado termina sem erro."""
    # Preparar dados de treino
    data_dir = tmp_path / "training_data"
    data_dir.mkdir()
    _write_jsonl(
        data_dir / "2026-05-23.jsonl",
        [{"messages": [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"}]}] * 5,
    )

    ckpt_dir = tmp_path / "checkpoints"

    fake_ds = _make_fake_datasets()
    mocks = _build_ml_mocks(tmp_path, fake_ds)
    for name, mod in mocks.items():
        monkeypatch.setitem(sys.modules, name, mod)

    from logos.qlora_trainer import train, TrainerConfig

    cfg = TrainerConfig(
        training_data_dir=str(data_dir),
        checkpoint_dir=str(ckpt_dir),
    )

    from vram_monitor import VramInfo
    low_vram = VramInfo(used_mb=2000, total_mb=8000, used_pct=25.0, source="amd_sysfs")

    with patch("vram_monitor.get_vram_info", return_value=low_vram):
        result = train(cfg)

    assert result.steps_completed == 50
    assert result.pauses == 0
    assert "smollm2-qlora" in result.checkpoint_dir
    assert result.elapsed_seconds >= 0.0


def test_train_raises_if_deps_missing(tmp_path, monkeypatch):
    """RuntimeError claro se unsloth não estiver instalado."""
    for pkg in ("unsloth", "bitsandbytes", "trl", "peft"):
        monkeypatch.setitem(sys.modules, pkg, None)

    from logos.qlora_trainer import train, TrainerConfig
    cfg = TrainerConfig(
        training_data_dir=str(tmp_path),
        checkpoint_dir=str(tmp_path / "ckpt"),
    )
    with pytest.raises(RuntimeError, match="Dependências de ML"):
        train(cfg)
