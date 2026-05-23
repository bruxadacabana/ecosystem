"""
Testes para vram_monitor.py.

Cobre:
  - _amd_sysfs(): leitura sysfs com múltiplas GPUs (escolhe a maior)
  - _nvidia_smi(): parsing da saída do nvidia-smi
  - _ram_fallback(): leitura psutil
  - get_vram_info(): roteamento por perfil (main_pc / laptop / work_pc)
  - should_block_p3(): threshold 85%
  - maybe_unload_before_p3(): integração com ecosystem_client.unload_model
"""
from __future__ import annotations
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import vram_monitor as vm


# ─── _amd_sysfs ──────────────────────────────────────────────────────────────

def test_amd_sysfs_reads_correct_card():
    """Retorna a GPU com maior VRAM total (card discreta)."""
    vram_total_bytes = 8 * 1024 ** 3   # 8 GiB
    vram_used_bytes  = 4 * 1024 ** 3   # 4 GiB

    def mock_sysfs(path: str) -> str:
        if "card0" in path and "vram_total" in path:
            return str(vram_total_bytes)
        if "card0" in path and "vram_used" in path:
            return str(vram_used_bytes)
        return ""

    with patch("vram_monitor._sysfs", side_effect=mock_sysfs):
        info = vm._amd_sysfs()

    assert info is not None
    assert info.source   == "amd_sysfs"
    assert info.total_mb == 8192
    assert info.used_mb  == 4096
    assert abs(info.used_pct - 50.0) < 0.1


def test_amd_sysfs_picks_largest_card():
    """Com dois cards, seleciona o de maior VRAM."""
    def mock_sysfs(path: str) -> str:
        if "card0" in path and "vram_total" in path:
            return str(2 * 1024 ** 3)   # 2 GiB (integrada)
        if "card0" in path and "vram_used" in path:
            return str(512 * 1024 ** 2)
        if "card1" in path and "vram_total" in path:
            return str(8 * 1024 ** 3)   # 8 GiB (discreta)
        if "card1" in path and "vram_used" in path:
            return str(2 * 1024 ** 3)
        return ""

    with patch("vram_monitor._sysfs", side_effect=mock_sysfs):
        info = vm._amd_sysfs()

    assert info is not None
    assert info.total_mb == 8192


def test_amd_sysfs_returns_none_when_no_gpu():
    """Sem sysfs disponível retorna None."""
    with patch("vram_monitor._sysfs", return_value=""):
        info = vm._amd_sysfs()
    assert info is None


def test_amd_sysfs_available_mb():
    """available_mb = total_mb - used_mb."""
    def mock_sysfs(path: str) -> str:
        if "card0" in path and "vram_total" in path:
            return str(8 * 1024 ** 3)
        if "card0" in path and "vram_used" in path:
            return str(6 * 1024 ** 3)
        return ""

    with patch("vram_monitor._sysfs", side_effect=mock_sysfs):
        info = vm._amd_sysfs()

    assert info is not None
    assert info.available_mb == 8192 - 6144


# ─── _nvidia_smi ─────────────────────────────────────────────────────────────

def test_nvidia_smi_parses_output():
    """Parsing correto de 'used_mb, total_mb' sem unidade."""
    with patch("vram_monitor._run", return_value="512, 2048"):
        info = vm._nvidia_smi()

    assert info is not None
    assert info.source   == "nvidia_smi"
    assert info.used_mb  == 512
    assert info.total_mb == 2048
    assert abs(info.used_pct - 25.0) < 0.1


def test_nvidia_smi_returns_none_when_empty():
    """nvidia-smi ausente/falhou → retorna None."""
    with patch("vram_monitor._run", return_value=""):
        info = vm._nvidia_smi()
    assert info is None


def test_nvidia_smi_returns_none_on_malformed():
    """Saída inesperada → retorna None sem exceção."""
    with patch("vram_monitor._run", return_value="N/A"):
        info = vm._nvidia_smi()
    assert info is None


# ─── _ram_fallback ────────────────────────────────────────────────────────────

def test_ram_fallback_uses_psutil():
    """RAM fallback lê total, used e percent do psutil."""
    mock_vm = MagicMock()
    mock_vm.total     = 8 * 1024 ** 3   # 8 GiB
    mock_vm.available = 4 * 1024 ** 3   # 4 GiB livre
    mock_vm.percent   = 50.0

    with patch("psutil.virtual_memory", return_value=mock_vm):
        info = vm._ram_fallback()

    assert info.source   == "ram_fallback"
    assert info.total_mb == 8192
    assert info.used_mb  == 4096
    assert info.used_pct == 50.0


# ─── get_vram_info (roteamento por perfil) ────────────────────────────────────

def test_get_vram_info_main_pc_uses_sysfs():
    """Perfil main_pc → usa _amd_sysfs."""
    fake_info = vm.VramInfo(used_mb=2048, total_mb=8192, used_pct=25.0, source="amd_sysfs")
    with patch("vram_monitor.hp.get_profile", return_value="main_pc"), \
         patch("vram_monitor._amd_sysfs", return_value=fake_info):
        info = vm.get_vram_info()
    assert info.source == "amd_sysfs"


def test_get_vram_info_laptop_uses_nvidia_smi():
    """Perfil laptop → usa _nvidia_smi primeiro."""
    fake_info = vm.VramInfo(used_mb=512, total_mb=2048, used_pct=25.0, source="nvidia_smi")
    with patch("vram_monitor.hp.get_profile", return_value="laptop"), \
         patch("vram_monitor._nvidia_smi", return_value=fake_info):
        info = vm.get_vram_info()
    assert info.source == "nvidia_smi"


def test_get_vram_info_laptop_falls_back_to_sysfs():
    """Laptop sem nvidia-smi → fallback para _amd_sysfs."""
    fake_info = vm.VramInfo(used_mb=512, total_mb=2048, used_pct=25.0, source="amd_sysfs")
    with patch("vram_monitor.hp.get_profile", return_value="laptop"), \
         patch("vram_monitor._nvidia_smi", return_value=None), \
         patch("vram_monitor._amd_sysfs", return_value=fake_info):
        info = vm.get_vram_info()
    assert info.source == "amd_sysfs"


def test_get_vram_info_work_pc_uses_ram():
    """Perfil work_pc → usa _ram_fallback."""
    mock_vm = MagicMock()
    mock_vm.total     = 8 * 1024 ** 3
    mock_vm.available = 6 * 1024 ** 3
    mock_vm.percent   = 25.0
    with patch("vram_monitor.hp.get_profile", return_value="work_pc"), \
         patch("psutil.virtual_memory", return_value=mock_vm):
        info = vm.get_vram_info()
    assert info.source == "ram_fallback"


# ─── should_block_p3 ─────────────────────────────────────────────────────────

def test_should_block_p3_above_threshold():
    """used_pct >= 85 → True."""
    high = vm.VramInfo(used_mb=7000, total_mb=8192, used_pct=90.0, source="amd_sysfs")
    with patch("vram_monitor.get_vram_info", return_value=high):
        assert vm.should_block_p3(85.0) is True


def test_should_block_p3_below_threshold():
    """used_pct < 85 → False."""
    low = vm.VramInfo(used_mb=2048, total_mb=8192, used_pct=25.0, source="amd_sysfs")
    with patch("vram_monitor.get_vram_info", return_value=low):
        assert vm.should_block_p3(85.0) is False


def test_should_block_p3_at_threshold():
    """used_pct == threshold → True (inclusive)."""
    exact = vm.VramInfo(used_mb=6963, total_mb=8192, used_pct=85.0, source="amd_sysfs")
    with patch("vram_monitor.get_vram_info", return_value=exact):
        assert vm.should_block_p3(85.0) is True


# ─── maybe_unload_before_p3 ──────────────────────────────────────────────────

def test_maybe_unload_calls_unload_when_above_threshold():
    """Acima do threshold → chama ecosystem_client.unload_model e retorna True."""
    import ecosystem_client as ec
    high = vm.VramInfo(used_mb=7000, total_mb=8192, used_pct=90.0, source="amd_sysfs")
    with patch("vram_monitor.get_vram_info", return_value=high), \
         patch.object(ec, "_logos_post", return_value={"ok": True}):
        result = vm.maybe_unload_before_p3("smollm2:1.7b")
    assert result is True


def test_maybe_unload_skips_when_below_threshold():
    """Abaixo do threshold → não chama unload, retorna False."""
    import ecosystem_client as ec
    low = vm.VramInfo(used_mb=2048, total_mb=8192, used_pct=25.0, source="amd_sysfs")
    with patch("vram_monitor.get_vram_info", return_value=low), \
         patch.object(ec, "_logos_post") as mock_post:
        result = vm.maybe_unload_before_p3("smollm2:1.7b")
    assert result is False
    mock_post.assert_not_called()


def test_maybe_unload_logos_offline():
    """LOGOS offline (unload retorna False) → retorna False sem exceção."""
    import ecosystem_client as ec
    high = vm.VramInfo(used_mb=7000, total_mb=8192, used_pct=90.0, source="amd_sysfs")
    with patch("vram_monitor.get_vram_info", return_value=high), \
         patch.object(ec, "_logos_post", return_value=None):
        result = vm.maybe_unload_before_p3("smollm2:1.7b")
    assert result is False
