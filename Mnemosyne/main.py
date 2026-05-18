# Entry point, starts the Qt application
# setup_logger() deve ser chamado antes de qualquer outro import para garantir
# que os handlers de arquivo estejam ativos desde o início.

import sys
from core.logger import setup_logger

if __name__ == "__main__":
    setup_logger()
    from gui.main_window import run
    run()