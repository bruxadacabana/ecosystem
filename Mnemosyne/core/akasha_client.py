"""
Cliente HTTP para a API REST do AKASHA (porta 7071).

Endpoints esperados (Fase 13 do AKASHA):
  GET  /health          → {"status": "ok", ...}
  GET  /search/json     → list[{url, title, snippet}]
  POST /fetch           → {url, title, content_md, word_count}

is_available() e search() são síncronos.
fetch() é assíncrono — usar com asyncio.gather para paralelismo.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from .errors import AkashaFetchError, AkashaOfflineError

_BASE_URL = "http://localhost:7071"
_HEALTH_TIMEOUT = 2.0
_DEFAULT_TIMEOUT = 15.0


@dataclass
class AkashaResult:
    url: str
    title: str
    snippet: str


@dataclass
class FetchResult:
    url: str
    title: str
    content_md: str
    word_count: int


class AkashaClient:
    """
    Cliente para a API REST do AKASHA.

    Uso típico no worker:
        client = AkashaClient()
        if not client.is_available():
            raise AkashaOfflineError()
        results = client.search(query, max_results=5)
        pages = asyncio.run(asyncio.gather(*[client.fetch(r.url) for r in results]))
    """

    def __init__(self, base_url: str = _BASE_URL) -> None:
        self._base = base_url.rstrip("/")

    def is_available(self) -> bool:
        """Verifica se o AKASHA está acessível. Timeout de 2s."""
        try:
            r = httpx.get(f"{self._base}/health", timeout=_HEALTH_TIMEOUT)
            return r.status_code == 200
        except (httpx.TransportError, OSError):
            return False

    def search(self, query: str, max_results: int = 5) -> list[AkashaResult]:
        """
        Busca no AKASHA via GET /search/json.

        Raises:
            AkashaOfflineError: se o AKASHA não estiver acessível.
            AkashaFetchError: se a resposta for inválida.
        """
        try:
            r = httpx.get(
                f"{self._base}/search/json",
                params={"q": query, "max": max_results},
                timeout=_DEFAULT_TIMEOUT,
            )
        except httpx.ConnectError as exc:
            raise AkashaOfflineError() from exc
        except httpx.TimeoutException as exc:
            raise AkashaOfflineError() from exc
        except httpx.TransportError as exc:
            raise AkashaOfflineError() from exc

        if r.status_code != 200:
            raise AkashaFetchError(
                f"AKASHA retornou status {r.status_code} em /search/json"
            )

        try:
            items: list = r.json()
        except (ValueError, TypeError) as exc:
            raise AkashaFetchError(f"Resposta inválida do AKASHA: {exc}") from exc

        results: list[AkashaResult] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            results.append(AkashaResult(
                url=item["url"],
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
            ))
            if len(results) >= max_results:
                break
        return results

    async def fetch(self, url: str) -> FetchResult:
        """
        Busca e processa uma URL via POST /fetch.
        Assíncrono — usar com asyncio.gather para paralelismo.

        Raises:
            AkashaOfflineError: se o AKASHA não estiver acessível.
            AkashaFetchError: se a URL não puder ser processada.
        """
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                r = await client.post(f"{self._base}/fetch", json={"url": url})
        except httpx.ConnectError as exc:
            raise AkashaOfflineError() from exc
        except httpx.TimeoutException as exc:
            raise AkashaFetchError(f"Timeout ao buscar {url}") from exc
        except httpx.TransportError as exc:
            raise AkashaFetchError(f"Erro de transporte ao buscar {url}: {exc}") from exc

        if r.status_code != 200:
            raise AkashaFetchError(
                f"AKASHA retornou status {r.status_code} para {url}"
            )

        try:
            data: dict = r.json()
        except (ValueError, TypeError) as exc:
            raise AkashaFetchError(f"Resposta inválida do AKASHA para {url}: {exc}") from exc

        return FetchResult(
            url=data.get("url", url),
            title=data.get("title", ""),
            content_md=data.get("content_md", ""),
            word_count=int(data.get("word_count", 0)),
        )

    def fetch_sync(self, url: str) -> FetchResult:
        """Wrapper síncrono de fetch() — conveniente quando asyncio.gather não é necessário."""
        return asyncio.run(self.fetch(url))

    def send_feedback(self, url: str, is_positive: bool) -> None:
        """Envia feedback de utilidade de uma URL ao AKASHA via POST /friendship/feedback.

        Usado pelo ciclo emocional do Collab 3: quando a Mnemosyne avalia positivamente
        um documento web que o AKASHA indexou, notifica a AKASHA para gerar appraisal.

        Raises:
            AkashaOfflineError: se o AKASHA não estiver acessível.
            AkashaFetchError: se a resposta for inválida.
        """
        try:
            r = httpx.post(
                f"{self._base}/friendship/feedback",
                json={"url": url, "is_positive": is_positive},
                timeout=_DEFAULT_TIMEOUT,
            )
        except httpx.ConnectError as exc:
            raise AkashaOfflineError() from exc
        except httpx.TimeoutException as exc:
            raise AkashaFetchError(f"Timeout ao enviar feedback para {url}") from exc
        except httpx.TransportError as exc:
            raise AkashaFetchError(f"Erro de transporte ao enviar feedback: {exc}") from exc

        if r.status_code not in (200, 204):
            raise AkashaFetchError(
                f"AKASHA retornou status {r.status_code} em /friendship/feedback"
            )

    def dialogue_turn(
        self,
        question: str,
        context: list[str],
        turn_index: int,
        fragment_cb,   # (text: str) -> None — chamado para cada fragmento SSE
        sources_cb,    # (sources: list[dict]) -> None — chamado ao receber sources
        stop_check,    # () -> bool — retorna True para interromper
        timeout: float = 30.0,
    ) -> None:
        """
        Chama POST /dialogue/turn no AKASHA e itera o stream SSE.

        Chama fragment_cb(text) para cada fragmento de texto recebido.
        Chama sources_cb(sources) ao receber o evento de fontes.
        Retorna silenciosamente se AKASHA estiver offline ou parar for solicitado.

        Raises:
            AkashaOfflineError: se a conexão falhar.
            AkashaFetchError: se a resposta for inválida.
        """
        import json as _json

        payload = {
            "question":   question,
            "context":    context,
            "turn_index": turn_index,
        }
        try:
            with httpx.stream(
                "POST",
                f"{self._base}/dialogue/turn",
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status_code != 200:
                    raise AkashaFetchError(
                        f"AKASHA /dialogue/turn retornou status {resp.status_code}"
                    )
                for raw_line in resp.iter_lines():
                    if stop_check():
                        break
                    line = raw_line.strip() if raw_line else ""
                    if not line.startswith("data:"):
                        continue
                    payload_str = line[5:].strip()
                    if payload_str == "[DONE]":
                        break
                    try:
                        event = _json.loads(payload_str)
                    except _json.JSONDecodeError:
                        continue
                    if event.get("type") == "fragment":
                        text = event.get("text", "")
                        if text:
                            fragment_cb(text)
                    elif event.get("type") == "sources":
                        sources_cb(event.get("sources", []))
        except httpx.ConnectError as exc:
            raise AkashaOfflineError() from exc
        except httpx.TimeoutException as exc:
            raise AkashaFetchError("Timeout em /dialogue/turn") from exc
        except httpx.TransportError as exc:
            raise AkashaFetchError(f"Erro de transporte em /dialogue/turn: {exc}") from exc
