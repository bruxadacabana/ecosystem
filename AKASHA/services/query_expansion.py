"""
AKASHA — Expansão de query via Pseudo-Relevance Feedback (PRF), sem LLM.

Técnica clássica de IR: pega os top-5 docs retornados pela busca FTS5,
extrai termos discriminativos via TF-IDF sobre esse sub-corpus e retorna
uma lista de candidatos para uma segunda busca FTS5 aditiva.

100% corpus-anchored: os termos vêm de documentos que já existem no índice,
garantindo recall real sem query drift.

Aplicado apenas a queries com ≥ 3 tokens — abaixo disso, ambiguidade alta.
Termos com len < 4 são ignorados (preposições, artigos etc.).
"""
from __future__ import annotations

import math
import re


_STOPWORDS: frozenset[str] = frozenset({
    # PT
    "para", "sobre", "entre", "também", "ainda", "mais",
    "muito", "todo", "toda", "todos", "todas", "pelo", "pela",
    "pelos", "pelas", "pode", "esse", "essa", "esses", "essas",
    "este", "esta", "estes", "estas", "aquele", "aquela",
    "aqueles", "aquelas", "nosso", "nossa", "nossos", "nossas",
    "vocês", "eles", "elas", "isso", "aquilo", "aqui", "então",
    "pois", "logo", "porque", "assim", "após", "cada", "qual",
    "como", "quando", "onde", "quem", "nada", "algo", "alguém",
    "tudo", "nunca", "sempre", "talvez", "apenas", "mesmo",
    "seria", "estar", "fazer", "ficar", "deve", "sendo",
    # EN
    "also", "about", "into", "than", "then", "from", "with",
    "this", "that", "they", "them", "what", "when", "where",
    "will", "would", "could", "should", "have", "been", "being",
    "does", "their", "there", "these", "those", "some", "more",
    "most", "both", "each", "other", "very", "just", "only",
    "even", "like", "such", "after", "which", "while", "since",
})

_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ɏЀ-ӿ]{4,}")


def _tokenize(text: str) -> list[str]:
    """Extrai tokens de len ≥ 4, lowercase, sem stopwords."""
    return [
        t.lower() for t in _TOKEN_RE.findall(text)
        if t.lower() not in _STOPWORDS
    ]


def _tfidf_score(term: str, doc_tokens: list[str], all_docs: list[list[str]]) -> float:
    """TF normalizado × IDF: mede quão discriminativo o termo é neste sub-corpus."""
    if not doc_tokens:
        return 0.0
    tf = doc_tokens.count(term) / len(doc_tokens)
    df = sum(1 for d in all_docs if term in d)
    if df == 0:
        return 0.0
    # IDF suavizado com +1 para evitar log(0)
    idf = math.log((len(all_docs) + 1) / (df + 1)) + 1.0
    return tf * idf


def expand_query_prf(
    query: str,
    top_docs: list,
    max_terms: int = 5,
) -> list[str]:
    """Retorna termos de expansão via PRF — sem LLM, sem DB calls.

    Args:
        query:    Query original; termos já presentes são excluídos da expansão.
        top_docs: Objetos com atributos `.title` e `.snippet` (ex: SearchResult)
                  ou dicts com chaves 'title' e 'snippet'.
        max_terms: Máximo de termos de expansão a retornar (default 5).

    Returns:
        Lista de termos de expansão (vazia se query < 3 tokens ou sem docs).
        Os termos são garantidamente distintos entre si e ausentes na query original.
    """
    q_tokens = query.lower().split()
    if len(q_tokens) < 3 or not top_docs:
        return []

    # Termos a excluir: tokens da query original + suas formas tokenizadas
    q_excluded = frozenset(q_tokens) | frozenset(_tokenize(query))

    # Constrói sub-corpus a partir dos top-5 docs
    doc_token_lists: list[list[str]] = []
    for doc in top_docs[:5]:
        if isinstance(doc, dict):
            title   = doc.get("title", "")
            snippet = doc.get("snippet", "")
        else:
            title   = getattr(doc, "title", "") or ""
            snippet = getattr(doc, "snippet", "") or ""
        doc_token_lists.append(_tokenize(f"{title} {snippet}"))

    if not any(doc_token_lists):
        return []

    # Candidatos: termos presentes no sub-corpus mas não na query
    candidates: set[str] = {
        t for tl in doc_token_lists for t in tl
        if t not in q_excluded
    }
    if not candidates:
        return []

    # Pontua cada candidato pelo TF-IDF no doc em que mais aparece
    best_scores: dict[str, float] = {}
    for term in candidates:
        for dl in doc_token_lists:
            if term in dl:
                score = _tfidf_score(term, dl, doc_token_lists)
                if score > best_scores.get(term, 0.0):
                    best_scores[term] = score

    # Ordena por score desc e retorna os top-max_terms
    ranked = sorted(best_scores.items(), key=lambda kv: -kv[1])
    return [term for term, _ in ranked[:max_terms]]
