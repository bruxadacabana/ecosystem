"""
Testes para services/weather_widget.py.

Cobre:
  - extract_city: "tempo em Lisboa" → "Lisboa"
  - extract_city: "clima para São Paulo" → "São Paulo"
  - extract_city: sem cidade → None
  - extract_city: fallback token ≥4 chars não-stopword
  - get_weather_card: geocode retorna coords → card com temp e forecast
  - get_weather_card: geocode falha → None
  - get_weather_card: Open-Meteo falha → None
  - get_weather_card: cidade no cache → Nominatim não chamado
  - get_weather_card: query sem cidade + default_city vazio → None
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# extract_city
# ---------------------------------------------------------------------------

def test_extract_city_em_preposition():
    from services.weather_widget import extract_city
    assert extract_city("tempo em Lisboa") == "Lisboa"


def test_extract_city_para_preposition():
    from services.weather_widget import extract_city
    result = extract_city("clima para São Paulo")
    assert result is not None
    assert "Paulo" in result or "Paulo" in result


def test_extract_city_in_english():
    from services.weather_widget import extract_city
    result = extract_city("weather in Madrid")
    assert result == "Madrid"


def test_extract_city_no_city_returns_none():
    from services.weather_widget import extract_city
    # Todos os tokens são termos de clima
    result = extract_city("tempo clima chuva previsão")
    assert result is None


def test_extract_city_fallback_token():
    from services.weather_widget import extract_city
    result = extract_city("temperatura Paris")
    assert result == "Paris"


def test_extract_city_strips_climate_terms():
    from services.weather_widget import extract_city
    result = extract_city("previsão de tempo em Porto hoje")
    assert result is not None
    assert "Porto" in result


# ---------------------------------------------------------------------------
# get_weather_card — via mocks
# ---------------------------------------------------------------------------

def _make_open_meteo_resp(temp: float = 22.5, code: int = 0) -> dict:
    return {
        "current_weather": {"temperature": temp, "weathercode": code, "windspeed": 10},
        "daily": {
            "time":                        ["2025-01-15", "2025-01-16", "2025-01-17", "2025-01-18"],
            "temperature_2m_max":          [24.0, 23.5, 22.0, 20.0],
            "temperature_2m_min":          [15.0, 14.5, 13.0, 12.0],
            "precipitation_probability_max": [10, 20, 50, 80],
            "weathercode":                 [0, 1, 61, 63],
        },
    }


@pytest.mark.anyio
async def test_get_weather_card_full_pipeline(monkeypatch):
    """Geocode retorna coords + Open-Meteo retorna dados → card completo."""
    import services.weather_widget as _ww

    async def _mock_geocode(city):
        assert city == "Lisboa"
        return (38.7169, -9.1395)

    monkeypatch.setattr(_ww, "_geocode", _mock_geocode)
    monkeypatch.setattr(_ww, "_default_city", lambda: "")

    import httpx
    payload = _make_open_meteo_resp(21.3, 1)
    request = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
    mock_resp = httpx.Response(200, content=json.dumps(payload).encode(), request=request)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        card = await _ww.get_weather_card("tempo em Lisboa")

    assert card is not None
    assert card["city"] == "Lisboa"
    assert card["temp"] == 21.3
    assert "claro" in card["condition"].lower() or card["condition"] != ""
    assert len(card["forecast"]) == 3


@pytest.mark.anyio
async def test_get_weather_card_geocode_fails_returns_none(monkeypatch):
    """Geocode retorna None → card não gerado."""
    import services.weather_widget as _ww

    async def _mock_geocode(city):
        return None

    monkeypatch.setattr(_ww, "_geocode", _mock_geocode)
    monkeypatch.setattr(_ww, "_default_city", lambda: "")

    result = await _ww.get_weather_card("tempo em CidadeInexistente")
    assert result is None


@pytest.mark.anyio
async def test_get_weather_card_open_meteo_error_returns_none(monkeypatch):
    """Open-Meteo lança exception → None."""
    import services.weather_widget as _ww

    async def _mock_geocode(city):
        return (0.0, 0.0)

    monkeypatch.setattr(_ww, "_geocode", _mock_geocode)
    monkeypatch.setattr(_ww, "_default_city", lambda: "")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=ConnectionError("timeout"))

    import httpx
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        result = await _ww.get_weather_card("tempo em TestCity")

    assert result is None


@pytest.mark.anyio
async def test_get_weather_card_no_city_no_default_returns_none(monkeypatch):
    """Sem cidade detectada e default_city vazio → None."""
    import services.weather_widget as _ww

    monkeypatch.setattr(_ww, "_default_city", lambda: "")

    result = await _ww.get_weather_card("tempo clima chuva previsão")
    assert result is None


@pytest.mark.anyio
async def test_get_weather_card_uses_default_city(monkeypatch):
    """Sem cidade na query, usa default_city do ecosystem.json."""
    import services.weather_widget as _ww

    monkeypatch.setattr(_ww, "_default_city", lambda: "Porto Alegre")
    geocode_calls: list[str] = []

    async def _mock_geocode(city):
        geocode_calls.append(city)
        return (None)  # falha intencionalmente para terminar cedo

    monkeypatch.setattr(_ww, "_geocode", _mock_geocode)

    await _ww.get_weather_card("tempo clima chuva previsão")
    assert geocode_calls == ["Porto Alegre"]


@pytest.mark.anyio
async def test_weather_geocode_cache_hit_skips_nominatim(tmp_path, monkeypatch):
    """Cache HIT → Nominatim não é chamado."""
    import services.weather_widget as _ww
    monkeypatch.setattr(_ww, "DB_PATH", tmp_path / "akasha.db")

    async def _fake_get_geo_cache(city_hash):
        return (38.7, -9.1)

    monkeypatch.setattr(_ww, "_get_geo_cache", _fake_get_geo_cache)

    nominatim_called: list[bool] = []

    import httpx
    original_client = httpx.AsyncClient

    class _FailIfCalledWithNominatim:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url, **kw):
            if "nominatim" in str(url):
                nominatim_called.append(True)
            # Para Open-Meteo, retorna resposta mínima válida
            payload = _make_open_meteo_resp()
            request = httpx.Request("GET", url)
            return httpx.Response(200, content=json.dumps(payload).encode(), request=request)

    with patch.object(httpx, "AsyncClient", _FailIfCalledWithNominatim):
        await _ww._geocode("Lisboa")

    assert nominatim_called == [], "Nominatim não deve ser chamado com cache HIT"
