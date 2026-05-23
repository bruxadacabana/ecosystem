"""
logos/gguf_converter.py — conversão do adapter LoRA treinado para GGUF e registro no LOGOS.

Pipeline após treinamento QLoRA:
  1. Mesclar adapter ao modelo base via PEFT ``merge_and_unload()``
  2. Converter para GGUF F16 com ``convert_hf_to_gguf.py`` do llama.cpp
  3. Quantizar para Q4_K_M com ``llama-quantize``
  4. Registrar no registry do LOGOS ({models_dir}/registry.json)
  5. Atualizar ecosystem.json com o nome do novo modelo

Pré-requisitos:
  - ``llama.cpp`` compilado (``llama-quantize`` no PATH ou em ``llama_cpp_dir``)
  - ``convert_hf_to_gguf.py`` disponível (llama.cpp scripts ou ``llama-cpp-python``)
  - ``peft`` e ``transformers`` instalados (mesmos que o qlora_trainer)

Uso::

    from logos.gguf_converter import convert_and_register, ConverterConfig

    cfg = ConverterConfig(checkpoint_dir="/path/to/smollm2-qlora-20260523-120000")
    result = convert_and_register(cfg)
    print(result.ollama_model_name)  # "mnemosyne-ft-v2"
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import ecosystem_client as ec

log = logging.getLogger("ecosystem.logos.gguf_converter")

_DEFAULT_BASE_MODEL = "HuggingFaceTB/SmolLM2-1.7B"
_MODEL_PREFIX = "mnemosyne-ft"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ConverterConfig:
    """Parâmetros da conversão — a maioria tem fallback via ecosystem.json."""

    # Diretório do checkpoint LoRA (saída do qlora_trainer)
    checkpoint_dir: str = ""

    # Modelo base HuggingFace (deve coincidir com o usado no treino)
    base_model_name: str = _DEFAULT_BASE_MODEL

    # Onde salvar o GGUF final (default: {sync_root}/logos/models/)
    output_dir: str = ""

    # Caminho ao diretório do llama.cpp (contém llama-quantize e convert_hf_to_gguf.py)
    # Vazio → busca no PATH e em locais comuns
    llama_cpp_dir: str = ""

    def resolve(self) -> "ConverterConfig":
        """Preenche campos vazios via ecosystem.json."""
        cfg = ConverterConfig(**self.__dict__)
        eco = ec.read_ecosystem()

        sync_root = eco.get("sync_root", "")
        if not sync_root:
            raise RuntimeError(
                "sync_root não configurado em ecosystem.json — configure via HUB"
            )
        if not cfg.output_dir:
            cfg.output_dir = str(Path(sync_root) / "logos" / "models")
        return cfg


# ---------------------------------------------------------------------------
# Utilitários de sistema
# ---------------------------------------------------------------------------

def _run(cmd: list[str], *, cwd: "str | None" = None, timeout: float = 3600.0) -> str:
    """Executa subprocesso e retorna stdout. Levanta RuntimeError se falhar."""
    log.debug("$ %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Comando falhou (código {result.returncode}):\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _find_binary(name: str, llama_cpp_dir: str = "") -> str:
    """Localiza um binário do llama.cpp no PATH ou no diretório explícito.

    Retorna o caminho absoluto ou levanta RuntimeError.
    """
    candidates: list[Path] = []
    if llama_cpp_dir:
        candidates.extend([
            Path(llama_cpp_dir) / name,
            Path(llama_cpp_dir) / "build" / "bin" / name,
        ])
    in_path = shutil.which(name)
    if in_path:
        return in_path
    for c in candidates:
        if c.exists() and c.is_file():
            return str(c)
    raise RuntimeError(
        f"Binário '{name}' não encontrado. Compile llama.cpp e adicione ao PATH, "
        f"ou defina ConverterConfig.llama_cpp_dir."
    )


def _find_convert_script(llama_cpp_dir: str = "") -> str:
    """Localiza convert_hf_to_gguf.py no llama.cpp ou via llama-cpp-python.

    Retorna caminho absoluto ao script ou levanta RuntimeError.
    """
    if llama_cpp_dir:
        explicit = Path(llama_cpp_dir) / "convert_hf_to_gguf.py"
        if explicit.exists():
            return str(explicit)

    try:
        import llama_cpp  # noqa: PLC0415
        pkg_dir = Path(llama_cpp.__file__).parent
        script = pkg_dir / "convert_hf_to_gguf.py"
        if script.exists():
            return str(script)
    except ImportError:
        pass

    in_path = shutil.which("convert_hf_to_gguf.py")
    if in_path:
        return in_path

    raise RuntimeError(
        "convert_hf_to_gguf.py não encontrado. Compile llama.cpp e defina "
        "ConverterConfig.llama_cpp_dir, ou instale llama-cpp-python."
    )


# ---------------------------------------------------------------------------
# Etapas do pipeline
# ---------------------------------------------------------------------------

def _merge_adapter(checkpoint_dir: str, base_model_name: str, merged_dir: str) -> None:
    """Mescla o adapter LoRA ao modelo base e salva o modelo completo HuggingFace."""
    try:
        from peft import PeftModel  # noqa: PLC0415
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "peft e transformers são necessários para merge do adapter. "
            "Instale: pip install peft transformers"
        ) from exc

    log.info("Carregando modelo base %s…", base_model_name)
    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype="auto",
        device_map="cpu",
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model_name)

    log.info("Carregando adapter de %s…", checkpoint_dir)
    model = PeftModel.from_pretrained(model, checkpoint_dir)

    log.info("Mesclando adapter (merge_and_unload)…")
    model = model.merge_and_unload()

    log.info("Salvando modelo mesclado em %s…", merged_dir)
    model.save_pretrained(merged_dir)
    tokenizer.save_pretrained(merged_dir)


def _convert_to_gguf(merged_dir: str, gguf_f16_path: str, llama_cpp_dir: str) -> None:
    """Converte modelo HuggingFace para GGUF F16."""
    script = _find_convert_script(llama_cpp_dir)
    log.info("Convertendo para GGUF F16: %s → %s", merged_dir, gguf_f16_path)
    _run([
        sys.executable, script,
        merged_dir,
        "--outtype", "f16",
        "--outfile", gguf_f16_path,
    ])


def _quantize_gguf(f16_path: str, q4_path: str, llama_cpp_dir: str) -> None:
    """Quantiza GGUF F16 para Q4_K_M."""
    binary = _find_binary("llama-quantize", llama_cpp_dir)
    log.info("Quantizando para Q4_K_M: %s → %s", f16_path, q4_path)
    _run([binary, f16_path, q4_path, "Q4_K_M"])


def _sha256_file(path: str) -> str:
    """Calcula SHA256 de um arquivo em blocos de 4 MB."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _next_version(output_dir: str) -> int:
    """Descobre o próximo número de versão para mnemosyne-ft-vN via registry.json.

    Retorna 1 se nenhum modelo fine-tuned existir.
    """
    registry_path = Path(output_dir) / "registry.json"
    if not registry_path.exists():
        return 1
    try:
        entries = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            return 1
    except Exception:
        return 1
    versions = []
    for entry in entries:
        name = entry.get("name", "")
        m = re.search(rf"{re.escape(_MODEL_PREFIX)}-v(\d+)", name)
        if m:
            versions.append(int(m.group(1)))
    return (max(versions) + 1) if versions else 1


def _model_version_name(version: int) -> str:
    return f"{_MODEL_PREFIX}-v{version}"


def _register_logos_registry(model_name: str, gguf_path: str, output_dir: str) -> None:
    """Registra o GGUF no registry do LOGOS ({output_dir}/registry.json).

    Usa a mesma estrutura que update_model_registry em logos.rs:
    deduplicação por `filename`, escrita atômica via arquivo .tmp.
    """
    p = Path(gguf_path)
    log.info("Calculando SHA256 de %s…", p.name)
    sha256 = _sha256_file(gguf_path)
    entry = {
        "name": model_name,
        "repo_id": "local/fine-tuned",
        "filename": p.name,
        "path": str(p),
        "size_bytes": p.stat().st_size,
        "sha256": sha256,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }

    registry_path = Path(output_dir) / "registry.json"
    entries: list[dict] = []
    if registry_path.exists():
        try:
            loaded = json.loads(registry_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = loaded
        except Exception:
            pass

    entries = [e for e in entries if e.get("filename") != entry["filename"]]
    entries.append(entry)

    tmp = registry_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(registry_path)
    log.info("Modelo '%s' registrado no LOGOS registry: %s", model_name, gguf_path)


def _update_ecosystem_json(new_model: str, prev_model: str) -> None:
    """Persiste o nome do modelo fine-tuned em ecosystem.json (seção 'logos').

    Campos escritos:
      logos.finetuned_rag_model      — modelo atual ("mnemosyne-ft-vN")
      logos.finetuned_rag_model_prev — versão anterior

    Tenta também atualizar o LOGOS em memória via HTTP (graceful se offline).
    """
    ec.write_section("logos", {
        "finetuned_rag_model": new_model,
        "finetuned_rag_model_prev": prev_model,
    })
    log.info("ecosystem.json atualizado: finetuned_rag_model=%s", new_model)

    result = ec._logos_post(
        "/logos/models/assign",
        {"app": "mnemosyne", "model_type": "llm_rag", "model": new_model},
        timeout=5.0,
    )
    if result is None:
        log.debug("LOGOS offline ou endpoint ausente — override em memória não aplicado")


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@dataclass
class ConverterResult:
    ollama_model_name: str = ""   # mantido por compatibilidade — nome do modelo no registry
    prev_model_name: str = ""
    gguf_path: str = ""
    elapsed_seconds: float = 0.0

    def __str__(self) -> str:
        return (
            f"ConverterResult("
            f"model={self.ollama_model_name!r}, "
            f"prev={self.prev_model_name!r}, "
            f"gguf={self.gguf_path!r}, "
            f"elapsed={self.elapsed_seconds:.1f}s)"
        )


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def convert_and_register(cfg: "ConverterConfig | None" = None) -> ConverterResult:
    """Executa o pipeline completo: merge → GGUF F16 → Q4_K_M → registry LOGOS.

    Raises:
        RuntimeError: se checkpoint_dir não definido, deps faltando, ou conversão falhar.
        FileNotFoundError: se checkpoint_dir não existir.
    """
    cfg = (cfg or ConverterConfig()).resolve()

    if not cfg.checkpoint_dir:
        raise RuntimeError(
            "checkpoint_dir não especificado. "
            "Defina ConverterConfig.checkpoint_dir com o diretório de saída do qlora_trainer."
        )
    ckpt_path = Path(cfg.checkpoint_dir)
    if not ckpt_path.exists():
        raise FileNotFoundError(f"checkpoint_dir não existe: {cfg.checkpoint_dir}")

    t0 = time.monotonic()
    result = ConverterResult()

    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    version = _next_version(cfg.output_dir)
    model_name = _model_version_name(version)
    result.ollama_model_name = model_name

    # Nome do modelo anterior (para fallback no ecosystem.json)
    prev_name = _model_version_name(version - 1) if version > 1 else ""
    result.prev_model_name = prev_name

    with tempfile.TemporaryDirectory(prefix="gguf_merge_") as tmp_dir:
        merged_dir = str(Path(tmp_dir) / "merged")
        f16_path   = str(output_dir / f"{model_name}-f16.gguf")
        q4_path    = str(output_dir / f"{model_name}-q4km.gguf")

        # Etapa 1: merge adapter → modelo completo
        _merge_adapter(cfg.checkpoint_dir, cfg.base_model_name, merged_dir)

        # Etapa 2: converter para GGUF F16
        _convert_to_gguf(merged_dir, f16_path, cfg.llama_cpp_dir)

    # Etapa 3: quantizar F16 → Q4_K_M
    _quantize_gguf(f16_path, q4_path, cfg.llama_cpp_dir)
    result.gguf_path = q4_path

    try:
        Path(f16_path).unlink()
        log.debug("GGUF F16 removido: %s", f16_path)
    except OSError:
        pass

    # Etapa 4: registrar no LOGOS registry
    _register_logos_registry(model_name, q4_path, cfg.output_dir)

    # Etapa 5: persistir no ecosystem.json + notificar LOGOS
    _update_ecosystem_json(model_name, result.prev_model_name)

    result.elapsed_seconds = time.monotonic() - t0
    log.info("Conversão concluída: %s", result)
    return result


def configure_logging(log_dir: "Path | None" = None) -> None:
    """Configura logging para este módulo (chamar no entry point do processo pai)."""
    from ecosystem_logging import setup_ecosystem_logger, default_log_dir  # noqa: PLC0415
    setup_ecosystem_logger("ecosystem.logos.gguf_converter", log_dir or default_log_dir())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    result = convert_and_register()
    print(result)
