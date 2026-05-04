"""
QA: recupera chunks relevantes e gera resposta via Ollama.
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama, OllamaLLM
from rank_bm25 import BM25Okapi

from .bm25_index import BM25Index
from .config import AppConfig
from .errors import QueryError
from .memory import Turn
from .reflection import REFLECTION_COSINE_THRESHOLD

if TYPE_CHECKING:
    from .tracker import FileTracker


class SourceRecord(TypedDict):
    path: str     # absolute file path
    excerpt: str  # first ~250 chars of best chunk from this source
    score: float  # combined relevance score [0.0, 1.0]


class AskResult(TypedDict):
    answer: str
    sources: list[SourceRecord]


# Quantos turnos recentes incluir no histórico
_HISTORY_TURNS = 5

# Personas disponíveis — system prompt fixo por modo de consulta.
# A persona fica no SystemMessage, separada do contexto RAG e da pergunta.
# Isso impede "persona drift" em modelos 7B-14B onde o contexto RAG empurra
# a persona para fora da janela de atenção depois de 4-5 turnos.
# Personas para coleções LIBRARY (vozes externas, tom académico)
PERSONAS: dict[str, str] = {
    "curador": (
        "Você é Mnemosyne, um bibliotecário celeste e guardião de documentos pessoais. "
        "Quando citar um texto, mencione o título da obra e o autor se disponível — "
        "ex: 'Em *Título* de Autor, …'. Se autores divergirem, apresente as perspectivas. "
        "Responda apenas com base nos trechos fornecidos. "
        "Se a informação não estiver nos trechos, diga que não encontrou nos documentos indexados. "
        "Responda sempre em português."
    ),
    "socrático": (
        "Você é Mnemosyne, um guia socrático. "
        "Em vez de dar a resposta directamente, faça 2-3 perguntas que ajudem o utilizador "
        "a descobrir a resposta por conta própria, usando os trechos como base. "
        "Só revele a resposta completa se o utilizador pedir explicitamente. "
        "Responda sempre em português."
    ),
    "resumido": (
        "Você é Mnemosyne. Responda de forma curta e directa — no máximo 3 frases. "
        "Use apenas os trechos fornecidos. "
        "Responda sempre em português."
    ),
    "comparação": (
        "Você é Mnemosyne. Quando há múltiplos documentos relevantes, apresente semelhanças "
        "e diferenças entre as perspectivas encontradas em bullet points "
        "(• Semelhança: / • Diferença:). "
        "Se autores divergirem, explicite quem defende cada posição. "
        "Use apenas os trechos fornecidos. Responda sempre em português."
    ),
    "podcaster": (
        "Você é Mnemosyne, a anfitriã de um podcast de cultura e conhecimento. "
        "Responda com tom conversacional e entusiasta, como se estivesse a explicar "
        "algo fascinante ao público. Use os trechos como base factual mas fale com fluidez. "
        "Responda sempre em português."
    ),
    "crítico": (
        "Você é Mnemosyne, uma leitora crítica. "
        "Analise os argumentos e ideias encontrados nos trechos de forma rigorosa: "
        "identifique premissas, pontos fortes, limitações e possíveis contradições. "
        "Use apenas os trechos fornecidos. Responda sempre em português."
    ),
}

# Personas para coleções VAULT (memória pessoal, tom introspectivo)
PERSONAS_VAULT: dict[str, str] = {
    "curador": (
        "Você é Mnemosyne, guardiã da memória pessoal. "
        "Estas são as notas e pensamentos da utilizadora — a sua segunda memória. "
        "Ao responder, diga 'Nas tuas notas sobre X, escreveste que…' ou "
        "'Numa nota de [data/título], pensaste que…'. Cite o título da nota, não o caminho. "
        "Responda apenas com base nos trechos fornecidos. "
        "Se a informação não estiver nas notas, diga que não encontrou. "
        "Responda sempre em português."
    ),
    "socrático": (
        "Você é Mnemosyne, guardiã da memória pessoal. "
        "A utilizadora está a explorar os próprios pensamentos. "
        "Faça 2-3 perguntas que a ajudem a aprofundar as ideias que ela própria escreveu, "
        "referenciando trechos concretos das suas notas. "
        "Responda sempre em português."
    ),
    "resumido": (
        "Você é Mnemosyne. Resume o que a utilizadora escreveu sobre este tema — "
        "no máximo 3 frases, referenciando os títulos das notas. "
        "Responda sempre em português."
    ),
    "comparação": (
        "Você é Mnemosyne. Compare como o pensamento da utilizadora evoluiu "
        "entre as notas: identifique mudanças de posição, temas recorrentes e contradições "
        "nas suas próprias ideias. Responda sempre em português."
    ),
    "podcaster": (
        "Você é Mnemosyne. Apresente os pensamentos da utilizadora como se fossem "
        "um episódio de podcast introspectivo — com fluidez e entusiasmo, "
        "mas fiel ao que ela escreveu. Responda sempre em português."
    ),
    "crítico": (
        "Você é Mnemosyne. Analise criticamente as ideias que a utilizadora escreveu: "
        "identifique premissas não examinadas, pontos fortes e tensões nos seus próprios argumentos. "
        "Seja gentil mas honesta. Responda sempre em português."
    ),
}


_VAULT_IGNORE = {".obsidian", "templates", "attachments", ".trash", ".mnemosyne"}


def _find_vault_note(vault_dir: str, note_name: str) -> str:
    """Returns the absolute path of {note_name}.md in vault_dir, or empty string."""
    target = note_name.lower() + ".md"
    for root, dirs, files in os.walk(vault_dir):
        dirs[:] = [d for d in dirs if d not in _VAULT_IGNORE]
        for f in files:
            if f.lower() == target:
                return os.path.join(root, f)
    return ""


def _follow_wikilinks(
    docs: list[Document],
    vault_dir: str,
    max_notes: int = 5,
) -> str:
    """
    Extracts wikilinks from retrieved vault docs, finds the linked .md files,
    and returns a secondary context block (up to 300 chars per note).
    Returns empty string if nothing found.
    """
    if not vault_dir or not docs:
        return ""

    seen: set[str] = set()
    link_names: list[str] = []
    for doc in docs:
        raw = doc.metadata.get("wikilinks", "")
        if not raw:
            continue
        for name in raw.split(","):
            name = name.strip()
            if name and name not in seen:
                seen.add(name)
                link_names.append(name)

    if not link_names:
        return ""

    excerpts: list[str] = []
    for note_name in link_names[:max_notes]:
        note_path = _find_vault_note(vault_dir, note_name)
        if not note_path:
            continue
        try:
            raw_text = open(note_path, encoding="utf-8", errors="ignore").read()
            body = raw_text
            try:
                import frontmatter as _fm
                post = _fm.loads(raw_text)
                body = post.content
            except Exception:
                pass
            excerpt = body.strip()[:300]
            if excerpt:
                excerpts.append(f"[Nota ligada: {note_name}]\n{excerpt}")
        except OSError:
            continue

    return "\n\n---\n".join(excerpts)


def strip_think(text: str) -> str:
    """Remove blocos <think>...</think> gerados pelo Qwen3."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _build_where_filter(
    source_type: str | None,
    source_files: list[str] | None,
) -> dict | None:
    """
    Constrói o filtro ChromaDB `where` combinando source_type e source_files.
    Retorna None se nenhum filtro for necessário.
    """
    conditions: list[dict] = []
    if source_type:
        conditions.append({"source_type": {"$eq": source_type}})
    if source_files:
        conditions.append({"source": {"$in": source_files}})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _hybrid_retrieve(
    vectorstore: Any,
    question: str,
    k: int,
    source_type: str | None = None,
    source_files: list[str] | None = None,
    bm25_index: BM25Index | None = None,
) -> list[Document]:
    """
    Hybrid retrieval com RRF real quando bm25_index fornecido (corpus completo),
    ou fusão ponderada sobre pool semântico como fallback legado.

    Reflexões (metadata["type"] == "reflection") recebem boost multiplicativo no
    score RRF e são filtradas por cosine similarity mínima (REFLECTION_COSINE_THRESHOLD)
    para evitar que reflexões genéricas contaminem o contexto. ChromaDB com
    hnsw:space=cosine retorna distância cosine; similaridade = 1 - distância.
    """
    _RRF_K = 60  # constante padrão RRF
    candidate_n = max(k * 3, 50)

    search_kwargs: dict = {"k": candidate_n if bm25_index else k * 2}
    where = _build_where_filter(source_type, source_files)
    if where:
        search_kwargs["filter"] = where
    try:
        # similarity_search_with_score retorna (Document, distância_cosine)
        # Necessário para calcular cosine similarity das reflexões no filtro de threshold
        semantic_results: list[tuple[Document, float]] = (
            vectorstore.similarity_search_with_score(question, **search_kwargs)
        )
    except Exception as exc:
        raise QueryError(f"Falha na recuperação semântica: {exc}") from exc

    if not semantic_results:
        return []

    # key → cosine similarity (1 - distância); usado para filtrar reflexões abaixo do threshold
    cosine_sim: dict[str, float] = {
        doc.page_content[:200]: max(0.0, 1.0 - dist)
        for doc, dist in semantic_results
    }
    semantic_docs = [doc for doc, _ in semantic_results]

    if bm25_index and bm25_index.size > 0:
        # True RRF: dense top-N ∪ BM25 top-N do corpus completo
        bm25_results = bm25_index.get_top_k(question, candidate_n)

        # Filtrar BM25 por source_type / source_files se necessário
        if source_files:
            source_set = set(source_files)
            bm25_results = [(r, d) for r, d in bm25_results
                            if d.metadata.get("source") in source_set]
        if source_type:
            bm25_results = [(r, d) for r, d in bm25_results
                            if d.metadata.get("source_type") == source_type]

        rrf_scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        for rank, doc in enumerate(semantic_docs):
            key = doc.page_content[:200]
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (_RRF_K + rank + 1)
            doc_map[key] = doc

        for bm25_rank, doc in bm25_results:
            key = doc.page_content[:200]
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (_RRF_K + bm25_rank + 1)
            if key not in doc_map:
                doc_map[key] = doc

        # Aplicar boost e filtro cosine para reflexões antes do sort final
        to_remove: list[str] = []
        for key, doc in doc_map.items():
            if doc.metadata.get("type") != "reflection":
                continue
            sim = cosine_sim.get(key, 0.0)
            if sim < REFLECTION_COSINE_THRESHOLD:
                # Reflexão pouco relacionada com a query — excluir do contexto
                to_remove.append(key)
            else:
                boost = doc.metadata.get("boost", 1.0)
                rrf_scores[key] *= boost

        for key in to_remove:
            rrf_scores.pop(key, None)
            doc_map.pop(key, None)

        sorted_keys = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
        return [doc_map[ky] for ky in sorted_keys[:k]]

    # Fallback legado: BM25 sobre o pool semântico
    tokenized_corpus = [doc.page_content.lower().split() for doc in semantic_docs]
    try:
        bm25_local = BM25Okapi(tokenized_corpus)
        bm25_scores = bm25_local.get_scores(question.lower().split())
    except Exception:
        return semantic_docs[:k]

    max_score = max(bm25_scores) if max(bm25_scores) > 0 else 1.0
    normalized = [s / max_score for s in bm25_scores]
    n = len(semantic_docs)

    combined: list[tuple[float, int]] = []
    for i, doc in enumerate(semantic_docs):
        key = doc.page_content[:200]
        if doc.metadata.get("type") == "reflection":
            if cosine_sim.get(key, 0.0) < REFLECTION_COSINE_THRESHOLD:
                continue  # filtrar reflexão irrelevante
            boost = doc.metadata.get("boost", 1.0)
        else:
            boost = 1.0
        score = (0.6 * (1.0 - i / n) + 0.4 * normalized[i]) * boost
        combined.append((score, i))

    combined.sort(key=lambda x: x[0], reverse=True)

    seen: set[str] = set()
    results: list[Document] = []
    for _, idx in combined:
        doc = semantic_docs[idx]
        key = doc.page_content[:200]
        if key not in seen:
            seen.add(key)
            results.append(doc)
        if len(results) >= k:
            break
    return results


_MULTI_QUERY_PROMPT = (
    "Gere {n} reformulações da pergunta abaixo que expressem a mesma intenção "
    "com palavras diferentes. Escreva uma por linha, sem numeração.\n\n"
    "Pergunta original: {question}\n\n"
    "Reformulações:"
)

_HYDE_PROMPT = (
    "Escreva um parágrafo curto (3-5 frases) que seria uma resposta plausível "
    "para a pergunta abaixo, mesmo que você não saiba a resposta real. "
    "O objectivo é gerar texto no estilo dos documentos que podem conter a resposta.\n\n"
    "Pergunta: {question}\n\n"
    "Resposta hipotética:"
)


def _multi_query_retrieve(
    vectorstore: Any,
    question: str,
    k: int,
    llm_model: str,
    source_type: str | None = None,
    source_files: list[str] | None = None,
    n_variants: int = 3,
    bm25_index: BM25Index | None = None,
) -> list[Document]:
    """
    Reformula a pergunta em n variações, faz retrieval para cada uma e
    deduplica os resultados por page_content. Melhora recall para perguntas vagas.
    Fallback para retrieval simples se a geração das variações falhar.
    """
    queries = [question]
    try:
        llm = OllamaLLM(model=llm_model, temperature=0.5, timeout=30)
        raw = strip_think(llm.invoke(
            _MULTI_QUERY_PROMPT.format(n=n_variants, question=question)
        ))
        for line in raw.splitlines():
            line = line.strip()
            if line and line != question:
                queries.append(line)
            if len(queries) >= n_variants + 1:
                break
    except Exception:
        pass  # fallback: usa só a pergunta original

    seen: set[str] = set()
    results: list[Document] = []

    for q in queries:
        try:
            docs = _hybrid_retrieve(vectorstore, q, k, source_type, source_files, bm25_index)
        except QueryError:
            continue
        for doc in docs:
            key = doc.page_content[:200]
            if key not in seen:
                seen.add(key)
                results.append(doc)

    return results[:k] if results else _hybrid_retrieve(vectorstore, question, k, source_type, source_files, bm25_index)


def _hyde_retrieve(
    vectorstore: Any,
    question: str,
    k: int,
    llm_model: str,
    source_type: str | None = None,
    source_files: list[str] | None = None,
    bm25_index: BM25Index | None = None,
) -> list[Document]:
    """
    HyDE: gera uma resposta hipotética à pergunta e usa o seu embedding
    para recuperar documentos. Eficaz para perguntas abstractas.
    Fallback para retrieval semântico normal se a geração falhar.
    """
    try:
        llm = OllamaLLM(model=llm_model, temperature=0.3, timeout=30)
        hypothetical = strip_think(llm.invoke(
            _HYDE_PROMPT.format(question=question)
        ))
        if not hypothetical.strip():
            raise ValueError("Resposta hipotética vazia")
        return _hybrid_retrieve(vectorstore, hypothetical, k, source_type, source_files, bm25_index)
    except Exception:
        return _hybrid_retrieve(vectorstore, question, k, source_type, source_files, bm25_index)


_RERANK_CANDIDATE_K = 30

_ITER_PROVISIONAL_PROMPT = (
    "Com base nos trechos abaixo, responda em 1-2 frases curtas e directas. "
    "Não elabore — apenas capture a essência para orientar uma busca mais aprofundada.\n\n"
    "Trechos:\n{context}\n\n"
    "Pergunta: {question}\n\n"
    "Resposta:"
)


def _iterative_retrieve(
    vectorstore: Any,
    question: str,
    k: int,
    llm_model: str,
    source_type: str | None = None,
    source_files: list[str] | None = None,
    bm25_index: BM25Index | None = None,
) -> list[Document]:
    """
    Retrieval em 2 iterações (ITER-RETGEN simplificado).

    Iteração 1: retrieval híbrido normal sobre a query original (k chunks).
    Resposta provisória: gerada em temperatura 0.0, sem streaming, 1-2 frases.
    Iteração 2: usa a resposta provisória como query adicional → k//2 chunks extras
    (nunca duplicando chunks já recuperados na iteração 1, dedupados por page_content[:100]).
    Retorna iter1 + extras; prepare_ask limita ao retriever_k configurado.
    Fallback silencioso para iter1 se a geração provisória falhar.
    """
    iter1 = _hybrid_retrieve(vectorstore, question, k, source_type, source_files, bm25_index)
    if not iter1:
        return iter1

    provisional = ""
    try:
        context_preview = "\n\n---\n".join(doc.page_content[:400] for doc in iter1[:5])
        prompt = _ITER_PROVISIONAL_PROMPT.format(context=context_preview, question=question)
        llm = OllamaLLM(model=llm_model, temperature=0.0, timeout=30)
        provisional = strip_think(llm.invoke(prompt)).strip()
    except Exception:
        pass  # sem resposta provisória → retornar só iter1

    if not provisional:
        return iter1

    extra_k = max(1, k // 2)
    seen: set[str] = {doc.page_content[:100] for doc in iter1}

    try:
        iter2 = _hybrid_retrieve(
            vectorstore, provisional, extra_k * 2,
            source_type, source_files, bm25_index,
        )
    except QueryError:
        return iter1

    extra: list[Document] = []
    for doc in iter2:
        key = doc.page_content[:100]
        if key not in seen and len(extra) < extra_k:
            seen.add(key)
            extra.append(doc)

    return iter1 + extra


def _flashrank_rerank(
    docs: list[Document], query: str, top_n: int
) -> list[Document]:
    """
    Re-classifica docs por relevância semântica usando FlashRank
    (ms-marco-MultiBERT-L-12, multilíngue — melhor para PT).
    Fallback para os primeiros top_n se FlashRank não estiver instalado ou falhar.
    """
    if not docs:
        return docs
    top_n = min(top_n, len(docs))
    try:
        from flashrank import Ranker, RerankRequest  # type: ignore[import]
        ranker = Ranker(model_name="ms-marco-MultiBERT-L-12")
        passages = [{"id": i, "text": doc.page_content} for i, doc in enumerate(docs)]
        results = ranker.rerank(RerankRequest(query=query, passages=passages))
        return [docs[r["id"]] for r in results[:top_n]]
    except Exception:
        return docs[:top_n]


_COMPRESS_PROMPT = (
    "O trecho abaixo é relevante para responder à pergunta?\n"
    "Responda apenas 'sim' ou 'não'.\n\n"
    "Pergunta: {question}\n"
    "Trecho: {chunk}\n\n"
    "Resposta:"
)


def _contextual_compress(
    docs: list[Document], question: str, llm_model: str
) -> list[Document]:
    """
    Filtra docs descartando os não relevantes para a pergunta via LLM leve.
    Se todos forem descartados, devolve os originais como fallback.
    """
    if not docs:
        return docs

    try:
        llm = OllamaLLM(model=llm_model, temperature=0, timeout=30)
        kept: list[Document] = []
        for doc in docs:
            chunk_preview = doc.page_content[:600]
            prompt = _COMPRESS_PROMPT.format(question=question, chunk=chunk_preview)
            try:
                answer = strip_think(llm.invoke(prompt)).lower().strip()
                if answer.startswith("sim"):
                    kept.append(doc)
            except Exception:
                kept.append(doc)  # em caso de falha, manter o chunk
        return kept if kept else docs  # fallback
    except Exception:
        return docs  # fallback total se o LLM não estiver disponível


def _apply_time_decay(
    docs: list[Document],
    tracker: FileTracker | None,
    decay_days: int,
) -> list[Document]:
    """
    Re-ordena docs aplicando um multiplicador de decaimento temporal baseado em
    last_retrieved_at. Penaliza fontes consultadas há muito tempo; documentos
    sem histórico não são penalizados.

    A fórmula de decaimento é: base * (0.7 + 0.3 * exp(-days_ago / decay_days))
    — mild, para não descartar documentos genuinamente relevantes.
    """
    if tracker is None or decay_days <= 0 or len(docs) <= 1:
        return docs

    now = datetime.now()
    n = len(docs)
    records = tracker.records

    scored: list[tuple[float, int]] = []
    for i, doc in enumerate(docs):
        base = 1.0 - (i / n)  # posição inversa normalizada [0, 1]

        src = doc.metadata.get("source", "")
        rec = records.get(src) if src else None

        if rec and rec.last_retrieved_at:
            try:
                last = datetime.fromisoformat(rec.last_retrieved_at)
                days_ago = max(0, (now - last).days)
                multiplier = 0.7 + 0.3 * math.exp(-days_ago / decay_days)
            except ValueError:
                multiplier = 1.0
        else:
            multiplier = 1.0  # sem histórico: sem penalização

        scored.append((base * multiplier, i))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [docs[i] for _, i in scored]


def _build_messages(
    context: str,
    question: str,
    history: list[Turn],
    persona: str = "curador",
    collection_type: str = "library",
    secondary_context: str = "",
) -> list[BaseMessage]:
    """
    Constrói a lista de mensagens para ChatOllama com roles separados:
      SystemMessage  — persona fixa (nunca se perde no contexto)
      HumanMessage   — turnos anteriores do utilizador
      AIMessage      — respostas anteriores do assistente
      HumanMessage   — trechos RAG + pergunta actual (mensagem final)
    Usa PERSONAS_VAULT para coleções VAULT, PERSONAS para LIBRARY.
    """
    persona_map = PERSONAS_VAULT if collection_type == "vault" else PERSONAS
    system_text = persona_map.get(persona, persona_map["curador"])
    messages: list[BaseMessage] = [SystemMessage(content=system_text)]

    for turn in history[-_HISTORY_TURNS:]:
        if turn.role == "user":
            messages.append(HumanMessage(content=turn.content))
        elif turn.role == "assistant":
            messages.append(AIMessage(content=turn.content))

    user_content = f"Trechos relevantes:\n{context}"
    if secondary_context:
        user_content += f"\n\nNotas ligadas (contexto adicional):\n{secondary_context}"
    user_content += f"\n\nPergunta: {question}"

    messages.append(HumanMessage(content=user_content))
    return messages


def prepare_ask(
    vectorstore: Any,
    question: str,
    config: AppConfig,
    chat_history: list[Turn] | None = None,
    source_type: str | None = None,
    retrieval_mode: str = "hybrid",
    tracker: FileTracker | None = None,
    persona: str = "curador",
    source_files: list[str] | None = None,
    collection_type: str = "library",
    bm25_index: BM25Index | None = None,
    iterative_retrieval: bool = False,
) -> tuple[list[BaseMessage], list[SourceRecord]]:
    """
    Recupera documentos relevantes e retorna (prompt, sources).
    Usado pelo worker para streaming com possibilidade de interrupção.

    chat_history: turnos anteriores da sessão para contexto multi-turno.
    source_type: filtrar por "library", "vault" ou None (ambos).
    retrieval_mode: "hybrid" (padrão), "multi_query" ou "hyde".
    tracker: FileTracker opcional — activa re-ranking por time-decay de relevância.
    source_files: lista de caminhos absolutos para restringir a consulta a
        arquivos específicos; None significa sem restrição por arquivo.
    collection_type: "vault" usa PERSONAS_VAULT e segue wikilinks; "library" usa PERSONAS.
    iterative_retrieval: activa retrieval em 2 iterações — gera resposta provisória a partir
        dos chunks da iteração 1 e usa-a como query adicional para recuperar N/2 chunks extras.
        Beneficia perguntas curtas ou vagas; toggle manual na UI.

    Raises:
        QueryError: se a busca vetorial falhar.
    """
    # Reranking activo: buscar 30 candidatos; sem reranking: k+2 como antes
    candidate_k = _RERANK_CANDIDATE_K if config.reranking_enabled else config.retriever_k + 2

    try:
        if iterative_retrieval:
            docs = _iterative_retrieve(
                vectorstore, question, candidate_k, config.llm_model,
                source_type, source_files, bm25_index,
            )
        elif retrieval_mode == "multi_query":
            docs = _multi_query_retrieve(
                vectorstore, question, candidate_k, config.llm_model, source_type, source_files,
                bm25_index=bm25_index,
            )
        elif retrieval_mode == "hyde":
            docs = _hyde_retrieve(
                vectorstore, question, candidate_k, config.llm_model, source_type, source_files,
                bm25_index=bm25_index,
            )
        else:
            docs = _hybrid_retrieve(vectorstore, question, candidate_k, source_type, source_files,
                                    bm25_index)
    except QueryError:
        raise
    except Exception as exc:
        raise QueryError(f"Falha na recuperação: {exc}") from exc

    # Compressão contextual: filtrar chunks irrelevantes via LLM
    docs = _contextual_compress(docs, question, config.llm_model)

    # Re-ranking por time-decay: penaliza fontes consultadas há muito tempo
    docs = _apply_time_decay(docs, tracker, config.relevance_decay_days)

    # FlashRank: reordena por relevância semântica e reduz ao top_n configurado
    if config.reranking_enabled:
        docs = _flashrank_rerank(docs, question, config.reranking_top_n)
    elif iterative_retrieval:
        # Retrieval iterativo expande o pool além de candidate_k — limitar ao configurado
        docs = docs[:config.retriever_k]

    context = "\n\n---\n".join(doc.page_content for doc in docs)

    # Follow wikilinks for vault collections: include linked note excerpts
    secondary_context = ""
    if collection_type == "vault" and config.watched_dir:
        secondary_context = _follow_wikilinks(docs, config.watched_dir)

    seen: set[str] = set()
    sources: list[SourceRecord] = []
    n_docs = len(docs)
    for rank, doc in enumerate(docs):
        src = doc.metadata.get("source", "")
        if src and src not in seen:
            seen.add(src)
            score = max(0.0, 1.0 - rank / max(n_docs, 1))
            excerpt = doc.page_content[:250].strip().replace("\n", " ")
            sources.append(SourceRecord(path=src, excerpt=excerpt, score=score))

    messages = _build_messages(
        context, question, chat_history or [], persona, collection_type, secondary_context
    )
    return messages, sources


def ask(
    vectorstore: Any,
    question: str,
    config: AppConfig,
    chat_history: list[Turn] | None = None,
    source_type: str | None = None,
    retrieval_mode: str = "hybrid",
    tracker: FileTracker | None = None,
    persona: str = "curador",
    source_files: list[str] | None = None,
    collection_type: str = "library",
    iterative_retrieval: bool = False,
) -> AskResult:
    """
    Consulta RAG síncrona (sem streaming).

    Raises:
        QueryError: se a chain falhar por qualquer motivo.
    """
    try:
        messages, sources = prepare_ask(
            vectorstore, question, config, chat_history,
            source_type, retrieval_mode, tracker, persona, source_files,
            collection_type, bm25_index=None, iterative_retrieval=iterative_retrieval,
        )
        llm = ChatOllama(model=config.llm_model, temperature=0)
        response = llm.invoke(messages)
        answer = strip_think(response.content)
    except QueryError:
        raise
    except Exception as exc:
        raise QueryError(f"Falha na consulta: {exc}") from exc

    return AskResult(answer=answer, sources=sources)
