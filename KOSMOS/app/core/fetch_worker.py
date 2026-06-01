"""
fetch_worker.py — FetchWorker: QThread P2 para busca periódica de feeds.

Roda em background enquanto o KOSMOS está aberto. A cada ciclo:
  1. Consulta o banco por feeds habilitados com intervalo vencido.
  2. Chama feed_fetcher.fetch_and_save() para cada feed vencido.
  3. Emite sinais de progresso para a GUI atualizar contadores.

Prioridade P2: importante, mas não crítica. O fetch de feeds é I/O de rede
simples — não passa pelo LOGOS (sem LLM envolvido aqui).

O sleep entre ciclos é interruptível: verifica _stop_flag a cada 1s para
responder a stop() sem esperar o intervalo completo.
"""
from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import QThread, Signal

from app.core.database import get_conn
from app.core.feed_fetcher import fetch_and_save

log = logging.getLogger("kosmos.fetch_worker")

_POLL_INTERVAL_SEC = 60  # intervalo entre ciclos de verificação


def get_due_feeds(conn: sqlite3.Connection | None = None) -> list[tuple[int, str]]:
    """Retorna feeds habilitados cujo intervalo de fetch já venceu.

    Um feed está vencido quando:
    - nunca foi buscado (last_fetched_at IS NULL), ou
    - o tempo decorrido desde o último fetch >= fetch_interval_min.

    Feeds nunca buscados têm prioridade (NULL primeiro), depois os mais
    antigos. Em caso de erro no banco, retorna lista vazia (não lança).

    Args:
        conn: conexão existente (usada em testes); None → cria e fecha própria.

    Returns:
        Lista de (feed_id, feed_url) em ordem de prioridade.
    """
    _conn = conn if conn is not None else get_conn()
    should_close = conn is None
    try:
        rows = _conn.execute(
            """
            SELECT id, url FROM feeds
             WHERE enabled = 1
               AND (
                     last_fetched_at IS NULL
                     OR CAST(strftime('%s', 'now') AS INTEGER)
                        - CAST(strftime('%s', last_fetched_at) AS INTEGER)
                        >= fetch_interval_min * 60
                   )
             ORDER BY last_fetched_at IS NOT NULL, last_fetched_at ASC
            """
        ).fetchall()
        return [(row["id"], row["url"]) for row in rows]
    except sqlite3.Error as exc:
        log.error("Falha ao consultar feeds vencidos: %s", exc)
        return []
    finally:
        if should_close:
            _conn.close()


class FetchWorker(QThread):
    """QThread P2: busca periódica de todos os feeds habilitados.

    Sinais:
        feed_started(int)    — feed_id cujo fetch foi iniciado
        feed_done(int, int)  — (feed_id, novos_artigos) após fetch bem-sucedido
        feed_error(int, str) — (feed_id, msg) após falha irrecuperável
        cycle_done(int)      — total de novos artigos ao fim do ciclo
    """

    feed_started = Signal(int)
    feed_done    = Signal(int, int)
    feed_error   = Signal(int, str)
    cycle_done   = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_flag: bool = False
        self._poll_interval_sec: int = _POLL_INTERVAL_SEC

    def stop(self) -> None:
        """Solicita parada. O worker encerra após o ciclo atual ou o próximo tick."""
        self._stop_flag = True
        log.info("FetchWorker: parada solicitada.")

    def run(self) -> None:
        """Loop principal: ciclo de fetch → pausa interruptível → repete."""
        log.info("FetchWorker iniciado (poll=%ds).", self._poll_interval_sec)
        self._stop_flag = False
        while not self._stop_flag:
            total = self._run_cycle()
            self.cycle_done.emit(total)
            for _ in range(self._poll_interval_sec):
                if self._stop_flag:
                    break
                self.msleep(1000)
        log.info("FetchWorker encerrado.")

    def _run_cycle(self) -> int:
        """Busca todos os feeds vencidos. Retorna total de artigos novos."""
        due = get_due_feeds()
        if not due:
            log.debug("Nenhum feed vencido neste ciclo.")
            return 0

        log.info("Ciclo: %d feed(s) vencido(s).", len(due))
        total = 0
        for feed_id, feed_url in due:
            if self._stop_flag:
                log.debug("Ciclo interrompido por stop_flag.")
                break
            self.feed_started.emit(feed_id)
            count = fetch_and_save(feed_id, feed_url)
            if count >= 0:
                self.feed_done.emit(feed_id, count)
                total += count
            else:
                self.feed_error.emit(feed_id, f"Falha ao buscar feed {feed_id}")
        return total
