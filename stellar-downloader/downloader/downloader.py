#!/usr/bin/env python3
"""
Stellar Downloader — universal video downloader
yt-dlp + tkinter, tema cyberpunk/astronomia roxo neon
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import threading
import os
import sys
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
import math, random, time

# ─────────────────────────────────────────────
# Prefs
# ─────────────────────────────────────────────
PREFS_FILE = Path(__file__).parent / ".dl_prefs.json"

def load_prefs():
    try: return json.loads(PREFS_FILE.read_text())
    except: return {}

def save_prefs(p):
    try: PREFS_FILE.write_text(json.dumps(p, indent=2))
    except: pass

# ─────────────────────────────────────────────
# Paleta
# ─────────────────────────────────────────────
BG       = "#0A0612"   # void escuro
BG2      = "#100D1C"   # superfície ligeiramente mais clara
GRID     = "#1A1530"   # linhas de grade
PUR1     = "#B44FFF"   # roxo neon primário
PUR2     = "#7B2FBE"   # roxo médio
PUR3     = "#3D1A6E"   # roxo escuro
CYAN     = "#A78BFA"   # violeta/lavanda como acento
WHITE    = "#EDE9F6"
MUTED    = "#6B5E8A"
RED      = "#FF4F7B"
GREEN    = "#4FFFB0"
WARN     = "#FFB84F"
MONO     = "Courier New" if sys.platform == "win32" else "Courier"
DISPLAY  = "Georgia"

# ─────────────────────────────────────────────
# Canvas de estrelas (fundo animado)
# ─────────────────────────────────────────────
class StarField(tk.Canvas):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, highlightthickness=0, **kw)
        self._stars   = []
        self._nebulae = []
        self._lines   = []   # constelações
        self._running = True
        self.bind("<Configure>", self._on_resize)
        self.after(100, self._init_field)

    def _on_resize(self, e):
        self._init_field()

    def _init_field(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            self.after(200, self._init_field)
            return

        # Nebulosidades (elipses suaves)
        self._nebulae = []
        for _ in range(4):
            cx = random.randint(0, w)
            cy = random.randint(0, h)
            rx = random.randint(80, 220)
            ry = random.randint(50, 140)
            colors = ["#1A0833", "#0D0A2A", "#120820", "#1A0A30"]
            c = random.choice(colors)
            oid = self.create_oval(cx-rx, cy-ry, cx+rx, cy+ry,
                fill=c, outline="", tags="nebula")
            self._nebulae.append(oid)

        # Grade cyberpunk (linhas horizontais e verticais sutis)
        for y in range(0, h, 40):
            self.create_line(0, y, w, y, fill=GRID, width=1, tags="grid")
        for x in range(0, w, 40):
            self.create_line(x, 0, x, h, fill=GRID, width=1, tags="grid")

        # Estrelas
        self._stars = []
        for _ in range(200):
            x  = random.randint(0, w)
            y  = random.randint(0, h)
            r  = random.uniform(0.4, 2.2)
            br = random.uniform(0.3, 1.0)
            col = self._star_color(br)
            oid = self.create_oval(x-r, y-r, x+r, y+r, fill=col, outline="")
            self._stars.append({"id": oid, "x": x, "y": y, "r": r,
                                 "br": br, "phase": random.uniform(0, 6.28),
                                 "speed": random.uniform(0.5, 2.0)})

        # Constelações — linhas entre estrelas próximas
        pts = [(s["x"], s["y"]) for s in self._stars]
        used = set()
        for i, (x1, y1) in enumerate(pts[:60]):
            for j, (x2, y2) in enumerate(pts[i+1:i+8], i+1):
                dist = math.hypot(x2-x1, y2-y1)
                if 40 < dist < 100 and (i,j) not in used:
                    used.add((i,j))
                    alpha = int(40 + random.randint(0,30))
                    col = f"#{alpha:02x}{alpha//3:02x}{alpha+20:02x}"
                    self.create_line(x1, y1, x2, y2, fill=col, width=1,
                                     dash=(2,6), tags="const")
                    if len(used) > 30:
                        break
            if len(used) > 30:
                break

        self._animate()

    def _star_color(self, br):
        # Estrelas variam de branco-azulado a roxo-rosado
        r = int(180 + br * 75)
        g = int(160 + br * 60)
        b = int(220 + br * 35)
        return f"#{min(r,255):02x}{min(g,255):02x}{min(b,255):02x}"

    def _animate(self):
        if not self._running:
            return
        t = time.time()
        for s in self._stars:
            pulse = 0.6 + 0.4 * math.sin(t * s["speed"] + s["phase"])
            col   = self._star_color(pulse)
            r     = s["r"] * (0.8 + 0.4 * pulse)
            x, y  = s["x"], s["y"]
            self.coords(s["id"], x-r, y-r, x+r, y+r)
            self.itemconfig(s["id"], fill=col)
        self.after(80, self._animate)

    def stop(self):
        self._running = False

# ─────────────────────────────────────────────
# Lógica yt-dlp
# ─────────────────────────────────────────────
def fetch_info(url: str) -> dict:
    """Retorna metadados e lista de formatos via yt-dlp."""
    import yt_dlp
    ydl_opts = {"quiet": True, "no_warnings": True,
                "extract_flat": False, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def fetch_playlist_index(url: str) -> list:
    """Lista rápida de entradas de uma playlist (sem baixar)."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True,
            "extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries", [])
    result  = []
    for e in (entries or []):
        if not e:
            continue
        vurl = e.get("url") or e.get("webpage_url", "")
        if vurl and not vurl.startswith("http"):
            vurl = f"https://www.youtube.com/watch?v={vurl}"
        result.append({"url": vurl, "title": e.get("title", "(sem título)")})
    return result

def build_format_list(info: dict) -> list:
    """
    Constrói lista de opções exibíveis para o usuário.
    Retorna [{"label": str, "format_id": str, "ext": str, "note": str}]
    """
    fmts = info.get("formats", [])
    options = []

    # ── Opções especiais sempre no topo ──
    options.append({
        "label":     "✦  Melhor qualidade (vídeo + áudio)",
        "format_id": "bestvideo+bestaudio/best",
        "ext":       "mp4",
        "note":      "automático",
    })
    options.append({
        "label":     "◈  Apenas áudio (MP3)",
        "format_id": "bestaudio",
        "ext":       "mp3",
        "note":      "extrai áudio",
    })
    options.append({"label": "─" * 48, "format_id": None, "ext": None, "note": ""})

    # ── Formatos concretos, agrupados por resolução ──
    seen_res = {}
    for f in reversed(fmts):  # reversed = melhor bitrate primeiro
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        if vcodec == "none":
            continue  # pula audio-only na lista principal
        height  = f.get("height") or 0
        fps     = f.get("fps") or 0
        ext     = f.get("ext", "?")
        fid     = f.get("format_id", "")
        tbr     = f.get("tbr") or f.get("vbr") or 0
        has_audio = acodec != "none"

        res_key = (height, ext)
        if res_key in seen_res:
            continue
        seen_res[res_key] = True

        res_str  = f"{height}p" if height else "?"
        fps_str  = f" {fps:.0f}fps" if fps and fps > 30 else ""
        aud_str  = " + áudio" if has_audio else " [sem áudio]"
        tbr_str  = f" ~{tbr:.0f}k" if tbr else ""
        note     = f"{ext.upper()}{tbr_str}{aud_str}"
        label    = f"  {res_str}{fps_str}  —  {note}"
        options.append({
            "label":     label,
            "format_id": fid,
            "ext":       ext,
            "note":      note,
        })

    return options

def is_playlist_url(url: str) -> bool:
    return bool(re.search(r"(playlist|list=|/channel/|/@[^/]+/?$|/c/|/user/)", url, re.I))

def download(url: str, fmt: dict, outdir: str, log_fn, cancel_event,
             progress_fn=None):
    import yt_dlp

    def hook(d):
        if cancel_event.is_set():
            raise Exception("Cancelado.")
        if d.get("status") == "downloading" and progress_fn:
            total    = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                progress_fn(int(downloaded / total * 100))
        if d.get("status") == "finished":
            if progress_fn: progress_fn(100)
            log_fn(f"  Processando...", "ok")

    ext = fmt["ext"]
    fid = fmt["format_id"]
    is_audio = fid == "bestaudio"

    postprocessors = []
    if is_audio:
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        })
    else:
        postprocessors.append({
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        })

    ydl_opts = {
        "format":         fid,
        "outtmpl":        os.path.join(outdir, "%(title)s.%(ext)s"),
        "postprocessors": postprocessors,
        "quiet":          True,
        "no_warnings":    True,
        "progress_hooks": [hook],
        "noplaylist":     True,
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info.get("title") or "video"

# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("STELLAR DOWNLOADER")
        self.geometry("860x820")
        self.resizable(True, True)
        self.configure(bg=BG)

        self._prefs        = load_prefs()
        self._running      = False
        self._cancel_event = threading.Event()
        self._formats      = []   # lista de dicts de formato
        self._info         = None
        self._playlist     = []   # entradas se URL for playlist

        self._build_ui()
        self._load_prefs()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── fundo de estrelas (canvas cobrindo tudo)
        self.star_canvas = StarField(self, width=860, height=820)
        self.star_canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # ── frame principal sobre o canvas
        main = tk.Frame(self, bg=BG, bd=0)
        main.place(relx=0, rely=0, relwidth=1, relheight=1)

        # ── Cabeçalho ──
        hdr = tk.Frame(main, bg=BG)
        hdr.pack(fill="x", padx=36, pady=(28, 0))

        # linha decorativa superior
        tk.Canvas(hdr, height=2, bg=BG, highlightthickness=0,
                  relief="flat").pack(fill="x")
        top_line = tk.Canvas(hdr, height=2, bg=PUR1,
                             highlightthickness=0, relief="flat")
        top_line.pack(fill="x")

        title_row = tk.Frame(hdr, bg=BG)
        title_row.pack(fill="x", pady=(10, 0))
        tk.Label(title_row, text="✦ STELLAR", bg=BG, fg=PUR1,
                 font=(DISPLAY, 26, "bold")).pack(side="left")
        tk.Label(title_row, text=" DOWNLOADER", bg=BG, fg=WHITE,
                 font=(DISPLAY, 26, "bold")).pack(side="left")
        tk.Label(title_row, text="  v1.0", bg=BG, fg=MUTED,
                 font=(MONO, 10)).pack(side="left", pady=(8,0))

        tk.Label(hdr, text="Universal video downloader — 1000+ sites via yt-dlp",
                 bg=BG, fg=MUTED, font=(MONO, 8, "italic")).pack(anchor="w", pady=(2,0))

        bot_line = tk.Canvas(hdr, height=1, bg=PUR3,
                             highlightthickness=0, relief="flat")
        bot_line.pack(fill="x", pady=(10, 0))

        # ── Corpo ──
        body = tk.Frame(main, bg=BG)
        body.pack(fill="both", expand=True, padx=36, pady=(18, 0))

        # URL row
        self._lbl(body, "ENDEREÇO / URL").pack(anchor="w")
        url_row = tk.Frame(body, bg=BG)
        url_row.pack(fill="x", pady=(4, 4))

        self._paste_btn(url_row, self._paste_url).pack(side="left", padx=(0,6))

        url_wrap = tk.Frame(url_row, bg=PUR3,
                            highlightbackground=PUR2, highlightthickness=1)
        url_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(url_wrap, textvariable=self.url_var,
            bg=BG2, fg=WHITE, insertbackground=PUR1,
            relief="flat", font=(MONO, 11), bd=7)
        self.url_entry.pack(fill="x")
        self.url_entry.bind("<Return>", lambda _: self._fetch())

        self.fetch_btn = self._neon_btn(url_row, "[ BUSCAR ]", self._fetch)
        self.fetch_btn.pack(side="left", padx=(0,6))
        self.cancel_btn = self._neon_btn(url_row, "[ CANCELAR ]",
                                         self._cancel, color=RED)
        self.cancel_btn.config(state="disabled")
        self.cancel_btn.pack(side="left")

        # Info do vídeo (aparece após fetch)
        self.info_frame = tk.Frame(body, bg=BG2,
                                   highlightbackground=PUR3, highlightthickness=1)
        self.info_frame.pack(fill="x", pady=(8, 4))
        self.thumb_canvas = tk.Canvas(self.info_frame, width=120, height=68,
                                      bg=BG2, highlightthickness=0)
        self.thumb_canvas.pack(side="left", padx=(10,0), pady=8)
        self._draw_thumb_placeholder()

        info_text = tk.Frame(self.info_frame, bg=BG2)
        info_text.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        self.title_lbl = tk.Label(info_text, text="—",
            bg=BG2, fg=WHITE, font=(DISPLAY, 11, "bold"),
            anchor="w", justify="left", wraplength=500)
        self.title_lbl.pack(anchor="w")
        self.meta_lbl = tk.Label(info_text, text="",
            bg=BG2, fg=MUTED, font=(MONO, 8), anchor="w")
        self.meta_lbl.pack(anchor="w", pady=(2,0))
        self.site_lbl = tk.Label(info_text, text="",
            bg=BG2, fg=CYAN, font=(MONO, 8), anchor="w")
        self.site_lbl.pack(anchor="w")

        # Playlist panel (aparece se URL for playlist)
        self.pl_frame = tk.Frame(body, bg=BG)
        # (empacotado dinamicamente)
        self._lbl_pl = self._lbl(self.pl_frame, "PLAYLIST — SELECIONE O ITEM")
        self._lbl_pl.pack(anchor="w")
        pl_inner = tk.Frame(self.pl_frame, bg=BG2,
                            highlightbackground=PUR3, highlightthickness=1)
        pl_inner.pack(fill="x", pady=(4,0))
        scrollbar = tk.Scrollbar(pl_inner, orient="vertical",
                                 bg=BG2, troughcolor=BG2,
                                 activebackground=PUR2)
        self.pl_listbox = tk.Listbox(pl_inner,
            bg=BG2, fg=WHITE, selectbackground=PUR3,
            selectforeground=PUR1, activestyle="none",
            font=(MONO, 9), relief="flat", bd=6,
            highlightthickness=0, height=5,
            yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.pl_listbox.yview)
        self.pl_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.pl_listbox.bind("<<ListboxSelect>>", self._on_playlist_select)
        pl_hint = tk.Frame(self.pl_frame, bg=BG)
        pl_hint.pack(fill="x", pady=(4,0))
        tk.Label(pl_hint, text="Selecione um item para baixar individualmente",
            bg=BG, fg=MUTED, font=(MONO, 7, "italic")).pack(side="left")
        self.pl_all_btn = self._sec_btn(pl_hint, "[BAIXAR TODA A PLAYLIST]",
                                        self._download_all_playlist)
        self.pl_all_btn.pack(side="right")

        # Formato / Qualidade
        fmt_row = tk.Frame(body, bg=BG)
        fmt_row.pack(fill="x", pady=(10, 4))
        self._lbl(fmt_row, "FORMATO / QUALIDADE").pack(side="left")
        self.fmt_var = tk.StringVar()
        self.fmt_cb  = ttk.Combobox(fmt_row, textvariable=self.fmt_var,
            values=[], width=54, state="disabled",
            font=(MONO, 9))
        self._style_combobox()
        self.fmt_cb.pack(side="left", padx=(8, 0))

        # Pasta de saída
        out_row = tk.Frame(body, bg=BG)
        out_row.pack(fill="x", pady=(6, 10))
        self._lbl(out_row, "PASTA DE SAÍDA:").pack(side="left")
        self.outdir_var = tk.StringVar(
            value=self._prefs.get("outdir", str(Path.home() / "Downloads")))
        dir_wrap = tk.Frame(out_row, bg=PUR3,
                            highlightbackground=PUR2, highlightthickness=1)
        dir_wrap.pack(side="left", padx=(6,6))
        tk.Entry(dir_wrap, textvariable=self.outdir_var,
            bg=BG2, fg=WHITE, insertbackground=PUR1,
            relief="flat", font=(MONO, 9), width=36, bd=4).pack()
        self._sec_btn(out_row, "[...]", self._pick_dir).pack(side="left")

        # Barra de progresso
        self._lbl(body, "PROGRESSO").pack(anchor="w", pady=(4,0))
        prog_bg = tk.Frame(body, bg=BG2, height=18,
                           highlightbackground=PUR3, highlightthickness=1)
        prog_bg.pack(fill="x", pady=(4, 0))
        prog_bg.pack_propagate(False)
        self.prog_bar = tk.Canvas(prog_bg, height=16, bg=BG2,
                                  highlightthickness=0)
        self.prog_bar.pack(fill="both", expand=True)
        self._prog_pct = 0
        self._prog_rect = None

        # Log
        log_hdr = tk.Frame(body, bg=BG)
        log_hdr.pack(fill="x", pady=(12, 0))
        self._lbl(log_hdr, "TRANSMISSÃO DE DADOS").pack(side="left")
        tk.Label(log_hdr, text=" " + "·" * 40,
            bg=BG, fg=MUTED, font=(MONO, 7)).pack(side="left")
        self._sec_btn(log_hdr, "[COPIAR LOG]",
                      self._copy_log).pack(side="right")

        log_wrap = tk.Frame(body, bg=BG2,
                            highlightbackground=PUR3, highlightthickness=1)
        log_wrap.pack(fill="both", expand=True, pady=(4, 0))
        self.log_box = scrolledtext.ScrolledText(log_wrap,
            height=8, bg=BG2, fg=WHITE,
            insertbackground=PUR1, relief="flat",
            font=(MONO, 9), bd=8, state="disabled",
            wrap="word", cursor="xterm")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("ok",   foreground=GREEN)
        self.log_box.tag_config("err",  foreground=RED)
        self.log_box.tag_config("warn", foreground=WARN)
        self.log_box.tag_config("pur",  foreground=PUR1)
        self.log_box.tag_config("cyan", foreground=CYAN)

        # Rodapé
        footer = tk.Frame(body, bg=BG)
        footer.pack(fill="x", pady=(10, 20))
        top_line2 = tk.Canvas(footer, height=1, bg=PUR3,
                              highlightthickness=0, relief="flat")
        top_line2.pack(fill="x", pady=(0,8))
        btn_row = tk.Frame(footer, bg=BG)
        btn_row.pack(fill="x")
        self.dl_btn = self._neon_btn(btn_row, "[ ✦ BAIXAR ]",
                                     self._start_download, big=True)
        self.dl_btn.config(state="disabled")
        self.dl_btn.pack(side="left")
        self.open_btn = self._sec_btn(btn_row, "[ ABRIR PASTA ]",
                                      self._open_outdir)
        self.open_btn.config(state="disabled")
        self.open_btn.pack(side="left", padx=(10, 0))
        self.status_lbl = tk.Label(btn_row, text="",
            bg=BG, fg=MUTED, font=(MONO, 8))
        self.status_lbl.pack(side="right")

    # ── Widgets helpers ───────────────────────────────────────────────────────
    def _lbl(self, parent, text):
        return tk.Label(parent, text=text, bg=BG, fg=MUTED,
                        font=(MONO, 7))

    def _neon_btn(self, parent, text, cmd, color=PUR1, big=False):
        size = 11 if big else 9
        btn = tk.Button(parent, text=text, command=cmd,
            bg=BG2, fg=color, activebackground=PUR3,
            activeforeground=WHITE, relief="flat",
            font=(MONO, size, "bold"), cursor="hand2",
            bd=0, padx=14, pady=8,
            highlightbackground=color, highlightthickness=1)
        return btn

    def _sec_btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd,
            bg=BG2, fg=CYAN, activebackground=PUR3,
            activeforeground=WHITE, relief="flat",
            font=(MONO, 8), cursor="hand2",
            bd=0, padx=10, pady=5,
            highlightbackground=PUR3, highlightthickness=1)

    def _paste_btn(self, parent, cmd):
        return tk.Button(parent, text="[COLAR]", command=cmd,
            bg=BG2, fg=CYAN, activebackground=PUR3,
            activeforeground=WHITE, relief="flat",
            font=(MONO, 8), cursor="hand2",
            bd=0, padx=8, pady=6,
            highlightbackground=PUR3, highlightthickness=1)

    def _style_combobox(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox",
            fieldbackground=BG2, background=BG2,
            foreground=WHITE, selectbackground=PUR3,
            selectforeground=PUR1,
            arrowcolor=PUR1, insertcolor=PUR1)
        style.map("TCombobox",
            fieldbackground=[("readonly", BG2)],
            foreground=[("readonly", WHITE)],
            selectbackground=[("readonly", PUR3)])
        self.option_add("*TCombobox*Listbox.background", BG2)
        self.option_add("*TCombobox*Listbox.foreground", WHITE)
        self.option_add("*TCombobox*Listbox.selectBackground", PUR3)
        self.option_add("*TCombobox*Listbox.selectForeground", PUR1)
        self.option_add("*TCombobox*Listbox.font", (MONO, 9))

    def _draw_thumb_placeholder(self):
        c = self.thumb_canvas
        c.delete("all")
        c.create_rectangle(0, 0, 120, 68, fill=BG2, outline=PUR3)
        # estrela central decorativa
        c.create_text(60, 34, text="✦", fill=PUR2, font=(DISPLAY, 22))

    # ── Prefs ─────────────────────────────────────────────────────────────────
    def _load_prefs(self):
        if "outdir" in self._prefs:
            self.outdir_var.set(self._prefs["outdir"])

    def _save_prefs(self):
        self._prefs["outdir"] = self.outdir_var.get()
        save_prefs(self._prefs)

    # ── Log ───────────────────────────────────────────────────────────────────
    def _log(self, msg, tag=""):
        def _do():
            self.log_box.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_box.insert("end", f"  {ts}  ›  {msg}\n", tag or None)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _do)

    def _copy_log(self):
        self.log_box.configure(state="normal")
        content = self.log_box.get("1.0", "end")
        self.log_box.configure(state="disabled")
        self.clipboard_clear()
        self.clipboard_append(content)
        self._flash_status("— log copiado —")

    def _flash_status(self, msg, ms=2000):
        self.status_lbl.config(text=msg)
        self.after(ms, lambda: self.status_lbl.config(text=""))

    # ── Progresso ─────────────────────────────────────────────────────────────
    def _set_progress(self, pct):
        def _do():
            w = self.prog_bar.winfo_width()
            h = self.prog_bar.winfo_height()
            self.prog_bar.delete("all")
            if pct > 0:
                fill_w = int(w * pct / 100)
                # gradiente simulado com duas faixas
                self.prog_bar.create_rectangle(0, 0, fill_w, h,
                    fill=PUR2, outline="")
                self.prog_bar.create_rectangle(max(0, fill_w-20), 0, fill_w, h,
                    fill=PUR1, outline="")
            # texto
            self.prog_bar.create_text(w//2, h//2,
                text=f"{pct}%" if pct > 0 else "",
                fill=WHITE, font=(MONO, 7))
        self.after(0, _do)

    # ── Ações ─────────────────────────────────────────────────────────────────
    def _paste_url(self):
        try:
            t = self.clipboard_get().strip()
            if t:
                self.url_var.set(t)
                self._flash_status("— URL colada —")
        except tk.TclError:
            pass

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

    # ── Fetch ─────────────────────────────────────────────────────────────────
    def _fetch(self):
        url = self.url_var.get().strip()
        if not url:
            return
        self._reset_ui()
        self._set_busy(True, phase="fetch")
        self._log(f"Buscando informações: {url[:60]}...", "pur")
        threading.Thread(target=self._do_fetch, args=(url,), daemon=True).start()

    def _do_fetch(self, url):
        try:
            if is_playlist_url(url):
                self._log("Detectada playlist — lendo índice...", "cyan")
                entries = fetch_playlist_index(url)
                self.after(0, lambda: self._show_playlist(url, entries))
            else:
                info = fetch_info(url)
                self._formats   = build_format_list(info)
                self._info      = info
                self._single_url = url   # garante que o URL correto é usado no download
                self.after(0, lambda: self._show_video_info(info))
        except Exception as e:
            self._log(f"ERRO ao buscar: {e}", "err")
            self.after(0, lambda: self._set_busy(False))

    def _show_video_info(self, info):
        self._set_busy(False)
        title    = info.get("title", "(sem título)")
        duration = info.get("duration", 0)
        uploader = info.get("uploader") or info.get("channel") or ""
        extractor = info.get("extractor_key", info.get("extractor", ""))
        dur_str  = f"{duration//60}m{duration%60:02d}s" if duration else ""
        meta     = "  ".join(filter(None, [uploader, dur_str]))

        self.title_lbl.config(text=title[:90] + ("…" if len(title)>90 else ""))
        self.meta_lbl.config(text=meta)
        self.site_lbl.config(text=f"⬡ {extractor}")

        # Popula combobox de formatos
        labels = [f["label"] for f in self._formats]
        self.fmt_cb.config(values=labels, state="readonly")
        self.fmt_cb.current(0)

        self.dl_btn.config(state="normal")
        self._log(f"✦ {title}", "pur")
        self._log(f"  {len(self._formats)-3} formato(s) disponível(is) + opções automáticas", "cyan")

    def _show_playlist(self, url, entries):
        self._playlist = entries
        self._set_busy(False)

        # Mostra painel de playlist
        self.pl_frame.pack(fill="x", pady=(8, 4), before=self.fmt_cb.master)
        self.pl_listbox.delete(0, "end")
        for e in entries:
            self.pl_listbox.insert("end", f"  {e['title'][:70]}")

        self.title_lbl.config(text=f"Playlist — {len(entries)} vídeo(s)")
        self.meta_lbl.config(text=url[:70])
        self.site_lbl.config(text="")
        self._log(f"✦ Playlist: {len(entries)} item(ns) encontrado(s)", "pur")
        self._log("Selecione um item para baixar individualmente, ou use [BAIXAR TODA A PLAYLIST]", "cyan")

    def _on_playlist_select(self, event):
        sel = self.pl_listbox.curselection()
        if not sel:
            return
        idx   = sel[0]
        entry = self._playlist[idx]
        self._log(f"Buscando formatos: {entry['title'][:50]}...", "cyan")
        self._set_busy(True, phase="fetch")
        threading.Thread(
            target=self._do_fetch_single,
            args=(entry["url"],), daemon=True).start()

    def _do_fetch_single(self, url):
        try:
            info = fetch_info(url)
            self._formats = build_format_list(info)
            self._info    = info
            self.after(0, lambda: self._show_video_info(info))
            # guarda url do item individual
            self._single_url = url
        except Exception as e:
            self._log(f"ERRO: {e}", "err")
            self.after(0, lambda: self._set_busy(False))

    # ── Download ──────────────────────────────────────────────────────────────
    def _get_selected_format(self):
        idx = self.fmt_cb.current()
        if idx < 0 or idx >= len(self._formats):
            return None
        fmt = self._formats[idx]
        if fmt["format_id"] is None:
            return None  # separador
        return fmt

    def _start_download(self):
        fmt = self._get_selected_format()
        if not fmt:
            self._log("Selecione um formato válido.", "warn")
            return
        url = self._single_url or self.url_var.get().strip()
        outdir = self.outdir_var.get()
        os.makedirs(outdir, exist_ok=True)
        self._save_prefs()
        self._set_busy(True, phase="download")
        self._set_progress(0)
        self._log(f"⬇  Iniciando download: {fmt['label'].strip()}", "pur")
        threading.Thread(
            target=self._do_download,
            args=(url, fmt, outdir), daemon=True).start()

    def _download_all_playlist(self):
        if not self._playlist:
            return
        outdir = self.outdir_var.get()
        os.makedirs(outdir, exist_ok=True)
        self._save_prefs()
        # Usa melhor qualidade para playlist inteira
        fmt = {"label": "Melhor qualidade", "format_id": "bestvideo+bestaudio/best",
               "ext": "mp4", "note": "automático"}
        self._set_busy(True, phase="download")
        self._log(f"⬇  Baixando playlist completa ({len(self._playlist)} item(ns))...", "pur")
        threading.Thread(
            target=self._do_download_playlist,
            args=(fmt, outdir), daemon=True).start()

    def _do_download(self, url, fmt, outdir):
        try:
            title = download(url, fmt, outdir,
                             self._log, self._cancel_event,
                             progress_fn=self._set_progress)
            self._log(f"✦ Concluído: {title}", "ok")
            self.after(0, self._on_done)
        except Exception as e:
            if self._cancel_event.is_set():
                self._log("Cancelado.", "warn")
            else:
                self._log(f"ERRO: {e}", "err")
            self.after(0, lambda: self._set_busy(False))

    def _do_download_playlist(self, fmt, outdir):
        total  = len(self._playlist)
        errors = 0
        for i, entry in enumerate(self._playlist, 1):
            if self._cancel_event.is_set():
                break
            self._log(f"[{i}/{total}] {entry['title'][:50]}", "cyan")
            self._set_progress(int((i-1)/total*100))
            try:
                download(entry["url"], fmt, outdir,
                         self._log, self._cancel_event)
            except Exception as e:
                if self._cancel_event.is_set():
                    break
                self._log(f"  ERRO: {e}", "err")
                errors += 1
        self._set_progress(100)
        msg = f"✦ Playlist concluída: {total-errors}/{total}"
        if errors:
            msg += f" ({errors} erro(s))"
        self._log(msg, "ok" if not errors else "warn")
        self.after(0, self._on_done)

    def _cancel(self):
        self._cancel_event.set()
        self._log("Cancelando...", "warn")
        self.cancel_btn.config(state="disabled")

    def _on_done(self):
        self._set_busy(False)
        self.open_btn.config(state="normal")
        self._flash_status("✦ download completo", 4000)

    # ── Estado da UI ──────────────────────────────────────────────────────────
    def _set_busy(self, busy, phase=""):
        self._running = busy
        self._cancel_event.clear()
        if busy:
            self.fetch_btn.config(state="disabled")
            self.dl_btn.config(state="disabled")
            self.cancel_btn.config(state="normal")
        else:
            self.fetch_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")

    def _reset_ui(self):
        self.title_lbl.config(text="—")
        self.meta_lbl.config(text="")
        self.site_lbl.config(text="")
        self.fmt_cb.config(values=[], state="disabled")
        self.fmt_var.set("")
        self.dl_btn.config(state="disabled")
        self._formats = []
        self._info    = None
        self._playlist = []
        self._single_url = None
        self._draw_thumb_placeholder()
        self._set_progress(0)
        try:
            self.pl_frame.pack_forget()
        except Exception:
            pass


# ─────────────────────────────────────────────
def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
