"""
Testes unitários para app/utils/config.py.

ecosystem_client é mockado — os testes são completamente offline e não
dependem de ecosystem.json real nem de Syncthing configurado.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ecosystem_mock(tmp_path):
    """Mock do ecosystem_client que retorna caminhos dentro de tmp_path."""
    archive = tmp_path / "kosmos" / "archive"
    config  = tmp_path / "kosmos" / ".config"

    mock = MagicMock()
    mock.read_ecosystem.return_value = {
        "kosmos": {
            "archive_path": str(archive),
            "config_path":  str(config),
        },
        "sync_root": str(tmp_path),
    }
    mock.write_section.return_value = None
    mock.derive_paths.return_value = {}
    return mock, archive, config


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_returns_kosmos_config(self, tmp_path, ecosystem_mock):
        mock, archive, config = ecosystem_mock

        with patch.dict("sys.modules", {"ecosystem_client": mock}):
            import importlib, utils.config as cfg_module
            importlib.reload(cfg_module)  # recarrega com o mock ativo

            result = cfg_module.load_config()

        from utils.config import KosmosConfig
        assert isinstance(result, KosmosConfig)

    def test_paths_from_ecosystem(self, tmp_path, ecosystem_mock):
        mock, archive, config = ecosystem_mock

        with patch.dict("sys.modules", {"ecosystem_client": mock}):
            import importlib, utils.config as cfg_module
            importlib.reload(cfg_module)

            result = cfg_module.load_config()

        assert result.archive_path == str(archive)
        assert result.config_path  == str(config)

    def test_creates_directories(self, tmp_path, ecosystem_mock):
        mock, archive, config = ecosystem_mock

        with patch.dict("sys.modules", {"ecosystem_client": mock}):
            import importlib, utils.config as cfg_module
            importlib.reload(cfg_module)
            cfg_module.load_config()

        assert archive.exists()
        assert config.exists()

    def test_reads_settings_json(self, tmp_path, ecosystem_mock):
        mock, archive, config = ecosystem_mock
        config.mkdir(parents=True, exist_ok=True)
        (config / "settings.json").write_text(
            json.dumps({"theme": "night", "reader_font_size": 18}),
            encoding="utf-8",
        )

        with patch.dict("sys.modules", {"ecosystem_client": mock}):
            import importlib, utils.config as cfg_module
            importlib.reload(cfg_module)

            result = cfg_module.load_config()

        assert result.theme == "night"
        assert result.reader_font_size == 18

    def test_corrupt_settings_json_uses_defaults(self, tmp_path, ecosystem_mock):
        mock, archive, config = ecosystem_mock
        config.mkdir(parents=True, exist_ok=True)
        (config / "settings.json").write_text("{ broken", encoding="utf-8")

        with patch.dict("sys.modules", {"ecosystem_client": mock}):
            import importlib, utils.config as cfg_module
            importlib.reload(cfg_module)

            result = cfg_module.load_config()

        assert result.theme == "day"  # default

    def test_missing_settings_json_uses_defaults(self, tmp_path, ecosystem_mock):
        mock, archive, config = ecosystem_mock

        with patch.dict("sys.modules", {"ecosystem_client": mock}):
            import importlib, utils.config as cfg_module
            importlib.reload(cfg_module)

            result = cfg_module.load_config()

        assert result.update_interval_minutes == 60  # default
        assert result.purge_read_days == 15          # default


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------

class TestSaveConfig:
    @pytest.fixture
    def cfg(self, tmp_path, ecosystem_mock):
        """KosmosConfig já com config_path resolvido para tmp_path."""
        mock, archive, config = ecosystem_mock
        config.mkdir(parents=True, exist_ok=True)

        with patch.dict("sys.modules", {"ecosystem_client": mock}):
            import importlib, utils.config as cfg_module
            importlib.reload(cfg_module)
            return cfg_module.load_config()

    def test_creates_settings_json(self, cfg):
        config_path = Path(cfg.config_path)

        from utils.config import save_config
        save_config(cfg)

        assert (config_path / "settings.json").exists()

    def test_saved_json_is_valid(self, cfg):
        from utils.config import save_config
        save_config(cfg)

        raw = (Path(cfg.config_path) / "settings.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        assert "theme" in data

    def test_roundtrip(self, cfg, ecosystem_mock):
        mock, archive, config = ecosystem_mock
        cfg.theme = "night"
        cfg.reader_font_size = 24

        from utils.config import save_config
        save_config(cfg)

        with patch.dict("sys.modules", {"ecosystem_client": mock}):
            import importlib, utils.config as cfg_module
            importlib.reload(cfg_module)

            loaded = cfg_module.load_config()

        assert loaded.theme == "night"
        assert loaded.reader_font_size == 24

    def test_no_tmp_file_left(self, cfg):
        from utils.config import save_config
        save_config(cfg)

        config_path = Path(cfg.config_path)
        tmp_files = list(config_path.glob("*.tmp"))
        assert tmp_files == [], f"arquivo .tmp não removido: {tmp_files}"

    def test_only_persistent_fields_saved(self, cfg):
        """Campos internos (archive_path, data_path) não devem ir para o JSON."""
        from utils.config import save_config, _PERSISTENT_FIELDS
        save_config(cfg)

        data = json.loads(
            (Path(cfg.config_path) / "settings.json").read_text(encoding="utf-8")
        )
        assert set(data.keys()) == set(_PERSISTENT_FIELDS)
        assert "archive_path" not in data
        assert "data_path" not in data
        assert "config_path" not in data

    def test_overwrite_existing(self, cfg):
        from utils.config import save_config
        save_config(cfg)

        cfg.theme = "night"
        save_config(cfg)

        data = json.loads(
            (Path(cfg.config_path) / "settings.json").read_text(encoding="utf-8")
        )
        assert data["theme"] == "night"
