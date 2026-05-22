"""
AKASHA — Extração e indexação de imagens com pHash e BK-tree.

Pipeline:
  1. extract_images()     — extrai <img src alt title> de HTML (sem rede)
  2. ImageDeduplicator    — BK-tree in-memory para detecção de near-duplicates
  3. phash_from_bytes()   — calcula pHash 64-bit a partir de bytes de imagem
  4. index_page_images()  — orquestra download best-effort, dedup e INSERT no DB

Sem download permanente: imagens são baixadas em memória para calcular o hash;
nenhum arquivo de imagem é gravado em disco.
"""
from __future__ import annotations

import io
import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

if TYPE_CHECKING:
    import aiosqlite
    import httpx

log = logging.getLogger("akasha.image_indexer")

# Extensões que com alta probabilidade são imagens reais (não ícones SVG de UI)
_IMG_EXTS = re.compile(
    r"\.(jpe?g|png|gif|webp|bmp|tiff?)(\?.*)?$", re.IGNORECASE
)

# Timeout (segundos) para download de imagem durante crawl
_FETCH_TIMEOUT = 3.0

# Distância de Hamming máxima para considerar near-duplicate
_HAMMING_THRESHOLD = 10


# ---------------------------------------------------------------------------
# Extração de metadados de imagens (pura, sem I/O)
# ---------------------------------------------------------------------------

def extract_images(html: str, base_url: str) -> list[dict]:
    """Extrai <img src alt title> de HTML e normaliza as URLs.

    Retorna lista de dicts com chaves: img_url, alt_text, title.
    Exclui: src vazio, URLs não-HTTP, data URIs, imagens SVG inline.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        log.debug("extract_images: BeautifulSoup error: %s", exc)
        return []

    results: list[dict] = []
    seen: set[str] = set()

    for img in soup.find_all("img"):
        src = img.get("src", "").strip()
        if not src or src.startswith("data:"):
            continue

        img_url = urljoin(base_url, src)
        parsed = urlparse(img_url)
        if parsed.scheme not in ("http", "https"):
            continue
        if img_url in seen:
            continue
        seen.add(img_url)

        results.append({
            "img_url":  img_url,
            "alt_text": img.get("alt",   "").strip(),
            "title":    img.get("title", "").strip(),
        })

    return results


# ---------------------------------------------------------------------------
# pHash
# ---------------------------------------------------------------------------

def phash_from_bytes(image_bytes: bytes) -> str:
    """Calcula pHash 64-bit a partir de bytes de imagem.

    Retorna string hex de 16 caracteres (ex: 'a3c4f5b2e1d07890').
    Retorna '' em caso de erro (bytes inválidos, formato não suportado).
    """
    try:
        import imagehash
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        return str(imagehash.phash(img))
    except Exception as exc:
        log.debug("phash_from_bytes: %s", exc)
        return ""


async def _fetch_image_bytes(img_url: str, client: "httpx.AsyncClient") -> bytes:
    """Baixa imagem em memória. Retorna bytes vazios se falhar."""
    try:
        resp = await client.get(img_url, timeout=_FETCH_TIMEOUT)
        if resp.status_code == 200:
            return resp.content
    except Exception as exc:
        log.debug("_fetch_image: %s: %s", img_url, exc)
    return b""


# ---------------------------------------------------------------------------
# BK-tree in-memory para deduplicação por pHash
# ---------------------------------------------------------------------------

def _hamming_int(a: int, b: int) -> int:
    """Distância de Hamming entre dois inteiros."""
    return bin(a ^ b).count("1")


class ImageDeduplicator:
    """BK-tree in-memory para deduplicação de imagens por pHash.

    Mantido por sessão de crawl. Imagens com distância de Hamming ≤ threshold
    são consideradas near-duplicates e rejeitadas.

    Usa pybktree com distância de Hamming sobre inteiros de 64 bits
    (pHash armazenado como hex string, convertido internamente para int).
    """

    def __init__(self, threshold: int = _HAMMING_THRESHOLD) -> None:
        import pybktree
        self._tree: pybktree.BKTree = pybktree.BKTree(_hamming_int)
        self._threshold = threshold

    def _to_int(self, phash_hex: str) -> int | None:
        """Converte hex pHash para int. Retorna None se inválido."""
        try:
            return int(phash_hex, 16)
        except ValueError:
            return None

    def is_duplicate(self, phash_hex: str) -> bool:
        """Retorna True se há um hash similar (Hamming ≤ threshold) no índice."""
        h = self._to_int(phash_hex)
        if h is None:
            return False
        results = self._tree.find(h, self._threshold)
        return len(results) > 0

    def add(self, phash_hex: str) -> None:
        """Adiciona pHash ao índice. Silenciosamente ignora hexes inválidos."""
        h = self._to_int(phash_hex)
        if h is not None:
            self._tree.add(h)

    def load_from_db_hashes(self, hashes: list[str]) -> None:
        """Pré-carrega hashes existentes do DB para detectar duplicates entre sessões."""
        for h in hashes:
            self.add(h)


# ---------------------------------------------------------------------------
# Pipeline completo: extração + pHash + dedup + INSERT
# ---------------------------------------------------------------------------

async def index_page_images(
    db: "aiosqlite.Connection",
    page_url: str,
    images: list[dict],
    client: "httpx.AsyncClient",
    deduplicator: ImageDeduplicator,
) -> int:
    """Índice imagens de uma página no DB.

    Para cada imagem:
      1. Verifica se img_url já existe (dedup exata por URL)
      2. Tenta baixar e calcular pHash (best-effort, falha silenciosamente)
      3. Verifica near-duplicate via BK-tree (Hamming ≤ 10)
      4. Insere em page_images + page_images_fts

    Retorna número de imagens indexadas.
    """
    indexed = 0
    for img in images:
        img_url  = img["img_url"]
        alt_text = img["alt_text"]
        title    = img["title"]

        # Skip sem alt_text nem title: sem texto para busca, não vale indexar
        if not alt_text and not title:
            continue

        # Dedup por URL exata
        existing = await (await db.execute(
            "SELECT 1 FROM page_images WHERE img_url = ? LIMIT 1", (img_url,)
        )).fetchone()
        if existing:
            continue

        # pHash best-effort (só para imagens com extensão conhecida)
        phash = ""
        if _IMG_EXTS.search(img_url):
            img_bytes = await _fetch_image_bytes(img_url, client)
            if img_bytes:
                phash = phash_from_bytes(img_bytes)

        # Near-duplicate check via BK-tree
        if phash and deduplicator.is_duplicate(phash):
            log.debug("near-duplicate ignorada: %s (phash=%s)", img_url, phash)
            continue

        now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            """INSERT OR IGNORE INTO page_images
               (page_url, img_url, alt_text, title, phash, crawled_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (page_url, img_url, alt_text, title, phash, now),
        )
        await db.execute(
            """INSERT OR REPLACE INTO page_images_fts
               (img_url, page_url, alt_text, title, phash)
               VALUES (?, ?, ?, ?, ?)""",
            (img_url, page_url, alt_text, title, phash),
        )

        if phash:
            deduplicator.add(phash)
        indexed += 1

    return indexed


async def search_images(
    db: "aiosqlite.Connection",
    query: str,
    limit: int = 20,
) -> list[dict]:
    """Busca FTS5 sobre alt_text + title de imagens indexadas.

    Retorna lista de dicts: img_url, page_url, alt_text, title, phash.
    """
    if not query.strip():
        return []

    # Sanitiza query para FTS5: remove caracteres especiais
    fts_query = re.sub(r"[\"'()\[\]^:*]", " ", query).strip()
    if not fts_query:
        return []

    try:
        rows = await (await db.execute(
            """SELECT img_url, page_url, alt_text, title, phash
               FROM page_images_fts
               WHERE page_images_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (fts_query, limit),
        )).fetchall()
    except Exception as exc:
        log.debug("search_images FTS5 error: %s", exc)
        return []

    return [
        {
            "img_url":  r[0],
            "page_url": r[1],
            "alt_text": r[2],
            "title":    r[3],
            "phash":    r[4],
        }
        for r in rows
    ]
