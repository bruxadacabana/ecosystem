"""
Fixtures compartilhadas entre todos os testes do KOSMOS.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_KOSMOS_ROOT = Path(__file__).parent.parent
if str(_KOSMOS_ROOT) not in sys.path:
    sys.path.insert(0, str(_KOSMOS_ROOT))

# app/ precisa estar no path para que `from app.core.database import ...` funcione
_APP_ROOT = _KOSMOS_ROOT / "app"
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


# ---------------------------------------------------------------------------
# QApplication global — compartilhada por todos os testes que usam Qt
# (QApplication é subclasse de QCoreApplication, satisfaz ambos os casos)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app
