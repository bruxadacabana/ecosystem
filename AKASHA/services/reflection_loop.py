"""
AKASHA — Loop de reflexão periódica
Gera reflexões pessoais sobre o conhecimento acumulado.
Roda como P3 — fire-and-forget, não bloqueia operações críticas.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger("akasha.reflection_loop")

_REFLECTION_INTERVAL_S: float = 86400.0  # 24h entre reflexões periódicas
_REFLECT_TIMEOUT: float       = 30.0     # timeout por chamada Ollama
_MIN_RESPONSE_LEN: int        = 20       # resposta abaixo disso é descartada

_GENERIC_PREFIXES = (
    "não há", "não tenho", "como ia", "como um assistente",
    "preciso de mais", "não posso", "desculpe", "lamento",
    "não é possível",
)

try:
    from ecosystem_client import get_ollama_url as _get_ollama_url, get_active_profile as _get_profile
    _OLLAMA_BASE: str = _get_ollama_url()
    _p = _get_profile()
    _DEFAULT_MODEL: str = (_p or {}).get("models", {}).get("llm_kosmos", "") if _p else ""
except Exception:
    _OLLAMA_BASE   = "http://localhost:11434"
    _DEFAULT_MODEL = ""


async def run_reflection_loop() -> None:
    """Ponto de entrada P3: cold start + loop periódico de 24h."""
    # Cold start: roda imediatamente se personal_memory vazia mas há conhecimento acumulado
    try:
        from services.personal_memory import get_all
        import database as _db
        memories   = get_all()
        page_count = await _db.count_page_knowledge()
        if not memories and page_count > 0:
            log.info("reflection_loop: cold start — executando reflexão inicial.")
            await _run_reflection()
    except Exception as exc:
        log.debug("reflection_loop: cold start falhou: %s", exc)

    while True:
        await asyncio.sleep(_REFLECTION_INTERVAL_S)
        try:
            await _run_reflection()
        except Exception as exc:
            log.debug("reflection_loop: erro na reflexão periódica: %s", exc)


async def _run_reflection() -> None:
    """Lê dados recentes, chama Ollama, salva reflexão em personal_memory."""
    if not _DEFAULT_MODEL:
        return

    import database as _db
    recent_pages = await _db.get_recent_page_knowledge(10)
    top_topics   = await _db.get_top_topics(8)
    if not recent_pages and not top_topics:
        return

    import config as _config
    personality = _config.PERSONALITY_PROMPT

    pages_summary = "\n".join(
        f"- {p['title']}: {p['summary']}"
        for p in recent_pages if p.get("summary")
    ) or "Sem resumos recentes."

    topics_str = ", ".join(t for t, _ in top_topics) or "Sem tópicos registrados."

    prompt = (
        f"{personality}\n\n"
        f"Tópicos de interesse acumulados: {topics_str}\n\n"
        f"Páginas processadas recentemente:\n{pages_summary}\n\n"
        f"Olhando para esses dados, há algo que vale registrar na sua memória pessoal? "
        f"Alguma conexão, surpresa ou observação genuína que você quer guardar para si? "
        f"Responda em uma frase, na sua voz, sem introduções. "
        f"Se não houver nada relevante, responda apenas: nada."
    )

    raw = await _call_ollama(prompt)
    if not raw:
        return
    if not _is_meaningful(raw):
        log.debug("reflection_loop: resposta descartada (genérica): %r", raw[:60])
        return

    from services.personal_memory import save_memory
    save_memory(type="reflection", content=raw, tags=["loop_periodico"])
    log.info("reflection_loop: reflexão salva (%d chars).", len(raw))


async def _call_ollama(prompt: str) -> str | None:
    """Chama Ollama com temperature=0.7 para reflexão criativa."""
    try:
        async with httpx.AsyncClient(timeout=_REFLECT_TIMEOUT) as client:
            resp = await client.post(
                f"{_OLLAMA_BASE}/api/generate",
                json={
                    "model":   _DEFAULT_MODEL,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {"num_predict": 120, "temperature": 0.7},
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
    except Exception as exc:
        log.debug("reflection_loop: Ollama falhou: %s", exc)
        return None


def _is_meaningful(text: str) -> bool:
    """Descarta respostas genéricas, vazias ou muito curtas."""
    t = text.strip().lower()
    if len(t) < _MIN_RESPONSE_LEN:
        return False
    if t in {"nada.", "nada", "—", "-"}:
        return False
    for prefix in _GENERIC_PREFIXES:
        if t.startswith(prefix):
            return False
    return True
