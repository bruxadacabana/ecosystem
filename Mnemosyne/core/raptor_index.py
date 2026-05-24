"""RAPTOR — Recursive Abstractive Processing for Tree-Organized Retrieval.

Implementação custom usando umap-learn + scikit-learn + ChromaDB.
Não depende do llama-index — usa as dependências já instaladas no Mnemosyne.

Pipeline de indexação (offline, rodado no MainPc):
  1. Extrai embeddings e textos dos chunks PDF do ChromaDB
  2. UMAP reduz dimensões para clustering efetivo
  3. GMM determina k via BIC e agrupa semanticamente
  4. LLM sumariza cada cluster (qwen2.5:7b via Ollama)
  5. Recursão com sumários como próximos "chunks" (até max_rounds)
  6. Persiste todos os nós sumários como JSON em {chroma_dir}/../raptor_papers/

Retrieval (em tempo de consulta, qualquer máquina):
  - Lê raptor_summaries.json (arquivo de texto, sem ChromaDB adicional)
  - Busca por sobreposição de tokens TF-IDF aproximada
  - Prioriza nós de rodadas superiores (mais abstratos) para perguntas de síntese
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AppConfig

log = logging.getLogger("mnemosyne.raptor")

# Palavras-gatilho que indicam perguntas de síntese ou visão geral
_SYNTHESIS_TRIGGERS = {
    # Português
    "quais são", "quais foram", "quais os", "quais as",
    "resumo", "resuma", "sumarize", "sumarização", "sintetize", "síntese",
    "visão geral", "visão ampla", "panorama", "overview",
    "principais temas", "temas centrais", "temas principais",
    "tendências", "conclusões", "em geral", "de forma geral", "no geral",
    "o que dizem", "o que falam", "o que discutem", "o que abordam",
    "me dê uma ideia", "explique em geral",
    # Inglês
    "what are", "what were", "summarize", "summary",
    "main themes", "key themes", "overall", "broadly",
    "trends", "conclusions", "in general", "give me an overview",
}


def _raptor_dir(config: AppConfig) -> Path:
    """Retorna {chroma_dir}/../raptor_papers/ como diretório de persistência."""
    if config.persist_dir:
        return Path(config.persist_dir).parent / "raptor_papers"
    return Path.home() / ".local" / "share" / "mnemosyne" / "raptor_papers"


def _summaries_path(config: AppConfig) -> Path:
    return _raptor_dir(config) / "raptor_summaries.json"


def has_index(config: AppConfig) -> bool:
    """True se o índice RAPTOR existe (arquivo JSON com sumários)."""
    return _summaries_path(config).exists()


def _is_synthesis_query(query: str) -> bool:
    """True se a query parece pedir síntese temática em vez de detalhe específico."""
    q_lower = query.lower()
    return any(trigger in q_lower for trigger in _SYNTHESIS_TRIGGERS)


async def _call_inference(prompt: str, model: str, inference_url: str) -> str | None:
    """Chama llama-server para sumarização. Retorna texto ou None em falha."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{inference_url}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "max_tokens": 512,
                    "temperature": 0.3,
                },
            )
            return r.json()["choices"][0]["message"]["content"].strip() or None
    except Exception as exc:
        log.warning("raptor._call_inference: %s", exc)
        return None


async def build_raptor_index(
    config: AppConfig,
    vectorstore: object,
    progress_cb: Callable[[str], None] | None = None,
    max_rounds: int = 3,
) -> int:
    """Constrói o índice RAPTOR para chunks PDF da coleção ChromaDB.

    Retorna o número total de nós sumários gerados (0 em falha).
    Seguro para rodar em thread separada via asyncio.run().
    """
    if not config.raptor_enabled:
        return 0

    try:
        import numpy as np
        import umap  # type: ignore[import]
        from sklearn.mixture import GaussianMixture  # type: ignore[import]
    except ImportError:
        log.warning("raptor: umap-learn ou scikit-learn não instalado")
        return 0

    from ecosystem_client import get_inference_url as _giu
    _inference_url = _giu()

    # ── Extrai chunks PDF do ChromaDB ─────────────────────────────────────────
    if progress_cb:
        progress_cb("RAPTOR: lendo PDFs do índice ChromaDB…")
    try:
        collection = vectorstore._collection  # type: ignore[union-attr]
        result = collection.get(include=["documents", "embeddings", "metadatas"])
    except Exception as exc:
        log.warning("raptor: erro ao ler ChromaDB — %s", exc)
        return 0

    all_docs  = result.get("documents") or []
    all_embs  = result.get("embeddings") or []
    all_metas = result.get("metadatas") or []

    # Filtra apenas PDFs, excluindo reflexões sintéticas
    pdf_idx = [
        i for i, m in enumerate(all_metas)
        if m
        and str(m.get("source", "")).lower().endswith(".pdf")
        and m.get("type", "") != "reflection"
    ]

    if len(pdf_idx) < 6:
        log.info("raptor: %d chunks PDF — mínimo 6 necessário, índice não construído", len(pdf_idx))
        return 0

    texts   = [all_docs[i] for i in pdf_idx]
    vectors = [all_embs[i] for i in pdf_idx]

    log.info("raptor: iniciando indexação com %d chunks PDF", len(texts))

    out_dir = _raptor_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_nodes: list[dict] = []
    current_texts   = texts
    current_vectors = vectors

    # ── Recursão por rodadas ──────────────────────────────────────────────────
    for round_num in range(max_rounds):
        n = len(current_texts)
        if n < 6:
            break

        if progress_cb:
            progress_cb(f"RAPTOR: rodada {round_num + 1}/{max_rounds} — {n} textos…")

        # UMAP: reduz para clustering efetivo
        n_comp = min(10, n - 2)
        n_nbrs = min(15, n - 2)
        arr = np.array(current_vectors, dtype=np.float32)

        try:
            reducer = umap.UMAP(
                n_components=n_comp,
                n_neighbors=n_nbrs,
                metric="cosine",
                random_state=42,
                min_dist=0.0,
            )
            reduced = reducer.fit_transform(arr)
        except Exception as exc:
            log.warning("raptor: UMAP rodada %d falhou — %s", round_num + 1, exc)
            break

        # GMM: número de clusters determinado por BIC
        best_k, best_bic = 2, float("inf")
        k_max = min(n // 3, 20)
        for k in range(2, k_max + 1):
            try:
                gm = GaussianMixture(n_components=k, random_state=42, n_init=1)
                gm.fit(reduced)
                bic = gm.bic(reduced)
                if bic < best_bic:
                    best_bic, best_k = bic, k
            except Exception:
                break

        gm = GaussianMixture(n_components=best_k, random_state=42)
        labels = gm.fit_predict(reduced)
        log.info("raptor: rodada %d — %d clusters (BIC=%.1f)", round_num + 1, best_k, best_bic)

        # Sumarizar cada cluster via LLM
        round_texts:   list[str] = []
        round_vectors: list      = []

        for cid in range(best_k):
            cluster_texts = [current_texts[i] for i in range(n) if labels[i] == cid]
            if not cluster_texts:
                continue

            if progress_cb:
                progress_cb(f"RAPTOR: sumarizando cluster {cid + 1}/{best_k} (rodada {round_num + 1})…")

            combined = "\n\n---\n\n".join(cluster_texts[:12])
            prompt = (
                "Você recebeu fragmentos de artigos científicos sobre um mesmo tema. "
                "Sintetize os conceitos-chave, identifique conexões não-óbvias e gere "
                "um artefato de conhecimento estruturado em 200-350 palavras. "
                "Escreva parágrafos explicativos, não listas.\n\n"
                f"{combined}"
            )
            summary = await _call_inference(prompt, config.llm_model or "qwen2.5:7b", _inference_url)
            if not summary:
                continue

            all_nodes.append({
                "round": round_num,
                "cluster": cid,
                "text": summary,
                "n_sources": len(cluster_texts),
            })
            round_texts.append(summary)

        if not round_texts:
            break

        # Embedar sumários para próxima rodada
        try:
            from .indexer import _InferenceEmbeddings
            embedder = _InferenceEmbeddings(config.embed_model or "nomic-embed-text")
            round_vectors = embedder.embed_documents(round_texts)
        except Exception as exc:
            log.warning("raptor: embedding de sumários falhou — %s", exc)
            break

        current_texts   = round_texts
        current_vectors = round_vectors

    if not all_nodes:
        log.warning("raptor: nenhum nó gerado — verifique Ollama e modelo")
        return 0

    # ── Persiste índice ───────────────────────────────────────────────────────
    _summaries_path(config).write_text(
        json.dumps(all_nodes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("raptor: %d nós sumários persistidos em %s", len(all_nodes), out_dir)
    if progress_cb:
        progress_cb(f"RAPTOR: {len(all_nodes)} sumários gerados.")
    return len(all_nodes)


def query_raptor(question: str, config: AppConfig) -> list[str]:
    """Recupera sumários RAPTOR relevantes para a questão.

    Usa sobreposição de tokens (TF simples) — sem embedding em tempo de consulta.
    Prioriza rodadas superiores (nós mais abstratos) para perguntas de síntese.
    Retorna até 3 sumários ordenados por score.
    """
    path = _summaries_path(config)
    if not path.exists():
        return []
    try:
        nodes = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    q_tokens = set(re.findall(r"\w+", question.lower()))
    if not q_tokens:
        return []

    scored: list[tuple[float, str]] = []
    for node in nodes:
        text = node.get("text", "")
        t_tokens = set(re.findall(r"\w+", text.lower()))
        overlap = len(q_tokens & t_tokens) / (len(q_tokens) + 1)
        # Nós de rodadas superiores (mais abstratos) recebem bônus para síntese
        round_bonus = node.get("round", 0) * 0.05
        score = overlap + round_bonus
        if score > 0:
            scored.append((score, text))

    scored.sort(key=lambda x: -x[0])
    return [text for _, text in scored[:3]]
