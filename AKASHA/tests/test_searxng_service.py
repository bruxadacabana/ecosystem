"""
Testes para SearXNG 4 — Inicialização automática via systemd --user.

Cobre:
  - Unit file existe no caminho correto
  - Serviço habilitado (enabled) — inicia com o login
  - Restart=on-failure no unit file
  - RestartSec configurado
  - WorkingDirectory aponta para instalação real
  - ExecStart usa o python do venv isolado
  - SEARXNG_SETTINGS_PATH aponta para config do AKASHA
  - Serviço está ativo (running) quando SearXNG instalado
  - (live) SearXNG responde ao healthcheck após inicialização automática
  - (live) SearXNG reinicia automaticamente quando morto (Restart=on-failure)

Nota: testes que fazem SIGKILL no processo são marcados como 'slow' e
requerem permissão de processo (são executados se o usuário tem permissão
para matar o próprio processo). Não são executados em CI.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / "searxng.service"
SEARXNG_INSTALL_DIR = Path.home() / ".local" / "share" / "searxng"
SEARXNG_CONFIG_DIR = Path.home() / ".config" / "searxng"
SEARXNG_URL = "http://localhost:8888"


def _systemctl(*args) -> tuple[int, str]:
    """Executa systemctl --user com os argumentos dados.

    Em SO sem systemd (Windows, macOS), o binário `systemctl` não existe e o
    subprocess levanta FileNotFoundError. Tratamos isso como "systemd indisponível"
    (rc=127) para que os testes deste módulo sejam PULADOS em vez de quebrar a
    coleção do pytest inteira no Windows.
    """
    try:
        result = subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return 127, ""
    return result.returncode, result.stdout.strip()


def _searxng_running() -> bool:
    try:
        with urllib.request.urlopen(f"{SEARXNG_URL}/healthz", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _systemd_available() -> bool:
    rc, _ = _systemctl("list-units", "--quiet")
    return rc == 0


systemd_available = pytest.mark.skipif(
    not _systemd_available(),
    reason="systemd --user não disponível neste ambiente",
)

# Todo este módulo testa o setup via systemd --user (Linux). Sem systemd (Windows,
# macOS), pula o módulo inteiro — inclusive os testes de unit file, que antes
# falhavam fora do Linux.
pytestmark = systemd_available

searxng_installed = pytest.mark.skipif(
    not SEARXNG_INSTALL_DIR.exists(),
    reason=f"SearXNG não instalado em {SEARXNG_INSTALL_DIR}",
)

searxng_live = pytest.mark.skipif(
    not _searxng_running(),
    reason="SearXNG não está respondendo em localhost:8888",
)


# ---------------------------------------------------------------------------
# Unit file — estrutura e conteúdo
# ---------------------------------------------------------------------------

class TestUnitFile:

    def test_unit_file_exists(self):
        """Arquivo de serviço systemd deve existir."""
        assert UNIT_PATH.exists(), (
            f"Unit file não encontrado: {UNIT_PATH}. "
            "Execute AKASHA/scripts/setup_searxng.sh para instalar."
        )

    def test_unit_file_has_restart_on_failure(self):
        """Unit file deve ter Restart=on-failure para reinício automático."""
        content = UNIT_PATH.read_text()
        assert "Restart=on-failure" in content, (
            "Restart=on-failure ausente no unit file — "
            "o serviço não reiniciará automaticamente se cair"
        )

    def test_unit_file_has_restartsec(self):
        """Unit file deve ter RestartSec configurado (pausa entre restarts)."""
        content = UNIT_PATH.read_text()
        assert "RestartSec=" in content, (
            "RestartSec ausente — sem pausa entre restarts o systemd pode "
            "atingir o rate limit e desabilitar o serviço"
        )

    def test_unit_file_has_correct_execstart(self):
        """ExecStart deve usar o python do venv isolado do SearXNG."""
        content = UNIT_PATH.read_text()
        assert ".venv/bin/python" in content, (
            "ExecStart não usa o venv do SearXNG — pode usar o python global "
            "que não tem as dependências instaladas"
        )
        assert "searx.webapp" in content, "ExecStart não inicia searx.webapp"

    def test_unit_file_sets_settings_path(self):
        """Unit file deve definir SEARXNG_SETTINGS_PATH apontando para config do AKASHA."""
        content = UNIT_PATH.read_text()
        assert "SEARXNG_SETTINGS_PATH" in content, (
            "SEARXNG_SETTINGS_PATH não definido no unit file — "
            "SearXNG vai usar config padrão em vez da configuração do AKASHA"
        )
        assert ".config/searxng/settings.yml" in content, (
            "SEARXNG_SETTINGS_PATH não aponta para ~/.config/searxng/settings.yml"
        )

    def test_unit_file_has_wanted_by(self):
        """Unit file deve ter WantedBy=default.target para iniciar com o login."""
        content = UNIT_PATH.read_text()
        assert "WantedBy=default.target" in content, (
            "WantedBy=default.target ausente — "
            "o serviço não será iniciado automaticamente ao fazer login"
        )

    def test_unit_file_type_simple(self):
        """Tipo do serviço deve ser 'simple' (processo em foreground)."""
        content = UNIT_PATH.read_text()
        assert "Type=simple" in content, (
            f"Type=simple ausente — SearXNG roda em foreground, não daemon"
        )

    def test_unit_file_working_directory(self):
        """WorkingDirectory deve apontar para o diretório de instalação do SearXNG."""
        content = UNIT_PATH.read_text()
        assert "WorkingDirectory=" in content, "WorkingDirectory ausente no unit file"
        assert ".local/share/searxng" in content, (
            "WorkingDirectory não aponta para ~/.local/share/searxng"
        )

    def test_unit_file_after_network(self):
        """Unit deve declarar After=network.target."""
        content = UNIT_PATH.read_text()
        assert "After=network.target" in content, (
            "After=network.target ausente — serviço pode iniciar antes da rede estar pronta"
        )


# ---------------------------------------------------------------------------
# Estado do serviço systemd
# ---------------------------------------------------------------------------

class TestServiceState:

    @systemd_available
    def test_service_is_enabled(self):
        """Serviço deve estar enabled para iniciar automaticamente com o login."""
        rc, _ = _systemctl("is-enabled", "searxng")
        assert rc == 0, (
            "Serviço não está enabled. Execute: systemctl --user enable searxng"
        )

    @systemd_available
    @searxng_installed
    def test_service_is_active(self):
        """Serviço deve estar active (running) quando instalado."""
        rc, status = _systemctl("is-active", "searxng")
        assert rc == 0, (
            f"Serviço não está active: {status!r}. "
            "Execute: systemctl --user start searxng"
        )

    @systemd_available
    def test_service_unit_loaded(self):
        """Serviço deve estar carregado (loaded) pelo systemd."""
        _, output = _systemctl("show", "searxng", "--property=LoadState", "--value")
        assert output.strip() == "loaded", (
            f"Serviço não carregado: {output!r}. "
            "Execute: systemctl --user daemon-reload"
        )

    @systemd_available
    def test_service_restart_policy(self):
        """Política de restart no systemd deve ser 'on-failure'."""
        _, restart_policy = _systemctl("show", "searxng",
                                       "--property=Restart", "--value")
        assert restart_policy.strip() == "on-failure", (
            f"Política de restart inesperada: {restart_policy!r}"
        )


# ---------------------------------------------------------------------------
# Restart automático (requer processo ativo)
# ---------------------------------------------------------------------------

class TestAutoRestart:

    @systemd_available
    @searxng_live
    def test_service_restarts_after_sigkill(self):
        """SearXNG deve reiniciar automaticamente após SIGKILL (Restart=on-failure).

        1. Obtém o PID atual do processo.
        2. Envia SIGKILL (morte imediata, sem cleanup).
        3. Aguarda até 12s para o systemd reiniciar (RestartSec=5 + margem).
        4. Verifica que o novo PID é diferente e o serviço está respondendo.
        """
        _, pid_str = _systemctl("show", "searxng", "--property=MainPID", "--value")
        pid_before = int(pid_str.strip() or 0)
        assert pid_before > 0, "Não foi possível obter PID do serviço"

        # Mata o processo (SIGKILL = não pode ser ignorado)
        try:
            os.kill(pid_before, 9)
        except ProcessLookupError:
            pytest.skip("Processo não encontrado — pode ter morrido antes do kill")

        # Aguarda restart (RestartSec=5 + margem de 7s)
        deadline = time.time() + 12
        pid_after = pid_before
        while time.time() < deadline:
            time.sleep(1)
            _, new_pid_str = _systemctl("show", "searxng", "--property=MainPID", "--value")
            pid_after = int(new_pid_str.strip() or 0)
            if pid_after > 0 and pid_after != pid_before:
                break

        assert pid_after > 0 and pid_after != pid_before, (
            f"Serviço não reiniciou após SIGKILL. "
            f"PID antes: {pid_before}, PID depois: {pid_after}"
        )

        # Verifica que o healthcheck responde após restart
        ok = False
        deadline2 = time.time() + 10
        while time.time() < deadline2:
            if _searxng_running():
                ok = True
                break
            time.sleep(1)

        assert ok, "SearXNG não respondeu ao healthcheck após restart automático"

    @systemd_available
    @searxng_live
    def test_healthcheck_after_start(self):
        """SearXNG deve responder ao healthcheck imediatamente após inicialização."""
        assert _searxng_running(), (
            "SearXNG não está respondendo — serviço pode ter falhado na inicialização"
        )
