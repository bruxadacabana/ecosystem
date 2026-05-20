"""
AKASHA — Session Insight: observação espontânea durante pesquisa.

Monitora queries da sessão ativa. Quando ≥ SESSION_INSIGHT_MIN_QUERIES queries
temáticas forem acumuladas, agenda geração de um comentário pessoal em P3
(background, não-bloqueante). O resultado fica disponível via get_current()
para polling pelo frontend a cada ~10 s.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

log = logging.getLogger("akasha.session_insight")

SESSION_INSIGHT_MIN_QUERIES: int   = 4
_INSIGHT_COOLDOWN_S:         float = 180.0   # 3 min entre insights na mesma sessão
_INSIGHT_MAX_AGE_S:          float = 1800.0  # insight expira após 30 min
_GENERATE_TIMEOUT:           float = 25.0

def _get_ollama_base() -> str:
    try:
        from ecosystem_client import get_ollama_url as _get_url
        return _get_url()
    except Exception:
        return "http://localhost:11434"


def _get_model() -> str:
    try:
        from ecosystem_client import get_active_profile as _get_profile
        p = _get_profile()
        return ((p or {}).get("models", {}) or {}).get("llm_query", "") if p else ""
    except Exception:
        return ""

# {session_id: {"text": str, "memory_id": int | None, "generated_at": float}}
_current:  dict[str, dict[str, Any]] = {}
# timestamp da última geração iniciada por sessão (para cooldown)
_last_gen: dict[str, float]           = {}

# Entrada de personal_memory atualmente exibida no overlay (global — um overlay por vez)
_pm_current: dict[str, Any] | None = None


def get_pm_current() -> dict[str, Any] | None:
    """Retorna a entrada de personal_memory exibida no overlay, ou None."""
    return _pm_current


def set_pm_current(entry: dict[str, Any] | None) -> None:
    """Define (ou limpa) a entrada de personal_memory do overlay."""
    global _pm_current
    _pm_current = entry


def maybe_schedule(
    session_id: str,
    queries:    list[str],
    snippets:   list[str],
) -> None:
    """Agenda geração de insight se condições forem satisfeitas. Fire-and-forget."""
    if len(queries) < SESSION_INSIGHT_MIN_QUERIES:
        return
    if not _get_model():
        return
    now = time.time()
    if now - _last_gen.get(session_id, 0) < _INSIGHT_COOLDOWN_S:
        return
    _last_gen[session_id] = now
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_generate(session_id, queries, snippets))
    except RuntimeError:
        pass


def get_current(session_id: str) -> dict[str, Any] | None:
    """Retorna {"text": str, "memory_id": int | None} ou None se ausente/expirado."""
    entry = _current.get(session_id)
    if not entry:
        return None
    if time.time() - entry["generated_at"] > _INSIGHT_MAX_AGE_S:
        _current.pop(session_id, None)
        return None
    return {"text": entry["text"], "memory_id": entry.get("memory_id")}


def dismiss(session_id: str) -> None:
    """Descarta insight atual — session_insight ou entrada de personal_memory."""
    global _pm_current
    if session_id in _current:
        _current.pop(session_id, None)
    else:
        # Descartando entrada de personal_memory do overlay
        _pm_current = None


async def _generate(session_id: str, queries: list[str], snippets: list[str]) -> None:
    """Gera insight em background (P3) e armazena para polling."""
    import config as _config

    model = _get_model()
    if not model:
        return

    log.info("session_insight: gerando insight (sessão %.8s…, %d queries)", session_id, len(queries))

    personality  = _config.PERSONALITY_PROMPT
    queries_text = "\n".join(f"- {q}" for q in queries[-6:])
    snippets_text = "\n".join(s for s in snippets[:4] if s)

    prompt = (
        f"{personality}\n\n"
        f"Contexto: a usuária pesquisou:\n{queries_text}\n"
        + (f"\nTrechos encontrados:\n{snippets_text}\n\n" if snippets_text else "\n")
        + "Escreva UMA frase — apenas uma — na sua voz, sobre o que você nota "
        "nessa pesquisa. Não explique o tema. Não faça conexões com outros assuntos. "
        "Não apresente você mesma. Apenas a observação, direta."
    )

    try:
        async with httpx.AsyncClient(timeout=_GENERATE_TIMEOUT) as client:
            resp = await client.post(
                f"{_get_ollama_base()}/api/generate",
                json={
                    "model":  model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 60, "temperature": 0.65},
                },
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
    except Exception as exc:
        log.debug("session_insight: Ollama falhou: %s", exc)
        return

    if not text or len(text) < 10:
        return

    # Salva na memória pessoal para que a usuária possa dar feedback
    memory_id: int | None = None
    try:
        from services.personal_memory import save_memory as _save_memory
        memory_id = await _save_memory("observation", text, tags=["session_insight"])
    except Exception as exc:
        log.debug("session_insight: falha ao salvar em personal_memory: %s", exc)

    _current[session_id] = {
        "text":         text,
        "memory_id":    memory_id,
        "generated_at": time.time(),
    }
    log.info("session_insight: insight salvo (memória #%s) para sessão %.8s…", memory_id, session_id)
