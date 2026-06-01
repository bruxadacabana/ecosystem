"""
AKASHA — Router de amizade (comunicação bidirecional AKASHA↔Mnemosyne).

Endpoints:
  POST /friendship/feedback  — recebe feedback de utilidade de URL da Mnemosyne
                               para gerar appraisal emocional e reforço de tópicos.

O fluxo AKASHA→Mnemosyne (notify_mnemosyne_insight) é fire-and-forget via
ecosystem.json — não precisa de endpoint REST neste lado.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger("akasha.friendship")

router = APIRouter(prefix="/friendship", tags=["friendship"])


class FeedbackPayload(BaseModel):
    url: str
    is_positive: bool


@router.post("/feedback", status_code=204)
async def receive_url_feedback(body: FeedbackPayload) -> None:
    """Recebe feedback de utilidade de URL da Mnemosyne.

    Quando a Mnemosyne aplica FAIR-RAG em um documento originalmente encontrado
    pelo AKASHA (URL http/https), notifica a AKASHA para gerar appraisal emocional.

    - is_positive=True  → gratificação: conteúdo foi útil para a Mnemosyne.
    - is_positive=False → vigilância: conteúdo não foi útil.

    Falha silenciosamente — retorna 204 mesmo se o appraisal não puder ser gerado.
    """
    log.info(
        "friendship.feedback: url='%s' is_positive=%s",
        body.url[:100], body.is_positive,
    )
    try:
        from services.knowledge_worker import on_url_feedback as _on_feedback
        _on_feedback(body.url, body.is_positive)
    except Exception as exc:
        log.debug("friendship.feedback: on_url_feedback falhou: %s", exc)
