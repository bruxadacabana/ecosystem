"""
Mnemosyne — Agendador de insights espontâneos.

Decide qual insight da personal_memory deve ser exibido como pop-up.
Não usa cooldown de tempo — o critério é simples: se não há popup ativo,
o próximo candidato de maior saliência (arousal × importance) é exibido.
Quando o popup fecha (qualquer motivo), verifica imediatamente se há outro.

Ao receber feedback (✓ / ✗), a Mnemosyne reflete sobre o que o feedback
diz sobre o seu julgamento — essa reflexão é salva em personal_memory e
afeta o contexto das próximas gerações.

Ao receber ✓, também envia o pensamento para a AKASHA como "visita".
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal

log = logging.getLogger("mnemosyne.insight_scheduler")

MIN_CONTENT_LEN: int = 20


class InsightScheduler(QObject):
    """Seleciona e emite insights por saliência; reage a feedback com reflexão.

    Uso:
        scheduler = InsightScheduler(parent=self)
        scheduler.insight_ready.connect(self._show_insight_popup)
        scheduler.reflection_requested.connect(self._on_reflection_requested)
        worker.finished.connect(scheduler.maybe_show)
        popup.confirmed.connect(scheduler.on_confirmed)
        popup.dismissed.connect(scheduler.on_dismissed)
        popup.destroyed.connect(scheduler.on_popup_closed)
    """

    insight_ready        = Signal(str, int)   # (content, memory_id)
    reflection_requested = Signal(int, str)   # (memory_id, "confirmed"|"dismissed")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._popup_active: bool = False

    def maybe_show(self) -> None:
        """Exibe o próximo insight de maior saliência, se não há popup ativo.

        Deve ser chamado após IndexReflectionWorker.finished.
        Nunca propaga exceções — erros são logados silenciosamente.
        """
        if self._popup_active:
            log.debug("InsightScheduler: popup já ativo — aguardando fechamento")
            return

        # G(e): arousal alto → adiar popup — evitar sobrecarga em momento de alta ativação
        try:
            from core.affective_state import get_current_state
            _st = get_current_state()
            _arousal = _st.get("episodic_arousal", 0.0)
            if _arousal > 0.6:
                log.debug(
                    "InsightScheduler: arousal=%.2f > 0.6 — popup adiado até estabilização",
                    _arousal,
                )
                return
        except Exception:
            pass

        try:
            from core.personal_memory import get_unshown_popup_entries
            entries = get_unshown_popup_entries(5)
        except Exception as exc:
            log.debug("InsightScheduler: erro ao ler memórias: %s", exc)
            return

        candidate: dict | None = None
        # K: câmara de eco → epsilon-greedy — 5% de chance de insight divergente (menor saliência)
        try:
            import random as _random
            from core.affective_state import detect_echo_chamber
            if detect_echo_chamber() and _random.random() < 0.05 and len(entries) > 1:
                for entry in reversed(entries):
                    if len(entry.get("content", "")) >= MIN_CONTENT_LEN:
                        candidate = entry
                        log.info(
                            "InsightScheduler: epsilon-greedy diversidade — id=%d",
                            entry["id"],
                        )
                        break
        except Exception:
            pass

        if candidate is None:
            for entry in entries:
                if len(entry.get("content", "")) >= MIN_CONTENT_LEN:
                    candidate = entry
                    break

        if candidate is None:
            log.debug("InsightScheduler: nenhuma entrada nova para exibir")
            return

        mid = int(candidate["id"])
        try:
            from core.personal_memory import mark_shown_as_popup
            mark_shown_as_popup(mid)
        except Exception as exc:
            log.debug("InsightScheduler: erro ao marcar shown: %s", exc)

        self._popup_active = True
        log.info("InsightScheduler: emitindo insight id=%d", mid)
        self.insight_ready.emit(candidate["content"], mid)

    def on_popup_closed(self) -> None:
        """Chamado quando o popup fecha (qualquer motivo).

        Imediatamente verifica se há outro insight para exibir.
        """
        self._popup_active = False
        self.maybe_show()

    def on_confirmed(self, memory_id: int) -> None:
        """Usuária confirmou (✓) — reflectir sobre o acerto + enviar para AKASHA."""
        if memory_id < 0:
            return
        self.reflection_requested.emit(memory_id, "confirmed")
        self._send_to_akasha_by_id(memory_id)

    def on_dismissed(self, memory_id: int) -> None:
        """Usuária dispensou (✗) — refletir sobre o que foi mal julgado."""
        if memory_id < 0:
            return
        self.reflection_requested.emit(memory_id, "dismissed")

    def _send_to_akasha_by_id(self, memory_id: int) -> None:
        """Envia o conteúdo de um pensamento confirmado para a AKASHA."""
        try:
            from core.personal_memory import get_by_id
            entry = get_by_id(memory_id)
            if not entry:
                return
            content = entry.get("content", "")
            if not content:
                return
            root = str(Path(__file__).parent.parent.parent)
            if root not in sys.path:
                sys.path.insert(0, root)
            from ecosystem_client import notify_akasha_insight  # type: ignore
            notify_akasha_insight(content, tags=["from_mnemosyne"])
            log.info("InsightScheduler: pensamento confirmado enviado para AKASHA.")
        except Exception as exc:
            log.debug("InsightScheduler: falha ao notificar AKASHA: %s", exc)

    def reset(self) -> None:
        """Força reset de estado — útil para testes."""
        self._popup_active = False
