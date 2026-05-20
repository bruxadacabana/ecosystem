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

# ── Cálculo de valência/arousal — backend multilíngue ────────────────────────
# Prioridade de backend: XLM-RoBERTa → NRC-VAD lexicon → VADER → (None, None)
#
# NRC-VAD lexicon (Mohammad 2018): baixar de
#   https://saifmohammad.com/WebPages/nrc-vad-lexicon.html
# e colocar em ~/.cache/ecosystem/nrc_vad_lexicon.tsv
# Formato TSV: Word<TAB>Valence<TAB>Arousal<TAB>Dominance (com cabeçalho)

_xlmr_pipe:  object | None = None                    # lazy: transformers pipeline
_nrc_vad:    dict   | None = None                    # lazy: word → (valence, arousal)
_sia:        object | None = None                    # lazy: VADER fallback
_va_backend: str           = ""                      # resolvido na primeira chamada


def _load_nrc_vad() -> "dict[str, tuple[float, float]] | None":
    nrc_path = Path.home() / ".cache" / "ecosystem" / "nrc_vad_lexicon.tsv"
    if not nrc_path.exists():
        return None
    try:
        data: dict[str, tuple[float, float]] = {}
        with nrc_path.open(encoding="utf-8") as f:
            next(f, None)  # pula cabeçalho
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
            device=-1,  # CPU — GPU reservada para Ollama
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
                # NRC-VAD valence ∈ [0,1] → remapear para [−1,1]
                return round(sum(vals) / len(vals) * 2.0 - 1.0, 4), round(sum(arousals) / len(arousals), 4)
            return None, None

        if _va_backend == "vader" and _sia is not None:
            compound = _sia.polarity_scores(text)["compound"]  # type: ignore[union-attr]
            return round(compound, 4), round(abs(compound), 4)
    except Exception:
        pass
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
        # affective_state — estado emocional ativo da AKASHA (item [F])
        await db.execute("""
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
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_affstate_created ON affective_state(created_at)"
        )
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
