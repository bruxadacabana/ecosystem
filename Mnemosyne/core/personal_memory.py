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
import math
import shutil
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

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

# ── B1: Entropia de Shannon + B2: Decaimento Ebbinghaus ──────────────────────

_EBBINGHAUS_HALFLIFE_H = 72.0
_H_MAX = math.log2(3)
_H_THRESHOLD = 0.8
_PRUNE_H_THRESHOLD = 1.4
_PRUNE_STALE_HOURS = 240.0


def _shannon_entropy(valence: float | None, arousal: float | None) -> float:
    """H ∈ [0, 1.585]. Retorna 1.0 se VA ausente (incerteza neutra).

    Polaridades derivadas: neu = 1−arousal; pos = (arousal+valence)/2;
    neg = (arousal−valence)/2. Exato para XLM-RoBERTa, aproximado para NRC-VAD/VADER.
    """
    if valence is None or arousal is None:
        return 1.0
    neu = max(1e-10, 1.0 - arousal)
    pos = max(1e-10, (arousal + valence) / 2.0)
    neg = max(1e-10, (arousal - valence) / 2.0)
    total = neu + pos + neg
    neu /= total; pos /= total; neg /= total
    return -(pos * math.log2(pos) + neg * math.log2(neg) + neu * math.log2(neu))


def _ebbinghaus_retention(created_at: str, display_count: int) -> float:
    """R = exp(−t / τ) onde τ = S × halflife/ln2, S = 1 + display_count."""
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        t_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
    except Exception:
        t_h = 0.0
    tau = (1.0 + display_count) * _EBBINGHAUS_HALFLIFE_H / math.log(2)
    return math.exp(-t_h / tau)


# ── D: Emotional RAG — vetores Plutchik ──────────────────────────────────────

_PLUTCHIK_LABELS = (
    "joy", "trust", "fear", "surprise", "sadness", "disgust", "anger", "anticipation"
)
_PLUTCHIK_PROMPT = (
    "Avalie o texto abaixo nas 8 emoções primárias de Plutchik "
    "(0.0 = ausente, 1.0 = dominante).\n"
    "Responda APENAS com JSON válido, sem texto adicional:\n"
    '{"joy":X,"trust":X,"fear":X,"surprise":X,"sadness":X,"disgust":X,"anger":X,"anticipation":X}\n\n'
    "Texto: {content}\n\nJSON:"
)


def _va_to_plutchik(valence: float, arousal: float) -> list[float]:
    """Mapeia estado VA para vetor Plutchik aproximado (proxy para mood-congruent retrieval)."""
    v  = max(-1.0, min(1.0, valence))
    a  = max(0.0,  min(1.0, arousal))
    vn = (v + 1.0) / 2.0
    vec = [
        vn * a,
        vn * (1.0 - a),
        (1.0 - vn) * a * 0.6,
        a * (1.0 - abs(v)),
        (1.0 - vn) * (1.0 - a),
        (1.0 - vn) * (1.0 - a) * 0.5,
        (1.0 - vn) * a,
        vn * a * 0.7,
    ]
    total = sum(vec) or 1.0
    return [round(x / total, 4) for x in vec]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def _plutchik_congruence(stored_json: str | None, mood_vec: list[float]) -> float:
    """Cosine similarity entre vetor Plutchik armazenado e humor atual (0–1)."""
    if not stored_json:
        return 0.0
    try:
        data = json.loads(stored_json)
        if isinstance(data, list) and len(data) == 8:
            vec = [float(x) for x in data]
        elif isinstance(data, dict):
            vec = [float(data.get(k, 0.0)) for k in _PLUTCHIK_LABELS]
        else:
            return 0.0
        return _cosine_similarity(vec, mood_vec)
    except Exception:
        return 0.0


# ── C: Zettelkasten / A-Mem — linking de memórias relacionadas ───────────────

_STOPWORDS_ZKN: frozenset = frozenset({
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "por", "para", "com", "uma", "um", "que", "se", "os", "as",
    "ao", "aos", "foi", "ser", "ter", "tem", "está", "mais", "como",
    "the", "and", "for", "are", "but", "not", "can", "has", "was",
    "that", "this", "with", "from", "they", "will", "also", "any",
    "uma", "uns", "umas", "seu", "sua", "seus", "suas", "este", "essa",
    "isso", "aqui", "ali", "bem", "muito", "quando", "onde", "pelo",
    "pela", "pelos", "pelas", "entre", "sobre", "mesmo", "cada",
})


def _zkn_keywords(text: str, max_kw: int = 15) -> list[str]:
    """Extrai keywords por split + filtro de stopwords + comprimento mínimo 3."""
    seen: set[str] = set()
    result: list[str] = []
    for token in text.lower().split():
        word = "".join(c for c in token if c.isalpha())
        if len(word) >= 3 and word not in _STOPWORDS_ZKN and word not in seen:
            seen.add(word)
            result.append(word)
            if len(result) >= max_kw:
                break
    return result


def _zkn_jaccard(a: list[str], b: list[str]) -> float:
    """Jaccard similarity entre dois conjuntos de keywords."""
    sa, sb = set(a), set(b)
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def _zettel_link_bg(memory_id: int, keywords: list[str], db_path: Path) -> None:
    """Liga nova memória a memórias semanticamente relacionadas (A-Mem/Zettelkasten).

    Busca últimas 200 memórias com zettel_keywords preenchidos, calcula Jaccard,
    mantém top-5 com J ≥ 0.15; atualiza zettel_links bidirecionalmente.
    Corre em thread daemon — falhas são suprimidas via log.debug.
    """
    if not keywords:
        return
    try:
        con = sqlite3.connect(str(db_path))
        rows = con.execute(
            "SELECT id, zettel_keywords FROM personal_memory "
            "WHERE id != ? AND zettel_keywords IS NOT NULL "
            "AND zettel_keywords != '[]' "
            "ORDER BY id DESC LIMIT 200",
            (memory_id,),
        ).fetchall()

        scored: list[tuple[int, float]] = []
        for rid, rkw_json in rows:
            try:
                rkw = json.loads(rkw_json or "[]")
            except Exception:
                rkw = []
            if rkw:
                j = _zkn_jaccard(keywords, rkw)
                if j >= 0.15:
                    scored.append((rid, j))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_ids = [rid for rid, _ in scored[:5]]
        if not top_ids:
            con.close()
            return

        con.execute(
            "UPDATE personal_memory SET zettel_links = ? WHERE id = ?",
            (json.dumps(top_ids), memory_id),
        )
        for rid in top_ids:
            row = con.execute(
                "SELECT zettel_links FROM personal_memory WHERE id = ?", (rid,)
            ).fetchone()
            if row:
                existing: list[int] = json.loads(row[0] or "[]")
                if memory_id not in existing:
                    existing.append(memory_id)
                    con.execute(
                        "UPDATE personal_memory SET zettel_links = ? WHERE id = ?",
                        (json.dumps(existing[:10]), rid),
                    )
        con.commit()
        con.close()
    except Exception as exc:
        log.debug("_zettel_link_bg: %s", exc)


def _update_plutchik_bg(memory_id: int, content: str, llm_model: str, db_path: Path) -> None:
    """Atualiza coluna plutchik em background (thread daemon)."""
    try:
        _root = str(db_path.parent.parent.parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from ecosystem_client import request_llm  # type: ignore
        prompt = _PLUTCHIK_PROMPT.format(content=content[:400])
        resp   = request_llm(
            [{"role": "user", "content": prompt}],
            app="mnemosyne", model=llm_model, priority=3,
        )
        raw = (resp.get("message", {}).get("content", "") or "").strip()
        start = raw.find("{"); end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return
        data = json.loads(raw[start:end])
        if isinstance(data, dict):
            vec = [float(data.get(k, 0.0)) for k in _PLUTCHIK_LABELS]
        elif isinstance(data, list) and len(data) == 8:
            vec = [float(x) for x in data]
        else:
            return
        total = sum(vec) or 1.0
        vec   = [round(x / total, 4) for x in vec]
        con   = sqlite3.connect(str(db_path))
        con.execute("UPDATE personal_memory SET plutchik = ? WHERE id = ?",
                    (json.dumps(vec), memory_id))
        con.commit(); con.close()
    except Exception as exc:
        log.debug("_update_plutchik_bg: %s", exc)


def _salience_score(row: tuple) -> float:
    """Score composto: base × Ebbinghaus_R × entropy_factor + type_bonus.

    row: (id, created_at, type, content, tags, feedback, category,
          valence, arousal, importance, display_count)
    """
    valence      = row[7]
    arousal_v    = (row[8] if row[8] is not None else 0.5)
    importance_v = (row[9] if row[9] is not None else 5) / 10.0
    display_c    = int(row[10] or 0)

    base = arousal_v * importance_v
    R    = _ebbinghaus_retention(row[1], display_c)

    H     = _shannon_entropy(valence, row[8])
    h_pen = max(0.0, (H - _H_THRESHOLD) / (_H_MAX - _H_THRESHOLD))
    ent_f = 1.0 - 0.3 * h_pen

    type_bonus = 0.001 if row[2] == "surprise" else 0.0
    return base * R * ent_f + type_bonus


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
            importance     INTEGER          DEFAULT NULL,
            comm_id        INTEGER          DEFAULT NULL
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
    if "display_count" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN display_count INTEGER NOT NULL DEFAULT 0")
    if "last_shown_at" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN last_shown_at TEXT DEFAULT NULL")
    if "plutchik" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN plutchik TEXT DEFAULT NULL")
    if "zettel_keywords" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN zettel_keywords TEXT NOT NULL DEFAULT '[]'")
    if "zettel_links" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN zettel_links TEXT NOT NULL DEFAULT '[]'")
    if "comm_id" not in cols:
        con.execute("ALTER TABLE personal_memory ADD COLUMN comm_id INTEGER DEFAULT NULL")
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
    kws = _zkn_keywords(content)
    import threading
    with _conn() as con:
        cursor = con.execute(
            "INSERT INTO personal_memory "
            "(type, content, tags, category, valence, arousal, importance, zettel_keywords) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (type, content, json.dumps(tags, ensure_ascii=False),
             category, valence, arousal, importance, json.dumps(kws)),
        )
        mid = cursor.lastrowid or 0
    # D: Plutchik — classificação emocional em background (fire-and-forget)
    try:
        _root = str(Path(__file__).parent.parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from ecosystem_client import get_active_profile as _gp  # type: ignore
        _model = (_gp() or {}).get("llm_analysis", (_gp() or {}).get("llm_rag", ""))
        if _model and mid:
            threading.Thread(
                target=_update_plutchik_bg,
                args=(mid, content, _model, _get_db()),
                daemon=True,
            ).start()
    except Exception:
        pass
    # C: Zettelkasten — liga memórias relacionadas em background
    if kws and mid:
        threading.Thread(
            target=_zettel_link_bg,
            args=(mid, kws, _get_db()),
            daemon=True,
        ).start()
    return mid


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

        # H + I-ext + I: curiosidade epistêmica + atribuição causal + appraisal OCC
        def _curiosity_from_feedback(mid: int, fb: str) -> None:
            try:
                from core.affective_state import (
                    get_epistemic_curiosity, record_curiosity_event, record_appraisal,
                )
                con = _conn()
                row = con.execute(
                    "SELECT valence, content FROM personal_memory WHERE id = ?", (mid,)
                ).fetchone()
                con.close()
                valence = (row[0] or 0.0) if row else 0.0
                content = (row[1] or "")  if row else ""

                # I-ext: atribuição causal usando topic_interest_profile
                attribution = "ambiguous"
                try:
                    from core.topic_profile import extract_keywords, get_topic_scores_for_list
                    terms = list(extract_keywords(content))
                    if terms:
                        scores    = get_topic_scores_for_list(terms)
                        max_score = max(scores.values(), default=0.0) if scores else 0.0
                        if max_score > 5.0:
                            attribution = "internal"
                        elif max_score < 1.0:
                            attribution = "external"
                except Exception:
                    pass

                # H + I-ext: intensidade de curiosidade escalada pela atribuição
                if fb == "dismissed" and valence > 0.2:
                    delta = (0.7 if attribution == "internal"
                             else 0.5 if attribution == "ambiguous"
                             else 0.3)
                    record_curiosity_event(delta, event_ref=f"dismissed_{attribution}:mem#{mid}")
                elif fb == "confirmed":
                    current = get_epistemic_curiosity()
                    if current > 0.3:
                        record_curiosity_event(-0.4, event_ref=f"epistemic_satisfied:mem#{mid}")

                # I: appraisal OCC do evento de feedback → estado VA temporário decaível
                if fb == "confirmed":
                    record_appraisal(
                        "feedback_confirmed",
                        novelty=0.15, pleasantness=0.75,
                        goal_relevance=0.80, coping_potential=0.80,
                        event_ref=f"confirmed:mem#{mid}",
                    )
                elif fb == "dismissed":
                    if attribution == "internal":
                        record_appraisal(
                            "feedback_dismissed",
                            novelty=0.40, pleasantness=0.25,
                            goal_relevance=0.70, coping_potential=0.35,
                            event_ref=f"dismissed_internal:mem#{mid}",
                        )
                    elif attribution == "external":
                        record_appraisal(
                            "feedback_dismissed",
                            novelty=0.30, pleasantness=0.45,
                            goal_relevance=0.40, coping_potential=0.60,
                            event_ref=f"dismissed_external:mem#{mid}",
                        )
                    else:
                        record_appraisal(
                            "feedback_dismissed",
                            novelty=0.35, pleasantness=0.40,
                            goal_relevance=0.55, coping_potential=0.50,
                            event_ref=f"dismissed_ambiguous:mem#{mid}",
                        )
            except Exception as exc:
                log.debug("curiosity_from_feedback: %s", exc)

        threading.Thread(
            target=_curiosity_from_feedback, args=(memory_id, feedback), daemon=True
        ).start()


def get_context_memories(n: int = 8) -> list[dict]:
    """Memórias para uso como contexto em reflexões.

    D: rerank por congruência Plutchik com humor atual (mood-congruent retrieval).
    Confirmed sempre preferenciais; dentro de cada grupo, as de assinatura emocional
    mais próxima do humor atual ganham prioridade.
    """
    fetch_n = max(n * 2, 16)
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, "
            "valence, arousal, importance, plutchik, zettel_links "
            "FROM personal_memory "
            "WHERE feedback IS NULL OR feedback = 'confirmed' "
            "LIMIT ?",
            (fetch_n,),
        ).fetchall()

    mood_vec: list[float] = [0.125] * 8
    try:
        from core.affective_state import get_current_state
        state    = get_current_state()
        mood_vec = _va_to_plutchik(state.get("mood_valence", 0.0),
                                   state.get("mood_arousal", 0.5))
    except Exception:
        pass

    def _ctx_score(row: tuple) -> float:
        confirmed  = 1.0 if row[5] == "confirmed" else 0.0
        congruence = _plutchik_congruence(row[10], mood_vec)
        return confirmed + 0.4 * congruence

    top = sorted(rows, key=_ctx_score, reverse=True)[:n]

    # C: Zettelkasten — expandir contexto com memórias linkadas (até n//3 extras)
    top_ids = {r[0] for r in top}
    extra_ids: set[int] = set()
    for r in top:
        try:
            for lid in json.loads(r[11] or "[]"):
                if int(lid) not in top_ids:
                    extra_ids.add(int(lid))
        except Exception:
            pass

    extra_rows: list[tuple] = []
    if extra_ids:
        limit_extra = max(2, n // 3)
        with _conn() as con:
            extra_rows = con.execute(
                f"SELECT id, created_at, type, content, tags, feedback, category, "
                f"valence, arousal, importance FROM personal_memory "
                f"WHERE id IN ({','.join('?' * len(extra_ids))}) "
                f"AND (feedback IS NULL OR feedback = 'confirmed') "
                f"LIMIT ?",
                [*extra_ids, limit_extra],
            ).fetchall()

    result = [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in top
    ]
    for r in extra_rows:
        result.append({
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        })
    return result


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
    """Retorna entradas candidatas a popup ainda não exibidas, ordenadas por escore B1+B2.

    Busca pool de max(n×3, 20) candidatos e ordena em Python:
      score = (arousal × importance/10) × Ebbinghaus_R × (1 − 0.3 × H_penalty) + type_bonus
    B1: penalidade quando H > 0.8 (evidências conflitantes).
    B2: decaimento Ebbinghaus — entradas mais antigas decaem em saliência.
    """
    fetch_n = max(n * 3, 20)
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, "
            "valence, arousal, importance, display_count "
            "FROM personal_memory "
            "WHERE shown_as_popup = 0 "
            "AND type IN ('surprise', 'connection') "
            "AND tags NOT LIKE '%\"cross_insight\"%' "
            "LIMIT ?",
            (fetch_n,),
        ).fetchall()
    top = sorted(rows, key=_salience_score, reverse=True)[:n]
    return [
        {
            "id": r[0], "created_at": r[1], "type": r[2],
            "content": r[3], "tags": json.loads(r[4] or "[]"),
            "feedback": r[5], "category": r[6],
            "valence": r[7], "arousal": r[8], "importance": r[9],
        }
        for r in top
    ]


def get_entry_info(memory_id: int) -> dict | None:
    """Retorna content, importance e comm_id de uma entrada. None se não existir."""
    with _conn() as con:
        row = con.execute(
            "SELECT content, importance, comm_id FROM personal_memory WHERE id = ?",
            (memory_id,),
        ).fetchone()
    if row is None:
        return None
    return {"content": row[0], "importance": row[1], "comm_id": row[2]}


def mark_shown_as_popup(memory_id: int) -> None:
    """Marca entrada como já exibida como popup; incrementa display_count.

    Também registra em communication_history via ecosystem_client e persiste
    o comm_id retornado para que o feedback posterior possa ser associado.
    """
    with _conn() as con:
        row = con.execute(
            "SELECT content, importance, tags FROM personal_memory WHERE id = ?",
            (memory_id,),
        ).fetchone()

        comm_id: int | None = None
        if row:
            try:
                import json as _json
                from ecosystem_client import log_communication  # type: ignore
                tags_raw = row[2] or "[]"
                tags = _json.loads(tags_raw) if isinstance(tags_raw, str) else []
                comm_id = log_communication(
                    source_app="mnemosyne",
                    content=row[0],
                    importance=row[1],
                    tags=tags if isinstance(tags, list) else [],
                )
            except Exception:
                pass

        con.execute(
            "UPDATE personal_memory "
            "SET shown_as_popup = 1, display_count = display_count + 1, "
            "last_shown_at = datetime('now'), comm_id = ? WHERE id = ?",
            (comm_id, memory_id),
        )


def prune_high_entropy_stale(max_delete: int = 20) -> int:
    """Remove entradas antigas (>10d) com alta entropia de Shannon (H > 1.4).

    Entradas com evidências conflitantes que nunca foram exibidas e já esperam
    há muito tempo provavelmente nunca serão relevantes. Retorna nº removidos.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_PRUNE_STALE_HOURS)).isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT id, valence, arousal FROM personal_memory "
            "WHERE shown_as_popup = 0 "
            "AND type IN ('surprise', 'connection') "
            "AND created_at < ?",
            (cutoff,),
        ).fetchall()
        ids_to_del = [r[0] for r in rows
                      if _shannon_entropy(r[1], r[2]) > _PRUNE_H_THRESHOLD][:max_delete]
        if not ids_to_del:
            return 0
        con.execute(
            f"DELETE FROM personal_memory WHERE id IN ({','.join('?' * len(ids_to_del))})",
            ids_to_del,
        )
    return len(ids_to_del)


def clear_all() -> None:
    """Apaga toda a memória pessoal — irreversível."""
    with _conn() as con:
        con.execute("DELETE FROM personal_memory")
