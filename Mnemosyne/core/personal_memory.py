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

# ── Cálculo de valência/arousal — backend multilíngue ────────────────────────
# Prioridade de backend: XLM-RoBERTa → NRC-VAD lexicon → VADER → (None, None)
#
# NRC-VAD lexicon (Mohammad 2018): baixar de
#   https://saifmohammad.com/WebPages/nrc-vad-lexicon.html
# e colocar em ~/.cache/ecosystem/nrc_vad_lexicon.tsv
# Formato TSV: Word<TAB>Valence<TAB>Arousal<TAB>Dominance (com cabeçalho)

_xlmr_pipe:  object | None = None
_nrc_vad:    dict   | None = None
_sia:        object | None = None
_va_backend: str           = ""


def _load_nrc_vad() -> "dict[str, tuple[float, float]] | None":
    nrc_path = Path.home() / ".cache" / "ecosystem" / "nrc_vad_lexicon.tsv"
    if not nrc_path.exists():
        return None
    try:
        data: dict[str, tuple[float, float]] = {}
        with nrc_path.open(encoding="utf-8") as f:
            next(f, None)
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    word = parts[0].lower()
                    data[word] = (float(parts[1]), float(parts[2]))
        return data or None
    except Exception as exc:
        log.debug("NRC-VAD: falha ao carregar: %s", exc)
        return None


def _resolve_va_backend() -> None:
    global _xlmr_pipe, _nrc_vad, _sia, _va_backend

    try:
        from transformers import pipeline as _hf_pipeline  # type: ignore[import-untyped]
        _xlmr_pipe = _hf_pipeline(
            "text-classification",
            model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
            top_k=None,
            device=-1,
        )
        _va_backend = "xlm_roberta"
        log.debug("VA backend: XLM-RoBERTa")
        return
    except Exception as exc:
        log.debug("XLM-RoBERTa indisponível: %s", exc)

    _nrc_vad = _load_nrc_vad()
    if _nrc_vad:
        _va_backend = "nrc_vad"
        log.debug("VA backend: NRC-VAD (%d palavras)", len(_nrc_vad))
        return

    try:
        import nltk
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        try:
            _sia = SentimentIntensityAnalyzer()
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
            _sia = SentimentIntensityAnalyzer()
        _va_backend = "vader"
        log.debug("VA backend: VADER (fallback inglês)")
        return
    except Exception as exc:
        log.debug("VADER indisponível: %s", exc)

    _va_backend = "none"


def _compute_valence_arousal(text: str) -> tuple[float | None, float | None]:
    """Valence ∈ [−1, 1] e arousal ∈ [0, 1] via modelo multilíngue.

    Backend: XLM-RoBERTa → NRC-VAD lexicon → VADER → (None, None).
    """
    if not _va_backend:
        _resolve_va_backend()
    try:
        if _va_backend == "xlm_roberta" and _xlmr_pipe is not None:
            results = _xlmr_pipe(text[:512], truncation=True)  # type: ignore[operator]
            scores = {r["label"].upper(): r["score"] for r in results[0]}
            pos = scores.get("POSITIVE", scores.get("POS", 0.0))
            neg = scores.get("NEGATIVE", scores.get("NEG", 0.0))
            neu = scores.get("NEUTRAL",  scores.get("NEU", 0.0))
            return round(pos - neg, 4), round(1.0 - neu, 4)

        if _va_backend == "nrc_vad" and _nrc_vad is not None:
            vals, arousals = [], []
            for w in text.lower().split():
                entry = _nrc_vad.get(w)
                if entry:
                    vals.append(entry[0])
                    arousals.append(entry[1])
            if vals:
                return round(sum(vals) / len(vals) * 2.0 - 1.0, 4), round(sum(arousals) / len(arousals), 4)
            return None, None

        if _va_backend == "vader" and _sia is not None:
            compound = _sia.polarity_scores(text)["compound"]  # type: ignore[union-attr]
            return round(compound, 4), round(abs(compound), 4)
    except Exception:
        pass
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
    # affective_state — estado emocional ativo da Mnemosyne (item [F])
    con.execute("""
        CREATE TABLE IF NOT EXISTS affective_state (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            event_type        TEXT    NOT NULL,
            event_ref         TEXT             DEFAULT NULL,
            novelty           REAL             DEFAULT NULL,
            pleasantness      REAL             DEFAULT NULL,
            goal_relevance    REAL             DEFAULT NULL,
            coping_potential  REAL             DEFAULT NULL,
            valence           REAL    NOT NULL,
            arousal           REAL    NOT NULL
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_affstate_created ON affective_state(created_at)"
    )
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
    if feedback in {"confirmed", "dismissed"}:
        import threading
        try:
            from core.affective_state import record_approval_momentum
            threading.Thread(target=record_approval_momentum, daemon=True).start()
        except Exception:
            pass


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
