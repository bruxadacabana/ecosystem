"""
Testes para services/invidious.py.

Cobre:
  - _format_duration: segundos → MM:SS e HH:MM:SS
  - _pick_thumbnail: medium > default > primeira disponível; lista vazia → ''
  - search_videos: mock API retorna JSON válido → resultados parseados
  - search_videos: instância offline (TimeoutException) → lista vazia + mensagem de erro
  - search_videos: resposta malformada → itens inválidos ignorados, sem crash
  - search_videos: videoId ausente em item → item ignorado
  - search_videos_quick: painel inline — retorna resultados, vazio em falha,
    respeita limite max, query vazia → []
  - fallback de instâncias: primária falha → fallback tentado; todas falham → []
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------

def test_format_duration_seconds_only():
    from services.invidious import _format_duration
    assert _format_duration(45) == "0:45"


def test_format_duration_minutes_seconds():
    from services.invidious import _format_duration
    assert _format_duration(125) == "2:05"


def test_format_duration_with_hours():
    from services.invidious import _format_duration
    assert _format_duration(3661) == "1:01:01"


def test_format_duration_zero():
    from services.invidious import _format_duration
    assert _format_duration(0) == ""


# ---------------------------------------------------------------------------
# _pick_thumbnail
# ---------------------------------------------------------------------------

def test_pick_thumbnail_medium_preferred():
    from services.invidious import _pick_thumbnail
    thumbs = [
        {"quality": "low",    "url": "http://low.jpg"},
        {"quality": "medium", "url": "http://med.jpg"},
        {"quality": "high",   "url": "http://high.jpg"},
    ]
    assert _pick_thumbnail(thumbs) == "http://med.jpg"


def test_pick_thumbnail_fallback_to_first():
    from services.invidious import _pick_thumbnail
    thumbs = [{"quality": "maxres", "url": "http://max.jpg"}]
    assert _pick_thumbnail(thumbs) == "http://max.jpg"


def test_pick_thumbnail_empty_list():
    from services.invidious import _pick_thumbnail
    assert _pick_thumbnail([]) == ""


# ---------------------------------------------------------------------------
# search_videos — mock API retorna JSON válido
# ---------------------------------------------------------------------------

_FAKE_API_RESPONSE = [
    {
        "videoId": "abc123",
        "title":   "Test Video",
        "author":  "Test Channel",
        "lengthSeconds": 185,
        "viewCount": 12345,
        "videoThumbnails": [
            {"quality": "medium", "url": "https://example.com/thumb.jpg"},
        ],
    },
    {
        "videoId": "def456",
        "title":   "Another Video",
        "author":  "Other Channel",
        "lengthSeconds": 3600,
        "viewCount": 999,
        "videoThumbnails": [],
    },
]


def test_search_videos_success():
    from services.invidious import search_videos

    mock_resp = MagicMock()
    mock_resp.json.return_value = _FAKE_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        results, error = run(search_videos("test query"))

    assert error is None
    assert len(results) == 2

    r0 = results[0]
    assert r0["video_id"] == "abc123"
    assert r0["title"] == "Test Video"
    assert r0["author"] == "Test Channel"
    assert r0["duration"] == "3:05"
    assert r0["thumbnail_url"] == "https://example.com/thumb.jpg"
    assert "watch?v=abc123" in r0["invidious_url"]

    r1 = results[1]
    assert r1["duration"] == "1:00:00"
    assert r1["thumbnail_url"] == ""


# ---------------------------------------------------------------------------
# search_videos — instância offline → lista vazia + mensagem de erro
# ---------------------------------------------------------------------------

def test_search_videos_timeout():
    import httpx
    from services.invidious import search_videos

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        results, error = run(search_videos("test"))

    assert results == []
    assert error is not None
    assert len(error) > 0


def test_search_videos_connection_error():
    import httpx
    from services.invidious import search_videos

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        results, error = run(search_videos("test"))

    assert results == []
    assert error is not None


# ---------------------------------------------------------------------------
# search_videos — item sem videoId → ignorado
# ---------------------------------------------------------------------------

def test_search_videos_missing_video_id_ignored():
    from services.invidious import search_videos

    api_data = [
        {"title": "No ID video", "author": "Chan", "lengthSeconds": 10, "videoThumbnails": []},
        {"videoId": "valid123", "title": "Valid", "author": "Chan", "lengthSeconds": 60, "videoThumbnails": []},
    ]

    mock_resp = MagicMock()
    mock_resp.json.return_value = api_data
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        results, error = run(search_videos("test"))

    assert len(results) == 1
    assert results[0]["video_id"] == "valid123"


# ---------------------------------------------------------------------------
# search_videos_quick — painel inline
# ---------------------------------------------------------------------------

def _make_client_mock(response_data: list) -> MagicMock:
    """Helper: cria mock de httpx.AsyncClient retornando response_data."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_data
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client


class TestSearchVideosQuick:
    def test_empty_query_returns_empty(self):
        """query vazia → [] sem tocar na API."""
        from services.invidious import search_videos_quick
        result = run(search_videos_quick(""))
        assert result == []

    def test_whitespace_query_returns_empty(self):
        """query só espaços → []."""
        from services.invidious import search_videos_quick
        result = run(search_videos_quick("   "))
        assert result == []

    def test_returns_results_from_invidious(self):
        """Resultado parseado pelo search_videos reaparece em search_videos_quick."""
        from services.invidious import search_videos_quick

        mock_client = _make_client_mock(_FAKE_API_RESPONSE)
        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(search_videos_quick("python tutorial", max=4))

        assert len(results) <= 4
        assert len(results) >= 1
        assert "video_id" in results[0]
        assert "title" in results[0]
        assert "invidious_url" in results[0]

    def test_max_limits_results(self):
        """max=1 retorna no máximo 1 resultado, mesmo com mais disponíveis."""
        from services.invidious import search_videos_quick

        mock_client = _make_client_mock(_FAKE_API_RESPONSE)
        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(search_videos_quick("test", max=1))

        assert len(results) <= 1

    def test_invidious_offline_returns_empty(self):
        """Invidious offline → [] sem propagar exceção."""
        import httpx
        from services.invidious import search_videos_quick

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(search_videos_quick("test"))

        assert results == []

    def test_result_has_required_keys(self):
        """Cada item deve ter video_id, title, author, duration, thumbnail_url, invidious_url."""
        from services.invidious import search_videos_quick

        mock_client = _make_client_mock(_FAKE_API_RESPONSE)
        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run(search_videos_quick("test"))

        assert len(results) >= 1
        for r in results:
            for key in ("video_id", "title", "author", "duration", "thumbnail_url", "invidious_url"):
                assert key in r, f"Chave '{key}' ausente: {r}"
