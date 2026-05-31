"""
Testes para Config 1–4 — aba de configurações e widget de clima.

Config 1 — routers/settings.py:
  - GET /settings retorna 200 com HTML
  - POST /settings persiste no ecosystem.json
  - GET /settings após POST reflete o novo valor
  - POST /settings com valores inválidos usa defaults (não explode)
  - Campos booleanos ausentes no POST salvam como False

Config 2 — settings.html:
  - Template contém as 6 seções obrigatórias
  - Campos de formulário corretos presentes

Config 3 — base.html navbar:
  - Link ⚙ para /settings aparece em páginas que herdam base.html
  - active_tab=settings marca o link como ativo

Config 4 — weather:
  - classify_intent_lexical: novos termos disparam weather
  - classify_intent_lexical: frases compostas disparam weather
  - weather_card = {"no_city": True} quando intent=weather e sem cidade
  - _default_city lê de ecosystem.json via read_ecosystem
  - Busca "vai chover hoje" → weather intent
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def client():
    from main import app  # noqa: PLC0415
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Config 1 — GET/POST /settings
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_settings_get_returns_200(client):
    resp = await client.get("/settings")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.anyio
async def test_settings_get_contains_form(client):
    resp = await client.get("/settings")
    assert '<form method="post" action="/settings"' in resp.text


@pytest.mark.anyio
async def test_settings_post_persists_and_redirects(client):
    """POST /settings deve redirecionar para /settings?saved=1."""
    with (
        patch("routers.settings._read_cfg", return_value={}),
        patch("routers.settings._save_cfg") as mock_save,
    ):
        resp = await client.post(
            "/settings",
            data={"default_city": "Curitiba", "max_per_domain": "3",
                  "web_pages": "2", "semantic_search": "on"},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert "saved=1" in resp.headers.get("location", "")
    mock_save.assert_called_once()
    saved = mock_save.call_args[0][0]
    assert saved["default_city"] == "Curitiba"
    assert saved["max_per_domain"] == 3
    assert saved["web_pages"] == 2
    assert saved["semantic_search"] is True


@pytest.mark.anyio
async def test_settings_saved_banner_shown_after_redirect(client):
    """GET /settings?saved=1 mostra banner de sucesso."""
    resp = await client.get("/settings?saved=1")
    assert "Configurações salvas" in resp.text


@pytest.mark.anyio
async def test_settings_post_invalid_int_uses_default(client):
    """Valores inválidos para campos numéricos usam defaults."""
    with (
        patch("routers.settings._read_cfg", return_value={}),
        patch("routers.settings._save_cfg") as mock_save,
    ):
        await client.post(
            "/settings",
            data={"max_per_domain": "nao-é-numero", "web_pages": "abc"},
            follow_redirects=False,
        )
    saved = mock_save.call_args[0][0]
    assert saved["max_per_domain"] == 5   # default
    assert saved["web_pages"] == 4        # default


@pytest.mark.anyio
async def test_settings_post_unchecked_checkbox_saves_false(client):
    """Checkbox não enviada no POST → salva como False."""
    with (
        patch("routers.settings._read_cfg", return_value={}),
        patch("routers.settings._save_cfg") as mock_save,
    ):
        # Não enviar "semantic_search" → deve ser False
        await client.post("/settings", data={}, follow_redirects=False)
    saved = mock_save.call_args[0][0]
    assert saved["semantic_search"] is False
    assert saved["reranking"] is False
    assert saved["save_search_history"] is False


@pytest.mark.anyio
async def test_settings_post_web_pages_clamped(client):
    """web_pages fora do range 1–10 é limitado."""
    with (
        patch("routers.settings._read_cfg", return_value={}),
        patch("routers.settings._save_cfg") as mock_save,
    ):
        await client.post(
            "/settings",
            data={"web_pages": "99"},
            follow_redirects=False,
        )
    saved = mock_save.call_args[0][0]
    assert saved["web_pages"] == 10


@pytest.mark.anyio
async def test_settings_post_search_languages_list(client):
    """Múltiplos idiomas são salvos como lista."""
    with (
        patch("routers.settings._read_cfg", return_value={}),
        patch("routers.settings._save_cfg") as mock_save,
    ):
        await client.post(
            "/settings",
            content=b"search_languages=pt&search_languages=en",
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
    saved = mock_save.call_args[0][0]
    assert set(saved["search_languages"]) == {"pt", "en"}


# ---------------------------------------------------------------------------
# Config 2 — settings.html contém as 6 seções
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_settings_html_has_all_sections(client):
    resp = await client.get("/settings")
    html = resp.text
    assert "Busca" in html
    assert "Localização" in html
    assert "Fontes preferidas" in html
    assert "Backends" in html
    assert "IA" in html
    assert "Privacidade" in html


@pytest.mark.anyio
async def test_settings_html_has_key_fields(client):
    resp = await client.get("/settings")
    html = resp.text
    assert 'name="max_per_domain"' in html
    assert 'name="web_pages"' in html
    assert 'name="search_languages"' in html
    assert 'name="default_city"' in html
    assert 'name="web_search_backend"' in html
    assert 'name="semantic_search"' in html
    assert 'name="deep_research_max_docs"' in html
    assert 'name="save_search_history"' in html


# ---------------------------------------------------------------------------
# Config 3 — navbar contém link ⚙ para /settings
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_navbar_has_settings_link(client):
    """Link ⚙ para /settings aparece em qualquer página com base.html."""
    resp = await client.get("/")
    assert 'href="/settings"' in resp.text


@pytest.mark.anyio
async def test_settings_page_marks_navbar_active(client):
    """Página /settings marca o link ⚙ como ativo."""
    resp = await client.get("/settings")
    # O link deve ter nav-link-active quando active_tab='settings'
    assert "nav-link-active" in resp.text and 'href="/settings"' in resp.text


# ---------------------------------------------------------------------------
# Config 4 — weather: novos termos e frases
# ---------------------------------------------------------------------------

def test_classify_intent_frio():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("frio hoje") == "weather"


def test_classify_intent_calor():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("muito calor amanhã") == "weather"


def test_classify_intent_geada():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("risco de geada esta semana") == "weather"


def test_classify_intent_granizo():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("granizo previsto") == "weather"


def test_classify_intent_trovoada():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("trovoada a tarde") == "weather"


def test_classify_intent_neblina():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("neblina na estrada") == "weather"


def test_classify_intent_phrase_vai_chover():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("vai chover hoje?") == "weather"


def test_classify_intent_phrase_vai_fazer_frio():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("vai fazer frio amanhã") == "weather"


def test_classify_intent_phrase_como_esta_o_tempo():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("como está o tempo lá fora") == "weather"


def test_classify_intent_phrase_guarda_chuva():
    from services.query_understanding import classify_intent_lexical
    assert classify_intent_lexical("precisa de guarda-chuva hoje") == "weather"


# ---------------------------------------------------------------------------
# Config 4 — weather_card no_city quando sem cidade configurada
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_weather_no_city_banner_shown(client):
    """Busca com intent weather + sem cidade → banner de configuração no HTML."""
    with (
        patch("services.weather_widget.get_weather_card", new_callable=AsyncMock, return_value=None),
        patch("services.weather_widget.extract_city", return_value=None),
        patch("services.weather_widget._default_city", return_value=""),
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.classify_intent_lexical", return_value="weather"),
        patch("routers.search._get_intent_routing", return_value={
            "weather": True, "wiki": False, "images": False,
            "translation": False, "video": False,
        }),
    ):
        resp = await client.get("/search", params={"q": "vai chover hoje", "src_web": "on"})
    assert resp.status_code == 200
    assert "Configure sua cidade" in resp.text
    assert 'href="/settings"' in resp.text


@pytest.mark.anyio
async def test_weather_with_city_shows_card_not_banner(client):
    """Com cidade configurada, mostra o card normal (não o banner)."""
    fake_card = {
        "city": "Curitiba", "temp": 18.5, "condition": "Parcialmente nublado",
        "forecast": [], "no_city": False,
    }
    with (
        patch("services.weather_widget.get_weather_card", new_callable=AsyncMock, return_value=fake_card),
        patch("routers.search.search_web", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_local", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.search_sites", new_callable=AsyncMock, return_value=[]),
        patch("routers.search.classify_intent_lexical", return_value="weather"),
        patch("routers.search._get_intent_routing", return_value={
            "weather": True, "wiki": False, "images": False,
            "translation": False, "video": False,
        }),
    ):
        resp = await client.get("/search", params={"q": "temperatura curitiba", "src_web": "on"})
    assert resp.status_code == 200
    assert "Curitiba" in resp.text
    assert "Configure sua cidade" not in resp.text


# ---------------------------------------------------------------------------
# Config 4 — _default_city usa read_ecosystem, não get_akasha_config
# ---------------------------------------------------------------------------

def test_default_city_reads_from_read_ecosystem():
    mock_ec = MagicMock()
    mock_ec.read_ecosystem.return_value = {"akasha": {"default_city": "São Paulo"}}
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        import importlib
        import services.weather_widget as ww
        importlib.reload(ww)
        result = ww._default_city()
    assert result == "São Paulo"


def test_default_city_returns_empty_on_error():
    mock_ec = MagicMock()
    mock_ec.read_ecosystem.side_effect = RuntimeError("offline")
    with patch.dict("sys.modules", {"ecosystem_client": mock_ec}):
        import importlib
        import services.weather_widget as ww
        importlib.reload(ww)
        result = ww._default_city()
    assert result == ""
