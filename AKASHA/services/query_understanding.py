"""
AKASHA — Query Understanding e gerenciamento de ciclo de vida do modelo LLM.

Responsabilidades:
  - pin_model() / release_model(): mantém o modelo em VRAM durante uma sessão
    de pesquisa ativa, eliminando o cold-start de 2–5 s por query.
  - Temporizador de inatividade: libera VRAM automaticamente após SESSION_IDLE_S
    segundos sem atividade.
  - classify_intent(): classifica a intenção da query em fact-seeking, exploratory
    ou navigational via chamada Ollama rápida (~200ms com modelo 3B Q4).

Integração:
  - routers/search.py chama pin_model() e classify_intent() no início de cada busca.
  - release_model() é chamado automaticamente pelo timer ou por endpoint explícito.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Literal

import httpx

log = logging.getLogger("akasha.query_understanding")

# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

IntentType = Literal["fact-seeking", "exploratory", "navigational"]

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

SESSION_IDLE_S:        int   = 1800   # 30 min sem atividade → libera VRAM
INTENT_CLASSIFY_MODEL: str   = ""     # sobrescrito por ecosystem.json; vazio = usa DEFAULT_LLM_MODEL
INTENT_TIMEOUT_S:      float = 5.0   # timeout da classificação; fallback para "exploratory"

# Resolvidos no startup via ecosystem_client:
#   _OLLAMA_BASE     → LOGOS (7072) se disponível, Ollama direto (11434) como fallback
#   DEFAULT_LLM_MODEL → modelo llm_kosmos do perfil ativo; "" se LOGOS não estiver rodando
try:
    from ecosystem_client import (
        get_ollama_url    as _ec_ollama_url,
        get_active_profile as _ec_profile,
    )
    _OLLAMA_BASE: str = _ec_ollama_url()
    _p = _ec_profile()
    DEFAULT_LLM_MODEL: str = (_p or {}).get("models", {}).get("llm_kosmos", "") if _p else ""
except Exception:
    _OLLAMA_BASE      = "http://localhost:11434"
    DEFAULT_LLM_MODEL = ""

OLLAMA_BASE_URL: str = _OLLAMA_BASE  # alias público (retrocompat)

# ---------------------------------------------------------------------------
# Reescrita conversacional — anáforas detectadas
# ---------------------------------------------------------------------------

_ANAPHORA_RE = re.compile(
    r"\b(isso|esse|essa|esses|essas|ele|ela|eles|elas|aquilo|aqueles|aquelas|"
    r"este|esta|estes|estas|daí|lá|ali|"
    r"this|that|it|they|them|those|these|here|there)\b",
    re.IGNORECASE,
)


def needs_rewrite(query: str) -> bool:
    """True se a query provavelmente precisa de reescrita conversacional.

    Critérios: muito curta (< 3 tokens) OU contém anáfora pt/en.
    """
    if len(query.split()) < 3:
        return True
    return bool(_ANAPHORA_RE.search(query))


async def rewrite_query(query: str, context: list[str], model: str = "") -> str:
    """Reescreve query anafórica ou curta como busca autônoma usando contexto da sessão.

    Retorna a query reescrita ou "" se não aplicável / falhou.
    Nunca levanta exceção — falha silenciosa usa query original.
    """
    model = model or INTENT_CLASSIFY_MODEL or DEFAULT_LLM_MODEL
    if not model or not context:
        return ""

    context_str = " → ".join(context[-3:])
    prompt = (
        f'Reescreva como busca independente e específica: "{query}"\n'
        f"Contexto recente: {context_str}\n"
        "Responda apenas com a busca reescrita. Uma linha, sem explicação."
    )
    try:
        async with httpx.AsyncClient(timeout=INTENT_TIMEOUT_S) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 30, "temperature": 0.1},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip().strip("\"'")
            if raw and len(raw) <= 200 and raw.lower() != query.lower():
                return raw
    except Exception as exc:
        log.debug("rewrite_query falhou (%s) — usando query original.", exc)
    return ""

# ---------------------------------------------------------------------------
# Clarificação seletiva
# ---------------------------------------------------------------------------

async def score_ambiguity(query: str, model: str = "") -> tuple[int, str]:
    """Avalia ambiguidade da query e gera pergunta de clarificação quando necessário.

    Score 1-4 (1=clara, 4=muito ambígua). Pergunta exibida apenas quando score ≥ 3.
    A pergunta deve ser específica sobre o atributo ambíguo — nunca genérica.
    Retorna (1, "") em qualquer falha. Nunca levanta exceção.
    """
    model = model or INTENT_CLASSIFY_MODEL or DEFAULT_LLM_MODEL
    if not model:
        return 1, ""

    prompt = (
        f'Query de busca: "{query}"\n\n'
        "Avalie a ambiguidade de 1 a 4:\n"
        "1 = clara (ex: 'capital do Brasil')\n"
        "2 = levemente ambígua\n"
        "3 = ambígua (ex: 'Java' — linguagem ou país?)\n"
        "4 = muito ambígua (ex: 'como funciona')\n\n"
        "Se score ≥ 3, escreva UMA pergunta específica sobre o atributo ambíguo.\n"
        "Formato obrigatório:\n"
        "SCORE: N\n"
        "PERGUNTA: texto (vazio se score < 3)"
    )
    try:
        async with httpx.AsyncClient(timeout=INTENT_TIMEOUT_S) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 60, "temperature": 0},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()

        score = 1
        question = ""
        for line in raw.splitlines():
            u = line.upper()
            if u.startswith("SCORE:"):
                try:
                    score = max(1, min(4, int(line.split(":", 1)[1].strip())))
                except ValueError:
                    pass
            elif u.startswith("PERGUNTA:"):
                question = line.split(":", 1)[1].strip()

        return score, question if score >= 3 and question else ""
    except Exception as exc:
        log.debug("score_ambiguity falhou (%s).", exc)
        return 1, ""

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


async def classify_intent(query: str, model: str = "") -> IntentType:
    """Classifica a intenção da query via Ollama em ~200ms.

    Retorna um de três tipos:
      - "navigational" — usuária quer um URL/página específica (ex: "github anthropic")
      - "fact-seeking" — usuária quer um dado factual pontual (ex: "capital do Brasil")
      - "exploratory" — usuária quer pesquisar um tema amplo (ex: "machine learning intro")

    O classificador age APENAS na camada de roteamento de busca — não sintetiza
    respostas nem interpreta resultados. Se Ollama não responder em INTENT_TIMEOUT_S
    segundos, retorna "exploratory" (comportamento padrão da busca) sem bloquear.

    Raises: nunca — todos os erros são absorvidos e retornam "exploratory".
    """
    model = model or INTENT_CLASSIFY_MODEL or DEFAULT_LLM_MODEL
    if not model:
        return "exploratory"

    prompt = (
        "Classify this search query into exactly one category:\n"
        "- navigational: looking for a specific website, URL, or known page\n"
        "- fact-seeking: looking for a specific fact, number, or quick answer\n"
        "- exploratory: researching a broad topic, concept, or idea\n\n"
        f'Query: "{query}"\n\n'
        "Answer with one word only: navigational, fact-seeking, or exploratory."
    )

    try:
        async with httpx.AsyncClient(timeout=INTENT_TIMEOUT_S) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 8, "temperature": 0},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip().lower()
    except (httpx.HTTPError, httpx.TimeoutException, KeyError, ValueError) as exc:
        log.debug("classify_intent falhou (%s) — usando 'exploratory'.", exc)
        return "exploratory"

    if "navigational" in raw:
        return "navigational"
    if "fact" in raw:
        return "fact-seeking"
    if "exploratory" in raw:
        return "exploratory"

    log.debug("classify_intent resposta inesperada %r — usando 'exploratory'.", raw)
    return "exploratory"


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
