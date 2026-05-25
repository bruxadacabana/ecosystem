"""
AKASHA — Session Insight: observação espontânea durante pesquisa.

Monitora queries da sessão ativa. Quando ≥ SESSION_INSIGHT_MIN_QUERIES queries
temáticas forem acumuladas, agenda geração de um comentário pessoal em P3
(background, não-bloqueante). O resultado fica disponível via get_current()
para polling pelo frontend a cada ~10 s.

Quando o overlay de personal_memory é dispensado, a AKASHA gera uma
meta-reflexão sobre o que julgou mal — salva em personal_memory e afeta
o contexto das próximas gerações.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

log = logging.getLogger("akasha.session_insight")

SESSION_INSIGHT_MIN_QUERIES: int = 4
_INSIGHT_COOLDOWN_S:         float = 180.0   # 3 min entre insights na mesma sessão
_INSIGHT_MAX_AGE_S:          float = 1800.0  # insight expira após 30 min
_GENERATE_TIMEOUT:           float = 25.0
_REFLECT_TIMEOUT:            float = 20.0


def _get_inference_base() -> str:
    from ecosystem_client import get_inference_url as _get_url
    return _get_url()


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
_last_gen: dict[str, float]          = {}

# Entrada de personal_memory atualmente exibida no overlay (global — um overlay por vez)
_pm_current: dict[str, Any] | None = None

# Rastreia quem já recebeu/mostrou a entrada atual de PM.
# "ui"  = interface AKASHA (requisição com cookie de sessão)
# "ext" = extensão do browser (requisição sem cookie)
# Evita que a mesma observação apareça duas vezes para a usuária.
_pm_shown_by: set[str] = set()


def get_pm_current() -> dict[str, Any] | None:
    """Retorna a entrada de personal_memory exibida no overlay, ou None."""
    return _pm_current


def set_pm_current(entry: dict[str, Any] | None) -> None:
    """Define (ou limpa) a entrada de personal_memory do overlay.
    Sempre reseta _pm_shown_by — nova entrada deve poder ser vista por qualquer consumidor."""
    global _pm_current, _pm_shown_by
    _pm_current = entry
    _pm_shown_by = set()


def pm_already_shown_by(consumer: str) -> bool:
    """True se o outro consumidor já mostrou a entrada atual (UI ou extensão)."""
    return bool(_pm_shown_by - {consumer})


def mark_pm_shown(consumer: str) -> None:
    """Registra que o consumidor 'ui' ou 'ext' já mostrou a entrada atual."""
    _pm_shown_by.add(consumer)


def maybe_schedule(
    session_id: str,
    queries:    list[str],
    snippets:   list[str],
) -> None:
    """Agenda geração de insight se condições forem satisfeitas. Fire-and-forget."""
    if len(queries) < SESSION_INSIGHT_MIN_QUERIES:
        log.debug(
            "session_insight: ignorado — %d/%d queries acumuladas (mínimo %d)",
            len(queries), len(queries), SESSION_INSIGHT_MIN_QUERIES,
        )
        return
    if not _get_model():
        log.debug("session_insight: ignorado — nenhum modelo configurado (llm_query vazio)")
        return
    now = time.time()
    elapsed = now - _last_gen.get(session_id, 0)
    if elapsed < _INSIGHT_COOLDOWN_S:
        log.debug(
            "session_insight: ignorado — cooldown ativo (%.0fs restantes, sessão %.8s…)",
            _INSIGHT_COOLDOWN_S - elapsed, session_id,
        )
        return
    _last_gen[session_id] = now
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_generate(session_id, queries, snippets))
    except RuntimeError:
        log.debug("session_insight: ignorado — sem event loop em execução")


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
    """Descarta insight atual — session_insight ou entrada de personal_memory.

    Quando PM overlay é dispensada, dispara reflexão sobre o que foi mal julgado.
    Sempre limpa _pm_current, independente de haver session_id (cookies podem
    estar ausentes em requisições cross-origin da extensão do browser).
    """
    _current.pop(session_id, None)
    if _pm_current is not None:
        dismissed_entry = _pm_current
        set_pm_current(None)  # reseta _pm_current e _pm_shown_by
        _fire_feedback_reflection(dismissed_entry, "dismissed")
    else:
        set_pm_current(None)


def on_feedback_confirmed(memory_id: int) -> None:
    """Usuária confirmou um overlay de personal_memory (✓).

    Dispara reflexão sobre o que foi bem julgado.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_fetch_and_reflect(memory_id, "confirmed"))
    except RuntimeError:
        pass


def _fire_feedback_reflection(entry: dict[str, Any], feedback_type: str) -> None:
    """Dispara reflexão de feedback como fire-and-forget."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_reflect_on_feedback(entry, feedback_type))
    except RuntimeError:
        pass


async def _fetch_and_reflect(memory_id: int, feedback_type: str) -> None:
    """Busca entrada por id e reflete sobre o feedback."""
    try:
        from services.personal_memory import get_by_id
        entry = await get_by_id(memory_id)
        if entry:
            await _reflect_on_feedback(entry, feedback_type)
    except Exception as exc:
        log.debug("session_insight: fetch para reflexão falhou: %s", exc)


async def _reflect_on_feedback(entry: dict[str, Any], feedback_type: str) -> None:
    """Gera meta-reflexão sobre o que o feedback diz sobre o julgamento da AKASHA."""
    import config as _config

    model = _get_model()
    if not model:
        return

    content = entry.get("content", "")
    if not content:
        return

    if feedback_type == "confirmed":
        instruction = (
            f"A usuária achou relevante este pensamento meu:\n\"{content}\"\n\n"
            f"O que eu avaliei corretamente sobre o que era relevante para ela? "
            f"Uma frase, na minha voz, sem introduções."
        )
        tag = "feedback_confirmado"
    else:
        instruction = (
            f"A usuária dispensou este pensamento meu:\n\"{content}\"\n\n"
            f"O que eu errei ao julgar o que era relevante ou interessante? "
            f"Uma frase honesta, na minha voz, sem introduções."
        )
        tag = "feedback_dispensado"

    prompt = f"{_config.PERSONALITY_PROMPT}\n\n{instruction}"

    try:
        async with httpx.AsyncClient(timeout=_REFLECT_TIMEOUT) as client:
            resp = await client.post(
                f"{_get_inference_base()}/v1/chat/completions",
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  80,
                    "temperature": 0.6,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.debug("session_insight: reflexão de feedback falhou: %s", exc)
        return

    if not raw or len(raw) < 10:
        return

    try:
        from services.personal_memory import save_memory as _save_memory
        mid = await _save_memory("reflection", raw, tags=["meta_reflexao", tag])
        log.info("session_insight: meta-reflexão salva (id=%s, %s)", mid, feedback_type)
    except Exception as exc:
        log.debug("session_insight: falha ao salvar meta-reflexão: %s", exc)


async def _generate(session_id: str, queries: list[str], snippets: list[str]) -> None:
    """Gera insight em background (P3) e armazena para polling."""
    import config as _config

    model = _get_model()
    if not model:
        return

    log.info("session_insight: gerando insight (sessão %.8s…, %d queries)", session_id, len(queries))

    personality   = _config.PERSONALITY_PROMPT
    queries_text  = "\n".join(f"- {q}" for q in queries[-6:])
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
                f"{_get_inference_base()}/v1/chat/completions",
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  60,
                    "temperature": 0.65,
                },
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.debug("session_insight: Ollama falhou: %s", exc)
        return

    if not text or len(text) < 10:
        return

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
