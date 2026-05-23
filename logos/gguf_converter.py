"""
logos/gguf_converter.py — conversão do adapter LoRA treinado para GGUF e registro no Ollama.

Pipeline após treinamento QLoRA:
  1. Mesclar adapter ao modelo base via PEFT ``merge_and_unload()``
  2. Converter para GGUF F16 com ``convert_hf_to_gguf.py`` do llama.cpp
  3. Quantizar para Q4_K_M com ``llama-quantize``
  4. Gerar Modelfile com o prompt de personalidade da Mnemosyne
  5. Registrar via ``ollama create mnemosyne-ft-vN``
  6. Manter versão anterior como ``mnemosyne-ft-prev`` no Ollama
  7. Atualizar ecosystem.json com o nome do novo modelo

Pré-requisitos:
  - ``llama.cpp`` compilado (``llama-quantize`` no PATH ou em ``llama_cpp_dir``)
  - ``convert_hf_to_gguf.py`` disponível (llama.cpp scripts ou ``llama-cpp-python``)
  - ``peft`` e ``transformers`` instalados (mesmos que o qlora_trainer)
  - ``ollama`` no PATH

Uso::

    from logos.gguf_converter import convert_and_register, ConverterConfig

    cfg = ConverterConfig(checkpoint_dir="/path/to/smollm2-qlora-20260523-120000")
    result = convert_and_register(cfg)
    print(result.ollama_model_name)  # "mnemosyne-ft-v2"
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import ecosystem_client as ec

log = logging.getLogger("ecosystem.logos.gguf_converter")

_DEFAULT_BASE_MODEL = "HuggingFaceTB/SmolLM2-1.7B"
_OLLAMA_MODEL_PREFIX = "mnemosyne-ft"
_OLLAMA_PREV_NAME = "mnemosyne-ft-prev"

# Modelfile — parâmetros conservadores para SmolLM2 1.7B Q4_K_M
_MODELFILE_TMPL = """\
FROM {gguf_path}

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 4096

SYSTEM \"\"\"{system_prompt}\"\"\"
"""

_DEFAULT_SYSTEM_PROMPT = (
    "You are Mnemosyne, a thoughtful and intellectually curious AI assistant. "
    "You help the user explore ideas, synthesize information, and remember what matters. "
    "Be concise, precise, and honest."
)


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

    # Prompt de personalidade para o Modelfile (vazio → lê mnemosyne.personality_prompt)
    personality_prompt: str = ""

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
        if not cfg.personality_prompt:
            cfg.personality_prompt = (
                eco.get("mnemosyne", {}).get("personality_prompt", "")
                or _DEFAULT_SYSTEM_PROMPT
            )
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
    # PATH padrão
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
    # Diretório explícito
    if llama_cpp_dir:
        explicit = Path(llama_cpp_dir) / "convert_hf_to_gguf.py"
        if explicit.exists():
            return str(explicit)

    # llama-cpp-python instala o script junto ao pacote
    try:
        import llama_cpp  # noqa: PLC0415
        pkg_dir = Path(llama_cpp.__file__).parent
        script = pkg_dir / "convert_hf_to_gguf.py"
        if script.exists():
            return str(script)
    except ImportError:
        pass

    # PATH (caso o usuário tenha ln -s)
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
    """Mescla o adapter LoRA ao modelo base e salva o modelo completo HuggingFace.

    Requer: peft, transformers (mesmas dependências do qlora_trainer).
    """
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
        device_map="cpu",       # merge sempre em CPU — sem VRAM
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


def _write_modelfile(gguf_path: str, personality_prompt: str, modelfile_path: str) -> None:
    """Gera o Modelfile do Ollama com prompt de personalidade da Mnemosyne."""
    content = _MODELFILE_TMPL.format(
        gguf_path=gguf_path,
        system_prompt=personality_prompt.replace('"', '\\"'),
    )
    Path(modelfile_path).write_text(content, encoding="utf-8")
    log.debug("Modelfile escrito em %s", modelfile_path)


def _next_version() -> int:
    """Descobre o próximo número de versão para mnemosyne-ft-vN via `ollama list`.

    Retorna 1 se nenhum modelo existir.
    """
    try:
        out = _run(["ollama", "list"])
    except RuntimeError:
        return 1
    # Procura linhas como "mnemosyne-ft-v3:latest"
    versions = re.findall(rf"{re.escape(_OLLAMA_MODEL_PREFIX)}-v(\d+)", out)
    if not versions:
        return 1
    return max(int(v) for v in versions) + 1


def _ollama_model_name(version: int) -> str:
    return f"{_OLLAMA_MODEL_PREFIX}-v{version}"


def _register_ollama(model_name: str, modelfile_path: str) -> None:
    """Registra o modelo no Ollama via `ollama create`."""
    log.info("Registrando modelo '%s' no Ollama…", model_name)
    _run(["ollama", "create", model_name, "-f", modelfile_path])


def _copy_to_prev(current_name: str) -> bool:
    """Copia o modelo atual para 'mnemosyne-ft-prev' antes de substituir.

    Retorna False se não existir modelo atual (primeira vez).
    """
    try:
        _run(["ollama", "list"])
    except RuntimeError:
        return False
    try:
        _run(["ollama", "cp", current_name, _OLLAMA_PREV_NAME])
        log.info("Versão anterior copiada como '%s'", _OLLAMA_PREV_NAME)
        return True
    except RuntimeError:
        log.debug("Sem modelo anterior para copiar ('%s' não existe)", current_name)
        return False


def _update_ecosystem_json(new_model: str, prev_model: str) -> None:
    """Persiste o nome do modelo fine-tuned em ecosystem.json (seção 'logos').

    Campos escritos:
      logos.finetuned_rag_model      — modelo atual ("mnemosyne-ft-vN")
      logos.finetuned_rag_model_prev — versão anterior ("mnemosyne-ft-prev")

    Tenta também atualizar o LOGOS em memória via HTTP (graceful se offline).
    """
    ec.write_section("logos", {
        "finetuned_rag_model": new_model,
        "finetuned_rag_model_prev": prev_model,
    })
    log.info("ecosystem.json atualizado: finetuned_rag_model=%s", new_model)

    # Notificar LOGOS em memória — sem garantia se HUB offline
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
    ollama_model_name: str = ""
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
    """Executa o pipeline completo: merge → GGUF → quantize → Ollama.

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

    # Versão do novo modelo
    version = _next_version()
    model_name = _ollama_model_name(version)
    result.ollama_model_name = model_name

    # Copiar modelo anterior como prev antes de sobrescrever
    prev_name = _ollama_model_name(version - 1) if version > 1 else ""
    if prev_name:
        _copy_to_prev(prev_name)
    result.prev_model_name = _OLLAMA_PREV_NAME if prev_name else ""

    with tempfile.TemporaryDirectory(prefix="gguf_merge_") as tmp_dir:
        merged_dir   = str(Path(tmp_dir) / "merged")
        f16_path     = str(output_dir / f"{model_name}-f16.gguf")
        q4_path      = str(output_dir / f"{model_name}-q4km.gguf")
        modelfile    = str(output_dir / f"{model_name}.Modelfile")

        # Etapa 1: merge
        _merge_adapter(cfg.checkpoint_dir, cfg.base_model_name, merged_dir)

        # Etapa 2: convert → GGUF F16
        _convert_to_gguf(merged_dir, f16_path, cfg.llama_cpp_dir)

    # Etapa 3: quantize F16 → Q4_K_M (fora do tmpdir, o F16 ficou em output_dir)
    _quantize_gguf(f16_path, q4_path, cfg.llama_cpp_dir)
    result.gguf_path = q4_path

    # Apagar F16 após quantização — economiza ~3x espaço
    try:
        Path(f16_path).unlink()
        log.debug("GGUF F16 removido: %s", f16_path)
    except OSError:
        pass

    # Etapa 4: Modelfile
    _write_modelfile(q4_path, cfg.personality_prompt, modelfile)

    # Etapa 5: registrar no Ollama
    _register_ollama(model_name, modelfile)

    # Etapa 6: persistir no ecosystem.json + notificar LOGOS
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
