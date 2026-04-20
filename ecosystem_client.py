"""
ecosystem_client — utilitário Python compartilhado do ecossistema.

Usado por KOSMOS, Mnemosyne e Hermes para ler/escrever
~/.local/share/ecosystem/ecosystem.json (Linux) ou
%APPDATA%\\ecosystem\\ecosystem.json (Windows).
"""
from __future__ import annotations

import json
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any

try:
    from filelock import FileLock as _FileLock
    _HAS_FILELOCK = True
except ImportError:
    _HAS_FILELOCK = False
    warnings.warn(
        "filelock não instalado — write_section sem proteção contra race condition. "
        "Instale com: pip install filelock",
        stacklevel=1,
    )

# ---------------------------------------------------------------------------
# Schema padrão — seções por app
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    "aether":    {"vault_path": "", "config_path": ""},
    "kosmos":    {"data_path": "", "archive_path": "", "config_path": ""},
    "ogma":      {"data_path": "", "config_path": ""},
    "mnemosyne": {"index_paths": [], "config_path": ""},
    "hub":       {"data_path": ""},
    "hermes":    {"output_dir": "", "config_path": ""},
    "akasha":    {"archive_path": "", "data_path": "", "base_url": "", "config_path": ""},
}


def ecosystem_path() -> Path:
    """Retorna o caminho canônico do ecosystem.json segundo XDG/AppData."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "ecosystem" / "ecosystem.json"


def read_ecosystem() -> dict[str, Any]:
    """
    Lê ecosystem.json e retorna o conteúdo mergeado com os defaults.
    Retorna apenas defaults se o arquivo não existir ou estiver corrompido.
    """
    path = ecosystem_path()
    if not path.exists():
        return {k: dict(v) if isinstance(v, dict) else list(v)
                for k, v in _DEFAULTS.items()}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        # Merge: garante que todas as seções existam mesmo em arquivos antigos
        result: dict[str, Any] = {}
        # Preserva campos extras do arquivo que não estão em _DEFAULTS (ex: sync_root)
        for key, value in data.items():
            if key not in _DEFAULTS:
                result[key] = value
        for key, default in _DEFAULTS.items():
            if isinstance(default, dict):
                result[key] = {**default, **data.get(key, {})}
            else:
                result[key] = data.get(key, list(default))
        return result
    except (json.JSONDecodeError, OSError):
        return {k: dict(v) if isinstance(v, dict) else list(v)
                for k, v in _DEFAULTS.items()}


def derive_paths(sync_root: str) -> dict[str, Any]:
    """
    Dado um diretório raiz de sincronização, retorna os caminhos derivados
    para cada app do ecossistema.

    Estrutura gerada:
        {sync_root}/aether/          → aether.vault_path
        {sync_root}/kosmos/          → kosmos.archive_path
        {sync_root}/mnemosyne/docs/  → mnemosyne.watched_dir
        {sync_root}/mnemosyne/chroma_db/ → mnemosyne.chroma_dir
        {sync_root}/hermes/          → hermes.output_dir
        {sync_root}/akasha/          → akasha.archive_path
        {sync_root}/ogma/            → ogma.data_path
    """
    root = Path(sync_root)
    return {
        "aether":    {"vault_path":   str(root / "aether"),
                      "config_path":  str(root / "aether"    / ".config")},
        "kosmos":    {"archive_path": str(root / "kosmos"),
                      "config_path":  str(root / "kosmos"    / ".config")},
        "mnemosyne": {"watched_dir":  str(root / "mnemosyne" / "docs"),
                      "chroma_dir":   str(root / "mnemosyne" / "chroma_db"),
                      "config_path":  str(root / "mnemosyne" / ".config")},
        "hermes":    {"output_dir":   str(root / "hermes"),
                      "config_path":  str(root / "hermes"    / ".config")},
        "akasha":    {"archive_path": str(root / "akasha"),
                      "data_path":    str(root / "akasha"),
                      "config_path":  str(root / "akasha"    / ".config")},
        "ogma":      {"data_path":    str(root / "ogma"),
                      "config_path":  str(root / "ogma"      / ".config")},
    }


def _lock_path() -> Path:
    return ecosystem_path().parent / ".ecosystem.lock"


def write_section(app: str, section: dict[str, Any]) -> None:
    """
    Atualiza apenas a seção `app` do ecosystem.json, preservando as demais.
    Escrita atômica + lock exclusivo para evitar race condition entre processos.

    Raises:
        OSError: se a escrita falhar.
    """
    path = ecosystem_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    def _do_write() -> None:
        data = read_ecosystem()
        if app not in data:
            data[app] = {}
        data[app].update(section)

        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    if _HAS_FILELOCK:
        with _FileLock(str(_lock_path()), timeout=10):
            _do_write()
    else:
        _do_write()
