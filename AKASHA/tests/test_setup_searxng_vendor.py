"""
Testes do setup do SearXNG vendorizado (geração de settings.yml + paths).

Offline — cobre a lógica pura (idempotência, substituição de secret, template
ausente, caminho do python do venv por plataforma). O passo de venv+install é
integração (uv + rede) e é validado manualmente.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

_MOD_PATH = pathlib.Path(__file__).parent.parent / "vendor" / "setup_searxng_vendor.py"
_spec = importlib.util.spec_from_file_location("setup_searxng_vendor", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

_TEMPLATE = (
    "server:\n"
    '  secret_key: "__SECRET_KEY__"\n'
    "  limiter: false\n"
    "  port: 8889\n"
)


def _write_template(d: pathlib.Path) -> None:
    (d / "settings.base.yml").write_text(_TEMPLATE, encoding="utf-8")


def test_ensure_settings_generates_secret(tmp_path):
    _write_template(tmp_path)
    out = mod.ensure_settings(tmp_path)
    assert out == tmp_path / "settings.yml"
    txt = out.read_text(encoding="utf-8")
    assert "__SECRET_KEY__" not in txt
    assert re.search(r'secret_key: "[0-9a-f]{64}"', txt), "secret de 64 hex deve estar presente"
    assert "limiter: false" in txt and "8889" in txt  # resto do template preservado


def test_ensure_settings_idempotent(tmp_path):
    _write_template(tmp_path)
    first = mod.ensure_settings(tmp_path).read_text(encoding="utf-8")
    second = mod.ensure_settings(tmp_path).read_text(encoding="utf-8")
    assert first == second, "segunda chamada não pode regenerar/alterar o segredo"


def test_ensure_settings_missing_template(tmp_path):
    with pytest.raises(FileNotFoundError):
        mod.ensure_settings(tmp_path)


def test_venv_python_path():
    p = mod.venv_python(pathlib.Path("/x"))
    assert ".venv" in str(p)
    assert p.name in ("python.exe", "python")


def test_real_vendor_template_exists():
    """O template real do vendor deve existir e ter os requisitos do AKASHA."""
    tpl = mod.VENDOR / "settings.base.yml"
    assert tpl.is_file()
    txt = tpl.read_text(encoding="utf-8")
    assert "__SECRET_KEY__" in txt and "json" in txt and "limiter: false" in txt
