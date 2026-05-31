"""
AKASHA — Busca semântica com embeddings via LOGOS.

Pipeline:
  embed_text()          — chama LOGOS /v1/embeddings, retorna ndarray float32
  embed_and_store()     — gera embedding e persiste em page_embeddings + page_vec
  semantic_search_local() — KNN em page_vec, retorna [(url, distance), ...]
  hybrid_rrf()          — Reciprocal Rank Fusion entre resultados lexicais e semânticos

O modelo potion-multilingual-128M (configurado no LOGOS) é cross-lingual para
101 idiomas por natureza: uma query em qualquer língua encontra documentos em
qualquer outra sem tradução explícita — o espaço de embeddings é compartilhado.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("akasha.semantic_search")

try:
    import sqlite_vec as _sqlite_vec  # type: ignore
    _SQLITE_VEC_AVAILABLE = True
except ImportError:
    _SQLITE_VEC_AVAILABLE = False

# ---------------------------------------------------------------------------
# Detecção de latência excessiva — hardware sem AVX2 (ex: i5-3470)
#
# sqlite-vec sem AVX2 cai para caminho escalar que pode ultrapassar 300ms em
# coleções de 50k+ vetores, tornando a busca interativa perceptível.
# Acumulamos as 3 primeiras amostras de latência e desativamos KNN se a média
# exceder _LATENCY_THRESHOLD_MS. Média em vez de primeira amostra para evitar
# falso positivo de cold start (cache miss, warm-up de JIT).
# A flag é em memória — resetada ao reiniciar o processo, nunca persiste.
# ---------------------------------------------------------------------------

_LATENCY_THRESHOLD_MS: float = 250.0
_LATENCY_SAMPLES_NEEDED: int = 3

_latency_samples: list[float] = []
_vector_too_slow: bool = False


def get_vector_too_slow() -> bool:
    """Retorna True se o hardware detectado é lento demais para KNN interativo."""
    return _vector_too_slow


def reset_latency_state() -> None:
    """Reseta o estado de latência (usado em testes)."""
    global _latency_samples, _vector_too_slow
    _latency_samples = []
    _vector_too_slow = False


def _get_inference_url() -> str:
    try:
        from ecosystem_client import get_inference_url  # type: ignore
        return get_inference_url()
    except Exception:
        return "http://localhost:7072"


def _get_embed_model() -> str:
    try:
        from ecosystem_client import get_active_profile  # type: ignore
        p = get_active_profile()
        return ((p or {}).get("models", {}) or {}).get("embed", "") if p else ""
    except Exception:
        return ""


async def _load_vec_ext_async(db: object) -> None:
    """Carrega sqlite-vec numa conexão aiosqlite (aiosqlite >= 0.17)."""
    await db.enable_load_extension(True)   # type: ignore[union-attr]
    await db.load_extension(_sqlite_vec.loadable_path())  # type: ignore[union-attr]
    await db.enable_load_extension(False)  # type: ignore[union-attr]


async def _ensure_page_vec_table() -> None:
    """Cria page_vec (sqlite-vec virtual table) se ainda não existir.

    Separado de database.py/init_db porque virtual tables exigem que a
    extensão sqlite-vec esteja carregada na conexão — não é possível fazer
    via CREATE TABLE IF NOT EXISTS puro sem load_extension.
    """
    if not _SQLITE_VEC_AVAILABLE:
        return
    try:
        import aiosqlite
        from config import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            await _load_vec_ext_async(db)
            await db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS page_vec USING vec0(embedding float[768])"
            )
            await db.commit()
        log.debug("_ensure_page_vec_table: page_vec pronta")
    except Exception as exc:
        log.debug("_ensure_page_vec_table: %s", exc)


async def embed_text(text: str) -> "list[float] | None":
    """Chama LOGOS POST /v1/embeddings para um único texto.

    Trunca para ~2000 chars. Retorna lista de floats (dim 768) ou None se
    LOGOS offline ou qualquer erro de rede/protocolo.
    """
    if not text.strip():
        return None
    try:
        import httpx
        url = _get_inference_url()
        model = _get_embed_model()
        payload: dict = {"model": model, "input": [text[:2000]]}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{url}/v1/embeddings", json=payload)
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
    except Exception as exc:
        log.debug("embed_text: %s", exc)
        return None


async def embed_and_store(url: str, content_md: str) -> None:
    """Gera embedding de content_md e persiste em page_embeddings + page_vec.

    Fire-and-forget seguro: nunca lança exceção. Se LOGOS offline, retorna
    silenciosamente. Se page_vec não existe ainda, cria via _ensure_page_vec_table.
    """
    if not _SQLITE_VEC_AVAILABLE:
        return
    vec = await embed_text(content_md)
    if vec is None:
        log.debug("embed_and_store: LOGOS offline, skip %s", url)
        return
    try:
        import aiosqlite
        from config import DB_PATH
        embedding_bytes = _sqlite_vec.serialize_float32(vec)  # type: ignore[union-attr]
        async with aiosqlite.connect(DB_PATH) as db:
            await _load_vec_ext_async(db)
            # Garante que page_vec existe (criação lazy)
            await db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS page_vec USING vec0(embedding float[768])"
            )
            # Upsert em page_embeddings: obtém ou cria id
            row = await (await db.execute(
                "SELECT id FROM page_embeddings WHERE url = ?", (url,)
            )).fetchone()
            if row is None:
                cur = await db.execute(
                    "INSERT INTO page_embeddings (url) VALUES (?)", (url,)
                )
                emb_id = cur.lastrowid
                await db.execute(
                    "INSERT INTO page_vec(rowid, embedding) VALUES (?, ?)",
                    (emb_id, embedding_bytes),
                )
            else:
                emb_id = row[0]
                await db.execute(
                    "INSERT OR REPLACE INTO page_vec(rowid, embedding) VALUES (?, ?)",
                    (emb_id, embedding_bytes),
                )
            await db.execute(
                "UPDATE page_embeddings SET updated_at = datetime('now') WHERE id = ?",
                (emb_id,),
            )
            await db.commit()
        log.debug("embed_and_store: embedding salvo para %s", url)
    except Exception as exc:
        log.debug("embed_and_store: erro em %s: %s", url, exc)


async def semantic_search_local(
    query: str,
    top_k: int = 50,
) -> list[tuple[str, float]]:
    """KNN em page_vec para a query fornecida.

    Retorna lista de (url, distance) ordenada por distância crescente
    (menor distância = maior similaridade). Lista vazia se LOGOS offline,
    sqlite-vec indisponível, sem vetores no banco, ou hardware detectado
    como lento demais para KNN interativo (_vector_too_slow=True).

    Mede latência das 3 primeiras chamadas: se a média ultrapassar
    _LATENCY_THRESHOLD_MS (250ms), seta _vector_too_slow e subsequentes
    chamadas retornam [] imediatamente — apenas a query interativa é afetada,
    o backfill de embeddings (Semântico 3) continua rodando normalmente.
    """
    global _latency_samples, _vector_too_slow

    # Guarda rápida: hardware já marcado como lento
    if _vector_too_slow:
        log.debug("semantic_search_local: _vector_too_slow ativo — pulando KNN")
        return []

    if not _SQLITE_VEC_AVAILABLE:
        return []
    vec = await embed_text(query)
    if vec is None:
        return []
    try:
        import aiosqlite
        from config import DB_PATH
        embedding_bytes = _sqlite_vec.serialize_float32(vec)  # type: ignore[union-attr]
        async with aiosqlite.connect(DB_PATH) as db:
            await _load_vec_ext_async(db)
            _t0 = time.monotonic()
            rows = await (await db.execute(
                """SELECT pe.url, pv.distance
                   FROM page_vec pv
                   JOIN page_embeddings pe ON pe.id = pv.rowid
                   WHERE pv.embedding MATCH ? AND k = ?
                   ORDER BY pv.distance""",
                (embedding_bytes, top_k),
            )).fetchall()
            _elapsed_ms = (time.monotonic() - _t0) * 1000

        # Acumula amostras de latência até ter _LATENCY_SAMPLES_NEEDED
        if len(_latency_samples) < _LATENCY_SAMPLES_NEEDED:
            _latency_samples.append(_elapsed_ms)
            if len(_latency_samples) == _LATENCY_SAMPLES_NEEDED:
                _avg_ms = sum(_latency_samples) / _LATENCY_SAMPLES_NEEDED
                if _avg_ms > _LATENCY_THRESHOLD_MS:
                    _vector_too_slow = True
                    log.warning(
                        "[PERF] busca vetorial lenta (média %.0fms em %d amostras) — "
                        "possível hardware sem AVX2; usando só FTS5 para queries interativas",
                        _avg_ms, _LATENCY_SAMPLES_NEEDED,
                    )
                else:
                    log.debug(
                        "latência vetorial OK: média %.0fms em %d amostras",
                        _avg_ms, _LATENCY_SAMPLES_NEEDED,
                    )

        return [(r[0], float(r[1])) for r in rows]
    except Exception as exc:
        log.debug("semantic_search_local: %s", exc)
        return []


def hybrid_rrf(
    lexical_urls: list[str],
    semantic_pairs: list[tuple[str, float]],
    k: int = 60,
) -> list[str]:
    """Reciprocal Rank Fusion entre resultados lexicais (BM25/FTS5) e semânticos (KNN).

    Score = 0.6 × 1/(k + rank_bm25) + 0.4 × 1/(k + rank_vec)

    URLs ausentes numa das listas recebem rank = len(lista)+1, reduzindo sua
    contribuição desse sinal a ~0 sem quebrá-la algebricamente.

    Implementado em Python puro para facilitar testes unitários.
    """
    bm25_rank: dict[str, int] = {url: i + 1 for i, url in enumerate(lexical_urls)}
    vec_rank:  dict[str, int] = {url: i + 1 for i, (url, _) in enumerate(semantic_pairs)}

    all_urls = set(bm25_rank) | set(vec_rank)
    n_bm25 = len(lexical_urls)
    n_vec  = len(semantic_pairs)

    scores: dict[str, float] = {}
    for url in all_urls:
        rb = bm25_rank.get(url, n_bm25 + 1)
        rv = vec_rank.get(url, n_vec  + 1)
        scores[url] = 0.6 / (k + rb) + 0.4 / (k + rv)

    return sorted(all_urls, key=lambda u: scores[u], reverse=True)
