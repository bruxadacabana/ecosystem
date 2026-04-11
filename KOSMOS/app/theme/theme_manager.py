"""Carregamento de fontes e troca de tema (day/night)."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from app.utils.paths import Paths

log = logging.getLogger("kosmos.theme")

_FONT_FILES = (
    "IMFellEnglish-Regular.ttf",
    "IMFellEnglish-Italic.ttf",
    "SpecialElite-Regular.ttf",
    "CourierPrime-Regular.ttf",
    "CourierPrime-Bold.ttf",
    "CourierPrime-Italic.ttf",
)

_VALID_THEMES = frozenset({"day", "night"})


class ThemeError(Exception):
    """Erro ao aplicar tema."""


class ThemeManager:
    """Gerencia fontes e alternância de tema da aplicação.

    Exemplo::

        mgr = ThemeManager(app)
        mgr.apply_theme("day")
        mgr.toggle_theme()        # retorna "night"
        css = mgr.reader_css_path()
    """

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._current: str = "day"
        self._load_fonts()

    # ------------------------------------------------------------------
    # Fontes
    # ------------------------------------------------------------------

    def _load_fonts(self) -> None:
        fonts_dir: Path = Paths.FONTS
        missing: list[str] = []

        for filename in _FONT_FILES:
            path = fonts_dir / filename
            if path.exists():
                fid = QFontDatabase.addApplicationFont(str(path))
                if fid == -1:
                    log.warning("Falha ao registrar fonte: %s", filename)
                else:
                    log.debug("Fonte registrada: %s", filename)
            else:
                missing.append(filename)

        if missing:
            log.warning(
                "%d fonte(s) não encontrada(s) em %s — usando fallbacks do sistema: %s",
                len(missing),
                fonts_dir,
                ", ".join(missing),
            )

    # ------------------------------------------------------------------
    # Tema
    # ------------------------------------------------------------------

    def apply_theme(self, theme: str) -> None:
        """Aplica o tema especificado à aplicação.

        Args:
            theme: "day" ou "night".

        Raises:
            ThemeError: se o tema for desconhecido ou o arquivo .qss não
                        existir.
        """
        if theme not in _VALID_THEMES:
            raise ThemeError(
                f"Tema inválido: '{theme}'. Use 'day' ou 'night'."
            )

        qss_path: Path = Paths.THEME / f"{theme}.qss"
        if not qss_path.exists():
            raise ThemeError(
                f"Arquivo de tema não encontrado: {qss_path}"
            )

        try:
            with open(qss_path, "r", encoding="utf-8") as fh:
                self._app.setStyleSheet(fh.read())
        except OSError as exc:
            raise ThemeError(f"Não foi possível ler {qss_path}: {exc}") from exc

        self._current = theme
        log.info("Tema aplicado: %s", theme)

    def toggle_theme(self) -> str:
        """Alterna entre day e night. Retorna o novo tema."""
        new_theme = "night" if self._current == "day" else "day"
        self.apply_theme(new_theme)
        return new_theme

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------

    @property
    def current(self) -> str:
        return self._current

    def reader_css_path(self) -> str:
        """Caminho absoluto para o CSS do painel de leitura."""
        return str(Paths.THEME / f"reader_{self._current}.css")
