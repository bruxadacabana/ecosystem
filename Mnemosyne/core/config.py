"""
Configuração do Mnemosyne — lê config.json, usa defaults se ausente.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError


def _resolve_config_path() -> Path:
    """Retorna {mnemosyne.config_path}/settings.json se definido no ecosystem.json."""
    try:
        import os as _os
        appdata = _os.environ.get("APPDATA", "")
        candidates = [
            Path(appdata) / "ecosystem" / "ecosystem.json",
            Path.home() / ".local" / "share" / "ecosystem" / "ecosystem.json",
        ]
        for eco_path in candidates:
            if eco_path.exists():
                data = json.loads(eco_path.read_text(encoding="utf-8"))
                config_dir = data.get("mnemosyne", {}).get("config_path", "")
                if config_dir:
                    return Path(config_dir) / "settings.json"
    except Exception:
        pass
    return Path(__file__).parent.parent / "config.json"


_CONFIG_PATH = _resolve_config_path()
_LEGACY_CONFIG_PATH = Path(__file__).parent.parent / "config.json"

_DEFAULTS: dict = {
    "llm_model": "",
    "embed_model": "",
    "chunk_size": 800,
    "chunk_overlap": 100,
    "retriever_k": 4,
    "watched_dir": "",
    "vault_dir": "",
    "chroma_dir": "",
    "auto_index_on_change": True,
    "relevance_decay_days": 30,
    "semantic_chunking": False,
    "indexing_only": False,
}


@dataclass
class AppConfig:
    llm_model: str
    embed_model: str
    chunk_size: int
    chunk_overlap: int
    retriever_k: int
    watched_dir: str
    vault_dir: str = ""
    chroma_dir: str = ""
    auto_index_on_change: bool = True
    relevance_decay_days: int = 30
    semantic_chunking: bool = False
    indexing_only: bool = False

    @property
    def persist_dir(self) -> str:
        """Caminho do vectorstore: chroma_dir se definido, senão derivado de watched_dir."""
        if self.chroma_dir:
            return self.chroma_dir
        if self.watched_dir:
            return str(Path(self.watched_dir) / ".mnemosyne" / "chroma_db")
        return ""

    @property
    def mnemosyne_dir(self) -> str:
        """Diretório .mnemosyne dentro da pasta monitorada."""
        if self.watched_dir:
            return str(Path(self.watched_dir) / ".mnemosyne")
        return ""

    @property
    def is_configured(self) -> bool:
        """True se todos os campos obrigatórios estiverem preenchidos."""
        return bool(self.llm_model and self.embed_model and self.watched_dir)


def load_config() -> AppConfig:
    """
    Carrega config.json; usa defaults para chaves ausentes.

    Raises:
        ConfigError: se config.json existir mas for inválido.
    """
    data: dict = dict(_DEFAULTS)

    # Tenta caminho primário (config_path sincronizado), fallback para config.json local
    for candidate in (_CONFIG_PATH, _LEGACY_CONFIG_PATH):
        if candidate.exists():
            try:
                with candidate.open(encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ConfigError("settings.json deve ser um objeto JSON.")
                data.update(loaded)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"settings.json inválido: {exc}") from exc
            break

    return AppConfig(
        llm_model=str(data.get("llm_model", "")),
        embed_model=str(data.get("embed_model", "")),
        chunk_size=int(data.get("chunk_size", 800)),
        chunk_overlap=int(data.get("chunk_overlap", 100)),
        retriever_k=int(data.get("retriever_k", 4)),
        watched_dir=str(data.get("watched_dir", "")),
        vault_dir=str(data.get("vault_dir", "")),
        chroma_dir=str(data.get("chroma_dir", "")),
        auto_index_on_change=bool(data.get("auto_index_on_change", True)),
        relevance_decay_days=int(data.get("relevance_decay_days", 30)),
        semantic_chunking=bool(data.get("semantic_chunking", False)),
        indexing_only=bool(data.get("indexing_only", False)),
    )


def save_config(config: AppConfig) -> None:
    """Persiste AppConfig em settings.json (ou config.json legado)."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "llm_model": config.llm_model,
        "embed_model": config.embed_model,
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "retriever_k": config.retriever_k,
        "watched_dir": config.watched_dir,
        "vault_dir": config.vault_dir,
        "chroma_dir": config.chroma_dir,
        "auto_index_on_change": config.auto_index_on_change,
        "relevance_decay_days": config.relevance_decay_days,
        "semantic_chunking": config.semantic_chunking,
        "indexing_only": config.indexing_only,
    }
    with _CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
