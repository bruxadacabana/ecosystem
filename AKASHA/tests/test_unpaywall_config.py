"""
Testes da configuração do e-mail Unpaywall/OpenAlex (BUG: e-mail pessoal hardcoded).

Garante que:
- `config.get_unpaywall_email()` lê o valor fresco do ecosystem.json, faz strip,
  trata vazio e degrada graciosamente em erro;
- o enriquecimento (`paper_search`) e o download (`paper_download`) via Unpaywall
  pulam graciosamente quando não há e-mail configurado (sem chamar HTTP);
- a chave `unpaywall_email` existe nos defaults do Settings (exposta na UI);
- regressão: nenhum e-mail pessoal hardcoded nos serviços.
"""
from __future__ import annotations

import pathlib

import pytest

import config


def test_get_unpaywall_email_reads_ecosystem(monkeypatch):
    monkeypatch.setattr(config, "_ECO_AVAILABLE", True)
    monkeypatch.setattr(config, "read_ecosystem",
                        lambda: {"akasha": {"unpaywall_email": "x@y.com"}})
    assert config.get_unpaywall_email() == "x@y.com"


def test_get_unpaywall_email_strips_and_empty(monkeypatch):
    monkeypatch.setattr(config, "_ECO_AVAILABLE", True)
    monkeypatch.setattr(config, "read_ecosystem",
                        lambda: {"akasha": {"unpaywall_email": "   "}})
    assert config.get_unpaywall_email() == ""


def test_get_unpaywall_email_missing_key(monkeypatch):
    monkeypatch.setattr(config, "_ECO_AVAILABLE", True)
    monkeypatch.setattr(config, "read_ecosystem", lambda: {"akasha": {}})
    assert config.get_unpaywall_email() == ""


def test_get_unpaywall_email_graceful_on_error(monkeypatch):
    monkeypatch.setattr(config, "_ECO_AVAILABLE", True)

    def _boom():
        raise RuntimeError("ecosystem indisponível")

    monkeypatch.setattr(config, "read_ecosystem", _boom)
    monkeypatch.setattr(config, "unpaywall_email", "fallback@e.com")
    assert config.get_unpaywall_email() == "fallback@e.com"


@pytest.mark.asyncio
async def test_enrich_unpaywall_skips_without_email(monkeypatch):
    import services.paper_search as ps

    monkeypatch.setattr(ps.config, "get_unpaywall_email", lambda: "")

    def _no_http(*a, **k):
        raise AssertionError("não deveria chamar httpx sem e-mail")

    monkeypatch.setattr(ps.httpx, "AsyncClient", _no_http)
    r = ps.PaperResult(title="t", url="http://u", snippet="s", doi="10.1/x")
    await ps._enrich_unpaywall([r])  # não deve levantar nem chamar HTTP
    assert not r.pdf_url


@pytest.mark.asyncio
async def test_fetch_unpaywall_none_without_email(monkeypatch):
    import httpx

    import services.paper_download as pd

    monkeypatch.setattr(pd.config, "get_unpaywall_email", lambda: "")
    async with httpx.AsyncClient() as client:
        assert await pd._fetch_unpaywall("10.1/x", client) is None


def test_unpaywall_email_in_settings_defaults():
    import routers.settings as s
    assert "unpaywall_email" in s._DEFAULTS, "campo precisa estar exposto no Settings (UI)"


def test_no_hardcoded_personal_email():
    """Regressão: nenhum e-mail pessoal hardcoded nos serviços."""
    services_dir = pathlib.Path(__file__).parent.parent / "services"
    for py in services_dir.glob("*.py"):
        txt = py.read_text(encoding="utf-8")
        assert "jenmangelo@gmail.com" not in txt, f"e-mail pessoal hardcoded em {py.name}"
