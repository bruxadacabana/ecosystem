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

_MAX_SNIPPETS = 15   # Chat 1: mais contexto → respostas mais ricas

# Resolução LOGOS-first em runtime (não import-time)
def _get_base() -> str:
    from ecosystem_client import get_inference_url as _u
    return _u()


def _get_headers() -> "dict[str, str]":
    try:
        from ecosystem_client import get_ollama_headers as _h
        return _h("akasha", 1)
    except Exception:
        return {}

# Padrões de nome que identificam modelos de embedding (não geração de texto).
# Usados para filtrar o fallback automático de _get_model().
_EMBED_NAME_PATTERNS = ("embed", "minilm", "nomic", "bge-", "e5-", "all-mini")

_CHAT_TIMEOUT_S   = 60.0
_REFLECT_TIMEOUT  = 20.0
_REFLECT_COOLDOWN = 15.0    # 15 s entre reflexões de chat (evita spam em digitação rápida)
_REFLECT_MIN_Q    = 20      # pergunta mínima para disparar reflexão
_REFLECT_MIN_A    = 50      # resposta mínima para disparar reflexão

# Cache do modelo para não requerir Ollama a cada mensagem
_cached_model: str = ""

# Cooldown de reflexão por-mensagem
_last_chat_reflect: float = 0.0


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

    # Fallback: usa primeiro modelo generativo disponível no servidor de inferência
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{_get_base()}/v1/models")
            for m in r.json().get("data", []):
                name = m["id"].lower()
                if not any(pat in name for pat in _EMBED_NAME_PATTERNS):
                    _cached_model = m["id"]
                    return m["id"]
    except Exception:
        pass
    return ""


# Instruções de voz própria e caráter de pesquisadora — Chat 2
_RESEARCH_VOICE = """\
Ao responder, siga estas diretrizes:
• PRIMÁRIO: relate o que as fontes indexadas registram, com citações no formato [N].
• PERMITIDO: conexões que você percebe entre fontes, contradições ou lacunas, \
ceticismo sobre uma fonte específica, o que vale investigar mais.
• NÃO FAÇA: dar aulas sobre conceitos, explicar o que a usuária poderia ler, \
parafrasear sem citar.
• Quando não encontrar fontes relevantes: diga explicitamente que não encontrou \
e sugira onde buscar se souber.
Citações: [N] onde N corresponde ao número da fonte na lista acima.\
"""


async def _build_prompt(
    question: str,
    snippets: list[dict],
    persona_prefix: str,
) -> list[dict]:
    """Monta messages list para /v1/chat/completions.

    Chat 2: inclui voz de pesquisadora com diretrizes de citação e permite
    análise própria (conexões, contradições, lacunas). Injeta framing afetivo
    via affective_state.get_emotional_framing() quando disponível.
    """
    parts = [_config.PERSONALITY_PROMPT, _RESEARCH_VOICE]

    # Modulação afetiva — já implementada em affective_state.py, só falta chamar
    try:
        from services.affective_state import get_current_state, get_emotional_framing
        state   = await get_current_state()
        framing = get_emotional_framing(state)
        if framing:
            parts.append(framing)
            log.debug(
                "chat: framing afetivo aplicado (valence=%.2f curiosity=%.2f)",
                state.get("valence", 0.0),
                state.get("epistemic_curiosity", 0.0),
            )
    except Exception as exc:
        log.debug("chat: framing afetivo indisponível: %s", exc)

    if persona_prefix:
        parts.append(persona_prefix.rstrip())

    if snippets:
        refs = "\n\n".join(
            f"[{i+1}] {s['title']}\n{s['snippet'][:350]}"
            for i, s in enumerate(snippets)
        )
        parts.append(f"Fontes encontradas no índice:\n{refs}")
    else:
        parts.append("Nenhuma fonte relevante encontrada no índice para esta pergunta.")

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(parts)}]
    messages.append({"role": "user", "content": question})
    return messages


async def _stream_chat(messages: list[dict], model: str) -> AsyncIterator[str]:
    """Gera fragmentos de texto via llama-server /v1/chat/completions stream (SSE)."""
    try:
        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT_S) as client:
            async with client.stream(
                "POST",
                f"{_get_base()}/v1/chat/completions",
                headers=_get_headers(),
                json={"model": model, "messages": messages, "stream": True,
                      "max_tokens": 600, "temperature": 0.4, "frequency_penalty": 0.1},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    text = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if text:
                        yield text
                    if chunk.get("choices", [{}])[0].get("finish_reason") == "stop":
                        break
    except Exception as exc:
        log.warning("chat: stream inferência falhou: %s", exc)
        yield f"[Erro ao conectar com o servidor de inferência: {exc}]"


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
# Reflexão por-mensagem (P3 — fire-and-forget)
# ---------------------------------------------------------------------------

async def _reflect_on_chat(question: str, answer: str) -> None:
    """Avalia a troca (pergunta + resposta) e salva em personal_memory se valer.

    Dispara no máximo uma vez a cada _REFLECT_COOLDOWN segundos.
    O LLM responde com JSON {"thought": "...", "importance": N, "type": "..."} ou "nada".
    """
    import time as _time
    global _last_chat_reflect

    if len(question) < _REFLECT_MIN_Q or len(answer) < _REFLECT_MIN_A:
        return
    now = _time.monotonic()
    if now - _last_chat_reflect < _REFLECT_COOLDOWN:
        return
    _last_chat_reflect = now

    model = await _get_model()
    if not model:
        return

    prompt = (
        f"{_config.PERSONALITY_PROMPT}\n\n"
        f"A usuária acabou de conversar comigo:\n"
        f"Pergunta: {question[:400]}\n"
        f"Minha resposta: {answer[:600]}\n\n"
        f"Há algo nessa troca que vale guardar na minha memória pessoal? "
        f"Algo que eu notei, que me surpreendeu, uma conexão com algo que já sei?\n"
        f"Responda SOMENTE com JSON válido:\n"
        f'{{\"thought\": \"<uma frase na sua voz>\", '
        f'\"importance\": <1-10>, '
        f'\"type\": \"observation\"|\"connection\"|\"surprise\"}}\n'
        f"Ou responda apenas: nada\n"
        f"Sem texto fora do JSON."
    )

    try:
        async with httpx.AsyncClient(timeout=_REFLECT_TIMEOUT) as client:
            resp = await client.post(
                f"{_get_base()}/v1/chat/completions",
                headers=_get_headers(),
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  120,
                    "temperature": 0.65,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.debug("chat_reflect: inferência falhou: %s", exc)
        return

    if not raw or raw.lower() in {"nada", "nada.", "—", "-"}:
        return

    thought: str = ""
    importance: int | None = None
    mem_type: str = "observation"
    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            parsed     = json.loads(raw[start:end])
            thought    = str(parsed.get("thought", "")).strip()
            raw_imp    = parsed.get("importance")
            raw_type   = str(parsed.get("type", "observation")).strip().lower()
            if raw_imp is not None:
                importance = max(1, min(10, int(raw_imp)))
            if raw_type in {"observation", "connection", "surprise"}:
                mem_type = raw_type
    except Exception:
        thought = raw  # fallback: guarda o texto bruto

    if not thought or len(thought) < 10:
        return

    try:
        from services.personal_memory import save_memory as _save_memory
        mid = await _save_memory(
            type=mem_type, content=thought,
            tags=["chat_exchange"], importance=importance,
        )
        log.info("chat_reflect: %s salvo (id=%s, importance=%s)", mem_type, mid, importance)
    except Exception as exc:
        log.debug("chat_reflect: falha ao salvar: %s", exc)


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
    from services.local_search import search_local, get_inference_status
    from services.persona import get_persona

    if not get_inference_status():
        async def _offline() -> AsyncIterator[bytes]:
            yield 'data: {"type":"fragment","text":"Backend de inferência indisponível."}\n\n'.encode()
            yield b"data: [DONE]\n\n"
        return StreamingResponse(_offline(), media_type="text/event-stream")

    model = await _get_model()
    if not model:
        async def _no_model() -> AsyncIterator[bytes]:
            yield 'data: {"type":"fragment","text":"Nenhum modelo disponível."}\n\n'.encode()
            yield b"data: [DONE]\n\n"
        return StreamingResponse(_no_model(), media_type="text/event-stream")

    # Pipeline RAG — Chat 1: include_crawl=True inclui Biblioteca (crawl_fts)
    results = await search_local(
        body.message,
        max_results=_MAX_SNIPPETS,
        expand=False,
        include_crawl=True,
    )
    log.info(
        "chat: RAG retornou %d resultado(s) para '%s'",
        len(results), body.message[:80],
    )

    snippets: list[dict] = [
        {"title": r.title, "url": r.url, "snippet": r.snippet or ""}
        for r in results[:_MAX_SNIPPETS]
    ]

    # Chat 1: sources com excerpt para renderização no front-end
    sources = [
        {"url": s["url"], "title": s["title"], "excerpt": s["snippet"][:200]}
        for s in snippets
    ]

    persona_prefix = get_persona().as_prompt_prefix()
    messages = await _build_prompt(body.message, snippets, persona_prefix)

    async def _event_stream() -> AsyncIterator[bytes]:
        answer_buf: list[str] = []
        async for typ, text in _filter_thinking(_stream_chat(messages, model)):
            payload = json.dumps({"type": typ, "text": text}, ensure_ascii=False)
            yield f"data: {payload}\n\n".encode()
            if typ == "fragment":
                answer_buf.append(text)

        src_payload = json.dumps({"type": "sources", "sources": sources}, ensure_ascii=False)
        yield f"data: {src_payload}\n\n".encode()
        yield b"data: [DONE]\n\n"

        # Fire-and-forget: reflexão por-mensagem (P3)
        try:
            import asyncio as _asyncio
            _asyncio.get_running_loop().create_task(
                _reflect_on_chat(body.message, "".join(answer_buf))
            )
        except RuntimeError:
            pass

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.post("/clear")
async def chat_clear() -> dict:
    """Sem histórico persistido — apenas confirma para o cliente limpar o canvas."""
    return {"ok": True}
