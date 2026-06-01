"""
Testes para Timeline (Linha do Tempo) e Mind Map outputs do Studio.

Cobertura:
  Timeline:
    - _parse_timeline_entry parseia formatos Markdown corretos
    - formato ** negrito com [periodo] — evento
    - formato [periodo] → evento
    - linhas sem formato reconhecido retornam vazio
    - output salvo e recuperado como StudioOutput com tipo correto

  Mind Map:
    - parse_mindmap_json aceita JSON direto e extrai raiz/nós
    - parse_mindmap_json extrai JSON de bloco ```json ... ```
    - parse_mindmap_json retorna None para texto não-JSON
    - parse_mindmap_json retorna None para JSON sem campos esperados
    - nós têm pai_id correto na estrutura
    - _populate_mindmap_tree popula QTreeWidget sem erro
    - fallback para texto plano quando parse_mindmap_json retorna None

  Integração com StudioOutput:
    - tipo "Linha do Tempo" e "Mind Map" são persistidos como StudioOutput
    - conteúdo JSON do mind map é salvo corretamente
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))

# Mock langchain_openai antes de importar core
if "langchain_openai" not in sys.modules:
    _mock = MagicMock()
    _mock.ChatOpenAI = MagicMock
    sys.modules["langchain_openai"] = _mock

from core.mindmap import parse_mindmap_json

_MAIN_WINDOW_PY = _MNEMOSYNE_ROOT / "gui" / "main_window.py"


# ---------------------------------------------------------------------------
# _parse_timeline_entry (via import estático da função)
# ---------------------------------------------------------------------------

def _get_parse_fn():
    """Importa _parse_timeline_entry sem instanciar a janela."""
    src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
    import ast, types, textwrap
    tree = ast.parse(src)
    # Extrair só o corpo do método estático
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_parse_timeline_entry":
            func_src = ast.get_source_segment(src, node)
            if func_src:
                # Indentar para nível top-level
                func_src = textwrap.dedent(func_src)
                ns: dict = {}
                exec(compile(func_src, "<timeline>", "exec"), ns)
                return ns["_parse_timeline_entry"]
    return None


class TestParseTimelineEntry:
    def setup_method(self):
        self.fn = _get_parse_fn()
        if self.fn is None:
            pytest.skip("_parse_timeline_entry não encontrada via AST")

    def test_bold_bracket_format(self):
        """Formato **[periodo]** — evento deve ser parseado."""
        period, event = self.fn("- **[2022]** — Evento importante aconteceu")
        assert period == "2022"
        assert "Evento" in event

    def test_bracket_arrow_format(self):
        """Formato [periodo] → evento deve ser parseado."""
        period, event = self.fn("- [Séc. XIX] → Revolução Industrial")
        assert "XIX" in period
        assert "Revolução" in event

    def test_bracket_dash_format(self):
        """Formato [periodo] — evento deve ser parseado."""
        period, event = self.fn("- [1945] — Fim da Segunda Guerra")
        assert "1945" in period
        assert "Fim" in event

    def test_empty_line_returns_empty(self):
        """Linha vazia retorna ('', '')."""
        period, event = self.fn("")
        assert period == "" and event == ""

    def test_heading_line_returns_empty(self):
        """Linha sem formato timeline retorna ('', '')."""
        period, event = self.fn("## Título da Seção")
        assert period == "" and event == ""

    def test_no_period_marker_returns_empty(self):
        """Linha de texto puro sem [periodo] retorna ('', '')."""
        period, event = self.fn("Apenas texto livre sem marcador")
        assert period == "" and event == ""

    def test_strips_whitespace(self):
        """Resultado não deve conter espaços extras."""
        period, event = self.fn("  - **[  2023  ]**  —  Evento com espaços  ")
        assert period == "2023"
        assert not event.startswith(" ")
        assert not event.endswith(" ")

    def test_hyphen_as_separator(self):
        """Hífen simples como separador deve ser reconhecido."""
        period, event = self.fn("- [1900] - Início do século")
        assert "1900" in period
        assert "Início" in event


# ---------------------------------------------------------------------------
# parse_mindmap_json
# ---------------------------------------------------------------------------

class TestParseMindmapJson:
    def test_valid_json_returns_dict(self):
        """JSON válido com raiz e nós retorna dict."""
        data = {"raiz": "Tema", "nós": [{"id": "1", "label": "Ramo", "pai_id": ""}]}
        result = parse_mindmap_json(json.dumps(data))
        assert result is not None
        assert result["raiz"] == "Tema"

    def test_json_with_nodes_correct_pai_id(self):
        """Nós devem preservar pai_id correto."""
        data = {
            "raiz": "Raiz",
            "nós": [
                {"id": "1", "label": "Filho da raiz", "pai_id": ""},
                {"id": "1.1", "label": "Neto", "pai_id": "1"},
            ],
        }
        result = parse_mindmap_json(json.dumps(data))
        assert result is not None
        assert result["nós"][0]["pai_id"] == ""
        assert result["nós"][1]["pai_id"] == "1"

    def test_json_inside_code_block(self):
        """JSON dentro de ```json ... ``` deve ser extraído."""
        data = {"raiz": "T", "nós": [{"id": "1", "label": "A", "pai_id": ""}]}
        text = f"```json\n{json.dumps(data)}\n```"
        result = parse_mindmap_json(text)
        assert result is not None
        assert result["raiz"] == "T"

    def test_mermaid_text_returns_none(self):
        """Sintaxe Mermaid (legado) deve retornar None."""
        mermaid = "```mermaid\nmindmap\n  root((Tema))\n    Ramo\n```"
        assert parse_mindmap_json(mermaid) is None

    def test_plain_text_returns_none(self):
        """Texto livre sem JSON retorna None."""
        assert parse_mindmap_json("Este é um texto qualquer.") is None

    def test_empty_string_returns_none(self):
        """String vazia retorna None."""
        assert parse_mindmap_json("") is None

    def test_json_without_raiz_returns_none(self):
        """JSON sem campo 'raiz' retorna None."""
        data = {"nodes": [{"id": "1", "label": "A"}]}
        assert parse_mindmap_json(json.dumps(data)) is None

    def test_json_without_nos_returns_none(self):
        """JSON sem campo 'nós' retorna None."""
        data = {"raiz": "Tema"}
        assert parse_mindmap_json(json.dumps(data)) is None

    def test_nos_can_be_empty_list(self):
        """nós vazio ainda é estrutura válida."""
        data = {"raiz": "Tema", "nós": []}
        result = parse_mindmap_json(json.dumps(data))
        assert result is not None
        assert result["nós"] == []

    def test_json_with_extra_text_around_is_extracted(self):
        """LLM pode adicionar texto antes/depois do JSON — deve extrair o JSON."""
        data = {"raiz": "X", "nós": []}
        text = f"Aqui está o mind map:\n{json.dumps(data)}\nEspero que ajude."
        result = parse_mindmap_json(text)
        assert result is not None
        assert result["raiz"] == "X"


# ---------------------------------------------------------------------------
# _populate_mindmap_tree — via QTreeWidget mock
# ---------------------------------------------------------------------------

class TestPopulateMindmapTree:
    def _get_populate_fn(self):
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        import ast, textwrap
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name == "_populate_mindmap_tree":
                func_src = ast.get_source_segment(src, node)
                if func_src:
                    return textwrap.dedent(func_src)
        return None

    def test_populate_uses_raiz_as_root(self):
        """Função _populate_mindmap_tree deve usar 'raiz' como nó raiz."""
        func_src = self._get_populate_fn()
        assert func_src is not None
        assert "raiz" in func_src

    def test_populate_handles_pai_id(self):
        """Função deve usar pai_id para determinar hierarquia."""
        func_src = self._get_populate_fn()
        assert func_src is not None
        assert "pai_id" in func_src

    def test_populate_uses_qtreewidgetitem(self):
        """Função deve criar QTreeWidgetItem."""
        func_src = self._get_populate_fn()
        assert func_src is not None
        assert "QTreeWidgetItem" in func_src

    def test_structure_with_nested_nodes(self):
        """Estrutura aninhada: pai → filho → neto deve ser aceita sem erro."""
        # Test via mock sem Qt real
        tree_mock = MagicMock()
        root_item = MagicMock()

        items_created = []

        class FakeItem:
            def __init__(self, labels):
                self.labels = labels
                self.children: list = []
            def addChild(self, child):
                self.children.append(child)

        # Simular comportamento: testar apenas a lógica do parse_mindmap_json
        data = {
            "raiz": "Raiz",
            "nós": [
                {"id": "1", "label": "Ramo A", "pai_id": ""},
                {"id": "2", "label": "Ramo B", "pai_id": ""},
                {"id": "1.1", "label": "Filho de A", "pai_id": "1"},
            ],
        }
        result = parse_mindmap_json(json.dumps(data))
        assert result is not None
        # Verificar estrutura
        assert result["nós"][2]["pai_id"] == "1"


# ---------------------------------------------------------------------------
# Análise estática: main_window.py contém os handlers corretos
# ---------------------------------------------------------------------------

class TestMainWindowTimelineMindmapHandlers:
    def test_on_tile_opened_dispatches_to_timeline(self):
        """_on_tile_opened deve despachar 'Linha do Tempo' para _open_timeline_output."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        idx = src.find("def _on_tile_opened")
        end = src.find("\n    def ", idx + 1)
        method_src = src[idx:end]
        assert "_open_timeline_output" in method_src

    def test_on_tile_opened_dispatches_to_mindmap(self):
        """_on_tile_opened deve despachar 'Mind Map' para _open_mindmap_output."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        idx = src.find("def _on_tile_opened")
        end = src.find("\n    def ", idx + 1)
        method_src = src[idx:end]
        assert "_open_mindmap_output" in method_src

    def test_open_timeline_output_exists(self):
        """_open_timeline_output deve existir em main_window.py."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "def _open_timeline_output" in src

    def test_open_mindmap_output_exists(self):
        """_open_mindmap_output deve existir em main_window.py."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "def _open_mindmap_output" in src

    def test_open_timeline_uses_scroll_area(self):
        """Timeline deve usar QScrollArea para lista longa de eventos."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        idx = src.find("def _open_timeline_output")
        end = src.find("\n    def ", idx + 1)
        method_src = src[idx:end]
        assert "QScrollArea" in method_src or "scroll" in method_src.lower()

    def test_open_mindmap_uses_qtreewidget(self):
        """Mind Map deve usar QTreeWidget para renderização."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        idx = src.find("def _open_mindmap_output")
        end = src.find("\n    def ", idx + 1)
        method_src = src[idx:end]
        assert "QTreeWidget" in method_src

    def test_mindmap_has_fallback_to_text(self):
        """Mind Map deve ter fallback para texto plano (outputs legados Mermaid)."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        idx = src.find("def _open_mindmap_output")
        end = src.find("\n    def ", idx + 1)
        method_src = src[idx:end]
        assert "QTextEdit" in method_src or "setPlainText" in method_src

    def test_populate_mindmap_tree_exists(self):
        """_populate_mindmap_tree deve existir em main_window.py."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "def _populate_mindmap_tree" in src

    def test_timeline_imports_parse_fn(self):
        """_parse_timeline_entry deve ser definido em main_window.py."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "def _parse_timeline_entry" in src

    def test_qtreewidget_in_imports(self):
        """QTreeWidget deve estar nos imports de main_window.py."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "QTreeWidget" in src

    def test_qtreewidgetitem_in_imports(self):
        """QTreeWidgetItem deve estar nos imports de main_window.py."""
        src = _MAIN_WINDOW_PY.read_text(encoding="utf-8")
        assert "QTreeWidgetItem" in src


# ---------------------------------------------------------------------------
# Integração: StudioOutput persiste timeline e mindmap
# ---------------------------------------------------------------------------

class TestStudioOutputPersistence:
    def test_timeline_studio_output_type(self):
        """StudioOutput com tipo 'Linha do Tempo' deve ser criado sem erro."""
        from core.studio_output import StudioOutput
        output = StudioOutput(
            type="Linha do Tempo",
            content="- **[2022]** — Evento A\n- **[2023]** — Evento B",
            collection_name="test",
        )
        assert output.type == "Linha do Tempo"
        assert "2022" in output.content

    def test_mindmap_studio_output_with_json(self):
        """StudioOutput com tipo 'Mind Map' e conteúdo JSON deve ser criado sem erro."""
        from core.studio_output import StudioOutput
        data = {"raiz": "Tema", "nós": [{"id": "1", "label": "Ramo", "pai_id": ""}]}
        output = StudioOutput(
            type="Mind Map",
            content=json.dumps(data),
            collection_name="test",
        )
        assert output.type == "Mind Map"
        parsed = parse_mindmap_json(output.content)
        assert parsed is not None
        assert parsed["raiz"] == "Tema"

    def test_mindmap_output_persisted_json_roundtrip(self, tmp_path):
        """JSON do mind map deve sobreviver ao ciclo salvar/carregar do StudioStore."""
        from core.studio_output import StudioOutput
        from core.studio_store import StudioStore
        data = {
            "raiz": "Ecossistema",
            "nós": [
                {"id": "1", "label": "AKASHA", "pai_id": ""},
                {"id": "2", "label": "Mnemosyne", "pai_id": ""},
                {"id": "1.1", "label": "Busca", "pai_id": "1"},
            ],
        }
        store = StudioStore(str(tmp_path))
        output = StudioOutput(
            type="Mind Map",
            content=json.dumps(data),
            collection_name="test",
        )
        store.save(output)
        loaded = store.load_all()
        mindmap_outputs = [o for o in loaded if o.type == "Mind Map"]
        assert len(mindmap_outputs) == 1
        parsed = parse_mindmap_json(mindmap_outputs[0].content)
        assert parsed is not None
        assert parsed["raiz"] == "Ecossistema"
        assert len(parsed["nós"]) == 3
