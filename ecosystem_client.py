"""
ecosystem_client — utilitário Python compartilhado do ecossistema.

Usado por KOSMOS, Mnemosyne e Hermes para ler/escrever
~/.local/share/ecosystem/ecosystem.json (Linux) ou
%APPDATA%\\ecosystem\\ecosystem.json (Windows).
"""
from __future__ import annotations

import json
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any

try:
    from filelock import FileLock as _FileLock
    _HAS_FILELOCK = True
except ImportError:
    _HAS_FILELOCK = False
    warnings.warn(
        "filelock não instalado — write_section sem proteção contra race condition. "
        "Instale com: pip install filelock",
        stacklevel=1,
    )

# ---------------------------------------------------------------------------
# Schema padrão — seções por app
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    "aether":    {"vault_path": "", "config_path": ""},
    "kosmos":    {"data_path": "", "archive_path": "", "config_path": "", "http_port": 8965},
    "ogma":      {"data_path": "", "config_path": ""},
    "mnemosyne": {"index_paths": [], "config_path": ""},
    "hub":       {"data_path": ""},
    "hermes":    {"output_dir": "", "config_path": ""},
    "akasha":    {"archive_path": "", "data_path": "", "base_url": "", "config_path": ""},
    "logos":     {"ollama_base": "http://localhost:11434"},
}


def ecosystem_path() -> Path:
    """Retorna o caminho canônico do ecosystem.json segundo XDG/AppData."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "ecosystem" / "ecosystem.json"


def read_ecosystem() -> dict[str, Any]:
    """
    Lê ecosystem.json e retorna o conteúdo mergeado com os defaults.
    Retorna apenas defaults se o arquivo não existir ou estiver corrompido.
    """
    path = ecosystem_path()
    if not path.exists():
        return {k: dict(v) if isinstance(v, dict) else list(v)
                for k, v in _DEFAULTS.items()}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        # Merge: garante que todas as seções existam mesmo em arquivos antigos
        result: dict[str, Any] = {}
        # Preserva campos extras do arquivo que não estão em _DEFAULTS (ex: sync_root)
        for key, value in data.items():
            if key not in _DEFAULTS:
                result[key] = value
        for key, default in _DEFAULTS.items():
            if isinstance(default, dict):
                result[key] = {**default, **data.get(key, {})}
            else:
                result[key] = data.get(key, list(default))
        return result
    except (json.JSONDecodeError, OSError):
        return {k: dict(v) if isinstance(v, dict) else list(v)
                for k, v in _DEFAULTS.items()}


def derive_paths(sync_root: str) -> dict[str, Any]:
    """
    Dado um diretório raiz de sincronização, retorna os caminhos derivados
    para cada app do ecossistema.

    Estrutura gerada:
        {sync_root}/aether/          → aether.vault_path
        {sync_root}/kosmos/          → kosmos.archive_path
        {sync_root}/mnemosyne/docs/  → mnemosyne.watched_dir
        {sync_root}/mnemosyne/chroma_db/ → mnemosyne.chroma_dir
        {sync_root}/hermes/          → hermes.output_dir
        {sync_root}/akasha/          → akasha.archive_path + akasha.data_path
        {sync_root}/ogma/            → ogma.data_path
    """
    root = Path(sync_root)
    return {
        "aether":    {"vault_path":   str(root / "aether"),
                      "config_path":  str(root / "aether"    / ".config")},
        "kosmos":    {"archive_path": str(root / "kosmos"),
                      "config_path":  str(root / "kosmos"    / ".config")},
        "mnemosyne": {"watched_dir":  str(root / "mnemosyne" / "docs"),
                      "chroma_dir":   str(root / "mnemosyne" / "chroma_db"),
                      "config_path":  str(root / "mnemosyne" / ".config")},
        "hermes":    {"output_dir":   str(root / "hermes"),
                      "config_path":  str(root / "hermes"    / ".config")},
        "akasha":    {"archive_path": str(root / "akasha"),
                      "data_path":    str(root / "akasha"),
                      "config_path":  str(root / "akasha"    / ".config")},
        "ogma":      {"data_path":    str(root / "ogma"),
                      "config_path":  str(root / "ogma"      / ".config")},
    }


# ---------------------------------------------------------------------------
# LOGOS — cliente HTTP (porta 7072)
# ---------------------------------------------------------------------------

_LOGOS_PORT = 7072
_LOGOS_BASE = f"http://127.0.0.1:{_LOGOS_PORT}"

# URL do Ollama a usar nos apps: aponta para o LOGOS (proxy transparente).
# Apps devem usar get_ollama_url() para obter a URL correta em runtime.
LOGOS_OLLAMA_BASE = f"http://127.0.0.1:{_LOGOS_PORT}"
OLLAMA_DIRECT     = "http://localhost:11434"


def get_ollama_url() -> str:
    """Retorna a URL do Ollama a usar: 7072 (LOGOS) se disponível, 11434 direto como fallback."""
    status = _logos_get("/logos/status", timeout=1.5)
    return LOGOS_OLLAMA_BASE if status is not None else OLLAMA_DIRECT


def _logos_get(path: str, timeout: float = 3.0) -> "dict[str, Any] | None":
    """GET JSON ao LOGOS. Retorna None se HUB não estiver rodando."""
    import urllib.request as _r
    try:
        with _r.urlopen(f"{_LOGOS_BASE}{path}", timeout=timeout) as resp:
            return json.loads(resp.read())
    except OSError:
        return None


def _logos_post(path: str, data: "dict[str, Any]", timeout: float = 10.0) -> "dict[str, Any] | None":
    """POST JSON ao LOGOS. Retorna None se HUB não estiver rodando."""
    import urllib.request as _r
    import urllib.error as _ue
    body = json.dumps(data).encode()
    req = _r.Request(f"{_LOGOS_BASE}{path}", data=body,
                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _r.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except _ue.HTTPError:
        return None
    except OSError:
        return None


def get_ollama_base() -> str:
    """Retorna o endpoint base do Ollama conforme configurado em ecosystem.json.

    Lê logos.ollama_base; fallback para http://localhost:11434.
    """
    eco = read_ecosystem()
    return eco.get("logos", {}).get("ollama_base", "http://localhost:11434")


def logos_status() -> "dict[str, Any] | None":
    """Retorna status do LOGOS (prioridade ativa, fila, VRAM). None se HUB não estiver rodando."""
    return _logos_get("/logos/status")


def get_active_profile() -> "dict[str, Any] | None":
    """Retorna o perfil de hardware ativo do LOGOS com modelos recomendados.

    Estrutura retornada::

        {
          "profile": "main_pc" | "laptop" | "work_pc",
          "profile_display": str,
          "models": {"llm_mnemosyne": str, "llm_kosmos": str, "embed": str}
        }

    Retorna None se o HUB não estiver rodando.
    """
    return _logos_get("/logos/hardware")


def logos_silence() -> bool:
    """Envia keep_alive: 0 para descarregar modelos do Ollama. Retorna True se bem-sucedido."""
    result = _logos_post("/logos/silence", {}, timeout=15.0)
    return result is not None


# Mapeamento de nome de app para campo do ModelProfile retornado por /logos/hardware.
# Apps não listados usam "llm_kosmos" como fallback (modelo mais leve).
_APP_MODEL_KEY: "dict[str, str]" = {
    "mnemosyne": "llm_mnemosyne",
    "kosmos":    "llm_kosmos",
}

# Modelo usado se LOGOS não estiver rodando e model não for especificado.
_FALLBACK_MODEL = "smollm2:1.7b"


def request_llm(
    messages: "list[dict[str, Any]]",
    *,
    app: str,
    model: "str | None" = None,
    priority: int = 3,
    stream: bool = False,
    ollama_base: str = "http://localhost:11434",
    **options: Any,
) -> "dict[str, Any]":
    """Envia chamada LLM ao LOGOS (fila de prioridades) com failsafe direto ao Ollama.

    Se `model` for None, consulta GET /logos/hardware e usa o modelo recomendado
    para o `app` informado. Callers que passam `model` explicitamente não são afetados.

    priority: 1=P1 interativo, 2=P2 RAG, 3=P3 background (padrão)

    Raises:
        RuntimeError: se LOGOS rejeitar (429) ou Ollama retornar erro HTTP.
    """
    import urllib.request as _r
    import urllib.error as _ue

    if model is None:
        profile = get_active_profile()
        if profile is not None:
            key = _APP_MODEL_KEY.get(app, "llm_kosmos")
            model = profile["models"].get(key, _FALLBACK_MODEL)
        else:
            model = _FALLBACK_MODEL

    payload: dict[str, Any] = {
        "app": app,
        "priority": max(1, min(3, priority)),
        "model": model,
        "messages": messages,
        "stream": stream,
        **options,
    }

    # --- Tentar via LOGOS ---
    logos_req = _r.Request(
        f"{_LOGOS_BASE}/logos/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _r.urlopen(logos_req, timeout=300) as resp:
            return json.loads(resp.read())
    except _ue.HTTPError as e:
        if e.code == 429:
            raise RuntimeError(json.loads(e.read()).get("error", "LOGOS: solicitação rejeitada (429)"))
        # Outros erros HTTP → fallback ao Ollama direto
    except OSError:
        pass  # HUB/LOGOS não está rodando → modo emergência

    # --- Failsafe: Ollama direto ---
    direct: dict[str, Any] = {k: v for k, v in payload.items() if k not in ("app", "priority")}
    direct_req = _r.Request(
        f"{ollama_base}/api/chat",
        data=json.dumps(direct).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _r.urlopen(direct_req, timeout=300) as resp:
            return json.loads(resp.read())
    except _ue.HTTPError as e:
        raise RuntimeError(f"Ollama HTTP {e.code}: {e.read().decode(errors='replace')}")
    except OSError as e:
        raise RuntimeError(f"Ollama indisponível: {e}")


def request_llm_stream(
    messages: "list[dict[str, Any]]",
    *,
    app: str,
    model: "str | None" = None,
    priority: int = 1,
    ollama_base: str = "http://localhost:11434",
    **options: Any,
) -> "Generator[str, None, None]":
    """Streaming LLM via LOGOS (P1 por padrão) com fallback direto ao Ollama.

    Yields tokens de texto à medida que chegam (NDJSON, campo ``message.content``).

    Raises:
        RuntimeError: se LOGOS rejeitar (429) ou Ollama retornar erro.
    """
    import urllib.request as _r
    import urllib.error as _ue
    from typing import Generator

    if model is None:
        profile = get_active_profile()
        if profile is not None:
            key = _APP_MODEL_KEY.get(app, "llm_kosmos")
            model = profile["models"].get(key, _FALLBACK_MODEL)
        else:
            model = _FALLBACK_MODEL

    payload: dict[str, Any] = {
        "app": app,
        "priority": max(1, min(3, priority)),
        "model": model,
        "messages": messages,
        "stream": True,
        **options,
    }

    def _iter_ndjson(resp: Any) -> "Generator[str, None, None]":
        buf = b""
        while True:
            chunk = resp.read(512)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    token = (
                        obj.get("message", {}).get("content")  # /api/chat
                        or obj.get("response")                  # /api/generate
                        or ""
                    )
                    if token:
                        yield token
                    if obj.get("done"):
                        return
                except (json.JSONDecodeError, AttributeError):
                    continue

    # --- Tentar via LOGOS ---
    logos_req = _r.Request(
        f"{_LOGOS_BASE}/logos/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _r.urlopen(logos_req, timeout=300) as resp:
            yield from _iter_ndjson(resp)
            return
    except _ue.HTTPError as e:
        if e.code == 429:
            raise RuntimeError(json.loads(e.read()).get("error", "LOGOS: solicitação rejeitada (429)"))
    except OSError:
        pass  # HUB não está rodando → fallback

    # --- Failsafe: Ollama direto ---
    direct: dict[str, Any] = {k: v for k, v in payload.items() if k not in ("app", "priority")}
    direct_req = _r.Request(
        f"{ollama_base}/api/chat",
        data=json.dumps(direct).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _r.urlopen(direct_req, timeout=300) as resp:
            yield from _iter_ndjson(resp)
    except _ue.HTTPError as e:
        raise RuntimeError(f"Ollama HTTP {e.code}: {e.read().decode(errors='replace')}")
    except OSError as e:
        raise RuntimeError(f"Ollama indisponível: {e}")


def _lock_path() -> Path:
    return ecosystem_path().parent / ".ecosystem.lock"


def write_section(app: str, section: dict[str, Any]) -> None:
    """
    Atualiza apenas a seção `app` do ecosystem.json, preservando as demais.
    Escrita atômica + lock exclusivo para evitar race condition entre processos.

    Raises:
        OSError: se a escrita falhar.
    """
    path = ecosystem_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    def _do_write() -> None:
        data = read_ecosystem()
        if app not in data:
            data[app] = {}
        data[app].update(section)

        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    if _HAS_FILELOCK:
        with _FileLock(str(_lock_path()), timeout=10):
            _do_write()
    else:
        _do_write()
