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
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import asyncio

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


# ── B1: Entropia de Shannon + B2: Decaimento Ebbinghaus ──────────────────────
# DAM-LLM (2025): H(m) = −Σ p_k log₂(p_k) sobre polaridades pos/neg/neu.
# MemoryBank (Zhong et al. AAAI 2024): R = exp(−t / τ), τ = S × halflife/ln2.

_EBBINGHAUS_HALFLIFE_H = 72.0   # halflife em horas para S=1 (~3 dias)
_H_MAX = math.log2(3)           # ≈ 1.585 — entropia máxima para 3 classes
_H_THRESHOLD = 0.8              # abaixo: convicção consolidada
_PRUNE_H_THRESHOLD = 1.4        # H > 1.4 = evidências conflitantes
_PRUNE_STALE_HOURS = 240.0      # 10 dias sem exibição → candidata a poda


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
    """R = exp(−t / τ) onde τ = S × halflife/ln2, S = 1 + display_count.

    t = horas desde created_at. R ≈ 1 = fresco; R ≈ 0 = muito antigo.
    """
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        t_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
    except Exception:
        t_h = 0.0
    tau = (1.0 + display_count) * _EBBINGHAUS_HALFLIFE_H / math.log(2)
    return math.exp(-t_h / tau)


def _salience_score(row: tuple) -> float:
    """Score composto: base × Ebbinghaus_R × entropy_factor + type_bonus.

    row: (id, created_at, type, content, tags, feedback, category,
          valence, arousal, importance, display_count)
    B1: penalty de até 30% quando H > 0.8 (evidências conflitantes).
    B2: decaimento temporal — entradas mais antigas decaem em saliência.
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


# ── D: Emotional RAG — vetores Plutchik ──────────────────────────────────────
# Huang et al. (ICKG2024): codificar memórias nas 8 emoções primárias de Plutchik
# para retrieval mood-congruente (congruência com estado afetivo atual).

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
    """Mapeia estado VA para vetor Plutchik aproximado (proxy para mood-congruent retrieval).

    Baseado no modelo circumplexo de Russell: quadrante VA → emoções Plutchik dominantes.
    """
    v  = max(-1.0, min(1.0, valence))
    a  = max(0.0,  min(1.0, arousal))
    vn = (v + 1.0) / 2.0   # normaliza para [0, 1]
    vec = [
        vn * a,                          # joy       — alta V, alto A
        vn * (1.0 - a),                  # trust     — alta V, baixo A
        (1.0 - vn) * a * 0.6,            # fear      — baixa V, alto A
        a * (1.0 - abs(v)),              # surprise  — neutro + alto A
        (1.0 - vn) * (1.0 - a),         # sadness   — baixa V, baixo A
        (1.0 - vn) * (1.0 - a) * 0.5,   # disgust   — baixa V, baixo A
        (1.0 - vn) * a,                  # anger     — baixa V, alto A
        vn * a * 0.7,                    # anticipation — alta V, alto A
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


def _ensure_eco_path_pm() -> None:
    root = str(Path(__file__).parent.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)


async def _update_plutchik_bg(memory_id: int, content: str, llm_model: str) -> None:
    """Atualiza coluna plutchik em background após save_memory (fire-and-forget)."""
    try:
        _ensure_eco_path_pm()
        from ecosystem_client import request_llm  # type: ignore
        prompt = _PLUTCHIK_PROMPT.format(content=content[:400])
        resp = await asyncio.to_thread(
            request_llm,
            [{"role": "user", "content": prompt}],
            app="akasha", model=llm_model, priority=3,
        )
        raw = (resp.get("message", {}).get("content", "") or "").strip()
        start = raw.find("{")
        end   = raw.rfind("}") + 1
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
        vec = [round(x / total, 4) for x in vec]
        async with aiosqlite.connect(_get_pm_db()) as db:
            await db.execute(
                "UPDATE personal_memory SET plutchik = ? WHERE id = ?",
                (json.dumps(vec), memory_id),
            )
            await db.commit()
    except Exception as exc:
        log.debug("_update_plutchik_bg: %s", exc)


# ── C: Zettelkasten / A-Mem — linking de memórias relacionadas ───────────────
# A-Mem (Xu et al. arXiv:2502.12110, 2025): cada memória como nota estruturada
# com keywords e links bidirecionais para memórias semanticamente relacionadas.
# Implementação: extração rápida de keywords (sem LLM) + Jaccard sobre keywords
# como proxy de similaridade semântica; linking em background fire-and-forget.
# get_context_memories() expande via zettel_links após selecionar top-n.

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


async def _zettel_link_bg(memory_id: int, keywords: list[str]) -> None:
    """Liga nova memória a memórias semanticamente relacionadas (A-Mem/Zettelkasten).

    Busca últimas 200 memórias com zettel_keywords preenchidos, calcula Jaccard,
    mantém top-5 com J ≥ 0.15; atualiza zettel_links bidirecionalmente.
    Limita cada entrada a 10 links para evitar crescimento descontrolado.
    Fire-and-forget — falhas são suprimidas via log.debug.
    """
    if not keywords:
        return
    try:
        async with aiosqlite.connect(_get_pm_db()) as db:
            rows = await (await db.execute(
                "SELECT id, zettel_keywords FROM personal_memory "
                "WHERE id != ? AND zettel_keywords IS NOT NULL "
                "AND zettel_keywords != '[]' "
                "ORDER BY id DESC LIMIT 200",
                (memory_id,),
            )).fetchall()

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
            return

        async with aiosqlite.connect(_get_pm_db()) as db:
            await db.execute(
                "UPDATE personal_memory SET zettel_links = ? WHERE id = ?",
                (json.dumps(top_ids), memory_id),
            )
            for rid in top_ids:
                row = await (await db.execute(
                    "SELECT zettel_links FROM personal_memory WHERE id = ?", (rid,)
                )).fetchone()
                if row:
                    existing: list[int] = json.loads(row[0] or "[]")
                    if memory_id not in existing:
                        existing.append(memory_id)
                        await db.execute(
                            "UPDATE personal_memory SET zettel_links = ? WHERE id = ?",
                            (json.dumps(existing[:10]), rid),
                        )
            await db.commit()
    except Exception as exc:
        log.debug("_zettel_link_bg: %s", exc)


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
            "ALTER TABLE personal_memory ADD COLUMN display_count    INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE personal_memory ADD COLUMN last_shown_at    TEXT    DEFAULT NULL",
            "ALTER TABLE personal_memory ADD COLUMN plutchik         TEXT    DEFAULT NULL",
            "ALTER TABLE personal_memory ADD COLUMN zettel_keywords  TEXT    NOT NULL DEFAULT '[]'",
            "ALTER TABLE personal_memory ADD COLUMN zettel_links     TEXT    NOT NULL DEFAULT '[]'",
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
    kws = _zkn_keywords(content)
    async with aiosqlite.connect(_get_pm_db()) as db:
        cur = await db.execute(
            "INSERT INTO personal_memory "
            "(type, content, tags, category, valence, arousal, importance, zettel_keywords) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (type, content, json.dumps(tags, ensure_ascii=False), category,
             valence, arousal, importance, json.dumps(kws)),
        )
        await db.commit()
        mid = cur.lastrowid  # type: ignore[return-value]
    # D: Plutchik — classificação emocional em background (fire-and-forget)
    try:
        _ensure_eco_path_pm()
        from ecosystem_client import get_active_profile as _gp  # type: ignore
        _model = (_gp() or {}).get("llm_analysis", (_gp() or {}).get("llm_rag", ""))
        if _model and mid:
            asyncio.create_task(_update_plutchik_bg(int(mid), content, _model))
    except Exception:
        pass
    # C: Zettelkasten — liga memórias relacionadas em background
    if kws and mid:
        asyncio.create_task(_zettel_link_bg(int(mid), kws))
    return mid


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
    if feedback in {"confirmed", "dismissed"}:
        import asyncio
        try:
            from services.affective_state import record_approval_momentum
            asyncio.create_task(record_approval_momentum())
        except Exception:
            pass


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

    D: rerank por congruência Plutchik com humor atual (mood-congruent retrieval).
    Confirmed sempre preferenciais; dentro de cada grupo, memórias cuja assinatura
    emocional Plutchik é mais próxima do humor atual ganham prioridade.
    """
    fetch_n = max(n * 2, 16)
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, "
            "valence, arousal, importance, plutchik, zettel_links "
            "FROM personal_memory "
            "WHERE feedback IS NULL OR feedback = 'confirmed' "
            "LIMIT ?",
            (fetch_n,),
        )).fetchall()

    mood_vec: list[float] = [0.125] * 8  # uniforme por padrão
    try:
        from services.affective_state import get_current_state
        state   = await get_current_state()
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

    extra_rows: list = []
    if extra_ids:
        limit_extra = max(2, n // 3)
        async with aiosqlite.connect(_get_pm_db()) as db:
            extra_rows = await (await db.execute(
                f"SELECT id, created_at, type, content, tags, feedback, category, "
                f"valence, arousal, importance FROM personal_memory "
                f"WHERE id IN ({','.join('?' * len(extra_ids))}) "
                f"AND (feedback IS NULL OR feedback = 'confirmed') "
                f"LIMIT ?",
                [*extra_ids, limit_extra],
            )).fetchall()

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


async def get_next_for_overlay(n: int = 5) -> list[dict]:
    """Candidatos para o overlay do browser, ordenados por escore composto B1+B2.

    Busca pool de max(n×3, 20) candidatos e ordena em Python:
      score = (arousal × importance/10) × Ebbinghaus_R × (1 − 0.3 × H_penalty) + type_bonus
    B1: penalidade quando entropia de Shannon H > 0.8 (evidências conflitantes).
    B2: decaimento Ebbinghaus — entradas mais antigas decaem em saliência.
    """
    fetch_n = max(n * 3, 20)
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, created_at, type, content, tags, feedback, category, "
            "valence, arousal, importance, display_count "
            "FROM personal_memory "
            "WHERE shown_as_overlay = 0 "
            "AND type IN ('surprise', 'connection') "
            "LIMIT ?",
            (fetch_n,),
        )).fetchall()
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


async def mark_shown_as_overlay(memory_id: int) -> None:
    """Marca entrada como já exibida no overlay; incrementa display_count."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        await db.execute(
            "UPDATE personal_memory "
            "SET shown_as_overlay = 1, display_count = display_count + 1, "
            "last_shown_at = datetime('now') WHERE id = ?",
            (memory_id,),
        )
        await db.commit()


async def prune_high_entropy_stale(max_delete: int = 20) -> int:
    """Remove entradas antigas (>10d) com alta entropia de Shannon (H > 1.4).

    Entradas com evidências conflitantes que nunca foram exibidas provavelmente
    nunca serão relevantes. Retorna o número de entradas removidas.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_PRUNE_STALE_HOURS)).isoformat()
    async with aiosqlite.connect(_get_pm_db()) as db:
        rows = await (await db.execute(
            "SELECT id, valence, arousal FROM personal_memory "
            "WHERE shown_as_overlay = 0 "
            "AND type IN ('surprise', 'connection') "
            "AND created_at < ?",
            (cutoff,),
        )).fetchall()
    ids_to_del = [r[0] for r in rows
                  if _shannon_entropy(r[1], r[2]) > _PRUNE_H_THRESHOLD][:max_delete]
    if not ids_to_del:
        return 0
    async with aiosqlite.connect(_get_pm_db()) as db:
        await db.execute(
            f"DELETE FROM personal_memory WHERE id IN ({','.join('?' * len(ids_to_del))})",
            ids_to_del,
        )
        await db.commit()
    return len(ids_to_del)


async def clear_all() -> None:
    """Apaga toda a memória pessoal — irreversível."""
    async with aiosqlite.connect(_get_pm_db()) as db:
        await db.execute("DELETE FROM personal_memory")
        await db.commit()
