"""Buffer circular em memória para logs do AKASHA.

Registra as últimas N linhas de log formatadas para que o HUB
possa exibi-las via GET /system/logs sem precisar ler arquivos.
"""
from __future__ import annotations

import logging
from collections import deque

_CAPACITY = 500
_buffer: deque[str] = deque(maxlen=_CAPACITY)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class _CircularHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _buffer.append(_fmt.format(record))
        except Exception:
            pass


_handler = _CircularHandler()
_handler.setLevel(logging.INFO)


def attach_to_root() -> None:
    """Registra o handler no logger raiz. Chamar uma vez no startup."""
    root = logging.getLogger()
    if _handler not in root.handlers:
        root.addHandler(_handler)


def get_lines(n: int = 100) -> list[str]:
    """Retorna as últimas n linhas de log."""
    lines = list(_buffer)
    return lines[-n:] if n < len(lines) else lines
