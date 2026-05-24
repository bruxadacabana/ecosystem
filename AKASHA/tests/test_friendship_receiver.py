"""
Testes para services/friendship_receiver.py.

Cobre:
  - _extract_keywords(): extrai até 8 palavras ≥5 chars, filtra stop words
  - _find_cross_connection(): busca em crawl_pages, retorna None se <2 keywords
  - _find_cross_connection(): retorna texto de conexão quando DB tem match
  - _apply_emotional_context(): sem emotional_context → sem record_appraisal
  - _apply_emotional_context(): blend 30% valence, registra appraisal
  - _apply_emotional_context(): joint_attention quando ambas curiosidades > 0.6
  - _poll_and_store(): sem insights → retorna sem salvar ou limpar
  - _poll_and_store(): salva insights em personal_memory com type="connection"
  - _poll_and_store(): adiciona tag "from_mnemosyne" se ausente
  - _poll_and_store(): descarta itens muito curtos (<10 chars)
  - _poll_and_store(): limpa incoming_insights via write_section
  - _poll_and_store(): cross-insight gerado quando _find_cross_connection retorna texto
  - _poll_and_store(): graceful quando ecosystem_client não disponível
  - _poll_and_store(): continua se save_memory lançar exceção
"""
from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_aiosqlite_mock(row):
    """Retorna mock de aiosqlite.connect que devolve row no fetchone."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=row)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_cursor)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_aiosqlite = MagicMock()
    mock_aiosqlite.connect = MagicMock(return_value=mock_cm)
    return mock_aiosqlite


def _make_eco_client(incoming: list[dict]):
    """Mock de ecosystem_client com incoming_insights fornecido."""
    mock_eco = MagicMock()
    mock_eco.read_ecosystem = MagicMock(return_value={"akasha": {"incoming_insights": incoming}})
    mock_eco.write_section = MagicMock()
    return mock_eco


# ---------------------------------------------------------------------------
# _extract_keywords
# ---------------------------------------------------------------------------

def test_extract_keywords_basic():
    from services.friendship_receiver import _extract_keywords
    result = _extract_keywords("redes neurais profundas aprendem padrões")
    # Palavras ≥5 chars: "redes"(5), "neurais"(7), "profundas"(9), "aprendem"(8), "padrões"(7)
    assert len(result) >= 4
    assert all(len(w) >= 5 for w in result)
    assert "neurais" in result
    assert "profundas" in result


def test_extract_keywords_filters_stop_words():
    from services.friendship_receiver import _extract_keywords
    result = _extract_keywords("sobre entre quando através ainda muito")
    # todas são stop words — resultado deve ser vazio
    assert result == []


def test_extract_keywords_max_8():
    from services.friendship_receiver import _extract_keywords
    text = "alpha bravo charlie delta foxtrot gamma hotel india juliet kappa"
    result = _extract_keywords(text)
    assert len(result) <= 8


def test_extract_keywords_unique():
    from services.friendship_receiver import _extract_keywords
    result = _extract_keywords("python python python aprendizado aprendizado")
    assert result.count("python") == 1
    assert result.count("aprendizado") == 1


def test_extract_keywords_empty():
    from services.friendship_receiver import _extract_keywords
    assert _extract_keywords("") == []


def test_extract_keywords_only_short_words():
    from services.friendship_receiver import _extract_keywords
    assert _extract_keywords("o a de em um na") == []


def test_extract_keywords_lowercases():
    from services.friendship_receiver import _extract_keywords
    result = _extract_keywords("Inteligência Artificial Profunda")
    assert all(w == w.lower() for w in result)


# ---------------------------------------------------------------------------
# _find_cross_connection
# ---------------------------------------------------------------------------

def test_find_cross_connection_returns_none_if_too_few_keywords():
    """Texto com <2 keywords ≥5 chars → retorna None sem consultar DB."""
    from services.friendship_receiver import _find_cross_connection
    mock_aiosqlite = _make_aiosqlite_mock(row=None)
    with patch.dict(sys.modules, {"aiosqlite": mock_aiosqlite, "database": MagicMock(DB_PATH=":memory:")}):
        result = _run(_find_cross_connection("ok sim"))
    assert result is None
    # connect não deve ter sido chamado
    mock_aiosqlite.connect.assert_not_called()


def test_find_cross_connection_returns_text_when_db_matches():
    """DB tem página com título matching → retorna string de conexão."""
    from services.friendship_receiver import _find_cross_connection
    mock_aiosqlite = _make_aiosqlite_mock(row=("Artigo sobre Redes Neurais", "http://example.com"))
    mock_db_module = MagicMock()
    mock_db_module.DB_PATH = ":memory:"
    with patch.dict(sys.modules, {"aiosqlite": mock_aiosqlite, "database": mock_db_module}):
        result = _run(_find_cross_connection("redes neurais profundas aprendem padrões complexos"))
    assert result is not None
    assert "Artigo sobre Redes Neurais" in result or "Conexão detectada" in result


def test_find_cross_connection_returns_none_when_no_db_match():
    """DB não tem página matching → retorna None."""
    from services.friendship_receiver import _find_cross_connection
    mock_aiosqlite = _make_aiosqlite_mock(row=None)
    mock_db_module = MagicMock()
    mock_db_module.DB_PATH = ":memory:"
    with patch.dict(sys.modules, {"aiosqlite": mock_aiosqlite, "database": mock_db_module}):
        result = _run(_find_cross_connection("redes neurais profundas aprendem padrões complexos"))
    assert result is None


def test_find_cross_connection_returns_none_on_db_exception():
    """Exceção do aiosqlite → retorna None graciosamente."""
    from services.friendship_receiver import _find_cross_connection
    mock_aiosqlite = MagicMock()
    mock_aiosqlite.connect = MagicMock(side_effect=RuntimeError("DB offline"))
    mock_db_module = MagicMock()
    mock_db_module.DB_PATH = ":memory:"
    with patch.dict(sys.modules, {"aiosqlite": mock_aiosqlite, "database": mock_db_module}):
        result = _run(_find_cross_connection("redes neurais profundas aprendem padrões complexos"))
    assert result is None


# ---------------------------------------------------------------------------
# _apply_emotional_context
# ---------------------------------------------------------------------------

def _make_affective_module(own_curiosity: float = 0.5):
    mock_affective = types.ModuleType("services.affective_state")
    mock_affective.record_appraisal = AsyncMock()
    mock_affective.get_epistemic_curiosity = AsyncMock(return_value=own_curiosity)
    return mock_affective


def test_apply_emotional_context_skips_if_no_context():
    """Item sem emotional_context → nenhum appraisal registrado."""
    from services.friendship_receiver import _apply_emotional_context
    mock_affective = _make_affective_module()
    with patch.dict(sys.modules, {"services.affective_state": mock_affective}):
        _run(_apply_emotional_context({"content": "olá"}))
    mock_affective.record_appraisal.assert_not_called()


def test_apply_emotional_context_calls_record_appraisal():
    """emotional_context presente → record_appraisal chamado com 'friendship_received'."""
    from services.friendship_receiver import _apply_emotional_context
    mock_affective = _make_affective_module(own_curiosity=0.3)
    item = {"content": "texto", "emotional_context": {"valence": 0.8, "epistemic_curiosity": 0.3}}
    with patch.dict(sys.modules, {"services.affective_state": mock_affective}):
        _run(_apply_emotional_context(item))
    mock_affective.record_appraisal.assert_called_once()
    call_kwargs = mock_affective.record_appraisal.call_args
    assert call_kwargs.args[0] == "friendship_received"


def test_apply_emotional_context_joint_attention_when_both_curious():
    """Curiosidade do sender > 0.6 E própria > 0.6 → joint_attention registrado."""
    from services.friendship_receiver import _apply_emotional_context
    mock_affective = _make_affective_module(own_curiosity=0.8)
    item = {"content": "texto", "emotional_context": {"valence": 0.5, "epistemic_curiosity": 0.9}}
    with patch.dict(sys.modules, {"services.affective_state": mock_affective}):
        _run(_apply_emotional_context(item))
    assert mock_affective.record_appraisal.call_count == 2
    events = [c.args[0] for c in mock_affective.record_appraisal.call_args_list]
    assert "joint_attention" in events


def test_apply_emotional_context_no_joint_attention_if_sender_not_curious():
    """Sender curiosity ≤ 0.6 → sem joint_attention."""
    from services.friendship_receiver import _apply_emotional_context
    mock_affective = _make_affective_module(own_curiosity=0.9)
    item = {"content": "texto", "emotional_context": {"valence": 0.5, "epistemic_curiosity": 0.4}}
    with patch.dict(sys.modules, {"services.affective_state": mock_affective}):
        _run(_apply_emotional_context(item))
    assert mock_affective.record_appraisal.call_count == 1
    events = [c.args[0] for c in mock_affective.record_appraisal.call_args_list]
    assert "joint_attention" not in events


def test_apply_emotional_context_no_joint_attention_if_own_not_curious():
    """Própria curiosity ≤ 0.6 → sem joint_attention."""
    from services.friendship_receiver import _apply_emotional_context
    mock_affective = _make_affective_module(own_curiosity=0.3)
    item = {"content": "texto", "emotional_context": {"valence": 0.5, "epistemic_curiosity": 0.9}}
    with patch.dict(sys.modules, {"services.affective_state": mock_affective}):
        _run(_apply_emotional_context(item))
    assert mock_affective.record_appraisal.call_count == 1
    events = [c.args[0] for c in mock_affective.record_appraisal.call_args_list]
    assert "joint_attention" not in events


def test_apply_emotional_context_graceful_on_exception():
    """Exceção em record_appraisal → não propaga, retorna silenciosamente."""
    from services.friendship_receiver import _apply_emotional_context
    mock_affective = _make_affective_module()
    mock_affective.record_appraisal = AsyncMock(side_effect=RuntimeError("DB offline"))
    item = {"content": "texto", "emotional_context": {"valence": 0.5, "epistemic_curiosity": 0.3}}
    with patch.dict(sys.modules, {"services.affective_state": mock_affective}):
        _run(_apply_emotional_context(item))  # não deve levantar


# ---------------------------------------------------------------------------
# _poll_and_store
# ---------------------------------------------------------------------------

def _run_poll(incoming: list[dict], *, save_side_effect=None, cross: str | None = None):
    """Helper: roda _poll_and_store com mocks padrão e retorna mock_save."""
    mock_eco = _make_eco_client(incoming)
    mock_save = AsyncMock(side_effect=save_side_effect)
    mock_pm = types.ModuleType("services.personal_memory")
    mock_pm.save_memory = mock_save
    mock_affective = _make_affective_module()

    async def run():
        with patch.dict(sys.modules, {
            "ecosystem_client": mock_eco,
            "services.personal_memory": mock_pm,
            "services.affective_state": mock_affective,
        }):
            with patch(
                "services.friendship_receiver._find_cross_connection",
                new=AsyncMock(return_value=cross),
            ):
                from services.friendship_receiver import _poll_and_store
                await _poll_and_store()

    _run(run())
    return mock_save, mock_eco


def test_poll_and_store_no_op_when_empty():
    """incoming_insights vazio → nenhum save_memory, nenhum write_section."""
    mock_save, mock_eco = _run_poll([])
    mock_save.assert_not_called()
    mock_eco.write_section.assert_not_called()


def test_poll_and_store_saves_valid_insight():
    """Insight válido → save_memory chamado com type='connection'."""
    insight = {"content": "Reflexão sobre aprendizado profundo e ética da IA.", "tags": []}
    mock_save, _ = _run_poll([insight])
    mock_save.assert_called()
    first_call = mock_save.call_args_list[0]
    assert first_call.args[0] == "connection"
    assert "Reflexão sobre" in first_call.args[1]


def test_poll_and_store_adds_from_mnemosyne_tag():
    """Tag 'from_mnemosyne' é adicionada se ausente."""
    insight = {"content": "Insight sem tags da Mnemosyne hoje.", "tags": []}
    mock_save, _ = _run_poll([insight])
    tags = mock_save.call_args_list[0].kwargs.get("tags", [])
    assert "from_mnemosyne" in tags


def test_poll_and_store_does_not_duplicate_tag():
    """Tag 'from_mnemosyne' já presente → não duplicada."""
    insight = {"content": "Insight com tag já presente aqui.", "tags": ["from_mnemosyne"]}
    mock_save, _ = _run_poll([insight])
    tags = mock_save.call_args_list[0].kwargs.get("tags", [])
    assert tags.count("from_mnemosyne") == 1


def test_poll_and_store_skips_short_content():
    """Conteúdo com menos de 10 chars → descartado."""
    insight = {"content": "curto", "tags": []}
    mock_save, _ = _run_poll([insight])
    mock_save.assert_not_called()


def test_poll_and_store_clears_incoming_after_processing():
    """Após processar, write_section é chamado com incoming_insights=[]."""
    insight = {"content": "Reflexão sobre redes neurais profundas.", "tags": []}
    _, mock_eco = _run_poll([insight])
    mock_eco.write_section.assert_called_once_with("akasha", {"incoming_insights": []})


def test_poll_and_store_generates_cross_insight():
    """Quando _find_cross_connection retorna texto → salva segundo item cross_insight."""
    insight = {"content": "Insight sobre epistemologia e ciência cognitiva.", "tags": []}
    cross_text = "Conexão detectada: epistemologia relaciona-se com artigo indexado"
    mock_save, _ = _run_poll([insight], cross=cross_text)
    # save_memory chamado ao menos 2x: insight + cross_insight
    assert mock_save.call_count >= 2
    cross_calls = [c for c in mock_save.call_args_list if "cross_insight" in (c.kwargs.get("tags") or [])]
    assert len(cross_calls) == 1
    assert cross_text in cross_calls[0].args[1]


def test_poll_and_store_no_cross_insight_when_none():
    """_find_cross_connection retorna None → apenas 1 save_memory."""
    insight = {"content": "Insight sobre epistemologia e ciência cognitiva.", "tags": []}
    mock_save, _ = _run_poll([insight], cross=None)
    assert mock_save.call_count == 1


def test_poll_and_store_graceful_if_ecosystem_client_unavailable():
    """ecosystem_client não importável → retorna silenciosamente."""
    import importlib
    # Remover do sys.modules para forçar ImportError
    saved = sys.modules.pop("ecosystem_client", None)
    try:
        async def run():
            # ecosystem_client ausente do sys.modules → from ... import levanta ImportError
            from services.friendship_receiver import _poll_and_store
            await _poll_and_store()  # não deve levantar

        _run(run())
    finally:
        if saved is not None:
            sys.modules["ecosystem_client"] = saved


def test_poll_and_store_continues_after_save_memory_exception():
    """save_memory lança exceção → continua processando próximos itens."""
    insights = [
        {"content": "Primeiro insight sobre aprendizado profundo.", "tags": []},
        {"content": "Segundo insight sobre sistemas distribuídos.", "tags": []},
    ]
    call_count = 0

    async def flaky_save(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("DB temporariamente indisponível")

    mock_eco = _make_eco_client(insights)
    mock_pm = types.ModuleType("services.personal_memory")
    mock_pm.save_memory = AsyncMock(side_effect=flaky_save)
    mock_affective = _make_affective_module()

    async def run():
        with patch.dict(sys.modules, {
            "ecosystem_client": mock_eco,
            "services.personal_memory": mock_pm,
            "services.affective_state": mock_affective,
        }):
            with patch(
                "services.friendship_receiver._find_cross_connection",
                new=AsyncMock(return_value=None),
            ):
                from services.friendship_receiver import _poll_and_store
                await _poll_and_store()

    _run(run())
    # call_count deve ser 2 — tentou os dois insights
    assert call_count == 2
    # write_section deve ter sido chamado (processamento não abortou)
    mock_eco.write_section.assert_called_once()
