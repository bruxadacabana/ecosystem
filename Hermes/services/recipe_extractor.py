"""
Extrator de receitas de vídeo — pipeline yt-dlp → legendas/Whisper → LLM → RecipeResult.

Fluxo de extração:
  1. yt-dlp: metadata + download de legendas (pt/en/*)
  2. Se nenhuma legenda disponível: download de áudio + WhisperModel
  3. LLM: extração estruturada JSON com ingredientes, passos e dicas
  4. Retorna RecipeResult com todos os metadados e o conteúdo estruturado
"""
from __future__ import annotations

import glob
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class RecipeError(Exception):
    """Falha genérica no pipeline de extração de receita."""


class RecipeDownloadError(RecipeError):
    """Falha ao baixar vídeo ou legendas."""


class RecipeTranscribeError(RecipeError):
    """Falha na transcrição por Whisper."""


class RecipeLLMError(RecipeError):
    """Falha ao chamar o LLM ou parsear o JSON retornado."""


@dataclass
class RecipeResult:
    recipe_name: str = ""
    ingredients: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)
    # metadados do vídeo
    title: str = ""
    source_url: str = ""
    source_platform: str = ""
    channel: str = ""
    duration_seconds: int = 0
    language: str = ""
    published_date: str = ""   # YYYY-MM-DD
    thumbnail: str = ""
    extracted_at: str = ""
    transcript: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


_LLM_PROMPT = (
    "Analise a transcrição abaixo de um vídeo de receita culinária e extraia as informações "
    "no seguinte JSON:\n\n"
    "{\n"
    '  "recipe_name": "nome da receita",\n'
    '  "ingredients": ["ingrediente 1", "ingrediente 2"],\n'
    '  "steps": ["passo 1", "passo 2"],\n'
    '  "tips": ["dica 1"]\n'
    "}\n\n"
    "Regras:\n"
    "- Inclua apenas informações presentes na transcrição — não invente.\n"
    "- `tips` pode ser lista vazia se não houver dicas.\n"
    "- Responda APENAS com o JSON, sem texto antes ou depois.\n"
    "- Responda em português.\n\n"
    "Transcrição:\n{transcript}\n\n"
    "JSON:"
)


def _infer_platform(url: str) -> str:
    if not url or not url.startswith("http"):
        return "local"
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "tiktok.com" in url:
        return "tiktok"
    if any(x in url for x in ("spotify.com", "anchor.fm", "soundcloud.com")):
        return "podcast"
    return "web"


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    m2 = re.search(r"\{.*\}", raw, re.DOTALL)
    if m2:
        raw = m2.group(0)
    return json.loads(raw)


def _get_subtitles(info: dict, tmpdir: str) -> str:
    """Tenta ler legenda já baixada pelo yt-dlp. Retorna texto limpo ou ''."""
    title_safe = re.sub(r'[<>:"/\\|?*]', "_", info.get("title", "video"))[:80]
    for lang in ("pt", "pt-BR", "pt-PT", "en"):
        for ext in ("vtt", "srt", "srv3", "ttml"):
            pattern = os.path.join(tmpdir, f"{title_safe}.{lang}.{ext}")
            matches = glob.glob(pattern)
            if not matches:
                # tenta glob mais permissivo
                matches = glob.glob(os.path.join(tmpdir, f"*.{lang}.{ext}"))
            if matches:
                try:
                    raw = Path(matches[0]).read_text(encoding="utf-8", errors="replace")
                    return _clean_vtt(raw)
                except OSError:
                    continue
    # fallback: qualquer legenda no tmpdir
    for f in glob.glob(os.path.join(tmpdir, "*.vtt")):
        try:
            return _clean_vtt(Path(f).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return ""


def _clean_vtt(raw: str) -> str:
    """Remove timestamps e tags HTML de arquivos VTT/SRT, retorna texto limpo."""
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        # pula cabeçalho WEBVTT, timestamps, linhas de índice numéricas
        if (line.startswith("WEBVTT")
                or re.match(r"^\d+$", line)
                or re.match(r"[\d:.,\s]+ --> ", line)
                or not line):
            continue
        # remove tags HTML/VTT como <c>, <00:00:00.000>
        line = re.sub(r"<[^>]+>", "", line)
        lines.append(line)
    # deduplica linhas adjacentes iguais (legendas auto-geradas repetem)
    deduped = []
    prev = ""
    for ln in lines:
        if ln != prev:
            deduped.append(ln)
        prev = ln
    return " ".join(deduped)


def _transcribe_audio(audio_path: str, model_size: str, language: str) -> str:
    """Transcreve áudio com faster-whisper. Retorna texto concatenado."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RecipeTranscribeError(
            f"faster-whisper não encontrado. Instale com: pip install faster-whisper"
        ) from exc

    device = "cpu"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            device = "cuda"
    except Exception:
        pass

    compute_type = "float16" if device == "cuda" else "int8"
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type, num_workers=1)
        lang_arg = language if language != "auto" else None
        segments_gen, _ = model.transcribe(audio_path, language=lang_arg, vad_filter=True, beam_size=1)
        return " ".join(seg.text.strip() for seg in segments_gen)
    except Exception as exc:
        raise RecipeTranscribeError(f"Falha na transcrição Whisper: {exc}") from exc


def _call_llm(transcript: str, llm_model: str) -> dict:
    """Chama llama-server com o prompt de extração e retorna dict parsed."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RecipeLLMError(
            "langchain-openai não encontrado. Instale com: pip install langchain-openai"
        ) from exc

    try:
        from ecosystem_client import get_inference_url as _giu
        base_url = f"{_giu()}/v1"
        llm = ChatOpenAI(model=llm_model, temperature=0.2, timeout=120,
                         base_url=base_url, api_key="logos")
        raw = llm.invoke(_LLM_PROMPT.format(transcript=transcript[:6000])).content
    except Exception as exc:
        raise RecipeLLMError(f"Falha ao chamar LLM: {exc}") from exc

    try:
        return _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RecipeLLMError(f"Resposta do LLM não é JSON válido: {exc}\nRaw: {raw[:300]}") from exc


def extract_recipe(
    url: str,
    *,
    model_size: str = "small",
    language: str = "auto",
    llm_model: str = "qwen2.5:7b",
    recipes_dir: str = "",
) -> RecipeResult:
    """Extrai receita de uma URL de vídeo.

    Fluxo:
      1. yt-dlp: metadata + legendas (skip_download)
      2. Se sem legenda: download de áudio + Whisper
      3. LLM: extração JSON de ingredientes/passos/dicas
    """
    try:
        import yt_dlp
    except ImportError as exc:
        return RecipeResult(source_url=url, error="yt-dlp não encontrado. Instale com: pip install yt-dlp")

    result = RecipeResult(
        source_url=url,
        source_platform=_infer_platform(url),
        extracted_at=datetime.now(timezone.utc).isoformat(),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # ── Passo 1: metadata + legendas ────────────────────────────────────────
        try:
            subtitle_opts = {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["pt", "pt-BR", "en", ".*"],
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
                "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
            }
            with yt_dlp.YoutubeDL(subtitle_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as exc:
            result.error = f"Falha ao obter metadados: {exc}"
            return result

        result.title = info.get("title", "")
        result.channel = info.get("uploader") or info.get("channel") or ""
        result.duration_seconds = int(info.get("duration") or 0)
        result.language = info.get("language") or language
        result.thumbnail = info.get("thumbnail") or ""
        upload_date = info.get("upload_date", "")  # YYYYMMDD
        if upload_date and len(upload_date) == 8:
            result.published_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

        # ── Passo 2: transcript via legenda ou Whisper ────────────────────────
        transcript = _get_subtitles(info, tmpdir)

        if not transcript:
            # Sem legenda disponível — baixar áudio e transcrever
            try:
                audio_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
                    "postprocessors": [{"key": "FFmpegExtractAudio",
                                        "preferredcodec": "mp3", "preferredquality": "128"}],
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                }
                with yt_dlp.YoutubeDL(audio_opts) as ydl:
                    ydl.extract_info(url, download=True)
                mp3_files = glob.glob(os.path.join(tmpdir, "*.mp3"))
                if not mp3_files:
                    raise RecipeDownloadError(
                        "Arquivo de áudio não encontrado após download. "
                        "Verifique se o ffmpeg está instalado e no PATH."
                    )
                transcript = _transcribe_audio(mp3_files[0], model_size, language)
            except RecipeTranscribeError as exc:
                result.error = str(exc)
                return result
            except RecipeDownloadError as exc:
                result.error = str(exc)
                return result
            except Exception as exc:
                result.error = f"Falha ao baixar/transcrever áudio: {exc}"
                return result

        if not transcript:
            result.error = "Não foi possível obter transcrição para esta URL."
            return result

        result.transcript = transcript

    # ── Passo 3: LLM JSON extraction ─────────────────────────────────────────
    try:
        data = _call_llm(transcript, llm_model)
    except RecipeLLMError as exc:
        result.error = str(exc)
        return result

    result.recipe_name = data.get("recipe_name", result.title)
    result.ingredients = [str(x) for x in data.get("ingredients", [])]
    result.steps = [str(x) for x in data.get("steps", [])]
    result.tips = [str(x) for x in data.get("tips", [])]

    return result


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-")[:60]


def to_markdown(result: RecipeResult, *, recipes_dir: str = "") -> str:
    """Constrói markdown com frontmatter YAML e salva em recipes_dir.

    Retorna o markdown gerado (string). Se recipes_dir for fornecido,
    salva o arquivo automaticamente e define result.saved_path se o
    atributo existir.
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    filename = f"{_slugify(result.recipe_name or result.title) or 'receita'}-{now.strftime('%Y%m%d')}.md"

    # ── Frontmatter ────────────────────────────────────────────────────────────
    name_safe = (result.recipe_name or result.title).replace('"', '\\"')
    lines = [
        "---",
        "type: recipe",
        f'title: "{name_safe}"',
        f"source_url: {result.source_url}",
        f"source_platform: {result.source_platform}",
    ]
    if result.channel:
        lines.append(f'channel: "{result.channel.replace(chr(34), chr(92)+chr(34))}"')
    lines += [
        f"duration_seconds: {result.duration_seconds}",
        f"language: {result.language}",
        f"published_date: {result.published_date or date_str}",
    ]
    if result.thumbnail:
        lines.append(f"thumbnail: {result.thumbnail}")
    lines += [
        f"extracted_at: {result.extracted_at or now.isoformat()}",
        "---",
        "",
        f"# {result.recipe_name or result.title}",
        "",
    ]

    # ── Ingredientes ──────────────────────────────────────────────────────────
    lines.append("## Ingredientes")
    lines.append("")
    if result.ingredients:
        for ing in result.ingredients:
            lines.append(f"- {ing}")
    else:
        lines.append("_(nenhum ingrediente identificado)_")
    lines.append("")

    # ── Modo de Preparo ───────────────────────────────────────────────────────
    lines.append("## Modo de Preparo")
    lines.append("")
    if result.steps:
        for i, step in enumerate(result.steps, start=1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("_(nenhum passo identificado)_")
    lines.append("")

    # ── Dicas (opcional) ──────────────────────────────────────────────────────
    if result.tips:
        lines.append("## Dicas")
        lines.append("")
        for tip in result.tips:
            lines.append(f"- {tip}")
        lines.append("")

    md = "\n".join(lines)

    if recipes_dir:
        out_dir = Path(recipes_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / filename).write_text(md, encoding="utf-8")

    return md


class RecipePlaylistExtractor:
    """Extrai URLs de vídeos de uma playlist/canal para extração em lote."""

    def extract_urls(self, playlist_url: str) -> list[str]:
        """Retorna lista de URLs de vídeos da playlist."""
        try:
            import yt_dlp
        except ImportError as exc:
            raise RecipeDownloadError(
                "yt-dlp não encontrado. Instale com: pip install yt-dlp"
            ) from exc

        opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
        except Exception as exc:
            raise RecipeDownloadError(f"Falha ao ler playlist: {exc}") from exc

        urls: list[str] = []
        for entry in info.get("entries") or []:
            if not entry:
                continue
            vurl = entry.get("url") or entry.get("webpage_url", "")
            if vurl and not vurl.startswith("http"):
                vurl = f"https://www.youtube.com/watch?v={vurl}"
            if vurl:
                urls.append(vurl)
        return urls

    def iter_extract(
        self,
        playlist_url: str,
        *,
        model_size: str = "small",
        language: str = "auto",
        llm_model: str = "qwen2.5:7b",
        recipes_dir: str = "",
        progress_cb=None,   # callable(current: int, total: int, title: str)
    ) -> Iterator[RecipeResult]:
        """Extrai receitas de todos os vídeos da playlist.

        Yields cada RecipeResult (incluindo os que falharam com error != '').
        Chama progress_cb(current, total, title) antes de cada vídeo.
        """
        urls = self.extract_urls(playlist_url)
        total = len(urls)
        for i, url in enumerate(urls, start=1):
            result = extract_recipe(
                url,
                model_size=model_size,
                language=language,
                llm_model=llm_model,
                recipes_dir=recipes_dir,
            )
            if progress_cb is not None:
                progress_cb(i, total, result.title or url)
            yield result
