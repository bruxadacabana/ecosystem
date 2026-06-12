## Fila de implementação atual:

Estou no meio da implementação do item "ServerTarget::Kosmos no HUB (Rust)" da Fase 7 do KOSMOS (TODO.md ~linha 6851), seguindo a decisão da usuária de política "CPU-first, nunca evita" — o servidor KOSMOS (porta 8084, llm_analysis/gemma2:2b) carrega na GPU só se houver VRAM livre, senão roda em CPU, e nunca descarrega Akasha (8081)/Mnemosyne (8083) que ela usa ativamente. Todo o código em HUB/src-tauri/src/logos.rs já foi escrito e cargo check --tests passou limpo (só warnings pré-existentes de dead-code). O que falta é só rodar a suíte de testes do HUB para confirmar — eu não consegui porque saí da máquina. Rode cd HUB/src-tauri && cargo test --lib (no CachyOS/Linux, onde os testes que usam o comando sleep funcionam — no Windows eles falham por falta de sleep.exe). Se tudo passar: marque o item [x] no TODO.md, verifique/atualize README.md e GUIDE.md mencionando o novo servidor KOSMOS na porta 8084 (a seção de portas/LOGOS), e faça commit com git -C /caminho/do/ecosystem (estávamos com commits sendo feitos da raiz, não de dentro de subpastas). Resumo do que implementei em logos.rs: novo KOSMOS_SERVER_PORT = 8084; variante ServerTarget::Kosmos; route_request agora roteia "kosmos"→Kosmos (antes ia pra Akasha — atualizei o teste route_kosmos_returns_akasha→route_kosmos_returns_kosmos); novos campos no Inner (kosmos_semaphore, kosmos_proc, kosmos_disabled, kosmos_crash_count, last_kosmos_request_at, kosmos_health_port) preenchidos nos 3 construtores (produção, for_testing, e o make_test_state dos testes); helpers kill_kosmos_proc/kosmos_proc_active; todos os match target exaustivos atualizados; em ensure_server_loaded o KOSMOS pula o bloco de eviction (&& target != ServerTarget::Kosmos) e ganha CPU fallback (condição estendida + store do handle target-aware); do_silence, check_idle_kosmos + watchdog idle, e um crash watchdog próprio do KOSMOS espelhando o do Mnemosyne; collect_status + StatusResponse ganharam chat_kosmos_model/online/ms. Adicionei ~11 testes novos (bloco "Testes de kosmos_proc"): porta 8084, all_four_server_ports_are_distinct, roteamento, proc lifecycle, disabled flag, semáforo independente, e idle watchdog (kills/keeps/noop). Importante: nada foi commitado ainda — confira git status antes. Itens restantes da Fase 7 depois deste: "Testes: entidades, investigações, cobertura" (combinado). Não avance para outros itens sem ordem explícita da usuária — pare e aguarde após concluir este.

Não commitado / pendente

- Item do TODO segue desmarcado de propósito — falta rodar cargo test --lib no Linux para confirmar (testes de processo usam sleep, que não existe no Windows). cargo check --tests já passou limpo aqui.
- README/GUIDE ainda não atualizados com a porta 8084 — fica para depois da confirmação dos testes na outra máquina.
O parágrafo que te passei continua válido para a outra instância; só lembra que o commit 430a09e já existe, então lá é git pull/sincronizar antes de rodar os testes.

---

pode prosseguir para a implementação da seção '### KOSMOS v3 — Redesign como ferramenta para jornalistas/estudantes/ativistas | 2026-06-01', mas lembre-se sempre: um item por vez (um item = 1 - [ ]). Implemente, teste, marque no TODO, commite tudo, resuma o que foi feito e o porquê no chat, peça permissão para prosseguir. Seu resumo sempre deve ser detalhado mas acessível, explicando mais a lógica do que códigos e tecnicidades.
Não se esqueça das regras para documentar no README e GUIDE. Não se esqueça de executar testes (unitários e de integração) exaustivamente (tanto na implementação em si quanto nas funcionalidades ao redor e como funcionamah em conjunto) e incluir criação de logs em todo o processo envolvendo a nova feature implementada.

---

SearXNG tem suporte oficial apenas para Linux (incluindo Docker). No Windows, as opções são:

Docker Desktop — a forma mais simples: docker run -d -p 8888:8080 searxng/searxng
WSL2 — instalar via pip dentro do WSL2 como se fosse Linux
Não usar no Windows — a AKASHA pode usar o SearXNG do PC principal via IP local (se estiver na mesma rede)


key = 11c345dcaebdada6070a5545e7245f5ac91fa265d24324b8b57a5d6ae11c8609

---

> O valor real desse servidor pro ecossistema seria como nó sempre ligado: Syncthing disponível mesmo quando o CachyOS estiver desligado, AKASHA crawlando em background permanentemente, KOSMOS agregando feeds o dia todo. Coisas que hoje dependem do PC principal estar acordado.

---


## próximo: 

### AKASHA — Ferramenta sem IA, SearXNG primário+fallback, histórico sincronizado | 2026-06-08

### Prioridade de IA: análise da Mnemosyne (core, P2) acima do fundo da AKASHA (P3) | 2026-06-05

### HUB (LOGOS) — validar embed-server em CPU por padrão (BUG-028) | 2026-06-03

### HUB (LOGOS) — Encerramento completo dos processos llama-server (sem órfãos) | 2026-06-03

### HUB (LOGOS) — BUG-028: embed-server em loop de restart mata indexação do Mnemosyne | 2026-06-03

### AKASHA — Qualidade de busca SearXNG: remoção de Qwant e filtro anti-spam | 2026-06-01

### KOSMOS v3 — Redesign como ferramenta para jornalistas/estudantes/ativistas | 2026-06-01

## Auditoria de erros silenciosos — logs em todo caminho de erro (PLANEJADO — fazer depois) | 2026-06-03

### CODEX — Leitor centralizado do ecossistema | 2026-05-13

### Redesign visual da Mnemosyne — "Bibliotecária Celeste" | 2026-05-19

### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05


## Anotações

Journalist investigativo:

Tracking stories over time - same entities, organizations, topics appearing across multiple sources

Cross-referencing: when Source A and Source B both cover something, what do they agree/disagree on?

Detecting editorial gaps: what stories are being ignored?

Building a chronological narrative from fragmented coverage

Entity relationships: who is connected to whom, based on co-occurrence

Source credibility and bias analysis

Export and citation capabilities, investigation folders to organize active projects, keyword alerts for tracked entities, and the ability to compare how different outlets with varying political leanings cover the same story or identify what's conspicuously absent from certain feeds

Estudante:
For students, the focus shifts to comprehension and synthesis—aggregating multiple perspectives on complex topics, connecting news to academic knowledge, annotating articles directly, and exporting highlights with proper citations. They'd benefit from condensed summaries of lengthy pieces, generated study materials like event timelines and key actor lists, and statistical visualizations showing how coverage of a topic evolves over time, plus discovery of related articles to deepen understanding.

Ativista político:
Political activists need to track bias across sources, monitor specific actors and organizations, detect how narratives shift around particular stories, identify propaganda techniques like loaded language, see which stories gain traction versus get suppressed, compare how different countries frame the same event, connect news to legislative developments, and follow protest movements and organizing efforts.

Common to all three:
All three personas rely heavily on entity tracking and relationship mapping, chronological story progression, cross-source comparison, the ability to create curated collections for investigations or projects, exporting to structured formats, full-text search, and privacy-first local storage.

---

enquanto Mnemosyne é uma só, a ferramenta e a assistente são a mesma entidade, AKASHA tem uma diferenciação lógica (AKASHA (ferramenta) e a Akasha (assistente)) e é necessário que o AKASHA como ferramenta possa funcionar independemente da Akasha assistente. É por isso que os bancos de dados são separados inclusive, é por isso que devem funcionar em paralelo, com duas filas/processos ocorrendo ao mesmo tempo mas sem um pausar ou interromper o outro.

---

### Como as emoções são usadas no ecossistema
Tanto AKASHA quanto Mnemosyne têm um sistema afetivo completo funcionando agora. Aqui está o que acontece de verdade:

#### O que é gerado

Cada IA tem um estado afetivo bidimensional: valência (positivo/negativo, de −1 a +1) e arousal (ativação, de 0 a 1). Esse estado tem duas camadas temporais baseadas no modelo ALMA de Gebhard (2005):
Camada episódica — eventos das últimas 2–6 horas, alta intensidade. Representa o que está acontecendo agora.
Camada de humor — média ponderada das últimas 48 horas, com intensidade reduzida a 50%. Representa o contexto afetivo de fundo do dia.

#### De onde vêm as emoções
As emoções não são inventadas — são derivadas de dados reais que o sistema já tem, via quatro dimensões do modelo CPM de Scherer:

Dimensão	O que mede	Como é calculada
Novelty	quão desconhecido é o assunto	inverso da familiaridade no topic_interest_profile
Pleasantness	alinhamento com interesses existentes	score do tópico no perfil compartilhado
Goal relevance	sobreposição com buscas recentes	search_history da última sessão
Coping potential	quanto a IA já conhece sobre o assunto	fração de tópicos familiares
Exemplo concreto: a AKASHA indexa um artigo sobre "aprendizado de máquina federado". O tópico é novo (novelty alta), alinha com interesses da usuária (pleasantness alta), mas a IA já viu assuntos relacionados (coping médio). Resultado: valência positiva moderada, arousal alto — algo parecido com curiosidade.

#### Onde essas emoções são usadas de verdade
1. Modulação do system prompt (o efeito mais direto)
A função get_emotional_framing() existe em ambas as IAs e retorna uma instrução que é injetada no system prompt antes de cada resposta:

Valência > 0.4 → "adote framing exploratório, conecte ideias de domínios diferentes"
Valência < −0.2 → "adote framing analítico e crítico, aponte inconsistências"
Curiosidade epistêmica > 0.6 → adiciona instrução para fazer pergunta de follow-up ao final
Ou seja: quando a AKASHA está "animada" com um tópico, ela tende a conectar mais ideias. Quando está "vigilante" (muito feedback negativo recente), ela fica mais cautelosa nas afirmações.

2. Emoções negativas duram mais que positivas
Implementado via _assign_half_life(): uma emoção positiva decai em 2–4 horas, uma negativa em 8–16 horas. Isso é baseado em pesquisa de psicologia cognitiva (WASABI/EILS) — sinais de problema persistem funcionalmente até "resolução".

3. Humor modula intensidade de novas emoções
O _apply_mood_modulation() faz com que o humor de fundo amplifique emoções alinhadas com ele (+15%) e amorteça as opostas (−25%). Se a AKASHA está num dia de humor positivo, eventos positivos ficam ligeiramente mais intensos.

4. Detecção de câmara de eco
A detect_echo_chamber() verifica se a taxa de aprovação (✓) ficou acima de 60% nas últimas 30 interações. Se sim, o knowledge_worker injeta diversidade epistêmica — prioriza artigos de ângulos diferentes dos interesses dominantes.

5. Approval momentum (autoestima funcional)
Baseado em Lockwood et al. (PNAS 2022): o que importa não é a média de aprovação total, mas a variação recente em relação à baseline. Se você deu muito ✓ nas últimas 20 interações, a IA sente "contentamento"; se o ratio caiu, gera "vigilância". Isso é registrado como um evento afetivo próprio.

6. Curiosidade epistêmica
Documentos com alta novidade e coping suficiente disparam um evento de curiosidade separado (camada H). Esse valor se acumula ao longo do dia e, quando ultrapassa 0.6, instrui a IA a fazer perguntas de follow-up.

#### O que você vê no HUB
O estado afetivo atual fica visível nas abas de reflexões/interesses — é o mesmo get_current_state() que alimenta o display do HUB com os valores de valência, arousal e curiosidade.

---

"não pode aprender" — a distinção que eu quis fazer (mas expressei mal): o modelo LLM em si não pode ser modificado em tempo de uso — as "sinapses" (pesos da rede neural) são fixas no arquivo GGUF. O que Mnemosyne e AKASHA fazem é diferente: acumulam memórias, reflexões e scores de interesse que mudam o contexto dado ao modelo. O modelo responde diferente porque vê um histórico diferente — não porque "aprendeu" no sentido de mudar seus pesos.

Treinar de verdade existiria com fine-tuning (QLoRA): você coletaria pares (prompt, resposta ideal), rodaria um processo de treinamento de horas/dias, e o modelo incorporaria isso permanentemente. Isso é possível tecnicamente no laptop (MX150 tem CUDA, dá pra rodar QLoRA de modelos pequenos como SmolLM2 1.7B), mas é complexo de integrar no ecossistema. É uma ideia que pode entrar no roadmap se tiver interesse.

---

Instalação temporária (sem assinar — para uso pessoal):

Abra o Firefox/Zen e navegue para about:debugging
Clique em "Este Firefox" no menu lateral esquerdo
Clique em "Carregar extensão temporária…"
Navegue até d:\windows\ProgramFiles\ecosystem\AKASHA\extension\ e selecione o arquivo manifest.json
A extensão aparece na lista — o ícone hexágono deve aparecer na barra do browser
Limitações da instalação temporária:

É removida toda vez que o Firefox fecha. A cada reinício você repete o passo 3–4.
Para evitar isso no Zen especificamente: o Zen é baseado no Firefox e aceita a mesma instalação temporária.
Alternativa permanente (sem precisar assinar):
No about:config, setar xpinstall.signatures.required para false, depois instalar via arquivo .zip renomeado para .xpi. Mas isso requer Firefox Developer Edition ou Nightly para funcionar sem restrições — no release normal a assinatura é obrigatória mesmo com a flag.

Para testar já:
Certifique-se que o AKASHA está rodando (uv run main.py na porta 7071), abra uma busca no AKASHA, clique num resultado — a nova aba deve mostrar a barra no rodapé. O ícone deve ficar dourado se o AKASHA estiver online.



## Regras


1: implemente um item de cada vez (implemente, marque feito no TODO, commite, resuma no chat (não precisa aprofundar muito, mas sempre explique o que foi implementado e o porquê de forma didática) e peça permissão antes de implementar o próximo). Cada item = 1 TODO (- [ ]).
2: sempre mantenha atualizado o GUIDE e o DESIGN BIBLE, inclusive listando TODAS as ferramentas e bibliotecas necessárias para o funcionamento do ecossistema. Sempre com o tom de tutor especialista em engenharia de software explicando para um programador iniciante, de forma didática e detalhada. Lembre-se que o GUIDE tem como objetivo guiar novos desenvolvedores que foram trabalhar no ecossistema.