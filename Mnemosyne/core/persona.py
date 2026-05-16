"""
Mnemosyne — Persona persistente
Constrói e mantém uma auto-representação da Mnemosyne baseada nas reflexões
de conhecimento acumuladas pelo indexador. Reconstruída após cada lote de
Knowledge Reflection. Injetada no system prompt de todas as chamadas LLM
para moldar o tom sem alterar o pipeline RAG.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("mnemosyne.persona")

_PERSONA_DB_FILENAME = "persona.db"
_REBUILD_MIN_TEXTS   = 2      # mínimo de textos de reflexão para reconstruir
_MAX_TEXT_CHARS      = 400    # trunca cada reflexão antes de enviar ao LLM


# ---------------------------------------------------------------------------
# Estrutura
# ---------------------------------------------------------------------------

@dataclass
class AppPersona:
    self_description: str       = ""
    expertise_topics: list[str] = field(default_factory=list)
    formed_at:        str       = ""

    @property
    def is_formed(self) -> bool:
        return bool(self.self_description)

    def as_prompt_prefix(self) -> str:
        """Retorna string para injetar antes do system prompt."""
        if not self.is_formed:
            return ""
        return f"Contexto: {self.self_description}\n"


# ---------------------------------------------------------------------------
# Cache em memória
# ---------------------------------------------------------------------------

_cached_persona: AppPersona = AppPersona()


def get_persona() -> AppPersona:
    """Retorna a persona atual (em memória). Nunca faz IO."""
    return _cached_persona


# ---------------------------------------------------------------------------
# Persistência SQLite síncrona (Mnemosyne é Qt/sync, não asyncio)
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    from .config import get_app_data_dir
    return get_app_data_dir() / _PERSONA_DB_FILENAME


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS persona "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.commit()


def _get_value(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM persona WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def _set_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO persona (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, now),
    )


def load_persona() -> AppPersona:
    """Lê persona do DB e atualiza o cache. Chamado no startup do app."""
    global _cached_persona
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            _init_db(conn)
            desc      = _get_value(conn, "self_description")
            topics_j  = _get_value(conn, "expertise_topics", "[]")
            formed_at = _get_value(conn, "formed_at")
        try:
            topics = json.loads(topics_j)
        except Exception:
            topics = []
        _cached_persona = AppPersona(
            self_description=desc,
            expertise_topics=topics,
            formed_at=formed_at,
        )
    except Exception as exc:
        log.debug("persona: erro ao carregar do DB: %s", exc)
    return _cached_persona


# ---------------------------------------------------------------------------
# Reconstrução via LLM
# ---------------------------------------------------------------------------

def rebuild_persona_from_texts(texts: list[str], model: str) -> None:
    """
    Reconstrói self_description a partir de textos de reflexão recentes.

    Chamado pelo indexador após cada lote de Knowledge Reflection. Os textos
    são as reflexões geradas nesse lote — não fazemos busca no ChromaDB aqui.
    Se houver < _REBUILD_MIN_TEXTS ou LLM falhar, mantém a persona existente.
    """
    if len(texts) < _REBUILD_MIN_TEXTS:
        return

    excerpts = "\n\n".join(t[:_MAX_TEXT_CHARS] for t in texts[:6])

    prompt = (
        "As seguintes sínteses foram geradas automaticamente a partir dos documentos "
        "indexados nesta sessão de pesquisa pessoal:\n\n"
        f"{excerpts}\n\n"
        "Com base nessas sínteses, escreva em 2-3 frases curtas quem você é como "
        "assistente de pesquisa e memória pessoal, em primeira pessoa. "
        "Seja específica sobre as áreas de conhecimento e o tipo de conteúdo que guarda. "
        "Não mencione que é uma IA. Apenas as frases, sem introdução."
    )

    try:
        from ecosystem_client import request_llm as _request_llm  # type: ignore
        resp = _request_llm(
            [{"role": "user", "content": prompt}],
            app="mnemosyne",
            model=model,
            priority=3,
            options={"num_predict": 120, "temperature": 0.4},
        )
        description = resp.get("message", {}).get("content", "").strip()
    except Exception as exc:
        log.debug("persona: LLM falhou: %s", exc)
        return

    if not description:
        return

    now = datetime.now(timezone.utc).isoformat()
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            _init_db(conn)
            _set_value(conn, "self_description", description)
            _set_value(conn, "formed_at", now)
            conn.commit()
    except Exception as exc:
        log.debug("persona: erro ao salvar no DB: %s", exc)
        return

    global _cached_persona
    _cached_persona = AppPersona(
        self_description=description,
        expertise_topics=_cached_persona.expertise_topics,
        formed_at=now,
    )
    log.info("persona: reconstruída a partir de %d reflexões.", len(texts))
