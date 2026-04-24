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
