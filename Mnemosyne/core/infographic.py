"""
Infográfico — extração estruturada de dados para visualização HTML.

O LLM extrai 4 categorias do corpus e o resultado é renderizado como HTML
autocontido (CSS inline) compatível com QWebEngineView e navegadores.

Categorias extraídas:
  - Estatísticas chave (números, percentuais, valores relevantes)
  - Entidades (pessoas, organizações, conceitos + atributos)
  - Relações causais (causa → efeito)
  - Linha do tempo (eventos com data ou período)
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import MnemosyneError
from .rag import strip_think


class InfographicError(MnemosyneError):
    """Falha ao gerar infográfico."""


_SAMPLE_K = 16
_CHUNK_CAP = 800

_EXTRACT_PROMPT = (
    "Analise os trechos abaixo e extraia as informações em JSON com exatamente estas chaves:\n\n"
    "{\n"
    '  "titulo": "título descritivo para o infográfico",\n'
    '  "estatisticas": [\n'
    '    {"valor": "42%", "descricao": "descrição do que representa"}\n'
    "  ],\n"
    '  "entidades": [\n'
    '    {"nome": "Nome da Entidade", "tipo": "pessoa|org|conceito", "detalhe": "atributo principal"}\n'
    "  ],\n"
    '  "relacoes": [\n'
    '    {"causa": "X", "efeito": "Y"}\n'
    "  ],\n"
    '  "timeline": [\n'
    '    {"periodo": "2020", "evento": "descrição do evento"}\n'
    "  ]\n"
    "}\n\n"
    "Regras:\n"
    "- Inclua apenas informações presentes nos trechos — não invente.\n"
    "- Cada lista pode ter 0 a 6 itens.\n"
    "- Responda APENAS com o JSON, sem texto antes ou depois.\n"
    "- Responda em português.\n\n"
    "Trechos:\n{context}\n\n"
    "JSON:"
)

_CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #12161E;
  color: #C8B99A;
  font-family: "Courier Prime", "Courier New", monospace;
  font-size: 13px;
  padding: 20px;
  line-height: 1.5;
}
h1 {
  color: #D4A820;
  font-size: 16px;
  margin-bottom: 18px;
  border-bottom: 1px solid #2A3148;
  padding-bottom: 8px;
  font-style: italic;
}
h2 {
  color: #9A9080;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  margin-bottom: 10px;
}
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.card {
  background: #1C2030;
  border: 1px solid #2A3148;
  border-radius: 3px;
  padding: 14px;
}
.card.full { grid-column: 1 / -1; }
.stat-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.stat {
  background: #252B3A;
  border: 1px solid #2A3148;
  border-radius: 2px;
  padding: 8px 12px;
  min-width: 100px;
}
.stat .valor { color: #D4A820; font-size: 18px; font-weight: bold; }
.stat .desc  { color: #7C828E; font-size: 10px; margin-top: 2px; }
.entity { margin-bottom: 6px; }
.entity .nome { color: #C8B99A; font-weight: bold; }
.entity .tipo { color: #D4A820; font-size: 10px; margin-left: 4px; }
.entity .detalhe { color: #7C828E; font-size: 11px; }
.rel { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.rel .box {
  background: #252B3A;
  border: 1px solid #2A3148;
  padding: 4px 8px;
  border-radius: 2px;
  font-size: 11px;
  flex: 1;
}
.rel .arrow { color: #D4A820; font-size: 14px; flex-shrink: 0; }
.tl-item { display: flex; gap: 12px; margin-bottom: 8px; align-items: flex-start; }
.tl-periodo {
  color: #D4A820;
  font-size: 10px;
  white-space: nowrap;
  min-width: 60px;
  padding-top: 2px;
}
.tl-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #D4A820;
  flex-shrink: 0;
  margin-top: 5px;
}
.tl-evento { color: #C8B99A; font-size: 11px; }
.empty { color: #4A5060; font-style: italic; font-size: 11px; }
</style>
"""


def _sample_context(vectorstore: Any) -> str:
    try:
        docs = vectorstore.similarity_search(
            "dados estatísticas entidades eventos causas", k=_SAMPLE_K
        )
    except Exception as exc:
        raise InfographicError(f"Falha ao amostrar vectorstore: {exc}") from exc

    seen: set[str] = set()
    parts: list[str] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            parts.append(doc.page_content[:_CHUNK_CAP])
    if not parts:
        raise InfographicError("Nenhum documento encontrado.")
    return "\n\n---\n".join(parts)


def _extract_json(raw: str) -> dict:
    """Extrai o primeiro bloco JSON da resposta do LLM."""
    raw = raw.strip()
    # Tenta bloco ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    # Tenta primeiro { ... } do texto
    m2 = re.search(r"\{.*\}", raw, re.DOTALL)
    if m2:
        raw = m2.group(0)
    return json.loads(raw)


def _render_html(data: dict) -> str:
    titulo = data.get("titulo", "Infográfico")
    stats = data.get("estatisticas", [])
    entidades = data.get("entidades", [])
    relacoes = data.get("relacoes", [])
    timeline = data.get("timeline", [])

    def _stat_card() -> str:
        if not stats:
            return '<p class="empty">Nenhuma estatística encontrada.</p>'
        items = "".join(
            f'<div class="stat"><div class="valor">{s.get("valor","")}</div>'
            f'<div class="desc">{s.get("descricao","")}</div></div>'
            for s in stats
        )
        return f'<div class="stat-grid">{items}</div>'

    def _entity_card() -> str:
        if not entidades:
            return '<p class="empty">Nenhuma entidade encontrada.</p>'
        items = "".join(
            f'<div class="entity">'
            f'<span class="nome">{e.get("nome","")}</span>'
            f'<span class="tipo">[{e.get("tipo","")}]</span>'
            f'<div class="detalhe">{e.get("detalhe","")}</div>'
            f'</div>'
            for e in entidades
        )
        return items

    def _rel_card() -> str:
        if not relacoes:
            return '<p class="empty">Nenhuma relação causal encontrada.</p>'
        items = "".join(
            f'<div class="rel">'
            f'<div class="box">{r.get("causa","")}</div>'
            f'<span class="arrow">→</span>'
            f'<div class="box">{r.get("efeito","")}</div>'
            f'</div>'
            for r in relacoes
        )
        return items

    def _timeline_card() -> str:
        if not timeline:
            return '<p class="empty">Nenhum evento temporal encontrado.</p>'
        items = "".join(
            f'<div class="tl-item">'
            f'<div class="tl-periodo">{t.get("periodo","")}</div>'
            f'<div class="tl-dot"></div>'
            f'<div class="tl-evento">{t.get("evento","")}</div>'
            f'</div>'
            for t in timeline
        )
        return items

    return f"""<!DOCTYPE html>
<html lang="pt">
<head><meta charset="utf-8">{_CSS}</head>
<body>
<h1>{titulo}</h1>
<div class="grid">
  <div class="card">
    <h2>Estatísticas Chave</h2>
    {_stat_card()}
  </div>
  <div class="card">
    <h2>Entidades</h2>
    {_entity_card()}
  </div>
  <div class="card">
    <h2>Relações Causais</h2>
    {_rel_card()}
  </div>
  <div class="card">
    <h2>Linha do Tempo</h2>
    {_timeline_card()}
  </div>
</div>
</body>
</html>"""


def iter_infographic(vectorstore: Any, config: "AppConfig") -> Iterator[str]:
    """Gera infográfico HTML estruturado como output do Studio.

    Yields:
        Um único chunk com o HTML completo.

    Raises:
        InfographicError: se a extração ou renderização falhar.
    """
    context = _sample_context(vectorstore)

    try:
        llm = OllamaLLM(model=config.llm_model, temperature=0.1, timeout=90)
        raw = strip_think(llm.invoke(_EXTRACT_PROMPT.format(context=context)))
    except Exception as exc:
        raise InfographicError(f"Falha ao chamar LLM: {exc}") from exc

    try:
        data = _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        # Fallback: HTML simples com o texto bruto
        data = {"titulo": "Infográfico", "estatisticas": [], "entidades": [],
                "relacoes": [], "timeline": []}

    yield _render_html(data)
