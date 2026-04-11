"""Exporta artigos para Markdown em data/archive/."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.models import Article

log = logging.getLogger("kosmos.archive")

_MONTHS = [
    "jan.", "fev.", "mar.", "abr.", "maio", "jun.",
    "jul.", "ago.", "set.", "out.", "nov.", "dez.",
]


def _format_abnt(article: "Article", feed_name: str | None) -> str:
    """Gera referência bibliográfica ABNT para artigo online."""
    author = (article.author or "").strip()
    if author:
        parts = author.split()
        if len(parts) >= 2:
            last  = parts[-1].upper()
            first = " ".join(parts[:-1])
            author_fmt = f"{last}, {first}. "
        else:
            author_fmt = author.upper() + ". "
    else:
        author_fmt = ""

    title       = (article.title or "").strip()
    publication = (feed_name or "").strip()

    pub_date = ""
    if article.published_at:
        d = article.published_at
        pub_date = f"{d.day} {_MONTHS[d.month - 1]} {d.year}"

    today  = date.today()
    access = f"{today.day} {_MONTHS[today.month - 1]} {today.year}"
    url    = (article.url or "").strip()

    citation  = author_fmt
    citation += f"{title}. "
    if publication:
        citation += f"{publication}, "
    citation += "[s.l.], "
    if pub_date:
        citation += f"{pub_date}. "
    if url:
        citation += f"Disponível em: {url}. "
    citation += f"Acesso em: {access}."
    return citation


def _slugify(text: str, max_len: int = 60) -> str:
    """Converte texto em slug seguro para nomes de arquivo."""
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "_", text.strip())
    return text[:max_len].rstrip("_") or "untitled"


def _yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def export_article(article: "Article", feed_name: str | None = None) -> Path:
    """Exporta o artigo para Markdown em data/archive/{feed}/{slug}.md.

    Retorna o Path do arquivo criado.
    """
    import html2text as _h2t

    from app.utils.paths import Paths

    feed_slug = _slugify(feed_name or "sem-fonte", 40)
    dest_dir = Paths.ARCHIVE / feed_slug
    dest_dir.mkdir(parents=True, exist_ok=True)

    title = article.title or "sem-titulo"
    dest = dest_dir / (_slugify(title) + ".md")

    # HTML → Markdown
    converter = _h2t.HTML2Text()
    converter.ignore_links  = False
    converter.ignore_images = True
    converter.body_width    = 0   # sem quebra de linha automática
    content_html = article.content_full or article.summary or ""
    body_md = converter.handle(content_html).strip() if content_html else "_Sem conteúdo._"

    # Data de publicação
    pub = ""
    if article.published_at:
        ts = article.published_at
        pub = ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, datetime) else str(ts)

    lines: list[str] = [
        "---",
        f"title: {_yaml_str(title)}",
        f"source: {_yaml_str(feed_name or '')}",
        f"date: {pub}",
        f"author: {_yaml_str(article.author or '')}",
        f"url: {article.url or ''}",
        "---",
        "",
        f"# {title}",
        "",
        body_md,
    ]

    # Resumo gerado por IA
    if article.ai_summary and article.ai_summary.strip():
        lines += [
            "",
            "---",
            "",
            "## Resumo",
            "",
            article.ai_summary.strip(),
        ]

    # Análise 5Ws
    if article.ai_5ws:
        try:
            ws = json.loads(article.ai_5ws)
            _LABELS = [
                ("who",   "Quem"),
                ("what",  "O quê"),
                ("when",  "Quando"),
                ("where", "Onde"),
                ("why",   "Por quê"),
            ]
            ws_lines = [
                "",
                "---",
                "",
                "## Análise 5Ws",
                "",
            ]
            for key, label in _LABELS:
                val = (ws.get(key) or "").strip()
                if val:
                    ws_lines.append(f"**{label}:** {val}")
            lines += ws_lines
        except Exception:
            pass

    # Referência ABNT
    lines += [
        "",
        "---",
        "",
        "## Referência (ABNT)",
        "",
        _format_abnt(article, feed_name),
    ]

    dest.write_text("\n".join(lines), encoding="utf-8")
    log.info("Artigo exportado: %s", dest)
    return dest
