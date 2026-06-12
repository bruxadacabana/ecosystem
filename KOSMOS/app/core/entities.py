"""
entities.py — ponte e consultas do rastreador de entidades (Fase 7).

A análise rica (Call B) salva as entidades como JSON em `articles.ai_entities`. Para o
rastreador cruzar artigos por entidade — e para o vínculo **sobreviver ao TTL de 6
meses** que zera `ai_entities` — materializamos esse JSON nas tabelas relacionais
`entities` (canônica, com notas da usuária) e `article_entities` (vínculo).

`materialize_entity_links` é chamada pelo AnalysisWorker logo após `save_full_analysis`
(incremental); `backfill_entity_links` preenche os artigos já analisados de uma vez.
As demais funções servem o `entity_view.py`: lista de entidades, linha do tempo de
cobertura, sentimento acumulado, quais feeds cobriram mais, e notas por entidade.
"""
from __future__ import annotations

import json
import logging
import sqlite3

from app.core.database import get_conn

log = logging.getLogger("kosmos.entities")

# tipo livre da análise (pt) → tipo canônico do schema (person|org|place|topic)
_TYPE_MAP = {
    "pessoa": "person", "person": "person", "people": "person",
    "organizacao": "org", "organização": "org", "org": "org", "organization": "org", "empresa": "org",
    "lugar": "place", "local": "place", "place": "place", "pais": "place", "país": "place", "cidade": "place",
    "tema": "topic", "topico": "topic", "tópico": "topic", "topic": "topic", "assunto": "topic",
}


def _canonical_type(tipo: object) -> str:
    return _TYPE_MAP.get(str(tipo or "").strip().lower(), "topic")


def parse_entities(ai_entities: str | None) -> list[dict]:
    """Decodifica o JSON de `ai_entities` numa lista de {nome, tipo}. [] em falha."""
    if not ai_entities:
        return []
    try:
        data = json.loads(ai_entities)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for e in data:
        if isinstance(e, dict) and str(e.get("nome", "")).strip():
            out.append({"nome": str(e["nome"]).strip(), "tipo": str(e.get("tipo", "")).strip()})
    return out


def materialize_entity_links(
    article_id: int, entities: list[dict], conn: sqlite3.Connection | None = None
) -> int:
    """Grava entidades de um artigo nas tabelas relacionais (upsert + religa).

    Substitui os vínculos anteriores do artigo (re-análise muda entidades) e faz
    upsert das entidades por (name, entity_type). Retorna o nº de vínculos criados.
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute("DELETE FROM article_entities WHERE article_id = ?", (article_id,))
        n = 0
        for e in entities or []:
            nome = str(e.get("nome", "")).strip()
            if not nome:
                continue
            etype = _canonical_type(e.get("tipo"))
            _conn.execute(
                "INSERT OR IGNORE INTO entities (name, entity_type) VALUES (?, ?)", (nome, etype)
            )
            row = _conn.execute(
                "SELECT id FROM entities WHERE name = ? AND entity_type = ?", (nome, etype)
            ).fetchone()
            if row is None:
                continue
            _conn.execute(
                "INSERT OR IGNORE INTO article_entities (article_id, entity_id) VALUES (?, ?)",
                (article_id, row["id"]),
            )
            n += 1
        _conn.commit()
        return n
    except sqlite3.Error as exc:
        log.error("entities: falha ao materializar vínculos do artigo %d: %s", article_id, exc)
        return 0
    finally:
        if should_close:
            _conn.close()


def backfill_entity_links(conn: sqlite3.Connection | None = None) -> int:
    """Materializa as entidades de todos os artigos que têm `ai_entities`. Retorna nº de artigos."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            "SELECT id, ai_entities FROM articles WHERE ai_entities IS NOT NULL AND ai_entities != ''"
        ).fetchall()
        n = 0
        for r in rows:
            ents = parse_entities(r["ai_entities"])
            if ents:
                materialize_entity_links(r["id"], ents, conn=_conn)
                n += 1
        log.info("entities: backfill materializou entidades de %d artigo(s).", n)
        return n
    except sqlite3.Error as exc:
        log.error("entities: falha no backfill de entidades: %s", exc)
        return 0
    finally:
        if should_close:
            _conn.close()


def list_entities(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Entidades com contagem de artigos, mais cobertas primeiro."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT e.id, e.name, e.entity_type, e.notes, COUNT(ae.article_id) AS article_count
              FROM entities e
              LEFT JOIN article_entities ae ON ae.entity_id = e.id
             GROUP BY e.id
             ORDER BY article_count DESC, e.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("entities: falha ao listar entidades: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()


def get_entity_timeline(entity_id: int, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Artigos que mencionam a entidade, do mais novo ao mais antigo (linha do tempo)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT a.id, a.title, a.published_at, a.ai_sentiment,
                   COALESCE(f.title, f.url) AS feed
              FROM article_entities ae
              JOIN articles a ON a.id = ae.article_id
              JOIN feeds f    ON f.id = a.feed_id
             WHERE ae.entity_id = ?
             ORDER BY a.published_at DESC, a.id DESC
            """,
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("entities: falha na linha do tempo da entidade %d: %s", entity_id, exc)
        return []
    finally:
        if should_close:
            _conn.close()


def get_entity_sentiment_breakdown(entity_id: int, conn: sqlite3.Connection | None = None) -> dict:
    """Sentimento acumulado: contagem por classe (positivo/neutro/negativo)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT a.ai_sentiment AS s, COUNT(*) AS n
              FROM article_entities ae
              JOIN articles a ON a.id = ae.article_id
             WHERE ae.entity_id = ? AND a.ai_sentiment IS NOT NULL
             GROUP BY a.ai_sentiment
            """,
            (entity_id,),
        ).fetchall()
        return {r["s"]: r["n"] for r in rows}
    except sqlite3.Error as exc:
        log.error("entities: falha no sentimento da entidade %d: %s", entity_id, exc)
        return {}
    finally:
        if should_close:
            _conn.close()


def get_entity_feed_breakdown(entity_id: int, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Quais feeds cobriram mais a entidade (feed → contagem, desc)."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT COALESCE(f.title, f.url) AS feed, COUNT(*) AS n
              FROM article_entities ae
              JOIN articles a ON a.id = ae.article_id
              JOIN feeds f    ON f.id = a.feed_id
             WHERE ae.entity_id = ?
             GROUP BY f.id
             ORDER BY n DESC, feed COLLATE NOCASE
            """,
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("entities: falha nos feeds da entidade %d: %s", entity_id, exc)
        return []
    finally:
        if should_close:
            _conn.close()


def get_entity_coverage(
    entity_id: int, days: int = 14, conn: sqlite3.Connection | None = None
) -> dict:
    """Mapa de cobertura feed×dia de uma entidade (para o mapa de cobertura).

    Args:
        entity_id: entidade alvo.
        days:      tamanho da janela em dias (1–60), terminando hoje.
        conn:      conexão existente (testes); None → cria e fecha própria.

    Returns:
        dict com:
          - "days":   lista de datas "YYYY-MM-DD" do mais antigo ao mais recente (len=days);
          - "feeds":  [{"id", "title"}] dos feeds **ativos** no período (≥1 artigo de qualquer
                      assunto), ordenados por título — feeds ativos sem nenhuma menção aparecem
                      com a linha toda zerada, tornando o silêncio editorial evidente;
          - "counts": {(feed_id, "YYYY-MM-DD"): n} com as menções da entidade por feed/dia.
    """
    from datetime import date, timedelta

    days = max(1, min(60, int(days)))
    today = date.today()
    day_list = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    cutoff = day_list[0]

    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        feed_rows = _conn.execute(
            """
            SELECT DISTINCT a.feed_id AS id, COALESCE(f.title, f.url) AS title
              FROM articles a
              JOIN feeds f ON f.id = a.feed_id
             WHERE substr(a.published_at, 1, 10) >= ?
             ORDER BY title COLLATE NOCASE
            """,
            (cutoff,),
        ).fetchall()
        count_rows = _conn.execute(
            """
            SELECT a.feed_id AS fid, substr(a.published_at, 1, 10) AS day, COUNT(*) AS n
              FROM article_entities ae
              JOIN articles a ON a.id = ae.article_id
             WHERE ae.entity_id = ?
               AND substr(a.published_at, 1, 10) >= ?
             GROUP BY a.feed_id, day
            """,
            (entity_id, cutoff),
        ).fetchall()
    except sqlite3.Error as exc:
        log.error("entities: falha no mapa de cobertura da entidade %d: %s", entity_id, exc)
        return {"days": day_list, "feeds": [], "counts": {}}
    finally:
        if should_close:
            _conn.close()

    feeds = [{"id": r["id"], "title": r["title"]} for r in feed_rows]
    counts = {(r["fid"], r["day"]): r["n"] for r in count_rows}
    return {"days": day_list, "feeds": feeds, "counts": counts}


_SPECTRUM_ORDER = (
    "esquerda", "centro-esquerda", "centro", "centro-direita", "direita", "indefinido",
)


def get_entity_framing(entity_id: int, conn: sqlite3.Connection | None = None) -> dict:
    """Comparação de enquadramento de uma entidade por espectro político.

    Agrupa os artigos que mencionam a entidade pelo `ai_bias.espectro` (esquerda →
    direita; sem análise → 'indefinido') e, por espectro, calcula: contagem,
    distribuição de sentimento, entidades co-citadas (top) e manchetes de amostra.
    Permite ver lado a lado como fontes de inclinações diferentes enquadram o
    mesmo assunto. (O agrupamento é por ENTIDADE — não há clustering de evento.)

    Returns:
        dict ordenado {espectro: {"count", "sentiment", "co_entities", "headlines"}},
        apenas para espectros com ≥1 artigo.
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT a.id, a.title, a.published_at, a.ai_sentiment, a.ai_bias,
                   COALESCE(f.title, f.url) AS feed
              FROM article_entities ae
              JOIN articles a ON a.id = ae.article_id
              JOIN feeds f    ON f.id = a.feed_id
             WHERE ae.entity_id = ?
             ORDER BY a.published_at DESC, a.id DESC
            """,
            (entity_id,),
        ).fetchall()
        co_rows = _conn.execute(
            """
            SELECT ae.article_id AS aid, e2.name AS name
              FROM article_entities ae
              JOIN article_entities ae2 ON ae2.article_id = ae.article_id
                                       AND ae2.entity_id != ae.entity_id
              JOIN entities e2 ON e2.id = ae2.entity_id
             WHERE ae.entity_id = ?
            """,
            (entity_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        log.error("entities: falha no enquadramento da entidade %d: %s", entity_id, exc)
        return {}
    finally:
        if should_close:
            _conn.close()

    def _spectrum_of(ai_bias_raw: str | None) -> str:
        if not ai_bias_raw:
            return "indefinido"
        try:
            esp = (json.loads(ai_bias_raw) or {}).get("espectro") or ""
        except (json.JSONDecodeError, TypeError):
            esp = ""
        esp = str(esp).strip().lower()
        return esp if esp in _SPECTRUM_ORDER else "indefinido"

    article_spectrum: dict[int, str] = {}
    groups: dict[str, dict] = {}
    for r in rows:
        esp = _spectrum_of(r["ai_bias"])
        article_spectrum[r["id"]] = esp
        g = groups.setdefault(esp, {
            "count": 0,
            "sentiment": {"positivo": 0, "neutro": 0, "negativo": 0},
            "co_entities": {},   # name → n (vira lista ordenada no fim)
            "headlines": [],
        })
        g["count"] += 1
        s = (r["ai_sentiment"] or "").strip().lower()
        if s in g["sentiment"]:
            g["sentiment"][s] += 1
        if len(g["headlines"]) < 5:
            g["headlines"].append({
                "title": r["title"], "feed": r["feed"],
                "published_at": r["published_at"], "ai_sentiment": r["ai_sentiment"],
            })

    # Entidades co-citadas, agregadas por espectro do artigo onde co-ocorreram.
    for cr in co_rows:
        esp = article_spectrum.get(cr["aid"])
        if esp is None:
            continue
        co = groups[esp]["co_entities"]
        co[cr["name"]] = co.get(cr["name"], 0) + 1

    # Finaliza: co_entities → lista top-5 por contagem; ordena espectros canonicamente.
    result: dict[str, dict] = {}
    for esp in _SPECTRUM_ORDER:
        if esp not in groups:
            continue
        g = groups[esp]
        g["co_entities"] = sorted(g["co_entities"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        result[esp] = g
    return result


def set_entity_notes(entity_id: int, notes: str, conn: sqlite3.Connection | None = None) -> bool:
    """Persiste as notas da usuária para uma entidade. True em sucesso."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute("UPDATE entities SET notes = ? WHERE id = ?", (notes, entity_id))
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("entities: falha ao salvar notas da entidade %d: %s", entity_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()
