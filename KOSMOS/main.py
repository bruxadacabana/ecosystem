"""KOSMOS v3 — entry point."""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

# paths.py configura sys.path para ecosystem_client antes de qualquer outro import
from app.utils.paths import LOG_PATH
from app.utils.logger import setup_logger

setup_logger(LOG_PATH)
log = logging.getLogger("kosmos")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.utils.config import load_config               # noqa: E402
from app.core.database import init_db                  # noqa: E402
from app.theme.theme_manager import apply_theme        # noqa: E402
from app.ui.splash_screen import SplashScreen          # noqa: E402
from app.ui.main_window import MainWindow              # noqa: E402


def main() -> None:
    log.info("KOSMOS v3 iniciando…")

    app = QApplication(sys.argv)
    app.setApplicationName("KOSMOS")
    app.setApplicationVersion("3.0.0")
    app.setOrganizationName("ecosystem")

    try:
        config = load_config()
    except OSError as exc:
        log.critical("Falha ao carregar configuração: %s", exc)
        QMessageBox.critical(
            None, "KOSMOS — Erro Fatal",
            f"Não foi possível carregar a configuração:\n{exc}",
        )
        sys.exit(1)

    apply_theme(app, config.theme)

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    try:
        init_db()
    except sqlite3.OperationalError as exc:
        log.critical("Falha ao inicializar banco de dados: %s", exc)
        QMessageBox.critical(
            None, "KOSMOS — Erro Fatal",
            f"Não foi possível inicializar o banco de dados:\n{exc}",
        )
        sys.exit(1)

    window = MainWindow(config)
    window.show()
    splash.finish(window)

    log.info("KOSMOS pronto.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
