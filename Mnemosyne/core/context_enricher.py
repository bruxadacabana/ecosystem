"""
ContextEnricher — enriquece chunks indexados com um sumário contextual de 1-2 frases.

Rodada como tarefa P3 após a indexação básica de cada arquivo (opt-in via
AppConfig.enrichment_enabled, default False).

O sumário é gerado pelo LOGOS (X-Priority: 3 — baixa prioridade) e salvo como
metadado `context_summary` no ChromaDB. Na próxima reindexação, o sumário pode
ser prefixado ao chunk antes do embedding via `prefix_context_summary()`, melhorando
a qualidade da representação vetorial sem alterar o texto original.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import AppConfig

log = logging.getLogger("mnemosyne.context_enricher")

_ENRICH_PROMPT = (
    "Descreva em 1–2 frases onde este trecho se encaixa no documento "
    "e qual é o seu tema principal:\n\n{text}"
)

_MAX_TEXT_CHARS = 800   # truncar antes de enviar ao LOGOS
_MAX_TOKENS     = 80    # 1-2 frases são suficientes
_LOGOS_TIMEOUT  = 30.0  # timeout por chamada (P3 pode aguardar na fila)


class ContextEnricher:
    """
    Enriquece chunks do ChromaDB com sumários contextuais via LOGOS (P3).

    O enriquecimento é idempotente: chunks que já têm `context_summary` são
    ignorados. Erros (LOGOS offline, timeout) são capturados silenciosamente —
    nunca interrompem a indexação básica.

    Uso:
        enricher = ContextEnricher(config)
        n = enricher.enrich_file("/path/to/doc.md", vectorstore)
    """

    def __init__(self, config: "AppConfig") -> None:
        self._config = config

    def enrich_file(self, file_path: str, vectorstore: Any) -> int:
        """Enriquece chunks de um arquivo com context_summary.

        Retorna o número de chunks efetivamente enriquecidos (0 se
        enrichment_enabled=False, LOGOS offline, ou todos já enriquecidos).
        """
        if not self._config.enrichment_enabled:
            return 0

        try:
            result = vectorstore._collection.get(
                where={"source": {"$eq": file_path}}
            )
        except Exception as exc:
            log.debug("context_enricher: falha ao obter chunks de %s: %s", file_path, exc)
            return 0

        ids   = result.get("ids")       or []
        metas = result.get("metadatas") or []
        docs  = result.get("documents") or []

        if not ids:
            log.debug("context_enricher: nenhum chunk para %s", file_path)
            return 0

        enriched = 0
        for chunk_id, meta, text in zip(ids, metas, docs):
            if (meta or {}).get("context_summary"):
                continue  # já enriquecido

            t0 = time.monotonic()
            try:
                summary = self._call_logos(text or "")
            except Exception as exc:
                log.debug("context_enricher: _call_logos lançou exceção para %s: %s", chunk_id, exc)
                continue
            if not summary:
                continue

            ms = (time.monotonic() - t0) * 1000
            try:
                new_meta = dict(meta or {})
                new_meta["context_summary"] = summary
                vectorstore._collection.update(
                    ids=[chunk_id],
                    metadatas=[new_meta],
                )
                enriched += 1
                log.debug(
                    "context_enricher: chunk %s enriquecido em %.0fms",
                    chunk_id, ms,
                )
            except Exception as exc:
                log.debug(
                    "context_enricher: falha ao atualizar chunk %s: %s", chunk_id, exc
                )

        if enriched:
            log.info(
                "context_enricher: %d/%d chunks enriquecidos (%s)",
                enriched, len(ids), file_path,
            )
        return enriched

    def _call_logos(self, text: str) -> str:
        """Chama LOGOS (P3) para gerar context_summary de 1-2 frases.

        Retorna string vazia em caso de erro (LOGOS offline, timeout, etc.).
        """
        if not text.strip():
            return ""
        try:
            import httpx
            from ecosystem_client import get_inference_url as _giu
            base_url = _giu()
            prompt   = _ENRICH_PROMPT.format(text=text[:_MAX_TEXT_CHARS])
            resp = httpx.post(
                f"{base_url}/v1/chat/completions",
                json={
                    "model":       self._config.llm_model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      False,
                    "temperature": 0,
                    "max_tokens":  _MAX_TOKENS,
                },
                headers={"X-Priority": "3"},
                timeout=_LOGOS_TIMEOUT,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return content.strip()
        except Exception as exc:
            log.debug("context_enricher: LOGOS indisponível ou erro: %s", exc)
            return ""


def prefix_context_summary(chunk_text: str, context_summary: str) -> str:
    """Prefixa o sumário contextual ao texto do chunk antes do embedding.

    Quando presente, melhora a representação vetorial do chunk porque o
    embedding captura tanto o tema/posição (sumário) quanto o conteúdo.
    Usado na reindexação quando context_summary já existe no metadata.

    Retorna chunk_text inalterado se context_summary for vazio.
    """
    if not context_summary or not context_summary.strip():
        return chunk_text
    return f"[Contexto: {context_summary}]\n\n{chunk_text}"
