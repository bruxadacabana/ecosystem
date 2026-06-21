"""
ecosystem_client — utilitário Python compartilhado do ecossistema.

Usado por KOSMOS, Mnemosyne e Hermes para ler/escrever
~/.local/share/ecosystem/ecosystem.json (Linux) ou
%APPDATA%\\ecosystem\\ecosystem.json (Windows).
"""
from __future__ import annotations

import json
import logging
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
    "sync_root": "",
    "aether":    {"vault_path": "", "config_path": ""},
    "kosmos":    {"data_path": "", "archive_path": "", "config_path": "", "http_port": 8965},
    "ogma":      {"data_path": "", "config_path": ""},
    "mnemosyne": {"index_paths": [], "config_path": ""},
    "hub":       {"data_path": ""},
    "hermes":    {"output_dir": "", "config_path": ""},
    "akasha":    {"archive_path": "", "data_path": "", "base_url": "", "config_path": ""},
    "logos":     {},
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
        return {
            k: dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v
            for k, v in _DEFAULTS.items()
        }
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        # Merge: garante que todas as seções existam mesmo em arquivos antigos
        result: dict[str, Any] = {}
        # Preserva campos extras do arquivo que não estão em _DEFAULTS
        for key, value in data.items():
            if key not in _DEFAULTS:
                result[key] = value
        for key, default in _DEFAULTS.items():
            if isinstance(default, dict):
                result[key] = {**default, **data.get(key, {})}
            elif isinstance(default, list):
                result[key] = data.get(key, list(default))
            else:
                result[key] = data.get(key, default)
        return result
    except (json.JSONDecodeError, OSError):
        return {
            k: dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v
            for k, v in _DEFAULTS.items()
        }


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

_log = logging.getLogger(__name__)

_LOGOS_PORT = 7072
_LOGOS_BASE = f"http://127.0.0.1:{_LOGOS_PORT}"

# Loga a URL de inferência resolvida só uma vez (evita ruído por chamada).
_inference_url_logged = False


def get_inference_url() -> str:
    """URL do backend de inferência (LOGOS).

    Lê ``akasha.inference_url`` do ecosystem.json em runtime — permite que uma
    instância da AKASHA rodando em outra máquina (ex.: o servidor T410, sem AVX)
    aponte os embeddings/LLM para o LOGOS de outra máquina pela Tailscale
    (ex.: ``http://thewitch:7072``). Sem essa chave configurada (caso do PC
    principal), usa o default local ``http://127.0.0.1:7072`` — comportamento
    inalterado. Deve apontar para o **proxy LOGOS (7072)**, não o embed-server
    (8082) direto, para preservar a serialização do ``embed_semaphore``.

    Toda comunicação com LLMs passa pelo LOGOS. Se o LOGOS não estiver disponível,
    os callers recebem esta URL e a chamada falha — sem fallback.
    """
    global _inference_url_logged
    try:
        configured = read_ecosystem().get("akasha", {}).get("inference_url", "") or ""
    except Exception:  # leitura do ecosystem.json nunca deve quebrar a inferência
        configured = ""
    url = configured.rstrip("/") if isinstance(configured, str) and configured else _LOGOS_BASE
    if not _inference_url_logged:
        _inference_url_logged = True
        _log.info(
            "ecosystem_client: inference_url resolvido para %s (%s)",
            url, "config akasha.inference_url" if configured else "default 127.0.0.1:7072",
        )
    return url


get_ollama_url = get_inference_url   # alias backward-compat


def load_model(model_name: str) -> bool:
    """Pré-aquece um modelo no backend de inferência (carrega na VRAM).

    Envia sinal ao LOGOS para carregar o modelo antes de uma tarefa P1/P2.
    Retorna True se o LOGOS confirmou o carregamento.
    Sem efeito se LOGOS offline — não levanta exceção.
    """
    result = _logos_post("/logos/models/load", {"model": model_name})
    return bool(result and result.get("ok"))


def unload_model(model_name: str) -> bool:
    """Descarrega um modelo do backend de inferência (libera VRAM explicitamente).

    Útil antes de carregar um modelo mais pesado ou liberar VRAM para tarefas P1.
    Retorna True se o LOGOS confirmou o descarregamento.
    Sem efeito se LOGOS offline — não levanta exceção.
    """
    result = _logos_post("/logos/models/unload", {"model": model_name})
    return bool(result and result.get("ok"))


def get_inference_headers(app_name: str, priority: int) -> "dict[str, str]":
    """Headers HTTP para enviar ao LOGOS com app e prioridade explícitos.

    Prioridades:
      1 — chat interativo (usuária aguardando resposta em tempo real)
      2 — operações user-triggered não imediatas (Studio, análise on-demand)
      3 — background autônomo (indexação, reflexões, transcrições)
    """
    return {"X-App": app_name, "X-Priority": str(priority)}


get_ollama_headers = get_inference_headers  # alias backward-compat


def _logos_get(path: str, timeout: float = 3.0) -> "dict[str, Any] | None":
    """GET JSON ao LOGOS. Retorna None se HUB não estiver rodando."""
    import urllib.request as _r
    try:
        with _r.urlopen(f"{get_inference_url()}{path}", timeout=timeout) as resp:
            return json.loads(resp.read())
    except OSError:
        return None


def _logos_post(path: str, data: "dict[str, Any]", timeout: float = 10.0) -> "dict[str, Any] | None":
    """POST JSON ao LOGOS. Retorna None se HUB não estiver rodando."""
    import urllib.request as _r
    import urllib.error as _ue
    body = json.dumps(data).encode()
    req = _r.Request(f"{get_inference_url()}{path}", data=body,
                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _r.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except _ue.HTTPError:
        return None
    except OSError:
        return None


get_ollama_base = get_inference_url  # alias backward-compat


def list_inference_models() -> list[str]:
    """Lista modelos disponíveis no backend de inferência (LOGOS ou llama-server direto).

    Retorna [] se o backend estiver offline ou retornar erro.
    """
    import urllib.request as _r
    url = f"{get_inference_url()}/v1/models"
    try:
        with _r.urlopen(url, timeout=5.0) as resp:
            data = json.loads(resp.read())
            return [item["id"] for item in data.get("data", [])]
    except OSError:
        return []


def logos_status() -> "dict[str, Any] | None":
    """Retorna status do LOGOS (prioridade ativa, fila, VRAM). None se HUB não estiver rodando."""
    return _logos_get("/logos/status")


def get_active_profile() -> "dict[str, Any] | None":
    """Retorna o perfil de hardware ativo do LOGOS com modelos recomendados.

    Estrutura retornada::

        {
          "profile": "main_pc" | "laptop" | "work_pc",
          "profile_display": str,
          "models": {"llm_rag": str, "llm_analysis": str, "llm_query": str, "embed": str}
        }

    Retorna None se o HUB não estiver rodando.
    """
    return _logos_get("/logos/hardware")


def logos_silence() -> bool:
    """Descarrega modelos carregados no llama-server (libera VRAM). Retorna True se bem-sucedido."""
    result = _logos_post("/logos/silence", {}, timeout=15.0)
    return result is not None


# Mapeamento de nome de app para campo do ModelProfile retornado por /logos/hardware
# e para o atributo correspondente em hardware_probe.ModelProfile.
_APP_MODEL_KEY: "dict[str, str]" = {
    "mnemosyne": "llm_rag",
    "kosmos":    "llm_analysis",
    "akasha":    "llm_query",
}


def _fallback_model_for_app(app: str) -> str:
    """Retorna modelo recomendado para o app no hardware atual (fallback offline do LOGOS).

    Usa hardware_probe.get_model_profile() — espelha os mesmos valores de
    HardwareProfile::model_profile() no Rust, por hardware × funcionalidade.
    """
    import hardware_probe as _hp
    mp = _hp.get_model_profile()
    attr = _APP_MODEL_KEY.get(app, "llm_query")
    return getattr(mp, attr, mp.llm_query)


def request_llm(
    messages: "list[dict[str, Any]]",
    *,
    app: str,
    model: "str | None" = None,
    priority: int = 3,
    **options: Any,
) -> "dict[str, Any]":
    """Envia chamada LLM ao LOGOS (→ llama-server).

    Retorna resposta OpenAI-compatível completa (choices[0].message.content).
    Se o LOGOS estiver offline (HUB fechado), levanta RuntimeError imediatamente.

    priority: 1=P1 interativo, 2=P2 RAG, 3=P3 background (padrão)

    Raises:
        RuntimeError: se LOGOS rejeitar (429) ou estiver indisponível.
    """
    import urllib.request as _r
    import urllib.error as _ue

    if model is None:
        profile = get_active_profile()
        if profile is not None:
            key = _APP_MODEL_KEY.get(app, "llm_query")
            model = profile["models"].get(key) or _fallback_model_for_app(app)
        else:
            model = _fallback_model_for_app(app)

    temperature = options.pop("temperature", 0.7)
    max_tokens = options.pop("max_tokens", None) or options.pop("num_predict", None)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    req_headers = {
        "Content-Type": "application/json",
        "X-App": app,
        "X-Priority": str(max(1, min(3, priority))),
    }

    def _try(base: str) -> "dict[str, Any] | None":
        req = _r.Request(
            f"{base}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers=req_headers,
            method="POST",
        )
        try:
            with _r.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read())
        except _ue.HTTPError as e:
            if e.code == 429:
                raise RuntimeError(json.loads(e.read()).get("error", "backend: solicitação rejeitada (429)"))
            return None
        except OSError:
            return None

    result = _try(get_inference_url())
    if result is not None:
        return result
    raise RuntimeError("Backend de inferência indisponível — abra o HUB e ligue a IA")


def request_llm_stream(
    messages: "list[dict[str, Any]]",
    *,
    app: str,
    model: "str | None" = None,
    priority: int = 1,
    **options: Any,
) -> "Generator[str, None, None]":
    """Streaming LLM via LOGOS (P1 por padrão).

    Yields tokens de texto (SSE OpenAI-compatível, choices[0].delta.content).
    Se o LOGOS estiver offline, levanta RuntimeError imediatamente.

    Raises:
        RuntimeError: se LOGOS rejeitar (429) ou estiver indisponível.
    """
    import urllib.request as _r
    import urllib.error as _ue
    from typing import Generator

    if model is None:
        profile = get_active_profile()
        if profile is not None:
            key = _APP_MODEL_KEY.get(app, "llm_query")
            model = profile["models"].get(key) or _fallback_model_for_app(app)
        else:
            model = _fallback_model_for_app(app)

    temperature = options.pop("temperature", 0.7)
    max_tokens = options.pop("max_tokens", None) or options.pop("num_predict", None)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    req_headers = {
        "Content-Type": "application/json",
        "X-App": app,
        "X-Priority": str(max(1, min(3, priority))),
    }

    req = _r.Request(
        f"{get_inference_url()}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers=req_headers,
        method="POST",
    )
    try:
        resp = _r.urlopen(req, timeout=300)
    except _ue.HTTPError as e:
        if e.code == 429:
            raise RuntimeError(json.loads(e.read()).get("error", "backend: solicitação rejeitada (429)"))
        raise RuntimeError(f"LOGOS retornou {e.code} — backend indisponível")
    except OSError as e:
        raise RuntimeError(f"Backend de inferência indisponível — abra o HUB e ligue a IA: {e}")

    buf = b""
    try:
        while True:
            chunk = resp.read(512)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    return
                try:
                    obj = json.loads(data)
                    token = obj["choices"][0]["delta"].get("content", "")
                    if token:
                        yield token
                    if obj["choices"][0].get("finish_reason") == "stop":
                        return
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    finally:
        resp.close()


def _lock_path() -> Path:
    return ecosystem_path().parent / ".ecosystem.lock"


def consult_akasha(
    question: str,
    context: list[str],
    turn_index: int = 0,
    timeout: float = 30.0,
) -> list[tuple[str, list[dict]]]:
    """
    Chama POST {akasha_base_url}/dialogue/turn e retorna os fragmentos recebidos.

    Retorna lista de (text, sources) onde sources é [] para fragmentos intermediários
    e preenchida no evento final. Retorna [] silenciosamente se AKASHA estiver offline
    ou base_url não configurada — a Mnemosyne degrada mostrando só o vault.

    Nota: versão síncrona usando urllib (sem httpx) para compatibilidade com ambientes
    que não têm asyncio rodando (Qt workers). Para SSE streaming character-by-character
    use AkashaClient.dialogue_turn() em core/akasha_client.py.
    """
    import urllib.error
    import urllib.request

    eco = read_ecosystem()
    base_url = eco.get("akasha", {}).get("base_url", "").rstrip("/")
    if not base_url:
        return []

    payload_bytes = json.dumps(
        {"question": question, "context": context, "turn_index": turn_index},
        ensure_ascii=False,
    ).encode()

    try:
        req = urllib.request.Request(
            f"{base_url}/dialogue/turn",
            data=payload_bytes,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        fragments: list[tuple[str, list[dict]]] = []
        current_sources: list[dict] = []
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                payload_str = line[5:].strip()
                if payload_str == "[DONE]":
                    break
                try:
                    event = json.loads(payload_str)
                except (ValueError, TypeError):
                    continue
                if event.get("type") == "fragment":
                    text = event.get("text", "")
                    if text:
                        fragments.append((text, []))
                elif event.get("type") == "sources":
                    current_sources = event.get("sources", [])
        if fragments and current_sources:
            last_text, _ = fragments[-1]
            fragments[-1] = (last_text, current_sources)
        return fragments
    except (urllib.error.URLError, OSError, TimeoutError):
        return []


def notify_mnemosyne_insight(
    topics: list[str],
    summary: str,
    sources: list[dict],
    timeout: float = 5.0,          # mantido por compatibilidade de assinatura
    akasha_thought: str | None = None,
    emotional_context: dict | None = None,
    source_path: str | None = None,
) -> None:
    """
    Deposita insight do AKASHA no ecosystem.json para ser lido pela Mnemosyne.

    A Mnemosyne é uma app Qt sem servidor HTTP — o IPC é via ecosystem.json.
    Escreve em mnemosyne.incoming_insights (lista FIFO de até 20 entradas).
    A Mnemosyne lê via QTimer a cada 60s, move para SQLite local e limpa o campo.
    Falha silenciosamente em caso de erro de IO.

    akasha_thought: nota pessoal do AKASHA sobre a descoberta (opcional). Se
    presente, a Mnemosyne a exibe separada como "AKASHA pensa:" no painel de
    diálogo e a injeta como contexto no prompt.

    source_path: caminho do arquivo arquivado (para arquivos locais do AKASHA) ou
    URL da página (para conteúdo crawleado). Permite à Mnemosyne indexar
    prioritariamente o documento que gerou o insight.
    """
    import datetime as _dt

    try:
        data = read_ecosystem()
        incoming: list[dict] = data.get("mnemosyne", {}).get("incoming_insights", [])
        entry: dict = {
            "topics":      topics,
            "summary":     summary,
            "sources":     sources,
            "received_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        if akasha_thought:
            entry["akasha_thought"] = akasha_thought
        if emotional_context:
            entry["emotional_context"] = emotional_context
        if source_path:
            entry["source_path"] = source_path
        incoming.append(entry)
        incoming = incoming[-50:]  # FIFO com limite de 50
        write_section("mnemosyne", {"incoming_insights": incoming})
    except Exception:
        pass


def notify_akasha_insight(
    content: str,
    tags: list[str] | None = None,
    emotional_context: dict | None = None,
) -> None:
    """
    Deposita insight da Mnemosyne no ecosystem.json para ser lido pelo AKASHA.

    Escreve em akasha.incoming_insights (lista FIFO de até 50 entradas).
    O AKASHA lê via loop de background a cada 5min, move para personal_memory
    com type="connection" e limpa o campo.
    Falha silenciosamente em caso de erro de IO.

    emotional_context (N1): {valence, arousal, epistemic_curiosity,
    dominant_emotion, appraisal_source} — estado afetivo da Mnemosyne ao enviar.
    """
    import datetime as _dt

    try:
        data = read_ecosystem()
        incoming: list[dict] = data.get("akasha", {}).get("incoming_insights", [])
        entry: dict = {
            "content":     content,
            "received_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        if tags:
            entry["tags"] = tags
        if emotional_context:
            entry["emotional_context"] = emotional_context
        incoming.append(entry)
        incoming = incoming[-50:]  # FIFO com limite de 50
        write_section("akasha", {"incoming_insights": incoming})
    except Exception:
        pass


def write_top_level(key: str, value: Any) -> None:
    """
    Atualiza um campo top-level do ecosystem.json (ex: sync_root).
    Escrita atômica + lock exclusivo para evitar race condition entre processos.

    Raises:
        OSError: se a escrita falhar.
    """
    path = ecosystem_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    def _do_write() -> None:
        data = read_ecosystem()
        data[key] = value
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


def get_sync_root() -> Path | None:
    """Retorna sync_root configurado no ecosystem.json. None se não configurado."""
    raw = read_ecosystem().get("sync_root", "")
    return Path(raw) if raw else None


def get_ai_private_dir() -> Path | None:
    """Retorna {sync_root}/.ai_private/. None se sync_root não configurado."""
    root = get_sync_root()
    return (root / ".ai_private") if root is not None else None


def get_backup_dir() -> Path | None:
    """Retorna {sync_root}/.backup/. None se sync_root não configurado."""
    root = get_sync_root()
    return (root / ".backup") if root is not None else None


def _interests_path() -> Path | None:
    """Retorna {sync_root}/interests.json ou None se sync_root não configurado."""
    root = get_sync_root()
    return (root / "interests.json") if root is not None else None


def get_interests() -> list[dict]:
    """Retorna a lista de tópicos de interesse do ecossistema.

    Lê {sync_root}/interests.json. Retorna [] se o arquivo não existir,
    sync_root não estiver configurado, ou o arquivo estiver corrompido.
    Nunca lança exceção.
    """
    path = _interests_path()
    if path is None or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("topics", [])
    except Exception:
        return []


def update_interests(topics: list[dict]) -> None:
    """Faz merge de `topics` no interests.json, preservando entradas fixadas e excluídas.

    Regras de merge por `name` (case-insensitive):
    - Se o tópico já existe com `pinned=True`: mantém weight e sources atuais — não
      sobrescreve (o usuário fixou manualmente, não deve ser modificado por automação).
    - Se o tópico já existe com `excluded=True`: ignora a entrada recebida — o usuário
      excluiu explicitamente e não quer ver ele de volta.
    - Caso contrário: atualiza weight e faz union de sources; mantém pinned/excluded atuais.
    - Tópicos novos (não existem no arquivo): adicionados com os valores recebidos.

    Escrita atômica com filelock. Silenciosamente ignorado se sync_root não configurado.
    """
    path = _interests_path()
    if path is None:
        return

    import datetime as _dt

    def _do_write() -> None:
        existing: list[dict] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8")).get("topics", [])
            except Exception:
                existing = []

        by_name: dict[str, dict] = {t["name"].lower(): t for t in existing if "name" in t}

        for incoming in topics:
            name = incoming.get("name", "").strip()
            if not name:
                continue
            key = name.lower()
            if key in by_name:
                current = by_name[key]
                if current.get("excluded"):
                    continue
                if current.get("pinned"):
                    # Mantém weight e sources atuais — apenas garante que name correto
                    by_name[key] = current
                    continue
                # Merge: atualiza weight, faz union de sources
                merged_sources = list({
                    *current.get("sources", []),
                    *incoming.get("sources", []),
                })
                by_name[key] = {
                    "name":     current["name"],
                    "weight":   incoming.get("weight", current.get("weight", 1.0)),
                    "sources":  merged_sources,
                    "pinned":   current.get("pinned", False),
                    "excluded": current.get("excluded", False),
                }
            else:
                by_name[key] = {
                    "name":     name,
                    "weight":   incoming.get("weight", 1.0),
                    "sources":  incoming.get("sources", []),
                    "pinned":   incoming.get("pinned", False),
                    "excluded": incoming.get("excluded", False),
                }

        result = {
            "topics":     list(by_name.values()),
            "updated_at": _dt.datetime.utcnow().isoformat() + "Z",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
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


def get_akasha_config() -> dict[str, Any]:
    """Retorna a seção 'akasha' do ecosystem.json.

    Usada por serviços do AKASHA para ler configurações em runtime sem
    depender de import de config.py (que lê o ecosystem em import-time).
    Retorna {} silenciosamente se o arquivo não existir ou estiver corrompido.
    """
    return read_ecosystem().get("akasha", {})


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


# ---------------------------------------------------------------------------
# Histórico de comunicações IA → usuária
# ---------------------------------------------------------------------------

def _comm_history_path() -> Path | None:
    """Retorna {sync_root}/communication_history.db ou None se sync_root não configurado."""
    root = get_sync_root()
    return (root / "communication_history.db") if root is not None else None


def _comm_history_init(db_path: Path) -> None:
    """Garante que a tabela existe. Chamado antes de cada operação."""
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS communications (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                source_app      TEXT    NOT NULL,
                content         TEXT    NOT NULL,
                importance      INTEGER,
                tags            TEXT,
                sent_at         TEXT    NOT NULL,
                feedback        TEXT,
                feedback_at     TEXT,
                feedback_reason TEXT
            )
        """)
        conn.commit()


def log_communication(
    source_app: str,
    content: str,
    importance: int | None = None,
    tags: list[str] | None = None,
) -> int | None:
    """Registra uma comunicação IA → usuária em communication_history.db.

    Retorna o id gerado (para associar feedback posterior) ou None se
    sync_root não estiver configurado ou a escrita falhar.
    Falha silenciosamente — nunca bloqueia o fluxo do caller.
    """
    import datetime as _dt
    import json as _json
    import sqlite3

    path = _comm_history_path()
    if path is None:
        return None
    try:
        _comm_history_init(path)
        tags_str = _json.dumps(tags, ensure_ascii=False) if tags else None
        sent_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.execute(
                "INSERT INTO communications (source_app, content, importance, tags, sent_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_app, content, importance, tags_str, sent_at),
            )
            conn.commit()
            return cur.lastrowid
    except Exception:
        return None


def update_communication_feedback(
    comm_id: int,
    feedback: str,
    reason: str | None = None,
) -> None:
    """Atualiza o feedback (e opcionalmente o motivo) de uma comunicação registrada.

    feedback: "confirmed" | "dismissed"
    reason: texto livre ou tag rápida do motivo do ✗ (opcional).
    Falha silenciosamente.
    """
    import datetime as _dt
    import sqlite3

    path = _comm_history_path()
    if path is None:
        return
    try:
        feedback_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "UPDATE communications SET feedback=?, feedback_at=?, feedback_reason=? "
                "WHERE id=?",
                (feedback, feedback_at, reason, comm_id),
            )
            conn.commit()
    except Exception:
        pass
