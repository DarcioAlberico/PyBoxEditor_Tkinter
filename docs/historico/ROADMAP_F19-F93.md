# ROADMAP — histórico das fases F19 a F93

As seções abaixo saíram do `ROADMAP.md` em 2026-10-06 (item 8 da análise geral), tal como
estavam: o arquivo vivo ficou com o sumário, a ordem de execução, o índice das fases e o que
está em aberto. Cada seção é o registro da fase — o que entrou, o que foi medido e onde está.

## F19 — A altura relativa à linha — MEDIDA, e o remédio não é este

A F14 fechou pedindo isto com todas as letras: homóglifo e caixa são 23% dos erros, "não
são erro de treino, são o mesmo desenho", e pedem "**entrada nova** — altura relativa à
linha junto do recorte". Esta fase foi atrás. **O sinal está lá, e mesmo assim não
melhora nada.** As duas metades importam.

### O sinal existe, e o discriminante não é o que a F14 escreveu

Medido nos `.box` rotulados, em distância entre médias por desvio combinado (d'):

| par | d′(topo) | d′(base) | d′(altura) | |
|---|---:|---:|---:|---|
| s/S | **3,78** | 0,60 | 3,18 | separa |
| o/0 | **3,24** | 0,60 | 2,66 | separa |
| w/W | **3,10** | 0,20 | 2,78 | separa |
| c/C | **3,00** | 0,30 | 1,82 | separa |
| g/9 | **2,32** | 1,24 | 0,78 | separa |
| l/1 | 1,93 | 1,02 | 0,06 | fraco |
| p/P | 1,14 | 0,56 | 0,74 | não |
| i/1 | 0,01 | 0,90 | 0,86 | não |

**É o topo, e não a altura.** O topo ganha em toda linha da tabela, e a razão é
tipográfica: todo glifo se apoia na mesma linha de base, então a base não distingue nada;
o que muda é até onde o glifo sobe. Minúscula de x-height começa em 0,30 da faixa da
linha; maiúscula e dígito, em 0,08.

**A altura sozinha erraria justamente o `p`.** Ele desce abaixo da base e mede quase o
mesmo que um `P` (0,703 contra 0,771) — por isso `p/P` fica em 1,14. Um módulo escrito
como a F14 formulou ("altura") erraria o par que ela própria lista como o maior da família
de caixa. `i/1` e `k/K` também não têm separação: os dois lados sobem igual.

### E não dá para pôr na rede, que é onde a F14 queria

A base são **127 mil PNGs de 32x32 já normalizados** (`training_data/`), e a altura
relativa não é recuperável deles: foi descartada na gravação. Acrescentar a entrada à CNN
exigiria reextrair e rerrotular a base inteira a partir das páginas originais — e o rótulo
é trabalho humano de meses, não de uma fase.

### Desempatar depois também não funciona

O que dava para testar sem retreinar nada: a rede oferece as candidatas (`predict_topk`), a
altura escolhe entre elas. `medir_altura.py` varre 63 combinações — dois normalizadores
(faixa da linha; mediana de `y1`/`y2`, que é menos ruidosa), quatro cortes, três faixas de
incerteza, três margens de probabilidade — em 9.178 caracteres:

| | acerto |
|---|---:|
| rede como está (argmax) | **98,29%** |
| melhor combinação com desambiguação | nenhuma passa de 98,29% |

Nenhuma supera, e nenhuma sequer empata mexendo em alguma coisa. Testado também
restringindo a troca só aos pares confundíveis, em vez de a toda divergência de classe:
igual.

**A conta que explica.** Numa amostra de 2.257 caracteres a rede erra 62, e 21 são de
classe de topo — o alvo real. Para render, a medida geométrica teria de disparar nesses 21
e quase nunca nos 2.195 acertos: a 2% de falso positivo já seriam 44 quebras contra 21
consertos possíveis. **Uma base a 98% não tolera um canal lateral a 97%.**

Houve um erro de percurso que vale registrar, porque quase virou conclusão errada: a
primeira varredura usou margem de probabilidade de 0,02 e o desambiguador tocou **1 box em
2.257**. A rede é peaked — a F14 mediu 0,9994 de confiança num acerto —, então a segunda
candidata vem com ~0,0005 e a margem cortava todas. "Não mudou nada" parecia "não tem
sinal", e era "o filtro estava fechado". Só depois de abrir a margem até 1e-6 a medição
passou a responder a pergunta feita.

### O que fica

Nada em produção mudou. Ficam `core/altura_relativa.py` e `medir_altura.py` — instrumento
e medição, como `avaliacao_pagina.py` e `medir_paginas.py` —, mais
`NeuralPredictor.predict_topk`, que a varredura precisa e que qualquer tentativa futura
aqui também vai precisar.

**Isto não desmente a F14; reforça a parte dela que esta fase não alcançou.** A altura tem
de entrar **na** rede, treinada junto, onde o modelo aprende quanto confiar nela — e o
caminho para isso passa por reextrair a base com a escala preservada, não por pendurar um
votante depois. Enquanto isso, quem resolve homóglifo e caixa de verdade é o contexto, e
esse é o resultado da F17.

Cobertura: `tests/test_f19_altura_relativa.py`, 18 testes.

---

## F20 — A leitura por linha no «Detectar e Preencher (Neural)» — CONCLUÍDA

Mesma pergunta da F18, no outro caminho que usa a cadeia inteira, e a mesma resposta.
Medido nas páginas rotuladas, com a rede e o k-NN carregados:

| | acerto | boxes trocados pela linha |
|---|---:|---:|
| como estava | 97,50% | — |
| **com a linha, trava em 0,70** | **97,54%** | 1 |
| com a linha, sem trava | **90,47%** | 173 |

A trava não é cautela: sem ela a linha troca 173 boxes e derruba **7 pontos**, porque
estaria pondo o EasyOCR (89,5%) por cima da rede (97,6%). Com ela, toca em 1.

O limiar virou `CONF_MAXIMA_PARA_A_LINHA` em `ui/main_window.py`, um lugar só, com a
tabela ao lado — inclusive a frase que importa para quem for mexer nele: **o ganho é
pequeno por construção**, porque a rede responde 98,9% dos boxes e sobra 0,7% onde a linha
tem o que dizer.

### Duas mudanças de contrato

**`ler_caractere` devolve `(char, confiança, fonte)`.** A âncora agora carrega quem
respondeu, e sem isso não havia como preservar `neural` no box que a linha só confirmou.

**`easyocr_linha` marca só o box que a linha trocou.** Antes, uma linha lida marcava todos
os boxes dela — e num caminho onde a rede responde quase tudo isso apagaria da revisão a
informação de quem realmente leu. Que a linha tenha corroborado continua registrado, mas
na **confiança**, que sobe quando as duas concordam. O caminho só-EasyOCR (F17) não muda de
resultado; muda o rótulo dos boxes que a linha confirmou sem alterar.

`_preencher_por_linha` passou a ser o laço por linha compartilhado pelas duas ações, como
`_preencher_boxes` é o laço por box.

Cobertura: 4 testes novos em `tests/test_f17_leitura_de_linha.py` (34 no arquivo).

---

## F21 — A leitura por linha no «Híbrido/Ref» — CONCLUÍDA, e aqui ela rende

Último caminho que faltava, e o único dos três em que a linha paga de verdade. A razão é
o que as três medições juntas mostram: **a linha rende na proporção inversa da força da
âncora.**

Este caminho não tem rede — é k-NN → EasyOCR —, e começa 2,7 pontos abaixo do neural.
Medido em 2.278 caracteres:

| trava | com a rede (F20) | **híbrido (esta)** | trocados |
|---|---:|---:|---:|
| sem linha | 97,50% | **94,82%** | 0 |
| 0,70 | 97,54% | 95,22% | 39 |
| **0,85** | 97,50% | **95,26%** | 42 |
| 0,90 | — | 95,08% | 50 |
| 0,95 | 97,32% | 95,08% | 53 |
| sempre | 90,47% | 90,25% | 194 |

**+0,44 ponto, dez vezes o ganho do caminho neural** (+0,04). E o ótimo desloca de 0,70
para 0,85 — que não é número achado só por varredura: 0,85 é o `learner_threshold` desta
ação, então a linha age exatamente nos boxes em que o k-NN se recusou a responder.

"Sempre" continua sendo o pior de todos os mundos, e por muito: 90,25%.

### O box vazio é onde a linha mais tem a dizer

Esta ação zera o box cuja fonte não é `learner` nem `easyocr` — a confiança dele fica em
0,0, abaixo de qualquer trava. É o caso em que a âncora admite não saber, e é exatamente
onde a segunda opinião vale mais. O alinhamento já tratava disso (a `MARCA_DE_VAZIO` da
F17); agora há teste dizendo que o caminho inteiro faz isso.

### O resumo das três fases

| caminho | âncora | antes | depois | trava |
|---|---|---:|---:|---:|
| Preencher (EasyOCR por linha) | EasyOCR | 72,9% | **89,5%** | sem trava |
| Detectar e Preencher (Neural) | rede + k-NN | 97,50% | 97,54% | 0,70 |
| Detectar e Preencher (Híbrido) | k-NN | 94,82% | **95,26%** | 0,85 |
| PDF pesquisável | rede + k-NN | 97,50% | 97,54% | 0,70 |

Quem quiser mexer numa dessas travas: a pergunta não é "qual o melhor número", é "quão boa
é a âncora deste caminho". Onde ela já lê melhor que 89,5%, a linha só deve encostar no
que sobrou.

Cobertura: 2 testes novos em `tests/test_f17_leitura_de_linha.py` (36 no arquivo).

---

## F22 — O modelo calibrado, e as travas remedidas contra ele — CONCLUÍDA

O treino de 12/08 gravou `temperatura: 1.0`, que é o que **todo** treino grava — a
calibração da F1.9 é ajustada para um conjunto de pesos e herdá-la aplicaria correção
medida sobre outros. O modelo estava em softmax cru desde então.

### A calibração paga

`calibrar_modelo.py` ajusta em **leave-one-page-out**: a temperatura de cada página sai
das outras nove, senão o número é bonito e falso.

| | ECE |
|---|---:|
| T = 1 (como estava) | 0,0287 |
| **T = 2,1916** | **0,0227** |

21% de erro de calibração a menos. O valor bate com o 2,0768 do modelo de 143 classes —
dois treinos diferentes, mesma família de correção.

### O que a temperatura mexe não é o que se espera

Ela **não muda qual classe vence** — só a confiança. Mas a cadeia **roteia por
confiança**, e aí o efeito é real. Medido em 2.278 caracteres, com `neural_threshold=0.8`:

| | T = 1 | T = 2,19 |
|---|---:|---:|
| respondidos pela rede | 2.263 | 2.203 |
| pelo k-NN | 10 | 63 |
| pelo EasyOCR | 5 | 12 |
| **acerto da cadeia** | **97,50%** | **97,37%** |

Sessenta boxes migraram da rede para o k-NN, e a cadeia perdeu 0,13 ponto. **O
`neural_threshold=0.8` estava afinado para a escala não calibrada**, e na nova ele corta
alto demais:

| `neural_threshold` | acerto | rede / k-NN / OCR |
|---:|---:|---|
| 0,40–0,70 | **97,45%** | 2.272–2.253 / 3–17 / 3–8 |
| 0,80 (atual) | 97,37% | 2.203 / 63 / 12 |
| 0,90 | 97,19% | 2.114 / 139 / 25 |

Baixado para 0,70, e virou `NEURAL_THRESHOLD` em vez dos literais repetidos — a SPEC §5.1
ainda pede que estes limiares venham de configuração, e uma constante nomeada com a tabela
ao lado é o passo que falta para isso, não um desvio dele.

**0,70 e não 0,40, apesar de medirem igual.** No trecho chato do platô o que muda é quem
responde, não o acerto: 19 boxes a mais na rede entre uma ponta e outra. Ficar na borda
alta mantém o k-NN como segunda opinião onde a rede hesita, que é a razão de ele existir
na cadeia — medido em `CharacterLearner`, nos casos difíceis ele acerta 88,5% contra 72,4%
da rede sozinha. Descer a 0,40 compraria o mesmo número desligando quase toda a segunda
opinião.

Conferido pelo caminho de produção, com a linha ligada e a trava em 0,70: **97,50%**, com
2.253 boxes na rede, 17 no k-NN, 7 no EasyOCR e 1 corrigido pela linha. É o mesmo número
de antes da calibração — o custo caiu de 0,13 para 0,04 ponto, e os 21% de ECE ficam.

### As travas da F18 sobreviveram

Era a pergunta que motivou remedir, e a resposta é que as duas ficam:

| trava | com a rede | híbrido |
|---|---:|---:|
| sem linha | 97,37% | 94,82% |
| 0,60 | 97,45% | 95,17% |
| **0,70** | **97,45%** | 95,22% |
| 0,80 | 97,45% | 95,22% |
| **0,85** | 97,28% | **95,26%** |
| sempre | 90,34% | 90,25% |

**Mas a razão mudou, e é isso que o comentário da constante agora diz.** Em T = 1 o 0,70
era um ponto, com 0,85 neutro; em T = 2,19 virou um **platô de 0,60 a 0,80**, e 0,85 passou
a fazer mal ao caminho com a rede (97,28% contra 97,37% sem linha nenhuma). O 0,70 ficou
por ser o meio do platô, não por ser o valor de antes.

O 0,85 do híbrido não se moveu, e não tinha por quê: aquele caminho não usa a rede, e a
confiança do k-NN não passa pela temperatura.

### O saldo, dito inteiro

A calibração custava **0,13 ponto de acerto** e devolve **21% de ECE**. Com o
`neural_threshold` seguindo a escala nova, o custo cai para **0,04 ponto** — um caractere
em 2.278 — e o ECE fica.

Valeria mesmo pelos 0,13: a confiança aqui não é enfeite, é ela que ordena a fila de
revisão (F3.2) e que a F14 mediu como o melhor filtro disponível, e acerto bruto com a
confiança mentindo rende menos que o contrário. Mas não foi preciso escolher.

**A lição é do formato do limiar, não do valor.** Um número afinado contra a escala de
confiança de um modelo é um número que o próximo treino invalida em silêncio — nada
quebra, nada avisa, e o roteamento da cadeia muda sozinho. Os três que existem hoje
(`NEURAL_THRESHOLD`, as duas travas da F18) carregam a tabela que os produziu, e a tabela
diz contra qual temperatura foi medida.

---

## F23 — O limiar que se justificava por outro limiar — CONCLUÍDA

A F22 fechou dizendo que um limiar afinado contra uma escala de confiança é um número que
o próximo treino invalida em silêncio, e listou os três que carregam a tabela que os
produziu. **Faltava dizer que havia um quarto, sem tabela nenhuma.** O `learner_threshold`
do «Detectar e Preencher (Híbrido/Ref)» era `0.85`, literal dentro do `preparar` da ação,
e a única razão registrada era ser o mesmo número da trava da linha — cuja razão, por sua
vez, era ser o `learner_threshold` da ação. Os dois se justificavam um pelo outro e nenhum
dos dois pela página.

### O instrumento vinha faltando desde a F18

As tabelas da F18, F20, F21 e F22 saíram de script que não ficou: nada em `medir_*.py`
chamava `fallback_chain`, e refazer qualquer uma delas era reescrever o instrumento antes
de medir. `medir_cadeia.py` é o que faltava, e é para a cadeia o que `medir_paginas.py` é
para a segmentação.

Ele chama o `fallback_chain` e o `ler_pagina` **de produção**, com os limiares importados
de `ui/main_window` — a única cópia é o `_recortes_do_box`, seis linhas que moram dentro
da classe da janela. Cada modelo é consultado uma vez por recorte e memorizado; o que
reexecuta a cada ponto da varredura é o roteamento, que é o que está sendo medido. Sem
isso uma varredura de seis limiares pagaria seis vezes os ~16 ms por caractere do EasyOCR.

E ele mede o que as tabelas anteriores não diziam: a **composição** (quem responde quantos
boxes e quanto acerta nos que pegou) e o **roteamento** — o k-NN e o EasyOCR postos no
*mesmo* box, separados por faixa de confiança do k-NN. É esta segunda que decide o limiar,
e ela custa consultar o EasyOCR em todos os boxes, inclusive nos que a cadeia jamais lhe
mandaria.

### O k-NN ganha em toda faixa, e a confiança dele mal ordena qualidade

Medido em 10.481 caracteres de 10 páginas rotuladas:

| confiança do k-NN | boxes | k-NN | EasyOCR | ganha |
|---|---:|---:|---:|---|
| 0,00 – 0,50 | 395 | 51,9% | 47,6% | k-NN |
| 0,50 – 0,70 | 839 | **98,6%** | 62,7% | k-NN |
| 0,70 – 0,80 | 808 | **97,8%** | 65,7% | k-NN |
| 0,80 – 0,85 | 218 | 99,1% | 85,8% | k-NN |
| 0,85 – 0,90 | 216 | 98,6% | 87,0% | k-NN |
| 0,95 – 0,99 | 2.006 | 97,5% | 79,1% | k-NN |
| 0,99 – 1,00 | 5.972 | 99,7% | 74,6% | k-NN |

Nas faixas de 0,50 a 0,85 o k-NN faz 98% — **acima da própria faixa 0,95–0,99**. A
confiança é `1 - distância/2000`, uma L2 absoluta sobre 32x32 em cinza cru, e no meio da
escala ela quase não ordena qualidade. O corte em 0,85 mandava **21,6% dos boxes para o
pior dos dois classificadores**.

A varredura, com a trava acompanhando o limiar:

| limiar | 10 páginas | as 2 limpas |
|---:|---:|---:|
| 0,00 | 97,53% | 95,73% |
| **0,30** | **97,62%** | **95,68%** |
| 0,50 | 97,36% | 95,45% |
| 0,70 | 95,53% | 92,65% |
| 0,85 *(era)* | 93,72% | 87,68% |
| 0,95 | 94,11% | 88,51% |

**+3,90 pontos** no conjunto e **+8,00** nas duas páginas limpas. De 0,00 a 0,50 é platô; o
que decide a borda é a faixa mais baixa, onde nas páginas limpas o k-NN faz 46,7% contra
48,9% — cara ou coroa, e a única em que ele não ganha. O 0,30 o mantém fora dela.

### A página que já estava na base, e por que a coluna "as 2 limpas" existe

`training_data` foi colhida com "Aprender com Página Atual" **das próprias páginas
rotuladas**, e onde o k-NN responde acima de 0,99 a distância está abaixo de 20 em 1.024
pixels — meio nível de cinza por pixel. Ali ele não generaliza, consulta a própria cópia:

| página | boxes | acerto | já na base |
|---|---:|---:|---:|
| Kasparov page-0013 | 1.557 | 99,23% | **97,2%** |
| Kasparov page-0057 | 1.184 | 97,89% | **94,9%** |
| Aagaard pg11 | 1.115 | 94,71% | 63,1% |
| Kasparov page-0022 | 508 | 94,88% | 61,4% |
| Kasparov page-0014 | 1.002 | 96,61% | 57,7% |
| Aagaard (1ª) | 292 | 90,75% | 47,9% |
| Kasparov page-0033 | 1.259 | 95,08% | 47,7% |
| Kasparov page-0108 | 1.388 | 89,55% | 43,8% |
| Kasparov page-0020 | 1.085 | 92,35% | 27,0% |
| **Kasparov page-0128** | 1.091 | **83,04%** | **9,1%** |

A correlação é a tabela inteira, sem exceção. **O número deste caminho é, em boa medida,
uma medida de quanto da página já foi aprendida** — e as duas de baixo são o que esperar
de livro novo. É por isso que a varredura foi refeita só nelas: se os +3,90 fossem
vazamento, encolheriam ali. Dobraram. O que o k-NN faz entre 0,50 e 0,85 é generalização —
644 boxes a ~96%, com distância entre 300 e 1.000, longe de qualquer cópia.

`tabela_por_pagina` passou a imprimir essa coluna sempre, porque um número alto medido em
página contaminada é a boa notícia falsa mais fácil de acreditar neste projeto.

### Os dois limiares viraram um, e agora em código

Separá-los foi medido de propósito — limiar novo (0,30) com a trava velha (0,85), nas duas
páginas limpas:

| trava | acerto | trocados |
|---|---:|---:|
| sem linha | **95,68%** | 0 |
| 0,30 | 95,68% | 3 |
| 0,60 | 95,22% | 22 |
| 0,70 | 93,57% | 65 |
| 0,85 | 91,54% | 112 |
| sempre | 88,01% | 209 |

São **7 consertos contra 97 quebras**, saldo de −90 caracteres. É a lei da F21 — a linha
rende na proporção inversa da força da âncora — vista do outro lado: fortalecer a âncora
**tira** trabalho da linha em vez de somar com ele. Por isso
`CONF_MAXIMA_PARA_A_LINHA_HIBRIDO = LEARNER_THRESHOLD_HIBRIDO`, amarrados no código e não
só no comentário, com teste que quebra se a amarração se desfizer.

O caminho híbrido passa a ter o mesmo formato do neural: âncora forte, linha agindo só na
sobra. O ganho dela caiu de +2,31 pontos para +0,02, e isso é o esperado, não uma perda.

### O que esta fase fecha, e o que ela reabre

**Fecha o canal geométrico da F19 para este caminho.** A conta que o refutou era "uma base
a 98% não tolera um canal lateral a 97%", e o argumento não valia aqui enquanto a âncora
era 94,8%. Com ela em 97,6% volta a valer, e o alvo de homóglifo e caixa da F14 volta a
depender de a altura entrar **na** rede, treinada junto.

**Reabre a fórmula da confiança do k-NN.** A tabela de roteamento mostra que
`1 - distância/2000` mal ordena qualidade no meio da escala, e o `threshold=2000.0` de
`CharacterLearner.predict` nunca foi medido contra nada. Voto entre os k vizinhos mais
próximos e confiança por **margem** (o melhor da classe vencedora contra o melhor de outra
classe) são a mesma conta de matriz que já roda — o vetor de distâncias está calculado, é
trocar `argmin` por `argpartition`. Mas mexer nisso desloca a escala inteira e **obriga a
remedir os dois limiares desta fase**, que é exatamente a lição da F22.

**A base é o outro caminho, e é o mais barato.** Este elo é vizinho mais próximo sobre
amostras colhidas destes livros; a coluna "já na base" é literalmente a curva de retorno
de "Aprender com Página Atual". Uma ou duas páginas de um livro novo movem este caminho
mais que qualquer limiar.

Cobertura: `tests/test_f23_medir_cadeia.py`, 9 testes — a memorização não muda resposta
nenhuma (que é a afirmação de que o instrumento inteiro depende) e os dois limiares são o
mesmo número.

---

## F24 — O voto e a margem — MEDIDAS, e as duas voltaram

A F23 fechou reabrindo a fórmula da confiança do k-NN: a tabela de roteamento mostrava
`1 - distância/2000` mal ordenando qualidade no meio da escala, e o 2000 nunca tinha sido
medido contra nada. Os dois candidatos naturais eram voto entre os k vizinhos e confiança
por margem. **Foram implementados, medidos e devolvidos.** O que ficou é o instrumento das
duas e uma explicação de por que a fórmula "pior" é a certa aqui.

### O voto perde, e monotonicamente

A hipótese: o 1-NN deixa uma amostra ruim decidir sozinha, e a maioria entre os k
corrigiria. Medido em 3.564 caracteres das três páginas menos contaminadas pela própria
base (`medir_cadeia.py --knn --k N`, segundos por ponto):

| k | acerto do k-NN sozinho |
|---:|---:|
| **1** | **96,10%** |
| 3 | 95,90% |
| 5 | 95,90% |
| 7 | 95,79% |

Não há joelho, é descida. A explicação provável está na composição da base: 70.755
referências em 211 classes, sobreviventes de uma dedup byte a byte que tirou 86% de
repetição. O vizinho mais próximo costuma ser quase o mesmo PNG, e exigir maioria entre
cinco arrasta amostra de classe vizinha para dentro da decisão. **Classe rara é quem mais
perde** — ligadura e figurina não têm cinco amostras para votar.

O caso construído que motivou a hipótese existe e o `voto` de fato o resolve
(`test_o_voto_escolhe_a_maioria_e_nao_o_mais_proximo`). Um caso construído não é uma
distribuição.

### A margem perde nos dois usos, e o segundo explica o primeiro

A margem é `1 - (distância à classe vencedora) / (distância à classe mais próxima que não
seja ela)` — a razão de Lowe. Ela conserta, no papel, exatamente o que se criticava:
é **invariante de escala**, então não rebaixa o glifo de traço grosso por engordar, e
dispensa a constante mágica.

**Roteamento da cadeia**, 10.481 caracteres, mesmas páginas e mesma segmentação da F23:

| limiar | margem (esta) | absoluta (F23) |
|---:|---:|---:|
| 0,00 | 97,19% | 97,53% |
| **0,10** | **97,32%** | — |
| 0,30 | 97,02% | **97,62%** |
| 0,50 | 96,13% | 97,36% |
| 0,85 | 93,65% | 93,72% |

O melhor de cada uma: **97,32% contra 97,62%**. A margem custa 0,30 ponto.

**Fila de revisão** (F3.2, que ordena por confiança). Cortes fixos não comparam duas
escalas diferentes — o mesmo 0,70 cai em lugares diferentes da distribuição —, então a
comparação é a recall igual: para pegar a mesma fração dos erros, quantos acertos entram
na revisão à toa.

| para pegar | 25% dos erros | 50% dos erros | 75% dos erros |
|---|---:|---:|---:|
| absoluta (produção) | **0 à toa** | **26 à toa** | 1.991 à toa |
| margem | 37 à toa | 125 à toa | **1.380 à toa** |

A absoluta ganha no topo da fila, que é onde o revisor de verdade olha; a margem ganha na
cauda, onde ninguém chega. A mediana de confiança de um erro fica igual nas duas (0,215
contra 0,231).

### O motivo, e é ele que vale guardar

**Os dois números respondem perguntas diferentes, e a cadeia faz a da absoluta.**

- distância absoluta: *"isto se parece com alguma coisa que eu já vi?"* — detector de
  **novidade**. Recorte-lixo cai no fundo dela.
- margem: *"o vencedor está claramente à frente?"* — detector de **ambiguidade**. Um
  recorte-lixo pode estar duas vezes mais perto de `a` que de `b` e tirar margem 0,50.

A evidência está numa linha da tabela acima que parece erro de medição e não é: com a
fórmula absoluta e o limiar em **0,00**, a cadeia dá 97,53% — **acima dos 97,19% que o
k-NN acerta sozinho**. Só é possível porque alguns boxes não passam pelo k-NN mesmo com o
limiar no chão: são os de distância acima de `DISTANCIA_MAXIMA`, que a absoluta manda para
o EasyOCR, e lá eles são lidos certo. **O elo seguinte da cadeia existe justamente para o
box que esta base nunca viu**, e é a absoluta quem sabe qual é.

O teste que guarda isso é `test_a_margem_mede_ambiguidade_e_a_producao_mede_novidade`, no
menor caso que o mostra: margem 0,50 e confiança de produção 0,04, no mesmo recorte.

### A base cresceu no meio da medição, e quase virou conclusão errada

A rodada de verificação reproduziu a tabela da F23 em quatro dos seis limiares e ficou
**0,01 ponto** abaixo nos outros dois. Em 10.481 caracteres isso é **um caractere**, e num
lugar suspeito: só nos limiares baixos, que são os que mandam mais boxes ao k-NN.

Não era a reversão. `training_data` passou de **70.755 para 73.900 referências** entre uma
rodada e a outra — "Aprender com Página Atual" grava na base enquanto a medição roda, e o
`CharacterLearner` reconstruiu o cache sozinho, como deve. **Nada na saída dizia isso**: as
duas rodadas se apresentavam com o mesmo número de caracteres e de páginas.

Duas coisas saíram daí. O cabeçalho do instrumento passou a imprimir o tamanho da base, que
é o que torna duas rodadas comparáveis. E a verificação virou **código contra código**, que
não depende de a base estar parada: o corpo anterior de `predict` reescrito contra as
mesmas matrizes, em 4.280 recortes de quatro páginas reais — **zero divergências**. É a
mesma técnica que a F7.2 usou para provar que a conta de matriz não mudava a resposta, e
`test_predict_responde_o_que_respondia_antes_da_f24` a guarda.

O que isso diz das tabelas acima: a comparação margem × absoluta é limpa — as duas rodadas
usaram as mesmas 70.755 referências —, e a varredura de `k` também. A de verificação foi a
primeira a pegar a base nova.

### O que ficou

Produção voltou ao que era, conferido código contra código como acima. Ficaram:

- **`CharacterLearner.vizinhos(crop, k)`** — o `predict_topk` deste elo, que faltava. É o
  que tornou toda a medição possível, e qualquer desempate futuro aqui vai precisar dele
  (a F19 precisou do equivalente na rede).
- **`voto` e `margem_de_confianca`** — as duas alternativas, com as tabelas nos docstrings.
  Nada em produção as chama, e é de propósito: mesma decisão que a F19 tomou com
  `core/altura_relativa.py`. Sem elas `medir_cadeia.py` não reproduz o que decidiu.
- **`DISTANCIA_MAXIMA = 2000.0`** — o `threshold` que era literal na assinatura de
  `predict` virou constante nomeada, com o aviso de que **continua sem tabela** e de que os
  dois limiares do híbrido saem desta escala.
- No instrumento: `--k` para varrer o voto, `--knn` para medir só este elo sem carregar o
  EasyOCR (segundos em vez de minutos), `--combinada` para varrer duas confianças na mesma
  base e no mesmo processo, e a comparação por recall igual entre as três.

**A coluna "já na base" mudou de definição, e a mudança é o assunto da F22 acontecendo com
o instrumento desta fase.** Na F23 ela era `conf >= 0,99`, o que valia enquanto a confiança
fosse distância absoluta. Sob a margem, 0,99 passou a significar "o vencedor está 100x mais
perto que a segunda classe" — verdadeiro em box fácil que a base nunca viu. O número não
teria mudado de nome, só de significado. Agora é a distância crua: zero é cópia exata.

### E a combinação das duas também perde

Ficava a pergunta óbvia: se a absoluta detecta novidade e a margem detecta ambiguidade,
`min(absoluta, margem)` acende nos dois casos. Medida em 10.481 caracteres, com as duas
confianças varridas **no mesmo processo e na mesma base** — o cuidado que esta fase
aprendeu à força:

| limiar | absoluta | `min(absoluta, margem)` |
|---:|---:|---:|
| 0,00 | 97,52% | 97,52% |
| 0,10 | 97,56% | 97,40% |
| 0,20 | **97,64%** | 97,19% |
| 0,30 | 97,61% | 97,05% |
| 0,50 | 97,36% | 96,08% |
| 0,70 | 95,53% | 94,33% |

O melhor de cada uma: **97,64% contra 97,52%**. E na fila de revisão o combinado empata no
topo e fica entre as duas no resto (0 / 66 / 1.613 alarmes falsos contra 0 / 28 / 1.990 da
absoluta e 37 / 124 / 1.379 da margem).

**O motivo é que `min` só sabe baixar.** Ela de fato acende nos dois casos, como a hipótese
dizia — mas acender junto significa despejar na fila e no elo seguinte os boxes ambíguos
que a absoluta já resolvia bem, e a maioria deles está certa. O combinado não soma o melhor
das duas: fica entre elas, herdando a cauda de uma e perdendo o topo da outra.

Com isso a pergunta da confiança do k-NN está fechada nas três formas testáveis sem
mudar o que entra no classificador: absoluta, margem, e o mínimo das duas. **A absoluta
ganha.**

### O que continua aberto

**O 2000 segue sem medição.** Esta fase mediu as alternativas que o dispensariam, não o
valor dele. Ele é o divisor da confiança **e** o corte acima do qual o k-NN não responde —
dois papéis num número só, e nenhum dos dois com tabela.

**Um número serve dois usos, e eles pedem coisas diferentes.** Roteamento quer novidade,
fila de revisão quer as duas coisas. Toda esta fase mediu qual fórmula única serve melhor
aos dois; ninguém mediu ainda o que acontece separando-os — `b.confidence` continuaria a
absoluta, e a fila de revisão passaria a ordenar por outro critério. É a pergunta anterior
a qualquer nova fórmula.

**O limiar do híbrido continua em 0,30, e isto é decisão e não descuido.** Na base de hoje
(73.900 referências, contra 70.755 quando a F23 mediu) o pico da varredura caiu em 0,20 com
97,64%, contra 97,61% de 0,30 — **três caracteres em 10.481**. De 0,10 a 0,30 é platô
(97,56 / 97,64 / 97,61), o 0,30 está dentro dele, e mover uma constante por três caracteres
é afinar contra o ruído de uma base que muda sozinha.

Cobertura: `tests/test_f72_knn.py`, 51 testes (14 novos), mais um em
`tests/test_f23_medir_cadeia.py` para o envelope da confiança combinada. Dois mudaram de
contrato e o registro fica: `test_a_resposta_e_a_mesma_do_laco` virou
`test_a_busca_e_a_mesma_do_laco` — a propriedade que a F7.2 garantia continua valendo, e
quem a expõe agora é `vizinhos`.

**As tabelas desta fase estão em duas bases**, e o cabeçalho do instrumento agora diz
qual: voto, margem e a comparação de roteamento saíram com 70.755 referências; a
combinação e a varredura acima, com 73.900. Cada tabela é internamente comparável, e é o
que importa — nenhuma conclusão aqui compara números de rodadas diferentes.

---

## F25 — A calibração que o retreino apagou, e os dois usos da confiança — CONCLUÍDA

A pergunta de partida era a que a F24 deixou aberta: **um número serve dois usos** —
roteamento da cadeia e ordenação da fila de revisão (F3.2) —, e eles pedem coisas
diferentes. A suspeita concreta: `ui/confidence.py` compara `box.confidence` com 0,90 e
0,70 **sem olhar a fonte**, e as fontes não estão na mesma régua — softmax calibrado na
rede, `1 - distância/2000` no k-NN, a do CRNN no EasyOCR, e a combinação de
`leitura_de_linha.confianca` na linha. Quatro escalas, um par de cortes.

A suspeita está **refutada**, e no caminho apareceu um defeito maior.

### Réguas separadas medem pior, e duas vezes

Se a régua comum custasse revisão, ordenar a fila pela confiança crua e ordená-la pelo
**percentil dentro da própria fonte** — que tira a escala e deixa só a ordem — dariam
curvas diferentes a favor da segunda. Medido em 10.484 caracteres, custo em acertos
revisados à toa para achar cada fração dos erros:

| ordenação da fila | 25% dos erros | 50% dos erros | 75% dos erros |
|---|---:|---:|---:|
| **confiança crua (hoje)** | **392** | **1.971** | **4.645** |
| percentil por fonte | 718 | 2.811 | 5.226 |

Pior em toda coluna, e antes da calibração também era (204/1.140/4.194 contra
206/1.742/5.229). O motivo é o desequilíbrio: a rede responde 98,5% dos boxes, o EasyOCR
0,8%, o k-NN 0,5%, a linha 0,2%. Normalizar por fonte espalha esses punhados pela faixa
inteira de percentil e joga box correto para a frente da fila. **Uma régua comum, mesmo
torta, custa menos que quatro réguas próprias.**

### O que estava errado era a calibração, e ela some sozinha

`model_meta.json` do treino de **14/08 às 00:17** (210 classes) trazia `temperatura: 1.0`.
Não é descuido de ninguém: é o que **todo** treino grava, e a F22 já tinha registrado o
porquê — a temperatura é ajustada para um conjunto de pesos, e herdá-la aplicaria correção
medida sobre outros. O que falta é qualquer coisa que avise, e por isso o modelo rodou o
dia em softmax cru.

O preço, medido na fila de revisão antes e depois de `calibrar_modelo.py --gravar`:

| | mediana da confiança num erro | abaixo de 0,90 | erros pegos |
|---|---:|---:|---:|
| T = 1 (como estava) | **0,9997** | 80 | 29 de 257 |
| **T = 2,1682** | 0,9895 | 421 | **48 de 213** |

Com a confiança em softmax cru, **`precisa_revisao` via 11% dos erros da rede**. A
calibração dobra isso, para 23%. O ECE cai de 0,0276 para 0,0235 em leave-one-page-out, e
o 2,1682 bate com o 2,1916 que a F22 mediu no modelo anterior — dois treinos, mesma família
de correção.

### O `NEURAL_THRESHOLD` se moveu pela segunda vez

| limiar | acerto | rede / k-NN / OCR |
|---:|---:|---|
| 0,40 | 97,32% | 10.405 / 5 / 26 |
| 0,60 | 97,43% | 10.368 / 32 / 63 |
| 0,70 *(era)* | 97,43% | 10.325 / 54 / 86 |
| **0,80** | **97,52%** | 10.168 / 168 / 125 |
| 0,90 | 97,10% | 9.904 / 293 / 245 |

Era 0,8 antes da F22, virou 0,7 nela, e volta a 0,8 aqui. **Isto não é indecisão, é a
propriedade do limiar**: ele compara confiança, a escala da confiança é do conjunto de
pesos, e o valor certo é por modelo. São 9 caracteres de vantagem sobre 0,70 — pouco por si
só; o que decide é a composição apontar no mesmo sentido, com o k-NN vendo 168 boxes em vez
de 54, que é a razão de ele estar na cadeia.

A trava da linha foi remedida junto e **sobreviveu inteira** em 0,70 (97,43%, contra 97,41%
em 0,60 e 97,31% em 0,80).

`medir_cadeia.py` ganhou `--rede`, que faltava: a tabela da F22 era a única das quatro que
o instrumento ainda não reproduzia.

### O que fica aberto, e o primeiro é de processo

**Nada avisa que o modelo está sem calibração.** `NeuralPredictor.load` já tem um canal de
`aviso` e já o usa para o par `.pth`/`.json` trocado. `temperatura == 1.0` num modelo
treinado depois da F1.9 é a mesma classe de problema — nada quebra, nada avisa, e a fila de
revisão fica cega até alguém desconfiar. O remédio barato é o aviso; o certo é o treino
chamar a calibração no fim.

### A linha não esconde erro da revisão — e a suspeita de que escondia era erro de medida

Um box abaixo da trava numa linha lida recebe `confianca(concordam, conf_linha, cf)`, que é
o **máximo** dos dois quando as duas leituras concordam (F17). Uma leitura neural a 0,30
corroborada sobe para ~0,95 e sai da fila de revisão. A pergunta era quantos desses boxes
eram erro que as duas leituras cometeram junto — cada um seria um erro que o revisor deixou
de ver.

Medido nas 10 páginas, comparando a confiança crua da cadeia com a final, box a box, pelo
`precisa_revisao` de produção:

| | boxes | dos quais errados |
|---|---:|---:|
| saíram da fila por corroboração | **2** | **0** |
| entraram na fila por divergência | 0 | 0 |

**Custo zero.** O desenho da F17 se sustenta inteiro, e a razão de a população ser tão
pequena estava disponível o tempo todo: o reforço só alcança box com confiança abaixo da
trava (0,70), e depois do roteamento quase nada chega lá — um box em que a rede hesita é
passado ao k-NN ou ao EasyOCR, e esses respondem com confiança própria alta (mediana do
k-NN num acerto: 1,0000).

**A suspeita vinha de comparar duas medidas de coisas diferentes.** O `calibrar_modelo.py`
punha ~250 boxes abaixo de 0,90 e esta fase media 80 na UI, e a diferença foi atribuída à
linha. Era a **temperatura**: com o modelo calibrado a mesma tabela passou a mostrar 264
boxes abaixo de 0,90. Fica registrado porque é o terceiro caso da mesma família nesta série
— a F23 quase concluiu contaminação onde havia base crescendo, a F24 quase concluiu
reversão infiel pelo mesmo motivo, e aqui dois números de origens diferentes viraram uma
inferência sobre um mecanismo que não estava agindo. **Números de instrumentos diferentes
não se subtraem.**

Conferido no caminho de produção, com `NEURAL_THRESHOLD = 0,80` aplicado: **97,52%**, com
10.168 boxes na rede, 168 no k-NN, 125 no EasyOCR e 23 corrigidos pela linha. É o número que
a varredura previa.

Cobertura: nenhum teste novo. Esta fase não mudou código de produção além de uma constante;
o que ela produziu foram tabelas, e o que as reproduz é `medir_cadeia.py --neural --rede`.

---

## F26 — O aviso que faltava, e o canal que ninguém lia — CONCLUÍDA

A F25 terminou com um item de processo: **nada avisa que o modelo está sem calibração**.
Todo treino grava `temperatura: 1.0` de propósito — a F22 explica por quê —, e o modelo de
14/08 rodou um dia inteiro em softmax cru com a fila de revisão mostrando 11% dos erros em
vez de 23%. Ninguém tinha como saber.

### O canal existia e estava morto

`NeuralPredictor` tem `erro` e `aviso` desde a F7.3. O `erro` é lido — `motivo_do_modelo`
o entrega quando a carga **falha**. O `aviso`, que é para o modelo que **carregou** com
ressalva, não tinha leitor nenhum: nenhum lugar da UI o consultava.

Um aviso que ninguém lê é o mesmo que não avisar, e havia um já escrito ali dentro (o
metadado de formato anterior à F7.3, que não permite conferir o par) que nunca chegou a
ninguém.

### O que entrou

- `AVISO_SEM_CALIBRACAO` em `core/neural_trainer.py`, disparado quando a temperatura
  efetiva é 1,0 — o que cobre tanto o campo gravado pelo treino quanto o metadado anterior
  à F1.9, que não tem o campo. **Acumula** com a ressalva de formato em vez de substituí-la:
  as duas são independentes e um metadado antigo costuma ser as duas coisas.
- `LearningService.aviso_do_modelo()`, irmã de `motivo_do_modelo` para o caso em que a
  carga deu certo.
- `MainWindow._avisar_do_modelo()`, **uma vez por sessão**. Uma vez porque a ressalva é
  sobre o arquivo e não sobre a ação: repetida a cada preenchimento, ela treina o usuário a
  fechá-la sem ler — o mesmo que não avisar, com mais atrito. Modal e não barra de status
  porque o que resolve é uma linha de comando que precisa ser lida inteira. Chamada da
  thread da UI, no começo de `generate_and_fill_neural`, antes do trabalho: é a confiança
  desse caminho que vira `b.confidence`, e saber que a escala não está calibrada muda como
  o usuário lê o resultado que está prestes a gerar.
- **O diálogo de fim de treino diz junto**, porque é o momento em que a temperatura é
  zerada e o único em que o usuário sabe que foi ele que causou. `_modelo_avisado` volta a
  falso ali: a ressalva agora é de outro arquivo.

O recado carrega a medida da F25 — 11% contra 23% — e o comando. Aviso que não diz o que
fazer é ruído.

### O que fica de fora

**Os outros caminhos que carregam a rede ainda não chamam o aviso** — o PDF pesquisável e o
preenchimento por caractere. O gancho é uma linha em cada, e a razão de não estarem aqui é
que só o «Detectar e Preencher (Neural)» foi conferido de ponta a ponta nesta fase.
*(Fechado na F28.)*

**O certo é o treino calibrar sozinho no fim.** O aviso é o remédio barato; enquanto o
usuário puder terminar um treino e sair sem calibrar, a situação da F25 volta a acontecer —
só que agora avisada. O que impede hoje é o custo: `calibrar_modelo.py` roda
leave-one-page-out sobre as 10 páginas rotuladas, e emendá-lo no fim do treino sem medir
quanto isso acrescenta ao tempo é a decisão que falta. *(Fechado na F27: são 20 s.)*

Cobertura: `tests/test_f73_modelo.py`, 26 testes (10 novos) — a ressalva aparece, diz o
comando, convive com a de formato, cala em modelo calibrado, e a janela a mostra uma vez
por sessão. Conferido também contra os arquivos reais: silêncio no `model_meta.json`
calibrado de hoje, e o recado completo no backup de antes da calibração, que tem os mesmos
pesos e `temperatura: 1.0`.

---

## F27 — O treino calibra sozinho no fim — CONCLUÍDA

A F26 fechou dizendo que o aviso é o remédio barato: **enquanto der para terminar um treino
e sair sem calibrar, a situação da F25 volta a acontecer — só que avisada.** O que faltava
para decidir era o custo, e ele nunca tinha sido medido.

### 20 segundos

Medido nas 10 páginas rotuladas, 10.549 caracteres:

| | |
|---|---:|
| colher os logits (segmentar + rede) | 8,6 s |
| ajustar a temperatura | 11,6 s |
| **total** | **20,2 s** |

Contra os minutos de um treino, a pergunta se responde sozinha. Era só medir.

### Onde o código foi parar

A coleta morava dentro de `calibrar_modelo.py` e importava `medir_paginas` — e o núcleo
não pode depender de um script de medição do diretório raiz. Saiu para
`core/calibracao_de_pagina.py`, que é a metade "página real" da calibração;
`core/calibracao.py` continua sendo só a matemática, sem torch nem cv2.

`medir_paginas.py` **reexporta** `paginas_rotuladas`, `MIN_ROTULADOS` e `PASTAS_DE_IMAGEM`
de lá, para os cinco `medir_*.py` que importavam daqui continuarem funcionando — a mesma
solução que `avaliacao_pagina.carregar_box` usa desde a F5.2. E `calibrar_modelo.py` passou
a consumir o núcleo: continua sendo quem **mostra** as tabelas e quem recalibra sem
retreinar.

`NeuralTrainer._calibrar` roda depois do relatório, com `model.eval()` — sem isso o dropout
continuaria ligado e os logits sairiam de um modelo que não é o que a aplicação usa. E
`LearningService.train_neural` passou a soltar o preditor anterior: `load_predictor`
devolve `True` sem reler quando já há um carregado, então sem isso a sessão seguiria com os
pesos velhos e a ressalva da F26 seria a do arquivo recém-substituído.

### A calibração nunca derruba o treino

O modelo já está gravado quando ela roda. Três saídas, e nenhuma perde o treino:

- **sem página rotulada** — o estado normal de quem nunca rotulou uma. Relata, deixa a
  temperatura neutra, e o aviso da F26 acende;
- **exceção qualquer** — relata e segue. O que se perde é a calibração, não os minutos;
- **temperatura na borda do intervalo** — recusada, e este é o caso que a fase encontrou.

### Automatizar tirou o humano que julgava, e isso precisou ser reposto

Na verificação de ponta a ponta — um modelo de 4 classes treinado num tmp, calibrado contra
as páginas reais — a temperatura saiu **10,0000**, que é exatamente o teto do intervalo
`(0,4 – 10,0)`. O modelo não sabia ler aquelas páginas; errava quase tudo com confiança
alta, e a busca foi empurrando a temperatura para o teto tentando amaciá-la.

O valor de borda **não é uma temperatura medida, é o fim da régua** — e gravá-lo seria pior
que não calibrar: com T no teto nada mais passaria pelo `NEURAL_THRESHOLD` e a cadeia
inteira mudaria de comportamento sem ninguém ter pedido.

Antes desta fase isso não podia acontecer calado: quem rodava `calibrar_modelo.py` via as
tabelas e julgava. **Automatizar a rotina tirou esse julgamento**, e `no_limite` é o que o
repõe — a verificação que o humano fazia a olho, agora escrita. É o custo escondido de
automatizar um passo manual, e vale registrar porque não aparece na medição de tempo.

### A suíte denunciou uma dependência que ninguém tinha pedido

Com a calibração no fim do treino, a suíte foi de 82 s para **185 s**: onze testes de treino
passaram a achar as dez páginas rotuladas do diretório de trabalho e a colher logits delas
de verdade. Pior que o tempo é o que isso significava — testes cujo resultado dependia de
arquivos que não estão no repositório e não existem num clone limpo.

O `conftest.py` ganhou uma trava autouse que esvazia `paginas_rotuladas` para a suíte
inteira. O caminho não é desligado, é esvaziado: `_calibrar` roda, não acha página e relata
— que é exatamente o estado de um clone limpo. A suíte voltou a 83 s, e os testes de treino
caíram de ~9 s para ~1,5 s cada, o que revela que eles **já** pagavam a segmentação das
páginas reais sem que isso estivesse escrito em lugar nenhum.

Cobertura: `tests/test_f27_calibracao_no_treino.py`, 11 testes — a temperatura sai de 1,0
quando dá; o treino não cai quando não dá; o metadado sobrevive inteiro à regravação (ele
carrega os dois SHA-256 da F7.3, e remontá-lo de fora é como se perde a amarração); e a
borda é recusada nas duas pontas. Suíte em 1.312.

---

## F28 — O aviso nos outros caminhos — CONCLUÍDA

A F26 pôs o aviso de modelo sem calibração num caminho só, e registrou que os outros
ficaram de fora. São seis os que carregam a rede, e o levantamento corrigiu duas suposições
minhas.

### O nome de um deles engana

`run_general_neural_training` parece treino e é **processamento em lote**: lê imagens e
PDFs com a rede e grava a saída. Estava na lista dos que não precisavam avisar por causa do
nome. Precisa — é output lido pela rede como qualquer outro.

Passaram a conferir o modelo: «Detectar e Preencher (Neural)» (F26), PDF pesquisável,
exportação de livro, extração de recortes, correção do mapa de glifos e o processamento em
lote.

### Um fica de fora, e a razão está escrita nele

`_arbitro_de_corte` roda em **toda** `generate_boxes_opencv`, inclusive nas ações híbrida e
EasyOCR. Ali a rede arbitra corte de glifo colado (F1.5b), não lê texto: a confiança dela
não vira `b.confidence` nem roteia nada, e o recado da F26 fala de fila de revisão e de
roteamento da cadeia — nenhum dos dois é verdade naquele caminho.

A margem da F1.5b **é** uma comparação de confiança, então a calibração provavelmente mexe
na segmentação também. *Provavelmente* — não está medido, e avisar por causa disso seria
afirmar o que não se sabe. Fica registrado como pergunta, não como omissão.

### Um defeito que só apareceu ao espalhar

`_avisar_do_modelo` marcava a sessão como avisada **só quando havia ressalva**. Com o
modelo em ordem a marca nunca era posta, e cada chamada refazia `load_predictor` na thread
da UI — 2 s de janela congelada na primeira, em cada uma das seis ações. Com o aviso num
caminho só isso passava; espalhado por seis, viraria sintoma.

A marca passou a ser posta antes de saber se há ressalva, e o campo mudou de nome —
`_modelo_conferido`, que é o que ele sempre quis dizer. Uma conferência por sessão nos dois
casos.

### O teste que guarda a lista

O erro da F26 não foi escrever o aviso: foi haver um canal sem leitor. Uma lista de
chamadas espalhada por seis métodos tem o mesmo formato de defeito — some uma e ninguém
nota. `test_todo_caminho_que_le_com_a_rede_confere_o_modelo` lê a própria árvore sintática
de `ui/main_window.py`, junta quem chama `load_predictor` sem chamar `_avisar_do_modelo`, e
exige que o conjunto seja exatamente `{_arbitro_de_corte}`. Caminho novo que carregue a
rede e esqueça o aviso quebra o teste; e tirar o árbitro da exceção também, o que obriga
quem o fizer a explicar por quê.

Cobertura: `tests/test_f73_modelo.py`, 28 testes (2 novos). Suíte em 1.314.

---

## F29 — Quanto a calibração mexe na segmentação — MEDIDA, e mexe quase nada

A F28 deixou a pergunta escrita: o árbitro de corte (F1.5b) endossa o corte quando
`menor > p_inteiro + margem`, o que é uma **comparação de confiança** — e a temperatura
mexe em toda confiança. A `margem = 0,30` foi afinada na F1.5b, antes de existir
calibração. Se o ótimo dela tivesse se movido, seria o quarto número desta série afinado
contra uma escala que deixou de existir, junto do `NEURAL_THRESHOLD`, das duas travas da
linha e do `learner_threshold`.

`medir_paginas.py` ganhou `--temperatura`, que força a do árbitro em vez de usar a gravada.
Era o que faltava — o instrumento já media segmentação e já varria a margem.

### No ponto de produção, três cortes

Nas 10 páginas rotuladas, ~12.000 caracteres, modo `arbitrado` com a margem de produção:

| | T = 1 | T = 2,1682 |
|---|---:|---:|
| F1 | 94,9 | **95,0** |
| espúrios | 339 | 344 |
| cortes bons | 14 | 17 |
| cortes falsos | 1 | 2 |

### E o ótimo da margem não se move

| margem | F1 (T = 1) | F1 (T = 2,1682) | bons/falsos (T=1) | bons/falsos (T=2,17) |
|---:|---:|---:|---|---|
| **0,00** | **95,1** | **95,1** | 43 / 14 | 45 / 16 |
| 0,15 | 94,9 | 95,0 | 19 / 4 | 26 / 5 |
| 0,30 *(produção)* | 94,9 | 95,0 | 14 / 1 | 17 / 2 |
| 0,50 | 94,8 | 94,9 | 3 / 0 | 10 / 0 |

O ranking é o mesmo nas duas colunas, e o ótimo cai no mesmo lugar. **A `margem = 0,30` não
é um limiar invalidado pela calibração** — é um número insensível a ela, que era a terceira
possibilidade e a que eu não tinha nomeado.

A razão de a superfície ser tão pequena está na própria tabela: o árbitro é conservador de
saída. O modo `local`, sem ele, faz **192 cortes falsos**; o `arbitrado` faz 1 ou 2. Sobra
pouco para a temperatura mover.

### O mecanismo que eu previ está errado, e não o substituo por outro

A previsão era: a temperatura comprime as confianças, a folga `menor - p_inteiro` encolhe,
e contra uma margem absoluta menos cortes passam. O medido é o contrário — **calibrado
endossa mais cortes em todas as quatro margens** (43→45, 19→26, 14→17, 3→10), sem exceção.

Tentei medir a folga direto e a reconstrução do laço de candidatos saiu divergente da
produção (zero candidatos onde ela acha vários). Parei ali: depurar uma cópia do pipeline
para explicar 0,1 de F1 é o erro que a F1.5 registrou, com menos motivo. **A direção está
medida e o mecanismo não está verificado**, e é assim que fica escrito — foi a quarta vez
nesta série que uma aritmética plausível não sobreviveu à medida.

### Uma pergunta que esta medição abriu e não é a dela

`margem = 0,00` mede **melhor** que a de produção nas duas temperaturas — 95,1 contra 94,9
e 95,0. São +0,2 de F1, e a troca é explícita: 48 espúrios a mais e 13 cortes falsos a mais,
comprados com 0,5 ponto de recall.

Isso contradiz a decisão da F1.5b, cujo docstring diz com todas as letras que "a margem é
0,30, e quem decidiu foi o F1 da página". O F1 da página agora aponta para 0,00. Entre uma
medida e outra mudaram o dpi (F15), o modelo (210 classes) e a base — então não é a mesma
pergunta feita duas vezes, é uma pergunta velha cujo terreno se moveu. **Fica registrada,
não resolvida**: é fase própria, com a varredura mais fina e a conta de espúrio contra
recall feita à parte, e não um número para mudar de passagem no fim de outra fase.

Cobertura: nenhum teste novo — a fase não mudou código de produção, só acrescentou uma
opção ao instrumento. Reproduzir:
`python medir_paginas.py --temperatura 1.0 --margens 0.0 0.15 0.30 0.50`.

---

## F30 — A margem 0,00, medida direito — MEDIDA, e o 0,30 fica

A F29 encontrou de passagem que `margem = 0,00` media +0,2 de F1 sobre a de produção, e
registrou que aquilo era fase própria e não número para mudar no fim de outra. Esta é a
fase. **A conclusão é que a margem fica em 0,30**, e as três medidas que decidem estão
abaixo — cada uma enfraquecendo mais a hipótese que a anterior.

### A varredura fina transforma o pico em platô

A F29 varreu quatro pontos e 0,00 apareceu 0,2 acima. Com oito, na temperatura de produção:

| margem | recall | precisão | F1 | espúrios | bons | falsos |
|---:|---:|---:|---:|---:|---:|---:|
| 0,00 | 96,4% | 93,8% | **95,1** | 392 | 45 | 16 |
| 0,05 | 96,2% | 93,8% | 95,0 | 383 | 39 | 11 |
| 0,10 | 96,1% | 93,8% | 95,0 | 370 | 32 | 8 |
| 0,15 | 96,1% | 93,9% | 95,0 | 358 | 26 | 5 |
| 0,20 | 96,0% | 94,0% | 95,0 | 354 | 25 | 3 |
| 0,25 | 96,0% | 94,0% | 95,0 | 350 | 21 | 3 |
| **0,30** *(produção)* | 95,9% | 94,0% | 95,0 | 344 | 17 | 2 |
| 0,40 | 95,8% | 94,0% | 94,9 | 342 | 13 | 2 |

De 0,05 a 0,30 o F1 não se mexe. A vantagem de 0,00 cai de 0,2 para **0,1**, e o que
parecia pico é a borda de um platô — a mesma armadilha da grade grossa que a F22 registrou
no `NEURAL_THRESHOLD`.

### Em caracteres, a troca fica explícita

Com os 10.613 caracteres rotulados de denominador, `0,00` contra `0,30`:

| | |
|---|---:|
| caracteres a mais lidos certo | **~+53** |
| boxes espúrios a mais para apagar | **+48** |
| glifos partidos ao meio a mais | **+14** |

(O recall vem arredondado em uma casa, então os 53 carregam ~±11 de folga.)

**Os três não custam a mesma coisa ao revisor, e o F1 os pesa igual.** Box espúrio é lixo
visível: aparece na lista, é apagado. Box faltando deixa buraco visível. **Corte falso é o
pior dos três e é o único calado** — um `m` partido vira `r`+`n`, que continua lendo como
palavra e passa pela revisão inteira sem acender nada. Comprar 53 caracteres com 14 leituras
silenciosamente erradas não é o negócio que o F1 anuncia.

### E a conferência por página desfaz o resto

| página | F1 (0,00) | F1 (0,30) | Δ | falsos (0,00) |
|---|---:|---:|---:|---:|
| Kasparov 0013 | 97,4 | 97,0 | +0,4 | 0 |
| Kasparov 0014 | 95,4 | 95,8 | **−0,4** | 1 |
| Kasparov 0020 | 92,6 | 92,2 | +0,4 | 1 |
| Kasparov 0022 | 91,8 | 92,0 | −0,2 | 0 |
| Kasparov 0033 | 93,9 | 94,1 | −0,2 | 2 |
| Kasparov 0057 | 96,0 | 95,9 | +0,1 | 1 |
| Kasparov 0128 | 93,4 | 93,2 | +0,2 | 3 |
| Aagaard | 96,8 | 96,8 | 0,0 | 0 |
| Aagaard pg11 | 95,2 | 94,7 | +0,5 | 1 |
| Kasparov 0108 | 96,4 | 96,6 | −0,2 | **7** |

**Ganha em 5, empata em 1, perde em 4.** O +0,1 do total é a soma de oscilações nos dois
sentidos, não um efeito.

O padrão de comparação está na F15, que mudou o dpi de 200 para 300: *"aparece em **todas**
as sete páginas do Kasparov: +4,1 +3,6 +3,1 +2,8 +2,9 +2,0 +2,0. Nenhuma exceção."* É essa
a cara de um ganho real. Cinco a quatro é a cara de uma moeda.

Repare também na última linha: os 16 cortes falsos de `0,00` não estão espalhados — **7
saem de uma página só**. O modo agressivo não erra pouco em toda parte, erra muito onde a
digitalização é ruim, que é justamente onde o revisor já tem mais trabalho.

### O que fica

Nada em produção mudou. `medir_paginas.py --margens` já existia e a F29 lhe deu
`--temperatura`; esta fase não precisou de código novo, só de rodar a grade fina e olhar
por página.

**A decisão de a F1.5b usar o F1 da página continua valendo, mas o número não é mais o
argumento.** Ela escolheu 0,30 porque o F1 apontava para lá; hoje o F1 é plano no intervalo
inteiro, e o que sustenta o 0,30 é a assimetria entre os três modos de errar — o único
critério que o F1 não sabe expressar. Se alguém reabrir isto, o que decide não é uma
varredura mais fina ainda: é medir **quanto custa um corte falso na revisão**, que ninguém
mediu.

Cobertura: nenhum teste novo, nenhuma mudança de produção. Reproduzir:
`python medir_paginas.py --margens 0.0 0.05 0.10 0.15 0.20 0.25 0.30 0.40`.

---

## F31 — Quanto custa um corte falso na revisão — MEDIDA

A F30 fechou dizendo que o F1 da página não decide mais a margem do árbitro — ele é plano
de 0,05 a 0,30 —, e que quem sustenta o 0,30 é a **assimetria entre os três modos de
errar**, que o F1 não sabe expressar. Deixou escrito que quem reabrisse aquilo não
precisaria de grade mais fina: precisaria medir o custo de um corte falso. É esta fase, e
o argumento da F30 passa a ter número.

### A moeda é o erro que ninguém vê

Um box a mais é caro se o revisor tem de caçá-lo, e barato se ele salta. A página já tem
duas redes, e elas pegam coisas diferentes:

1. **`precisa_revisao`** (F3.2) — box vazio ou de confiança baixa. É cega para o erro
   confiante, e a F14 mediu que a confiança mediana de um erro é alta;
2. **o léxico** (F9) — palavra de prosa fora do dicionário, **independente da confiança**.
   Foi construído exatamente para o que a primeira não vê.

Um erro que escapa das duas chega ao texto final e ninguém o vê. É esse que se conta.

### Cada corte falso custa ~0,8 erro invisível

| margem | cortes falsos | pedaços | errados | na fila | só léxico | **invisíveis** |
|---:|---:|---:|---:|---:|---:|---:|
| 0,00 | 16 | 39 | 34 | 9 | 12 | **13** |
| **0,30** *(produção)* | 2 | 5 | 5 | 1 | 2 | **2** |

Um corte falso gera ~2,4 pedaços, ~2,1 deles errados, e **~0,8 deles atravessa as duas
redes**. Não é um box a mais para apagar: é caractere errado no texto final, calado.

### O léxico pega mais que a confiança, num caso que ele não previa

12 pegos só pelo léxico contra 9 pela fila de revisão. A F9 foi construída sobre a medida
de que "1,000 é a confiança mediana de um erro", e aqui está o mesmo mecanismo num caso que
ela não tinha em vista: glifo partido gera pedaço que o modelo lê **com confiança alta** —
e que quebra a palavra. É a rede certa para o defeito certo, por acidente de projeto.

E ainda assim 13 escapam das duas: os pedaços que caem em notação, onde o léxico não opina
por contrato, e os que formam palavra válida. O `m` → `rn` do argumento da F30 deixou de ser
suposição.

### O box espúrio

| margem | espúrios | na fila | só léxico | **invisíveis** |
|---:|---:|---:|---:|---:|
| 0,00 | 392 | 73 | 73 | **246** |
| **0,30** | 344 | 59 | 53 | **232** |

"Invisível" aqui quer dizer outra coisa, e vale distinguir: o espúrio não corrompe uma
leitura certa, ele **acrescenta** um caractere de lixo que a filtragem não acende — quem lê
o texto o encontra, quem confia no filtro não. Já o pedaço de corte falso substitui um
caractere certo por um plausível.

### O saldo, na moeda certa

De `0,00` para `0,30`: **−11 erros invisíveis de corte falso e −14 espúrios invisíveis**.

> **Correção (F32): a soma abaixo está errada, e a conclusão dela também.** As duas
> contagens **se sobrepõem** — um corte falso parte um glifo em k pedaços, no máximo um
> casa com o rótulo e os outros k−1 *são* boxes espúrios, já contados na outra coluna.
> Somá-las conta o mesmo pedaço duas vezes. Medido na F32, sobre caractere rotulado a
> margem agressiva perde **1**, não 11. O parágrafo fica como estava, com esta ressalva,
> porque apagá-lo esconderia o erro em vez de registrá-lo.

Ponha ao lado da conta da F30, que era `0,00` comprando ~+53 caracteres lidos certo:

    a favor de 0,00     ~+53 caracteres certos
    contra              +25 erros que ninguém vê

**A margem fica em 0,30, agora por medida e não por argumento.**

### O que continua sem medida, e é metade da conta

Os +53 caracteres estão contados em "certo contra errado", não em "visível contra
invisível". Se as leituras que eles substituem já eram pegas pelas duas redes — e há razão
para suspeitar que sim, porque colagem lida como um caractere só costuma quebrar a palavra
—, então o ganho é de trabalho poupado e a perda é de erro permanente, que são moedas
diferentes. **Medir o lado do ganho com o mesmo instrumento é o que fecharia a conta**, e
não foi feito.

E o custo em **tempo** de consertar um box não é mensurável aqui: isso é medida com gente,
não com script. O que esta fase estabelece é que não precisa de cronômetro para escolher
entre duas margens — basta contar o que fica errado sem ninguém saber.

Cobertura: `medir_corte_falso.py`, instrumento novo. `avaliacao_pagina.pais_por_categoria`
passou a devolver os boxes de cada categoria e `classificar_cortes` virou a contagem dele —
uma classificação só, para as duas não poderem divergir. Reproduzir:
`python medir_corte_falso.py --margens 0.0 0.30`.

---

## F32 — O lado do ganho, e um erro de aritmética meu na F31 — MEDIDA

A F31 mediu o custo de uma margem agressiva em **erro invisível** e o ganho em **caractere
certo**, e fechou dizendo que são moedas diferentes e que medir o ganho na mesma moeda
fecharia a conta. Fechou — e virou o sinal.

### Como se conta o mesmo caractere nas duas margens

Cada caractere **rotulado** ganha um destino em cada margem, e o índice do rotulado não muda
entre elas: é a mesma verdade lida do mesmo `.box`. Isso permite seguir o mesmo caractere de
uma margem para a outra.

    certo               saiu certo
    errado_visivel      saiu errado, e a fila de revisão ou o léxico acenderam
    errado_invisivel    saiu errado e nada acendeu
    sem_box             não saiu

**`sem_box` não é invisível**, e a distinção importa: falta deixa buraco, e buraco se vê
lendo. O único destino que chega ao fim parecendo certo é `errado_invisivel`.

### O que muda de 0,30 para 0,00

| ganhos — passaram a sair certos | 48 |
|---|---:|
| vinham de `errado_visivel` | 14 |
| vinham de **`errado_invisivel`** | **11** |
| vinham de `sem_box` | 23 |

| perdas — deixaram de sair certos | **1** |
|---|---:|
| viraram `errado_invisivel` | 1 |

**Saldo de erro invisível sobre caractere rotulado: −10, a favor de `0,00`.**

Sobre o texto de verdade, a margem agressiva ganha 48 e perde **um**.

### O erro da F31

A F31 somou os `−11` de corte falso com os `−14` de espúrio e escreveu "+25 erros que
ninguém vê" contra o `0,00`. **As duas contagens se sobrepõem.** Um corte falso parte um
glifo em k pedaços; no máximo um casa com o rótulo, e os outros k−1 **são** boxes espúrios,
já contados na outra coluna. Dos 39 pedaços que os 16 cortes falsos geram, ~16 são pareados
e ~23 são espúrios — somar as colunas conta o mesmo pedaço duas vezes.

A tabela de transição mostra o tamanho real: **uma** regressão de caractere rotulado, não
onze. O parágrafo da F31 ficou onde estava, com a ressalva ao lado, porque apagá-lo
esconderia o erro em vez de registrá-lo.

### O que a conta corrigida diz

| | 0,00 contra 0,30 |
|---|---|
| caracteres rotulados | **+47 certos**, e **−10** erros invisíveis |
| boxes espúrios | **+48**, dos quais **+14** não acendem nada |

Não é "+53 visíveis contra +25 invisíveis". É **texto melhor, lixo a mais**: 47 caracteres a
mais saem certos e 10 erros calados somem, ao preço de 14 caracteres de lixo a mais que o
filtro não acusa.

### E mesmo assim a margem não muda hoje

A F30 recusou o `0,00` por três razões. A terceira — a assimetria entre os modos de errar —
**está refutada por esta medição**: ela apontava para o `0,30` e aponta para o `0,00`. As
outras duas continuam de pé, e uma delas é o obstáculo:

- o F1 é plano de 0,05 a 0,30 — continua verdade, e agora sabe-se por quê: ele desconta em
  precisão os 48 espúrios que a recall ganha;
- **o teste por página deu 5 a 4** — e a métrica nova ainda não passou por ele. Foi a F30
  que estabeleceu esse padrão, citando a F15 ("nenhuma exceção"), e trocar um número de
  produção sem aplicá-lo à medida que decide seria abandonar o critério justamente quando
  ele passou a incomodar.

**A próxima medida é a quebra por página da tabela de transição.** Se os 48 ganhos e a
única perda estiverem espalhados, o `0,30` cai — e cai com número, que é como as outras
constantes desta série caíram. Se estiverem concentrados numa digitalização ruim, fica.

### O que esta série vem mostrando sobre medir

É a quinta vez em dez fases que uma conclusão minha não sobreviveu à medida seguinte, e a
segunda em que o defeito não foi o dado e sim **o que eu fiz com ele** — na F25 subtraí
números de instrumentos diferentes, aqui somei contagens que se sobrepunham. As duas passam
despercebidas do mesmo jeito: a aritmética fecha, as unidades parecem iguais e o resultado é
plausível. O que as pega é olhar o que cada linha **conta**, uma de cada vez, antes de
juntá-las.

Cobertura: `medir_corte_falso.py` ganhou `estado_por_rotulo` e a tabela de transição.
Reproduzir: `python medir_corte_falso.py --margens 0.0 0.30`.

---

## F33 — A margem do árbitro cai para 0,00 — CONCLUÍDA

Quatro fases para trocar um número. A F30 recusou o `0,00` por três razões, a F32 refutou
uma delas e a segunda caiu aqui: **a quebra por página**, que era o obstáculo que a própria
F32 nomeou.

### O 0,00 ganha em 7 de 10 e não perde em nenhuma

| página | ganhos | perdas | saldo | invisível |
|---|---:|---:|---:|---:|
| Kasparov 0013 | 15 | 0 | **+15** | −2 |
| Kasparov 0014 | 0 | 0 | 0 | 0 |
| Kasparov 0020 | 7 | 0 | +7 | −1 |
| Kasparov 0022 | 2 | 0 | +2 | −1 |
| Kasparov 0033 | 0 | 0 | 0 | 0 |
| Kasparov 0057 | 4 | 1 | +3 | +1 |
| Kasparov 0128 | 7 | 0 | +7 | −2 |
| Aagaard | 0 | 0 | 0 | 0 |
| Aagaard pg11 | 10 | 0 | **+10** | −4 |
| Kasparov 0108 | 3 | 0 | +3 | −1 |

Sete ganham, três empatam, **nenhuma perde**. A única regressão de caractere em dez páginas
está numa que ganha quatro.

Compare com o 5 a 4 que fez a F30 recusar: aquele era o F1, que desconta em precisão os
espúrios que a recall ganha. Sobre o texto — caractere rotulado — não há empate técnico.

### E o meio não domina as pontas, que era o risco de repetir a F29

A F32 fechou dizendo que o `0,30` cai mas não necessariamente para `0,00`, porque a
varredura da F30 sugeria que `0,10` pudesse dar quase o mesmo com metade dos cortes falsos.
Medido, contra a de produção:

| margem | saldo do texto | saldo invisível | ganha em | cortes falsos |
|---:|---:|---:|---:|---:|
| **0,00** | **+47** | **+4** | **7 de 10** | 16 |
| 0,05 | +33 | +7 | 6 de 10 | 11 |
| 0,10 | +22 | +6 | 6 de 10 | 8 |
| 0,15 | +14 | +6 | 5 de 10 | 5 |
| 0,30 *(era)* | 0 | 0 | — | 2 |

O `0,00` ganha em toda coluna, inclusive na do erro invisível — os −10 que ele tira sobre
caractere rotulado compensam quase todo o +14 que ele acrescenta em espúrio que não acende.
O meio não domina: rende menos texto **e** mais erro calado.

"Saldo invisível" soma os dois lados sem sobrepô-los, que é a correção da F32.

### O critério foi fixado antes do resultado, e isso foi o que sustentou a decisão

Está escrito na conversa antes de a medição rodar: vence o melhor saldo de texto sem perder
em página nenhuma, e havendo empate fica a margem maior, porque menos corte falso é menos
risco fora destas dez páginas.

Não houve empate. Se tivesse havido, o `0,15` levaria — e é por isso que fixar o critério
antes tem valor: das quatro fases desta sequência, três terminaram invertendo a leitura da
anterior, e a única defesa contra escolher a régua pelo resultado é escolhê-la antes de
tê-lo.

### O risco que o número carrega, e que a medida não cobre

O `0,00` sobe os cortes falsos de **2 para 16**, e a F30 já tinha registrado que **7 dos 16
saem de uma única digitalização ruim**. Nestas dez páginas o saldo é francamente positivo;
num livro pior escaneado, a conta pode virar — e cada corte falso custa ~0,8 erro que
ninguém vê (F31).

Está escrito no comentário da constante, junto de qual instrumento responde: se aparecer um
livro assim, `medir_corte_falso.py` diz quanto, e é aqui que se mexe.

### O que ficou de dívida no instrumento

`medir_pagina` e `estado_por_rotulo` segmentam a mesma página cada um, então cada margem
custa duas passadas em vez de uma — 100 segmentações nesta rodada em vez de 50. O resultado
é o mesmo e o tempo é o dobro. Fica anotado porque é desperdício que se acumula em
instrumento feito para ser rodado muitas vezes.

Cobertura: `tests/test_f15b_arbitro.py`, com `test_margem_padrao_e_a_medida` guardando o
valor novo **e a régua nova** — o docstring dele dizia "0,30 foi o pico de F1", que a F30
mediu não ser mais verdade. Suíte em 1.314.

---

## F34 — A segmentação duplicada do instrumento — CONCLUÍDA

A F33 fechou anotando uma dívida: `medir_pagina` e `estado_por_rotulo` segmentavam a mesma
página cada um, então cada margem custava duas passadas em vez de uma — 100 segmentações
naquela rodada em vez de 50.

`medir_pagina` passou a devolver `(contas, estado por rótulo)` de uma segmentação só, e
`_estado_por_rotulo` virou função pura do que já foi calculado: recebe `filhos`,
`rotulados`, os pares e as suspeitas, em vez de refazer o caminho a partir da imagem.

### O que estava em jogo não era o tempo

As duas funções partilhavam a intenção e não o código. Cada uma segmentava, classificava e
montava as suspeitas do léxico por conta própria — **duas cópias do mesmo caminho, que
podem divergir sem nada quebrar**. É o defeito que a F1.5 registrou e que fez
`medir_paginas.py` passar a chamar o separador de produção em vez de uma cópia dele.

E aqui isso não era hipótese ociosa: foi com esses números que a **F33 mudou uma constante
de produção**. Se as duas metades tivessem discordado, a decisão teria saído de uma média
de duas medições diferentes sem ninguém saber.

Por isso a verificação foi a mesma da F7.2 — comparar a saída inteira, e não confiar em que
"deve dar no mesmo":

    diff da rodada de 5 margens, antiga contra nova:
    131a132
    >

Uma linha em branco a mais no fim. **Todo número idêntico**, incluindo as dez linhas da
quebra por página, que é onde uma divergência apareceria primeiro. Os números da F33 ficam
de pé, agora conferidos por duas implementações independentes em vez de uma.

### O custo, medido e não estimado

| | 2 margens, 10 páginas |
|---|---:|
| antes | 58,8 s |
| **depois** | **32,5 s** |

1,81×, e não 2× exatos porque ~6 s são custo fixo — carregar o modelo, o léxico e os
imports. Cada margem custa ~13 s de trabalho real. A varredura de cinco margens da F33,
que era o caso pesado, sai agora em 1m17s.

Não é ganho grande em segundos, e é ganho em outra coisa: o instrumento passou a ter **um**
caminho onde tinha dois, e a rodada da F33 deixou de ser cara o bastante para desencorajar
refazê-la. Instrumento que ninguém quer rodar de novo é instrumento que envelhece com
número velho dentro.

Cobertura: nenhum teste novo — a garantia desta fase é a saída idêntica, e ela é do tipo
que se confere rodando, não afirmando. Reproduzir:
`python medir_corte_falso.py --margens 0.0 0.05 0.10 0.15 0.30`.

---

## F35 — O `DISTANCIA_MAXIMA`, o último sem tabela — MEDIDO, e está certo

Era o que sobrava da lista: o único limiar do projeto sem medição ao lado. A F24 o nomeou e
registrou que continuava sem tabela; a F35 mede, e **o 2.000 fica** — desta vez por número.

### Ele nunca foi um parâmetro independente

A confiança é `1 - d/D` e o roteamento é `conf > t`. Isso é `d < D(1-t)`: **os dois números
têm um grau de liberdade só**, e quem decide é o corte em distância. O projeto vinha
carregando dois limiares onde um bastava, e nenhuma fase tinha notado.

O que `D` controla sozinho é o **teto**: com `t` em [0, 1), o corte nunca passa de `D`. É
por isso que a varredura da F23 — que percorreu `t` de 0,00 a 0,95 com `D = 2.000` — não
podia enxergar esta região: `t = 0` já é o limite, e ele dá corte 2.000.

### Onde o k-NN deixa de ganhar

Medido em 10.484 boxes, k-NN e EasyOCR nos **mesmos** boxes, por distância crua:

| distância | boxes | k-NN | EasyOCR | ganha |
|---|---:|---:|---:|---|
| 0 – 200 | 8.026 | 99,1% | 75,7% | k-NN |
| 200 – 500 | 733 | 97,4% | 80,2% | k-NN |
| 500 – 800 | 1.090 | 98,5% | 64,6% | k-NN |
| 800 – 1.000 | 281 | 98,9% | 55,2% | k-NN |
| 1.000 – 1.200 | 133 | 86,5% | 51,9% | k-NN |
| 1.200 – 1.400 | 85 | 74,1% | 45,9% | k-NN |
| 1.400 – 1.700 | 33 | 63,6% | 48,5% | k-NN |
| **1.700 – 2.000** | 34 | **29,4%** | 52,9% | **EasyOCR** |
| 2.000 – 2.500 | 31 | 25,8% | 32,3% | EasyOCR |
| 2.500 – 3.000 | 44 | 9,1% | 25,0% | EasyOCR |
| 3.000 – ∞ | 24 | 4,2% | 37,5% | EasyOCR |

**A travessia é em ~1.700.** É a tabela mais informativa desta série inteira, e é a única
que não depende de escala nenhuma: sobrevive a qualquer mudança futura nos dois limiares,
porque está em unidade de distância.

### E a varredura confirma o teto

| `D` | acerto | corte efetivo | k-NN | EasyOCR |
|---:|---:|---:|---:|---:|
| 800 | 93,52% | 560 | 9.017 | 1.330 |
| 1.400 | 97,18% | 980 | 10.103 | 380 |
| **2.000** | **97,65%** | **1.400** | 10.348 | 156 |
| 3.000 | 97,62% | 2.100 | 10.420 | 90 |
| 5.000 | 97,43% | 3.500 | 10.512 | 2 |
| 20.000 | 97,43% | 14.000 | 10.514 | 0 |

O `20.000` está aí de propósito: com ele o k-NN responde **tudo**, e a cadeia cai 0,22
ponto. O teto está fazendo trabalho, e o trabalho é o certo — ele corta depois da travessia,
então não tira do k-NN nada que ele ainda ganhasse, e o corte efetivo de produção (1.400)
cai dentro da região em que o k-NN ganha.

O critério estava fixado antes de rodar: *"se o acerto parar de subir em corte ≤ 2.000, o
2.000 é teto adequado e nada muda"*. Parou.

### Uma folga que a tabela mostra e que não vale perseguir

A travessia é em 1.700 e o corte está em 1.400 — a faixa 1.400–1.700 tem **33 boxes** em que
o k-NN faz 63,6% contra 48,5%. Levá-los ao k-NN valeria ~5 caracteres em 10.484, e cairia
dentro do platô que a F23 já mediu no `learner_threshold`. É a mesma ordem de grandeza que a
F24 recusou perseguir quando 0,20 media três caracteres acima de 0,30.

### O que fica registrado e não foi feito

`DISTANCIA_MAXIMA` é **valor padrão de argumento** em `predict`, então liga em tempo de
`def`: editar o arquivo funciona, trocar o global em tempo de execução não. Todas as outras
constantes ajustáveis do projeto são lidas na chamada (`BoxService.MARGEM_ARBITRO` é o
modelo). Foi por isso que a medição precisou de `_MemoComDistancia` no instrumento em vez de
trocar o global. É inconsistência pequena e não foi mexida aqui: esta fase concluiu que nada
muda em produção, e emendar uma alteração de código numa fase dessas é o jeito de ela passar
sem ser lida.

Cobertura: nenhum teste novo. `medir_cadeia.py` ganhou `--distancia` e a tabela por
distância crua. Reproduzir:
`python medir_cadeia.py --distancia 800 1400 2000 3000 5000 20000`.

---

## F36 — O filtro de glifo que ninguém alimentava — MEDIDO, e ele custa

A F17 escreveu no cabeçalho do módulo que a linha com figurina (♗, ♘) ou ligadura fica de
fora do modo bloco, e como: "o módulo não sabe disso sozinho: quem chama informa por
`alfabeto`". **Ninguém informava.** As três ações de preenchimento chamavam `ler_pagina`
sem o parâmetro, e o laço do PDF pesquisável chamava `em_bloco` sem ele. A exclusão estava
escrita, testada e morta — a mesma forma do `aviso` da F26.

E passar o parâmetro não teria resolvido. `em_bloco` olhava `b.char`, e numa ação «Detectar
e Preencher» isso está vazio em **todos** os boxes: a ação acabou de gerá-los e ainda não
leu nada. Quem sabe o que a linha tem é a leitura da âncora, que o `ler_pagina` calcula
três linhas antes de decidir e jogava fora. Consertado o contrato, dava para medir.

### Alimentado, o filtro mede pior — nos dois caminhos

10.514 caracteres em 10 páginas rotuladas, 84.741 referências. As três corridas de cada
tabela saem do **mesmo processo e da mesma base** — o cuidado que a F24 aprendeu à força —,
e "consertos" e "quebras" são contra a corrida sem filtro, caractere a caractere. As 441
linhas são as que chegam a ser lidas em bloco, já descontados girado, negativo e linha de
um box só.

**Caminho híbrido** (`medir_cadeia.py --alfabeto`), trava em 0,30:

| filtro | linhas tiradas | acerto | trocados pela linha | consertos | quebras |
|---|---:|---:|---:|---:|---:|
| nenhum | 0 | **97,65%** | 10 | — | — |
| estreito (figurina + ligadura) | 207 de 441 (46,9%) | 97,64% | 3 | 0 | 1 |
| largo (fora do alfabeto) | 224 de 441 (50,8%) | 97,64% | 3 | 0 | 1 |

A causa da exclusão, no largo: **188 figurina, 19 ligadura, 17 outro símbolo**.

**Caminho neural** (`--neural --alfabeto`), trava em 0,70:

| filtro | linhas tiradas | acerto | trocados pela linha | consertos | quebras |
|---|---:|---:|---:|---:|---:|
| nenhum | 0 | **97,58%** | 24 | — | — |
| estreito (figurina + ligadura) | 236 de 441 (53,5%) | 97,54% | 10 | 1 | 6 |
| largo (fora do alfabeto) | 246 de 441 (55,8%) | 97,53% | 9 | 1 | 7 |

A causa da exclusão, no largo: **172 figurina, 64 ligadura, 10 outro símbolo**.

No híbrido é empate técnico com uma quebra, e a coluna que explica é `trocados`: com a
trava em 0,30 a linha encosta em **10 boxes de 10.514**, então qualquer filtro sobre ela
mede quase nada. O neural é onde a pergunta tem resposta — a trava em 0,70 deixa a linha
agir em 24 boxes, e ali o filtro **quebra 6 para consertar 1**. As duas tabelas concordam
no sinal; a segunda tem tamanho para ser lida.

### O motivo: o `_alinhar` já absorvia o deslocamento

A hipótese da F17 é explícita: um glifo fora do alfabeto faz a linha "ler outra coisa no
lugar dele — o que desloca o alinhamento em vez de errar um caractere só". **Ele desloca, e
o deslocamento não sobrevive: o `_alinhar` absorve.**

É para isso que a distância de edição entrou na F17. O desvio mais comum já era a linha
trazer caractere **a mais** que boxes — +1 em 34 das 275 linhas medidas, +2 em 29 —, e um
glifo que o reconhecedor troca por duas letras é exatamente esse caso. A F17 mediu o
remédio e o instalou; a mesma F17 escreveu a seção que diz que o remédio não basta. As duas
coisas não foram confrontadas até aqui.

O que o filtro faz de fato é jogar fora as correções do **resto** da linha. Uma linha de
notação tem uma figurina e dez outros caracteres, e são esses dez que a leitura por linha
conserta.

### O estreito também não salva, e ele existia por um argumento correto

A primeira tentativa foi o filtro largo — tudo fora dos 96 caracteres do `english_g2`. Ele
tira metade das linhas, o que parecia largo demais: `±`, `½`, travessão e aspa curva também
estão fora do alfabeto, e saem do reconhecedor como **um** caractere errado numa casa
certa, que é o erro comum e não deslocamento. Daí o estreito: só o que gasta um número de
casas diferente de um, com a ligadura entrando por `len(char) > 1` — `fi` é feito de duas
letras que estão no alfabeto e mesmo assim desloca.

O argumento está certo e **não é o que movia o número.** As linhas de causa nas duas tabelas
acima dizem por quê: no híbrido os `±` explicam **17 de 224** exclusões, e no neural **10 de
246**. O que enche o filtro é figurina, e essa o estreito tira igual. Todo o refinamento
valeu 17 linhas no híbrido, 10 no neural, e um caractere de acerto.

### Quase metade das linhas, e não 19%

A F17 estimou 19% das linhas com glifo fora do alfabeto. Medido pela âncora, são **46,9%**
no híbrido e **53,5%** no neural, das 441 que chegam a ser lidas em bloco. A estimativa
antiga era de contagem de rótulo; esta é do que a cadeia lê, que é o que o filtro veria.

Isto muda o tamanho da aposta e não o sinal dela: filtrar metade das linhas seria a maior
mudança de comportamento desta série, e ela custa.

### O que ficou

Produção voltou ao que era — nenhum caminho passa filtro de glifo. Ficaram:

- **`em_bloco(linha, deslocam, chars)`** — o `chars` é o conserto do contrato, e fica
  mesmo com o filtro desligado: sem ele não há como medir o filtro, e a próxima pessoa a
  tentar o caminho cairia no mesmo `b.char` vazio. A polaridade é uma só ("este glifo
  desloca?"); o complemento do alfabeto é `_ForaDoAlfabeto` no instrumento, e não um `not
  in` escondido dentro do `if`.
- **`GLIFOS_QUE_DESLOCAM` e `ALFABETO_EASYOCR`** — os dois filtros, com a tabela no
  docstring e nenhum chamador em produção. Mesma decisão que a F19 tomou com
  `core/altura_relativa.py` e a F24 com `voto` e `margem_de_confianca`.
- No instrumento: `--alfabeto` mede os três de uma vez com a causa da exclusão decomposta,
  e `--com-filtro` liga o filtro nas outras tabelas.

**O cabeçalho do módulo mentia, e essa é a correção que sobra.** A seção "o que fica de
fora" listava a linha com figurina há dezenove fases; agora ela lista só girado e negativo,
e diz por que a figurina não está lá.

Cobertura: `tests/test_f17_leitura_de_linha.py`, 43 testes. O que muda de sentido fica
registrado: `test_fora_do_alfabeto_tira_a_linha_do_bloco` virou
`test_figurina_tira_a_linha_do_bloco`, e `test_sem_alfabeto_nao_filtra` perdeu um docstring
que explicava o furo como se fosse desenho ("num preenchimento os boxes ainda não têm
caractere, então o filtro não tem o que olhar"). O teste que guarda a decisão é
`test_nenhum_caminho_de_producao_filtra_a_linha`: ele existe porque a leitura óbvia do
código é a oposta — o parâmetro está ali, a lista está ali, e ligá-los parece esquecimento.

---

## F37 — A altura relativa apontada ao k-NN — MEDIDA, e a premissa estava invertida

A F19 mediu o canal geométrico contra a rede e o descartou com uma conta explícita: "uma
base a 98% não tolera um canal lateral a 97%". Ficou de pé o argumento de que contra uma
âncora **mais fraca** ele renderia — e o k-NN parecia essa âncora, com o número de 96,10%
que a F24 registrou. A F21 tinha mostrado exatamente essa lei para a leitura por linha: o
ganho é inverso à força da âncora.

**Medido, o k-NN não é a âncora mais fraca. Nesta amostra ele é a mais forte.**

### As duas âncoras, na mesma amostra e no mesmo dia

> **A tabela abaixo foi refeita na F41.** A primeira versão desta fase saiu com 9.178
> caracteres de 10 páginas — o conjunto que `medir_altura.py` montava por conta própria, e
> que diverge do de todas as outras tabelas do projeto. Corrigido o instrumento, são 10.565
> caracteres de 11 páginas. **A conclusão não se moveu; ficou mais dura.** Os números
> antigos estão na F41, lado a lado com estes.

10.565 caracteres em 11 páginas rotuladas, base de 85.151 referências em 216 classes.
"Tocou" é quantos boxes o desempate de fato trocou; consertos e quebras decompõem essa
troca. Cada linha é o melhor ponto daquela margem, sobre as combinações de normalizador,
corte e faixa de incerteza:

| âncora | margem | melhor | delta | tocou | consertos | quebras |
|---|---:|---:|---:|---:|---:|---:|
| **rede**, 98,19% de base | 1e-6 | 97,52% | −0,67 | 72 | 0 | 71 |
| | 1e-4 | 97,88% | −0,31 | 34 | 0 | 33 |
| | 1e-3 | 97,92% | −0,27 | 32 | 1 | 30 |
| **k-NN**, 98,49% de base | 0,00 | 97,55% | −0,94 | 105 | 2 | 101 |
| | 0,30 | 98,46% | −0,03 | 3 | 0 | 3 |
| | 0,50 | 98,47% | −0,02 | 2 | 0 | 2 |
| | 0,70 | 98,49% | ±0,00 | 0 | 0 | 0 |

Nenhum dos 63 pontos da rede nem dos 84 do k-NN supera a própria âncora, e a monotonia diz
o resto: **quanto mais o canal fala, pior fica**. A única linha que empata é a que não fala.

### A coluna que a F19 não tinha, e é ela que fecha a questão

A F19 registrou um erro de percurso: a primeira varredura usou margem de 0,02 sobre uma
rede peaked, o desambiguador tocou **1 box em 2.257**, e "não mudou nada" quase passou por
"não tem sinal" quando era "o filtro estava fechado". A correção foi abrir a margem; o que
faltou foi **imprimir quantos boxes foram tocados**, que é o que separa as duas leituras.

Agora está na tabela, e ela dá o número que a F19 estimou e não mediu. Aquela fase supôs
"a 2% de falso positivo já seriam 44 quebras contra 21 consertos". O que se mede é mais
duro: a **precisão** do canal quando ele fala é **0 em 72** na rede e **2 em 105** no k-NN.
Ele não é um canal a 97% que erra 2% das vezes; na rede ele não acerta nenhuma das vezes em
que abre a boca, e no k-NN acerta ~2%.

O mecanismo explica. `desambiguar` só dispara quando a classe tipográfica da vencedora
**discorda** da medida geométrica. Com uma âncora forte, essas discordâncias não são
dominadas por erro da âncora — são dominadas por erro da medida: a faixa da linha é
`max(y2) - min(y1)` dos boxes dela, e uma linha sem descendente ou sem ascendente encolhe a
faixa e desloca todas as frações juntas. O conjunto "âncora e geometria discordam" é quase
todo composto de linhas em que a geometria escorregou.

### O 98,53% é contaminado, e dizê-lo é metade do resultado

O k-NN aparece **acima** da rede nesta amostra, e isso não quer dizer que ele leia melhor.
As páginas rotuladas de `Box/` e `ilovepdf_pages-to-jpg/` são as mesmas em que se rodou
"Aprender com Página Atual", então boa parte delas está dentro de `training_data` byte a
byte — ali o k-NN não generaliza, consulta a própria cópia. Foi por isso que a F24 mediu o
voto **nas três páginas menos contaminadas** e obteve 96,10%.

Para esta fase a contaminação não atrapalha, e vale dizer por quê: ela torna a âncora
**mais forte**, que é o caso mais desfavorável ao canal lateral. Um resultado negativo sob
a âncora inflada precisaria ser reconferido; mas o negativo aqui vem com precisão de 2%, e
2% não vira positivo baixando a âncora de 98,5% para 96,1%.

**O que isso faz com a premissa.** A conta que sustentava esta fase era um orçamento de erro
três vezes maior, vindo de uma base a 94,8%. Esse número não existe: o k-NN sozinho mede
96,10% nas páginas limpas e 98,53% nestas, e a cadeia inteira 97,6%. O orçamento é o mesmo
da F19, e a F19 já o tinha gasto.

### O que ficou

Produção não mudou. Ficaram:

- **`CharacterLearner.candidatas(crop, n)`** — o `predict_topk` **por classe**, e ele fazia
  falta. `vizinhos` devolve as `n` amostras mais próximas, e depois da dedup byte a byte da
  F7.2 elas são quase sempre a mesma classe: é a razão de o voto da F24 medir pior, e era
  também a razão de não haver o que desempatar. Desempatar precisa da segunda *classe*, que
  é a generalização de `margem_de_confianca` de duas para `n`. A confiança devolvida é a de
  `predict`, para a `margem` do desempate ficar na mesma escala que roteia a cadeia.
- **`medir_altura.py --knn`**, e a coluna `tocou` **nas duas âncoras** — a da rede foi
  refeita junto, e é dela que sai o 1-em-22 que a F19 não tinha.
- `core/altura_relativa.py` continua sem nenhum chamador em produção, agora com duas
  medições contra si em vez de uma.

**O que esta fase não fecha.** A F14 pediu a altura **dentro** da rede, treinada junto, e
isso continua de pé e continua caro pelo mesmo motivo: `training_data` são PNGs de 32x32 já
normalizados, e a escala foi descartada na gravação. O que a F19 e a F37 fecham é a versão
barata — pendurar a geometria depois, como votante. Ela não funciona contra âncora nenhuma
que este projeto tenha.

Cobertura: `tests/test_f72_knn.py`, 4 testes novos para `candidatas` — que ela devolve
classes onde `vizinhos` devolve amostras, que a primeira é o que `predict` responde, que
não repete classe e que aguenta base vazia.

---

## F38 — Os botões que não giravam — CONCLUÍDA

A F35 fechou registrando uma dívida por escrito: `DISTANCIA_MAXIMA` era **valor padrão de
argumento** em `predict`, então ligava em tempo de `def` — editar o arquivo funcionava,
trocar o global em execução não. Foi por isso que aquela fase precisou de
`_MemoComDistancia` no instrumento em vez de simplesmente trocar o global. Ela não mexeu:
"esta fase concluiu que nada muda em produção, e emendar uma alteração de código numa fase
dessas é o jeito de ela passar sem ser lida".

Vim consertar essa linha. **O mesmo defeito estava vivo no botão ao lado, e lá ele tinha
uma medição em cima.**

### O `--k` estava desligado, e de dois jeitos

`medir_cadeia.py --k N` faz uma coisa só: `core_learner.K_VIZINHOS = args.k`. Para isso
valer, alguém teria de ler o global depois. Ninguém lê:

- `K_VIZINHOS` é o padrão de argumento de `vizinhos` e de `voto`, ligado em tempo de `def`
  como o `DISTANCIA_MAXIMA` — trocar o global não muda o padrão;
- e **nada no instrumento chamava `voto`**. O `aquecer` chama `predict`, que é 1-NN e não
  tem `k`; as três chamadas de `vizinhos` passam `k=1` explícito. Fora dos testes, `voto`
  não tinha chamador nenhum no projeto.

O agravante é o cabeçalho: ele imprime `k = {core_learner.K_VIZINHOS}`, que **mostra o valor
novo**. O botão se anunciava como aplicado e não estava ligado a nada. Uma varredura de `k`
rodada hoje devolveria quatro linhas idênticas, e o relatório diria `k = 7` em cima.

A tabela de `k` da F24 (96,10 / 95,90 / 95,90 / 95,79) tem valores distintos, então naquele
momento o caminho existia — a fase estava com o voto **em produção**, dentro de `predict`,
antes de desfazer. A reversão devolveu `predict` ao argmin e deixou o `--k` órfão. Não é o
achado desta fase, mas explica por que o instrumento ficou parecendo certo.

### O conserto, e ele é o mínimo

`predict`, `vizinhos` e `voto` passaram a receber `None` e a ler a constante **no corpo**.
Nenhum valor mudou, nenhuma resposta mudou; o que muda é que o global volta a ser um botão.
No instrumento entrou `_MemoComVoto`, irmão de `_MemoComDistancia`: ele envolve o memo, e
não o k-NN, então varrer `k` não custa consulta nova — as distâncias já estão no cache do
aquecimento. Com ele, `--k` faz o que o `--help` promete.

Os testes travam a propriedade certa, que não é "a constante vale tanto" e sim **"o botão
gira"**: trocam o global com `monkeypatch` e exigem que a resposta mude. Um teste que só
conferisse o valor padrão passaria com o defeito de volta.

### A frase da F35 estava errada, e a correção fica registrada

A F35 escreveu que "todas as outras constantes ajustáveis do projeto são lidas na chamada
(`BoxService.MARGEM_ARBITRO` é o modelo)". Não são. Varrendo `core/`, ligam em tempo de
`def`: `SEMENTE_PADRAO` e `MIN_PARA_DIVIDIR` (`avaliacao`), `BINS_PADRAO` (`calibracao`),
`CHESS_UNICODE` (`chess_pdf_processor`), `MIN_AMOSTRAS_POR_CLASSE` (`dataset_check`),
`CONF_MINIMA`, `DPI_FIGURA` e `TONS_DA_FIGURA` (`livro`), `CONCORDANCIA_MINIMA` e
`CONFIANCA_MINIMA` (`mapa_glifos`), `TETO_DE_REPETICAO` (`neural_trainer`),
`TEXTURA_ALTURA` (`preprocess`).

**Ficam como estão, e a razão é a diferença entre as duas situações.** Um padrão de
argumento ligado em tempo de `def` só é defeito quando alguém troca o global esperando
efeito — e é isso que um `medir_*.py` faz. As de cima ninguém troca assim: elas são
parâmetro de chamada, e quem mede passa o valor explícito. Os dois desta fase eram
diferentes porque havia instrumento tentando girá-los, e num deles havia tabela publicada.

O critério, para a próxima vez: **constante que um instrumento varre é lida no corpo.** As
outras podem ficar na assinatura, onde documentam melhor.

Cobertura: `tests/test_f72_knn.py`, 58 testes (3 novos) — o `DISTANCIA_MAXIMA` gira, o
`K_VIZINHOS` gira, e o instrumento chama `voto` de verdade. Nada muda em produção; a suíte
inteira em 1.328 confirma a resposta idêntica.

---

## F39 — O último limiar sem tabela, no outro caminho — CONCLUÍDA, e ele cai para 0,30

A F23 achou dois limiares que se justificavam um pelo outro e nenhum pela página, mediu, e
o do k-NN no caminho híbrido caiu de 0,85 para 0,30. **O irmão dele no caminho neural ficou
onde estava**: o literal `0.9`, escrito dentro do `preparar` de `generate_and_fill_neural`
e de novo no do PDF pesquisável — duas cópias, sem nome e sem tabela. `medir_cadeia.py`
mantinha uma terceira cópia (`LEARNER_NEURAL`) só para conseguir falar dele, com um
comentário explicando que produção o deixava inline.

### Medido, é o mesmo veredito

10.504 caracteres em 10 páginas, 85.151 referências. A trava da linha fica presa em 0,70,
que é onde produção a deixa — ver o defeito de instrumento mais abaixo:

| limiar | âncora | com a linha (trava 0,70) |
|---:|---:|---:|
| 0,00 | 97,46% | 97,51% |
| 0,10 | 97,46% | 97,50% |
| 0,15 | 97,47% | 97,51% |
| **0,20** | **97,48%** | **97,51%** |
| 0,25 | 97,47% | 97,50% |
| 0,30 | 97,44% | 97,50% |
| 0,50 | 97,42% | 97,48% |
| 0,70 | 97,32% | 97,43% |
| 0,90 | 97,03% | 97,13% |

**O 0,90 custava 0,38 ponto** — 40 caracteres. E a composição diz o mecanismo sem sobra:

    fonte      boxes       %    acerto
    neural     10.144   96,6%   98,12%
    learner       165    1,6%   96,36%
    easyocr       163    1,6%   46,01%

Em 0,90 o k-NN respondia 165 boxes e acertava 96,4%; 163 caíam no EasyOCR, que acerta
**46,0%**. Baixar o limiar move box do pior classificador para o melhor, e é só isso.

### O 0,20 não é pico, é platô — e o número sai do mecanismo

A primeira varredura foi de 0,20 para cima e a tabela ainda subia na borda, o que faria de
0,20 um pico aparente. Varrida a região de baixo, **de 0,00 a 0,30 é platô**: seis linhas
separadas por um caractere. Escolher pelo máximo aqui seria afinar contra o ruído, que é o
que a F24 registrou ao recusar mover uma constante por três caracteres.

O desempate vem da F35. A confiança é `1 - d/2000`, então o corte em distância é
`2000·(1-t)`, e a tabela por distância diz onde o k-NN deixa de ganhar do EasyOCR: acima de
~1.700.

| limiar | corte em distância | região |
|---:|---:|---|
| 0,30 | 1.400 | dentro da faixa em que o k-NN ganha |
| 0,15 | 1.700 | em cima da travessia |
| 0,00 | 2.000 | inclui 1.700–2.000, onde o k-NN faz 24,4% contra 56,1% |

Hoje essa faixa tem ~40 boxes e não move o total; numa base pior, move. **0,30 é o ponto do
platô que só entrega ao k-NN o que ele demonstradamente ganha.**

Que dê no mesmo número do híbrido é consequência e **não é a razão** — a F23 desmontou
exatamente o raciocínio inverso. Haver uma constante a menos no projeto é desempate de
terceira ordem, atrás da varredura e do mecanismo.

### O defeito de instrumento que quase entrou na tabela

A varredura do `learner_threshold` amarrava a trava da linha ao limiar em **todo** caminho:
`rodar(cadeia, paginas, caminho, lt, lt)`. No híbrido isso é o desenho —
`CONF_MAXIMA_PARA_A_LINHA_HIBRIDO` **é** `LEARNER_THRESHOLD_HIBRIDO`, para a linha agir
exatamente onde o k-NN se recusou (F21/F23). No caminho neural os dois são independentes: a
trava é 0,70 e o limiar é outro número. A coluna "com a linha" do neural mostrava, em cada
ponto, uma configuração que produção nunca roda.

Corrigido, com a distinção escrita no lugar em que alguém repetiria o erro. A primeira
rodada desta fase saiu com a coluna errada; a decisão não dependia dela — a coluna "âncora"
é limpa nos dois casos —, mas a tabela publicada é a refeita.

### O que ficou

`LEARNER_THRESHOLD_NEURAL = 0.30` em `ui/main_window.py`, com a tabela ao lado, substituindo
as duas cópias do literal. `medir_cadeia.py` deixou de manter a terceira e passou a
importar. Com isso **nenhum limiar de roteamento deste projeto continua sem tabela**: os
dois do k-NN, o da rede, as duas travas da linha e o `DISTANCIA_MAXIMA` (F35) carregam a
medição que os produziu e o comando que a refaz.

Cobertura: nenhum teste novo — nenhum fixava o 0,9, o que por si só é o comentário sobre
como ele estava. Suíte em 1.328.

---

## F40 — O outro laço ganha instrumento — CONCLUÍDA, e a F18 se confirma

`medir_cadeia.py` dizia no cabeçalho que não media o PDF pesquisável, "que usa a mesma
cadeia por outro laço". A tabela da F18 saiu de script que não ficou, sobre 2.278
caracteres, e a F36 teve de deixar aquele caminho sem medida por não haver com o quê. Era o
último caminho de leitura sem instrumento.

`--pdf` chama `searchable_pdf._ler_boxes` de verdade — código de produção, como o
`ler_pagina` do outro laço —, nas mesmas páginas, com os mesmos modelos memorizados e no
mesmo processo.

### A tabela da F18, refeita com 4,6x mais caracteres

> **Esta tabela é de antes da F39 entrar em produção**, e a F42 a refez depois. O
> `learner_threshold` do caminho neural ainda era 0,90 quando ela foi medida — a F39 estava
> decidida e ainda não estava no código. Os números novos estão na F42; **o vencedor não
> muda**, e é ele que esta seção afirma.

| a linha manda quando | acerto (t = 0,90) | trocados | | acerto (t = 0,30, F42) | trocados |
|---|---:|---:|---|---:|---:|
| nunca | 96,90% | 0 | | 97,46% | 0 |
| **confiança < 0,70** | **97,13%** | 41 | | **97,52%** | 29 |
| confiança < 0,90 | 97,09% | 56 | | 97,48% | 49 |
| confiança < 0,99 | 96,73% | 121 | | 97,04% | 108 |
| sempre | 89,82% | 954 | | 89,82% | 899 |

Mesmo formato, mesmo vencedor, e o 0,70 continua sendo o corte. O que muda é o tamanho do
prêmio: a F18 mediu o ganho como "**um caractere em 2.278**" e concluiu "rende quase nada".
Em 10.504 são **24 caracteres**, 0,23 ponto. Não é muito, mas é cinco vezes o que a amostra
pequena deixava ver — e o "sempre" continua custando 7,3 pontos, que é a lei da F21 no seu
caso mais extremo.

### Os dois laços empatam, e a diferença entre eles explica por quê

| | acerto | neural | k-NN | EasyOCR | linha |
|---|---:|---:|---:|---:|---:|
| laço da janela (`ler_pagina`) | 97,13% | 10.144 | 165 | 163 | 32 |
| laço do PDF (`_ler_boxes`) | 97,13% | 10.144 | 165 | 154 | 41 |

Refeito depois da F39 entrar (`t = 0,30`), o empate se mantém: **97,52% do PDF contra
97,50% da janela**, com o k-NN respondendo 281 boxes em vez de 165 e o EasyOCR 50 em vez de
154. Dois centésimos separam os dois laços, nas duas configurações.

**O laço do PDF não passa `contexto`** ao reconhecedor — o mesmo box esticado até a faixa da
linha, que a F14 mediu levar o elo do EasyOCR de 66,9% para 74,2%, porque devolve a altura
relativa que a normalização de 32x32 apaga. A janela passa; o PDF não. E os dois empatam.

A razão está na coluna: esse elo responde **1,5% dos boxes**. Melhorá-lo em 7 pontos move
0,1 ponto no total, que se perde no arredondamento. É a lei da F21 mais uma vez — o ganho
de um elo lateral é inverso à força da âncora —, e aqui a âncora responde 96,6% dos boxes
com 98,12% de acerto.

**Isto não diz que o `contexto` é dispensável**, diz que ele é invisível *nesta*
composição. Num livro que a rede leia pior, o elo cresce e a diferença aparece. Fica
registrado onde se procura: quem for atrás de por que dois caminhos com a mesma cadeia dão
números diferentes, esta é a primeira diferença a olhar.

### Dois defeitos do próprio instrumento, e um é do tipo que esta fase veio caçar

O `--pdf` nasceu com o sentinela errado. O `--trava` usa `None` para "a linha manda sempre",
porque é assim que `ler_pagina` lê o parâmetro; `_ler_boxes` compara
`conf < conf_linha_maxima` direto, e `None` ali é `TypeError`. **O mesmo limiar tem dois
contratos nos dois laços**, e copiar o sentinela de um para o outro quebra — que é
exatamente a classe de divergência que ter um instrumento só para os dois serve para expor.

E o bloco novo estava no meio do `main`, então a exceção dele levou junto a tabela do
`learner_threshold`, que já estava calculada. Bloco novo entra por último.

A trava do PDF o instrumento **lê da assinatura** (`inspect.signature`) em vez de copiar: a
UI chama `gerar_pdf_pesquisavel` sem o argumento, então o número de produção é o padrão
declarado. Copiá-lo criaria a terceira cópia de um limiar neste projeto, que é como o 0,85
da F23 e o 0,9 da F39 chegaram onde chegaram.

### O que ficou

`rodar_pdf` e `--pdf` em `medir_cadeia.py`, e o cabeçalho do arquivo trocou a seção "o que
ele não mede" por uma seção "os dois laços". O que ele continua não medindo é a
**renderização**: o caminho real rasteriza o PDF a 300 dpi e segmenta o que sai dali,
enquanto aqui as páginas são as rotuladas, para as tabelas serem comparáveis entre si.

Cobertura: nenhum teste novo — é instrumento, como `medir_paginas.py`. Suíte em 1.328.

---

## F41 — Duas definições de "página rotulada", e uma tabela publicada sobre a errada — CONCLUÍDA

A F37 saiu na véspera com 9.178 caracteres, o mesmo número da F19, e eu escrevi "a mesma
amostra da F19" como se isso fosse garantia. Era o contrário: os dois números batem porque
**os dois vêm do mesmo instrumento errado**.

`medir_altura.py` montava a própria lista de páginas rotuladas — `PASTAS` e um
`paginas_rotuladas` de onze linhas. A canônica mora em `core/calibracao_de_pagina` e é a
que `medir_paginas.py`, `medir_cadeia.py` e `calibrar_modelo.py` usam. As duas divergem em
duas pontas, e cada uma erra para um lado:

| | canônica | a de `medir_altura` |
|---|---|---|
| onde procura a imagem | na pasta do `.box` **e** na outra | só na pasta do `.box` |
| corte de tamanho | `MIN_ROTULADOS = 50`, aplicado por quem chama | nenhum |
| resultado | 11 páginas | 10 páginas |

A página que faltava é a `Kasparov ... page-0108`, cuja imagem está na outra pasta. A que
sobrava é `boxes.box`, com **28 rótulos** — o retalho que o `MIN_ROTULADOS` existe para
recusar, e cujo comentário diz "abaixo disto a página é um retalho e não uma amostra".

Corrigido: **10.565 caracteres em 11 páginas**, contra 9.178 em 10.

### Refeita, a F37 fica mais dura

Nenhuma conclusão se moveu; a evidência engrossou. Os dois conjuntos, lado a lado:

| âncora | margem | tocou | consertos | quebras | | tocou | consertos | quebras |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| | | **9.178 (errado)** | | | | **10.565 (certo)** | | |
| rede | 1e-6 | 22 | 1 | 20 | | 72 | **0** | 71 |
| rede | 1e-4 | 12 | 1 | 10 | | 34 | **0** | 33 |
| rede | 1e-3 | 8 | 1 | 6 | | 32 | 1 | 30 |
| k-NN | 0,00 | 90 | 2 | 86 | | 105 | 2 | 101 |
| k-NN | 0,30 | 3 | 0 | 3 | | 3 | 0 | 3 |
| k-NN | 0,70 | 0 | 0 | 0 | | 0 | 0 | 0 |

O acerto da âncora quase não se move — rede de 98,21% para 98,19%, k-NN de 98,53% para
98,49% —, o que era de esperar: entrou uma página inteira e saiu um retalho. O que muda é o
**volume de disparos**, que triplica na rede, e com ele o único conserto que a rede tinha
desaparece. A frase da F37 sobre a precisão do canal passou de "1 em 22" para **0 em 72**.

A tabela da F37 no ROADMAP foi substituída pelos números novos, com o aviso de que foi
refeita aqui e os antigos ficam nesta fase. Substituir e não emendar é a escolha certa
quando os números velhos são de um conjunto que ninguém mais consegue reproduzir: o
instrumento que os produziu não existe mais.

### O que o instrumento não dizia, e agora diz

**Nada na saída denunciava o conjunto.** As duas rodadas se apresentavam com o total de
caracteres e mais nada, então "9.178" parecia uma amostra e era duas coisas ao mesmo tempo.
É a mesma forma do achado da F24 — a base cresceu no meio da medição e nada na saída dizia
—, e é a segunda vez que este projeto aprende a mesma lição.

`medir_altura.py` passou a imprimir **quantas páginas** entraram, e a marcar na listagem a
que ficou de fora por poucos rótulos. `medir_cadeia.py` já fazia isso (páginas, caracteres,
tamanho da base) desde a F24, o que é justamente por que a divergência ficou visível: as
duas saídas, lidas lado a lado, não fechavam.

### O que ficou

`medir_altura.py` importa `paginas_rotuladas` e `MIN_ROTULADOS` de
`core/calibracao_de_pagina` — a definição de "página rotulada" volta a ser uma só no
projeto. `core/altura_relativa.py` teve a seção da aritmética reescrita: ela citava 9.178
caracteres e a estimativa de 2% de falso positivo da F19, e agora carrega a medida da F37
com o conjunto certo.

**Fica registrado o que não foi feito.** A F19 mediu com o instrumento antigo, e as tabelas
dela — a de d' e a de 63 combinações — não foram refeitas. A de d' não depende do conjunto
da mesma forma (é separação entre classes, e o retalho de 28 rótulos contribui quase nada);
a das 63 combinações foi refeita pela F37 e substituída. O que sobra de F19 no ROADMAP são
números históricos, e agora eles dizem de que amostra vieram.

Cobertura: nenhum teste novo — é instrumento. Suíte em 1.328.

---

## F42 — O `contexto` que falta no laço do PDF — MEDIDO, e não paga

A F40 pôs os dois laços no mesmo instrumento e a primeira diferença apareceu sozinha: o da
janela passa ao reconhecedor o recorte justo **e** o mesmo box esticado até a faixa da
linha; o do PDF passa só o justo. A F14 mediu que essa faixa leva o elo do EasyOCR de
66,9% para 74,2%, porque devolve a altura relativa que a normalização de 32x32 apaga. Uma
diferença de 7 pontos num elo, entre dois caminhos que deveriam ler igual, é candidata
óbvia a conserto.

**Medida, ela não rende — e o caminho para medi-la importa tanto quanto o número.**

### Medir sem mexer

`searchable_pdf._ler_boxes` chama `reconhecer(recorte)` e mais nada, então dar-lhe o
contexto exigiria trocar a assinatura de `reconhecer`, que é parâmetro público de
`gerar_pdf_pesquisavel` e tem dois chamadores. Trocar a assinatura em produção para depois
descobrir que não paga é a ordem errada.

Não foi preciso: **quem monta o `reconhecer` dentro do instrumento sou eu**. A faixa da
linha é recuperável pelos bytes do recorte justo, porque `_ler_boxes` o calcula com o mesmo
`vertical.recorte_de_pe` que o laço do medidor — então `rodar_pdf(com_contexto=True)` serve
o contexto por dentro, com o código de produção intocado.

### O número

10.504 caracteres, 10 páginas, caminho neural com os limiares de produção:

| | acerto | boxes no EasyOCR |
|---|---:|---:|
| sem contexto (hoje) | **97,52%** | 50 |
| com a faixa da linha | 97,50% | 50 |

O total esconde o efeito, porque o elo responde 0,5% dos boxes. Restringindo aos **53 boxes
que passaram pelo EasyOCR em alguma das duas** rodadas: 41,51% sem contexto contra 37,74%
com. São 22 acertos contra 20 — **dois caracteres**, e para o lado errado.

A contagem de boxes no elo não muda, e isso é o esperado: `fallback_chain` só usa o
`contexto` na chamada final ao EasyOCR, então o roteamento é idêntico e o que varia é
apenas o que aquele elo lê.

### Por que a F14 não se repete aqui

A F14 mediu os 7 pontos com o EasyOCR lendo **todos** os boxes da página. Aqui os boxes que
chegam nele são o resto: o que a rede recusou a 0,80 **e** o k-NN recusou a 0,30. É outra
população — recorte-lixo, glifo colado, fragmento —, e nela a faixa da linha traz tinta do
vizinho junto com a altura relativa. O ganho da F14 é sobre glifo legível cuja única dúvida
é o tamanho; não é isso que sobra aqui.

**O que este número não autoriza a dizer.** São 50 boxes, e dois caracteres de diferença
não separam "não ajuda" de "atrapalha um pouco". O que a medição sustenta é que **não há
ganho a colher**, e portanto não há razão para mexer na assinatura de `reconhecer`. Num
livro que a rede leia pior o elo cresce, e aí a pergunta volta — com amostra para respondê-la.

### O que ficou

Produção intocada: o laço do PDF continua sem `contexto`, agora por medição e não por
descuido, e o comentário em `_ler_boxes` diz isso. No instrumento ficou
`rodar_pdf(com_contexto=...)` e a tabela, para a pergunta não precisar ser remontada quando
a composição mudar.

**E uma correção na F40.** As tabelas dela foram medidas com o `learner_threshold` do
caminho neural ainda em 0,90 — a F39 estava decidida e ainda não estava no código, e as
duas fases foram escritas na mesma sessão. Refeitas com 0,30, o vencedor da tabela da F18
não muda (0,70 continua o corte) e o empate entre os dois laços se mantém: 97,52% do PDF
contra 97,50% da janela. As duas tabelas da F40 agora trazem as duas colunas.

Cobertura: nenhum teste novo — é instrumento. Reproduzir:
`python medir_cadeia.py --neural --pdf`.

---

## F43 — Um número serve dois usos — MEDIDO, e separá-los rende pouco (números refeitos na F47)

A F24 fechou com este item, marcado lá como "a pergunta anterior a qualquer nova fórmula":

> Roteamento quer novidade, fila de revisão quer as duas coisas. Toda esta fase mediu qual
> fórmula única serve melhor aos dois; ninguém mediu ainda o que acontece **separando-os** —
> `b.confidence` continuaria a absoluta, e a fila passaria a ordenar por outro critério.

Medido, separar rende — e rende mais do que qualquer coisa que esta série mexeu.

### A fila, ordenada de quatro jeitos

A conta é a de recall igual, que é a única que compara duas escalas diferentes: para pegar
uma fração dos erros, quantos **acertos** o revisor abre à toa. Caminho híbrido, com os
limiares de produção. Onde não há margem — EasyOCR e linha — vale a confiança crua, e
aquele box não sai do lugar.

> **As tabelas desta fase foram refeitas na F47, e os números abaixo são os corrigidos.** A
> versão original media a margem do k-NN em **todos** os boxes, inclusive nos que outro elo
> respondeu, e comparava os cortes de margem contra um **único** ponto da confiança. Os dois
> defeitos empurravam para o mesmo lado. Os números antigos e o que os produziu estão na F47.

**10 páginas, 10.504 caracteres:**

| ordenação | 25% dos erros | 50% dos erros | 75% dos erros |
|---|---:|---:|---:|
| confiança crua (hoje) | **155** | 2.261 | 3.894 |
| percentil por fonte (F25) | 864 | 2.691 | 4.617 |
| margem onde há | 411 | **2.160** | **3.658** |
| mín. das duas | 313 | 2.227 | 3.865 |

**As 3 páginas menos contaminadas** (0,7%, 31,5% e 0,0% dos boxes já na base), 3.440
caracteres:

| ordenação | 25% dos erros | 50% dos erros | 75% dos erros |
|---|---:|---:|---:|
| confiança crua (hoje) | 94 | 914 | 1.988 |
| percentil por fonte | 378 | 997 | 1.936 |
| **margem onde há** | **93** | **775** | **1.689** |
| mín. das duas | 89 | 851 | 1.820 |

Para achar metade dos erros, a fila de hoje faz o revisor abrir **914** boxes certos; a
margem, 775. É **15% menos trabalho**, e só na cauda — no topo da fila a confiança ganha nas
dez páginas e empata nas limpas.

### A contaminação era a suspeita óbvia, e ela não explica

A distância absoluta satura: quando o vizinho mais próximo é uma cópia byte a byte da
própria página, `1 - d/2000` dá ~1,00 e não ordena mais nada. Como as páginas rotuladas são
as mesmas em que se rodou "Aprender com Página Atual", metade delas tem mais de 40% dos
boxes já na base, e a saturação favoreceria a margem por artefato.

Por isso a segunda tabela. Nas três páginas em que a base quase não viu a página, a
vantagem **sobrevive e é pequena**: 914 para 775. O mecanismo não é a contaminação — mas
também não é grande, e a F47 explica por que a primeira versão desta fase o mediu enorme.

### O motivo, e ele estava escrito na F24 sem que ela o visse

A F24 mediu margem contra absoluta **no elo do k-NN isolado** e a absoluta ganhou no topo
da fila — 0 alarmes falsos contra 37 para pegar 25% dos erros. Aqui, na fila de verdade, o
resultado se inverte: 94 contra 35. As duas medições estão certas, e a diferença entre elas
é a resposta.

No elo isolado, o conjunto inclui o recorte-lixo, aquele que a base nunca viu. A absoluta o
detecta — é o detector de novidade que a F24 descreveu — e o põe no topo da fila, onde ele
deve estar. **Na cadeia esse box nunca chega à fila com a confiança do k-NN**: a absoluta
já o usou para *roteá-lo* ao EasyOCR, e o que aparece na fila é a confiança do CRNN.

Ou seja: **o trabalho da absoluta é gasto no roteamento.** Quando o box chega à fila, a
pergunta "isto é novidade?" já foi feita e respondida por quem escolheu o classificador. O
que sobra por decidir é "o vencedor estava claramente à frente?", e essa é a pergunta da
margem. Um número não serve dois usos porque o primeiro uso **consome** a informação.

### O que isto não conserta

Os boxes que o EasyOCR responde. Nas páginas limpas são 44 boxes com 40,9% de acerto e
mediana de confiança **0,9708 tanto no erro quanto no acerto** — a confiança do CRNN não
separa nada ali, e nenhuma das quatro ordenações melhora isso, porque para eles não há
margem e todas caem na crua. São 26 erros escondidos no topo da fila. É o pior ponto cego
da revisão hoje, e é outra fase.

### O que ficou, e o que falta para isto entrar

Só instrumento: `tabela_revisao` ganhou as duas ordenações e a comparação de quatro linhas.
**Produção não mudou**, e a razão é que a mudança não é de fórmula, é de estrutura: a fila
ordena por `b.confidence`, e passar a ordenar pela margem exige um **segundo número por
box**. `BoxEntry` teria de carregá-lo, as três ações de preenchimento teriam de preenchê-lo
onde a fonte for `learner`, e `ui/confidence.py` teria de escolher qual dos dois olhar —
com o cuidado de que `b.confidence` **continua** sendo a absoluta, porque é ela que colore
o box e é ela que a F25 mediu contra a calibração da rede.

Isso é fase de código, com decisão de formato no meio (o `.box` não guarda confiança
nenhuma hoje), e emendá-la no fim de uma fase de medição é o jeito de ela passar sem ser
lida — a mesma razão que a F35 deu para não consertar o `DISTANCIA_MAXIMA` na hora.

Fica registrado com o número que a justifica: **7x menos trabalho de revisão para achar
metade dos erros**, medido fora da contaminação.

Cobertura: nenhum teste novo — é instrumento. Reproduzir:
`python medir_cadeia.py` e `python medir_cadeia.py --so page-0020 page-0128 page-0033`.

---

## F44 — A margem chega ao box, e o corte da revisão muda — DESFEITA na F47

A F43 mediu que separar os dois usos da confiança rende, e parou ali: "produção não mudou,
e a razão é que a mudança não é de fórmula, é de estrutura". Esta fase faz a estrutura.

**E a primeira coisa que ela achou foi um erro de leitura meu.** A F43 falou o tempo todo
em "ordenar a fila", e mediu curvas de recall. O código não ordena nada: `precisa_revisao`
é um **corte** — `confidence < LIMIAR_ALTO` —, e o revisor navega os marcados. A pergunta
prática é um ponto da curva, não a curva. Isso torna a decisão mais fácil e a medição mais
direta.

### O corte, medido

`margem < X` onde há margem, e a regra de antes onde não há — rede, EasyOCR e linha não têm
margem, e para elas nada muda. Nas 10 páginas (246 erros) e nas 3 menos contaminadas (105):

> **As tabelas desta fase foram refeitas na F47, e os números abaixo são os corrigidos.** A
> versão original media a margem do k-NN em **todos** os boxes, inclusive nos que outro elo
> respondeu, e comparava os cortes de margem contra um **único** ponto da confiança. Os dois
> defeitos empurravam para o mesmo lado. Os números antigos e o que os produziu estão na F47.

| | 10 páginas | | 3 limpas | |
|---|---:|---:|---:|---:|
| **regra** | **pegos** | **à toa** | **pegos** | **à toa** |
| conf < 0,90 (antes) | **123** | 2.266 | **53** | 918 |
| margem < 0,30 | 69 | 163 | 25 | 56 |
| margem < 0,50 | 88 | 458 | 38 | 177 |
| margem < 0,70 | 112 | 1.071 | 45 | 408 |
| margem < 0,90 | 125 | 2.287 | 55 | 939 |

**Não há domínio, e o corte que esta fase escolheu — `margem < 0,50` — pega menos erro que a
regra que ele substituiu**: 88 contra 123. Foi regressão, e foi desfeita.

Com a confiança também varrida (o que esta fase não fez, e a F47 fez), as duas curvas se
cruzam: a margem ganha no meio, empata no ponto de operação de hoje e perde na cauda. A
decisão final está na F47, e é **ficar na confiança**.

### O que a estrutura exigiu, e o que ela custou

- **`CharacterLearner.predict_e_margem`** — as duas escalas numa busca só. Chamar `predict`
  e `margem_de_confianca` em seguida faria a multiplicação de matriz contra 87 mil
  referências **duas vezes**, e no caminho híbrido o k-NN responde 98% dos boxes: seria
  dobrar o preço da ação inteira, que é exatamente o que a F7.2 existe para conter. Há
  teste de que a resposta é idêntica à das duas funções separadas, e outro de que a base é
  consultada uma vez só.
- **`OCRService.fallback_chain_detalhado`**, devolvendo uma `Leitura`, com o
  `fallback_chain` de sempre implementado **em cima dele**. Duas implementações da cadeia
  divergiriam com o tempo, e é o defeito que a F1.5 registrou.
- **`BoxEntry.margem`**, e ele entra **no fim** da lista de campos. `from_state` carrega o
  estado por posição, então um campo enfiado no meio faria um estado de nove campos virar
  outro box em silêncio, com o `angulo` lido como margem.
  `test_estado_anterior_a_margem_continua_carregando` guarda isso.
- **A margem viaja por fora do `ler_pagina`**, num dicionário por `id(box)` — o mesmo idioma
  que o `faixas` daquele laço já usa. Ela é do reconhecimento do caractere, não da leitura
  da linha, e enfiá-la na tupla mudaria o contrato de um módulo que o `searchable_pdf`
  também usa.

O contrato do `learner` mudou — a cadeia agora pede `predict_e_margem` —, e isso alcançou
os quatro envelopes de `medir_cadeia.py` e dois dublês de teste. Foi o preço de não ter dois
caminhos, e está pago.

### O que fica de fora, e é pergunta de interface

**A cor do box continua na confiança.** `cor_do_box` não mudou: ela diz "o quanto esta
leitura se parece com o que a base conhece", que é o número que a F25 mediu contra a
calibração da rede. A consequência é que um box pode sair **verde e mesmo assim entrar na
fila** — quer dizer "parecidíssimo com algo que eu já vi, e quase igualmente parecido com
outra coisa".

São dois fatos diferentes sobre o mesmo box, e nada os impede de discordar. O que não foi
medido é se mostrar os dois separados ajuda ou confunde quem revisa, e isso não se decide
com script: é medida com gente, como a F31 registrou sobre o custo de consertar um box.

Cobertura: `tests/test_f72_knn.py` (3 novos), `tests/test_f38_historico.py` (1 novo, o do
estado antigo), mais os dublês de `test_f16_easyocr.py` e `test_f32_confianca.py`
acompanhando o contrato. Suíte em 1.332. Reproduzir:
`python medir_cadeia.py` e `python medir_cadeia.py --so page-0020 page-0128 page-0033`.

---

## F45 — O ponto cego do EasyOCR — MEDIDO, e a concordância o abre

A F43 fechou apontando o pior ponto cego da revisão: nos boxes que o EasyOCR responde, a
mediana de confiança é **0,9708 tanto no erro quanto no acerto**. A régua do CRNN não separa
nada ali, e a F44 não os alcança — para eles não existe margem, e a regra cai na confiança,
que é justamente a que falha.

O sinal que sobra é o que a F17 já usava para a linha: **concordância**. E ele está
disponível de graça, o que é o ponto: o k-NN respondeu esses mesmos boxes antes de ser
recusado pelo roteamento. Foi recusado por confiança baixa, não por silêncio — a resposta
dele existe e foi jogada fora.

| | boxes | acerto | erros |
|---|---:|---:|---:|
| **10 páginas**, 160 boxes, 92 erros | | | |
| o k-NN concorda | 21 | 90,5% | 2 |
| o k-NN diverge | 139 | 35,3% | 90 |
| **3 limpas**, 44 boxes, 26 erros | | | |
| o k-NN concorda | 8 | 100,0% | 0 |
| o k-NN diverge | 36 | 27,8% | 26 |

**Marcar só os divergentes pega 98% dos erros nas dez páginas e 100% nas três limpas**,
abrindo 49 e 10 acertos à toa. Contra uma régua que hoje não distingue erro de acerto, é a
diferença entre ter e não ter filtro.

O mecanismo é o da F17 dito de outro jeito: duas leituras independentes que concordam se
corroboram, e onde divergem é onde o erro se concentra. A novidade é que aqui a segunda
leitura vem de um elo que a cadeia **descartou**, e o descarte não a torna inútil — torna-a
inútil para *responder*, não para *duvidar*.

### O que falta para isto entrar

Um terceiro dado por box: o que o elo anterior disse. `Leitura` teria de carregá-lo,
`BoxEntry` também, e `precisa_revisao` compararia. É a mesma forma da F44 e o mesmo tamanho,
e fica registrado com o número que a justifica em vez de emendado no fim desta.

**E há uma pergunta anterior a essa.** Se a leitura do k-NN é bom sinal quando a do EasyOCR
está errada, vale perguntar por que ela não é a resposta: 44 boxes com 27,8% de acerto do
EasyOCR contra o k-NN concordando em 8 e acertando todos. Pode ser que o roteamento esteja
mandando ao EasyOCR box que o k-NN responderia melhor mesmo com confiança baixa — e isso é
a varredura do `learner_threshold` outra vez, agora olhando o **acerto por faixa** em vez do
total. A tabela por distância da F35 já diz que não: abaixo de 1.700 o k-NN ganha e é ele
que responde; acima, ele perde e é lá que estes 44 boxes vivem. Fica anotado que a resposta
já existe, para ninguém refazer a pergunta.

Cobertura: nenhum teste novo — é instrumento. Reproduzir: as mesmas duas linhas da F44.

---

## F46 — O limiar do híbrido remedido — MEDIDO, e o 0,30 fica por um motivo novo

A F24 fechou registrando este como pendência com condição escrita:

> Na base de hoje (73.900 referências, contra 70.755 quando a F23 mediu) o pico da varredura
> caiu em 0,20 com 97,64%, contra 97,61% de 0,30 — **três caracteres em 10.481**. (…) mover
> uma constante por três caracteres é afinar contra o ruído de uma base que muda sozinha.

A base está em **86.897**, 17% maior. Refeita a varredura, o pico volta a cair em 0,20.

| limiar | âncora | com a linha | corte em distância |
|---:|---:|---:|---:|
| 0,10 | 97,57% | 97,57% | 1.800 |
| **0,20** | **97,67%** | **97,67%** | 1.600 |
| 0,30 | 97,61% | 97,64% | 1.400 |
| 0,40 | 97,38% | 97,55% | 1.200 |
| 0,50 | 97,01% | 97,37% | 1.000 |

### Repetir não é confirmar, e essa é a primeira metade

O resultado parece confirmação independente — duas bases, dois picos em 0,20, mesma
diferença de três caracteres. **Não é.** O que mudou entre a F24 e agora foi o tamanho da
base de *referência*; as **páginas medidas são as mesmas dez**. Os boxes que separam 0,20 de
0,30 são em grande parte os mesmos boxes, olhados duas vezes.

Uma medida repetida sobre a mesma amostra estreita o intervalo do *método*, não o da
*população*. Se os 34 boxes em disputa forem atípicos, repetir a conta os mantém atípicos
nas duas vezes. Isso vale para todas as tabelas desta série, e é a razão de a coluna "já na
base" e o `--so` existirem.

### O que decide é a tabela por distância, e ela não existia na F24

A confiança é `1 - d/2000`, então o corte em distância é `2000·(1-t)` e é ele que roteia. A
tabela por distância entrou na F35:

| distância | boxes | k-NN | EasyOCR |
|---|---:|---:|---:|
| 1.200 – 1.400 | 81 | 75,3% | 45,7% |
| **1.400 – 1.700** | **34** | **58,8%** | **47,1%** |
| 1.700 – 2.000 | 41 | 24,4% | 56,1% |

Ela explica a curva inteira. Mover de 0,30 para 0,20 leva o corte de 1.400 para 1.600 e
entrega ao k-NN a faixa de 1.400–1.700: **34 boxes**, 11,7 pontos de vantagem, cerca de 4
caracteres. Erro padrão binomial de ~3 boxes. Mover de 0,20 para 0,10 leva o corte a 1.800
e engole a faixa seguinte, onde o k-NN faz 24,4% contra 56,1% — e é por isso que a curva
despenca ali.

**O único ponto em disputa é uma faixa de 34 boxes cujo vencedor está dentro do ruído.** A
queda dos dois lados é sólida; o pico não é.

### O 0,30 fica, e agora com mecanismo

A F24 recusou mover por não ter razão além de três caracteres. Hoje há razão, e ela aponta
para o mesmo lado: **o corte de produção deve ficar dentro da região em que o k-NN
demonstradamente ganha**, e 1.400 está; 1.600 encosta na travessia apoiado numa faixa fina.
É o mesmo critério que a F39 usou para escolher o 0,30 do caminho neural, e os dois
caminhos ficarem no mesmo número continua sendo consequência e não razão.

O que mudaria a decisão: uma amostra com **páginas novas** na faixa de 1.400–1.700. Não é
mais base de referência que resolve — é mais página rotulada.

Cobertura: nenhum teste novo; a tabela entra ao lado da constante em
`ui/main_window.py`. Reproduzir:
`python medir_cadeia.py --learner 0.10 0.20 0.30 0.40 0.50`.

---

## F47 — A margem não ganha da confiança, e as duas fases que disseram que sim estavam medindo errado — CONCLUÍDA

Esta fase ia perguntar se a razão de Lowe da **rede** filtra a fila do caminho neural como a
do k-NN filtrou a do híbrido. Ao instrumentar isso, o defeito apareceu — e ele estava embaixo
da F43 e da F44, que são as duas fases que decidiram trocar a régua da revisão.

### Os dois defeitos, e eles empurravam para o mesmo lado

**Um: a margem valia para quem não tinha respondido.** O mapa de margens vem do aquecimento,
que consulta o k-NN em **todos** os boxes — inclusive nos que o roteamento mandou ao EasyOCR.
A F43 (ordenação) e a F44 (corte) usavam esse mapa sem olhar a fonte, então um box lido pelo
EasyOCR era julgado pela ambiguidade de um classificador que tinha sido recusado por estar
longe de tudo. É justamente ali que os erros se concentram — 46% de acerto —, e marcá-los em
bloco fazia a margem parecer excelente. A F24 já tinha escrito o que essa margem vale nesse
caso: "um recorte-lixo pode estar duas vezes mais perto de `a` que de `b` e tirar margem
0,50".

**Dois: a comparação era torta.** Cinco cortes de margem contra **um** ponto da confiança, o
0,90 do `LIMIAR_ALTO`. Duas réguas só se comparam a recall igual ou a custo igual, e para
isso as duas precisam de curva. Sem isso eu não comparei réguas, comparei uma régua com um
ponto — e o ponto era o pior lugar da outra curva para ela.

Produção sempre implementou a regra certa (`b.margem` só é preenchida onde a fonte é
`learner`), então o código estava coerente; o que não estava era a justificativa. E o corte
escolhido com base nela, `margem < 0,50`, **pegava menos erro que a regra que substituiu**.

### O corte, com as duas curvas

Cortes de confiança e de margem na mesma tabela, nos dois caminhos, com e sem a contaminação
da base.

**Híbrido, 10 páginas, 246 erros:**

| regra | marcados | pegos | à toa | | regra | marcados | pegos | à toa |
|---|---:|---:|---:|---|---|---:|---:|---:|
| conf < 0,50 | 248 | 65 | 183 | | margem < 0,30 | 232 | 69 | 163 |
| conf < 0,70 | 1.108 | 91 | 1.017 | | margem < 0,70 | 1.183 | **112** | 1.071 |
| **conf < 0,90** | 2.389 | **123** | 2.266 | | margem < 0,90 | 2.412 | **125** | 2.287 |
| conf < 0,99 | 4.461 | **195** | 4.266 | | margem < 0,99 | 4.319 | 176 | 4.143 |

**Híbrido, 3 páginas limpas, 105 erros:**

| regra | marcados | pegos | à toa | | regra | marcados | pegos | à toa |
|---|---:|---:|---:|---|---|---:|---:|---:|
| conf < 0,50 | 67 | 23 | 44 | | margem < 0,30 | 81 | 25 | 56 |
| conf < 0,70 | 348 | 33 | 315 | | margem < 0,70 | 453 | **45** | 408 |
| **conf < 0,90** | 971 | **53** | 918 | | margem < 0,90 | 994 | **55** | 939 |
| conf < 0,99 | 2.429 | **88** | 2.341 | | margem < 0,99 | 2.363 | 82 | 2.281 |

**As duas curvas se cruzam.** No meio a margem ganha — a custo igual, +20 erros nas dez
páginas e +9 nas limpas, uns 20 a 25% a mais. No **ponto de operação de hoje** elas empatam:
123 contra 125, e 53 contra 55. Na cauda a confiança ganha: 195 contra 176.

Isso é o oposto de dominar, e o que ele diz sobre a decisão é direto: **no ponto onde o
programa opera, trocar a régua não muda nada.** A vantagem da margem existe, mas mora num
lugar da curva que ninguém escolheu — e chegar lá significa revisar mil boxes em vez de dois
mil e achar 112 erros em vez de 123, que é troca e não ganho.

### A margem da rede, que era a pergunta original

`NeuralPredictor.margem_de_confianca` — `1 - p2/p1` sobre as duas classes mais prováveis,
irmã da razão de Lowe do k-NN. No caminho neural a rede responde 96,6% dos boxes, então é
ela que decide se a fila daquele caminho tem régua.

**Neural, 10 páginas, 263 erros** (a margem do k-NN sozinha quase não move nada ali, porque
o k-NN responde 2,7% dos boxes):

| regra | marcados | pegos | à toa |
|---|---:|---:|---:|
| conf < 0,70 | 73 | 24 | 49 |
| conf < 0,90 (hoje) | 762 | 72 | 690 |
| conf < 0,99 | 2.270 | 117 | 2.153 |
| margem < 0,30 (k-NN e rede) | 91 | **33** | 58 |
| margem < 0,90 (k-NN e rede) | 563 | 68 | 495 |
| margem < 0,99 (k-NN e rede) | 2.145 | 108 | 2.037 |

Nas 3 limpas (102 erros) a forma se repete: `conf < 0,90` dá 28 erros por 263 alarmes e
`margem < 0,90` dá 27 por 212.

**O sinal existe e é o mesmo do k-NN**: no topo a margem é mais precisa — 33 erros em 91
marcados contra 24 em 73 —, e no resto empata. A rede ser peaked não impediu a razão de
funcionar, que era o risco herdado da F19; o que impede é a mesma coisa que impede no k-NN,
que é não haver folga no ponto de operação.

### A ordenação da F43, refeita

| | 25% dos erros | 50% | 75% | | 25% | 50% | 75% |
|---|---:|---:|---:|---|---:|---:|---:|
| | **10 páginas** | | | | **3 limpas** | | |
| confiança crua (hoje) | **155** | 2.261 | 3.894 | | 94 | 914 | 1.988 |
| percentil por fonte (F25) | 864 | 2.691 | 4.617 | | 378 | 997 | 1.936 |
| margem onde há | 411 | **2.160** | **3.658** | | **93** | **775** | **1.689** |
| mín. das duas | 313 | 2.227 | 3.865 | | 89 | 851 | 1.820 |

A F43 publicou "**7x menos trabalho**". O número certo é **15% menos**, e só na cauda: para
metade dos erros, 775 contra 914 nas páginas limpas. No topo da fila a confiança ganha nas
dez páginas (155 contra 411) e empata nas limpas.

O achado de mecanismo da F43 — o roteamento **gasta** a informação da absoluta, e o que sobra
por decidir na fila é ambiguidade — **continua de pé e continua valendo**. Ele explica por que
a margem ordena melhor a cauda. O que não se sustenta é o tamanho.

### O que fica em produção

**Nada muda: a fila continua na confiança.** O `precisa_revisao` já tinha voltado atrás
quando o defeito apareceu, e a medição completa confirma que voltar foi certo — no ponto de
operação as duas réguas empatam, e empate não paga troca.

Ficam `BoxEntry.margem`, `predict_e_margem`, `fallback_chain_detalhado` e a margem da rede.
Nenhum deles custa consulta a mais (`predict_e_margem` faz a busca uma vez só) e todos são o
que qualquer nova tentativa aqui vai precisar. É a mesma decisão que a F19 tomou com
`altura_relativa` e a F24 com `voto` e `margem_de_confianca`: o instrumento fica, a conclusão
é não.

**O que mudaria isto** é escolher outro ponto de operação. Se um dia a revisão tiver orçamento
para mil boxes em vez de dois mil, a margem entrega 112 erros onde a confiança entrega 91 —
e aí a régua muda junto com a política, não antes dela.

### O que este erro ensina, e não é sobre índice de lista

Os dois defeitos empurravam para o mesmo lado, e o resultado saiu redondo demais: sete vezes
melhor. **A F24 passou uma fase inteira medindo a margem e concluindo que ela perdia.** Eu a
fiz ganhar por sete vezes numa tarde e tratei isso como boa notícia.

O sintoma não estava na aritmética, estava no **tamanho**. Um resultado que contradiz uma
fase anterior inteira exige explicar o que mudou desde ela — e a explicação que eu dei ("a
F24 mediu o elo isolado, esta mede a fila") era plausível, o que é pior que ser falsa: ela
me impediu de olhar o instrumento.

O que teria pego: rodar a régua nova **contra a antiga varrida**, que é o que esta fase fez e
a F44 não. Uma régua que domina outra em toda a curva é raro; quando aparecer, é para
desconfiar da medida antes de comemorar.

Cobertura: nenhum teste novo — os defeitos eram do instrumento, e o que os pega é a
comparação completa, não uma asserção. Reproduzir: `python medir_cadeia.py`, com `--neural`
e `--so page-0020 page-0128 page-0033` nas quatro combinações.

---

## F48 — O ponto cego do EasyOCR fecha, e sem dado novo — CONCLUÍDA

A F45 mediu que a concordância com o k-NN separa os boxes que o EasyOCR responde: onde ele
concorda o acerto é 90,5%, onde diverge é 35,3%. E registrou o custo de usar isso: um
terceiro dado por box, do mesmo tamanho da F44.

Aplicando a lição da F47 desde o começo — medir a regra nova contra a antiga **varrida**, e
não contra um ponto dela —, apareceu uma linha que faltava: **a alternativa trivial**.

**Os 160 boxes que o EasyOCR respondeu, com 92 erros:**

| regra | marcados | pegos | à toa | escapam |
|---|---:|---:|---:|---:|
| conf < 0,50 | 23 | 16 | 7 | 76 |
| conf < 0,70 | 39 | 30 | 9 | 62 |
| **conf < 0,90 (a régua de então)** | 63 | **39** | 24 | **53** |
| conf < 0,99 | 98 | 59 | 39 | 33 |
| **marcar todos (esta fase)** | 160 | **92** | 68 | **0** |
| o k-NN diverge | 139 | 90 | 49 | 2 |
| diverge e conf < 0,90 | 52 | 39 | 13 | 53 |

**A concordância não é um filtro fino, é uma aparadora.** Ela tira 19 alarmes de um
subconjunto que é **57% errado** — e custa 2 erros e um campo novo em `BoxEntry`, na
`Leitura` e nas três ações de preenchimento. Dezenove boxes em 10.504 não pagam isso.

O achado que importa é a linha do meio: a régua de então deixava **53 dos 92 erros
escaparem** ali, e o remédio não precisa de dado nenhum. `FONTES_SEMPRE_REVISADAS =
{"easyocr"}` custa 68 boxes a mais na fila em dez páginas — sete por página.

Nas 3 páginas menos contaminadas a forma se repete: 26 erros em 44 boxes, a régua antiga
pegava 9 e deixava 17 escapar.

**A razão é da régua, não do elo.** A F43 mediu ali mediana de confiança **0,9708 no erro e
no acerto** — o CRNN é confiante do mesmo jeito quando acerta e quando erra, então nenhum
corte separa nada. E o que sobra para ele é o pior da página: só vê o que a rede recusou e o
k-NN recusou, que é recorte-lixo, fragmento e glifo colado. 57% de erro contra 2,3% da página
inteira.

`manual` não é arrastado junto, e tem teste: mandar revisar o que o usuário digitou seria
circular.

### E o instrumento voltou a copiar a regra de produção — mas o conserto só veio na F51

A tabela do corte tinha `r[1] < conf_ui.LIMIAR_ALTO` escrito à mão em quatro lugares. Com a
mudança desta fase, a linha "hoje" continuou medindo a regra **velha**, calada — que é
exatamente o defeito da F44 outra vez, três fases depois.

> **Esta seção afirmava, quando foi escrita, que o conserto tinha entrado aqui. Não tinha.**
> O script que o aplicava morreu numa asserção, e o `sintaxe ok` que apareceu na saída era do
> comando seguinte — eu li a vizinhança em vez do comando. A afirmação foi para o ROADMAP e
> para a mensagem do commit desta fase antes de alguém conferir. O conserto de verdade está
> na F51, junto com a trava que o teria pegado.
>
> **A tabela desta fase não é afetada**: ela vem de `tabela_ponto_cego`, que nunca usou
> `LIMIAR_ALTO` — os cortes de confiança dela são explícitos. O que estava errado era esta
> seção, não a medida.

O que deveria ter entrado, e entrou na F51: chamar `conf_ui.precisa_revisao` através do
`_BoxFalso`, que existe desde a F23 com o docstring "o mínimo que `ui.confidence` olha num
box, **para não copiar a regra**". A ferramenta estava lá; eu é que não a usei.

Cobertura: `tests/test_f32_confianca.py`, 3 testes novos.

---

## F49 — Salvar e reabrir zerava a fila de revisão — CONCLUÍDA

Toda a série da F43 à F47 discutiu **qual régua** usa a fila de revisão. Nenhuma perguntou
se a fila sobrevive a fechar o arquivo. Não sobrevivia.

Medido no caminho de ida e volta pelo próprio programa, com três boxes dos quais dois
pendentes:

    pendentes antes  : 2 de 3
    pendentes depois : 0 de 3
    cores depois     : azul, azul, azul   ("sem informação")

A página inteira volta como não avaliada, e a revisão responde "nada pendente" com tudo por
conferir. O `F3` — pular para o próximo pendente, que é o que transforma "reler 2.000
caracteres" em "conferir os 80 duvidosos" — não anda.

### O defeito estava documentado como desenho

`ui/confidence.py` explica, e a explicação está certa: "um box carregado de um `.box` não
traz confiança nenhuma (o formato do Tesseract não guarda isso), e pintá-lo de vermelho
diria 'confira este' quando o correto é 'não sei'".

**Mas isso vale para um arquivo que veio de fora.** Para o arquivo que este programa acabou
de gravar, a informação existia e estava sendo jogada fora — e "não sei" é justamente o que
ele **não** deveria dizer sobre o que ele próprio mediu meia hora antes.

E havia um teste travando a perda como contrato: `test_box_carregado_de_arquivo_fica_sem_info`
salvava pelo programa, recarregava e **exigia** `source == ""`. Ele misturava os dois casos
num só, e o round-trip pelo próprio programa é o caso em que a perda é defeito. Foi separado
em dois: o arquivo de fora é escrito à mão no teste, que é o que ele sempre quis dizer.

### O formato já tinha a resposta

O `.box` do Tesseract tem seis campos, e este projeto já o estendeu duas vezes pela mesma
regra: sétimo campo para o ângulo (F8.1), oitavo para o negativo (F10), **escritos só quando
não são o padrão**, de modo que uma página comum grava o arquivo byte a byte igual e um
leitor de seis campos não vê diferença.

Origem e confiança entram como nono e décimo pela mesma regra:

    a 1 6 3 8 0                              <- box sem fonte, seis campos como sempre
    a 1 6 3 8 0 0 0 learner 0.2000           <- com fonte, os de trás vêm junto
    c 9 6 12 8 0 90 1 easyocr 0.5500         <- e convivem com ângulo e negativo

Os campos são posicionais, então escrever o nono obriga a escrever o sétimo e o oitavo — a
mesma regra que a F10 fixou, e há teste para ela. Campo estranho ou confiança fora de
[0, 1] é ignorado em vez de derrubar a linha, também como os anteriores: perder a origem
custa menos que perder o box.

**A margem (F44) não entra**, e é decisão e não esquecimento. Ela não está em produção
decidindo nada desde a F47, e gravar num formato de arquivo um número que nenhum código lê é
a forma mais cara de guardar uma ideia. Se a F47 for revisitada e a margem voltar, ela entra
como décimo primeiro campo, pela mesma regra.

### O que isto muda no uso

O `.box` deste programa passa a ser um arquivo de trabalho e não só de rótulo: fechar e
reabrir mantém a fila, as cores e o `F3`. Um `.box` de terceiro continua chegando sem os
campos e continua sendo lido como "não avaliado", que ali é a verdade.

Cobertura: `tests/test_f52_formato_box.py`, 6 testes novos — a ida e volta preserva a fila,
o box sem fonte grava a linha de sempre, a fonte obriga os campos de trás, o arquivo de fora
continua sem informação, campo estranho não derruba o box, e fonte com espaço passa pelo
escape (nenhuma fonte de hoje tem espaço, e a trava entra agora justamente por isso). Mais o
teste da F3.2 partido em dois. Suíte em 1.339.

---

## F50 — O léxico é aditivo, e agora está medido — CONCLUÍDA

`ui/main_window.py` justifica o filtro do léxico duas vezes com a mesma frase: **"um sinal
independente da confiança"**. A F9.1 mediu a fatia alcançável (53,8% dos erros em palavra de
prosa) e o custo (5,8% das palavras certas acendendo). **Independência não estava medida** — e
é a diferença entre um filtro que acrescenta e um que repete. Um léxico que acendesse
exatamente nos boxes já vermelhos teria os mesmos dois números da F9.1 e não valeria nada.

É a mesma pergunta que a F47 obrigou a fazer da margem, feita antes de o número desmentir
alguém.

| | 10 páginas (246 erros) | 3 limpas (105 erros) |
|---|---:|---:|
| boxes que o léxico acende | 1.333 | 475 |
| destes, a fila já mostrava | 321 | 140 |
| destes, **novos para o revisor** | 1.012 | 335 |
| erros dentro do que ele acende | 83 | 29 |
| **erros que só o léxico pega** | **41** | **13** |
| — em fração dos erros da página | 16,7% | 12,4% |
| precisão do que ele acrescenta | 4,1% | 3,9% |

**A afirmação se sustenta.** Metade dos erros que o léxico acende — 41 de 83 — estava fora da
fila, e são 16,7% de todos os erros da página. A independência não é total, e nem precisava
ser: o que ela precisava era não ser zero.

O número que fecha o argumento é o último. A precisão marginal do léxico — erros novos por
box novo aberto — é **4,1%**, contra os **5,1%** da própria fila (123 erros em 2.389
marcados). Ou seja, **o léxico entrega erro por box aberto quase na mesma taxa que a fila**,
e o faz num conjunto que a fila não alcança. Não é um sinal barato pendurado ao lado de um
caro: é outro sinal do mesmo preço, olhando para outro lugar.

Isso explica o mecanismo que a F1.9 tinha registrado e ninguém tinha ligado ao léxico: a
mediana de confiança de um erro é **1,000**, então há uma família inteira de erros que
nenhum corte de confiança alcança — e é nela que o dicionário morde.

### O que fica

Nenhuma mudança de código: a fase mediu uma afirmação que já estava em produção e a
confirmou. O que entra é a tabela, ao lado das duas frases que a alegavam sem número, e
`tabela_lexico` em `medir_cadeia.py`, montada sobre o mesmo `suspeitas_da_pagina` que a UI
consome — a população é a de produção, com a leitura que a cadeia deu.

**O que não foi medido**, e vale registrar: se os 41 erros que só o léxico pega são *úteis*
ao revisor. Eles estão em palavra de prosa, então provavelmente sim — palavra errada é mais
fácil de ver que caractere errado. Mas "mais fácil de ver" é medida com gente, como a F31
registrou sobre o custo de consertar um box.

Cobertura: nenhum teste novo — é instrumento. Reproduzir: `python medir_cadeia.py`.

---

## F51 — A régua de cada fonte, medida — e a mais plana é a que cobre a página

A F48 pôs o EasyOCR em `FONTES_SEMPRE_REVISADAS` porque ali "a mediana de confiança é a
mesma no erro e no acerto". É um argumento por anedota de duas medianas, e ele tratou **um
caso** e não a classe: `easyocr_linha` acerta 33% e ninguém tinha perguntado se a régua dele
separa.

A medida certa é a **separação**: dado um erro e um acerto da mesma fonte, com que
frequência a régua os põe na ordem certa. É a U de Mann-Whitney normalizada, que é a área
sob a curva ROC. 1,00 é régua perfeita, 0,50 é moeda. Não é acerto e não é confiança média —
uma fonte pode acertar pouco e ainda assim **saber** quando errou, e é essa que a fila
consegue usar.

| caminho | fonte | boxes | erros | acerto | **separação** | na fila hoje |
|---|---|---:|---:|---:|---:|---:|
| híbrido | learner | 10.335 | 148 | 98,6% | **0,795** | 22% |
| | easyocr | 160 | 92 | 42,5% | 0,582 | 100% |
| | easyocr_linha | 9 | 6 | 33,3% | 0,667 | 100% |
| neural | **neural** | **10.144** | 191 | 98,1% | **0,634** | **6%** |
| | learner | 281 | 23 | 91,8% | 0,726 | 39% |
| | easyocr | 50 | 32 | 36,0% | 0,531 | 100% |
| | easyocr_linha | 29 | 17 | 41,4% | 0,659 | 100% |
| 3 limpas | learner | 3.393 | 76 | 97,8% | 0,696 | 28% |
| | easyocr | 44 | 26 | 40,9% | 0,536 | 100% |

### Nenhuma fonte nova entra na lista, e por dois motivos diferentes

O `easyocr_linha` era o candidato óbvio — 33% de acerto no híbrido, 41% no neural. **Ele já
está 100% na fila, e por construção, não por sorte.** A F17 decidiu que leitura divergente
vale a *menor* das duas confianças ("a linha venceu, mas há dúvida real, e vale a menor, que
é o que põe o box na fila de revisão"), e isso empurra todos abaixo do corte. Uma decisão de
dezessete fases atrás já tinha resolvido o caso.

O `easyocr` confirma a F48 com número em vez de anedota: 0,582 e 0,531, encostado na moeda.

### O achado é outro, e é o maior desta série sobre a fila

**A rede tem separação 0,634 e responde 96,6% dos boxes — e só 6% deles estão na fila.**

Ela acerta 98,1%, então a régua dela parecer ruim não é contradição: acertar muito e saber
quando errou são coisas diferentes, e é exatamente o que esta medida separa. 0,634 está mais
perto de moeda que de régua boa, e é a régua que governa quase toda a página no caminho que
usa a rede.

Isso põe número na frase que a F1.9 deixou solta e que `ui/main_window.py` cita duas vezes —
"1,000 é a confiança mediana de um erro". Não é um detalhe de calibração: é a régua
principal do programa mal ordenando erro contra acerto, e é o teto da fila de revisão como
ela existe hoje.

**E não há remédio pela lista.** Pôr `neural` em `FONTES_SEMPRE_REVISADAS` marcaria a página
inteira, que é o não-filtro que a F53 acabou de tirar das ações de OCR puro. O caminho, se
houver, é outra régua para a rede — e a F47 já mediu a candidata natural, a razão entre as
duas primeiras probabilidades: ela ordena melhor no topo (33 erros em 91 marcados contra 24
em 73) e empata no ponto de operação. **A F47 mediu a coisa certa e concluiu "não paga
trocar"; esta fase mostra por que a pergunta vai voltar.**

**A F54 respondeu, e a resposta é não.** A margem da rede desarruma 26,6% da ordem e separa
0,6335 contra os 0,6339 da confiança: ela acrescenta informação, e a informação não é sobre
erro. O teto de 0,634 fica de pé.

### O que fica

Só instrumento: `tabela_regua_por_fonte` em `medir_cadeia.py`, com a separação ao lado do
acerto e da fração já na fila. `FONTES_SEMPRE_REVISADAS` não muda.

O que a tabela dá e as anteriores não davam é **uma pergunta comparável entre fontes**. Até
aqui cada elo era discutido com a sua própria evidência — mediana aqui, tabela de corte ali —
e a comparação era impossível. Agora é uma coluna.

Cobertura: nenhum teste novo — é instrumento. Reproduzir: `python medir_cadeia.py`, com
`--neural` e `--so page-0020 page-0128 page-0033`.

---

## F52 — A trava contra o instrumento copiar a regra de produção — CONCLUÍDA

O mesmo defeito apareceu quatro vezes nesta série, e o custo dele cresceu a cada vez:

- **F43 e F44** — a margem do k-NN aplicada a boxes que outro elo respondeu. Duas fases
  publicaram conclusões erradas, uma delas virou mudança de produção, e a F47 desfez;
- **F48** — `conf < LIMIAR_ALTO` copiado à mão. A própria fase mudou a regra
  (`FONTES_SEMPRE_REVISADAS`) e a linha "hoje" das tabelas continuou medindo a anterior.

Em todos, o instrumento **respondia** a pergunta que devia **fazer** a produção. E em todos
havia ferramenta pronta: `_BoxFalso` existe desde a F23 com o docstring "o mínimo que
`ui.confidence` olha num box, **para não copiar a regra**".

### A trava

`test_o_instrumento_nao_copia_a_regra_da_fila` varre a AST de `medir_cadeia.py` atrás de
**comparações** contra `LIMIAR_ALTO`, `LIMIAR_MEDIO` ou `LIMIAR_DE_MARGEM`. Comparação e não
menção: citar o limiar dentro de uma f-string de rótulo é legítimo — o que denuncia é usá-lo
para decidir.

O segundo teste guarda o outro lado: `_BoxFalso` tem de continuar servindo à pergunta. Se
`precisa_revisao` passar a olhar um campo que ele não tem, o instrumento quebra alto, que é
o que se quer em vez de divergir calado.

### A trava foi conferida contra o defeito, e não contra si mesma

Um teste que nunca viu o defeito que promete pegar é a mesma classe de coisa que esta fase
conserta. Reintroduzi a cópia — `marcados_hoje = [r for r in linhas if r[1] <
conf_ui.LIMIAR_ALTO]` — e confirmei que a varredura acusa (`LIMIAR_ALTO`, linha 966) antes de
desfazer.

### E o conserto da F48 não existia

Ao aplicar a trava, os quatro sítios apareceram — o que significava que o conserto anunciado
na F48 nunca tinha entrado. **O script que o aplicava morreu numa asserção, e o `sintaxe ok`
que apareceu na saída era do comando seguinte.** Eu li a vizinhança em vez do comando, e a
afirmação foi para o ROADMAP e para a mensagem de commit sem ninguém conferir.

A F48 foi corrigida no lugar, com o aviso. A tabela dela não é afetada — vem de
`tabela_ponto_cego`, cujos cortes de confiança são explícitos —, mas a seção que descrevia o
conserto era falsa.

É a lição da série aplicada a mim mesmo, e ela vale escrita como regra: **conferir o
comando, não a vizinhança dele.** Um `ok` numa saída de terminal pertence a algum comando; a
qual, é preciso olhar.

Cobertura: `tests/test_f23_medir_cadeia.py`, 2 testes novos. Os quatro sítios foram
consertados de fato — confirmado por `grep`, que agora só encontra `LIMIAR_ALTO` em rótulo
impresso.

---

## F53 — A regra da F48 valia onde não foi medida, e a cor discordava da fila — CONCLUÍDA

Duas consequências da F48 que apareceram ao olhar a interface, e a primeira é um defeito
dela.

### `easyocr` é dois elos com o mesmo nome

A F48 mediu os boxes em que o EasyOCR é o **último recurso** — o que sobra depois de a rede
recusar a 0,80 e o k-NN recusar a 0,30. Ali são 57% de erro, e marcar todos é a decisão
certa.

Mas `"easyocr"` também era a fonte gravada pelas duas ações em que ele é o **leitor**: «OCR
(EasyOCR)» e «OCR (EasyOCR por linha)». Nessas, o mesmo elo lê a página inteira e acerta
89,5% (F17). Depois da F48, elas passaram a marcar **todos os boxes da página** — que não é
filtro nenhum.

> **Corrigido na F55:** os 89,5% são da leitura **por linha**, e são duas ações a gravar essa
> fonte. A por caractere acerta **73,2%**. A isenção continua de pé, por outro motivo —
> separação 0,776 contra os 0,582 do último recurso —, mas esta seção defendeu uma das duas
> ações com a medida da outra.

A fonte ganhou nome próprio, `easyocr_so`, e a regra ficou onde foi medida. O nome está nas
duas ações com o motivo escrito, porque a diferença não é de implementação e sim de
população: **o mesmo classificador tem duas taxas de erro conforme o que lhe é entregue.**

### A cor dizia verde e a fila dizia pendente

Levantei isto na F44 como pergunta aberta — "um box pode sair verde e mesmo assim entrar na
fila" — e naquele momento era hipótese. A F48 tornou realidade: um box do EasyOCR com
confiança 0,99 saía **verde**, com **"99%"** na lista lateral, e entrava nos pendentes. O
usuário navega os pendentes com `F3` e vê verde.

Não é uma contradição que se resolva escolhendo um dos dois lados. **Naquele elo o número
não quer dizer nada** — separação 0,582, quase moeda (F51) —, e a cor não pode fingir que
quer. Fonte de régua plana sai vermelha, e o rótulo vira `!`.

O `!` não é o `?` de "não avaliado" nem uma porcentagem baixa. Ele diz o que é verdade ali:
**há leitura, e o número dela não vale.** Escrever "99%" ao lado de um box vermelho e
pendente seria contradizer duas vezes na mesma linha.

### O que isto fecha, e o que não

Fecha a coerência: as três coisas que a interface diz sobre um box — cor, rótulo e fila —
passam a concordar, e passam a concordar **pela mesma regra**, não por coincidência de
limiar.

Não fecha a pergunta da F44 no caso geral. Se um dia a margem voltar (F47), a fila terá um
critério que a cor não tem, e a divergência volta — desta vez entre dois números que ambos
querem dizer alguma coisa, que é um problema mais difícil que este.

Cobertura: `tests/test_f32_confianca.py`, 3 testes novos — o leitor não entra na regra, a cor
não discorda da fila, e a lista lateral mostra `!` em vez de `99%`. Suíte em 1.346.

---

## F54 — A outra régua da rede desarruma um quarto da ordem e não separa um erro a mais — MEDIDA

A F51 fechou com a rede tendo separação 0,634, governando 96,6% da página e com 6% dos
boxes na fila, e deixou a pergunta escrita: **existe régua melhor para ela?** A candidata
tinha nome — a razão de Lowe, `1 - p2/p1` — e a F47 já a tinha medido, mas em **quatro
pontos de corte**. "Empata no ponto de operação" é uma frase sobre o ponto, não sobre a
régua.

Separação é a curva inteira num número, e é a única forma de fazer a pergunta certa.

| caminho | fonte | boxes | erros | confiança | margem | mín. das duas | discordam |
|---|---|---:|---:|---:|---:|---:|---:|
| neural | **neural** | 10.144 | 191 | **0,6339** | **0,6335** | 0,6344 | **26,6%** |
| | learner | 281 | 23 | 0,7256 | 0,7264 | 0,7264 | 20,7% |
| híbrido | learner | 10.335 | 148 | 0,7947 | **0,8122** | 0,8116 | 18,1% |
| 3 limpas | learner | 3.393 | 76 | 0,6962 | **0,7424** | 0,7325 | 34,4% |

`discordam` é a fração de pares vizinhos em que a margem inverte a ordem da confiança.

### A resposta é não, e a coluna da direita é o que a torna interessante

**A margem da rede não é a mesma régua** — ela desarruma um quarto da ordem — **e mesmo
assim separa exatamente igual**: 0,6335 contra 0,6339, uma diferença de 0,0004 sobre 1,9
milhão de pares (191 erros × 9.953 acertos). Ela reordena 26,6% da página e não põe um erro
a mais abaixo de um acerto.

Isso é diferente de "as duas réguas são a mesma coisa", que é o que eu esperava ver, e é
uma resposta mais dura: **a informação que a margem acrescenta existe e não é sobre erro.**
Não há de onde tirar separação melhor mexendo nessas duas quantidades.

No k-NN o quadro é outro e confirma que a medida funciona: **menos discordância e ganho
real** — 18,1% e +0,018 no híbrido, 34,4% e +0,046 nas páginas limpas. A margem do k-NN é
uma régua melhor que a confiança dele. É a mesma conclusão que a F24 e a F47 tiveram por
outros caminhos, agora num número comparável entre fontes.

### A coluna `discordam` existe porque eu não sabia se era achado ou bug

As três colunas saíram idênticas na primeira rodada — 0,634, 0,634, 0,634 no `neural`, e
0,726 nas três no `learner`. Colunas iguais em duas fontes diferentes é o formato de um
instrumento quebrado, não o de um resultado, e a F47 é justamente a fase em que eu comemorei
antes de conferir.

O que resolveu não foi olhar o código: foi perguntar ao instrumento **por que** elas seriam
iguais. Duas réguas que ordenam igual têm a mesma separação por construção — ela não se move
por reescala monótona, que é o teste `test_a_separacao_nao_muda_com_o_corte_nem_com_a_escala`.
Então ou a discordância era zero, e as colunas iguais eram trivialidade, ou não era, e o
empate era o achado. **A coluna responde qual das duas**, e ficou.

O híbrido tinha respondido antes disso, aliás: lá as colunas divergiram (0,795 contra 0,812)
na mesma rodada, o que já dizia que o instrumento distinguia.

### Isto não contradiz a F47, e vale dizer onde as duas se encontram

A F47 mediu que no topo da curva a margem da rede é **mais precisa** — 33 erros em 91
marcados contra 24 em 73 — e que no resto empata. Uma vantagem no topo e um empate na curva
inteira convivem: o que a margem ganha nos primeiros 90 boxes ela devolve abaixo, e a
separação, que é a curva toda, registra a soma. As duas medidas estão certas e respondem
perguntas diferentes; a desta fase é a que a F51 fez.

### O teto da F51 fica de pé

**0,634 continua sendo a régua que governa 96,6% da página**, e nenhuma escolha de limiar
melhora isso — mexer no 0,90 anda sobre a mesma curva, que é o que o segundo teste fixa. A
fila do caminho neural tem esse teto até aparecer uma quantidade nova, e as duas que estavam
na mão não são.

### O que fica

Só instrumento: `_separacao` extraída da F51 e `tabela_regua_alternativa` em
`medir_cadeia.py`. `FONTES_SEMPRE_REVISADAS` e `precisa_revisao` não mudam.

A margem só vale para quem a produziu — fonte sem régua própria sai com `—` e não com um
número emprestado de outro elo, que é o conserto que a F47 fez na F43 e na F44, agora com
teste.

Cobertura: `tests/test_f23_medir_cadeia.py`, 3 testes novos — a definição da separação, a
invariância por reescala e a trava da margem emprestada. Suíte em 1.349. Reproduzir:
`python medir_cadeia.py`, com `--neural` e `--so page-0020 page-0128 page-0033`.

---

## F55 — O número que isentou o leitor era da outra ação, e a isenção estava certa por outro motivo — CONCLUÍDA

A F53 tirou o leitor da regra da F48 com esta frase, que está no código, no teste e na
mensagem de commit: *"na ação em que ele é o leitor o mesmo elo acerta 89,5%"*.

**89,5% é o número da F17, que é a leitura por linha.** A fonte `easyocr_so` é gravada por
**duas** ações — «OCR (EasyOCR)», caractere a caractere, e «OCR (EasyOCR por linha)» —, e a
primeira é a que a F16 mediu em 74,9%. A isenção foi decidida com o número da outra.

É a F41 de novo em outra roupa: duas populações com o mesmo nome, e a tabela publicada saiu
da errada.

### As duas ações, medidas

| ação | fonte | boxes | erros | acerto | separação | na fila | pegos | escapam |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **OCR (EasyOCR)** | easyocr_so | 10.502 | 2.808 | **73,3%** | **0,776** | 4.366 | 2.005 | **803** |
| | a ação inteira | 10.504 | 2.810 | 73,2% | | 4.368 | 2.007 | 803 |
| **OCR (EasyOCR por linha)** | easyocr_so | 7.963 | 457 | 94,3% | 0,794 | 2.399 | 326 | 131 |
| | easyocr_linha | 2.541 | 670 | 73,6% | 0,756 | 2.466 | 668 | 2 |
| | a ação inteira | 10.504 | 1.127 | **89,3%** | | 4.865 | 994 | 133 |

Os dois números da F16 e da F17 se reproduzem — 73,2% e 89,3% —, o que confirma que são
mesmo duas ações e não duas leituras da mesma.

### A decisão estava certa, e o motivo é outro

`easyocr_so` fica fora de `FONTES_SEMPRE_REVISADAS`, e agora por uma razão comparável entre
fontes em vez de por acerto: **separação 0,776**, contra os 0,582 que puseram `easyocr` na
lista. É régua melhor que a da rede (0,634), que ninguém propõe marcar inteira.

O que muda é a justificativa escrita — no código, no teste e nesta tabela. A F51 já tinha
estabelecido que acerto não responde a pergunta ("uma fonte pode acertar pouco e ainda assim
saber quando errou"), e o converso é o que estava valendo aqui sem ninguém conferir: **uma
fonte pode acertar bastante e ter régua ruim.** Não é o caso desta, e ninguém sabia disso
antes desta fase.

### O que a linha faz, medido onde ela age

|  | boxes | a âncora acertava | e depois da linha |
|---|---:|---:|---:|
| a linha trocou | 2.541 | **7,4%** | **73,6%** |
| a linha não encostou | 7.963 | 94,3% | 94,3% |

A F17 mediu o efeito na página — 72,9% para 89,5% — e a página é a soma de duas populações
muito diferentes. Cruzando as duas leituras pelo mesmo box: **o alinhamento troca quase
exclusivamente os boxes que o leitor por caractere tinha errado**, e nesses o acerto vai de
7,4% para 73,6%. Nos que ele não encosta, 94,3%.

Isto não estava medido. A F17 mostrou que a linha ganha; esta tabela mostra que ela ganha
**escolhendo onde agir**, e é a diferença entre um remédio que funciona e um que funciona por
ser aplicado em todo mundo. É o mesmo mecanismo da F45 — concordância separa —, agora do lado
do leitor.

### O que a fila entrega em cada ação

Na ação por linha a fila pega 994 dos 1.127 erros: **133 escapam**. Na ação por caractere
pega 2.007 dos 2.810: **803 escapam, 28,6% deles**, e a página fica com um quarto errado e
58% dela verde.

Não é defeito da régua — 0,776 é boa. É o ponto de operação: o `LIMIAR_ALTO` é um número só
para o programa inteiro, e ele cai em lugares muito diferentes de cada curva (6% da página no
caminho neural, 42% nesta ação). **Fica registrado e não muda aqui**: mexer nesse número mexe
em todos os caminhos de uma vez, e a F47 já mostrou o que custa trocar régua sem varrer a
antiga.

### A trava, que não existia

`easyocr_so` é a fonte de que dependem a cor, o rótulo e a fila desde a F53, e **nada prendia
o nome**. Trocá-lo por `"easyocr"` numa das duas ações põe a página inteira em vermelho e na
fila, calado, e é uma linha de diferença.

Conferida contra o defeito, como manda a F52: reintroduzi `"easyocr"` em
`auto_fill_characters_easyocr` e o teste acusou antes de desfazer.

Cobertura: `tests/test_f32_confianca.py`, 1 teste novo cobrindo as duas ações — a por
caractere e a por linha, esta última nos boxes que a linha confirmou, que é onde a fonte da
âncora sobrevive. Suíte em 1.350. Reproduzir: `python medir_cadeia.py --leitor`.

---

## F56 — A ação que deixava escapar 803 erros tem uma fonte só, e o orçamento de hoje bastaria a uma régua perfeita — MEDIDA

A F55 fechou acusando o ponto de operação: `LIMIAR_ALTO` é um número só para o programa
inteiro, cai em 6% da página no caminho neural e em 42% da ação «OCR (EasyOCR)», e ali
**803 erros escapam**. A régua de lá é boa (separação 0,776), então o suspeito era onde ela
foi cortada. Esta fase construiu o instrumento que precifica o corte **por fonte** e o
comparou com o número único — a custo igual e a recall igual, que é a regra da F47, e com o
limiar ajustado em dez páginas e medido na décima primeira.

**A hipótese não sobreviveu ao próprio instrumento**, e por dois motivos independentes.

### Na ação acusada não há o que distribuir

| a custo igual | marcados | erros pegos | à toa | escapam | fora da amostra |
|---|---:|---:|---:|---:|---:|
| hoje (um limiar para todos) | 4.368 | 2.007 | 2.361 | 803 | |
| um percentil por fonte | 4.368 | 2.007 | 2.361 | 803 | 2.007 em 4.369 |
| um limiar por fonte (teto) | 4.367 | 2.007 | 2.360 | 803 | 2.006 em 4.364 |
| **oráculo (gasta tudo em erro)** | 4.368 | **2.810** | 1.558 | **0** | |

`easyocr_so` responde 10.502 dos 10.504 boxes — os outros dois entram por regra fixa. **Uma
fonte só**: um corte por fonte é o corte único com outro nome, e a tabela mostra isso sem
margem para leitura torta. O percentil cai em 0,9001 e marca os mesmos 42%, o que também
serve de aferição do instrumento: pedindo a regra de hoje, ele devolve a regra de hoje.

### E o orçamento não é o que falta

A linha do oráculo é a que responde a F55. **Com os mesmos 4.368 boxes marcados, uma régua
perfeita pegaria os 2.810 erros** — todos. O dinheiro para pegar os 803 já está sendo gasto;
o que não existe é a separação para saber em quem gastá-lo. Os 803 são os 0,776 da régua, e
nenhum ponto de operação os alcança.

Isso troca a pergunta que a F55 deixou aberta. Não é "onde cortar", é "que régua" — e a F54
já mediu o que custa procurar régua melhor sem varrer a antiga.

### Onde havia duas fontes, o ganho não sobreviveu à validação

A ação «OCR (EasyOCR por linha)» é o caso em que o mesmo 0,90 cai mesmo em lugares
diferentes: marca 30% de `easyocr_so` e 97% de `easyocr_linha`.

| a custo igual | marcados | erros pegos | escapam | fora da amostra |
|---|---:|---:|---:|---:|
| hoje | 4.865 | 994 | 133 | |
| um percentil por fonte | 4.865 | 872 | 255 | 876 em 4.892 |
| um limiar por fonte (teto) | 4.864 | **998** | 129 | 992 em 4.855 |

| a recall igual | marcados | erros pegos | fora da amostra |
|---|---:|---:|---:|
| hoje | 4.865 | 994 | |
| um percentil por fonte | 6.428 | 994 | 995 em 6.446 |
| um limiar por fonte (teto) | **4.805** | 994 | 982 em 4.813 |

Dentro da amostra o teto ganha quatro erros a custo igual, e economiza 60 boxes a recall
igual — 1,2%. **Fora da amostra some**: 992 pegos contra os 994 de hoje, e 982 em 4.813
contra 994 em 4.865, que é pegar doze erros a menos para poupar 52 boxes. Quatro erros em
10.504 é o que um limiar por fonte decora de onze páginas, e não o que ele sabe.

O percentil é pior nas duas direções, e a segunda tabela diz por quê: para alcançar o recall
de hoje ele marca 6.428 boxes, um terço a mais. Igualar a *fração* marcada de cada fonte
ignora que as duas curvas têm formatos diferentes.

### O que fica

Só instrumento: `tabela_ponto_de_operacao` em `medir_cadeia.py`, com os cortes por
orçamento, por recall e por percentil, e a coluna fora da amostra. `LIMIAR_ALTO`,
`precisa_revisao` e `FONTES_SEMPRE_REVISADAS` não mudam.

Fica registrado o que a F55 pedia e esta fase responde: **o ponto de operação estava certo.**

Cobertura: `tests/test_f23_medir_cadeia.py`, 5 testes novos — o corte que não separa dois
boxes com a mesma nota, o teto respeitando orçamento e recall, o teto nunca ficando abaixo
de um limiar único, o corte caindo na regra de produção onde não há curva, e a trava de que a
coluna fora da amostra não vê a página que mede. Suíte em 1.356. Reproduzir:
`python medir_cadeia.py --leitor`.

---

## F57 — A régua de `easyocr_so` não é a confiança dele, é concordar com o k-NN — MEDIDA

A F56 trocou a pergunta: o orçamento da fila já basta, e os 803 erros que escapam da ação
«OCR (EasyOCR)» são a separação de 0,776. Sobrou "que régua". Esta fase mediu nove
candidatas na escala da F51, todas feitas de sinal que o roteamento **já produziu e
descartou naquele mesmo box** — nenhuma pede modelo novo nem rótulo novo.

**Pela primeira vez nesta série a resposta é sim, e não por pouco.**

| régua | separação | marcados | pegos | escapam |
|---|---:|---:|---:|---:|
| hoje (confiança do EasyOCR) | 0,7761 | 4.366 | 2.005 | 803 |
| **concorda com o k-NN** | **0,9781** | 2.864 | 2.733 | 75 |
| **concorda, e a confiança dentro** | **0,9847** | 4.366 | 2.756 | **52** |
| mín. das duas confianças | 0,7556 | 4.366 | 1.922 | 886 |
| margem da rede | 0,6682 | 4.366 | 1.818 | 990 |
| confiança da rede | 0,6648 | 4.366 | 1.805 | 1.003 |
| margem do k-NN | 0,5407 | 4.366 | 1.303 | 1.505 |
| confiança do k-NN | 0,5371 | 4.366 | 1.273 | 1.535 |
| proximidade da base (−dist) | 0,5371 | 4.366 | 1.273 | 1.535 |

A binária **ganha nos dois eixos ao mesmo tempo**, que é o que quase nunca acontece: 728
erros a mais que hoje marcando 1.502 boxes a menos. Ela não consegue gastar o orçamento —
tem dois degraus, e o `marcados` para em 2.864 — e é por isso que a segunda linha existe:
somar a confiança do EasyOCR ordena *dentro* de cada grupo sem nunca cruzá-los, porque a
confiança vive em [0, 1].

### A tabela quase não valia, e a trava é a F37

A base do k-NN contém cópia byte a byte destas páginas. Num box desses o k-NN não
classifica — **lembra do rótulo** —, e "concorda com o k-NN" seria "concorda com o
gabarito": uma separação de 0,98 mediria a cópia, e a fila funcionaria na medição e falharia
no livro seguinte. `dist == 0` é a definição direta de cópia exata, a mesma da coluna "já na
base" desde a F23, e 4.874 dos 10.502 boxes caem nela.

| só os 5.628 que a base não tem | separação | marcados | pegos | escapam |
|---|---:|---:|---:|---:|
| hoje | 0,7932 | 2.345 | 1.112 | 381 |
| concorda com o k-NN | 0,9597 | 1.551 | 1.420 | 73 |
| **concorda, e a confiança dentro** | **0,9728** | 2.345 | 1.445 | **48** |

**Cai 0,012 e continua de pé.** Fora da base, ao mesmo custo de hoje, a régua nova pega
1.445 dos 1.493 erros contra 1.112 — os que escapam vão de 381 para 48, 87% a menos. A
contaminação explica quase nada do ganho, que era o desfecho que esta fase mais arriscava.

### Duas leituras de controle, e a segunda desmente a F24 aqui

A trava da F54 pegou o que devia: `confiança do k-NN` e `proximidade da base` saíram
idênticas até a quarta casa com a mesma discordância. **Têm de sair**: a confiança do k-NN é
`1 − d/D`, transformação monótona da distância, e são a mesma régua com outra roupa. A
tabela disse isso sozinha, que é o que ela existe para fazer.

E o **mínimo das duas** — a ideia da F24, que ganhou lá — perde aqui: 0,7556 contra os
0,7761 de hoje. Misturar uma régua boa com uma que é quase moeda (0,5371) contamina a boa.
A F24 mediu o mínimo entre duas réguas *do mesmo elo*; aqui uma delas é de um elo que foi
recusado neste box, e a diferença aparece no número.

A proibição da F47 — número de outro elo não se empresta calado — sai **confirmada e
refinada**. Emprestar a *nota* do k-NN é ruim mesmo (0,5371, quase moeda, o pior da tabela).
O que vale não é a nota dele: é ele **concordar**. Concordância não é um número emprestado,
é uma medida sobre os dois elos juntos, e é a F45 outra vez.

### O que fica, e o que falta antes de embarcar

Só instrumento: `tabela_regua_do_easyocr` e `_reguas_candidatas` em `medir_cadeia.py`, atrás
de `--regua`, mais `_fora_de_ordem` promovida a função de módulo para as duas tabelas de
régua a chamarem em vez de copiarem. `precisa_revisao` não muda **ainda**, e faltam duas
coisas para que possa mudar:

- **a assimetria do corte.** A separação não tem parâmetro, mas a coluna `marcados` escolhe
  o corte da candidata *na mesma amostra*, enquanto o `LIMIAR_ALTO` de hoje é fixo e não foi
  ajustado em lugar nenhum. A comparação a custo igual favorece a candidata nessa medida, e
  quem responde é a coluna fora da amostra da F56, aplicada a esta régua;
- **o custo em produção.** Nos caminhos híbrido e neural a concordância é de graça — o k-NN
  já foi consultado, e foi por ele ter sido recusado que o box chegou ao EasyOCR. Na ação
  «OCR (EasyOCR)», que é onde estão os 803, o k-NN **não** é consultado hoje: são 12 ms por
  box sobre os 16 que a ação já paga, +75%.

Cobertura: `tests/test_f23_medir_cadeia.py`, 5 testes novos — a separação lida por régua, a
binária não prometendo corte que não alcança, sinal ausente saindo `—` em vez de zero, a
população restrita à fonte medida, e a trava da contaminação (dentro da base perfeita, fora
dela moeda). Suíte em 1.361. Reproduzir: `python medir_cadeia.py --regua`.

---

## F58 — O diagrama deixa de ser recorte e passa a ser desenho — CONCLUÍDA

A F2.6 exporta EPUB e DOCX recortando o diagrama da imagem da página: fiel, e feio —
hachura de meio-tom, moldura torta, tinta do papel. Como a F7.x já **lê** a posição, o
diagrama pode nascer redesenhado a partir do FEN, com fonte de xadrez, no tamanho que o
formato pedir e com coordenadas só quando alguém pedir.

**O número que manda nesta fase é o da F8.4.** Nosso leitor faz 92,49% de tabuleiro
inteiro certo em 346 tabuleiros de livros fora do treino — **um em treze sairia errado**,
e errado do pior jeito possível: o desenho vem limpo, com a mesma nitidez nas 64 casas, e
nada nele denuncia que o bispo de c1 era um peão. O recorte, quando o OCR erra, ao menos
mostra o que o livro imprimiu.

Daí o desenho do conjunto: **não é "renderizar", é "renderizar com porteiro"**, e o
recorte não morre — vira a queda de quem não passa. Quem decide é o porteiro (etapa 2);
o `core/render_diagrama.py` só desenha.

### Etapa 0 — o mapa da fonte, que é o que não existia

Uma fonte de diagrama mapeia caractere → *casa inteira*: peça e fundo saem no mesmo
glifo, e por isso cada peça tem **duas letras**, uma por cor de casa. Esse mapa não estava
em lugar nenhum — o projeto irmão `Chess_SVG_Generator` tem sete dessas fontes em
`app/templates/` e **não usa nenhuma**, renderiza com `chess.svg`.

**Três fontes de evidência independentes, e as três concordam.**

1. **A documentação da própria fonte.** A página 3 do `fonts/SkakNew.pdf` imprime a
   posição inicial na SkakNew-Diagram, e dela saem 26 caracteres de uma vez:

       8rmblkans   7opopopop   60Z0Z0Z0Z   2POPOPOPO   1SNAQJBMR

   Maiúscula é branca, minúscula é preta, `0` é casa clara vazia e `Z` é escura vazia.
   Sobram quatro combinações que a posição inicial não mostra — dama preta em casa clara,
   rei preto em escura, e as duas brancas correspondentes —, e elas se fecham por
   eliminação: `q j` e `L K`.

2. **A geometria dos glifos**, que não depende de ler PDF nenhum. As 12 letras de casa
   clara desenham só a peça; as 12 de casa escura pintam o quadrado inteiro. Medido na
   tinta das quinas da casa renderizada, 0 é branco e 1 é preto:

   | | faixa | caracteres |
   |---|---:|---:|
   | casa clara | 0,000 – 0,000 | 13 |
   | casa escura | 0,150 – 0,150 | 13 |
   | **vão** | **+0,150** | |

   Os dois grupos batem letra por letra com o que a posição inicial diz.

3. **As duas redes da F7.4/F7.5.** Renderizar o FEN com o mapa e reler o desenho com o
   `diagrama.ler` devolve o mesmo FEN:

   | ida e volta | casa certa | tabuleiro inteiro |
   |---|---:|---:|
   | 2 tabuleiros de cobertura (as 24 combinações) | 100,00% (128) | 100,00% (2 de 2) |
   | 348 tabuleiros do corpus da F8.4 | 100,00% (22.272) | 100,00% (348 de 348) |

**Esses 100% medem o mapa, e não o leitor** — dizê-lo é obrigatório, porque o mesmo
leitor faz 92,49% no scan. O render é domínio limpo: sem papel, sem meio-tom, sem moldura
torta. O que a tabela prova é que o mapa está certo; o que o porteiro vale continua por
medir, e é a etapa 2.

### O que a fonte respondeu de quebra

- **A licença permite embutir.** LPPL 1.2+, © 2004–2009 Ulrich Dirr, sobre as fontes
  `skak` de Torben Hoffmann e Dirk Bächle, elas mesmas sobre a `chess` de Piet Tutelaers.
  Redistribuição autorizada — é o que abre a porta da F59.
- **A fonte tem 46 codepoints, e entre eles não há `a`–`h` nem `7` e `8`.** As letras e
  dígitos que sobrariam para rótulo desenham casa. **Coordenada sai em fonte de texto**,
  e no modo de fonte embutida isso vira alinhamento em CSS e em tabela, não um caractere
  a mais na linha.
- **Doze glifos de avanço zero** (`1`–`6`, `T`–`Y`) e o `z`. São a família de destaque —
  as mesmas 12 peças em casa cheia. Nenhum uso ainda; ficam na folha de contato.
- **O `-8`**: os glifos de casa escura transbordam 8 milésimos de em para cada lado, para
  que não sobre linha branca entre as filas. Quem desenha respeita avanço de 1 em exato,
  sem espaçamento e sem entrelinha.

### O que entrou

`core/render_diagrama.py` (mapa + desenho, PNG por PyMuPDF, **sem dependência nova**),
`core/dados/fontes_de_diagrama.json` (o mapa, versionado, com o sha256 do arquivo da
fonte junto — F7.3 aplicada aqui), `medir_fonte_diagrama.py` (as quatro provas e a folha
de contato de conferência humana) e `tests/test_f58_render_diagrama.py`, 15 testes.

Cobertura da fase inteira: 15 + 7 (`test_f58_porteiro.py`) + 9 novos em
`test_f26_livro.py`, que agora tem 30.

O lado do desenho é arredondado para múltiplo de 8, e não é preciosismo: quem relê divide
a imagem em 8×8 **iguais**, e a F8.4 mediu que moldura de 2% desloca toda casa.

### Etapa 2 — o porteiro, e o piso que a medição escolheu

Mesmos 346 tabuleiros do split `test` do corpus da F8.4, que nunca entraram em treino
nenhum. **24 deles saem errados** — 93,06% de tabuleiro inteiro certo, contra os 92,49%
que a F8.4 registrou; são dois tabuleiros de diferença, a base de ocupação mudou nesse
intervalo pelas confirmações do usuário (F8.3), e a atribuição não foi feita.

As oito réguas candidatas não pedem modelo novo nem rótulo novo: são sinais que a
`diagrama.ler` já produzia e descartava. Separação é a da F51 — dado um tabuleiro errado
e um certo ao acaso, com que frequência a régua os põe na ordem certa:

| régua | separação |
|---|---:|
| confiança da peça, a média | 0,9812 |
| **a menor das duas (peça e ocupação), na casa mais fraca** | **0,9806** |
| a menor das duas, zerada se implausível | 0,9806 |
| a menor das duas, zerada se implausível ou arbitrada | 0,9806 |
| confiança da peça, a pior casa | 0,9805 |
| confiança da ocupação, a pior casa | 0,8830 |
| nada foi arbitrado | 0,6875 |
| posição plausível | 0,5000 |

**A média ganha por 0,0006 e perde onde importa.** Seis milésimos em 24×322 pares são
cinco pares — ruído. O que separa as duas é o começo da escala:

| corte | barrados | pegos | escapam | certos perdidos |
|---:|---:|---:|---:|---:|
| 0,00 (sem porteiro) | 0 | 0 | 24 | 0 (0,0%) |
| 0,50 | 10 | 10 | 14 | **0 (0,0%)** |
| 0,90 | 21 | 17 | 7 | 4 (1,2%) |
| 0,95 | 28 | 21 | 3 | 7 (2,2%) |
| **0,98** | **30** | **22** | **2** | **8 (2,5%)** |
| 0,99 | 34 | 22 | 2 | 12 (3,7%) |
| 0,999 | 56 | 22 | 2 | 34 (10,6%) |

A 0,50 a régua do mínimo pega **10 dos 24 erros sem custar um tabuleiro certo** — são as
casas em que a rede jogou cara ou coroa, e a média as dilui entre as outras 63. A da
média, no mesmo ponto, não pega um erro sequer.

**O piso fica em 0,98, que é onde a curva vira.** Pega 22 dos 24 por 2,5% dos certos, e
daí para cima o preço sobe sem que mais nenhum erro seja pego: **um em treze vira um em
173**, e o custo é oito tabuleiros que saem recortados — exatamente o que o livro já
exportava antes desta fase.

**Os dois que escapam escapam de tudo.** Nenhuma das oito réguas os separa abaixo de
0,9995, e ali já vão 14% dos certos junto. São leituras erradas e confiantes, e nenhum
sinal que a `ler` produz hoje as distingue. Fica registrado como o teto desta régua.

#### Duas coisas que a tabela revelou de passagem

**A plausibilidade nunca dispara.** Separação 0,5000 é régua constante: os 346 tabuleiros
são plausíveis, porque o árbitro da F1.7 conserta a posição antes de alguém perguntar.
Ela ficou no porteiro mesmo assim, como veto seco e fora da conta do piso — barrar uma
posição impossível não pode custar um tabuleiro certo, e o caso que ela protege é o que o
corpus não tem: diagrama mal recortado, em que o árbitro não dá conta.

**A rede de ocupação calculava a confiança dela e jogava fora.** O `ocupadas` decidia no
`>= 0.5` e devolvia o booleano. Agora a probabilidade da decisão tomada — `p` onde disse
"tem peça", `1 - p` onde disse "vazia" — vive em `Casa.confianca_ocupacao`, nas 64 casas,
inclusive nas vazias. Sem ela o porteiro seria cego para o erro mais comum: a F8.4 mediu
a ocupação em 99,38% contra 99,62% da identidade, e uma peça inventada não abaixa
confiança de identidade nenhuma.

#### O que entrou

`medir_porteiro.py` (as oito réguas, a varredura e a tabela de operação),
`diagrama.confiavel` com o `PISO_DO_PORTEIRO` carregando a tabela acima no comentário,
`diagrama.confianca_de_ocupacao`, o campo novo na `Casa`, e
`tests/test_f58_porteiro.py`, 7 testes que não carregam modelo — as leituras são montadas
à mão, que é o que permite pôr uma casa exatamente no piso e outra logo abaixo.

O instrumento **não reimplementa a regra**: a última linha do relatório é a decisão do
próprio `diagrama.confiavel`, e ela bate com a linha 0,98 da tabela. É a trava da F52.

### Etapas 1 e 3 — o desenho chega ao EPUB e ao DOCX

**Um retângulo virou dois, e era o defeito latente da fase.** O `livro` guardava só a
borda **mais a margem** — o retângulo que não pode virar texto, sem o qual os rótulos
`a`–`h` entram como linhas de um caractere. Enquanto o único uso dele era recortar, dava
no mesmo; para ler o tabuleiro, não: o `_casas_do_recorte` divide o recorte em 8×8
**iguais**, e a F8.4 mediu que moldura de 2% desloca toda casa. Ler pela `exclusao`
devolveria 64 casas deslocadas e um FEN errado sem quebrar nada. Agora a `Diagrama` tem
os dois campos com nome, e trocá-los deixou de ser possível por descuido.

O resto da costura:

- `Figura` ganha `fen`, `origem` (`render`/`recorte`/`pagina`) e `aviso`, e a
  `PaginaExtraida` conta `diagramas_desenhados`. É o que permite o relatório do fim dizer
  **em que páginas** o livro preferiu o scan, e por quê;
- **falta de modelo ou de fonte não derruba a exportação**: cai para o recorte com o
  motivo escrito, uma vez por diagrama. Um livro de 264 páginas não pode morrer na
  página 3 porque o `.pth` do diagrama não foi treinado;
- `coordenadas` é falso por padrão **nos dois modos**, e o recorte de queda segue a
  opção: desenho e recorte convivem no mesmo livro, e um com rótulo e outro sem seria a
  única diferença visível entre a página em que o modelo se saiu bem e a outra;
- o `alt` da figura passa a ser o FEN nos dois formatos — no DOCX pelo `descr` do
  `docPr`, que o `python-docx` não expõe e que sai pela camada XML. Acessibilidade e
  busca no mesmo campo;
- a UI pergunta as duas coisas e lista as quedas no fim.

**O lado do desenho subiu para 528 px, e a medição diz que é de graça.** O EPUB escala
pela CSS; o DOCX fixa a figura em 9 cm, e ali o lado em pixels *é* a resolução impressa:

| lado | arquivo | dpi a 9 cm no DOCX |
|---:|---:|---:|
| 350 px | 6,8 KB | 99 ← o que o recorte a 150 dpi dava |
| **528 px** | **11,2 KB** | **149** |
| 700 px | 14,4 KB | 198 |

O recorte que isto substitui pesava ~85 KB a 700 px, e cerca de um quarto disso a 350.
**O desenho a 528 custa metade do recorte a 350** e imprime a 149 dpi onde ele dava 99 —
não há troca a fazer, e por isso o padrão não é o mínimo.

### A prova em página de livro

Três páginas do Chess Evolution 1, com os modelos de verdade: **11 diagramas, 11
desenhados, nenhuma queda**, em 2,6 s. Duas posições conferidas casa a casa contra o
impresso — Ex. 22-3 e Ex. 22-6 da página 220 — batem nas 64. As outras nove não foram
conferidas à mão: quem sustenta o número de acerto é a medição dos 346, não este passeio.

A suíte também deixou de ter dublê no caminho crítico: `test_do_pdf_ao_desenho_sem_nenhum_dublê`
imprime um diagrama com fonte, monta um PDF com ele, extrai e exige o mesmo FEN de volta.
É o teste que pega a troca dos dois retângulos, que nenhum outro pegaria.

### O que fica registrado

**O cabeçalho do exercício não escapa, e agora está medido.** A pergunta ficou em aberto
na etapa 3 e a F59 a respondeu de passagem, ao exportar a página 220 do Yusupov: ela sai
com os seis diagramas e **três** caixas de texto. A escala da página é 57 px, a margem de
exclusão é 80 px (1,4 escalas), e nela cabem 27 caixas por diagrama — **11 delas acima da
borda**, que são exatamente o `➤ Ex. 22-1 ◀ ★★ ▼`.

Antes da F58 isso não se via, porque o recorte saía com a margem junto e o cabeçalho ia
dentro da figura. Com o desenho — ou com o recorte justo — ele some do livro: não vira
texto, porque foi excluído; não vira figura, porque a figura agora é o tabuleiro. **É
perda de informação introduzida por esta fase**, e das piores, porque leva junto o ▼/△ de
quem joga, que é a única coisa na página que diz de quem é o lance.

Duas saídas, e a escolha é medição de outra fase: ler as caixas da faixa e emitir uma
legenda antes da figura (o `➤`, o `★` e o `▼` teriam de entrar no alfabeto do modelo), ou
recortar a faixa como imagem e pô-la acima do desenho.

## F59 — O modo de fonte embutida — CONCLUÍDA (com uma verificação em aberto)

O mesmo mapa da F58, entregue como **texto de verdade** em vez de PNG: opção, com o PNG
continuando padrão. A vantagem é tamanho; o risco é o leitor que força a fonte do usuário
e transforma o tabuleiro em `rmblkans`.

**O intermediário carrega os dois.** A `Figura` ganhou `linhas` e `fonte` **junto** do
PNG, e não no lugar dele: são 72 bytes por figura, e é o que permite escolher o modo na
hora de *escrever o arquivo* em vez de na hora de ler o PDF. A extração custa minutos; a
escrita, segundos — quem quer o mesmo livro nos dois modos não paga o OCR duas vezes.

Medido nas mesmas três páginas do Yusupov, 11 diagramas:

| | PNG | fonte |
|---|---:|---:|
| EPUB | 104,5 KB | **19,1 KB** |
| DOCX | 137,9 KB | **52,3 KB** |

O EPUB cai para 18%: cada diagrama deixa de custar ~7,8 KB e passa a custar ~200 bytes,
mais os 18 KB da fonte, uma vez. No DOCX a queda é menor porque a fonte embutida vai
ofuscada e sem subset.

### O EPUB, medido no navegador

A estrutura o teste prende; a **geometria** exige motor de layout, e foi medida com a
página aberta num deles:

| | |
|---|---|
| vão entre filas | **0,000 px** nas sete emendas |
| tabuleiro | quadrado dentro de 0,02 px |
| letras `a`–`h` | alinhadas às colunas dentro de 0,02 px, passo de 33,59 px = 1 casa |

**Duas coisas quebraram nessa medição, e nenhuma apareceria num teste de estrutura.**

A primeira: centrar cada linha por si desalinhava a fileira de letras em 1,3 px. As
linhas do tabuleiro são glifos e a das letras são caixas de 1 em; as larguras diferem por
um arredondamento, e centrar cada uma reparte a diferença pela metade. Encaixotar tudo
num bloco que encolhe até o conteúdo (`display: table`) e centrar **o bloco** resolve.

A segunda: o seletor `p.colunas span` pegava junto o `span` do rótulo da fila e o alargava
de 0,92 em para 1 em — 2,69 px, o tabuleiro andando para um lado e as letras para o outro.
Uma classe própria (`span.col`) fecha isso.

E o `<meta property="ibooks:specified-fonts">true</meta>`, sem o qual o Apple Books troca
a fonte embutida pela do leitor: o arquivo passaria em todos os outros leitores e falharia
só lá, que é o pior tipo de defeito de formato.

### O DOCX, e o que dele não dá para verificar aqui

São **quatro costuras**, e faltar qualquer uma dá um arquivo que abre sem a fonte, ou não
abre: a extensão `.odttf` no `[Content_Types].xml`, a parte `word/fonts/fonte1.odttf`, a
entrada no `word/fontTable.xml` com o relacionamento, e o `w:embedTrueTypeFonts` no
`settings.xml` — em ordem, porque a sequência de `CT_Settings` é fixa no esquema e fora
de lugar o Word acusa arquivo corrompido.

Saiu pela camada do zip, e não pela do `python-docx`: a biblioteca escreveria o tipo de
conteúdo como `Override` por nome de parte, e o Word escreve `Default` por extensão.
Trinta linhas reescrevendo o zip produzem exatamente o que ele produz.

A ofuscação é o XOR dos 32 primeiros bytes com os 16 do GUID **em ordem inversa**,
aplicados duas vezes (ECMA-376 §15.2.13). O teste desofusca a parte e compara com o
arquivo do disco, byte a byte.

**O que fica em aberto é o Word.** Não há como abri-lo daqui, e há uma dúvida concreta
sobre a qual só ele responde: a SkakNew-Diagram é **CFF** (`OTTO`), e o embutimento do
Word é orientado a TrueType. Se ele recusar, o remédio é converter o contorno com o
fontTools — e aí a LPPL exige renomear a família, porque arquivo modificado não pode
sair com o nome do original.

**Diagrama com coordenadas continua saindo em imagem no DOCX.** Alinhar rótulo de outra
fonte sobre as casas exigiria uma tabela de 81 células por diagrama; no EPUB são três
linhas de CSS, aqui não. A imagem já traz as coordenadas desenhadas, então nada se perde
além dos bytes.

Cobertura: `tests/test_f59_fonte_embutida.py`, 14 testes.

## F60 — O cabeçalho do diagrama volta, como faixa — CONCLUÍDA

A F59 mediu o estrago que a F58 tinha feito sem notar: a página 220 do Yusupov saía com
seis diagramas e **três** caixas de texto. A margem de exclusão de 80 px (1,4 escalas, com
a escala em 57) come 27 caixas por diagrama, **11 delas acima da borda** — que são o
`➤ Ex. 22-1 ◀ ★★ ▼`. Não viravam texto, porque a margem as excluía; e deixaram de virar
figura quando a figura passou a ser só o tabuleiro.

**A faixa é recortada da página e entra como figura logo acima do diagrama.** O retângulo
dela sai das caixas que a margem comeu e que estão acima da borda — não de uma altura
fixa —, então diagrama sem nada em cima não ganha faixa nenhuma, que é o caso do diagrama
no meio da prosa.

Duas decisões, e as duas são de alinhamento:

- **a largura é a da borda do tabuleiro, e a folga é só vertical.** As duas figuras são
  escaladas para a mesma largura no arquivo, e meia altura de caractere de cada lado já
  dava 16% a mais — medido: 619 px de faixa contra 534 de tabuleiro. Na horizontal a
  faixa só cresce se a tinta passar da borda, o que na página 220 acontece por 7% (o `➤`
  e o `▼` moram fora dela);
- **a faixa sai na escala do tabuleiro, e não na do scan.** No EPUB a imagem aparece no
  tamanho natural: recortada a 150 dpi, ela sairia com pouco mais da metade da largura de
  um tabuleiro desenhado a 528 px, e o cabeçalho ficaria menor que o diagrama que
  encabeça.

Há um caso em que a faixa **não** entra: recorte com coordenadas, em que a figura já sai
pelo retângulo de exclusão e traz o cabeçalho dentro — seria a mesma tinta duas vezes.

Medido nas três páginas: 11 faixas para 11 diagramas, entre 1,1 e 1,8 KB cada. O `▼` de
quem joga voltou ao livro.

**Fica registrado o que isto não resolve.** A faixa é imagem, então o cabeçalho não é
pesquisável nem lido por leitor de tela — o `alt` dela diz só "Cabeçalho do diagrama". E
a margem continua sendo instrumento cego: prosa impressa a menos de 1,4 alturas de
caractere acima de um diagrama também vira faixa, em vez de parágrafo. Nestes livros isso
é o cabeçalho; noutro, pode ser uma linha de texto.

Cobertura: 6 testes novos em `tests/test_f26_livro.py`.

## F61 — O livro de duas colunas deixa de sair misturado — CONCLUÍDA

A queixa: "os textos da coluna da esquerda se misturam com os da direita em muitos
trechos". Ela é justa, e o "em muitos trechos" é literal — a régua da calha acerta em
algumas páginas do mesmo livro e erra nas outras.

A ordem de leitura respeita colunas desde a F1.6. O que nunca foi medido é a **régua**:
`calha >= 3 × largura mediana de caractere`. Medido agora em 33 páginas de 6 livros, com
a segmentação de produção, o maior vão da projeção em x, em larguras medianas:

| | calha medida | a régua de antes (3,0) |
|---|---|---|
| Nunn, *Secrets of Rook Endings* | 1,00 – 1,18 (17–20 px) | nunca acha |
| Kasparov, *Dynamic Benko* | 2,58 – 3,31 (49–58 px) | acha em 4 de 9 páginas |
| Yusupov, *Complete* | 2,59 – 2,94 (44–46 px) | quase nunca acha |
| ~~Aagaard, *Attacking Manual* (1 coluna)~~ | ~~0,06 – 0,12 (1–2 px)~~ | ~~correto~~ |

> **A linha do Aagaard está errada, e a F70 a corrigiu.** O *Attacking Manual* **é de duas
> colunas** — conferido na página 128, prosa justificada em duas colunas com diagrama. O
> que se mediu como "vão que não é calha" era a calha do livro **apagada pelo cabeçalho
> corrente**, e o livro saía embaralhado em 27 das 30 páginas amostradas. Ele entrou aqui
> como controle de coluna única e não era um: as duas colunas desta tabela que o citam não
> sustentam nada. O controle de coluna única de verdade é o Darcy Lima. Ver a F70.

A régua cai para **0,8**: 1,25× abaixo da menor calha medida e 6,7× acima do maior vão
que não é calha. O espaço entre palavras não chega perto porque a projeção é da **página
inteira** — para sobreviver a ela, toda linha teria de ter espaço no mesmo x.

### O que a medição obrigou a acrescentar: a coluna estreita demais para ser coluna

Baixar a régua sozinha piora o sumário. O vão entre o título e o número da página é largo
em qualquer régua, e com a de antes o `Practical Chess Defence` já saía partido: dez
títulos juntos e dez números juntos, em vez de dez linhas. Medido, a "coluna" de número de
capítulo tem 2% da largura do texto e a de número de página 4%, contra 48% de cada coluna
de verdade no Kasparov e 45% da mais estreita no Chess Evolution 1. `COLUNA_MINIMA = 0,10`
fica no vão, e a faixa que não passa **se funde** à vizinha — nenhum box se perde.

O mesmo piso limpa um defeito antigo que ninguém tinha visto: no Chess Evolution 1 e no
Darcy Lima, respingo de scan na margem abria uma "coluna" de 1–3% da página, e a leitura
saía com esses boxes no fim.

### Achar a calha não bastava: havia mais três lugares sem coluna

**A linha atravessava a calha.** `quebrar_em_linhas` cortava onde a sequência desce ou
volta para a esquerda. Ao passar da última linha da esquerda para a primeira da direita
ela faz nem uma coisa nem outra — **sobe** —, e as duas linhas saíam coladas numa só.
Medido na página 118 do Nunn, `...followed by ♔f7.` saía preso a `ROOK ENDINGS`, que é o
cabeçalho da coluna vizinha. A régua de subir é contra o **topo da linha**, e não contra a
caixa anterior: contra a anterior ela corta dentro da linha, porque a vírgula mora na base
e a letra seguinte começa acima do topo dela (`Gurgenidze,` / `1981` viravam duas linhas).
Pilha girada fica de fora — a 90° o texto se lê de baixo para cima.

**A margem do recuo não era de coluna nenhuma.** `_agrupar_em_paragrafos` tirava a margem
da mediana das esquerdas da página. Numa página de duas colunas metade das linhas começa
em 122 e metade em 893: com essa mediana, ou a coluna da direita inteira parece recuada —
cada linha vira um parágrafo — ou a da esquerda perde todos os recuos. Medido na página 13
do Kasparov, **54 parágrafos em 56 linhas**. Agora a margem é por coluna e da página
inteira, e não do trecho entre dois diagramas, que tinha cinco linhas para tirar mediana.

**O fim da coluna não abria parágrafo.** Nem o recuo nem o salto vertical o veem: ali o
salto é *negativo*, porque a leitura volta ao topo da página. A troca de coluna virou a
terceira regra de corte.

**A figura entrava pela altura na página.** O diagrama do alto da coluna da direita está
acima de quase toda a coluna da esquerda, e era emitido antes dela. Agora cada figura
entra na coluna a que pertence, e o que sobra de uma coluna é despejado antes de a
próxima começar.

### O resultado

`medir_colunas.py` reproduz a tabela. Saltos entre colunas na ordem de leitura — numa
página de duas colunas lida direito, é **1** por página:

| | páginas | saltos antes | saltos hoje |
|---|---:|---:|---:|
| 10 páginas rotuladas (7 de 2 colunas) | 10 | **95** | **7** |
| Nunn, amostra de 8 páginas | 8 | 79 | 6 |
| Yusupov *Chess Evolution 1*, 7 páginas | 7 | 103 | 4 |
| Aagaard *Attacking Manual* (~~1 coluna~~ — **2**, ver F70), 7 | 7 | 8 | 1 |
| Darcy Lima (1 coluna), 9 páginas | 9 | 8 | 1 |

O livro de coluna única não se mexe: das 16 páginas dos dois livros tidos por de uma
coluna, uma única passa a ser lida em duas — a de *preview* de diagramas do Aagaard, que é
uma grade 3×3 de legendas, e mesmo ali os saltos caem de 8 para 1.

**A leitura deste parágrafo mudou com a F70**, e vale registrar o erro: o Aagaard é de
duas colunas, então as suas 7 páginas não eram um controle passando — eram sete páginas
saindo embaralhadas, e a fase não percebeu porque contava as colunas certas nos livros
errados. O único controle de coluna única aqui é o Darcy Lima.

O relatório do fim da exportação passa a dizer quantas páginas saíram com mais de uma
coluna. Sem esse número não havia como conferir a queixa sem abrir o arquivo.

### Corrigido de passagem: o peão entra no alfabeto de figurinas

O retreino de 2026-08-17 (216 → 230 classes) trouxe `♙`, e `test_f14_dataset` reprovou —
que é exatamente o serviço dele: `searchable_pdf.PECAS` tinha 5 peças, e o modo "replace"
passaria a pular calado todo box que o modelo lesse como peão.

**A razão de excluí-lo estava certa sobre lance e errada sobre a página.** Peão não ganha
letra em notação algébrica — `e4`, nunca com figurina —, e daí concluía-se que U+2659 era
inalcançável. Mas a figurina aparece onde o texto **nomeia material**. Impresso na página
118 do Nunn, na prosa:

> There are 11 positions of reciprocal zugzwang with ♖+♙b7 v ♖.

O modelo aprendeu a classe sozinho: `sym_9817`, 36 amostras, todas peão branco limpo,
contra 14–21 mil de cada uma das outras cinco. `PECAS` e o `PECAS_RAPIDAS` da barra de
botões passam a seis. A metade "preta" continua fora, pela regra que não mudou: estes
livros usam **um** conjunto de figurinas para os dois lados.

### O que fica em aberto

**Coluna e tabela continuam sendo a mesma coisa para o programa.** O piso de largura
resolve o sumário porque as faixas dele são estreitas; um glossário de duas casas largas
— símbolo à esquerda, descrição à direita — passaria, e sairia com os símbolos todos
juntos. O que separa os dois é o alinhamento das linhas através da calha, e isso não foi
medido.

Cobertura: `tests/test_f61_duas_colunas.py`, 17 testes, mais os de `test_f14_dataset.py` e
`test_nags.py` que travavam o cinco.

## F62 — A fonte que desenha os símbolos vai junto — CONCLUÍDA

O texto exportado tem `♔♕♖♗♘♙`, `▼`, `△`, `★` e os sinais de avaliação, e até aqui
**nenhuma fonte viajava com o arquivo para desenhá-los**. O EPUB e o DOCX contavam com o
leitor, e o leitor não tem.

Medido no alfabeto do modelo — 230 classes, 40 delas fora do ASCII:

| fonte | cobre | o que falta |
|---|---:|---|
| **NotoSansSymbols2** (OFL, já no repositório) | 14/40 | `✝ ⩱ ⩲` e o que é texto comum |
| SkakNew-Figurine, ISChess | **0/40** | mapeiam glifo em posição ASCII, não Unicode |
| Times New Roman | 24/40 | **as seis figurinas**, `★ △ ⮜ ⮞ 🗸` |
| DejaVu Serif | 27/40 | as figurinas, `★ ✝ ⩱ ⩲ ⮜ ⮞ 🗸` |
| Segoe UI Symbol | 38/40 | é da Microsoft: não se redistribui |

**Times mais Noto cobrem tudo menos `⇄ ∓ ✝ ⩱ ⩲`**, e as 11 que só a Noto desenha são as
que importam: `△ ★ ♔ ♕ ♖ ♗ ♘ ♙ ⮜ ⮞ 🗸`. A escolha da fonte não é nova — é a
`FONTES_DE_SIMBOLO` da §4.2 da SPEC, a mesma do PDF pesquisável, e pelo mesmo motivo.

**As fontes de xadrez do repositório não servem para isto, e a medição foi rápida**:
`SkakNew-Figurine` e `ISChess` cobrem **zero** dos 40. Elas desenham peça na posição de
letra — é o defeito que este projeto inteiro existe para desfazer.

Três decisões:

- **entra sozinha, e só quando faz falta.** A fonte tem 641 KB; o texto é varrido antes, e
  livro que não traga símbolo nenhum não a carrega. Não é opção de menu: sem ela o livro
  sai com quadradinhos onde deveria ter peça;
- **o corte entre "letra" e "símbolo" é U+2000, e foi medido no alfabeto.** Abaixo dele
  estão `©`, `±`, `²`, `½` e as acentuadas, que qualquer fonte de texto desenha e que
  ficariam de outro peso numa fonte de símbolos;
- **no EPUB é `<span class="sim">`, no DOCX é um run com outra família.** Lá haveria
  `unicode-range`; aqui a fonte é atributo do run, e o parágrafo tem de ser partido onde a
  família muda. Nos dois casos os símbolos seguidos vão juntos, e não um a um.

### Um defeito da F59 que só apareceu aqui

O `<Default Extension="odttf">` estava sendo inserido **depois da declaração XML**, e não
dentro do `<Types>` — um segundo elemento na raiz, e o `[Content_Types].xml` deixava de
ser XML. Os testes da F59 conferiam por substring e passaram todos; o Word abriu o arquivo
assim mesmo. Quem acusou foi o `python-docx`, ao ser usado para reabrir o DOCX num teste
novo.

A lição virou teste: `test_o_docx_com_fonte_embutida_continua_sendo_um_docx` **abre** o
arquivo em vez de procurar pedaço dentro dele.

### O recorte da fonte, e por que ele não virou dependência

Embutir a fonte inteira custou caro: o EPUB de três páginas foi de 19 KB para **327**. A
`NotoSansSymbols2` tem 641 KB e ~2.600 codepoints, e este livro usa **15** — levar o bloco
de dominós e o de I Ching para desenhar seis figurinas.

O `gerar_fonte_de_simbolos.py` recorta: **5,2 KB, os mesmos 15 símbolos, 0,8% do
original.** Nos arquivos de verdade, as mesmas três páginas:

| | antes da F62 | fonte inteira | recorte |
|---|---:|---:|---:|
| EPUB, modo fonte | 19,1 KB | 327,5 KB | **40,2 KB** |
| DOCX, modo fonte | 52,3 KB | 361,0 KB | **73,8 KB** |

Três decisões em volta dele:

- **o `fontTools` não entra em produção.** O `requirements.txt` deste projeto é
  declaradamente só do que o aplicativo importa, e quem exporta um livro consome o
  recorte versionado — não o produz. Ele é dependência de desenvolvimento, como o pytest;
  a suíte mede cobertura com o PyMuPDF, que já estava lá;
- **a escolha é por cobertura, e não por ordem.** O recorte é produto de script rodado à
  mão, e alfabeto de modelo cresce. Se um dia ele não cobrir o que o texto pede, o
  `exportar` cai sozinho para a fonte inteira — o livro sai maior, e não sai errado. O
  `test_o_recorte_cobre_o_que_a_fonte_inteira_cobre` lê o `model_meta.json` e avisa antes;
- **a família foi renomeada.** Subset é modificação, e a OFL pede que a modificada não se
  passe pela original. Há um motivo prático junto: uma Noto instalada na máquina de quem
  abre o arquivo brigaria com esta, que tem quinze glifos.

### Duas coisas erradas desde a F2.6, corrigidas de passagem

**O EPUB saía declarado em português.** `<dc:language>pt</dc:language>` fixo, e estes
livros são em inglês — a mesma distinção que a §5.8 faz para o léxico ("o idioma dos
livros, não o do programa"). Idioma errado é hifenização pelas regras erradas e leitor de
tela lendo notação inglesa com fonemas portugueses. Agora é parâmetro, com `"en"` de
padrão.

**O `Paragrafo.titulo` era letra morta.** O campo existe desde a F2.6 e os dois
exportadores o ignoravam: todo cabeçalho saía como parágrafo comum, e sem `<h2>` (ou
`Heading 2`, no DOCX) o leitor não tem por onde navegar. Nada o marca ainda — detectar
título na página é fase de quem for medi-lo —, mas quem marcar encontra os dois formatos
prontos.

Cobertura: 8 testes novos em `tests/test_f59_fonte_embutida.py`, que agora tem 22, mais
`tests/test_f62_simbolos.py`, com 8.

> **A numeração pulou o 61 de propósito.** A régua da calha (`CALHA_EM_CARACTERES`,
> `COLUNA_MINIMA`) foi remedida em paralelo a esta fase e já se chamava F61 nos
> comentários do `box_service`. Duas fases com o mesmo número são duas fases que ninguém
> acha depois. A F61 está escrita acima, entre a F60 e esta.

## F63 — O apóstrofo deixava a prosa em pedaços — CONCLUÍDA

Conferindo o Kasparov exportado inteiro (322 páginas), a prosa saía picada:

    following fresh        ← três parágrafos, uma frase
    , high-
    quality encounter

Não é coluna, não é OCR: é a **quebra de linha**. `quebrar_em_linhas` cortava onde a caixa
nova descia em relação à **caixa anterior sozinha**, e o apóstrofo é uma caixa curta
plantada no alto — o fundo dele fica acima da altura de x, então qualquer letra depois
dele tem o centro abaixo disso e parece ter descido uma linha. O hífen faz o mesmo.

**A régua passa a ser a linha, e não a caixa anterior** — é a mesma correção que a F61 já
tinha feito no `subiu`, que na época foi só metade do serviço. A base de uma linha é o
maior fundo do que já entrou nela.

Duas coisas precisaram entrar junto, e cada uma tem um caso que a obriga:

**Caixa curta não fixa a base** (`CAIXA_CURTA = 0,65`). Sem isso, uma linha que *começa*
com aspas teria a régua cravada no fundo das aspas e o defeito voltaria pela porta dos
fundos. Medido nas 10 páginas rotuladas, com a altura normalizada pela mediana da própria
página (p05 – p95):

| | altura relativa | casos |
|---|---|---:|
| hífen e travessão | 0,11 – 0,38 | 76 |
| ponto e vírgula | 0,15 – 0,54 | 925 |
| apóstrofo e aspa simples | 0,31 – 0,58 | 50 |
| minúscula sem ascendente | 0,68 – 1,00 | 8.147 |
| minúscula com ascendente | 0,85 – 1,67 | 3.798 |
| maiúscula | 1,00 – 1,67 | 838 |

O vão é de 0,58 a 0,68. O limiar fica **em 0,65 e não no meio** porque os dois erros não
custam o mesmo: letra tomada por curta só deixa de atualizar a base, que as outras letras
da linha dão igual; apóstrofo tomado por letra crava a base na altura de x e devolve o
defeito.

**Descer é passar da base com folga** (`FOLGA_DE_LINHA = 0,25`). A vírgula desce um fio
abaixo da linha de base, então o centro dela fica **meio pixel** abaixo do fundo das
letras — e sem folga isso conta como linha nova. Medido, os 26 cortes que sobravam depois
da régua da linha se separam em dois montes, e entre eles não há nada:

| | excesso, em alturas medianas | casos |
|---|---|---:|
| vírgula raspando a base | 0,02 | 11 |
| quebra de linha de verdade | 0,66 – 4,88 | 15 |

O limiar fica no vão: 12× acima do maior raspão e 2,6× abaixo da menor quebra de verdade.
Varrido, o platô é largo — de 0,10 a 0,60 o resultado não muda; a 0,90 começa a comer
quebra de verdade.

### O resultado

`medir_quebra_de_linha.py` reproduz a tabela. Duas medidas, e elas puxam para lados
opostos: **corte no meio** é o defeito (corte que nem `voltou` nem `subiu` explicam) e tem
de cair; **linha alta** é o risco do conserto (régua frouxa fundindo duas linhas numa) e
não pode subir.

| | linhas | cortes no meio | linhas altas |
|---|---:|---:|---:|
| antes (a régua da F61) | 532 | **69** (13%) | 71 |
| hoje | 476 | **15** (3%) | **68** |

As linhas altas **caem**, então o conserto não pagou com o outro defeito. Os 15 cortes que
sobram são todos legítimos e nenhum é de pontuação: apóstrofo abrindo a linha seguinte
(0,66 – 1,07) e número de página ou cabeçalho `Game N` centrado (1,44 – 4,88) — nenhum
deles volta para a esquerda, então é esta régua que os corta, e corretamente.

Na página 13 do Kasparov, com o rótulo à mão como entrada:

    antes   'As an illustration on the theme of ' / 'typical' / 'black plans…'
            'following fresh' / ', high-' / 'quality encounter'
    hoje    'As an illustration on the theme of 'typical'
            'following fresh, high-quality encounter'

**A acurácia da cadeia não se move, e era de esperar.** Medido em 10.510 caracteres das 10
páginas rotuladas, o caminho híbrido dá 97,48% antes e depois: o k-NN responde 98,5% dos
boxes e a leitura por linha trocou 3. O que a F63 conserta é a **montagem** — o texto que
sai —, não o reconhecimento de caractere. Quem se beneficia do caractere é a linha do
EasyOCR, e ela mal entra no caminho de produção.

### O que ficou em aberto — e virou a F64

**A ordem dentro da linha ainda punha o apóstrofo antes da palavra.** `White's` saía
`' White s`. A F63 arrumou onde a **linha** se corta; faltava onde a **banda** se forma.

Cobertura: `tests/test_f63_quebra_de_linha.py`, 11 testes. Os dois casos que justificam as
constantes têm teste que **falha de propósito** com a constante desligada — sem isso o
teste passaria por acaso e ninguém saberia.

## F64 — O apóstrofo deixa de abrir banda sozinho — CONCLUÍDA

O mesmo glifo, um degrau antes. `BoxService._linhas` agrupa em bandas por sobreposição
vertical, ordenando por `y1`, e o apóstrofo mora na altura de **ascendente**: ele chega
antes da letra que segue e abre a banda sozinho. Com o fundo da banda cravado na altura de
x, nenhuma letra da linha consegue entrar — e a banda da aspa sai antes, porque as bandas
saem de cima para baixo.

Medido na página 13 do Kasparov, com o `.box` à mão: o apóstrofo de `White's` ocupa
409–418 e as letras da linha, 421–440. A aspa não encosta em nenhuma delas.

**O fundo médio passa a sair só das caixas altas.** Enquanto a banda só tiver caixa curta
ela não tem fundo, e a próxima caixa entra sem discussão — que é o certo: uma aspa não
estabelece linha de base, e a letra depois dela é da linha dela. A régua é a mesma
`CAIXA_CURTA` da F63, importada de lá e não recopiada; um teste falha se as duas se
separarem.

| | bandas | feitas só de caixa curta |
|---|---:|---:|
| antes | 346 | **7** (todas aspas ou apóstrofo) |
| hoje | 339 | **0** |

As bandas caem exatamente sete — as órfãs, e nada além delas. Na página 13, as linhas
como o instrumento as devolve:

    antes   '
            Whitesqueensideisruined.
    hoje    White'squeensideisruined.

No EPUB isso aparecia pior do que aqui, porque a linha de um caractere vira parágrafo e o
parágrafo junta com espaço: `' White s queenside is ruined.`

**E a F63 melhora de carona**, porque a banda é o que alimenta a ordem de leitura.
Remedido com o `_linhas` de hoje: cortes no meio de linha **12 em 466**, contra 15 em 476
na tabela da F63 e 79 em 535 com a régua da F61. As linhas altas ficam em 68 nas duas.

Cobertura: `tests/test_f64_banda_da_linha.py`, 8 testes, e `medir_quebra_de_linha.py
--bandas` reproduz a tabela.

## F65 — O apóstrofo deixa de virar troca de coluna — CONCLUÍDA

O terceiro e último lugar em que o mesmo glifo partia a palavra. Conferindo o Kasparov
reexportado com a F63 e a F64, sobrou `we can` / `'t say that`.

A F61 corta a linha onde a sequência **sobe**, porque é assim que se sai da coluna da
esquerda para a da direita. Só que o apóstrofo mora na altura de **ascendente**: chegando
depois de `can`, que é todo altura de x, ele fica inteiro acima do topo da linha — e a
régua o lia como coluna vizinha.

**A `FOLGA_DE_LINHA` da F63 não servia aqui, e o motivo é físico.** O vão entre a altura
de ascendente e a de x chega a ~0,4 altura mediana em fonte comum, mais que os 0,25 que
bastam para a vírgula. Medido nas 10 páginas rotuladas, o `subiu` dispara 10 vezes e os
dois montes não se tocam nem de longe:

| | subida, em alturas medianas | casos |
|---|---|---:|
| apóstrofo subindo dentro da linha | 0,08 – 0,14 | 3 |
| troca de coluna | 66,22 – 104,23 | 7 |

O vão é de **470×**. `FOLGA_DE_COLUNA = 1,0` fica dentro dele com 7× de margem acima do
maior apóstrofo e 66× abaixo da menor troca de coluna. Varrido, o platô vai de 0,25 a 60;
a 80 começa a comer troca de coluna de verdade (as linhas altas sobem de 68 para 70).

**É folga, e não "a caixa tem de ser alta", de propósito.** Uma coluna que *começa* com
aspas sobe centenas de alturas e continua sendo cortada — a régua alternativa a perderia.

### O resultado, com as três fases juntas

`medir_quebra_de_linha.py` reproduz a tabela. A régua do "corte no meio" passou a medir a
troca de coluna **com** a folga desta fase: sem isso, o corte que a F65 conserta era
contado como legítimo e a tabela não via o defeito.

| | linhas | cortes no meio | linhas altas |
|---|---:|---:|---:|
| antes (a régua da F61) | 535 | **84** (16%) | 71 |
| hoje (F63 + F64 + F65) | 463 | **12** (3%) | **68** |

Na página 13 do Kasparov, as três palavras que abriram cada fase:

    antes   following fresh / , high- / quality encounter
            ' / Whitesqueensideisruined.
            we can / 't say that
    hoje    following fresh, high-quality encounter
            White's queenside is ruined.
            can't say that his pawn structure is com-

Cobertura: `tests/test_f65_folga_de_coluna.py`, 6 testes.

## F66 — O erro de OCR dos "títulos em negrito" — MEDIDO, e o reparo não paga

A queixa era `The Dmamic Bxf6o Gambit` e `Andxein,Dity` nos títulos. **A medição
desmentiu as duas metades dela: não é dos títulos, e não é do modelo.**

### Não é do modelo

Com o **box certo** — o recorte do `.box` à mão —, a página 13 sai quase perfeita, e o
cabeçalho e os nomes dos jogadores saem **inteiros**. Das 46 linhas, 4 têm erro, e cada
uma erra 1 caractere. O que estraga o livro é **colagem**: dois glifos que se encostam
viram um box, e o box vira um caractere.

| população | rotulados | com o box certo | no caminho de produção |
|---|---:|---:|---:|
| corpo (< 1,15 altura mediana) | 7.883 | 98,20% | 96,8% |
| meio (1,15 – 1,45) | 2.189 | 97,99% | 95,9% |
| grande (≥ 1,45) | 541 | 95,75% | 91,3% |

### Não é dos títulos

O cabeçalho `The Dynamic Benko Gambit` tem altura relativa **0,96** — é *itálico*, não
grande. E a colagem bate na prosa comum igual: `moving` → `moTng`, `pawn down` →
`pamdowI1`, `manoeuvres` → `manoeumes`, `the pawns` → `tliepams`. O padrão é sempre dois
traços verticais que se encostam virando `m`, `T` ou `E`.

### Por que não há conserto barato

São **96 boxes com 2+ caracteres dentro** nas 10 páginas rotuladas, em **74 pares
distintos** — cauda plana, o par mais frequente aparece 6 vezes. Acrescentar classes de
ligadura não alcança: **39 dos 96 já saem certos**, e são justamente os pares que o
modelo já tem como classe (`am`, `c4`, `ry`, `♗x`). E o separador de colados está no ótimo
que a F1.5b mediu — as colagens escapam por três estágios diferentes, ~20% em cada.

### O que parecia a saída, e o número que a fecha

O dicionário **já sabe**: das 11 palavras estragadas catalogadas, 10 não existem no
léxico, e as 11 certas existem todas. Daí o reparo desta fase: mascarar o que veio de um
box largo demais para um glifo, ancorar no resto, e trocar **só quando o dicionário tem
uma palavra só naquele molde** (`lexico.reparar`, com `medir_reparo.py` medindo).

| juiz | consertadas | estragadas | intocadas |
|---|---:|---:|---:|
| léxico geral (310.465 palavras) | 2 | 2 | 80 |
| vocabulário do próprio livro (2.829) | **5** | **3** | 69 |

**A primeira linha morre no juiz.** O léxico geral contém `Iftime` e `titli` — a cauda do
ABBYY —, e uma máscara de três âncoras acha lixo. Trocar o juiz pelo vocabulário do
próprio livro (palavra lida 2+ vezes **e** conhecida pelo léxico) resolve isso: ali
`dynamic` aparece 30 vezes, `benko` 62, `pawns` 82, e `iftime` e `titli` não aparecem.

**Os 8 casos foram conferidos no impresso, um a um, e a contagem automática estava
errada** — ela dizia 3 certas e 5 erradas porque três rótulos daquelas páginas estão
incompletos (`eample`, `tonamt`, `Dmic`). No impresso são 5 certas (`manoeuvres`,
`example`, `tournament`, `years`, `compensation`) e 3 erradas.

**As 3 erradas são a mesma palavra**, e o mecanismo está identificado: `Dynamic` do
cabeçalho vira `Drazic`, que é um jogador deste livro. A regra de Occam que eu pus — "do
menos escondido para o mais, e para no primeiro que der" — prefere `drazic`, que casa sem
esconder caractere nenhum, a `dynamic`, que precisa esconder um.

### Por que não foi adiante

62,5% de precisão é inaceitável para algo que **reescreve o texto em silêncio**: o erro de
hoje pelo menos aparece como gibberish e o revisor o vê. E a correção óbvia do mecanismo —
exigir ao menos um caractere escondido por trecho mascarado — quebra no trecho mascarado
**falso**, que a 1,5 são 7,6% dos boxes bons. São 8 eventos em 10 páginas: ajustar régua
contra 8 eventos é o erro que a F47 registrou nesta casa.

**O código fica, e `livro` não o chama.** É o instrumento que reproduz a tabela, e a
próxima fase que atacar isto começa dele em vez de reescrevê-lo — a mesma solução da F36.
O livro exportado não muda nem corre risco.

### O que a medição diz que falta

**Prova visual do trecho mascarado** — **virou a F69, e foi feita.** O que separa
`dynamic` de `drazic` não é o dicionário nem a largura: é o que está desenhado ali. O
árbitro da F1.5b já sabe pontuar um recorte contra um caractere; apontá-lo para as letras
candidatas é a evidência que falta, e é uma fase inteira.

**O vocabulário do próprio livro é um bom juiz e ainda não existe como peça.** Ele exige
duas passadas — ler o livro para saber o que ele fala, depois reparar — e vale por si:
`medir_lexico.py` mede o alarme falso do léxico geral, e 2.829 palavras contra 310.465
mudariam esse número. **Continua em aberto depois da F69**: a prova visual ataca o outro
lado do mesmo erro e não dispensa este.

## F67 — O `⩱`, o `⩲` e a faixa que ninguém podia pesquisar — CONCLUÍDA

Duas pontas soltas da F62, e as duas eram a mesma pergunta: **o que o livro imprime tem
de chegar ao arquivo como aquilo que é**.

### Os cinco símbolos que não existiam em fonte redistribuível

Varridos os **578 arquivos de fonte** de `C:\Windows\Fonts` e da pasta do usuário, o `⩱`
e o `⩲` — a ligeira vantagem de cada lado, o símbolo mais comum destes livros depois das
figurinas — aparecem em quatro famílias: Segoe UI Symbol e Cambria (Microsoft), CBArialLink
(ChessBase) e AqChessUnicode. Nenhuma pode viajar dentro de um EPUB.

**A saída estava no repositório.** A `SkakNew-Figurine` é LPPL, desenha os cinco, e o que
falta a ela é só o `cmap`: como toda fonte de xadrez antiga, ela põe símbolo em posição de
letra. O `gerar_fonte_de_simbolos.py` agora copia o glifo e o **remapeia para o codepoint
certo** — o contrário exato do que este projeto desfaz nos PDFs de entrada, onde a letra
mente sobre o desenho.

O contorno muda de forma no caminho (CFF cúbico → TrueType quadrático, pelo `Cu2QuPen`), e
o giro do contorno tem de ser invertido junto: as duas convenções giram em sentidos
opostos, e um glifo com o giro trocado sai **vazado**, sem erro nenhum no caminho.

**O casamento glifo↔símbolo foi decidido contra os recortes de treino, e não contra outra
fonte** — e é o miolo desta fase. A primeira tentativa casou `⩲` com o `e` e `∓` com o
`h`, olhando a folha de contato da fonte; as duas estavam erradas. O gabarito existe:
`training_data/sym_*` guarda os recortes de cada classe, tirados das páginas. Postos lado
a lado, os quatro da família do `±` se separam pela **contagem de barras**:

| símbolo | o que o livro imprime | glifo |
|---|---|---|
| `±` (sym_177) | mais, uma barra embaixo | `c` |
| `⩲` (sym_10866) | mais, **duas** barras embaixo | `f` |
| `∓` (sym_8723) | uma barra em cima, mais | `e` |
| `⩱` (sym_10865) | **duas** barras em cima, mais | `g` |

A mesma comparação pegou o `⇄`: a SkakNew desenha a seta de cima para a **esquerda**, e
tanto o livro quanto o nome do codepoint (U+21C4) querem a de cima para a direita — é o
glifo do U+21C6, que é outro símbolo. Entra espelhado.

O recorte foi de 5,2 KB para **6,3 KB** e passou de 15 para **21 símbolos**. Continua em
1,0% da fonte original.

### A faixa vira texto quando dá para lê-la

A F60 trouxe o cabeçalho de volta como imagem, e imagem não se pesquisa: quem procura
"Ex. 22-1" no arquivo exportado não acha a página do exercício. Agora ela é lida pelo
mesmo classificador do resto da página e sai como **título** — `<h2>` no EPUB, `Heading 2`
no DOCX, que é por onde o sumário do leitor navega, e o campo que a F62 tinha acabado de
tirar de letra morta.

**Uma letra fraca já manda a faixa de volta para a imagem**, e é mais severo que o resto
do livro de propósito: na prosa, um caractere derrubado deixa um buraco que o leitor
remonta; aqui a faixa tem cinco caracteres, e o buraco é o número do exercício.

Medido em três páginas do Yusupov, 11 cabeçalhos:

    página 10     2 em texto     "Diagram 1-3 △"  "Diagram 1-4 △"
    página 11     3 em texto     "Diagram 1-6 △"  "Diagram 1-7 △"  ("Diagrram 1-5 ▼")
    página 220    1 em texto     "⮞Ex. 22-2⮜ ★★ ▼"   e 5 em imagem

**E o que barra os cinco é o hífen**, não os símbolos exóticos. Medido caractere a
caractere na página 220: `⮞` 1,000 · `Ex` 1,000 · `2` 1,000 · **hífen 0,108** (lido `♕`) ·
`⮜` 1,000 · `★` 1,000 · `▼` 0,997. O modelo lê o `➤` e o `★` com folga e tropeça no
traço de `22-4` — que é assunto da família de traços do alfabeto, não desta fase.

**De quebra, o `▼`/`△` de quem joga entrou no texto.** Ele viaja no fim do cabeçalho, e
com isso deixa de ser a informação que a F58 registrou como perdida.

### O defeito que a leitura revelou

Com a faixa em texto, a página 10 saiu com `"agram -"`: o cabeçalho partido ao meio. A
faixa recolhia caixa por **continência** no retângulo de exclusão, e a margem começa em
y=896 enquanto o `D` de `Diagram` vai de 887 a 916 — **a maiúscula sobe acima da margem, a
minúscula não**. O `Di` ia para o texto da página e o resto para a faixa.

A régua passou a ser o **pé** da caixa, e não o topo: `topo da margem ≤ y2 ≤ topo do
tabuleiro`, com sobreposição horizontal em vez de continência. Linha de prosa mais acima
não entra, porque o pé dela fica antes do topo da margem. A imagem da F60 tinha o mesmo
defeito e ninguém via — ela mostrava o cabeçalho cortado.

Cobertura: `tests/test_f26_livro.py` sobe para 36 testes.

> **Esta fase nasceu numerada F63.** Ela foi escrita em paralelo com a F63–F66, e os
> comentários da faixa no `livro.py` diziam F63 enquanto a quebra de linha já tinha
> tomado esse número. Renumerada para F67 **antes de entrar** — duas fases com o mesmo
> número são duas fases que ninguém acha depois, que é o mesmo motivo da nota sob a F62.
> A numeração não ficou com buraco: F60 a F68 estão ocupadas, cada uma com um dono só.

## F68 — O `✝` era o `+` do xeque — CONCLUÍDA

Estes livros desenham o xeque na fonte de xadrez, com uma cruz mais cheia que o sinal de
mais do texto, e a base de treino separou as duas formas em **classes diferentes**. Para o
olho do modelo isso é certo — são desenhos distintos, e juntá-los pioraria o
reconhecimento dos dois. Para tudo o que vem depois, é errado.

Medido na página 11 do Yusupov, **16 ocorrências numa página só**: `♘e4✝`, `♕c5✝`,
`dxc4✝`, `♗g2✝`, `♖h3✝`, `♗xd4✝`. Em quatro páginas, 44 — o segundo caractere não-ASCII
mais frequente do texto, atrás só da dama.

O estrago é de três tipos, e nenhum deles aparece na tela:

- o livro exportado **não responde a uma busca por `Nxe4+`**, que é o que a pessoa digita;
- o `notacao.SUFIXOS` não conhece o `✝`, então ele ficava colado ao lance e o
  `parece_lance` deixava de reconhecer o que era lance — a partida sumia do PGN;
- a camada invisível do PDF pesquisável saía com um caractere que a fonte embutida pode
  nem desenhar.

**A classe continua existindo, e a saída é que muda.** É a mesma separação que a
`notacao.FIGURINAS` já fazia entre o `♘` que o livro imprime e o `N` que o SAN exige — só
que agora com nome: `SINONIMOS_DE_SAIDA`, aplicado nos três lugares em que caractere de
modelo vira texto de arquivo (o livro, a notação e a camada do PDF). A base de treino
recebe o recorte sob a classe original, porque é ela que ensina o modelo.

Depois: `0` ocorrências de `✝` e `17` de `+` na mesma página, com `5.♔xf2 ♘e4+`,
`♕c5+`, `dxc4+ `, `♗g2+` — e o `+—` de "brancas ganham", que é ligadura e não xeque,
intacto.

Cobertura: 3 testes em `tests/test_f61_pgn.py` e 1 em `tests/test_f26_livro.py`.

## F69 — A prova visual do reparo, e o comprimento deixa de decidir — CONCLUÍDA (instrumento)

A F66 fechou nomeando o que faltava: *"o que separa `dynamic` de `drazic` não é o
dicionário nem a largura: é o que está desenhado ali"*. Esta fase é essa evidência, e o
número que ela existe para virar é a precisão de 62,5% que reprovou o reparo lá.

O reparo da F66 escolhia por **comprimento** — do menos escondido para o mais, e parava no
primeiro molde que desse. É Occam com a geometria, e é a única régua que existe quando não
se olha o papel: por ela `drazic` ganha de `dynamic`, porque casa sem esconder caractere
nenhum. Não é defeito da regra; é o limite de decidir sem prova.

### A pergunta é a do árbitro, feita ao contrário

O árbitro da F1.5b pontua um recorte e devolve **o que leu**. Aqui o dicionário já disse o
que deveria estar escrito, e o que falta saber é se o papel concorda:

> "o dicionário diz que neste pedaço está um `y`; quanto você dá a `y`?"

`predict_topk` não responde isso, e não é questão de conveniência: a resposta certa
costuma estar **longe do topo** — se estivesse no topo, o caractere não teria saído
errado. `NeuralPredictor.probabilidade_de(recorte, char)` é a pergunta invertida, e devolve
0,0 para classe que o modelo não conhece — que é o mesmo que "não posso afirmar isto", e é
a resposta segura para um número que **autoriza uma troca**.

### Onde cortar, quando não há vale

Provar `yn` num box exige partir o box, e a repartição igual erraria por construção: as
letras que colam não têm a mesma largura. Um vale do perfil resolveria, mas de cada quatro
colagens **uma não tem vale nenhum** (F66) — em negrito e itálico os traços se soldam, que
é justamente onde a prova precisa falar.

`BoxService.provar_letras` varre ±40% de uma letra em passos de 20%, cada junta
independente das outras: 5 posições por junta, e cobre de `il` a `wn` sem depender do
perfil. Uma letra só dispensa corte — é o box largo que escondia uma ligadura inteira.

**A nota é sempre a do pedaço mais fraco**, nos três níveis: a letra dentro do box, o box
dentro do trecho, o trecho dentro da palavra. É a mesma escolha do `_cortes_endossados` e
pelo mesmo motivo — `dynamic` só está ali se o `y` **e** o `n` estiverem, e uma média
deixaria um `y` convincente pagar por um `n` que não existe.

### A costura, e por que ela é uma função

`core.lexico` raciocina em índices de box e em letras; a prova mora na imagem.
`BoxService.prova_de_reparo(imagem, boxes, probabilidade)` devolve o `(caixas, letras) ->
nota` que `lexico.reparar` consome, e é a única passagem entre os dois — o léxico continua
sem saber o que é um pixel, como `generate_boxes_opencv` não sabe o que é um modelo e
recebe o `arbitro`. Um trecho que cai sobre **dois** boxes reparte as letras entre eles de
todos os modos com ao menos uma por box, e vale o melhor.

Sem `provar`, `reparar` faz **exatamente** o que fazia na F66. A fase não conserta o que
havia: acrescenta um juiz, e quem não passa por ele continua com o juiz antigo.

### O resultado

Nas 10 páginas rotuladas (8 do Kasparov, 2 do Aagaard), com o modelo de 249 classes de
2026-08-20:

| | reparos | pelo rótulo automático |
|---|---:|---|
| sem prova (o que a F66 media) | 5 | 2 certos, 3 errados |
| com prova, pontuando todos (régua 0,0) | 26 | 14 certos, 12 errados |
| **destes, os que passam a régua 0,5** | **19** | **13 certos, 6 errados** |

**A régua separa as duas populações inteiras, e o vão é o resultado desta fase.** Vistas as
26 notas da linha do meio:

|  | reparos | nota |
|---|---:|---|
| aceitos pela régua | 19 | **0,884 – 1,000** |
| recusados | 7 | **0,000 – 0,004** |

Não há uma única nota entre 0,004 e 0,884 — fator 221, e a régua pode ficar em qualquer
ponto do vão sem mudar uma linha do resultado. 0,5 é o que também se lê em voz alta: "o
papel concorda mais do que discorda".

**Seis dos sete recusados são erro de verdade, e são de dois tipos.** Quatro vêm de lance
que escapou do `notacao._fatiar` porque a figurina foi lida como letra, e que o dicionário
então "conserta": `Ndl` → `Geidl`, `Bfl` → `Kifl` (duas vezes), `NChess` → `Ichess`. Os
outros dois são palavras que o OCR leu **certas** — falta-lhes só o espaço — e que a troca
estragaria: `wehave` → `behave` e `Ifwe` → `Iftime`. Este último é literalmente a cauda do
ABBYY que a F66 apontou como o que mata o léxico geral como juiz.

Os seis tiram **0,000**. O papel não desenha nada daquilo, e a prova diz isso sem precisar
saber o que é um lance, o que é um nome ou o que é espaço faltando — que é o que torna esta
régua diferente das três que teriam de ser escritas para cobrir os mesmos casos.

**O sétimo é o preço, e ele tem nome:** `Dfnce` → `Defence` está **certo** e sai com 0,004.
É da página do Aagaard cujo rótulo tem 297 boxes — a menor das dez —, e a prova simplesmente
não enxerga a palavra. É o que a régua custa, e é o lado seguro de errar: quem reescreve
texto em silêncio paga em recall, não em precisão, e a fila de revisão continua vendo essa
palavra porque ela segue fora do dicionário.

Do outro lado, os que entram são a queixa que abriu a F66, resolvida: `Dmamic` → `Dynamic`
(0,996 e 0,999, nas três páginas em que aparece), mais `Beoko` → `Benko`, `zug3wang` →
`zugzwang`, `Sectets` → `Secrets`, `cloK` → `close`, `tbe` → `the`, `fow` → `few`, `eafer`
→ `safer`, `woald`/`wodd`/`coald`/`shodd` → `would`/`could`/`should`.

> **O rótulo automático é teto, e não conta** — é o mesmo defeito que a F66 registrou. Os
> **seis** que ele chama de errados acima da régua são todos rótulo **truncado**: ele diz
> `eample` onde o reparo escreve `example`, `tonamt` onde escreve `tournament`, `Dmic`
> onde escreve `Dynamic`, `difcult` onde escreve `difficult`, `Wadering` onde escreve
> `Wandering` — e num caso não há rótulo nenhum (`wiWh` → `within`, 0,940). É o rótulo que
> está incompleto, não o reparo. **Nada disto foi conferido no impresso nesta fase**: o que
> se leu aqui foram os rótulos, e a conferência à mão que escolheu as réguas foi feita
> sobre o modelo anterior.

### A régua é uma probabilidade, e por isso ela não atravessa uma calibração

**Este é o número que mais precisa de cuidado no futuro.** `NOTA_MINIMA` é lida na saída da
softmax, e a softmax depende da temperatura da F1.9. O modelo com que esta tabela foi
tirada está em `temperatura = 1.0` — softmax cru, porque **todo treino grava assim de
propósito** (`_gravar_meta`, F26) e a calibração ainda não foi refeita.

A consequência é a mesma que `AVISO_SEM_CALIBRACAO` dá para a fila de revisão: herdar esta
régua depois de `python calibrar_modelo.py --gravar` é aplicar um limiar medido sobre uma
escala à outra. O vão de 0,004 a 0,884 parece largo o bastante para sobreviver, mas
"parece" não é medida — e a medida foi feita no mesmo dia, logo abaixo.

#### A régua sobrevive à calibração, e isso passou a ser medido

Modelo de **258 classes** treinado às 18:18 do mesmo dia e calibrado a **T = 2,0993** — o
dobro da escala da tabela acima, que saiu em softmax cru. Mesmas 10 páginas:

| | reparos | nota |
|---|---:|---|
| aceitos pela régua 0,5 | 13 | **0,777 – 0,998** |
| recusados | 5 | **0,000 – 0,052** |

**O vão encolheu de 221x para 15x e continua sendo um vão**: nada entre 0,052 e 0,777, e o
0,5 continua dentro dele. A régua não precisou mexer.

Os quatro erros de verdade que ela barra são os mesmos de sempre — `wehave` → `behave` e
`Ifwe` → `Iftime` (palavras lidas certas, só sem espaço), `fChess` → `lchess` e `Afier` →
`Alfier` (nome). E o preço continua tendo o mesmo nome: `Dg6nce` → `Defence` está certo,
sai com 0,051 e é recusado.

**Não é um A/B limpo da temperatura**, e vale dizer: os pesos também mudaram, e o modelo lê
a página de outro jeito — onde antes saía `zug3wang` agora sai `zugwang`, `eafer` virou
`çafer`, `Whndering` virou `Wndering`. O que estas duas tabelas mostram juntas é que a
separação é **do método**, e não de uma escala específica: em softmax cru ou calibrado, a
prova dá quase 1 ao que está no papel e quase 0 ao que não está.

**Como isto foi medido, porque sem a trava não teria sido.** O modelo foi retreinado seis
vezes no dia e duas varreduras longas saíram misturadas antes de alguém perceber. As duas
tabelas acima só entraram porque a corrida grava o `modelo_sha256` **e** a temperatura
antes e depois, e se descarta sozinha se qualquer um dos dois mudar — ver a re-medida de
2026-08-20 na F1.9.

### O custo, medido

Página 13 do Kasparov, 1.575 boxes, 100 deles largos:

| | chamadas ao modelo | tempo |
|---|---:|---:|
| como a fase nasceu | 89.694 | 58,7 s |
| guardando a resposta por pedaço | **19.374** | **14,8 s** |

A varredura repete recorte: com três letras são 25 partições e 75 perguntas, mas só 35
pedaços distintos. Guardar a resposta por `(início, fim, letra)` não muda nota nenhuma — o
modelo é determinístico — e é o que faz a fase caber em minutos. Ainda assim são ~15 s por
página, e é mais uma razão de isto ser instrumento e não caminho de revisão.

### A maiúscula que a máscara comia, e a pergunta errada por trás dela

O dicionário é todo minúsculo, e é por isso que `_remontar` remonta em vez de devolver a
palavra dele — trocando só o pedaço estragado, o `D` de `Dynamic` fica de pé. Isso resolve
**enquanto a máscara começa depois da inicial**, que é o caso comum: colar exige um vizinho
à esquerda. Quando ela pega a inicial, a letra vem do dicionário e a maiúscula ia junto:
`Wandering` lido `Whndering` saía `wandering`.

**E o estrago não era só na saída.** As letras que vão à prova saíam do mesmo lugar, então
a pergunta ao modelo era pela **classe errada** — `W` e `w` são classes separadas, porque
são desenhos separados, e a prova pedia a probabilidade do minúsculo sobre um maiúsculo
impresso. Medido nas mesmas 10 páginas, `Whndering` sai de **0,619 para 0,903** com a
pergunta certa: era a pior nota aceita da tabela, e a causa não era o papel.

Um segundo caso mudou de vencedor: `Dfnce` propunha `prince` e passa a propor `Defence`,
que é o que está impresso. Continua abaixo da régua, porque a prova não enxerga nem um nem
outro — só que agora o que a régua recusa é um reparo **certo**, e é ele o preço nomeado
acima.

`_com_a_inicial_do_lido` é a regra, num lugar só, e vale para os dois caminhos — o da F66
também tinha o defeito. **Ela para na inicial de propósito**: o candidato pode ter
comprimento diferente do lido, então nenhuma posição interna corresponde à outra. Palavra
toda em maiúscula sairia meio a meio, e não há nenhuma no material medido.

### A outra régua, e o que ela não faz

**`MIN_PARA_REPARAR = 3`, e não o `MIN_PARTE = 2` da triagem.** Sinalizar `p1ay` é barato e
útil; **reparar** um núcleo de duas letras é adivinhar, porque quase não sobra âncora fora
da máscara. É 3 e não 4 porque a 4 se perde `fow` → `few`, que está certo e tira 1,000 na
prova; régua que custa acerto sem comprar recusa não fica de pé, e é a conta da F24 e da
F36. Note que ela **não** é o que barra o lance de xadrez: `Ndl`, `Bfl` e `NChess` têm
núcleo de três e passam por ela — quem os mata é a nota.

### O que fica em aberto

**O livro continua não chamando o reparo, e isso é decisão, não pendência.** O contrato 2
da SPEC §5.8 diz que palavra fora do dicionário é sinalizada e **nunca** aproximada da mais
parecida; embarcar a troca é emendar esse contrato, não uma consequência de a prova
existir. `livro.py` não mudou e o livro exportado não corre risco nenhum desta fase.

**O empate no topo é resolvido por ordem alfabética.** Dois candidatos com a mesma nota
acima da régua entram como se um tivesse ganhado; `Reparo.vantagem` sai 0,0 e denuncia, mas
ninguém lê o campo ainda. Não há caso no material medido, e a régua que resolveria —
recusar vantagem zero — não tem população que a escolha.

**O vocabulário do próprio livro continua fora**, herdado da F66: ele exige duas passadas e
vale por si, e a prova visual não o dispensa — ataca o outro lado do mesmo erro.

Cobertura: `tests/test_f69_prova_do_reparo.py`, 27 testes — as duas metades e a costura,
com `provar` injetado. O modelo não entra em teste nenhum, pelo motivo da F27: teste que
precisa de rede treinada não roda em máquina limpa.

Reproduzir: `python medir_reparo.py --prova --exemplos`, e
`python medir_reparo.py --nota 0 0.3 0.5` para a varredura da régua.

## F70 — Uma letra do cabeçalho apagava a calha da página inteira — CONCLUÍDA

A F61 fechou dizendo que o livro de duas colunas deixava de sair misturado, e ele
continuava saindo em parte das páginas. A régua de lá — `calha >= 0,8 × largura mediana de
caractere` — não era o problema. O problema é que ela media a coisa errada.

Medidas as **354 páginas** do Nunn (`scratchpad/calha_nunn.py`), com a posição da calha
como verdade de referência — num livro de duas colunas ela fica sempre no mesmo x, e a
mediana das páginas inequívocas dá 0,505 da largura do texto:

| | |
|---|---:|
| páginas de prosa | 352 |
| de duas colunas (têm vão na posição canônica) | 305 |
| lidas em duas colunas | 298 |
| **falsos negativos** | **8** |

Os oito são o capítulo *Solutions to Exercises* — páginas 333 a 351, ímpares —, prosa
justificada em duas colunas, saindo intercalada. E outras sete passavam por 0 ou 1 px:
as páginas 38 e 316 empatavam com o limiar, e as 112, 114, 118, 140 e 310 o venciam por
um pixel.

### A causa não era o limiar, e sim o OR

Em cada página falha há **um único box de 25×27 px em y≈105** — uma letra do cabeçalho
corrente, que é centralizado, e centralizado é em cima da calha:

| | com o box | sem ele |
|---|---:|---:|
| p335 | 7 px → 1 coluna | 31 px → 2 colunas |
| p345 | 6 px → 1 coluna | 31 px → 2 colunas |
| p038 | 13 px (empate) | 42 px |

A projeção era `ocupado[x] = True` para **qualquer** box: um caractere apaga a calha da
página inteira. É por isso que o defeito era errático — "acerta em algumas páginas e erra
nas outras" era literal, e a variável é onde a letra do cabeçalho calha de cair.

**A calha de verdade do Nunn tem ~56 px (3,3 larguras medianas), e não os 14–20 que a
régua via.** O que a F61 mediu foi o resto que o cabeçalho deixou, e é por isso que
`CALHA_EM_CARACTERES` precisou descer a 0,8. Baixá-la nunca foi o remédio: era o sintoma.

### O controle da F61 não era um controle

O *Attacking Manual* entrou na tabela de calibração da F61 como livro de **uma** coluna, e
os seus 0,06–0,12 serviram de prova do que é "vão que não é calha". Conferida a página 128:
**é de duas colunas**, prosa justificada com diagrama. O que se mediu como vão inocente era
a calha do livro apagada pelo mesmo cabeçalho, e o livro saía embaralhado em **27 das 30**
páginas amostradas. O único controle de coluna única daquela tabela é o Darcy Lima.

### A correção: contar linhas, não boxes

O cabeçalho é **uma** linha. O miolo de uma página de coluna única é coberto por todas as
quarenta, porque o espaço entre palavras do texto justificado cai num x diferente a cada
linha e nenhum x central sobrevive à conta. `LINHAS_NA_CALHA = 1`.

Tolerar linha exige um piso, e ele foi medido: no recorte de cinco linhas do
`test_f16_colunas`, uma linha é 20% da página e a tolerância inventa uma terceira faixa.
`LINHAS_PARA_TOLERAR = 12` fica no vão — 2,4× acima do recorte e 1,25× abaixo da menor
página de prosa medida (15 linhas no Nunn, 23 no Aagaard, 30 no Darcy Lima). Abaixo dele
vale a régua de antes, que é o lado seguro do erro.

Também: o vão que encosta na margem esquerda deixa de poder virar calha. Com o OR ele não
tinha como existir; com a tolerância ele aparece na página em que só o cabeçalho alcança a
margem, e faixa aberta ali jogaria os boxes dele para o fim da página.

### A calha certa é larga, e aí cabe gente dentro dela

Achar a calha de verdade quebrou uma coisa que ninguém tinha visto porque não havia como
ver: o `_por_colunas` **despejava no fim da página** todo box que não caísse em faixa
nenhuma. Com a calha de 20 px isso nunca disparava — não cabe caractere ali. Com os 56 px
que a calha tem de verdade, quem mora lá dentro é o caractere central do cabeçalho, o
mesmo do defeito, e ele passou a sair depois da página inteira.

Aparece como salto a mais na régua: as páginas do Nunn saíam com **2** saltos entre
colunas em vez de 1, e o segundo era o cabeçalho no fim. Quem cai na calha passa a ficar
com a faixa **mais próxima**, que é a regra que o `livro._coluna_de` já usava para decidir
de quem a figura é vizinha.

### O resultado

Páginas lidas em duas ou mais colunas, com o código de produção
(`scratchpad/verificar_final.py`):

| | antes | depois |
|---|---:|---:|
| Nunn, *Secrets of Rook Endings* (2 colunas) | 298/352 | **316**/352 |
| Aagaard, *Attacking Manual* (2 colunas) | 3/30 | **28**/30 |
| Yusupov, *Complete* (2 colunas) | 23/35 | **25**/35 |
| **Darcy Lima (1 coluna) — o controle** | 0/39 | **0/39** |

As oito páginas falhas passam todas, com calha de 51–59 px, e as que passavam por empate
ganham folga de verdade: 13 px viram 50.

E os saltos entre colunas na ordem de leitura, que é a régua da F61 — numa página de duas
colunas lida direito, **1** por página (`medir_colunas.py --pdf`):

| | páginas | F1.6 | F61 | hoje |
|---|---:|---:|---:|---:|
| Nunn, amostra de 12 em 12 | 12 | 147 | 12 | **12** |
| Aagaard, amostra de 10 em 10 | 9 | 155 | 156 | **11** |
| Darcy Lima (1 coluna) — o controle | 11 | 4 | 1 | **1** |

O Aagaard é o número que justifica a fase: 156 saltos onde o certo são 9, e a F61 não
tinha como saber porque o contava como livro de uma coluna. Na amostra de 12 em 12 do
Nunn a F61 já acertava tudo — as páginas que ela erra são as do *Solutions to Exercises*,
e é preciso varrer as 354 para dar com elas.

### O que fica em aberto

**O título de duas linhas sobre a calha ainda a apaga.** A tolerância é de uma linha, e
duas cruzando derrubam a régua de volta para coluna única. O `sort_boxes_reading_order`
sabe tratar elemento transversal, mas só depois de as colunas existirem — e aqui elas não
chegam a existir. Não foi medido quantas páginas têm título de duas linhas.

**Coluna e tabela continuam sendo a mesma coisa**, herdado da F61 e não tocado aqui.

**O Yusupov sai com três faixas no medidor cru** (17 de 25 páginas, contra 11 de 23 antes),
e isso é artefato da medição, não do produto: são os rótulos `8`–`1` e `a`–`h` ao lado do
tabuleiro. No caminho real de exportação some, porque o `livro.caixas_e_diagramas` tira os
diagramas antes de chamar `detectar_colunas` — conferido nas páginas 60, 300, 360 e 600,
que dão 3 no medidor e 1 ou 2 na exportação.

**~~A tabela da página 236 passa a sair partida ao meio.~~** Errado, e corrigido na F71: a
tabela **não sai de jeito nenhum**, nem antes nem depois desta fase. Ela tem moldura
fechada, e com `RETR_EXTERNAL` tudo que está dentro dela é contorno filho — o retângulo
sai como **um** box de 1342×1099, o descarte o joga fora por ser grande, e as 24 células
vão junto. Medido: 0 boxes dentro do retângulo, contra as 276 caixas de caractere que há
ali. A leitura em duas colunas desta página está certa, e é a da metade de baixo (texto à
esquerda, diagrama à direita).

Cobertura: `tests/test_f70_calha_do_cabecalho.py`, 12 testes.

## F71 — A tabela não saía partida: não saía — CONCLUÍDA

A F70 registrou que a tabela da página 236 do Nunn "passa a sair partida ao meio". Errado,
e o erro é meu: fui olhar o texto exportado e não havia texto nenhum. **Dentro do retângulo
da tabela há 0 boxes**, contra as 276 caixas de caractere que o papel tem ali. A tabela
some do livro, e sumia antes da F70 também.

`findContours` roda com `RETR_EXTERNAL`. Moldura fechada, e tudo que está dentro dela é
contorno **filho**, que não é devolvido: o retângulo sai como **um** box de 1342×1099, o
descarte o joga fora por ser grande, e as 24 células vão junto. É o mecanismo que a
`descartar_blocos_nao_texto` documenta desde a F1.8 como uma *vantagem* — é o que impede o
tabuleiro de virar 64 caixas de casa. Para uma tabela, é a perda silenciosa do conteúdo.

### A manobra já existia, e a peneira é que estava no lugar errado

A F11 já fazia exatamente isto — olhar dentro do bloco antes de jogá-lo fora, com Otsu
local — para o painel de pontuação do Yusupov. O que a impedia de ver a tabela era a
peneira que protege o diagrama, `largura >= altura × 1,5`, posta "no meio do vão de
propósito" porque nada no material caía entre 1,3 e 2,6.

Caía. A tabela mede 1342×1099, razão **1,22**:

| | razão | o que era |
|---|---:|---|
| tabuleiro (medidos 509 blocos) | 1,000 – 1,072 (p95) | diagrama, não se abre |
| **tabela de finais, Nunn p236** | **1,22** | ficava no vão |
| painel de pontuação, Yusupov | 2,69 | o caso da F11 |

A régua passa a ser a **mesma** que o `diagrama` usa para dizer o que é tabuleiro
(`TOLERANCIA_QUADRADO`, 1,12), importada e não copiada. Assim o caso do meio deixa de
existir por construção: o que o `diagrama` reconhece como tabuleiro é exatamente o que aqui
não se abre, e não há mais faixa em que um bloco seja quadrado demais para ser lido e pouco
quadrado para virar diagrama. De quebra a régua deixa de ser só "mais largo que alto" —
uma tabela pode estar em pé.

### Duas coisas que abrir mais blocos escancarou

**A página que é uma fotografia rende 40.382 "glifos".** Medida a capa do *Chess Evolution
1*: `escala_de_texto` devolve **2 px** — não há texto na página para pesar —, e com essa
régua `ALTURA_GLIFO` aceita como caractere qualquer grão entre 0,7 e 5 px. A página saía de
1 box para **24.041**. Uma régua de capacidade não pega isso e por construção: com escala
de 2 px "cabem" 1,4 milhão de caracteres na capa. O vão está na contagem e é largo — 71 no
painel da F11, 276 na tabela, 392 na capa do Aagaard, contra 40.382 —, então
`MAX_GLIFOS = 2000`, 5× acima do maior caso bom e 20× abaixo do único ruim.

**A moldura fechada reaparece dentro do próprio recorte.** Recortar o bloco pelo seu
retângulo traz a borda junto, e ali dentro ela é de novo o contorno externo — o
`RETR_EXTERNAL` devolve a moldura e o conteúdo continua sendo filho de alguém. Na tabela do
Nunn isso não aparece porque o scan quebra a borda em pedaços; numa moldura que fecha de
verdade, o defeito sobreviveria à própria correção. `MARGEM_DA_MOLDURA` tira 0,25 altura de
caractere de cada lado antes de olhar. Medido na montagem do teste: 0 glifos com a borda
dentro, 12 sem ela.

### O resultado

A página 236 no caminho de exportação:

| | antes | depois |
|---|---:|---:|
| boxes na página | 557 | **895** |
| boxes dentro da tabela | **0** | **338** |
| colunas detectadas | 2 | 1 |

E a tabela sai em 16 linhas, cada uma da esquerda para a direita — que é como se lê uma
tabela. A página passar a ser lida em **uma** coluna é a consequência certa: a calha que a
F70 achava ali era o vão entre o texto e o diagrama da metade de baixo, e com as células
preenchendo a largura ela deixa de existir. Nada de "a tabela sai partida": ela sai.

Efeito no resto, medido em 84 páginas de 5 livros — só cresce onde havia bloco engolido, e
nenhuma explosão:

    Nunn        +38 boxes (a capa)        Yusupov Complete   +0
    Aagaard      +7 boxes (a capa)        Chess Evolution    +0
    Darcy      +152 boxes (a capa e 4 páginas de texto)

### O que fica em aberto

**A tabela é lida como texto corrido, e não como tabela.** As células saem na ordem certa,
mas nada marca onde uma acaba e a outra começa: no EPUB isso é um parágrafo por linha da
tabela, com as colunas separadas por espaço. Para o livro de finais do Nunn, em que a
tabela *é* o conteúdo, ler na ordem certa já é a diferença entre ter e não ter — mas não é
uma tabela.

**A moldura ainda vira um box.** Ela deixa de engolir o conteúdo, mas continua na página
como retângulo descartado; o que sai do `trama.aplicar` são os caracteres, não a estrutura.

Cobertura: `tests/test_f71_tabela_engolida.py`, 9 testes.

## F72 — A tabela sai como tabela — CONCLUÍDA

A F71 tirou a tabela de dentro da moldura que a engolia e ela passou a sair na ordem certa,
mas como prosa: as células uma atrás da outra, sem nada que dissesse onde uma acabava e a
outra começava. No livro de finais do Nunn a tabela **é** o conteúdo — `W: Win (1 ♖e1!)` na
casa de `B♖h2` × `W♔d1` é a informação —, e um parágrafo por linha com as colunas separadas
por espaço não a preserva.

### Onde está a tabela: a marca, e o merge que a apagava

A moldura **não sobrevive** à correção da F71: o `trama.aplicar` troca o bloco pelo que há
dentro dele, e o retângulo some. Sem ele não sobra na página nada que diga onde a tabela
estava. Daí a marca: `BoxEntry.moldura`, posta em cada glifo na hora da troca.

E ela se perdia logo em seguida. O `merge_vertical_boxes` **constrói uma caixa nova** e
copiava só `negativo`; medido na página 236, os 277 boxes chegavam marcados e saíam sem
marca nenhuma. Agora `moldura` viaja junto, e basta um dos dois lados do merge tê-la — o
pingo e o corpo do `i` são o mesmo caractere.

**A marca diz onde olhar, e não o que aquilo é.** O painel de pontuação da F11 vem marcado
igual: quem decide é a grade, e sem duas linhas e duas colunas de réguas o conteúdo segue
o caminho de sempre.

### A grade vem da imagem, e sem folga arbitrária

As réguas se procuram onde elas estão — na imagem —, projetando a tinta na extensão inteira
da página. Passa por régua o que atravessa metade da faixa; linha de texto não atravessa.

Duas coisas que a medição obrigou:

**As verticais são medidas só no miolo**, entre a primeira e a última horizontal. Medi-las
na altura toda mistura a divisória da tabela com o vão entre as colunas do texto que vem
antes e depois dela, e foi assim que a divisória mais fraca da página 236 se perdeu — a
tabela sairia com 3 colunas em vez de 4. O limiar também foi medido: a 0,6 falta essa
divisória; a 0,5 e a 0,4 aparecem as 5 certas; a 0,3 entra uma sexta que não existe.

**A régua se acha por vizinhança, não por distância.** A primeira tentativa procurava a
moldura a tantos pixels do texto, e erra assim que a célula tem mais respiro: 7 px na
tabela do Nunn contra 130 px na montagem do teste, com caracteres de altura parecida.
`_cercam` pega a última régua **antes** do texto e a primeira **depois**, com uma tolerância
de 2% — porque um pedaço da moldura partido pelo scan vira glifo e entra no retângulo do
texto: medido, o texto começa em x=156 e a régua esquerda em x=159.

### E dentro da célula não se lê como se lê a página

Com a grade pronta e o modelo de verdade rodando, a primeira célula saiu
`w win ( 1 B Draw ( l ♖e 1` — as duas linhas dela **intercaladas**. A culpa é de usar a
ordem de leitura da página dentro da célula: ela procura colunas, e numa célula de duas
linhas curtas acha uma, porque o vão vertical entre as palavras passa por calha. Célula se
lê linha a linha, sempre — `_agrupar_em_linhas`, que agrupa sem procurar coluna nenhuma.
Depois: `w w in ( 1 ♖e 1 ! ) B Draw ( l ♖a2 !)`.

### O resultado

Página 236 do Nunn, do PDF ao EPUB:

| | |
|---|---|
| grade encontrada | 6 filas × 4 colunas |
| boxes consumidos pela tabela | 264 de 265 |
| células com texto | 21 de 24 |
| no EPUB | `<table>` com `<tr>`/`<td>` e fio de célula |

As 3 células vazias não são todas perda: duas estão vazias no papel, onde está impresso `*`.
A terceira, e mais duas da mesma coluna, saem vazias porque **a recuperação da F71 não
trouxe nada delas** — contados os boxes por célula, chegam 0 onde há texto impresso. É
perda da recuperação, não da grade.

No livro inteiro, e nos outros três:

| | páginas | tabelas |
|---|---:|---:|
| Nunn, *Secrets of Rook Endings* | 354 | **6** (7×4, 4×4, 9×3, 6×4, 7×4, 7×4) |
| Aagaard, *Attacking Manual* | 33 | 0 |
| Darcy Lima | 40 | 0 |
| Yusupov, *Complete* | 44 | 0 |

**O Darcy dava 6 e nenhuma existia.** Foi a primeira versão da busca de réguas, a que
procurava a moldura a uma distância fixa do texto: ela achava "grades" de 24 e de 17
colunas em páginas de prosa com diagrama. Procurar a régua que **cerca** o texto, em vez de
a que está a tantos pixels, derrubou as seis sem custar nenhuma das do Nunn — que é o que
uma peneira boa faz.

Medida também a recontagem de colunas depois de tirar a tabela da página, que parecia
necessária (as células apagam a calha): **não muda em nenhuma das 6**. A página que tem
tabela é de coluna única abaixo dela também, e o código ficou de fora.

**As células entram no texto da página** (`PaginaExtraida.texto`), e isso não é arrumação:
é de lá que sai o alfabeto que escolhe a fonte dos símbolos da F62. Sem elas a figurina
saía nua dentro da célula e vestida no parágrafo da mesma página — `♖` contra
`<span class="sim">♔</span>`, medido no EPUB.

O DOCX ganha a tabela pelo `Table Grid`, que é o único estilo de grade do template padrão
do Word. Sem ele a tabela sai sem fio e não se vê onde a célula acaba.

**Sem `<th>`, e não é descuido**: nada aqui sabe se a primeira fila é cabeçalho. O que se
mediu foi a grade, e a grade não diz o que a célula significa — marcar cabeçalho por
posição erraria em toda tabela que começa com dado, e o leitor de tela anunciaria
"coluna: W: Win" como se fosse título.

### O que fica em aberto

**Uma moldura por página.** Duas tabelas na mesma página entrariam no mesmo retângulo
envolvente e sairiam como uma só, embaralhada. Não há caso no material medido, e adivinhar
o agrupamento custaria mais do que o defeito que evitaria.

**A célula não guarda a quebra de linha.** As linhas de dentro dela viram um texto só,
separado por espaço: `W: Win (1 ♖e1!) B: Draw (1...♖a2!)` sai numa linha, e no papel são
duas. Para esta tabela isso não perde informação; para uma de duas frases independentes,
perderia.

**A pontuação miúda continua fora**, herdado da F71: o filtro de altura de `trama.glifos`
não deixa passar ponto nem vírgula, e o que encosta na divisória vai junto com ela.

Cobertura: `tests/test_f72_tabela_no_epub.py`, 12 testes.

---

## F93 — A pasta de revisão passa a ter régua, e o teto pegava uma página só — CONCLUÍDA

"Criar Recortes para Revisão" existe desde a F2.7 e nunca tinha sido medido. A acurácia do
modelo tem régua (`medir_paginas.py`); o que a pasta de revisão **entrega** não tinha, e é
outra pergunta:

> dos arquivos que caíram em `revisao_ocr/lower_o/`, quantos são um `o`?

`medir_coleta.py` responde nas 10 páginas rotuladas à mão — as mesmas da calibração —
classificando cada recorte em três, porque os três importam por motivos diferentes:
**certo** (é o contraste que faz o intruso saltar aos olhos na grade), **errado** (é o
material de treino que a fase existe para colher) e **espúrio** (não há caractere nenhum ali;
o modelo foi obrigado a responder e respondeu).

### O ponto de partida, medido

| modo | na pasta | certos | errados | espúrios |
|---|---:|---:|---:|---:|
| todos | 10.853 | **93,7%** | 2,6% | 3,7% |
| só os duvidosos | 58 | 10,3% | **55,2%** | 34,5% |

Os dois modos fazem o que prometem: o primeiro é contraste, o segundo é densidade de erro —
58 arquivos para achar 32 erros, contra 10.853 para achar 282. O que estava errado não era
a composição da pasta; era **tudo o que acontece com ela depois**.

### O primeiro erro desta fase foi medir no caminho errado

A primeira rodada usou `generate_boxes_opencv` na página inteira, que é como `medir_paginas`
e a calibração medem, e deu **6,6% de espúrios**. O botão não faz isso: ele passa por
`livro.caixas_e_diagramas`, que tira os respingos e o miolo dos diagramas **antes** de
classificar. No caminho certo são 3,7% — a exclusão de diagrama já resolvia metade do
problema que eu ia atacar. `medir_coleta.py --caminho cru` guarda a comparação.

### A porta que não paga — medida, e desligada

A hipótese: recorte que não é caractere entra como caractere, e geometria o pega. Está
errada, e a varredura mostra por quê — as medianas coincidem nos dois lados:

| | lado | área | tinta | proporção | confiança |
|---|---:|---:|---:|---:|---:|
| caractere | 17 | 380 | 0,491 | 1,364 | 0,9996 |
| espúrio | 16 | 380 | 0,505 | 1,366 | 0,9966 |

Nenhum corte tem troca acima de 1x. O melhor deles pega **11 espúrios e leva 49 caracteres
de verdade junto**.

**O motivo é estrutural, e é a parte que vale guardar.** Depois de a exclusão de diagrama
passar, o que sobra sem rótulo não é lixo: é tinta com forma de texto que o rotulador humano
não rotulou — cabeça de página, número de folha, nota de rodapé. Nenhuma régua de geometria
separa isso de texto, **porque é texto**. E o contraste, que eu tinha como a régua segura,
nunca dispara: o box nasce de um componente conexo de tinta, então há sempre tinta e sempre
papel dentro dele — mediana 255 dos dois lados.

Fica ligável (`Coletor(filtrar=True)`) e fica medido. É a mesma decisão da F47 com a margem:
**o instrumento fica, a conclusão é não.** O que a mudaria é uma pilha em que o espúrio de
verdade sobreviva à exclusão de diagrama — um scan sujo, uma página com trama.

### Os três que pagam

**1. A mesma renderização entrava muitas vezes.** Em PDF digital o mesmo glifo sai byte a
byte igual toda vez.

| | na pasta | repetidos |
|---|---:|---:|
| Chess Evolution 1, 6 páginas, sem dedução | 4.093 | — |
| com dedução | 717 | **3.376 (82,5%)** |

Nas páginas rotuladas, que são JPG de scan, são 9,8% — e a diferença entre os dois números
**é** o achado: em scan o mesmo glifo nunca sai com os mesmos pixels, em PDF digital sai
sempre. A régua é igualdade e não semelhança: a impressão é o hash dos 32x32 que a rede
recebe, então dois recortes com a mesma impressão são o **mesmo tensor**, e treinar nos dois
ensina o que treinar num deles ensina. Não há como colapsar duas amostras que o modelo saiba
distinguir.

Custo honesto: a pasta fica marginalmente mais densa em erro (93,7% → 93,2% de certos),
porque o que se repete são as letras comuns e elas estão certas. Isso é o efeito desejado —
o que a grade precisa não é de mais acertos, é de miniaturas diferentes umas das outras.

**2. O teto guardava os primeiros N, que são as primeiras páginas.** Contar páginas
distintas na pasta inteira não mede nada — com 147 classes e 10 páginas, qualquer amostra
toca as 10. O viés é **dentro** da classe, e das 147 classes, 43 passam de um teto de 30:

| teto | na pasta | páginas por classe (mediana) | a pior classe |
|---|---:|---:|---:|
| sem teto | 9.792 | 10 | 6 |
| primeiro-a-chegar (antes) | 1.902 | **1** | 1 |
| sorteado (F93) | 1.902 | **8** | 4 |

**Mediana de uma página.** A classe inteira saía da primeira página em que aparecia: uma
fonte, um estado de scan, um contexto — e o itálico da página 200, o borrado e o quebrado,
que são exatamente o que a revisão quer ver, eram descartados em silêncio depois que o teto
enchia. Trocado por amostragem de reservatório: uma passada, mesma memória, amostra uniforme
do livro inteiro. Semente fixa, para duas coletas do mesmo livro se compararem.

**3. "Mais duvidoso primeiro" não funcionava.** O nome do arquivo carregava página e
confiança nessa ordem — `p0042_c037_…` —, e a intenção documentada era ordenar por dúvida
sem abrir o índice. Só que clicar em Nome no Explorer ordena por **página**, e o recorte mais
duvidoso da classe podia estar na página 240, no fim da lista. Trocados de lugar
(`c037_p0042_…`), a ordem prometida é a que sai, e a página continua ali para desempatar.

### E o índice ganhou a segunda candidata

Quem revisa e acha um recorte na pasta errada quer saber **para onde ele ia**. O CSV ganhou
`segunda`, `p2` e `margem`; ordenado por `margem`, ele agrupa os pares que o modelo confunde
em vez de espalhá-los pela pasta. Nas 10 páginas do Yusupov, o topo dessa fila é
`-`/`.`, `'`/`,`, `"`/`u`, `w`/`M` — que é a lista de pares para conferir em bloco.

**É dado, e não régua.** A F47 mediu as duas curvas e concluiu que no ponto de operação a
margem empata com a confiança; nada aqui a promove a critério. O custo é uma inferência por
arquivo **gravado** — com a dedução na frente, e não por box da página.

### O livro escaneado inteiro — 322 páginas, e é a escala que fala

As 10 páginas rotuladas respondem "o que tem na pasta"; o que depende de **escala** elas não
podem responder, e a métrica do teto saturava nelas (com 10 páginas, qualquer amostra toca
as 10). `medir_coleta.py --livro` faz uma passada por um livro sem gabarito, guardando por
recorte só classe, impressão, página e confiança — a imagem sai da memória assim que a
impressão é tirada, que é o que torna 425 mil recortes viáveis.

Kasparov, *The Dynamic Benko Gambit* — 322 páginas escaneadas:

**425.550 recortes, 1.322 por página, 230 classes.** A dedução tira **7,7%** (32.637), na
mesma faixa dos 9,8% das páginas rotuladas — e distante dos **82,5%** do PDF digital. Os
três números juntos são o achado: em scan o mesmo glifo nunca sai com os mesmos pixels; em
PDF digital sai sempre. A dedução paga onde o livro é renderizado, e não atrapalha onde não é.

O modo "só os duvidosos" rende **4.765 recortes no livro todo** — 14,8 por página, 1,1% da
pilha. É o mesmo porte dos 3.943 em 264 páginas que a F2.7 mediu no Chess Evolution 1.

E o teto, com espaço para falar. O teto máximo de páginas distintas que uma classe pode
cobrir é o próprio teto, então a coluna certa é quanto dele se alcança:

| teto | classes que enchem | páginas por classe (mediana) | do teto possível | a pior classe |
|---|---:|---:|---:|---:|
| 30 — primeiro-a-chegar | 123 | 14 | 47% | 2 |
| 30 — sorteado (F93) | 123 | **28** | **93%** | 19 |
| 100 — primeiro-a-chegar | 90 | 18 | 18% | 3 |
| 100 — sorteado (F93) | 90 | **81** | **81%** | 42 |
| 300 — primeiro-a-chegar | 65 | 24 | 8% | 4 |
| 300 — sorteado (F93) | 65 | **180** | **60%** | 88 |

**Quanto maior o teto, pior era o primeiro-a-chegar** — e o mecanismo está na tabela das
classes cheias: `e` aparece 30.519 vezes em 318 das 322 páginas, quase 100 por página. Com
teto de 300 e primeiro-a-chegar, as 300 amostras de `e` se esgotavam em **três páginas** do
livro; a pior classe medida ficou em quatro. Sorteando, as mesmas 300 vagas cobrem 180
páginas. O tamanho do arquivo é idêntico — 26.959 recortes nos dois casos —, e o que muda é
só de onde eles vêm.

O instrumento reimplementa a amostragem porque no livro inteiro não há memória para os
recortes; `test_o_instrumento_do_livro_inteiro_nao_reescreve_a_regra_do_teto` é a trava da
F52 contra os dois divergirem, e cobra que o script e o `Coletor` sorteiem igual.

### O que fica em produção

Dedução ligada, teto sorteado, nome com a confiança na frente, índice com a segunda
candidata, porta desligada e medida. E `resumo()` passou a explicar cada recorte que não
ficou, com o motivo: `total + descartados` é o que chegou, e a identidade é testada — é o
mesmo padrão do teto, em que um número escondido deixaria uma régua mal calibrada varrer um
livro inteiro sem ninguém notar.

Cobertura: `tests/test_f27_coleta.py`, 35 testes (12 novos). Reproduzir:
`python medir_coleta.py`, `--varrer` para as curvas da porta, `--pdf <arquivo>` para a
dedução em PDF digital, `--livro ilovepdf_pages-to-jpg` para o livro escaneado inteiro.

---

---
