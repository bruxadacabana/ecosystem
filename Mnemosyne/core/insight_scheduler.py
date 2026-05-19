"""
Mnemosyne — Agendador de insights espontâneos.

Decide quando e qual insight da personal_memory deve ser exibido
como pop-up para a usuária. Não é um QThread — é um QObject com
sinais, chamado do MainWindow após IndexReflectionWorker.finished.

Critérios para disparar:
  - Cooldown mínimo de COOLDOWN_SECONDS entre pop-ups (padrão: 10 min).
  - Entrada não exibida ainda nesta sessão (rastreado por ID).
  - Conteúdo com ≥ MIN_CONTENT_LEN chars.
"""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, Signal

log = logging.getLogger("mnemosyne.insight_scheduler")

COOLDOWN_SECONDS: float = 600.0   # 10 min entre pop-ups
MIN_CONTENT_LEN: int = 20          # descarta memórias muito curtas


class InsightScheduler(QObject):
    """Avalia se um insight deve ser exibido e emite o sinal quando sim.

    Uso:
        scheduler = InsightScheduler(parent=self)
        scheduler.insight_ready.connect(self._show_insight_popup)
        # conectar ao finished do IndexReflectionWorker:
        worker.finished.connect(scheduler.maybe_show)
    """

    insight_ready = Signal(str, int)  # (content, memory_id)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._last_shown: float = 0.0
        self._shown_ids: set[int] = set()

    def maybe_show(self) -> None:
        """Verifica se deve mostrar um insight e emite insight_ready se sim.

        Deve ser chamado após IndexReflectionWorker.finished.
        Nunca propaga exceções — erros são logados silenciosamente.
        """
        now = time.monotonic()
        elapsed = now - self._last_shown
        if elapsed < COOLDOWN_SECONDS:
            log.debug(
                "InsightScheduler: cooldown ativo (%.0fs restantes)",
                COOLDOWN_SECONDS - elapsed,
            )
            return

        try:
            from core.personal_memory import get_recent
            entries = get_recent(5)
        except Exception as exc:
            log.debug("InsightScheduler: erro ao ler memórias: %s", exc)
            return

        candidate: dict | None = None
        for entry in entries:
            mid = int(entry.get("id") or 0)
            if mid in self._shown_ids:
                continue
            content = entry.get("content", "")
            if len(content) >= MIN_CONTENT_LEN:
                candidate = entry
                break

        if candidate is None:
            log.debug("InsightScheduler: nenhuma entrada nova para exibir")
            return

        mid = int(candidate["id"])
        self._last_shown = now
        self._shown_ids.add(mid)
        log.info("InsightScheduler: emitindo insight id=%d", mid)
        self.insight_ready.emit(candidate["content"], mid)

    def reset_cooldown(self) -> None:
        """Reseta o cooldown — útil para testes ou forçar exibição."""
        self._last_shown = 0.0
