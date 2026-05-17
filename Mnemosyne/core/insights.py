"""
Mnemosyne — Gerenciamento de insights recebidos do AKASHA.

Fluxo:
  1. AKASHA escreve insight em ecosystem.json > mnemosyne.incoming_insights.
  2. _poll_insights() (chamado via QTimer a cada 60s) lê e move para SQLite local.
  3. Badge "⬡ N" exibido no MainWindow enquanto há insights não vistos.
  4. Ao clicar no badge: abre DialoguePanel com o tópico do insight; marca como visto.
  5. Insights vistos expiram em 7 dias.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("mnemosyne.insights")

_DB_FILENAME    = "insights.db"
_EXPIRE_DAYS    = 7


# ---------------------------------------------------------------------------
# Persistência SQLite
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    from .config import get_app_data_dir
    return get_app_data_dir() / _DB_FILENAME


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS incoming_insights (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            topics      TEXT    NOT NULL DEFAULT '[]',
            summary     TEXT    NOT NULL DEFAULT '',
            sources     TEXT    NOT NULL DEFAULT '[]',
            received_at TEXT    NOT NULL,
            seen        INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def poll_and_store() -> int:
    """
    Lê insights pendentes do ecosystem.json e os move para o SQLite local.
    Retorna a contagem total de insights não vistos após a operação.
    Deve ser chamado a cada 60s via QTimer no MainWindow.
    """
    try:
        from ecosystem_client import read_ecosystem, write_section  # type: ignore
        eco = read_ecosystem()
        incoming: list[dict] = eco.get("mnemosyne", {}).get("incoming_insights", [])
        if incoming:
            with _get_conn() as conn:
                for item in incoming:
                    topics      = json.dumps(item.get("topics", []), ensure_ascii=False)
                    summary     = item.get("summary", "")
                    sources     = json.dumps(item.get("sources", []), ensure_ascii=False)
                    received_at = item.get("received_at", datetime.now(timezone.utc).isoformat())
                    conn.execute(
                        "INSERT INTO incoming_insights (topics, summary, sources, received_at) "
                        "VALUES (?, ?, ?, ?)",
                        (topics, summary, sources, received_at),
                    )
                conn.commit()
            # Limpa incoming_insights do ecosystem.json após mover para SQLite
            write_section("mnemosyne", {"incoming_insights": []})
    except Exception as exc:
        log.debug("insights: poll_and_store falhou: %s", exc)

    return count_unseen()


def count_unseen() -> int:
    """Retorna o número de insights não vistos."""
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM incoming_insights WHERE seen = 0"
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def get_latest_unseen() -> dict | None:
    """Retorna o insight não visto mais recente, ou None se não houver."""
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT id, topics, summary, sources, received_at "
                "FROM incoming_insights WHERE seen = 0 "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {
            "id":          row[0],
            "topics":      json.loads(row[1]),
            "summary":     row[2],
            "sources":     json.loads(row[3]),
            "received_at": row[4],
        }
    except Exception:
        return None


def mark_seen(insight_id: int) -> None:
    """Marca um insight como visto pelo ID."""
    try:
        with _get_conn() as conn:
            conn.execute(
                "UPDATE incoming_insights SET seen = 1 WHERE id = ?", (insight_id,)
            )
            conn.commit()
    except Exception as exc:
        log.debug("insights: mark_seen falhou: %s", exc)


def expire_old() -> None:
    """Remove insights vistos com mais de _EXPIRE_DAYS dias. Chamar uma vez ao dia."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_EXPIRE_DAYS)).isoformat()
    try:
        with _get_conn() as conn:
            conn.execute(
                "DELETE FROM incoming_insights WHERE seen = 1 AND received_at < ?",
                (cutoff,),
            )
            conn.commit()
    except Exception as exc:
        log.debug("insights: expire_old falhou: %s", exc)


def check_reset_command() -> None:
    """
    Verifica se o HUB solicitou reset da memória pessoal via ecosystem.json.
    Se mnemosyne.cmd_reset_memory == True, apaga toda a personal_memory e
    escreve False de volta para confirmar execução.
    Chamado na mesma periodicidade que poll_and_store (60s).
    """
    try:
        from ecosystem_client import read_ecosystem, write_section  # type: ignore
        eco = read_ecosystem()
        if eco.get("mnemosyne", {}).get("cmd_reset_memory", False):
            from .personal_memory import clear_all
            clear_all()
            write_section("mnemosyne", {"cmd_reset_memory": False})
            log.info("insights: memória pessoal apagada via comando do HUB")
    except Exception as exc:
        log.debug("insights: check_reset_command falhou: %s", exc)


def write_pending_count_to_ecosystem(count: int) -> None:
    """
    Escreve pending_insights no ecosystem.json para o HUB exibir o badge.
    Chamado após cada poll ou mark_seen.
    """
    try:
        from ecosystem_client import write_section  # type: ignore
        write_section("mnemosyne", {"pending_insights": count})
    except Exception:
        pass
