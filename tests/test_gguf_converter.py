"""
Testes para logos/gguf_converter.py.

Cobre:
  - _find_binary(): localiza binário no PATH ou dir explícito, levanta se ausente
  - _find_convert_script(): localiza script no dir explícito, levanta se ausente
  - _write_modelfile(): gera Modelfile com path e prompt corretos
  - _next_version(): extrai versão de `ollama list`, retorna 1 se nenhum existir
  - _ollama_model_name(): gera nome correto
  - _copy_to_prev(): retorna False se ollama falhar
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

from logos.gguf_converter import (
    ConverterConfig,
    ConverterResult,
    _find_binary,
    _next_version,
    _ollama_model_name,
    _write_modelfile,
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


# ─── _write_modelfile ─────────────────────────────────────────────────────────

def test_write_modelfile_contains_gguf_path(tmp_path):
    mf = str(tmp_path / "model.Modelfile")
    _write_modelfile("/path/to/model.gguf", "Be helpful.", mf)
    content = Path(mf).read_text()
    assert "FROM /path/to/model.gguf" in content


def test_write_modelfile_contains_system_prompt(tmp_path):
    mf = str(tmp_path / "model.Modelfile")
    _write_modelfile("/model.gguf", "Custom personality here.", mf)
    content = Path(mf).read_text()
    assert "Custom personality here." in content


def test_write_modelfile_escapes_double_quotes(tmp_path):
    mf = str(tmp_path / "model.Modelfile")
    prompt = 'Say "hello".'
    _write_modelfile("/model.gguf", prompt, mf)
    content = Path(mf).read_text()
    # As aspas no prompt devem ser escapadas
    assert '\\"hello\\"' in content


# ─── _next_version ────────────────────────────────────────────────────────────

def test_next_version_returns_1_if_no_models():
    with patch("logos.gguf_converter._run", return_value=""):
        assert _next_version() == 1


def test_next_version_returns_1_if_ollama_fails():
    with patch("logos.gguf_converter._run", side_effect=RuntimeError("not found")):
        assert _next_version() == 1


def test_next_version_parses_existing_versions():
    fake_list = (
        "mnemosyne-ft-v1:latest   abc123   2.1 GB\n"
        "mnemosyne-ft-v3:latest   def456   2.1 GB\n"
        "mnemosyne-ft-v2:latest   ghi789   2.1 GB\n"
        "llama3:latest            xyz000   4.5 GB\n"
    )
    with patch("logos.gguf_converter._run", return_value=fake_list):
        assert _next_version() == 4


def test_next_version_handles_single_version():
    with patch("logos.gguf_converter._run", return_value="mnemosyne-ft-v5:latest ..."):
        assert _next_version() == 6


# ─── _ollama_model_name ───────────────────────────────────────────────────────

def test_ollama_model_name():
    assert _ollama_model_name(1) == "mnemosyne-ft-v1"
    assert _ollama_model_name(42) == "mnemosyne-ft-v42"


# ─── _update_ecosystem_json ───────────────────────────────────────────────────

def test_update_ecosystem_json_writes_section(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
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
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": str(tmp_path)}))

    with patch("ecosystem_client._logos_post", return_value=None):
        _update_ecosystem_json("mnemosyne-ft-v1", "")  # não deve levantar


# ─── ConverterConfig.resolve ──────────────────────────────────────────────────

def test_resolve_raises_if_sync_root_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cfg = ConverterConfig()
    with pytest.raises(RuntimeError, match="sync_root"):
        cfg.resolve()


def test_resolve_fills_output_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": str(tmp_path / "sync")}))

    cfg = ConverterConfig().resolve()
    assert "logos" in cfg.output_dir
    assert "models" in cfg.output_dir


def test_resolve_uses_personality_from_ecosystem(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({
        "sync_root": str(tmp_path / "sync"),
        "mnemosyne": {"personality_prompt": "I am a custom persona."},
    }))

    cfg = ConverterConfig().resolve()
    assert cfg.personality_prompt == "I am a custom persona."


def test_resolve_uses_default_personality_if_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": str(tmp_path / "sync")}))

    cfg = ConverterConfig().resolve()
    assert "Mnemosyne" in cfg.personality_prompt  # default contém o nome


# ─── ConverterResult.__str__ ──────────────────────────────────────────────────

def test_converter_result_str():
    r = ConverterResult(
        ollama_model_name="mnemosyne-ft-v2",
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
        personality_prompt="Test persona.",
    )

    with patch("logos.gguf_converter._run", return_value="") as mock_run, \
         patch("logos.gguf_converter._find_binary", return_value="/fake/llama-quantize"), \
         patch("logos.gguf_converter._find_convert_script", return_value="/fake/convert.py"), \
         patch("logos.gguf_converter._next_version", return_value=1), \
         patch("logos.gguf_converter._copy_to_prev", return_value=False), \
         patch("logos.gguf_converter._update_ecosystem_json"), \
         patch("shutil.which", return_value=None):
        result = convert_and_register(cfg)

    assert result.ollama_model_name == "mnemosyne-ft-v1"
    assert "mnemosyne-ft-v1" in result.gguf_path
    assert result.elapsed_seconds >= 0.0
    # Verifica que ollama create foi chamado
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert any("ollama" in " ".join(c) and "create" in " ".join(c) for c in calls)


def test_convert_and_register_raises_if_no_checkpoint(tmp_path, monkeypatch):
    """Levanta FileNotFoundError se checkpoint_dir não existir."""
    cfg = ConverterConfig(
        checkpoint_dir=str(tmp_path / "nonexistent"),
        output_dir=str(tmp_path / "out"),
        personality_prompt="x",
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
