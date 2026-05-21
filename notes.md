## Fila de implementação atual:

### KOSMOS — refazer do zero com nova stack | 2026-05-20

### Pesquisa: Contexto em Tempo Real — Extensão Firefox/Zen + Clipboard Monitor | 2026-05-18


## próximo: 

### Pesquisa: Detecção de Evento em Feeds — Clustering Temporal-Semântico de Artigos | 2026-05-14

### Redesign visual da Mnemosyne — "Bibliotecária Celeste" | 2026-05-19

### CODEX — Leitor centralizado do ecossistema | 2026-05-13

### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05


## Anotações

vamos retomar o que você tinha me mandado: 

"2. O que dispara o popup e o overlay, e como os sentimentos participam
Mnemosyne — cadeia completa até o popup

Quem gera os pensamentos:

Existem dois geradores de entradas type=surprise/connection na personal_memory da Mnemosyne:
A) IndexReflectionWorker (workers.py:1640) — cada vez que um documento é indexado na Mnemosyne, este worker pega chunks do ChromaDB, extrai keywords (dos metadados ou via TF-IDF), detecta overlap com known_terms da sessão, e pede ao LLM uma frase na voz da Mnemosyne + um score de importance 1-10. Se overlap ≥ 2 tópicos → type="connection"; senão → type="surprise". Ao terminar, emite .finished que aciona InsightScheduler.maybe_show(). 
B) insights.py — pensamentos que chegam da AKASHA (via badge check periódico no main_window) são salvos como type="connection" com tags ["from_akasha"]. Mas esses são exibidos pelo caminho de badge com memory_id negativo — não passam por get_unshown_popup_entries().

Onde os sentimentos entram:

Na seleção (hora de mostrar): get_unshown_popup_entries() aplica o scoring B1+B2: (arousal_da_entrada × importance/10) × Ebbinghaus_R × (1 − 0.3 × H_penalty). O arousal aqui é o que foi armazenado na entrada quando foi criada, calculado pelo appraisal da indexação. Importance 1-10 vem do LLM. Ebbinghaus decai com tempo e aumenta com exibições anteriores. H_penalty penaliza entradas com evidências conflitantes.
No timing (arousal atual do agente): InsightScheduler.maybe_show() lê affective_state.get_current_state() — se o arousal episódico do agente naquele momento está > 0.6, o popup é adiado. Esse arousal acumulado vem dos eventos de appraisal.
Diversidade K: 5% de chance de mostrar o insight de menor saliência quando câmara de eco detectada.
O IndexReflectionWorker NÃO usa o estado VA para modular o prompt — a Mnemosyne gera a frase com o mesmo tom independente de como está se sentindo. Isso é diferente da AKASHA.


AKASHA — cadeia completa até o overlay
Quem gera os pensamentos:

A) knowledge_worker._event_reflection() — cada vez que a AKASHA indexa uma página ou paper, computa overlap dos tópicos com o top-15 de tópicos conhecidos (connection vs surprise), inclui as 2 últimas memórias confirmadas como "o que já notei antes", e chama o LLM para gerar um pensamento. Aqui o VA é usado para modular o texto gerado: valence > 0.5 → exploratório/especulativo; valence < -0.3 → analítico/crítico; arousal > 0.7 → linguagem cuidadosa com qualificações ([G]).

B) friendship_receiver — pensamentos confirmados da Mnemosyne chegam e são salvos como type="connection".

Appraisal automático durante indexação:

Antes de gerar o pensamento, _record_doc_appraisal() calcula novelty (1 - familiarity dos tópicos), pleasantness (familiarity), coping_potential (% tópicos já conhecidos), goal_relevance (overlap com queries recentes) e persiste no estado afetivo. Isso alimenta o VA que vai modular o próximo documento indexado.

Onde os sentimentos entram no overlay:

No scoring: igual ao da Mnemosyne — arousal_da_entrada × importance/10 × Ebbinghaus × H_penalty
No timing: diferente da Mnemosyne, GET /insight/current não verifica o arousal atual do agente antes de responder — mostra sempre. Essa é uma lacuna em relação ao comportamento da Mnemosyne.
No feedback: quando você confirma (✓) no overlay, knowledge_worker.on_feedback_confirmed() dispara appraisal de goal_congruence positivo + salva episódio + atualiza topic_interest_profile. Dismissed dispara penalidade nos scores + appraisal de goal_congruence negativo.
O que faz uma IA mandar algo para a outra:
Mnemosyne → AKASHA: você confirma (✓) um popup → InsightScheduler.on_confirmed() → notify_akasha_insight() com emotional_context (valence, arousal, epistemic_curiosity, appraisal_source="mnemosyne_confirmed"). A AKASHA recebe via friendship_receiver (poll de 5 min no ecosystem.json), aplica blend emocional 30/70, e salva na personal_memory da AKASHA como type="connection".

AKASHA → Mnemosyne: o knowledge_worker detecta sobreposição de tópicos indexados com o topic_interest_profile e chama notify_mnemosyne_insight() — que escreve no ecosystem.json. A Mnemosyne verifica isso periodicamente via badge check no main_window; quando há novo insight, exibe popup com memory_id negativo.

3. O problema com maybe_schedule no TODO de POST /context/push
Escrevi no TODO: "chamar InsightScheduler.maybe_schedule(context)". Isso está errado por duas razões:

Razão 1 — objeto errado: InsightScheduler é a classe da Mnemosyne (core/insight_scheduler.py). Ela não tem um método maybe_schedule() — tem maybe_show() (sem argumentos, vai ao DB sozinha). O que existe no AKASHA é uma função de módulo em services/session_insight.py chamada maybe_schedule(session_id, queries, snippets).

Razão 2 — interface errada: a assinatura real é maybe_schedule(session_id: str, queries: list[str], snippets: list[str]) e exige ≥ 4 queries acumuladas na sessão para disparar. Uma URL empurrada via /context/push é uma página sendo lida — não é uma query de busca — então chamar maybe_schedule() com ela como se fosse query não faz sentido semanticamente, e não satisfaria o threshold de 4.

O que realmente precisa ser feito quando a URL chega no /context/push: ou criar uma função separada no session_insight.py específica para contexto de leitura (ex: maybe_schedule_from_url(session_id, url, title, topics)), ou simplesmente não chamar maybe_schedule() no push — fazer apenas o appraisal + topic_interest_profile e deixar o insight normal de sessão acontecer quando a usuária fizer buscas.

Quer que eu corrija o TODO de POST /context/push para refletir isso com precisão?"


## Regras


1: implemente um item de cada vez (implemente, marque feito no TODO, commite, resuma no chat (não precisa aprofundar muito, mas sempre explique o que foi implementado e o porquê de forma didática) e peça permissão antes de implementar o próximo). Cada item = 1 TODO (- [ ]).
2: sempre mantenha atualizado o GUIDE e o DESIGN BIBLE, inclusive listando TODAS as ferramentas e bibliotecas necessárias para o funcionamento do ecossistema. Sempre com o tom de tutor especialista em engenharia de software explicando para um programador iniciante, de forma didática e detalhada. Lembre-se que o GUIDE tem como objetivo guiar novos desenvolvedores que foram trabalhar no ecossistema.