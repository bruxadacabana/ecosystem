"""
logos_client.py — wrapper fino do KOSMOS sobre o LOGOS (via ecosystem_client).

Toda análise AI do KOSMOS passa por aqui. Reusa `ecosystem_client.request_llm`
(mesma convenção do translator.py) — nunca fala HTTP direto com o llama-server;
os headers obrigatórios `X-App: kosmos` e `X-Priority: 1|2|3` são postos pelo
próprio `request_llm`, e o modelo (`llm_analysis`) é resolvido do perfil ativo
do LOGOS quando `model=None`.

Graceful fallback: quando o LOGOS está offline (HUB fechado) ou rejeita (429),
`chat()` levanta `LogosUnavailable` — o caller (AnalysisWorker, Fase 4) deixa o
artigo na fila `pending` e tenta de novo depois, sem travar. P3 não é bloqueado
pelo LOGOS, apenas atrasado (gerenciado do lado do LOGOS).
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("kosmos.logos_client")


class LogosUnavailable(RuntimeError):
    """LOGOS offline/indisponível ou rejeitou a chamada — manter artigo pendente."""


def is_available() -> bool:
    """True se o LOGOS responde (HUB aberto e IA ligada). Nunca levanta."""
    try:
        import ecosystem_client as _ec
        return _ec.logos_status() is not None
    except Exception as exc:  # qualquer falha = indisponível, mas sempre logado
        log.debug("logos_client.is_available: LOGOS inacessível: %s", exc)
        return False


def get_analysis_model() -> str:
    """Modelo de análise (`llm_analysis`) do perfil ativo do LOGOS.

    Cai no fallback por hardware quando o LOGOS está offline — mesma lógica que o
    `request_llm` aplica internamente. Retorna "" se nem o fallback resolver.
    """
    try:
        import ecosystem_client as _ec
        profile = _ec.get_active_profile()
        if profile:
            model = (profile.get("models") or {}).get("llm_analysis")
            if model:
                return model
        return _ec._fallback_model_for_app("kosmos")
    except Exception as exc:
        log.warning("logos_client.get_analysis_model: não resolveu modelo: %s", exc)
        return ""


def chat(
    messages: "list[dict[str, Any]]",
    *,
    priority: int,
    model: "str | None" = None,
    temperature: float = 0.3,
    max_tokens: "int | None" = None,
) -> str:
    """Envia chat ao LOGOS e devolve o conteúdo textual da resposta.

    priority: 1 (artigo aberto pela usuária), 2 (on-demand), 3 (pré-análise BG).
    `model=None` → o LOGOS resolve `llm_analysis` do perfil ativo.
    temperature baixa (0.3) por padrão: análise é extração estruturada, não criação.

    Raises:
        LogosUnavailable: LOGOS offline, rejeitou (429) ou devolveu resposta vazia.
    """
    import ecosystem_client as _ec

    opts: dict[str, Any] = {"temperature": temperature}
    if max_tokens is not None:
        opts["max_tokens"] = max_tokens

    log.debug("logos_client.chat: prio=%s model=%s msgs=%d", priority, model or "auto", len(messages))
    try:
        resp = _ec.request_llm(messages, app="kosmos", model=model, priority=priority, **opts)
    except RuntimeError as exc:
        log.warning("logos_client.chat: LOGOS indisponível (prio=%s): %s", priority, exc)
        raise LogosUnavailable(str(exc)) from exc

    choices = resp.get("choices") or []
    content = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
    if not content:
        log.warning("logos_client.chat: resposta vazia do LOGOS (prio=%s)", priority)
        raise LogosUnavailable("LOGOS retornou resposta vazia")
    log.debug("logos_client.chat: resposta OK (%d chars, prio=%s)", len(content), priority)
    return content
