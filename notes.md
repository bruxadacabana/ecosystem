## Fila de implementação atual:

### Pesquisa: Funcionalidades Core da AKASHA — Query Understanding, Expansão e Memória de Sessão | 2026-05-22

### Pesquisa: Backends de Inferência LLM Local sem Intermediários (LOGOS Option B) | 2026-05-22

### Pesquisa: Fine-Tuning Local com QLoRA — Aprendizado Real de Corpus Pessoal | 2026-05-22

## próximo: 

### KOSMOS — refazer do zero com nova stack | 2026-05-20

### Pesquisa: Detecção de Evento em Feeds — Clustering Temporal-Semântico de Artigos | 2026-05-14

### Redesign visual da Mnemosyne — "Bibliotecária Celeste" | 2026-05-19

### CODEX — Leitor centralizado do ecossistema | 2026-05-13

### Auditoria pesquisas.md → itens não registrados no TODO | 2026-05-05


## Anotações

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