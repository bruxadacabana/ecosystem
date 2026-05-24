"""
Geração de flashcards (pares pergunta/resposta) a partir dos documentos indexados.

O LLM produz um array JSON com 12 pares; iter_flashcards empacota o resultado em:
  {"cards": [{"id": str, "front": str, "back": str}, ...], "progress": {id: "unseen"}}

O campo "progress" é atualizado em runtime pelo FlashcardsDialog e re-persistido via
StudioStore — o estudo progride entre sessões sem re-gerar os cards.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from .config import AppConfig

log = logging.getLogger("mnemosyne.flashcards")

_N_CARDS = 12
_RETRIEVAL_K = 20
_MAX_CONTEXT_CHARS = 8_000

_PROMPT = (
    "Com base nos documentos abaixo, crie {n} flashcards de estudo.\n"
    "Retorne APENAS um array JSON válido, sem texto extra antes ou depois.\n"
    'Formato: [{{"id": "1", "front": "Pergunta aqui", "back": "Resposta aqui"}}, ...]\n\n'
    "Regras:\n"
    "- Perguntas diretas e objetivas (1 linha)\n"
    "- Respostas concisas (1-3 frases)\n"
    "- Cobertura variada dos temas do corpus\n"
    "- Mesmo idioma dos documentos\n\n"
    "Documentos:\n{context}\n\n"
    "Array JSON:"
)


def iter_flashcards(vectorstore, config: "AppConfig") -> Iterator[str]:
    """Gera flashcards JSON a partir do corpus indexado.

    Yields:
        Um único chunk com o JSON final:
        {"cards": [...], "progress": {card_id: "unseen", ...}}

    Raises:
        Exception: se o corpus estiver vazio ou o LLM não retornar JSON válido.
    """
    from langchain_openai import ChatOpenAI
    from ecosystem_client import get_inference_url as _ec_url
    from .rag import strip_think

    docs = vectorstore.similarity_search("conceitos principais temas abordados", k=_RETRIEVAL_K)
    if not docs:
        raise Exception("Nenhum documento indexado. Indexe documentos antes de gerar flashcards.")

    # Monta contexto truncado
    parts: list[str] = []
    total = 0
    for doc in docs:
        text = doc.page_content.strip()
        if not text:
            continue
        remaining = _MAX_CONTEXT_CHARS - total
        if remaining <= 0:
            break
        parts.append(text[:remaining])
        total += len(parts[-1])

    context = "\n\n---\n\n".join(parts)
    prompt = _PROMPT.format(n=_N_CARDS, context=context)

    llm = ChatOpenAI(model=config.llm_model, base_url=f"{_ec_url()}/v1", api_key="logos", temperature=0.3, timeout=120)
    raw = ""
    for chunk in llm.stream(prompt):
        raw += chunk
    raw = strip_think(raw).strip()

    # Extrai o array JSON da resposta (ignora texto extra ao redor)
    start = raw.find("[")
    end   = raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise Exception("O modelo não retornou JSON válido. Tente novamente.")

    try:
        cards_raw: list = json.loads(raw[start:end])
        if not isinstance(cards_raw, list):
            raise ValueError("Esperado array JSON")
    except (json.JSONDecodeError, ValueError) as exc:
        raise Exception(f"Erro ao parsear flashcards: {exc}") from exc

    cards: list[dict] = []
    for i, card in enumerate(cards_raw):
        if not isinstance(card, dict):
            continue
        front = str(card.get("front", "")).strip()
        back  = str(card.get("back",  "")).strip()
        if front and back:
            cards.append({
                "id":    str(card.get("id", i + 1)),
                "front": front,
                "back":  back,
            })

    if not cards:
        raise Exception("O modelo retornou um array vazio. Tente novamente.")

    result = json.dumps(
        {"cards": cards, "progress": {c["id"]: "unseen" for c in cards}},
        ensure_ascii=False,
        indent=2,
    )
    yield result
