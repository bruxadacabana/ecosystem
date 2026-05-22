"""
Testes unitários para AKASHA/services/affective_state.py.

Cobre apenas funções puras — sem acesso a DB, sem rede, sem asyncio:
  - compute_va: mapeamento CPM → (valence, arousal)
  - get_emotional_framing: instrução gerada a partir do estado afetivo
  - _apply_mood_modulation: amplificação/amortecimento por humor de fundo
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# compute_va
# ---------------------------------------------------------------------------

class TestComputeVa:
    """Cobre os casos extremos e intermediários do mapeamento CPM → VA."""

    def _va(self, novelty=0.5, pleasantness=0.5, goal_relevance=0.5, coping_potential=0.5):
        from services.affective_state import compute_va
        return compute_va(novelty, pleasantness, goal_relevance, coping_potential)

    def test_all_neutral_returns_near_zero_valence(self):
        v, a = self._va(0.5, 0.5, 0.5, 0.5)
        assert abs(v) < 0.1, f"valência esperada ≈ 0, obteve {v}"

    def test_high_pleasantness_gives_positive_valence(self):
        v, a = self._va(novelty=0.3, pleasantness=1.0, goal_relevance=0.5, coping_potential=0.8)
        assert v > 0.3, f"pleasantness alta deve dar valência positiva, obteve {v}"

    def test_low_pleasantness_gives_negative_valence(self):
        v, a = self._va(novelty=0.3, pleasantness=0.0, goal_relevance=0.5, coping_potential=0.5)
        assert v < -0.2, f"pleasantness baixa deve dar valência negativa, obteve {v}"

    def test_high_novelty_low_coping_gives_negative_valence(self):
        # Novidade alta + coping baixo = confusão → valência negativa
        v, a = self._va(novelty=1.0, pleasantness=0.5, goal_relevance=0.5, coping_potential=0.0)
        assert v < 0, f"alta novidade + baixo coping deve ser negativo, obteve {v}"

    def test_high_novelty_high_coping_gives_positive_valence(self):
        # Novidade alta + coping alto = curiosidade → valência positiva
        v, a = self._va(novelty=1.0, pleasantness=0.5, goal_relevance=0.5, coping_potential=1.0)
        assert v > 0, f"alta novidade + alto coping deve ser positivo, obteve {v}"

    def test_high_novelty_increases_arousal(self):
        _, a_low  = self._va(novelty=0.0, pleasantness=0.5, goal_relevance=0.5, coping_potential=0.5)
        _, a_high = self._va(novelty=1.0, pleasantness=0.5, goal_relevance=0.5, coping_potential=0.5)
        assert a_high > a_low, "novidade alta deve elevar o arousal"

    def test_valence_clamped_to_minus_one_one(self):
        # Caso extremo: deve ser clamped em [-1, 1]
        v, _ = self._va(novelty=1.0, pleasantness=0.0, goal_relevance=1.0, coping_potential=0.0)
        assert -1.0 <= v <= 1.0, f"valência fora do intervalo [-1,1]: {v}"

    def test_arousal_clamped_to_zero_one(self):
        _, a = self._va(novelty=1.0, pleasantness=1.0, goal_relevance=1.0, coping_potential=0.0)
        assert 0.0 <= a <= 1.0, f"arousal fora do intervalo [0,1]: {a}"

    def test_output_rounded_to_4_decimals(self):
        v, a = self._va(0.333, 0.666, 0.777, 0.888)
        assert v == round(v, 4)
        assert a == round(a, 4)

    def test_returns_tuple_of_two_floats(self):
        result = self._va(0.5, 0.5, 0.5, 0.5)
        assert isinstance(result, tuple) and len(result) == 2
        assert all(isinstance(x, float) for x in result)


# ---------------------------------------------------------------------------
# get_emotional_framing
# ---------------------------------------------------------------------------

class TestGetEmotionalFraming:
    """Verifica que a instrução textual é gerada corretamente para cada estado."""

    def _frame(self, state):
        from services.affective_state import get_emotional_framing
        return get_emotional_framing(state)

    def _baseline(self):
        return {
            "valence": 0.0, "arousal": 0.0,
            "epistemic_curiosity": 0.0,
            "novelty": 0.5, "pleasantness": 0.5,
            "goal_relevance": 0.5, "coping_potential": 0.5,
        }

    def test_neutral_state_returns_empty(self):
        result = self._frame(self._baseline())
        assert result == "", f"estado neutro deve retornar ''; obteve: {result!r}"

    def test_high_positive_valence_returns_exploratory_framing(self):
        state = {**self._baseline(), "valence": 0.5}
        result = self._frame(state)
        assert "exploratório" in result.lower(), \
            f"valência positiva deve gerar framing exploratório: {result!r}"

    def test_negative_valence_returns_analytical_framing(self):
        state = {**self._baseline(), "valence": -0.3}
        result = self._frame(state)
        assert "analítico" in result.lower() or "crítico" in result.lower(), \
            f"valência negativa deve gerar framing analítico: {result!r}"

    def test_high_curiosity_appends_followup_instruction(self):
        state = {**self._baseline(), "epistemic_curiosity": 0.7}
        result = self._frame(state)
        assert "follow-up" in result.lower() or "pergunta" in result.lower(), \
            f"curiosidade alta deve gerar instrução de follow-up: {result!r}"

    def test_borderline_valence_below_threshold_is_empty(self):
        state = {**self._baseline(), "valence": 0.35}  # < 0.4
        result = self._frame(state)
        assert result == "", f"valência 0.35 está abaixo do threshold 0.4; esperava '' "

    def test_borderline_negative_valence_above_threshold_is_empty(self):
        state = {**self._baseline(), "valence": -0.1}  # > -0.2
        result = self._frame(state)
        assert result == "", f"valência -0.1 está acima do threshold -0.2; esperava ''"

    def test_framing_starts_with_modulacao_header(self):
        state = {**self._baseline(), "valence": 0.5}
        result = self._frame(state)
        assert "[Modulação contextual]" in result

    def test_missing_keys_do_not_crash(self):
        result = self._frame({})
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _apply_mood_modulation (via importação direta da função interna)
# ---------------------------------------------------------------------------

class TestApplyMoodModulation:
    """Verifica a modulação de emoção episódica pelo humor de fundo."""

    def _modulate(self, valence, mood_valence):
        import services.affective_state as _m
        _m._mood_cache = {"valence": mood_valence, "arousal": 0.0}
        return _m._apply_mood_modulation(valence)

    def test_neutral_mood_no_change(self):
        result = self._modulate(0.5, 0.0)
        assert result == 0.5, "humor neutro não deve alterar a valência"

    def test_positive_mood_amplifies_positive_valence(self):
        result = self._modulate(0.5, 0.4)
        assert result > 0.5, "humor positivo deve amplificar valência positiva"

    def test_positive_mood_dampens_negative_valence(self):
        result = self._modulate(-0.5, 0.4)
        assert abs(result) < 0.5, "humor positivo deve amortecer valência negativa"

    def test_result_is_rounded_to_4_decimals(self):
        result = self._modulate(0.333, 0.2)
        assert result == round(result, 4)
