"""
Workers PyQt6 para operacoes assincronas da aba de Receitas do HERMES.
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from services.recipe_extractor import (
    RecipePlaylistExtractor,
    RecipeResult,
    extract_recipe,
)


class RecipeExtractWorker(QThread):
    """Extrai receita(s) de video em background.

    Para URL unica: emite recipe_ready uma vez, depois finished.
    Para playlist: emite progress + recipe_ready por item, depois finished.
    """

    identified = pyqtSignal(str, str, bool, int)   # (platform, title, is_playlist, count)
    progress   = pyqtSignal(int, int, str)          # (current, total, title)
    recipe_ready = pyqtSignal(object)               # RecipeResult
    finished   = pyqtSignal()
    error      = pyqtSignal(str)

    def __init__(
        self,
        url: str,
        *,
        model_size: str = "small",
        language: str = "auto",
        ollama_model: str = "qwen2.5:7b",
        recipes_dir: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.url          = url
        self.model_size   = model_size
        self.language     = language
        self.ollama_model = ollama_model
        self.recipes_dir  = recipes_dir
        self._cancelled   = False
        self.setPriority(QThread.Priority.LowPriority)

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc) or type(exc).__name__)

    def _run(self) -> None:
        # Detecta se e playlist antes de extrair
        try:
            import yt_dlp
        except ImportError:
            self.error.emit("yt-dlp nao encontrado. Instale com: pip install yt-dlp")
            return

        is_playlist = False
        playlist_urls: list[str] = []

        flat_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(flat_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            entries = info.get("entries") or []
            is_playlist = bool(entries)
            if is_playlist:
                for e in entries:
                    if not e:
                        continue
                    vurl = e.get("url") or e.get("webpage_url", "")
                    if vurl and not vurl.startswith("http"):
                        vurl = f"https://www.youtube.com/watch?v={vurl}"
                    if vurl:
                        playlist_urls.append(vurl)
                title   = info.get("title") or info.get("uploader") or ""
                platform = info.get("extractor_key") or info.get("ie_key") or "web"
                self.identified.emit(platform.lower(), title, True, len(playlist_urls))
            else:
                title    = info.get("title", "")
                platform = info.get("extractor_key") or info.get("ie_key") or "web"
                self.identified.emit(platform.lower(), title, False, 1)
        except Exception as exc:
            # Se a identificacao falhar, tenta extrair diretamente como video unico
            self.identified.emit("web", "", False, 1)

        if self._cancelled:
            return

        if is_playlist:
            total = len(playlist_urls)
            for i, vurl in enumerate(playlist_urls, start=1):
                if self._cancelled:
                    break
                result = extract_recipe(
                    vurl,
                    model_size=self.model_size,
                    language=self.language,
                    ollama_model=self.ollama_model,
                    recipes_dir=self.recipes_dir,
                )
                self.progress.emit(i, total, result.title or vurl)
                self.recipe_ready.emit(result)
        else:
            result = extract_recipe(
                self.url,
                model_size=self.model_size,
                language=self.language,
                ollama_model=self.ollama_model,
                recipes_dir=self.recipes_dir,
            )
            self.progress.emit(1, 1, result.title or self.url)
            self.recipe_ready.emit(result)

        self.finished.emit()
