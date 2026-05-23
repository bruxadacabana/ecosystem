"""
Cliente HTTP mínimo para o backend de inferência — detecção de disponibilidade e listagem de modelos.
Não depende do pacote ollama, usa apenas urllib da stdlib.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .errors import OllamaUnavailableError


_TIMEOUT = 2  # segundos

# Fragmentos de nome que identificam modelos de embedding
_EMBED_HINTS = ("embed", "nomic", "mxbai", "bge", "e5", "minilm", "qwen3")

try:
    from ecosystem_client import get_inference_url as _get_inference_url
except ImportError:
    def _get_inference_url() -> str:  # type: ignore[misc]
        return "http://localhost:8080"


def _base_url() -> str:
    return _get_inference_url()


@dataclass
class OllamaModel:
    name: str
    size: int = 0
    modified_at: str = ""


def check_inference() -> bool:
    """Retorna True se o backend de inferência responde no endpoint /health; False caso contrário."""
    try:
        urllib.request.urlopen(f"{_base_url()}/health", timeout=_TIMEOUT)
        return True
    except Exception:
        return False


def check_ollama() -> bool:
    """Alias de check_inference() — mantido para compatibilidade com código legado."""
    return check_inference()


def list_models() -> list[OllamaModel]:
    """
    Retorna os modelos disponíveis no backend de inferência via GET /v1/models.

    Raises:
        OllamaUnavailableError: se o backend não estiver acessível ou retornar dados inválidos.
    """
    try:
        with urllib.request.urlopen(
            f"{_base_url()}/v1/models", timeout=_TIMEOUT
        ) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise OllamaUnavailableError(f"Backend de inferência inacessível: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OllamaUnavailableError(f"Resposta inválida do backend: {exc}") from exc

    return [OllamaModel(name=m.get("id", "")) for m in data.get("data", [])]


def filter_embed_models(models: list[OllamaModel]) -> list[OllamaModel]:
    """Filtra modelos de embedding pelo nome."""
    return [m for m in models if any(h in m.name.lower() for h in _EMBED_HINTS)]


def filter_chat_models(models: list[OllamaModel]) -> list[OllamaModel]:
    """Retorna modelos que não são de embedding (presumidos como modelos de chat/LLM)."""
    embed_names = {m.name for m in filter_embed_models(models)}
    return [m for m in models if m.name not in embed_names]


def validate_model(model_name: str) -> None:
    """
    Verifica se um modelo específico está disponível no backend de inferência.

    Raises:
        OllamaUnavailableError: se o backend não estiver acessível.
        ModelNotFoundError: se o modelo não estiver instalado.
    """
    from .errors import ModelNotFoundError

    models = list_models()
    names = {m.name for m in models}
    if model_name not in names:
        raise ModelNotFoundError(model_name)
