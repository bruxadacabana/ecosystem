"""
AKASHA — Receptor de insights da Mnemosyne.

Poleia ecosystem.json > akasha.incoming_insights a cada 5 minutos.
Quando há insights novos, move para personal_memory com type="connection"
e tag "from_mnemosyne" — nunca indexado no RAG ou vectorstore.

Roda como P3 (background, não-bloqueante). Registrado no lifespan do main.py.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

log = logging.getLogger("akasha.friendship_receiver")

_POLL_INTERVAL_S: float = 300.0   # 5 min entre verificações
_MIN_CONTENT_LEN: int   = 10      # descarta entradas muito curtas

_STOP_WORDS = {
    "sobre", "entre", "quando", "através", "ainda", "muito", "como",
    "mais", "para", "pela", "pelo", "isso", "esta", "esse", "with",
    "that", "this", "from", "have", "there", "their", "where", "which",
    "também", "outro", "outra", "todos", "todas",
}


def _extract_keywords(text: str) -> list[str]:
    """Extrai até 8 palavras-chave únicas com ≥5 chars."""
    import re
    words = re.findall(r"[a-záéíóúàâêîôûãõçüäöë]{5,}", text.lower())
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        if w not in _STOP_WORDS and w not in seen:
            seen.add(w)
            result.append(w)
        if len(result) >= 8:
            break
    return result


async def _find_cross_connection(content: str) -> str | None:
    """Procura em crawl_pages conteúdo local relacionado ao insight recebido.

    Retorna texto da conexão ou None se não encontrado.
    """
    keywords = _extract_keywords(content)
    if len(keywords) < 2:
        return None
    try:
        import aiosqlite
        from database import DB_PATH
        # Testa os dois primeiros keywords no título das páginas crawleadas
        kw1, kw2 = keywords[0], keywords[1]
        async with aiosqlite.connect(DB_PATH) as db:
            row = await (await db.execute(
                "SELECT cp.title, cp.url FROM crawl_pages cp "
                "JOIN crawl_sites cs ON cs.id = cp.site_id "
                "WHERE cs.deleted = 0 AND cp.title IS NOT NULL "
                "AND (cp.title LIKE ? OR cp.title LIKE ?) LIMIT 1",
                (f"%{kw1}%", f"%{kw2}%"),
            )).fetchone()
        if row:
            title = (row[0] or row[1])[:80]
            kw_str = ", ".join(keywords[:3])
            return (
                f"Conexão detectada: insight da Mnemosyne sobre '{kw_str}' "
                f"relaciona-se com conteúdo local indexado: \"{title}\""
            )
    except Exception as exc:
        log.debug("_find_cross_connection: %s", exc)
    return None


def _ensure_ecosystem_client_path() -> None:
    root = str(Path(__file__).parent.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)


async def run_friendship_receiver_loop() -> None:
    """Loop P3: poleia insights da Mnemosyne e persiste em personal_memory."""
    while True:
        await asyncio.sleep(_POLL_INTERVAL_S)
        try:
            await _poll_and_store()
        except Exception as exc:
            log.debug("friendship_receiver: erro no ciclo: %s", exc)


async def _poll_and_store() -> None:
    """Lê akasha.incoming_insights do ecosystem.json e salva em personal_memory."""
    _ensure_ecosystem_client_path()

    try:
        from ecosystem_client import read_ecosystem, write_section  # type: ignore
    except ImportError as exc:
        log.debug("friendship_receiver: ecosystem_client não disponível: %s", exc)
        return

    try:
        eco      = read_ecosystem()
        incoming: list[dict] = eco.get("akasha", {}).get("incoming_insights", [])
    except Exception as exc:
        log.debug("friendship_receiver: leitura ecosystem.json falhou: %s", exc)
        return

    if not incoming:
        return

    from services.personal_memory import save_memory

    saved = 0
    for item in incoming:
        content = (item.get("content") or "").strip()
        if len(content) < _MIN_CONTENT_LEN:
            continue
        tags: list[str] = list(item.get("tags") or [])
        if "from_mnemosyne" not in tags:
            tags.append("from_mnemosyne")
        try:
            await save_memory("connection", content, tags=tags)
            saved += 1
        except Exception as exc:
            log.debug("friendship_receiver: save_memory falhou: %s", exc)
            continue
        # Cross-insight: verifica sobreposição com conteúdo local
        try:
            cross = await _find_cross_connection(content)
            if cross:
                await save_memory("connection", cross, tags=["cross_insight", "from_mnemosyne"])
                log.debug("friendship_receiver: cross-insight gerado para insight recebido")
        except Exception as exc:
            log.debug("friendship_receiver: cross-insight falhou: %s", exc)

    try:
        write_section("akasha", {"incoming_insights": []})
    except Exception as exc:
        log.debug("friendship_receiver: write_section falhou: %s", exc)

    if saved:
        log.info(
            "friendship_receiver: %d pensamento(s) da Mnemosyne salvos em personal_memory.",
            saved,
        )
