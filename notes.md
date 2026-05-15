# Pesquisa: LLMs por Funcionalidade e Hardware — Controle de Recursos e Compatibilidade | 2026-05-14


## P1 — Sem isso o LOGOS não funciona corretamente hoje:

- [x] Item 6 — num_thread por tipo de tarefa (WorkPc) — já existe código de inject_efficiency_params mas os valores precisam de ajuste. Baixo risco, alto impacto no WorkPc que é o hardware mais fraco. Já tem infraestrutura pronta.

- [x] Item 5 — Injetar env vars do Ollama no startup — OLLAMA_FLASH_ATTENTION, OLLAMA_MAX_LOADED_MODELS, OLLAMA_GPU_OVERHEAD. Já existe configure_ollama_env() em logos.rs que escreve o arquivo — falta só o subprocesso usar essas vars ao dar spawn. Sem isso o Ollama ignora os limites de memória.

## P2 — Funciona hoje, mas vai travar em uso real:

- [x] Item 14 — JSON schema enforcement no KOSMOS — sem isso o WorkPc (smollm2/qwen2.5:0.5b) vai gerar JSON inválido e o KOSMOS vai quebrar em produção. Afeta diretamente a usabilidade do app.

- [x] Item 8 — logos_start_ollama() — hoje o botão "Iniciar Ollama" na UI chama algo, mas sem as env vars do perfil injetadas no spawn o item 5 fica incompleto. Dependência do item 5.

## P3 — Importante mas não bloqueia uso:

- [ ] Item 4 — Controle de % máximo de VRAM — o VRAM_P3_BLOCK = 0.85 já protege P3; o controle configurável via slider é uma melhoria de conforto.

- [x] Item 13 — indexing_enabled flag — necessário para o WorkPc não tentar reindexar com dims incompatíveis (256 vs 1024), mas só bloqueia quando a usuária ativar indexação no WorkPc.

- [ ] Item 12 — Detecção de mudança de embedding — proteção contra corrupção de índice ChromaDB; importante mas só dispara se a usuária mudar o modelo de embedding manualmente.

## P4 — Conforto/polish:

- [ ] Item 9 — logos_stop_ollama() — útil, mas parar o Ollama manualmente é raro.
- [ ] Item 10 — logos_abort_model_inference() — boa UX mas não bloqueia nada.
- [ ] Item 11 — Aviso de cancelamento de pull — cosmético.
- [ ] Item 7 — Painel de configuração na UI — depende dos itens 4/5/6 estarem implementados primeiro.


Dos itens restantes da sessão de pesquisa, os próximos pela ordem de prioridade são:

Item 4 — limite de VRAM em % no LOGOS (evict automático)
Item 8/9 — logos_start_ollama() / logos_stop_ollama() como comandos Tauri
Item 10/11 — cancelamento de inferência em andamento
Item 7 — painel de configuração no LogosView (slider VRAM, threads, FlashAttention)
Item 12 — detecção de troca de modelo de embedding

========================================

vamos prosseguir com a implementação de ### Pesquisa: LLMs por Funcionalidade e Hardware — Controle de Recursos e Compatibilidade | 2026-05-14


1: implemente um item de cada vez (implemente, marque feito no TODO, commite, resuma no chat (não precisa aprofundar muito, mas sempre explique o que foi implementado e o porquê de forma didática) e peça permissão antes de implementar o próximo). Cada item = 1 TODO (- [ ]).
2: sempre mantenha atualizado o GUIDE e o DESIGN BIBLE, inclusive listando TODAS as ferramentas e bibliotecas necessárias para o funcionamento do ecossistema. Sempre com o tom de tutor especialista em engenharia de software explicando para um programador iniciante, de forma didática e detalhada. Lembre-se que o GUIDE tem como objetivo guiar novos desenvolvedores que foram trabalhar no ecossistema.

======

próximo:

### Pesquisa: LLMs para RAG/Sumarização e Embeddings Multilíngues — Seleção por Hardware | 2026-05-13

### Pesquisa: RAG Multilíngue — Estratégias de Pipeline, Indexação e Geração Cross-lingual | 2026-05-14

### Pesquisa: Detecção de Evento em Feeds — Clustering Temporal-Semântico de Artigos | 2026-05-14

### Pesquisa: Assistente de Pesquisa Inteligente — LLM-Augmented Search e Query Understanding | 2026-05-06

### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05


depois:

- leia tudo que ainda não está marcado como completo no TODO e sugira os próximos passos


========================


Resumo dos achados principais:

LLMs para RAG (1–2 min de leitura)

No MainPc, o Qwen2.5-7B é o modelo mais forte para RAG: IFEval de ~87% (vs. 80,4% do Llama 3.1 8B), janela de 131K tokens, suporte robusto e documentado ao português em 29+ idiomas com validação humana. O Llama 3.1 8B é competente para sumarização em linguagem natural mas perde em tarefas com restrição de formato. O Command R7B (não instalado, 5,1 GB) é candidato interessante para casos onde citação verificável de fontes importa — mas sem benchmarks numéricos independentes publicados para o 7B especificamente.

No Laptop, o Phi-3.5 Mini (já instalado, 2,2 GB) é a escolha correta: único modelo de 3,8B com 128K de contexto, superando o Gemma 2 2B em todos os aspectos relevantes para RAG. O Gemma 2 2B (instalado) tem janela de apenas 8.192 tokens e taxa de alucinação documentada elevada — serve como fallback para contexto curto. O Qwen2.5-3B em Q3_K_M seria upgrade para português no Laptop, mas rodaria em offload CPU+GPU ou inteiramente em CPU (~4,5 tok/s).

No WorkPc, nenhum LLM adicional justifica instalação. O teto prático é SmolLM2 1.7B e qwen2.5:0.5b já instalados — operação em background assíncrono com 2–5 tok/s sem AVX2.

Embeddings

Descoberta crítica: nomic-embed-text v1.5 (instalado no Laptop) é inglês-only — para conteúdo em português, a qualidade de retrieval é degradada. O all-minilm (WorkPc) também é inglês-only. O bge-m3 (MainPc) é o único dos quatro com suporte real a 100+ idiomas e alta qualidade. O potion-multilingual-128M (já no Mnemosyne) é a solução correta para WorkPc e para Laptop quando velocidade é prioritária: 100–500× mais rápido que transformers em CPU, 101 idiomas, derivado do bge-m3 por destilação.   

================


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

