"""
logits_worker — worker em processo separado para acesso a logits LLM.

Instancia llama_cpp.Llama com logits_all=True em PROCESSO SEPARADO do servidor
de inferência principal. Isolamento obrigatório: logits_all=True armazena logits
para todos os tokens, aumentando uso de memória e latência — não pode coexistir
no mesmo processo que serve chat P1.

Fluxo:
  1. Caller chama score_emotion(text, model_path) no processo principal.
  2. Se o worker não estiver ativo, _get_worker() inicia um multiprocessing.Process.
  3. O worker carrega o modelo, envia "ready", e aguarda tarefas na req_queue.
  4. score_emotion() envia ("score", text), aguarda resposta na res_queue.
  5. A resposta é um EmotionScore ou None (em caso de falha silenciosa).

Zero-shot via logits: sem classificador treinado, usa distribuição de probabilidade
sobre tokens de emoção (positive/negative/excited/calm) como proxy de valência/arousal.
O scorer treinado (QLoRA, item futuro) substituirá essa heurística quando disponível.

Uso::

    from logits_worker import score_emotion, is_available, shutdown

    if is_available():
        score = score_emotion("Text about a surprising discovery", "/path/to/model.gguf")
        if score:
            print(score.valence, score.arousal)
    shutdown()  # chamar no encerramento do processo
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import queue
from dataclasses import dataclass
from pathlib import Path

import hardware_probe as hp

log = logging.getLogger("ecosystem.logits_worker")

# Tokens de classificação zero-shot — vocabuário de emoção básico.
# Positivo/negativo → valência; excitado/calmo → arousal.
# Os tokens com espaço leading (" positive") correspondem ao tokenizer BPE padrão.
_VALENCE_POSITIVE = [" positive", " good", " happy", " pleasant", " wonderful", " great"]
_VALENCE_NEGATIVE = [" negative", " bad", " sad", " unpleasant", " awful", " terrible"]
_AROUSAL_HIGH     = [" exciting", " intense", " surprising", " shocking", " thrilling"]
_AROUSAL_LOW      = [" calm", " quiet", " boring", " routine", " mild", " gentle"]

# Contexto máximo para o worker de logits — pequeno porque só precisamos do último token.
_WORKER_N_CTX = 512


@dataclass(frozen=True)
class EmotionScore:
    """Pontuação emocional derivada dos logits do LLM.

    valence ∈ [−1, 1]: negativo = aversivo, positivo = agradável.
    arousal ∈ [0, 1]:  baixo = calmo, alto = ativado/intenso.
    *_confidence: quão dominante é o sinal no vocabulário (0–1).
    """
    valence:            float
    arousal:            float
    valence_confidence: float
    arousal_confidence: float


# ── Worker process ────────────────────────────────────────────────────────────

class _LogitsWorkerProcess:
    """Gerencia um processo filho que mantém Llama(logits_all=True) isolado."""

    def __init__(self, model_path: str, n_gpu_layers: int, n_ctx: int) -> None:
        self._req_q: mp.Queue = mp.Queue()
        self._res_q: mp.Queue = mp.Queue()
        self._ready = False
        self._proc = mp.Process(
            target=_worker_main,
            args=(model_path, n_gpu_layers, n_ctx, self._req_q, self._res_q),
            daemon=True,
        )
        self._proc.start()
        # Aguarda sinal de modelo carregado (pode demorar)
        try:
            msg = self._res_q.get(timeout=90.0)
            if isinstance(msg, Exception):
                log.warning("logits_worker: falha ao carregar modelo: %s", msg)
                self._proc.terminate()
            elif msg == "ready":
                self._ready = True
        except queue.Empty:
            log.warning("logits_worker: timeout aguardando modelo — terminando worker")
            self._proc.terminate()

    def is_ready(self) -> bool:
        return self._ready and self._proc.is_alive()

    def score(self, text: str, timeout: float = 30.0) -> EmotionScore | None:
        if not self.is_ready():
            return None
        self._req_q.put(("score", text))
        try:
            result = self._res_q.get(timeout=timeout)
        except queue.Empty:
            log.debug("logits_worker: timeout na pontuação")
            return None
        if isinstance(result, Exception):
            log.debug("logits_worker: %s", result)
            return None
        return result

    def shutdown(self) -> None:
        if self._proc.is_alive():
            self._req_q.put(("exit", None))
            self._proc.join(timeout=5)
            if self._proc.is_alive():
                self._proc.terminate()


def _worker_main(
    model_path: str,
    n_gpu_layers: int,
    n_ctx: int,
    req_q: mp.Queue,
    res_q: mp.Queue,
) -> None:
    """Corpo do processo filho. Não chamar diretamente — usado por _LogitsWorkerProcess."""
    try:
        from llama_cpp import Llama  # noqa: PLC0415
        import numpy as np           # noqa: PLC0415
    except ImportError as exc:
        res_q.put(RuntimeError(f"llama-cpp-python não instalado: {exc}"))
        return

    try:
        llm = Llama(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            logits_all=True,
            verbose=False,
        )
    except Exception as exc:
        res_q.put(RuntimeError(f"Falha ao carregar {model_path}: {exc}"))
        return

    res_q.put("ready")

    while True:
        cmd, payload = req_q.get()
        if cmd == "exit":
            break
        if cmd == "score":
            try:
                score = _compute_emotion_score(llm, payload, np)
                res_q.put(score)
            except Exception as exc:
                res_q.put(exc)


def _compute_emotion_score(llm: object, text: str, np: object) -> EmotionScore:
    """Extrai pontuação emocional via logits do último token de um prompt zero-shot.

    Captura os logits via callback registrado em logits_processor antes do sampling.
    LogitsProcessorList em llama_cpp é apenas um alias para list — usa lista direta
    para evitar dependência de import no caminho de teste.
    Calcula valência e arousal como razão de probabilidades entre tokens de emoção
    opostos no vocabulário.
    """
    captured: list = []

    def capture_processor(input_ids, scores):
        captured.append(scores.copy())
        return scores

    prompt = (
        f"Text: {text[:300]}\n\n"
        "The emotional tone of this text is"
    )
    # logits_processor aceita lista direta (LogitsProcessorList = List[...] em llama_cpp)
    llm(
        prompt,
        max_tokens=1,
        logits_processor=[capture_processor],
    )

    if not captured:
        raise ValueError("Nenhum logit capturado — LogitsProcessorList não foi invocado")

    logits = captured[-1]
    # Softmax manual — np importado como parâmetro para testabilidade
    exp_logits = np.exp(logits - np.max(logits))
    probs = exp_logits / exp_logits.sum()

    def vocab_prob(tokens: list[str]) -> float:
        total = 0.0
        for tok in tokens:
            ids = llm.tokenize(tok.encode())
            if ids:
                tid = int(ids[0])
                if 0 <= tid < len(probs):
                    total += float(probs[tid])
        return total

    p_pos = vocab_prob(_VALENCE_POSITIVE)
    p_neg = vocab_prob(_VALENCE_NEGATIVE)
    p_hi  = vocab_prob(_AROUSAL_HIGH)
    p_low = vocab_prob(_AROUSAL_LOW)

    total_v = p_pos + p_neg
    valence  = (p_pos - p_neg) / total_v if total_v > 1e-9 else 0.0
    v_conf   = min(1.0, total_v * 20.0)   # escala: 0.05 de prob total → conf≈1

    total_a  = p_hi + p_low
    arousal  = p_hi / total_a if total_a > 1e-9 else 0.5
    a_conf   = min(1.0, total_a * 20.0)

    return EmotionScore(
        valence=round(float(max(-1.0, min(1.0, valence))), 4),
        arousal=round(float(max(0.0,  min(1.0, arousal))), 4),
        valence_confidence=round(float(v_conf), 4),
        arousal_confidence=round(float(a_conf), 4),
    )


# ── API pública ───────────────────────────────────────────────────────────────

_worker: _LogitsWorkerProcess | None = None
_worker_model_path: str = ""


def _n_gpu_layers_for_hardware() -> int:
    """Retorna n_gpu_layers adequado para o hardware atual."""
    backend = hp.get_inference_backend()
    if backend in ("vulkan", "cuda"):
        return -1   # offload total para GPU
    return 0        # CPU-only (WorkPc sem AVX2)


def _get_worker(model_path: str, n_gpu_layers: int) -> _LogitsWorkerProcess:
    global _worker, _worker_model_path
    needs_restart = (
        _worker is None
        or not _worker.is_ready()
        or _worker_model_path != model_path
    )
    if needs_restart:
        if _worker is not None:
            _worker.shutdown()
        _worker = _LogitsWorkerProcess(model_path, n_gpu_layers, _WORKER_N_CTX)
        _worker_model_path = model_path
    return _worker


def score_emotion(
    text: str,
    model_path: str,
    n_gpu_layers: int | None = None,
    timeout: float = 30.0,
) -> EmotionScore | None:
    """Pontua emoção no texto via logits LLM em processo isolado.

    Retorna None se:
      - llama-cpp-python não estiver instalado
      - model_path não existir
      - worker falhar ao carregar o modelo
      - timeout atingido

    n_gpu_layers: None → detectado automaticamente via hardware_probe.
    Fallback silencioso — nunca levanta exceção.
    """
    if not Path(model_path).exists():
        log.debug("score_emotion: modelo não encontrado: %s", model_path)
        return None
    if n_gpu_layers is None:
        n_gpu_layers = _n_gpu_layers_for_hardware()
    try:
        worker = _get_worker(model_path, n_gpu_layers)
        return worker.score(text, timeout=timeout)
    except Exception as exc:
        log.debug("score_emotion: %s", exc)
        return None


def is_available() -> bool:
    """True se llama-cpp-python está instalado no ambiente atual."""
    try:
        import llama_cpp  # noqa: F401
        return True
    except ImportError:
        return False


def shutdown() -> None:
    """Desliga o worker se ativo. Chamar no encerramento do processo pai."""
    global _worker
    if _worker is not None:
        _worker.shutdown()
        _worker = None
