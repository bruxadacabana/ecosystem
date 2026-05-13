"""
LOGOS — Dispatcher de skills multi-agente.

Arquitetura:
  Router 3B (sempre aquecido, keep_alive: -1) → seleciona o skill correto
  Executor 7B+ (carregado sob demanda)        → executa com o system prompt do skill

Uso:
    from logos.dispatcher import dispatch, get_skill_system_prompt

    selection = await dispatch("resuma esse texto sobre transformers")
    # SkillSelection(skill='synthesis', confidence=0.92)

    system_prompt = get_skill_system_prompt(selection.skill)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from pydantic import BaseModel, field_validator

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

_SKILLS_DIR          = Path(__file__).parent / "skills"
_FALLBACK_SKILL      = "synthesis"
_CONFIDENCE_THRESHOLD = 0.7
_DEFAULT_ROUTER_MODEL = "llama3.2:3b"
_DEFAULT_LOGOS_URL   = "http://127.0.0.1:7072"

# ---------------------------------------------------------------------------
# Carregamento de skills
# ---------------------------------------------------------------------------

def _load_skills() -> dict[str, dict]:
    """
    Carrega todos os arquivos .md de logos/skills/ e extrai:
    - frontmatter YAML: name, description (usados pelo dispatcher)
    - corpo Markdown: system_prompt (usado pelo executor)
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


# Carregado uma vez no import — os arquivos .md raramente mudam em runtime
_SKILLS: dict[str, dict] = _load_skills()


def reload_skills() -> None:
    """Recarrega skills do disco (útil após editar os .md sem reiniciar)."""
    global _SKILLS
    _SKILLS = _load_skills()


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class SkillSelection(BaseModel):
    """Resultado do dispatcher: skill selecionado + confiança do router."""

    skill:      str
    confidence: float

    @field_validator("skill")
    @classmethod
    def validate_skill(cls, v: str) -> str:
        if _SKILLS and v not in _SKILLS:
            log.warning("Skill desconhecido retornado pelo router: %r — usando fallback", v)
            return _FALLBACK_SKILL
        return v

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# ---------------------------------------------------------------------------
# Prompt do dispatcher
# ---------------------------------------------------------------------------

def _build_dispatch_prompt(request: str) -> str:
    """
    Monta o prompt para o router 3B.
    Inclui apenas os campos `name` e `description` de cada skill —
    o system_prompt (executor) nunca vai para o router.
    """
    skill_lines = "\n".join(
        f"- {name}: {info['description'][:300]}"
        for name, info in _SKILLS.items()
    )
    return (
        "Você é um dispatcher de tarefas de IA. Dado o request do usuário, "
        "selecione o skill mais adequado da lista abaixo.\n\n"
        f"Skills disponíveis:\n{skill_lines}\n\n"
        f"Request: {request}\n\n"
        "Responda com o nome EXATO do skill (sem aspas extras) e sua confiança "
        "(0.0 = incerto, 1.0 = certeza absoluta)."
    )


# ---------------------------------------------------------------------------
# Dispatcher assíncrono
# ---------------------------------------------------------------------------

async def dispatch(
    request:      str,
    router_model: str = _DEFAULT_ROUTER_MODEL,
    logos_url:    str = _DEFAULT_LOGOS_URL,
) -> SkillSelection:
    """
    Roteia um request para o skill correto usando o modelo router 3B.

    O modelo router é mantido sempre aquecido na VRAM (keep_alive: -1).
    Temperature 0 garante respostas determinísticas.
    JSON schema com enum restringe a saída aos skills disponíveis.

    Retorna SkillSelection com o skill e confiança. Se confiança < threshold
    ou em caso de erro, retorna o skill de fallback ('synthesis').
    """
    if not _SKILLS:
        return SkillSelection(skill=_FALLBACK_SKILL, confidence=1.0)

    valid_skills = list(_SKILLS.keys())

    # JSON Schema com enum limitando aos skills existentes
    # O Ollama usa isso para forçar structured output válido
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
        "model":    router_model,
        "messages": [{"role": "user", "content": _build_dispatch_prompt(request)}],
        "format":   schema,
        "stream":   False,
        "keep_alive": -1,         # router sempre aquecido
        "options":  {"temperature": 0, "num_predict": 64},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{logos_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "{}")
            result = SkillSelection.model_validate_json(content)
            if result.confidence < _CONFIDENCE_THRESHOLD:
                log.debug(
                    "Confiança baixa (%.2f < %.2f) para skill %r — usando fallback",
                    result.confidence, _CONFIDENCE_THRESHOLD, result.skill,
                )
                return SkillSelection(skill=_FALLBACK_SKILL, confidence=result.confidence)
            return result
    except httpx.TimeoutException:
        log.warning("Timeout no dispatcher — usando fallback")
    except httpx.HTTPStatusError as exc:
        log.warning("HTTP %d no dispatcher — usando fallback", exc.response.status_code)
    except Exception as exc:
        log.warning("Erro no dispatcher: %s — usando fallback", exc)

    return SkillSelection(skill=_FALLBACK_SKILL, confidence=0.0)


# ---------------------------------------------------------------------------
# Helpers para o executor
# ---------------------------------------------------------------------------

def get_skill_system_prompt(skill_name: str) -> str:
    """
    Retorna o system prompt (corpo do .md) do skill solicitado.
    Fallback para 'synthesis' se o skill não existir.
    """
    skill = _SKILLS.get(skill_name) or _SKILLS.get(_FALLBACK_SKILL)
    if skill is None:
        return ""
    return skill["system_prompt"]


def list_skills() -> list[dict]:
    """Retorna lista de skills carregados com name e description."""
    return [
        {"name": s["name"], "description": s["description"]}
        for s in _SKILLS.values()
    ]
