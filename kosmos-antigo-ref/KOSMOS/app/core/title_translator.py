"""Tradução assíncrona de títulos de cards do KOSMOS.

Roda em background com prioridade BELOW_NORMAL. Mantém cache em memória
(article_id → título traduzido) que sobrevive enquanto o app está aberto.
Ao mudar o idioma alvo, o cache é limpo e as traduções são refeitas.

Integração:
  - MainWindow cria e inicia o TitleTranslator no startup.
  - set_target_lang(lang): atualiza o idioma e limpa cache.
  - enqueue_batch(items): enfileira lista de (article_id, title, source_lang).
  - pause() / resume(): usado pelo reader para dar prioridade à análise.
  - Sinal title_translated(article_id, translated) → MainWindow repassa às views.
"""

from __future__ import annotations

import json
import logging
import queue
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.paths import Paths

log = logging.getLogger("kosmos.title_translator")

_SENTINEL = (-1, "", None)


class TitleTranslator(QThread):
    """Worker de tradução de títulos em background.

    Sinais:
        title_translated(int, str): emitido após tradução bem-sucedida.
        status_message(str):        mensagem de progresso/erro para a barra de status.
    """

    title_translated = pyqtSignal(int, str)
    status_message   = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._queue:       queue.Queue    = queue.Queue()
        self._target_lang: str            = ""
        self._cache:       dict[int, str] = {}
        self._running:     bool           = True
        self._paused:      bool           = False

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def _cache_path(self) -> Path:
        return Paths.DATA / f"title_cache_{self._target_lang or 'none'}.json"

    def _load_cache(self) -> None:
        path = self._cache_path()
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self._cache = {int(k): v for k, v in raw.items()}
                log.debug("Cache de traduções carregado: %d entradas (%s)", len(self._cache), path.name)
            except Exception as exc:
                log.debug("Falha ao carregar cache de traduções: %s", exc)

    def save_cache(self) -> None:
        """Persiste o cache em disco (chamar no closeEvent da MainWindow)."""
        if not self._target_lang or not self._cache:
            return
        try:
            path = self._cache_path()
            path.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")
            log.debug("Cache de traduções salvo: %d entradas", len(self._cache))
        except Exception as exc:
            log.debug("Falha ao salvar cache de traduções: %s", exc)

    def set_target_lang(self, lang: str) -> None:
        """Define o idioma alvo; persiste cache anterior e carrega cache do novo idioma."""
        if lang != self._target_lang:
            self.save_cache()
            self._target_lang = lang
            self._cache.clear()
            self._load_cache()
            log.debug("Idioma de tradução alterado para '%s'.", lang)

    def enqueue_batch(self, items: list[tuple[int, str, "str | None"]]) -> None:
        """Enfileira lista de (article_id, title, source_lang) para tradução."""
        for article_id, title, source_lang in items:
            # Cache hit: emite imediatamente sem enfileirar
            if article_id in self._cache:
                self.title_translated.emit(article_id, self._cache[article_id])
                continue
            self._queue.put((article_id, title, source_lang))

    def pause(self) -> None:
        """Pausa traduções (usado quando artigo é aberto para liberar recursos)."""
        self._paused = True

    def resume(self) -> None:
        """Retoma traduções após fechar o reader."""
        self._paused = False

    def reapply_cache(self, article_ids: "list[int]") -> None:
        """Re-emite traduções em cache para os IDs fornecidos (chamado ao voltar do reader).

        Opera na thread principal — as emissões são diretas (sem fila), garantindo
        que os cards recebam títulos traduzidos antes de serem exibidos ao usuário.
        """
        for article_id in article_ids:
            if article_id in self._cache:
                self.title_translated.emit(article_id, self._cache[article_id])

    def stop(self) -> None:
        self._running = False
        self._queue.put(_SENTINEL)

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    def run(self) -> None:
        import sys as _sys, os as _os
        if _sys.platform != "win32":
            try:
                _os.nice(15)
            except OSError:
                pass
        else:
            try:
                import ctypes as _ct
                _ct.windll.kernel32.SetPriorityClass(
                    _ct.windll.kernel32.GetCurrentProcess(), 0x00004000)
            except Exception:
                pass

        while self._running:
            if self._paused:
                self.msleep(200)
                continue

            try:
                article_id, title, source_lang = self._queue.get(timeout=2)
            except queue.Empty:
                continue

            if article_id == -1:
                break

            if not self._target_lang:
                continue

            # Já traduzido (pode ter chegado ao cache enquanto estava na fila)
            if article_id in self._cache:
                self.title_translated.emit(article_id, self._cache[article_id])
                continue

            # Mesmo idioma: emite original
            if source_lang and source_lang.lower()[:2] == self._target_lang.lower()[:2]:
                self._cache[article_id] = title
                self.title_translated.emit(article_id, title)
                continue

            try:
                self.status_message.emit("Traduzindo títulos…")
                from app.core.translator import translate_text
                translated = translate_text(title, "auto", self._target_lang)
                if translated:
                    self._cache[article_id] = translated
                    self.title_translated.emit(article_id, translated)
            except Exception as exc:
                log.debug("Tradução falhou (artigo %d): %s", article_id, exc)
                self.status_message.emit(f"⚠ Falha ao traduzir título {article_id}: {exc}")
