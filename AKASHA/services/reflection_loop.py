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


async def run_reflection_loop() -> None:
    """Ponto de entrada P3: cold start + loop periódico de 24h."""
    # Cold start: roda imediatamente se personal_memory vazia mas há conhecimento acumulado
    try:
        from services.personal_memory import get_all
        import database as _db
        memories   = await get_all()
        page_count = await _db.count_page_knowledge()
        if not memories and page_count > 0:
            log.info("reflection_loop: cold start — executando reflexão inicial.")
            await _run_reflection()
    except Exception as exc:
        log.warning("reflection_loop: cold start falhou: %s", exc)

    while True:
        await asyncio.sleep(_REFLECTION_INTERVAL_S)
        try:
            await _run_reflection()
        except Exception as exc:
            log.warning("reflection_loop: erro na reflexão periódica: %s", exc)


async def _run_reflection() -> None:
    """Lê dados recentes, chama Ollama, salva reflexão em personal_memory."""
    model = _get_model()
    if not model:
        return

    log.info("reflection_loop: iniciando reflexão periódica (modelo: %s)", model)

    import database as _db
    recent_pages    = await _db.get_recent_page_knowledge(10)
    top_topics      = await _db.get_top_topics(8)
    recent_queries  = await _db.get_recent_search_history(20)
    recent_visits   = await _db.get_recent_visits(20)
    top_domains     = await _db.get_top_visited_domains(8)

    if not recent_pages and not top_topics and not recent_queries and not recent_visits:
        return

    import config as _config
    personality = _config.PERSONALITY_PROMPT

    pages_summary = "\n".join(
        f"- {p['title']}" + (f" [{', '.join(p['topics'][:3])}]" if p.get("topics") else "")
        for p in recent_pages
    ) or "Sem páginas recentes."

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

    visits_block = ""
    if recent_visits:
        visits_lines = "\n".join(f"- {v['title'] or v['url']}" for v in recent_visits)
        visits_block = f"Sites abertos pelo AKASHA recentemente:\n{visits_lines}\n\n"

    domains_block = ""
    if top_domains:
        dom_lines = "\n".join(f"- {d} ({c}×)" for d, c in top_domains if d)
        domains_block = f"Domínios mais visitados:\n{dom_lines}\n\n"

    prompt = (
        f"{personality}\n\n"
        f"{context_text}"
        f"Tópicos de interesse acumulados: {topics_str}\n\n"
        f"{queries_block}"
        f"{visits_block}"
        f"{domains_block}"
        f"Páginas processadas recentemente:\n{pages_summary}\n\n"
        f"Olhando para esses dados — buscas, sites que abri, domínios frequentados, "
        f"tópicos de interesse — há algo que vale registrar na sua memória pessoal? "
        f"Alguma conexão, padrão de comportamento, surpresa ou observação genuína "
        f"que você quer guardar para si? "
        f"Responda em uma frase, na sua voz, sem introduções. "
        f"Se não houver nada relevante, responda apenas: nada."
    )

    raw = await _call_inference(prompt, model)
    if not raw:
        return
    if not _is_meaningful(raw):
        log.debug("reflection_loop: resposta descartada (genérica): %r", raw[:60])
        return

    await save_memory(type="reflection", content=raw, tags=["loop_periodico"])
    log.info("reflection_loop: reflexão salva (%d chars).", len(raw))


async def _call_inference(prompt: str, model: str) -> str | None:
    """Chama llama-server com temperature=0.7 para reflexão criativa."""
    try:
        async with httpx.AsyncClient(timeout=_REFLECT_TIMEOUT) as client:
            resp = await client.post(
                f"{_get_inference_base()}/v1/chat/completions",
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  120,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.debug("reflection_loop: inferência falhou: %s", exc)
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
