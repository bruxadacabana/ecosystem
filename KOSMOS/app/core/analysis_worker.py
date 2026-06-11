"""
analysis_worker.py — AnalysisWorker: análise AI dos artigos via LOGOS, em duas calls.

Duas filas orquestradas num único QThread (sem concorrência real — processamento
serial com preempção):

  • Pré-análise P3 (background, contínua, newest-first): roda a **Call A rápida**
    (tags, sentimento, clickbait, idioma, resumo) nos artigos `pending`/`failed`,
    dando aos cards sua cor/chips. Nunca bloqueia; LOGOS offline → artigo volta a
    `pending` e há back-off.
  • Análise completa P1 (artigo aberto pela usuária): roda a **Call B rica** (cinco
    Ws, entidades, viés político) — e a Call A antes, se ainda faltar. Preempta o
    lote P3 (a usuária está esperando).

Saída estruturada por **prompt-e-parseia**: o prompt pede JSON estrito e o parser
(`_extract_json`) é tolerante a ruído/cercas markdown/vírgulas finais; 1 retry por
call. Sem gramática GBNF nem response_format — não toca código compartilhado.

Schema versioning (`ANALYSIS_SCHEMA_VERSION`): ao subir a versão do prompt, artigos
com versão antiga são re-analisados. TTL: 5W/entidades de artigos > 6 meses são
zerados (tags/sentimento permanecem) para conter o crescimento do banco sincronizado.
"""
from __future__ import annotations

import json
import logging
import queue
import re
import sqlite3

from PySide6.QtCore import QThread, Signal

from app.core import logos_client
from app.core.database import get_conn
from app.core.logos_client import LogosUnavailable

log = logging.getLogger("kosmos.analysis_worker")

# Subir esta versão quando os prompts/campos mudarem → força re-análise dos antigos.
ANALYSIS_SCHEMA_VERSION = 1

_BATCH_SIZE = 8            # artigos pré-analisados (Call A) por ciclo P3
_IDLE_INTERVAL_SEC = 30   # pausa interruptível entre ciclos
_TTL_EVERY_CYCLES = 60    # periodicidade do TTL (~30min com idle de 30s)
_BODY_LIMIT = 4000        # nº de chars do corpo enviados ao LLM
_SENTIMENTS = ("positivo", "neutro", "negativo")


# ===========================================================================
# Parsing tolerante de JSON
# ===========================================================================

def _try_loads(s: str) -> "dict | None":
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_json(text: str) -> "dict | None":
    """Extrai o primeiro objeto JSON de uma resposta de LLM, tolerante a ruído.

    Lida com: cercas markdown (```json), texto antes/depois do objeto e vírgulas
    finais antes de `}`/`]`. Retorna None se nada parseável for encontrado.
    """
    if not text:
        return None
    s = re.sub(r"```(?:json)?", "", text).strip()
    obj = _try_loads(s)
    if obj is not None:
        return obj
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        block = s[start:end + 1]
        obj = _try_loads(block)
        if obj is not None:
            return obj
        repaired = re.sub(r",(\s*[}\]])", r"\1", block)  # remove vírgula final
        obj = _try_loads(repaired)
        if obj is not None:
            return obj
    return None


# ===========================================================================
# Normalização dos resultados (protege contra deriva do modelo)
# ===========================================================================

def _normalize_quick(data: dict) -> dict:
    sentimento = str(data.get("sentimento", "")).strip().lower()
    if sentimento not in _SENTIMENTS:
        sentimento = "neutro"
    try:
        clickbait = float(data.get("clickbait", 0.0))
    except (TypeError, ValueError):
        clickbait = 0.0
    clickbait = max(0.0, min(1.0, clickbait))
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(t).strip().lower() for t in tags if str(t).strip()][:6] if isinstance(tags, list) else []
    return {
        "tags": tags,
        "sentimento": sentimento,
        "clickbait": clickbait,
        "idioma": str(data.get("idioma", "")).strip()[:10],
        "resumo": str(data.get("resumo", "")).strip(),
    }


def _normalize_full(data: dict) -> dict:
    five_raw = data.get("cinco_ws")
    five_raw = five_raw if isinstance(five_raw, dict) else {}
    five_ws = {k: str(five_raw.get(k, "")).strip() for k in ("quem", "o_que", "quando", "onde", "por_que")}

    entities = []
    ents_raw = data.get("entidades")
    if isinstance(ents_raw, list):
        for e in ents_raw:
            if isinstance(e, dict) and str(e.get("nome", "")).strip():
                entities.append({"nome": str(e["nome"]).strip(), "tipo": str(e.get("tipo", "")).strip().lower()})
            elif isinstance(e, str) and e.strip():
                entities.append({"nome": e.strip(), "tipo": ""})

    bias_raw = data.get("vies") or data.get("viés")
    bias_raw = bias_raw if isinstance(bias_raw, dict) else {}
    marcadores = bias_raw.get("marcadores") or []
    if isinstance(marcadores, str):
        marcadores = [marcadores]
    marcadores = [str(m).strip() for m in marcadores if str(m).strip()] if isinstance(marcadores, list) else []
    bias = {
        "espectro": str(bias_raw.get("espectro", "")).strip().lower() or "indefinido",
        "marcadores": marcadores,
        "qualidade_apuracao": str(bias_raw.get("qualidade_apuracao", "")).strip().lower(),
    }
    return {"cinco_ws": five_ws, "entidades": entities, "vies": bias}


# ===========================================================================
# Prompts e chamadas ao LOGOS
# ===========================================================================

def _build_quick_messages(title: str, body: str) -> list[dict]:
    system = (
        "Você é um analisador de notícias. Leia o artigo e responda APENAS com um "
        "objeto JSON válido — sem texto antes ou depois, sem markdown, sem comentários. "
        "Formato EXATO:\n"
        '{"tags": ["t1","t2"], "sentimento": "positivo|neutro|negativo", '
        '"clickbait": 0.0, "idioma": "pt", "resumo": "uma a duas frases"}\n'
        "Regras: tags = 3 a 6 palavras-chave curtas em minúsculas; sentimento = exatamente "
        "uma das três opções; clickbait = número de 0.0 (título fiel) a 1.0 (sensacionalista); "
        "idioma = código ISO (pt, en, es...); resumo = 1-2 frases no idioma do artigo."
    )
    user = f"Título: {title}\n\nTexto:\n{(body or '').strip()[:_BODY_LIMIT]}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_full_messages(title: str, body: str) -> list[dict]:
    system = (
        "Você é um analisador de notícias. Leia o artigo e responda APENAS com um "
        "objeto JSON válido — sem texto antes ou depois, sem markdown, sem comentários. "
        "Formato EXATO:\n"
        '{"cinco_ws": {"quem":"","o_que":"","quando":"","onde":"","por_que":""}, '
        '"entidades": [{"nome":"","tipo":"pessoa|organizacao|lugar|tema"}], '
        '"vies": {"espectro":"esquerda|centro-esquerda|centro|centro-direita|direita|indefinido", '
        '"marcadores":["..."], "qualidade_apuracao":"alta|media|baixa"}}\n'
        "Regras: cinco_ws = uma frase curta por campo (vazio se não houver); entidades = "
        "pessoas, organizações, lugares e temas centrais citados; vies.espectro = inclinação "
        "política aparente (indefinido se factual/neutro); marcadores = trechos que indicam o "
        "viés; qualidade_apuracao = avaliação do rigor jornalístico."
    )
    user = f"Título: {title}\n\nTexto:\n{(body or '').strip()[:_BODY_LIMIT]}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def analyze_quick(title: str, body: str, *, priority: int) -> "dict | None":
    """Call A: análise rápida. Retorna dict normalizado ou None (JSON inválido após retry).

    Raises:
        LogosUnavailable: LOGOS offline/rejeitou — propaga para o caller decidir.
    """
    messages = _build_quick_messages(title, body)
    for attempt in (1, 2):
        raw = logos_client.chat(messages, priority=priority, max_tokens=400)
        data = _extract_json(raw)
        if data is not None:
            return _normalize_quick(data)
        log.warning("analyze_quick: JSON inválido (tentativa %d/2) — %r", attempt, (title or "")[:60])
    return None


def analyze_full(title: str, body: str, *, priority: int) -> "dict | None":
    """Call B: análise rica. Retorna dict normalizado ou None (JSON inválido após retry).

    Raises:
        LogosUnavailable: LOGOS offline/rejeitou — propaga para o caller decidir.
    """
    messages = _build_full_messages(title, body)
    for attempt in (1, 2):
        raw = logos_client.chat(messages, priority=priority, max_tokens=700)
        data = _extract_json(raw)
        if data is not None:
            return _normalize_full(data)
        log.warning("analyze_full: JSON inválido (tentativa %d/2) — %r", attempt, (title or "")[:60])
    return None


# ===========================================================================
# Helpers de banco (padrão conn=None injetável, como no translation_worker)
# ===========================================================================

def get_pending_analysis(limit: int = _BATCH_SIZE, conn: "sqlite3.Connection | None" = None) -> list[tuple[int, str, str]]:
    """Artigos que precisam de Call A: pending/failed OU versão de schema antiga.

    Newest-first. Body = content_text com fallback para content_excerpt.
    Returns: lista de (article_id, title, body).
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT id, title, content_text, content_excerpt FROM articles
             WHERE (analysis_status IN ('pending','failed')
                    OR (analysis_status = 'done' AND analysis_schema_version < ?))
               AND title IS NOT NULL AND title != ''
             ORDER BY published_at DESC, id DESC
             LIMIT ?
            """,
            (ANALYSIS_SCHEMA_VERSION, limit),
        ).fetchall()
        return [(r["id"], r["title"], (r["content_text"] or r["content_excerpt"] or "")) for r in rows]
    except sqlite3.Error as exc:
        log.error("analysis_worker: falha ao consultar fila de análise: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()


def claim_for_analysis(article_id: int, conn: "sqlite3.Connection | None" = None) -> bool:
    """Reivindica atomicamente um artigo para Call A (status→running). True se reivindicou.

    Só reivindica pending/failed ou versão de schema antiga — evita trabalho duplicado
    entre máquinas (banco sincronizado via Syncthing).
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        cur = _conn.execute(
            """
            UPDATE articles
               SET analysis_status = 'running',
                   analysis_started_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE id = ?
               AND (analysis_status IN ('pending','failed')
                    OR (analysis_status = 'done' AND analysis_schema_version < ?))
            """,
            (article_id, ANALYSIS_SCHEMA_VERSION),
        )
        _conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error as exc:
        log.error("analysis_worker: falha ao reivindicar artigo %d: %s", article_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def save_quick_analysis(article_id: int, data: dict, conn: "sqlite3.Connection | None" = None) -> bool:
    """Persiste Call A e marca analysis_status='done' + versão de schema atual."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            """
            UPDATE articles
               SET ai_tags = ?, ai_sentiment = ?, ai_clickbait_score = ?,
                   ai_summary = ?, ai_language = ?,
                   analysis_status = 'done', analysis_started_at = NULL,
                   analysis_schema_version = ?
             WHERE id = ?
            """,
            (json.dumps(data["tags"], ensure_ascii=False), data["sentimento"],
             data["clickbait"], data["resumo"], data["idioma"],
             ANALYSIS_SCHEMA_VERSION, article_id),
        )
        _conn.commit()
        return True
    except (sqlite3.Error, KeyError) as exc:
        log.error("analysis_worker: falha ao salvar Call A (id=%d): %s", article_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def save_full_analysis(article_id: int, data: dict, conn: "sqlite3.Connection | None" = None) -> bool:
    """Persiste Call B (cinco Ws, entidades, viés) como JSON."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            "UPDATE articles SET ai_five_ws = ?, ai_entities = ?, ai_bias = ? WHERE id = ?",
            (json.dumps(data["cinco_ws"], ensure_ascii=False),
             json.dumps(data["entidades"], ensure_ascii=False),
             json.dumps(data["vies"], ensure_ascii=False), article_id),
        )
        _conn.commit()
        return True
    except (sqlite3.Error, KeyError) as exc:
        log.error("analysis_worker: falha ao salvar Call B (id=%d): %s", article_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def mark_analysis_failed(article_id: int, conn: "sqlite3.Connection | None" = None) -> None:
    """Marca a Call A como falha (JSON inválido após retry). Re-tentável depois."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            "UPDATE articles SET analysis_status = 'failed', analysis_started_at = NULL WHERE id = ?",
            (article_id,),
        )
        _conn.commit()
    except sqlite3.Error as exc:
        log.error("analysis_worker: falha ao marcar artigo %d como failed: %s", article_id, exc)
    finally:
        if should_close:
            _conn.close()


def revert_to_pending(article_id: int, conn: "sqlite3.Connection | None" = None) -> None:
    """Devolve um artigo 'running' para 'pending' (ex.: LOGOS caiu no meio)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            "UPDATE articles SET analysis_status = 'pending', analysis_started_at = NULL "
            "WHERE id = ? AND analysis_status = 'running'",
            (article_id,),
        )
        _conn.commit()
    except sqlite3.Error as exc:
        log.error("analysis_worker: falha ao reverter artigo %d para pending: %s", article_id, exc)
    finally:
        if should_close:
            _conn.close()


def get_article_for_analysis(article_id: int, conn: "sqlite3.Connection | None" = None) -> "dict | None":
    """Estado de análise de um artigo para o caminho P1. None se não existir.

    Retorna title, body e flags has_quick (Call A feita, versão atual) / has_full
    (Call B feita) para o worker decidir o que falta.
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        row = _conn.execute(
            "SELECT title, content_text, content_excerpt, analysis_status, "
            "analysis_schema_version, ai_tags, ai_five_ws FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        log.error("analysis_worker: falha ao ler artigo %d para análise: %s", article_id, exc)
        return None
    finally:
        if should_close:
            _conn.close()
    if row is None:
        return None
    has_quick = (
        row["ai_tags"] is not None
        and row["analysis_status"] == "done"
        and (row["analysis_schema_version"] or 0) >= ANALYSIS_SCHEMA_VERSION
    )
    return {
        "title": row["title"],
        "body": (row["content_text"] or row["content_excerpt"] or ""),
        "has_quick": has_quick,
        "has_full": row["ai_five_ws"] is not None,
    }


def apply_analysis_ttl(conn: "sqlite3.Connection | None" = None) -> int:
    """Zera 5W/entidades de artigos > 6 meses (mantém tags/sentimento). Retorna nº afetado."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        cur = _conn.execute(
            """
            UPDATE articles SET ai_five_ws = NULL, ai_entities = NULL
             WHERE published_at IS NOT NULL
               AND published_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-6 months')
               AND (ai_five_ws IS NOT NULL OR ai_entities IS NOT NULL)
            """
        )
        _conn.commit()
        return cur.rowcount
    except sqlite3.Error as exc:
        log.error("analysis_worker: falha no TTL de análise: %s", exc)
        return 0
    finally:
        if should_close:
            _conn.close()


# ===========================================================================
# Worker
# ===========================================================================

class AnalysisWorker(QThread):
    """QThread: pré-análise P3 contínua + análise completa P1 (preempta) por artigo aberto.

    Sinais:
        quick_analysis_done(int) — (article_id) Call A salva → cards atualizam
        full_analysis_done(int)  — (article_id) Call B salva → leitor atualiza
        analysis_failed(int)     — (article_id) Call A falhou (JSON inválido)
        cycle_done(int)          — nº de calls concluídas no ciclo
    """

    quick_analysis_done = Signal(int)
    full_analysis_done  = Signal(int)
    analysis_failed     = Signal(int)
    cycle_done          = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_flag: bool = False
        self._batch_size: int = _BATCH_SIZE
        self._idle_interval_sec: int = _IDLE_INTERVAL_SEC
        self._cycle_count: int = 0
        # Fila P1: ids de artigos abertos pela usuária (análise completa, preempta o lote P3).
        self._priority_q: "queue.Queue[int]" = queue.Queue()

    def request_full_analysis(self, article_id: int) -> None:
        """Enfileira análise completa P1 de um artigo aberto (preempta a pré-análise)."""
        self._priority_q.put(article_id)
        log.info("Análise completa P1 solicitada: id=%d.", article_id)

    def stop(self) -> None:
        """Solicita parada. Encerra após o item atual ou o próximo tick ocioso."""
        self._stop_flag = True
        log.info("AnalysisWorker: parada solicitada.")

    def run(self) -> None:
        log.info("AnalysisWorker iniciado (batch=%d, idle=%ds, schema=v%d).",
                 self._batch_size, self._idle_interval_sec, ANALYSIS_SCHEMA_VERSION)
        self._stop_flag = False
        n_ttl = apply_analysis_ttl()
        if n_ttl:
            log.info("AnalysisWorker: TTL zerou 5W/entidades de %d artigo(s) > 6 meses.", n_ttl)
        while not self._stop_flag:
            n = self._run_cycle()
            self.cycle_done.emit(n)
            self._idle_sleep()
        log.info("AnalysisWorker encerrado.")

    # -- laço ---------------------------------------------------------------

    def _idle_sleep(self) -> None:
        """Pausa interruptível entre ciclos; acorda em stop ou novo pedido P1."""
        for _ in range(self._idle_interval_sec):
            if self._stop_flag or not self._priority_q.empty():
                break
            self.msleep(1000)

    def _drain_priority(self) -> list[int]:
        items: list[int] = []
        while True:
            try:
                items.append(self._priority_q.get_nowait())
            except queue.Empty:
                break
        return items

    def _run_cycle(self) -> int:
        """P1 (artigos abertos) primeiro; depois o lote P3 de pré-análise."""
        count = 0
        # 1. P1 — análise completa de artigos abertos
        for aid in self._drain_priority():
            if self._stop_flag:
                return count
            count += self._analyze_opened(aid)
        # 2. TTL periódico
        self._cycle_count += 1
        if self._cycle_count % _TTL_EVERY_CYCLES == 0:
            apply_analysis_ttl()
        # 3. P3 — lote de pré-análise (Call A), newest-first, com preempção P1
        for aid, title, body in get_pending_analysis(self._batch_size):
            if self._stop_flag:
                break
            for pid in self._drain_priority():
                if self._stop_flag:
                    return count
                count += self._analyze_opened(pid)
            count += self._preanalyze(aid, title, body)
        return count

    # -- unidades de trabalho ----------------------------------------------

    def _preanalyze(self, article_id: int, title: str, body: str) -> int:
        """Call A (P3) num artigo pendente. Retorna 1 se analisou, 0 caso contrário."""
        if not claim_for_analysis(article_id):
            return 0  # outra máquina/processo já pegou
        try:
            data = analyze_quick(title, body, priority=3)
        except LogosUnavailable:
            revert_to_pending(article_id)
            log.info("AnalysisWorker: LOGOS offline — artigo %d volta a pending; back-off.", article_id)
            self._idle_sleep()
            return 0
        if data is None:
            mark_analysis_failed(article_id)
            self.analysis_failed.emit(article_id)
            return 0
        save_quick_analysis(article_id, data)
        self.quick_analysis_done.emit(article_id)
        return 1

    def _analyze_opened(self, article_id: int) -> int:
        """P1: Call A (se faltar) + Call B num artigo aberto. Retorna nº de calls feitas."""
        info = get_article_for_analysis(article_id)
        if info is None:
            return 0
        title, body = info["title"], info["body"]
        done = 0
        if not info["has_quick"] and claim_for_analysis(article_id):
            try:
                data = analyze_quick(title, body, priority=1)
            except LogosUnavailable:
                revert_to_pending(article_id)
                log.info("AnalysisWorker: LOGOS offline na Call A P1 do artigo %d.", article_id)
                return done
            if data is None:
                mark_analysis_failed(article_id)
                self.analysis_failed.emit(article_id)
            else:
                save_quick_analysis(article_id, data)
                self.quick_analysis_done.emit(article_id)
                done += 1
        if not info["has_full"]:
            try:
                data = analyze_full(title, body, priority=1)
            except LogosUnavailable:
                log.info("AnalysisWorker: LOGOS offline na Call B P1 do artigo %d.", article_id)
                return done
            if data is not None:
                save_full_analysis(article_id, data)
                self.full_analysis_done.emit(article_id)
                done += 1
        return done
