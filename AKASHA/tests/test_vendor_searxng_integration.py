"""
Testes de INTEGRAÇÃO do SearXNG vendorizado (condicionais ao venv instalado).

Pulam (skip) quando `vendor/searxng/.venv` não existe — então rodam na máquina que
fez o setup (item 2) e ficam silenciosos em CI/máquinas sem o vendor.

Cobrem o que os testes offline não conseguem:
  - `import searx.webapp` funciona no venv do vendor (com o stub `pwd` no PYTHONPATH
    no Windows) — prova que o remendo destrava a importação;
  - o servidor sobe e responde `/healthz` 200 e `/search?format=json` 200
    (tolera 0 resultados — engines bloqueiam em automação).

Roda o python do PRÓPRIO venv do vendor via subprocess (isolado do venv da AKASHA).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

VENDOR = Path(__file__).parent.parent / "vendor" / "searxng"


def _venv_python() -> Path:
    if os.name == "nt":
        return VENDOR / ".venv" / "Scripts" / "python.exe"
    return VENDOR / ".venv" / "bin" / "python"


_VENV_PY = _venv_python()

pytestmark = pytest.mark.skipif(
    not _VENV_PY.exists(),
    reason=f"venv do SearXNG vendorizado ausente ({_VENV_PY}); rode o atualizar/setup",
)


def _child_env(settings_path: Path | None) -> dict:
    """Ambiente para o processo do SearXNG, espelhando o que o HUB usa."""
    env = dict(os.environ)
    if settings_path is not None:
        env["SEARXNG_SETTINGS_PATH"] = str(settings_path)
    # Stub do pwd só no Windows (no Linux shadowaria o módulo real).
    if os.name == "nt":
        env["PYTHONPATH"] = str(VENDOR / "_winshim")
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _temp_settings(tmp_path: Path, port: int) -> Path:
    """Gera um settings.yml temporário (porta livre + secret) a partir do template."""
    base = (VENDOR / "settings.base.yml").read_text(encoding="utf-8")
    import secrets
    content = base.replace("__SECRET_KEY__", secrets.token_hex(32)).replace("port: 8889", f"port: {port}")
    out = tmp_path / "settings.yml"
    out.write_text(content, encoding="utf-8")
    return out


def test_import_searx_webapp_with_stub():
    """`import searx.webapp` deve funcionar no venv do vendor (stub pwd no Windows)."""
    settings = VENDOR / "settings.yml"
    env = _child_env(settings if settings.exists() else None)
    result = subprocess.run(
        [str(_VENV_PY), "-c", "import searx.webapp; print('IMPORT_OK')"],
        cwd=str(VENDOR), env=env, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, f"import falhou:\n{result.stderr}"
    assert "IMPORT_OK" in result.stdout


def test_vendor_server_boots_and_responds(tmp_path):
    """Sobe o servidor numa porta livre e checa /healthz 200 e /search?format=json 200."""
    port = _free_port()
    settings = _temp_settings(tmp_path, port)
    proc = subprocess.Popen(
        [str(_VENV_PY), "-m", "searx.webapp"],
        cwd=str(VENDOR), env=_child_env(settings),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        # Aguarda o servidor responder /healthz (startup carrega engines — pode demorar).
        healthy = False
        for _ in range(60):
            if proc.poll() is not None:
                pytest.fail("processo do SearXNG saiu antes de responder")
            try:
                with urllib.request.urlopen(f"{base}/healthz", timeout=2) as r:
                    if r.status == 200:
                        healthy = True
                        break
            except Exception:
                pass
            time.sleep(1)
        assert healthy, "SearXNG vendorizado não respondeu /healthz em ~60s"

        # /search?format=json deve responder 200 (tolera 0 resultados — engines flaky).
        with urllib.request.urlopen(
            f"{base}/search?q=test&format=json", timeout=30
        ) as r:
            assert r.status == 200
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
