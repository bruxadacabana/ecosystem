"""
Fixtures compartilhadas entre todos os testes do KOSMOS.
"""
from __future__ import annotations

import sys
from pathlib import Path

_KOSMOS_ROOT = Path(__file__).parent.parent
if str(_KOSMOS_ROOT) not in sys.path:
    sys.path.insert(0, str(_KOSMOS_ROOT))

# app/ precisa estar no path para que `from app.core.database import ...` funcione
_APP_ROOT = _KOSMOS_ROOT / "app"
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
