"""
Notebook Guide: gerado automaticamente após indexação.
Inclui resumo geral da coleção e 5 perguntas sugeridas sobre o conteúdo.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langchain_ollama import OllamaLLM

from .config import AppConfig
from .errors import GuideError, SummarizationError
from .rag import strip_think
from .summarizer import summarize_all


class GuideResult(TypedDict):
    summary: str
    questions: list[str]
    generated_at: str


_QUESTIONS_PROMPT = (
    "Com base nos trechos abaixo, formule 5 perguntas relevantes que um leitor "
    "poderia fazer sobre esta coleção de documentos. "
    "As perguntas devem cobrir aspectos diferentes do conteúdo. "
    "Escreva uma pergunta por linha, sem numeração e sem marcadores.\n\n"
    "Trechos:\n{context}\n\n"
    "Perguntas:"
)

_SAMPLE_K = 12
_SAMPLE_CHAR_CAP = 1_000


def _sample_context(vectorstore: Any) -> str:
    """Amostra representativa dos docs indexados para a geração de perguntas."""
    try:
        docs = vectorstore.similarity_search(
            "tema principal assunto conteúdo", k=_SAMPLE_K
        )
    except Exception as exc:
        raise GuideError(f"Falha ao amostrar vectorstore: {exc}") from exc

    seen: set[str] = set()
    parts: list[str] = []
    for doc in docs:
        src = doc.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            parts.append(doc.page_content[:_SAMPLE_CHAR_CAP])

    if not parts:
        raise GuideError("Nenhum documento encontrado para gerar o guide.")

    return "\n\n---\n".join(parts)


def _generate_questions(context: str, config: AppConfig) -> list[str]:
    """Gera até 5 perguntas sugeridas sobre o corpus."""
    try:
        llm = OllamaLLM(model=config.llm_model, temperature=0.4, timeout=60)
        raw = strip_think(llm.invoke(_QUESTIONS_PROMPT.format(context=context)))
    except Exception as exc:
        raise GuideError(f"Falha ao gerar perguntas: {exc}") from exc

    questions: list[str] = []
    for line in raw.splitlines():
        # Remove numeração, marcadores e espaços iniciais
        line = line.strip().lstrip("0123456789.-) \t")
        if line and len(line) > 10:
            questions.append(line)
        if len(questions) >= 5:
            break

    if not questions:
        raise GuideError("LLM não retornou perguntas válidas.")

    return questions


def generate_guide(vectorstore: Any, config: AppConfig) -> GuideResult:
    """
    Gera resumo geral da coleção + 5 perguntas sugeridas.

    Raises:
        GuideError: se qualquer etapa da geração falhar.
    """
    try:
        summary = summarize_all(vectorstore, config)
    except SummarizationError as exc:
        raise GuideError(f"Falha ao gerar resumo: {exc}") from exc

    context = _sample_context(vectorstore)
    questions = _generate_questions(context, config)

    return GuideResult(
        summary=summary,
        questions=questions,
        generated_at=datetime.now().isoformat(),
    )


def save_guide(result: GuideResult, mnemosyne_dir: str) -> None:
    """
    Persiste GuideResult em .mnemosyne/guide.json.

    Raises:
        OSError: se a escrita falhar.
    """
    path = Path(mnemosyne_dir) / "guide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


def load_guide(mnemosyne_dir: str) -> GuideResult | None:
    """
    Carrega guide.json se existir. Retorna None se não houver guide salvo.

    Raises:
        GuideError: se o arquivo existir mas for inválido.
    """
    path = Path(mnemosyne_dir) / "guide.json"
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return GuideResult(
            summary=str(data.get("summary", "")),
            questions=list(data.get("questions", [])),
            generated_at=str(data.get("generated_at", "")),
        )
    except (json.JSONDecodeError, KeyError) as exc:
        raise GuideError(f"guide.json inválido: {exc}") from exc
