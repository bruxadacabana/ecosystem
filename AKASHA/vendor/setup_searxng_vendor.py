#!/usr/bin/env python3
"""
Setup do SearXNG VENDORIZADO do AKASHA (multiplataforma — Windows e Linux).

Faz, de forma idempotente:
  1. gera `searxng/settings.yml` a partir de `searxng/settings.base.yml`, substituindo
     `__SECRET_KEY__` por um segredo aleatório (preserva o segredo se o arquivo já existe);
  2. cria o venv dedicado `searxng/.venv` (Python 3.13) via `uv`;
  3. instala `searxng/requirements.txt` nesse venv.

NÃO inicia o servidor (o HUB gerencia o processo — ver TODO). Substitui, para o caso
vendorizado, o `scripts/setup_searxng.sh` (que é Linux/systemd e clona o SearXNG).

Uso: `python AKASHA/vendor/setup_searxng_vendor.py`
Embutido em `atualizar.sh` / `atualizar.bat`.
"""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

PREFIX = "[searxng-vendor]"
VENDOR = Path(__file__).resolve().parent / "searxng"
PY_VERSION = "3.13"


def log(msg: str) -> None:
    print(f"{PREFIX} {msg}", flush=True)


def err(msg: str) -> None:
    print(f"{PREFIX} ERRO: {msg}", file=sys.stderr, flush=True)


def venv_python(vendor: Path) -> Path:
    """Caminho do interpretador do venv do SearXNG, por plataforma."""
    if os.name == "nt":
        return vendor / ".venv" / "Scripts" / "python.exe"
    return vendor / ".venv" / "bin" / "python"


def ensure_settings(vendor: Path) -> Path:
    """Gera settings.yml a partir do template (idempotente: preserva o existente).

    Retorna o caminho do settings.yml. Levanta FileNotFoundError se faltar o template.
    """
    settings = vendor / "settings.yml"
    template = vendor / "settings.base.yml"
    if settings.exists():
        log(f"settings.yml já existe — preservando (segredo intacto): {settings}")
        return settings
    if not template.exists():
        raise FileNotFoundError(f"template ausente: {template}")
    secret = secrets.token_hex(32)
    content = template.read_text(encoding="utf-8").replace("__SECRET_KEY__", secret)
    settings.write_text(content, encoding="utf-8")
    log(f"settings.yml gerado com secret_key novo: {settings}")
    return settings


def ensure_venv(vendor: Path, uv: str) -> None:
    """Cria o venv dedicado (Python 3.13) se ainda não existir."""
    py = venv_python(vendor)
    if py.exists():
        log(f"venv já existe: {py}")
        return
    log(f"criando venv (Python {PY_VERSION}) em {vendor / '.venv'} …")
    subprocess.run(
        [uv, "venv", "--python", PY_VERSION, str(vendor / ".venv")],
        cwd=str(vendor), check=True,
    )


def install_requirements(vendor: Path, uv: str) -> None:
    """Instala requirements.txt no venv dedicado."""
    req = vendor / "requirements.txt"
    if not req.exists():
        raise FileNotFoundError(f"requirements.txt ausente: {req}")
    env = dict(os.environ, UV_LINK_MODE="copy")  # evita warning de hardlink entre FS
    log("instalando dependências do SearXNG (pode demorar na 1ª vez) …")
    subprocess.run(
        [uv, "pip", "install", "--python", str(venv_python(vendor)), "-r", str(req)],
        cwd=str(vendor), check=True, env=env,
    )


def main() -> int:
    log(f"vendor: {VENDOR}")
    if not VENDOR.exists():
        err(f"pasta vendorizada não encontrada: {VENDOR}")
        return 1

    uv = shutil.which("uv")
    if not uv:
        err("'uv' não encontrado no PATH — instale: https://docs.astral.sh/uv/")
        return 1

    try:
        ensure_settings(VENDOR)
        ensure_venv(VENDOR, uv)
        install_requirements(VENDOR, uv)
    except FileNotFoundError as exc:
        err(str(exc))
        return 1
    except subprocess.CalledProcessError as exc:
        err(f"comando falhou (código {exc.returncode}): {' '.join(map(str, exc.cmd))}")
        return 1

    log("setup concluído — SearXNG vendorizado pronto (o HUB inicia o processo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
