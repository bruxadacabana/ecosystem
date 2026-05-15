"""
AKASHA — Query Understanding e gerenciamento de ciclo de vida do modelo LLM.

Responsabilidades atuais:
  - pin_model() / release_model(): mantém o modelo em VRAM durante uma sessão
    de pesquisa ativa, eliminando o cold-start de 2–5 s por query.
  - Temporizador de inatividade: libera VRAM automaticamente após SESSION_IDLE_S
    segundos sem atividade.

Integração:
  - routers/search.py chama pin_model() no início de cada busca que usa LLM.
  - release_model() é chamado automaticamente pelo timer ou por endpoint explícito.
  - Os módulos synthesis.py e classificador (a implementar) usam este módulo como
    ponto central de configuração do modelo LLM.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger("akasha.query_understanding")

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL:   str = "http://localhost:11434"
SESSION_IDLE_S:    int = 1800   # 30 min sem atividade → libera VRAM

# Modelo padrão para síntese e classificação. Vazio = Ollama usa o que estiver
# carregado. Será sobrescrito por ecosystem.json quando o LOGOS for consultado.
DEFAULT_LLM_MODEL: str = ""

# ---------------------------------------------------------------------------
# Estado interno
# ---------------------------------------------------------------------------

_pinned_model:  str | None        = None
_idle_task:     asyncio.Task | None = None


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

async def pin_model(model: str = "") -> None:
    """Mantém o modelo em VRAM com keep_alive=-1.

    Idempotente: chamadas repetidas com o mesmo modelo apenas reiniciam o
    timer de inatividade. Se o modelo mudar, o anterior é liberado primeiro.

    O Ollama interpreta keep_alive=-1 como "nunca descarregar" — o modelo
    fica residente em VRAM até que release_model() seja chamado ou o processo
    do Ollama reinicie.
    """
    global _pinned_model, _idle_task

    model = model or DEFAULT_LLM_MODEL
    if not model:
        return

    if _pinned_model and _pinned_model != model:
        await release_model(_pinned_model)

    if _pinned_model != model:
        await _set_keep_alive(model, keep_alive=-1)
        _pinned_model = model
        log.debug("Modelo '%s' fixado em VRAM (keep_alive=-1).", model)

    _reset_idle_timer(model)


async def release_model(model: str = "") -> None:
    """Libera o modelo da VRAM com keep_alive=0."""
    global _pinned_model, _idle_task

    model = model or _pinned_model or DEFAULT_LLM_MODEL
    if not model:
        return

    if _idle_task and not _idle_task.done():
        _idle_task.cancel()
        _idle_task = None

    await _set_keep_alive(model, keep_alive=0)
    _pinned_model = None
    log.debug("Modelo '%s' liberado da VRAM (keep_alive=0).", model)


def get_pinned_model() -> str | None:
    """Retorna o modelo atualmente fixado em VRAM, ou None."""
    return _pinned_model


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

async def _set_keep_alive(model: str, keep_alive: int) -> None:
    """Envia request ao Ollama para ajustar keep_alive do modelo."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": model, "prompt": "", "keep_alive": keep_alive},
            )
    except Exception as exc:
        log.debug("keep_alive(%d) para '%s' falhou: %s", keep_alive, model, exc)


def _reset_idle_timer(model: str) -> None:
    """Cancela o timer de inatividade existente e inicia um novo."""
    global _idle_task

    if _idle_task and not _idle_task.done():
        _idle_task.cancel()

    try:
        loop = asyncio.get_running_loop()
        _idle_task = loop.create_task(_idle_release(model))
    except RuntimeError:
        pass  # sem loop ativo — ignorar (testes síncronos)


async def _idle_release(model: str) -> None:
    """Libera o modelo após SESSION_IDLE_S de inatividade."""
    try:
        await asyncio.sleep(SESSION_IDLE_S)
        log.info(
            "Inatividade de %d min — liberando modelo '%s' da VRAM.",
            SESSION_IDLE_S // 60, model,
        )
        await release_model(model)
    except asyncio.CancelledError:
        pass  # timer reiniciado por nova atividade — normal
