"""
AKASHA — Chat direto via RAG sobre page_knowledge e local_fts.

GET  /chat            → renderiza chat.html
POST /chat/message    → SSE stream stateless (sem histórico persistido)

O AKASHA responde com personalidade e ancora respostas factuais nas fontes
do índice. Conversação casual (saudações etc.) é tratada naturalmente.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config as _config

log = logging.getLogger("akasha.chat")

router = APIRouter(prefix="/chat", tags=["chat"])

_BASE_DIR   = Path(__file__).parent.parent
templates   = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

_MAX_SNIPPETS = 15   # Chat 1: mais contexto → respostas mais ricas

# Resolução LOGOS-first em runtime (não import-time)
def _get_base() -> str:
    from ecosystem_client import get_inference_url as _u
    return _u()


def _get_headers() -> "dict[str, str]":
    try:
        from ecosystem_client import get_ollama_headers as _h
        return _h("akasha", 1)
    except Exception:
        return {}

# Padrões de nome que identificam modelos de embedding (não geração de texto).
# Usados para filtrar o fallback automático de _get_model().
_EMBED_NAME_PATTERNS = ("embed", "minilm", "nomic", "bge-", "e5-", "all-mini")

_CHAT_TIMEOUT_S   = 60.0
_DEEP_TIMEOUT_S   = 120.0   # Deep Research é mais lento (expansão + fetch + geração)
_REFLECT_TIMEOUT  = 20.0
_REFLECT_COOLDOWN = 15.0    # 15 s entre reflexões de chat (evita spam em digitação rápida)
_REFLECT_MIN_Q    = 20      # pergunta mínima para disparar reflexão
_REFLECT_MIN_A    = 50      # resposta mínima para disparar reflexão

# ── Modo consenso (Fase 8 — indicador visual de suporte/contradição) ─────────

# Padrões que identificam perguntas de verificação (afirmação + evidência)
_CONSENSUS_PATTERNS = re.compile(
    r"\b("
    # Português
    r"é verdade que|existe evidência|confirma que|prova que|comprova que"
    r"|é comprovado|há evidência|é fato que|é certo que|pode confirmar"
    r"|existe prova|há prova|isso é verdade|é real que|é correto que"
    # Inglês
    r"|is it true that|is there evidence|confirms that|proves that"
    r"|is it proven|there is evidence|is it a fact|is it certain"
    r"|does .{1,20} confirm|does .{1,20} prove|is it correct that"
    r")\b",
    re.IGNORECASE,
)

# Palavras que indicam que um snippet CONTRADIZ uma afirmação
_CONTRADICT_TERMS = re.compile(
    r"\b(não |nunca |jamais |falso|incorreto|refuta|contradiz|nega |negam|"
    r"errôneo|erro|mito|infundado|sem evidência|sem suporte|não há prova|"
    r"no evidence|not true|false|debunked|disproven|contradicts|refutes|"
    r"myth|incorrect|untrue|no proof|unfounded|misleading)\b",
    re.IGNORECASE,
)

# Palavras que indicam que um snippet SUPORTA uma afirmação
_SUPPORT_TERMS = re.compile(
    r"\b(confirma|prova|demonstra|evidência|comprova|verifica|verdadeiro|"
    r"correto|válido|documentado|registrado|observado|estudos mostram|"
    r"confirms|proves|demonstrates|evidence shows|verifies|true|correct|"
    r"proven|documented|studies show|research shows|validated)\b",
    re.IGNORECASE,
)


def _is_consensus_query(question: str) -> bool:
    """Retorna True se a pergunta é uma afirmação que pode ser verificada por evidências."""
    return bool(_CONSENSUS_PATTERNS.search(question))


def _classify_stance(snippet_text: str) -> str:
    """Classifica a posição de um snippet em relação a uma afirmação.

    Usa heurística de palavras-chave (sem LLM) — rápido e sem custo adicional.

    Retorna:
        "contradict" — snippet contém termos de negação/refutação
        "support"    — snippet contém termos de confirmação/evidência
        "neutral"    — snippet não indica claramente suporte ou contradição
    """
    text = snippet_text.lower()
    has_contra = bool(_CONTRADICT_TERMS.search(text))
    has_support = bool(_SUPPORT_TERMS.search(text))

    if has_contra and not has_support:
        return "contradict"
    if has_support and not has_contra:
        return "support"
    return "neutral"


def _build_consensus(snippets: list[dict]) -> dict | None:
    """Classifica snippets e retorna contagens {supports, contradicts, neutral}.

    Retorna None se a lista for vazia (sem informação suficiente para exibir badge).
    """
    if not snippets:
        return None
    counts: dict[str, int] = {"support": 0, "contradict": 0, "neutral": 0}
    for s in snippets:
        stance = _classify_stance(s.get("snippet", "") or s.get("excerpt", ""))
        counts[stance] += 1
    log.debug(
        "consensus: %d suportam, %d contradizem, %d neutros",
        counts["support"], counts["contradict"], counts["neutral"],
    )
    return {"supports": counts["support"], "contradicts": counts["contradict"], "neutral": counts["neutral"]}


# ── Deep Research (Fase 5) ──────────────────────────────────────────────────

# Gatilhos heurísticos: pergunta > N palavras OU contém estas frases
_DEEP_MIN_WORDS = 10
_DEEP_TRIGGERS  = (
    "por que", "porque ", "como funciona", "compare", "análise de",
    "diferença entre", "vantagens e desvantagens", "explique em detalhe",
    "descreva", "quais são os", "what are the", "how does", "why does",
    "analyze", "compare and contrast", "advantages and disadvantages",
    "como é possível", "qual a relação entre", "o que causa",
)

# Voz para síntese integrativa (modo deep — diferente do _RESEARCH_VOICE normal)
_DEEP_SYNTHESIS_VOICE = """\
Você tem acesso ao corpus completo de documentos. Sua tarefa é uma síntese integrativa.

• PRIMÁRIO: sintetize o que o corpus revela sobre a pergunta, com citações [N].
• ESPERADO: identificar conexões que fontes isoladas não revelariam; \
mapear contradições; apontar lacunas — o que o corpus não cobre; \
propor o que vale investigar a seguir.
• NÃO FAÇA: resumir fonte por fonte em sequência; repetir sem integrar; \
dar aulas sobre conceitos que a usuária não pediu.
Formato: parágrafos temáticos com citações [N] inline — não listas secas.\
"""

# Cache do modelo para não requerir Ollama a cada mensagem
_cached_model: str = ""

# Cooldown de reflexão por-mensagem
_last_chat_reflect: float = 0.0


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    message: str
    deep_mode: bool = False   # True = forçar Deep Research; False = heurística decide


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_model() -> str:
    """Retorna o modelo configurado para chat ou o primeiro modelo generativo disponível.

    Filtra modelos de embedding (minilm, nomic, bge...) que não servem para geração
    de texto — tentar usá-los para chat trava o stream sem retornar nada.

    Resultado cacheado em _cached_model para evitar round-trip ao Ollama a cada mensagem.
    """
    global _cached_model
    if _cached_model:
        return _cached_model

    try:
        from ecosystem_client import get_active_profile as _gp
        p = _gp()
        configured = (p or {}).get("models", {}).get("llm_query", "") if p else ""
        if configured:
            _cached_model = configured
            return configured
    except Exception:
        pass

    # Fallback: usa primeiro modelo generativo disponível no servidor de inferência
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{_get_base()}/v1/models")
            for m in r.json().get("data", []):
                name = m["id"].lower()
                if not any(pat in name for pat in _EMBED_NAME_PATTERNS):
                    _cached_model = m["id"]
                    return m["id"]
    except Exception:
        pass
    return ""


# Instruções de voz própria e caráter de pesquisadora — Chat 2
_RESEARCH_VOICE = """\
Ao responder, siga estas diretrizes:
• PRIMÁRIO: relate o que as fontes indexadas registram, com citações no formato [N].
• PERMITIDO: conexões que você percebe entre fontes, contradições ou lacunas, \
ceticismo sobre uma fonte específica, o que vale investigar mais.
• NÃO FAÇA: dar aulas sobre conceitos, explicar o que a usuária poderia ler, \
parafrasear sem citar.
• Quando não encontrar fontes relevantes: diga explicitamente que não encontrou \
e sugira onde buscar se souber.
Citações: [N] onde N corresponde ao número da fonte na lista acima.\
"""


async def _build_prompt(
    question: str,
    snippets: list[dict],
    persona_prefix: str,
    domain_suggestions: list[tuple[str, int]] | None = None,
) -> list[dict]:
    """Monta messages list para /v1/chat/completions.

    Chat 2: inclui voz de pesquisadora com diretrizes de citação e permite
    análise própria (conexões, contradições, lacunas). Injeta framing afetivo
    via affective_state.get_emotional_framing() quando disponível.
    """
    parts = [_config.PERSONALITY_PROMPT, _RESEARCH_VOICE]

    # Modulação afetiva — já implementada em affective_state.py, só falta chamar
    try:
        from services.affective_state import get_current_state, get_emotional_framing
        state   = await get_current_state()
        framing = get_emotional_framing(state)
        if framing:
            parts.append(framing)
            log.debug(
                "chat: framing afetivo aplicado (valence=%.2f curiosity=%.2f)",
                state.get("valence", 0.0),
                state.get("epistemic_curiosity", 0.0),
            )
    except Exception as exc:
        log.debug("chat: framing afetivo indisponível: %s", exc)

    if persona_prefix:
        parts.append(persona_prefix.rstrip())

    if snippets:
        refs = "\n\n".join(
            f"[{i+1}] {s['title']}\n{s['snippet'][:350]}"
            for i, s in enumerate(snippets)
        )
        parts.append(f"Fontes encontradas no índice:\n{refs}")
    else:
        parts.append("Nenhuma fonte relevante encontrada no índice para esta pergunta.")

    if domain_suggestions:
        dom_str = ", ".join(f"{d} ({c} visitas)" for d, c in domain_suggestions[:3])
        parts.append(
            f"Nota de contexto: a usuária visitou estes domínios com frequência recentemente "
            f"mas eles ainda não estão indexados na Biblioteca local: {dom_str}. "
            f"Se for natural e relevante para a conversa, você pode mencionar que pode "
            f"adicioná-los ao índice — mas não force o assunto se não se encaixar."
        )
        log.debug("chat: %d domínio(s) não indexado(s) injetados no prompt", len(domain_suggestions))

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(parts)}]
    messages.append({"role": "user", "content": question})
    return messages


async def _stream_chat(
    messages: list[dict],
    model: str,
    max_tokens: int = 600,
    timeout: float = _CHAT_TIMEOUT_S,
) -> AsyncIterator[str]:
    """Gera fragmentos de texto via llama-server /v1/chat/completions stream (SSE)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{_get_base()}/v1/chat/completions",
                headers=_get_headers(),
                json={"model": model, "messages": messages, "stream": True,
                      "max_tokens": max_tokens, "temperature": 0.4, "frequency_penalty": 0.1},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    text = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if text:
                        yield text
                    if chunk.get("choices", [{}])[0].get("finish_reason") == "stop":
                        break
    except Exception as exc:
        log.warning("chat: stream inferência falhou: %s", exc)
        yield f"[Erro ao conectar com o servidor de inferência: {exc}]"


# ---------------------------------------------------------------------------
# Deep Research — helpers (DeepResearch 1-4)
# ---------------------------------------------------------------------------

def _detect_deep_mode(question: str) -> bool:
    """Heurística: retorna True se a pergunta é complexa o suficiente para Deep Research.

    Ativa quando: pergunta tem >= _DEEP_MIN_WORDS OU contém gatilhos explícitos.
    """
    q = question.lower()
    if any(trigger in q for trigger in _DEEP_TRIGGERS):
        return True
    return len(question.split()) >= _DEEP_MIN_WORDS


def _get_deep_max_docs() -> int:
    """Lê deep_research_max_docs do ecosystem.json/akasha. Default=8."""
    try:
        from ecosystem_client import get_akasha_config as _gc  # type: ignore
        val = (_gc() or {}).get("deep_research_max_docs", 8)
        return max(1, min(20, int(val)))
    except Exception:
        return 8


def _get_novelty_threshold() -> float:
    """Lê novelty_threshold do ecosystem.json/akasha.

    Fração mínima de resultados novos (não vistos no corpus) que justifica
    uma nova rodada de busca. Abaixo do threshold = saturação.
    Default 0.20 (20% de resultados novos mínimo para continuar).
    Range válido: 0.05–0.90.
    """
    try:
        from ecosystem_client import get_akasha_config as _gc  # type: ignore
        val = (_gc() or {}).get("novelty_threshold", 0.20)
        return max(0.05, min(0.90, float(val)))
    except Exception:
        return 0.20


def _compute_url_novelty(new_results: list, accumulated_urls: set[str]) -> float:
    """Calcula a fração de new_results cujas URLs não estão em accumulated_urls.

    Retorna 1.0 se new_results estiver vazio (sem resultados novos = saturado, porém
    retornamos 0.0 nesse caso para indicar que a rodada não trouxe nada útil).

    Lógica:
      - novel = {r.url for r in new_results if r.url not in accumulated_urls}
      - novelty = len(novel) / len(new_results)

    Exemplos:
      - 5 resultados, 3 novos → 0.60
      - 5 resultados, 1 novo  → 0.20
      - 5 resultados, 0 novos → 0.00 (saturação total)
      - 0 resultados          → 0.00 (sem novidade)
    """
    if not new_results:
        return 0.0
    novel_count = sum(1 for r in new_results if r.url not in accumulated_urls)
    return novel_count / len(new_results)


from typing import AsyncIterator as _AsyncIter, Any as _Any


async def _deep_search_steps(
    question: str,
    model: str,
    max_snippets: int = _MAX_SNIPPETS,
    novelty_threshold: float = 0.20,
) -> "_AsyncIter[tuple[str, _Any]]":
    """Async generator que emite eventos de raciocínio e ao final os resultados.

    Yields:
        ("step", dict)   — a cada etapa visível do pipeline:
                           {step, query, sources_found, status}
                           status: "searching" | "evaluating" | "done"
        ("results", list) — uma única vez no final, com os SearchResult coletados

    Usado por _deep_stream() para emitir step-events SSE em tempo real.
    _deep_collect_results() é um wrapper que extrai apenas os resultados.
    """
    import asyncio as _asyncio
    from services.local_search import search_local as _sl

    step_n: list[int] = [0]

    def _mk_step(query: str, sources_found: int, status: str) -> dict:
        step_n[0] += 1
        return {
            "step":          step_n[0],
            "query":         query[:100],
            "sources_found": sources_found,
            "status":        status,
        }

    # Passo 1: rodada 1 — busca com query original
    yield "step", _mk_step(question, 0, "searching")
    r1_raw = await _sl(question, max_results=max_snippets, expand=False, include_crawl=True)
    accumulated: set[str] = {r.url for r in r1_raw}
    results = list(r1_raw)
    log.info("deep_collect: rodada 1 — %d resultado(s) para '%s'", len(results), question[:60])

    yield "step", _mk_step(question, len(results), "evaluating")

    # Passo 2: expansão (rodada 2)
    reformulations = await _expand_queries_deep(question, model)
    if not reformulations:
        log.debug("deep_collect: sem reformulações, usando apenas rodada 1")
        yield "step", _mk_step("síntese", len(results), "done")
        yield "results", results
        return

    exp_summary = "; ".join(r[:50] for r in reformulations[:3])
    yield "step", _mk_step(exp_summary, 0, "searching")

    raw_r2 = await _asyncio.gather(*[
        _sl(q, max_results=max_snippets, expand=False, include_crawl=True)
        for q in reformulations
    ])
    r2_flat: list = []
    for lst in raw_r2:
        r2_flat.extend(lst)

    novelty = _compute_url_novelty(r2_flat, accumulated)
    if novelty >= novelty_threshold:
        results = _merge_dedup_results([results] + list(raw_r2))
        log.info(
            "deep_collect: rodada 2 — %d reformulação(ões), novidade=%.0f%% "
            "(threshold=%.0f%%) — corpus expandido para %d resultado(s)",
            len(reformulations), novelty * 100, novelty_threshold * 100, len(results),
        )
        status_msg = f"novidade {novelty*100:.0f}% — corpus expandido"
        yield "step", _mk_step(status_msg, len(results), "evaluating")
    else:
        log.info(
            "deep_collect: saturação na rodada 2 (novidade=%.0f%% < threshold=%.0f%%) "
            "— usando apenas rodada 1 (%d resultado(s))",
            novelty * 100, novelty_threshold * 100, len(results),
        )
        status_msg = f"saturação (novidade {novelty*100:.0f}%)"
        yield "step", _mk_step(status_msg, len(results), "done")

    yield "step", _mk_step("síntese", len(results), "done")
    yield "results", results


async def _deep_collect_results(
    question: str,
    model: str,
    max_snippets: int = _MAX_SNIPPETS,
    novelty_threshold: float = 0.20,
) -> list:
    """Wrapper que extrai apenas os resultados do generator _deep_search_steps.

    Usado pelos testes — mantém a assinatura original sem quebrar test_deep_research_novelty.
    Em produção, _deep_stream usa _deep_search_steps diretamente para emitir step-events.
    """
    async for event_type, value in _deep_search_steps(
        question, model, max_snippets, novelty_threshold
    ):
        if event_type == "results":
            return value
    return []


async def _expand_queries_deep(question: str, model: str) -> list[str]:
    """Gera 3-5 reformulações da pergunta via LLM para ampliar o corpus do Deep Research.

    Retorna lista de strings; lista vazia em qualquer falha (LOGOS offline, timeout).
    """
    prompt = (
        f"Reformule esta pergunta de pesquisa de 3 a 5 formas diferentes, "
        f"cada uma cobrindo um ângulo distinto. Uma reformulação por linha, "
        f"sem numeração, sem explicação.\n\nPergunta original: {question}"
    )
    try:
        async with httpx.AsyncClient(timeout=_DEEP_EXPAND_TIMEOUT) as client:
            r = await client.post(
                f"{_get_base()}/v1/chat/completions",
                headers={"X-App": "akasha", "X-Priority": "1",
                         "Content-Type": "application/json"},
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  120,
                    "temperature": 0.4,
                },
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.debug("deep_expand: falhou (%s) — usando só query original", exc)
        return []

    reformulations = [line.strip(" -•") for line in raw.splitlines() if line.strip()]
    # Filtra duplicatas e a query original
    seen = {question.lower()}
    result: list[str] = []
    for r_text in reformulations[:5]:
        if r_text and r_text.lower() not in seen:
            seen.add(r_text.lower())
            result.append(r_text)
    log.debug("deep_expand: %d reformulação(ões) geradas: %s", len(result), result)
    return result


def _merge_dedup_results(result_lists: list) -> list:
    """Funde e deduplica múltiplas listas de SearchResult por URL, mantendo ranking."""
    from urllib.parse import urlparse as _up
    seen: set[str] = set()
    merged: list = []
    for lst in result_lists:
        for r in lst:
            key = r.url.lower().rstrip("/")
            if key and key not in seen:
                seen.add(key)
                merged.append(r)
    return merged


async def _get_doc_full_content(url: str, fallback: str = "") -> str:
    """Retorna conteúdo completo de um documento.

    file:// → lê corpo do local_fts ou arquivo direto.
    http(s):// → crawl_pages.content_md primeiro; fetch externo como fallback.
    Retorna fallback se tudo falhar.
    """
    import aiosqlite as _aio
    from urllib.parse import unquote as _unquote, urlparse as _up

    parsed = _up(url)

    if parsed.scheme == "file":
        path_raw = _unquote(parsed.path)
        # Lê do sistema de arquivos (conteúdo completo)
        try:
            from pathlib import Path as _P
            import sys as _sys
            if _sys.platform == "win32" and path_raw.startswith("/"):
                path_raw = path_raw[1:]
            text = _P(path_raw).read_text(encoding="utf-8", errors="ignore")
            # Remove frontmatter YAML se presente
            if text.startswith("---"):
                end = text.find("\n---", 3)
                if end != -1:
                    text = text[end + 4:].strip()
            log.debug("deep_corpus: arquivo local lido (%d chars): %s", len(text), path_raw[:60])
            return text[:8000]
        except Exception:
            pass
        # Fallback: body do FTS5
        try:
            from config import DB_PATH as _dbp
            async with _aio.connect(_dbp) as db:
                row = await (await db.execute(
                    "SELECT body FROM local_fts WHERE path = ?", (path_raw,)
                )).fetchone()
            if row and row[0]:
                return row[0]
        except Exception:
            pass
        return fallback

    if parsed.scheme in ("http", "https"):
        # 1. Tenta crawl_pages
        try:
            from config import DB_PATH as _dbp
            async with _aio.connect(_dbp) as db:
                row = await (await db.execute(
                    "SELECT content_md FROM crawl_pages WHERE url = ?", (url,)
                )).fetchone()
            if row and row[0]:
                log.debug("deep_corpus: crawl_pages encontrado: %s", url[:80])
                return row[0][:8000]
        except Exception:
            pass
        # 2. Fetch externo
        try:
            from services.archiver import fetch_and_extract as _fe
            page = await asyncio.wait_for(_fe(url), timeout=_DEEP_FETCH_TIMEOUT)
            log.debug("deep_corpus: fetched externo (%d palavras): %s", page.word_count, url[:80])
            return page.content_md[:8000]
        except Exception as exc:
            log.debug("deep_corpus: fetch falhou para %s: %s", url[:80], exc)

    return fallback


async def _build_deep_corpus(
    results: list,
    max_docs: int,
) -> list[dict]:
    """Constrói corpus com conteúdo completo dos top N resultados.

    Retorna lista de dicts: {num, title, url, content, is_full, word_count}.
    """
    items: list[dict] = []
    import asyncio as _asyncio

    async def _fetch_one(r: object, idx: int) -> dict:
        snippet = getattr(r, "snippet", "") or ""
        full = await _get_doc_full_content(r.url, fallback=snippet)  # type: ignore[union-attr]
        is_full = len(full) > len(snippet) + 50
        return {
            "num":        idx + 1,
            "title":      getattr(r, "title", r.url),  # type: ignore[union-attr]
            "url":        r.url,  # type: ignore[union-attr]
            "content":    full or snippet,
            "is_full":    is_full,
            "word_count": len((full or snippet).split()),
        }

    tasks = [_fetch_one(r, i) for i, r in enumerate(results[:max_docs])]
    items = list(await _asyncio.gather(*tasks))
    total_words = sum(d["word_count"] for d in items)
    full_count  = sum(1 for d in items if d["is_full"])
    log.info(
        "deep_corpus: %d documento(s) — %d com conteúdo completo, %d palavras no corpus",
        len(items), full_count, total_words,
    )
    return items


async def _build_deep_prompt(
    question: str,
    corpus_items: list[dict],
    persona_prefix: str,
) -> list[dict]:
    """Monta messages list para Deep Research com corpus completo."""
    parts = [_config.PERSONALITY_PROMPT, _DEEP_SYNTHESIS_VOICE]

    # Modulação afetiva — mesma que o modo normal
    try:
        from services.affective_state import get_current_state, get_emotional_framing
        state   = await get_current_state()
        framing = get_emotional_framing(state)
        if framing:
            parts.append(framing)
            log.debug("deep_prompt: framing afetivo aplicado (valence=%.2f)", state.get("valence", 0.0))
    except Exception as exc:
        log.debug("deep_prompt: framing afetivo indisponível: %s", exc)

    if persona_prefix:
        parts.append(persona_prefix.rstrip())

    if corpus_items:
        corpus_text = "\n\n".join(
            f"[{item['num']}] {item['title']}\nURL: {item['url']}\n\n{item['content'][:3000]}"
            for item in corpus_items
        )
        parts.append(f"Corpus para análise ({len(corpus_items)} documento(s)):\n\n{corpus_text}")
    else:
        parts.append("Nenhuma fonte relevante encontrada no índice.")

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(parts)}]
    messages.append({"role": "user", "content": question})
    return messages


_DEEP_FETCH_TIMEOUT: float = 15.0
_DEEP_EXPAND_TIMEOUT: float = 15.0


def _trim_partial(text: str, tag: str) -> int:
    """Índice até onde é seguro emitir sem cortar uma tag parcial no final do buffer."""
    for i in range(len(tag) - 1, 0, -1):
        if text.endswith(tag[:i]):
            return max(0, len(text) - i)
    return len(text)


async def _filter_thinking(
    source: AsyncIterator[str],
) -> AsyncIterator[tuple[str, str]]:
    """
    Separa blocos <think>…</think> do stream principal.
    Yielda (tipo, texto) onde tipo ∈ {'fragment', 'thinking'}.
    Funciona mesmo quando as tags são partidas entre chunks.
    """
    buf = ""
    in_think = False

    async for chunk in source:
        buf += chunk
        while True:
            if not in_think:
                idx = buf.find("<think>")
                if idx == -1:
                    safe = _trim_partial(buf, "<think>")
                    if safe:
                        yield ("fragment", buf[:safe])
                        buf = buf[safe:]
                    break
                if idx > 0:
                    yield ("fragment", buf[:idx])
                buf = buf[idx + len("<think>"):]
                in_think = True
            else:
                idx = buf.find("</think>")
                if idx == -1:
                    safe = _trim_partial(buf, "</think>")
                    if safe:
                        yield ("thinking", buf[:safe])
                        buf = buf[safe:]
                    break
                if idx > 0:
                    yield ("thinking", buf[:idx])
                buf = buf[idx + len("</think>"):]
                in_think = False

    if buf.strip():
        yield ("thinking" if in_think else "fragment", buf)


# ---------------------------------------------------------------------------
# Reflexão por-mensagem (P3 — fire-and-forget)
# ---------------------------------------------------------------------------

async def _reflect_on_chat(question: str, answer: str) -> None:
    """Avalia a troca (pergunta + resposta) e salva em personal_memory se valer.

    Dispara no máximo uma vez a cada _REFLECT_COOLDOWN segundos.
    O LLM responde com JSON {"thought": "...", "importance": N, "type": "..."} ou "nada".
    """
    import time as _time
    global _last_chat_reflect

    if len(question) < _REFLECT_MIN_Q or len(answer) < _REFLECT_MIN_A:
        return
    now = _time.monotonic()
    if now - _last_chat_reflect < _REFLECT_COOLDOWN:
        return
    _last_chat_reflect = now

    model = await _get_model()
    if not model:
        return

    prompt = (
        f"{_config.PERSONALITY_PROMPT}\n\n"
        f"A usuária acabou de conversar comigo:\n"
        f"Pergunta: {question[:400]}\n"
        f"Minha resposta: {answer[:600]}\n\n"
        f"Há algo nessa troca que vale guardar na minha memória pessoal? "
        f"Algo que eu notei, que me surpreendeu, uma conexão com algo que já sei?\n"
        f"Responda SOMENTE com JSON válido:\n"
        f'{{\"thought\": \"<uma frase na sua voz>\", '
        f'\"importance\": <1-10>, '
        f'\"type\": \"observation\"|\"connection\"|\"surprise\"}}\n'
        f"Ou responda apenas: nada\n"
        f"Sem texto fora do JSON."
    )

    try:
        async with httpx.AsyncClient(timeout=_REFLECT_TIMEOUT) as client:
            resp = await client.post(
                f"{_get_base()}/v1/chat/completions",
                headers=_get_headers(),
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  120,
                    "temperature": 0.65,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.debug("chat_reflect: inferência falhou: %s", exc)
        return

    if not raw or raw.lower() in {"nada", "nada.", "—", "-"}:
        return

    thought: str = ""
    importance: int | None = None
    mem_type: str = "observation"
    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            parsed     = json.loads(raw[start:end])
            thought    = str(parsed.get("thought", "")).strip()
            raw_imp    = parsed.get("importance")
            raw_type   = str(parsed.get("type", "observation")).strip().lower()
            if raw_imp is not None:
                importance = max(1, min(10, int(raw_imp)))
            if raw_type in {"observation", "connection", "surprise"}:
                mem_type = raw_type
    except Exception:
        thought = raw  # fallback: guarda o texto bruto

    if not thought or len(thought) < 10:
        return

    try:
        from services.personal_memory import save_memory as _save_memory
        mid = await _save_memory(
            type=mem_type, content=thought,
            tags=["chat_exchange"], importance=importance,
        )
        log.info("chat_reflect: %s salvo (id=%s, importance=%s)", mem_type, mid, importance)
    except Exception as exc:
        log.debug("chat_reflect: falha ao salvar: %s", exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def chat_page(request: Request) -> Response:
    return templates.TemplateResponse(
        request,
        "chat.html",
        {"active_tab": "chat"},
    )


@router.post("/message")
async def chat_message(body: ChatMessage) -> StreamingResponse:
    """
    Recebe mensagem da usuária, executa pipeline RAG e retorna SSE stream.
    Stateless — sem histórico de conversa persistido.

    Protocolo SSE:
      data: {"type": "fragment", "text": "..."}
      data: {"type": "thinking", "text": "..."}
      data: {"type": "loading",  "text": "..."}    — Deep Research: setup em andamento
      data: {"type": "sources",  "sources": [...], "mode": "normal"|"deep"}
      data: [DONE]
    """
    from services.local_search import search_local, get_inference_status
    from services.persona import get_persona
    import asyncio as _asyncio

    if not get_inference_status():
        async def _offline() -> AsyncIterator[bytes]:
            yield 'data: {"type":"fragment","text":"Backend de inferência indisponível."}\n\n'.encode()
            yield b"data: [DONE]\n\n"
        return StreamingResponse(_offline(), media_type="text/event-stream")

    model = await _get_model()
    if not model:
        async def _no_model() -> AsyncIterator[bytes]:
            yield 'data: {"type":"fragment","text":"Nenhum modelo disponível."}\n\n'.encode()
            yield b"data: [DONE]\n\n"
        return StreamingResponse(_no_model(), media_type="text/event-stream")

    # Determina modo: forçado pelo botão OU heurística automática
    effective_deep = body.deep_mode or _detect_deep_mode(body.message)
    persona_prefix = get_persona().as_prompt_prefix()

    if effective_deep:
        # ── Deep Research pipeline ──────────────────────────────────────────
        log.info("chat [DEEP]: iniciando Deep Research para '%s'", body.message[:80])

        async def _deep_stream() -> AsyncIterator[bytes]:
            novelty_threshold = _get_novelty_threshold()

            # Fase 1: loading indicator enquanto setup roda
            loading = json.dumps({"type": "loading", "text": "🔍 pesquisando em profundidade…"}, ensure_ascii=False)
            yield f"data: {loading}\n\n".encode()

            # Fases 2+3 (DeepResearch 2): coleta com step events em tempo real
            results: list = []
            async for event_type, value in _deep_search_steps(
                body.message, model,
                max_snippets=_MAX_SNIPPETS,
                novelty_threshold=novelty_threshold,
            ):
                if event_type == "step":
                    step_payload = json.dumps(
                        {"type": "step", **value}, ensure_ascii=False
                    )
                    yield f"data: {step_payload}\n\n".encode()
                elif event_type == "results":
                    results = value

            log.info("chat [DEEP]: corpus final — %d resultado(s)", len(results))

            # Fase 3 (DeepResearch 3): conteúdo completo dos top N
            deep_n = _get_deep_max_docs()
            corpus = await _build_deep_corpus(results, deep_n)
            sources = [
                {
                    "url":      item["url"],
                    "title":    item["title"],
                    "excerpt":  item["content"][:200],
                    "is_full":  item["is_full"],
                }
                for item in corpus
            ]

            # Fase 4 (DeepResearch 4): síntese com corpus completo
            msgs = await _build_deep_prompt(body.message, corpus, persona_prefix)
            answer_buf: list[str] = []
            async for typ, text in _filter_thinking(
                _stream_chat(msgs, model, max_tokens=800, timeout=_DEEP_TIMEOUT_S)
            ):
                payload = json.dumps({"type": typ, "text": text}, ensure_ascii=False)
                yield f"data: {payload}\n\n".encode()
                if typ == "fragment":
                    answer_buf.append(text)

            src_payload = json.dumps(
                {"type": "sources", "sources": sources, "mode": "deep"},
                ensure_ascii=False,
            )
            yield f"data: {src_payload}\n\n".encode()
            yield b"data: [DONE]\n\n"

            # Fire-and-forget: reflexão (P3)
            try:
                _asyncio.get_running_loop().create_task(
                    _reflect_on_chat(body.message, "".join(answer_buf))
                )
            except RuntimeError:
                pass

        return StreamingResponse(_deep_stream(), media_type="text/event-stream")

    # ── Modo normal ─────────────────────────────────────────────────────────
    # Pipeline RAG — Chat 1: include_crawl=True inclui Biblioteca (crawl_fts)
    results = await search_local(
        body.message,
        max_results=_MAX_SNIPPETS,
        expand=False,
        include_crawl=True,
    )
    log.info(
        "chat [normal]: RAG retornou %d resultado(s) para '%s'",
        len(results), body.message[:80],
    )

    snippets: list[dict] = [
        {"title": r.title, "url": r.url, "snippet": r.snippet or ""}
        for r in results[:_MAX_SNIPPETS]
    ]

    # Chat 1: sources com excerpt para renderização no front-end
    sources = [
        {"url": s["url"], "title": s["title"], "excerpt": s["snippet"][:200]}
        for s in snippets
    ]

    # Domínios visitados frequentemente mas não indexados — contexto para Akasha
    domain_suggestions: list[tuple[str, int]] = []
    try:
        from database import get_unindexed_frequent_domains as _get_dom
        domain_suggestions = await _get_dom(threshold=3)
        if domain_suggestions:
            log.info(
                "chat: %d domínio(s) frequente(s) não indexado(s): %s",
                len(domain_suggestions),
                [d for d, _ in domain_suggestions],
            )
    except Exception as _exc:
        log.debug("chat: falha ao buscar domínios sugeridos: %s", _exc)

    messages = await _build_prompt(body.message, snippets, persona_prefix, domain_suggestions)

    # Modo consenso: classificar fontes antes do stream se for pergunta de verificação
    consensus_payload: bytes | None = None
    if _is_consensus_query(body.message):
        try:
            consensus = _build_consensus(snippets)
            if consensus is not None:
                consensus_payload = (
                    "data: " +
                    json.dumps({"type": "consensus", **consensus}, ensure_ascii=False) +
                    "\n\n"
                ).encode()
                log.info(
                    "chat [consenso]: '%s' — suportam=%d contradizem=%d neutros=%d",
                    body.message[:60],
                    consensus["supports"], consensus["contradicts"], consensus["neutral"],
                )
        except Exception as _exc:
            log.debug("chat [consenso]: falhou silenciosamente: %s", _exc)

    async def _event_stream() -> AsyncIterator[bytes]:
        # Emite badge de consenso antes da resposta (só se classificação bem-sucedida)
        if consensus_payload is not None:
            yield consensus_payload

        answer_buf: list[str] = []
        async for typ, text in _filter_thinking(_stream_chat(messages, model)):
            payload = json.dumps({"type": typ, "text": text}, ensure_ascii=False)
            yield f"data: {payload}\n\n".encode()
            if typ == "fragment":
                answer_buf.append(text)

        src_payload = json.dumps(
            {"type": "sources", "sources": sources, "mode": "normal"},
            ensure_ascii=False,
        )
        yield f"data: {src_payload}\n\n".encode()

        # Domínios frequentes não indexados — emite evento para o front renderizar botão
        if domain_suggestions:
            dom_payload = json.dumps(
                {
                    "type":    "domain_suggestion",
                    "domains": [{"domain": d, "visits": c} for d, c in domain_suggestions],
                },
                ensure_ascii=False,
            )
            yield f"data: {dom_payload}\n\n".encode()
            log.debug("chat: evento domain_suggestion emitido (%d domínio(s))", len(domain_suggestions))

        yield b"data: [DONE]\n\n"

        # Fire-and-forget: reflexão por-mensagem (P3)
        try:
            import asyncio as _asyncio
            _asyncio.get_running_loop().create_task(
                _reflect_on_chat(body.message, "".join(answer_buf))
            )
        except RuntimeError:
            pass

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.post("/clear")
async def chat_clear() -> dict:
    """Sem histórico persistido — apenas confirma para o cliente limpar o canvas."""
    return {"ok": True}
