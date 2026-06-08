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


class TranslationWorker(QThread):
    """QThread P3: traduz títulos de artigos em background, newest-first.

    Sinais:
        title_translated(int, str) — (article_id, título traduzido) ao traduzir um
        cycle_done(int)            — nº de títulos traduzidos no ciclo
    """

    title_translated = Signal(int, str)
    cycle_done       = Signal(int)

    def __init__(self, target_lang: str, backend: str = "argos", parent=None):
        super().__init__(parent)
        self._target_lang: str = (target_lang or "").strip().lower()
        self._backend: str = backend or "argos"
        self._stop_flag: bool = False
        self._batch_size: int = _BATCH_SIZE
        self._idle_interval_sec: int = _IDLE_INTERVAL_SEC

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
            # Pausa interruptível entre ciclos (não há laço quente em caso de falhas).
            for _ in range(self._idle_interval_sec):
                if self._stop_flag:
                    break
                self.msleep(1000)
        log.info("TranslationWorker encerrado.")

    def _run_cycle(self) -> int:
        """Traduz um lote de títulos pendentes. Retorna o nº traduzido."""
        batch = get_untranslated_titles(self._target_lang, self._batch_size)
        if not batch:
            return 0
        count = 0
        for article_id, title, src in batch:
            if self._stop_flag:
                break
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
