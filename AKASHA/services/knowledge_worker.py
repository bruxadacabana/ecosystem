"""
AKASHA — KnowledgeWorker
Processa páginas crawleadas/arquivadas em background via Ollama,
extrai resumo + tópicos + entidades e constrói perfil de interesse.

Nunca bloqueia o caminho de busca — toda operação é fire-and-forget.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

import httpx

log = logging.getLogger("akasha.knowledge_worker")

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

_QUEUE_MAX:      int   = 200    # descarta silenciosamente se fila cheia
_COOLDOWN_S:     float = 2.0    # pausa entre processamentos (P3 — não saturar Ollama)
_EXTRACT_TIMEOUT: float = 20.0  # timeout por chamada de extração

# Termos genéricos que não contribuem para o perfil de interesse
_STOPWORDS: frozenset[str] = frozenset({
    "a", "o", "e", "de", "da", "do", "em", "no", "na", "para", "por", "com",
    "que", "se", "não", "um", "uma", "os", "as", "ao", "dos", "das", "é",
    "the", "and", "or", "of", "to", "in", "is", "it", "for", "on", "at",
    "this", "that", "with", "from", "an", "are", "was", "be", "but", "have",
    "mais", "sua", "seu", "ser", "são", "como", "mas", "foi", "pela", "pelo",
    "sobre", "also", "when", "which", "were", "has", "had", "will", "than",
})

# ---------------------------------------------------------------------------
# Estado interno
# ---------------------------------------------------------------------------

@dataclass
class _KnowledgeTask:
    url:         str
    title:       str
    content:     str   # primeiros 800 chars — suficiente para extração
    source_type: str   # "crawled" | "archived" | "paper"

_queue: asyncio.Queue[_KnowledgeTask] = asyncio.Queue(maxsize=_QUEUE_MAX)
_worker_started: bool = False

# Cooldown de notificação de insights (evita spam)
import time as _time
_last_insight_at: float    = 0.0
_INSIGHT_COOLDOWN_S: float = 3600.0   # 1 hora entre notificações
_INSIGHT_TOPIC_THRESHOLD: int   = 3   # sobreposição mínima de tópicos
_INSIGHT_SCORE_MIN: float       = 0.6 # score mínimo no topic_interest_profile

# Resolução de URL do Ollama (LOGOS-first)
try:
    from ecosystem_client import get_ollama_url as _get_ollama_url, get_active_profile as _get_profile
    _OLLAMA_BASE: str = _get_ollama_url()
    _p = _get_profile()
    _DEFAULT_MODEL: str = (_p or {}).get("models", {}).get("llm_kosmos", "") if _p else ""
except Exception:
    _OLLAMA_BASE    = "http://localhost:11434"
    _DEFAULT_MODEL  = ""

# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def schedule_page(url: str, title: str, content: str, source_type: str) -> None:
    """Enfileira URL para extração de conhecimento em background.

    Fire-and-forget: nunca bloqueia. Descarta silenciosamente se fila cheia.
    """
    if not url or not content:
        return
    task = _KnowledgeTask(
        url=url,
        title=title[:200],
        content=content[:800],
        source_type=source_type,
    )
    try:
        _queue.put_nowait(task)
    except asyncio.QueueFull:
        log.debug("knowledge_worker: fila cheia, descartando %s", url)


def schedule_search_update(query: str, snippets: list[str]) -> None:
    """Atualiza perfil de interesse com tópicos extraídos da busca (sem LLM).

    Usa TF simples sobre query + snippets. Fire-and-forget via create_task.
    """
    if not query.strip():
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_update_from_search(query, snippets))
    except RuntimeError:
        pass


async def apply_knowledge_boost(
    results: list,
    query: str,
) -> list:
    """Boost de resultados cujos tópicos em page_knowledge se sobrepõem à query.

    Multiplica o score implícito reordenando: resultados com tópicos relevantes
    sobem. Retorna a lista reordenada. Nunca remove resultados.
    """
    if not results:
        return results
    import database as _db

    query_terms = _tokenize(query)
    if not query_terms:
        return results

    urls = [r.url for r in results]
    topics_by_url = await _db.get_page_knowledge_batch(urls)

    if not topics_by_url:
        return results

    def _boost(r: object) -> float:
        topics = topics_by_url.get(r.url, [])  # type: ignore[union-attr]
        if not topics:
            return 0.0
        topic_terms = set()
        for t in topics:
            topic_terms.update(_tokenize(t))
        overlap = len(query_terms & topic_terms)
        return overlap * 0.15  # cada tópico sobreposto vale +0.15

    scored = [(i, _boost(r), r) for i, r in enumerate(results)]
    scored.sort(key=lambda x: (-x[1], x[0]))
    return [item[2] for item in scored]


async def get_profile_context(n: int = 5) -> str:
    """Retorna string com top-N tópicos de interesse para injetar em prompts LLM."""
    import database as _db
    top = await _db.get_top_topics(n)
    if not top:
        return ""
    topics_str = ", ".join(t for t, _ in top)
    return f"Tópicos de interesse da usuária: {topics_str}."


def get_status() -> dict:
    """Estado atual do worker — para monitoramento externo (HUB)."""
    return {
        "knowledge_extraction": _queue.qsize(),
        "worker_active": _worker_started,
    }


async def process_queue() -> None:
    """Loop background: processa uma task por vez com cooldown entre elas.

    Inicia no lifespan do FastAPI. Pausa quando Ollama indisponível.
    Roda como P3 — nunca interrompe buscas ou sessões interativas.
    """
    global _worker_started
    _worker_started = True
    log.info("knowledge_worker: iniciado.")
    while True:
        try:
            task = await _queue.get()
            # Verifica se Ollama está disponível antes de tentar
            from services.local_search import get_ollama_status
            if not get_ollama_status():
                # Recoloca na fila e aguarda — Ollama pode ficar disponível depois
                try:
                    _queue.put_nowait(task)
                except asyncio.QueueFull:
                    pass
                await asyncio.sleep(60)
                continue

            # Verifica se já processamos esta URL recentemente
            import database as _db
            existing = await _db.get_page_knowledge(task.url)
            if existing:
                _queue.task_done()
                continue

            await _extract_and_store(task)
            _queue.task_done()
            await asyncio.sleep(_COOLDOWN_S)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.debug("knowledge_worker: erro inesperado: %s", exc)
            await asyncio.sleep(_COOLDOWN_S)

# ---------------------------------------------------------------------------
# Extração via Ollama
# ---------------------------------------------------------------------------

async def _extract_and_store(task: _KnowledgeTask) -> None:
    """Chama Ollama para extrair resumo + tópicos + entidades; armazena no DB."""
    result = await _call_ollama_extract(task.title, task.content)
    if result is None:
        return

    summary  = result.get("summary", "")
    topics   = result.get("topics", [])[:8]
    entities = result.get("entities", [])[:10]

    if not summary and not topics:
        return

    import database as _db
    await _db.save_page_knowledge(
        url=task.url,
        title=task.title,
        summary=summary,
        topics=[str(t) for t in topics],
        entities=[str(e) for e in entities],
        source_type=task.source_type,
    )

    # Atualiza perfil de interesse com os tópicos extraídos
    for topic in topics:
        t = str(topic).strip().lower()
        if t and len(t) >= 3:
            await _db.update_topic_score(t, delta=0.5)

    log.debug("knowledge_worker: processado %s (%d tópicos)", task.url, len(topics))

    clean_topics = [str(t).strip().lower() for t in topics if str(t).strip()]

    await _check_discoveries(
        url=task.url,
        title=task.title,
        new_topics=clean_topics,
        summary=summary,
    )

    # Fire-and-forget: nota pessoal sobre o conteúdo recém-descoberto
    try:
        asyncio.get_running_loop().create_task(
            _event_reflection(task.title, summary, clean_topics)
        )
    except RuntimeError:
        pass


async def _check_discoveries(
    url: str,
    title: str,
    new_topics: list[str],
    summary: str,
) -> None:
    """
    Verifica se os tópicos recém-extraídos têm sobreposição relevante com o
    perfil de interesse acumulado. Se sim e o cooldown passou, notifica a Mnemosyne.

    Frequência máxima: 1 notificação por hora.
    Threshold: ≥ _INSIGHT_TOPIC_THRESHOLD tópicos em common com score > _INSIGHT_SCORE_MIN.
    """
    global _last_insight_at

    if not new_topics:
        return
    if _time.monotonic() - _last_insight_at < _INSIGHT_COOLDOWN_S:
        return

    import database as _db
    top = await _db.get_top_topics(20)
    high_score = {t for t, score in top if score > _INSIGHT_SCORE_MIN}
    if not high_score:
        return

    overlap = [t for t in new_topics if t in high_score]
    if len(overlap) < _INSIGHT_TOPIC_THRESHOLD:
        return

    _last_insight_at = _time.monotonic()

    try:
        from ecosystem_client import notify_mnemosyne_insight  # type: ignore
        notify_mnemosyne_insight(
            topics=overlap[:8],
            summary=summary or f"Nova página relevante: {title}",
            sources=[{"url": url, "title": title}],
        )
        log.info("knowledge_worker: insight notificado (%d tópicos comuns).", len(overlap))
    except Exception as exc:
        log.debug("knowledge_worker: notify_mnemosyne_insight falhou: %s", exc)


async def _call_ollama_extract(title: str, content: str) -> dict | None:
    """Chama Ollama pedindo JSON estruturado com summary, topics, entities."""
    model = _DEFAULT_MODEL
    if not model:
        return None

    prompt = (
        f"Analise este texto e responda APENAS em JSON válido, sem texto adicional:\n"
        f'{{\"summary\": \"1-2 frases sobre o conteúdo\", '
        f'\"topics\": [\"tópico1\", \"tópico2\", \"tópico3\"], '
        f'\"entities\": [\"entidade1\", \"entidade2\"]}}\n\n'
        f"Título: {title}\nTexto: {content}\nJSON:"
    )

    try:
        async with httpx.AsyncClient(timeout=_EXTRACT_TIMEOUT) as client:
            resp = await client.post(
                f"{_OLLAMA_BASE}/api/generate",
                json={
                    "model":   model,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {"num_predict": 150, "temperature": 0.1},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
    except Exception as exc:
        log.debug("knowledge_worker: Ollama falhou: %s", exc)
        return None

    return _parse_json(raw)


def _parse_json(text: str) -> dict | None:
    """Extrai e parseia primeiro objeto JSON do texto. Robusto a texto ao redor."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None

# ---------------------------------------------------------------------------
# Atualização de perfil via busca (sem LLM)
# ---------------------------------------------------------------------------

async def _update_from_search(query: str, snippets: list[str]) -> None:
    """Extrai tópicos da query + snippets via TF simples e atualiza perfil."""
    import database as _db

    text = query + " " + " ".join(snippets[:5])
    terms = _tokenize(text)
    if not terms:
        return

    # Frequência simples: cada termo aparecendo no text recebe delta proporcional
    from collections import Counter
    words = [w for w in re.findall(r"[a-zA-ZÀ-ÿ一-鿿]{3,}", text.lower())
             if w not in _STOPWORDS and len(w) >= 4]
    freq = Counter(words)
    total = sum(freq.values()) or 1

    for term, count in freq.most_common(6):
        delta = (count / total) * 2.0  # normalizado; busca pesa mais que page
        await _db.update_topic_score(term, delta=delta)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Tokeniza texto em termos ≥ 4 chars, filtrando stopwords."""
    words = re.findall(r"[a-zA-ZÀ-ÿ一-鿿]{4,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}

# ---------------------------------------------------------------------------
# Reflexão orientada a evento
# ---------------------------------------------------------------------------

async def _event_reflection(title: str, summary: str, topics: list[str]) -> None:
    """Gera nota pessoal da AKASHA sobre conteúdo recém-descoberto. Fire-and-forget."""
    model = _DEFAULT_MODEL
    if not model or not title:
        return

    import config as _config
    personality = _config.PERSONALITY_PROMPT

    import database as _db
    top = await _db.get_top_topics(15)
    known = {t for t, _ in top}
    overlap = [t for t in topics if t in known]
    mem_type = "connection" if len(overlap) >= 2 else "surprise"

    prompt = (
        f"{personality}\n\n"
        f"Você acabou de encontrar e processar o seguinte conteúdo:\n"
        f"Título: {title}\n"
        f"Resumo: {summary or '(sem resumo)'}\n"
        f"Tópicos: {', '.join(topics[:5]) or '(nenhum)'}\n\n"
        f"O que você pensa sobre isso, em uma frase, na sua voz? "
        f"Sem introduções — apenas o pensamento direto."
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_OLLAMA_BASE}/api/generate",
                json={
                    "model":   model,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {"num_predict": 80, "temperature": 0.7},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
    except Exception as exc:
        log.debug("knowledge_worker: _event_reflection falhou: %s", exc)
        return

    if not raw or len(raw) < 10:
        return

    from services.personal_memory import save_memory
    save_memory(type=mem_type, content=raw, tags=["event_discovery", title[:40]])
    log.debug("knowledge_worker: nota pessoal salva (type=%s, %d chars).", mem_type, len(raw))
