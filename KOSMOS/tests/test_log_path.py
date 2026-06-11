"""
Testes para a resolução do caminho de log do KOSMOS (Fase Extra — Fixes).

O HUB lê o log de cada app em {sync_root}/{app}/{app}.log (read_app_log) para a aba
Monitor. O KOSMOS precisa escrever exatamente nesse caminho — antes escrevia no
diretório local e o Monitor mostrava "sem logs".

Cobre `paths._resolve_log_path`:
  - sync_root configurado → {sync_root}/kosmos/kosmos.log (e cria o diretório);
  - sync_root ausente (None) → fallback local LOG_DIR/kosmos.log;
  - get_sync_root lança → fallback local (não propaga);
  - o caminho com sync_root casa com a convenção do HUB ({sync_root}/kosmos/kosmos.log).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_resolves_to_sync_root_when_configured(tmp_path):
    import app.utils.paths as paths
    sync_root = tmp_path / "ecosystem_root"
    sync_root.mkdir()
    with patch("ecosystem_client.get_sync_root", return_value=sync_root):
        result = paths._resolve_log_path()
    assert result == sync_root / "kosmos" / "kosmos.log"
    assert result.parent.is_dir()  # diretório criado


def test_matches_hub_convention(tmp_path):
    """O caminho deve ser {sync_root}/kosmos/kosmos.log — o que o HUB read_app_log lê."""
    import app.utils.paths as paths
    sync_root = tmp_path / "root"
    sync_root.mkdir()
    with patch("ecosystem_client.get_sync_root", return_value=sync_root):
        result = paths._resolve_log_path()
    # Convenção do HUB: {sync_root}/{app}/{app}.log
    expected = Path(sync_root) / "kosmos" / "kosmos.log"
    assert result == expected


def test_falls_back_to_local_when_no_sync_root():
    import app.utils.paths as paths
    with patch("ecosystem_client.get_sync_root", return_value=None):
        result = paths._resolve_log_path()
    assert result == paths.LOG_DIR / "kosmos.log"


def test_falls_back_to_local_on_error():
    import app.utils.paths as paths
    with patch("ecosystem_client.get_sync_root", side_effect=RuntimeError("boom")):
        result = paths._resolve_log_path()
    assert result == paths.LOG_DIR / "kosmos.log"


def test_log_path_filename_is_kosmos_log(tmp_path):
    import app.utils.paths as paths
    sync_root = tmp_path / "r"
    sync_root.mkdir()
    with patch("ecosystem_client.get_sync_root", return_value=sync_root):
        result = paths._resolve_log_path()
    assert result.name == "kosmos.log"
