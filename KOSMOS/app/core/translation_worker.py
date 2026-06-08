"""
translation_worker.py — TranslationWorker: QThread P3 para tradução de títulos.

Roda em background enquanto o KOSMOS está aberto, em paralelo com a análise. A cada
ciclo, pega um lote de artigos cujo título ainda não foi traduzido e cujo idioma
detectado difere do idioma alvo (Settings → default_translation_lang), traduz o
título via `translator.translate` (argos offline padrão; LOGOS opcional) e salva em
`title_translated`. Processa do mais novo para o mais antigo (newest-first).

Prioridade P3: background, não urgente. Tradução nunca bloqueia leitura/busca —
falhas são logadas e o artigo é re-tentado num ciclo futuro (após a pausa ociosa),
sem laço quente.
"""
from __future__ import annotations

import logging
import queue
import sqlite3

from PySide6.QtCore import QThread, Signal

from app.core.database import get_conn
from app.core.translator import translate

log = logging.getLogger("kosmos.translation_worker")

_BATCH_SIZE = 10          # nº de títulos traduzidos por ciclo
_IDLE_INTERVAL_SEC = 60   # pausa entre ciclos (interruptível)


def get_untranslated_titles(
    target_lang: str,
    limit: int = _BATCH_SIZE,
    conn: sqlite3.Connection | None = None,
) -> list[tuple[int, str, str]]:
    """Títulos ainda sem tradução cujo idioma detectado difere do alvo.

    Exclui: já traduzidos (`title_translated` não-nulo), título vazio, idioma
    desconhecido (`language_detected` nulo — não dá para traduzir com confiança) e
    artigos já no idioma alvo (sem necessidade). Ordena newest-first.

    Returns:
        Lista de (article_id, title, language_detected).
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT id, title, language_detected FROM articles
             WHERE title_translated IS NULL
               AND title IS NOT NULL AND title != ''
               AND language_detected IS NOT NULL
               AND language_detected != ?
             ORDER BY published_at DESC, id DESC
             LIMIT ?
            """,
            (target_lang, limit),
        ).fetchall()
        return [(r["id"], r["title"], r["language_detected"]) for r in rows]
    except sqlite3.Error as exc:
        log.error("translation_worker: falha ao consultar títulos pendentes: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()


def save_title_translation(
    article_id: int,
    translated: str,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Persiste o título traduzido. Retorna True em sucesso."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            "UPDATE articles SET title_translated = ? WHERE id = ?",
            (translated, article_id),
        )
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("translation_worker: falha ao salvar título traduzido (id=%d): %s", article_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


def get_article_for_translation(
    article_id: int,
    conn: sqlite3.Connection | None = None,
) -> tuple[str, str] | None:
    """Retorna (corpo, idioma_detectado) de um artigo para tradução sob demanda.

    Corpo = content_text (texto completo) com fallback para content_excerpt.
    Retorna None se o artigo não existir ou não tiver corpo.
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        row = _conn.execute(
            "SELECT content_text, content_excerpt, language_detected "
            "FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        log.error("translation_worker: falha ao ler artigo %d para tradução: %s", article_id, exc)
        return None
    finally:
        if should_close:
            _conn.close()
    if row is None:
        return None
    body = (row["content_text"] or row["content_excerpt"] or "").strip()
    if not body:
        return None
    return body, (row["language_detected"] or "")


def save_body_translation(
    article_id: int,
    translated: str,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Persiste a tradução do corpo em content_text_translated. True em sucesso."""
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        _conn.execute(
            "UPDATE articles SET content_text_translated = ? WHERE id = ?",
            (translated, article_id),
        )
        _conn.commit()
        return True
    except sqlite3.Error as exc:
        log.error("translation_worker: falha ao salvar corpo traduzido (id=%d): %s", article_id, exc)
        return False
    finally:
        if should_close:
            _conn.close()


class TranslationWorker(QThread):
    """QThread P3: traduz títulos de artigos em background, newest-first.

    Sinais:
        title_translated(int, str)   — (article_id, título traduzido) ao traduzir um
        article_translated(int, str) — (article_id, corpo traduzido) sob demanda (P2)
        cycle_done(int)              — nº de títulos traduzidos no ciclo
    """

    title_translated   = Signal(int, str)
    article_translated = Signal(int, str)
    cycle_done         = Signal(int)

    def __init__(self, target_lang: str, backend: str = "argos", parent=None):
        super().__init__(parent)
        self._target_lang: str = (target_lang or "").strip().lower()
        self._backend: str = backend or "argos"
        self._stop_flag: bool = False
        self._batch_size: int = _BATCH_SIZE
        self._idle_interval_sec: int = _IDLE_INTERVAL_SEC
        # Fila prioritária P2: tradução de corpo de artigo sob demanda (usuária pediu).
        self._priority_q: "queue.Queue[int]" = queue.Queue()

    def request_article_translation(self, article_id: int) -> None:
        """Enfileira tradução P2 do corpo de um artigo (botão 'Traduzir' no leitor)."""
        self._priority_q.put(article_id)
        log.info("Tradução de artigo P2 solicitada: id=%d.", article_id)

    def stop(self) -> None:
        """Solicita parada. Encerra após o item atual ou o próximo tick ocioso."""
        self._stop_flag = True
        log.info("TranslationWorker: parada solicitada.")

    def run(self) -> None:
        if not self._target_lang:
            log.info("TranslationWorker: sem idioma alvo configurado — worker não inicia.")
            return
        log.info(
            "TranslationWorker iniciado (alvo=%s, backend=%s, batch=%d, idle=%ds).",
            self._target_lang, self._backend, self._batch_size, self._idle_interval_sec,
        )
        self._stop_flag = False
        while not self._stop_flag:
            n = self._run_cycle()
            self.cycle_done.emit(n)
            # Pausa interruptível entre ciclos; acorda em stop ou novo pedido P2.
            for _ in range(self._idle_interval_sec):
                if self._stop_flag or not self._priority_q.empty():
                    break
                self.msleep(1000)
        log.info("TranslationWorker encerrado.")

    def _drain_priority(self) -> list[int]:
        """Esvazia a fila de pedidos P2 (tradução de corpo) sem bloquear."""
        items: list[int] = []
        while True:
            try:
                items.append(self._priority_q.get_nowait())
            except queue.Empty:
                break
        return items

    def _translate_article_body(self, article_id: int) -> bool:
        """Traduz o corpo de um artigo (P2) e salva content_text_translated."""
        info = get_article_for_translation(article_id)
        if info is None:
            return False
        body, src = info
        result = translate(
            body, self._target_lang, source_lang=src or None,
            backend=self._backend, priority=2,
        )
        if result and result.strip() and result.strip() != body.strip():
            if save_body_translation(article_id, result):
                self.article_translated.emit(article_id, result)
                return True
        return False

    def _run_cycle(self) -> int:
        """P2 (corpo sob demanda) primeiro, depois o lote P3 de títulos.

        Retorna o nº de itens traduzidos (corpos + títulos).
        """
        count = 0

        # 1. P2 — pedidos de tradução de corpo têm prioridade
        for article_id in self._drain_priority():
            if self._stop_flag:
                return count
            if self._translate_article_body(article_id):
                count += 1

        # 2. P3 — lote de títulos pendentes (newest-first)
        for article_id, title, src in get_untranslated_titles(self._target_lang, self._batch_size):
            if self._stop_flag:
                break
            # Preempção: atende pedidos P2 que chegaram durante o lote
            for p_id in self._drain_priority():
                if self._stop_flag:
                    return count
                if self._translate_article_body(p_id):
                    count += 1
            result = translate(
                title, self._target_lang, source_lang=src,
                backend=self._backend, priority=3,
            )
            # translate devolve o original quando origem == alvo (no-op) — não persistir igual.
            if result and result.strip() and result.strip() != title.strip():
                if save_title_translation(article_id, result):
                    self.title_translated.emit(article_id, result)
                    count += 1
        return count
