"""
AKASHA — Loop de reflexão periódica
Gera reflexões pessoais sobre o conhecimento acumulado.
Roda como P3 — fire-and-forget, não bloqueia operações críticas.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
from collections import defaultdict
from pathlib import Path

import httpx

log = logging.getLogger("akasha.reflection_loop")

_REFLECTION_INTERVAL_S: float = 86400.0  # 24h (relógio) entre reflexões
_STARTUP_GRACE_S: float       = 300.0    # carência pós-startup (deixa crawl/backfill assentar)
_POLL_S: float                = 3600.0   # de hora em hora, checa se a reflexão venceu
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


def _state_path() -> Path:
    """Arquivo de estado local (junto ao banco) com o timestamp da última reflexão."""
    import config as _config
    return Path(_config.DB_PATH).parent / ".reflection_state.json"


def _last_reflection_at() -> float:
    try:
        return float(json.loads(_state_path().read_text(encoding="utf-8"))["last_reflection_at"])
    except Exception:
        return 0.0


def _mark_reflected() -> None:
    try:
        _state_path().write_text(
            json.dumps({"last_reflection_at": time.time()}), encoding="utf-8"
        )
    except Exception as exc:
        log.warning("reflection_loop: não foi possível persistir last_reflection_at: %s", exc)


def _reflection_due() -> bool:
    """True se passou o intervalo (relógio) desde a última reflexão registrada."""
    return (time.time() - _last_reflection_at()) >= _REFLECTION_INTERVAL_S


async def run_reflection_loop() -> None:
    """Ponto de entrada P3: agendamento ancorado no relógio.

    Não roda no instante do startup (deixa o crawl/backfill inicial assentar via
    carência); depois, em poll horário, reflete se a reflexão venceu (24h de relógio
    desde a última, persistida em arquivo de estado). A reflexão é P3 no LOGOS — sob
    carga, é atrasada, não bloqueia o backfill.
    """
    await asyncio.sleep(_STARTUP_GRACE_S)
    while True:
        try:
            if _reflection_due():
                ran = await _run_reflection()
                if ran:  # só marca quando houve dados para refletir
                    _mark_reflected()
        except Exception as exc:
            log.warning("reflection_loop: erro na reflexão periódica: %s", exc)
        await asyncio.sleep(_POLL_S)


async def _run_reflection() -> bool:
    """Lê dados recentes, chama o LLM, salva reflexão em personal_memory.

    Retorna True se havia dados e a reflexão foi tentada (independe do resultado);
    False se saiu cedo por falta de modelo ou de dados (para não "queimar" a janela).
    """
    model = _get_model()
    if not model:
        return False

    log.info("reflection_loop: iniciando reflexão periódica (modelo: %s)", model)

    import database as _db
    recent_pages    = await _db.get_recent_page_knowledge(10)
    top_topics      = await _db.get_top_topics(8)
    recent_queries  = await _db.get_recent_search_history(20)
    recent_visits   = await _db.get_recent_visits(20)
    top_domains     = await _db.get_top_visited_domains(8)
    cross_block     = _cross_device_block()  # atividade em OUTRAS máquinas (shared_history)

    if not recent_pages and not top_topics and not recent_queries and not recent_visits and not cross_block:
        return False

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
        f"{cross_block}"
        f"Páginas processadas recentemente:\n{pages_summary}\n\n"
        f"Olhando para esses dados — buscas, sites que abri, domínios frequentados, "
        f"tópicos de interesse e o que fiz em outros dispositivos — há algo que vale "
        f"registrar na sua memória pessoal? "
        f"Alguma conexão, padrão de comportamento, surpresa ou observação genuína "
        f"que você quer guardar para si? "
        f"Responda em uma frase, na sua voz, sem introduções. "
        f"Se não houver nada relevante, responda apenas: nada."
    )

    raw = await _call_inference(prompt, model)
    if not raw:
        return True  # houve dados e o LLM foi chamado — janela cumprida
    if not _is_meaningful(raw):
        log.debug("reflection_loop: resposta descartada (genérica): %r", raw[:60])
        return True

    await save_memory(type="reflection", content=raw, tags=["loop_periodico"])
    log.info("reflection_loop: reflexão salva (%d chars).", len(raw))
    return True


def _cross_device_block(limit: int = 20) -> str:
    """Bloco de prompt com a atividade em OUTRAS máquinas (shared_history),
    discriminado por máquina. Exclui a máquina atual (já coberta pelos blocos
    locais). Vazio se não houver atividade cross-device ou sem sync_root.
    """
    try:
        import shared_history  # type: ignore
        searches = shared_history.recent_searches(limit)
        visits   = shared_history.recent_visits(limit)
    except Exception as exc:
        log.debug("reflection_loop: shared_history indisponível: %s", exc)
        return ""

    this_machine = socket.gethostname()
    by_q: dict[str, list[str]] = defaultdict(list)
    by_v: dict[str, list[str]] = defaultdict(list)
    for s in searches:
        m = (s.get("machine") or "").strip()
        if m and m != this_machine and s.get("query"):
            by_q[m].append(s["query"])
    for v in visits:
        m = (v.get("machine") or "").strip()
        if m and m != this_machine:
            by_v[m].append(v.get("title") or v.get("url") or "")

    machines = sorted(set(by_q) | set(by_v))
    if not machines:
        return ""

    lines: list[str] = []
    for m in machines:
        parts: list[str] = []
        if by_q[m]:
            parts.append("buscou: " + ", ".join(by_q[m][:8]))
        if by_v[m]:
            parts.append("abriu: " + ", ".join(x for x in by_v[m][:6] if x))
        if parts:
            lines.append(f"- [{m}] " + " · ".join(parts))
    if not lines:
        return ""
    log.debug("reflection_loop: bloco cross-device com %d máquina(s)", len(lines))
    return "Atividade em outros dispositivos:\n" + "\n".join(lines) + "\n\n"


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
