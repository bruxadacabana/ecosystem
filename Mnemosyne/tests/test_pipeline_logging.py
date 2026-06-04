"""
Testes da observabilidade do pipeline do Mnemosyne (BUG-030).

Garante que cada etapa de persistência/processo emite log, para a usuária
conseguir auditar pelo log se o Mnemosyne está funcionando:

  - save_memory: emite INFO "memória pessoal salva id=..." a cada gravação
    (teste funcional via caplog).
  - IndexWorker / ResumeIndexWorker: narram início por arquivo, batch embedado
    e arquivo concluído com contagem de vetores (inspeção de source — o pipeline
    completo exige Qt + Chroma, inviável em teste unitário).

Estilo escolhido pela usuária: "narração viva" (INFO nos marcos, DEBUG no
detalhe fino).
"""

import logging
import sys
from pathlib import Path

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))

_WORKERS_PY = _MNEMOSYNE_ROOT / "gui" / "workers.py"


# ---------------------------------------------------------------------------
# Fixture — banco personal_memory temporário (mesmo padrão de test_integracao2)
# ---------------------------------------------------------------------------

@pytest.fixture
def pm_db(tmp_path, monkeypatch):
    """Banco personal_memory temporário; injeta via monkeypatch em _DB_PATH."""
    db_path = str(tmp_path / "personal_memory.db")
    import core.personal_memory as pm

    monkeypatch.setattr(pm, "_DB_PATH", Path(db_path))
    pm._conn()  # inicializa schema no db temporário
    yield pm


# ---------------------------------------------------------------------------
# save_memory — log funcional
# ---------------------------------------------------------------------------

class TestSaveMemoryLog:

    def test_save_memory_emite_info(self, pm_db, caplog):
        """save_memory deve emitir um INFO confirmando a gravação."""
        with caplog.at_level(logging.INFO, logger="mnemosyne.personal_memory"):
            mid = pm_db.save_memory(type="observation", content="Conteúdo de teste")
        msgs = [r.getMessage() for r in caplog.records
                if r.name == "mnemosyne.personal_memory"]
        assert any("memória pessoal salva" in m for m in msgs), (
            f"save_memory deveria logar a gravação; logs: {msgs}"
        )

    def test_log_inclui_id_e_type(self, pm_db, caplog):
        """O log deve identificar a memória salva (id e type) para auditoria."""
        with caplog.at_level(logging.INFO, logger="mnemosyne.personal_memory"):
            mid = pm_db.save_memory(type="connection", content="Conexão A↔B")
        msgs = [r.getMessage() for r in caplog.records
                if r.name == "mnemosyne.personal_memory"]
        joined = " ".join(msgs)
        assert f"id={mid}" in joined, f"log deve conter id={mid}; logs: {msgs}"
        assert "type=connection" in joined, f"log deve conter o type; logs: {msgs}"

    def test_log_nivel_info(self, pm_db, caplog):
        """A gravação é um marco — deve ser INFO, não DEBUG (visível por padrão)."""
        with caplog.at_level(logging.INFO, logger="mnemosyne.personal_memory"):
            pm_db.save_memory(type="observation", content="X")
        salvos = [r for r in caplog.records
                  if r.name == "mnemosyne.personal_memory"
                  and "memória pessoal salva" in r.getMessage()]
        assert salvos, "deveria haver ao menos um registro de gravação"
        assert all(r.levelno == logging.INFO for r in salvos), (
            "o log de gravação de memória deve ser nível INFO"
        )

    def test_cada_save_gera_um_log(self, pm_db, caplog):
        """Cada chamada a save_memory gera exatamente um log de gravação."""
        with caplog.at_level(logging.INFO, logger="mnemosyne.personal_memory"):
            pm_db.save_memory(type="observation", content="primeiro")
            pm_db.save_memory(type="observation", content="segundo")
            pm_db.save_memory(type="observation", content="terceiro")
        salvos = [r for r in caplog.records
                  if "memória pessoal salva" in r.getMessage()]
        assert len(salvos) == 3, (
            f"3 saves deveriam gerar 3 logs de gravação, obteve {len(salvos)}"
        )


# ---------------------------------------------------------------------------
# IndexWorker / ResumeIndexWorker — narração (inspeção de source)
# ---------------------------------------------------------------------------

class TestIndexWorkerNarration:

    @pytest.fixture(scope="class")
    def src(self):
        return _WORKERS_PY.read_text(encoding="utf-8")

    def test_indexworker_loga_inicio_de_arquivo(self, src):
        assert 'IndexWorker: indexando [%d/%d]' in src, (
            "IndexWorker deve logar o início de cada arquivo (i/total)"
        )

    def test_indexworker_loga_chunks(self, src):
        assert 'chunks gerados de' in src, (
            "IndexWorker deve logar o nº de chunks gerados por arquivo"
        )

    def test_indexworker_loga_batch_embedado(self, src):
        assert 'batch %d/%d embedado' in src, (
            "IndexWorker deve logar cada batch embedado (resolve o '10 min mudo')"
        )

    def test_indexworker_loga_arquivo_concluido_com_vetores(self, src):
        assert 'vetores gravados no Chroma' in src, (
            "IndexWorker deve logar o arquivo concluído com a contagem de vetores"
        )

    def test_resumeindexworker_tambem_narra(self, src):
        # O caminho de retomada ("Atualizar índice") deve ser igualmente auditável.
        assert 'ResumeIndexWorker: indexando [%d/%d]' in src
        assert 'ResumeIndexWorker: batch %d/%d embedado' in src
        assert src.count('vetores gravados no Chroma') >= 2, (
            "ambos os workers (Index e Resume) devem logar vetores gravados"
        )

    def test_batch_inicial_logado(self, src):
        # O probe de GPU (primeiro batch do IndexWorker) também deve aparecer.
        assert 'batch inicial embedado' in src


# ---------------------------------------------------------------------------
# Tarefas de enriquecimento em background (zettel / plutchik) — logam gravação
# ---------------------------------------------------------------------------

class TestBackgroundEnrichmentLogs:

    def test_zettel_link_loga_ao_ligar(self, pm_db, caplog):
        """_zettel_link_bg deve logar quando cria links entre memórias."""
        import json
        con = pm_db._conn()
        con.execute(
            "INSERT INTO personal_memory (id, type, content, zettel_keywords) "
            "VALUES (1, 'observation', 'mem A', ?)",
            (json.dumps(["a", "b", "c"]),),
        )
        con.execute(
            "INSERT INTO personal_memory (id, type, content, zettel_keywords) "
            "VALUES (2, 'observation', 'mem B', ?)",
            (json.dumps(["a", "b", "c", "d"]),),
        )
        con.commit()
        con.close()

        with caplog.at_level(logging.DEBUG, logger="mnemosyne.personal_memory"):
            # Jaccard(["a","b","c","d"], ["a","b","c"]) = 0.75 ≥ 0.15 → liga
            pm_db._zettel_link_bg(2, ["a", "b", "c", "d"], pm_db._get_db())

        msgs = [r.getMessage() for r in caplog.records]
        assert any("zettel: memória 2 ligada" in m for m in msgs), (
            f"_zettel_link_bg deveria logar a ligação criada; logs: {msgs}"
        )

    def test_plutchik_e_zettel_success_logs_existem(self):
        """Source: as duas funções de background devem ter log de sucesso, não só de erro."""
        src = (_MNEMOSYNE_ROOT / "core" / "personal_memory.py").read_text(encoding="utf-8")
        assert 'zettel: memória %d ligada' in src
        assert 'plutchik: memória %d classificada' in src

    def test_disparo_plutchik_nao_e_silencioso(self):
        """Source: o except do disparo da thread Plutchik não pode ser `pass` mudo."""
        src = (_MNEMOSYNE_ROOT / "core" / "personal_memory.py").read_text(encoding="utf-8")
        assert "não foi possível iniciar classificação Plutchik" in src, (
            "o except do disparo do Plutchik deve logar, não engolir em silêncio"
        )


# ---------------------------------------------------------------------------
# Sem `except: pass` mudo nos caminhos de persistência/pipeline (escopo A)
# ---------------------------------------------------------------------------

class TestNoSilentSwallows:
    """Regressão: nenhum `except ...: pass` (corpo só `pass`) pode reaparecer nos
    arquivos de persistência/pipeline do Mnemosyne — todo erro deve ser logado."""

    _SCOPE_A = [
        "core/indexer.py", "core/personal_memory.py", "core/memory.py",
        "core/parent_store.py", "core/bm25_index.py", "core/insight_scheduler.py",
        "core/reflection.py", "core/insights.py", "core/session_indexer.py",
        "core/idle_indexer.py", "core/rag.py", "gui/workers.py", "core/config.py",
    ]

    @pytest.mark.parametrize("rel", _SCOPE_A)
    def test_arquivo_sem_except_pass_mudo(self, rel):
        import ast
        src = (_MNEMOSYNE_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)
        mudos = [
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
        ]
        assert not mudos, (
            f"{rel} ainda tem `except: pass` mudo nas linhas {mudos} — "
            f"todo erro deve ser logado (escopo A do BUG-030)"
        )
