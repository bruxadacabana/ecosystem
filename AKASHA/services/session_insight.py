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

try:
    from ecosystem_client import get_ollama_url as _get_ollama_url, get_active_profile as _get_profile
    _OLLAMA_BASE: str = _get_ollama_url()
    _p = _get_profile()
    _DEFAULT_MODEL: str = (_p or {}).get("models", {}).get("llm_kosmos", "") if _p else ""
except Exception:
    _OLLAMA_BASE   = "http://localhost:11434"
    _DEFAULT_MODEL = ""

# {session_id: {"text": str, "generated_at": float}}
_current:  dict[str, dict[str, Any]] = {}
# timestamp da última geração iniciada por sessão (para cooldown)
_last_gen: dict[str, float]           = {}


def maybe_schedule(
    session_id: str,
    queries:    list[str],
    snippets:   list[str],
) -> None:
    """Agenda geração de insight se condições forem satisfeitas. Fire-and-forget."""
    if len(queries) < SESSION_INSIGHT_MIN_QUERIES:
        return
    if not _DEFAULT_MODEL:
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


def get_current(session_id: str) -> str | None:
    """Retorna texto do insight atual ou None se ausente/expirado."""
    entry = _current.get(session_id)
    if not entry:
        return None
    if time.time() - entry["generated_at"] > _INSIGHT_MAX_AGE_S:
        _current.pop(session_id, None)
        return None
    return entry["text"]


def dismiss(session_id: str) -> None:
    """Descarta insight atual para esta sessão."""
    _current.pop(session_id, None)


async def _generate(session_id: str, queries: list[str], snippets: list[str]) -> None:
    """Gera insight em background (P3) e armazena para polling."""
    import config as _config

    model = _DEFAULT_MODEL
    if not model:
        return

    personality  = _config.PERSONALITY_PROMPT
    queries_text = "\n".join(f"- {q}" for q in queries[-6:])
    snippets_text = "\n".join(s for s in snippets[:4] if s)

    prompt = (
        f"{personality}\n\n"
        f"A usuária está pesquisando sobre:\n{queries_text}\n"
        + (f"\nAlguns trechos encontrados:\n{snippets_text}\n" if snippets_text else "")
        + "\nO que você comentaria sobre o que ela está explorando? "
        "Responda em 1-2 frases na sua voz, sem explicar o conteúdo — "
        "apenas seu comentário pessoal."
    )

    try:
        async with httpx.AsyncClient(timeout=_GENERATE_TIMEOUT) as client:
            resp = await client.post(
                f"{_OLLAMA_BASE}/api/generate",
                json={
                    "model":   model,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {"num_predict": 100, "temperature": 0.75},
                },
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
    except Exception as exc:
        log.debug("session_insight: Ollama falhou: %s", exc)
        return

    if not text or len(text) < 15:
        return

    _current[session_id] = {"text": text, "generated_at": time.time()}
    log.debug("session_insight: insight gerado para sessão %.8s…", session_id)
