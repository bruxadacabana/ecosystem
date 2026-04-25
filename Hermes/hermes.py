#!/usr/bin/env python3
"""
Hermes — Mensageiro Universal
Baixar e transcrever vídeos do YouTube, TikTok e 1000+ sites.
PyQt6 · Ecossistema local-first · Design Bible v2.0
"""

import sys
import os
import json
import logging
import logging.handlers
import re
import shutil
from datetime import datetime
from pathlib import Path

from api_server import ApiSignalBridge, HermesApiServer

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QFileDialog,
    QTabWidget, QFrame, QProgressBar, QListWidget, QListWidgetItem,
    QSizePolicy, QAbstractItemView, QSplitter, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

# Componentes e estilos partilhados do ecossistema
sys.path.insert(0, str(Path(__file__).parent.parent))
from ecosystem_client import read_ecosystem
from ecosystem_qt import (
    PAPER, PAPER_DARK, PAPER_DARKER,
    INK, INK_LIGHT, INK_FAINT, INK_GHOST,
    ACCENT, RIBBON, RIBBON_LIGHT, ACCENT_GREEN, STAMP, RULE,
    load_ecosystem_fonts, build_qss,
    AlchemyLoaderQt, WaxSealQt, CandleGlowQt, VignetteWidget,
)

APP_DIR  = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _resolve_prefs_file() -> Path:
    """Retorna settings.json em {hermes.config_path} se definido, senão .prefs.json local."""
    try:
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "ecosystem" / "ecosystem.json",
            Path.home() / ".local" / "share" / "ecosystem" / "ecosystem.json",
        ]
        for eco_path in candidates:
            if eco_path.exists():
                data = json.loads(eco_path.read_text(encoding="utf-8"))
                config_dir = data.get("hermes", {}).get("config_path", "")
                if config_dir:
                    p = Path(config_dir)
                    p.mkdir(parents=True, exist_ok=True)
                    return p / "settings.json"
    except Exception:
        pass
    return APP_DIR / ".prefs.json"


PREFS_FILE = _resolve_prefs_file()

_LOGS_DIR = DATA_DIR / "logs"


def _setup_logger() -> None:
    """Configura logging para arquivo rotativo e stderr."""
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.handlers.TimedRotatingFileHandler(
                _LOGS_DIR / "hermes.log",
                when="midnight",
                backupCount=7,
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
    )
    for noisy_lib in ("yt_dlp", "urllib3", "httpx"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)


_log_file = logging.getLogger("hermes")


# ── Preferências ──────────────────────────────────────────────────────────────
_LEGACY_PREFS = APP_DIR / ".prefs.json"

def load_prefs() -> dict:
    # Tenta o caminho primário; fallback para arquivo legado na pasta do app
    for candidate in (PREFS_FILE, _LEGACY_PREFS):
        try:
            if candidate.exists():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_prefs(p: dict):
    try:
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFS_FILE.write_text(json.dumps(p, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── Idiomas ───────────────────────────────────────────────────────────────────
LANGUAGES = {
    "auto": "Automático",   "pt": "Português",   "en": "Inglês",
    "es":   "Espanhol",     "fr": "Francês",     "de": "Alemão",
    "it":   "Italiano",     "ja": "Japonês",     "ko": "Coreano",
    "zh":   "Chinês",       "ru": "Russo",       "ar": "Árabe",
    "nl":   "Holandês",     "pl": "Polonês",     "tr": "Turco",
    "sv":   "Sueco",        "da": "Dinamarquês", "fi": "Finlandês",
    "uk":   "Ucraniano",    "hi": "Hindi",
}
LANG_DISPLAY = [f"{v}  [{k}]" for k, v in LANGUAGES.items()]
LANG_CODES   = list(LANGUAGES.keys())
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]


# ── Utilitários — detecção e device ──────────────────────────────────────────
def detect_device() -> tuple[str, str]:
    try:
        import torch
        if not torch.cuda.is_available():
            return "cpu", "CPU (CUDA indisponível)"
        vram_mb  = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
        gpu_name = torch.cuda.get_device_properties(0).name
        if vram_mb < 3072:
            return "cpu", f"CPU (GPU {gpu_name} — {vram_mb} MB insuficiente)"
        return "cuda", f"GPU {gpu_name} ({vram_mb} MB)"
    except Exception:
        return "cpu", "CPU"


def is_playlist_url(url: str) -> bool:
    return bool(re.search(
        r"(playlist|list="                               # YouTube playlist params
        r"|/channel/|/@[^/]+/?$|/c/|/user/"             # YouTube channel URLs
        r"|twitch\.tv/[^/]+/(videos|clips|schedule)"    # Twitch collections
        r"|soundcloud\.com/[^/]+/sets/"                 # SoundCloud sets
        r"|vimeo\.com/(channels|groups|album)/"         # Vimeo collections
        r"|dailymotion\.com/playlist/"                  # Dailymotion playlists
        r"|bandcamp\.com/album/"                        # Bandcamp albums
        r"|space\.bilibili\.com/"                       # Bilibili user space
        r"|nicovideo\.jp/(user|mylist)/)"               # Niconico user/mylist
        , url, re.I))


# ── Utilitários — formatos yt-dlp ─────────────────────────────────────────────
def build_format_list(info: dict) -> list[dict]:
    fmts = info.get("formats", [])
    options = [
        {"label": "✦  Melhor qualidade (vídeo + áudio)", "format_id": "bestvideo+bestaudio/best", "ext": "mp4"},
        {"label": "◈  Apenas áudio (MP3)",                "format_id": "bestaudio",               "ext": "mp3"},
        {"label": "─" * 52,                               "format_id": None,                       "ext": None},
    ]
    seen: set = set()
    for f in reversed(fmts):
        if f.get("vcodec", "none") == "none":
            continue
        height = f.get("height") or 0
        ext    = f.get("ext", "?")
        key    = (height, ext)
        if key in seen:
            continue
        seen.add(key)
        fps      = f.get("fps") or 0
        tbr      = f.get("tbr") or f.get("vbr") or 0
        has_aud  = f.get("acodec", "none") != "none"
        res_str  = f"{height}p" if height else "?"
        fps_str  = f" {fps:.0f}fps" if fps and fps > 30 else ""
        aud_str  = " + áudio" if has_aud else " [sem áudio]"
        tbr_str  = f" ~{tbr:.0f}k" if tbr else ""
        options.append({
            "label":     f"  {res_str}{fps_str}  —  {ext.upper()}{tbr_str}{aud_str}",
            "format_id": f.get("format_id", ""),
            "ext":       ext,
        })
    return options


# Formatos fixos para download de playlist inteira (sem inspecionar cada vídeo)
_PLAYLIST_FORMATS: list[dict] = [
    {"label": "✦  Melhor qualidade (vídeo + áudio)", "format_id": "bestvideo+bestaudio/best", "ext": "mp4"},
    {"label": "◈  Apenas áudio (MP3)",                "format_id": "bestaudio",               "ext": "mp3"},
]


# ── Utilitários — markdown ────────────────────────────────────────────────────
def build_markdown(title: str, url: str, info: dict, result: dict, forced_lang: str,
                   is_local: bool = False) -> str:
    now       = datetime.now().strftime("%Y-%m-%d %H:%M")
    dur_s     = info.get("duration", 0)
    duration  = f"{dur_s // 60}m {dur_s % 60}s" if dur_s else "desconhecida"
    detected  = result.get("language", "?").upper()
    lang_note = detected if forced_lang == "auto" else f"{forced_lang.upper()} (forçado)"
    if is_local:
        fonte_line  = f"> **Arquivo:** `{url}`  "
        origem_line = f"> **Origem:** arquivo local  "
    else:
        channel     = info.get("uploader") or info.get("channel") or "desconhecido"
        fonte_line  = f"> **Fonte:** [{url}]({url})  "
        origem_line = f"> **Canal:** {channel}  "
    lines = [
        f"# {title}", "",
        fonte_line,
        origem_line,
        f"> **Duração:** {duration}  ",
        f"> **Idioma:** {lang_note}  ",
        f"> **Gerado em:** {now}",
        "", "---", "", "## Transcrição", "",
    ]
    for seg in result.get("segments", []):
        start = int(seg["start"])
        mm, ss = divmod(start, 60)
        lines.append(f"**[{mm:02d}:{ss:02d}]** {seg['text'].strip()}")
        lines.append("")
    if not result.get("segments"):
        for para in result.get("text", "").split("\n"):
            if para.strip():
                lines.append(para.strip())
                lines.append("")
    return "\n".join(lines)


# ── Utilitários — markdown Mnemosyne ─────────────────────────────────────────
def build_mnemosyne_markdown(title: str, url: str, duration: str, full_md: str) -> str:
    """Markdown com frontmatter YAML para indexação pelo Mnemosyne.
    Remove timestamps e cabeçalhos do markdown completo, deixando
    apenas o texto limpo da transcrição."""
    date       = datetime.now().strftime("%Y-%m-%d")
    title_safe = title.replace('"', '\\"')

    clean_lines: list[str] = []
    for line in full_md.splitlines():
        stripped = line.strip()
        if (stripped.startswith("#")
                or stripped.startswith(">")
                or stripped == "---"
                or stripped == "## Transcrição"):
            continue
        # Remove prefixo **[MM:SS]** mas mantém o texto
        clean = re.sub(r"^\*\*\[\d{2}:\d{2}\]\*\*\s*", "", line)
        clean_lines.append(clean)

    body = "\n".join(clean_lines).strip()

    return "\n".join([
        "---",
        f'title: "{title_safe}"',
        f"date: {date}",
        f"source: {url}",
        f"duration: {duration}",
        "---",
        "",
        body,
    ])


# ── Workers ───────────────────────────────────────────────────────────────────
class DownloadWorker(QThread):
    log      = pyqtSignal(str, str)   # (mensagem, tag: ok|err|warn|"")
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)        # título do vídeo
    error    = pyqtSignal(str)

    def __init__(self, url: str, fmt: dict, outdir: str, parent=None,
                 playlist_mode: bool = False):
        super().__init__(parent)
        self.url           = url
        self.fmt           = fmt
        self.outdir        = outdir
        self.playlist_mode = playlist_mode
        self._cancelled    = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            import yt_dlp
        except ImportError:
            self.error.emit("yt-dlp não encontrado. Instale com: pip install yt-dlp")
            return

        def hook(d):
            if self._cancelled:
                raise Exception("Cancelado.")
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done  = d.get("downloaded_bytes", 0)
                if total:
                    self.progress.emit(int(done / total * 100))
            elif d.get("status") == "finished":
                self.progress.emit(100)
                self.log.emit("Processando…", "ok")

        fid      = self.fmt["format_id"]
        is_audio = fid == "bestaudio"
        pp = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}] \
             if is_audio else \
             [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]

        outtmpl = os.path.join(
            self.outdir,
            "%(playlist_index)02d - %(title)s.%(ext)s" if self.playlist_mode else "%(title)s.%(ext)s",
        )
        ydl_opts = {
            "format":              fid,
            "outtmpl":             outtmpl,
            "postprocessors":      pp,
            "quiet":               True,
            "no_warnings":         True,
            "progress_hooks":      [hook],
            "noplaylist":          not self.playlist_mode,
            "merge_output_format": "mp4",
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                self.finished.emit(info.get("title") or "vídeo")
        except Exception as exc:
            if self._cancelled:
                self.log.emit("Download cancelado.", "warn")
            else:
                self.error.emit(str(exc))


class InspectWorker(QThread):
    log      = pyqtSignal(str, str)
    finished = pyqtSignal(dict, list)  # (info, formats)
    error    = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            import yt_dlp
        except ImportError:
            self.error.emit("yt-dlp não encontrado.")
            return
        self.log.emit("Inspecionando URL…", "")
        try:
            opts = {"quiet": True, "no_warnings": True, "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            fmts = build_format_list(info)
            self.finished.emit(info, fmts)
        except Exception as exc:
            self.error.emit(str(exc))


class PlaylistIndexWorker(QThread):
    log      = pyqtSignal(str, str)
    finished = pyqtSignal(list)
    error    = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            import yt_dlp
        except ImportError:
            self.error.emit("yt-dlp não encontrado.")
            return
        self.log.emit("Lendo playlist…", "")
        try:
            opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            entries = []
            for e in (info.get("entries") or []):
                if not e:
                    continue
                vurl = e.get("url") or e.get("webpage_url", "")
                if vurl and not vurl.startswith("http"):
                    vurl = f"https://www.youtube.com/watch?v={vurl}"
                entries.append({"url": vurl, "title": e.get("title", "(sem título)")})
            self.finished.emit(entries)
        except Exception as exc:
            self.error.emit(str(exc))


class TranscribeWorker(QThread):
    log      = pyqtSignal(str, str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str, str, str, str, str)   # (markdown_text, output_path, title, source, duration)
    error    = pyqtSignal(str)

    def __init__(self, source: str, is_local: bool, model_size: str, language: str,
                 cpu_limit: int, outdir: str, parent=None):
        super().__init__(parent)
        self.source     = source
        self.is_local   = is_local
        self.model_size = model_size
        self.language   = language
        self.cpu_limit  = cpu_limit
        self.outdir     = outdir
        self._cancelled = False
        self._model_cache: list = []

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            import whisper
        except ImportError as e:
            self.error.emit(f"Dependência não encontrada: {e}. Instale openai-whisper.")
            return

        if self._cancelled: return
        self._apply_cpu_limit()

        if self.is_local:
            self._run_local(whisper)
        else:
            self._run_url(whisper)

    def _run_local(self, whisper) -> None:
        audio_path = self.source
        title      = Path(audio_path).stem
        self.log.emit(f"Arquivo local: {Path(audio_path).name}", "")
        self.progress.emit(20)
        try:
            self._transcribe_and_save(whisper, audio_path, title, self.source,
                                      info={}, is_local=True)
        except Exception as exc:
            if self._cancelled:
                self.log.emit("Transcrição cancelada.", "warn")
            else:
                self.error.emit(str(exc))

    def _run_url(self, whisper) -> None:
        try:
            import yt_dlp
        except ImportError as e:
            self.error.emit(f"Dependência não encontrada: {e}. Instale yt-dlp.")
            return

        import tempfile

        self.log.emit("Baixando áudio…", "")
        self.progress.emit(10)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                ydl_opts = {
                    "format":         "bestaudio/best",
                    "outtmpl":        os.path.join(tmpdir, "%(title)s.%(ext)s"),
                    "postprocessors": [{"key": "FFmpegExtractAudio",
                                        "preferredcodec": "mp3", "preferredquality": "128"}],
                    "quiet":          True,
                    "no_warnings":    True,
                    "noplaylist":     True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info       = ydl.extract_info(self.source, download=True)
                    audio_path = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"
                    title      = info.get("title", "transcrição")

                if self._cancelled: return
                self.progress.emit(40)
                self._transcribe_and_save(whisper, audio_path, title, self.source,
                                          info=info, is_local=False)

        except Exception as exc:
            if self._cancelled:
                self.log.emit("Transcrição cancelada.", "warn")
            else:
                self.error.emit(str(exc))

    def _transcribe_and_save(self, whisper, audio_path: str, title: str,
                              source: str, info: dict, is_local: bool) -> None:
        device, _ = detect_device()
        cache_key = (self.model_size, device)
        if not self._model_cache or self._model_cache[0][0] != cache_key:
            self.log.emit(f"Carregando modelo Whisper ({self.model_size}) em {device.upper()}…", "")
            model = whisper.load_model(self.model_size, device=device)
            self._model_cache.clear()
            self._model_cache.append((cache_key, model))
        else:
            model = self._model_cache[0][1]

        if self._cancelled: return
        self.progress.emit(60)

        lang_arg = self.language if self.language != "auto" else None
        self.log.emit(f"Transcrevendo… idioma: {self.language}", "")
        result   = model.transcribe(audio_path, verbose=False, language=lang_arg)
        self.progress.emit(90)

        dur_s    = info.get("duration", 0)
        duration = f"{dur_s // 60}m {dur_s % 60}s" if dur_s else "desconhecida"
        md_text  = build_markdown(title, source, info, result, self.language, is_local=is_local)
        safe     = re.sub(r'[<>:"/\\|?*]', "_", title)[:60]
        out_path = os.path.join(self.outdir, f"{datetime.now().strftime('%Y%m%d_%H%M')}_{safe}.md")
        Path(out_path).write_text(md_text, encoding="utf-8")
        self.progress.emit(100)
        self.finished.emit(md_text, out_path, title, source, duration)

    def _apply_cpu_limit(self):
        import math
        total   = os.cpu_count() or 1
        threads = max(1, math.ceil(total * self.cpu_limit / 100))
        os.environ["OMP_NUM_THREADS"] = str(threads)
        os.environ["MKL_NUM_THREADS"] = str(threads)
        try:
            import torch
            torch.set_num_threads(threads)
        except Exception:
            pass


class BatchTranscribeWorker(QThread):
    log            = pyqtSignal(str, str)
    batch_progress = pyqtSignal(int, int)      # (current, total)
    step_done      = pyqtSignal(str, str, str) # (out_path, title, md_text)
    finished       = pyqtSignal(int, int)      # (done, total)

    def __init__(self, entries: list, model_size: str, language: str,
                 cpu_limit: int, outdir: str, parent=None):
        super().__init__(parent)
        self.entries    = entries
        self.model_size = model_size
        self.language   = language
        self.cpu_limit  = cpu_limit
        self.outdir     = outdir
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _apply_cpu_limit(self) -> None:
        import math
        total   = os.cpu_count() or 1
        threads = max(1, math.ceil(total * self.cpu_limit / 100))
        os.environ["OMP_NUM_THREADS"] = str(threads)
        os.environ["MKL_NUM_THREADS"] = str(threads)
        try:
            import torch
            torch.set_num_threads(threads)
        except Exception:
            pass

    def run(self) -> None:
        try:
            import whisper
        except ImportError as e:
            self.log.emit(f"Dependência não encontrada: {e}", "err")
            return
        try:
            import yt_dlp
        except ImportError as e:
            self.log.emit(f"Dependência não encontrada: {e}", "err")
            return
        import tempfile

        self._apply_cpu_limit()
        device, _ = detect_device()
        self.log.emit(f"Carregando modelo {self.model_size} ({device.upper()})…", "")
        try:
            model = whisper.load_model(self.model_size, device=device)
        except Exception as e:
            self.log.emit(f"Erro ao carregar modelo: {e}", "err")
            return

        lang_arg = self.language if self.language != "auto" else None
        total    = len(self.entries)
        done     = 0

        for i, entry in enumerate(self.entries):
            if self._cancelled:
                self.log.emit("Transcrição em lote cancelada.", "warn")
                break

            url   = entry["url"]
            title = entry.get("title", f"item_{i + 1}")
            self.batch_progress.emit(i + 1, total)
            self.log.emit(f"[{i + 1}/{total}] Baixando: {title}", "")

            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    ydl_opts = {
                        "format":         "bestaudio/best",
                        "outtmpl":        os.path.join(tmpdir, "%(title)s.%(ext)s"),
                        "postprocessors": [{"key": "FFmpegExtractAudio",
                                            "preferredcodec": "mp3",
                                            "preferredquality": "128"}],
                        "quiet":          True,
                        "no_warnings":    True,
                        "noplaylist":     True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info       = ydl.extract_info(url, download=True)
                        audio_path = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"
                        real_title = info.get("title", title)

                    if self._cancelled:
                        break

                    self.log.emit(f"[{i + 1}/{total}] Transcrevendo: {real_title}", "")
                    result = model.transcribe(audio_path, verbose=False, language=lang_arg)

                dur_s    = info.get("duration", 0)
                duration = f"{dur_s // 60}m {dur_s % 60}s" if dur_s else "desconhecida"
                md_text  = build_markdown(real_title, url, info, result, self.language)
                safe     = re.sub(r'[<>:"/\\|?*]', "_", real_title)[:60]
                out_path = os.path.join(
                    self.outdir,
                    f"{datetime.now().strftime('%Y%m%d_%H%M')}_{safe}.md",
                )
                Path(out_path).write_text(md_text, encoding="utf-8")
                done += 1
                self.log.emit(f"[{i + 1}/{total}] ✓ {real_title}", "ok")
                self.step_done.emit(out_path, real_title, md_text)

            except OSError as e:
                self.log.emit(f"[{i + 1}/{total}] Erro de I/O em '{title}': {e}", "err")
            except Exception as e:
                self.log.emit(f"[{i + 1}/{total}] Erro em '{title}': {e}", "err")

        self.finished.emit(done, total)


# ── Janela principal ──────────────────────────────────────────────────────────
class HermesApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hermes")
        self.resize(920, 820)

        self._prefs           = load_prefs()
        self._formats: list          = []
        self._info: dict             = {}
        self._playlist: list         = []
        self._from_playlist_select   = False  # mantém playlist visível ao inspecionar vídeo individual
        self._last_md: str    = ""
        self._worker          = None
        self._device, self._device_label = detect_device()

        display_family, mono_family = load_ecosystem_fonts()
        self._display = display_family
        self._mono    = mono_family

        self.setStyleSheet(build_qss(display_family, mono_family))
        self._build_ui()
        self._load_prefs()
        self._load_history()

        self._api_port   = self._prefs.get("api_port", 7072)
        self._api_bridge = ApiSignalBridge(self)
        self._api_server = HermesApiServer(self._api_port, self._api_bridge)
        self._api_bridge.download_requested.connect(self._on_api_download)
        self._api_bridge.transcribe_requested.connect(self._on_api_transcribe)
        self._api_server.start()

        self._register_ecosystem()
        self._check_ffmpeg()
        self._log(f"Hermes iniciado. Dispositivo: {self._device_label}", "ok")

    def _register_ecosystem(self) -> None:
        try:
            import platform as _platform
            from ecosystem_client import write_section
            script = "iniciar.bat" if _platform.system() == "Windows" else "iniciar.sh"
            data: dict = {"exe_path": str(APP_DIR / script), "api_port": self._api_port}
            outdir = self._prefs.get("outdir", "")
            if outdir:
                data["output_dir"] = outdir
            write_section("hermes", data)
        except Exception:
            pass

    def _check_ffmpeg(self) -> None:
        if not shutil.which("ffmpeg"):
            self._log(
                "⚠ ffmpeg não encontrado — downloads e transcrições podem falhar. "
                "Instale ffmpeg e certifique-se de que está no PATH.",
                "warn",
            )

    # ── Construção da UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(32, 24, 32, 20)
        root.setSpacing(0)

        # Cabeçalho
        root.addLayout(self._build_header())
        root.addSpacing(16)
        root.addWidget(self._rule())
        root.addSpacing(14)

        # URL (compartilhada)
        root.addWidget(self._section_label("ENDEREÇO DO VÍDEO OU PLAYLIST"))
        root.addSpacing(4)
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "YouTube · Twitch · Vimeo · TikTok · Twitter/X · Instagram · Reddit · Bilibili · 1000+ sites")
        self.url_edit.setToolTip(
            "Suporta qualquer site do yt-dlp:\n"
            "YouTube, Twitch, Vimeo, TikTok, Twitter/X, Instagram,\n"
            "Reddit, Dailymotion, Bilibili, Niconico, SoundCloud e 1000+ outros.\n\n"
            "Lista completa: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md")
        self.url_edit.returnPressed.connect(self._on_url_enter)
        url_row.addWidget(self.url_edit)
        self.paste_btn = QPushButton("COLAR")
        self.paste_btn.clicked.connect(self._paste_url)
        url_row.addWidget(self.paste_btn)
        root.addLayout(url_row)
        root.addSpacing(14)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_download_tab(), "BAIXAR")
        self.tabs.addTab(self._build_transcribe_tab(), "TRANSCREVER")
        root.addWidget(self.tabs)
        root.addSpacing(12)

        # Output dir
        root.addWidget(self._rule())
        root.addSpacing(10)
        out_row = QHBoxLayout()
        out_row.addWidget(self._section_label("PASTA DE SAÍDA"))
        out_row.addSpacing(8)
        self.outdir_edit = QLineEdit(str(DATA_DIR))
        out_row.addWidget(self.outdir_edit)
        self._home_btn = QPushButton("⌂")
        self._home_btn.setFixedWidth(30)
        self._home_btn.setToolTip("Restaurar pasta sincronizada (configurada no HUB)")
        self._home_btn.clicked.connect(self._set_home_outdir)
        out_row.addWidget(self._home_btn)
        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(36)
        browse_btn.clicked.connect(self._pick_dir)
        out_row.addWidget(browse_btn)
        self.outdir_edit.textChanged.connect(self._load_history)
        root.addLayout(out_row)
        root.addSpacing(12)

        # Log
        root.addWidget(self._section_label("REGISTRO"))
        root.addSpacing(4)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        self.log_box.setMaximumHeight(180)
        root.addWidget(self.log_box)
        root.addSpacing(10)

        # Rodapé
        footer = QHBoxLayout()
        self.open_btn = QPushButton("ABRIR PASTA")
        self.open_btn.clicked.connect(self._open_outdir)
        footer.addWidget(self.open_btn)
        self.copy_md_btn = QPushButton("COPIAR MARKDOWN")
        self.copy_md_btn.setEnabled(False)
        self.copy_md_btn.clicked.connect(self._copy_md)
        footer.addWidget(self.copy_md_btn)
        footer.addStretch()
        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("meta")
        footer.addWidget(self.status_lbl)
        root.addLayout(footer)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        title = QLabel("Hermes")
        title.setObjectName("title")
        row.addWidget(title)
        row.addSpacing(16)
        sub_col = QVBoxLayout()
        sub_col.addSpacing(10)
        sub = QLabel("MENSAGEIRO UNIVERSAL")
        sub.setObjectName("subtitle")
        sub_col.addWidget(sub)
        device_lbl = QLabel(self._device_label.upper())
        device_lbl.setObjectName("meta")
        sub_col.addWidget(device_lbl)
        row.addLayout(sub_col)
        row.addStretch()
        return row

    def _build_download_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Botões de ação
        action_row = QHBoxLayout()
        self.inspect_btn = QPushButton("✦ INSPECIONAR")
        self.inspect_btn.setObjectName("primary")
        self.inspect_btn.clicked.connect(self._inspect)
        action_row.addWidget(self.inspect_btn)
        self.dl_btn = QPushButton("BAIXAR")
        self.dl_btn.setEnabled(False)
        self.dl_btn.clicked.connect(self._start_download)
        action_row.addWidget(self.dl_btn)
        self.dl_cancel_btn = QPushButton("CANCELAR")
        self.dl_cancel_btn.setObjectName("danger")
        self.dl_cancel_btn.setEnabled(False)
        self.dl_cancel_btn.clicked.connect(self._cancel)
        action_row.addWidget(self.dl_cancel_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Info do vídeo
        self.video_info_lbl = QLabel()
        self.video_info_lbl.setObjectName("meta")
        self.video_info_lbl.setWordWrap(True)
        layout.addWidget(self.video_info_lbl)

        # Lista de playlist (visível se URL for playlist)
        self.playlist_lbl = self._section_label("PLAYLIST")
        self.playlist_lbl.hide()
        layout.addWidget(self.playlist_lbl)
        self.playlist_list = QListWidget()
        self.playlist_list.setMaximumHeight(120)
        self.playlist_list.hide()
        self.playlist_list.itemSelectionChanged.connect(self._on_playlist_select)
        layout.addWidget(self.playlist_list)

        self.playlist_hint_lbl = QLabel(
            "Selecione um vídeo acima para ver as opções de qualidade e baixar individualmente.\n"
            "Ou use os formatos abaixo para baixar toda a playlist de uma vez."
        )
        self.playlist_hint_lbl.setObjectName("meta")
        self.playlist_hint_lbl.setWordWrap(True)
        self.playlist_hint_lbl.hide()
        layout.addWidget(self.playlist_hint_lbl)

        # Formatos
        layout.addWidget(self._section_label("FORMATO / QUALIDADE"))
        self.fmt_combo = QComboBox()
        self.fmt_combo.setEnabled(False)
        self.fmt_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.fmt_combo.setToolTip(
            "Algumas plataformas (ex: TikTok, Instagram, Twitter/X) disponibilizam\n"
            "apenas vídeo+áudio já mesclados — 'Melhor qualidade' funcionará sempre.")
        layout.addWidget(self.fmt_combo)

        # Progresso
        self.dl_progress = QProgressBar()
        self.dl_progress.setValue(0)
        layout.addWidget(self.dl_progress)

        layout.addStretch()
        return w

    def _build_transcribe_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Opções
        opts_row = QHBoxLayout()
        opts_row.addWidget(self._section_label("MODELO"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(WHISPER_MODELS)
        self.model_combo.setCurrentText("small")
        self.model_combo.setFixedWidth(100)
        opts_row.addWidget(self.model_combo)
        opts_row.addSpacing(20)
        opts_row.addWidget(self._section_label("IDIOMA"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANG_DISPLAY)
        self.lang_combo.setFixedWidth(180)
        opts_row.addWidget(self.lang_combo)
        opts_row.addSpacing(20)
        opts_row.addWidget(self._section_label("LIMITE CPU"))
        self.cpu_combo = QComboBox()
        self.cpu_combo.addItems(["25%", "50%", "75%", "100%"])
        self.cpu_combo.setCurrentText("100%")
        self.cpu_combo.setFixedWidth(80)
        if self._device == "cuda":
            self.cpu_combo.setEnabled(False)
        opts_row.addWidget(self.cpu_combo)
        opts_row.addStretch()
        layout.addLayout(opts_row)

        # Arquivo local (alternativa à URL)
        local_row = QHBoxLayout()
        local_row.addWidget(self._section_label("ARQUIVO LOCAL"))
        local_row.addSpacing(8)
        self.local_file_edit = QLineEdit()
        self.local_file_edit.setPlaceholderText(
            "Opcional — selecione um arquivo de vídeo ou áudio local (mp4, mkv, mp3, wav…)")
        local_row.addWidget(self.local_file_edit)
        local_browse_btn = QPushButton("…")
        local_browse_btn.setFixedWidth(36)
        local_browse_btn.clicked.connect(self._pick_local_file)
        local_row.addWidget(local_browse_btn)
        layout.addLayout(local_row)

        # Botões
        action_row = QHBoxLayout()
        self.tr_btn = QPushButton("☿ TRANSCREVER")
        self.tr_btn.setObjectName("primary")
        self.tr_btn.clicked.connect(self._start_transcribe)
        action_row.addWidget(self.tr_btn)
        self.batch_tr_btn = QPushButton("TRANSCREVER PLAYLIST")
        self.batch_tr_btn.setEnabled(False)
        self.batch_tr_btn.hide()
        self.batch_tr_btn.clicked.connect(self._start_batch_transcribe)
        action_row.addWidget(self.batch_tr_btn)
        self.tr_cancel_btn = QPushButton("CANCELAR")
        self.tr_cancel_btn.setObjectName("danger")
        self.tr_cancel_btn.setEnabled(False)
        self.tr_cancel_btn.clicked.connect(self._cancel)
        action_row.addWidget(self.tr_cancel_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Progresso
        self.tr_progress = QProgressBar()
        self.tr_progress.setValue(0)
        layout.addWidget(self.tr_progress)

        # Integração Mnemosyne
        layout.addWidget(self._rule())
        mnemo_row = QHBoxLayout()
        mnemo_row.addWidget(self._section_label("PASTA DO MNEMOSYNE"))
        mnemo_row.addSpacing(8)
        self.mnemo_dir_edit = QLineEdit()
        self.mnemo_dir_edit.setPlaceholderText("Pasta monitorada pelo Mnemosyne… (veja ecosystem.json)")
        self.mnemo_dir_edit.textChanged.connect(self._on_mnemo_dir_changed)
        mnemo_row.addWidget(self.mnemo_dir_edit)
        mnemo_browse_btn = QPushButton("…")
        mnemo_browse_btn.setFixedWidth(36)
        mnemo_browse_btn.clicked.connect(self._pick_mnemo_dir)
        mnemo_row.addWidget(mnemo_browse_btn)
        layout.addLayout(mnemo_row)

        self.mnemo_check = QCheckBox("Indexar no Mnemosyne após transcrever")
        self.mnemo_check.setEnabled(False)
        layout.addWidget(self.mnemo_check)
        layout.addWidget(self._rule())

        # Preview do markdown
        layout.addWidget(self._section_label("PRÉVIA DA TRANSCRIÇÃO"))
        self.md_preview = QTextEdit()
        self.md_preview.setReadOnly(True)
        self.md_preview.setPlaceholderText("A transcrição gerada aparecerá aqui…")
        layout.addWidget(self.md_preview)

        # Histórico de transcrições
        layout.addSpacing(6)
        layout.addWidget(self._section_label("HISTÓRICO DE TRANSCRIÇÕES"))
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(110)
        self.history_list.setToolTip("Clique num item para carregar na prévia")
        self.history_list.itemClicked.connect(self._on_history_select)
        layout.addWidget(self.history_list)

        return w

    # ── Helpers de UI ─────────────────────────────────────────────────────────
    def _rule(self) -> QFrame:
        f = QFrame()
        f.setObjectName("rule")
        f.setFixedHeight(1)
        return f

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section")
        return lbl

    # ── Log ───────────────────────────────────────────────────────────────────
    def _log(self, msg: str, tag: str = ""):
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {"ok": ACCENT_GREEN, "err": RIBBON, "warn": ACCENT, "": INK_FAINT}
        color = colors.get(tag, INK_FAINT)
        self.log_box.append(
            f'<span style="color:{INK_GHOST}; font-size:10px">{ts}</span>'
            f'<span style="color:{INK_GHOST}">  |  </span>'
            f'<span style="color:{color}">{msg}</span>'
        )
        if tag == "err":
            _log_file.error(msg)
        elif tag == "warn":
            _log_file.warning(msg)
        else:
            _log_file.info(msg)

    # ── Preferências ──────────────────────────────────────────────────────────
    def _load_prefs(self):
        # Pasta de saída: ecosystem.json é sempre o ponto de partida.
        # Prefs é fallback para quando ecosystem não está configurado.
        self._set_home_outdir(silent=True)
        if not self.outdir_edit.text() and "outdir" in self._prefs:
            self.outdir_edit.setText(self._prefs["outdir"])
        if "model" in self._prefs:
            self.model_combo.setCurrentText(self._prefs["model"])
        if "lang_idx" in self._prefs:
            self.lang_combo.setCurrentIndex(self._prefs["lang_idx"])
        if "cpu_limit" in self._prefs:
            self.cpu_combo.setCurrentText(self._prefs["cpu_limit"])
        # Pasta do Mnemosyne: preferência salva > sugestão do ecosystem.json
        if "mnemo_dir" in self._prefs:
            self.mnemo_dir_edit.setText(self._prefs["mnemo_dir"])
        else:
            try:
                eco   = read_ecosystem()
                paths = eco.get("mnemosyne", {}).get("index_paths", [])
                if paths:
                    self.mnemo_dir_edit.setText(paths[0])
            except Exception:
                pass
        if self._prefs.get("mnemo_check") and self.mnemo_dir_edit.text().strip():
            self.mnemo_check.setChecked(True)

    def _save_prefs(self):
        save_prefs({
            "outdir":      self.outdir_edit.text(),
            "model":       self.model_combo.currentText(),
            "lang_idx":    self.lang_combo.currentIndex(),
            "cpu_limit":   self.cpu_combo.currentText(),
            "mnemo_dir":   self.mnemo_dir_edit.text(),
            "mnemo_check": self.mnemo_check.isChecked(),
        })

    def closeEvent(self, event):
        self._save_prefs()
        self._api_server.stop()
        super().closeEvent(event)

    # ── Ações compartilhadas ──────────────────────────────────────────────────
    def _paste_url(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.url_edit.setText(text)

    def _on_url_enter(self):
        if self.tabs.currentIndex() == 0:
            self._inspect()
        else:
            self._start_transcribe()

    def _set_home_outdir(self, silent: bool = False) -> None:
        """Preenche outdir_edit com a pasta sincronizada definida no HUB."""
        try:
            eco_outdir = read_ecosystem().get("hermes", {}).get("output_dir", "")
            if eco_outdir:
                self.outdir_edit.setText(eco_outdir)
            elif not silent:
                self.status_lbl.setText("Configure o diretório de sincronização no HUB.")
        except Exception:
            pass

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Pasta de saída", self.outdir_edit.text())
        if d:
            self.outdir_edit.setText(d)

    def _pick_mnemo_dir(self):
        current = self.mnemo_dir_edit.text() or str(DATA_DIR)
        d = QFileDialog.getExistingDirectory(self, "Pasta monitorada pelo Mnemosyne", current)
        if d:
            self.mnemo_dir_edit.setText(d)

    def _on_mnemo_dir_changed(self, text: str):
        enabled = bool(text.strip())
        self.mnemo_check.setEnabled(enabled)
        if not enabled:
            self.mnemo_check.setChecked(False)

    def _open_outdir(self):
        import subprocess
        subprocess.Popen(["xdg-open", self.outdir_edit.text()])

    def _copy_md(self):
        if self._last_md:
            QApplication.clipboard().setText(self._last_md)
            self.status_lbl.setText("Markdown copiado.")
            QTimer.singleShot(2000, lambda: self.status_lbl.setText(""))

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    def _set_busy(self, busy: bool, tab: int = 0):
        if tab == 0:
            self.inspect_btn.setEnabled(not busy)
            self.dl_btn.setEnabled(not busy and bool(self._formats))
            self.dl_cancel_btn.setEnabled(busy)
            self.fmt_combo.setEnabled(not busy)
        else:
            self.tr_btn.setEnabled(not busy)
            self.batch_tr_btn.setEnabled(not busy and bool(self._playlist))
            self.tr_cancel_btn.setEnabled(busy)

    # ── Baixar ────────────────────────────────────────────────────────────────
    def _inspect(self):
        url = self.url_edit.text().strip()
        if not url:
            self._log("Nenhuma URL inserida.", "warn")
            return

        self._set_busy(True, 0)
        self.fmt_combo.clear()
        self.fmt_combo.setEnabled(False)
        self.dl_btn.setEnabled(False)
        self.video_info_lbl.setText("")

        if is_playlist_url(url):
            self._worker = PlaylistIndexWorker(url, self)
            self._worker.log.connect(self._log)
            self._worker.finished.connect(self._on_playlist_loaded)
            self._worker.error.connect(self._on_worker_error)
        else:
            self._worker = InspectWorker(url, self)
            self._worker.log.connect(self._log)
            self._worker.finished.connect(self._on_inspect_done)
            self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_inspect_done(self, info: dict, fmts: list):
        self._info    = info
        self._formats = fmts
        # Esconde a playlist só se a inspeção não veio de um clique na lista
        # (se veio, mantém a lista visível para o usuário navegar entre vídeos)
        if not self._from_playlist_select:
            self.playlist_lbl.hide()
            self.playlist_list.hide()
            self.playlist_hint_lbl.hide()
            self.batch_tr_btn.setEnabled(False)
            self.batch_tr_btn.hide()
        self._from_playlist_select = False

        title    = info.get("title", "")
        channel  = info.get("uploader") or info.get("channel") or ""
        dur_s    = info.get("duration", 0)
        duration = f"{dur_s // 60}m {dur_s % 60}s" if dur_s else ""
        self.video_info_lbl.setText(
            f"<b>{title}</b>  ·  {channel}  ·  {duration}")

        self.fmt_combo.clear()
        for f in fmts:
            self.fmt_combo.addItem(f["label"])
        self.fmt_combo.setEnabled(True)
        self.fmt_combo.setCurrentIndex(0)
        self.dl_btn.setEnabled(True)
        self._set_busy(False, 0)
        self._log(f"Inspecionado: {title}", "ok")

    def _on_playlist_loaded(self, entries: list):
        self._playlist = entries
        self.playlist_list.clear()
        for e in entries:
            self.playlist_list.addItem(e["title"])
        self.playlist_lbl.show()
        self.playlist_list.show()
        self.playlist_hint_lbl.show()
        # Popula formatos padrão para download de toda a playlist
        self._formats = list(_PLAYLIST_FORMATS)
        self.fmt_combo.clear()
        for f in self._formats:
            self.fmt_combo.addItem(f["label"])
        self.fmt_combo.setEnabled(True)
        self.fmt_combo.setCurrentIndex(0)
        self.dl_btn.setEnabled(True)
        self.batch_tr_btn.setEnabled(True)
        self.batch_tr_btn.show()
        self._set_busy(False, 0)
        self._log(f"Playlist: {len(entries)} itens.", "ok")
        # Auto-seleciona o primeiro vídeo para mostrar as opções de qualidade imediatamente
        if entries:
            self.playlist_list.setCurrentRow(0)

    def _on_playlist_select(self):
        rows = self.playlist_list.selectedItems()
        if not rows:
            return
        idx = self.playlist_list.row(rows[0])
        entry = self._playlist[idx]
        self.playlist_hint_lbl.hide()
        self.url_edit.setText(entry["url"])
        self._from_playlist_select = True
        self._inspect()

    def _start_download(self):
        url = self.url_edit.text().strip()
        if not url or not self._formats:
            return
        idx = self.fmt_combo.currentIndex()
        if idx < 0 or idx >= len(self._formats):
            return
        fmt = self._formats[idx]
        if fmt.get("format_id") is None:
            return  # separador

        outdir = self.outdir_edit.text() or str(DATA_DIR)
        self._set_busy(True, 0)
        self.dl_progress.setValue(0)
        self._log(f"Baixando: {fmt['label'].strip()}…", "")

        self._worker = DownloadWorker(url, fmt, outdir, self,
                                       playlist_mode=is_playlist_url(url))
        self._worker.log.connect(self._log)
        self._worker.progress.connect(self.dl_progress.setValue)
        self._worker.finished.connect(self._on_download_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_download_done(self, title: str):
        self._set_busy(False, 0)
        self.dl_progress.setValue(100)
        self._log(f"Download concluído: {title}", "ok")
        self.status_lbl.setText(f"✓ {title}")

    # ── Transcrever ───────────────────────────────────────────────────────────
    def _pick_local_file(self):
        exts = "Vídeo e áudio (*.mp4 *.mkv *.avi *.mov *.webm *.mp3 *.wav *.m4a *.ogg *.flac);;Todos os arquivos (*)"
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo", str(DATA_DIR), exts)
        if path:
            self.local_file_edit.setText(path)

    def _start_transcribe(self):
        local_file = self.local_file_edit.text().strip() if hasattr(self, "local_file_edit") else ""
        url        = self.url_edit.text().strip()

        if local_file:
            if not Path(local_file).is_file():
                self._log(f"Arquivo não encontrado: {local_file}", "err")
                return
            source, is_local = local_file, True
        elif url:
            source, is_local = url, False
        else:
            self._log("Insira uma URL ou selecione um arquivo local.", "warn")
            return

        model    = self.model_combo.currentText()
        lang_idx = self.lang_combo.currentIndex()
        lang     = LANG_CODES[lang_idx] if lang_idx < len(LANG_CODES) else "auto"
        cpu_pct  = int(self.cpu_combo.currentText().replace("%", ""))
        outdir   = self.outdir_edit.text() or str(DATA_DIR)

        self._set_busy(True, 1)
        self.tr_progress.setValue(0)
        self.md_preview.clear()
        self._log(f"Iniciando transcrição — {'arquivo local' if is_local else 'URL'}, modelo: {model}, idioma: {lang}…", "")

        self._worker = TranscribeWorker(source, is_local, model, lang, cpu_pct, outdir, self)
        self._worker.log.connect(self._log)
        self._worker.progress.connect(self.tr_progress.setValue)
        self._worker.finished.connect(self._on_transcribe_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_transcribe_done(self, md_text: str, out_path: str,
                             title: str, url: str, duration: str):
        self._last_md = md_text
        self._set_busy(False, 1)
        self.tr_progress.setValue(100)
        self.md_preview.setPlainText(md_text)
        self.copy_md_btn.setEnabled(True)
        self._log(f"Transcrição salva: {out_path}", "ok")
        self.status_lbl.setText(f"✓ Salvo em {Path(out_path).name}")
        item = QListWidgetItem(Path(out_path).stem)
        item.setData(Qt.ItemDataRole.UserRole, out_path)
        self.history_list.insertItem(0, item)

        # Indexar no Mnemosyne, se solicitado
        if self.mnemo_check.isChecked():
            mnemo_dir = self.mnemo_dir_edit.text().strip()
            if mnemo_dir:
                mnemo_md  = build_mnemosyne_markdown(title, url, duration, md_text)
                safe      = re.sub(r'[<>:"/\\|?*]', "_", title)[:60]
                mnemo_path = Path(mnemo_dir) / f"{datetime.now().strftime('%Y%m%d_%H%M')}_{safe}.md"
                try:
                    mnemo_path.write_text(mnemo_md, encoding="utf-8")
                    self._log(f"Indexado no Mnemosyne: {mnemo_path.name}", "ok")
                except OSError as e:
                    self._log(f"Erro ao salvar no Mnemosyne: {e}", "err")

    # ── Batch transcription ───────────────────────────────────────────────────
    def _start_batch_transcribe(self) -> None:
        if not self._playlist:
            return
        model    = self.model_combo.currentText()
        lang_idx = self.lang_combo.currentIndex()
        lang     = LANG_CODES[lang_idx] if lang_idx < len(LANG_CODES) else "auto"
        cpu_pct  = int(self.cpu_combo.currentText().replace("%", ""))
        outdir   = self.outdir_edit.text() or str(DATA_DIR)

        self._set_busy(True, 1)
        self.tr_progress.setValue(0)
        self._log(f"Iniciando transcrição em lote — {len(self._playlist)} vídeos…", "")

        self._worker = BatchTranscribeWorker(
            self._playlist, model, lang, cpu_pct, outdir, self)
        self._worker.log.connect(self._log)
        self._worker.batch_progress.connect(self._on_batch_progress)
        self._worker.step_done.connect(self._on_batch_step_done)
        self._worker.finished.connect(self._on_batch_done)
        self._worker.start()

    def _on_batch_progress(self, current: int, total: int) -> None:
        self.tr_progress.setValue(int(current / total * 100))
        self.status_lbl.setText(f"{current}/{total} transcrições…")

    def _on_batch_step_done(self, out_path: str, title: str, md_text: str) -> None:
        item = QListWidgetItem(Path(out_path).stem)
        item.setData(Qt.ItemDataRole.UserRole, out_path)
        self.history_list.insertItem(0, item)
        self.md_preview.setPlainText(md_text)
        self._last_md = md_text
        self.copy_md_btn.setEnabled(True)

    def _on_batch_done(self, done: int, total: int) -> None:
        self._set_busy(False, 1)
        self.tr_progress.setValue(100)
        self._log(f"Lote concluído: {done}/{total} transcrições.", "ok")
        self.status_lbl.setText(f"✓ {done}/{total} transcrições concluídas")

    # ── API handlers ─────────────────────────────────────────────────────────
    def _on_api_download(self, url: str, format_id: str) -> None:
        self._log(f"[API] Download solicitado: {url}", "")
        fmt    = {"format_id": format_id, "label": format_id, "ext": "mp4"}
        outdir = self.outdir_edit.text() or str(DATA_DIR)
        worker = DownloadWorker(url, fmt, outdir, self, playlist_mode=is_playlist_url(url))
        worker.log.connect(self._log)
        worker.finished.connect(
            lambda title: self._on_api_job_done(f"[API] Download concluído: {title}"))
        worker.error.connect(
            lambda msg: self._on_api_job_done(f"[API] Erro no download: {msg}", err=True))
        worker.start()

    def _on_api_transcribe(self, url: str) -> None:
        self._log(f"[API] Transcrição solicitada: {url}", "")
        model    = self.model_combo.currentText()
        lang_idx = self.lang_combo.currentIndex()
        lang     = LANG_CODES[lang_idx] if lang_idx < len(LANG_CODES) else "auto"
        cpu_pct  = int(self.cpu_combo.currentText().replace("%", ""))
        outdir   = self.outdir_edit.text() or str(DATA_DIR)
        worker = TranscribeWorker(url, False, model, lang, cpu_pct, outdir, self)
        worker.log.connect(self._log)
        worker.progress.connect(self.tr_progress.setValue)
        worker.finished.connect(self._on_api_transcribe_done)
        worker.error.connect(
            lambda msg: self._on_api_job_done(f"[API] Erro na transcrição: {msg}", err=True))
        worker.start()

    def _on_api_transcribe_done(self, md_text: str, out_path: str,
                                 title: str, url: str, duration: str) -> None:
        self._on_transcribe_done(md_text, out_path, title, url, duration)
        self._on_api_job_done(f"[API] Transcrição concluída: {title}")

    def _on_api_job_done(self, msg: str, err: bool = False) -> None:
        self._api_server.active = max(0, self._api_server.active - 1)
        self._log(msg, "err" if err else "ok")

    # ── Histórico ─────────────────────────────────────────────────────────────
    def _load_history(self) -> None:
        self.history_list.clear()
        outdir = self.outdir_edit.text().strip()
        if not outdir or not Path(outdir).is_dir():
            return
        md_files = sorted(
            Path(outdir).glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:20]
        for p in md_files:
            item = QListWidgetItem(p.stem)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.history_list.addItem(item)

    def _on_history_select(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            text = Path(path).read_text(encoding="utf-8")
            self.md_preview.setPlainText(text)
            self._last_md = text
            self.copy_md_btn.setEnabled(True)
        except OSError as e:
            self._log(f"Erro ao abrir arquivo: {e}", "err")

    # ── Erros ─────────────────────────────────────────────────────────────────
    def _on_worker_error(self, msg: str):
        self._from_playlist_select = False
        self._set_busy(False, self.tabs.currentIndex())
        self._log(f"Erro: {msg}", "err")
        self.status_lbl.setText("Erro — ver registro.")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    _setup_logger()
    _log_file.info("Hermes iniciado.")
    app = QApplication(sys.argv)
    app.setApplicationName("Hermes")
    window = HermesApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
