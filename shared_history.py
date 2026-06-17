"""
shared_history — Histórico de uso da AKASHA compartilhado entre máquinas.

Store único em {sync_root}/akasha_history.db (sincronizado via Syncthing), com
backup JSON em {sync_root}/akasha_history.json. Registra buscas, cliques e visitas
(páginas abertas) com timestamp e **máquina de origem** — para a Akasha (assistente)
aprender com o uso em todos os dispositivos.

Espelha o padrão do `shared_topic_profile`:
  - threading.Lock() protege escritas no mesmo processo;
  - SQLite WAL + timeout protege escritas entre processos;
  - backup JSON a cada escrita (limitado às entradas recentes — histórico cresce
    sem limite, então só as últimas N por tabela vão ao backup);
  - auto-recria do backup se o banco corromper.

NÃO substitui o banco local rápido (akasha.db) — é um espelho adicional, best-effort:
qualquer falha aqui é logada e engolida, nunca quebra a ferramenta.
"""
from __future__ import annotations

import json
import logging
import socket
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger("ecosystem.shared_history")

_write_lock = threading.Lock()

# Quantas entradas recentes por tabela vão ao backup JSON (corrupção → restauração).
_BACKUP_LIMIT = 5000

_DDL = """
CREATE TABLE IF NOT EXISTS searches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    query        TEXT    NOT NULL,
    sources      TEXT    NOT NULL DEFAULT '',
    result_count INTEGER NOT NULL DEFAULT 0,
    machine      TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS clicks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    query      TEXT    NOT NULL DEFAULT '',
    url        TEXT    NOT NULL,
    position   INTEGER NOT NULL DEFAULT 0,
    machine    TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS visits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT    NOT NULL,
    title      TEXT    NOT NULL DEFAULT '',
    machine    TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_searches_created ON searches(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clicks_created   ON clicks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visits_created   ON visits(created_at DESC);
"""

_TABLES = ("searches", "clicks", "visits")
# Colunas completas (backup/restore — created_at preservado).
_COLUMNS = {
    "searches": ("query", "sources", "result_count", "machine", "created_at"),
    "clicks":   ("query", "url", "position", "machine", "created_at"),
    "visits":   ("url", "title", "machine", "created_at"),
}
# Colunas de inserção ao vivo — SEM created_at (deixa o DEFAULT datetime('now')).
_INSERT_COLUMNS = {
    "searches": ("query", "sources", "result_count", "machine"),
    "clicks":   ("query", "url", "position", "machine"),
    "visits":   ("url", "title", "machine"),
}


def _machine() -> str:
    try:
        return socket.gethostname() or ""
    except Exception:
        return ""


# ── Caminhos ────────────────────────────────────────────────────────────────

def _db_path() -> Path | None:
    from ecosystem_client import get_sync_root
    root = get_sync_root()
    return (root / "akasha_history.db") if root is not None else None


def _backup_path() -> Path | None:
    from ecosystem_client import get_sync_root
    root = get_sync_root()
    return (root / "akasha_history.json") if root is not None else None


# ── Conexão e schema ─────────────────────────────────────────────────────────

def _conn(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=10.0, check_same_thread=False)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        con.close()
        raise
    return con


def _recreate_from_backup(path: Path) -> None:
    """Apaga banco corrompido (+ WAL/SHM) e recria do backup JSON, se houver."""
    for suffix in ("-wal", "-shm"):
        try:
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass

    with _conn(path) as con:
        con.executescript(_DDL)

    bk = _backup_path()
    if bk is None or not bk.exists():
        log.warning("shared_history: banco recriado vazio — backup JSON não encontrado")
        return
    try:
        data = json.loads(bk.read_text(encoding="utf-8"))
        with _conn(path) as con:
            for table in _TABLES:
                cols = _COLUMNS[table]
                ph = ",".join("?" * len(cols))
                collist = ",".join(cols)
                for row in data.get(table, []):
                    con.execute(
                        f"INSERT INTO {table} ({collist}) VALUES ({ph})",
                        tuple(row.get(c) for c in cols),
                    )
        log.info("shared_history: banco restaurado do backup JSON")
    except Exception as exc:
        log.warning("shared_history: restauração do backup falhou: %s", exc)


def _ensure_db(path: Path) -> None:
    try:
        with _conn(path) as con:
            con.executescript(_DDL)
    except sqlite3.DatabaseError as exc:
        msg = str(exc).lower()
        if "malformed" in msg or "corrupt" in msg or "not a database" in msg:
            log.warning("shared_history: banco corrompido (%s) — recriando do backup", exc)
            _recreate_from_backup(path)
        else:
            raise


# ── Backup JSON (limitado às entradas recentes) ──────────────────────────────

def _write_backup(db_path: Path, backup_path: Path) -> None:
    try:
        con = sqlite3.connect(str(db_path), timeout=5.0)
        data: dict[str, list] = {}
        for table in _TABLES:
            cols = _COLUMNS[table]
            collist = ",".join(cols)
            rows = con.execute(
                f"SELECT {collist} FROM {table} ORDER BY created_at DESC LIMIT ?",
                (_BACKUP_LIMIT,),
            ).fetchall()
            data[table] = [dict(zip(cols, r)) for r in rows]
        con.close()
        tmp = backup_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(backup_path)
    except Exception as exc:
        log.debug("shared_history: backup falhou — %s", exc)


def _insert(table: str, values: dict) -> None:
    """Insere uma linha em `table` (best-effort) + atualiza o backup JSON."""
    path = _db_path()
    if path is None:
        return
    cols = _INSERT_COLUMNS[table]
    with _write_lock:
        try:
            _ensure_db(path)
            collist = ",".join(cols)
            ph = ",".join("?" * len(cols))
            with _conn(path) as con:
                con.execute(
                    f"INSERT INTO {table} ({collist}) VALUES ({ph})",
                    tuple(values.get(c) for c in cols),
                )
            bk = _backup_path()
            if bk is not None:
                _write_backup(path, bk)
        except Exception as exc:
            log.warning("shared_history: insert em %s falhou: %s", table, exc)


# ── Escrita (API pública) ────────────────────────────────────────────────────

def record_search(query: str, sources: str = "", result_count: int = 0) -> None:
    q = (query or "").strip()
    if not q:
        return
    _insert("searches", {
        "query": q, "sources": sources or "", "result_count": int(result_count or 0),
        "machine": _machine(),
    })


def record_click(url: str, query: str = "", position: int = 0) -> None:
    u = (url or "").strip()
    if not u:
        return
    _insert("clicks", {
        "query": (query or "").strip(), "url": u, "position": int(position or 0),
        "machine": _machine(),
    })


def record_visit(url: str, title: str = "") -> None:
    u = (url or "").strip()
    if not u:
        return
    _insert("visits", {
        "url": u, "title": (title or "").strip(),
        "machine": _machine(),
    })


# ── Leitura (para as análises da Akasha) ─────────────────────────────────────

def _query(sql: str, params: tuple = ()) -> list[tuple]:
    path = _db_path()
    if path is None or not path.exists():
        return []
    try:
        con = sqlite3.connect(str(path), timeout=5.0)
        rows = con.execute(sql, params).fetchall()
        con.close()
        return rows
    except Exception as exc:
        log.debug("shared_history: query falhou: %s", exc)
        return []


def recent_searches(limit: int = 20) -> list[dict]:
    rows = _query(
        "SELECT query, sources, result_count, machine, created_at "
        "FROM searches ORDER BY created_at DESC LIMIT ?", (limit,),
    )
    keys = ("query", "sources", "result_count", "machine", "created_at")
    return [dict(zip(keys, r)) for r in rows]


def recent_visits(limit: int = 20) -> list[dict]:
    rows = _query(
        "SELECT url, title, machine, created_at "
        "FROM visits ORDER BY created_at DESC LIMIT ?", (limit,),
    )
    keys = ("url", "title", "machine", "created_at")
    return [dict(zip(keys, r)) for r in rows]


def recent_clicks(limit: int = 20) -> list[dict]:
    rows = _query(
        "SELECT query, url, position, machine, created_at "
        "FROM clicks ORDER BY created_at DESC LIMIT ?", (limit,),
    )
    keys = ("query", "url", "position", "machine", "created_at")
    return [dict(zip(keys, r)) for r in rows]


def top_domains(limit: int = 8, days: int = 30) -> list[tuple[str, int]]:
    """Domínios mais visitados nos últimos `days` dias (host extraído da URL)."""
    rows = _query(
        f"SELECT url FROM visits WHERE created_at >= datetime('now', '-{int(days)} days')"
    )
    from urllib.parse import urlparse
    counts: dict[str, int] = {}
    for (url,) in rows:
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            host = ""
        if host:
            counts[host] = counts.get(host, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]


def counts() -> dict[str, int]:
    """Contagem total por tabela (diagnóstico/testes)."""
    out: dict[str, int] = {}
    for table in _TABLES:
        rows = _query(f"SELECT COUNT(*) FROM {table}")
        out[table] = rows[0][0] if rows else 0
    return out
