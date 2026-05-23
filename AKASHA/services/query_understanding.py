"""
AKASHA — Query Understanding e gerenciamento de ciclo de vida do modelo LLM.

Responsabilidades:
  - pin_model() / release_model(): mantém o modelo em VRAM durante uma sessão
    de pesquisa ativa, eliminando o cold-start de 2–5 s por query.
  - Temporizador de inatividade: libera VRAM automaticamente após SESSION_IDLE_S
    segundos sem atividade.
  - classify_intent(): classifica a intenção da query em fact-seeking, exploratory
    ou navigational via chamada Ollama rápida (~200ms com modelo 3B Q4).

Integração:
  - routers/search.py chama pin_model() e classify_intent() no início de cada busca.
  - release_model() é chamado automaticamente pelo timer ou por endpoint explícito.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Literal

import httpx

log = logging.getLogger("akasha.query_understanding")

# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

IntentType = Literal["fact-seeking", "exploratory", "navigational"]

# Tipos para o classificador léxico (sem LLM) — AKASHA como ferramenta
IntentTypeLexical = Literal[
    "navigational", "informational", "exploratory",
    "visual", "weather", "translation", "video",
]

# ---------------------------------------------------------------------------
# Classificador léxico — sem LLM, usado pelo AKASHA ferramenta
# ---------------------------------------------------------------------------

_KNOWN_TLDS = frozenset({
    "com", "org", "net", "io", "dev", "edu", "gov", "br", "uk",
    "pt", "de", "fr", "es", "it", "ca", "au", "co",
})

_INFORMATIONAL_PREFIXES = (
    "o que é", "o que são", "o que foi", "o que estava", "o que era",
    "como funciona", "como fazer", "como se", "como é", "como eu",
    "por que", "porque", "por quê", "explique", "explica", "defina", "definição de",
    "what is", "what are", "what was", "what does", "what's",
    "how to", "how do", "how does", "how can", "how is",
    "why is", "why does", "why did", "explain", "definition of",
)

_VISUAL_TERMS = frozenset({
    "foto", "fotos", "imagem", "imagens", "image", "images",
    "photo", "photos", "logo", "logos", "ilustração", "ilustrações",
    "picture", "pictures", "screenshot", "wallpaper", "icon", "ícone",
    "diagrama", "diagram", "thumbnail",
})

_WEATHER_TERMS = frozenset({
    "tempo", "clima", "temperatura", "chuva", "previsão",
    "weather", "forecast", "rain", "snow", "hot", "cold",
    "humidity", "umidade", "vento", "wind", "sol", "nublado", "cloudy",
    "chuvoso", "ensolarado", "sunny",
})

# Tokens únicos de tradução (comparação por token_set)
_TRANSLATION_TOKENS = frozenset({
    "traduzir", "tradução", "translate", "translation",
})

# Frases de tradução (verificadas via substring, antes do check informacional
# porque algumas começam com prefixos como "como se")
_TRANSLATION_PHRASES = (
    "em inglês", "em português", "em espanhol", "em francês",
    "in english", "in portuguese", "in spanish", "in french",
    "como se diz", "como fala", "como escreve",
    "what is the translation", "how do you say",
)

_VIDEO_TERMS = frozenset({
    "vídeo", "video", "videos", "vídeos", "assistir", "watch",
    "youtube", "tutorial video", "stream", "streaming",
    "filme", "movie", "série", "series", "episódio", "episode",
})


def classify_intent_lexical(query: str) -> IntentTypeLexical:
    """Classifica intenção por regras léxicas — sem LLM, baixa latência.

    Prioridade (primeira correspondência ganha):
    1. URL ou token com TLD reconhecido (≤2 tokens) → navigational
    2. Frases de tradução (antes do check informacional — "como se diz" etc.) → translation
    3. Prefixo de pergunta → informational
    4. Termos visuais → visual
    5. Termos de clima → weather
    6. Token único de tradução → translation
    7. Termos de vídeo → video
    8. Default: ≤3 tokens → informational; ≥4 tokens → exploratory
    """
    q_lower = query.lower().strip()
    if not q_lower:
        return "exploratory"
    tokens = q_lower.split()
    token_set = set(tokens)

    # Regra 1: navigational
    if q_lower.startswith(("http://", "https://", "www.")):
        return "navigational"
    if len(tokens) <= 2:
        for tok in tokens:
            parts = tok.rstrip("/").split(".")
            if len(parts) >= 2 and parts[-1] in _KNOWN_TLDS and len(parts[0]) >= 2:
                return "navigational"

    # Regra 2: frases de tradução — antes do check informacional porque algumas
    # começam com prefixos como "como se", que disparariam informational primeiro
    for phrase in _TRANSLATION_PHRASES:
        if phrase in q_lower:
            return "translation"

    # Regra 3: informational
    for prefix in _INFORMATIONAL_PREFIXES:
        if q_lower.startswith(prefix):
            return "informational"

    # Regra 4: visual
    if token_set & _VISUAL_TERMS:
        return "visual"

    # Regra 5: weather
    if token_set & _WEATHER_TERMS:
        return "weather"

    # Regra 6: token único de tradução
    if token_set & _TRANSLATION_TOKENS:
        return "translation"

    # Regra 7: video
    if token_set & _VIDEO_TERMS:
        return "video"

    # Regra 8: default por tamanho
    return "informational" if len(tokens) <= 3 else "exploratory"


# ---------------------------------------------------------------------------
# Configuração (LLM — Akasha assistente)
# ---------------------------------------------------------------------------

SESSION_IDLE_S:        int   = 1800   # 30 min sem atividade → libera VRAM
INTENT_CLASSIFY_MODEL: str   = ""     # sobrescrito por ecosystem.json; vazio = usa DEFAULT_LLM_MODEL
INTENT_TIMEOUT_S:      float = 5.0   # timeout da classificação; fallback para "exploratory"

# Resolvidos em runtime (não import-time) via ecosystem_client.
# DEFAULT_LLM_MODEL ainda pode ser sobrescrito em runtime pelo chamador.
DEFAULT_LLM_MODEL: str = ""


def _get_base() -> str:
    try:
        from ecosystem_client import get_inference_url as _u
        return _u()
    except Exception:
        return "http://localhost:8080"


def _get_headers() -> "dict[str, str]":
    try:
        from ecosystem_client import get_ollama_headers as _h
        return _h("akasha", 2)  # P2: expansão de query é user-triggered, não imediata
    except Exception:
        return {}

# ---------------------------------------------------------------------------
# Reescrita conversacional — anáforas detectadas
# ---------------------------------------------------------------------------

_ANAPHORA_RE = re.compile(
    r"\b(isso|esse|essa|esses|essas|ele|ela|eles|elas|aquilo|aqueles|aquelas|"
    r"este|esta|estes|estas|daí|lá|ali|"
    r"this|that|it|they|them|those|these|here|there)\b",
    re.IGNORECASE,
)


def needs_rewrite(query: str) -> bool:
    """True se a query provavelmente precisa de reescrita conversacional.

    Critérios: muito curta (< 3 tokens) OU contém anáfora pt/en.
    """
    if len(query.split()) < 3:
        return True
    return bool(_ANAPHORA_RE.search(query))


async def rewrite_query(query: str, context: list[str], model: str = "") -> str:
    """Reescreve query anafórica ou curta como busca autônoma usando contexto da sessão.

    Retorna a query reescrita ou "" se não aplicável / falhou.
    Nunca levanta exceção — falha silenciosa usa query original.
    """
    model = model or INTENT_CLASSIFY_MODEL or DEFAULT_LLM_MODEL
    if not model or not context:
        return ""

    context_str = " → ".join(context[-3:])
    prompt = (
        f'Reescreva como busca independente e específica: "{query}"\n'
        f"Contexto recente: {context_str}\n"
        "Responda apenas com a busca reescrita. Uma linha, sem explicação."
    )
    try:
        async with httpx.AsyncClient(timeout=INTENT_TIMEOUT_S) as client:
            resp = await client.post(
                f"{_get_base()}/v1/chat/completions",
                headers=_get_headers(),
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  30,
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip().strip("\"'")
            if raw and len(raw) <= 200 and raw.lower() != query.lower():
                return raw
    except Exception as exc:
        log.debug("rewrite_query falhou (%s) — usando query original.", exc)
    return ""

# ---------------------------------------------------------------------------
# Clarificação seletiva
# ---------------------------------------------------------------------------

async def score_ambiguity(query: str, model: str = "") -> tuple[int, str]:
    """Avalia ambiguidade da query e gera pergunta de clarificação quando necessário.

    Score 1-4 (1=clara, 4=muito ambígua). Pergunta exibida apenas quando score ≥ 3.
    A pergunta deve ser específica sobre o atributo ambíguo — nunca genérica.
    Retorna (1, "") em qualquer falha. Nunca levanta exceção.
    """
    model = model or INTENT_CLASSIFY_MODEL or DEFAULT_LLM_MODEL
    if not model:
        return 1, ""

    prompt = (
        f'Query de busca: "{query}"\n\n'
        "Avalie a ambiguidade de 1 a 4:\n"
        "1 = clara (ex: 'capital do Brasil')\n"
        "2 = levemente ambígua\n"
        "3 = ambígua (ex: 'Java' — linguagem ou país?)\n"
        "4 = muito ambígua (ex: 'como funciona')\n\n"
        "Se score ≥ 3, escreva UMA pergunta específica sobre o atributo ambíguo.\n"
        "Formato obrigatório:\n"
        "SCORE: N\n"
        "PERGUNTA: texto (vazio se score < 3)"
    )
    try:
        async with httpx.AsyncClient(timeout=INTENT_TIMEOUT_S) as client:
            resp = await client.post(
                f"{_get_base()}/v1/chat/completions",
                headers=_get_headers(),
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  60,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()

        score = 1
        question = ""
        for line in raw.splitlines():
            u = line.upper()
            if u.startswith("SCORE:"):
                try:
                    score = max(1, min(4, int(line.split(":", 1)[1].strip())))
                except ValueError:
                    pass
            elif u.startswith("PERGUNTA:"):
                question = line.split(":", 1)[1].strip()

        return score, question if score >= 3 and question else ""
    except Exception as exc:
        log.debug("score_ambiguity falhou (%s).", exc)
        return 1, ""

# ---------------------------------------------------------------------------
# Síntese opcional de snippets
# ---------------------------------------------------------------------------

async def summarize_snippets(query: str, snippets: list[str], model: str = "") -> str:
    """Gera 1-2 parágrafos de orientação de leitura sobre os snippets recuperados.

    Nunca substitui os links — apenas orienta. Retorna "" em qualquer falha.
    Chamado apenas por ação explícita da usuária (botão), nunca automaticamente.
    """
    model = model or INTENT_CLASSIFY_MODEL or DEFAULT_LLM_MODEL
    if not model or not snippets:
        return ""

    _snips = [s[:300] for s in snippets[:8]]
    snips_text = "\n\n".join(f"[{i + 1}] {s}" for i, s in enumerate(_snips))

    prompt = (
        f'A usuária buscou por: "{query}"\n\n'
        f"Trechos recuperados:\n{snips_text}\n\n"
        "Escreva 1-2 parágrafos orientando a leitura — o que cada fonte aborda e como "
        "pode ajudar a responder a busca. Use [N] para referenciar os trechos. "
        "Não invente informações além dos trechos fornecidos. Responda em português."
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_get_base()}/v1/chat/completions",
                headers=_get_headers(),
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  300,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.debug("summarize_snippets falhou (%s).", exc)
        return ""


# ---------------------------------------------------------------------------
# Estado interno
# ---------------------------------------------------------------------------

_pinned_model:  str | None        = None
_idle_task:     asyncio.Task | None = None


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

async def pin_model(model: str = "") -> None:
    """Mantém o modelo em VRAM com keep_alive=-1.

    Idempotente: chamadas repetidas com o mesmo modelo apenas reiniciam o
    timer de inatividade. Se o modelo mudar, o anterior é liberado primeiro.

    O Ollama interpreta keep_alive=-1 como "nunca descarregar" — o modelo
    fica residente em VRAM até que release_model() seja chamado ou o processo
    do Ollama reinicie.
    """
    global _pinned_model, _idle_task

    model = model or DEFAULT_LLM_MODEL
    if not model:
        return

    if _pinned_model and _pinned_model != model:
        await release_model(_pinned_model)

    if _pinned_model != model:
        await _set_keep_alive(model, keep_alive=-1)
        _pinned_model = model
        log.debug("Modelo '%s' fixado em VRAM (keep_alive=-1).", model)

    _reset_idle_timer(model)


async def release_model(model: str = "") -> None:
    """Libera o modelo da VRAM com keep_alive=0."""
    global _pinned_model, _idle_task

    model = model or _pinned_model or DEFAULT_LLM_MODEL
    if not model:
        return

    if _idle_task and not _idle_task.done():
        _idle_task.cancel()
        _idle_task = None

    await _set_keep_alive(model, keep_alive=0)
    _pinned_model = None
    log.debug("Modelo '%s' liberado da VRAM (keep_alive=0).", model)


def get_pinned_model() -> str | None:
    """Retorna o modelo atualmente fixado em VRAM, ou None."""
    return _pinned_model


async def classify_intent(query: str, model: str = "") -> IntentType:
    """Classifica a intenção da query via Ollama em ~200ms.

    Retorna um de três tipos:
      - "navigational" — usuária quer um URL/página específica (ex: "github anthropic")
      - "fact-seeking" — usuária quer um dado factual pontual (ex: "capital do Brasil")
      - "exploratory" — usuária quer pesquisar um tema amplo (ex: "machine learning intro")

    O classificador age APENAS na camada de roteamento de busca — não sintetiza
    respostas nem interpreta resultados. Se Ollama não responder em INTENT_TIMEOUT_S
    segundos, retorna "exploratory" (comportamento padrão da busca) sem bloquear.

    Raises: nunca — todos os erros são absorvidos e retornam "exploratory".
    """
    model = model or INTENT_CLASSIFY_MODEL or DEFAULT_LLM_MODEL
    if not model:
        return "exploratory"

    prompt = (
        "Classify this search query into exactly one category:\n"
        "- navigational: looking for a specific website, URL, or known page\n"
        "- fact-seeking: looking for a specific fact, number, or quick answer\n"
        "- exploratory: researching a broad topic, concept, or idea\n\n"
        f'Query: "{query}"\n\n'
        "Answer with one word only: navigational, fact-seeking, or exploratory."
    )

    try:
        async with httpx.AsyncClient(timeout=INTENT_TIMEOUT_S) as client:
            resp = await client.post(
                f"{_get_base()}/v1/chat/completions",
                headers=_get_headers(),
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "max_tokens":  8,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip().lower()
    except (httpx.HTTPError, httpx.TimeoutException, KeyError, ValueError) as exc:
        log.debug("classify_intent falhou (%s) — usando 'exploratory'.", exc)
        return "exploratory"

    if "navigational" in raw:
        return "navigational"
    if "fact" in raw:
        return "fact-seeking"
    if "exploratory" in raw:
        return "exploratory"

    log.debug("classify_intent resposta inesperada %r — usando 'exploratory'.", raw)
    return "exploratory"


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

async def _set_keep_alive(model: str, keep_alive: int) -> None:
    """No-op: llama-server gerencia o ciclo de vida do modelo nativamente."""
    _ = model, keep_alive


def _reset_idle_timer(model: str) -> None:
    """Cancela o timer de inatividade existente e inicia um novo."""
    global _idle_task

    if _idle_task and not _idle_task.done():
        _idle_task.cancel()

    try:
        loop = asyncio.get_running_loop()
        _idle_task = loop.create_task(_idle_release(model))
    except RuntimeError:
        pass  # sem loop ativo — ignorar (testes síncronos)


async def _idle_release(model: str) -> None:
    """Libera o modelo após SESSION_IDLE_S de inatividade."""
    try:
        await asyncio.sleep(SESSION_IDLE_S)
        log.info(
            "Inatividade de %d min — liberando modelo '%s' da VRAM.",
            SESSION_IDLE_S // 60, model,
        )
        await release_model(model)
    except asyncio.CancelledError:
        pass  # timer reiniciado por nova atividade — normal
