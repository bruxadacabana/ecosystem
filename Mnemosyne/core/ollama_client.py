"""
Cliente HTTP mínimo para o Ollama — detecção de disponibilidade e listagem de modelos.
Não depende do pacote ollama, usa apenas urllib da stdlib.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .errors import OllamaUnavailableError


_BASE_URL = "http://localhost:7072"   # LOGOS proxy; fallback direto via Ollama 11434
_TIMEOUT = 2  # segundos

# Fragmentos de nome que identificam modelos de embedding
_EMBED_HINTS = ("embed", "nomic", "mxbai", "bge", "e5", "minilm")


@dataclass
class OllamaModel:
    name: str
    size: int        # bytes
    modified_at: str


def check_ollama() -> bool:
    """Retorna True se o Ollama responde no endereço padrão; False caso contrário."""
    try:
        urllib.request.urlopen(_BASE_URL, timeout=_TIMEOUT)
        return True
    except Exception:
        return False


def list_models() -> list[OllamaModel]:
    """
    Retorna os modelos disponíveis localmente no Ollama.

    Raises:
        OllamaUnavailableError: se o Ollama não estiver acessível ou retornar dados inválidos.
    """
    try:
        with urllib.request.urlopen(
            f"{_BASE_URL}/api/tags", timeout=_TIMEOUT
        ) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise OllamaUnavailableError(f"Ollama inacessível: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OllamaUnavailableError(f"Resposta inválida do Ollama: {exc}") from exc

    models: list[OllamaModel] = []
    for m in data.get("models", []):
        models.append(
            OllamaModel(
                name=m.get("name", ""),
                size=m.get("size", 0),
                modified_at=m.get("modified_at", ""),
            )
        )
    return models


def filter_embed_models(models: list[OllamaModel]) -> list[OllamaModel]:
    """Filtra modelos de embedding pelo nome."""
    return [m for m in models if any(h in m.name.lower() for h in _EMBED_HINTS)]


def filter_chat_models(models: list[OllamaModel]) -> list[OllamaModel]:
    """Retorna modelos que não são de embedding (presumidos como modelos de chat/LLM)."""
    embed_names = {m.name for m in filter_embed_models(models)}
    return [m for m in models if m.name not in embed_names]


def validate_model(model_name: str) -> None:
    """
    Verifica se um modelo específico está disponível no Ollama.

    Raises:
        OllamaUnavailableError: se o Ollama não estiver acessível.
        ModelNotFoundError: se o modelo não estiver instalado.
    """
    from .errors import ModelNotFoundError

    models = list_models()
    names = {m.name for m in models}
    if model_name not in names:
        raise ModelNotFoundError(model_name)
