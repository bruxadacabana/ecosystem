"""
Testes para Fase 5 — Deep Research integrado ao /chat.

DeepResearch 1 cobre:
  - _detect_deep_mode: gatilhos corretos ativam modo deep
  - _detect_deep_mode: perguntas curtas sem gatilhos → False
  - _detect_deep_mode: perguntas longas (>= 10 palavras) → True
  - ChatMessage aceita deep_mode: bool = False
  - _deepForced em chat.html → envia deep_mode:true
  - botão toggle existe no HTML

DeepResearch 2 cobre:
  - _merge_dedup_results: duplicatas por URL removidas
  - _merge_dedup_results: ordem preservada (primeiro encontrado vence)
  - _expand_queries_deep: LOGOS offline → lista vazia, sem exceção
  - _expand_queries_deep: resultado limitado a 5 reformulações
  - query original não aparece nas reformulações retornadas

DeepResearch 3 cobre:
  - _get_deep_max_docs: retorna default=8 sem config
  - _get_deep_max_docs: respeita configuração do ecosystem.json
  - _build_deep_corpus: retorna lista de dicts com campos obrigatórios
  - _build_deep_corpus: fallback para snippet quando conteúdo indisponível
  - _get_doc_full_content: URL desconhecida retorna fallback silenciosamente

DeepResearch 4 cobre:
  - _build_deep_prompt é async
  - _build_deep_prompt inclui corpus no system message
  - _build_deep_prompt inclui _DEEP_SYNTHESIS_VOICE
  - _DEEP_SYNTHESIS_VOICE tem instrução de síntese integrativa
  - _stream_chat aceita max_tokens e timeout como parâmetros
  - chat.html: loading indicator no início do deep stream
  - chat.html: label 'Pesquisa Profunda' quando mode='deep'
  - chat.html: modo normal não mostra label deep
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent))


@pytest.fixture(autouse=True)
def _patch_heavy(monkeypatch):
    fake_eco = types.ModuleType("ecosystem_client")
    fake_eco.get_inference_url = lambda: "http://127.0.0.1:7072"
    fake_eco.get_active_profile = lambda: {"models": {"llm_query": "test"}}
    fake_eco.get_ollama_headers = lambda app, p: {"X-App": app, "X-Priority": str(p)}
    fake_eco.get_akasha_config = lambda: {"deep_research_max_docs": 8}
    monkeypatch.setitem(sys.modules, "ecosystem_client", fake_eco)

    for mod in ("database", "config", "services.persona", "services.local_search",
                "services.crawler", "services.archiver", "services.affective_state"):
        monkeypatch.setitem(sys.modules, mod, types.ModuleType(mod))

    cfg = sys.modules["config"]
    cfg.PERSONALITY_PROMPT = "Você é a Akasha."
    yield


def run(coro):
    return asyncio.run(coro)


def _reimport_chat():
    if "routers.chat" in sys.modules:
        del sys.modules["routers.chat"]
    import routers.chat as chat_mod
    return chat_mod


# ---------------------------------------------------------------------------
# DeepResearch 1 — detecção heurística e schema
# ---------------------------------------------------------------------------

class TestDeepDetect:

    def test_trigger_word_activates_deep(self):
        """Pergunta com 'por que' ativa modo deep."""
        chat = _reimport_chat()
        assert chat._detect_deep_mode("por que os pássaros migram") is True

    def test_trigger_compare_activates(self):
        """'compare' ativa modo deep."""
        chat = _reimport_chat()
        assert chat._detect_deep_mode("compare rust e go") is True

    def test_trigger_como_funciona(self):
        """'como funciona' ativa modo deep."""
        chat = _reimport_chat()
        assert chat._detect_deep_mode("como funciona um transformador") is True

    def test_trigger_analise_de(self):
        """'análise de' ativa modo deep."""
        chat = _reimport_chat()
        assert chat._detect_deep_mode("análise de algoritmos de busca") is True

    def test_long_query_activates_deep(self):
        """Pergunta com >= 10 palavras ativa modo deep mesmo sem gatilho."""
        chat = _reimport_chat()
        # 10 palavras exatas, sem gatilhos
        query = "me diga algo sobre bancos de dados sql em geral"
        words = query.split()
        assert len(words) >= 10
        assert chat._detect_deep_mode(query) is True

    def test_short_query_no_trigger_is_normal(self):
        """Pergunta curta sem gatilho → modo normal."""
        chat = _reimport_chat()
        assert chat._detect_deep_mode("o que é rag") is False

    def test_greeting_is_normal(self):
        """Saudação simples → modo normal."""
        chat = _reimport_chat()
        assert chat._detect_deep_mode("olá") is False

    def test_chat_message_accepts_deep_mode(self):
        """ChatMessage aceita deep_mode=False por padrão."""
        chat = _reimport_chat()
        msg = chat.ChatMessage(message="Pergunta?")
        assert msg.deep_mode is False

    def test_chat_message_deep_mode_true(self):
        """ChatMessage aceita deep_mode=True."""
        chat = _reimport_chat()
        msg = chat.ChatMessage(message="Pergunta?", deep_mode=True)
        assert msg.deep_mode is True


# ---------------------------------------------------------------------------
# DeepResearch 2 — merge/dedup e query expansion
# ---------------------------------------------------------------------------

class TestMergeDedup:

    def test_removes_duplicate_urls(self):
        """URLs duplicadas são removidas."""
        chat = _reimport_chat()

        class FakeResult:
            def __init__(self, url, title="T"):
                self.url = url
                self.title = title
                self.snippet = ""
                self.source = "TEST"

        lists = [
            [FakeResult("http://a.com"), FakeResult("http://b.com")],
            [FakeResult("http://a.com"), FakeResult("http://c.com")],  # a duplicado
        ]
        result = chat._merge_dedup_results(lists)
        urls = [r.url for r in result]
        assert urls.count("http://a.com") == 1, "URL duplicada deve aparecer apenas uma vez"
        assert set(urls) == {"http://a.com", "http://b.com", "http://c.com"}

    def test_preserves_first_occurrence_order(self):
        """Primeiro resultado encontrado tem prioridade sobre duplicatas."""
        chat = _reimport_chat()

        class FakeResult:
            def __init__(self, url, title):
                self.url = url
                self.title = title
                self.snippet = ""
                self.source = "TEST"

        lists = [
            [FakeResult("http://a.com", "Primeira"), FakeResult("http://b.com", "B")],
            [FakeResult("http://a.com", "Segunda"), FakeResult("http://c.com", "C")],
        ]
        result = chat._merge_dedup_results(lists)
        a_item = next(r for r in result if r.url == "http://a.com")
        assert a_item.title == "Primeira", "Título da primeira ocorrência deve ser preservado"

    def test_empty_lists(self):
        """Listas vazias retornam lista vazia."""
        chat = _reimport_chat()
        assert chat._merge_dedup_results([[], []]) == []


class TestExpandQueriesDeep:

    def test_logos_offline_returns_empty(self):
        """LOGOS offline → lista vazia, sem exceção."""
        chat = _reimport_chat()

        async def _fake_post(*a, **kw):
            raise Exception("connection refused")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(side_effect=Exception("offline"))
            mock_cls.return_value = mock_instance

            result = run(chat._expand_queries_deep("pergunta?", "model"))

        assert result == [], "LOGOS offline deve retornar lista vazia"

    def test_no_exception_on_failure(self):
        """_expand_queries_deep nunca propaga exceção."""
        chat = _reimport_chat()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(side_effect=RuntimeError("falha"))
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_instance

            try:
                result = run(chat._expand_queries_deep("pergunta?", "model"))
                assert isinstance(result, list)
            except Exception as exc:
                pytest.fail(f"_expand_queries_deep propagou exceção: {exc}")

    def test_result_capped_at_5(self):
        """Retorna no máximo 5 reformulações."""
        chat = _reimport_chat()

        mock_response = MagicMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "\n".join([
                f"Reformulação {i}" for i in range(10)
            ])}}]
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_instance

            result = run(chat._expand_queries_deep("pergunta original?", "model"))

        assert len(result) <= 5, f"Máximo de 5 reformulações, obteve {len(result)}"

    def test_original_query_not_in_result(self):
        """A query original não deve aparecer nas reformulações."""
        chat = _reimport_chat()
        original = "Como funciona o RAG?"

        mock_response = MagicMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": (
                "Como funciona o RAG?\n"  # duplicata da original
                "De que modo o RAG opera?\n"
                "Qual o mecanismo do RAG?\n"
            )}}]
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_instance

            result = run(chat._expand_queries_deep(original, "model"))

        assert original not in result, "Query original não deve estar nas reformulações"
        assert all(r.lower() != original.lower() for r in result), (
            "Variantes case-insensitive da query original também devem ser removidas"
        )


# ---------------------------------------------------------------------------
# DeepResearch 3 — config e corpus
# ---------------------------------------------------------------------------

class TestGetDeepMaxDocs:

    def test_default_is_8(self):
        """Sem config, retorna 8."""
        chat = _reimport_chat()
        result = chat._get_deep_max_docs()
        assert result == 8

    def test_reads_from_ecosystem(self, monkeypatch):
        """Lê valor do ecosystem.json."""
        chat = _reimport_chat()
        fake_eco = sys.modules.get("ecosystem_client")
        if fake_eco:
            monkeypatch.setattr(fake_eco, "get_akasha_config", lambda: {"deep_research_max_docs": 12})
        result = chat._get_deep_max_docs()
        assert result == 12

    def test_clamps_to_valid_range(self, monkeypatch):
        """Valores fora do range [1, 20] são clamped."""
        chat = _reimport_chat()
        fake_eco = sys.modules.get("ecosystem_client")
        if fake_eco:
            monkeypatch.setattr(fake_eco, "get_akasha_config", lambda: {"deep_research_max_docs": 999})
        result = chat._get_deep_max_docs()
        assert 1 <= result <= 20


class TestGetDocFullContent:

    def test_unknown_scheme_returns_fallback(self):
        """URL com scheme desconhecido retorna fallback."""
        chat = _reimport_chat()
        result = run(chat._get_doc_full_content("ftp://unknown.com", fallback="meu_snippet"))
        assert result == "meu_snippet"

    def test_http_url_not_found_returns_fallback(self):
        """URL http não encontrada no DB e fetch falhando retorna fallback."""
        chat = _reimport_chat()

        # Mocka config.DB_PATH para evitar erro de import
        import types as _types
        fake_config = sys.modules.get("config") or _types.ModuleType("config")
        fake_config.DB_PATH = ":memory:"
        sys.modules["config"] = fake_config

        result = run(chat._get_doc_full_content("http://notfound.xyz/page", fallback="snippet"))
        assert result == "snippet"


class TestBuildDeepCorpus:

    def test_returns_list_of_dicts(self):
        """_build_deep_corpus retorna lista de dicts."""
        chat = _reimport_chat()

        class FakeResult:
            def __init__(self, url, title="T", snippet="S"):
                self.url = url
                self.title = title
                self.snippet = snippet

        # Mock _get_doc_full_content para retornar snippet
        async def fake_get_content(url, fallback=""):
            return fallback

        with patch.object(chat, "_get_doc_full_content", fake_get_content):
            results = [FakeResult(f"file:///doc{i}.md", f"Doc {i}", f"Snippet {i}") for i in range(3)]
            corpus = run(chat._build_deep_corpus(results, max_docs=3))

        assert len(corpus) == 3
        for item in corpus:
            assert "num" in item
            assert "title" in item
            assert "url" in item
            assert "content" in item
            assert "is_full" in item
            assert "word_count" in item

    def test_respects_max_docs(self):
        """Nunca processa mais de max_docs resultados."""
        chat = _reimport_chat()

        class FakeResult:
            def __init__(self, url):
                self.url = url
                self.title = "T"
                self.snippet = "S"

        async def fake_get_content(url, fallback=""):
            return fallback

        with patch.object(chat, "_get_doc_full_content", fake_get_content):
            results = [FakeResult(f"file:///doc{i}.md") for i in range(10)]
            corpus = run(chat._build_deep_corpus(results, max_docs=3))

        assert len(corpus) == 3, "Deve respeitar max_docs=3"

    def test_uses_snippet_when_content_unavailable(self):
        """Quando conteúdo não disponível, usa snippet como fallback."""
        chat = _reimport_chat()

        class FakeResult:
            def __init__(self):
                self.url = "http://unknown.xyz"
                self.title = "Test"
                self.snippet = "este é o snippet"

        async def fake_get_content(url, fallback=""):
            return fallback  # retorna o snippet como fallback

        with patch.object(chat, "_get_doc_full_content", fake_get_content):
            corpus = run(chat._build_deep_corpus([FakeResult()], max_docs=1))

        assert corpus[0]["content"] == "este é o snippet"


# ---------------------------------------------------------------------------
# DeepResearch 4 — prompt e stream
# ---------------------------------------------------------------------------

class TestBuildDeepPrompt:

    def test_is_async(self):
        """_build_deep_prompt deve ser async."""
        import inspect
        src = (_ROOT / "routers" / "chat.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            if "_build_deep_prompt" in line and "def " in line:
                assert "async def" in line
                break

    def test_includes_deep_synthesis_voice(self):
        """System message deve incluir _DEEP_SYNTHESIS_VOICE."""
        chat = _reimport_chat()
        fake_aff = types.ModuleType("services.affective_state")
        fake_aff.get_current_state = AsyncMock(return_value={})
        fake_aff.get_emotional_framing = lambda s: ""

        corpus = [{"num": 1, "title": "Doc A", "url": "http://a.com", "content": "Conteúdo A"}]
        with patch.dict(sys.modules, {"services.affective_state": fake_aff}):
            msgs = run(chat._build_deep_prompt("Pergunta?", corpus, ""))

        system = msgs[0]["content"]
        assert "síntese" in system.lower() or "sintetize" in system.lower() or "corpus" in system.lower(), (
            "Deep prompt deve incluir instrução de síntese integrativa"
        )

    def test_includes_corpus_in_system(self):
        """System message inclui conteúdo dos corpus_items."""
        chat = _reimport_chat()
        fake_aff = types.ModuleType("services.affective_state")
        fake_aff.get_current_state = AsyncMock(return_value={})
        fake_aff.get_emotional_framing = lambda s: ""

        corpus = [{"num": 1, "title": "Artigo sobre IA", "url": "http://a.com", "content": "IA é fascinante"}]
        with patch.dict(sys.modules, {"services.affective_state": fake_aff}):
            msgs = run(chat._build_deep_prompt("O que é IA?", corpus, ""))

        system = msgs[0]["content"]
        assert "Artigo sobre IA" in system, "Título do corpus deve estar no system message"
        assert "IA é fascinante" in system, "Conteúdo do corpus deve estar no system message"

    def test_includes_question_as_user_message(self):
        """Última mensagem é a pergunta do usuário."""
        chat = _reimport_chat()
        fake_aff = types.ModuleType("services.affective_state")
        fake_aff.get_current_state = AsyncMock(return_value={})
        fake_aff.get_emotional_framing = lambda s: ""

        with patch.dict(sys.modules, {"services.affective_state": fake_aff}):
            msgs = run(chat._build_deep_prompt("Qual o sentido da vida?", [], ""))

        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "Qual o sentido da vida?"

    def test_empty_corpus_says_not_found(self):
        """Sem corpus, system message informa que não encontrou fontes."""
        chat = _reimport_chat()
        fake_aff = types.ModuleType("services.affective_state")
        fake_aff.get_current_state = AsyncMock(return_value={})
        fake_aff.get_emotional_framing = lambda s: ""

        with patch.dict(sys.modules, {"services.affective_state": fake_aff}):
            msgs = run(chat._build_deep_prompt("Pergunta?", [], ""))

        system = msgs[0]["content"]
        assert "nenhuma fonte" in system.lower() or "não encontrada" in system.lower()


class TestStreamChatSignature:

    def test_stream_chat_accepts_max_tokens(self):
        """_stream_chat aceita parâmetro max_tokens."""
        import inspect
        src = (_ROOT / "routers" / "chat.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            if "_stream_chat" in line and "def " in line and "async" in line:
                assert "max_tokens" in src.split(line)[1][:300] or "max_tokens" in line
                break

    def test_stream_chat_accepts_timeout(self):
        """_stream_chat aceita parâmetro timeout."""
        src = (_ROOT / "routers" / "chat.py").read_text(encoding="utf-8")
        assert "timeout: float" in src or "timeout=" in src


# ---------------------------------------------------------------------------
# DeepResearch 1-4 — estrutura HTML
# ---------------------------------------------------------------------------

class TestChatHtmlStructure:

    def test_deep_button_exists(self):
        """chat.html deve ter botão de Deep Research."""
        src = (_ROOT / "templates" / "chat.html").read_text(encoding="utf-8")
        assert "deep-btn" in src, "Deve ter elemento com id='deep-btn'"

    def test_toggle_deep_function_exists(self):
        """chat.html deve ter função toggleDeep()."""
        src = (_ROOT / "templates" / "chat.html").read_text(encoding="utf-8")
        assert "toggleDeep" in src, "Deve ter função toggleDeep() no JS"

    def test_deep_forced_variable(self):
        """chat.html deve ter variável _deepForced para o estado do toggle."""
        src = (_ROOT / "templates" / "chat.html").read_text(encoding="utf-8")
        assert "_deepForced" in src

    def test_deep_indicator_element(self):
        """chat.html deve ter indicador visual de modo deep ativo."""
        src = (_ROOT / "templates" / "chat.html").read_text(encoding="utf-8")
        assert "deep-indicator" in src or "Pesquisa Profunda" in src

    def test_deep_mode_sent_in_request(self):
        """sendMessage deve enviar deep_mode no corpo do request."""
        src = (_ROOT / "templates" / "chat.html").read_text(encoding="utf-8")
        assert "deep_mode" in src, "Request body deve incluir deep_mode"

    def test_loading_event_handled(self):
        """chat.html deve lidar com tipo 'loading' do SSE."""
        src = (_ROOT / "templates" / "chat.html").read_text(encoding="utf-8")
        assert "ev.type === 'loading'" in src or "type === 'loading'" in src, (
            "Front-end deve lidar com evento 'loading' para Deep Research"
        )

    def test_deep_mode_label_shown_in_response(self):
        """Quando mode='deep', label visual deve ser adicionado."""
        src = (_ROOT / "templates" / "chat.html").read_text(encoding="utf-8")
        assert "mode === 'deep'" in src or "ev.mode" in src, (
            "chat.html deve verificar ev.mode === 'deep' para mostrar label"
        )

    def test_deep_synthesis_voice_in_chat_py(self):
        """_DEEP_SYNTHESIS_VOICE deve estar definido em chat.py."""
        src = (_ROOT / "routers" / "chat.py").read_text(encoding="utf-8")
        assert "_DEEP_SYNTHESIS_VOICE" in src
        assert "síntese" in src.lower() or "sintetize" in src.lower()
