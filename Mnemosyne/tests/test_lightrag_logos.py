"""
Testes da migração do LightRAG de Ollama → LOGOS (BUG-032).

O wrapper `core/lightrag_graph.py` precisava parar de usar `lightrag.llm.ollama`
(Ollama foi descartado no ecossistema) e passar a usar o binding OpenAI do
LightRAG apontando ao LOGOS (OpenAI-compatível em {base}/v1). Também precisa
chamar `initialize_storages()` (exigido pelo LightRAG 1.x).

Os testes stubam LightRAG e as funções OpenAI para verificar o cabeamento sem
depender de um LOGOS rodando.
"""

import asyncio
import sys
from pathlib import Path

import pytest

_MNEMOSYNE_ROOT = Path(__file__).parent.parent
if str(_MNEMOSYNE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNEMOSYNE_ROOT))

_LG_PY = _MNEMOSYNE_ROOT / "core" / "lightrag_graph.py"


class _FakeConfig:
    lightrag_enabled = True
    embed_model = "bge-m3"
    llm_model = "qwen2.5:7b"

    def __init__(self, persist_dir: str):
        self.persist_dir = persist_dir


@pytest.fixture
def lg_stubbed(monkeypatch, tmp_path):
    """Stuba LightRAG + funções OpenAI + get_inference_url; reseta os globais."""
    import core.lightrag_graph as lg

    monkeypatch.setattr(lg, "_rag_instance", None)
    monkeypatch.setattr(lg, "_init_attempted", False)

    captured: dict = {}

    class _StubLightRAG:
        def __init__(self, **kw):
            captured.update(kw)

        async def initialize_storages(self):
            captured["storages_initialized"] = True

    import lightrag
    monkeypatch.setattr(lightrag, "LightRAG", _StubLightRAG)

    calls: dict = {}

    async def _fake_complete(model, prompt, **kw):
        calls["complete_model"] = model
        calls["complete_base_url"] = kw.get("base_url")
        calls["complete_api_key"] = kw.get("api_key")
        return "ok"

    async def _fake_embed(texts, **kw):
        calls["embed_model"] = kw.get("model")
        calls["embed_base_url"] = kw.get("base_url")
        return [[0.0] * 4 for _ in texts]

    import lightrag.llm.openai as lopenai
    monkeypatch.setattr(lopenai, "openai_complete_if_cache", _fake_complete)
    monkeypatch.setattr(lopenai, "openai_embed", _fake_embed)

    import ecosystem_client
    monkeypatch.setattr(ecosystem_client, "get_inference_url",
                        lambda: "http://127.0.0.1:7072")

    return lg, captured, calls, str(tmp_path / "chroma")


class TestLightRAGUsaLOGOS:

    def test_init_constroi_e_inicializa_storages(self, lg_stubbed):
        lg, captured, _calls, persist = lg_stubbed
        ok = asyncio.run(lg.init_lightrag(_FakeConfig(persist)))
        assert ok is True
        assert "llm_model_func" in captured, "deve passar nosso wrapper de LLM"
        assert "embedding_func" in captured
        assert captured.get("storages_initialized") is True, (
            "initialize_storages() deve ser chamado (exigência do LightRAG 1.x)"
        )

    def test_llm_e_embed_roteiam_para_logos_v1(self, lg_stubbed):
        lg, captured, calls, persist = lg_stubbed
        asyncio.run(lg.init_lightrag(_FakeConfig(persist)))

        # Executa o wrapper de LLM e a função de embedding capturados
        asyncio.run(captured["llm_model_func"]("pergunta"))
        asyncio.run(captured["embedding_func"].func(["texto"]))

        assert calls["complete_base_url"] == "http://127.0.0.1:7072/v1", (
            "o LLM deve apontar para o LOGOS em /v1"
        )
        assert calls["embed_base_url"] == "http://127.0.0.1:7072/v1", (
            "o embedding deve apontar para o LOGOS em /v1"
        )
        assert calls["complete_model"] == "qwen2.5:7b"
        assert calls["embed_model"] == "bge-m3"

    def test_nenhuma_referencia_a_ollama_no_source(self):
        src = _LG_PY.read_text(encoding="utf-8")
        assert "lightrag.llm.ollama" not in src, "não deve mais importar o binding Ollama"
        assert "ollama_client" not in src, "não deve mais usar a URL do ollama_client"
        assert "ollama_model_complete" not in src
        assert "ollama_embed" not in src

    def test_usa_get_inference_url_e_openai_binding(self):
        src = _LG_PY.read_text(encoding="utf-8")
        assert "get_inference_url" in src, "deve resolver a URL via LOGOS"
        assert "lightrag.llm.openai" in src, "deve usar o binding OpenAI do LightRAG"
        assert "initialize_storages" in src
