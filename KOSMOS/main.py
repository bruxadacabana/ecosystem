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

    # --- Registrar caminhos no ecosystem compartilhado (completado após config) --

    # --- Logger ---------------------------------------------------------
    from app.utils.logger import setup_logger
    setup_logger()
    log = logging.getLogger("kosmos")
    log.info("KOSMOS v0.1 iniciando...")

    # --- Configurações --------------------------------------------------
    from app.utils.config import Config
    config = Config()

    # --- Registrar no ecosystem (inclui http_port agora que config está disponível) --
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).parent.parent))
        from ecosystem_client import write_section as _write_ecosystem
        _write_ecosystem("kosmos", {
            "data_path":    str(Paths.DATA),
            "archive_path": str(Paths.ARCHIVE),
            "http_port":    config.get("http_port", 8965),
        })
    except Exception:
        pass  # Ecosystem é opcional — nunca bloquear o startup

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

    # --- API HTTP local (integração AKASHA → KOSMOS) --------------------
    import threading as _threading
    from http.server import HTTPServer as _HTTPServer, BaseHTTPRequestHandler as _BaseHandler
    from urllib.parse import parse_qs as _parse_qs

    def _make_http_handler(fm, _log):
        class _Handler(_BaseHandler):
            def do_GET(self):
                if self.path == "/health":
                    body = b'{"status":"ok","app":"KOSMOS"}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path == "/add-source":
                    length = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(length).decode("utf-8", errors="replace")
                    params = _parse_qs(raw)
                    url = params.get("url", [""])[0].strip()
                    name = params.get("name", [""])[0].strip() or url
                    if not url:
                        self.send_response(400)
                        self.end_headers()
                        return
                    try:
                        from app.utils.validators import detect_feed_type
                        feed_type = detect_feed_type(url)
                        fm.add_feed(url, name, feed_type)
                        self.send_response(200)
                        self.end_headers()
                    except Exception as exc:
                        _log.warning("HTTP /add-source erro: %s", exc)
                        self.send_response(500)
                        self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, fmt, *args):
                pass

        return _Handler

    _http_port = config.get("http_port", 8965)
    try:
        _http_srv = _HTTPServer(("127.0.0.1", _http_port), _make_http_handler(feed_manager, log))
        _http_thread = _threading.Thread(target=_http_srv.serve_forever, daemon=True)
        _http_thread.start()
        log.info("KOSMOS HTTP API na porta %d", _http_port)
    except OSError as exc:
        log.warning("Não foi possível iniciar HTTP API: %s", exc)

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
