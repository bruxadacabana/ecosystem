## Implementação atual:

### Bugs no sistema de backup do AKASHA | 2026-05-19

### page_knowledge — dados de análise LLM no banco principal da AKASHA | 2026-05-19

### Pesquisa: Emoções em Reflexões de IAs e Critérios de Notificação Proativa | 2026-05-19

### Integração KOSMOS-AKASHA: Perfil de Interesse Compartilhado e Busca Unificada | 2026-05-19

### Pesquisa: Contexto em Tempo Real — Extensão Firefox/Zen + Clipboard Monitor | 2026-05-18

### Redesign visual da Mnemosyne — "Bibliotecária Celeste" | 2026-05-19

### CODEX — Leitor centralizado do ecossistema | 2026-05-13

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

