"""
Fixtures compartilhadas entre todos os testes do Hermes.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERMES_ROOT = Path(__file__).parent.parent
if str(_HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(_HERMES_ROOT))
