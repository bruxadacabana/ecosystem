#!/usr/bin/env python3
"""
Video Transcriber - YouTube & TikTok -> Markdown
Suporta videos individuais e playlists.
Compativel com Windows, Linux (Pop!_OS / Arch) e qualquer GPU/CPU.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import os
import re
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────
# Persistencia de preferencias
# ─────────────────────────────────────────────
PREFS_FILE = Path(__file__).parent / ".prefs.json"

def load_prefs() -> dict:
    try:
        return json.loads(PREFS_FILE.read_text())
    except Exception:
        return {}

def save_prefs(prefs: dict):
    try:
        PREFS_FILE.write_text(json.dumps(prefs, indent=2))
    except Exception:
        pass


# ─────────────────────────────────────────────
# Deteccao de dispositivo (GPU / CPU)
# ─────────────────────────────────────────────
def detect_device() -> tuple:
    """
    Detecta o melhor dispositivo para o Whisper.
    - Sem torch ou sem CUDA: CPU
    - GPU com menos de 3 GB VRAM: CPU (evita OOM)
    - Caso contrario: CUDA
    Retorna (device_str, descricao_humana).
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return "cpu", "CPU (CUDA indisponivel)"
        vram_mb  = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
        gpu_name = torch.cuda.get_device_properties(0).name
        if vram_mb < 3072:
            return "cpu", f"CPU (GPU {gpu_name} so tem {vram_mb} MB VRAM — insuficiente)"
        return "cuda", f"GPU {gpu_name} ({vram_mb} MB VRAM)"
    except Exception:
        return "cpu", "CPU"


# ─────────────────────────────────────────────
# Limite de uso de CPU
# ─────────────────────────────────────────────
def apply_cpu_limit(pct: int):
    """
    Reduz o impacto do Whisper na CPU usando duas estrategias combinadas:

    1. PRIORIDADE BAIXA DO PROCESSO
       Diz ao SO para ceder CPU para outros apps quando necessario.
       Nao impede o Whisper de usar 100% de um nucleo quando o computador
       esta ocioso, mas ele nunca vai competir com o que voce esta fazendo.
         - Windows: BELOW_NORMAL (pct<100) ou NORMAL
         - Linux/Mac: nice +10 (pct<100) ou nice 0

    2. LIMITE DE THREADS (complementar)
       Controla quantos nucleos o PyTorch/OMP podem usar em paralelo.
       pct=25 -> ceil(nucleos * 0.25), minimo 1
       pct=100 -> todos os nucleos

    Resultado pratico:
       - 100%: sem restricao, usa tudo que tiver
       - 75%:  prioridade normal, menos threads
       - 50%:  prioridade baixa, metade dos threads
       - 25%:  prioridade baixa, quarto dos threads — voce mal vai notar
    """
    import os
    import sys
    import math

    total   = os.cpu_count() or 1
    threads = max(1, math.ceil(total * pct / 100))

    # ── 1. Prioridade do processo ──
    if pct < 100:
        try:
            if sys.platform == "win32":
                import ctypes
                # BELOW_NORMAL_PRIORITY_CLASS = 0x4000
                ctypes.windll.kernel32.SetPriorityClass(
                    ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
            else:
                os.nice(10)   # aumenta o nice (reduz prioridade)
        except Exception:
            pass  # sem permissao — continua sem erro
    else:
        try:
            if sys.platform == "win32":
                import ctypes
                # NORMAL_PRIORITY_CLASS = 0x0020
                ctypes.windll.kernel32.SetPriorityClass(
                    ctypes.windll.kernel32.GetCurrentProcess(), 0x0020)
            else:
                os.nice(0)
        except Exception:
            pass

    # ── 2. Limite de threads ──
    os.environ["OMP_NUM_THREADS"]        = str(threads)
    os.environ["MKL_NUM_THREADS"]        = str(threads)
    os.environ["OPENBLAS_NUM_THREADS"]   = str(threads)
    os.environ["VECLIB_MAXIMUM_THREADS"] = str(threads)
    os.environ["NUMEXPR_NUM_THREADS"]    = str(threads)

    try:
        import torch
        torch.set_num_threads(threads)
        torch.set_num_interop_threads(max(1, threads // 2))
    except Exception:
        pass

    return threads


# ─────────────────────────────────────────────
# Deteccao de dependencias
# ─────────────────────────────────────────────
def check_dependencies():
    missing = []
    try:
        import yt_dlp
    except ImportError:
        missing.append("yt-dlp")
    try:
        import whisper
    except ImportError:
        missing.append("openai-whisper")
    return missing


# ─────────────────────────────────────────────
# Deteccao de playlist
# ─────────────────────────────────────────────
def is_playlist(url: str) -> bool:
    playlist_patterns = [
        r"youtube\.com/playlist",
        r"[?&]list=",
        r"tiktok\.com/@[^/]+/?$",
        r"tiktok\.com/@[^/]+/collection/",
        r"youtube\.com/@[^/]+/?$",
        r"youtube\.com/c/",
        r"youtube\.com/user/",
    ]
    return any(re.search(p, url, re.I) for p in playlist_patterns)

def extract_playlist_entries(url: str, log_fn, cancel_event) -> list:
    import yt_dlp
    log_fn("Lendo playlist...")
    ydl_opts = {"quiet": True, "no_warnings": True,
                "extract_flat": True, "skip_download": True}
    entries = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if cancel_event.is_set():
            raise Exception("Cancelado pelo usuario.")
        if "entries" in info:
            for e in info["entries"]:
                if e:
                    video_url = e.get("url") or e.get("webpage_url", "")
                    if video_url and not video_url.startswith("http"):
                        video_url = f"https://www.youtube.com/watch?v={video_url}"
                    entries.append({"url": video_url, "title": e.get("title", "video")})
        else:
            entries.append({"url": url, "title": info.get("title", "video")})
    return entries


# ─────────────────────────────────────────────
# Logica de transcricao
# ─────────────────────────────────────────────
def download_audio(url: str, output_dir: str, log_fn, cancel_event):
    import yt_dlp

    def progress_hook(d):
        if cancel_event.is_set():
            raise Exception("Cancelado pelo usuario.")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3", "preferredquality": "128"}],
        "quiet": True, "no_warnings": True,
        "progress_hooks": [progress_hook],
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        safe_title = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"
        return safe_title, info.get("title", "video"), info


def transcribe_audio(audio_path: str, model_size: str, language: str,
                     log_fn, cancel_event, model_cache: list,
                     device: str) -> dict:
    import whisper

    if cancel_event.is_set():
        raise Exception("Cancelado pelo usuario.")

    # Reusa modelo carregado se mesmo tamanho e mesmo dispositivo
    cache_key = (model_size, device)
    if not model_cache or model_cache[0][0] != cache_key:
        log_fn(f"Carregando modelo Whisper ({model_size}) em {device.upper()}...")
        model = whisper.load_model(model_size, device=device)
        model_cache.clear()
        model_cache.append((cache_key, model))
    else:
        model = model_cache[0][1]

    if cancel_event.is_set():
        raise Exception("Cancelado pelo usuario.")

    lang_arg   = language if language != "auto" else None
    lang_label = language if language != "auto" else "deteccao automatica"
    log_fn(f"Transcrevendo... idioma: {lang_label}")
    return model.transcribe(audio_path, verbose=False, language=lang_arg)


def build_markdown(title: str, url: str, info: dict, result: dict,
                   forced_lang: str) -> str:
    now        = datetime.now().strftime("%Y-%m-%d %H:%M")
    duration_s = info.get("duration", 0)
    duration   = f"{duration_s // 60}m {duration_s % 60}s" if duration_s else "desconhecida"
    channel    = info.get("uploader") or info.get("channel") or "desconhecido"
    detected   = result.get("language", "?").upper()
    lang_note  = detected if forced_lang == "auto" else f"{forced_lang.upper()} (forcado)"

    lines = [
        f"# {title}", "",
        f"> **Fonte:** [{url}]({url})  ",
        f"> **Canal:** {channel}  ",
        f"> **Duracao:** {duration}  ",
        f"> **Idioma:** {lang_note}  ",
        f"> **Gerado em:** {now}",
        "", "---", "", "## Transcricao", "",
    ]

    segments = result.get("segments", [])
    if segments:
        for seg in segments:
            start = int(seg["start"])
            mm, ss = divmod(start, 60)
            lines.append(f"**[{mm:02d}:{ss:02d}]** {seg['text'].strip()}")
            lines.append("")
    else:
        for paragraph in result.get("text", "").split("\n"):
            if paragraph.strip():
                lines.append(paragraph.strip())
                lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Idiomas suportados
# ─────────────────────────────────────────────
LANGUAGES = {
    "auto": "Automatico",   "pt": "Portugues",    "en": "Ingles",
    "es":   "Espanhol",     "fr": "Frances",      "de": "Alemao",
    "it":   "Italiano",     "ja": "Japones",      "ko": "Coreano",
    "zh":   "Chines",       "ru": "Russo",        "ar": "Arabe",
    "nl":   "Holandes",     "pl": "Polones",      "tr": "Turco",
    "sv":   "Sueco",        "da": "Dinamarques",  "fi": "Finlandes",
    "nb":   "Noruegues",    "uk": "Ucraniano",    "hi": "Hindi",
}
LANG_DISPLAY = [f"{v}  [{k}]" for k, v in LANGUAGES.items()]
LANG_CODES   = list(LANGUAGES.keys())


# ─────────────────────────────────────────────
# Interface grafica
# ─────────────────────────────────────────────
class App(tk.Tk):
    MODELS = ["tiny", "base", "small", "medium", "large"]

    BG      = "#F5F0E8"
    SURFACE = "#EDE8DC"
    BORDER  = "#C8BFA8"
    TEXT    = "#1A1208"
    MUTED   = "#7A6E5E"
    RED     = "#8B1A1A"
    GREEN   = "#2E5A1C"
    WARN    = "#7A5A00"
    KEY     = "#2C2C2C"
    CANCEL  = "#6B2020"

    FONT_SERIF = "Georgia"
    FONT_MONO  = "Courier New" if sys.platform == "win32" else "Courier"

    def __init__(self):
        super().__init__()
        self.title("Transcriber")
        self.geometry("900x820")
        self.resizable(True, True)
        self.configure(bg=self.BG)
        self._running      = False
        self._cancel_event = threading.Event()
        self._anim_chars   = ["|", "/", "-", "\\"]
        self._anim_idx     = 0
        self._last_md      = ""
        self._model_cache  = []
        self._prefs        = load_prefs()
        self._device, self._device_label = detect_device()
        self._cpu_limit = 100  # porcentagem, so usado quando device=cpu
        self._build_ui()
        self._load_prefs()
        self.after(100, self._check_deps_and_device)

    # ── Persistencia ──────────────────────────
    def _load_prefs(self):
        if "outdir"    in self._prefs: self.outdir_var.set(self._prefs["outdir"])
        if "model"     in self._prefs: self.model_var.set(self._prefs["model"])
        if "cpu_limit" in self._prefs:
            try: self.cpu_limit_var.set(self._prefs["cpu_limit"])
            except Exception: pass
        if "lang_idx" in self._prefs:
            try: self.lang_cb.current(self._prefs["lang_idx"])
            except Exception: pass

    def _save_prefs(self):
        self._prefs.update({
            "outdir":    self.outdir_var.get(),
            "model":     self.model_var.get(),
            "lang_idx":  self.lang_cb.current(),
            "cpu_limit": self.cpu_limit_var.get(),
        })
        save_prefs(self._prefs)

    # ── UI ────────────────────────────────────
    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT,
                        font=(self.FONT_SERIF, 10))
        style.configure("Key.TButton",
                        background=self.KEY, foreground="#F5F0E8",
                        font=(self.FONT_SERIF, 10, "bold"),
                        borderwidth=0, relief="flat", padding=(18, 9))
        style.map("Key.TButton",
                  background=[("active","#444444"),("disabled","#AAAAAA")],
                  foreground=[("disabled","#cccccc")])
        style.configure("Cancel.TButton",
                        background=self.CANCEL, foreground="#F5F0E8",
                        font=(self.FONT_SERIF, 10),
                        borderwidth=0, relief="flat", padding=(18, 9))
        style.map("Cancel.TButton",
                  background=[("active","#9B3232"),("disabled","#AAAAAA")],
                  foreground=[("disabled","#cccccc")])
        style.configure("Sec.TButton",
                        background=self.SURFACE, foreground=self.TEXT,
                        font=(self.FONT_SERIF, 9),
                        borderwidth=1, relief="flat", padding=(10, 6))
        style.map("Sec.TButton",
                  background=[("active",self.BORDER),("disabled",self.BG)],
                  foreground=[("disabled",self.MUTED)])
        style.configure("TCombobox",
                        fieldbackground=self.SURFACE, background=self.SURFACE,
                        foreground=self.TEXT, selectbackground=self.BORDER,
                        selectforeground=self.TEXT, font=(self.FONT_SERIF, 9))
        style.configure("Paper.Horizontal.TProgressbar",
                        troughcolor=self.SURFACE, background=self.KEY,
                        bordercolor=self.BORDER, lightcolor=self.KEY, darkcolor=self.KEY)
        style.configure("Playlist.Horizontal.TProgressbar",
                        troughcolor=self.SURFACE, background=self.GREEN,
                        bordercolor=self.BORDER, lightcolor=self.GREEN, darkcolor=self.GREEN)

        # ── Cabecalho ──
        header = tk.Frame(self, bg=self.BG)
        header.pack(fill="x", padx=32, pady=(28, 0))
        tk.Label(header,
            text="* * * * * * * * * * * * * * * * * * * * * * * * * * * * *",
            bg=self.BG, fg=self.BORDER, font=(self.FONT_MONO, 8)).pack(anchor="w")
        title_row = tk.Frame(header, bg=self.BG)
        title_row.pack(fill="x", pady=(8, 2))
        tk.Label(title_row, text="VIDEO TRANSCRIBER",
            bg=self.BG, fg=self.TEXT, font=(self.FONT_SERIF, 22, "bold")).pack(side="left")
        tk.Label(title_row, text="  [Mk. IV]",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 11)).pack(side="left", pady=(6,0))
        # Dispositivo — canto direito do titulo
        self.device_lbl = tk.Label(title_row,
            text=f"  {self._device.upper()}  |  {self._device_label}",
            bg=self.BG,
            fg=self.GREEN if self._device == "cuda" else self.MUTED,
            font=(self.FONT_MONO, 8))
        self.device_lbl.pack(side="right", pady=(6, 0))
        tk.Label(header,
            text="Converte videos e playlists do YouTube & TikTok em transcricoes Markdown",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_SERIF, 9, "italic")).pack(anchor="w")
        tk.Label(header,
            text="* * * * * * * * * * * * * * * * * * * * * * * * * * * * *",
            bg=self.BG, fg=self.BORDER, font=(self.FONT_MONO, 8)).pack(anchor="w", pady=(8,0))

        # ── Corpo ──
        body = tk.Frame(self, bg=self.BG)
        body.pack(fill="both", expand=True, padx=32, pady=(18, 0))

        # URL
        tk.Label(body, text="ENDERECO DO VIDEO OU PLAYLIST",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7)).pack(anchor="w")
        url_row = tk.Frame(body, bg=self.BG)
        url_row.pack(fill="x", pady=(4, 2))

        # [COLAR] antes do campo
        ttk.Button(url_row, text="[COLAR]", style="Sec.TButton",
            command=self._paste_url).pack(side="left", padx=(0, 6))

        url_frame = tk.Frame(url_row, bg=self.SURFACE,
            highlightbackground=self.BORDER, highlightthickness=1)
        url_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.url_var = tk.StringVar()
        url_entry = tk.Entry(url_frame, textvariable=self.url_var,
            bg=self.SURFACE, fg=self.TEXT, insertbackground=self.TEXT,
            relief="flat", font=(self.FONT_MONO, 10), bd=6)
        url_entry.pack(fill="x")
        url_entry.bind("<Return>", lambda _: self._start())

        self.start_btn = ttk.Button(url_row, text="[ TRANSCREVER ]",
            style="Key.TButton", command=self._start)
        self.start_btn.pack(side="left", padx=(0, 6))
        self.cancel_btn = ttk.Button(url_row, text="[ CANCELAR ]",
            style="Cancel.TButton", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left")

        tk.Label(body,
            text="ex: youtube.com/watch?v=...   youtube.com/playlist?list=...   tiktok.com/@perfil/collection/nome-ID",
            bg=self.BG, fg=self.BORDER, font=(self.FONT_MONO, 7)).pack(anchor="w", pady=(2, 10))

        # Opcoes: modelo + idioma
        opt_row = tk.Frame(body, bg=self.BG)
        opt_row.pack(fill="x", pady=(0, 10))
        tk.Label(opt_row, text="MODELO:",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7)).pack(side="left")
        self.model_var = tk.StringVar(value="small")
        ttk.Combobox(opt_row, textvariable=self.model_var, values=self.MODELS,
            width=8, state="readonly", font=(self.FONT_SERIF, 9)).pack(side="left", padx=(6,24))
        tk.Label(opt_row, text="IDIOMA:",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7)).pack(side="left")
        self.lang_var = tk.StringVar()
        self.lang_cb  = ttk.Combobox(opt_row, textvariable=self.lang_var,
            values=LANG_DISPLAY, width=20, state="readonly", font=(self.FONT_SERIF, 9))
        self.lang_cb.current(0)
        self.lang_cb.pack(side="left", padx=(6, 0))
        tk.Label(opt_row, text="  (fixar evita erros de deteccao)",
            bg=self.BG, fg=self.BORDER, font=(self.FONT_MONO, 7)).pack(side="left")

        # Limite de CPU (visivel apenas quando device=cpu)
        self.cpu_row = tk.Frame(body, bg=self.BG)
        self.cpu_row.pack(fill="x", pady=(0, 8))
        tk.Label(self.cpu_row, text="LIMITE DE CPU:",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7)).pack(side="left")
        self.cpu_limit_var = tk.StringVar(value="100%")
        cpu_cb = ttk.Combobox(self.cpu_row,
            textvariable=self.cpu_limit_var,
            values=["25%", "50%", "75%", "100%"],
            width=6, state="readonly", font=(self.FONT_SERIF, 9))
        cpu_cb.pack(side="left", padx=(6, 8))
        self.cpu_limit_hint = tk.Label(self.cpu_row,
            text="",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7))
        self.cpu_limit_hint.pack(side="left")
        # mostra/oculta e atualiza hint conforme dispositivo
        self._update_cpu_row()

        # Pasta de saida
        out_row = tk.Frame(body, bg=self.BG)
        out_row.pack(fill="x", pady=(0, 10))
        tk.Label(out_row, text="PASTA DE SAIDA:",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7)).pack(side="left")
        self.outdir_var = tk.StringVar(value=str(Path.home() / "Transcricoes"))
        dir_frame = tk.Frame(out_row, bg=self.SURFACE,
            highlightbackground=self.BORDER, highlightthickness=1)
        dir_frame.pack(side="left", padx=(6, 6))
        tk.Entry(dir_frame, textvariable=self.outdir_var,
            bg=self.SURFACE, fg=self.TEXT, insertbackground=self.TEXT,
            relief="flat", font=(self.FONT_MONO, 9), width=38, bd=4).pack()
        ttk.Button(out_row, text="[...]", style="Sec.TButton",
            command=self._pick_dir, width=4).pack(side="left")

        # Progresso item atual
        tk.Label(body, text="PROGRESSO DO ITEM ATUAL",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7)).pack(anchor="w")
        self.progress = ttk.Progressbar(body, mode="indeterminate",
            style="Paper.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(2, 8))

        # Progresso playlist
        pl_row = tk.Frame(body, bg=self.BG)
        pl_row.pack(fill="x", pady=(0, 10))
        tk.Label(pl_row, text="PROGRESSO DA PLAYLIST:",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7)).pack(side="left")
        self.pl_label = tk.Label(pl_row, text="--",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7))
        self.pl_label.pack(side="left", padx=(8, 0))
        self.pl_progress = ttk.Progressbar(body, mode="determinate",
            style="Playlist.Horizontal.TProgressbar")
        self.pl_progress.pack(fill="x", pady=(0, 10))

        # Log — cabecalho com botao [COPIAR LOG]
        log_header = tk.Frame(body, bg=self.BG)
        log_header.pack(fill="x")
        tk.Label(log_header, text="REGISTRO DA MAQUINA",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 7)).pack(side="left")
        tk.Label(log_header, text=" " + "-" * 42,
            bg=self.BG, fg=self.BORDER, font=(self.FONT_MONO, 7)).pack(side="left")
        ttk.Button(log_header, text="[COPIAR LOG]", style="Sec.TButton",
            command=self._copy_log).pack(side="right")

        log_frame = tk.Frame(body, bg=self.SURFACE,
            highlightbackground=self.BORDER, highlightthickness=1)
        log_frame.pack(fill="both", expand=True, pady=(4, 14))
        self.log_box = scrolledtext.ScrolledText(log_frame,
            height=10, bg=self.SURFACE, fg=self.TEXT,
            insertbackground=self.TEXT, relief="flat",
            font=(self.FONT_MONO, 9), bd=8, state="disabled",
            wrap="word", cursor="xterm")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("ok",   foreground=self.GREEN)
        self.log_box.tag_config("err",  foreground=self.RED)
        self.log_box.tag_config("warn", foreground=self.WARN)
        self.log_box.tag_config("head", foreground=self.TEXT, font=(self.FONT_MONO, 9, "bold"))

        # ── Rodape ──
        footer = tk.Frame(self, bg=self.BG)
        footer.pack(fill="x", padx=32, pady=(0, 20))
        tk.Label(footer, text=". " * 42,
            bg=self.BG, fg=self.BORDER, font=(self.FONT_MONO, 7)).pack(anchor="w", pady=(0, 8))
        btn_row = tk.Frame(footer, bg=self.BG)
        btn_row.pack(fill="x")
        self.open_btn = ttk.Button(btn_row, text="[ ABRIR PASTA ]",
            style="Sec.TButton", command=self._open_outdir, state="disabled")
        self.open_btn.pack(side="left")
        self.copy_btn = ttk.Button(btn_row, text="[ COPIAR ULTIMO MARKDOWN ]",
            style="Sec.TButton", command=self._copy_md, state="disabled")
        self.copy_btn.pack(side="left", padx=(8, 0))
        self.status_lbl = tk.Label(btn_row, text="",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_MONO, 8))
        self.status_lbl.pack(side="right")

    # ── Helpers ───────────────────────────────
    def _log(self, msg: str, tag: str = ""):
        def _do():
            self.log_box.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_box.insert("end", f"  {ts}  |  {msg}\n", tag or None)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _do)

    def _set_pl_progress(self, current: int, total: int):
        def _do():
            pct = int(current / total * 100) if total else 0
            self.pl_progress["value"] = pct
            self.pl_label.config(text=f"{current} / {total}  ({pct}%)")
        self.after(0, _do)

    def _check_deps_and_device(self):
        self._log(f"Dispositivo: {self._device_label}",
                  "ok" if self._device == "cuda" else "")
        self._update_cpu_row()
        missing = check_dependencies()
        if missing:
            self._log(f"ATENCAO: faltando {', '.join(missing)}", "warn")
            self._log("Execute: pip install " + " ".join(missing), "warn")
        else:
            self._log("Sistema pronto. Aguardando instrucoes.", "ok")

    def _update_cpu_row(self):
        """Atualiza visibilidade e hint do seletor de limite de CPU."""
        import os, math
        total   = os.cpu_count() or 1
        pct_str = self.cpu_limit_var.get() if hasattr(self, "cpu_limit_var") else "100%"
        pct     = int(pct_str.replace("%", ""))
        threads = max(1, math.ceil(total * pct / 100))
        hint    = f"{threads} de {total} nucleos"
        if self._device == "cuda":
            hint = "(inativo — usando GPU)"
        if hasattr(self, "cpu_limit_hint"):
            self.cpu_limit_hint.config(text=hint)

    def _get_cpu_limit_pct(self) -> int:
        try:
            return int(self.cpu_limit_var.get().replace("%", ""))
        except Exception:
            return 100

    def _paste_url(self):
        try:
            text = self.clipboard_get().strip()
            if text:
                self.url_var.set(text)
                self.status_lbl.config(text="-- URL colada --")
                self.after(1500, lambda: self.status_lbl.config(text=""))
        except tk.TclError:
            pass

    def _copy_log(self):
        self.log_box.configure(state="normal")
        content = self.log_box.get("1.0", "end")
        self.log_box.configure(state="disabled")
        self.clipboard_clear()
        self.clipboard_append(content)
        self.status_lbl.config(text="-- log copiado --")
        self.after(1500, lambda: self.status_lbl.config(text=""))

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir_var.get())
        if d:
            self.outdir_var.set(d)

    def _open_outdir(self):
        d = self.outdir_var.get()
        if sys.platform == "win32":
            os.startfile(d)
        else:
            subprocess.Popen(["xdg-open", d])

    def _copy_md(self):
        self.clipboard_clear()
        self.clipboard_append(self._last_md)
        self.status_lbl.config(text="-- markdown copiado --")
        self.after(2000, lambda: self.status_lbl.config(text=""))

    def _animate_status(self):
        if self._running:
            ch = self._anim_chars[self._anim_idx % len(self._anim_chars)]
            self.status_lbl.config(text=f"  {ch}  trabalhando...")
            self._anim_idx += 1
            self.after(120, self._animate_status)

    def _selected_lang(self) -> str:
        idx = self.lang_cb.current()
        return LANG_CODES[idx] if 0 <= idx < len(LANG_CODES) else "auto"

    # ── Core ──────────────────────────────────
    def _start(self):
        if self._running:
            return
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Campos incompletos", "Cole uma URL.")
            return
        if not re.search(r"(youtube\.com|youtu\.be|tiktok\.com)", url, re.I):
            if not messagebox.askyesno("URL incomum",
                    "A URL nao parece ser do YouTube ou TikTok. Continuar?"):
                return

        outdir = self.outdir_var.get()
        os.makedirs(outdir, exist_ok=True)
        self._save_prefs()

        self._running = True
        self._cancel_event.clear()
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.open_btn.config(state="disabled")
        self.copy_btn.config(state="disabled")
        self._last_md = ""
        self.pl_progress["value"] = 0
        self.pl_label.config(text="--")
        self.progress.start(10)
        self._animate_status()

        # Aplica limite de CPU antes de iniciar (so tem efeito se device=cpu)
        if self._device == "cpu":
            pct     = self._get_cpu_limit_pct()
            threads = apply_cpu_limit(pct)
            self._log(f"Limite de CPU: {pct}% ({threads} thread(s))", "")

        threading.Thread(
            target=self._run_pipeline,
            args=(url, outdir, self.model_var.get(), self._selected_lang()),
            daemon=True).start()

    def _cancel(self):
        if self._running:
            self._cancel_event.set()
            self._log("Cancelando... aguarde o item atual terminar.", "warn")
            self.cancel_btn.config(state="disabled")

    def _run_pipeline(self, url: str, outdir: str, model_size: str, language: str):
        playlist_mode = is_playlist(url)
        saved_count   = 0
        error_count   = 0

        try:
            if playlist_mode:
                entries = extract_playlist_entries(url, self._log, self._cancel_event)
                total   = len(entries)
                self._log(f"Playlist detectada: {total} video(s) encontrado(s).", "ok")
                pl_title = re.sub(r'[\\/*?:"<>|]', "_",
                    url.split("list=")[-1][:40] if "list=" in url else "playlist")
                pl_dir = os.path.join(outdir, pl_title)
                os.makedirs(pl_dir, exist_ok=True)
                work_dir = pl_dir
            else:
                entries  = [{"url": url, "title": ""}]
                total    = 1
                work_dir = outdir

            for i, entry in enumerate(entries, 1):
                if self._cancel_event.is_set():
                    break

                video_url = entry["url"]
                self._set_pl_progress(i - 1, total)
                self._log(f"[{i}/{total}] {entry.get('title') or video_url}", "head")

                audio_path = None
                try:
                    audio_path, title, info = download_audio(
                        video_url, work_dir, self._log, self._cancel_event)
                    self._log(f"  Audio: {os.path.basename(audio_path)}", "ok")

                    result = transcribe_audio(
                        audio_path, model_size, language,
                        self._log, self._cancel_event, self._model_cache,
                        self._device)

                    md = build_markdown(title, video_url, info, result, language)
                    safe = re.sub(r'[\\/*?:"<>|]', "_", title)[:80]
                    md_path = os.path.join(work_dir, f"{safe}.md")
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(md)
                    self._log(f"  Salvo: {os.path.basename(md_path)}", "ok")
                    self._last_md = md
                    saved_count  += 1

                except Exception as exc:
                    if self._cancel_event.is_set():
                        raise
                    self._log(f"  ERRO: {exc}", "err")
                    error_count += 1
                finally:
                    if audio_path and os.path.exists(audio_path):
                        try: os.remove(audio_path)
                        except Exception: pass

                self._set_pl_progress(i, total)

            if self._cancel_event.is_set():
                self._log(f"Cancelado. {saved_count} arquivo(s) salvo(s).", "warn")
                self.after(0, self._on_cancelled)
            else:
                summary = f"{saved_count} transcricao(oes) salva(s)"
                if error_count:
                    summary += f", {error_count} erro(s)"
                self._log(f"Concluido: {summary}.", "ok")
                self.after(0, self._on_success, work_dir, saved_count)

        except Exception as exc:
            if self._cancel_event.is_set():
                self._log(f"Cancelado. {saved_count} arquivo(s) salvo(s).", "warn")
                self.after(0, self._on_cancelled)
            else:
                self._log(f"ERRO FATAL: {exc}", "err")
                self.after(0, self._on_error)

    def _on_success(self, folder: str, count: int):
        self._running = False
        self.progress.stop()
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.open_btn.config(state="normal")
        if self._last_md:
            self.copy_btn.config(state="normal")
        self.status_lbl.config(text=f"  OK  {count} arquivo(s) em {os.path.basename(folder)}")

    def _on_error(self):
        self._running = False
        self.progress.stop()
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.status_lbl.config(text="  XX  falha -- veja o registro")

    def _on_cancelled(self):
        self._running = False
        self.progress.stop()
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.status_lbl.config(text="  --  cancelado")


# ─────────────────────────────────────────────
def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
