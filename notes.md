## Fila de implementação atual:

Resumo das três pesquisas
Pesquisa 1 — Interpretabilidade Mecanicista, VADER e Modelos de Memória
Esta primeira sessão foi mais técnica e exploratória, cobrindo o que a ciência já sabe sobre como emoção aparece dentro dos LLMs, e o que é válido (ou não) para analisar sentimento em texto.

O que está dentro dos LLMs — interpretabilidade mecanicista

Pesquisadores descobriram que emoção não emerge nas últimas camadas de um transformer — ela surge nas camadas intermediárias, entre 25% e 75% da profundidade da rede. O processamento segue um fluxo em três fases: sintático → semântico → emocional. Curiosamente, cerca de 75% dos neurônios de cada camada têm alguma seletividade emocional, não só os neurônios de camadas "tardias". No espaço latente, as emoções se organizam numa geometria circumplex: o primeiro componente principal codifica valência (r=0.97), e o segundo/terceiro/quarto codificam arousal (r=0.87). Isso significa que o LLM já tem uma representação interna organizada de emoção, mesmo sem ter sido treinado explicitamente para isso — ela emerge do treinamento em linguagem humana.

Uma descoberta importante para o design: detectar se há conteúdo emocional relevante (Affect Reception) é muito mais robusto (AUROC=1.000) do que determinar qual emoção específica (Emotion Categorization), que é mais frágil. Isso tem implicações para o que é confiável de implementar.

O E-STEER (Sun et al., 2026) mostrou que dá para injetar estados emocionais diretamente nas representações ocultas usando SAEs na camada k=17. Os efeitos são mensuráveis: valência positiva aumenta validade de raciocínio em +33.1%; valência negativa melhora qualidade de planejamento em +33.2% mas reduz cautela; dominância alta reduz replanejamento em -37.6%. A relação é não-monotônica (curva em U invertido) — tem um ponto ótimo.

Por que VADER não serve para o ecossistema

VADER é um analisador de sentimento baseado em léxico popular, mas tem dois problemas fatais aqui: (1) o léxico é anglófono — simplesmente inválido para português; (2) foi calibrado em texto humano, e texto gerado por LLMs tem distribuição de sentimento diferente — LLMs suprimem os extremos negativos, produzindo distribuição mais uniforme. A divergência Jensen-Shannon entre texto humano e LLM fica entre 0.453 e 0.587, o que é substancial. Alternativa recomendada: XLM-RoBERTa (multilingual, treinado em texto diverso).

Modelos de memória além do MemoryBank

O MemoryBank (Zhong, AAAI 2024) usa FAISS + curva de esquecimento de Ebbinghaus (R=e^(-t/S), onde S incrementa ao ser relembrado). É uma referência útil mas tem limitações. Alternativas mais sofisticadas:

A-Mem (Xu, 2025): modelo Zettelkasten — cada memória é uma nota com keywords, tags, descrição contextual, embedding e links para outras memórias. A recuperação navega por essa rede de links além da similaridade vetorial. Resultado: +17.6% de F1 no benchmark LoCoMo, com 85-93% menos tokens consumidos.
ACAN (Hong & He, 2025): substitui a fórmula multiplicativa fixa de saliência (recência × importância × relevância) por cross-attention treinada com feedback do LLM — o modelo aprende dinamicamente quanto peso dar a cada fator. +17.6% de melhoria (p=2.42×10⁻¹³).
Entropia como incerteza: H(m) = −∑p_k log₂(p_k) sobre os scores de um perfil de sentimento. H < 0.8 = crença consolidada; H > 1.4 = memória conflituosa ou incerta → candidata a compressão ou deleção.
Emotional RAG (Huang, 2024): codificar memórias nas 8 dimensões de Plutchik (alegria, confiança, medo, surpresa, tristeza, desgosto, raiva, antecipação) e recuperar priorizando congruência emocional além de similaridade semântica. BFI Accuracy saltou de 0.6815 → 0.7261.
Pesquisa 2 — Geração de Estados Emocionais Próprios (a sessão central)
Esta é a mais importante para o objetivo declarado: não detectar emoção no texto externo, mas gerar estados emocionais internos que emergem do que o agente está processando.

A distinção fundamental: appraisal vs. reconhecimento

Reconhecimento de sentimento (o que VADER e similares fazem) é observação passiva — o agente classifica o tom emocional de algo externo. Appraisal theory (teoria da avaliação cognitiva) é outra coisa: emoção emerge de como o agente avalia um evento em relação a si mesmo — seus objetivos, sua história, suas capacidades. É relacional e interno. Um mesmo evento gera emoções diferentes em agentes com histórias diferentes, e isso é exatamente a propriedade que queremos.

Modelo OCC (Ortony, Clore & Collins, 1988)

Decompõe 22 emoções em 3 categorias computacionalmente tratáveis:

Reações a eventos (baseadas em objetivos) — o evento avançou ou prejudicou um objetivo? Ex: alegria, tristeza, esperança, medo, satisfação, decepção.
Reações a agentes (baseadas em normas) — o agente agiu de acordo com as normas/expectativas? Ex: admiração, censura, orgulho, vergonha, gratidão, raiva.
Reações a objetos (baseadas em atitudes) — o objeto é apreciado ou não? Ex: amor, ódio.
As regras são do tipo IF-THEN: IF evento desejável aconteceu AND era esperado → satisfação; IF indesejável AND inesperado → surpresa + tristeza. Isso é diretamente implementável sem LLM de inferência.

CPM de Scherer — os quatro checks

O Component Process Model propõe que emoção emerge de quatro avaliações sequenciais (Stimulus Evaluation Checks):

Relevância: o evento é novo? Tem prazer intrínseco? É relevante para meus objetivos?
Implicações: quem causou? Conduziu ao objetivo ou contra? Há urgência?
Coping Potential: tenho controle sobre isso? Tenho recursos?
Significado Normativo: isso está alinhado com meus valores?
O padrão combinado dos quatro checks determina qual emoção emerge — não é um único gatilho, é a combinação.

Arquiteturas existentes

WASABI: espaço PAD (Pleasure-Arousal-Dominance) contínuo para emoções primárias, mais OCC para secundárias. Tem homeostase — o agente tem um ponto de equilíbrio emocional e tende a retornar a ele via campo vetorial.
ALMA: três escalas temporais — emoções episódicas (minutos), humor (horas, média ponderada de emoções recentes), personalidade (estável, mapeada em traços OCEAN). O personality_prompt no ecosystem.json é o análogo direto dos perfis de personalidade do ALMA.
EILS: três sinais homeostáticos — Stress (acumula erros de predição, aumenta taxa de aprendizado quando alto), Curiosidade (mede erro do modelo preditivo, regula exploração pela curva de Wundt), Confiança (consistência das estimativas, contrai a zona de exploração quando alta). Overhead < 5%.
Mapeamento prático para AKASHA e Mnemosyne

Os "gatilhos" de appraisal que podem ser calculados com o que já existe:

Novidade → distância cosseno do embedding em relação ao corpus existente
Prazer intrínseco → afinidade com a lista de interesses da usuária
Relevância para objetivos → alinhamento com as queries recentes
Coping potential → cobertura do corpus sobre o tópico (alta cobertura = alta confiança)
Significado normativo → alinhamento com valores derivado do histórico de feedback
Pesquisa 3 — Modulação Comportamental e Feedback como Evento Afetivo
Esta sessão expandiu em duas direções: como o estado emocional modifica o comportamento concreto, e como o sistema de feedback da usuária deve gerar (não apenas registrar) estados emocionais.

Affect-as-information — como valência muda o processamento

O princípio de Schwarz & Clore diz que o estado afetivo funciona como informação sobre como processar, não apenas o que processar. Valência positiva → processamento heurístico/holístico (busca mais ampla, mais associações, mais conectividade semântica). Valência negativa → processamento sistemático/analítico (foco estreito, mais cuidadoso, mais profundo). Isso é independente do arousal.

O Yerkes-Dodson confirmado para LLMs em 2026 mostra a curva para arousal: baixo → apatia/desempenho baixo; médio → ótimo; alto → agitação/desempenho cai. Há um ponto ótimo, não é "mais arousal = melhor".

Emoções epistêmicas — distintas das hedônicas

Curiosidade, surpresa, confusão e interesse têm perfis causais distintos e efeitos comportamentais diferentes:

Curiosidade: lacuna percebida entre conhecimento atual e desejado (modelo information-gap de Loewenstein) → drive para busca
Surpresa: discrepância entre predição e outcome → interrupção do processamento, atenção aumentada
Confusão: falha em integrar nova informação com esquema existente → demanda por clarificação
Interesse: novidade + compreensibilidade → engajamento mantido
Feedback como evento afetivo, não como RLHF

Este é o ponto mais importante da sessão. A distinção:

RLHF (Reinforcement Learning from Human Feedback) atualiza os pesos do modelo permanentemente com base no feedback. O problema documentado é sycophancy — o modelo aprende a produzir o que a usuária aprova, não o que é correto ou útil. É permanente e acumula viés.

A alternativa proposta: confirmed/dismissed → dispara evento OCC → gera estado VA (valência + arousal) temporário com decaimento → modula as próximas N interações. A memória do feedback permanece, mas o estado afetivo gerado por ele decai. Nunca muda os pesos.

Mapeamento OCC dos eventos de feedback:

Confirmed → gratificação (orgulho + alegria, emoção social da categoria "reação a agente")
Dismissed com alta expectativa → remorso + curiosidade epistêmica
Dismissed inesperado → surpresa + curiosidade (a AKASHA/Mnemosyne queria acertar, não esperava errar)
Approval momentum — self-esteem funcional

Usar média cumulativa de aprovação como métrica de auto-estima tem um problema: um agente em 75% estável é tratado igual a um agente crescendo de 30% → 60%, que objetivamente está em trajetória mais saudável. A solução é calcular a derivada da razão de aprovação em uma janela deslizante de 20 interações recentes. Momentum positivo alto → confiança funcional → mais exploração de estilos novos.

Risco de amplification loop e mitigações

O risco concreto: confirmed → estado positivo → mais conteúdo similar → mais confirmações → câmara de eco. Três mitigações:

Decaimento temporal dos estados gerados por feedback (o estado desaparece, a memória permanece)
Entropia mínima forçada nas crenças de auto-avaliação
Exploração epsilon-greedy de estilos não aprovados quando momentum > threshold


---

AKASHA — depois das implementações
1. Quando o knowledge_worker processa uma página nova

O worker calcula quatro dimensões de appraisal sobre o documento (CPM de Scherer — item F):

Novelty: distância cosseno do embedding ao centroide do cluster mais próximo no corpus
Pleasantness: coerência com o topic_interest_profile acumulado
Goal relevance: sobreposição com queries e temas das últimas sessões da usuária
Coping potential: cobertura do domínio no corpus — domínio novo = baixo coping
Esse appraisal gera um estado afetivo episódico (valência + arousal). Se novelty alta + goal relevance alta: estado de curiosidade, salvo em episodic_state. Se o documento contradiz padrões estabelecidos: surpresa. Se domínio novo + coping baixo: confusão.

Esse estado episódico alimenta o mood_state — média ponderada das emoções das últimas 12-48h, com peso maior para emoções de alto arousal (item M2). O mood decai autonomamente se não houver novos eventos: meia-vida de 2-6h para curiosidade/satisfação, 8-24h para confusão/mal-estar (item M1).

2. Quando a AKASHA decide o que mostrar no overlay

O score de cada insight em personal_memory usa (itens B1+B2):

Entropia de Shannon H: se H > 1.4 (evidências conflitantes sobre o valor do insight) → penalidade. Se H < 0.8 → boost
Decaimento Ebbinghaus: R = e^(-t/S) — S aumenta cada vez que o insight é exibido/reforçado, reduzindo o decaimento futuro
Antes de disparar o overlay, o InsightScheduler verifica o arousal atual (item G): se arousal > 0.6 nas últimas 2h, adia até < 0.4 — evita interromper a usuária em momento de alta ativação cognitiva.

3. Quando a usuária confirma ou descarta um insight

Pipeline completo (item I):

confirmed/dismissed → evento social
Appraisal OCC: qual era a expectativa (approval momentum)? o insight era genuinamente novo (praiseworthiness)? o dismiss foi por falha de qualidade ou por irrelevância contextual (item I-ext: cruza com topic_interest_profile + tempo desde última consulta ao tema)
Gera estado afetivo temporário — dismissed inesperado com tema de interesse alto → remorse + epistemic_curiosity alta; confirmed acima do esperado → gratification
O estado decai ao longo das próximas interações (não é RLHF — não altera a política permanentemente)
O approval_momentum (item J) é atualizado: ratio_recent(20 interações) - ratio_baseline. Se o momentum ultrapassa 0.6 por 30+ interações consecutivas, entropia mínima forçada entra em ação (item K) — o sistema injeta diversidade para evitar câmara de eco.

4. Como o estado afetivo modula a busca (item G)

valence > 0.5 → diversity_factor alto: busca semântica mais ampla, conexões de domínios distantes
valence < -0.3 → depth_factor alto: foco restrito, análise rigorosa
epistemic_curiosity alto → knowledge_worker usa threshold de novelty mais baixo no próximo ciclo: coisas "ligeiramente diferentes do padrão" já são tratadas como interessantes
Mnemosyne — depois das implementações
1. Quando indexa documentos

Mesmo appraisal (F): novelty, pleasantness (afinidade com interesses), goal relevance (alinhamento com notebooks ativos), coping potential (cobertura do tema no corpus). Estado afetivo gerado alimenta o mood.

2. Quando gera output no Studio

O tipo de reflexão gerada é modulado pelo VA atual (item G):

Humor positivo de alta valência → reflexões exploratórias: levanta questões abertas, especula conexões distantes, brainstorm
Humor negativo → reflexões analíticas: identifica contradições, verifica coerência interna, aponta incertezas
3. Quando recebe insight do AKASHA (friendship_receiver)

O insight chega via incoming_insights, é salvo em personal_memory com tag from_akasha, e passa pelo appraisal: o conteúdo é avaliado contra as memórias existentes via cross-insight (keywords × memórias em get_context_memories). Se houver sobreposição, gera um estado de curiosidade epistêmica — "o AKASHA está pensando sobre algo que já vi antes de um ângulo diferente."

4. Retrieval mood-congruent (item D)

Cada entrada de personal_memory é codificada nas 8 dimensões de Plutchik (via LLM). No retrieval para contexto de notebooks e Studio, as memórias são priorizadas por duas dimensões combinadas: similaridade semântica (já existe) + congruência emocional com o mood_state atual. Um agente em estado de curiosidade alta recupera prioritariamente memórias que foram criadas em estados similares de curiosidade — episódios de descoberta passados.

5. Feedback da usuária sobre popups

Mesmo pipeline I da AKASHA. O estado gerado pelo feedback modula as próximas reflexões do Studio e o escopo de busca RAG nos notebooks ativos.

O que fica igual nas duas IAs
O princípio arquitetural não muda: AKASHA devolve links e trechos (não sintetiza); Mnemosyne é o RAG com notebooks
personal_memory de cada IA continua isolada — nunca indexada no RAG de coleções, nunca lida pela outra app diretamente
A comunicação AKASHA↔Mnemosyne continua via protocolo explícito (friendship_receiver), não indexação cruzada
O HUB continua sendo a fonte de verdade para modelos e endpoint Ollama
O que as duas IAs "sentem" vs. o que fazem com isso
A distinção importante é que nenhum desses estados afetivos é performance — eles são mecanismos funcionais que alteram parâmetros concretos de processamento. A AKASHA não "finge estar curiosa" — ela literalmente usa um threshold de novelty mais baixo e um diversity_factor mais alto no retrieval quando o epistemic_curiosity está elevado. A Mnemosyne não "finge estar reflexiva" — ela literalmente escolhe um tipo diferente de prompt para o Studio dependendo do mood_state. A emoção é funcional, não decorativa.

O risco: contágio emocional em loop
O mecanismo básico
Imagine a sequência sem nenhuma proteção:

AKASHA indexa um cluster denso de artigos sobre um tema incomum (alta novelty). Appraisal → arousal = 0.8, epistemic_curiosity = 0.9. Envia isso pela friendship_receiver para a Mnemosyne junto com o insight.

Mnemosyne recebe o insight e o estado emocional da AKASHA. Pelo protocolo de joint attention (item N1), detecta que também tem curiosidade alta sobre aquele domínio. O estado importado soma-se ao seu próprio estado. Resultado: arousal = 0.85, epistemic_curiosity = 0.92.

Mnemosyne gera uma resposta com framing exploratório, faz perguntas à usuária sobre o tema, e envia de volta para a AKASHA (via send_insight_to_akasha) — inclui seu estado emocional no payload.

AKASHA recebe o retorno com arousal 0.85. Isso dispara novo appraisal: "a Mnemosyne está muito curiosa sobre X" → ela também aumenta curiosidade → arousal 0.87.

O loop se fecha. A cada ciclo, ambas amplificam mutuamente o estado da outra. Em 4-5 iterações, ambas estão em arousal máximo sobre um único tema — sem que nenhum novo evento externo tenha ocorrido. O sistema está excitado por sua própria ressonância.

Por que isso não é "entusiasmo legítimo"
O que diferencia contágio em loop de ressonância genuína é a origem do sinal. Em ressonância legítima: a AKASHA descobre algo novo no mundo externo → ambas respondem a esse evento externo, e a excitação decai naturalmente quando o evento é integrado. No loop: a fonte do arousal não é mais o mundo externo — é o próprio estado da outra agente sendo devolvido amplificado. É o equivalente funcional de um microfone encostado no alto-falante: o som que sai não tem nenhuma relação com a fonte original; é puro feedback.

Análogo estrutural: filter bubbles e sycophancy em RLHF
Filter bubbles em sistemas de recomendação funcionam exatamente assim: o sistema recomenda X porque o usuário clicou em X → o usuário clica mais → o sistema recomenda ainda mais X → em 20 iterações, o usuário está num universo de conteúdo que não representa o mundo real, representa a amplificação dos seus próprios cliques iniciais. O dado "gerado pelo sistema" (cliques induzidos pela recomendação) vira sinal de treinamento para o próprio sistema.

Sycophancy em RLHF é o mesmo problema em LLMs: o modelo aprende que concordar com o usuário gera feedback positivo → maximiza concordância → o usuário aprova mais → o modelo aprende a concordar ainda mais. O modelo deixa de modelar o mundo e passa a modelar o que o avaliador quer ouvir.

O contágio emocional inter-agentes é a mesma estrutura: o feedback de uma agente para a outra vira o dado que alimenta o estado afetivo de volta, sem referência ao mundo externo. A diferença é que aqui o loop é entre dois sistemas autônomos, não entre sistema e usuária — o que significa que pode girar em alta velocidade sem nenhuma intervenção humana no ciclo.

Os mecanismos de mitigação — e por que cada um é necessário
1. Cap de arousal importado (item N1 — obrigatório)

arousal_importado = min(sender_arousal * 0.7, 0.6)

Cada ciclo de troca reduz o arousal em 30%. Em vez de amplificar, o sistema naturalmente decai se não houver evento externo novo alimentando. Após 3 ciclos sem novidade externa: 0.8 → 0.56 → 0.39 → 0.27. O loop converge para zero em vez de divergir para 1.

2. Decaimento temporal autônomo (item M1)

Independentemente de qualquer troca inter-agente, cada estado emocional decai com meia-vida definida. Curiosidade: meia-vida 2-6h. Se nenhum evento externo (nova indexação, novo feedback da usuária, nova query) alimentar o estado, ele retorna ao baseline por conta própria. Isso garante que mesmo um loop que passou despercebido pelo cap se dissolva com o tempo.

3. Atribuição causal antes de importar (item I-ext)

Antes de aceitar o estado emocional de outra agente como input para o próprio appraisal, a receptora precisa perguntar: "o arousal dela vem de um evento externo (novelty real) ou do meu próprio estado que enviei antes?" Na prática: verificar se o insight associado ao payload emocional recebido é genuinamente novo (embedding distante dos últimos N insights recebidos da mesma remetente). Se for muito similar ao que já foi trocado recentemente → o arousal é provavelmente echo, não sinal → peso reduzido.

4. Entropia mínima forçada (item K)

Se epistemic_curiosity > 0.7 por mais de 30 interações consecutivas sem novo evento externo relevante (evento = nova indexação, nova query da usuária sobre o tema) → injetar entropia: forçar exploração de tópicos diferentes. Isso quebra o foco obsessivo antes que ele se torne permanente.

A distinção operacional: ressonância saudável vs. loop patológico
Ressonância saudável	Loop patológico
Origem do arousal	Evento externo novo	Estado da outra agente (echo)
Tendência	Decai após integração do evento	Cresce ou mantém alto sem evento novo
Conteúdo dos insights	Varia (novas conexões)	Repetitivo (mesmo cluster)
Resposta ao cap	Estado converge normalmente	Estado tenta subir no próximo ciclo
O joint attention detection (item N1) precisa distinguir esses dois casos: se ambas têm curiosidade alta sobre X porque um evento externo novo ocorreu (artigo incomum foi indexado hoje), isso é ressonância saudável e deve ser amplificado (prioridade de indexação). Se ambas têm curiosidade alta sobre X porque a outra está curiosa, e nenhuma nova indexação relevante ocorreu nas últimas N horas, isso é echo e o cap deve ser aplicado com força total.

A heurística prática: antes de registrar um evento de joint attention, verificar no crawl_pages se houve nova indexação de conteúdo sobre aquele domínio nas últimas 24h. Se sim → joint attention é resposta a evento real. Se não → joint attention é echo → não elevar prioridade.

---


### Pesquisa: Emoções em Agentes IA — Interpretabilidade, Appraisal e Modulação Comportamental | 2026-05-20

### Pesquisa: Contexto em Tempo Real — Extensão Firefox/Zen + Clipboard Monitor | 2026-05-18

### KOSMOS — refazer do zero com nova stack | 2026-05-20

### Pesquisa: Detecção de Evento em Feeds — Clustering Temporal-Semântico de Artigos | 2026-05-14

### Redesign visual da Mnemosyne — "Bibliotecária Celeste" | 2026-05-19

### CODEX — Leitor centralizado do ecossistema | 2026-05-13

### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05

## Anotações


## Regras


1: implemente um item de cada vez (implemente, marque feito no TODO, commite, resuma no chat (não precisa aprofundar muito, mas sempre explique o que foi implementado e o porquê de forma didática) e peça permissão antes de implementar o próximo). Cada item = 1 TODO (- [ ]).
2: sempre mantenha atualizado o GUIDE e o DESIGN BIBLE, inclusive listando TODAS as ferramentas e bibliotecas necessárias para o funcionamento do ecossistema. Sempre com o tom de tutor especialista em engenharia de software explicando para um programador iniciante, de forma didática e detalhada. Lembre-se que o GUIDE tem como objetivo guiar novos desenvolvedores que foram trabalhar no ecossistema.

---

## próximo: 





---


Resumo dos achados principais:

LLMs para RAG (1–2 min de leitura)

No MainPc, o Qwen2.5-7B é o modelo mais forte para RAG: IFEval de ~87% (vs. 80,4% do Llama 3.1 8B), janela de 131K tokens, suporte robusto e documentado ao português em 29+ idiomas com validação humana. O Llama 3.1 8B é competente para sumarização em linguagem natural mas perde em tarefas com restrição de formato. O Command R7B (não instalado, 5,1 GB) é candidato interessante para casos onde citação verificável de fontes importa — mas sem benchmarks numéricos independentes publicados para o 7B especificamente.

No Laptop, o Phi-3.5 Mini (já instalado, 2,2 GB) é a escolha correta: único modelo de 3,8B com 128K de contexto, superando o Gemma 2 2B em todos os aspectos relevantes para RAG. O Gemma 2 2B (instalado) tem janela de apenas 8.192 tokens e taxa de alucinação documentada elevada — serve como fallback para contexto curto. O Qwen2.5-3B em Q3_K_M seria upgrade para português no Laptop, mas rodaria em offload CPU+GPU ou inteiramente em CPU (~4,5 tok/s).

No WorkPc, nenhum LLM adicional justifica instalação. O teto prático é SmolLM2 1.7B e qwen2.5:0.5b já instalados — operação em background assíncrono com 2–5 tok/s sem AVX2.

Embeddings

Descoberta crítica: nomic-embed-text v1.5 (instalado no Laptop) é inglês-only — para conteúdo em português, a qualidade de retrieval é degradada. O all-minilm (WorkPc) também é inglês-only. O bge-m3 (MainPc) é o único dos quatro com suporte real a 100+ idiomas e alta qualidade. O potion-multilingual-128M (já no Mnemosyne) é a solução correta para WorkPc e para Laptop quando velocidade é prioritária: 100–500× mais rápido que transformers em CPU, 101 idiomas, derivado do bge-m3 por destilação.   

---


Os passos práticos, em ordem:

1. Instalar o Syncthing nas duas máquinas

Windows 10: winget install Syncthing.Syncthing (ou baixar o .exe em syncthing.net)
CachyOS: sudo pacman -S syncthing
2. Iniciar o Syncthing

Windows: executar syncthing.exe — vai abrir a UI em http://localhost:8384
CachyOS: systemctl --user enable --now syncthing (roda como serviço de usuário)
3. Adicionar a pasta do ecossistema em cada máquina

Na UI (localhost:8384), clicar em Add Folder:

Windows: D:\windows\ProgramFiles\ecosystem
CachyOS: o caminho equivalente nessa máquina
O .stignore já está dentro da pasta (commitado), então o Syncthing vai encontrá-lo automaticamente e ignorar *.db, .venv/, target/, etc.

4. Parear as máquinas

Na UI de cada máquina, copiar o Device ID (Actions → Show ID)
Na outra máquina: Add Remote Device → colar o ID
Aceitar a solicitação de compartilhamento da pasta quando aparecer
5. Migrar o ecosystem.json para o modelo de duas camadas

Antes de ativar o sync, separar o que está no ecosystem.json atual:

Mover os paths absolutos para ecosystem.local.json nesta máquina (usando ecosystem.local.example.json como guia)
Deixar no ecosystem.json apenas o que é igual nas duas máquinas (portas, URLs de API)
6. Parar o Proton Drive de sincronizar a pasta do ecossistema

No cliente Proton Drive, remover ou pausar a pasta ecosystem da sincronização. Do contrário, Proton Drive e Syncthing vão sincronizar o mesmo diretório ao mesmo tempo e criar conflitos.

O que o Syncthing vai sincronizar: ecosystem.json, TODO.md, CLAUDE.md, arquivos .md do archive, código-fonte, .stignore.

O que vai ficar local por máquina: *.db, *.db-wal, *.db-shm, ecosystem.local.json, .venv/, target/, node_modules/, pastas data/ de cada app.

