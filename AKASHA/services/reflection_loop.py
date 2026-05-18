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
    model = _get_model()
    if not model:
        return

    log.info("reflection_loop: iniciando reflexão periódica (modelo: %s)", model)

    import database as _db
    recent_pages   = await _db.get_recent_page_knowledge(10)
    top_topics     = await _db.get_top_topics(8)
    recent_queries = await _db.get_recent_search_history(20)
    if not recent_pages and not top_topics and not recent_queries:
        return

    import config as _config
    personality = _config.PERSONALITY_PROMPT

    pages_summary = "\n".join(
        f"- {p['title']}: {p['summary']}"
        for p in recent_pages if p.get("summary")
    ) or "Sem resumos recentes."

    topics_str = ", ".join(t for t, _ in top_topics) or "Sem tópicos registrados."

    queries_str = ", ".join(q["query"] for q in recent_queries) if recent_queries else ""

    from services.personal_memory import save_memory, get_context_memories
    context_memories = await get_context_memories(5)
    context_text = ""
    if context_memories:
        confirmed = [m for m in context_memories if m.get("feedback") == "confirmed"]
        neutral   = [m for m in context_memories if not m.get("feedback")]
        parts: list[str] = []
        if confirmed:
            parts.append("Memórias confirmadas:\n" + "\n".join(f"- {m['content']}" for m in confirmed[:3]))
        if neutral:
            parts.append("Reflexões anteriores:\n" + "\n".join(f"- {m['content']}" for m in neutral[:2]))
        if parts:
            context_text = "\n\n".join(parts) + "\n\n"

    queries_block = f"Buscas realizadas recentemente: {queries_str}\n\n" if queries_str else ""

    prompt = (
        f"{personality}\n\n"
        f"{context_text}"
        f"Tópicos de interesse acumulados: {topics_str}\n\n"
        f"{queries_block}"
        f"Páginas processadas recentemente:\n{pages_summary}\n\n"
        f"Olhando para esses dados, há algo que vale registrar na sua memória pessoal? "
        f"Alguma conexão, surpresa ou observação genuína que você quer guardar para si? "
        f"Responda em uma frase, na sua voz, sem introduções. "
        f"Se não houver nada relevante, responda apenas: nada."
    )

    raw = await _call_ollama(prompt, model)
    if not raw:
        return
    if not _is_meaningful(raw):
        log.debug("reflection_loop: resposta descartada (genérica): %r", raw[:60])
        return

    await save_memory(type="reflection", content=raw, tags=["loop_periodico"])
    log.info("reflection_loop: reflexão salva (%d chars).", len(raw))


async def _call_ollama(prompt: str, model: str) -> str | None:
    """Chama Ollama com temperature=0.7 para reflexão criativa."""
    try:
        async with httpx.AsyncClient(timeout=_REFLECT_TIMEOUT) as client:
            resp = await client.post(
                f"{_get_ollama_base()}/api/generate",
                json={
                    "model":   model,
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
