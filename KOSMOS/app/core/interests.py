"""
interests.py — alimenta o perfil de tópicos compartilhado do ecossistema (KOSMOS v3, Fase 5).

Quando um artigo é analisado, os temas que o KOSMOS extraiu (tags da IA + entidades)
sobem no `shared_topic_profile` com source 'kosmos'. As tags de interesse definidas
manualmente pela usuária (config.manual_topics, editáveis em Settings) também reforçam
o perfil, com peso maior por serem declaração explícita de interesse.

O `shared_topic_profile` é o store unificado lido por AKASHA, Mnemosyne e KOSMOS
(`{sync_root}/shared_topic_profile.db`). Atualizações são **best-effort**: falhas não
propagam — alimentar o perfil nunca pode bloquear análise ou arquivamento.
"""
from __future__ import annotations

import json
import logging
import sqlite3

from app.core.database import get_conn
from app.utils import paths as _paths  # noqa: F401  (garante program files no sys.path)

try:
    import shared_topic_profile as _stp
except Exception:  # pragma: no cover - ambiente sem o módulo compartilhado
    _stp = None

log = logging.getLogger("kosmos.interests")

_SOURCE = "kosmos"
_ANALYSIS_DELTA = 0.5   # tema descoberto pela análise da IA
_MANUAL_DELTA   = 1.0   # tag manual = interesse explícito da usuária (peso maior)


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def extract_topics(ai_tags: str | None, ai_entities: str | None) -> list[str]:
    """Extrai os temas de uma análise: tags da IA + nomes de entidades.

    Deduplica preservando a ordem (case-insensitive). Retorna lista vazia se não
    houver análise.
    """
    topics: list[str] = []

    tags = _loads(ai_tags)
    if isinstance(tags, list):
        topics.extend(str(t).strip() for t in tags if str(t).strip())

    ents = _loads(ai_entities)
    if isinstance(ents, list):
        for ent in ents:
            if isinstance(ent, dict):
                nome = str(ent.get("nome") or "").strip()
                if nome:
                    topics.append(nome)
            elif ent:
                topics.append(str(ent).strip())

    seen: set[str] = set()
    out: list[str] = []
    for t in topics:
        key = t.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def update_from_article(article_id: int, conn: sqlite3.Connection | None = None) -> int:
    """Empurra os temas da análise do artigo ao perfil compartilhado (source kosmos).

    Args:
        article_id: ID do artigo.
        conn:       conexão existente (testes); None → cria e fecha própria.

    Returns:
        Número de temas enviados (0 se sem análise ou store indisponível).
    """
    if _stp is None:
        return 0

    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        row = _conn.execute(
            "SELECT ai_tags, ai_entities FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        log.error("interests: falha ao ler análise do artigo %d: %s", article_id, exc)
        return 0
    finally:
        if should_close:
            _conn.close()

    if row is None:
        return 0

    topics = extract_topics(row["ai_tags"], row["ai_entities"])
    if not topics:
        return 0

    try:
        _stp.update_scores(topics, _ANALYSIS_DELTA, _SOURCE)
        log.info(
            "interests: %d tema(s) do artigo %d enviados ao perfil compartilhado.",
            len(topics), article_id,
        )
        return len(topics)
    except Exception as exc:
        log.warning("interests: falha ao atualizar perfil (artigo %d): %s", article_id, exc)
        return 0


def apply_manual_topics(manual_topics: list[str] | None) -> int:
    """Reforça as tags de interesse manuais da usuária no perfil compartilhado.

    Chamado ao salvar Settings e no startup. Peso maior que temas automáticos por
    serem declaração explícita de interesse.

    Returns:
        Número de tags aplicadas (0 se vazio ou store indisponível).
    """
    if _stp is None or not manual_topics:
        return 0

    clean = [str(t).strip() for t in manual_topics if str(t).strip()]
    if not clean:
        return 0

    try:
        _stp.update_scores(clean, _MANUAL_DELTA, _SOURCE)
        log.info("interests: %d tag(s) manual(is) reforçada(s) no perfil.", len(clean))
        return len(clean)
    except Exception as exc:
        log.warning("interests: falha ao aplicar tags manuais: %s", exc)
        return 0
