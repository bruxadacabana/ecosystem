"""
Smoke tests para core/ollama_client.py após migração Ollama → llama-server.

Cobre:
  - check_inference() retorna bool (sem exceção)
  - check_ollama() é alias de check_inference()
  - list_models() parseia resposta /v1/models corretamente
  - filter_embed_models() e filter_chat_models() funcionam com nova estrutura
  - validate_model() levanta ModelNotFoundError para modelo ausente
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import Mnemosyne.core.ollama_client as oc


# ---------------------------------------------------------------------------
# check_inference / check_ollama
# ---------------------------------------------------------------------------

class TestCheckInference:
    def test_returns_true_when_backend_responds(self):
        with patch.object(oc, "_base_url", return_value="http://localhost:8080"):
            with patch("Mnemosyne.core.ollama_client.urllib.request.urlopen"):
                assert oc.check_inference() is True

    def test_returns_false_when_backend_offline(self):
        import urllib.error
        with patch.object(oc, "_base_url", return_value="http://localhost:8080"):
            with patch("Mnemosyne.core.ollama_client.urllib.request.urlopen",
                       side_effect=urllib.error.URLError("offline")):
                assert oc.check_inference() is False

    def test_check_ollama_is_alias(self):
        with patch.object(oc, "check_inference", return_value=True) as mock:
            result = oc.check_ollama()
        mock.assert_called_once()
        assert result is True


# ---------------------------------------------------------------------------
# list_models — parser do formato /v1/models
# ---------------------------------------------------------------------------

class TestListModels:
    def _mock_response(self, model_ids: list[str]):
        body = json.dumps({"object": "list", "data": [{"id": mid} for mid in model_ids]}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_parses_v1_models_response(self):
        with patch("urllib.request.urlopen", return_value=self._mock_response(["qwen2.5:7b", "nomic-embed-text"])):
            models = oc.list_models()
        assert len(models) == 2
        names = [m.name for m in models]
        assert "qwen2.5:7b" in names
        assert "nomic-embed-text" in names

    def test_empty_data_returns_empty_list(self):
        body = json.dumps({"data": []}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            models = oc.list_models()
        assert models == []

    def test_raises_when_backend_offline(self):
        import urllib.error
        from Mnemosyne.core.errors import OllamaUnavailableError
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("conn refused")):
            with pytest.raises(OllamaUnavailableError):
                oc.list_models()

    def test_model_name_maps_from_id_field(self):
        with patch("urllib.request.urlopen", return_value=self._mock_response(["smollm2:1.7b"])):
            models = oc.list_models()
        assert models[0].name == "smollm2:1.7b"

    def test_model_size_defaults_to_zero(self):
        with patch("urllib.request.urlopen", return_value=self._mock_response(["qwen2.5:7b"])):
            models = oc.list_models()
        assert models[0].size == 0


# ---------------------------------------------------------------------------
# filter_embed_models / filter_chat_models
# ---------------------------------------------------------------------------

class TestFilterModels:
    def _models(self, names: list[str]) -> list[oc.OllamaModel]:
        return [oc.OllamaModel(name=n) for n in names]

    def test_filter_embed_returns_embed_models(self):
        models = self._models(["nomic-embed-text", "qwen2.5:7b", "bge-m3"])
        embed = oc.filter_embed_models(models)
        names = [m.name for m in embed]
        assert "nomic-embed-text" in names
        assert "bge-m3" in names
        assert "qwen2.5:7b" not in names

    def test_filter_chat_excludes_embed_models(self):
        models = self._models(["nomic-embed-text", "qwen2.5:7b", "smollm2:1.7b"])
        chat = oc.filter_chat_models(models)
        names = [m.name for m in chat]
        assert "nomic-embed-text" not in names
        assert "qwen2.5:7b" in names
        assert "smollm2:1.7b" in names


# ---------------------------------------------------------------------------
# validate_model
# ---------------------------------------------------------------------------

class TestValidateModel:
    def _mock_list(self, names: list[str]):
        return [oc.OllamaModel(name=n) for n in names]

    def test_raises_model_not_found_when_absent(self):
        from Mnemosyne.core.errors import ModelNotFoundError
        with patch.object(oc, "list_models", return_value=self._mock_list(["qwen2.5:7b"])):
            with pytest.raises(ModelNotFoundError):
                oc.validate_model("smollm2:1.7b")

    def test_no_exception_when_model_present(self):
        with patch.object(oc, "list_models", return_value=self._mock_list(["smollm2:1.7b"])):
            oc.validate_model("smollm2:1.7b")  # não deve lançar
