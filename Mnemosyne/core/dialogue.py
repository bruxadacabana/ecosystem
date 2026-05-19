"""
Mnemosyne — Orquestrador de diálogo inter-app com o AKASHA.

Executa até MAX_TURNS rodadas de "pensa em voz alta":
  ◇ Mnemosyne busca no vault e gera um thought fragment.
  ⬡ AKASHA recebe a pergunta, busca no índice e responde em stream SSE.

Comunicação com a GUI via callbacks (fragment_cb / sources_cb) — não usa sinais Qt
diretamente para manter o core independente de PySide6.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Literal

log = logging.getLogger("mnemosyne.dialogue")

Speaker    = Literal["mnemosyne", "akasha"]
FragmentCb = Callable[[Speaker, str], None]
SourcesCb  = Callable[[Speaker, list[dict]], None]
StopCheck  = Callable[[], bool]

MAX_TURNS         = 5
_SNIPPET_MAX_CHARS = 300
_FOLLOWUP_PREDICT  = 60


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _search_vault(vectorstore: Any, question: str, k: int = 3) -> list[dict]:
    """Busca RAG simples no vault. Retorna lista de {title, snippet}."""
    try:
        if hasattr(vectorstore, "stores") and vectorstore.stores:
            docs = vectorstore.stores[0][0].similarity_search(question, k=k)
        else:
            docs = vectorstore.similarity_search(question, k=k)
        return [
            {
                "title":   d.metadata.get("title", d.metadata.get("source", "")),
                "snippet": d.page_content[:_SNIPPET_MAX_CHARS],
            }
            for d in docs
        ]
    except Exception as exc:
        log.debug("dialogue: busca vault falhou: %s", exc)
        return []


def _build_mnemosyne_thought(question: str, snippets: list[dict], config: Any) -> str:
    """Gera thought fragment da Mnemosyne via LLM com base nos snippets do vault."""
    if not snippets:
        return ""
    context = "\n\n".join(
        f"[{i+1}] {s['title']}\n{s['snippet']}"
        for i, s in enumerate(snippets)
    )
    prompt = (
        f"Contexto do vault pessoal:\n{context}\n\n"
        f"Pergunta em análise: {question}\n\n"
        "Em 1-3 frases curtas, reflita sobre o que o vault revela sobre essa pergunta. "
        "Use 'Nas minhas notas' ou 'No vault' para referir-se ao conteúdo. "
        "Seja específica e concisa. Não repita a pergunta."
    )
    try:
        from ecosystem_client import request_llm as _request_llm  # type: ignore
        resp = _request_llm(
            [{"role": "user", "content": prompt}],
            app="mnemosyne",
            model=config.llm_model,
            priority=2,
            options={"num_predict": 120, "temperature": 0.5},
        )
        return resp.get("message", {}).get("content", "").strip()
    except Exception as exc:
        log.debug("dialogue: thought mnemosyne falhou: %s", exc)
        return ""


def _generate_followup(
    question: str,
    exchange: list[str],
    config: Any,
) -> str | None:
    """
    Gera pergunta de follow-up com base no diálogo até agora.
    Retorna None se o LLM disser que o tema está esgotado.
    """
    history = "\n".join(exchange[-6:])
    prompt = (
        f"Diálogo até agora:\n{history}\n\n"
        "Com base nesse diálogo, qual é a pergunta de aprofundamento mais interessante? "
        "Responda com UMA pergunta em português, sem prefácio. "
        "Se o tema estiver suficientemente explorado, responda apenas: ENCERRAR"
    )
    try:
        from ecosystem_client import request_llm as _request_llm  # type: ignore
        resp = _request_llm(
            [{"role": "user", "content": prompt}],
            app="mnemosyne",
            model=config.llm_model,
            priority=3,
            options={"num_predict": _FOLLOWUP_PREDICT, "temperature": 0.4},
        )
        text = resp.get("message", {}).get("content", "").strip()
        if not text or "ENCERRAR" in text.upper():
            return None
        return text
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def run_dialogue(
    question: str,
    vectorstore: Any,
    config: Any,
    fragment_cb: FragmentCb,
    sources_cb: SourcesCb,
    stop_check: StopCheck,
    max_turns: int = MAX_TURNS,
) -> None:
    """
    Executa o diálogo inter-app Mnemosyne ↔ AKASHA.

    Para cada turno:
      1. Mnemosyne busca no vault → gera ◇ thought fragment.
      2. AKASHA recebe a pergunta → responde em stream SSE (⬡ fragments).
      3. Gera pergunta de follow-up (LLM); encerra se retornar None.

    fragment_cb(speaker, text) — emitido para cada fragmento.
    sources_cb(speaker, sources) — emitido para cada lista de fontes.
    stop_check() — se retornar True, interrompe imediatamente.
    """
    from .akasha_client import AkashaClient
    from .errors import AkashaOfflineError, AkashaFetchError

    akasha = AkashaClient()
    akasha_available = akasha.is_available()

    exchange: list[str] = []
    current_question = question

    for turn in range(max_turns):
        if stop_check():
            break

        # ── Turno Mnemosyne ◇ ──────────────────────────────────────────
        snippets = _search_vault(vectorstore, current_question)
        mne_thought = _build_mnemosyne_thought(current_question, snippets, config)
        if mne_thought:
            fragment_cb("mnemosyne", mne_thought)
            exchange.append(mne_thought)
            if snippets:
                sources_cb("mnemosyne", [{"title": s["title"], "url": ""} for s in snippets])

        if stop_check():
            break

        # ── Turno AKASHA ⬡ ─────────────────────────────────────────────
        if akasha_available:
            akasha_buffer: list[str] = []
            akasha_sources: list[dict] = []

            def _frag(text: str) -> None:
                akasha_buffer.append(text)
                fragment_cb("akasha", text)

            def _srcs(sources: list[dict]) -> None:
                akasha_sources.extend(sources)
                if sources:
                    sources_cb("akasha", sources)

            try:
                akasha.dialogue_turn(
                    question=current_question,
                    context=exchange[-4:],
                    turn_index=turn,
                    fragment_cb=_frag,
                    sources_cb=_srcs,
                    stop_check=stop_check,
                )
                full_akasha = "".join(akasha_buffer)
                if full_akasha:
                    exchange.append(full_akasha)
            except (AkashaOfflineError, AkashaFetchError) as exc:
                log.debug("dialogue: AKASHA indisponível no turno %d: %s", turn, exc)
                akasha_available = False

        if stop_check():
            break

        # ── Decide follow-up ────────────────────────────────────────────
        if turn < max_turns - 1:
            followup = _generate_followup(current_question, exchange, config)
            if followup is None:
                break
            current_question = followup
        else:
            break
