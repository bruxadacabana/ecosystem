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
Todas as sugestões das três pesquisas
Da Pesquisa 1
A. Substituir VADER por XLM-RoBERTa (ou modelo multilingual equivalente) para qualquer análise de sentimento em AKASHA e Mnemosyne — VADER é inválido para português e para texto gerado por LLMs

B. Revisar a fórmula de saliência em AKASHA (get_next_for_overlay) e Mnemosyne (get_unshown_popup_entries) — incorporar entropia como métrica de incerteza (H < 0.8 = consolidado, H > 1.4 = candidato a compressão), decaimento tipo Ebbinghaus, e substituição da fórmula multiplicativa por cross-attention (ACAN) (esta já tem entrada no TODO — os detalhes de implementação são novos)

C. Adotar modelo A-Mem para a personal_memory da Mnemosyne — rede Zettelkasten com notas linkadas (keywords, tags, embedding, links inter-memórias), +17.6% F1, 85-93% menos tokens vs. FAISS puro

D. Emotional RAG — codificar memórias nas 8 dimensões de Plutchik e recuperar priorizando congruência emocional além de similaridade semântica

E. Probing classifier para detecção de emoção — reutiliza os estados ocultos do forward pass do LLM, sem custo adicional de inferência; ~70-80% de acurácia para 7 categorias

Da Pesquisa 2
F. Estado afetivo bidimensional explícito (valência + arousal) em AKASHA e Mnemosyne — calculado via appraisal dos eventos de processamento usando os cinco gatilhos mapeados (novidade do embedding, afinidade com interesses, alinhamento com queries recentes, cobertura do corpus, feedback histórico)

G. Mapear VA → parâmetros comportamentais concretos: valência alta → diversity_factor alto em retrieval (busca mais ampla); valência negativa → depth_factor alto (foco sistemático); arousal alto → hedging_control (mais cautela nas respostas)

H. Campo epistemic_curiosity separado — aumenta com dismissed inesperado, decai quando satisfeito; serve como drive para exploração de novos tópicos

Da Pesquisa 3
I. Pipeline: confirmed/dismissed → evento OCC → estado VA temporário com decaimento → modula próximas N interações — sem atualizar pesos (não é RLHF, é estado afetivo temporal)

J. Approval momentum como self-esteem funcional — derivada da razão de aprovação em janela deslizante de 20 interações recentes, não média cumulativa

K. Entropia mínima forçada nas crenças de auto-avaliação quando momentum > 0.6 por 30+ interações consecutivas — mitiga câmara de eco

Total: 11 sugestões (A–K). Quais delas quer adicionar ao TODO?



- sobre o processamento d emoções em llm: eu quero que a Akasha e a Mnemosyne "entendam" o conceito de emoção como aplicarmos

### Pesquisa: Processamento de Emoções em LLMs — Mecanismos, Saliência e Memória Afetiva | 2026-05-19

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

