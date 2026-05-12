"""
AKASHA — Busca local nos arquivos do ecossistema
Indexa KOSMOS archive + AETHER vault em FTS5 (SQLite).
ChromaDB (Mnemosyne) é opcional — importação com graceful fallback.
"""
from __future__ import annotations

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

try:
    import bm25s as _bm25s
    _BM25S_AVAILABLE = True
except ImportError:
    _BM25S_AVAILABLE = False

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
# Frontmatter (YAML simples: chave: valor)
# ---------------------------------------------------------------------------

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
    return title, body[:8000]



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
    async with aiosqlite.connect(DB_PATH) as db:
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
        # Atualiza meta
        await db.execute(
            "INSERT OR REPLACE INTO local_index_meta (path, source, mtime) VALUES (?, ?, ?)",
            (path_str, source, mtime),
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
        for path_str in missing:
            fts_rows = await (await db.execute(
                "SELECT rowid FROM local_fts WHERE path = ?", (path_str,)
            )).fetchall()
            for (rowid,) in fts_rows:
                await db.execute("DELETE FROM local_fts WHERE rowid = ?", (rowid,))
            await db.execute("DELETE FROM local_index_meta WHERE path = ?", (path_str,))
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
# Busca FTS5
# ---------------------------------------------------------------------------

_PHRASE_RE    = re.compile(r'"([^"]+)"')
_FTS_STRIP    = re.compile(r"['\(\)\:\^]")


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

async def _search_chroma(query: str) -> list[SearchResult]:
    if not _CHROMA_AVAILABLE or not config.mnemosyne_indices:
        return []
    results: list[SearchResult] = []
    try:
        for index_path in config.mnemosyne_indices:
            client = _get_chroma_client(index_path)
            for col in client.list_collections():
                collection = client.get_collection(col.name)
                qr = collection.query(query_texts=[query], n_results=5)
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

def _rrf(rankings: list[list[SearchResult]], k: int = 60) -> list[SearchResult]:
    scores: dict[str, float]        = {}
    by_url: dict[str, SearchResult] = {}
    for ranking in rankings:
        for rank, result in enumerate(ranking):
            key = result.url.lower().rstrip("/")
            if not key:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            by_url[key] = result
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
# Função pública
# ---------------------------------------------------------------------------

async def search_local(query: str, max_results: int = 500) -> list[SearchResult]:
    """Busca local: FTS5 + ChromaDB fundidos via Reciprocal Rank Fusion."""
    fts_results    = await _search_fts(query, max_results)
    chroma_results = await _search_chroma(query)
    return _rrf([fts_results, chroma_results])[:max_results]
