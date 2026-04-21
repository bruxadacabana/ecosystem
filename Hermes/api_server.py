"""
HermesApiServer — servidor HTTP local para integração com AKASHA/extensão Firefox.
Porta padrão: 7072. Roda em daemon thread separada; comunica com a UI via
ApiSignalBridge (QObject/pyqtSignal — thread-safe no Qt).
"""

from __future__ import annotations

import json
import http.server
import socketserver
import threading

from PyQt6.QtCore import QObject, pyqtSignal


class ApiSignalBridge(QObject):
    """Ponte thread-safe entre o servidor HTTP e o event loop do Qt."""
    download_requested   = pyqtSignal(str, str)  # (url, format_id)
    transcribe_requested = pyqtSignal(str)        # (url,)


class HermesApiServer(threading.Thread):
    """Servidor HTTP leve; inicia como daemon thread, pára no closeEvent."""

    def __init__(self, port: int, bridge: ApiSignalBridge) -> None:
        super().__init__(daemon=True, name="hermes-api")
        self._port   = port
        self._bridge = bridge
        self._server: socketserver.TCPServer | None = None
        self.active  = 0  # contador aproximado de jobs em fila

    @property
    def port(self) -> int:
        return self._port

    def run(self) -> None:
        Handler = self._make_handler()

        class _Server(socketserver.TCPServer):
            allow_reuse_address = True

        try:
            with _Server(("127.0.0.1", self._port), Handler) as srv:
                self._server = srv
                srv.serve_forever()
        except OSError:
            pass  # porta ocupada — falha silenciosa, Hermes abre normalmente

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()

    def _make_handler(self) -> type:
        bridge  = self._bridge
        counter = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/health":
                    self._respond(200, {"status": "ok", "active": counter.active})
                else:
                    self._respond(404, {"error": "not found"})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                raw    = self.rfile.read(length)
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    self._respond(400, {"error": "JSON inválido"})
                    return

                url = (data.get("url") or "").strip()
                if not url:
                    self._respond(400, {"error": "campo 'url' obrigatório"})
                    return

                if self.path == "/download":
                    fmt = str(data.get("format", "bestvideo+bestaudio/best"))
                    bridge.download_requested.emit(url, fmt)
                    counter.active += 1
                    self._respond(200, {"status": "queued", "url": url})

                elif self.path == "/transcribe":
                    bridge.transcribe_requested.emit(url)
                    counter.active += 1
                    self._respond(200, {"status": "queued", "url": url})

                else:
                    self._respond(404, {"error": "endpoint não encontrado"})

            def _respond(self, code: int, body: dict) -> None:
                payload = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args) -> None:
                pass  # suprimir log padrão do http.server

        return _Handler
