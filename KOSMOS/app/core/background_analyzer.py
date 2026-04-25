"""Pré-análise de artigos em background para o KOSMOS.

Mantém uma PriorityQueue thread-safe com dois níveis:
  _HIGH (0): artigo aberto pelo usuário — processado imediatamente (1 call)
  _LOW (10): artigos sem análise na fila — processados em lotes de até BATCH_SIZE

O worker fica aguardando itens na fila e os processa enquanto o app está
em execução, sem bloquear a UI.

Integração:
  - MainWindow cria e inicia o BackgroundAnalyzer no startup.
  - enqueue_background(ids) → chamado no startup e em cada feed_updated.
  - enqueue_high(id, title, content) → ReaderView chama quando abre artigo
    sem análise (prioridade máxima para o usuário não esperar).
  - Sinal article_analyzed(article_id, data) → MainWindow repassa para
    atualizações de UI (e.g. badges de tags no feed).
"""

from __future__ import annotations

import json
import logging
import queue
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, pyqtSignal

if TYPE_CHECKING:
    from app.core.feed_manager import FeedManager
    from app.utils.config import Config

log = logging.getLogger("kosmos.bg_analyzer")

_HIGH       = 0    # artigo aberto pelo usuário
_LOW        = 10   # pré-análise silenciosa
_BATCH_SIZE = 5    # artigos por call LLM no modo batch

# Sistema de instrução fixo — idêntico ao _AnalyzeWorker para aproveitar KV cache
_SYSTEM = (
    'Você é uma API JSON. Responda APENAS com JSON válido. '
    'O primeiro caractere deve ser "{".'
)


class BackgroundAnalyzer(QThread):
    """Worker de pré-análise em background.

    Sinais:
        article_analyzed(int, dict): emitido após análise bem-sucedida.
    """

    article_analyzed = pyqtSignal(int, dict)

    def __init__(self, fm: "FeedManager", config: "Config") -> None:
        super().__init__()
        self._fm      = fm
        self._config  = config
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._running = True

    # ------------------------------------------------------------------
    # API pública — enfileiramento
    # ------------------------------------------------------------------

    def enqueue_high(self, article_id: int, title: str, content: str) -> None:
        """Prioridade alta: artigo aberto pelo usuário, analisado imediatamente."""
        self._queue.put((_HIGH, article_id, title, content))

    def enqueue_background(self, article_ids: list[int]) -> None:
        """Prioridade baixa: enfileira IDs para pré-análise silenciosa."""
        for aid in article_ids:
            self._queue.put((_LOW, aid, None, None))

    def stop(self) -> None:
        self._running = False
        self._queue.put((_HIGH, -1, None, None))  # sentinela de parada

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    def run(self) -> None:
        while self._running:
            try:
                prio, article_id, title, content = self._queue.get(timeout=5)
            except queue.Empty:
                continue

            if article_id == -1:
                break

            if not self._ai_enabled():
                continue

            if prio == _HIGH:
                # Análise imediata — single call com JSON Schema
                if title is not None and content is not None:
                    self._analyze_single(article_id, title, content)
            else:
                # Modo batch: coleta até BATCH_SIZE artigos LOW da fila
                batch = [(article_id, None, None)]
                while len(batch) < _BATCH_SIZE:
                    try:
                        p2, aid2, t2, c2 = self._queue.get_nowait()
                        if aid2 == -1:
                            self._running = False
                            break
                        if p2 == _HIGH:
                            # Devolve item HIGH e processa o batch atual
                            self._queue.put((p2, aid2, t2, c2))
                            break
                        batch.append((aid2, t2, c2))
                    except queue.Empty:
                        break

                self._analyze_batch(batch)

    # ------------------------------------------------------------------
    # Análise individual (HIGH priority)
    # ------------------------------------------------------------------

    def _analyze_single(self, article_id: int, title: str, content: str) -> None:
        from app.core.ai_bridge import AiBridge, OllamaError
        from app.ui.views.reader_view import _AnalyzeWorker

        endpoint  = str(self._config.get("ai_endpoint", "http://localhost:11434"))
        gen_model = str(self._config.get("ai_gen_model", ""))
        num_ctx   = int(self._config.get("ai_num_ctx", 4096))
        bridge    = AiBridge(endpoint=endpoint, gen_model=gen_model)

        prompt = self._build_single_prompt(title, content)
        try:
            raw  = bridge.generate(
                prompt,
                system=_SYSTEM,
                json_schema=_AnalyzeWorker._JSON_SCHEMA,
                num_ctx=num_ctx,
                priority=1,  # P1 — interativo
            )
            data = json.loads(raw)
            if isinstance(data, dict):
                self._persist(article_id, data)
                self.article_analyzed.emit(article_id, data)
        except (OllamaError, json.JSONDecodeError, Exception) as exc:
            log.debug("Análise individual falhou (artigo %d): %s", article_id, exc)

    # ------------------------------------------------------------------
    # Análise em batch (LOW priority)
    # ------------------------------------------------------------------

    def _analyze_batch(self, batch: list[tuple[int, str | None, str | None]]) -> None:
        """Analisa até BATCH_SIZE artigos em um único call LLM.

        Economiza cold start do modelo: todos os artigos compartilham o mesmo
        system prompt e as instruções de análise. Requer num_ctx=8192.
        """
        from app.core.ai_bridge import AiBridge, OllamaError

        endpoint  = str(self._config.get("ai_endpoint", "http://localhost:11434"))
        gen_model = str(self._config.get("ai_gen_model", ""))
        bridge    = AiBridge(endpoint=endpoint, gen_model=gen_model)

        # Resolver artigos que vieram só com ID (sem title/content)
        resolved: list[tuple[int, str, str]] = []
        for article_id, title, content in batch:
            if title is None or content is None:
                article = self._fm.get_article(article_id)
                if article is None:
                    continue
                if article.ai_sentiment is not None and article.ai_clickbait is not None:
                    continue  # já analisado
                title   = article.title or ""
                content = self._extract_text(article)
            resolved.append((article_id, title, content))

        if not resolved:
            return

        if len(resolved) == 1:
            aid, t, c = resolved[0]
            self._analyze_single(aid, t, c)
            return

        # Prompt batch com artigos numerados
        prompt_parts = [
            f"## Artigo {idx}\nTítulo: {t}\n{c}"
            for idx, (_, t, c) in enumerate(resolved)
        ]
        n = len(resolved)
        batch_prompt = (
            f"Analise os {n} artigos abaixo e retorne um objeto JSON com as chaves "
            f"'0' a '{n - 1}', uma por artigo.\n\n"
            + "\n\n".join(prompt_parts)
            + "\n\nRegras (para cada artigo):\n"
            "- tags: 3 a 5 palavras-chave em letras minúsculas, no idioma do artigo\n"
            "- sentiment: -1.0 (muito negativo) até +1.0 (muito positivo)\n"
            "- clickbait: 0.0 (sem clickbait) até 1.0 (clickbait puro)\n"
            "- five_ws: respostas concisas (máximo 2 frases), no idioma do artigo\n"
            "- entities: nomes próprios mencionados (listas vazias se não houver)"
        )

        # Schema dinâmico com uma chave numérica por artigo
        item_schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
                "sentiment": {"type": "number"},
                "clickbait": {"type": "number"},
                "five_ws": {
                    "type": "object",
                    "properties": {
                        k: {"type": "string"} for k in ("who", "what", "when", "where", "why")
                    },
                    "required": ["who", "what", "when", "where", "why"],
                },
                "entities": {
                    "type": "object",
                    "properties": {
                        k: {"type": "array", "items": {"type": "string"}}
                        for k in ("people", "orgs", "places")
                    },
                    "required": ["people", "orgs", "places"],
                },
            },
            "required": ["tags", "sentiment", "clickbait", "five_ws", "entities"],
        }
        batch_schema: dict = {
            "type": "object",
            "properties": {str(i): item_schema for i in range(n)},
            "required": [str(i) for i in range(n)],
        }

        try:
            raw  = bridge.generate(
                batch_prompt,
                system=_SYSTEM,
                json_schema=batch_schema,
                num_ctx=8192,   # batch requer janela maior
                priority=3,     # P3 — background
            )
            data = json.loads(raw)
            if not isinstance(data, dict):
                return
            for idx, (article_id, _, _) in enumerate(resolved):
                item = data.get(str(idx))
                if isinstance(item, dict):
                    self._persist(article_id, item)
                    self.article_analyzed.emit(article_id, item)
        except (OllamaError, json.JSONDecodeError, Exception) as exc:
            log.debug("Análise batch falhou (%d artigos): %s", len(resolved), exc)
            # Fallback: tentar individualmente
            for article_id, title, content in resolved:
                self._analyze_single(article_id, title, content)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ai_enabled(self) -> bool:
        return (
            bool(self._config.get("ai_enabled", False))
            and bool(self._config.get("ai_gen_model", ""))
        )

    def _extract_text(self, article) -> str:
        raw = article.content_full or article.summary or ""
        try:
            from bs4 import BeautifulSoup
            text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
        except Exception:
            import re
            text = re.sub(r"<[^>]+>", " ", raw)
        # ~3 chars/token; usar num_ctx do config para o limite de contexto
        num_ctx = int(self._config.get("ai_num_ctx", 4096))
        return text[: num_ctx * 3]

    @staticmethod
    def _build_single_prompt(title: str, content: str) -> str:
        return (
            f"Analise este artigo.\n\n"
            f"Título: {title}\n\n"
            f"{content}\n\n"
            f"Regras:\n"
            f"- tags: 3 a 5 palavras-chave em letras minúsculas, no idioma do artigo\n"
            f"- sentiment: -1.0 (muito negativo) até +1.0 (muito positivo)\n"
            f"- clickbait: 0.0 (sem clickbait) até 1.0 (clickbait puro)\n"
            f"- five_ws: respostas concisas (máximo 2 frases), no idioma do artigo\n"
            f"- entities: nomes próprios de pessoas, organizações e lugares "
            f"(listas vazias se não houver)"
        )

    def _persist(self, article_id: int, data: dict) -> None:
        """Persiste análise no banco e atualiza campo ai_tags."""
        sentiment = data.get("sentiment")
        clickbait = data.get("clickbait")
        ws_data   = data.get("five_ws") or data.get("5ws")
        entities  = data.get("entities")
        tags      = data.get("tags", [])

        self._fm.save_ai_analysis(
            article_id=article_id,
            sentiment=(
                float(max(-1.0, min(1.0, float(sentiment))))
                if sentiment is not None else None
            ),
            clickbait=(
                float(max(0.0, min(1.0, float(clickbait))))
                if clickbait is not None else None
            ),
            five_ws=(
                json.dumps(ws_data, ensure_ascii=False)
                if isinstance(ws_data, dict) else None
            ),
            entities=(
                json.dumps(entities, ensure_ascii=False)
                if isinstance(entities, dict) else None
            ),
        )

        clean_tags = [str(t).strip().lower() for t in tags if str(t).strip()]
        if clean_tags:
            self._fm.save_ai_tags_json(article_id, clean_tags)
