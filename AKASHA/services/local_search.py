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
# ChromaDB — import opcional
# ---------------------------------------------------------------------------

try:
    import chromadb as _chromadb  # type: ignore
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False


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


def _extract_aether(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    title = _stem_to_title(path.stem)
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return title, text[:8000]


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
    Indexa KOSMOS archive e AETHER vault incrementalmente.
    Remove do índice arquivos que não existem mais.
    Chamado no startup do app.
    """
    if config.kosmos_archive:
        await _index_directory(
            Path(config.kosmos_archive), "KOSMOS", "**/*.md", _extract_kosmos
        )
    if config.aether_vault:
        await _index_directory(
            Path(config.aether_vault), "AETHER", "*/chapters/*.md", _extract_aether
        )
    await _purge_missing()


# ---------------------------------------------------------------------------
# Busca FTS5
# ---------------------------------------------------------------------------

def _sanitize_fts(query: str) -> str:
    """Remove caracteres especiais do FTS5 para evitar erros de sintaxe."""
    cleaned = re.sub(r'["\'\(\)\*\:\^]', " ", query)
    tokens = cleaned.split()
    return " ".join(tokens)


async def _search_fts(query: str, max_results: int) -> list[SearchResult]:
    fts_query = _sanitize_fts(query)
    if not fts_query:
        return []
    results: list[SearchResult] = []
    # Busca em arquivos locais (KOSMOS, AETHER, MNEMOSYNE)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
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
            SearchResult(title=row[1], url=row[0], snippet=row[2], source=row[3])
            for row in rows
        )
    except Exception:
        pass
    # Busca na Biblioteca de URLs
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            lib_rows = await (await db.execute(
                """SELECT url, title,
                          snippet(library_fts, 3, '', '', '…', 40)
                   FROM library_fts
                   WHERE library_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, max_results),
            )).fetchall()
        results.extend(
            SearchResult(title=row[1], url=row[0], snippet=row[2], source="BIBLIOTECA")
            for row in lib_rows
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
            client = _chromadb.PersistentClient(path=index_path)
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

def _score(result: SearchResult, terms: list[str]) -> int:
    t = result.title.lower()
    s = result.snippet.lower()
    return sum(t.count(term) * 3 + s.count(term) for term in terms)


def rank_combined(
    results: list[SearchResult],
    query: str,
    max_results: int = 20,
) -> list[SearchResult]:
    """Deduplica por URL/path e ordena por relevância de termos."""
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

async def search_local(query: str, max_results: int = 20) -> list[SearchResult]:
    """Busca local: FTS5 + ChromaDB (opcional)."""
    fts_results = await _search_fts(query, max_results)
    chroma_results = await _search_chroma(query)
    return rank_combined(fts_results + chroma_results, query, max_results)
