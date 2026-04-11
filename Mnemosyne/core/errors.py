"""
Hierarquia de exceções tipadas do Mnemosyne.
"""
from __future__ import annotations


class MnemosyneError(Exception):
    """Base para todos os erros do Mnemosyne."""


class OllamaUnavailableError(MnemosyneError):
    """Ollama não está acessível no endereço configurado."""


class ModelNotFoundError(MnemosyneError):
    """Modelo solicitado não está instalado no Ollama."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        super().__init__(
            f"Modelo '{model_name}' não encontrado. "
            f"Instale-o com: ollama pull {model_name}"
        )


class DocumentLoadError(MnemosyneError):
    """Falha ao carregar um documento específico."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Não foi possível carregar '{path}': {reason}")


class UnsupportedFormatError(DocumentLoadError):
    """Formato de arquivo não suportado."""

    def __init__(self, path: str) -> None:
        ext = path.rsplit(".", 1)[-1] if "." in path else "sem extensão"
        super().__init__(path, f"formato .{ext} não suportado")


class IndexBuildError(MnemosyneError):
    """Falha durante a criação ou atualização do vectorstore."""


class EmptyDirectoryError(IndexBuildError):
    """Diretório não contém documentos suportados."""

    def __init__(self, directory: str) -> None:
        super().__init__(f"Nenhum documento suportado encontrado em: {directory}")


class VectorstoreNotFoundError(MnemosyneError):
    """Vectorstore não encontrado no caminho informado."""

    def __init__(self, persist_dir: str) -> None:
        super().__init__(f"Vectorstore não encontrado em: {persist_dir}")


class QueryError(MnemosyneError):
    """Falha ao executar uma consulta RAG."""


class SummarizationError(MnemosyneError):
    """Falha ao gerar resumo."""


class ConfigError(MnemosyneError):
    """Erro de configuração."""
