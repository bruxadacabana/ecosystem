"""
Testes para logos/training_data_generator.py.

Cobre:
  - _filter_chunk(): aceita chunks válidos, rejeita pequenos e majoritariamente código
  - _parse_qa_json(): extrai pares válidos, tolerante a lixo ao redor
  - _qa_to_chatml() / _anchor_to_chatml(): estrutura ChatML correta
  - _anchor_to_chatml(): todos os exemplos âncora são formatáveis
  - generate(): integração com ChromaDB fake e LLM mockado
  - GeneratorStats.__str__(): não lança exceção
  - GeneratorConfig.resolve(): levanta RuntimeError se sync_root vazio
"""
from __future__ import annotations

import json
import sys
import types
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from logos.training_data_generator import (
    _ANCHOR_EXAMPLES,
    GeneratorConfig,
    GeneratorStats,
    _anchor_to_chatml,
    _filter_chunk,
    _parse_qa_json,
    _qa_to_chatml,
    generate,
)


# ─── _filter_chunk ────────────────────────────────────────────────────────────

def _make_chunk(text: str) -> dict:
    return {"id": "x", "text": text, "metadata": {}, "collection": "test"}


def test_filter_rejects_short_chunk():
    assert _filter_chunk(_make_chunk("short"), min_chars=200) is False


def test_filter_accepts_long_chunk():
    text = "A" * 201
    assert _filter_chunk(_make_chunk(text), min_chars=200) is True


def test_filter_rejects_mostly_code():
    # Mais de 50% das linhas são código (leading spaces / tabs)
    lines = ["    def foo():", "    pass", "    return x"] * 10
    text = "\n".join(lines) + "\n" + "Some prose here."
    assert _filter_chunk(_make_chunk(text), min_chars=200) is False


def test_filter_accepts_mixed_prose():
    prose = "This is a long paragraph about science. " * 10
    assert _filter_chunk(_make_chunk(prose), min_chars=200) is True


# ─── _parse_qa_json ───────────────────────────────────────────────────────────

def test_parse_valid_json():
    raw = '[{"question": "What is X?", "answer": "X is Y."}]'
    pairs = _parse_qa_json(raw)
    assert len(pairs) == 1
    assert pairs[0]["question"] == "What is X?"


def test_parse_json_with_surrounding_text():
    raw = 'Sure! Here are the pairs:\n[{"question": "Q?", "answer": "A."}]\nDone.'
    pairs = _parse_qa_json(raw)
    assert len(pairs) == 1


def test_parse_filters_invalid_entries():
    raw = '[{"question": "Q?", "answer": "A."}, {"question": "", "answer": "A."}]'
    pairs = _parse_qa_json(raw)
    assert len(pairs) == 1


def test_parse_returns_empty_on_garbage():
    assert _parse_qa_json("No JSON here at all.") == []


def test_parse_returns_empty_on_malformed_json():
    assert _parse_qa_json("[{bad json}]") == []


# ─── ChatML formatting ────────────────────────────────────────────────────────

def test_qa_to_chatml_structure():
    entry = _qa_to_chatml("text", "question?", "answer.")
    assert "messages" in entry
    roles = [m["role"] for m in entry["messages"]]
    assert roles == ["system", "user", "assistant"]
    assert entry["messages"][1]["content"] == "question?"
    assert entry["messages"][2]["content"] == "answer."


def test_anchor_to_chatml_structure():
    anchor = {"instruction": "What is 2+2?", "answer": "4."}
    entry = _anchor_to_chatml(anchor)
    assert "messages" in entry
    roles = [m["role"] for m in entry["messages"]]
    assert roles == ["system", "user", "assistant"]
    assert entry["messages"][1]["content"] == "What is 2+2?"


def test_all_anchor_examples_formattable():
    for anchor in _ANCHOR_EXAMPLES:
        entry = _anchor_to_chatml(anchor)
        for msg in entry["messages"]:
            assert msg["role"] in ("system", "user", "assistant")
            assert isinstance(msg["content"], str)
            assert msg["content"].strip()


# ─── GeneratorStats ───────────────────────────────────────────────────────────

def test_stats_str_does_not_raise():
    stats = GeneratorStats(chunks_seen=10, pairs_generated=5)
    s = str(stats)
    assert "chunks_seen=10" in s
    assert "pairs=5" in s


# ─── GeneratorConfig.resolve ──────────────────────────────────────────────────

def test_resolve_raises_if_sync_root_empty(monkeypatch, tmp_path):
    # Aponta ecosystem_path para arquivo inexistente → retorna defaults (sync_root vazio)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cfg = GeneratorConfig()
    with pytest.raises(RuntimeError, match="sync_root"):
        cfg.resolve()


def test_resolve_fills_paths_from_sync_root(monkeypatch, tmp_path):
    fake_sync = str(tmp_path / "sync")
    eco_path = tmp_path / "ecosystem" / "ecosystem.json"
    eco_path.parent.mkdir(parents=True)
    eco_path.write_text(json.dumps({"sync_root": fake_sync}))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    cfg = GeneratorConfig().resolve()
    assert "mnemosyne" in cfg.chroma_dir or "chroma_db" in cfg.chroma_dir
    assert "logos" in cfg.output_dir


# ─── generate() — integração com mocks ───────────────────────────────────────

def _make_fake_chromadb(tmp_path: Path, chunks: list[str]) -> types.ModuleType:
    """Cria um módulo chromadb falso que retorna os chunks fornecidos."""
    fake = types.ModuleType("chromadb")

    class FakeColl:
        def __init__(self):
            self.name = "test_coll"

        def count(self):
            return len(chunks)

        def get(self, limit=100, offset=0, include=None):
            batch = chunks[offset : offset + limit]
            return {
                "documents": batch,
                "metadatas": [{}] * len(batch),
                "ids": [f"id-{i}" for i in range(offset, offset + len(batch))],
            }

    class FakeClient:
        def __init__(self, path):
            pass

        def list_collections(self):
            coll = FakeColl()
            coll.name = "test_coll"
            return [coll]

        def get_collection(self, name):
            return FakeColl()

    fake.PersistentClient = FakeClient
    return fake


def test_generate_produces_jsonl(tmp_path, monkeypatch):
    """Smoke test: generate() com ChromaDB falso e LLM mockado gera arquivo JSONL válido."""
    long_text = "This is a sufficiently long passage about an interesting topic. " * 5

    fake_chromadb = _make_fake_chromadb(tmp_path, [long_text, long_text])
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)

    fake_response = {
        "choices": [{"message": {"content": '[{"question": "What is this?", "answer": "A passage."}]'}}]
    }

    cfg = GeneratorConfig(
        chroma_dir=str(tmp_path / "chroma"),
        output_dir=str(tmp_path / "output"),
        pairs_per_chunk=(1, 1),
        anchor_ratio=0.1,
    )

    (tmp_path / "chroma").mkdir(parents=True)

    with patch("ecosystem_client.request_llm", return_value=fake_response):
        stats = generate(cfg)

    output = Path(stats.output_file)
    assert output.exists()
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 0
    for line in lines:
        entry = json.loads(line)
        assert "messages" in entry
        assert len(entry["messages"]) == 3


def test_generate_includes_anchors(tmp_path, monkeypatch):
    """Verifica que âncoras são intercaladas (anchor_ratio=0.5 → ~metade âncoras)."""
    long_text = "A long research text about science and discovery. " * 5
    fake_chromadb = _make_fake_chromadb(tmp_path, [long_text] * 10)
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)

    fake_response = {
        "choices": [{"message": {"content": '[{"question": "Q?", "answer": "A."}]'}}]
    }

    cfg = GeneratorConfig(
        chroma_dir=str(tmp_path / "chroma"),
        output_dir=str(tmp_path / "output"),
        pairs_per_chunk=(1, 1),
        anchor_ratio=0.5,
    )
    (tmp_path / "chroma").mkdir(parents=True)

    with patch("ecosystem_client.request_llm", return_value=fake_response):
        stats = generate(cfg)

    assert stats.anchors_added > 0


def test_generate_skips_llm_failure(tmp_path, monkeypatch):
    """Se LLM retornar JSON inválido, chunk é pulado sem travar o pipeline."""
    long_text = "A sufficiently long passage about something interesting. " * 5
    fake_chromadb = _make_fake_chromadb(tmp_path, [long_text])
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)

    bad_response = {"choices": [{"message": {"content": "I cannot help with that."}}]}

    cfg = GeneratorConfig(
        chroma_dir=str(tmp_path / "chroma"),
        output_dir=str(tmp_path / "output"),
        pairs_per_chunk=(1, 1),
        anchor_ratio=0.0,
    )
    (tmp_path / "chroma").mkdir(parents=True)

    with patch("ecosystem_client.request_llm", return_value=bad_response):
        stats = generate(cfg)

    assert stats.pairs_generated == 0


def test_generate_respects_max_chunks(tmp_path, monkeypatch):
    """max_chunks limita o número de chunks processados."""
    long_text = "Long passage about a topic with lots of useful information. " * 5
    fake_chromadb = _make_fake_chromadb(tmp_path, [long_text] * 20)
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)

    fake_response = {
        "choices": [{"message": {"content": '[{"question": "Q?", "answer": "A."}]'}}]
    }

    cfg = GeneratorConfig(
        chroma_dir=str(tmp_path / "chroma"),
        output_dir=str(tmp_path / "output"),
        pairs_per_chunk=(1, 1),
        anchor_ratio=0.0,
        max_chunks=3,
    )
    (tmp_path / "chroma").mkdir(parents=True)

    with patch("ecosystem_client.request_llm", return_value=fake_response):
        stats = generate(cfg)

    assert stats.chunks_seen <= 3
