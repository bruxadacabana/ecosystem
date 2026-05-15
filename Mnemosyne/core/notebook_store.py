"""
Mnemosyne — NotebookStore: camada de persistência de notebooks.

Cada notebook vive em {data_dir}/notebooks/{id}/ com os arquivos:
    metadata.json   — campos do Notebook serializado
    history.jsonl   — mensagens da conversa (append-only; gerenciado por fora)
    memory.json     — contexto RAG (gerenciado por fora)
    studio/         — outputs do Studio deste notebook (gerenciado por StudioStore)

NotebookStore não lê nem escreve history.jsonl nem memory.json — apenas
fornece os caminhos corretos via history_path() e memory_path(). O StudioStore
de um notebook é criado pelo chamador com studio_dir() como base.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from .errors import NotebookStoreError
from .notebook import Notebook


class NotebookStore:
    """Gerencia criação, listagem, carregamento, salvamento e exclusão de notebooks."""

    def __init__(self, data_dir: str | Path) -> None:
        self._root = Path(data_dir) / "notebooks"
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Helpers de caminhos
    # ------------------------------------------------------------------

    def _nb_dir(self, notebook_id: str) -> Path:
        return self._root / notebook_id

    def _meta_path(self, notebook_id: str) -> Path:
        return self._nb_dir(notebook_id) / "metadata.json"

    def studio_dir(self, notebook_id: str) -> Path:
        """Retorna (e cria) o diretório studio/ do notebook."""
        d = self._nb_dir(notebook_id) / "studio"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def history_path(self, notebook_id: str) -> Path:
        """Caminho para history.jsonl — gerenciado externamente."""
        return self._nb_dir(notebook_id) / "history.jsonl"

    def memory_path(self, notebook_id: str) -> Path:
        """Caminho para memory.json — gerenciado externamente."""
        return self._nb_dir(notebook_id) / "memory.json"

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        collection_names: list[str] | None = None,
        description: str = "",
    ) -> Notebook:
        """Cria novo notebook, persiste metadata.json e retorna o Notebook.

        Raises:
            NotebookStoreError: se não conseguir criar o diretório ou gravar o arquivo.
        """
        nb = Notebook.new(name, collection_names, description)
        nb_dir = self._nb_dir(nb.id)
        try:
            nb_dir.mkdir(parents=True, exist_ok=True)
            (nb_dir / "studio").mkdir(exist_ok=True)
        except OSError as exc:
            raise NotebookStoreError(f"Não foi possível criar diretório do notebook: {exc}") from exc
        self._write_meta(nb)
        return nb

    def save(self, notebook: Notebook) -> None:
        """Persiste notebook (atualiza updated_at).

        Raises:
            NotebookStoreError: se não conseguir gravar o arquivo.
        """
        notebook.updated_at = datetime.now().isoformat(timespec="seconds")
        self._write_meta(notebook)

    def load(self, notebook_id: str) -> Notebook:
        """Carrega notebook pelo id.

        Raises:
            NotebookStoreError: se o notebook não existir ou metadata.json for inválido.
        """
        path = self._meta_path(notebook_id)
        if not path.exists():
            raise NotebookStoreError(f"Notebook '{notebook_id}' não encontrado.")
        try:
            with path.open(encoding="utf-8") as f:
                return Notebook.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError) as exc:
            raise NotebookStoreError(
                f"metadata.json inválido para '{notebook_id}': {exc}"
            ) from exc

    def list_all(self) -> list[Notebook]:
        """Lista todos os notebooks, ordenados por updated_at decrescente.

        Arquivos corrompidos são silenciosamente ignorados para não travar a UI.
        """
        notebooks: list[Notebook] = []
        for meta_path in self._root.glob("*/metadata.json"):
            try:
                with meta_path.open(encoding="utf-8") as f:
                    notebooks.append(Notebook.from_dict(json.load(f)))
            except Exception:
                continue
        return sorted(notebooks, key=lambda n: n.updated_at, reverse=True)

    def delete(self, notebook_id: str) -> None:
        """Remove o diretório completo do notebook.

        Raises:
            NotebookStoreError: se o diretório existir mas não puder ser removido.
        """
        nb_dir = self._nb_dir(notebook_id)
        if not nb_dir.exists():
            return
        try:
            shutil.rmtree(nb_dir)
        except OSError as exc:
            raise NotebookStoreError(
                f"Não foi possível apagar notebook '{notebook_id}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _write_meta(self, notebook: Notebook) -> None:
        path = self._meta_path(notebook.id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(notebook.to_dict(), f, indent=2, ensure_ascii=False)
            tmp.replace(path)
        except OSError as exc:
            raise NotebookStoreError(f"Erro ao gravar metadata.json: {exc}") from exc
