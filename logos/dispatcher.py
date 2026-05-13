"""
LOGOS — Dispatcher de skills multi-agente.

Arquitetura 3-tier (latência crescente, acionado em ordem):
  Tier 1 — Regex/keyword  (~0 ms)   : cobre ~80% dos casos triviais
  Tier 2 — Embedding sim  (~50 ms)  : requests ambíguos mas estruturados
  Tier 3 — LLM router 3B (~200 ms) : casos que escapam aos dois filtros

Executor por skill:
  Cada skill pode ter um modelo executor específico definido em
  SKILL_EXECUTOR_OVERRIDES. Padrão: modelo configurado pelo chamador.
  Exceção: rag-query → command-r:7b (único sub-10B com grounded generation)

Uso:
    from logos.dispatcher import dispatch, get_skill_system_prompt, get_executor_model

    selection = await dispatch("resuma esse texto sobre transformers")
    # SkillSelection(skill='synthesis', confidence=1.0, tier='keyword')

    system_prompt = get_skill_system_prompt(selection.skill)
    executor = get_executor_model(selection.skill, default="llama3.1:8b")
    # executor = "command-r:7b" para rag-query, "llama3.1:8b" para os demais
"""
from __future__ import annotations

import math
import re
import logging
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, field_validator

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

_SKILLS_DIR           = Path(__file__).parent / "skills"
_FALLBACK_SKILL       = "synthesis"
_CONFIDENCE_THRESHOLD = 0.7
_DEFAULT_ROUTER_MODEL = "llama3.2:3b"
_DEFAULT_EMBED_MODEL  = "nomic-embed-text"
_DEFAULT_LOGOS_URL    = "http://127.0.0.1:7072"

# Tier 2: threshold de similaridade para aceitar resultado de embedding
_EMBED_THRESHOLD = 0.75

# Executor específico por skill (sobrescreve o default do chamador)
# command-r:7b é o único modelo sub-10B com treinamento explícito para
# grounded generation com citação de fontes (Cohere grounding spans).
SKILL_EXECUTOR_OVERRIDES: dict[str, str] = {
    "rag-query": "command-r:7b",
}

# ---------------------------------------------------------------------------
# Carregamento de skills
# ---------------------------------------------------------------------------

def _load_skills() -> dict[str, dict]:
    """
    Carrega todos os .md de logos/skills/ e extrai:
    - frontmatter YAML: name, description  (usados pelo dispatcher)
    - corpo Markdown:   system_prompt      (usado pelo executor)
    """
    skills: dict[str, dict] = {}
    try:
        import frontmatter as _fm
    except ImportError:
        log.warning("python-frontmatter não instalado — skills não carregados")
        return skills

    for md_file in sorted(_SKILLS_DIR.glob("*.md")):
        try:
            post = _fm.loads(md_file.read_text(encoding="utf-8"))
            name = str(post.metadata.get("name", md_file.stem)).strip()
            desc = str(post.metadata.get("description", "")).strip()
            if not name:
                continue
            skills[name] = {
                "name":          name,
                "description":   desc,
                "system_prompt": post.content.strip(),
                "path":          md_file,
            }
            log.debug("Skill carregado: %s", name)
        except Exception as exc:
            log.warning("Erro ao carregar skill %s: %s", md_file.name, exc)

    return skills


_SKILLS: dict[str, dict] = _load_skills()


def reload_skills() -> None:
    """Recarrega skills do disco e invalida cache de embeddings."""
    global _SKILLS, _skill_embeddings
    _SKILLS = _load_skills()
    _skill_embeddings = {}


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class SkillSelection(BaseModel):
    """Resultado do dispatcher: skill selecionado, confiança e tier usado."""

    skill:      str
    confidence: float
    tier:       Literal["keyword", "embedding", "llm", "fallback"] = "llm"

    @field_validator("skill")
    @classmethod
    def validate_skill(cls, v: str) -> str:
        if _SKILLS and v not in _SKILLS:
            log.warning("Skill desconhecido: %r — usando fallback", v)
            return _FALLBACK_SKILL
        return v

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# ---------------------------------------------------------------------------
# Tier 1 — Regex/keyword matching
# ---------------------------------------------------------------------------

# Cada tupla: (padrão compilado, nome do skill)
# Ordenados do mais específico para o mais genérico para evitar falsos positivos.
_KEYWORD_RULES: list[tuple[re.Pattern, str]] = [
    # entity-extraction — padrão: verbo de extração + tipo de entidade
    (re.compile(
        r"\b(extra[ií]|identifique?|liste?|encontre?)\b.{0,50}"
        r"\b(pessoas?|organiza[cç][õo]es?|entidades?|datas?|conceitos?|nomes?|lugares?|locais?)\b",
        re.I | re.S,
    ), "entity-extraction"),

    # chunk-classification — padrão: verbo de classificação + "chunk/trecho"
    (re.compile(
        r"\b(classifi[cq]|categorize?|rotule?|qual o tipo)\b.{0,50}"
        r"\b(chunk|trecho|parágrafo|fragmento)\b",
        re.I | re.S,
    ), "chunk-classification"),

    # rag-query — padrão: referência explícita a documentos indexados
    (re.compile(
        r"\b(nos? meus?|em meus?|nos? (seus?|minha?s?))\s+(documentos?|arquivos?|textos?|artigos?|pdfs?)\b"
        r"|\b(segundo|conforme|de acordo com)\s+(o|a|os|as)\s+(arquivo|documento|artigo|texto|pdf)\b"
        r"|\bcite (as )?fontes\b"
        r"|\bnas? fontes? indexadas?\b",
        re.I,
    ), "rag-query"),

    # synthesis — padrão: pedido direto de resumo/síntese
    (re.compile(
        r"\b(resuma|resumo|sintetize?|condense?|condensar|sumariz|sumário|sumario"
        r"|tl;?dr|pontos? principais?|principais? pontos?|fa[çc]a um resumo)\b",
        re.I,
    ), "synthesis"),
]


def _keyword_route(request: str) -> SkillSelection | None:
    """
    Tier 1: testa regras regex em ordem.
    Retorna SkillSelection com confidence=1.0 se alguma regra casou, None caso contrário.
    """
    for pattern, skill in _KEYWORD_RULES:
        if pattern.search(request):
            log.debug("Tier 1 (keyword) → %s", skill)
            return SkillSelection(skill=skill, confidence=1.0, tier="keyword")
    return None


# ---------------------------------------------------------------------------
# Tier 2 — Embedding similarity
# ---------------------------------------------------------------------------

# Cache de embeddings das descriptions dos skills (populado na primeira chamada)
_skill_embeddings: dict[str, list[float]] = {}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similaridade de cosseno sem numpy (vetores são pequenos o suficiente)."""
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


async def _get_embedding(
    text: str,
    logos_url: str,
    embed_model: str,
) -> list[float] | None:
    """Chama /api/embed no LOGOS e retorna o vetor. Retorna None em caso de erro."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{logos_url}/api/embed",
                json={"model": embed_model, "input": text},
            )
            resp.raise_for_status()
            data = resp.json()
            # Ollama retorna {"embeddings": [[...]]} (lista de listas)
            embeddings = data.get("embeddings")
            if embeddings and isinstance(embeddings[0], list):
                return embeddings[0]
    except Exception as exc:
        log.debug("Embedding falhou: %s", exc)
    return None


async def _ensure_skill_embeddings(logos_url: str, embed_model: str) -> bool:
    """
    Pré-computa e cacheia embeddings das descriptions de todos os skills.
    Retorna True se o cache está populado (mesmo que parcialmente).
    """
    if _skill_embeddings:
        return True  # já populado

    for name, info in _SKILLS.items():
        vec = await _get_embedding(info["description"], logos_url, embed_model)
        if vec is not None:
            _skill_embeddings[name] = vec

    return bool(_skill_embeddings)


async def _embedding_route(
    request: str,
    logos_url: str,
    embed_model: str,
) -> SkillSelection | None:
    """
    Tier 2: computa embedding do request e compara com embeddings das descriptions.
    Retorna SkillSelection se similaridade máxima > threshold, None caso contrário.
    """
    if not await _ensure_skill_embeddings(logos_url, embed_model):
        return None

    req_vec = await _get_embedding(request, logos_url, embed_model)
    if req_vec is None:
        return None

    best_skill = ""
    best_score = 0.0
    for name, skill_vec in _skill_embeddings.items():
        score = _cosine_similarity(req_vec, skill_vec)
        if score > best_score:
            best_score = score
            best_skill = name

    if best_skill and best_score >= _EMBED_THRESHOLD:
        log.debug("Tier 2 (embedding) → %s (score=%.3f)", best_skill, best_score)
        return SkillSelection(skill=best_skill, confidence=best_score, tier="embedding")

    log.debug("Tier 2 (embedding): melhor score %.3f < threshold %.3f", best_score, _EMBED_THRESHOLD)
    return None


# ---------------------------------------------------------------------------
# Tier 3 — LLM dispatcher (router 3B)
# ---------------------------------------------------------------------------

def _build_dispatch_prompt(request: str) -> str:
    skill_lines = "\n".join(
        f"- {name}: {info['description'][:300]}"
        for name, info in _SKILLS.items()
    )
    return (
        "Você é um dispatcher de tarefas de IA. Dado o request do usuário, "
        "selecione o skill mais adequado da lista abaixo.\n\n"
        f"Skills disponíveis:\n{skill_lines}\n\n"
        f"Request: {request}\n\n"
        "Responda com o nome EXATO do skill e sua confiança "
        "(0.0 = incerto, 1.0 = certeza absoluta)."
    )


async def _llm_route(
    request:      str,
    router_model: str,
    logos_url:    str,
) -> SkillSelection:
    """
    Tier 3: usa o router 3B via Ollama structured output.
    keep_alive: -1 mantém o router sempre aquecido na VRAM.
    """
    valid_skills = list(_SKILLS.keys())
    schema = {
        "type": "object",
        "properties": {
            "skill":      {"type": "string", "enum": valid_skills},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["skill", "confidence"],
        "additionalProperties": False,
    }

    payload = {
        "model":      router_model,
        "messages":   [{"role": "user", "content": _build_dispatch_prompt(request)}],
        "format":     schema,
        "stream":     False,
        "keep_alive": -1,
        "options":    {"temperature": 0, "num_predict": 64},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{logos_url}/api/chat", json=payload)
            resp.raise_for_status()
            data    = resp.json()
            content = data.get("message", {}).get("content", "{}")
            result  = SkillSelection.model_validate_json(content)
            result  = result.model_copy(update={"tier": "llm"})
            if result.confidence < _CONFIDENCE_THRESHOLD:
                log.debug("Tier 3 (LLM): confiança baixa %.2f → fallback", result.confidence)
                return SkillSelection(skill=_FALLBACK_SKILL, confidence=result.confidence, tier="fallback")
            log.debug("Tier 3 (LLM) → %s (conf=%.2f)", result.skill, result.confidence)
            return result
    except httpx.TimeoutException:
        log.warning("Timeout no dispatcher LLM")
    except httpx.HTTPStatusError as exc:
        log.warning("HTTP %d no dispatcher LLM", exc.response.status_code)
    except Exception as exc:
        log.warning("Erro no dispatcher LLM: %s", exc)

    return SkillSelection(skill=_FALLBACK_SKILL, confidence=0.0, tier="fallback")


# ---------------------------------------------------------------------------
# Dispatcher público — orquestra os 3 tiers
# ---------------------------------------------------------------------------

async def dispatch(
    request:      str,
    router_model: str = _DEFAULT_ROUTER_MODEL,
    embed_model:  str = _DEFAULT_EMBED_MODEL,
    logos_url:    str = _DEFAULT_LOGOS_URL,
) -> SkillSelection:
    """
    Roteia um request para o skill correto em até 3 tiers:
      1. Regex/keyword (~0 ms)    — cobre pedidos triviais e repetitivos
      2. Embedding sim (~50 ms)   — requests estruturados mas ambíguos
      3. LLM router   (~200 ms)   — apenas o que os filtros não resolveram

    O campo `tier` no resultado indica qual camada fez o routing.
    """
    if not _SKILLS:
        return SkillSelection(skill=_FALLBACK_SKILL, confidence=1.0, tier="fallback")

    # Tier 1
    result = _keyword_route(request)
    if result is not None:
        return result

    # Tier 2
    result = await _embedding_route(request, logos_url, embed_model)
    if result is not None:
        return result

    # Tier 3
    return await _llm_route(request, router_model, logos_url)


# ---------------------------------------------------------------------------
# Helpers para o executor
# ---------------------------------------------------------------------------

def get_skill_system_prompt(skill_name: str) -> str:
    """Retorna o system prompt (corpo do .md) para o skill. Fallback para 'synthesis'."""
    skill = _SKILLS.get(skill_name) or _SKILLS.get(_FALLBACK_SKILL)
    if skill is None:
        return ""
    return skill["system_prompt"]


def get_executor_model(skill_name: str, default_executor: str) -> str:
    """
    Retorna o modelo executor para o skill, aplicando overrides por skill.

    rag-query → command-r:7b  (grounded generation com citação de fontes)
    demais    → default_executor (configurado pelo chamador)
    """
    return SKILL_EXECUTOR_OVERRIDES.get(skill_name, default_executor)


def list_skills() -> list[dict]:
    """Retorna lista de skills carregados com name e description."""
    return [
        {"name": s["name"], "description": s["description"]}
        for s in _SKILLS.values()
    ]
