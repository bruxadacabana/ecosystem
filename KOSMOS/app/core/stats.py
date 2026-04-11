"""Agregação de estatísticas de leitura para a stats_view."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.database import get_session

log = logging.getLogger("kosmos.stats")


# ------------------------------------------------------------------
# Dataclasses de resultado
# ------------------------------------------------------------------

@dataclass
class TotalStats:
    """Totais gerais para o painel de resumo."""
    total_articles:       int
    total_read:           int
    total_saved:          int
    total_feeds:          int
    total_reading_minutes: float
    avg_daily_minutes:    float   # média dos últimos 30 dias


@dataclass
class DailyStats:
    """Artigos lidos e tempo de leitura num único dia."""
    date:             datetime
    articles_read:    int
    reading_minutes:  float


@dataclass
class FeedStats:
    """Estatísticas de leitura por feed."""
    feed_id:          int
    feed_name:        str
    feed_type:        str
    articles_read:    int
    reading_minutes:  float


@dataclass
class MonthlyStats:
    """Artigos salvos e lidos num único mês."""
    year:            int
    month:           int
    articles_saved:  int
    articles_read:   int


@dataclass
class PlatformStats:
    """Distribuição de leitura por tipo de plataforma."""
    feed_type:        str
    articles_read:    int
    reading_minutes:  float


@dataclass
class SentimentTrend:
    """Sentimento médio dos artigos analisados num único dia."""
    date:           datetime
    avg_sentiment:  float
    article_count:  int


@dataclass
class EntityStats:
    """Entidade nomeada e quantas vezes foi mencionada no período."""
    name:         str
    entity_type:  str   # "people" | "orgs" | "places"
    count:        int


@dataclass
class ArticleCluster:
    """Grupo de artigos semanticamente similares."""
    label:         str
    article_count: int
    sample_titles: list[str]
    article_ids:   list[int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.article_ids is None:
            self.article_ids = []


# ------------------------------------------------------------------
# Funções de agregação
# ------------------------------------------------------------------

def get_total_stats() -> TotalStats:
    """Totais gerais: artigos, lidos, salvos, feeds e tempo de leitura."""
    session = get_session()
    try:
        row = session.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM articles)                               AS total_articles,
                (SELECT COUNT(*) FROM articles WHERE is_read = 1)             AS total_read,
                (SELECT COUNT(*) FROM articles WHERE is_saved = 1)            AS total_saved,
                (SELECT COUNT(*) FROM feeds    WHERE active = 1)              AS total_feeds,
                (SELECT COALESCE(SUM(duration_sec), 0) FROM read_sessions
                    WHERE duration_sec IS NOT NULL)                           AS total_sec,
                (SELECT COALESCE(SUM(duration_sec), 0) FROM read_sessions
                    WHERE duration_sec IS NOT NULL
                      AND started_at >= datetime('now', '-30 days'))          AS last30_sec
        """)).fetchone()

        total_min  = round((row[4] or 0) / 60.0, 1)
        last30_min = (row[5] or 0) / 60.0
        avg_daily  = round(last30_min / 30.0, 1)

        return TotalStats(
            total_articles=row[0] or 0,
            total_read=row[1] or 0,
            total_saved=row[2] or 0,
            total_feeds=row[3] or 0,
            total_reading_minutes=total_min,
            avg_daily_minutes=avg_daily,
        )
    except Exception as exc:
        log.error("Erro ao obter totais: %s", exc)
        return TotalStats(0, 0, 0, 0, 0.0, 0.0)
    finally:
        session.close()


def get_daily_stats(days: int = 30) -> list[DailyStats]:
    """Artigos lidos e tempo de leitura por dia nos últimos N dias.

    Dias sem sessões são incluídos com zeros para facilitar a plotagem.
    """
    since = datetime.utcnow() - timedelta(days=days)
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT
                strftime('%Y-%m-%d', started_at) AS day,
                COUNT(*)                          AS articles_read,
                COALESCE(SUM(duration_sec), 0) / 60.0 AS reading_minutes
            FROM read_sessions
            WHERE started_at >= :since
              AND duration_sec IS NOT NULL
            GROUP BY day
            ORDER BY day
        """), {"since": since}).fetchall()

        by_date = {row[0]: row for row in rows}

        result: list[DailyStats] = []
        for i in range(1, days + 1):
            d = since + timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            if key in by_date:
                r = by_date[key]
                result.append(DailyStats(
                    date=d,
                    articles_read=r[1],
                    reading_minutes=round(r[2], 1),
                ))
            else:
                result.append(DailyStats(date=d, articles_read=0, reading_minutes=0.0))
        return result

    except Exception as exc:
        log.error("Erro ao obter stats diários: %s", exc)
        return []
    finally:
        session.close()


def get_feed_stats(limit: int = 10) -> list[FeedStats]:
    """Top feeds por número de artigos lidos e tempo total."""
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT
                rs.feed_id,
                f.name                                                  AS feed_name,
                f.feed_type,
                COUNT(*)                                                AS articles_read,
                COALESCE(SUM(rs.duration_sec), 0) / 60.0               AS reading_minutes
            FROM read_sessions rs
            JOIN feeds f ON f.id = rs.feed_id
            WHERE rs.duration_sec IS NOT NULL
              AND rs.feed_id IS NOT NULL
            GROUP BY rs.feed_id
            ORDER BY articles_read DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

        return [
            FeedStats(
                feed_id=row[0],
                feed_name=row[1],
                feed_type=row[2],
                articles_read=row[3],
                reading_minutes=round(row[4], 1),
            )
            for row in rows
        ]
    except Exception as exc:
        log.error("Erro ao obter stats por feed: %s", exc)
        return []
    finally:
        session.close()


def get_monthly_stats(months: int = 12) -> list[MonthlyStats]:
    """Artigos salvos e lidos por mês nos últimos N meses."""
    session = get_session()
    try:
        saved_rows = session.execute(text("""
            SELECT
                CAST(strftime('%Y', saved_at) AS INTEGER) AS year,
                CAST(strftime('%m', saved_at) AS INTEGER) AS month,
                COUNT(*)                                  AS count
            FROM articles
            WHERE is_saved = 1
              AND saved_at IS NOT NULL
              AND saved_at >= datetime('now', :offset)
            GROUP BY year, month
        """), {"offset": f"-{months} months"}).fetchall()

        read_rows = session.execute(text("""
            SELECT
                CAST(strftime('%Y', started_at) AS INTEGER) AS year,
                CAST(strftime('%m', started_at) AS INTEGER) AS month,
                COUNT(*)                                    AS count
            FROM read_sessions
            WHERE duration_sec IS NOT NULL
              AND started_at >= datetime('now', :offset)
            GROUP BY year, month
        """), {"offset": f"-{months} months"}).fetchall()

        saved_by: dict[tuple[int, int], int] = {
            (r[0], r[1]): r[2] for r in saved_rows
        }
        read_by: dict[tuple[int, int], int] = {
            (r[0], r[1]): r[2] for r in read_rows
        }

        now = datetime.utcnow()
        result: list[MonthlyStats] = []
        for i in range(months - 1, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            key = (y, m)
            result.append(MonthlyStats(
                year=y,
                month=m,
                articles_saved=saved_by.get(key, 0),
                articles_read=read_by.get(key, 0),
            ))
        return result

    except Exception as exc:
        log.error("Erro ao obter stats mensais: %s", exc)
        return []
    finally:
        session.close()


def get_sentiment_trend(days: int = 30) -> list[SentimentTrend]:
    """Média diária de ai_sentiment nos últimos N dias (só dias com dados)."""
    since = datetime.utcnow() - timedelta(days=days)
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT
                strftime('%Y-%m-%d', published_at)  AS day,
                AVG(ai_sentiment)                   AS avg_sentiment,
                COUNT(*)                            AS article_count
            FROM articles
            WHERE ai_sentiment IS NOT NULL
              AND published_at >= :since
            GROUP BY day
            ORDER BY day
        """), {"since": since}).fetchall()

        return [
            SentimentTrend(
                date=datetime.strptime(row[0], "%Y-%m-%d"),
                avg_sentiment=round(float(row[1]), 3),
                article_count=int(row[2]),
            )
            for row in rows
            if row[0] is not None
        ]
    except Exception as exc:
        log.error("Erro ao obter tendência de sentimento: %s", exc)
        return []
    finally:
        session.close()


def get_platform_stats() -> list[PlatformStats]:
    """Distribuição de leitura por tipo de plataforma (rss, reddit, youtube…)."""
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT
                f.feed_type,
                COUNT(*)                                               AS articles_read,
                COALESCE(SUM(rs.duration_sec), 0) / 60.0              AS reading_minutes
            FROM read_sessions rs
            JOIN feeds f ON f.id = rs.feed_id
            WHERE rs.duration_sec IS NOT NULL
              AND rs.feed_id IS NOT NULL
            GROUP BY f.feed_type
            ORDER BY articles_read DESC
        """)).fetchall()

        return [
            PlatformStats(
                feed_type=row[0],
                articles_read=row[1],
                reading_minutes=round(row[2], 1),
            )
            for row in rows
        ]
    except Exception as exc:
        log.error("Erro ao obter stats por plataforma: %s", exc)
        return []
    finally:
        session.close()


def get_top_entities(days: int = 30, limit: int = 8) -> dict[str, list[EntityStats]]:
    """Top entidades nomeadas mencionadas no período, por tipo (people/orgs/places)."""
    import json as _json
    since = datetime.utcnow() - timedelta(days=days)
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT ai_entities
            FROM articles
            WHERE ai_entities IS NOT NULL
              AND published_at >= :since
        """), {"since": since}).fetchall()

        counts: dict[str, dict[str, int]] = {"people": {}, "orgs": {}, "places": {}}
        for row in rows:
            try:
                data = _json.loads(row[0])
                for etype in ("people", "orgs", "places"):
                    for item in (data.get(etype) or []):
                        name = str(item).strip()
                        if name:
                            counts[etype][name] = counts[etype].get(name, 0) + 1
            except Exception:
                continue

        result: dict[str, list[EntityStats]] = {}
        for etype, c in counts.items():
            top = sorted(c.items(), key=lambda x: x[1], reverse=True)[:limit]
            result[etype] = [EntityStats(name=n, entity_type=etype, count=cnt) for n, cnt in top]
        return result
    except Exception as exc:
        log.error("Erro ao obter entidades: %s", exc)
        return {"people": [], "orgs": [], "places": []}
    finally:
        session.close()


# Stopwords para geração de rótulos de cluster
_CLUSTER_STOPWORDS = {
    "de", "do", "da", "dos", "das", "a", "o", "os", "as", "e", "em", "um", "uma",
    "para", "com", "por", "que", "se", "no", "na", "nos", "nas", "é", "ao", "à",
    "mais", "seu", "sua", "sobre", "entre", "após", "já", "ainda", "também",
    "the", "a", "an", "in", "of", "to", "and", "is", "was", "are", "for", "on",
    "at", "with", "it", "as", "be", "or", "but", "this", "that", "its", "by",
    "from", "has", "have", "had", "not", "will", "been", "says", "new", "after",
    "about", "over", "who", "which", "how", "when", "where", "could", "would",
}


def _cluster_label(titles: list[str], n_words: int = 3) -> str:
    """Extrai rótulo de cluster a partir dos títulos mais frequentes."""
    import re
    word_count: dict[str, int] = {}
    for title in titles:
        for word in re.split(r"[\s\-–—:,;.!?\"'()\[\]]+", title.lower()):
            if len(word) >= 4 and word not in _CLUSTER_STOPWORDS:
                word_count[word] = word_count.get(word, 0) + 1
    top = sorted(word_count.items(), key=lambda x: x[1], reverse=True)[:n_words]
    return "  ·  ".join(w.capitalize() for w, _ in top) if top else "—"


def get_article_clusters(days: int = 90) -> list[ArticleCluster]:
    """K-means nos embeddings dos artigos recentes; retorna grupos com rótulo e títulos."""
    try:
        import struct
        import numpy as np
    except ImportError:
        log.warning("numpy indisponível — clustering desativado")
        return []

    since = datetime.utcnow() - timedelta(days=days)
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT id, title, embedding
            FROM articles
            WHERE embedding IS NOT NULL
              AND published_at >= :since
            ORDER BY published_at DESC
        """), {"since": since}).fetchall()
    except Exception as exc:
        log.error("Erro ao buscar embeddings para clustering: %s", exc)
        return []
    finally:
        session.close()

    if len(rows) < 6:
        return []

    ids:    list[int] = []
    titles: list[str] = []
    vecs:   list[list[float]] = []
    for row in rows:
        try:
            blob = row[2]
            n = len(blob) // 4
            vec = list(struct.unpack(f"<{n}f", blob))
            ids.append(int(row[0]))
            titles.append(row[1] or "")
            vecs.append(vec)
        except Exception:
            continue

    if len(vecs) < 6:
        return []

    X = np.array(vecs, dtype=np.float32)
    # Normalizar para cosine similarity via distância euclidiana
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    X = X / norms

    k = min(7, max(2, len(X) // 15))

    # K-means com reinicializações
    best_labels: np.ndarray | None = None
    best_inertia = float("inf")
    rng = np.random.default_rng(42)

    for _ in range(5):
        idx       = rng.choice(len(X), k, replace=False)
        centroids = X[idx].copy()
        labels    = np.zeros(len(X), dtype=np.int32)

        for _ in range(100):
            # Distâncias: ||x - c||^2 = ||x||^2 - 2·x·c^T + ||c||^2
            X_sq = (X ** 2).sum(axis=1, keepdims=True)      # (n,1)
            C_sq = (centroids ** 2).sum(axis=1)              # (k,)
            dists = X_sq - 2.0 * (X @ centroids.T) + C_sq   # (n,k)
            new_labels = np.argmin(dists, axis=1).astype(np.int32)
            if np.array_equal(new_labels, labels):
                break
            labels = new_labels
            for j in range(k):
                mask = labels == j
                if mask.any():
                    centroids[j] = X[mask].mean(axis=0)

        inertia = float(sum(
            float(np.sum((X[labels == j] - centroids[j]) ** 2))
            for j in range(k) if (labels == j).any()
        ))
        if inertia < best_inertia:
            best_inertia  = inertia
            best_labels   = labels.copy()

    if best_labels is None:
        return []

    clusters: list[ArticleCluster] = []
    for j in range(k):
        mask = best_labels == j
        if not mask.any():
            continue
        indices        = [i for i in range(len(titles)) if mask[i]]
        cluster_titles = [titles[i] for i in indices]
        cluster_ids    = [ids[i]    for i in indices]
        label = _cluster_label(cluster_titles)
        clusters.append(ArticleCluster(
            label         = label,
            article_count = int(mask.sum()),
            sample_titles = cluster_titles[:3],
            article_ids   = cluster_ids,
        ))

    clusters.sort(key=lambda c: c.article_count, reverse=True)
    return clusters
