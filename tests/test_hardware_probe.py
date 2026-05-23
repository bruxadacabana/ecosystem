"""
Testes para hardware_probe.py.

Cobre:
  - Windows → work_pc / cpu / sem AVX2
  - Linux com nvidia-smi MX150 → laptop / cuda
  - Linux com AMD sysfs VRAM ≥ 4 GiB → main_pc / vulkan
  - Fallback (sem GPU) → work_pc / cpu
  - flags de build por perfil
  - limite de contexto por perfil
  - cache invalidation (detect_hardware.cache_clear)
"""
from __future__ import annotations
import sys
import os
from unittest.mock import patch, MagicMock

# Adiciona raiz do ecossistema ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import hardware_probe as hp


def _clear():
    """Limpa cache entre testes."""
    hp.detect_hardware.cache_clear()


# ─── Perfil Windows ───────────────────────────────────────────────────────────

def test_windows_returns_work_pc():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Windows"):
        info = hp.detect_hardware()
    assert info.profile  == "work_pc"
    assert info.backend  == "cpu"
    assert info.vram_mb  == 0


def test_windows_context_limit_2048():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Windows"):
        assert hp.get_context_limit() == 2048


# ─── Perfil Laptop (NVIDIA MX150 via nvidia-smi) ─────────────────────────────

def test_linux_nvidia_smi_returns_laptop():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value="NVIDIA GeForce MX150, 2000 MiB"):
        info = hp.detect_hardware()
    assert info.profile  == "laptop"
    assert info.backend  == "cuda"
    assert "MX150" in info.gpu_name or "NVIDIA" in info.gpu_name
    assert info.vram_mb  == 2000


def test_laptop_context_limit_2048():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value="NVIDIA GeForce MX150, 2000 MiB"):
        assert hp.get_context_limit() == 2048


def test_laptop_cuda_build_flags():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value="NVIDIA GeForce MX150, 2000 MiB"):
        flags = hp.get_llama_build_flags()
    assert "-DGGML_CUDA=ON" in flags


# ─── Perfil MainPc (AMD RX 6600 via sysfs) ───────────────────────────────────

def test_linux_amd_sysfs_returns_main_pc():
    _clear()
    vram_bytes = 8 * 1024 ** 3  # 8 GiB
    def mock_sysfs(path: str) -> str:
        if "mem_info_vram_total" in path and "card0" in path:
            return str(vram_bytes)
        if "product_name" in path and "card0" in path:
            return "Radeon RX 6600"
        if "vendor" in path:
            return "0x1002"  # AMD vendor
        return ""

    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value=""), \
         patch("hardware_probe._sysfs", side_effect=mock_sysfs):
        info = hp.detect_hardware()

    assert info.profile  == "main_pc"
    assert info.backend  == "vulkan"
    assert info.vram_mb  == 8192
    assert "RX 6600" in info.gpu_name or "AMD" in info.gpu_name


def test_main_pc_context_limit_8192():
    _clear()
    vram_bytes = 8 * 1024 ** 3
    def mock_sysfs(path: str) -> str:
        if "mem_info_vram_total" in path and "card0" in path:
            return str(vram_bytes)
        return ""

    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value=""), \
         patch("hardware_probe._sysfs", side_effect=mock_sysfs):
        assert hp.get_context_limit() == 8192


def test_main_pc_vulkan_build_flags():
    _clear()
    vram_bytes = 8 * 1024 ** 3
    def mock_sysfs(path: str) -> str:
        if "mem_info_vram_total" in path and "card0" in path:
            return str(vram_bytes)
        return ""

    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value=""), \
         patch("hardware_probe._sysfs", side_effect=mock_sysfs):
        flags = hp.get_llama_build_flags()

    assert "-DGGML_VULKAN=ON" in flags


# ─── Fallback (sem GPU) ───────────────────────────────────────────────────────

def test_no_gpu_returns_work_pc():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value=""), \
         patch("hardware_probe._sysfs", return_value=""):
        info = hp.detect_hardware()
    assert info.profile == "work_pc"
    assert info.backend == "cpu"


def test_work_pc_no_avx2_build_flags():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value=""), \
         patch("hardware_probe._sysfs", return_value=""), \
         patch("hardware_probe._has_avx2", return_value=False):
        flags = hp.get_llama_build_flags()
    assert "-DGGML_AVX=OFF"  in flags
    assert "-DGGML_AVX2=OFF" in flags
    assert "-DGGML_SSE41=ON" in flags


# ─── Cache e funções de conveniência ─────────────────────────────────────────

def test_detect_hardware_cached():
    """Segunda chamada retorna o mesmo objeto (cache ativo)."""
    _clear()
    with patch("hardware_probe.platform.system", return_value="Windows"):
        info1 = hp.detect_hardware()
        info2 = hp.detect_hardware()
    assert info1 is info2


def test_get_profile_shortcut():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Windows"):
        assert hp.get_profile() == "work_pc"


def test_get_inference_backend_shortcut():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Windows"):
        assert hp.get_inference_backend() == "cpu"


# ─── ModelProfile por perfil ──────────────────────────────────────────────────

def test_main_pc_model_profile():
    _clear()
    vram_bytes = 8 * 1024 ** 3
    def mock_sysfs(path: str) -> str:
        if "card0" in path and "mem_info_vram_total" in path:
            return str(vram_bytes)
        return ""

    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value=""), \
         patch("hardware_probe._sysfs", side_effect=mock_sysfs):
        mp = hp.get_model_profile()

    assert mp.llm_rag      == "qwen2.5:7b"
    assert mp.llm_analysis == "gemma2:2b"
    assert mp.llm_query    == "qwen2.5:3b"
    assert mp.embed        == "bge-m3"
    assert mp.image_ocr    == "moondream"
    assert mp.vram_budget_mb == 7_500


def test_laptop_model_profile():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value="NVIDIA GeForce MX150, 2000 MiB"):
        mp = hp.get_model_profile()

    assert mp.llm_rag      == "gemma2:2b"
    assert mp.llm_analysis == "smollm2:1.7b"
    assert mp.llm_query    == "smollm2:1.7b"
    # bge-m3 para compatibilidade de vetores com main_pc (Syncthing)
    assert mp.embed        == "bge-m3"
    assert mp.vram_budget_mb == 1_800


def test_work_pc_model_profile():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Windows"):
        mp = hp.get_model_profile()

    assert mp.llm_rag      == "smollm2:1.7b"
    assert mp.llm_analysis == "qwen2.5:0.5b"
    assert mp.llm_query    == "qwen2.5:0.5b"
    assert mp.embed        == "potion-multilingual-128M"
    assert mp.image_ocr    == ""    # sem GPU, sem OCR neural
    assert mp.vram_budget_mb == 4_000


def test_model_profile_in_hardware_info():
    """model_profile está presente em HardwareInfo e é o ModelProfile correto."""
    _clear()
    with patch("hardware_probe.platform.system", return_value="Windows"):
        info = hp.detect_hardware()

    assert isinstance(info.model_profile, hp.ModelProfile)
    assert info.model_profile.llm_rag == "smollm2:1.7b"


def test_model_profile_is_frozen():
    _clear()
    with patch("hardware_probe.platform.system", return_value="Windows"):
        mp = hp.get_model_profile()
    try:
        mp.llm_rag = "other"  # type: ignore
        assert False, "ModelProfile deve ser imutável"
    except Exception:
        pass


# ─── n_gpu_layers por perfil ──────────────────────────────────────────────────

def test_main_pc_gpu_layers_all_full():
    """main_pc: todos os modelos com GPU total (-1)."""
    _clear()
    vram_bytes = 8 * 1024 ** 3
    def mock_sysfs(path: str) -> str:
        if "card0" in path and "mem_info_vram_total" in path:
            return str(vram_bytes)
        return ""

    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value=""), \
         patch("hardware_probe._sysfs", side_effect=mock_sysfs):
        mp = hp.get_model_profile()

    assert mp.llm_rag_gpu_layers      == -1
    assert mp.llm_analysis_gpu_layers == -1
    assert mp.llm_query_gpu_layers    == -1
    assert mp.embed_gpu_layers         == -1
    assert mp.image_ocr_gpu_layers     == -1


def test_laptop_rag_partial_offload():
    """laptop: gemma2:2b usa offload parcial (17 layers) para coexistir com bge-m3."""
    _clear()
    with patch("hardware_probe.platform.system", return_value="Linux"), \
         patch("hardware_probe._run", return_value="NVIDIA GeForce MX150, 2000 MiB"):
        mp = hp.get_model_profile()

    # gemma2:2b com 17 layers na GPU: ~1026 MB — cabe junto com bge-m3 (670 MB)
    assert mp.llm_rag_gpu_layers == 17
    # smollm2:1.7b (~1000 MB) cabe full GPU junto com bge-m3 (670+1000+50=1720 MB)
    assert mp.llm_analysis_gpu_layers == -1
    assert mp.llm_query_gpu_layers    == -1
    assert mp.embed_gpu_layers         == -1
    assert mp.image_ocr_gpu_layers     == -1


def test_work_pc_gpu_layers_all_cpu():
    """work_pc: sem GPU discreta — todos os modelos em CPU (0)."""
    _clear()
    with patch("hardware_probe.platform.system", return_value="Windows"):
        mp = hp.get_model_profile()

    assert mp.llm_rag_gpu_layers      == 0
    assert mp.llm_analysis_gpu_layers == 0
    assert mp.llm_query_gpu_layers    == 0
    assert mp.embed_gpu_layers         == 0
    assert mp.image_ocr_gpu_layers     == 0
