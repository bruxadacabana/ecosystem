"""
Testes para logos/gguf_converter.py.

Cobre a lógica pura (sem deps externas pesadas):
  - _next_version: lê registry.json e retorna versão correta
  - _register_logos_registry: escreve entrada e deduplica por filename
  - _sha256_file: hash correto de arquivo temporário
  - _model_version_name: formato correto
  - _find_binary: levanta RuntimeError quando binário ausente
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from logos.gguf_converter import (
    _next_version,
    _register_logos_registry,
    _sha256_file,
    _model_version_name,
    _find_binary,
    _MODEL_PREFIX,
    ConverterResult,
)


# ---------------------------------------------------------------------------
# ConverterResult — campo model_registry_name (renomeado de ollama_model_name)
# ---------------------------------------------------------------------------

def test_converter_result_has_model_registry_name():
    r = ConverterResult(model_registry_name="mnemosyne-ft-v1")
    assert r.model_registry_name == "mnemosyne-ft-v1"


def test_converter_result_str_uses_model_registry_name():
    r = ConverterResult(model_registry_name="mnemosyne-ft-v2", gguf_path="/tmp/m.gguf", elapsed_seconds=5.0)
    s = str(r)
    assert "mnemosyne-ft-v2" in s
    assert "ollama" not in s.lower()


def test_converter_result_no_ollama_model_name_field():
    r = ConverterResult()
    assert not hasattr(r, "ollama_model_name"), "campo legado ollama_model_name não deve existir"


# ---------------------------------------------------------------------------
# _model_version_name
# ---------------------------------------------------------------------------

def test_model_version_name_format():
    assert _model_version_name(1) == f"{_MODEL_PREFIX}-v1"
    assert _model_version_name(42) == f"{_MODEL_PREFIX}-v42"


# ---------------------------------------------------------------------------
# _next_version
# ---------------------------------------------------------------------------

def test_next_version_returns_1_when_no_registry(tmp_path):
    assert _next_version(str(tmp_path)) == 1


def test_next_version_returns_1_when_registry_empty(tmp_path):
    (tmp_path / "registry.json").write_text("[]", encoding="utf-8")
    assert _next_version(str(tmp_path)) == 1


def test_next_version_returns_1_when_registry_corrupt(tmp_path):
    (tmp_path / "registry.json").write_text("not json", encoding="utf-8")
    assert _next_version(str(tmp_path)) == 1


def test_next_version_returns_1_when_no_finetune_entries(tmp_path):
    entries = [{"name": "other-model", "filename": "other.gguf"}]
    (tmp_path / "registry.json").write_text(json.dumps(entries), encoding="utf-8")
    assert _next_version(str(tmp_path)) == 1


def test_next_version_increments_from_existing(tmp_path):
    entries = [
        {"name": f"{_MODEL_PREFIX}-v1", "filename": f"{_MODEL_PREFIX}-v1-q4km.gguf"},
        {"name": f"{_MODEL_PREFIX}-v3", "filename": f"{_MODEL_PREFIX}-v3-q4km.gguf"},
    ]
    (tmp_path / "registry.json").write_text(json.dumps(entries), encoding="utf-8")
    assert _next_version(str(tmp_path)) == 4


def test_next_version_single_entry(tmp_path):
    entries = [{"name": f"{_MODEL_PREFIX}-v2", "filename": "f.gguf"}]
    (tmp_path / "registry.json").write_text(json.dumps(entries), encoding="utf-8")
    assert _next_version(str(tmp_path)) == 3


# ---------------------------------------------------------------------------
# _sha256_file
# ---------------------------------------------------------------------------

def test_sha256_file_matches_hashlib(tmp_path):
    content = b"conteudo de teste para sha256"
    f = tmp_path / "model.gguf"
    f.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert _sha256_file(str(f)) == expected


def test_sha256_file_empty_file(tmp_path):
    f = tmp_path / "empty.gguf"
    f.write_bytes(b"")
    assert _sha256_file(str(f)) == hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# _register_logos_registry
# ---------------------------------------------------------------------------

def test_register_creates_registry_file(tmp_path):
    gguf = tmp_path / "mnemosyne-ft-v1-q4km.gguf"
    gguf.write_bytes(b"fake gguf data")

    _register_logos_registry("mnemosyne-ft-v1", str(gguf), str(tmp_path))

    registry_path = tmp_path / "registry.json"
    assert registry_path.exists()
    entries = json.loads(registry_path.read_text(encoding="utf-8"))
    assert len(entries) == 1
    e = entries[0]
    assert e["name"] == "mnemosyne-ft-v1"
    assert e["filename"] == gguf.name
    assert e["path"] == str(gguf)
    assert e["size_bytes"] == len(b"fake gguf data")
    assert e["repo_id"] == "local/fine-tuned"
    assert len(e["sha256"]) == 64  # SHA256 hex
    assert e["downloaded_at"]  # ISO timestamp presente


def test_register_deduplicates_by_filename(tmp_path):
    gguf = tmp_path / "mnemosyne-ft-v1-q4km.gguf"
    gguf.write_bytes(b"v1")

    _register_logos_registry("mnemosyne-ft-v1", str(gguf), str(tmp_path))
    # Sobrescreve com novos bytes
    gguf.write_bytes(b"v1-updated")
    _register_logos_registry("mnemosyne-ft-v1", str(gguf), str(tmp_path))

    entries = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    assert len(entries) == 1, "deve deduplicar por filename"
    assert entries[0]["size_bytes"] == len(b"v1-updated")


def test_register_appends_distinct_models(tmp_path):
    for i in range(1, 4):
        gguf = tmp_path / f"mnemosyne-ft-v{i}-q4km.gguf"
        gguf.write_bytes(f"model v{i}".encode())
        _register_logos_registry(f"mnemosyne-ft-v{i}", str(gguf), str(tmp_path))

    entries = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    assert len(entries) == 3
    names = {e["name"] for e in entries}
    assert names == {"mnemosyne-ft-v1", "mnemosyne-ft-v2", "mnemosyne-ft-v3"}


def test_register_atomic_write_leaves_no_tmp_file(tmp_path):
    gguf = tmp_path / "m.gguf"
    gguf.write_bytes(b"x")
    _register_logos_registry("m", str(gguf), str(tmp_path))
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert not tmp_files, "arquivo .tmp não deve sobrar após escrita atômica"


# ---------------------------------------------------------------------------
# _find_binary
# ---------------------------------------------------------------------------

def test_find_binary_raises_when_not_in_path():
    with pytest.raises(RuntimeError, match="não encontrado"):
        _find_binary("binario-que-nao-existe-xyz-12345")


def test_find_binary_finds_in_explicit_dir(tmp_path):
    # Usar nome único para evitar colisão com binários instalados no PATH
    unique_name = "llama-quantize-test-only-xyz"
    fake_bin = tmp_path / unique_name
    fake_bin.write_bytes(b"")
    fake_bin.chmod(0o755)
    result = _find_binary(unique_name, str(tmp_path))
    assert result == str(fake_bin)
