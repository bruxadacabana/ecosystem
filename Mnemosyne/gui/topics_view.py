"""
Aba "Temas" — nuvem de palavras clicável gerada a partir de topics.json.

Sub-modo "Nuvem" (implementado aqui):
  - Frequências extraídas de topics.json (escores c-TF-IDF) + doc_keywords
  - wordcloud.WordCloud gera imagem PIL → convertida para QPixmap via numpy
  - QGraphicsScene exibe a imagem; QGraphicsRectItem invisíveis sobre cada
    palavra (bounding box estimada de layout_) capturam cliques
  - Sinal theme_clicked(str) emitido ao clicar — MainWindow conecta ao chat

Sub-modo "Mapa Mental" (previsto — a implementar separadamente):
  - Grafo NetworkX renderizado em QGraphicsScene com zoom/pan

Dependências: wordcloud, numpy (já requerido por bertopic/umap)
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QImage, QPixmap, QPen, QBrush, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsScene, QGraphicsView,
)

log = logging.getLogger("mnemosyne.topics_view")

# Dimensões da imagem gerada pelo WordCloud (pixels)
_WC_WIDTH  = 900
_WC_HEIGHT = 560


# ---------------------------------------------------------------------------
# _ClickableView — QGraphicsView com zoom por roda e sinal de clique
# ---------------------------------------------------------------------------

class _ClickableView(QGraphicsView):
    """
    Extensão de QGraphicsView que:
    - emite word_clicked(QPointF) com a posição na cena ao clicar com o botão esquerdo;
    - suporta zoom com a roda do mouse (fator 1.15× por scroll);
    - suporta pan arrastrando com o botão do meio.
    """

    word_clicked = Signal(QPointF)

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.word_clicked.emit(self.mapToScene(event.pos()))
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)


# ---------------------------------------------------------------------------
# TopicsView — widget principal da aba Temas
# ---------------------------------------------------------------------------

class TopicsView(QWidget):
    """
    Painel de visualização de temas extraídos do corpus.

    Usa dados de topics.json (produzidos por core/topic_extractor.py) para
    gerar uma nuvem de palavras clicável. Ao clicar numa palavra, emite
    theme_clicked(word) — a MainWindow conecta esse sinal para disparar
    uma query no chat sobre o tema escolhido.

    Uso típico:
        view = TopicsView()
        view.set_topics(load_topics(mnemosyne_dir))
        view.set_refresh_callback(lambda: extract_and_reload())
        view.theme_clicked.connect(lambda w: ask_about(w))
    """

    theme_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._topics_data: dict        = {}
        # Lista de (palavra, bounding_rect_em_coords_de_cena) para hit-testing
        self._word_rects: list[tuple[str, QRectF]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # ── Toolbar ───────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        self._status_label = QLabel("Nenhum tema extraído.")
        self._status_label.setObjectName("resultsMeta")

        self._refresh_btn = QPushButton("⟳  Atualizar temas")
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setToolTip(
            "Re-analisa o corpus e recalcula os temas (pode levar alguns segundos)"
        )

        toolbar.addWidget(self._status_label, 1)
        toolbar.addWidget(self._refresh_btn)
        layout.addLayout(toolbar)

        # ── QGraphicsView para a nuvem de palavras ────────────────────────
        self._scene = QGraphicsScene(self)
        self._view  = _ClickableView(self._scene, self)
        layout.addWidget(self._view, 1)

        self._view.word_clicked.connect(self._on_view_click)

    # ── API pública ───────────────────────────────────────────────────────

    def set_topics(self, topics_data: dict) -> None:
        """Recebe dados de topics.json e regenera a nuvem."""
        self._topics_data = topics_data or {}
        self._refresh_cloud()

    def set_refresh_callback(self, callback) -> None:
        """Conecta o botão 'Atualizar temas' a um callable externo."""
        self._refresh_btn.setEnabled(True)
        try:
            self._refresh_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._refresh_btn.clicked.connect(callback)

    # ── Geração da nuvem ──────────────────────────────────────────────────

    def _build_freq_dict(self) -> dict[str, float]:
        """Constrói frequências a partir de topics + doc_keywords."""
        freq: dict[str, float] = {}
        for t in self._topics_data.get("topics", []):
            for word, score in t.get("words", []):
                if word and len(word) > 2:
                    freq[word] = max(freq.get(word, 0.0), float(score) * 100)
        for kws in self._topics_data.get("doc_keywords", {}).values():
            for kw in kws:
                if kw and len(kw) > 2:
                    freq[kw] = max(freq.get(kw, 0.0), 5.0)
        return freq

    def _refresh_cloud(self) -> None:
        self._word_rects.clear()
        freq = self._build_freq_dict()

        if not self._topics_data:
            self._status_label.setText("Nenhum tema disponível. Indexe documentos primeiro.")
            self._scene.clear()
            return

        if not freq:
            self._status_label.setText("Sem termos suficientes para gerar a nuvem.")
            self._scene.clear()
            return

        try:
            self._render_cloud(freq)
        except ImportError:
            self._status_label.setText("Instale wordcloud:  pip install wordcloud")
            log.warning("wordcloud não instalado")
        except Exception as exc:
            log.exception("Falha ao gerar nuvem de palavras")
            self._status_label.setText(f"Erro ao gerar nuvem: {exc}")

    def _render_cloud(self, freq: dict[str, float]) -> None:
        """Gera o WordCloud, converte para QPixmap e popula a QGraphicsScene."""
        from wordcloud import WordCloud  # type: ignore[import-untyped]
        import numpy as np

        wc = WordCloud(
            width=_WC_WIDTH,
            height=_WC_HEIGHT,
            background_color=None,
            mode="RGBA",
            max_words=80,
            prefer_horizontal=0.75,
            random_state=42,
        ).generate_from_frequencies(freq)

        # Converte PIL Image → QPixmap
        pil_img   = wc.to_image().convert("RGBA")
        img_bytes = np.asarray(pil_img, dtype=np.uint8).tobytes()
        qimage    = QImage(img_bytes, _WC_WIDTH, _WC_HEIGHT, _WC_WIDTH * 4,
                           QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)

        # Reconstrói a cena
        self._scene.clear()
        self._word_rects.clear()
        self._scene.addPixmap(pixmap)

        # Adiciona QGraphicsRectItem invisíveis para cada palavra
        # layout_ entry: ((word, count), font_size, (x, y), orientation, color)
        # position (x, y) = canto superior esquerdo da palavra na imagem PIL
        # orientation None = horizontal; Image.Transpose.ROTATE_90 = vertical
        for (word, _count), font_size, (x, y), orientation, _color in wc.layout_:
            # Estimativa de largura: ~0.55× font_size por caractere (fonte proporcional)
            text_px = len(word) * font_size * 0.55
            if orientation is None:                   # horizontal
                rect = QRectF(x, y, text_px, font_size * 1.1)
            else:                                      # vertical — transposta 90°
                rect = QRectF(x, y, font_size * 1.1, text_px)

            self._word_rects.append((word, rect))
            item = self._scene.addRect(
                rect,
                QPen(Qt.PenStyle.NoPen),
                QBrush(Qt.BrushStyle.NoBrush),
            )
            item.setAcceptHoverEvents(True)
            item.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        n_topics = len(self._topics_data.get("topics", []))
        self._status_label.setText(
            f"{n_topics} tópico(s) · {len(freq)} termos — clique numa palavra para pesquisar"
        )

    # ── Hit-testing ───────────────────────────────────────────────────────

    def _on_view_click(self, scene_pos: QPointF) -> None:
        """Determina qual palavra foi clicada e emite theme_clicked."""
        # 1ª passagem: bounding box exata
        for word, rect in self._word_rects:
            if rect.contains(scene_pos):
                self.theme_clicked.emit(word)
                return
        # 2ª passagem: word mais próxima (tolerância 150px) — para cliques levemente fora
        best_word = ""
        best_d2   = float("inf")
        for word, rect in self._word_rects:
            c  = rect.center()
            d2 = (scene_pos.x() - c.x()) ** 2 + (scene_pos.y() - c.y()) ** 2
            if d2 < best_d2:
                best_d2   = d2
                best_word = word
        if best_word and best_d2 < 150 ** 2:
            self.theme_clicked.emit(best_word)
