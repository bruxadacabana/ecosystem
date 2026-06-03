"""
archiver.py — Arquivamento de artigos como Markdown no ecossistema (KOSMOS v3, Fase 5).

Gera um `.md` em `{archive_path}/Web/{YYYY-MM-DD}_{slug}.md` com:
  - frontmatter YAML completo (`archived_by: kosmos`, título, fonte, URL, data,
    autor, idioma, tags, tipo; `kosmos_analysis: true` quando há análise AI;
    `has_translation` + `languages` quando dual-language);
  - texto limpo do artigo (content_text; fallback para content_excerpt);
  - seção `## Análise do KOSMOS` (cinco Ws, entidades, sentimento, viés) — marcada
    no frontmatter com `kosmos_analysis: true` para a Mnemosyne tratar como análise
    computacional, com peso distinto de uma fonte editorial;
  - referência ABNT ao final: formato artigo científico se houver DOI (detectado na
    URL), documento eletrônico nos demais casos;
  - dual-language: se um texto traduzido for fornecido, ambas as versões entram em
    seções separadas e o frontmatter ganha `has_translation: true` + idiomas.

Após gravar, marca `is_saved = 1` no artigo. O caminho de arquivo (`archive_path`)
vem da config (`KosmosConfig.archive_path`, derivada do sync_root) — não é hardcoded.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import get_conn

log = logging.getLogger("kosmos.archiver")

# Meses abreviados em português, padrão ABNT (maio sem abreviação).
_ABNT_MONTHS = {
    1: "jan.", 2: "fev.", 3: "mar.", 4: "abr.", 5: "maio", 6: "jun.",
    7: "jul.", 8: "ago.", 9: "set.", 10: "out.", 11: "nov.", 12: "dez.",
}

# DOI: 10.NNNN/sufixo (NBR-padrão); arXiv como caso especial de identificador.
_DOI_RE   = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers de formatação
# ---------------------------------------------------------------------------

def _slugify(title: str, max_len: int = 60) -> str:
    """Converte o título num slug ASCII seguro para nome de arquivo."""
    norm = unicodedata.normalize("NFKD", title or "")
    ascii_only = norm.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    slug = slug[:max_len].strip("-")
    return slug or "artigo"


def _parse_dt(iso: str | None) -> datetime | None:
    """ISO8601 → datetime (UTC-aware). None se ausente/invalido."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _abnt_date(dt: datetime | None) -> str:
    """datetime → 'DD mmm. YYYY' (ABNT). Vazio se None."""
    if dt is None:
        return ""
    return f"{dt.day} {_ABNT_MONTHS[dt.month]} {dt.year}"


def _abnt_author(author: str | None, source: str) -> str:
    """Formata o autor no estilo ABNT (SOBRENOME, Prenome).

    Sem autor pessoal → usa a fonte como autor corporativo (em maiúsculas), que é
    o tratamento ABNT para matérias sem assinatura.
    """
    a = (author or "").strip()
    if not a:
        return (source or "FONTE DESCONHECIDA").upper()
    parts = a.split()
    if len(parts) == 1:
        return a.upper()
    surname = parts[-1].upper()
    given = " ".join(parts[:-1])
    return f"{surname}, {given}"


def _detect_doi(url: str | None) -> tuple[str | None, bool]:
    """Detecta DOI/arXiv na URL. Retorna (doi_ou_id, is_doi)."""
    if not url:
        return None, False
    m = _DOI_RE.search(url)
    if m:
        return m.group(0), True
    m = _ARXIV_RE.search(url)
    if m:
        return f"arXiv:{m.group(1)}", False
    return None, False


def _yaml_escape(value: str) -> str:
    """Escapa uma string para valor YAML entre aspas duplas."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _yaml_list(items: list[str]) -> str:
    """Renderiza uma lista YAML inline: ["a", "b"]."""
    inner = ", ".join(f'"{_yaml_escape(i)}"' for i in items)
    return f"[{inner}]"


def _loads(raw: str | None):
    """json.loads tolerante: retorna None em vazio/invalido."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Blocos do documento
# ---------------------------------------------------------------------------

def _has_analysis(row: dict) -> bool:
    return any(row.get(k) for k in ("ai_five_ws", "ai_entities", "ai_sentiment", "ai_bias"))


def _build_frontmatter(
    row: dict,
    source: str,
    languages: list[str] | None,
) -> str:
    """Monta o bloco de frontmatter YAML."""
    dt = _parse_dt(row.get("published_at"))
    tags = _loads(row.get("ai_tags")) or []
    if not isinstance(tags, list):
        tags = []
    language = (row.get("ai_language") or row.get("language_detected") or "").strip()

    lines = ["---", "archived_by: kosmos"]
    lines.append(f'title: "{_yaml_escape(row.get("title") or "")}"')
    lines.append(f'source: "{_yaml_escape(source)}"')
    lines.append(f'url: "{_yaml_escape(row.get("url") or "")}"')
    if dt is not None:
        lines.append(f'date: "{dt.date().isoformat()}"')
    if row.get("author"):
        lines.append(f'author: "{_yaml_escape(row["author"])}"')
    if language:
        lines.append(f'language: "{_yaml_escape(language)}"')
    if tags:
        lines.append(f"tags: {_yaml_list([str(t) for t in tags])}")
    if row.get("article_type"):
        lines.append(f'type: "{_yaml_escape(row["article_type"])}"')
    if _has_analysis(row):
        lines.append("kosmos_analysis: true")
    if languages:
        lines.append("has_translation: true")
        lines.append(f"languages: {_yaml_list(languages)}")
    lines.append(f'archived_at: "{datetime.now(timezone.utc).isoformat()}"')
    lines.append("---")
    return "\n".join(lines)


def _build_analysis_section(row: dict) -> str:
    """Monta a seção '## Análise do KOSMOS' a partir dos campos AI presentes."""
    if not _has_analysis(row):
        return ""

    out = [
        "## Análise do KOSMOS",
        "",
        "> Análise computacional gerada automaticamente pelo KOSMOS — "
        "não é fonte editorial.",
        "",
    ]

    sentiment = (row.get("ai_sentiment") or "").strip()
    if sentiment:
        out.append(f"**Sentimento:** {sentiment}")
        out.append("")

    five = _loads(row.get("ai_five_ws"))
    if isinstance(five, dict) and any(five.values()):
        labels = [
            ("quem", "Quem"), ("o_que", "O quê"), ("quando", "Quando"),
            ("onde", "Onde"), ("por_que", "Por quê"),
        ]
        out.append("**Cinco Ws:**")
        for key, label in labels:
            val = (str(five.get(key) or "")).strip()
            if val:
                out.append(f"- {label}: {val}")
        out.append("")

    entities = _loads(row.get("ai_entities"))
    if isinstance(entities, list) and entities:
        formatted = []
        for ent in entities:
            if isinstance(ent, dict):
                nome = str(ent.get("nome") or "").strip()
                tipo = str(ent.get("tipo") or "").strip()
                if nome:
                    formatted.append(f"{nome} ({tipo})" if tipo else nome)
            elif ent:
                formatted.append(str(ent))
        if formatted:
            out.append("**Entidades:** " + ", ".join(formatted))
            out.append("")

    bias = _loads(row.get("ai_bias"))
    if isinstance(bias, dict) and any(bias.values()):
        espectro = str(bias.get("espectro") or "").strip()
        marcadores = bias.get("marcadores")
        if isinstance(marcadores, list):
            marcadores = ", ".join(str(m) for m in marcadores)
        marcadores = str(marcadores or "").strip()
        qualidade = str(bias.get("qualidade_apuracao") or "").strip()
        parts = []
        if espectro:
            parts.append(f"espectro {espectro}")
        if marcadores:
            parts.append(f"marcadores: {marcadores}")
        if qualidade:
            parts.append(f"qualidade da apuração: {qualidade}")
        if parts:
            out.append("**Viés político:** " + "; ".join(parts))
            out.append("")

    return "\n".join(out).rstrip() + "\n"


def _build_abnt(row: dict, source: str) -> str:
    """Monta a referência ABNT ao final do documento.

    Com DOI → formato de artigo científico (com linha DOI); senão → documento
    eletrônico. Ambos terminam com 'Disponível em' + 'Acesso em' (NBR 6023).
    """
    author = _abnt_author(row.get("author"), source)
    title = (row.get("title") or "").strip().rstrip(".")
    url = row.get("url") or ""
    pub_dt = _parse_dt(row.get("published_at"))
    access = _abnt_date(datetime.now(timezone.utc))
    doi, is_doi = _detect_doi(url)

    ref = f"{author}. **{title}**. {source}"
    if pub_dt is not None:
        ref += f", {_abnt_date(pub_dt)}"
    ref += "."
    if doi:
        ref += f" DOI: {doi}." if is_doi else f" {doi}."
    if url:
        ref += f" Disponível em: {url}."
    if access:
        ref += f" Acesso em: {access}."

    kind = "Referência (ABNT — artigo científico)" if is_doi else "Referência (ABNT — documento eletrônico)"
    return f"## {kind}\n\n{ref}\n"


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def _render_markdown(
    row: dict,
    source: str,
    translated_text: str | None,
    translated_lang: str | None,
) -> str:
    """Monta o documento Markdown completo a partir dos dados do artigo."""
    body = (row.get("content_text") or row.get("content_excerpt") or "").strip()

    languages: list[str] | None = None
    if translated_text:
        original_lang = (row.get("ai_language") or row.get("language_detected") or "original").strip()
        languages = [original_lang or "original", translated_lang or "traduzido"]

    parts = [_build_frontmatter(row, source, languages), ""]
    parts.append(f"# {row.get('title') or '(sem título)'}")
    parts.append("")

    if translated_text:
        # Dual-language: versões em seções separadas.
        orig_label = (languages[0] if languages else "Original")
        trans_label = (translated_lang or "Tradução")
        parts.append(f"## Texto original ({orig_label})")
        parts.append("")
        parts.append(body)
        parts.append("")
        parts.append(f"## Tradução ({trans_label})")
        parts.append("")
        parts.append(translated_text.strip())
        parts.append("")
    else:
        parts.append(body)
        parts.append("")

    analysis = _build_analysis_section(row)
    if analysis:
        parts.append(analysis)
        parts.append("")

    parts.append(_build_abnt(row, source))

    return "\n".join(parts).rstrip() + "\n"


def _unique_path(directory: Path, base_name: str) -> Path:
    """Retorna um caminho .md inédito em `directory` (acrescenta -2, -3… se colidir)."""
    candidate = directory / f"{base_name}.md"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{base_name}-{counter}.md"
        counter += 1
    return candidate


def archive_article(
    article_id: int,
    archive_path: str,
    conn: sqlite3.Connection | None = None,
    translated_text: str | None = None,
    translated_lang: str | None = None,
) -> Path:
    """Arquiva um artigo como Markdown em `{archive_path}/Web/` e marca is_saved=1.

    Args:
        article_id:      ID do artigo na tabela articles.
        archive_path:    raiz de arquivamento do KOSMOS (config.archive_path).
        conn:            conexão existente (testes); None → cria e fecha própria.
        translated_text: texto traduzido (Fase 6); se presente, gera dual-language.
        translated_lang: idioma do texto traduzido (ex.: "pt").

    Returns:
        Path do arquivo .md gerado.

    Raises:
        ValueError:   artigo não encontrado.
        OSError:      falha ao criar diretório ou gravar o arquivo.
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        row_obj = _conn.execute(
            """
            SELECT a.id, a.url, a.title, a.author, a.published_at, a.article_type,
                   a.language_detected, a.content_excerpt, a.content_text,
                   a.ai_tags, a.ai_sentiment, a.ai_language, a.ai_five_ws,
                   a.ai_entities, a.ai_bias,
                   COALESCE(f.title, f.url) AS feed_title
              FROM articles a
              JOIN feeds f ON f.id = a.feed_id
             WHERE a.id = ?
            """,
            (article_id,),
        ).fetchone()

        if row_obj is None:
            raise ValueError(f"Artigo {article_id} não encontrado.")

        row = dict(row_obj)
        source = (row.get("feed_title") or "").strip() or "Fonte desconhecida"

        markdown = _render_markdown(row, source, translated_text, translated_lang)

        web_dir = Path(archive_path) / "Web"
        web_dir.mkdir(parents=True, exist_ok=True)

        dt = _parse_dt(row.get("published_at")) or datetime.now(timezone.utc)
        base_name = f"{dt.date().isoformat()}_{_slugify(row.get('title') or '')}"
        out_path = _unique_path(web_dir, base_name)

        out_path.write_text(markdown, encoding="utf-8")
        log.info("Artigo %d arquivado em %s.", article_id, out_path)

        _conn.execute("UPDATE articles SET is_saved = 1 WHERE id = ?", (article_id,))
        _conn.commit()

        return out_path
    except sqlite3.Error as exc:
        log.error("Falha de banco ao arquivar artigo %d: %s", article_id, exc)
        raise
    finally:
        if should_close:
            _conn.close()
