"""
AKASHA — Persona persistente
Constrói e mantém uma auto-representação do AKASHA baseada no perfil de
interesse acumulado pelo KnowledgeWorker. Atualizada uma vez por dia.
Injetada em prompts LLM para moldar o contexto sem alterar os resultados.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("akasha.persona")

_REBUILD_INTERVAL_S: int   = 86400   # 1 vez por dia
_PERSONA_TIMEOUT_S:  float = 20.0

def _get_inference_base() -> str:
    from ecosystem_client import get_inference_url as _get_url
    return _get_url()


def _get_model() -> str:
    try:
        from ecosystem_client import get_active_profile as _get_profile
        p = _get_profile()
        return ((p or {}).get("models", {}) or {}).get("llm_query", "") if p else ""
    except Exception:
        return ""

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
        """Retorna string para injetar no início de prompts LLM."""
        if not self.is_formed:
            return ""
        return f"Contexto: {self.self_description} "

# ---------------------------------------------------------------------------
# Cache em memória (evita leituras repetidas ao DB por busca)
# ---------------------------------------------------------------------------

_cached_persona: AppPersona = AppPersona()

# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def get_persona() -> AppPersona:
    """Retorna a persona atual (em memória). Nunca faz IO."""
    return _cached_persona


async def load_persona() -> AppPersona:
    """Lê a persona persistida no DB e atualiza o cache em memória."""
    global _cached_persona
    import database as _db
    desc      = await _db.get_profile_value("persona_description", "")
    topics_j  = await _db.get_profile_value("persona_topics", "[]")
    formed_at = await _db.get_profile_value("persona_formed_at", "")
    import json
    try:
        topics = json.loads(topics_j)
    except Exception:
        topics = []
    _cached_persona = AppPersona(
        self_description=desc,
        expertise_topics=topics,
        formed_at=formed_at,
    )
    return _cached_persona


async def persona_rebuild_loop() -> None:
    """Loop background: reconstrói a persona uma vez por dia."""
    # Carrega persona existente no startup
    await load_persona()
    while True:
        await asyncio.sleep(_REBUILD_INTERVAL_S)
        try:
            await _rebuild_persona()
        except Exception as exc:
            log.debug("persona: rebuild falhou: %s", exc)


# ---------------------------------------------------------------------------
# Reconstrução
# ---------------------------------------------------------------------------

async def _rebuild_persona() -> None:
    """Lê top-10 tópicos e chama Ollama para reescrever self_description."""
    import database as _db
    import json

    top = await _db.get_top_topics(10)
    if not top:
        return

    topics = [t for t, _ in top]
    topics_str = ", ".join(topics)

    model = _get_model()
    if not model:
        return

    log.info("persona: reconstruindo self_description com %d tópico(s) (modelo: %s)", len(topics), model)

    prompt = (
        f"Tópicos mais frequentes no índice deste sistema de busca: {topics_str}.\n\n"
        "Com base nesses tópicos, escreva em 2-3 frases curtas quem você é como sistema "
        "de busca pessoal, em primeira pessoa. Seja específico sobre as áreas de interesse. "
        "Não mencione que é uma IA. Apenas as frases, sem introdução."
    )

    try:
        async with httpx.AsyncClient(timeout=_PERSONA_TIMEOUT_S) as client:
            resp = await client.post(
                f"{_get_inference_base()}/v1/chat/completions",
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  100,
                    "temperature": 0.4,
                },
            )
            resp.raise_for_status()
            description = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.debug("persona: inferência falhou: %s", exc)
        return

    if not description:
        return

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    await _db.set_profile_value("persona_description", description)
    await _db.set_profile_value("persona_topics", json.dumps(topics))
    await _db.set_profile_value("persona_formed_at", now)

    global _cached_persona
    _cached_persona = AppPersona(
        self_description=description,
        expertise_topics=topics,
        formed_at=now,
    )
    log.info("persona: reconstruída com %d tópicos.", len(topics))
