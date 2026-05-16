"""
AKASHA — Busca local nos arquivos do ecossistema
Indexa KOSMOS archive + AETHER vault em FTS5 (SQLite).
ChromaDB (Mnemosyne) é opcional — importação com graceful fallback.
"""
from __future__ import annotations

import asyncio
import math
import re
from pathlib import Path

import aiosqlite

import config
from config import DB_PATH
from services.web_search import SearchResult

# ---------------------------------------------------------------------------
# Modo de snippet — 'fts5' (padrão) ou 'paragraph_bm25'
# 'paragraph_bm25': divide o body em parágrafos e retorna o mais relevante
# usando BM25 local (pip install bm25s). Produz snippets mais coerentes que
# o snippet() do FTS5 (limitado a 64 tokens, heurística simples).
# ---------------------------------------------------------------------------

SNIPPET_MODE: str = "fts5"

# ---------------------------------------------------------------------------
# Re-ranking cross-encoder (FlashRank) — desativado por padrão
# Quando ativado, os top-RERANK_TOP_K resultados FTS5+RRF são re-ordenados
# por um modelo cross-encoder leve (~4MB, CPU-only).
# Latência estimada: ~200ms/20 docs em CPU moderno; pode ser mais lento em
# máquinas antigas (ex: i5-3470 sem AVX2) — habilitar só se aceitável.
# Modelos disponíveis: "ms-marco-TinyBERT-L-2-v2" (4MB, rápido),
#                      "ms-marco-MiniLM-L-12-v2" (80MB, mais preciso).
# ---------------------------------------------------------------------------

RERANKING_ENABLED: bool = False
RERANK_TOP_K:      int  = 20
RERANK_MODEL:      str  = "ms-marco-TinyBERT-L-2-v2"

# ---------------------------------------------------------------------------
# Busca vetorial (sqlite-vec + sentence-transformers) — desativada por padrão
# Quando ativada, embeddings são calculados ao indexar e a busca combina
# FTS5 (BM25) + ChromaDB + sqlite-vec (KNN cosine) via RRF.
# Modelo: all-MiniLM-L6-v2 (~80MB, 384 dims, CPU-only).
# Atenção: i5-3470 (sem AVX2) pode ser lento — habilitar só em CachyOS/laptop.
# ---------------------------------------------------------------------------

VECTOR_SEARCH_ENABLED: bool = False
VEC_EMBED_MODEL:       str  = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Usage-based ranking — desativado por padrão
# Combina posição RRF com frequência de acesso + decaimento temporal.
# α (USAGE_RANKING_ALPHA): peso do ranking posicional (1-α = peso do uso).
# λ (USAGE_RANKING_DECAY): taxa de decaimento diário (0.1 = -10%/dia).
# ---------------------------------------------------------------------------

USAGE_RANKING_ENABLED: bool  = True
USAGE_RANKING_ALPHA:   float = 0.7
USAGE_RANKING_DECAY:   float = 0.1

# ---------------------------------------------------------------------------
# Annotation density como sinal de ranking — ativado por padrão
# Documentos com mais highlights pessoais sobem no ranking.
# β (ANNOTATION_DENSITY_BETA): peso da anotação. Default 0.1 — modesto para
# não deslocar documentos relevantes sem anotações, mas discernível.
# Fórmula: β × log(1 + highlight_count) somado ao score de uso.
# ---------------------------------------------------------------------------

ANNOTATION_DENSITY_ENABLED: bool  = True
ANNOTATION_DENSITY_BETA:    float = 0.1

# ---------------------------------------------------------------------------
# Correção ortográfica (symspellpy) — desativada por padrão
# Quando ativada, queries curtas (≤ 2 tokens) com zero resultados locais são
# corrigidas automaticamente e reexecutadas. Latência: < 1ms após carga.
# ---------------------------------------------------------------------------

SPELL_CORRECTION_ENABLED: bool = False

# ---------------------------------------------------------------------------
# Expansão de query via LLM (padrão MUST+SHOULD) — ativada por padrão
# Quando o Ollama está disponível, gera 3–5 termos sinônimos/relacionados via
# LLM leve e executa uma segunda busca FTS5 com esses termos. Os dois conjuntos
# de resultados são combinados via RRF: a query original permanece âncora
# (MUST), os termos expandidos são aditivos (SHOULD) — evita query drift.
# Latência extra: ~LLM_time - main_searches_time (rodando em paralelo).
# ---------------------------------------------------------------------------

FTS_EXPANSION_ENABLED: bool = True
FTS_EXPANSION_MODEL:   str  = ""   # vazio = usa primeiro modelo disponível no Ollama

# ---------------------------------------------------------------------------
# HyDE — Hypothetical Document Embeddings para busca ChromaDB/Mnemosyne
# Ativado por padrão; produz efeito apenas quando Mnemosyne está disponível.
# Ganho documentado: +38% nDCG@10 vs embedding direto de query (SIGIR 2023).
# Custo: ~500ms extra de inferência Ollama (paralelo à busca FTS5).
# ---------------------------------------------------------------------------

HYDE_ENABLED: bool = True

# ---------------------------------------------------------------------------
# Pesos por fonte — aplicados ao score RRF antes da ordenação final.
# Artigos científicos têm peso máximo por serem fontes primárias de maior
# densidade informacional; highlights têm peso alto por serem marcações
# explícitas da usuária; conteúdo arquivado intencionalmente > geral.
# ---------------------------------------------------------------------------

SOURCE_WEIGHTS: dict[str, float] = {
    "PAPER":     2.0,   # artigos científicos (Semantic Scholar, arXiv, OpenAlex)
    "HIGHLIGHT": 1.6,   # trechos destacados explicitamente pela usuária
    "AKASHA":    1.4,   # páginas arquivadas intencionalmente
    "KOSMOS":    1.2,   # arquivo pessoal do KOSMOS
    "OBSIDIAN":  1.2,   # vault do Obsidian / Mnemosyne
    "MNEMOSYNE": 1.1,   # busca semântica ChromaDB
    "HERMES":    1.0,   # transcrições automáticas
    "DEPOIS":    1.0,   # salvo para ler depois
}

_expansion_model_cache: str = ""

# LOGOS-first: URL do Ollama e modelo padrão resolvidos no startup via ecosystem_client.
# get_ollama_url() retorna 7072 (LOGOS proxy) se disponível, 11434 direto como fallback.
# check_ollama_available() atualiza _ollama_base_url em runtime.
try:
    from ecosystem_client import (
        get_ollama_url    as _ec_ollama_url,
        get_active_profile as _ec_profile,
    )
    _ollama_base_url: str = _ec_ollama_url()
    _p = _ec_profile()
    _expansion_default_model: str = (_p or {}).get("models", {}).get("llm_kosmos", "") if _p else ""
except Exception:
    _ollama_base_url         = "http://localhost:11434"
    _expansion_default_model = ""

try:
    import bm25s as _bm25s
    _BM25S_AVAILABLE = True
except ImportError:
    _BM25S_AVAILABLE = False

try:
    from flashrank import Ranker as _Ranker, RerankRequest as _RerankRequest  # type: ignore
    _FLASHRANK_AVAILABLE = True
except ImportError:
    _FLASHRANK_AVAILABLE = False

try:
    import sqlite_vec as _sqlite_vec  # type: ignore
    _SQLITE_VEC_AVAILABLE = True
except ImportError:
    _SQLITE_VEC_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer as _SentenceTransformer  # type: ignore
    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False

try:
    from symspellpy import SymSpell as _SymSpell, Verbosity as _Verbosity  # type: ignore
    _SYMSPELL_AVAILABLE = True
except ImportError:
    _SYMSPELL_AVAILABLE = False

try:
    from lingua import Language as _LinguaLang, LanguageDetectorBuilder as _LinguaBuilder  # type: ignore
    _LINGUA_AVAILABLE = True
except ImportError:
    _LINGUA_AVAILABLE = False

_lingua_detector_inst: object | None = None


def _get_lingua_detector() -> object | None:
    """Lazy init do detector lingua-py; carrega modelos só na primeira chamada."""
    global _lingua_detector_inst
    if _lingua_detector_inst is None and _LINGUA_AVAILABLE:
        try:
            _lingua_detector_inst = _LinguaBuilder.from_languages(  # type: ignore[union-attr]
                _LinguaLang.PORTUGUESE, _LinguaLang.ENGLISH, _LinguaLang.CHINESE,  # type: ignore[union-attr]
            ).build()
        except Exception:
            pass
    return _lingua_detector_inst

# ---------------------------------------------------------------------------
# Estado de disponibilidade do Ollama
# Verificado no startup e atualizado periodicamente pelo monitor.
# Qualquer feature LLM (HyDE, síntese, reranking LLM) deve checar essa flag
# antes de tentar se conectar — nunca bloquear o path FTS5 por falta de LLM.
# ---------------------------------------------------------------------------

_ollama_available: bool = False


async def check_ollama_available() -> bool:
    """Tenta conectar ao Ollama via LOGOS (7072) ou direto (11434). Atualiza URL e flag global."""
    global _ollama_available, _ollama_base_url
    try:
        from ecosystem_client import get_ollama_url as _get_url
        _ollama_base_url = _get_url()  # atualiza LOGOS vs direto em runtime
    except Exception:
        pass
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{_ollama_base_url}/api/tags")
            _ollama_available = r.status_code == 200
    except Exception:
        _ollama_available = False
    return _ollama_available


def get_ollama_status() -> bool:
    """Retorna o último estado conhecido do Ollama (sem fazer nova requisição)."""
    return _ollama_available


# ---------------------------------------------------------------------------
# Detecção de idioma + stemming (langdetect + NLTK SnowballStemmer)
# Ambos são opcionais — fallback silencioso se não estiverem instalados.
# ---------------------------------------------------------------------------

try:
    from langdetect import detect as _langdetect  # type: ignore
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False

try:
    from nltk.stem import SnowballStemmer as _SnowballStemmer  # type: ignore
    _NLTK_AVAILABLE = True
except ImportError:
    _NLTK_AVAILABLE = False

_stemmers: dict[str, object] = {}

_STEM_LANG_MAP: dict[str, str] = {
    "pt": "portuguese",
    "en": "english",
}


def _get_stemmer(lang: str) -> object:
    if lang not in _stemmers:
        _stemmers[lang] = _SnowballStemmer(lang)  # type: ignore[operator]
    return _stemmers[lang]

# ---------------------------------------------------------------------------
# ChromaDB — import opcional
# ---------------------------------------------------------------------------

try:
    import chromadb as _chromadb  # type: ignore
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

_chroma_clients: dict[str, object] = {}


def _get_chroma_client(index_path: str) -> object:
    if index_path not in _chroma_clients:
        _chroma_clients[index_path] = _chromadb.PersistentClient(path=index_path)
    return _chroma_clients[index_path]


# ---------------------------------------------------------------------------
# Embedding vetorial (sentence-transformers + sqlite-vec)
# ---------------------------------------------------------------------------

_encoder: object | None = None


def _get_encoder() -> object | None:
    global _encoder
    if _encoder is None and _ST_AVAILABLE:
        try:
            _encoder = _SentenceTransformer(VEC_EMBED_MODEL)  # type: ignore[operator]
        except Exception:
            pass
    return _encoder


def _load_vec_ext(conn: object) -> None:
    """Carrega a extensão sqlite-vec numa conexão sqlite3 (chamado via run_sync)."""
    conn.enable_load_extension(True)   # type: ignore[union-attr]
    _sqlite_vec.load(conn)             # type: ignore[union-attr]
    conn.enable_load_extension(False)  # type: ignore[union-attr]


def _embed_sync(text: str) -> bytes | None:
    """Calcula embedding e serializa como float32 bytes para sqlite-vec (síncrono)."""
    encoder = _get_encoder()
    if encoder is None:
        return None
    try:
        arr = encoder.encode(text, normalize_embeddings=True)  # type: ignore[union-attr]
        return _sqlite_vec.serialize_float32(arr.tolist())     # type: ignore[union-attr]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Correção ortográfica (symspellpy)
# ---------------------------------------------------------------------------

_sym_spell: object | None = None


def init_spell_checker() -> None:
    """Carrega o dicionário EN em memória (síncrono, ~3ms). Chamado no startup."""
    global _sym_spell
    if not SPELL_CORRECTION_ENABLED or not _SYMSPELL_AVAILABLE:
        return
    try:
        import os
        import symspellpy as _symspellpy_pkg  # type: ignore
        sym = _SymSpell(max_dictionary_edit_distance=2, prefix_length=7)  # type: ignore[operator]
        dict_path = os.path.join(
            os.path.dirname(_symspellpy_pkg.__file__),
            "frequency_dictionary_en_82_765.txt",
        )
        sym.load_dictionary(dict_path, term_index=0, count_index=1)
        _sym_spell = sym
    except Exception:
        pass


def correct_query(query: str) -> str | None:
    """Retorna versão corrigida da query ou None se já estiver correta / não aplicável.

    Só corrige queries de ≤ 2 tokens (buscas mais longas raramente são typos isolados).
    """
    if not SPELL_CORRECTION_ENABLED or not _SYMSPELL_AVAILABLE or _sym_spell is None:
        return None
    if len(query.split()) > 2:
        return None
    try:
        suggestions = _sym_spell.lookup_compound(query, max_edit_distance=2)  # type: ignore[union-attr]
        if suggestions and suggestions[0].term.lower() != query.lower():
            return suggestions[0].term
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Frontmatter (YAML simples: chave: valor)
# ---------------------------------------------------------------------------

def _unicode_chunk(text: str, max_chars: int = 8000) -> str:
    """Trunca text em max_chars respeitando limites de parágrafo e palavra.

    Python str é codepoint-safe — slice nunca corta no meio de um char multibyte.
    Prefere cortar em \\n\\n (parágrafo) ou espaço (palavra) antes do truncamento exato.
    """
    if len(text) <= max_chars:
        return text
    idx = text.rfind("\n\n", 0, max_chars)
    if idx > max_chars // 2:
        return text[:idx]
    idx = text.rfind(" ", 0, max_chars)
    if idx > 0:
        return text[:idx]
    return text[:max_chars]


def _detect_lang(text: str) -> str:
    """Detecta idioma de text (amostra de 500 chars). Retorna código ISO 639-1 ou ''.

    Usa lingua-py se instalado (mais preciso), fallback para langdetect.
    Corpus alvo: pt + en + zh.
    """
    sample = text[:500]
    detector = _get_lingua_detector()
    if detector is not None:
        try:
            lang = detector.detect_language_of(sample)  # type: ignore[union-attr]
            if lang is not None:
                return lang.iso_code_639_1.name.lower()  # type: ignore[union-attr]
        except Exception:
            pass
    if _LANGDETECT_AVAILABLE:
        try:
            return _langdetect(sample)
        except Exception:
            pass
    return ""


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extrai frontmatter YAML simples entre --- delimiters."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 4:].strip()
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm, body


def _stem_to_title(stem: str) -> str:
    return stem.replace("-", " ").replace("_", " ").title()


# ---------------------------------------------------------------------------
# Extração de conteúdo por fonte
# ---------------------------------------------------------------------------

def _extract_kosmos(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fm, body = _parse_frontmatter(text)
    title = fm.get("title") or _stem_to_title(path.stem)
    return title, _unicode_chunk(body, 8000)



# ---------------------------------------------------------------------------
# Acesso ao banco
# ---------------------------------------------------------------------------

async def _get_stored_mtime(path_str: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT mtime FROM local_index_meta WHERE path = ?", (path_str,)
        )).fetchone()
    return row[0] if row else None


async def _reindex(path_str: str, title: str, body: str, source: str, mtime: str) -> None:
    lang = _detect_lang(body)
    # Embedding calculado fora da conexão DB (CPU-bound → não bloqueia event loop)
    emb: bytes | None = None
    if VECTOR_SEARCH_ENABLED and _SQLITE_VEC_AVAILABLE and _ST_AVAILABLE:
        loop = asyncio.get_running_loop()
        emb = await loop.run_in_executor(
            None, _embed_sync, f"{title} {body[:2000]}"
        )

    async with aiosqlite.connect(DB_PATH) as db:
        if emb is not None:
            await db.run_sync(_load_vec_ext)
        # Remove entrada anterior do FTS (via rowid para evitar scan completo)
        rows = await (await db.execute(
            "SELECT rowid FROM local_fts WHERE path = ?", (path_str,)
        )).fetchall()
        for (rowid,) in rows:
            await db.execute("DELETE FROM local_fts WHERE rowid = ?", (rowid,))
        # Insere entrada atualizada
        await db.execute(
            "INSERT INTO local_fts (path, title, body, source) VALUES (?, ?, ?, ?)",
            (path_str, title, body, source),
        )
        # Atualiza meta (inclui lang para suporte multilíngue)
        await db.execute(
            "INSERT OR REPLACE INTO local_index_meta (path, source, mtime, lang) VALUES (?, ?, ?, ?)",
            (path_str, source, mtime, lang),
        )
        # Armazena embedding vetorial
        if emb is not None:
            row = await (await db.execute(
                "SELECT id FROM local_vec_paths WHERE path = ?", (path_str,)
            )).fetchone()
            if row:
                vec_id = row[0]
            else:
                cur = await db.execute(
                    "INSERT OR IGNORE INTO local_vec_paths (path) VALUES (?)", (path_str,)
                )
                vec_id = cur.lastrowid
            if vec_id:
                await db.execute(
                    "INSERT OR REPLACE INTO vec_items(rowid, embedding) VALUES (?, ?)",
                    (vec_id, emb),
                )
        await db.commit()


async def _purge_missing() -> None:
    """Remove do índice entradas cujos arquivos não existem mais."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute("SELECT path FROM local_index_meta")).fetchall()

    missing = [row[0] for row in rows if not Path(row[0]).exists()]
    if not missing:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        if VECTOR_SEARCH_ENABLED and _SQLITE_VEC_AVAILABLE:
            try:
                await db.run_sync(_load_vec_ext)
            except Exception:
                pass
        for path_str in missing:
            fts_rows = await (await db.execute(
                "SELECT rowid FROM local_fts WHERE path = ?", (path_str,)
            )).fetchall()
            for (rowid,) in fts_rows:
                await db.execute("DELETE FROM local_fts WHERE rowid = ?", (rowid,))
            await db.execute("DELETE FROM local_index_meta WHERE path = ?", (path_str,))
            # Limpa entradas vetoriais do arquivo removido
            if VECTOR_SEARCH_ENABLED and _SQLITE_VEC_AVAILABLE:
                vp_row = await (await db.execute(
                    "SELECT id FROM local_vec_paths WHERE path = ?", (path_str,)
                )).fetchone()
                if vp_row:
                    await db.execute("DELETE FROM vec_items WHERE rowid = ?", (vp_row[0],))
                    await db.execute("DELETE FROM local_vec_paths WHERE path = ?", (path_str,))
        await db.commit()


# ---------------------------------------------------------------------------
# Indexação por fonte
# ---------------------------------------------------------------------------

async def _index_directory(
    base: Path,
    source: str,
    pattern: str,
    extractor: object,
) -> None:
    if not base.exists():
        return
    for path in base.glob(pattern):
        if not path.is_file():
            continue
        mtime = str(path.stat().st_mtime)
        stored = await _get_stored_mtime(str(path))
        if stored == mtime:
            continue
        try:
            title, body = extractor(path)  # type: ignore[operator]
        except Exception:
            continue
        await _reindex(str(path), title, body, source, mtime)


async def index_local_files() -> None:
    """
    Indexa incrementalmente todos os archives do ecossistema.
    Fontes: KOSMOS, AETHER, AKASHA/data/archive, Mnemosyne watched_dir e vault_dir.
    Remove do índice arquivos que não existem mais.
    Chamado no startup do app.
    """
    if config.kosmos_archive:
        await _index_directory(
            Path(config.kosmos_archive), "KOSMOS", "**/*.md", _extract_kosmos
        )
    await _index_directory(
        config.ARCHIVE_PATH, "AKASHA", "**/*.md", _extract_kosmos
    )
    if config.mnemosyne_watched:
        await _index_directory(
            Path(config.mnemosyne_watched), "MNEMOSYNE", "**/*.md", _extract_kosmos
        )
    if config.mnemosyne_vault:
        await _index_directory(
            Path(config.mnemosyne_vault), "OBSIDIAN", "**/*.md", _extract_kosmos
        )
    if config.hermes_output:
        await _index_directory(
            Path(config.hermes_output), "HERMES", "**/*.md", _extract_kosmos
        )
    await _purge_missing()


async def init_vec_index() -> None:
    """
    Cria a virtual table vec_items (sqlite-vec) se a extensão estiver disponível.
    Deve ser chamada no startup após init_db().
    Se VECTOR_SEARCH_ENABLED=False ou sqlite-vec não estiver instalado, é no-op.
    """
    if not VECTOR_SEARCH_ENABLED or not _SQLITE_VEC_AVAILABLE:
        return
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.run_sync(_load_vec_ext)
            await db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(embedding FLOAT[384])"
            )
            await db.commit()
        # Pré-aquece o encoder para que a primeira busca não seja lenta
        if _ST_AVAILABLE:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _get_encoder)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Snippet por parágrafo (BM25)
# ---------------------------------------------------------------------------

def _best_paragraph(body: str, query: str, max_chars: int = 400) -> str:
    """Retorna o parágrafo de body mais relevante para query via BM25.

    Usado quando SNIPPET_MODE == 'paragraph_bm25'. Fallback para os primeiros
    max_chars do body se bm25s não estiver disponível ou body tiver ≤ 1 parágrafo.
    """
    if not _BM25S_AVAILABLE:
        return body[:max_chars]

    paragraphs = [p.strip() for p in body.split("\n\n") if len(p.strip()) > 30]
    if len(paragraphs) <= 1:
        return (paragraphs[0] if paragraphs else body)[:max_chars]

    try:
        corpus_tokens = _bm25s.tokenize(paragraphs, show_progress=False)
        query_tokens  = _bm25s.tokenize([query],    show_progress=False)
        retriever = _bm25s.BM25()
        retriever.index(corpus_tokens)
        results, _ = retriever.retrieve(query_tokens, corpus=paragraphs, k=1)
        return str(results[0][0])[:max_chars]
    except Exception:
        return paragraphs[0][:max_chars]


# ---------------------------------------------------------------------------
# Re-ranking cross-encoder (FlashRank)
# ---------------------------------------------------------------------------

_ranker: object | None = None


def _get_ranker() -> object | None:
    """Retorna instância singleton do Ranker (carregado na primeira chamada)."""
    global _ranker
    if _ranker is None and _FLASHRANK_AVAILABLE:
        try:
            _ranker = _Ranker(model_name=RERANK_MODEL)  # type: ignore[operator]
        except Exception:
            pass
    return _ranker


def _rerank(results: list[SearchResult], query: str) -> list[SearchResult]:
    """
    Re-ordena resultados usando cross-encoder FlashRank.
    Retorna a lista original inalterada se FlashRank não estiver disponível
    ou se ocorrer qualquer erro durante o re-ranking.
    """
    if not RERANKING_ENABLED or not _FLASHRANK_AVAILABLE:
        return results
    ranker = _get_ranker()
    if ranker is None or not results:
        return results
    try:
        passages = [
            {"id": i, "text": f"{r.title}. {r.snippet}"}
            for i, r in enumerate(results)
        ]
        request = _RerankRequest(query=query, passages=passages)  # type: ignore[operator]
        reranked = ranker.rerank(request)  # type: ignore[union-attr]
        return [results[item["id"]] for item in reranked]
    except Exception:
        return results


# ---------------------------------------------------------------------------
# Expansão de query via LLM (MUST+SHOULD)
# ---------------------------------------------------------------------------

async def _get_expansion_model() -> str:
    """Retorna modelo Ollama a usar para expansão. Resultado cacheado em memória.

    Prioridade: FTS_EXPANSION_MODEL explícito → perfil LOGOS (llm_kosmos) → primeiro
    modelo disponível via /api/tags. LOGOS resolve o melhor modelo para o hardware ativo.
    """
    global _expansion_model_cache
    if _expansion_model_cache:
        return _expansion_model_cache
    if FTS_EXPANSION_MODEL:
        _expansion_model_cache = FTS_EXPANSION_MODEL
        return _expansion_model_cache
    if _expansion_default_model:
        _expansion_model_cache = _expansion_default_model
        return _expansion_model_cache
    # Fallback: primeiro modelo disponível no Ollama (LOGOS ou direto)
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{_ollama_base_url}/api/tags")
            if r.status_code == 200:
                models = r.json().get("models", [])
                if models:
                    _expansion_model_cache = models[0]["name"]
    except Exception:
        pass
    return _expansion_model_cache


async def _anchor_to_corpus(terms: list[str]) -> list[str]:
    """Filtra termos que existem no índice FTS5.

    Evita query drift: termos gerados pelo LLM mas ausentes no arquivo pessoal
    retornam 0 resultados — descartá-los antecipadamente economiza a busca FTS5
    e garante que a expansão só adiciona recall real.
    """
    if not terms:
        return []
    anchored: list[str] = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            for term in terms:
                fts_term = _sanitize_fts(term)
                if not fts_term:
                    continue
                try:
                    row = await (await db.execute(
                        "SELECT 1 FROM local_fts WHERE local_fts MATCH ? LIMIT 1",
                        (fts_term,),
                    )).fetchone()
                    if row:
                        anchored.append(term)
                except Exception:
                    pass
    except Exception:
        return terms  # fallback: usa todos se DB inacessível
    return anchored


async def _expand_query_llm(query: str) -> list[str]:
    """Gera termos de expansão para a query via LLM local (Ollama).

    Retorna lista de termos adicionais — sem repetir a query original. Retorna []
    em qualquer falha (Ollama fora do ar, timeout, output malformado).
    Roda em paralelo com as buscas FTS5 principais para não adicionar latência.
    """
    if not _ollama_available:
        return []
    model = await _get_expansion_model()
    if not model:
        return []
    try:
        import httpx as _httpx
        # Detecta idioma da query para instrução no prompt (corpus multilíngue pt/en/zh)
        _lang_hint = ""
        if _LANGDETECT_AVAILABLE:
            try:
                _qlang = _langdetect(query)
                if _qlang == "pt":
                    _lang_hint = " Os termos devem estar em português."
                elif _qlang in ("zh-cn", "zh-tw", "zh"):
                    _lang_hint = " Os termos devem estar em chinês."
            except Exception:
                pass
        try:
            from services.persona import get_persona as _get_persona
            _persona_prefix = _get_persona().as_prompt_prefix()
        except Exception:
            _persona_prefix = ""
        prompt = (
            f"{_persona_prefix}"
            f'Busca: "{query}"\n'
            f"Liste 3 a 5 termos sinônimos ou fortemente relacionados, separados por vírgula."
            f"{_lang_hint} Apenas os termos, sem explicação, sem numeração."
        )
        async with _httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{_ollama_base_url}/api/generate",
                json={
                    "model":       model,
                    "prompt":      prompt,
                    "stream":      False,
                    "num_predict": 40,
                    "temperature": 0.2,
                },
            )
        if r.status_code != 200:
            return []
        text = r.json().get("response", "").strip()
        raw = [t.strip() for t in re.split(r"[,\n]", text) if t.strip()]
        # Regex estendido para pt/en (À-ÿ) e zh (CJK U+4E00–U+9FFF)
        terms = [
            t.lower() for t in raw
            if re.match(r"^[a-zA-ZÀ-ÿ一-鿿][a-zA-ZÀ-ÿ一-鿿\s]{1,29}$", t)
            and len(t.split()) <= 2
            and t.lower() not in query.lower()
        ]
        return terms[:5]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Busca FTS5
# ---------------------------------------------------------------------------

_PHRASE_RE = re.compile(r'"([^"]+)"')
_FTS_STRIP = re.compile(r"['\(\)\:\^]")


def _expand_token(token: str, lang: str) -> str:
    """Expande 'token' para '(token OR stem*)' se o stem for diferente do token.

    Tokens com * (prefix já explícito) e tokens com < 4 chars não são expandidos
    para evitar ruído. O stem mínimo é 3 chars — abaixo disso o OR seria muito amplo.
    """
    if not _NLTK_AVAILABLE or token.endswith("*") or len(token) < 4:
        return token
    try:
        stemmer = _get_stemmer(lang)
        stem = stemmer.stem(token)  # type: ignore[union-attr]
        if stem and stem != token and len(stem) >= 3:
            return f"({token} OR {stem}*)"
        return token
    except Exception:
        return token


def _expand_query_stems(fts_query: str, original_query: str) -> str:
    """Detecta idioma da query e expande tokens com suas raízes morfológicas.

    Exemplo: query='buscando artigos' (PT detectado) →
             '(buscando OR busc*) (artigos OR artig*)'
    Phrase queries entre aspas não são expandidas.
    Retorna fts_query inalterado se langdetect ou nltk não estiverem disponíveis
    ou se o idioma detectado não for PT nem EN.
    """
    if not _LANGDETECT_AVAILABLE or not _NLTK_AVAILABLE:
        return fts_query
    try:
        code = _langdetect(original_query)
        lang = _STEM_LANG_MAP.get(code)
        if not lang:
            return fts_query
    except Exception:
        return fts_query

    parts: list[str] = []
    cursor = 0
    for m in _PHRASE_RE.finditer(fts_query):
        before = fts_query[cursor:m.start()].strip()
        if before:
            parts.extend(_expand_token(t, lang) for t in before.split())
        parts.append(m.group(0))  # phrase inalterada
        cursor = m.end()
    tail = fts_query[cursor:].strip()
    if tail:
        parts.extend(_expand_token(t, lang) for t in tail.split())
    return " ".join(parts)


def _plain_tokens(text: str) -> list[str]:
    """Tokeniza texto fora de aspas: preserva * no final (prefix), remove no resto."""
    cleaned = _FTS_STRIP.sub(" ", text)
    tokens: list[str] = []
    for tok in cleaned.split():
        if tok.endswith("*"):
            base = tok[:-1].replace("*", "")
            if base:
                tokens.append(base + "*")
        else:
            tok_clean = tok.replace("*", "")
            if tok_clean:
                tokens.append(tok_clean)
    return tokens


def _sanitize_fts(query: str) -> str:
    """Sanitiza query FTS5 preservando phrase queries ("...") e prefix queries (tok*).

    Exemplos:
      'python tutorial'           → 'python tutorial'
      '"machine learning" python' → '"machine learning" python'
      'searc*'                    → 'searc*'
      'bad)char(s'                → 'bad char s'
    """
    query = query.strip()
    if not query:
        return ""
    parts: list[str] = []
    cursor = 0
    for m in _PHRASE_RE.finditer(query):
        before = query[cursor:m.start()]
        if before.strip():
            parts.extend(_plain_tokens(before))
        phrase = m.group(1).strip()
        if phrase:
            parts.append(f'"{phrase}"')
        cursor = m.end()
    tail = query[cursor:]
    if tail.strip():
        parts.extend(_plain_tokens(tail))
    return " ".join(parts)


async def _search_fts(query: str, max_results: int) -> list[SearchResult]:
    fts_query = _sanitize_fts(query)
    if not fts_query:
        return []
    fts_query = _expand_query_stems(fts_query, query)
    results: list[SearchResult] = []
    use_para = SNIPPET_MODE == "paragraph_bm25" and _BM25S_AVAILABLE
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if use_para:
                rows = await (await db.execute(
                    """SELECT path, title, body, source
                       FROM local_fts
                       WHERE local_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (fts_query, max_results),
                )).fetchall()
                results.extend(
                    SearchResult(
                        title=row[1],
                        url=Path(row[0]).as_uri(),
                        snippet=_best_paragraph(row[2] or "", query),
                        source=row[3],
                    )
                    for row in rows
                )
            else:
                rows = await (await db.execute(
                    """SELECT path, title,
                              snippet(local_fts, 2, '', '', '…', 40),
                              source
                       FROM local_fts
                       WHERE local_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (fts_query, max_results),
                )).fetchall()
                results.extend(
                    SearchResult(title=row[1], url=Path(row[0]).as_uri(), snippet=row[2], source=row[3])
                    for row in rows
                )
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Busca ChromaDB (Mnemosyne) — opcional
# ---------------------------------------------------------------------------

async def _generate_hyde(query: str) -> str:
    """Gera documento hipotético (HyDE) para melhorar busca semântica no ChromaDB.

    O embedding do documento hipotético como vetor de busca reduz o gap semântico
    entre a query curta e os documentos longos armazenados no Mnemosyne.
    Retorna "" em qualquer falha — busca cai de volta ao embedding direto da query.
    """
    if not _ollama_available:
        return ""
    model = await _get_expansion_model()
    if not model:
        return ""
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=4.0) as client:
            r = await client.post(
                f"{_ollama_base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": f"Escreva 2-3 frases que responderiam à busca: {query}",
                    "stream": False,
                    "options": {"num_predict": 80, "temperature": 0.3},
                },
            )
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except Exception:
        pass
    return ""


async def _search_chroma(query: str) -> list[SearchResult]:
    if not _CHROMA_AVAILABLE or not config.mnemosyne_indices:
        return []

    # HyDE: usa documento hipotético como query vector quando Ollama disponível
    effective_query = query
    if HYDE_ENABLED and _ollama_available:
        hyde_doc = await _generate_hyde(query)
        if hyde_doc:
            effective_query = hyde_doc

    results: list[SearchResult] = []
    try:
        for index_path in config.mnemosyne_indices:
            client = _get_chroma_client(index_path)
            for col in client.list_collections():
                collection = client.get_collection(col.name)
                qr = collection.query(query_texts=[effective_query], n_results=5)
                docs: list[str] = qr.get("documents", [[]])[0]
                metas: list[dict] = qr.get("metadatas", [[]])[0]
                for doc, meta in zip(docs, metas):
                    results.append(SearchResult(
                        title=str(meta.get("title", "Mnemosyne")),
                        url=str(meta.get("source", "")),
                        snippet=doc[:300],
                        source="MNEMOSYNE",
                    ))
    except Exception:
        pass  # graceful fallback — Mnemosyne é opcional
    return results


# ---------------------------------------------------------------------------
# Merge e ranking combinado
# ---------------------------------------------------------------------------

def _rrf(
    rankings: list[list[SearchResult]],
    k: int = 60,
    weight_fn: object = None,
) -> list[SearchResult]:
    """Reciprocal Rank Fusion com peso opcional por fonte.

    weight_fn: callable(SearchResult) -> float — multiplica o score acumulado
    pelo peso da fonte antes da ordenação final. Sem weight_fn: pesos uniformes.
    """
    scores: dict[str, float]        = {}
    by_url: dict[str, SearchResult] = {}
    for ranking in rankings:
        for rank, result in enumerate(ranking):
            key = result.url.lower().rstrip("/")
            if not key:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            by_url[key] = result
    if weight_fn is not None:
        scores = {
            key: score * weight_fn(by_url[key])  # type: ignore[operator]
            for key, score in scores.items()
        }
    ordered = sorted(scores, key=scores.__getitem__, reverse=True)
    return [by_url[key] for key in ordered]


def _score(result: SearchResult, terms: list[str]) -> int:
    t = result.title.lower()
    s = result.snippet.lower()
    return sum(t.count(term) * 3 + s.count(term) for term in terms)


def rank_combined(
    results: list[SearchResult],
    query: str,
    max_results: int = 500,
) -> list[SearchResult]:
    """Deduplica por URL/path e ordena por relevância de termos. Usado para fontes sem ranking explícito."""
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for r in results:
        key = r.url.lower().rstrip("/")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
    terms = query.lower().split()
    unique.sort(key=lambda r: _score(r, terms), reverse=True)
    return unique[:max_results]


# ---------------------------------------------------------------------------
# Busca vetorial (sqlite-vec KNN)
# ---------------------------------------------------------------------------

async def _search_vec(query: str, max_results: int) -> list[SearchResult]:
    """KNN por embedding no vec_items. Retorna lista vazia se vec não estiver ativo."""
    if not VECTOR_SEARCH_ENABLED or not _SQLITE_VEC_AVAILABLE or not _ST_AVAILABLE:
        return []
    loop = asyncio.get_running_loop()
    emb = await loop.run_in_executor(None, _embed_sync, query)
    if emb is None:
        return []
    results: list[SearchResult] = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.run_sync(_load_vec_ext)
            rows = await (await db.execute(
                """SELECT p.path, COALESCE(m.source, 'AKASHA')
                   FROM vec_items v
                   JOIN local_vec_paths p ON p.id = v.rowid
                   LEFT JOIN local_index_meta m ON m.path = p.path
                   WHERE v.embedding MATCH ?
                   AND k = ?
                   ORDER BY v.distance""",
                (emb, max_results),
            )).fetchall()
        for path_str, source in rows:
            path = Path(path_str)
            results.append(SearchResult(
                title=_stem_to_title(path.stem),
                url=path.as_uri(),
                snippet="",
                source=source,
            ))
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Usage-based ranking
# ---------------------------------------------------------------------------

async def _apply_usage_boost(results: list[SearchResult]) -> list[SearchResult]:
    """Reordena resultados combinando posição RRF com uso histórico e densidade de anotações.

    score = α × (1 / (rank + 1))
          + (1-α) × access_count × exp(-λ × days_since_last)   [se USAGE_RANKING_ENABLED]
          + β × log(1 + highlight_count)                        [se ANNOTATION_DENSITY_ENABLED]

    Retorna a lista original se nenhum dos dois sinais estiver habilitado.
    """
    if not (USAGE_RANKING_ENABLED or ANNOTATION_DENSITY_ENABLED) or not results:
        return results
    import database as _db
    from datetime import datetime, timezone

    urls = [r.url for r in results]
    stats           = await _db.get_access_stats(urls)    if USAGE_RANKING_ENABLED  else {}
    highlight_counts = await _db.get_highlight_counts(urls) if ANNOTATION_DENSITY_ENABLED else {}

    if not stats and not highlight_counts:
        return results

    now = datetime.now(timezone.utc)

    def _usage(url: str) -> float:
        if url not in stats:
            return 0.0
        count, last_str = stats[url]
        try:
            last = datetime.fromisoformat(last_str)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            days = max(0.0, (now - last).total_seconds() / 86400)
        except Exception:
            days = 0.0
        return count * math.exp(-USAGE_RANKING_DECAY * days)

    def _annotation(url: str) -> float:
        return ANNOTATION_DENSITY_BETA * math.log1p(highlight_counts.get(url, 0))

    if USAGE_RANKING_ENABLED:
        scored = [
            (
                USAGE_RANKING_ALPHA * (1.0 / (i + 1))
                + (1.0 - USAGE_RANKING_ALPHA) * _usage(r.url)
                + _annotation(r.url),
                i, r,
            )
            for i, r in enumerate(results)
        ]
    else:
        # Só annotation density: combina com score posicional básico
        scored = [
            ((1.0 / (i + 1)) + _annotation(r.url), i, r)
            for i, r in enumerate(results)
        ]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item[2] for item in scored]


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------

async def _search_highlights(query: str) -> list[SearchResult]:
    """Busca FTS5 em highlights pessoais. Resultados têm source='HIGHLIGHT'."""
    import database as _db
    rows = await _db.search_highlights(query)
    results: list[SearchResult] = []
    for _, url, exact, note in rows:
        snippet = note if note else exact[:200]
        results.append(SearchResult(
            title=exact[:80],
            url=url,
            snippet=snippet,
            source="HIGHLIGHT",
        ))
    return results


# ---------------------------------------------------------------------------
# TF-IDF textual — funções de sugestão (sem LLM)
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset({
    "a", "o", "e", "de", "da", "do", "em", "no", "na", "para", "por", "com",
    "que", "se", "não", "um", "uma", "os", "as", "ao", "dos", "das", "é",
    "the", "and", "or", "of", "to", "in", "is", "it", "for", "on", "at",
    "this", "that", "with", "from", "an", "are", "was", "be", "but", "have",
    "mais", "sua", "seu", "ser", "são", "como", "mas", "foi", "pela", "pelo",
})


def _top_terms(text: str, n: int, exclude: set[str] | None = None) -> list[str]:
    """Extrai os N termos mais frequentes de text, filtrando stopwords e exclude."""
    words = re.findall(r"[a-zA-ZÀ-ÿ]{4,}", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in _STOPWORDS and (exclude is None or w not in exclude):
            freq[w] = freq.get(w, 0) + 1
    return sorted(freq, key=freq.__getitem__, reverse=True)[:n]


async def suggest_related_docs(
    results: list[SearchResult],
    n: int = 5,
) -> list[SearchResult]:
    """Retorna documentos do corpus relacionados aos resultados atuais.

    Extrai os termos mais salientes dos snippets/títulos dos resultados via
    frequência de palavras, executa busca FTS5 silenciosa e retorna documentos
    não presentes nos resultados originais. Sem LLM — puramente textual, < 100ms.
    """
    if not results:
        return []
    text = " ".join(f"{r.title} {r.snippet}" for r in results)
    top = _top_terms(text, 8)
    if not top:
        return []
    fts_query = " OR ".join(top)
    existing = {r.url.lower().rstrip("/") for r in results}
    related: list[SearchResult] = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                """SELECT path, title, snippet(local_fts, 2, '', '', '…', 30), source
                   FROM local_fts
                   WHERE local_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, n + len(results)),
            )).fetchall()
        for row in rows:
            url = Path(row[0]).as_uri()
            if url.lower().rstrip("/") not in existing:
                related.append(SearchResult(
                    title=row[1], url=url, snippet=row[2], source=row[3],
                ))
            if len(related) >= n:
                break
    except Exception:
        pass
    return related


def suggest_related_queries(
    query: str,
    results: list[SearchResult],
    n: int = 3,
) -> list[str]:
    """Sugere tópicos relacionados derivados dos snippets dos resultados atuais.

    Extrai termos salientes dos snippets que não aparecem na query original.
    Retorna como sugestões standalone — o usuário decide se quer explorar.
    Sem LLM — puramente TF-IDF, < 50ms.
    """
    if not results or not query.strip():
        return []
    query_words = set(re.findall(r"[a-zA-ZÀ-ÿ]{3,}", query.lower()))
    text = " ".join(f"{r.title} {r.snippet}" for r in results)
    return _top_terms(text, n * 2, exclude=query_words)[:n]


async def find_related(url: str, n: int = 5) -> list[SearchResult]:
    """Encontra documentos relacionados via TF simplificado sobre FTS5.

    Extrai os termos mais discriminantes do documento apontado por url (frequência
    de palavras no corpo), executa nova busca FTS5 com esses termos, e exclui o
    próprio documento do resultado. Sem dependências externas — FTS5 puro.
    """
    import sys as _sys
    from urllib.parse import unquote as _unquote, urlparse as _urlparse

    parsed = _urlparse(url)
    if parsed.scheme != "file":
        return []
    raw = _unquote(parsed.path)
    if _sys.platform == "win32" and raw.startswith("/"):
        raw = raw[1:]
    path_str = str(Path(raw))

    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT title, body FROM local_fts WHERE path = ?",
            (path_str,),
        )).fetchone()
    if not row:
        return []

    text = f"{row[0] or ''} {row[1] or ''}"
    top_terms = _top_terms(text, 8)
    if not top_terms:
        return []
    fts_query = " OR ".join(top_terms)

    results: list[SearchResult] = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                """SELECT path, title, snippet(local_fts, 2, '', '', '…', 30), source
                   FROM local_fts
                   WHERE local_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, n + 1),
            )).fetchall()
        results = [
            SearchResult(title=row[1], url=Path(row[0]).as_uri(), snippet=row[2], source=row[3])
            for row in rows
            if row[0] != path_str
        ][:n]
    except Exception:
        pass
    return results


async def search_local(
    query: str,
    max_results: int = 500,
    expand: bool = True,
    expansion_log: list | None = None,
) -> list[SearchResult]:
    """Busca local: FTS5 + ChromaDB + sqlite-vec + highlights fundidos via RRF, com re-ranking e usage boost.

    Padrão MUST+SHOULD: a query original é a âncora (FTS obrigatório); termos
    gerados via LLM são aditivos (segundo FTS rodando em paralelo, combinado via RRF).
    Termos expandidos são ancorados ao vocabulário do corpus antes de usar — evita
    query drift por termos plausíveis mas ausentes no arquivo pessoal.

    Args:
        expand: se False, desativa expansão LLM (ex: usuário clicou "desfazer").
        expansion_log: lista mutável; se fornecida, os termos anchorados usados
            são adicionados via .extend() para o chamador exibir na UI.
    """
    # Inicia expansão LLM em paralelo com as buscas principais
    expand_task = None
    if expand and FTS_EXPANSION_ENABLED and _ollama_available:
        expand_task = asyncio.ensure_future(_expand_query_llm(query))

    fts_results       = await _search_fts(query, max_results)
    chroma_results    = await _search_chroma(query)
    vec_results       = await _search_vec(query, max_results)
    highlight_results = await _search_highlights(query)

    # MUST+SHOULD: ancora termos ao corpus e executa segunda busca FTS5 aditiva
    fts_expanded: list[SearchResult] = []
    if expand_task is not None:
        try:
            raw_terms = await asyncio.wait_for(asyncio.shield(expand_task), timeout=3.0)
            if raw_terms:
                anchored = await _anchor_to_corpus(raw_terms)
                if anchored:
                    if expansion_log is not None:
                        expansion_log.extend(anchored)
                    sanitized = [_sanitize_fts(t) for t in anchored]
                    exp_query = " OR ".join(t for t in sanitized if t)
                    if exp_query:
                        fts_expanded = await _search_fts(exp_query, max_results)
        except (asyncio.TimeoutError, Exception):
            expand_task.cancel()

    combined = _rrf(
        [fts_results, fts_expanded, chroma_results, vec_results, highlight_results],
        weight_fn=lambda r: SOURCE_WEIGHTS.get(r.source, 1.0),
    )[:max_results]
    try:
        from services.knowledge_worker import apply_knowledge_boost as _kb_boost
        combined = await _kb_boost(combined, query)
    except Exception:
        pass
    if RERANKING_ENABLED and len(combined) > 1:
        top    = _rerank(combined[:RERANK_TOP_K], query)
        rest   = combined[RERANK_TOP_K:]
        combined = top + rest
    combined = await _apply_usage_boost(combined)
    return combined
