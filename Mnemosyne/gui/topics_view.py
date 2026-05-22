"""
Aba "Temas" — nuvem de palavras clicável e mapa mental interativo.

Sub-modo "Nuvem":
  - Frequências extraídas de topics.json (escores c-TF-IDF) + doc_keywords
  - wordcloud.WordCloud gera imagem PIL → convertida para QPixmap via numpy
  - QGraphicsScene exibe a imagem; QGraphicsRectItem invisíveis sobre cada
    palavra (bounding box estimada de layout_) capturam cliques
  - Sinal theme_clicked(str) emitido ao clicar — MainWindow conecta ao chat

Sub-modo "Mapa":
  - Grafo NetworkX: nós de tópico (azul) + nós de documento (cinza)
  - Posições via kamada_kawai_layout(); fallback: spring_layout
  - _NodeItem (QGraphicsEllipseItem) com mousePressEvent:
      tópico → theme_clicked → chat; documento → abre arquivo no SO
  - Pan com botão do meio; zoom com roda do mouse (fator 1.15×)

Dependências: wordcloud, numpy, networkx
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QCursor, QFont, QImage, QPixmap, QPen, QBrush,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsScene, QGraphicsView, QGraphicsEllipseItem,
    QGraphicsTextItem, QStackedWidget,
)

log = logging.getLogger("mnemosyne.topics_view")

# Dimensões da imagem gerada pelo WordCloud (pixels)
_WC_WIDTH  = 900
_WC_HEIGHT = 560

# Estética do mapa mental
_COLOR_TOPIC = QColor("#4A90D9")   # azul — nós de tópico
_COLOR_DOC   = QColor("#777777")   # cinza — nós de documento
_R_TOPIC     = 22                  # raio (px)
_R_DOC       = 12

# Limites do mapa mental — evita freeze com corpora grandes (ChromaDB armazena
# chunks, não arquivos; um único PDF pode gerar centenas de chunks)
_MAX_FILES_PER_TOPIC = 5   # arquivos únicos exibidos por tópico
_MAX_LAYOUT_NODES    = 120  # acima disso usa spring_layout com poucas iterações


# ---------------------------------------------------------------------------
# _ClickableView — QGraphicsView para nuvem de palavras
# ---------------------------------------------------------------------------

class _ClickableView(QGraphicsView):
    """
    Extensão de QGraphicsView que:
    - emite word_clicked(QPointF) ao clicar com o botão esquerdo;
    - suporta zoom com a roda do mouse (fator 1.15×);
    - suporta pan arrastando com o botão esquerdo (ScrollHandDrag).
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
# _NodeItem — nó clicável no mapa mental (não é QObject: usa callback)
# ---------------------------------------------------------------------------

class _NodeItem(QGraphicsEllipseItem):
    """Nó clicável no grafo do mapa mental.

    Não é QObject — usa callback em vez de Signal para evitar herança múltipla
    entre QGraphicsEllipseItem e QObject.
    """

    def __init__(
        self,
        x: float,
        y: float,
        r: float,
        color: QColor,
        callback,
    ) -> None:
        super().__init__(-r, -r, r * 2, r * 2)
        self._callback = callback
        self.setPos(x, y)
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(150), 1.5))
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAcceptHoverEvents(True)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._callback:
            self._callback()
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# _MapView — QGraphicsView com zoom e pan por botão do meio
# ---------------------------------------------------------------------------

class _MapView(QGraphicsView):
    """QGraphicsView com zoom (roda) e pan (botão do meio)."""

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._pan_active = False
        self._pan_start  = QPointF()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_active = True
            self._pan_start  = event.position()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._pan_active:
            delta           = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_active = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# TopicsView — widget principal da aba Temas
# ---------------------------------------------------------------------------

class TopicsView(QWidget):
    """
    Painel de visualização de temas extraídos do corpus.

    Dois sub-modos acessíveis por botões na toolbar:
      "Nuvem"  — word cloud clicável (wordcloud + numpy)
      "Mapa"   — grafo NetworkX renderizado em QGraphicsScene

    Sinal público:
      theme_clicked(str) — emitido quando o usuário clica num tema; a
      MainWindow conecta ao chat para disparar uma query sobre o tema.

    Uso típico:
        view = TopicsView()
        view.set_topics(load_topics(mnemosyne_dir))
        view.set_refresh_callback(lambda: extract_and_reload())
        view.theme_clicked.connect(lambda w: ask_about(w))
    """

    theme_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._topics_data: dict = {}
        # Lista de (palavra, bounding_rect_em_coords_de_cena) para hit-testing da nuvem
        self._word_rects: list[tuple[str, QRectF]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # ── Toolbar ───────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)

        self._btn_cloud = QPushButton("Nuvem")
        self._btn_cloud.setCheckable(True)
        self._btn_cloud.setChecked(True)
        self._btn_cloud.setFixedWidth(80)

        self._btn_map = QPushButton("Mapa")
        self._btn_map.setCheckable(True)
        self._btn_map.setFixedWidth(80)

        self._btn_cloud.clicked.connect(lambda: self._switch_mode(0))
        self._btn_map.clicked.connect(lambda: self._switch_mode(1))

        self._status_label = QLabel("Nenhum tema extraído.")
        self._status_label.setObjectName("resultsMeta")

        self._refresh_btn = QPushButton("⟳  Atualizar temas")
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setToolTip(
            "Re-analisa o corpus e recalcula os temas (pode levar alguns segundos)"
        )

        toolbar.addWidget(self._btn_cloud)
        toolbar.addWidget(self._btn_map)
        toolbar.addSpacing(8)
        toolbar.addWidget(self._status_label, 1)
        toolbar.addWidget(self._refresh_btn)
        layout.addLayout(toolbar)

        # ── QStackedWidget com as duas views ─────────────────────────────
        self._stack = QStackedWidget(self)

        # Página 0 — Nuvem
        self._scene_cloud = QGraphicsScene(self)
        self._view_cloud  = _ClickableView(self._scene_cloud, self)
        self._stack.addWidget(self._view_cloud)
        self._view_cloud.word_clicked.connect(self._on_view_click)

        # Página 1 — Mapa
        self._scene_map = QGraphicsScene(self)
        self._view_map  = _MapView(self._scene_map, self)
        self._stack.addWidget(self._view_map)

        layout.addWidget(self._stack, 1)

    # ── Troca de sub-modo ─────────────────────────────────────────────────

    def _switch_mode(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._btn_cloud.setChecked(index == 0)
        self._btn_map.setChecked(index == 1)

    # ── API pública ───────────────────────────────────────────────────────

    def set_topics(self, topics_data: dict) -> None:
        """Recebe dados de topics.json e regenera ambas as visualizações."""
        self._topics_data = topics_data or {}
        self._refresh_cloud()
        self._refresh_map()

    def set_refresh_callback(self, callback) -> None:
        """Conecta o botão 'Atualizar temas' a um callable externo."""
        self._refresh_btn.setEnabled(True)
        try:
            self._refresh_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._refresh_btn.clicked.connect(callback)

    # ── Geração da nuvem de palavras ──────────────────────────────────────

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
            self._scene_cloud.clear()
            return

        if not freq:
            self._status_label.setText("Sem termos suficientes para gerar a nuvem.")
            self._scene_cloud.clear()
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

        pil_img   = wc.to_image().convert("RGBA")
        img_bytes = np.asarray(pil_img, dtype=np.uint8).tobytes()
        qimage    = QImage(img_bytes, _WC_WIDTH, _WC_HEIGHT, _WC_WIDTH * 4,
                           QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)

        self._scene_cloud.clear()
        self._word_rects.clear()
        self._scene_cloud.addPixmap(pixmap)

        # Adiciona QGraphicsRectItem invisíveis para hit-testing de cada palavra
        # layout_ entry: ((word, count), font_size, (x, y), orientation, color)
        # orientation None = horizontal; Image.Transpose.ROTATE_90 = vertical
        for (word, _count), font_size, (x, y), orientation, _color in wc.layout_:
            text_px = len(word) * font_size * 0.55
            if orientation is None:
                rect = QRectF(x, y, text_px, font_size * 1.1)
            else:
                rect = QRectF(x, y, font_size * 1.1, text_px)

            self._word_rects.append((word, rect))
            item = self._scene_cloud.addRect(
                rect,
                QPen(Qt.PenStyle.NoPen),
                QBrush(Qt.BrushStyle.NoBrush),
            )
            item.setAcceptHoverEvents(True)
            item.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self._view_cloud.fitInView(
            self._scene_cloud.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
        )

        n_topics = len(self._topics_data.get("topics", []))
        self._status_label.setText(
            f"{n_topics} tópico(s) · {len(freq)} termos — clique numa palavra para pesquisar"
        )

    # ── Hit-testing da nuvem ──────────────────────────────────────────────

    def _on_view_click(self, scene_pos: QPointF) -> None:
        """Determina qual palavra foi clicada e emite theme_clicked."""
        # 1ª passagem: bounding box exata
        for word, rect in self._word_rects:
            if rect.contains(scene_pos):
                self.theme_clicked.emit(word)
                return
        # 2ª passagem: palavra mais próxima (tolerância 150px)
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

    # ── Geração do mapa mental ────────────────────────────────────────────

    def _refresh_map(self) -> None:
        """Constrói grafo NetworkX e renderiza no QGraphicsScene do mapa."""
        self._scene_map.clear()

        topics      = self._topics_data.get("topics", [])
        doc_topic   = self._topics_data.get("doc_topic", {})
        doc_sources = self._topics_data.get("doc_sources", {})

        if not topics or not doc_topic:
            return

        try:
            import networkx as nx
        except ImportError:
            log.warning("networkx não instalado — mapa mental indisponível")
            return

        G: "nx.Graph" = nx.Graph()

        # Nós de tópico
        for t in topics:
            label = t["words"][0][0] if t.get("words") else f"Tópico {t['id']}"
            G.add_node(f"topic_{t['id']}", kind="topic", label=label)

        # Agrupa chunks por (topic_id, path) para deduplicar — ChromaDB guarda
        # chunks, não arquivos; um PDF pode gerar centenas de chunks do mesmo
        # arquivo, e renderizar todos os chunks travaria o layout.
        topic_files: dict[int, dict[str, str]] = {}  # topic_id → {path: label}
        for chroma_id, topic_id in doc_topic.items():
            tid = int(topic_id)
            if tid < 0:
                continue
            path  = doc_sources.get(chroma_id, "") or chroma_id[:14]
            label = os.path.basename(path) if path else chroma_id[:14]
            bucket = topic_files.setdefault(tid, {})
            if path not in bucket and len(bucket) < _MAX_FILES_PER_TOPIC:
                bucket[path] = label

        for tid, files in topic_files.items():
            for path, label in files.items():
                node_id = f"doc_{path}"
                G.add_node(node_id, kind="doc", label=label, path=path)
                G.add_edge(f"topic_{tid}", node_id)

        if not G.nodes:
            return

        n_nodes = len(G.nodes)
        if n_nodes <= _MAX_LAYOUT_NODES:
            try:
                pos = nx.kamada_kawai_layout(G)
            except Exception:
                pos = nx.spring_layout(G, seed=42, iterations=50)
        else:
            # Para grafos grandes spring_layout é muito mais rápido
            pos = nx.spring_layout(G, seed=42, iterations=30)

        scale = 420.0  # fator de escala: coordenadas NetworkX [-1,1] → unidades de cena

        # Arestas (z-value negativo = desenhadas abaixo dos nós)
        for u, v in G.edges():
            if u not in pos or v not in pos:
                continue
            x1, y1 = pos[u][0] * scale, pos[u][1] * scale
            x2, y2 = pos[v][0] * scale, pos[v][1] * scale
            line = self._scene_map.addLine(x1, y1, x2, y2, QPen(QColor("#555555"), 1))
            line.setZValue(-1)

        # Nós
        font_topic = QFont()
        font_topic.setPointSize(9)
        font_doc = QFont()
        font_doc.setPointSize(7)

        for node_id, attrs in G.nodes(data=True):
            if node_id not in pos:
                continue
            x, y  = pos[node_id][0] * scale, pos[node_id][1] * scale
            kind  = attrs.get("kind", "doc")
            label = attrs.get("label", "")

            if kind == "topic":
                r    = _R_TOPIC
                cb   = lambda word=label: self.theme_clicked.emit(word)
                node = _NodeItem(x, y, r, _COLOR_TOPIC, cb)
                font = font_topic
            else:
                r        = _R_DOC
                path_val = attrs.get("path", "")
                cb       = lambda p=path_val: self._open_file(p)
                node     = _NodeItem(x, y, r, _COLOR_DOC, cb)
                font     = font_doc

            self._scene_map.addItem(node)

            text_item = QGraphicsTextItem(label)
            text_item.setFont(font)
            text_item.setDefaultTextColor(QColor("#CCCCCC"))
            tw = text_item.boundingRect().width()
            text_item.setPos(x - tw / 2, y + r + 2)
            self._scene_map.addItem(text_item)

        rect = self._scene_map.sceneRect().adjusted(-30, -30, 30, 30)
        self._view_map.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    @staticmethod
    def _open_file(path: str) -> None:
        """Abre o arquivo no gerenciador padrão do SO."""
        if not path or not os.path.exists(path):
            return
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
