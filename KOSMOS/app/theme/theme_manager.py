from __future__ import annotations

import logging

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from app.utils.paths import FONTS_DIR, THEMES_DIR

log = logging.getLogger("kosmos.theme")

_FONT_FILES = [
    "IMFellEnglish-Regular.ttf",
    "IMFellEnglish-Italic.ttf",
    "SpecialElite-Regular.ttf",
    "CourierPrime-Regular.ttf",
    "CourierPrime-Bold.ttf",
    "CourierPrime-Italic.ttf",
]


def _load_fonts() -> None:
    if not FONTS_DIR.exists():
        log.warning("Diretório de fontes ausente: %s — usando fontes do sistema.", FONTS_DIR)
        return
    for name in _FONT_FILES:
        path = FONTS_DIR / name
        if not path.exists():
            log.debug("Fonte não encontrada (ignorando): %s", name)
            continue
        fid = QFontDatabase.addApplicationFont(str(path))
        if fid < 0:
            log.warning("Falha ao registrar fonte: %s", name)
        else:
            log.debug("Fonte carregada: %s", name)


def apply_theme(app: QApplication, theme: str) -> None:
    """Carrega fontes e aplica QSS do tema (day/night) à aplicação."""
    _load_fonts()

    qss_file = THEMES_DIR / f"{theme}.qss"
    if not qss_file.exists():
        log.warning("QSS '%s' não encontrado — app sem estilo.", qss_file.name)
        app.setStyleSheet("")
        return

    try:
        app.setStyleSheet(qss_file.read_text(encoding="utf-8"))
        log.info("Tema '%s' aplicado.", theme)
    except OSError as exc:
        log.error("Falha ao ler QSS '%s': %s", qss_file, exc)
        app.setStyleSheet("")
