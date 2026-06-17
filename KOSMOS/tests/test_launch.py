"""
Testes do script de lançamento (Fase 8 / BUG-042).

O HUB lança o KOSMOS via `Command::new(exe_path)` apontando para `iniciar.sh`.
No Linux isso executa o arquivo direto — exige o bit de execução E um shebang.
Sem o `+x`, o botão "Iniciar" do HUB não faz nada (o spawn falha).
"""
from __future__ import annotations

import os
from pathlib import Path

_INICIAR = Path(__file__).resolve().parent.parent / "iniciar.sh"


def test_iniciar_sh_exists():
    assert _INICIAR.exists(), "KOSMOS/iniciar.sh não encontrado"


def test_iniciar_sh_is_executable():
    # BUG-042: sem o bit +x, o HUB não consegue lançar o KOSMOS no Linux.
    assert os.access(_INICIAR, os.X_OK), "KOSMOS/iniciar.sh precisa ter o bit de execução (+x)"


def test_iniciar_sh_has_shebang():
    assert _INICIAR.read_text(encoding="utf-8").startswith("#!"), "iniciar.sh precisa de shebang"
