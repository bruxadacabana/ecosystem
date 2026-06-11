"""
Testes de app/ui/views/analysis_tab.py — scaffold da aba Análise (Fase 7, item 1).

Cobre: rail com as 5 ferramentas (labels + chaves); stack acompanha o rail;
set_pane substitui o placeholder mantendo posição e seleção; chave inválida → no-op;
show_tool seleciona pelo rail; pane() retorna o widget atual.
"""
from __future__ import annotations

import app.utils.paths  # noqa: F401
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from app.ui.views.analysis_tab import TOOLS, AnalysisTab


def test_rail_has_all_tools(qapp):
    tab = AnalysisTab()
    assert tab._rail.count() == len(TOOLS) == 5
    labels = [tab._rail.item(i).text() for i in range(tab._rail.count())]
    assert labels == ["Entidades", "Investigações", "Cobertura", "Enquadramento", "Estatísticas"]
    keys = [tab._rail.item(i).data(Qt.ItemDataRole.UserRole) for i in range(tab._rail.count())]
    assert keys == ["entities", "investigations", "coverage", "framing", "stats"]


def test_stack_has_a_pane_per_tool(qapp):
    tab = AnalysisTab()
    assert tab._stack.count() == len(TOOLS)


def test_rail_selection_switches_stack(qapp):
    tab = AnalysisTab()
    tab._rail.setCurrentRow(2)
    assert tab._stack.currentIndex() == 2
    tab._rail.setCurrentRow(4)
    assert tab._stack.currentIndex() == 4


def test_starts_on_first_tool(qapp):
    tab = AnalysisTab()
    assert tab._rail.currentRow() == 0
    assert tab._stack.currentIndex() == 0


def test_placeholders_present(qapp):
    tab = AnalysisTab()
    pane = tab.pane("entities")
    assert pane is not None
    lbl = pane.findChild(QLabel, "analysis_placeholder")
    assert lbl is not None and "em breve" in lbl.text()


def test_set_pane_replaces_keeping_position(qapp):
    tab = AnalysisTab()
    real = QWidget()
    tab.set_pane("coverage", real)
    assert tab.pane("coverage") is real
    assert tab._stack.count() == len(TOOLS)            # ainda 5 panes
    # a posição no stack é preservada (coverage = índice 2)
    tab._rail.setCurrentRow(2)
    assert tab._stack.currentWidget() is real


def test_set_pane_keeps_current_selection_visible(qapp):
    tab = AnalysisTab()
    tab._rail.setCurrentRow(0)            # entities é a atual
    real = QWidget()
    tab.set_pane("entities", real)
    assert tab._stack.currentWidget() is real


def test_set_pane_unknown_key_noop(qapp):
    tab = AnalysisTab()
    tab.set_pane("inexistente", QWidget())   # não deve levantar
    assert tab._stack.count() == len(TOOLS)


def test_show_tool_selects_rail(qapp):
    tab = AnalysisTab()
    tab.show_tool("stats")
    assert tab._rail.currentRow() == 4
    assert tab._stack.currentIndex() == 4
    tab.show_tool("inexistente")             # no-op
    assert tab._rail.currentRow() == 4
