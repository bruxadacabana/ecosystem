"""
Testes para logos/gguf_converter.py.

Cobre:
  - _find_binary(): localiza binário no PATH ou dir explícito, levanta se ausente
  - _find_convert_script(): localiza script no dir explícito, levanta se ausente
  - _next_version(): lê registry.json, retorna 1 se nenhum existir
  - _model_version_name(): gera nome correto
  - _update_ecosystem_json(): escreve seção logos e tenta LOGOS (graceful offline)
  - ConverterConfig.resolve(): levanta RuntimeError sem sync_root, preenche campos
  - ConverterResult.__str__(): não levanta exceção
  - convert_and_register(): smoke test com subprocessos mockados
"""
from __future__ import annotations

import json
import os
import sys
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

from logos.gguf_converter import (
    ConverterConfig,
    ConverterResult,
    _find_binary,
    _model_version_name,
    _next_version,
    _update_ecosystem_json,
    convert_and_register,
)


# ─── _find_binary ─────────────────────────────────────────────────────────────

def test_find_binary_from_explicit_dir(tmp_path):
    """Localiza binário dentro do llama_cpp_dir fornecido."""
    binary = tmp_path / "llama-quantize"
    binary.touch()
    binary.chmod(0o755)
    result = _find_binary("llama-quantize", str(tmp_path))
    assert result == str(binary)


def test_find_binary_raises_if_not_found(tmp_path):
    """Levanta RuntimeError se binário não existe em nenhum lugar."""
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="llama-quantize"):
            _find_binary("llama-quantize", llama_cpp_dir="")


def test_find_binary_uses_path_if_available():
    """Usa shutil.which quando binário está no PATH."""
    with patch("shutil.which", return_value="/usr/bin/llama-quantize"):
        result = _find_binary("llama-quantize")
    assert result == "/usr/bin/llama-quantize"


# ─── _next_version ────────────────────────────────────────────────────────────

def test_next_version_returns_1_if_no_registry(tmp_path):
    """Retorna 1 se registry.json não existir."""
    assert _next_version(str(tmp_path)) == 1


def test_next_version_returns_1_if_registry_empty(tmp_path):
    """Retorna 1 se registry.json está vazio."""
    (tmp_path / "registry.json").write_text("[]")
    assert _next_version(str(tmp_path)) == 1


def test_next_version_parses_existing_versions(tmp_path):
    """Retorna max(versão) + 1 para versões existentes no registry."""
    entries = [
        {"name": "mnemosyne-ft-v1", "filename": "v1.gguf"},
        {"name": "mnemosyne-ft-v3", "filename": "v3.gguf"},
        {"name": "mnemosyne-ft-v2", "filename": "v2.gguf"},
        {"name": "llama3", "filename": "llama3.gguf"},
    ]
    (tmp_path / "registry.json").write_text(json.dumps(entries))
    assert _next_version(str(tmp_path)) == 4


def test_next_version_handles_single_version(tmp_path):
    """Retorna version+1 com um único modelo registrado."""
    entries = [{"name": "mnemosyne-ft-v5", "filename": "v5.gguf"}]
    (tmp_path / "registry.json").write_text(json.dumps(entries))
    assert _next_version(str(tmp_path)) == 6


def test_next_version_returns_1_on_malformed_registry(tmp_path):
    """Retorna 1 se registry.json contiver JSON inválido."""
    (tmp_path / "registry.json").write_text("not json")
    assert _next_version(str(tmp_path)) == 1


# ─── _model_version_name ──────────────────────────────────────────────────────

def test_model_version_name():
    assert _model_version_name(1) == "mnemosyne-ft-v1"
    assert _model_version_name(42) == "mnemosyne-ft-v42"


# ─── _update_ecosystem_json ───────────────────────────────────────────────────

def test_update_ecosystem_json_writes_section(tmp_path, monkeypatch):
    _set_eco_env(monkeypatch, tmp_path)
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": str(tmp_path)}))

    with patch("ecosystem_client._logos_post", return_value=None):
        _update_ecosystem_json("mnemosyne-ft-v2", "mnemosyne-ft-prev")

    data = json.loads(eco_path.read_text())
    assert data["logos"]["finetuned_rag_model"] == "mnemosyne-ft-v2"
    assert data["logos"]["finetuned_rag_model_prev"] == "mnemosyne-ft-prev"


def test_update_ecosystem_json_graceful_if_logos_offline(tmp_path, monkeypatch):
    """Não levanta exceção se LOGOS offline (retorna None)."""
    _set_eco_env(monkeypatch, tmp_path)
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": str(tmp_path)}))

    with patch("ecosystem_client._logos_post", return_value=None):
        _update_ecosystem_json("mnemosyne-ft-v1", "")  # não deve levantar


# ─── ConverterConfig.resolve ──────────────────────────────────────────────────

def test_resolve_raises_if_sync_root_missing(tmp_path, monkeypatch):
    _set_eco_env(monkeypatch, tmp_path)
    # ecosystem.json existe mas sem sync_root
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({}))  # sync_root ausente
    cfg = ConverterConfig()
    with pytest.raises(RuntimeError, match="sync_root"):
        cfg.resolve()


def test_resolve_fills_output_dir(tmp_path, monkeypatch):
    _set_eco_env(monkeypatch, tmp_path)
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": str(tmp_path / "sync")}))

    cfg = ConverterConfig().resolve()
    assert "logos" in cfg.output_dir
    assert "models" in cfg.output_dir



# ─── ConverterResult.__str__ ──────────────────────────────────────────────────

def test_converter_result_str():
    r = ConverterResult(
        model_registry_name="mnemosyne-ft-v2",
        prev_model_name="mnemosyne-ft-prev",
        gguf_path="/tmp/model.gguf",
        elapsed_seconds=120.5,
    )
    s = str(r)
    assert "mnemosyne-ft-v2" in s
    assert "120.5" in s


# ─── convert_and_register() — smoke test ──────────────────────────────────────

def _make_fake_peft_transformers():
    """Módulos falsos para peft e transformers."""
    fake_transformers = types.ModuleType("transformers")
    fake_model = MagicMock()
    fake_model.merge_and_unload.return_value = fake_model
    fake_model.save_pretrained = MagicMock()
    fake_tokenizer = MagicMock()
    fake_tokenizer.save_pretrained = MagicMock()
    fake_transformers.AutoModelForCausalLM = MagicMock()
    fake_transformers.AutoModelForCausalLM.from_pretrained = MagicMock(return_value=fake_model)
    fake_transformers.AutoTokenizer = MagicMock()
    fake_transformers.AutoTokenizer.from_pretrained = MagicMock(return_value=fake_tokenizer)

    fake_peft = types.ModuleType("peft")
    fake_peft.PeftModel = MagicMock()
    fake_peft.PeftModel.from_pretrained = MagicMock(return_value=fake_model)

    return fake_transformers, fake_peft


def test_convert_and_register_smoke(tmp_path, monkeypatch):
    """Pipeline completo com subprocessos e ML mockados."""
    fake_transformers, fake_peft = _make_fake_peft_transformers()
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "peft", fake_peft)

    ckpt_dir = tmp_path / "checkpoint"
    ckpt_dir.mkdir()

    output_dir = tmp_path / "models"

    cfg = ConverterConfig(
        checkpoint_dir=str(ckpt_dir),
        output_dir=str(output_dir),
        llama_cpp_dir="",
    )

    with patch("logos.gguf_converter._run", return_value="") as mock_run, \
         patch("logos.gguf_converter._find_binary", return_value="/fake/llama-quantize"), \
         patch("logos.gguf_converter._find_convert_script", return_value="/fake/convert.py"), \
         patch("logos.gguf_converter._next_version", return_value=1), \
         patch("logos.gguf_converter._register_logos_registry"), \
         patch("logos.gguf_converter._update_ecosystem_json"), \
         patch("shutil.which", return_value=None):
        result = convert_and_register(cfg)

    assert result.model_registry_name == "mnemosyne-ft-v1"
    assert "mnemosyne-ft-v1" in result.gguf_path
    assert result.elapsed_seconds >= 0.0
    # Verifica que a quantização foi chamada (llama-quantize)
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert any("llama-quantize" in " ".join(c) or "quantize" in str(c) for c in calls)


def test_convert_and_register_raises_if_no_checkpoint(tmp_path, monkeypatch):
    """Levanta FileNotFoundError se checkpoint_dir não existir."""
    cfg = ConverterConfig(
        checkpoint_dir=str(tmp_path / "nonexistent"),
        output_dir=str(tmp_path / "out"),
    )
    # resolve() precisaria de sync_root — usamos campos já preenchidos
    with pytest.raises(FileNotFoundError):
        convert_and_register(cfg)


def test_convert_and_register_raises_if_no_checkpoint_dir_set(tmp_path, monkeypatch):
    """Levanta RuntimeError se checkpoint_dir não definido."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": str(tmp_path / "sync")}))

    cfg = ConverterConfig()  # checkpoint_dir vazio
    with pytest.raises(RuntimeError, match="checkpoint_dir"):
        convert_and_register(cfg)
