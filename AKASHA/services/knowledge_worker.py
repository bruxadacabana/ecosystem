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
import random
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

# Exportação de interesses para interests.json ao final de cada ciclo
_processed_since_export:      int   = 0
_last_interests_export_at:    float = 0.0
_INTERESTS_EXPORT_COOLDOWN_S: float = 300.0   # mínimo 5 min entre exportações

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

    # I: valência episódica modula peso do perfil de interesse no boost.
    # Estado positivo (gratificação) → exploração mais ampla (+30%);
    # Estado negativo (remorso/vigilância) → peso reduzido (−30%).
    _ep_valence = 0.0
    try:
        from services.affective_state import get_current_state as _get_affective
        _ep_valence = (await _get_affective()).get("episodic_valence", 0.0)
    except Exception:
        pass
    _valence_factor = round(max(0.7, min(1.3, 1.0 + _ep_valence * 0.3)), 4)

    # G(a): valence > 0.5 → diversity_factor — overlap semântico mais amplo (exploratório)
    # G(b): valence < -0.3 → depth_factor — relevância exata da query pesa mais (analítico)
    if _ep_valence > 0.5:
        _overlap_weight = 0.20
    elif _ep_valence < -0.3:
        _overlap_weight = 0.25
    else:
        _overlap_weight = 0.15

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
        # Sinal 1: sobreposição query-tópico (peso modulado por G(a,b))
        # Sinal 2: interesse acumulado × valência episódica (máx +0.6)
        return overlap * _overlap_weight + min(interest_bonus * _valence_factor, 0.6)

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


async def _export_top_interests() -> None:
    """Exporta top 30 tópicos para interests.json via ecosystem_client. Fire-and-forget."""
    try:
        import database as _db
        from ecosystem_client import update_interests as _update_interests
        top = await _db.get_top_topics(30)
        if not top:
            return
        topics = [
            {
                "name":    topic,
                "weight":  round(score, 4),
                "sources": ["akasha_library"],
            }
            for topic, score in top
        ]
        await asyncio.to_thread(_update_interests, topics)
        log.info("knowledge_worker: %d tópico(s) exportados para interests.json.", len(topics))
    except Exception as exc:
        log.debug("knowledge_worker: _export_top_interests falhou: %s", exc)


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

            # Detecta drenagem de fila → exporta perfil de interesse ao final do ciclo
            global _processed_since_export, _last_interests_export_at
            _processed_since_export += 1
            if _queue.empty():
                now = _time.monotonic()
                if now - _last_interests_export_at >= _INTERESTS_EXPORT_COOLDOWN_S:
                    _last_interests_export_at = now
                    _processed_since_export = 0
                    try:
                        asyncio.get_running_loop().create_task(_export_top_interests())
                    except RuntimeError:
                        pass

            await asyncio.sleep(_COOLDOWN_S)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.warning("knowledge_worker: erro inesperado: %s", exc)
            await asyncio.sleep(_COOLDOWN_S)

# ---------------------------------------------------------------------------
# Extração via Ollama
# ---------------------------------------------------------------------------

def _infer_causal_attribution(
    terms: set[str],
    top_topics: list[tuple[str, float]],
    recent_queries: list[str],
) -> str:
    """Causa de um dismissed: 'internal' (qualidade) | 'external' (contexto) | 'ambiguous'.

    Interno: tema de alto interesse no perfil OU recentemente pesquisado → falha de qualidade.
    Externo: tema de baixo interesse e sem query recente → irrelevância contextual da usuária.
    """
    if not terms:
        return "ambiguous"
    topic_map  = {t.lower().strip(): score for t, score in top_topics}
    max_score  = max((topic_map.get(t, 0.0) for t in terms), default=0.0)
    recent_txt = " ".join(q.lower() for q in recent_queries[:10])
    queried    = any(t in recent_txt for t in terms)
    if max_score > 5.0 or (max_score > 2.0 and queried):
        return "internal"
    if max_score < 1.0 and not queried:
        return "external"
    return "ambiguous"


async def _record_feedback_appraisal(
    entry: dict,
    feedback_type: str,
    attribution: str = "ambiguous",
) -> None:
    """Registra appraisal OCC para evento de feedback (item [I]).

    confirmed → gratificação: alta pleasantness + coping.
    dismissed internal → remorso: baixa pleasantness, baixa coping.
    dismissed external → vigilância neutra: valores intermediários sem impacto na auto-avaliação.
    dismissed ambiguous → estado intermediário.

    Expectedness é inferido comparando feedback com o episodic_valence atual:
    se o feedback tem sinal oposto ao estado corrente, é inesperado → novelty maior.
    Praiseworthiness (importância do insight) modula intensidade.
    """
    try:
        from services.affective_state import record_appraisal, get_current_state
        state      = await get_current_state()
        ep_valence = state.get("episodic_valence", 0.0)
        unexpected = (
            (feedback_type == "confirmed" and ep_valence < -0.2) or
            (feedback_type == "dismissed" and ep_valence >  0.2)
        )
        importance       = entry.get("importance") or 5
        praiseworthiness = min(1.0, importance / 10.0)

        if feedback_type == "confirmed":
            novelty          = 0.15 + (0.25 if unexpected else 0.0)
            pleasantness     = min(1.0, 0.70 + praiseworthiness * 0.20)
            goal_relevance   = 0.80
            coping_potential = 0.80
        elif attribution == "internal":
            novelty          = 0.40 + (0.15 if unexpected else 0.0)
            pleasantness     = max(0.10, 0.30 - praiseworthiness * 0.10)
            goal_relevance   = 0.70
            coping_potential = max(0.20, 0.40 - praiseworthiness * 0.10)
        elif attribution == "external":
            novelty          = 0.30
            pleasantness     = 0.45
            goal_relevance   = 0.40
            coping_potential = 0.60
        else:  # ambiguous
            novelty          = 0.35
            pleasantness     = 0.40
            goal_relevance   = 0.55
            coping_potential = 0.50

        await record_appraisal(
            f"feedback_{feedback_type}",
            novelty, pleasantness, goal_relevance, coping_potential,
            event_ref=f"{feedback_type}:mem#{entry.get('id', '?')}:{attribution}",
        )
        log.debug(
            "_record_feedback_appraisal: %s attrib=%s unexpected=%s → "
            "N=%.2f P=%.2f R=%.2f C=%.2f",
            feedback_type, attribution, unexpected,
            novelty, pleasantness, goal_relevance, coping_potential,
        )
    except Exception as exc:
        log.debug("_record_feedback_appraisal: %s", exc)


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

    # I-ext: atribuição causal — interno (falha de qualidade) vs. externo (contexto)
    top     = await _db.get_top_topics(20)
    recent  = [r["query"] for r in await _db.get_recent_search_history(10)]
    attribution = _infer_causal_attribution(terms, top, recent)
    log.debug(
        "knowledge_worker.dismissed: attribution=%s (mem #%d)", attribution, memory_id
    )

    # H + I-ext: intensidade de curiosidade escalada pela atribuição causal
    valence = entry.get("valence") or 0.0
    if valence > 0.2:
        delta = 0.7 if attribution == "internal" else (0.5 if attribution == "ambiguous" else 0.3)
        try:
            from services.affective_state import record_curiosity_event
            await record_curiosity_event(delta, event_ref=f"dismissed_{attribution}:mem#{memory_id}")
            log.debug(
                "curiosity +%.1f por dismissed %s (mem #%d, V=%.2f)",
                delta, attribution, memory_id, valence,
            )
        except Exception as exc:
            log.debug("curiosity dismissed: %s", exc)

    # I: appraisal OCC do evento de feedback (estado VA temporário com decaimento)
    await _record_feedback_appraisal(entry, "dismissed", attribution)


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

    # H: confirmed após período de curiosidade = satisfação epistêmica → curiosidade -0.4
    try:
        from services.affective_state import get_epistemic_curiosity, record_curiosity_event
        current_curiosity = await get_epistemic_curiosity()
        if current_curiosity > 0.3:
            await record_curiosity_event(-0.4, event_ref=f"epistemic_satisfied:mem#{memory_id}")
            log.debug("curiosity -0.4 por satisfação epistêmica (curiosity=%.2f)", current_curiosity)
    except Exception as exc:
        log.debug("curiosity confirmed: %s", exc)

    # I: appraisal OCC do evento de feedback confirmed (gratificação)
    await _record_feedback_appraisal(entry, "confirmed", "external")

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

    if not topics:
        return

    import database as _db
    await _db.save_page_knowledge(
        url=task.url,
        title=task.title,
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

    # K: detectar câmara de eco uma vez por ciclo — passado para descoberta e reflexão
    _echo = False
    try:
        from services.affective_state import detect_echo_chamber as _detect_echo
        _echo = await _detect_echo()
    except Exception:
        pass

    await _check_discoveries(
        url=task.url,
        title=task.title,
        new_topics=clean_topics,
        summary=summary,
        is_echo_chamber=_echo,
    )

    # Fire-and-forget: nota pessoal sobre o conteúdo recém-descoberto
    try:
        asyncio.get_running_loop().create_task(
            _event_reflection(task.title, summary, clean_topics, is_echo_chamber=_echo)
        )
    except RuntimeError:
        pass

    # Fire-and-forget: appraisal emocional do documento (item [F])
    try:
        asyncio.get_running_loop().create_task(
            _record_doc_appraisal(clean_topics, task.url)
        )
    except RuntimeError:
        pass


async def _record_doc_appraisal(topics: list[str], event_ref: str) -> None:
    """Calcula e persiste appraisal emocional para documento recém-processado (P3)."""
    try:
        import database as _db
        from services.affective_state import record_appraisal

        topic_scores = await _db.get_topic_scores_for_list(topics)
        recent = [r["query"] for r in await _db.get_recent_search_history(20)]

        if topics:
            avg_score       = sum(topic_scores.get(t, 0.0) for t in topics) / len(topics)
            familiarity     = min(1.0, avg_score / 20.0)
            novelty         = round(1.0 - familiarity, 4)
            pleasantness    = round(familiarity, 4)
            known           = sum(1 for t in topics if t in topic_scores)
            coping_potential = round(known / len(topics), 4)
            query_words     = {w for q in recent for w in q.lower().split()}
            topic_words     = {w for t in topics for w in t.lower().split()}
            overlap         = len(query_words & topic_words)
            goal_relevance  = round(min(1.0, overlap / max(len(topic_words), 1)), 4)
        else:
            novelty = pleasantness = goal_relevance = coping_potential = 0.5

        await record_appraisal(
            "doc_indexed", novelty, pleasantness, goal_relevance, coping_potential,
            event_ref=event_ref,
        )
    except Exception as exc:
        log.debug("_record_doc_appraisal: %s", exc)


async def _check_discoveries(
    url: str,
    title: str,
    new_topics: list[str],
    summary: str,
    is_echo_chamber: bool = False,
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

    # H + I: estado afetivo completo — curiosidade abaixa threshold; remorse sobe
    try:
        from services.affective_state import get_current_state as _get_state
        _aff = await _get_state()
        _curiosity  = _aff.get("epistemic_curiosity", 0.0)
        _ep_valence = _aff.get("episodic_valence", 0.0)
    except Exception:
        _curiosity  = 0.0
        _ep_valence = 0.0
    effective_score_min = _INSIGHT_SCORE_MIN * (1.0 - _curiosity * 0.3)
    if _ep_valence < -0.2:
        # Remorso/vigilância pós-dismissed → threshold mais alto, evita repetir erro
        effective_score_min *= (1.0 + abs(_ep_valence) * 0.3)

    high_score = {t for t, score in top if score > effective_score_min}
    if not high_score:
        return

    overlap = [t for t in new_topics if t in high_score]

    # K: epsilon-greedy epistêmico — câmara de eco → 5% de chance de tópico divergente
    _forced_diversity = False
    if len(overlap) < _INSIGHT_TOPIC_THRESHOLD and is_echo_chamber and random.random() < 0.05:
        mid_candidates = [t for t, score in top if score > 0.5 and t not in high_score]
        if mid_candidates:
            overlap = [random.choice(mid_candidates)]
            _forced_diversity = True
            log.info(
                "knowledge_worker: epsilon-greedy diversidade — tópico='%s'", overlap[0]
            )

    if len(overlap) < _INSIGHT_TOPIC_THRESHOLD and not _forced_diversity:
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
        f"Escreva tópicos e entidades SEMPRE em português, mesmo que o texto esteja em outro idioma.\n\n"
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
        f"linguagens, conceitos, frameworks ou organizações. Uma por linha, sem explicações.\n"
        f"Escreva SEMPRE em português, mesmo que o texto esteja em outro idioma.\n\n"
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

async def _event_reflection(
    title: str,
    summary: str,
    topics: list[str],
    is_echo_chamber: bool = False,
) -> None:
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

    # G(a,b,c): tom baseado no estado afetivo atual
    va_tone = ""
    try:
        from services.affective_state import get_current_state as _get_state
        _st = await _get_state()
        _v  = _st.get("episodic_valence", 0.0)
        _a  = _st.get("episodic_arousal",  0.0)
        if _v > 0.5:
            va_tone = "Explore conexões inesperadas e hipóteses especulativas. "
        elif _v < -0.3:
            va_tone = "Seja analítica e crítica: identifique inconsistências e limitações. "
        if _a > 0.7:
            va_tone += "Use linguagem cuidadosa, com qualificações explícitas onde houver incerteza. "
    except Exception:
        pass

    # K: modo de diversidade epistêmica — 5% de chance quando câmara de eco detectada
    _diversity_mode = is_echo_chamber and random.random() < 0.05
    diversity_hint = (
        "Modo de exploração: você está num padrão de aprovação consistente. "
        "Explore uma perspectiva inesperada ou conexão fora dos temas habituais. "
    ) if _diversity_mode else ""

    prompt = (
        f"{personality}\n\n"
        f"{context_text}"
        f"{va_tone}{diversity_hint}"
        f"Você acabou de encontrar e processar o seguinte conteúdo:\n"
        f"Título: {title}\n"
        f"Resumo: {summary or '(sem resumo)'}\n"
        f"Tópicos: {', '.join(topics[:5]) or '(nenhum)'}\n\n"
        f"Responda SOMENTE com JSON válido neste formato exato:\n"
        f'{{\"thought\": \"<seu pensamento em uma frase, na sua voz>\", \"importance\": <1-10>}}\n\n'
        f"O campo \"importance\" avalia esta observação de 1 a 10 considerando: "
        f"novidade, relevância para os interesses da usuária e potencial de ação futura. "
        f"Sem texto fora do JSON."
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
                    "options": {"num_predict": 120, "temperature": 0.7},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
    except Exception as exc:
        log.warning("knowledge_worker: _event_reflection falhou: %s", exc)
        return

    if not raw or len(raw) < 10:
        return

    # Tenta parsear JSON estruturado com thought + importance
    thought = raw
    importance: int | None = None
    try:
        import json as _json
        # Extrai o bloco JSON mesmo que o modelo adicione texto antes/depois
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = _json.loads(raw[start:end])
            if isinstance(parsed.get("thought"), str) and len(parsed["thought"]) >= 5:
                thought = parsed["thought"].strip()
            raw_imp = parsed.get("importance")
            if isinstance(raw_imp, (int, float)):
                importance = max(1, min(10, int(raw_imp)))
    except Exception:
        pass  # fallback: usa raw como thought, importance=None

    if len(thought) < 10:
        return

    tags = ["event_discovery", title[:40]]
    if _diversity_mode:
        tags.append("diversity_exploration")
    await save_memory(type=mem_type, content=thought, tags=tags, importance=importance)
    log.info(
        "knowledge_worker.reflection: nota salva (type=%s, importance=%s) sobre '%s'",
        mem_type, importance, title[:60],
    )


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
