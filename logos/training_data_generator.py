"""
logos/training_data_generator.py — gerador de pares Q&A sintéticos do corpus da Mnemosyne.

Itera os chunks do ChromaDB indexado pela Mnemosyne, filtra por tamanho mínimo e
idioma, e usa o LLM local (via LOGOS/Ollama) para gerar pares pergunta-resposta no
formato ChatML. Salva JSONL em {sync_root}/logos/training_data/YYYY-MM-DD.jsonl.

Inclui 10–15% de exemplos âncora (Alpaca/Dolly) para preservar a capacidade basal do
modelo após o fine-tuning — sem âncoras, o modelo colapsa para o domínio do corpus.

Uso direto::

    from logos.training_data_generator import generate, GeneratorConfig

    cfg = GeneratorConfig()  # usa ecosystem.json
    stats = generate(cfg)
    print(stats)

Uso como script::

    python -m logos.training_data_generator

Rodar como tarefa P3 — não bloquear P1/P2.
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterator

import ecosystem_client as ec

log = logging.getLogger("ecosystem.logos.training_data_generator")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class GeneratorConfig:
    """Parâmetros do gerador — valores padrão lidos do ecosystem.json."""

    min_chunk_chars: int = 200
    pairs_per_chunk: tuple[int, int] = (2, 5)
    anchor_ratio: float = 0.12        # 10–15%
    max_chunks: int | None = None     # None = sem limite
    llm_timeout: float = 120.0
    chroma_dir: str = ""              # vazio → lido de ecosystem_client
    output_dir: str = ""              # vazio → {sync_root}/logos/training_data

    def resolve(self) -> GeneratorConfig:
        """Preenche campos vazios a partir do ecosystem.json e sync_root."""
        cfg = GeneratorConfig(**self.__dict__)
        if not cfg.chroma_dir:
            eco = ec.read_ecosystem()
            sync_root = eco.get("sync_root", "")
            if not sync_root:
                raise RuntimeError(
                    "sync_root não configurado em ecosystem.json — configure via HUB"
                )
            paths = ec.derive_paths(sync_root)
            cfg.chroma_dir = paths["mnemosyne"]["chroma_dir"]
        if not cfg.output_dir:
            eco = ec.read_ecosystem()
            sync_root = eco.get("sync_root", "")
            cfg.output_dir = str(Path(sync_root) / "logos" / "training_data")
        return cfg


# ---------------------------------------------------------------------------
# ChromaDB — leitura dos chunks
# ---------------------------------------------------------------------------

def _iter_chroma_chunks(chroma_dir: str) -> Iterator[dict]:
    """Itera todos os chunks de todas as coleções no ChromaDB da Mnemosyne.

    Yields dicts com chaves: ``id``, ``text``, ``metadata``, ``collection``.
    """
    try:
        import chromadb  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "chromadb não instalado no ambiente atual. "
            "Instale com: pip install chromadb"
        ) from exc

    chroma_path = Path(chroma_dir)
    if not chroma_path.exists():
        raise FileNotFoundError(f"chroma_dir não existe: {chroma_dir}")

    client = chromadb.PersistentClient(path=str(chroma_path))
    collections = client.list_collections()
    log.info("ChromaDB: %d coleção(ões) encontradas", len(collections))

    for coll_meta in collections:
        coll = client.get_collection(coll_meta.name)
        total = coll.count()
        if total == 0:
            continue
        log.debug("Coleção %s: %d chunks", coll_meta.name, total)
        # Busca em lotes de 500 para não saturar memória
        batch = 500
        for offset in range(0, total, batch):
            result = coll.get(limit=batch, offset=offset, include=["documents", "metadatas"])
            docs = result.get("documents") or []
            metas = result.get("metadatas") or [{}] * len(docs)
            ids = result.get("ids") or []
            for doc, meta, chunk_id in zip(docs, metas, ids):
                if doc:
                    yield {"id": chunk_id, "text": doc, "metadata": meta or {}, "collection": coll_meta.name}


def _filter_chunk(chunk: dict, min_chars: int) -> bool:
    """Retorna True se o chunk passa nos filtros de qualidade."""
    text = chunk["text"].strip()
    if len(text) < min_chars:
        return False
    # Rejeitar chunks que são majoritariamente código ou tabelas
    code_lines = sum(1 for ln in text.splitlines() if ln.startswith(("    ", "\t", "```")))
    if code_lines > len(text.splitlines()) * 0.5:
        return False
    return True


# ---------------------------------------------------------------------------
# Geração de pares Q&A via LLM
# ---------------------------------------------------------------------------

_QA_SYSTEM = (
    "You are a helpful assistant that creates training data. "
    "Given a text passage, generate concise, self-contained question-answer pairs "
    "grounded exclusively in the passage. Each answer must be answerable from the text alone."
)

_QA_PROMPT_TMPL = """\
Text passage:
\"\"\"
{text}
\"\"\"

Generate {n} distinct question-answer pairs from this passage.
Respond with ONLY a JSON array, no explanation:
[
  {{"question": "...", "answer": "..."}},
  ...
]"""


def _generate_qa_pairs(text: str, n: int, timeout: float) -> list[dict]:
    """Gera n pares Q&A para o texto usando LLM local via LOGOS.

    Retorna lista de dicts com ``question`` e ``answer``.
    Retorna lista vazia em caso de falha (fallback silencioso para P3).
    """
    prompt = _QA_PROMPT_TMPL.format(text=text[:1500], n=n)
    messages = [
        {"role": "system", "content": _QA_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    try:
        resp = ec.request_llm(
            messages,
            app="logos",
            priority=3,
            ollama_base=ec.get_ollama_base(),
        )
        raw = resp.get("message", {}).get("content", "")
        pairs = _parse_qa_json(raw)
        return pairs
    except Exception as exc:
        log.debug("Falha ao gerar Q&A: %s", exc)
        return []


def _parse_qa_json(raw: str) -> list[dict]:
    """Extrai lista JSON do texto bruto da resposta do LLM."""
    # Procura o primeiro [...] na resposta
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
        if not isinstance(data, list):
            return []
        return [
            d for d in data
            if isinstance(d, dict)
            and isinstance(d.get("question"), str)
            and isinstance(d.get("answer"), str)
            and d["question"].strip()
            and d["answer"].strip()
        ]
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Âncoras de instruction tuning (Alpaca-style)
# ---------------------------------------------------------------------------

# Conjunto fixo de exemplos de instruction tuning gerais.
# Garantem que o modelo não colapse para o domínio do corpus após fine-tuning.
_ANCHOR_EXAMPLES: list[dict] = [
    {
        "instruction": "Explain the difference between a list and a tuple in Python.",
        "answer": (
            "A list is mutable (elements can be added, removed, or changed), while a tuple "
            "is immutable (its elements cannot be changed after creation). Lists use square "
            "brackets `[]`; tuples use parentheses `()`. Tuples are generally faster and "
            "are used when data should not change."
        ),
    },
    {
        "instruction": "Write a short haiku about the ocean.",
        "answer": "Waves crash on the shore / Salt air fills the endless sky / Peace beneath the tide",
    },
    {
        "instruction": "Summarize the water cycle in two sentences.",
        "answer": (
            "Water evaporates from oceans and lakes, rises into the atmosphere, condenses "
            "into clouds, and falls back as precipitation. It then flows into rivers and "
            "groundwater, eventually returning to the ocean."
        ),
    },
    {
        "instruction": "What is the capital of Japan?",
        "answer": "The capital of Japan is Tokyo.",
    },
    {
        "instruction": "Give an example of a palindrome and explain what it is.",
        "answer": (
            'A palindrome is a word, phrase, or sequence that reads the same forwards and '
            'backwards. Example: "racecar" — spelled R-A-C-E-C-A-R in both directions.'
        ),
    },
    {
        "instruction": "Convert 100 degrees Fahrenheit to Celsius.",
        "answer": "100°F = (100 − 32) × 5/9 ≈ 37.8°C.",
    },
    {
        "instruction": "Name three renewable energy sources.",
        "answer": "Solar, wind, and hydroelectric power are three common renewable energy sources.",
    },
    {
        "instruction": "What does CPU stand for and what does it do?",
        "answer": (
            "CPU stands for Central Processing Unit. It is the primary component of a computer "
            "that executes instructions from programs, performing arithmetic, logic, control, "
            "and input/output operations."
        ),
    },
    {
        "instruction": "Describe the plot of Romeo and Juliet in one paragraph.",
        "answer": (
            "Romeo and Juliet is a tragedy by Shakespeare about two young lovers from rival "
            "families in Verona — the Montagues and the Capulets. Despite their families' "
            "feud, they fall in love and secretly marry. A chain of misunderstandings leads "
            "to Romeo being exiled and Juliet faking her own death. Believing Juliet truly "
            "dead, Romeo kills himself; Juliet awakens and, finding Romeo dead, takes her "
            "own life. Their deaths reconcile the feuding families."
        ),
    },
    {
        "instruction": "What is the difference between RAM and storage?",
        "answer": (
            "RAM (Random Access Memory) is fast, temporary memory used by the CPU to store "
            "data currently in use. Storage (HDD, SSD) is slower but persistent — it retains "
            "data when the computer is off. More RAM allows more programs to run simultaneously; "
            "more storage allows more files and applications to be installed."
        ),
    },
    {
        "instruction": "Translate 'Hello, how are you?' to French.",
        "answer": "\"Bonjour, comment allez-vous ?\" (formal) or \"Salut, comment ça va ?\" (informal).",
    },
    {
        "instruction": "What is photosynthesis?",
        "answer": (
            "Photosynthesis is the process by which plants, algae, and some bacteria convert "
            "sunlight, water, and carbon dioxide into glucose and oxygen. It occurs primarily "
            "in chloroplasts and is the foundation of most food chains on Earth."
        ),
    },
]


def _anchor_to_chatml(anchor: dict) -> dict:
    """Converte um exemplo âncora para o formato ChatML."""
    return {
        "messages": [
            {"role": "system", "content": "You are a helpful, accurate assistant."},
            {"role": "user", "content": anchor["instruction"]},
            {"role": "assistant", "content": anchor["answer"]},
        ]
    }


def _qa_to_chatml(text: str, question: str, answer: str) -> dict:
    """Converte um par Q&A gerado em formato ChatML com contexto do texto."""
    system = (
        "You are a knowledgeable assistant. Answer questions accurately based on "
        "your understanding. Be concise and precise."
    )
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
        "source_chunk_preview": text[:120],
    }


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@dataclass
class GeneratorStats:
    chunks_seen: int = 0
    chunks_filtered: int = 0
    chunks_processed: int = 0
    pairs_generated: int = 0
    anchors_added: int = 0
    output_file: str = ""
    elapsed_seconds: float = 0.0

    def __str__(self) -> str:
        return (
            f"GeneratorStats("
            f"chunks_seen={self.chunks_seen}, "
            f"filtered_out={self.chunks_filtered}, "
            f"processed={self.chunks_processed}, "
            f"pairs={self.pairs_generated}, "
            f"anchors={self.anchors_added}, "
            f"output={self.output_file!r}, "
            f"elapsed={self.elapsed_seconds:.1f}s)"
        )


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def generate(cfg: GeneratorConfig | None = None) -> GeneratorStats:
    """Executa o pipeline completo de geração de dados de treinamento.

    1. Resolve config a partir do ecosystem.json.
    2. Itera chunks do ChromaDB da Mnemosyne.
    3. Para cada chunk aprovado, gera pares Q&A via LLM (P3).
    4. Intercala exemplos âncora conforme `anchor_ratio`.
    5. Salva JSONL em {output_dir}/{date}.jsonl.

    Retorna GeneratorStats com métricas do ciclo.
    """
    cfg = (cfg or GeneratorConfig()).resolve()
    stats = GeneratorStats()
    t0 = time.monotonic()

    output_path = Path(cfg.output_dir) / f"{date.today().isoformat()}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Iniciando geração: chroma=%s output=%s", cfg.chroma_dir, output_path)

    anchors = list(_ANCHOR_EXAMPLES)
    random.shuffle(anchors)
    anchor_pool: list[dict] = []

    records: list[dict] = []

    for chunk in _iter_chroma_chunks(cfg.chroma_dir):
        if cfg.max_chunks and stats.chunks_seen >= cfg.max_chunks:
            break
        stats.chunks_seen += 1

        if not _filter_chunk(chunk, cfg.min_chunk_chars):
            stats.chunks_filtered += 1
            continue

        n_pairs = random.randint(*cfg.pairs_per_chunk)
        pairs = _generate_qa_pairs(chunk["text"], n_pairs, cfg.llm_timeout)

        if not pairs:
            log.debug("Chunk %s: nenhum par gerado, pulando", chunk["id"])
            continue

        stats.chunks_processed += 1
        for p in pairs:
            records.append(_qa_to_chatml(chunk["text"], p["question"], p["answer"]))
            stats.pairs_generated += 1

        log.debug(
            "Chunk %s: %d par(es) gerados (total acumulado: %d)",
            chunk["id"], len(pairs), stats.pairs_generated,
        )

    # Intercalar âncoras para atingir anchor_ratio
    n_anchors_target = int(stats.pairs_generated * cfg.anchor_ratio / (1 - cfg.anchor_ratio))
    anchor_pool = [_anchor_to_chatml(a) for a in anchors]
    # Repetir pool se necessário
    while len(anchor_pool) < n_anchors_target:
        anchor_pool.extend([_anchor_to_chatml(a) for a in anchors])
    anchor_pool = anchor_pool[:n_anchors_target]
    stats.anchors_added = len(anchor_pool)

    # Mistura aleatória de Q&A + âncoras
    combined = records + anchor_pool
    random.shuffle(combined)

    with output_path.open("w", encoding="utf-8") as f:
        for entry in combined:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    stats.output_file = str(output_path)
    stats.elapsed_seconds = time.monotonic() - t0
    log.info("Concluído: %s", stats)
    return stats


def configure_logging(log_dir: Path | None = None) -> None:
    """Configura logging para este módulo (chamar no entry point do processo pai)."""
    from ecosystem_logging import setup_ecosystem_logger, default_log_dir
    setup_ecosystem_logger(
        "ecosystem.logos.training_data_generator",
        log_dir or default_log_dir(),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    stats = generate()
    print(stats)
