"""
Mnemosyne — FAQ Generator
Gera perguntas frequentes com respostas concisas a partir dos
documentos indexados no vectorstore.
"""
from __future__ import annotations

from typing import Generator, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from .config import AppConfig
from .rag import strip_think

# ── Prompts ───────────────────────────────────────────────────────────────────

_FAQ_SYSTEM = (
    "Você é Mnemosyne, um bibliotecário celeste especializado em extrair conhecimento. "
    "Analise os trechos fornecidos e gere perguntas frequentes (FAQ) com respostas concisas. "
    "Responda somente em português. Seja direto e factual."
)

_FAQ_PROMPT = """\
Com base nos trechos abaixo, gere {n} perguntas frequentes (FAQ) que um leitor \
provavelmente teria sobre este material.
Para cada pergunta, forneça uma resposta concisa baseada exclusivamente nos trechos.

Use exatamente este formato (sem numeração, sem marcadores extras):
PERGUNTA: <pergunta>
RESPOSTA: <resposta em 1-3 frases>

Trechos:
{context}
"""

# ── Tipos ─────────────────────────────────────────────────────────────────────

class FaqItem(TypedDict):
    question: str
    answer: str

# ── API pública ───────────────────────────────────────────────────────────────

def iter_faq(
    vectorstore,
    config: AppConfig,
    n_questions: int = 8,
    sample_k: int = 15,
) -> Generator[str, None, None]:
    """Gera FAQ com streaming token-a-token.

    Yields:
        Tokens de texto conforme o LLM os produz.

    Raises:
        ValueError: Se não houver documentos indexados.
        RuntimeError: Se o vectorstore não puder ser lido.
    """
    context = _build_context(vectorstore, sample_k)
    prompt  = _FAQ_PROMPT.format(n=n_questions, context=context)
    llm     = ChatOllama(model=config.llm_model, temperature=0)
    messages = [
        SystemMessage(content=_FAQ_SYSTEM),
        HumanMessage(content=prompt),
    ]
    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content


def generate_faq(
    vectorstore,
    config: AppConfig,
    n_questions: int = 8,
    sample_k: int = 15,
) -> list[FaqItem]:
    """Gera FAQ de forma síncrona.

    Returns:
        Lista de FaqItem(question, answer).

    Raises:
        ValueError: Se não houver documentos indexados.
        RuntimeError: Se o vectorstore não puder ser lido.
    """
    full = "".join(iter_faq(vectorstore, config, n_questions, sample_k))
    return parse_faq(strip_think(full))


# ── Helpers internos ──────────────────────────────────────────────────────────

def _build_context(vectorstore, sample_k: int) -> str:
    """Amostra uniforme de chunks do vectorstore."""
    try:
        raw  = vectorstore.get()
        docs = raw.get("documents", [])
    except Exception as exc:
        raise RuntimeError(f"Não foi possível acessar o vectorstore: {exc}") from exc

    if not docs:
        raise ValueError(
            "Nenhum documento indexado. Indexe documentos antes de gerar FAQ."
        )

    step   = max(1, len(docs) // sample_k)
    sample = docs[::step][:sample_k]
    return "\n\n---\n".join(chunk[:600] for chunk in sample)


def parse_faq(text: str) -> list[FaqItem]:
    """Parseia o texto no formato PERGUNTA:/RESPOSTA: em lista de FaqItem."""
    items: list[FaqItem] = []
    current_q: str | None = None
    current_a: list[str] = []
    in_answer = False

    for line in text.splitlines():
        stripped = line.strip()
        upper    = stripped.upper()

        if upper.startswith("PERGUNTA:"):
            if current_q is not None and current_a:
                items.append(
                    FaqItem(question=current_q, answer=" ".join(current_a).strip())
                )
            current_q = stripped[len("PERGUNTA:"):].strip()
            current_a = []
            in_answer  = False

        elif upper.startswith("RESPOSTA:"):
            current_a = [stripped[len("RESPOSTA:"):].strip()]
            in_answer  = True

        elif in_answer and stripped:
            current_a.append(stripped)

    # Último item
    if current_q is not None and current_a:
        items.append(
            FaqItem(question=current_q, answer=" ".join(current_a).strip())
        )

    return items
