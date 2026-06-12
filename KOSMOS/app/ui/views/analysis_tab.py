"""
analysis_tab.py — Aba "Análise": ferramentas de investigação (Fase 7).

Layout: um rail de lista à esquerda (as 5 ferramentas) + um QStackedWidget à direita
que mostra a ferramenta selecionada em largura cheia — espelha a sidebar de feeds da
aba de Leitura, e dá espaço vertical inteiro para conteúdo denso (timelines, tabelas
feed×dia, comparações lado a lado).

Este módulo é o scaffold: cada ferramenta começa como um placeholder e é substituída
pela view real (`set_pane`) conforme os itens seguintes da Fase 7 são implementados:
rastreador de entidades, pastas de investigação, mapa de cobertura, comparação de
enquadramento e dashboard de estatísticas.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("kosmos.analysis_tab")

# Ordem das ferramentas no rail. A chave identifica o pane para `set_pane`.
TOOLS: list[tuple[str, str]] = [
    ("entities", "Entidades"),
    ("investigations", "Investigações"),
    ("coverage", "Cobertura"),
    ("framing", "Enquadramento"),
    ("alerts", "Alertas"),
    ("stats", "Estatísticas"),
]


class AnalysisTab(QWidget):
    """Container das ferramentas de investigação: rail à esquerda + painel à direita."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._panes: dict[str, QWidget] = {}
        self._keys: list[str] = [key for key, _ in TOOLS]
        self._setup_ui()
        log.debug("AnalysisTab inicializada com %d ferramentas.", len(TOOLS))

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._rail = QListWidget()
        self._rail.setObjectName("analysis_rail")
        self._rail.setMaximumWidth(200)
        for key, label in TOOLS:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._rail.addItem(item)
        self._rail.currentRowChanged.connect(self._on_rail_changed)
        layout.addWidget(self._rail)

        self._stack = QStackedWidget()
        for key, label in TOOLS:
            pane = self._make_placeholder(label)
            self._panes[key] = pane
            self._stack.addWidget(pane)
        layout.addWidget(self._stack, 1)

        self._rail.setCurrentRow(0)

    def _make_placeholder(self, label: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(f"{label} — em breve")
        lbl.setObjectName("analysis_placeholder")
        lbl_align = Qt.AlignmentFlag.AlignCenter
        lbl.setAlignment(lbl_align)
        lay.addWidget(lbl)
        return w

    def _on_rail_changed(self, row: int) -> None:
        if 0 <= row < self._stack.count():
            self._stack.setCurrentIndex(row)

    # ------------------------------------------------------------------
    # API para os itens seguintes da Fase 7
    # ------------------------------------------------------------------

    def set_pane(self, key: str, widget: QWidget) -> None:
        """Substitui o placeholder de uma ferramenta pela view real.

        Mantém a posição no rail/stack. Usado por entity_view, investigation_view,
        coverage_map, etc. para injetar a ferramenta real sem mexer no rail.
        """
        if key not in self._panes:
            log.warning("AnalysisTab.set_pane: chave desconhecida %r", key)
            return
        idx = self._keys.index(key)
        old = self._panes[key]
        was_current = self._stack.currentIndex() == idx
        self._stack.removeWidget(old)
        old.deleteLater()
        self._stack.insertWidget(idx, widget)
        self._panes[key] = widget
        if was_current:
            self._stack.setCurrentIndex(idx)
        log.debug("AnalysisTab: ferramenta %r substituída pela view real.", key)

    def pane(self, key: str) -> QWidget | None:
        """Retorna o widget atual de uma ferramenta (placeholder ou view real)."""
        return self._panes.get(key)

    def show_tool(self, key: str) -> None:
        """Seleciona uma ferramenta pelo rail (ex.: navegação vinda de outra aba)."""
        if key in self._keys:
            self._rail.setCurrentRow(self._keys.index(key))
