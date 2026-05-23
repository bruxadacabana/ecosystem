## Fila de implementação atual:

- escreva um README atualizado para o ecossistema e inclua instruções para instalação do zero, incluindo ferramentas, plugins, fontes, dependências... Inclua TUDO o necessário, como o uv, rustc, npm, llama-cpp e outros
Inclua também um esquema detalhado das funcionalidades e capacidades de cada programa.
Faça isso tudo para todos os sistemas operacionais que usamos (CachyOS, fedora e Windows 10) e lembre-se do hardware de cada, caso necessário. Salve na memória que esse README deve ser mantido atualizado.

---


Você vai recriar do zero o arquivo `GUIDE.md` na raiz do projeto. Este é o guia de desenvolvimento definitivo do ecossistema, escrito para que uma pessoa com conhecimento básico de Python (sabe funções, classes, ambientes virtuais) e terminal possa entender, executar e dar continuidade ao projeto de forma independente.

O guia deve ser escrito em português (Brasil), com tom didático e paciente, explicando os "porquês" das decisões, sem condescendência. Use emojis com moderação para tornar a leitura agradável.

## Atenção especial à nomenclatura e novas capacidades

O ecossistema agora distingue dois componentes que devem sempre trabalhar em paralelo, sem interromper um ao outro:
- **AKASHA** (maiúsculo): a ferramenta de busca pessoal. Foco em crawling, indexação, ranqueamento, busca local e web, sem IA geradora no caminho crítico.
- **Akasha** (maiúsculo inicial apenas): o assistente inteligente de pesquisa.

O guia deve documentar o uso de **LLMs locais** (via Ollama, LOGOS, etc.) e a infraestrutura de **treinamento de LLMs** que está sendo incorporada ao projeto (fine-tuning, avaliação de modelos, etc.).

## Estrutura Obrigatória do GUIDE.md

Escreva o guia seguindo **estritamente a ordem abaixo**, uma seção por vez, sempre aguardando minha confirmação antes de passar para a próxima. Cada seção deve ser completa e autocontida, mas com referências explícitas a outras seções quando necessário (ex: "veja a Seção 5 para detalhes das dependências").

As seções são:

1. Visão Geral do Ecossistema
2. Pré-requisitos e Setup Inicial
3. Estrutura de Pastas do Projeto
4. Setup de Desenvolvimento por App
5. Dependências Completas por App e por Funcionalidade de LLM/Treinamento
6. Arquitetura de Dados
7. Pipeline de Busca (AKASHA)
8. Infraestrutura de LLMs Locais e Treinamento (Akasha)
9. Conceitos Importantes Explicados
10. Convenções de Código
11. Como Adicionar uma Feature Nova
12. Debugging e Solução de Problemas
13. Glossário
14. Referências e Links Úteis

## Instruções de Escrita por Seção

### Seção 1: Visão Geral do Ecossistema
- Apresente o ecossistema e o problema que resolve.
- Destaque a distinção entre AKASHA (busca) e Akasha (assistente com LLMs).
- Liste os 7 apps (HUB, AETHER, OGMA, KOSMOS, Mnemosyne, Hermes, AKASHA) com uma frase descritiva cada, mencionando relação com o assistente se aplicável.
- Inclua o diagrama ASCII da arquitetura, mostrando o fluxo entre busca e assistente.
- Explique a comunicação entre apps (ecosystem.json, HTTP, leitura de arquivos).
- Descreva o ecosystem.json: localização, estrutura completa comentada, quem lê/escreve cada campo.
- Tabela de portas reservadas.

### Seção 2: Pré-requisitos e Setup Inicial
- Liste todo software necessário: Python (versão exata usada), Node.js (versão), Rust/Cargo, uv, Docker (se usado), Ollama, ferramentas de treinamento de LLM (PyTorch, Axolotl, Unsloth, etc. — apenas as que o projeto realmente usa).
- Forneça comandos exatos para instalar cada item no Linux e Windows.
- Explique como verificar se cada ferramenta está funcional após a instalação.

### Seção 3: Estrutura de Pastas do Projeto
- Apresente a árvore de diretórios completa a partir da raiz do monorepo.
- Explique o propósito de cada pasta relevante.
- Indique onde estão: dados, logs, bancos de dados, configurações, checkpoints de modelos.

### Seção 4: Setup de Desenvolvimento por App
- Para cada um dos 7 apps, inclua: localização, stack tecnológica, como criar/ativar ambiente virtual, comando de instalação de dependências, comando para rodar em dev, comando de testes, variáveis de ambiente, porta.
- Adicione uma subseção extra para o componente **Akasha (assistente)** se houver implementação separada (scripts de treinamento, módulo específico). Descreva o ciclo de treinamento de LLM: preparação de dados, fine-tuning, avaliação, implantação.

### Seção 5: Dependências Completas por App e por Funcionalidade de LLM/Treinamento
- Para cada app e para a infraestrutura de LLM/treinamento, crie uma tabela com: Biblioteca/Ferramenta, Versão, Tipo (runtime/dev), Por que foi escolhida, Como está configurada.
- Liste APIs externas (DuckDuckGo, SearXNG, Open-Meteo, Wikipedia, Nominatim, Invidious, LibreTranslate, Ollama, Hugging Face Hub, etc.) com: URL da doc oficial, se precisa de chave (e como obter), rate limits, fallbacks.
- Para ferramentas de treinamento (PyTorch, Transformers, Datasets, PEFT, bitsandbytes, etc.), explique o propósito de cada uma no pipeline de fine-tuning.

### Seção 6: Arquitetura de Dados
- Descreva o fluxo de dados entre apps e entre AKASHA e Akasha.
- Explique o ecosystem.json campo a campo, com exemplos.
- Enumere os bancos de dados (SQLite com esquemas principais, ChromaDB, etc.) e onde os arquivos residem.
- Documente formatos de arquivo (Markdown, JSON) e convenções de nomenclatura.
- Explique como os dados de treinamento de LLM são coletados e armazenados (logs de conversa, feedback, datasets).

### Seção 7: Pipeline de Busca (AKASHA)
- Detalhe a jornada completa de uma query: recebimento → anáfora → classificação de intenção → expansão → busca local (FTS5 + vetorial) → busca web (SearXNG/DDG) → ranking (RRF + PageRank + domain_boost + freshness) → roteamento para aba/visualização → renderização.
- Explique o propósito de cada etapa.
- Aponte exatamente onde no código cada etapa ocorre (arquivo e função).
- Detalhe o funcionamento do cache dois níveis (memória + SQLite).

### Seção 8: Infraestrutura de LLMs Locais e Treinamento (Akasha)
- Explique como o LOGOS atua como proxy de LLM (fila de prioridade, fallback para Ollama).
- Liste os modelos usados atualmente e como são baixados/gerenciados.
- Descreva o pipeline de treinamento: coleta de dados pessoais → pré-processamento → fine-tuning (ex: LoRA) → avaliação → integração.
- Ensine como testar um modelo treinado localmente.
- Inclua boas práticas de privacidade e eficiência (quantização, execução local).

### Seção 9: Conceitos Importantes Explicados
- Explique em linguagem simples, com exemplos, cada um destes conceitos:
  - Índice invertido e FTS5
  - BM25 e TF-IDF
  - Busca vetorial e embeddings
  - Reciprocal Rank Fusion (RRF)
  - PageRank
  - Pseudo-Relevance Feedback (PRF)
  - pHash e distância de Hamming
  - WAL mode no SQLite
  - RAG e por que o AKASHA não gera respostas
  - LoRA, fine-tuning, embeddings para treinamento
  - Crawling respeitoso (robots.txt, politeness)

### Seção 10: Convenções de Código
- Estilo Python (PEP 8, Black, Ruff — qual é usado?)
- Nomenclatura de arquivos, funções, classes, variáveis
- Convenção de commits
- Padrão de docstrings
- Como escrever testes (pytest, unittest)
- Estrutura de módulos esperada (routers/, services/, models/, templates/)

### Seção 11: Como Adicionar uma Feature Nova
- Use um exemplo concreto do projeto (como "Adicionar busca de imagens no AKASHA" ou qualquer feature pequena que já tenha sido implementada ou esteja no TODO).
- Mostre todos os arquivos que precisam ser criados ou modificados.
- Demonstre o ciclo: ideia → branch → implementar → testar → integrar.
- Explique onde colocar a lógica (router vs service vs model).
- Ensine a registrar um novo endpoint, atualizar o template Jinja2 e escrever os testes.

### Seção 12: Debugging e Solução de Problemas
- Liste problemas comuns e suas soluções, incluindo:
  - Porta já em uso
  - ecosystem.json corrompido ou mal formatado
  - Índice FTS5 vazio ou sem resultados
  - Ollama offline ou inacessível
  - Memória insuficiente ao indexar
  - Crawler não respeitando robots.txt
- Ensine como acessar e interpretar os logs de cada app.
- Ferramentas de debug disponíveis (print, loguru, debugger integrado).

### Seção 13: Glossário
- Tabela com termo → definição curta, para consulta rápida. Inclua todos os termos técnicos mencionados no guia.

### Seção 14: Referências e Links Úteis
- Liste a documentação oficial de cada biblioteca e ferramenta usada.
- Artigos, papers e posts que inspiraram decisões de design (ex: o paper original do Google, artigos sobre BM25, PRF, etc.).
- Links para comunidades relevantes (se aplicável).

## Procedimento de Escrita

1. **Comece pela Seção 1** e escreva-a completamente no arquivo `GUIDE.md`.
2. Ao terminar a seção, diga apenas: "Seção [número] concluída. Aguardando confirmação para a próxima."
3. Eu responderei com "próxima" ou "continue".
4. Você então escreve a próxima seção, **anexando** ao arquivo `GUIDE.md` (não sobrescreva o conteúdo anterior).
5. Continue assim até completar todas as 14 seções.

## Regras de Qualidade por Seção
- Use informações **reais e atuais** extraídas dos arquivos do projeto (requirements, configurações, código-fonte, estrutura de pastas).
- Se não tiver certeza sobre algum detalhe específico (ex: versão exata de uma biblioteca), indique com `[VERIFICAR: ...]` e siga em frente.
- Mantenha o tom didático, paciente e explicativo.
- Cada seção deve ser compreensível isoladamente, mas com links para outras seções quando aprofundamento for necessário.

## Após Concluir Todas as Seções
- Revise o documento completo em busca de inconsistências ou informações conflitantes.
- Verifique se todos os `[VERIFICAR: ...]` foram resolvidos ou documentados como pendências.
- Informe que o guia está completo e pronto para uso.

## Regra Permanente de Manutenção do GUIDE.md

A partir de agora, **sempre que você implementar qualquer alteração no ecossistema**, você deve atualizar o `GUIDE.md` imediatamente como parte da tarefa. Isso inclui, mas não se limita a:

- Adicionar, remover ou atualizar uma biblioteca ou dependência → atualize a Seção 5 (tabela do app correspondente).
- Criar um novo endpoint, módulo ou serviço → atualize a Seção 7 (pipeline de busca) ou a Seção 4 (setup do app), conforme aplicável.
- Alterar a comunicação entre apps, portas ou o `ecosystem.json` → atualize as Seções 1 e 6.
- Introduzir um novo conceito técnico ou ferramenta → adicione na Seção 9 (conceitos) e na Seção 13 (glossário).
- Implementar um item do TODO que afete a arquitetura → revise a seção relevante e registre a mudança.
- Descobrir uma nova solução para um problema comum → adicione na Seção 12 (debugging).

**Procedimento a cada mudança:**
1. Ao finalizar uma implementação, verifique mentalmente: "O que mudei que um novo desenvolvedor precisaria saber?"
2. Abra o `GUIDE.md` e localize a(s) seção(ões) impactada(s).
3. Faça a atualização de forma precisa e no mesmo tom didático do restante do guia.
4. Se a mudança for significativa, considere adicionar um aviso de versão no topo do arquivo (ex: `<!-- Última atualização: 2026-05-23 — adicionada infraestrutura de fine-tuning -->`).
5. Informe na sua resposta que o `GUIDE.md` foi atualizado e em qual seção.

O objetivo é que o `GUIDE.md` nunca fique desatualizado. Ele é a bússola do projeto.

Comece agora pela Seção 1: Visão Geral do Ecossistema.


---


então prossiga com a implementação de '### Pesquisa: Fine-Tuning Local com QLoRA — Aprendizado Real de Corpus Pessoal | 2026-05-22
'!
lembre-se sempre: um item por vez (um item = 1 - [ ]). Implemente, teste, marque no TODO, commite tudo, resuma o que foi feito e o porquê no chat, peça permissão para prosseguir.


## próximo: 

### Bugs e investigações reportados após uso real | 2026-05-23 (b)

### KOSMOS — refazer do zero com nova stack | 2026-05-20

### Pesquisa: Detecção de Evento em Feeds — Clustering Temporal-Semântico de Artigos | 2026-05-14

### Redesign visual da Mnemosyne — "Bibliotecária Celeste" | 2026-05-19

### CODEX — Leitor centralizado do ecossistema | 2026-05-13

### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05


## Anotações

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