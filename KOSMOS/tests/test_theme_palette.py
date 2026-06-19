"""
Regressão da paleta do KOSMOS (redesign — passo de paleta).

Garante que o **modo noite** usa o azul canônico "Atlas Astronômico à Meia-Noite"
(`#12161E`) do DESIGN_BIBLE, sem cores sépia residuais; que o **modo dia** (padrão)
segue intacto no pergaminho; e que o corpo do leitor (reader_night.css) compartilha
a mesma base azul do chrome (night.qss) — corpo e moldura casam no modo escuro.
"""
from __future__ import annotations

from app.utils.paths import THEMES_DIR

# Cores sépia antigas que NÃO devem sobrar no modo noite após o recolor.
_SEPIA_LEFTOVERS = ("#1c1610", "#231d14", "#3d3226", "#332b1e", "#2a2218", "#2e2618")


def test_night_qss_is_blue_not_sepia():
    css = (THEMES_DIR / "night.qss").read_text(encoding="utf-8")
    low = css.lower()
    assert "#12161e" in low, "night.qss deve usar a base azul #12161E"
    assert "#d4a820" in low, "night.qss deve usar o dourado de acento #D4A820"
    for sepia in _SEPIA_LEFTOVERS:
        assert sepia not in low, f"cor sépia {sepia} ainda presente no night.qss"


def test_day_qss_stays_parchment():
    low = (THEMES_DIR / "day.qss").read_text(encoding="utf-8").lower()
    assert "#f0e8d5" in low, "day.qss deve manter a base pergaminho #f0e8d5 (modo dia intacto)"


def test_reader_night_matches_app_night_base():
    reader = (THEMES_DIR / "reader_night.css").read_text(encoding="utf-8").lower()
    assert "#12161e" in reader, "o corpo do leitor (noite) deve usar a mesma base azul do chrome"


def test_analysis_tools_styled_in_both_themes():
    # Re-skin V1: as ferramentas de Análise devem estar estilizadas nos DOIS temas
    # (o day.qss não tinha nenhum estilo de análise antes do V1).
    for name in ("night.qss", "day.qss"):
        css = (THEMES_DIR / name).read_text(encoding="utf-8").lower()
        assert "#analysis_rail" in css, f"{name} deve estilizar o rail de Análise"
        assert "#entity_header" in css, f"{name} deve estilizar os cabeçalhos de Análise"


def test_cosmos_painter_night_is_blue(qapp):
    from collections import Counter

    from app.theme.cosmos_painter import paint_cosmos
    from PySide6.QtGui import QColor

    pix = paint_cosmos(16, 16, theme="night")
    img = pix.toImage()
    # A cor dominante (fundo, sob as estrelas esparsas) deve ser a base azul-meia-noite.
    counts: Counter = Counter()
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor(img.pixel(x, y))
            counts[(c.red(), c.green(), c.blue())] += 1
    dominant = counts.most_common(1)[0][0]
    assert dominant == (0x12, 0x16, 0x1E)
