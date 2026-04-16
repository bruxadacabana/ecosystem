# Entry point, starts the Qt application

import sys
from core.logger import setup_logger
from gui.main_window import run

if __name__ == "__main__":
    setup_logger()
    run()