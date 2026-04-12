"""KOSMOS — ponto de entrada da aplicação."""

from __future__ import annotations

import logging
import sys
import time


def main() -> None:
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print(
            "ERRO: PyQt6 não está instalado.\n"
            "Execute: pip install -r requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    # QWebEngineWidgets DEVE ser importado antes de QApplication ser criado
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView as _QWV  # noqa: F401
    except ImportError:
        pass  # Opcional — fallback de texto será usado no ReaderView

    app = QApplication(sys.argv)
    app.setApplicationName("KOSMOS")
    app.setOrganizationName("KOSMOS")
    app.setApplicationVersion("0.1.0")

    # --- Caminhos e diretórios de dados ---------------------------------
    from app.utils.paths import Paths
    Paths.ensure_directories()

    # --- Registrar caminhos no ecosystem compartilhado ------------------
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).parent.parent))
        from ecosystem_client import write_section as _write_ecosystem
        _write_ecosystem("kosmos", {
            "data_path":    str(Paths.DATA),
            "archive_path": str(Paths.ARCHIVE),
        })
    except Exception:
        pass  # Ecosystem é opcional — nunca bloquear o startup

    # --- Logger ---------------------------------------------------------
    from app.utils.logger import setup_logger
    setup_logger()
    log = logging.getLogger("kosmos")
    log.info("KOSMOS v0.1 iniciando...")

    # --- Configurações --------------------------------------------------
    from app.utils.config import Config
    config = Config()

    # --- Tema -----------------------------------------------------------
    from app.theme.theme_manager import ThemeManager, ThemeError
    theme_manager = ThemeManager(app)
    try:
        theme_manager.apply_theme(config.get("theme", "day"))
    except ThemeError as exc:
        log.warning("Tema não disponível, usando padrão: %s", exc)

    # --- Splash screen --------------------------------------------------
    from app.ui.splash_screen import SplashScreen
    splash = SplashScreen(theme_manager)
    splash.show()
    app.processEvents()

    start_time = time.monotonic()

    # --- Banco de dados -------------------------------------------------
    splash.set_progress(20)
    app.processEvents()

    try:
        from app.core.database import init_database
        init_database()
        log.info("Banco de dados inicializado.")
    except Exception as exc:
        log.critical("Falha ao inicializar banco: %s", exc, exc_info=True)
        splash.close()
        QMessageBox.critical(
            None,
            "KOSMOS — Erro Fatal",
            f"Não foi possível inicializar o banco de dados:\n\n{exc}\n\n"
            "Verifique data/logs/kosmos.log para detalhes.",
        )
        sys.exit(1)

    splash.set_progress(45)
    app.processEvents()

    # --- Feed Manager ---------------------------------------------------
    from app.core.feed_manager import FeedManager
    feed_manager = FeedManager()

    # --- Seed de feeds padrão (primeiro uso) ----------------------------
    try:
        from app.core.feed_seeder import seed_default_feeds
        seed_default_feeds(feed_manager)
    except Exception as exc:
        log.warning("Erro durante seed de feeds padrão: %s", exc)

    # --- Purgação de artigos antigos ------------------------------------
    try:
        purged = feed_manager.purge_old_articles(
            read_days   = config.get("purge_read_days",   30),
            unread_days = config.get("purge_unread_days", 90),
        )
        if purged:
            log.info("Purgação inicial: %d artigos removidos.", purged)
    except Exception as exc:
        log.warning("Erro na purgação inicial: %s", exc)

    splash.set_progress(60)
    app.processEvents()

    # --- Background Updater ---------------------------------------------
    from app.core.background_updater import BackgroundUpdater
    updater = BackgroundUpdater(config, feed_manager)

    # --- Janela principal -----------------------------------------------
    try:
        from app.ui.main_window import MainWindow
        window = MainWindow(config, theme_manager, feed_manager, updater)
    except Exception as exc:
        log.critical("Falha ao construir a janela principal: %s", exc, exc_info=True)
        splash.close()
        QMessageBox.critical(
            None,
            "KOSMOS — Erro Fatal",
            f"Não foi possível abrir a janela principal:\n\n{exc}",
        )
        sys.exit(1)

    splash.set_progress(90)
    app.processEvents()

    # --- Tempo mínimo de splash (1.5s) ----------------------------------
    elapsed = time.monotonic() - start_time
    if elapsed < 1.5:
        remaining = 1.5 - elapsed
        steps = 10
        for _ in range(steps):
            time.sleep(remaining / steps)
            app.processEvents()

    splash.set_progress(100)
    app.processEvents()

    window.show()
    splash.finish(window)

    # Iniciar atualização em background após a UI estar visível
    updater.start()
    updater.trigger_now()

    log.info("KOSMOS pronto.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
