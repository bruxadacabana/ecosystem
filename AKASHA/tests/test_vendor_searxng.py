"""
Testes estruturais do SearXNG vendorizado (3ª alternativa de busca, Windows-sem-Docker).

Offline — valida que o vendor está íntegro e Windows-safe:
- pacote searx presente (webapp, requirements, LICENSE);
- NENHUM arquivo com ':' no nome (proibido no Windows; quebraria o checkout do repo);
- versão congelada (`version_frozen.py`) presente, dispensando .git;
- stub `pwd` presente e levantando NotImplementedError (não devolve dados falsos);
- `settings.base.yml` é template e tem os requisitos do AKASHA (json, limiter off, porta).

O teste de runtime (servidor sobe + responde JSON) é manual/integração — depende de
instalar as deps do SearXNG e de rede.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

VENDOR = pathlib.Path(__file__).parent.parent / "vendor" / "searxng"


def test_vendor_tree_present():
    assert (VENDOR / "searx" / "webapp.py").is_file()
    assert (VENDOR / "requirements.txt").is_file()
    assert (VENDOR / "LICENSE").is_file()


def test_no_colon_in_filenames():
    """Nenhum arquivo/dir com ':' no nome — senão o repo não faz checkout no Windows."""
    offenders = [str(p) for p in VENDOR.rglob("*") if ":" in p.name]
    assert not offenders, f"arquivos com ':' no nome: {offenders}"


def test_version_frozen_present():
    vf = VENDOR / "searx" / "version_frozen.py"
    assert vf.is_file(), "version_frozen.py congela a versão sem depender de .git"
    assert "502c820" in vf.read_text(encoding="utf-8")


def test_pwd_stub_raises():
    stub = VENDOR / "_winshim" / "pwd.py"
    assert stub.is_file()
    spec = importlib.util.spec_from_file_location("_vendor_pwd_stub", stub)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(NotImplementedError):
        mod.getpwuid(0)
    with pytest.raises(NotImplementedError):
        mod.getpwnam("root")


def test_settings_base_template():
    txt = (VENDOR / "settings.base.yml").read_text(encoding="utf-8")
    assert "__SECRET_KEY__" in txt, "deve ser template (segredo gerado no setup)"
    assert "limiter: false" in txt
    assert "json" in txt           # formato json obrigatório p/ o AKASHA
    assert "8889" in txt           # porta dedicada da instância vendorizada
