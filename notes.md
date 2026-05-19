## Implementação atual:

### Bugs e investigações — sessão de testes | 2026-05-19
- verifique se já está implementado para que, se o KOSMOS rodar em o Ollama aberto, no momento que o Ollama abrir ele deve varrer as notícias e começar a análise em segundo plano
- no momento que mnemosyne terminou de indexar a biblioteca e foi começar a indexar o kosmos, deu erro "Query error: Database error: error returned from database: (code 1032) attempt to write a readonly database"
- inclua a opção de arquivar sites crawleados no akasha
- "2026-05-19 08:21:45,101 [WARNING] gui.workers: IndexWorker: erro ao embedar 'Organização estruturada de computadores (Andrew S. Tanenbaum) (Z-Library).pdf': timed out" como podemos evitar e tentar novamente esse tip ode erro? Talvez o arquivo que der erro entre para a fila de arquivos a serem indexados (como os arquivos novos inseridos nas pastas assistidas) e serem tentados novamente. Mas além disso, precisamos ver porque seu erro e como evitar.
- verifique o funcionamento da mnemosyne: nem todo insight/reflexão/pensamento/memória/opnião deve ser um pop-up ou visita, mas devem ser armazenadas na memória pessoal dela. Verifique Akasha também. Verifique também para ambas o que é necessário para gerar um pop-up e o que é necessário para gerar um pensamento/reflexão na memória. Faça pesquisas adicionais se necessário.
- pesquise sobre o uso de emoções nessas reflexões (como está sendo usado "surpresa"), se pode ser útil e como implementar. Expanda essa pesquisa
- ainda esto tendo problemas com a exibição de logs da mnemosyne no monitor do hub
- como é lidado pela Akasha e Mnemosyne quando um arquivo é deletado?
- o chat/conversa diretamente com a Akasha parece não estar funcionando bem
- o que acontece se a indexação for apagada mas a memória da Mnemosyne não? Precisa haver uma forma dela não refazer o trabalho que ainda estiver disponível.
- KOSMOS ainda está me dando a opção de alterar o llm sendo que não deveria mais ser possível (tudo sobre o ollama deve ser feito pelo HUB)
- o mnemosyne tentou exibir um pop mas carregou apenas uma janela transparente e vazia
- "temas" da mnemosyne deveria carregar em tempo real assim como "conexões" da akasha
- apesar das trocas de insights não deverem ser indexadas no rag, a akasha e mnemosyne pode usar o insight da outra para refletir e criar conexões com o que já sabe
- a área do diálogo com akasha no mnemosyne está toda bugada:
◇ No vault, não há menção direta a budismo, meditação ou felicidade. As entradas se concentram em fundamentos artísticos, harmonia cromática e composição, sem abordar temas espirituais ou filosóficos como o budismo.
  [1] ART FUNDAMENTALS, TWELFTH EDITION · [2] The Complete Color Harmony · [3] Composition
⬡
⬡
⬡1⬡.⬡ Ab⬡ord⬡a⬡:⬡ ab⬡ord⬡ag⬡em⬡ para⬡ res⬡olver⬡ problem⬡as⬡ da⬡ v⬡ida⬡ base⬡ada⬡ em⬡ ident⬡ific⬡ar⬡ ca⬡ó⬡dig⬡os⬡ e⬡ ev⬡itar⬡ o⬡ so⬡f⬡rim⬡ento⬡,⬡ at⬡rav⬡és⬡ de⬡ u⬡ma⬡ ab⬡ord⬡ag⬡em⬡ por⬡ res⬡olver⬡ u⬡ma⬡ ab⬡ord⬡ag⬡em⬡ para⬡ res⬡olver⬡ problem⬡as⬡ (⬡ab⬡ord⬡ag⬡em⬡)⬡
⬡2⬡.⬡ Ab⬡ord⬡ag⬡em⬡:⬡ ab⬡ord⬡ag⬡em⬡ para⬡ res⬡olver⬡ problem⬡as⬡ da⬡ v⬡ida⬡ base⬡ada⬡ em⬡ ident⬡ific⬡ar⬡ ca⬡ó⬡dig⬡os⬡ e⬡ ev⬡itar⬡ o⬡ so⬡f⬡rim⬡ento⬡,⬡ at⬡rav⬡és⬡ de⬡ u⬡ma⬡ ab⬡ord⬡ag⬡em⬡ por⬡ res⬡olver⬡ u⬡ma⬡ ab⬡ord⬡ag⬡em⬡ para⬡ res⬡olver⬡ problem⬡as⬡ (⬡ab⬡ord⬡ag⬡em⬡)⬡
⬡3⬡.⬡ Ab⬡ord⬡ag⬡em⬡:⬡ ab⬡ord⬡ag⬡em⬡ para⬡ res⬡olver⬡ problem⬡as⬡ da⬡ v⬡ida⬡ base⬡ada⬡ em⬡ ident⬡ific⬡ar⬡ ca⬡ó⬡dig⬡os⬡ e⬡ ev⬡itar⬡ o⬡ so⬡f⬡rim⬡ento⬡,⬡ at⬡rav⬡és⬡ de⬡ u⬡ma⬡ ab⬡ord⬡ag⬡em⬡ por⬡ res⬡olver⬡ u⬡ma⬡ ab⬡ord⬡ag⬡em⬡ para⬡ res⬡olver⬡ problem
[Diálogo encerrado]


### Redesign visual da Mnemosyne — "Bibliotecária Celeste" | 2026-05-19

### Pesquisa: Contexto em Tempo Real — Extensão Firefox/Zen + Clipboard Monitor | 2026-05-18

### CODEX — Leitor centralizado do ecossistema | 2026-05-13

### Bugs e investigações reportados após uso real | 2026-05-18
- [ ] **Investigar: causa raiz do erro "readonly" recorrente no ChromaDB** — não é a primeira vez que ocorre; toda vez exige re-indexação completa. Coletar logs completos na próxima ocorrência. Suspeitas: WAL corrompido (já existe `_clear_orphan_wal()` no código — indício de histórico), dois processos com acesso simultâneo ao mesmo SQLite, ou bug de versão do chromadb. Investigar se o `persist_dir` está em filesystem com limitações (ex: BTRFS + COW + SQLite WAL).
- [ ] **Documentar no GUIDE.md as features implementadas em 2026-05-18** — as seguintes implementações da sessão de hoje não estão no GUIDE: `IndexReflectionWorker` (pipeline de memória pessoal por arquivo); sinal `file_indexed` no `IndexWorker` + `_analysis_queue` + timer de 30s; FolderWatcher modo notificação (`watcherPendingBtn`); metadados temáticos do notebook (`themes`, `keywords`, `top_sources`) + `update_meta_from_history()`; roteamento de insights AKASHA por overlap temático; `role="akasha_insight"` + `append_akasha_insight()`; bloco de insights no `build_messages()`; extração de temas pós-batch do FolderWatcher.
- [ ] **Bug: logs do Mnemosyne somem no monitor após renomear diretório** — o diretório `ecosystem_root/mnemosyne/` foi renomeado para `mnemosyne.bak/` enquanto Mnemosyne estava rodando. Linux manteve o file handle aberto, então os logs continuaram indo para `mnemosyne.bak/mnemosyne.log`. O HUB (`read_app_log`) lê de `{sync_root}/mnemosyne/mnemosyne.log` (novo path) que não existe. **Solução imediata: reiniciar a Mnemosyne.** Solução estrutural: `read_app_log` no Tauri deve tentar também `{sync_root}/{app}.bak/{app}.log` como fallback, ou Mnemosyne deve escrever o `log_path` atual no ecosystem.json ao iniciar para que o HUB leia de onde o log realmente está.


## Anotações


## Regras


1: implemente um item de cada vez (implemente, marque feito no TODO, commite, resuma no chat (não precisa aprofundar muito, mas sempre explique o que foi implementado e o porquê de forma didática) e peça permissão antes de implementar o próximo). Cada item = 1 TODO (- [ ]).
2: sempre mantenha atualizado o GUIDE e o DESIGN BIBLE, inclusive listando TODAS as ferramentas e bibliotecas necessárias para o funcionamento do ecossistema. Sempre com o tom de tutor especialista em engenharia de software explicando para um programador iniciante, de forma didática e detalhada. Lembre-se que o GUIDE tem como objetivo guiar novos desenvolvedores que foram trabalhar no ecossistema.

---

## próximo:

- faça uma nova auditoria no pesquisas.md (leia o arquivo e verifique se tem coisas lá que não constam no TODO. Se existir algo faltando, acrescente em '### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05' e atualize a data
- algum programa poderia detectar o livro que estou lendo (marcado no OGMA) e notar se esse livro está na biblioteca da Mnemosyne. 

### Pesquisa: Detecção de Evento em Feeds — Clustering Temporal-Semântico de Artigos | 2026-05-14

### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05


depois:

- leia tudo que ainda não está marcado como completo no TODO e sugira os próximos passos


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

