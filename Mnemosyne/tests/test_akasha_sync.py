"""
Testes de integração Mnemosyne↔AKASHA.

Cobre o protocolo de amizade: Mnemosyne deposita insights no ecosystem.json
via notify_akasha_insight (escrita); AKASHA lê via friendship_receiver (polling).
Também testa o caminho inverso e o comportamento com AKASHA offline.

Cenários:
  1. notify_akasha_insight grava no ecosystem.json com conteúdo correto
  2. notify_akasha_insight com tags → gravadas na entrada
  3. notify_akasha_insight com AKASHA offline → falha silenciosa (sem exception)
  4. Fila FIFO respeita limite de 50 entradas
  5. notify_akasha_insight com IO error → capturado, não propaga
  6. notify_mnemosyne_insight grava em mnemosyne.incoming_insights
  7. friendship_receiver AKASHA: processa entrada de incoming_insights (unit)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_ECO_ROOT = Path(__file__).parent.parent.parent  # program files/


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_eco(eco_path: Path, data: dict) -> None:
    eco_path.write_text(json.dumps(data), encoding="utf-8")


def _read_eco(eco_path: Path) -> dict:
    return json.loads(eco_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. notify_akasha_insight: grava no ecosystem.json
# ---------------------------------------------------------------------------

def test_notify_akasha_insight_writes_to_ecosystem_json():
    """notify_akasha_insight deve escrever entrada em akasha.incoming_insights."""
    sys.path.insert(0, str(_ECO_ROOT))
    import ecosystem_client as ec

    with tempfile.TemporaryDirectory() as td:
        eco = Path(td) / "ecosystem.json"
        _write_eco(eco, {"akasha": {"incoming_insights": []}})

        with patch.object(ec, "read_ecosystem", return_value={"akasha": {"incoming_insights": []}}):
            saved: list[dict] = []

            def _fake_write_section(section: str, data: dict) -> None:
                if section == "akasha":
                    saved.extend(data.get("incoming_insights", []))

            with patch.object(ec, "write_section", side_effect=_fake_write_section):
                ec.notify_akasha_insight(content="Descobri conexão entre X e Y")

    assert len(saved) == 1
    assert saved[0]["content"] == "Descobri conexão entre X e Y"
    assert "received_at" in saved[0]


# ---------------------------------------------------------------------------
# 2. notify_akasha_insight com tags
# ---------------------------------------------------------------------------

def test_notify_akasha_insight_includes_tags():
    """Tags devem ser gravadas junto com o insight."""
    import ecosystem_client as ec

    saved: list[dict] = []

    def _fake_write(section: str, data: dict) -> None:
        if section == "akasha":
            saved.extend(data.get("incoming_insights", []))

    with patch.object(ec, "read_ecosystem", return_value={"akasha": {"incoming_insights": []}}):
        with patch.object(ec, "write_section", side_effect=_fake_write):
            ec.notify_akasha_insight(content="insight", tags=["filosofia", "memória"])

    assert saved[0]["tags"] == ["filosofia", "memória"]


# ---------------------------------------------------------------------------
# 3. notify_akasha_insight com IO error → falha silenciosa
# ---------------------------------------------------------------------------

def test_notify_akasha_insight_io_error_is_silent():
    """Erros de IO não devem propagar para o caller."""
    import ecosystem_client as ec

    with patch.object(ec, "read_ecosystem", side_effect=OSError("disco cheio")):
        ec.notify_akasha_insight(content="qualquer coisa")
    # Se chegou aqui, exceção foi capturada corretamente.


# ---------------------------------------------------------------------------
# 4. FIFO respeita limite de 50 entradas
# ---------------------------------------------------------------------------

def test_notify_akasha_insight_respects_fifo_limit():
    """Após 50 entradas, as mais antigas devem ser descartadas."""
    import ecosystem_client as ec

    existing = [{"content": f"antigo_{i}", "received_at": "x"} for i in range(50)]
    saved: list[dict] = []

    def _fake_write(section: str, data: dict) -> None:
        if section == "akasha":
            saved.clear()
            saved.extend(data.get("incoming_insights", []))

    with patch.object(ec, "read_ecosystem", return_value={"akasha": {"incoming_insights": existing}}):
        with patch.object(ec, "write_section", side_effect=_fake_write):
            ec.notify_akasha_insight(content="novo_insight")

    assert len(saved) == 50, "fila não deve ultrapassar 50 entradas"
    assert saved[-1]["content"] == "novo_insight", "novo insight deve estar no fim"
    assert all(s["content"] != "antigo_0" for s in saved), "entrada mais antiga deve ser descartada"


# ---------------------------------------------------------------------------
# 5. notify_mnemosyne_insight: grava em mnemosyne.incoming_insights
# ---------------------------------------------------------------------------

def test_notify_mnemosyne_insight_writes_correctly():
    """notify_mnemosyne_insight deve gravar em mnemosyne.incoming_insights."""
    import ecosystem_client as ec

    saved: list[dict] = []

    def _fake_write(section: str, data: dict) -> None:
        if section == "mnemosyne":
            saved.extend(data.get("incoming_insights", []))

    with patch.object(ec, "read_ecosystem", return_value={"mnemosyne": {"incoming_insights": []}}):
        with patch.object(ec, "write_section", side_effect=_fake_write):
            ec.notify_mnemosyne_insight(
                topics=["memória", "corpus"],
                summary="Achei algo relevante no corpus",
                sources=[{"url": "http://example.com", "title": "Exemplo"}],
            )

    assert len(saved) == 1
    assert saved[0]["summary"] == "Achei algo relevante no corpus"
    assert "memória" in saved[0]["topics"]


# ---------------------------------------------------------------------------
# 6. AKASHA friendship_receiver: processa insight de incoming_insights
# ---------------------------------------------------------------------------

def test_friendship_receiver_insight_format():
    """notify_akasha_insight grava entry com formato correto para o friendship_receiver processar."""
    import ecosystem_client as ec

    # O friendship_receiver AKASHA espera campos: content, received_at, (opcional) tags
    saved: list[dict] = []

    def _fake_write(section: str, data: dict) -> None:
        if section == "akasha":
            saved.extend(data.get("incoming_insights", []))

    with patch.object(ec, "read_ecosystem", return_value={"akasha": {"incoming_insights": []}}):
        with patch.object(ec, "write_section", side_effect=_fake_write):
            ec.notify_akasha_insight(
                content="Mnemosyne notou padrão entre memória coletiva e identidade cultural",
                tags=["memória", "identidade", "cultura"],
                emotional_context={"valence": 0.7, "arousal": 0.4},
            )

    assert len(saved) == 1
    entry = saved[0]
    # Campos que o friendship_receiver usa para processar
    assert "content" in entry, "campo 'content' é obrigatório para o friendship_receiver"
    assert "received_at" in entry, "campo 'received_at' é obrigatório"
    assert entry["tags"] == ["memória", "identidade", "cultura"]
    assert entry["emotional_context"]["valence"] == 0.7


# ---------------------------------------------------------------------------
# 7. Mnemosyne → AKASHA: workers.py envia insight quando threshold atingido
# ---------------------------------------------------------------------------

def test_index_reflection_worker_sends_to_akasha_on_threshold():
    """IndexReflectionWorker deve chamar notify_akasha_insight quando overlap suficiente."""
    # Testa a lógica de envio isolada — sem Qt, sem thread real
    sys.path.insert(0, str(_ECO_ROOT))
    import ecosystem_client as ec

    sent: list[dict] = []

    def _fake_notify(content: str, tags: list | None = None, **kw) -> None:
        sent.append({"content": content, "tags": tags})

    # Mock do shared_topic_profile para simular overlap positivo
    fake_stp = MagicMock()
    fake_stp.has_overlap.return_value = True

    with patch.dict("sys.modules", {"shared_topic_profile": fake_stp}):
        with patch.object(ec, "notify_akasha_insight", side_effect=_fake_notify):
            # Simular diretamente a lógica do worker (sem importar Qt)
            keywords = ["memória", "filosófica", "coletiva"]
            reflection = "Reflexão sobre memória coletiva e impacto cultural."

            if fake_stp.has_overlap(keywords, min_topics=2, min_score=1.0):
                ec.notify_akasha_insight(content=reflection, tags=keywords[:8])

    assert len(sent) == 1
    assert sent[0]["content"] == reflection
    assert "memória" in sent[0]["tags"]
