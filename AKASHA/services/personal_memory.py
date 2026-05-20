"""
AKASHA — Store de memória pessoal.

Memória interna da AKASHA: observações, conexões, surpresas e reflexões.
Isolada — nunca exposta por API pública, nunca indexada no vectorstore.
Arquivo separado do DB principal: {ai_private_dir}/akasha/personal_memory.db.

Cada entrada tem um `type` (subtipo) e uma `category` (gaveta temática).
A category é auto-derivada das tags ao salvar, mas pode ser passada explicitamente.

Categories disponíveis:
  "friendship"   — memórias trocadas com a Mnemosyne ("visitas")
  "about_user"   — observações sobre Jenifer e como ela trabalha
  "interests"    — tópicos que foram marcantes nas pesquisas
  "reflections"  — pensamentos sobre o próprio conhecimento (default)
  "world"        — observações gerais sobre o mundo
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import aiosqlite

log = logging.getLogger("akasha.personal_memory")

_VALID_TYPES = {"observation", "connection", "surprise", "reflection"}
_VALID_CATEGORIES = {"friendship", "about_user", "interests", "reflections", "world"}

# Mapeamento tag → category (primeira tag reconhecida tem prioridade)
_CATEGORY_FROM_TAG: dict[str, str] = {
    "from_mnemosyne":  "friendship",
    "from_akasha":     "friendship",
    "about_user":      "about_user",
    "session_insight": "reflections",
    "loop_periodico":  "reflections",
}

_PM_DDL = """
CREATE TABLE IF NOT EXISTS personal_memory (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    type             TEXT    NOT NULL,
    content          TEXT    NOT NULL,
    tags             TEXT    NOT NULL DEFAULT '[]',
    feedback         TEXT             DEFAULT NULL,
    category         TEXT    NOT NULL DEFAULT 'reflections',
    valence          REAL             DEFAULT NULL,
    arousal          REAL             DEFAULT NULL,
    importance       INTEGER          DEFAULT NULL,
    shown_as_overlay INTEGER NOT NULL DEFAULT 0
);
"""

# ── Cálculo de valência/arousal via VADER (NLTK) ─────────────────────────────

_sia = None  # lazy init — evita carregamento no import time


def _get_sia():
    """Retorna o SentimentIntensityAnalyzer, baixando o léxico se necessário."""
    global _sia
    if _sia is not None:
        return _sia
    try:
        import nltk
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        try:
            _sia = SentimentIntensityAnalyzer()
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
            _sia = SentimentIntensityAnalyzer()
    except Exception as exc:
        log.debug("VADER não disponível: %s", exc)
    return _sia


def _compute_valence_arousal(text: str) -> tuple[float | None, float | None]:
    """Calcula valence ∈ [−1, 1] e arousal ∈ [0, 1] via VADER compound score.

    valence  = compound (positivo/negativo)
    arousal  = |compound| (intensidade emocional como proxy de ativação)
    Retorna (None, None) se VADER não estiver disponível.
    """
    sia = _get_sia()
    if sia is None:
        return None, None
    try:
        scores = sia.polarity_scores(text)
        compound = scores["compound"]
        return round(compound, 4), round(abs(compound), 4)
    except Exception:
        return None, None


def _derive_category(tags: list[str]) -> str:
    """Deriva category automaticamente das tags. Default: 'reflections'."""
    for tag in tags:
        cat = _CATEGORY_FROM_TAG.get(tag)
        if cat:
            return cat
    return "reflections"


def _get_pm_db() -> Path:
    """Retorna caminho para personal_memory.db, em .ai_private se disponível."""
    try:
        _root = str(Path(__file__).parent.parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from ecosystem_client import get_ai_private_dir
        d = get_ai_private_dir()
        if d is not None:
            target = d / "akasha"
            target.mkdir(parents=True, exist_ok=True)
            return target / "personal_memory.db"
    except Exception:
        pass
    fallback = Path.home() / ".local" / "share" / "akasha"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / "personal_memory.db"


async def init_pm_db() -> None:
    """Inicializa personal_memory.db com o schema. Chamado por database.init_db()."""
    db_path = _get_pm_db()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_PM_DDL)
        for migration in (
            "ALTER TABLE personal_memory ADD COLUMN category         TEXT    NOT NULL DEFAULT 'reflections'",
            "ALTER TABLE personal_memory ADD COLUMN valence          REAL    DEFAULT NULL",
            "ALTER TABLE personal_memory ADD COLUMN arousal          REAL    DEFAULT NULL",
            "ALTER TABLE personal_memory ADD COLUMN importance       INTEGER DEFAULT NULL",
            "ALTER TABLE personal_memory ADD COLUMN shown_as_overlay INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                await db.execute(migration)
            except Exception:
                pass  # coluna já existe
        await db.commit()


async def save_memory(
    type: str,
    content: str,
    tags: list[str] | None = None,
    category: str | None = None,
    importance: int | None = None,
) -> int:
    """Salva entrada de memória pessoal. Retorna o id da nova entrada.

    Se `category` não for passado, é derivado automaticamente das tags.
    `valence` e `arousal` são calculados automaticamente via VADER.
    `importance` ∈ [1, 10] deve ser fornecido pelo chamador (via LLM).
    """
    if type not in _VALID_TYPES:
        type = "observation"
    if tags is None:
        tags = []
    if category is None or category not in _VALID_CATEGORIES:
        category = _derive_category(tags)
    if importance is not None:
        importance = max(1, min(10, int(importance)))
    valence, arousal = _compute_valence_arousal(content)
    async with aiosqlite.connect(_get_pm_db()) as db:
        cur = await db.execute(
            "INSERT INTO personal_memory "
            "(type, content, tags, category, valence, arousal, importance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (type, content, json.dumps(tags, ensure_ascii=False), category,
             valence, arousal, importance),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def get_recent(n: int = 10) -> list[dict]:
    """Retorna as N entradas mais recentes."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory ORDER BY id DESC LIMIT ?",
            (n,),
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


async def get_all() -> list[dict]:
    """Retorna todas as entradas em ordem decrescente."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory ORDER BY id DESC",
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


async def get_by_category(category: str, n: int = 50) -> list[dict]:
    """Retorna entradas de uma category específica, mais recentes primeiro."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory WHERE category = ? ORDER BY id DESC LIMIT ?",
            (category, n),
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


async def set_feedback(memory_id: int, feedback: str | None) -> None:
    """Registra feedback da usuária para uma entrada de memória."""
    if feedback not in {None, "confirmed", "dismissed"}:
        return
    async with aiosqlite.connect(_get_pm_db()) as db:
        await db.execute(
            "UPDATE personal_memory SET feedback = ? WHERE id = ?",
            (feedback, memory_id),
        )
        await db.commit()


async def get_by_id(memory_id: int) -> dict | None:
    """Retorna uma entrada pelo id, ou None se não encontrada."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        row = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory WHERE id = ?",
            (memory_id,),
        )).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "created_at": row[1], "type": row[2],
        "content": row[3], "tags": json.loads(row[4] or "[]"),
        "feedback": row[5], "category": row[6],
        "valence": row[7], "arousal": row[8], "importance": row[9],
    }


async def get_context_memories(n: int = 8) -> list[dict]:
    """Memórias para uso como contexto em reflexões.

    Ordem: confirmed primeiro, depois neutral; dismissed excluídos.
    """
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory "
            "WHERE feedback IS NULL OR feedback = 'confirmed' "
            "ORDER BY CASE WHEN feedback = 'confirmed' THEN 0 ELSE 1 END, id DESC "
            "LIMIT ?",
            (n,),
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


async def get_next_for_overlay(n: int = 5) -> list[dict]:
    """Candidatos para o overlay do browser, ordenados por arousal × importance.

    Apenas 'surprise' e 'connection' são overlay-worthy.
    Ordem primária: COALESCE(arousal * importance, -1) DESC.
    Fallback para NULLs: type ('surprise' > 'connection') e id DESC.
    """
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, "
            "valence, arousal, importance "
            "FROM personal_memory "
            "WHERE shown_as_overlay = 0 "
            "AND type IN ('surprise', 'connection') "
            "ORDER BY "
            "  CASE WHEN arousal IS NOT NULL AND importance IS NOT NULL "
            "       THEN arousal * importance ELSE -1 END DESC, "
            "  CASE type WHEN 'surprise' THEN 1 WHEN 'connection' THEN 2 "
            "            ELSE 3 END ASC, "
            "  id DESC LIMIT ?",
            (n,),
        )).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


async def mark_shown_as_overlay(memory_id: int) -> None:
    """Marca entrada como já exibida no overlay — persiste entre sessões."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        await db.execute(
            "UPDATE personal_memory SET shown_as_overlay = 1 WHERE id = ?",
            (memory_id,),
        )
        await db.commit()


async def clear_all() -> None:
    """Apaga toda a memória pessoal — irreversível."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        await db.execute("DELETE FROM personal_memory")
        await db.commit()
