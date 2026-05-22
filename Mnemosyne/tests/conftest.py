"""
Fixtures compartilhadas entre todos os testes da Mnemosyne.

O conftest.py na raiz do pacote tests/ é carregado automaticamente pelo pytest
antes de qualquer módulo de teste. Aqui ficam apenas fixtures e configuração
de sys.path — nenhuma lógica de teste.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Garante que `import core.*` e `import gui.*` funcionem sem instalar o pacote.
# A raiz da Mnemosyne (um nível acima de tests/) precisa estar no path.
_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))
