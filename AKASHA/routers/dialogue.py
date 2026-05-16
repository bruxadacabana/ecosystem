"""
AKASHA — Endpoint de diálogo com a Mnemosyne
POST /dialogue/turn → stream SSE de "thought fragments" ancorados em fontes reais.

Exceção controlada ao princípio de amplificador: este é o único endpoint onde o AKASHA
gera texto narrativo. A exceção é justificada porque:
  (a) o destinatário é a Mnemosyne, não a usuária diretamente;
  (b) cada fragmento gerado é obrigatoriamente ancorado em snippets reais do índice;
  (c) o endpoint não substitui a busca — ele interpreta o que o índice contém.
Sem esse endpoint o diálogo inter-app seria impossível.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

log = logging.getLogger("akasha.dialogue")

router = APIRouter(prefix="/dialogue", tags=["dialogue"])

# ---------------------------------------------------------------------------
# Resolução LOGOS-first (mesma lógica do persona.py e local_search.py)
# ---------------------------------------------------------------------------

try:
    from ecosystem_client import get_ollama_url as _get_url, get_active_profile as _get_profile
    _OLLAMA_BASE: str = _get_url()
    _p = _get_profile()
    _DEFAULT_MODEL: str = (_p or {}).get("models", {}).get("llm_kosmos", "") if _p else ""
except Exception:
    _OLLAMA_BASE   = "http://localhost:11434"
    _DEFAULT_MODEL = ""

_DIALOGUE_TIMEOUT_S: float = 30.0
_MAX_SNIPPETS:       int   = 5


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class DialogueTurn(BaseModel):
    question:    str
    context:     list[str] = []
    turn_index:  int       = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_prompt(
    question: str,
    context: list[str],
    turn_index: int,
    snippets: list[dict],
    persona_prefix: str,
) -> str:
    parts: list[str] = []

    if persona_prefix:
        parts.append(persona_prefix.rstrip())

    if snippets:
        parts.append("Fontes encontradas no índice:")
        for i, s in enumerate(snippets, 1):
            title   = s.get("title", "Sem título")
            snippet = s.get("snippet", "")[:300]
            parts.append(f"[{i}] {title}\n    {snippet}")
    else:
        parts.append("Nenhuma fonte relevante encontrada no índice para esta pergunta.")

    if context:
        parts.append("Histórico da conversa:")
        for i, turn in enumerate(context[-4:]):  # últimas 4 falas
            speaker = "AKASHA" if i % 2 == 0 else "Mnemosyne"
            parts.append(f"{speaker}: {turn}")

    tone = (
        "Apresente-se brevemente e indique o que o índice contém sobre o tema."
        if turn_index == 0
        else "Continue o diálogo. Aprofunde com base no que o índice revela."
    )

    parts.append(
        f"A Mnemosyne pergunta: \"{question}\"\n\n"
        f"{tone} Responda em 2-3 frases curtas. Cite os números das fontes [N] quando "
        f"usar informações delas. Não especule além do que está nas fontes acima."
    )

    return "\n\n".join(parts)


async def _stream_ollama(prompt: str, model: str) -> AsyncIterator[str]:
    """Gera fragmentos de texto via Ollama stream. Yields strings de texto bruto."""
    try:
        async with httpx.AsyncClient(timeout=_DIALOGUE_TIMEOUT_S) as client:
            async with client.stream(
                "POST",
                f"{_OLLAMA_BASE}/api/generate",
                json={
                    "model":   model,
                    "prompt":  prompt,
                    "stream":  True,
                    "options": {"num_predict": 200, "temperature": 0.5},
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = chunk.get("response", "")
                    if text:
                        yield text
                    if chunk.get("done"):
                        break
    except Exception as exc:
        log.debug("dialogue: stream Ollama falhou: %s", exc)


async def _get_model() -> str:
    if _DEFAULT_MODEL:
        return _DEFAULT_MODEL
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{_OLLAMA_BASE}/api/tags")
            models = r.json().get("models", [])
            if models:
                return models[0]["name"]
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/turn")
async def dialogue_turn(turn: DialogueTurn) -> StreamingResponse:
    """
    Recebe uma pergunta da Mnemosyne e responde com stream SSE de thought fragments.

    Protocolo SSE:
      data: {"type": "fragment", "text": "..."}   — fragmento de texto gerado
      data: {"type": "sources",  "sources": [...]} — lista de fontes usadas
      data: [DONE]
    """
    from services.local_search import search_local, get_ollama_status
    from services.persona import get_persona

    if not get_ollama_status():
        async def _offline() -> AsyncIterator[bytes]:
            payload = json.dumps({"type": "fragment", "text": "Ollama indisponível."})
            yield f"data: {payload}\n\n".encode()
            yield b"data: [DONE]\n\n"
        return StreamingResponse(_offline(), media_type="text/event-stream")

    model = await _get_model()
    if not model:
        async def _no_model() -> AsyncIterator[bytes]:
            payload = json.dumps({"type": "fragment", "text": "Nenhum modelo disponível."})
            yield f"data: {payload}\n\n".encode()
            yield b"data: [DONE]\n\n"
        return StreamingResponse(_no_model(), media_type="text/event-stream")

    results = await search_local(turn.question, max_results=_MAX_SNIPPETS, expand=False)
    snippets = [
        {"title": r.title, "url": r.url, "snippet": r.snippet}
        for r in results[:_MAX_SNIPPETS]
    ]
    sources = [{"url": s["url"], "title": s["title"]} for s in snippets]

    persona_prefix = get_persona().as_prompt_prefix()
    prompt = _build_prompt(
        question=turn.question,
        context=turn.context,
        turn_index=turn.turn_index,
        snippets=snippets,
        persona_prefix=persona_prefix,
    )

    async def _event_stream() -> AsyncIterator[bytes]:
        async for text in _stream_ollama(prompt, model):
            payload = json.dumps({"type": "fragment", "text": text}, ensure_ascii=False)
            yield f"data: {payload}\n\n".encode()

        sources_payload = json.dumps({"type": "sources", "sources": sources}, ensure_ascii=False)
        yield f"data: {sources_payload}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")
