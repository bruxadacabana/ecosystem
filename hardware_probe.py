"""
hardware_probe — detecção de hardware em runtime para seleção de backend de inferência.

Detecta GPU disponível e retorna: backend de inferência (Vulkan/CUDA/CPU),
flags de build do llama-server, limite de contexto recomendado e perfil de hardware.

Lógica espelha detect_hardware_profile() em HUB/src-tauri/src/logos.rs
para consistência entre o componente Rust (LOGOS) e os apps Python.
A detecção acontece uma única vez por processo (resultado cacheado via lru_cache).
"""
from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

HardwareProfile  = Literal["main_pc", "laptop", "work_pc"]
InferenceBackend = Literal["vulkan", "cuda", "cpu"]

# Limite de contexto em tokens por perfil — baseado na VRAM disponível.
# Laptop (MX150 2 GB): KV cache para contextos >2048 esgota VRAM.
_CONTEXT_LIMIT: dict[str, int] = {
    "main_pc": 8192,
    "laptop":  2048,
    "work_pc": 2048,
}

# Flags cmake para build do llama-server por perfil.
# main_pc: Vulkan via RADV (Mesa) — mais estável que ROCm para gfx1032.
# laptop: CUDA padrão para MX150 (driver NVIDIA).
# work_pc: sem AVX2 (i5-3470 Ivy Bridge não tem AVX2); habilita SSE4.1.
_BUILD_FLAGS: dict[str, tuple[str, ...]] = {
    "main_pc": ("-DGGML_VULKAN=ON",),
    "laptop":  ("-DGGML_CUDA=ON",),
    "work_pc": ("-DGGML_AVX=OFF", "-DGGML_AVX2=OFF", "-DGGML_SSE41=ON"),
}


@dataclass(frozen=True)
class HardwareInfo:
    """Informações de hardware para seleção de backend de inferência."""
    profile:           HardwareProfile
    backend:           InferenceBackend
    gpu_name:          str
    vram_mb:           int
    has_avx2:          bool
    context_limit:     int
    llama_build_flags: tuple[str, ...]


def _run(cmd: list[str], timeout: float = 3.0) -> str:
    """Executa comando e retorna stdout; retorna '' em falha."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _sysfs(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def _detect_profile() -> tuple[HardwareProfile, InferenceBackend, str, int]:
    """Detecta perfil de hardware. Retorna (profile, backend, gpu_name, vram_mb)."""

    # Windows: sempre WorkPc/CPU-only (i5-3470, sem GPU dedicada)
    if platform.system() == "Windows":
        return "work_pc", "cpu", "", 0

    # Linux — cascata em 3 etapas (espelha logos.rs)

    # Etapa 1a: NVIDIA via nvidia-smi (MX150 ou qualquer NVIDIA detectado)
    nvidia_out = _run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]
    )
    if nvidia_out:
        first_line = nvidia_out.splitlines()[0]
        parts = [p.strip() for p in first_line.split(",")]
        gpu_name = parts[0] if parts else "NVIDIA"
        vram_raw = parts[1] if len(parts) > 1 else "0 MiB"
        try:
            vram_mb = int(vram_raw.split()[0])
        except (ValueError, IndexError):
            vram_mb = 0
        return "laptop", "cuda", gpu_name, vram_mb

    # Etapa 1b: NVIDIA via sysfs vendor (funciona sem nvidia-smi/driver proprietário)
    # Vendor 0x10de = NVIDIA
    has_nvidia_sysfs = any(
        _sysfs(f"/sys/class/drm/card{i}/device/vendor").lower() == "0x10de"
        for i in range(8)
    )

    # Etapa 2: AMD sysfs — VRAM ≥ 4 GiB → MainPc/RX 6600
    for i in range(8):
        raw = _sysfs(f"/sys/class/drm/card{i}/device/mem_info_vram_total")
        if raw:
            try:
                vram_bytes = int(raw)
            except ValueError:
                continue
            if vram_bytes >= 4 * 1024 ** 3:
                vram_mb = vram_bytes // (1024 * 1024)
                gpu_name = (
                    _sysfs(f"/sys/class/drm/card{i}/device/product_name")
                    or "AMD GPU"
                )
                return "main_pc", "vulkan", gpu_name, vram_mb

    # Etapa 1b aplicada após verificar AMD: NVIDIA sysfs sem AMD ≥ 4 GiB → Laptop
    if has_nvidia_sysfs:
        return "laptop", "cuda", "NVIDIA (sysfs)", 0

    # Etapa 3: Fallback → WorkPc/CPU-only
    return "work_pc", "cpu", "", 0


def _has_avx2() -> bool:
    """Verifica suporte a AVX2 via /proc/cpuinfo (Linux) ou conservativo (outros)."""
    if platform.system() == "Linux":
        try:
            return "avx2" in Path("/proc/cpuinfo").read_text().lower()
        except OSError:
            pass
    if platform.system() == "Windows":
        return False  # i5-3470 (WorkPc) não tem AVX2 — assumir conservativo
    return False


@lru_cache(maxsize=1)
def detect_hardware() -> HardwareInfo:
    """Detecta hardware e retorna HardwareInfo imutável. Cacheado por processo.

    Para forçar re-detecção (testes): chamar detect_hardware.cache_clear() antes.
    """
    profile, backend, gpu_name, vram_mb = _detect_profile()
    has_avx2 = _has_avx2()

    # WorkPc sem AVX2 confirmado → flags explícitas sem AVX
    build_flags: tuple[str, ...] = _BUILD_FLAGS[profile]
    if profile == "work_pc" and not has_avx2:
        build_flags = ("-DGGML_AVX=OFF", "-DGGML_AVX2=OFF", "-DGGML_SSE41=ON")

    return HardwareInfo(
        profile=profile,
        backend=backend,
        gpu_name=gpu_name,
        vram_mb=vram_mb,
        has_avx2=has_avx2,
        context_limit=_CONTEXT_LIMIT[profile],
        llama_build_flags=build_flags,
    )


def get_inference_backend() -> InferenceBackend:
    """Backend de inferência recomendado: 'vulkan' | 'cuda' | 'cpu'."""
    return detect_hardware().backend


def get_context_limit() -> int:
    """Limite de contexto em tokens recomendado para este hardware."""
    return detect_hardware().context_limit


def get_llama_build_flags() -> list[str]:
    """Flags cmake para build do llama-server neste hardware."""
    return list(detect_hardware().llama_build_flags)


def get_profile() -> HardwareProfile:
    """Perfil de hardware: 'main_pc' | 'laptop' | 'work_pc'."""
    return detect_hardware().profile
