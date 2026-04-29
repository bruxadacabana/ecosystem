"""Cliente Ollama para geração de texto e embeddings semânticos."""

from __future__ import annotations

import json
import logging
import struct
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Generator

import requests

if TYPE_CHECKING:
    pass

log = logging.getLogger("kosmos.ai")

# ecosystem_client: proxy LOGOS para serialização de chamadas LLM
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ecosystem_client import request_llm as _request_llm  # noqa: E402

DEFAULT_ENDPOINT = "http://localhost:7072"   # LOGOS proxy; fallback a 11434 nas Settings


class OllamaError(Exception):
    """Erro de comunicação com o Ollama."""


class AiBridge:
    """Interface com o servidor Ollama local.

    Os modelos não têm padrão — devem ser configurados explicitamente
    pelo usuário nas Settings. Chamar generate() ou embed() sem um
    modelo configurado levanta OllamaError.

    Uso::

        bridge = AiBridge(endpoint, gen_model="qwen2.5:7b",
                          embed_model="nomic-embed-text")
        if bridge.is_available():
            summary = bridge.generate(prompt, system=SYSTEM_SUMMARY)
            vec     = bridge.embed(article_text)
            blob    = AiBridge.vec_to_blob(vec)
    """

    def __init__(
        self,
        endpoint:    str = DEFAULT_ENDPOINT,
        gen_model:   str = "",
        embed_model: str = "",
    ) -> None:
        self._endpoint    = endpoint.rstrip("/")
        self._gen_model   = gen_model
        self._embed_model = embed_model
        self._session     = requests.Session()

    # ------------------------------------------------------------------
    # Disponibilidade
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Retorna True se o Ollama está acessível no endpoint configurado."""
        try:
            r = self._session.get(f"{self._endpoint}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Lista nomes dos modelos instalados localmente.

        Raises:
            OllamaError: se a requisição falhar.
        """
        try:
            r = self._session.get(f"{self._endpoint}/api/tags", timeout=5)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except requests.RequestException as exc:
            raise OllamaError(f"Não foi possível listar modelos: {exc}") from exc

    # ------------------------------------------------------------------
    # Geração de texto
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt:      str,
        system:      str        = "",
        json_format: bool       = False,
        json_schema: dict | None = None,
        num_ctx:     int  | None = None,
        priority:    int        = 3,
        timeout:     int        = 120,
    ) -> str:
        """Gera texto completo (sem streaming).

        Args:
            prompt:      Prompt do usuário.
            system:      Instrução de sistema opcional.
            json_format: Se True, força saída JSON simples via ``format: "json"``.
            json_schema: JSON Schema completo para constrained decoding (sobrepõe json_format).
            num_ctx:     Janela de contexto explícita (necessário para KV prefix cache).
            priority:    Prioridade LOGOS (1=P1 interativo, 2=P2, 3=P3 background).
            timeout:     Timeout em segundos.

        Returns:
            Texto gerado pelo modelo.

        Raises:
            OllamaError: em falha de rede ou resposta inesperada.
        """
        if not self._gen_model:
            raise OllamaError(
                "Nenhum modelo de geração configurado. "
                "Escolha um em Configurações → IA."
            )
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        options: dict = {}
        if json_schema is not None:
            options["format"] = json_schema
        elif json_format:
            options["format"] = "json"
        if num_ctx is not None:
            options["options"] = {"num_ctx": num_ctx}

        try:
            result = _request_llm(
                messages,
                app="kosmos",
                model=self._gen_model,
                priority=priority,
                stream=False,
                ollama_base=self._endpoint,
                **options,
            )
            return result.get("message", {}).get("content", "")
        except RuntimeError as exc:
            raise OllamaError(str(exc)) from exc

    def generate_stream(
        self,
        prompt:  str,
        system:  str = "",
        timeout: int = 120,
    ) -> Generator[str, None, None]:
        """Gera texto em streaming — yields tokens à medida que chegam.

        Raises:
            OllamaError: em falha de conexão.
        """
        if not self._gen_model:
            raise OllamaError(
                "Nenhum modelo de geração configurado. "
                "Escolha um em Configurações → IA."
            )
        payload: dict = {
            "model":  self._gen_model,
            "prompt": prompt,
            "stream": True,
        }
        if system:
            payload["system"] = system

        try:
            with self._session.post(
                f"{self._endpoint}/api/generate",
                json=payload,
                headers={"X-App": "kosmos", "X-Priority": "1"},
                timeout=timeout,
                stream=True,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        except requests.RequestException as exc:
            raise OllamaError(f"Erro no streaming: {exc}") from exc

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, text: str, timeout: int = 30) -> list[float]:
        """Gera vetor de embedding para o texto.

        Returns:
            Lista de floats (dimensão depende do modelo configurado).

        Raises:
            OllamaError: em falha de rede, modelo não configurado ou resposta inesperada.
        """
        if not self._embed_model:
            raise OllamaError(
                "Nenhum modelo de embeddings configurado. "
                "Escolha um em Configurações → IA."
            )
        try:
            r = self._session.post(
                f"{self._endpoint}/api/embed",
                json={"model": self._embed_model, "input": text},
                headers={"X-App": "kosmos", "X-Priority": "3"},
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            # /api/embed retorna {"embeddings": [[...]]}
            raw = data.get("embeddings") or data.get("embedding")
            if not raw:
                raise OllamaError("Resposta sem campo 'embeddings'.")
            return raw[0] if isinstance(raw[0], list) else raw
        except requests.RequestException as exc:
            raise OllamaError(f"Erro ao gerar embedding: {exc}") from exc

    def embed_to_blob(self, text: str) -> bytes:
        """Gera embedding e serializa como BLOB (little-endian float32).

        Conveniente para persistir diretamente no SQLite.
        """
        return AiBridge.vec_to_blob(self.embed(text))

    # ------------------------------------------------------------------
    # Utilitários de vetores (estáticos)
    # ------------------------------------------------------------------

    @staticmethod
    def vec_to_blob(vec: list[float]) -> bytes:
        """Serializa um vetor de floats como BLOB little-endian float32."""
        return struct.pack(f"<{len(vec)}f", *vec)

    @staticmethod
    def blob_to_vec(blob: bytes) -> list[float]:
        """Desserializa um BLOB de volta para lista de floats."""
        n = len(blob) // 4
        return list(struct.unpack(f"<{n}f", blob))

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity entre dois vetores. Retorna 0.0 se inválidos."""
        if not a or not b or len(a) != len(b):
            return 0.0
        try:
            import numpy as np
            va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
            denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
            return float(np.dot(va, vb)) / denom if denom > 0.0 else 0.0
        except ImportError:
            dot    = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            return dot / (norm_a * norm_b) if norm_a * norm_b > 0.0 else 0.0

    @staticmethod
    def average_vecs(vecs: list[list[float]]) -> list[float]:
        """Calcula a média de uma lista de vetores (perfil de interesses).

        Retorna lista vazia se a entrada estiver vazia.
        """
        if not vecs:
            return []
        try:
            import numpy as np
            return np.mean(np.array(vecs, dtype=np.float32), axis=0).tolist()
        except ImportError:
            n   = len(vecs)
            dim = len(vecs[0])
            return [sum(v[i] for v in vecs) / n for i in range(dim)]
