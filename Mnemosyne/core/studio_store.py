"""
Mnemosyne — StudioStore: camada de persistência dos outputs do Studio.

Lê e escreve arquivos .md em {base_dir}/studio/. O `base_dir` é o
`mnemosyne_dir` da coleção (ex: {watched_dir}/.mnemosyne/) ou o diretório
do notebook (ex: {data_dir}/notebooks/{id}/).

O diretório studio/ é criado automaticamente se não existir.
"""
from __future__ import annotations

from pathlib import Path

from .errors import FrontmatterParseError
from .studio_output import StudioOutput


class StudioStore:
    """Gerencia outputs do Studio no sistema de arquivos."""

    def __init__(self, base_dir: str | Path) -> None:
        self._dir = Path(base_dir) / "studio"
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def save(self, output: StudioOutput) -> None:
        """Persiste output como arquivo .md.

        Raises:
            OSError: se não conseguir escrever o arquivo.
        """
        output.to_markdown_file(self._dir / f"{output.id}.md")

    def delete(self, output_id: str) -> None:
        """Remove o arquivo de um output.

        Raises:
            OSError: se o arquivo existir mas não puder ser removido.
        """
        path = self._dir / f"{output_id}.md"
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def load_all(self, collection_name: str = "") -> list[StudioOutput]:
        """Carrega todos os outputs, ordenados por created_at decrescente.

        Arquivos inválidos (corrompidos, frontmatter malformado) são
        ignorados individualmente — não interrompem o carregamento dos demais.

        Se collection_name for fornecido, filtra apenas outputs daquela coleção.
        """
        outputs: list[StudioOutput] = []
        for path in self._dir.glob("*.md"):
            try:
                output = StudioOutput.from_markdown_file(path)
            except (OSError, FrontmatterParseError, ValueError):
                continue
            if collection_name and output.collection_name != collection_name:
                continue
            outputs.append(output)
        return sorted(outputs, key=lambda o: o.created_at, reverse=True)

    def get(self, output_id: str) -> StudioOutput | None:
        """Retorna output por id, ou None se não existir ou estiver inválido."""
        path = self._dir / f"{output_id}.md"
        if not path.exists():
            return None
        try:
            return StudioOutput.from_markdown_file(path)
        except (OSError, FrontmatterParseError, ValueError):
            return None
