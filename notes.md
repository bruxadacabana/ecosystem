## Fila de implementação atual:

### KOSMOS — refazer do zero com nova stack | 2026-05-20


## próximo: 

### Pesquisa: Detecção de Evento em Feeds — Clustering Temporal-Semântico de Artigos | 2026-05-14

### Redesign visual da Mnemosyne — "Bibliotecária Celeste" | 2026-05-19

### CODEX — Leitor centralizado do ecossistema | 2026-05-13

### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05


## Anotações
1. me explique o funcionamento dos testes (para uma leiga, nunca usei isso)
2. quando eu disse "vamos criar Testes unitários e de integração" era para todo o ecossistema
3. o sistema de feedback (implementado nas notificações/overlays/pop-ups) não está perguntando quando marco x, por algum motivo. 
4. o pop-up da mnemosyne é ruim, assim com os outros icons da mnemosyne inteiro, é inexistente e todos os botões são apenas caixas vazias coloridas, o que para o sistema de feedback é um pouco confuso e eu não sei bem que feedback estou dando
5. akasha às vezes repete suas notificações/overlays
6. como as emoções que demos a elas são usadas no ecossistema?
7. como sabemos se elas estão aprendendo com o que estão processando?
8. ah alias, precisamos rever o logos em conjunto a '### Discussão: backends de inferência alternativos ao Ollama | 2026-05-21'. Também quero que o logos tenha uma forma melhor de gerenciar o hardware e detectar capacidade ao invés de se apoiar fixamente nos três hardwares que tenho.

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