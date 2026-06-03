from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ecosystem_client  # disponível via sys.path configurado em paths.py
from app.utils.paths import LOCAL_DATA_DIR

log = logging.getLogger("kosmos.config")

_SETTINGS_FILE = "settings.json"

# Campos persistidos em settings.json — paths e config de IA vêm do HUB, não daqui
_PERSISTENT_FIELDS = (
    "theme",
    "reader_font_size",
    "update_interval_minutes",
    "purge_read_days",
    "purge_unread_days",
    "auto_scrape",
    "default_translation_lang",
    "display_language",
    "manual_topics",
)


@dataclass
class KosmosConfig:
    # Aparência e comportamento
    theme: str = "day"
    reader_font_size: int = 20
    update_interval_minutes: int = 60
    purge_read_days: int = 15
    purge_unread_days: int = 30
    auto_scrape: bool = True
    default_translation_lang: str = "pt"
    display_language: str = "pt"
    # Tags de interesse definidas manualmente pela usuária — reforçam o
    # shared_topic_profile (via interests.apply_manual_topics). Editáveis em Settings.
    manual_topics: list[str] = field(default_factory=list)

    # Paths — derivados do ecosystem.json em runtime, não editáveis pelo usuário diretamente
    archive_path: str = ""
    config_path: str = ""
    data_path: str = ""


def _resolve_ecosystem_paths() -> tuple[Path, Path]:
    """Retorna (archive_path, config_path) do ecosystem.json ou deriva do sync_root."""
    eco = ecosystem_client.read_ecosystem()
    kosmos = eco.get("kosmos", {})

    archive_str = kosmos.get("archive_path", "")
    config_str  = kosmos.get("config_path", "")

    if archive_str and config_str:
        return Path(archive_str), Path(config_str)

    sync_root = eco.get("sync_root", "")
    if sync_root:
        derived = ecosystem_client.derive_paths(sync_root)
        k = derived.get("kosmos", {})
        return Path(k.get("archive_path", "")), Path(k.get("config_path", ""))

    # Fallback: diretório local (sem Syncthing configurado)
    log.warning("sync_root não configurado — usando caminhos locais como fallback.")
    return LOCAL_DATA_DIR / "archive", LOCAL_DATA_DIR / ".config"


def load_config() -> KosmosConfig:
    archive_path, config_path = _resolve_ecosystem_paths()

    try:
        config_path.mkdir(parents=True, exist_ok=True)
        archive_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("Falha ao criar diretórios de configuração: %s", exc)
        raise

    cfg = KosmosConfig()
    settings_file = config_path / _SETTINGS_FILE

    if settings_file.exists():
        try:
            data: dict[str, Any] = json.loads(settings_file.read_text(encoding="utf-8"))
            for field in _PERSISTENT_FIELDS:
                if field in data:
                    setattr(cfg, field, data[field])
            log.debug("settings.json carregado de %s.", settings_file)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            log.warning("Falha ao ler settings.json (%s) — usando defaults.", exc)

    cfg.archive_path = str(archive_path)
    cfg.config_path  = str(config_path)
    cfg.data_path    = str(LOCAL_DATA_DIR)

    _register_paths(archive_path, config_path)
    log.info("Config carregada. archive=%s config=%s", archive_path, config_path)
    return cfg


def save_config(cfg: KosmosConfig) -> None:
    config_path = Path(cfg.config_path)
    settings_file = config_path / _SETTINGS_FILE

    data = {field: getattr(cfg, field) for field in _PERSISTENT_FIELDS}

    try:
        config_path.mkdir(parents=True, exist_ok=True)
        tmp = settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, settings_file)
        log.debug("Config salva em %s.", settings_file)
    except OSError as exc:
        log.error("Falha ao salvar settings.json: %s", exc)
        raise


def _register_paths(archive_path: Path, config_path: Path) -> None:
    """Escreve os paths do KOSMOS no ecosystem.json para que o HUB os conheça."""
    try:
        ecosystem_client.write_section("kosmos", {
            "data_path":    str(LOCAL_DATA_DIR),
            "archive_path": str(archive_path),
            "config_path":  str(config_path),
        })
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Falha ao registrar paths no ecosystem.json: %s", exc)
