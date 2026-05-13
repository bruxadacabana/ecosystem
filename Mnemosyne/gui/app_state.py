"""
Estado compartilhado entre painéis do Mnemosyne.

O AppState é um QObject com signals tipados que funciona como bus de eventos
entre os painéis do layout tri-pane. Cada painel recebe uma referência ao
AppState na construção e conecta apenas os signals relevantes para si —
nunca se referencia diretamente entre painéis. Isso elimina acoplamento
bidirecional que quebraria ao refatorar o layout.

Padrão documentado no JabRef (https://devdocs.jabref.org/contributing):
"StateManager is passed to all GUI components at construction time."
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AppState(QObject):
    """Bus de eventos tipados entre os painéis do Mnemosyne."""

    # Usuária selecionou um documento no painel de fontes
    source_selected = Signal(str, str)          # (collection_id, doc_id)

    # Chat retornou uma resposta com citação — rolar o painel de fontes
    # até o trecho exato (start_char..end_char) no arquivo doc_path
    chunk_cited = Signal(str, str, int, int)    # (collection_id, doc_path, start_char, end_char)

    # Usuária clicou "Salvar como Nota" numa resposta do chat
    note_promoted = Signal(str, list)           # (text, citations: list[dict])

    # Usuária submeteu uma query no campo de chat
    query_submitted = Signal(str)               # (text,)

    # Token parcial recebido do LLM (streaming)
    response_token_received = Signal(str)       # (token,)
