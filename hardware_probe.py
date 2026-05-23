"""
hardware_probe — detecção de hardware em runtime para seleção de backend de inferência.

Detecta GPU disponível e retorna: backend de inferência (Vulkan/CUDA/CPU),
flags de build do llama-server, limite de contexto, perfil de hardware e
modelos LLM recomendados por funcionalidade.

Lógica espelha detect_hardware_profile() + model_profile() em
HUB/src-tauri/src/logos.rs para consistência entre o componente Rust (LOGOS)
e os apps Python. Usado como fallback offline quando o LOGOS não está disponível.
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
class ModelProfile:
    """Modelos LLM recomendados por funcionalidade para um perfil de hardware.

    Espelha ModelProfile em HUB/src-tauri/src/logos.rs.
    Usado como fallback offline quando o LOGOS não está disponível.
    """
    llm_rag:        str   # RAG conversacional (Mnemosyne) — síntese multi-doc
    llm_analysis:   str   # análise/sumarização em background (KOSMOS) — JSON estruturado
    llm_query:      str   # extração on-demand e expansão de query (AKASHA) — baixa latência
    embed:          str   # modelo de embedding (todos os apps)
    image_ocr:      str   # multimodal/OCR (Mnemosyne) — "" se hardware não suporta
    vram_budget_mb: int   # orçamento de VRAM/RAM disponível para inferência (MB)

    # Camadas GPU por modelo (-1 = todas, 0 = CPU only, N = N camadas na GPU)
    # Espelha n_gpu_layers do llama-server. Controlado pelo LOGOS ao carregar cada modelo.
    llm_rag_gpu_layers:      int  # layers na GPU para llm_rag
    llm_analysis_gpu_layers: int  # layers na GPU para llm_analysis
    llm_query_gpu_layers:    int  # layers na GPU para llm_query
    embed_gpu_layers:         int  # layers na GPU para embed
    image_ocr_gpu_layers:     int  # layers na GPU para image_ocr


# Espelha HardwareProfile::model_profile() em logos.rs.
# Atualizar aqui quando os modelos recomendados mudarem no Rust.
_MODEL_PROFILE: dict[str, ModelProfile] = {
    "main_pc": ModelProfile(
        # RX 6600 8 GB: qwen2.5:7b (4.7 GB) + gemma2:2b (1.6 GB) coexistem (~6.3 GB < 7.5 GB)
        llm_rag      = "qwen2.5:7b",
        llm_analysis = "gemma2:2b",
        # qwen2.5:3b (~1.9 GB) coexiste com qwen2.5:7b (4.7+1.9=6.6 GB)
        llm_query    = "qwen2.5:3b",
        embed        = "bge-m3",
        # moondream (~1.7 GB) coexiste com qwen2.5:7b (4.7+1.7=6.4 GB < 7.5 GB)
        image_ocr    = "moondream",
        vram_budget_mb = 7_500,
        # RX 6600 8 GB — tudo na GPU
        llm_rag_gpu_layers      = -1,
        llm_analysis_gpu_layers = -1,
        llm_query_gpu_layers    = -1,
        embed_gpu_layers         = -1,
        image_ocr_gpu_layers     = -1,
    ),
    "laptop": ModelProfile(
        # MX150 2 GB: bge-m3 (670 MB) + gemma2:2b partial (17 layers, ~1026 MB) coexistem
        llm_rag      = "gemma2:2b",
        # smollm2:1.7b (~1000 MB) cabe junto com bge-m3 (670+1000+50=1720 MB < 1800 MB)
        llm_analysis = "smollm2:1.7b",
        llm_query    = "smollm2:1.7b",
        # bge-m3 (670 MB): mesmo vetorstore que main_pc — compatível via Syncthing
        embed        = "bge-m3",
        # moondream (~1700 MB): usar isolado — LOGOS descarga bge-m3 antes de carregar
        image_ocr    = "moondream",
        vram_budget_mb = 1_800,
        # gemma2:2b: offload parcial — 17 layers na GPU (~1026 MB), resto em RAM
        # bge-m3 (670 MB) + gemma2:2b parcial (1026 MB) + KV cache (~104 MB) ≈ 1800 MB ✓
        llm_rag_gpu_layers      = 17,
        # smollm2:1.7b: ~1000 MB full GPU, cabe junto com bge-m3 (670+1000+50=1720 MB)
        llm_analysis_gpu_layers = -1,
        llm_query_gpu_layers    = -1,
        embed_gpu_layers         = -1,
        # moondream: LOGOS descarga bge-m3 antes — pode usar GPU total
        image_ocr_gpu_layers     = -1,
    ),
    "work_pc": ModelProfile(
        llm_rag      = "smollm2:1.7b",
        # qwen2.5:0.5b: JSON parse rate 61% vs smollm2 26% — melhor para extração
        llm_analysis = "qwen2.5:0.5b",
        llm_query    = "qwen2.5:0.5b",
        # potion: modelo estático, sem GPU, multilíngue — substitui all-minilm
        embed        = "potion-multilingual-128M",
        # WorkPc sem GPU discreta — OCR via Tesseract local apenas
        image_ocr    = "",
        vram_budget_mb = 4_000,
        # i5-3470 sem GPU discreta — tudo em RAM/CPU
        llm_rag_gpu_layers      = 0,
        llm_analysis_gpu_layers = 0,
        llm_query_gpu_layers    = 0,
        embed_gpu_layers         = 0,
        image_ocr_gpu_layers     = 0,
    ),
}


@dataclass(frozen=True)
class HardwareInfo:
    """Informações de hardware para seleção de backend de inferência e modelos."""
    profile:           HardwareProfile
    backend:           InferenceBackend
    gpu_name:          str
    vram_mb:           int
    has_avx2:          bool
    context_limit:     int
    llama_build_flags: tuple[str, ...]
    model_profile:     ModelProfile


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
        model_profile=_MODEL_PROFILE[profile],
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


def get_model_profile() -> ModelProfile:
    """Modelos LLM recomendados para o hardware atual.

    Fallback offline do LOGOS: mesmos valores de HardwareProfile::model_profile()
    em logos.rs. Usar quando o HUB não estiver disponível.
    """
    return detect_hardware().model_profile
