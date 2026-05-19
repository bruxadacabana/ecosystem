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

# Termos técnicos conhecidos para extração de entidades sem LLM
_KNOWN_TECH: frozenset[str] = frozenset({
    "rust", "python", "typescript", "javascript", "go", "kotlin", "swift",
    "java", "cpp", "c++", "haskell", "erlang", "elixir", "ocaml", "scala",
    "react", "vue", "svelte", "nextjs", "tauri", "fastapi", "django", "flask",
    "pytorch", "tensorflow", "jax", "ollama", "llama", "mistral", "gemma",
    "chromadb", "sqlite", "postgres", "redis", "kafka", "docker", "kubernetes",
    "linux", "nixos", "arch", "debian", "ubuntu", "windows", "macos",
    "rocm", "cuda", "opengl", "vulkan", "webgpu",
    "transformer", "embedding", "rag", "llm", "nlp", "gpt", "bert",
    "attention", "diffusion", "stable diffusion", "gan", "vae",
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
_worker_started:   bool = False
_total_processed:  int  = 0   # conta páginas processadas com sucesso nesta sessão
_backfill_running: bool = False  # True enquanto backfill inicial estiver em andamento

# Cooldown de notificação de insights (evita spam)
import time as _time
_last_insight_at: float    = 0.0
_INSIGHT_COOLDOWN_S: float = 3600.0   # 1 hora entre notificações
_INSIGHT_TOPIC_THRESHOLD: int   = 3   # sobreposição mínima de tópicos
_INSIGHT_SCORE_MIN: float       = 0.6 # score mínimo no topic_interest_profile

# URL base do Ollama — resolvida dinamicamente em runtime via _get_ollama_base()
_OLLAMA_BASE: str = "http://localhost:11434"


def _get_ollama_base() -> str:
    """Retorna URL do Ollama em runtime (LOGOS 7072 se disponível, direto 11434)."""
    try:
        from ecosystem_client import get_ollama_url as _get_url  # type: ignore
        return _get_url()
    except Exception:
        return "http://localhost:11434"


def _get_llm_query_model() -> str:
    """Lê o modelo llm_query do perfil ativo do LOGOS em runtime."""
    try:
        from ecosystem_client import get_active_profile as _get_profile  # type: ignore
        p = _get_profile()
        return ((p or {}).get("models", {}) or {}).get("llm_query", "") if p else ""
    except Exception:
        return ""

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


_interests_cache: dict[str, float] = {}
_interests_cache_at: float = 0.0
_INTERESTS_CACHE_TTL: float = 60.0  # atualiza no máximo uma vez por minuto


async def apply_knowledge_boost(
    results: list,
    query: str,
) -> list:
    """Boost de resultados baseado em dois sinais:

    1. Sobreposição de tópicos da página com termos da query (relevância temática).
    2. Score de interesse acumulado da usuária para os tópicos da página (personalização).

    Retorna a lista reordenada. Nunca remove resultados.
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

    # Perfil de interesse da usuária: cached {topic_lower: normalized_score}
    global _interests_cache, _interests_cache_at
    import time as _time
    now = _time.monotonic()
    if now - _interests_cache_at >= _INTERESTS_CACHE_TTL:
        try:
            raw_interests = await _db.get_top_topics(20)
            if raw_interests:
                max_score = max(s for _, s in raw_interests)
                if max_score > 0:
                    _interests_cache = {t.lower().strip(): s / max_score for t, s in raw_interests}
        except Exception:
            pass
        _interests_cache_at = now
    interest_profile = _interests_cache

    def _boost(r: object) -> float:
        topics = topics_by_url.get(r.url, [])  # type: ignore[union-attr]
        if not topics:
            return 0.0
        topic_terms: set[str] = set()
        interest_bonus = 0.0
        for t in topics:
            topic_terms.update(_tokenize(t))
            t_key = t.lower().strip()
            if t_key in interest_profile:
                interest_bonus += interest_profile[t_key] * 0.3
        overlap = len(query_terms & topic_terms)
        # Sinal 1: sobreposição query-tópico (+0.15 por tópico)
        # Sinal 2: interesse acumulado da usuária (máx +0.6 para não engolir a relevância)
        return overlap * 0.15 + min(interest_bonus, 0.6)

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


def on_feedback_dismissed(memory_id: int) -> None:
    """Fire-and-forget: aplica penalidade de score quando usuária descarta (✗) um insight.

    Decrementa topic scores (delta=-0.5) dos termos presentes no conteúdo descartado,
    acelerando a convergência do perfil de interesse ao remover ruído explicitamente.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_process_dismissed_feedback(memory_id))
    except RuntimeError:
        pass


def on_feedback_confirmed(memory_id: int) -> None:
    """Fire-and-forget: cria memória episódica quando usuária confirma (✓) um insight.

    Incrementa topic scores (delta=1.0) e salva proposição sintetizada em
    personal_memory com tag 'episodic_confirmed'. Usa LLM se disponível;
    cai para template determinístico caso contrário.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_process_confirmed_feedback(memory_id))
    except RuntimeError:
        pass


def get_status() -> dict:
    """Estado atual do worker — para monitoramento externo (HUB)."""
    return {
        "knowledge_extraction": _queue.qsize(),
        "worker_active":        _worker_started,
        "processed_session":    _total_processed,
        "backfill_running":     _backfill_running,
    }


async def _apply_interest_seeds() -> None:
    """Pré-popula topic_interest_profile com seeds definidas pela usuária no HUB.

    Lê `akasha.interest_seeds` do ecosystem.json. Seeds recebem score inicial 1.0
    apenas se o tópico ainda não existir no perfil — não sobrescreve histórico acumulado.
    """
    try:
        from ecosystem_client import read_ecosystem  # type: ignore
        eco = read_ecosystem()
        seeds: list[str] = (eco.get("akasha") or {}).get("interest_seeds") or []
    except Exception:
        seeds = []

    if not seeds:
        return

    import database as _db
    count = 0
    for seed in seeds:
        topic = seed.strip().lower()
        if not topic or len(topic) < 3:
            continue
        existing = await _db.get_topic_score(topic)
        if existing is None:
            await _db.update_topic_score(topic, delta=1.0)
            count += 1

    if count:
        log.info("knowledge_worker: %d seed(s) de interesse pré-populados.", count)


async def process_queue() -> None:
    """Loop background: processa uma task por vez com cooldown entre elas.

    Inicia no lifespan do FastAPI. Pausa quando Ollama indisponível.
    Roda como P3 — nunca interrompe buscas ou sessões interativas.
    """
    global _worker_started
    _worker_started = True
    await _apply_interest_seeds()
    log.info("knowledge_worker: iniciado.")
    while True:
        try:
            task = await _queue.get()
            # Verifica se Ollama está disponível antes de tentar
            from services.local_search import get_ollama_status, check_ollama_available
            if not get_ollama_status():
                # Re-verifica em tempo real antes de desistir
                await check_ollama_available()
                if not get_ollama_status():
                    # Recoloca na fila e aguarda — Ollama pode ficar disponível depois
                    try:
                        _queue.put_nowait(task)
                    except asyncio.QueueFull:
                        pass
                    await asyncio.sleep(60)
                    continue

            # Verifica se já processamos esta URL recentemente.
            # Páginas crawleadas: usa crawl_pages.knowledge_processed (persiste
            # mesmo se page_knowledge for limpa para re-análise).
            # Arquivos arquivados/papers: usa page_knowledge como antes.
            import database as _db
            already_done: bool
            if task.source_type == "crawled":
                already_done = await _db.get_crawl_page_processed(task.url)
            else:
                already_done = bool(await _db.get_page_knowledge(task.url))
            if already_done:
                _queue.task_done()
                continue

            log.info("knowledge_worker: extraindo '%s' [%s]", task.title[:60] or task.url[:60], task.source_type)
            await _extract_and_store(task)
            _queue.task_done()
            await asyncio.sleep(_COOLDOWN_S)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.warning("knowledge_worker: erro inesperado: %s", exc)
            await asyncio.sleep(_COOLDOWN_S)

# ---------------------------------------------------------------------------
# Extração via Ollama
# ---------------------------------------------------------------------------

async def _process_dismissed_feedback(memory_id: int) -> None:
    """Aplica delta negativo nos tópicos de um insight descartado."""
    from services.personal_memory import get_by_id
    entry = await get_by_id(memory_id)
    if not entry:
        return

    terms = _tokenize(entry["content"])
    import database as _db
    for term in list(terms)[:8]:
        await _db.update_topic_score(term, delta=-0.5)

    log.info(
        "knowledge_worker.dismissed: penalidade em %d tópico(s) (memória #%d).",
        len(terms), memory_id,
    )


async def _process_confirmed_feedback(memory_id: int) -> None:
    """Gera entrada episódica a partir de um insight confirmado pela usuária."""
    from services.personal_memory import get_by_id, save_memory as _save
    entry = await get_by_id(memory_id)
    if not entry:
        return

    content = entry["content"]

    # Incrementa scores dos termos presentes no insight (sinal forte — confirmação explícita)
    import database as _db
    terms = _tokenize(content)
    for term in list(terms)[:8]:
        await _db.update_topic_score(term, delta=1.0)

    # Tenta síntese via LLM; cai para template determinístico
    model = _get_llm_query_model()
    proposition: str | None = None

    if model:
        prompt = (
            f"Sintetize em uma proposição factual o que esta observação revela "
            f"sobre os interesses da usuária:\n\n\"{content}\"\n\n"
            f"Apenas a proposição, sem introdução. Exemplo: "
            f"\"Usuária tem interesse em aprendizado de máquina aplicado a texto.\""
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{_get_ollama_base()}/api/generate",
                    json={
                        "model":   model,
                        "prompt":  prompt,
                        "stream":  False,
                        "options": {"num_predict": 60, "temperature": 0.2},
                    },
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "").strip()
                if raw and len(raw) >= 10:
                    proposition = raw
        except Exception as exc:
            log.debug("knowledge_worker: síntese episódica falhou: %s", exc)

    if not proposition:
        top_terms = sorted(terms, key=lambda t: len(t), reverse=True)[:5]
        if top_terms:
            proposition = f"Usuária confirmou interesse em: {', '.join(top_terms)}"
        else:
            proposition = f"Usuária confirmou: \"{content[:80]}\""

    await _save(
        type="observation",
        content=proposition,
        tags=["episodic_confirmed", f"source:{memory_id}"],
    )
    log.info(
        "knowledge_worker.confirmed: memória episódica salva (fonte memória #%d).",
        memory_id,
    )

    # Extrai entidades e atualiza grafo de co-ocorrência
    if model:
        entities = await _extract_entities_llm(content, model)
    else:
        entities = _extract_entities_regex(content)
    if entities:
        await _update_entity_graph(entities)


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
    # Marca a página crawleada como processada — flag independente do conteúdo LLM,
    # persiste mesmo se page_knowledge for limpa para re-análise.
    if task.source_type == "crawled":
        await _db.set_crawl_page_processed(task.url)

    # Atualiza perfil de interesse com os tópicos extraídos
    for topic in topics:
        t = str(topic).strip().lower()
        if t and len(t) >= 3:
            await _db.update_topic_score(t, delta=0.5)

    global _total_processed
    _total_processed += 1
    log.info("knowledge_worker: concluído '%s' — %d tópico(s), %d entidade(s)", task.title[:60] or task.url[:60], len(topics), len(entities))

    clean_topics = [str(t).strip().lower() for t in topics if str(t).strip()]

    # Adiciona pares de tópicos ao grafo de conexões (peso menor que entidades nomeadas)
    if len(clean_topics) >= 2:
        asyncio.get_running_loop().create_task(
            _update_entity_graph(clean_topics, delta=0.3)
        )

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

    # Pega a nota pessoal mais recente do AKASHA (se houver) para enviar à Mnemosyne
    _akasha_thought: str | None = None
    try:
        from services.personal_memory import get_recent as _get_mem
        recent_mems = await _get_mem(1)
        if recent_mems:
            _akasha_thought = recent_mems[0].get("content")
    except Exception:
        pass

    try:
        from ecosystem_client import notify_mnemosyne_insight  # type: ignore
        notify_mnemosyne_insight(
            topics=overlap[:8],
            summary=summary or f"Nova página relevante: {title}",
            sources=[{"url": url, "title": title}],
            akasha_thought=_akasha_thought,
        )
        log.info("knowledge_worker: insight notificado (%d tópicos comuns).", len(overlap))
    except Exception as exc:
        log.debug("knowledge_worker: notify_mnemosyne_insight falhou: %s", exc)


async def _call_ollama_extract(title: str, content: str) -> dict | None:
    """Chama Ollama pedindo JSON estruturado com summary, topics, entities."""
    model = _get_llm_query_model()
    if not model:
        log.debug("knowledge_worker: llm_query não configurado no perfil do LOGOS — extração ignorada.")
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
                f"{_get_ollama_base()}/api/generate",
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
        log.warning("knowledge_worker: Ollama falhou na extração: %s", exc)
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
# Extração de entidades + grafo de co-ocorrência
# ---------------------------------------------------------------------------

async def _extract_entities_llm(text: str, model: str) -> list[str]:
    """Extrai entidades via LLM (P3). Retorna lista vazia em falha."""
    prompt = (
        f"Liste as entidades principais do texto abaixo: nomes de pessoas, tecnologias, "
        f"linguagens, conceitos, frameworks ou organizações. Uma por linha, sem explicações.\n\n"
        f"Texto: {text[:500]}\n\nEntidades:"
    )
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                f"{_get_ollama_base()}/api/generate",
                json={
                    "model":   model,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {"num_predict": 80, "temperature": 0.1},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
    except Exception as exc:
        log.debug("knowledge_worker: extração de entidades LLM falhou: %s", exc)
        return []

    entities: list[str] = []
    for line in raw.splitlines():
        e = re.sub(r"^[\-\*\d\.\)]+\s*", "", line).strip().lower()
        if 2 < len(e) < 60:
            entities.append(e)
    return entities[:12]


def _extract_entities_regex(text: str) -> list[str]:
    """Fallback: extrai entidades via termos técnicos conhecidos + palavras capitalizadas."""
    found: list[str] = []
    text_lower = text.lower()

    # Termos técnicos conhecidos
    for tech in _KNOWN_TECH:
        if tech in text_lower:
            found.append(tech)

    # Palavras capitalizadas em mid-sentence (exceto início de frase)
    caps = re.findall(r"(?<=[a-záéíóúàãõ,;]\s)([A-Z][a-zA-Z]{2,})", text)
    found.extend(c.lower() for c in caps if c.lower() not in _STOPWORDS)

    seen: set[str] = set()
    result: list[str] = []
    for e in found:
        if e not in seen:
            seen.add(e)
            result.append(e)
    return result[:12]


async def _update_entity_graph(entities: list[str], delta: float = 1.0) -> None:
    """Registra pares de co-ocorrência no entity_graph."""
    if len(entities) < 2:
        return
    import database as _db
    from itertools import combinations
    pairs = list(combinations(entities, 2))
    for a, b in pairs:
        await _db.upsert_entity_pair(a, b, delta=delta)
    log.info(
        "knowledge_worker.entity_graph: %d item(s), %d par(es) registrado(s).",
        len(entities), len(pairs),
    )


# ---------------------------------------------------------------------------
# Reflexão orientada a evento
# ---------------------------------------------------------------------------

async def _event_reflection(title: str, summary: str, topics: list[str]) -> None:
    """Gera nota pessoal da AKASHA sobre conteúdo recém-descoberto. Fire-and-forget."""
    model = _get_llm_query_model()
    if not model or not title:
        return

    log.info("knowledge_worker.reflection: gerando nota sobre '%s'", title[:60])

    import config as _config
    personality = _config.PERSONALITY_PROMPT

    import database as _db
    top = await _db.get_top_topics(15)
    known = {t for t, _ in top}
    overlap = [t for t in topics if t in known]
    mem_type = "connection" if len(overlap) >= 2 else "surprise"

    from services.personal_memory import save_memory, get_context_memories
    context_memories = await get_context_memories(4)
    context_text = ""
    if context_memories:
        confirmed = [m for m in context_memories if m.get("feedback") == "confirmed"]
        if confirmed:
            context_text = "O que já notei antes:\n" + "\n".join(f"- {m['content']}" for m in confirmed[:2]) + "\n\n"

    prompt = (
        f"{personality}\n\n"
        f"{context_text}"
        f"Você acabou de encontrar e processar o seguinte conteúdo:\n"
        f"Título: {title}\n"
        f"Resumo: {summary or '(sem resumo)'}\n"
        f"Tópicos: {', '.join(topics[:5]) or '(nenhum)'}\n\n"
        f"O que você pensa sobre isso, em uma frase, na sua voz? "
        f"Sem introduções — apenas o pensamento direto."
    )

    # Aguarda antes de chamar Ollama — dá tempo à extração concorrente terminar.
    # Em CPUs lentos (2-5 tok/s) a extração da próxima página já começou; sem este
    # delay + timeout estendido a reflexão sempre perde a corrida e falha silenciosamente.
    await asyncio.sleep(5.0)
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{_get_ollama_base()}/api/generate",
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
        log.warning("knowledge_worker: _event_reflection falhou: %s", exc)
        return

    if not raw or len(raw) < 10:
        return

    await save_memory(type=mem_type, content=raw, tags=["event_discovery", title[:40]])
    log.info("knowledge_worker.reflection: nota salva (type=%s) sobre '%s'", mem_type, title[:60])


# ---------------------------------------------------------------------------
# Backfill — processa dados anteriores ao startup do worker
# ---------------------------------------------------------------------------

def _parse_archive_md(path: "Path") -> tuple[str, str, str]:
    """Extrai (url, title, content) de um arquivo .md arquivado pelo AKASHA."""
    from pathlib import Path as _Path
    try:
        text = _Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", "", ""

    if not text.startswith("---"):
        return "", "", ""

    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", "", ""

    url = title = ""
    for line in parts[1].splitlines():
        low = line.strip()
        if low.startswith("source_url:"):
            # papers usam source_url (não url)
            url = low[11:].strip().strip("\"'")
        elif low.startswith("url:") and not url:
            url = low[4:].strip().strip("\"'")
        elif low.startswith("title:"):
            title = low[6:].strip().strip("\"'")

    content = parts[2].strip()
    return url, title, content[:800]


async def backfill_knowledge(archive_path: "Path") -> None:
    """Enfileira para extração páginas já existentes que ainda não foram processadas.

    Chamada no lifespan após process_queue() ser iniciado. Aguarda 15s para dar
    tempo ao worker e ao DB inicializarem. Ritmo controlado: pausa quando a fila
    fica com > 50 itens para não bloquear processamento de novas páginas.
    """
    global _backfill_running
    from pathlib import Path as _Path
    import database as _db

    await asyncio.sleep(15)   # aguarda worker + DB prontos
    _backfill_running = True

    async def _wait_queue_drain(threshold: int = 50) -> None:
        while _queue.qsize() > threshold:
            await asyncio.sleep(5)

    total_enqueued = 0

    # ── 1. Arquivos arquivados manualmente (ARCHIVE_PATH/*.md) ──────────────
    archive_dir = _Path(archive_path)
    if archive_dir.is_dir():
        md_files = sorted(archive_dir.rglob("*.md"))
        log.info("backfill: %d arquivo(s) em %s", len(md_files), archive_dir)
        for md_file in md_files:
            url, title, content = _parse_archive_md(md_file)
            if not url or not content:
                continue
            existing = await _db.get_page_knowledge(url)
            if existing:
                continue
            await _wait_queue_drain()
            src_type = "paper" if "Papers" in md_file.parts else "archived"
            schedule_page(url, title or md_file.stem, content, src_type)
            total_enqueued += 1

    # ── 2. Páginas crawleadas da Biblioteca sem extração ───────────────────
    try:
        import aiosqlite
        from config import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                "SELECT cp.url, cp.title, cp.content_md "
                "FROM crawl_pages cp "
                "WHERE cp.knowledge_processed = 0 "
                "  AND cp.content_md != '' "
                "ORDER BY cp.crawled_at DESC"
            )).fetchall()
        log.info("backfill: %d página(s) de crawl_pages sem extração", len(rows))
        for url, title, content_md in rows:
            if not url or not content_md:
                continue
            await _wait_queue_drain()
            schedule_page(url, title or url, content_md[:800], "crawled")
            total_enqueued += 1
    except Exception as exc:
        log.warning("backfill: erro ao ler crawl_pages: %s", exc)

    if total_enqueued:
        log.info("backfill: %d página(s) enfileiradas para extração de conhecimento.", total_enqueued)
    else:
        log.info("backfill: nenhuma página nova para processar.")
    _backfill_running = False
