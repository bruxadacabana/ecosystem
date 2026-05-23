"""
logos/qlora_trainer.py — treinamento QLoRA local com Unsloth + bitsandbytes AMD.

Carrega SmolLM2 1.7B base em NF4 (4-bit) via Unsloth, aplica LoRA r=16/alpha=16,
treina com SFTTrainer sobre o JSONL mais recente de {sync_root}/logos/training_data/,
e salva checkpoints em {sync_root}/logos/checkpoints/.

Roda como tarefa P3: um VramPauseCallback monitora VRAM a cada step e suspende
o loop de treino quando uso supera `vram_threshold_pct` (padrão 85%) — liberando
VRAM para tarefas P1/P2 enquanto aguarda.

Pré-requisitos (não incluídos no venv base do ecossistema):

    # bitsandbytes AMD (pré-release — exige versão >0.49.2):
    pip install --force-reinstall --no-cache-dir --no-deps \
      "https://github.com/bitsandbytes-foundation/bitsandbytes/releases/download/continuous-release_main/bitsandbytes-1.33.7.preview-py3-none-manylinux_2_24_x86_64.whl"

    # Unsloth AMD:
    uv pip install "unsloth[amd]"

Uso::

    from logos.qlora_trainer import train, TrainerConfig

    cfg = TrainerConfig()        # lê ecosystem.json
    result = train(cfg)
    print(result)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import ecosystem_client as ec
import vram_monitor as vm

log = logging.getLogger("ecosystem.logos.qlora_trainer")

# Modelo base padrão: SmolLM2 1.7B — compatível com RX 6600 8GB (QLoRA ~2-3 GB VRAM)
_DEFAULT_MODEL = "HuggingFaceTB/SmolLM2-1.7B"

# Intervalo mínimo entre verificações de VRAM durante pausa (segundos)
_VRAM_CHECK_INTERVAL = 10.0
# Tempo máximo de pausa por step antes de desistir e continuar (segundos)
_PAUSE_MAX_WAIT = 600.0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class TrainerConfig:
    """Parâmetros do treinador QLoRA — valores padrão conservadores para RX 6600."""

    model_name: str = _DEFAULT_MODEL

    # LoRA
    lora_r: int = 16
    lora_alpha: int = 16
    lora_dropout: float = 0.0

    # Treinamento
    batch_size: int = 2
    grad_accumulation: int = 4
    lr: float = 2e-4
    epochs: int = 2
    seq_len: int = 512
    gradient_checkpointing: bool = True

    # VRAM
    vram_threshold_pct: float = 85.0

    # Caminhos (vazios → resolvidos do ecosystem.json)
    training_data_dir: str = ""
    checkpoint_dir: str = ""

    def resolve(self) -> "TrainerConfig":
        """Preenche caminhos vazios via ecosystem.json / sync_root."""
        cfg = TrainerConfig(**self.__dict__)
        eco = ec.read_ecosystem()
        sync_root = eco.get("sync_root", "")
        if not sync_root:
            raise RuntimeError(
                "sync_root não configurado em ecosystem.json — configure via HUB"
            )
        root = Path(sync_root)
        if not cfg.training_data_dir:
            cfg.training_data_dir = str(root / "logos" / "training_data")
        if not cfg.checkpoint_dir:
            cfg.checkpoint_dir = str(root / "logos" / "checkpoints")
        return cfg


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def _find_latest_training_file(data_dir: str) -> "Path | None":
    """Retorna o JSONL mais recente em data_dir, ou None se vazio."""
    p = Path(data_dir)
    if not p.exists():
        return None
    files = sorted(p.glob("*.jsonl"), reverse=True)
    return files[0] if files else None


def _load_dataset(data_dir: str) -> "object":
    """Carrega o JSONL mais recente como HuggingFace Dataset.

    O Dataset retornado contém coluna 'text' com o chat em formato ChatML formatado
    pelo template do tokenizer (aplicado pelo SFTTrainer via `dataset_text_field`).
    Para compatibilidade com SFTTrainer, cada registro precisa de coluna 'messages'.
    """
    from datasets import Dataset  # noqa: PLC0415

    latest = _find_latest_training_file(data_dir)
    if latest is None:
        raise FileNotFoundError(
            f"Nenhum arquivo .jsonl em {data_dir!r}. "
            "Execute training_data_generator.py primeiro."
        )
    records = []
    with latest.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                log.debug("Linha inválida em %s, pulando", latest)

    if not records:
        raise ValueError(f"Arquivo vazio: {latest}")

    log.info("Dataset: %d exemplos de %s", len(records), latest.name)
    return Dataset.from_list(records)


# ---------------------------------------------------------------------------
# Callback de VRAM — pausa o treino quando VRAM > threshold
# ---------------------------------------------------------------------------

def _make_vram_pause_callback(threshold_pct: float, pause_counter: "list[int]") -> "object":
    """Retorna um TrainerCallback que pausa o step se VRAM > threshold_pct.

    pause_counter é uma lista de um elemento usada para contar pausas (mutável,
    compartilhada por referência com o caller).
    """
    try:
        from transformers import TrainerCallback  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("transformers não instalado") from exc

    class VramPauseCallback(TrainerCallback):
        """Pausa o training step enquanto VRAM > threshold_pct (libera para P1/P2)."""

        def on_step_begin(self, args, state, control, **kwargs):
            info = vm.get_vram_info()
            if info.used_pct <= threshold_pct:
                return
            # VRAM alta — aguardar até liberar
            log.info(
                "VRAM %.1f%% > %.1f%% — pausando step %d (P1/P2 ativo)",
                info.used_pct, threshold_pct, state.global_step,
            )
            pause_counter[0] += 1
            deadline = time.monotonic() + _PAUSE_MAX_WAIT
            while time.monotonic() < deadline:
                time.sleep(_VRAM_CHECK_INTERVAL)
                info = vm.get_vram_info()
                if info.used_pct <= threshold_pct:
                    log.info("VRAM liberada (%.1f%%) — retomando", info.used_pct)
                    return
            log.warning(
                "Timeout de pausa atingido (%.0f s) — continuando com VRAM %.1f%%",
                _PAUSE_MAX_WAIT, info.used_pct,
            )

    return VramPauseCallback()


# ---------------------------------------------------------------------------
# Verificação de pré-requisitos
# ---------------------------------------------------------------------------

def check_prerequisites() -> dict[str, bool]:
    """Verifica se as dependências opcionais de ML estão instaladas.

    Retorna dict com nome do pacote → bool (disponível).
    """
    results: dict[str, bool] = {}
    for pkg in ("unsloth", "bitsandbytes", "transformers", "trl", "peft", "datasets"):
        try:
            __import__(pkg)
            results[pkg] = True
        except ImportError:
            results[pkg] = False
    return results


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@dataclass
class TrainerResult:
    checkpoint_dir: str = ""
    elapsed_seconds: float = 0.0
    steps_completed: int = 0
    pauses: int = 0
    training_file: str = ""

    def __str__(self) -> str:
        return (
            f"TrainerResult("
            f"steps={self.steps_completed}, "
            f"pauses={self.pauses}, "
            f"elapsed={self.elapsed_seconds:.1f}s, "
            f"checkpoint={self.checkpoint_dir!r})"
        )


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def train(cfg: "TrainerConfig | None" = None) -> TrainerResult:
    """Executa o pipeline QLoRA completo: carrega modelo, treina, salva checkpoint.

    1. Resolve config a partir do ecosystem.json.
    2. Verifica pré-requisitos (unsloth, bitsandbytes, trl, peft, datasets).
    3. Carrega modelo SmolLM2 1.7B em NF4 via FastLanguageModel do Unsloth.
    4. Aplica LoRA r=16 alpha=16 target_modules=all-linear.
    5. Carrega dataset do JSONL mais recente em training_data_dir.
    6. Treina com SFTTrainer; VramPauseCallback pausa steps se VRAM > 85%.
    7. Salva checkpoint nomeado com timestamp.

    Raises:
        RuntimeError: se pré-requisitos faltando ou sync_root não configurado.
        FileNotFoundError: se training_data_dir vazio (executar generator antes).
    """
    cfg = (cfg or TrainerConfig()).resolve()

    # Verificar pré-requisitos
    missing = [k for k, ok in check_prerequisites().items() if not ok]
    if missing:
        raise RuntimeError(
            f"Dependências de ML não instaladas: {', '.join(missing)}. "
            "Veja os pré-requisitos no docstring do módulo."
        )

    t0 = time.monotonic()
    result = TrainerResult()

    latest = _find_latest_training_file(cfg.training_data_dir)
    if latest:
        result.training_file = str(latest)

    log.info(
        "Iniciando QLoRA: model=%s lr=%g epochs=%d seq_len=%d",
        cfg.model_name, cfg.lr, cfg.epochs, cfg.seq_len,
    )

    # Imports pesados — carregados apenas aqui, não em import time
    from unsloth import FastLanguageModel  # noqa: PLC0415
    from trl import SFTTrainer, SFTConfig  # noqa: PLC0415

    # 1. Carregar modelo em NF4 via Unsloth
    log.info("Carregando %s em NF4 (4-bit)…", cfg.model_name)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=cfg.model_name,
        max_seq_length=cfg.seq_len,
        load_in_4bit=True,
        dtype=None,  # auto-detect
    )

    # 2. Aplicar LoRA
    log.info("Aplicando LoRA r=%d alpha=%d target=all-linear", cfg.lora_r, cfg.lora_alpha)
    model = FastLanguageModel.get_peft_model(
        model,
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules="all-linear",
        bias="none",
        use_gradient_checkpointing="unsloth" if cfg.gradient_checkpointing else False,
        random_state=42,
    )

    # 3. Dataset
    dataset = _load_dataset(cfg.training_data_dir)

    # 4. Checkpoint dir
    ckpt_name = f"smollm2-qlora-{time.strftime('%Y%m%d-%H%M%S')}"
    ckpt_path = Path(cfg.checkpoint_dir) / ckpt_name
    ckpt_path.mkdir(parents=True, exist_ok=True)

    # 5. Callback de VRAM
    pause_counter: list[int] = [0]
    vram_cb = _make_vram_pause_callback(cfg.vram_threshold_pct, pause_counter)

    # 6. Treinar
    log.info(
        "Treinando: batch=%d grad_acc=%d epochs=%d — checkpoint em %s",
        cfg.batch_size, cfg.grad_accumulation, cfg.epochs, ckpt_path,
    )
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            output_dir=str(ckpt_path),
            per_device_train_batch_size=cfg.batch_size,
            gradient_accumulation_steps=cfg.grad_accumulation,
            learning_rate=cfg.lr,
            num_train_epochs=cfg.epochs,
            max_seq_length=cfg.seq_len,
            dataset_text_field=None,   # usa coluna 'messages' diretamente
            logging_steps=10,
            save_steps=100,
            save_total_limit=3,
            fp16=False,                # Unsloth usa bf16/nf4 internamente
            bf16=True,
            report_to="none",          # sem wandb/tensorboard
        ),
        callbacks=[vram_cb],
    )
    train_result = trainer.train()

    result.steps_completed = int(train_result.global_step)
    result.pauses = pause_counter[0]
    result.checkpoint_dir = str(ckpt_path)
    result.elapsed_seconds = time.monotonic() - t0

    log.info("Treinamento concluído: %s", result)
    return result


def configure_logging(log_dir: "Path | None" = None) -> None:
    """Configura logging para este módulo (chamar no entry point do processo pai)."""
    from ecosystem_logging import setup_ecosystem_logger, default_log_dir  # noqa: PLC0415
    setup_ecosystem_logger("ecosystem.logos.qlora_trainer", log_dir or default_log_dir())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    result = train()
    print(result)
