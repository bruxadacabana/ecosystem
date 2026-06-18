"""
stats.py — métricas do dashboard de estudo (Fase 8).

Funções puras de consulta (sem Qt) que alimentam o `stats_view.py`: artigos lidos
por dia, feeds mais consumidos, sentimento ao longo do tempo, viés político médio
(indicador de bolha editorial) e cobertura por entidade rastreada.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

from app.core.database import get_conn
from app.core.entities import list_entities

log = logging.getLogger("kosmos.stats")

SENTIMENTS = ("positivo", "neutro", "negativo")

# espectro político → escore numérico (esquerda −2 … direita +2) para a média.
_BIAS_SCORE = {
    "esquerda": -2.0, "centro-esquerda": -1.0, "centro": 0.0,
    "centro-direita": 1.0, "direita": 2.0,
}
_SCORE_LABEL = [
    (-1.5, "esquerda"), (-0.5, "centro-esquerda"), (0.5, "centro"),
    (1.5, "centro-direita"), (99, "direita"),
]


def _today() -> "datetime.date":
    return datetime.now(timezone.utc).date()


def articles_read_per_day(days: int = 14, conn: sqlite3.Connection | None = None) -> list[tuple[str, int]]:
    """(data ISO, nº lidos) para os últimos `days` dias, preenchendo dias sem leitura com 0."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            "SELECT date(read_at) AS d, COUNT(*) AS n FROM articles "
            "WHERE is_read = 1 AND read_at IS NOT NULL GROUP BY d"
        ).fetchall()
        counts = {r["d"]: r["n"] for r in rows}
    except sqlite3.Error as exc:
        log.error("stats: falha em articles_read_per_day: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()
    base = _today()
    return [((base - timedelta(days=i)).isoformat(), counts.get((base - timedelta(days=i)).isoformat(), 0))
            for i in range(days - 1, -1, -1)]


def top_feeds(limit: int = 8, conn: sqlite3.Connection | None = None) -> list[tuple[str, int]]:
    """Feeds mais consumidos (por artigos lidos), maior primeiro."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            "SELECT COALESCE(f.title, f.url) AS feed, COUNT(*) AS n "
            "FROM articles a JOIN feeds f ON f.id = a.feed_id "
            "WHERE a.is_read = 1 GROUP BY f.id ORDER BY n DESC, feed COLLATE NOCASE LIMIT ?",
            (limit,),
        ).fetchall()
        return [(r["feed"], r["n"]) for r in rows]
    except sqlite3.Error as exc:
        log.error("stats: falha em top_feeds: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()


def top_tags(limit: int = 8, conn: sqlite3.Connection | None = None) -> list[tuple[str, int]]:
    """Tags de AI mais frequentes (parse do JSON `ai_tags`), maior primeiro."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            "SELECT ai_tags FROM articles WHERE ai_tags IS NOT NULL AND ai_tags != ''"
        ).fetchall()
    except sqlite3.Error as exc:
        log.error("stats: falha em top_tags: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()
    counter: Counter = Counter()
    for r in rows:
        try:
            tags = json.loads(r["ai_tags"])
        except (ValueError, TypeError):
            continue
        if isinstance(tags, list):
            for t in tags:
                t = str(t).strip()
                if t:
                    counter[t] += 1
    return counter.most_common(limit)


def totals(conn: sqlite3.Connection | None = None) -> dict:
    """Contagens gerais para o resumo do dashboard: artigos, lidos, não-lidos, feeds."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        total = _conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        read = _conn.execute("SELECT COUNT(*) FROM articles WHERE is_read = 1").fetchone()[0]
        feeds = _conn.execute("SELECT COUNT(*) FROM feeds").fetchone()[0]
    except sqlite3.Error as exc:
        log.error("stats: falha em totals: %s", exc)
        return {"total": 0, "read": 0, "unread": 0, "feeds": 0}
    finally:
        if should_close:
            _conn.close()
    return {"total": total, "read": read, "unread": total - read, "feeds": feeds}


def sentiment_over_time(days: int = 14, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Por dia (últimos `days`), contagem de cada sentimento (artigos analisados, por data de publicação)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            "SELECT date(published_at) AS d, ai_sentiment AS s, COUNT(*) AS n FROM articles "
            "WHERE ai_sentiment IS NOT NULL AND published_at IS NOT NULL GROUP BY d, s"
        ).fetchall()
    except sqlite3.Error as exc:
        log.error("stats: falha em sentiment_over_time: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()
    per_day: dict[str, dict] = {}
    for r in rows:
        per_day.setdefault(r["d"], {})[r["s"]] = r["n"]
    base = _today()
    out = []
    for i in range(days - 1, -1, -1):
        d = (base - timedelta(days=i)).isoformat()
        day = per_day.get(d, {})
        out.append({"date": d, **{s: day.get(s, 0) for s in SENTIMENTS}})
    return out


def sentiment_distribution(conn: sqlite3.Connection | None = None) -> dict:
    """Distribuição total de sentimento entre os artigos analisados."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            "SELECT ai_sentiment AS s, COUNT(*) AS n FROM articles "
            "WHERE ai_sentiment IS NOT NULL GROUP BY s"
        ).fetchall()
        return {s: 0 for s in SENTIMENTS} | {r["s"]: r["n"] for r in rows if r["s"] in SENTIMENTS}
    except sqlite3.Error as exc:
        log.error("stats: falha em sentiment_distribution: %s", exc)
        return {s: 0 for s in SENTIMENTS}
    finally:
        if should_close:
            _conn.close()


def bias_balance(conn: sqlite3.Connection | None = None) -> dict:
    """Indicador de bolha editorial: distribuição por espectro + média e rótulo.

    Retorna {"distribution": {espectro: n}, "mean": float|None, "label": str, "n": int}.
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            "SELECT ai_bias FROM articles WHERE ai_bias IS NOT NULL AND ai_bias != ''"
        ).fetchall()
    except sqlite3.Error as exc:
        log.error("stats: falha em bias_balance: %s", exc)
        return {"distribution": {}, "mean": None, "label": "—", "n": 0}
    finally:
        if should_close:
            _conn.close()

    dist: dict[str, int] = {}
    scores: list[float] = []
    for r in rows:
        try:
            esp = str((json.loads(r["ai_bias"]) or {}).get("espectro", "")).strip().lower()
        except (ValueError, TypeError):
            continue
        if not esp:
            continue
        dist[esp] = dist.get(esp, 0) + 1
        if esp in _BIAS_SCORE:
            scores.append(_BIAS_SCORE[esp])
    if not scores:
        return {"distribution": dist, "mean": None, "label": "indefinido", "n": sum(dist.values())}
    mean = sum(scores) / len(scores)
    label = next(lbl for thr, lbl in _SCORE_LABEL if mean <= thr)
    return {"distribution": dist, "mean": mean, "label": label, "n": sum(dist.values())}


def coverage_by_entity(limit: int = 10, conn: sqlite3.Connection | None = None) -> list[tuple[str, int]]:
    """Entidades rastreadas mais cobertas (nome, nº de artigos)."""
    out = [(e["name"], e["article_count"]) for e in list_entities(conn) if e["article_count"] > 0]
    return out[:limit]
