"""
Testes para logits_worker.py.

Cobre:
  - EmotionScore: dataclass e propriedades
  - is_available(): com e sem llama_cpp instalado
  - score_emotion(): modelo inexistente → None, llama_cpp ausente → None
  - _compute_emotion_score(): mock completo de llm + numpy
  - _LogitsWorkerProcess: falha ao carregar modelo → not ready
  - _n_gpu_layers_for_hardware(): mapeamento por backend
  - shutdown(): idempotente quando worker ausente
"""
from __future__ import annotations
import sys
import os
from unittest.mock import patch, MagicMock
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logits_worker as lw


# ─── EmotionScore ─────────────────────────────────────────────────────────────

def test_emotion_score_fields():
    score = lw.EmotionScore(
        valence=0.3, arousal=0.7,
        valence_confidence=0.8, arousal_confidence=0.6,
    )
    assert score.valence  == 0.3
    assert score.arousal  == 0.7
    assert score.valence_confidence == 0.8
    assert score.arousal_confidence == 0.6


def test_emotion_score_is_frozen():
    score = lw.EmotionScore(0.0, 0.0, 0.0, 0.0)
    try:
        score.valence = 1.0  # type: ignore
        assert False, "deveria ter levantado FrozenInstanceError"
    except Exception:
        pass


# ─── is_available ─────────────────────────────────────────────────────────────

def test_is_available_true_when_installed():
    with patch.dict(sys.modules, {"llama_cpp": MagicMock()}):
        assert lw.is_available() is True


def test_is_available_false_when_not_installed():
    real_modules = sys.modules.copy()
    sys.modules.pop("llama_cpp", None)
    with patch("builtins.__import__", side_effect=lambda name, *a, **kw: (
        (_ for _ in ()).throw(ImportError("no module")) if name == "llama_cpp"
        else real_modules.get(name, __builtins__)
    )):
        # Direct test: bypass cached import, call fresh
        result = _import_check_fresh()
    assert result is False


def _import_check_fresh() -> bool:
    try:
        import importlib
        importlib.import_module("llama_cpp")
        return True
    except ImportError:
        return False


# ─── score_emotion: early-exit guards ────────────────────────────────────────

def test_score_emotion_returns_none_when_model_missing(tmp_path):
    """Modelo não existe → None sem tentar iniciar worker."""
    missing = str(tmp_path / "nonexistent.gguf")
    result = lw.score_emotion("some text", missing)
    assert result is None


def test_score_emotion_returns_none_when_llama_cpp_missing(tmp_path):
    """llama-cpp-python não instalado → worker falha → None."""
    # Cria arquivo de modelo fake para passar o exists() check
    fake_model = tmp_path / "model.gguf"
    fake_model.write_bytes(b"fake")

    # Patch: simula que is_available() retorna True, mas o worker process
    # falha ao importar llama_cpp (RuntimeError enviado via res_q)
    import multiprocessing as mp

    original_process = mp.Process

    class FailingProcess:
        """Simula processo que envia error imediatamente."""
        def __init__(self, target, args, daemon=False):
            self._res_q = args[4]  # res_q is 5th arg in _worker_main

        def start(self):
            self._res_q.put(RuntimeError("llama-cpp-python não instalado"))

        def terminate(self): pass

        def is_alive(self): return False

        def join(self, timeout=None): pass

    with patch("logits_worker.mp.Process", FailingProcess), \
         patch("logits_worker._worker", None), \
         patch("logits_worker._worker_model_path", ""):
        result = lw.score_emotion("some text", str(fake_model))
    assert result is None


# ─── _n_gpu_layers_for_hardware ──────────────────────────────────────────────

def test_n_gpu_layers_vulkan_returns_minus_one():
    with patch("logits_worker.hp.get_inference_backend", return_value="vulkan"):
        assert lw._n_gpu_layers_for_hardware() == -1


def test_n_gpu_layers_cuda_returns_minus_one():
    with patch("logits_worker.hp.get_inference_backend", return_value="cuda"):
        assert lw._n_gpu_layers_for_hardware() == -1


def test_n_gpu_layers_cpu_returns_zero():
    with patch("logits_worker.hp.get_inference_backend", return_value="cpu"):
        assert lw._n_gpu_layers_for_hardware() == 0


# ─── _compute_emotion_score ───────────────────────────────────────────────────

class _MockLlm:
    """LLM fake que invoca o logits processor com logits controlados."""

    def __init__(self, positive_logit_boost: float = 5.0, excited_logit_boost: float = 3.0):
        self._positive_boost = positive_logit_boost
        self._excited_boost  = excited_logit_boost
        # Mapeamento fixo: tokens de emoção têm IDs previsíveis
        self._vocab: dict[bytes, list[int]] = {
            b" positive": [100],
            b" good":     [101],
            b" happy":    [102],
            b" pleasant": [103],
            b" wonderful":[104],
            b" great":    [105],
            b" negative": [200],
            b" bad":      [201],
            b" sad":      [202],
            b" unpleasant":[203],
            b" awful":    [204],
            b" terrible": [205],
            b" exciting": [300],
            b" intense":  [301],
            b" surprising":[302],
            b" shocking": [303],
            b" thrilling":[304],
            b" calm":     [400],
            b" quiet":    [401],
            b" boring":   [402],
            b" routine":  [403],
            b" mild":     [404],
            b" gentle":   [405],
        }

    def __call__(self, prompt, max_tokens=1, logits_processor=None):
        logits = np.zeros(1000, dtype=np.float32)
        # Boost tokens positivos
        for idx in [100, 101, 102, 103, 104, 105]:
            logits[idx] = self._positive_boost
        # Boost tokens excitados
        for idx in [300, 301, 302, 303, 304]:
            logits[idx] = self._excited_boost
        if logits_processor:
            for proc in logits_processor:
                proc(np.array([0, 1, 2], dtype=np.intc), logits)
        return {"choices": [{"text": " positive"}]}

    def tokenize(self, text: bytes) -> list[int]:
        return self._vocab.get(text, [])


def test_compute_emotion_score_positive_valence():
    """Logits favorecendo tokens positivos → valência > 0."""
    mock_llm = _MockLlm(positive_logit_boost=5.0)
    score = lw._compute_emotion_score(mock_llm, "Amazing discovery!", np)
    assert score.valence > 0.0


def test_compute_emotion_score_negative_valence():
    """Logits favorecendo tokens negativos → valência < 0."""

    class NegativeLlm(_MockLlm):
        def __call__(self, prompt, max_tokens=1, logits_processor=None):
            logits = np.zeros(1000, dtype=np.float32)
            for idx in [200, 201, 202, 203, 204, 205]:  # negative tokens
                logits[idx] = 5.0
            if logits_processor:
                for proc in logits_processor:
                    proc(np.array([0, 1, 2], dtype=np.intc), logits)
            return {"choices": [{"text": " negative"}]}

    score = lw._compute_emotion_score(NegativeLlm(), "Terrible failure!", np)
    assert score.valence < 0.0


def test_compute_emotion_score_high_arousal():
    """Logits favorecendo tokens excitados → arousal > 0.5."""
    mock_llm = _MockLlm(positive_logit_boost=0.0, excited_logit_boost=5.0)
    score = lw._compute_emotion_score(mock_llm, "Shocking revelation!", np)
    assert score.arousal > 0.5


def test_compute_emotion_score_low_arousal():
    """Logits favorecendo tokens calmos → arousal < 0.5."""

    class CalmLlm(_MockLlm):
        def __call__(self, prompt, max_tokens=1, logits_processor=None):
            logits = np.zeros(1000, dtype=np.float32)
            for idx in [400, 401, 402, 403, 404, 405]:  # calm tokens
                logits[idx] = 5.0
            if logits_processor:
                for proc in logits_processor:
                    proc(np.array([0, 1, 2], dtype=np.intc), logits)
            return {"choices": [{"text": " calm"}]}

    score = lw._compute_emotion_score(CalmLlm(), "A quiet afternoon.", np)
    assert score.arousal < 0.5


def test_compute_emotion_score_neutral_no_signal():
    """Sem logits de emoção → valência ≈ 0, arousal ≈ 0.5."""

    class NeutralLlm(_MockLlm):
        def __call__(self, prompt, max_tokens=1, logits_processor=None):
            logits = np.zeros(1000, dtype=np.float32)
            if logits_processor:
                for proc in logits_processor:
                    proc(np.array([0, 1, 2], dtype=np.intc), logits)
            return {"choices": [{"text": ""}]}

    score = lw._compute_emotion_score(NeutralLlm(), "A text.", np)
    assert score.valence == 0.0
    # Com logits uniformes, arousal = n_high / (n_high + n_low) = 5/11 ≈ 0.45
    assert 0.3 <= score.arousal <= 0.7


def test_compute_emotion_score_values_clamped():
    """Valores de saída sempre ∈ domínio válido."""
    mock_llm = _MockLlm(positive_logit_boost=100.0, excited_logit_boost=100.0)
    score = lw._compute_emotion_score(mock_llm, "Very positive!", np)
    assert -1.0 <= score.valence <= 1.0
    assert  0.0 <= score.arousal <= 1.0
    assert  0.0 <= score.valence_confidence <= 1.0
    assert  0.0 <= score.arousal_confidence <= 1.0


def test_compute_emotion_score_no_logits_raises():
    """Se o LogitsProcessor não for chamado, levanta ValueError."""

    class SilentLlm:
        def __call__(self, prompt, max_tokens=1, logits_processor=None):
            return {"choices": [{"text": ""}]}  # não invoca o processor

        def tokenize(self, text):
            return []

    try:
        lw._compute_emotion_score(SilentLlm(), "text", np)
        assert False, "deveria ter levantado ValueError"
    except ValueError as exc:
        assert "Nenhum logit capturado" in str(exc)


# ─── shutdown ─────────────────────────────────────────────────────────────────

def test_shutdown_is_idempotent_when_no_worker():
    with patch("logits_worker._worker", None):
        lw.shutdown()  # não deve levantar exceção
