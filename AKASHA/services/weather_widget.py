"""
AKASHA — Widget de clima
Geocoding via Nominatim (OSM) + dados via Open-Meteo (sem API key).
Cache de geocoding em akasha.db por 30 dias (tabela geo_cache).
"""
from __future__ import annotations

import hashlib
import re
import time

import aiosqlite
import httpx

from config import DB_PATH

_GEO_TTL = 30 * 86400  # 30 dias

_CLIMATE_TERMS = {
    "tempo", "clima", "temperatura", "chuva", "previsão", "previsao",
    "weather", "forecast", "rain", "sunny", "cloud", "storm", "hoje",
    "amanhã", "amanha", "semana", "agora", "now", "como", "qual",
    "está", "esta", "esta",
}

_CONDITION_CODES: dict[int, str] = {
    0: "Céu limpo", 1: "Principalmente claro", 2: "Parcialmente nublado",
    3: "Nublado", 45: "Neblina", 48: "Neblina com geada",
    51: "Garoa leve", 53: "Garoa moderada", 55: "Garoa densa",
    61: "Chuva fraca", 63: "Chuva moderada", 65: "Chuva forte",
    71: "Neve fraca", 73: "Neve moderada", 75: "Neve forte",
    80: "Pancadas de chuva", 81: "Pancadas moderadas", 82: "Pancadas fortes",
    95: "Tempestade", 99: "Tempestade com granizo",
}

# preposições que precedem o nome de cidade
_CITY_PREPS = r"(?:em|in|para|de|for|at)\s+"


def _city_key(city: str) -> str:
    return hashlib.md5(city.lower().strip().encode("utf-8")).hexdigest()


def extract_city(query: str) -> str | None:
    """Extrai nome de cidade de uma query de clima.

    Tenta 3 estratégias em ordem:
    1. Token(s) após preposição locativa (em, in, para, de, for, at)
    2. Token não-stopword ≥4 chars ausente da lista de termos de clima
    3. Retorna None
    """
    q = query.strip()

    # Estratégia 1: preposição + cidade
    m = re.search(
        _CITY_PREPS + r"([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\s\-]{1,40}?)(?:\s*$|\s+(?:hoje|amanhã|agora|now))",
        q,
        re.IGNORECASE,
    )
    if m:
        candidate = m.group(1).strip()
        words = [w for w in candidate.split() if w.lower() not in _CLIMATE_TERMS]
        if words:
            return " ".join(words).title()

    # Estratégia 2: primeiro token ≥4 chars fora dos termos de clima
    tokens = re.findall(r"[A-Za-zÀ-ɏ]{4,}", q)
    for tok in tokens:
        if tok.lower() not in _CLIMATE_TERMS:
            return tok.title()

    return None


def _default_city() -> str:
    try:
        import ecosystem_client as _ec  # type: ignore
        cfg = (_ec.read_ecosystem() or {}).get("akasha", {})
        return (cfg.get("default_city", "") or "").strip()
    except Exception:
        return ""


async def _get_geo_cache(city_hash: str) -> tuple[float, float] | None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            row = await (await db.execute(
                "SELECT lat, lon, cached_at FROM geo_cache WHERE city_key = ?",
                (city_hash,),
            )).fetchone()
        if not row:
            return None
        lat, lon, cached_at = row
        if time.time() > cached_at + _GEO_TTL:
            return None
        return float(lat), float(lon)
    except Exception:
        return None


async def _set_geo_cache(city_hash: str, lat: float, lon: float) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO geo_cache (city_key, lat, lon, cached_at) "
                "VALUES (?, ?, ?, ?)",
                (city_hash, lat, lon, int(time.time())),
            )
            await db.commit()
    except Exception:
        pass


async def _geocode(city: str) -> tuple[float, float] | None:
    """Resolve cidade → (lat, lon) via Nominatim, com cache local."""
    ck = _city_key(city)
    cached = await _get_geo_cache(ck)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(
            timeout=5.0,
            headers={"User-Agent": "AKASHA/1.0 (personal search engine; contact: local)"},
        ) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "json", "limit": "1"},
            )
            resp.raise_for_status()
            results = resp.json()
        if not results:
            return None
        lat = float(results[0]["lat"])
        lon = float(results[0]["lon"])
    except Exception:
        return None

    await _set_geo_cache(ck, lat, lon)
    return lat, lon


async def get_weather_card(query: str) -> dict | None:
    """Retorna card de clima para a cidade extraída da query, ou None se falhar."""
    city = extract_city(query) or _default_city()
    if not city:
        return None

    coords = await _geocode(city)
    if not coords:
        return None
    lat, lon = coords

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude":  str(lat),
                    "longitude": str(lon),
                    "current_weather":  "true",
                    "daily": "temperature_2m_max,temperature_2m_min,"
                             "precipitation_probability_max,weathercode",
                    "forecast_days": "4",
                    "timezone": "auto",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    cw = data.get("current_weather") or {}
    temp = cw.get("temperature")
    code = int(cw.get("weathercode", 0))
    condition = _CONDITION_CODES.get(code, "Desconhecido")

    daily = data.get("daily") or {}
    dates = daily.get("time", [])
    maxes = daily.get("temperature_2m_max", [])
    mins  = daily.get("temperature_2m_min", [])
    prec  = daily.get("precipitation_probability_max", [])
    codes = daily.get("weathercode", [])

    forecast: list[dict] = []
    for i in range(1, min(4, len(dates))):
        forecast.append({
            "date":      dates[i] if i < len(dates) else "",
            "temp_max":  maxes[i] if i < len(maxes) else None,
            "temp_min":  mins[i]  if i < len(mins)  else None,
            "precip":    prec[i]  if i < len(prec)  else None,
            "condition": _CONDITION_CODES.get(
                int(codes[i]) if i < len(codes) else 0, ""
            ),
        })

    return {
        "city":      city,
        "temp":      temp,
        "condition": condition,
        "forecast":  forecast,
    }
