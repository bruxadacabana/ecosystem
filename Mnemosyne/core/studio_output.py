"""
Mnemosyne — StudioOutput: output persistente do Studio.

Cada output é salvo como arquivo .md com frontmatter YAML marcado com
`source: mnemosyne_studio`. O indexador reconhece esse marcador e atribui
`source_type = "thought"` ao documento — o RAG trata o conteúdo como
"pensamento" da própria Mnemosyne, com peso distinto de fontes externas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _build_frontmatter(meta: dict[str, str]) -> str:
    """Serializa dicionário de strings como bloco frontmatter YAML."""
    lines = ["---"]
    for k, v in meta.items():
        if not v:
            lines.append(f"{k}:")
        elif any(c in v for c in ':#{}[]|>&!%@,`"\'') or v != v.strip():
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extrai bloco frontmatter YAML e retorna (meta, body).

    Reconhece apenas valores de string simples — suficiente para os
    campos do StudioOutput (UUIDs, timestamps, nomes de coleção).

    Raises:
        FrontmatterParseError: se o bloco de abertura '---' não tiver fechamento.
    """
    from .errors import FrontmatterParseError

    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        raise FrontmatterParseError("Frontmatter sem marcador de fechamento '---'.")
    fm_text = text[4:end].strip()
    body = text[end + 4:].lstrip("\n")
    meta: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


@dataclass
class StudioOutput:
    """Output persistente gerado pelo Studio da Mnemosyne.

    Serializado como arquivo .md com frontmatter `source: mnemosyne_studio`.
    O campo `id` é um UUID4 que também serve de nome do arquivo.
    """

    type: str                           # Briefing | FAQ | Guide | Flashcards | ...
    content: str
    collection_name: str
    title: str = ""
    table_data: list[list[str]] | None = None
    created_at: str = field(default_factory=_now_iso)
    id: str = field(default_factory=lambda: str(uuid4()))
    notebook_id: str | None = None

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def to_markdown_file(self, path: Path | str) -> None:
        """Persiste o output como arquivo .md com frontmatter YAML.

        Raises:
            OSError: se não conseguir criar o diretório ou escrever o arquivo.
        """
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fm = _build_frontmatter({
            "source": "mnemosyne_studio",
            "type": "studio_output",
            "studio_type": self.type,
            "collection": self.collection_name,
            "created_at": self.created_at,
            "notebook_id": self.notebook_id or "",
        })
        title_line = f"# {self.title}\n\n" if self.title else ""
        dest.write_text(f"{fm}{title_line}{self.content}", encoding="utf-8")

    @classmethod
    def from_markdown_file(cls, path: Path | str) -> "StudioOutput":
        """Carrega um StudioOutput a partir de arquivo .md.

        O nome do arquivo (sem extensão) é usado como `id`.

        Raises:
            OSError: se o arquivo não puder ser lido.
            FrontmatterParseError: se o bloco frontmatter estiver malformado.
            ValueError: se o campo obrigatório `studio_type` estiver ausente.
        """
        src = Path(path)
        text = src.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)

        studio_type = meta.get("studio_type", "")
        if not studio_type:
            raise ValueError(f"Campo 'studio_type' ausente em: {src}")

        title = ""
        content = body.strip()
        if content.startswith("# "):
            first, _, rest = content.partition("\n")
            title = first[2:].strip()
            content = rest.strip()

        return cls(
            id=src.stem,
            type=studio_type,
            content=content,
            collection_name=meta.get("collection", ""),
            title=title,
            created_at=meta.get("created_at", ""),
            notebook_id=meta.get("notebook_id") or None,
        )
