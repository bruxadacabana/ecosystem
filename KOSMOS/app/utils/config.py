"""Leitura e escrita das configurações do usuário em data/settings.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.utils.paths import Paths

log = logging.getLogger("kosmos.config")

DEFAULTS: dict[str, Any] = {
    "theme":                    "day",
    "reader_font_size":         18,
    "update_interval_minutes":  30,
    "purge_read_days":          30,
    "purge_unread_days":        90,
    "auto_scrape":              False,
    "default_translation_lang": "pt",
    "reddit_client_id":         "",
    "reddit_client_secret":     "",
    "reddit_user_agent":        "KOSMOS/1.0",
    "http_port":                8965,
    # IA — modelos recomendados pelo LOGOS para o KOSMOS
    "ai_gen_model":             "gemma2:2b",   # análise: ~2-3× mais rápido que 7B
    "ai_num_ctx":               4096,           # necessário para KV prefix cache consistente
}


class ConfigError(Exception):
    """Erro ao ler ou gravar as configurações."""


class Config:
    """Gerencia settings.json em data/.

    Uso::

        config = Config()
        theme = config.get("theme", "day")
        config.set("theme", "night")
    """

    _LEGACY_PATH: Path = Paths.DATA / "settings.json"

    def __init__(self) -> None:
        self._path: Path = Paths.SETTINGS
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def _load(self) -> None:
        # Tenta caminho primário (config_path sincronizado), fallback para legado em data/
        for candidate in (self._path, self._LEGACY_PATH):
            if candidate.exists():
                try:
                    with open(candidate, "r", encoding="utf-8") as fh:
                        loaded = json.load(fh)
                    if not isinstance(loaded, dict):
                        raise ConfigError("settings.json não contém um objeto JSON válido.")
                    self._data = loaded
                except json.JSONDecodeError as exc:
                    log.warning("settings.json corrompido, usando padrões. Detalhe: %s", exc)
                    self._data = {}
                except OSError as exc:
                    log.warning("Não foi possível ler settings.json: %s", exc)
                    self._data = {}
                break

        # Preencher chaves ausentes com defaults
        for key, value in DEFAULTS.items():
            if key not in self._data:
                self._data[key] = value

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            raise ConfigError(f"Não foi possível gravar settings.json: {exc}") from exc

    # ------------------------------------------------------------------
    # Acesso público
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def get_all(self) -> dict[str, Any]:
        return dict(self._data)
