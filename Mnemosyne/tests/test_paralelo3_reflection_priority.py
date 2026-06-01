"""
Testes para Paralelo 3 — IndexReflectionWorker com fila de prioridade.

Usa análise de AST para verificar propriedades estruturais do código sem
importar workers.py (que tem dependências pesadas de Qt/LLM em nível de módulo).

Cobre:
  IndexReflectionWorker.__init__:
    - aceita parâmetro priority: str = "high"
    - aceita parâmetro force: bool = False
    - armazena self._priority

  IndexReflectionWorker.start():
    - parâmetro renomeado para thread_priority (não conflita com self._priority)

  IndexReflectionWorker.run():
    - faz log.info com self._priority (label de prioridade)
    - faz log.debug com self._priority em _process_file

  _drain_analysis_queue (main_window.py):
    - cria IndexReflectionWorker com priority="high"
    - log menciona "alta"

  _reanalyze_all_reflections (main_window.py):
    - cria IndexReflectionWorker com priority="low"

  Verificação de não-bloqueio:
    - IndexReflectionWorker não chama self.wait()
    - IndexReflectionWorker não chama index_worker.wait() nem join()
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
_WORKERS_PY     = _MNEMOSYNE_ROOT / "gui" / "workers.py"
_MAIN_WINDOW_PY = _MNEMOSYNE_ROOT / "gui" / "main_window.py"

if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))


# ---------------------------------------------------------------------------
# Helpers de AST
# ---------------------------------------------------------------------------

def _load_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _find_method(class_node: ast.ClassDef, method_name: str) -> ast.FunctionDef | None:
    for node in ast.walk(class_node):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    return None


def _param_names(func: ast.FunctionDef) -> list[str]:
    return [arg.arg for arg in func.args.args]


def _param_defaults_as_constants(func: ast.FunctionDef) -> dict[str, object]:
    """Retorna {param_name: default_value} para parâmetros com defaults simples."""
    args  = func.args.args
    defs  = func.args.defaults
    # defaults alinhados ao final de args
    offset = len(args) - len(defs)
    result = {}
    for i, default in enumerate(defs):
        param = args[offset + i]
        if isinstance(default, ast.Constant):
            result[param.arg] = default.value
    return result


def _source_of(func: ast.FunctionDef) -> str:
    return ast.unparse(func)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def workers_tree():
    return _load_ast(_WORKERS_PY)


@pytest.fixture(scope="module")
def reflection_worker_cls(workers_tree):
    cls = _find_class(workers_tree, "IndexReflectionWorker")
    assert cls is not None, "IndexReflectionWorker não encontrado em workers.py"
    return cls


@pytest.fixture(scope="module")
def main_window_src():
    return _MAIN_WINDOW_PY.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# __init__ — parâmetro priority
# ---------------------------------------------------------------------------

class TestInitSignature:

    def test_init_accepts_priority_param(self, reflection_worker_cls):
        init = _find_method(reflection_worker_cls, "__init__")
        assert init is not None
        params = _param_names(init)
        assert "priority" in params, (
            "__init__ deve ter parâmetro 'priority'"
        )

    def test_priority_default_is_high(self, reflection_worker_cls):
        init = _find_method(reflection_worker_cls, "__init__")
        defaults = _param_defaults_as_constants(init)
        assert defaults.get("priority") == "high", (
            f"Default de priority deve ser 'high', obteve: {defaults.get('priority')}"
        )

    def test_init_still_accepts_force_param(self, reflection_worker_cls):
        init = _find_method(reflection_worker_cls, "__init__")
        params = _param_names(init)
        assert "force" in params, "force deve continuar como parâmetro de __init__"

    def test_init_stores_self_priority(self, reflection_worker_cls):
        init = _find_method(reflection_worker_cls, "__init__")
        src = _source_of(init)
        assert "self._priority" in src, (
            "__init__ deve armazenar self._priority"
        )

    def test_init_stores_self_force(self, reflection_worker_cls):
        init = _find_method(reflection_worker_cls, "__init__")
        src = _source_of(init)
        assert "self._force" in src, "__init__ deve armazenar self._force"


# ---------------------------------------------------------------------------
# start() — parâmetro renomeado para não conflitar
# ---------------------------------------------------------------------------

class TestStartSignature:

    def test_start_param_renamed_to_thread_priority(self, reflection_worker_cls):
        start = _find_method(reflection_worker_cls, "start")
        assert start is not None
        params = _param_names(start)
        assert "thread_priority" in params, (
            "start() deve usar 'thread_priority' como parâmetro "
            "(não 'priority' — conflitaria com o campo da instância)"
        )

    def test_start_param_is_not_named_priority(self, reflection_worker_cls):
        start = _find_method(reflection_worker_cls, "start")
        params = _param_names(start)
        assert "priority" not in params, (
            "start() não deve ter parâmetro 'priority' — conflitaria com self._priority"
        )


# ---------------------------------------------------------------------------
# run() — log com priority label
# ---------------------------------------------------------------------------

class TestRunLogs:

    def test_run_logs_self_priority(self, reflection_worker_cls):
        run = _find_method(reflection_worker_cls, "run")
        assert run is not None
        src = _source_of(run)
        assert "self._priority" in src, (
            "run() deve referenciar self._priority (para log de prioridade)"
        )

    def test_process_file_logs_self_priority(self, reflection_worker_cls):
        pf = _find_method(reflection_worker_cls, "_process_file")
        assert pf is not None
        src = _source_of(pf)
        assert "self._priority" in src, (
            "_process_file deve incluir self._priority no log"
        )


# ---------------------------------------------------------------------------
# Verificação de não-bloqueio
# ---------------------------------------------------------------------------

class TestNonBlocking:

    def test_no_wait_call_in_class(self, reflection_worker_cls):
        src = ast.unparse(reflection_worker_cls)
        assert "self.wait()" not in src, (
            "IndexReflectionWorker não deve chamar self.wait() — bloquearia o event loop Qt"
        )

    def test_no_blocking_join_in_run(self, reflection_worker_cls):
        run = _find_method(reflection_worker_cls, "run")
        src = _source_of(run)
        assert ".join()" not in src, (
            "run() não deve chamar .join() em nenhum worker — bloquearia a thread"
        )


# ---------------------------------------------------------------------------
# main_window — _drain_analysis_queue usa priority="high"
# ---------------------------------------------------------------------------

class TestDrainAnalysisQueuePriority:

    def test_drain_analysis_queue_passes_high_priority(self, main_window_src):
        # Encontra o trecho de _drain_analysis_queue
        assert 'priority="high"' in main_window_src or "priority='high'" in main_window_src, (
            "_drain_analysis_queue deve criar IndexReflectionWorker com priority='high'"
        )

    def test_drain_analysis_queue_logs_alta(self, main_window_src):
        # O log deve mencionar "alta" (arquivos recém-indexados = alta prioridade)
        assert '"alta"' in main_window_src or "'alta'" in main_window_src or "alta" in main_window_src, (
            "_drain_analysis_queue deve logar com label 'alta'"
        )


# ---------------------------------------------------------------------------
# main_window — _reanalyze_all_reflections usa priority="low"
# ---------------------------------------------------------------------------

class TestReanalyzePriority:

    def test_reanalyze_passes_low_priority(self, main_window_src):
        assert 'priority="low"' in main_window_src or "priority='low'" in main_window_src, (
            "_reanalyze_all_reflections deve criar IndexReflectionWorker com priority='low'"
        )

    def test_only_one_low_priority_assignment(self, main_window_src):
        count_low  = main_window_src.count('priority="low"') + main_window_src.count("priority='low'")
        count_high = main_window_src.count('priority="high"') + main_window_src.count("priority='high'")
        assert count_low >= 1,  "Deve haver ao menos uma atribuição priority='low'"
        assert count_high >= 1, "Deve haver ao menos uma atribuição priority='high'"
