"""
Fixtures compartilhadas entre todos os testes do AKASHA.
"""
from __future__ import annotations

import sys
from pathlib import Path

_AKASHA_ROOT = Path(__file__).parent.parent
if str(_AKASHA_ROOT) not in sys.path:
    sys.path.insert(0, str(_AKASHA_ROOT))
