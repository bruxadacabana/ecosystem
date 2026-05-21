"""
shared_topic_profile — Perfil de interesse unificado do ecossistema.

Store compartilhado em {sync_root}/shared_topic_profile.db.
Lido e escrito por AKASHA, Mnemosyne e KOSMOS.
JSON backup em {sync_root}/shared_topic_profile.json gerado a cada escrita.

Segurança de concorrência:
  - threading.Lock() protege escritas dentro de um mesmo processo.
  - SQLite WAL mode + timeout=10s protege escritas entre processos distintos.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger("ecosystem.shared_topic_profile")

_write_lock = threading.Lock()

_DDL = """
CREATE TABLE IF NOT EXISTS topic_interest_profile (
    topic            TEXT    PRIMARY KEY,
    score            REAL    NOT NULL DEFAULT 0.0,
    akasha_count     INTEGER NOT NULL DEFAULT 0,
    mnemosyne_count  INTEGER NOT NULL DEFAULT 0,
    kosmos_count     INTEGER NOT NULL DEFAULT 0,
    last_updated     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tip_score ON topic_interest_profile(score DESC);
"""

_VALID_SOURCES = frozenset({"akasha", "mnemosyne", "kosmos"})


# ── Caminhos ────────────────────────────────────────────────────────────────

def _profile_path() -> Path | None:
    from ecosystem_client import get_sync_root
    root = get_sync_root()
    return (root / "shared_topic_profile.db") if root is not None else None


def _backup_path() -> Path | None:
    from ecosystem_client import get_sync_root
    root = get_sync_root()
    return (root / "shared_topic_profile.json") if root is not None else None


# ── Conexão e schema ─────────────────────────────────────────────────────────

def _conn(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=10.0, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _ensure_db(path: Path) -> None:
    with _conn(path) as con:
        con.executescript(_DDL)


# ── Backup JSON ──────────────────────────────────────────────────────────────

def _write_backup(db_path: Path, backup_path: Path) -> None:
    try:
        con = sqlite3.connect(str(db_path), timeout=5.0)
        rows = con.execute(
            "SELECT topic, score, akasha_count, mnemosyne_count, kosmos_count, last_updated "
            "FROM topic_interest_profile ORDER BY score DESC"
        ).fetchall()
        con.close()
        data = [
            {
                "topic": r[0],
                "score": round(r[1], 4),
                "akasha_count": r[2],
                "mnemosyne_count": r[3],
                "kosmos_count": r[4],
                "last_updated": r[5],
            }
            for r in rows
        ]
        tmp = backup_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(backup_path)
    except Exception as exc:
        log.debug("shared_topic_profile: backup falhou — %s", exc)


# ── Escrita ──────────────────────────────────────────────────────────────────

def update_score(topic: str, delta: float, source: str) -> None:
    """Incrementa score de um tópico.

    Args:
        topic:  String do tópico (normalizada para lowercase internamente).
        delta:  Incremento de score (ex: +0.3 leitura, +0.5 query, +1.0 feedback).
        source: App de origem — 'akasha' | 'mnemosyne' | 'kosmos'.
    """
    update_scores([topic], delta, source)


def update_scores(topics: list[str], delta: float, source: str) -> None:
    """Incrementa score de múltiplos tópicos em uma transação."""
    path = _profile_path()
    if path is None or not topics:
        return

    normalized = [t.strip().lower() for t in topics if t and t.strip()]
    if not normalized:
        return

    count_col = f"{source}_count" if source in _VALID_SOURCES else "akasha_count"

    with _write_lock:
        try:
            _ensure_db(path)
            with _conn(path) as con:
                for topic in normalized:
                    con.execute(
                        f"""INSERT INTO topic_interest_profile
                               (topic, score, {count_col}, last_updated)
                           VALUES (?, ?, 1, datetime('now'))
                           ON CONFLICT(topic) DO UPDATE SET
                               score        = score + excluded.score,
                               {count_col}  = {count_col} + 1,
                               last_updated = datetime('now')""",
                        (topic, delta),
                    )
            bk = _backup_path()
            if bk is not None:
                _write_backup(path, bk)
        except Exception as exc:
            log.warning("shared_topic_profile.update_scores falhou: %s", exc)


def apply_seed_topics(topics: list[dict]) -> int:
    """Inicializa tópicos do interests.json sem sobrescrever scores acumulados.

    Só insere tópicos ausentes — nunca decrementa nem sobrescreve score existente.
    Retorna número de tópicos inseridos.
    """
    path = _profile_path()
    if path is None or not topics:
        return 0

    count = 0
    with _write_lock:
        try:
            _ensure_db(path)
            with _conn(path) as con:
                for t in topics:
                    name = str(t.get("name", "")).strip().lower()
                    weight = float(t.get("weight", 1.0))
                    if not name:
                        continue
                    con.execute(
                        """INSERT INTO topic_interest_profile (topic, score, last_updated)
                           VALUES (?, ?, datetime('now'))
                           ON CONFLICT(topic) DO NOTHING""",
                        (name, weight),
                    )
                    if con.execute("SELECT changes()").fetchone()[0]:
                        count += 1
            bk = _backup_path()
            if bk is not None:
                _write_backup(path, bk)
        except Exception as exc:
            log.warning("shared_topic_profile.apply_seed_topics falhou: %s", exc)
    return count


# ── Leitura ──────────────────────────────────────────────────────────────────

def get_top_topics(n: int = 30) -> list[tuple[str, float]]:
    """Retorna top N tópicos por score. Lista vazia se store não existir."""
    path = _profile_path()
    if path is None or not path.exists():
        return []
    try:
        con = sqlite3.connect(str(path), timeout=5.0)
        rows = con.execute(
            "SELECT topic, score FROM topic_interest_profile ORDER BY score DESC LIMIT ?",
            (n,),
        ).fetchall()
        con.close()
        return [(r[0], r[1]) for r in rows]
    except Exception as exc:
        log.debug("shared_topic_profile.get_top_topics falhou: %s", exc)
        return []


def get_scores(topics: list[str]) -> dict[str, float]:
    """Retorna scores para uma lista de tópicos. Tópicos ausentes retornam 0.0."""
    if not topics:
        return {}
    normalized = [t.strip().lower() for t in topics if t and t.strip()]
    if not normalized:
        return {}

    path = _profile_path()
    if path is None or not path.exists():
        return {t: 0.0 for t in normalized}

    try:
        placeholders = ",".join("?" * len(normalized))
        con = sqlite3.connect(str(path), timeout=5.0)
        rows = con.execute(
            f"SELECT topic, score FROM topic_interest_profile WHERE topic IN ({placeholders})",
            normalized,
        ).fetchall()
        con.close()
        result = {t: 0.0 for t in normalized}
        for topic, score in rows:
            result[topic] = score
        return result
    except Exception as exc:
        log.debug("shared_topic_profile.get_scores falhou: %s", exc)
        return {t: 0.0 for t in normalized}


def get_all_scores() -> dict[str, float]:
    """Retorna todos os tópicos e seus scores. Usado para visualização de grafo."""
    path = _profile_path()
    if path is None or not path.exists():
        return {}
    try:
        con = sqlite3.connect(str(path), timeout=5.0)
        rows = con.execute(
            "SELECT topic, score FROM topic_interest_profile"
        ).fetchall()
        con.close()
        return {r[0]: r[1] for r in rows}
    except Exception as exc:
        log.debug("shared_topic_profile.get_all_scores falhou: %s", exc)
        return {}


def search_topics(prefix: str, n: int = 20) -> list[str]:
    """Retorna tópicos cujo nome começa com `prefix`, ordenados por score. Usado no autocomplete."""
    path = _profile_path()
    if path is None or not path.exists():
        return []
    pat = prefix.strip().lower() + "%"
    try:
        con = sqlite3.connect(str(path), timeout=5.0)
        rows = con.execute(
            "SELECT topic FROM topic_interest_profile "
            "WHERE LOWER(topic) LIKE ? ORDER BY score DESC LIMIT ?",
            (pat, n),
        ).fetchall()
        con.close()
        return [r[0] for r in rows]
    except Exception as exc:
        log.debug("shared_topic_profile.search_topics falhou: %s", exc)
        return []


def decay_scores(factor: float = 0.97, days_inactive: int = 7) -> int:
    """Aplica decaimento EMA em tópicos sem atualização há mais de `days_inactive` dias.

    Remove tópicos com score abaixo de 0.01. Retorna número de tópicos afetados.
    """
    path = _profile_path()
    if path is None or not path.exists():
        return 0
    with _write_lock:
        try:
            with _conn(path) as con:
                cur = con.execute(
                    f"""UPDATE topic_interest_profile
                        SET score = score * ?
                        WHERE last_updated < datetime('now', '-{days_inactive} days')""",
                    (factor,),
                )
                affected = cur.rowcount
                con.execute("DELETE FROM topic_interest_profile WHERE score < 0.01")
            bk = _backup_path()
            if bk is not None:
                _write_backup(path, bk)
            return affected
        except Exception as exc:
            log.warning("shared_topic_profile.decay_scores falhou: %s", exc)
            return 0


def has_overlap(topics: list[str], min_topics: int = 2, min_score: float = 1.0) -> bool:
    """Retorna True se ao menos `min_topics` tópicos tiverem score >= `min_score`.

    Usado para decidir se um insight vale ser compartilhado entre IAs.
    Threshold padrão: ≥ 2 tópicos com score > 1.0.
    """
    if not topics:
        return False
    scores = get_scores(topics)
    return sum(1 for s in scores.values() if s >= min_score) >= min_topics
