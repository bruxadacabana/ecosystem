"""
vram_monitor — monitor de VRAM/RAM unificado por perfil de hardware.

Detecta o backend correto via hardware_probe e expõe:
  - get_vram_info() → VramInfo (sysfs AMD | nvidia-smi | RAM via psutil)
  - should_block_p3(threshold_pct) → bool
  - maybe_unload_before_p3(model_name, threshold_pct) → bool

Threshold padrão 85%: quando VRAM/RAM atinge esse percentual, tarefas P3 devem
ser bloqueadas ou o modelo P3 descarregado antes de enviar a requisição.

AMD (CachyOS): leitura via sysfs (espelha logos.rs sysfs_vram_mb, sem deps externas).
NVIDIA (Laptop): nvidia-smi --query-gpu.
Windows/CPU: psutil.virtual_memory() — sem GPU dedicada, RAM é o recurso limitante.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import hardware_probe as hp


@dataclass(frozen=True)
class VramInfo:
    """Snapshot de uso de VRAM (ou RAM no WorkPc)."""
    used_mb:  int
    total_mb: int
    used_pct: float    # 0.0–100.0
    source:   str      # "amd_sysfs" | "nvidia_smi" | "ram_fallback"

    @property
    def available_mb(self) -> int:
        return max(0, self.total_mb - self.used_mb)


def _sysfs(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def _run(cmd: list[str], timeout: float = 3.0) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        ).stdout.strip()
    except Exception:
        return ""


def _amd_sysfs() -> VramInfo | None:
    """Lê VRAM via sysfs da GPU discreta com maior VRAM total (Linux/AMD)."""
    best: tuple[int, int] | None = None  # (total_mb, used_mb)
    for i in range(8):
        t_raw = _sysfs(f"/sys/class/drm/card{i}/device/mem_info_vram_total")
        u_raw = _sysfs(f"/sys/class/drm/card{i}/device/mem_info_vram_used")
        if not t_raw or not u_raw:
            continue
        try:
            t_mb = int(t_raw) // 1_048_576
            u_mb = int(u_raw) // 1_048_576
        except ValueError:
            continue
        if t_mb == 0:
            continue
        if best is None or t_mb > best[0]:
            best = (t_mb, u_mb)
    if best is None:
        return None
    total_mb, used_mb = best
    return VramInfo(
        used_mb=used_mb,
        total_mb=total_mb,
        used_pct=(used_mb / total_mb) * 100.0,
        source="amd_sysfs",
    )


def _nvidia_smi() -> VramInfo | None:
    """Lê VRAM via nvidia-smi (Linux/NVIDIA)."""
    out = _run([
        "nvidia-smi",
        "--query-gpu=memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ])
    if not out:
        return None
    try:
        parts = [p.strip() for p in out.splitlines()[0].split(",")]
        used_mb  = int(parts[0])
        total_mb = int(parts[1])
    except (ValueError, IndexError):
        return None
    if total_mb == 0:
        return None
    return VramInfo(
        used_mb=used_mb,
        total_mb=total_mb,
        used_pct=(used_mb / total_mb) * 100.0,
        source="nvidia_smi",
    )


def _ram_fallback() -> VramInfo:
    """Usa RAM do sistema como proxy (Windows/CPU-only, sem GPU dedicada)."""
    import psutil
    vm = psutil.virtual_memory()
    total_mb = vm.total     // 1_048_576
    used_mb  = (vm.total - vm.available) // 1_048_576
    return VramInfo(
        used_mb=used_mb,
        total_mb=total_mb,
        used_pct=float(vm.percent),
        source="ram_fallback",
    )


def get_vram_info() -> VramInfo:
    """Retorna snapshot de VRAM/RAM usando o método correto para o hardware atual."""
    profile = hp.get_profile()
    if profile == "main_pc":
        info = _amd_sysfs()
        if info is not None:
            return info
    elif profile == "laptop":
        info = _nvidia_smi()
        if info is not None:
            return info
        info = _amd_sysfs()  # fallback se nvidia-smi ausente (ex: driver nouveau)
        if info is not None:
            return info
    return _ram_fallback()


def should_block_p3(threshold_pct: float = 85.0) -> bool:
    """True se VRAM/RAM estiver no threshold ou acima — P3 deve ser bloqueado."""
    return get_vram_info().used_pct >= threshold_pct


def maybe_unload_before_p3(model_name: str, threshold_pct: float = 85.0) -> bool:
    """Descarrega model_name via LOGOS se VRAM/RAM estiver acima do threshold.

    Retorna True se o modelo foi descarregado com sucesso.
    Retorna False se VRAM está abaixo do threshold ou LOGOS offline.
    Não levanta exceção — falhas são silenciosas para não bloquear o chamador.
    """
    if not should_block_p3(threshold_pct):
        return False
    import ecosystem_client as ec
    return ec.unload_model(model_name)
