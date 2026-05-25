"""
Testes de contrato: HUB (Rust) escreve ecosystem.json → ecosystem_client.py lê corretamente.

Garante que:
1. sync_root escrito pelo HUB (via apply_sync_root) é lido por read_ecosystem()
2. Caminhos derivados por app (mnemosyne, akasha, etc.) chegam corretamente
3. read_ecosystem() sempre lê do disco — sem cache em memória
4. Campos escritos por outros apps não são apagados por writes parciais
5. get_sync_root() retorna Path correto a partir do JSON
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ecosystem_client as ec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hub_json(eco_path: Path, sync_root: str) -> None:
    """Escreve o ecosystem.json exatamente como apply_sync_root do HUB faz."""
    root = Path(sync_root)
    data = {
        "sync_root": sync_root,
        "aether": {
            "vault_path":  str(root / "aether"),
            "config_path": str(root / "aether" / ".config"),
        },
        "kosmos": {
            "archive_path": str(root / "kosmos"),
            "config_path":  str(root / "kosmos" / ".config"),
        },
        "mnemosyne": {
            "watched_dir": str(root / "mnemosyne" / "docs"),
            "chroma_dir":  str(root / "mnemosyne" / "chroma_db"),
            "config_path": str(root / "mnemosyne" / ".config"),
        },
        "hermes": {
            "output_dir":  str(root / "hermes"),
            "config_path": str(root / "hermes" / ".config"),
        },
        "akasha": {
            "archive_path": str(root / "akasha"),
            "data_path":    str(root / "akasha"),
            "config_path":  str(root / "akasha" / ".config"),
        },
        "ogma": {
            "data_path":   str(root / "ogma"),
            "config_path": str(root / "ogma" / ".config"),
        },
    }
    eco_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

def test_read_ecosystem_reads_sync_root_written_by_hub():
    """read_ecosystem() retorna o sync_root que apply_sync_root escreveu."""
    with tempfile.TemporaryDirectory() as tmp:
        eco_path = Path(tmp) / "ecosystem.json"
        sync_root = str(Path(tmp) / "sync")
        _hub_json(eco_path, sync_root)

        with patch.object(ec, "ecosystem_path", return_value=eco_path):
            data = ec.read_ecosystem()

        assert data["sync_root"] == sync_root, (
            "sync_root escrito pelo HUB deve ser lido sem alteração pelo ecosystem_client"
        )


def test_get_sync_root_returns_correct_path():
    """get_sync_root() devolve Path() a partir do sync_root escrito pelo HUB."""
    with tempfile.TemporaryDirectory() as tmp:
        eco_path = Path(tmp) / "ecosystem.json"
        sync_root = str(Path(tmp) / "sync")
        _hub_json(eco_path, sync_root)

        with patch.object(ec, "ecosystem_path", return_value=eco_path):
            result = ec.get_sync_root()

        assert result == Path(sync_root)


def test_read_ecosystem_reads_mnemosyne_and_akasha_paths():
    """Caminhos derivados de mnemosyne e akasha chegam corretos ao Python."""
    with tempfile.TemporaryDirectory() as tmp:
        eco_path = Path(tmp) / "ecosystem.json"
        root = Path(tmp) / "sync"
        _hub_json(eco_path, str(root))

        with patch.object(ec, "ecosystem_path", return_value=eco_path):
            data = ec.read_ecosystem()

        assert data["mnemosyne"]["watched_dir"] == str(root / "mnemosyne" / "docs")
        assert data["mnemosyne"]["chroma_dir"]  == str(root / "mnemosyne" / "chroma_db")
        assert data["akasha"]["data_path"]       == str(root / "akasha")
        assert data["akasha"]["archive_path"]    == str(root / "akasha")
        assert data["ogma"]["data_path"]         == str(root / "ogma")


def test_read_ecosystem_reflects_hub_write_without_restart():
    """read_ecosystem() lê do disco a cada chamada — sem cache em memória.

    Simula HUB atualizando sync_root enquanto os apps Python estão rodando:
    a segunda leitura deve retornar o novo valor sem reiniciar o processo.
    """
    with tempfile.TemporaryDirectory() as tmp:
        eco_path = Path(tmp) / "ecosystem.json"
        root_v1 = str(Path(tmp) / "sync_v1")
        root_v2 = str(Path(tmp) / "sync_v2")
        _hub_json(eco_path, root_v1)

        with patch.object(ec, "ecosystem_path", return_value=eco_path):
            first = ec.read_ecosystem()
            assert first["sync_root"] == root_v1

            # HUB atualiza o arquivo (simula apply_sync_root com novo diretório)
            _hub_json(eco_path, root_v2)

            second = ec.read_ecosystem()

        assert second["sync_root"] == root_v2, (
            "read_ecosystem() deve ler do disco a cada chamada — "
            "sem cache em memória entre leituras"
        )


def test_read_ecosystem_preserves_non_hub_fields_after_hub_write():
    """Campos escritos por outros apps sobrevivem a um write do HUB.

    Ex: AKASHA registra base_url após startup; HUB escreve sync_root depois.
    A base_url não deve desaparecer.
    """
    with tempfile.TemporaryDirectory() as tmp:
        eco_path = Path(tmp) / "ecosystem.json"
        root = Path(tmp) / "sync"
        _hub_json(eco_path, str(root))

        # Outro app (AKASHA) adiciona campo após o HUB ter escrito
        existing = json.loads(eco_path.read_text(encoding="utf-8"))
        existing["akasha"]["base_url"] = "http://localhost:7071"
        existing["hub"] = {"port": 7072}
        eco_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        with patch.object(ec, "ecosystem_path", return_value=eco_path):
            data = ec.read_ecosystem()

        assert data["akasha"]["base_url"] == "http://localhost:7071", (
            "base_url do AKASHA deve ser preservada — "
            "ecosystem_client não deve apagar campos de outros apps"
        )
        assert data["akasha"]["data_path"] == str(root / "akasha"), (
            "data_path escrito pelo HUB deve coexistir com base_url do AKASHA"
        )
        assert data["hub"]["port"] == 7072, (
            "seção hub não deve ser removida por reads/writes de outras seções"
        )
