"""
Mnemosyne — Store de memória pessoal.

Memória interna da Mnemosyne: observações, conexões, surpresas e reflexões
geradas a partir do conhecimento processado. Separada do Chroma/BM25 e nunca
indexada no RAG de coleções.

Cada entrada tem um `type` (subtipo da memória) e uma `category` (gaveta
temática). A category é auto-derivada das tags ao salvar, mas pode ser
passada explicitamente.

Categories disponíveis:
  "friendship"   — memórias trocadas com a AKASHA ("visitas")
  "about_user"   — observações sobre Jenifer e como ela trabalha
  "interests"    — tópicos que foram marcantes na indexação
  "reflections"  — pensamentos sobre o próprio conhecimento (default)
  "world"        — observações gerais sobre o mundo
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import shutil
import sys

from .config import get_app_data_dir

log = logging.getLogger("mnemosyne.personal_memory")

# ── Cálculo de valência/arousal via VADER (NLTK) ─────────────────────────────

_sia = None  # lazy init


def _get_sia():
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
    """valence = compound ∈ [−1,1]; arousal = |compound| ∈ [0,1]."""
    sia = _get_sia()
    if sia is None:
        return None, None
    try:
        compound = sia.polarity_scores(text)["compound"]
        return round(compound, 4), round(abs(compound), 4)
    except Exception:
        return None, None

_DB_PATH: Path | None = None

# Mapeamento tag → category (primeiras tags reconhecidas têm prioridade)
_CATEGORY_FROM_TAG: dict[str, str] = {
    "from_akasha":     "friendship",
    "from_mnemosyne":  "friendship",
    "about_user":      "about_user",
    "session_insight": "reflections",
    "loop_periodico":  "reflections",
}

_VALID_CATEGORIES = {"friendship", "about_user", "interests", "reflections", "world"}


def _derive_category(tags: list[str]) -> str:
    """Deriva category automaticamente das tags. Default: 'reflections'."""
    for tag in tags:
        cat = _CATEGORY_FROM_TAG.get(tag)
        if cat:
            return cat
    return "reflections"


def _resolve_pm_db() -> Path:
    """Resolve caminho de personal_memory.db.

    Prefere {ai_private_dir}/mnemosyne/personal_memory.db quando sync_root
    configurado. Na primeira execução com novo caminho, copia o arquivo
    antigo para o novo local e renomeia o original para .db.bak.
    """
    try:
        _root = str(Path(__file__).parent.parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from ecosystem_client import get_ai_private_dir  # type: ignore
        d = get_ai_private_dir()
        if d is not None:
            new_dir = d / "mnemosyne"
            new_dir.mkdir(parents=True, exist_ok=True)
            new_path = new_dir / "personal_memory.db"
            old_path = get_app_data_dir() / "personal_memory.db"
            if not new_path.exists() and old_path.exists():
                shutil.copy2(str(old_path), str(new_path))
                try:
                    old_path.rename(old_path.with_suffix(".db.bak"))
                except OSError:
                    pass
            return new_path
    except Exception:
        pass
    return get_app_data_dir() / "personal_memory.db"


def _get_db() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _resolve_pm_db()
    return _DB_PATH


def _conn() -> sqlite3.Connection:
    db = _get_db()
    con = sqlite3.connect(db)
    con.execute("""
        CREATE TABLE IF NOT EXISTS personal_memory (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
            type           TEXT    NOT NULL,
            content        TEXT    NOT NULL,
            tags           TEXT    NOT NULL DEFAULT '[]',
            feedback       TEXT             DEFAULT NULL,
            shown_as_popup INTEGER NOT NULL DEFAULT 0,
            category       TEXT    NOT NULL DEFAULT 'reflections',
            valence        REAL             DEFAULT NULL,
            arousal        REAL             DEFAULT NULL,
            importance     INTEGER          DEFAULT NULL
        )
    """)
    # Migrations para DBs anteriores
    cols = {row[1] for row in con.execute("PRAGMA table_info(personal_memory)").fetchall()}
    if "feedback" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN feedback TEXT DEFAULT NULL")
    if "shown_as_popup" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN shown_as_popup INTEGER NOT NULL DEFAULT 0")
    if "category" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN category TEXT NOT NULL DEFAULT 'reflections'")
    if "valence" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN valence REAL DEFAULT NULL")
    if "arousal" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN arousal REAL DEFAULT NULL")
    if "importance" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN importance INTEGER DEFAULT NULL")
    con.commit()
    return con


_VALID_TYPES = {"observation", "connection", "surprise", "reflection"}


def save_memory(
    type: str,
    content: str,
    tags: list[str] | None = None,
    category: str | None = None,
    importance: int | None = None,
) -> int:
    """Salva entrada de memória pessoal. Retorna o ID inserido.

    Se `category` não for passado, é derivado automaticamente das tags.
    valence e arousal são calculados automaticamente via VADER.
    importance ∈ [1, 10] deve ser fornecido pelo chamador (via LLM).
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
    with _conn() as con:
        cursor = con.execute(
            "INSERT INTO personal_memory "
            "(type, content, tags, category, valence, arousal, importance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (type, content, json.dumps(tags, ensure_ascii=False),
             category, valence, arousal, importance),
        )
        return cursor.lastrowid or 0


def get_recent(n: int = 10) -> list[dict]:
    """Retorna as N entradas mais recentes."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


def get_all() -> list[dict]:
    """Retorna todas as entradas em ordem decrescente."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory ORDER BY id DESC",
        ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


def get_by_category(category: str, n: int = 50) -> list[dict]:
    """Retorna entradas de uma category específica, mais recentes primeiro."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory WHERE category = ? ORDER BY id DESC LIMIT ?",
            (category, n),
        ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


def set_feedback(memory_id: int, feedback: str | None) -> None:
    """Registra feedback da usuária para uma entrada de memória."""
    if feedback not in {None, "confirmed", "dismissed"}:
        return
    with _conn() as con:
        con.execute(
            "UPDATE personal_memory SET feedback = ? WHERE id = ?",
            (feedback, memory_id),
        )


def get_context_memories(n: int = 8) -> list[dict]:
    """Memórias para uso como contexto em reflexões.

    Ordem: confirmed primeiro, depois neutral; dismissed excluídos.
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory "
            "WHERE feedback IS NULL OR feedback = 'confirmed' "
            "ORDER BY CASE WHEN feedback = 'confirmed' THEN 0 ELSE 1 END, id DESC "
            "LIMIT ?",
            (n,),
        ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


def get_by_id(memory_id: int) -> dict | None:
    """Retorna uma entrada pelo id, ou None se não encontrada."""
    with _conn() as con:
        row = con.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory WHERE id = ?",
            (memory_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "created_at": row[1], "type": row[2],
        "content": row[3], "tags": json.loads(row[4] or "[]"),
        "feedback": row[5], "category": row[6],
        "valence": row[7], "arousal": row[8], "importance": row[9],
    }


def has_file_reflection(name_prefix: str) -> bool:
    """Retorna True se já existe reflexão sobre este arquivo (deduplicação)."""
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM personal_memory "
            "WHERE tags LIKE ? AND tags LIKE ? LIMIT 1",
            ('%"leitura"%', f'%{name_prefix}%'),
        ).fetchone()
    return row is not None


def get_unshown_popup_entries(n: int = 5) -> list[dict]:
    """Retorna entradas candidatas a popup ainda não exibidas.

    Apenas 'surprise' e 'connection' são popup-worthy — 'observation' e
    'reflection' ficam só na memória, nunca interrompem a usuária.
    Cross-insights internos (tag 'cross_insight') também excluídos.

    Ordem primária: arousal × importance DESC NULLS LAST.
    Fallback (campos NULL): type ('surprise' > 'connection') e id DESC.
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, valence, arousal, importance "
            "FROM personal_memory "
            "WHERE shown_as_popup = 0 "
            "AND type IN ('surprise', 'connection') "
            "AND tags NOT LIKE '%\"cross_insight\"%' "
            "ORDER BY "
            "  CASE WHEN arousal IS NOT NULL AND importance IS NOT NULL "
            "       THEN arousal * importance ELSE -1 END DESC, "
            "  CASE type WHEN 'surprise' THEN 1 WHEN 'connection' THEN 2 "
            "            ELSE 3 END ASC, "
            "  id DESC LIMIT ?",
            (n,),
        ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in rows
    ]


def mark_shown_as_popup(memory_id: int) -> None:
    """Marca uma entrada como já exibida como popup — persiste entre sessões."""
    with _conn() as con:
        con.execute(
            "UPDATE personal_memory SET shown_as_popup = 1 WHERE id = ?",
            (memory_id,),
        )


def clear_all() -> None:
    """Apaga toda a memória pessoal — irreversível."""
    with _conn() as con:
        con.execute("DELETE FROM personal_memory")
