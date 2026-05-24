"""
logos/finetune_scheduler.py — agendamento e orquestração do ciclo de fine-tuning.

Responsabilidades:
  - Detectar quando o corpus cresceu >20% desde o último ciclo (auto-trigger)
  - Executar o ciclo completo em background: gerar dados → treinar → converter → registrar
  - Proteger contra execução simultânea via lock file
  - Persistir estado em {sync_root}/logos/finetune_state.json
  - Notificar o HUB via ecosystem_client ao início e ao término

Integração com o HUB:
  O botão "Iniciar ciclo" no dashboard chama ``trigger_manual()`` (ou o endpoint
  HTTP do HUB que o invoca). O estado é lido pelo painel React via
  ``{sync_root}/logos/finetune_state.json``.

Uso::

    from logos.finetune_scheduler import trigger_manual, should_auto_trigger

    if should_auto_trigger():
        trigger_manual()   # retorna imediatamente; ciclo roda em background
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import ecosystem_client as ec

log = logging.getLogger("logos")

# Threshold de crescimento do corpus para disparo automático (20%)
_AUTO_TRIGGER_GROWTH = 0.20
# Arquivo de estado do ciclo de fine-tuning
_STATE_FILE = "finetune_state.json"
# Lock file — presença indica ciclo em andamento
_LOCK_FILE = "finetune.lock"


# ---------------------------------------------------------------------------
# Estado persistido
# ---------------------------------------------------------------------------

@dataclass
class FinetuneState:
    """Estado do ciclo de fine-tuning persistido em finetune_state.json."""

    # Contagem de chunks no ChromaDB na época do último treino
    corpus_chunks_at_last_train: int = 0

    # Timestamp ISO-8601 UTC do último ciclo concluído
    last_cycle_at: str = ""

    # Modelo atual registrado no LOGOS registry
    current_model: str = ""

    # Modelo anterior (fallback)
    prev_model: str = ""

    # Etapa atual do ciclo em andamento (vazio se parado)
    current_step: str = ""

    # Número de exemplos gerados no ciclo atual
    examples_generated: int = 0

    # Loss final do último treinamento (−1 se não disponível)
    last_train_loss: float = -1.0

    # True se um ciclo está em andamento
    running: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FinetuneState":
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


# ---------------------------------------------------------------------------
# Persistência do estado
# ---------------------------------------------------------------------------

def _state_path(sync_root: str) -> Path:
    return Path(sync_root) / "logos" / _STATE_FILE


def _lock_path(sync_root: str) -> Path:
    return Path(sync_root) / "logos" / _LOCK_FILE


def read_state(sync_root: str = "") -> FinetuneState:
    """Lê finetune_state.json. Retorna estado vazio se ausente ou corrompido."""
    if not sync_root:
        root = ec.get_sync_root()
        sync_root = str(root) if root else ""
    if not sync_root:
        return FinetuneState()
    p = _state_path(sync_root)
    if not p.exists():
        return FinetuneState()
    try:
        return FinetuneState.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return FinetuneState()


def _write_state(state: FinetuneState, sync_root: str) -> None:
    """Persiste o estado de forma atômica."""
    p = _state_path(sync_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _update_state(sync_root: str, **kwargs) -> FinetuneState:
    """Lê, aplica kwargs e persiste. Retorna o estado atualizado."""
    state = read_state(sync_root)
    for k, v in kwargs.items():
        if hasattr(state, k):
            setattr(state, k, v)
    _write_state(state, sync_root)
    return state


# ---------------------------------------------------------------------------
# Contagem de chunks no ChromaDB
# ---------------------------------------------------------------------------

def _count_chroma_chunks(chroma_dir: str) -> int:
    """Conta o total de chunks em todas as coleções do ChromaDB da Mnemosyne.

    Retorna 0 se chromadb não estiver instalado ou o diretório não existir.
    """
    try:
        import chromadb  # noqa: PLC0415
    except ImportError:
        log.debug("chromadb não instalado — contagem de chunks = 0")
        return 0
    p = Path(chroma_dir)
    if not p.exists():
        return 0
    try:
        client = chromadb.PersistentClient(path=str(p))
        return sum(
            client.get_collection(c.name).count()
            for c in client.list_collections()
        )
    except Exception as exc:
        log.debug("Erro ao contar chunks: %s", exc)
        return 0


def _get_chroma_dir() -> str:
    """Resolve chroma_dir via ecosystem_client."""
    root = ec.get_sync_root()
    if root is None:
        return ""
    paths = ec.derive_paths(str(root))
    return paths.get("mnemosyne", {}).get("chroma_dir", "")


# ---------------------------------------------------------------------------
# Lock file — previne execuções simultâneas
# ---------------------------------------------------------------------------

def _acquire_lock(sync_root: str) -> bool:
    """Tenta adquirir o lock file. Retorna True se bem-sucedido."""
    lp = _lock_path(sync_root)
    lp.parent.mkdir(parents=True, exist_ok=True)
    try:
        # O_CREAT | O_EXCL é atômico — falha se já existir
        fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _release_lock(sync_root: str) -> None:
    """Remove o lock file."""
    lp = _lock_path(sync_root)
    try:
        lp.unlink()
    except OSError:
        pass


def is_running(sync_root: str = "") -> bool:
    """True se o lock file existe (ciclo em andamento)."""
    if not sync_root:
        root = ec.get_sync_root()
        sync_root = str(root) if root else ""
    if not sync_root:
        return False
    return _lock_path(sync_root).exists()


# ---------------------------------------------------------------------------
# Trigger logic
# ---------------------------------------------------------------------------

def should_auto_trigger(sync_root: str = "") -> bool:
    """Retorna True se o corpus cresceu >20% desde o último ciclo.

    Condições adicionais: não está rodando, chroma_dir configurado.
    """
    if not sync_root:
        root = ec.get_sync_root()
        sync_root = str(root) if root else ""
    if not sync_root:
        return False
    if is_running(sync_root):
        return False
    state = read_state(sync_root)
    last = state.corpus_chunks_at_last_train
    if last == 0:
        # Nunca treinou — trigger se houver qualquer dado
        chroma_dir = _get_chroma_dir()
        return _count_chroma_chunks(chroma_dir) > 0
    chroma_dir = _get_chroma_dir()
    current = _count_chroma_chunks(chroma_dir)
    growth = (current - last) / last
    log.debug(
        "Crescimento do corpus: %.1f%% (%d → %d chunks)",
        growth * 100, last, current,
    )
    return growth > _AUTO_TRIGGER_GROWTH


# ---------------------------------------------------------------------------
# Ciclo completo
# ---------------------------------------------------------------------------

def _run_cycle(sync_root: str) -> None:
    """Executa o pipeline completo em background (chamado em thread separada).

    Não levanta exceção — falhas são logadas e persistidas no estado.
    """
    from logos.training_data_generator import generate, GeneratorConfig  # noqa: PLC0415
    from logos.qlora_trainer import train, TrainerConfig  # noqa: PLC0415
    from logos.gguf_converter import convert_and_register, ConverterConfig  # noqa: PLC0415

    def step(name: str) -> None:
        _update_state(sync_root, current_step=name)
        log.info("Ciclo fine-tuning: etapa '%s'", name)

    try:
        step("gerando_dados")
        gen_cfg = GeneratorConfig()
        gen_result = generate(gen_cfg)
        _update_state(sync_root, examples_generated=gen_result.pairs_generated + gen_result.anchors_added)

        step("treinando")
        train_cfg = TrainerConfig()
        train_result = train(train_cfg)
        loss = float(train_result.steps_completed)  # steps como proxy — loss real via callback futuro

        step("convertendo")
        conv_cfg = ConverterConfig(checkpoint_dir=train_result.checkpoint_dir)
        conv_result = convert_and_register(conv_cfg)

        step("concluido")
        chroma_dir = _get_chroma_dir()
        current_chunks = _count_chroma_chunks(chroma_dir)
        _update_state(
            sync_root,
            current_step="",
            running=False,
            last_cycle_at=datetime.now(timezone.utc).isoformat(),
            current_model=conv_result.model_registry_name,
            prev_model=conv_result.prev_model_name,
            corpus_chunks_at_last_train=current_chunks,
            last_train_loss=loss,
        )
        log.info("Ciclo de fine-tuning concluído: %s", conv_result.model_registry_name)

    except Exception as exc:
        log.error("Ciclo de fine-tuning falhou na etapa '%s': %s", read_state(sync_root).current_step, exc)
        _update_state(sync_root, current_step=f"erro: {exc}", running=False)
    finally:
        _release_lock(sync_root)


def trigger_manual(sync_root: str = "") -> bool:
    """Dispara o ciclo de fine-tuning em background thread.

    Retorna True se o ciclo foi iniciado.
    Retorna False se já estiver em andamento.
    Levanta RuntimeError se sync_root não configurado.
    """
    if not sync_root:
        root = ec.get_sync_root()
        sync_root = str(root) if root else ""
    if not sync_root:
        raise RuntimeError(
            "sync_root não configurado em ecosystem.json — configure via HUB"
        )

    if not _acquire_lock(sync_root):
        log.warning("Ciclo já em andamento — ignorando disparo")
        return False

    _update_state(sync_root, running=True, current_step="iniciando")
    log.info("Iniciando ciclo de fine-tuning (sync_root=%s)", sync_root)

    t = threading.Thread(target=_run_cycle, args=(sync_root,), daemon=True, name="finetune-cycle")
    t.start()
    return True


def configure_logging(log_dir: "Path | None" = None) -> None:
    """Configura logging para este módulo (chamar no entry point do processo pai).

    Escreve em {log_dir}/logos.log para que o HUB possa ler via read_app_log('logos', n).
    """
    from ecosystem_logging import setup_ecosystem_logger  # noqa: PLC0415
    resolved = log_dir or _default_logos_log_dir()
    setup_ecosystem_logger("logos", resolved)


def _default_logos_log_dir() -> Path:
    """Resolve o diretório de logs do LOGOS a partir do sync_root."""
    root = ec.get_sync_root()
    if root:
        return Path(str(root)) / "logos"
    from ecosystem_logging import default_log_dir  # noqa: PLC0415
    return default_log_dir()


# ---------------------------------------------------------------------------
# Entry point CLI — invocado pelo HUB via subprocess
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys as _sys
    # Configura logging em arquivo ({sync_root}/logos/logos.log) para o HUB ler
    configure_logging()
    # Fallback stderr para qualquer mensagem antes do handler de arquivo estar ativo
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=_sys.stderr,
    )
    # Suporta: python -m logos.finetune_scheduler [--trigger | --check]
    args = _sys.argv[1:]
    if "--trigger" in args or not args:
        started = trigger_manual()
        if started:
            log.info("Ciclo iniciado — aguardando conclusão…")
            # Manter o processo vivo enquanto o ciclo roda (thread daemon)
            while is_running():
                time.sleep(5)
            log.info("Ciclo concluído.")
            _sys.exit(0)
        else:
            log.warning("Ciclo já em andamento.")
            _sys.exit(1)
    elif "--check" in args:
        result = should_auto_trigger()
        print("true" if result else "false")
        _sys.exit(0)
    else:
        print(f"Uso: python -m logos.finetune_scheduler [--trigger | --check]", file=_sys.stderr)
        _sys.exit(2)
