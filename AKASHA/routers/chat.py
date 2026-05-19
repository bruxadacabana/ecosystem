"""
AKASHA — Chat direto via RAG sobre page_knowledge e local_fts.

GET  /chat            → renderiza chat.html
POST /chat/message    → SSE stream stateless (sem histórico persistido)

O AKASHA responde com personalidade e ancora respostas factuais nas fontes
do índice. Conversação casual (saudações etc.) é tratada naturalmente.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config as _config

log = logging.getLogger("akasha.chat")

router = APIRouter(prefix="/chat", tags=["chat"])

_BASE_DIR   = Path(__file__).parent.parent
templates   = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

_MAX_SNIPPETS = 5

# Resolução LOGOS-first em runtime (não import-time)
def _get_base() -> str:
    try:
        from ecosystem_client import get_ollama_url as _u
        return _u()
    except Exception:
        return "http://localhost:11434"


def _get_headers() -> "dict[str, str]":
    try:
        from ecosystem_client import get_ollama_headers as _h
        return _h("akasha", 1)
    except Exception:
        return {}

# Padrões de nome que identificam modelos de embedding (não geração de texto).
# Usados para filtrar o fallback automático de _get_model().
_EMBED_NAME_PATTERNS = ("embed", "minilm", "nomic", "bge-", "e5-", "all-mini")

_CHAT_TIMEOUT_S = 60.0

# Cache do modelo para não requerir Ollama a cada mensagem
_cached_model: str = ""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_model() -> str:
    """Retorna o modelo configurado para chat ou o primeiro modelo generativo disponível.

    Filtra modelos de embedding (minilm, nomic, bge...) que não servem para geração
    de texto — tentar usá-los para chat trava o stream sem retornar nada.

    Resultado cacheado em _cached_model para evitar round-trip ao Ollama a cada mensagem.
    """
    global _cached_model
    if _cached_model:
        return _cached_model

    try:
        from ecosystem_client import get_active_profile as _gp
        p = _gp()
        configured = (p or {}).get("models", {}).get("llm_query", "") if p else ""
        if configured:
            _cached_model = configured
            return configured
    except Exception:
        pass

    # Fallback: usa primeiro modelo generativo disponível no Ollama
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{_get_base()}/api/tags")
            for m in r.json().get("models", []):
                name = m["name"].lower()
                if not any(pat in name for pat in _EMBED_NAME_PATTERNS):
                    _cached_model = m["name"]
                    return m["name"]
    except Exception:
        pass
    return ""


def _build_prompt(
    question: str,
    snippets: list[dict],
    persona_prefix: str,
) -> list[dict]:
    """Monta messages list para Ollama /api/chat."""
    parts = [_config.PERSONALITY_PROMPT]
    if persona_prefix:
        parts.append(persona_prefix.rstrip())

    if snippets:
        refs = "\n\n".join(
            f"[{i+1}] {s['title']}\n{s['snippet'][:350]}"
            for i, s in enumerate(snippets)
        )
        parts.append(f"Fontes encontradas no índice:\n{refs}")

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(parts)}]
    messages.append({"role": "user", "content": question})
    return messages


async def _stream_chat(messages: list[dict], model: str) -> AsyncIterator[str]:
    """Gera fragmentos de texto via Ollama /api/chat stream."""
    try:
        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT_S) as client:
            async with client.stream(
                "POST",
                f"{_get_base()}/api/chat",
                headers=_get_headers(),
                json={"model": model, "messages": messages, "stream": True,
                      "options": {"num_predict": 400, "temperature": 0.4, "repeat_penalty": 1.1}},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = chunk.get("message", {}).get("content", "")
                    if text:
                        yield text
                    if chunk.get("done"):
                        break
    except Exception as exc:
        log.warning("chat: stream Ollama falhou: %s", exc)
        yield f"[Erro ao conectar com Ollama: {exc}]"


def _trim_partial(text: str, tag: str) -> int:
    """Índice até onde é seguro emitir sem cortar uma tag parcial no final do buffer."""
    for i in range(len(tag) - 1, 0, -1):
        if text.endswith(tag[:i]):
            return max(0, len(text) - i)
    return len(text)


async def _filter_thinking(
    source: AsyncIterator[str],
) -> AsyncIterator[tuple[str, str]]:
    """
    Separa blocos <think>…</think> do stream principal.
    Yielda (tipo, texto) onde tipo ∈ {'fragment', 'thinking'}.
    Funciona mesmo quando as tags são partidas entre chunks.
    """
    buf = ""
    in_think = False

    async for chunk in source:
        buf += chunk
        while True:
            if not in_think:
                idx = buf.find("<think>")
                if idx == -1:
                    safe = _trim_partial(buf, "<think>")
                    if safe:
                        yield ("fragment", buf[:safe])
                        buf = buf[safe:]
                    break
                if idx > 0:
                    yield ("fragment", buf[:idx])
                buf = buf[idx + len("<think>"):]
                in_think = True
            else:
                idx = buf.find("</think>")
                if idx == -1:
                    safe = _trim_partial(buf, "</think>")
                    if safe:
                        yield ("thinking", buf[:safe])
                        buf = buf[safe:]
                    break
                if idx > 0:
                    yield ("thinking", buf[:idx])
                buf = buf[idx + len("</think>"):]
                in_think = False

    if buf.strip():
        yield ("thinking" if in_think else "fragment", buf)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def chat_page(request: Request) -> Response:
    return templates.TemplateResponse(
        request,
        "chat.html",
        {"active_tab": "chat"},
    )


@router.post("/message")
async def chat_message(body: ChatMessage) -> StreamingResponse:
    """
    Recebe mensagem da usuária, executa pipeline RAG e retorna SSE stream.
    Stateless — sem histórico de conversa persistido.

    Protocolo SSE:
      data: {"type": "fragment", "text": "..."}
      data: {"type": "thinking", "text": "..."}
      data: {"type": "sources",  "sources": [...]}
      data: [DONE]
    """
    from services.local_search import search_local, get_ollama_status
    from services.persona import get_persona

    if not get_ollama_status():
        async def _offline() -> AsyncIterator[bytes]:
            yield 'data: {"type":"fragment","text":"Ollama indisponível."}\n\n'.encode()
            yield b"data: [DONE]\n\n"
        return StreamingResponse(_offline(), media_type="text/event-stream")

    model = await _get_model()
    if not model:
        async def _no_model() -> AsyncIterator[bytes]:
            yield 'data: {"type":"fragment","text":"Nenhum modelo disponível."}\n\n'.encode()
            yield b"data: [DONE]\n\n"
        return StreamingResponse(_no_model(), media_type="text/event-stream")

    # Pipeline RAG
    results = await search_local(body.message, max_results=_MAX_SNIPPETS, expand=False)

    snippets: list[dict] = [
        {"title": r.title, "url": r.url, "snippet": r.snippet or ""}
        for r in results[:_MAX_SNIPPETS]
    ]

    sources = [{"url": s["url"], "title": s["title"]} for s in snippets]
    persona_prefix = get_persona().as_prompt_prefix()
    messages = _build_prompt(body.message, snippets, persona_prefix)

    async def _event_stream() -> AsyncIterator[bytes]:
        async for typ, text in _filter_thinking(_stream_chat(messages, model)):
            payload = json.dumps({"type": typ, "text": text}, ensure_ascii=False)
            yield f"data: {payload}\n\n".encode()

        src_payload = json.dumps({"type": "sources", "sources": sources}, ensure_ascii=False)
        yield f"data: {src_payload}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.post("/clear")
async def chat_clear() -> dict:
    """Sem histórico persistido — apenas confirma para o cliente limpar o canvas."""
    return {"ok": True}
