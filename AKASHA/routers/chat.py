"""
AKASHA — Chat direto via RAG sobre page_knowledge e local_fts.

GET  /chat            → renderiza chat.html
POST /chat/message    → SSE stream com resposta ancorada em fontes reais

Regra invariável: se a pergunta não tem cobertura no índice, o AKASHA diz
que não sabe em vez de gerar texto não ancorado.

Histórico mantido em memória por session_id (cookie UUID). Não persiste
entre sessões — diferente da Mnemosyne cujos notebooks persistem.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Cookie, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

log = logging.getLogger("akasha.chat")

router = APIRouter(prefix="/chat", tags=["chat"])

_BASE_DIR   = Path(__file__).parent.parent
templates   = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

# Histórico em memória: {session_id: list[{role, content}]}
_sessions: dict[str, list[dict]] = {}
_MAX_HISTORY = 10   # últimas N mensagens enviadas ao LLM
_MAX_SNIPPETS = 5

# LOGOS-first
try:
    from ecosystem_client import get_ollama_url as _get_url, get_active_profile as _get_profile
    _OLLAMA_BASE: str = _get_url()
    _p = _get_profile()
    _DEFAULT_MODEL: str = (_p or {}).get("models", {}).get("llm_kosmos", "") if _p else ""
except Exception:
    _OLLAMA_BASE   = "http://localhost:11434"
    _DEFAULT_MODEL = ""

_CHAT_TIMEOUT_S = 60.0


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    message: str
    history: list[dict] = []   # [{role, content}] — enviado pelo cliente


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _build_prompt(
    question: str,
    snippets: list[dict],
    persona_prefix: str,
    history: list[dict],
) -> list[dict]:
    """Monta messages list para Ollama /api/chat."""
    system_parts = []
    if persona_prefix:
        system_parts.append(persona_prefix.rstrip())

    if snippets:
        refs = "\n\n".join(
            f"[{i+1}] {s['title']}\n{s['snippet'][:350]}"
            for i, s in enumerate(snippets)
        )
        system_parts.append(
            f"Fontes encontradas no índice:\n{refs}\n\n"
            "Responda APENAS com base nas fontes acima. "
            "Cite os números [N] quando usar informações delas. "
            "Se a pergunta não tiver cobertura nas fontes, diga claramente que não encontrou "
            "informação sobre isso no índice — nunca especule nem use conhecimento externo."
        )
    else:
        system_parts.append(
            "Nenhuma fonte relevante foi encontrada no índice para esta pergunta. "
            "Informe a usuária que não há cobertura sobre esse tema no índice do AKASHA. "
            "Não gere conteúdo fora das fontes indexadas."
        )

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(system_parts)}]
    for turn in history[-_MAX_HISTORY:]:
        role = turn.get("role", "user")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": turn.get("content", "")})
    messages.append({"role": "user", "content": question})
    return messages


async def _stream_chat(messages: list[dict], model: str) -> AsyncIterator[str]:
    """Gera fragmentos de texto via Ollama /api/chat stream."""
    try:
        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT_S) as client:
            async with client.stream(
                "POST",
                f"{_OLLAMA_BASE}/api/chat",
                json={"model": model, "messages": messages, "stream": True,
                      "options": {"num_predict": 400, "temperature": 0.4}},
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
        log.debug("chat: stream Ollama falhou: %s", exc)


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
async def chat_page(
    request: Request,
    chat_session: str | None = Cookie(default=None),
) -> Response:
    session_id = chat_session or str(uuid.uuid4())
    history = _sessions.get(session_id, [])
    resp = templates.TemplateResponse(
        request,
        "chat.html",
        {"active_tab": "chat", "history": history},
    )
    resp.set_cookie("chat_session", session_id, httponly=True, samesite="lax")
    return resp


@router.post("/message")
async def chat_message(
    body: ChatMessage,
    chat_session: str | None = Cookie(default=None),
) -> StreamingResponse:
    """
    Recebe mensagem da usuária, executa pipeline RAG e retorna SSE stream.

    Protocolo SSE:
      data: {"type": "fragment", "text": "..."}
      data: {"type": "sources",  "sources": [...]}
      data: [DONE]
    """
    from services.local_search import search_local, get_ollama_status
    from services.persona import get_persona
    import database as _db

    session_id = chat_session or str(uuid.uuid4())

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

    # Enriquece snippets com resumos do page_knowledge quando disponíveis
    urls = [r.url for r in results[:_MAX_SNIPPETS]]
    pk_batch = await _db.get_page_knowledge_batch(urls)
    snippets: list[dict] = []
    for r in results[:_MAX_SNIPPETS]:
        pk = pk_batch.get(r.url)
        snippet = pk.get("summary", r.snippet) if isinstance(pk, dict) and pk.get("summary") else r.snippet
        snippets.append({"title": r.title, "url": r.url, "snippet": snippet or ""})

    sources = [{"url": s["url"], "title": s["title"]} for s in snippets]
    persona_prefix = get_persona().as_prompt_prefix()
    messages = _build_prompt(body.message, snippets, persona_prefix, body.history)

    # Atualiza histórico em memória
    hist = _sessions.setdefault(session_id, [])
    hist.append({"role": "user", "content": body.message})
    if len(hist) > _MAX_HISTORY * 2:
        _sessions[session_id] = hist[-(  _MAX_HISTORY * 2):]

    assistant_buf: list[str] = []

    async def _event_stream() -> AsyncIterator[bytes]:
        async for typ, text in _filter_thinking(_stream_chat(messages, model)):
            if typ == "fragment":
                assistant_buf.append(text)
            payload = json.dumps({"type": typ, "text": text}, ensure_ascii=False)
            yield f"data: {payload}\n\n".encode()

        full_answer = "".join(assistant_buf)
        hist.append({"role": "assistant", "content": full_answer})

        src_payload = json.dumps({"type": "sources", "sources": sources}, ensure_ascii=False)
        yield f"data: {src_payload}\n\n".encode()
        yield b"data: [DONE]\n\n"

    resp = StreamingResponse(_event_stream(), media_type="text/event-stream")
    resp.set_cookie("chat_session", session_id, httponly=True, samesite="lax")
    return resp


@router.post("/clear")
async def chat_clear(chat_session: str | None = Cookie(default=None)) -> dict:
    """Limpa o histórico da sessão atual."""
    if chat_session and chat_session in _sessions:
        _sessions[chat_session] = []
    return {"ok": True}
