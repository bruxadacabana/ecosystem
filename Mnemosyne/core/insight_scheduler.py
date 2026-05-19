"""
Mnemosyne — Agendador de insights espontâneos.

Decide quando e qual insight da personal_memory deve ser exibido
como pop-up para a usuária. Não é um QThread — é um QObject com
sinais, chamado do MainWindow após IndexReflectionWorker.finished.

Critérios para disparar:
  - Cooldown mínimo de COOLDOWN_SECONDS entre pop-ups (padrão: 10 min).
  - Entrada não exibida ainda nesta sessão (rastreado por ID).
  - Conteúdo com ≥ MIN_CONTENT_LEN chars.

Após exibir, também envia o pensamento para a AKASHA via notify_akasha_insight,
com cooldown próprio de 2h (independente do cooldown do popup).
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

log = logging.getLogger("mnemosyne.insight_scheduler")

COOLDOWN_SECONDS: float        = 600.0    # 10 min entre pop-ups
MIN_CONTENT_LEN: int           = 20       # descarta memórias muito curtas
_SEND_TO_AKASHA_COOLDOWN: float = 7200.0  # 2h entre envios para a AKASHA


class InsightScheduler(QObject):
    """Avalia se um insight deve ser exibido e emite o sinal quando sim.

    Usa a coluna `shown_as_popup` da personal_memory para rastrear
    entradas já exibidas — persiste entre sessões (não in-memory).

    Após exibir, compartilha o pensamento com a AKASHA como "visita"
    (cooldown de 2h, independente do popup de 10min).

    Uso:
        scheduler = InsightScheduler(parent=self)
        scheduler.insight_ready.connect(self._show_insight_popup)
        worker.finished.connect(scheduler.maybe_show)
    """

    insight_ready = Signal(str, int)  # (content, memory_id)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._last_shown: float          = 0.0
        self._last_sent_to_akasha: float = 0.0

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
            from core.personal_memory import get_unshown_popup_entries
            entries = get_unshown_popup_entries(5)
        except Exception as exc:
            log.debug("InsightScheduler: erro ao ler memórias: %s", exc)
            return

        candidate: dict | None = None
        for entry in entries:
            content = entry.get("content", "")
            if len(content) >= MIN_CONTENT_LEN:
                candidate = entry
                break

        if candidate is None:
            log.debug("InsightScheduler: nenhuma entrada nova para exibir")
            return

        mid = int(candidate["id"])
        self._last_shown = now
        try:
            from core.personal_memory import mark_shown_as_popup
            mark_shown_as_popup(mid)
        except Exception as exc:
            log.debug("InsightScheduler: erro ao marcar shown: %s", exc)

        self._maybe_send_to_akasha(candidate["content"])
        log.info("InsightScheduler: emitindo insight id=%d", mid)
        self.insight_ready.emit(candidate["content"], mid)

    def _maybe_send_to_akasha(self, content: str) -> None:
        """Envia pensamento para a AKASHA se o cooldown de 2h tiver passado."""
        now = time.monotonic()
        if now - self._last_sent_to_akasha < _SEND_TO_AKASHA_COOLDOWN:
            log.debug("InsightScheduler: cooldown AKASHA ativo, não enviando.")
            return
        self._last_sent_to_akasha = now
        try:
            root = str(Path(__file__).parent.parent.parent)
            if root not in sys.path:
                sys.path.insert(0, root)
            from ecosystem_client import notify_akasha_insight  # type: ignore
            notify_akasha_insight(content, tags=["from_mnemosyne"])
            log.info("InsightScheduler: pensamento enviado para AKASHA.")
        except Exception as exc:
            log.debug("InsightScheduler: falha ao notificar AKASHA: %s", exc)

    def reset_cooldown(self) -> None:
        """Reseta o cooldown — útil para testes ou forçar exibição."""
        self._last_shown = 0.0
