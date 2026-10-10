# ROADMAP — histórico das fases F94 a F125

As seções abaixo saíram do `ROADMAP.md` em 2026-10-06 (item 8 da análise geral), tal como
estavam: o arquivo vivo ficou com o sumário, a ordem de execução, o índice das fases e o que
está em aberto. Cada seção é o registro da fase — o que entrou, o que foi medido e onde está.

## F94 — A letra que o OCR não consegue aprender sozinho — CONCLUÍDA

**Um caractere sem classe é um erro garantido, e o ciclo normal não fecha esse buraco.** A
rede só emite uma das classes que tem; se `š` não é classe, todo `š` do livro sai como outra
coisa — e a revisão da F2.7 não o pega, porque o recorte cai na pasta de `s` e ali ele
*parece* certo. Coletar → revisar → promover colhe o que o modelo leu, e o modelo não leu.

Então a classe tem de nascer de fora do OCR. `importar_letras.py` a faz nascer de duas
fontes, e o `--faltantes` diz quando: ele lê a camada de texto de um PDF e lista o que
aquele livro tem e o modelo não conhece — antes de qualquer OCR rodar. É o gatilho para
livro futuro.

### O que a camada de texto vale, e foram três respostas erradas antes da certa

O rótulo vem do PDF, não do modelo. Parece a melhor procedência possível — é o que o editor
do livro escreveu — e **nestes livros ela mente**, pelo defeito inteiro da F2.5: as fontes
de figurinha são Type0/Identity-H e o produtor escreveu qualquer coisa no `ToUnicode`. Nos
seis PDFs do projeto, `·` aparece 19.331 vezes, `>` 18.573, `ʘ` 514. Nenhum está impresso em
página nenhuma: são ♔♕♖♗♘.

**Primeira tentativa: filtrar por fonte.** Medir a concordância da camada em letras de
controle que o modelo conhece bem, e colher só das fontes que passassem. No Aagaard, cinco
fontes passaram com 85% a 97% — e as 54 amostras de `Å` colhidas delas eram **54 desenhos de
rei**. O portão não podia funcionar, e a razão é estrutural: a mesma face desenha o texto e a
figurinha, mapeia o texto certo e a figurinha errado, e as letras de controle nunca visitam a
figurinha. Só apareceu porque a folha de contato foi gerada e olhada.

**Segunda tentativa: filtrar por livro.** Hipótese natural depois da primeira — os Yusupov
seriam os livros ruins. Medido: Yusupov Complete tem **89,9%** de concordância nas letras de
controle e Dvoretsky **91,2%**. A camada está alinhada e bem mapeada nos dois. Hipótese morta.

**Terceira: perguntar ao modelo, recorte a recorte** — e aqui a régua certa não foi a
primeira que escrevi. O modelo nunca vai *confirmar* a letra nova (é por não a ter que ela
está sendo criada); o que ele pode é reconhecer a letra-base — num `š` de verdade ele lê `s`.
A primeira régua presumia a favor do recorte: entrava tudo, menos o que o modelo
contradissesse com confiança ≥ 0,90. O argumento era que hesitação não desmente, e que
recusar por ela jogaria fora o recorte estranho — que é o que a classe nova mais precisa.

Nas 58 amostras colhidas dos seis PDFs, rotuladas a olho na folha de contato:

| régua | dos 27 bons | dos 31 de lixo |
|---|---:|---:|
| presume a favor (contradição ≥ 0,90) | 27 | **31** |
| presume contra (só leitura plausível) | 17 | **0** |

**O lixo mora justamente na hesitação, e tinha de morar**: um borrão de trama ou um pedaço de
régua não pertence a classe nenhuma, então o softmax se espalha. O `♗` mais confiante da
pilha deu 0,871 e passava por baixo do limiar — e baixá-lo até pegá-lo mataria o `å` que o
modelo lê como `ä` a 0,590, que é bom. **Não há limiar; há inversão da presunção.**

O preço são 10 amostras boas em 27, e é o preço certo aqui: isto **semeia** uma classe, e uma
amostra errada na semente ensina a letra errada sem ninguém para pegá-la depois — a classe é
nova, não há com o que comparar. Volume quem dá é a fonte.

### A semente de fonte, e um `has_glyph` que mentiu

Para a letra que os livros não têm — `Ń` não aparece **uma vez** nos seis PDFs —, o glifo é
desenhado de faces serifadas do sistema, em três corpos, com a dedução da F93 tirando o que
sair igual. Quinze faces cobrem as 16 letras.

A primeira ideia foi melhor e não funcionou: extrair a fonte embutida do próprio livro, para
a semente ter a forma que aquele livro imprime. `fitz.Font.has_glyph` respondeu **sim** para
as 16 letras nas duas faces embutidas do Dvoretsky — e a renderização saiu vazia até para o
`a`. Por isso `faces_disponiveis` confere por **tinta**, com letras de controle: uma face que
devolve `.notdef` entrega um retângulo, e um retângulo promovido para a classe de `ń` ensina
que `ń` é um retângulo.

### O resultado

737 amostras em 16 classes: `Ń ń Š š Ž ž Č č Ć ć Å å Ş ş Ø ø`. Dezessete vieram de livro
(todas do Dvoretsky, todas conferidas a olho), 720 de fonte. As 108 do Aagaard, as 103 do
Yusupov Complete e as 28 do Yusupov corrigido ficaram de fora, nomeadas no relatório.

**Nada foi direto para `training_data`**: sai em `revisao_letras/`, com folha de contato por
classe, e entra na base pela promoção da F2.7. É a mesma propriedade de segurança, e aqui ela
pagou duas vezes — foi a folha que pegou os 54 reis e depois os 31 borrões.

### A procedência atravessa a promoção

O `learner.learn` renomeava toda amostra para UUID, e depois de promovida a semente ficava
indistinguível da amostra de livro. Não é cosmético: a semente existe para a classe existir
enquanto nenhum livro traz a letra, e quando um trouxer é ela que se troca — sem o nome não
há como achar qual, numa base de 130 mil arquivos. `learn` passou a aceitar o nome de origem,
higienizado (`_nome_de_amostra`: só-ASCII, sem separador de caminho, colisão vira UUID). É a
mesma lição que o `dataset_check._nome_livre` já tinha aprendido do outro lado.

### O que fica em aberto

**A semente não está medida de ponta a ponta.** Que ela faz a classe existir é certo; se ela
*ajuda* o modelo a ler a letra no livro impresso, só o próximo treino diz — o
`relatorio_treino.txt` traz acurácia por classe. É a verificação que esta fase não podia
fazer sem sobrescrever o modelo calibrado.

Cobertura: `tests/test_f94_letras.py`, 18 testes. Reproduzir:
`python importar_letras.py --faltantes "PDF/*/*.pdf"` e
`python importar_letras.py --pdf "PDF/*/*.pdf" --letras "ŃńŠšŽžČčĆćÅåŞşØø" --destino revisao_letras`.

## F95 — O diagrama dentro do painel, e o que está impresso em volta dele — CONCLUÍDA

A pergunta que abriu a fase foi "onde a leitura de diagramas ainda erra?", e a resposta
não veio de ler o código: veio de passar o comando **Ler posição dos diagramas** por 21
páginas de 5 livros e comparar com o que está impresso nelas. O gabarito ficou em
`tests/dados/paginas_com_diagrama.txt`, escrito à mão, e o instrumento em
`medir_rotulos.py`.

| | antes | depois |
|---|---:|---:|
| diagramas achados | 48 de 50 | **50 de 50** |
| tabuleiros inventados | 0 | **0** |
| decisões "há coordenadas?" certas | — | **50 de 50** |
| títulos lidos | — | **29** (de 30 achados) |
| custo da localização, por página | 0,00 s | 0,03 s (máximo 0,17) |

### Os dois que faltavam eram dois que ninguém podia achar

A premissa do módulo desde a F7.1 é que "o tabuleiro sai como **um** contorno só", porque
tem moldura fechada e o `findContours` roda com `RETR_EXTERNAL`. Ela vale enquanto o
tabuleiro **for** contorno externo, e a página 199 do Yusupov mostra quando ele não é: os
dois diagramas do capítulo estão dentro de um painel sombreado que atravessa a coluna
inteira. O painel é o contorno; os tabuleiros são filhos dele e nunca chegam à lista de
boxes. Medido: 3.745 contornos na página, o maior deles o painel (649x1441, proporção
2,22), e **nenhum** quadrado grande. O comando respondia "nenhum diagrama encontrado", e o
texto ainda mandava conferir a borda da página.

A segunda passada refaz os contornos com `RETR_LIST` — que devolve os de dentro também — e
peneira com **duas provas independentes**, porque nenhuma das duas basta sozinha:

| contorno da página 199 | lado | preenchimento | xadrez |
|---|---:|---:|---:|
| **tabuleiro de cima** | 589x587 | **0,96** | 30,9 |
| escada das casas escuras | 570x558 | 0,21 | **42,3** |
| escada, outro recorte | 555x568 | 0,20 | 28,3 |
| **tabuleiro de baixo** | 584x591 | **0,96** | 32,2 |
| escada das casas escuras | 567x566 | 0,20 | 48,4 |

O xadrez sozinho escolheria a escada, que pontua **mais** que o tabuleiro inteiro — ela é
um recorte deslocado do mesmo tabuleiro, e o alinhamento dela com as casas é acidental.
O preenchimento sozinho deixaria passar qualquer quadrado preto. Juntos, os dois
tabuleiros passam e os dez contornos internos caem.

### A prova do xadrez, e por que ela é a peneira certa

`pontuacao_de_tabuleiro` é a diferença média de tinta entre as 32 casas ímpares e as 32
pares, medida **no anel de fundo de cada casa** — a peça mora no meio, e incluí-la
apagaria a diferença que se quer medir. Medida em 49 tabuleiros e 5 recortes de texto do
mesmo tamanho:

| origem | menor | maior |
|---|---:|---:|
| tabuleiro hachurado (Nunn) | 19,7 | 38,3 |
| tabuleiro hachurado (Dvoretsky) | 20,2 | 22,8 |
| tabuleiro chapado (Yusupov) | 36,0 | 46,2 |
| tabuleiro chapado (Aagaard) | 32,9 | 44,2 |
| tabuleiro chapado (Darcy Lima) | 92,2 | 124,3 |
| **recorte de texto** | **-1,1** | **3,1** |

O vão entre 3,1 e 19,7 é de seis vezes. **O piso não foi afinado, foi posto no meio de um
vão** — que é a diferença entre um limiar que se justifica e um que se ajusta.

Ela mede tom, e não binarização, e isso não é detalhe: a casa escura destes livros tem
dois desenhos — cinza chapado num livro, hachura diagonal noutro —, e binarizada a
hachurada fica branca na moda. É o mesmo motivo pelo qual a F7.1 lê resíduo e não tom
absoluto, aplicado à localização.

### A ordem estava errada duas vezes

`localizar` ordenava por `(y1, x1)`. Na página 221 do Yusupov, que tem seis diagramas em
duas colunas, o da direita começa em y=358 e o da esquerda em y=359 — **a primeira fila
saía invertida**, e as outras duas certas por acaso. Quem via "Diagrama 1 de 6" via o
`Ex. 22-4`.

Estável, ordenar por fila ainda não é a ordem de leitura de uma página de duas colunas —
é a mesma armadilha que a F61 documenta para o texto. E aqui a fase pôde **conferir** em
vez de supor, porque passou a ler os títulos: nas duas páginas de seis diagramas do
material, `Ex. 22-1` a `Ex. 22-6` no Yusupov e os círculos de 1 a 6 no Aagaard, a
numeração desce a coluna da esquerda antes de começar a da direita. Por fila sairia
1, 4, 2, 5, 3, 6.

Coluna a coluna cobre também a fila única: dois diagramas lado a lado são duas colunas de
um, e saem da esquerda para a direita como sairiam por fila. Não há layout que peça a
outra ordem.

### As coordenadas, e a escolha que não existia

**A queixa que abriu esta metade:** para gerar o DOCX ou o EPUB, poder escolher se as
coordenadas entram. A escolha existia desde a F58 — `coordenadas=True|False` — mas era
para o livro inteiro e cega: nada no programa sabia o que o livro trazia. Um mesmo volume
imprime o exercício com `a`-`h` e o diagrama do meio da prosa sem.

`ler_rotulos` responde isso, e **a prova é geométrica, não é leitura**: rótulo de casa tem
uma marca por raia, e são oito raias. Contando raias ocupadas nas quatro bandas de 20
tabuleiros:

| livro | esquerda | abaixo | imprime coordenadas? |
|---|---:|---:|---|
| Yusupov (Chess Evolution) | 8 | 8 | sim |
| Dvoretsky | 8 | 8 | sim |
| Nunn | 0 | 0 | não |
| Aagaard | 0–4 | 0 | não |
| Darcy Lima | 0–3 | 0–2 | não |

Os dois grupos não encostam. O corte fica em 7 de 8, que deixa passar uma raia comida pelo
recorte sem abrir a porta para a prosa que corre ao lado do tabuleiro. Nas 50 leituras do
gabarito, **50 decisões certas** — e nenhuma delas precisa do modelo de texto, o que
importa: a exportação decide "como no livro" mesmo antes de carregar a rede.

`livro.extrair` passou a aceitar um terceiro valor, `COMO_NO_LIVRO`, e ele decide **por
diagrama**. O padrão da API continua `False`, para quem chamava não ter o livro mudando
debaixo de si; a janela de exportação é que passou a oferecer a terceira resposta primeiro.

### O que os rótulos dizem além de existirem

Lidos, eles respondem a única pergunta do diagrama que **nada mais no diagrama responde**:
para que lado ele está virado. `ler` sempre supôs brancas embaixo, e um diagrama impresso
do lado das pretas saía com o FEN girado 180° — plausível, legal, e errado.

**A paridade das casas não serve, e é o engano tentador.** Girar o tabuleiro 180° troca
fila e coluna ao mesmo tempo, e a soma dos índices conserva a paridade: a casa de baixo à
esquerda é escura nas duas orientações (`a1` numa, `h8` na outra). O único sinal impresso
que distingue as duas é o rótulo.

A régua é conservadora porque errar aqui estraga um diagrama que estava certo. Medido nos
rótulos lidos com o modelo de 105 classes:

| livro | letras lidas | contra `a`-`h` | contra `h`-`a` |
|---|---|---:|---:|
| Yusupov | `abcdefgh` | 8 | 0 |
| Dvoretsky | `abCdefOh` | 6 | 0 |

| livro | números lidos | contra `8`-`1` | contra `1`-`8` |
|---|---|---:|---:|
| Yusupov | `87654321` | 8 | 0 |
| Dvoretsky | `37))43)1` | 4 | 0 |

O Dvoretsky é o caso difícil — os algarismos dele estão numa fonte que o modelo nunca viu
— e ainda assim a distância entre as duas hipóteses é de 4 a 6. Exige-se 4 acertos e 2 de
vantagem; abaixo disso a resposta é `None`, que **não** é "brancas embaixo".

O FEN sai sempre o da posição, com as casas giradas de volta. Quem se vira é o desenho:
`render_diagrama.desenhar(orientacao=...)` e, no modo de fonte embutida, os rótulos em
texto — que eram `a`-`h` fixos e agora saem de `render_diagrama.rotulos`, um lugar só para
os dois usos.

### O título, e o lado que ninguém tinha olhado

A F60 trouxe de volta o cabeçalho do diagrama, e a F67 o fez virar texto. As duas
procuraram **acima** da borda, porque é ali que o Yusupov imprime. O Nunn imprime embaixo:
o número do diagrama à esquerda e a avaliação da posição à direita, na mesma linha. Nada
no programa olhava para lá — a legenda saía como parágrafo solto, sem nada dizendo de que
diagrama ela era, e num livro de finais ela **é** o índice.

`ler_titulo` olha os dois lados, e a assimetria que ele precisou aprender é de um pixel de
teoria e dois de medição: **a borda que conta é a que olha para o tabuleiro**. Acima é o
pé da caixa — a maiúscula sobe acima da banda e a minúscula não, e medir pelo topo fazia
`Diagram` sair `agram` (a F60 já documentava isso). Abaixo é o topo, pelo motivo
espelhado: o `437` do Nunn nasce a 1,29 escalas do tabuleiro e desce até 2,3, e medido
pelo pé ele não existia.

Lidos, 29 títulos em 50 diagramas: `Diagram 1-4`, `Ex. 22-1`, `437 /`, `Diagrama A`. E as
caixas que o título consome voltam com ele, para quem exporta tirá-las do texto da página
— a legenda de baixo começa dentro da margem de exclusão e **acaba fora**, então ela chega
ao texto e sairia duas vezes no livro.

### O que esta fase NÃO resolve, e está medido

- **A banda é a margem de exclusão, e legenda mais longe que ela continua sendo prosa.**
  É o invariante que dá segurança ao resto: o que a margem já exclui do texto pode virar
  título sem custo nenhum, porque não vai sair em lugar nenhum. Além de 1,4 escalas a
  conta se inverte. Medido: a legenda do Nunn está a 1,29 escalas na página 266 e a 1,76
  na 89 — a primeira vira legenda, a segunda continua parágrafo. E não há régua de
  distância que separe as duas: na página 80 do Darcy Lima a **prosa** começa a 1,40.
- **Título achado não é título lido.** Um caractere fraco derruba a linha inteira, que é a
  regra da F67 e continua sendo a certa — um buraco no meio de `Ex. 22-1` é o número do
  exercício. Dos 30 achados, 29 saíram com texto.
- **Um diagrama de fato invertido não foi medido**, porque o material não tem nenhum: os
  cinco livros imprimem tudo do lado das brancas. O que está medido é que a régua **não
  dispara** em 50 diagramas certos, e que ela reconhece o rótulo invertido montado à mão
  (`tests/test_f95_rotulos_e_titulo.py`).
- **A localização continua sem tolerar diagrama cortado pela borda da página.** Nenhuma
  das duas passadas o acha, e o gabarito não tem esse caso.

Cobertura: `tests/test_f95_rotulos_e_titulo.py`, 26 testes, mais 6 em
`tests/test_f26_livro.py`. Reproduzir: `python medir_rotulos.py` e
`python medir_rotulos.py --sem-aninhados`.

## F96 — O detector vindo de fora, e o laço que travava a página — CONCLUÍDA: o de casa ganha, o de fora fica com a página de trama, e o merge cai 4×

A pergunta que abriu a fase veio de fora: uma skill de outro projeto (o visualizador do
ChessVisionOFF) traz um detector de tabuleiro que não depende de nada do pipeline de texto,
e a pergunta era se ele serve aqui. Serve para uma coisa e não serve para a outra, e as
duas estão medidas.

| gabarito da F95, 21 páginas, 50 diagramas | achados | não achados | inventados |
|---|---:|---:|---:|
| **`diagrama.localizar` (F95, o de hoje)** | **50** | **0** | **0** |
| detector portado | 51 | 0 | **1** |
| detector portado + peneira da F95 | 47 | **3** | 0 |

O de casa ganha nas duas colunas que importam, e **fica**. O que a fase deixa no repositório
é `core/deteccao_de_tabuleiro.py` com 13 testes, por dois motivos que a tabela não mede — a
página que o pipeline de texto recusa e o diagrama torto, ambos adiante.

**E o que ela conserta é outra coisa, achada no caminho**: medir quem paga a localização
levou ao `merge_vertical_boxes`, que sozinho respondia pelas páginas de quatro minutos. Com
um índice espacial ele cai de 250,81 s para 62,77 s na pior delas, com saída idêntica caixa
a caixa. Está adiante, em "O laço que travava a página".

### O que a fase foi procurar: quem paga a localização

`localizar` custa 0,03 s por página (mediana do gabarito, máximo 0,14). Esse número é
verdadeiro e engana, porque ele exige `boxes_antes_do_descarte` antes de si — binarizar,
tirar trama, aplicar negativo, empilhar vertical e fundir pingos. Medido em 24 páginas de
cada um de cinco livros:

| livro | mediana | pior página |
|---|---:|---:|
| Dvoretsky | 0,50 s | 0,71 s |
| Nunn | 0,80 s | 1,07 s |
| Darcy Lima | 0,97 s | 1,27 s |
| Aagaard | 1,01 s | 1,64 s |
| **Yusupov** | 0,66 s | **256,54 s** |

A última coluna não é ruído de medição, e o estágio que a produz é um só:

| página do Yusupov | contornos | `merge_vertical_boxes` |
|---|---:|---:|
| 198 | 11.436 | 11,59 s |
| 134 | 38.945 | 106,76 s |
| **96** | **85.883** | **275,35 s** |

Todos os outros estágios daquelas páginas somam menos de 1 s. O
`MAX_CONTORNOS_DE_TEXTO = 20000` existe exatamente para isto e o `medir_rotulos` o passa —
**quem não passa é `extrair_diagramas`**, que chama `generate_boxes_opencv` sem teto. A
leitura de diagramas da UI congela por 4 minutos nessa página, e o docstring do
`boxes_antes_do_descarte` já culpava o caminho errado (`dividir_linhas_coladas`): medido
estágio a estágio, o `dividir_linhas_coladas` não chega a ser o problema, o merge é.

E armar a guarda não devolve o diagrama: ela devolve **lista vazia**. Numa página que o
pipeline de texto recusa, hoje não há como achar tabuleiro nenhum.

### O detector portado, e o que ele custa

Ele procura o tabuleiro pelo que ele é — quadrilátero grande, quase quadrado, com xadrez
dentro — a partir de `adaptiveThreshold` + `findContours(RETR_LIST)`, sem caractere nenhum
no caminho. Nas mesmas 24 páginas por livro: **0,26 a 0,48 s por página, pior caso 0,82 s**,
sem uma única página fora da faixa.

No gabarito ele fica em 0,21 s (máximo 0,62) contra 0,03 s do `localizar` — **sete vezes mais
caro na ponta**, e é assim que tem de ser lido: o que ele economiza é o preparo, não a
localização.

### Contagem não é acerto — o que a página 80 do Darcy Lima ensinou

Na primeira comparação o detector portado "acertou" 2 de 2 nessa página. As caixas dizem
outra coisa:

| | diagrama de cima | diagrama de baixo |
|---|---|---|
| `localizar` (F95) | 840x781 | 843x817 |
| detector portado | **1212x1191** | **1146x1134** |

Ele pegou o tabuleiro **mais a moldura de anotação em volta** — 44% a mais de lado. O recorte
sai com a grade 8x8 fora de registro, e quem diz isso sem precisar olhar é a prova de xadrez
da F95: `pontuacao_de_tabuleiro` dá **-6,43** e **2,35** nos dois recortes, num livro cujos
tabuleiros a F95 mediu entre **92,2 e 124,3**. É o vão de seis vezes da F95 sendo usado como
foi feito para ser.

Ou seja: a contagem batia e o recorte não servia. **Uma medição que conta caixas mede o
detector pela metade** — e foi por isso que a peneira entrou como opção em vez de ficar de
fora.

### A peneira da F95 conserta um caso e quebra dois

`piso_do_xadrez` liga `pontuacao_de_tabuleiro` sobre o recorte endireitado. Onde os três
caminhos divergem:

| página | gabarito | F95 | portado | portado + peneira |
|---|---:|---:|---:|---:|
| Chess Evolution 199 | 2 | 2 | **3** | 2 |
| Darcy Lima 80 | 2 | 2 | 2 (recorte errado) | **0** |
| Darcy Lima 112 | 3 | 3 | 3 | **2** |

*(as outras 18 páginas do gabarito batem nos quatro)*

A peneira mata o falso positivo da página do painel — a mesma página 199 que a F95 teve de
resolver — e mata junto os recortes largos do Darcy Lima, que ela está certa em recusar: o
que ela recusa ali **não é tabuleiro**, é tabuleiro com moldura. O defeito não é da peneira,
é do enquadramento do detector, e é onde ele teria de melhorar para virar substituto.

### Os quatro cantos, que é o que ele traz de novo

`localizar` devolve o retângulo envolvente do contorno e `ler` recorta esse retângulo. O
detector portado guarda os quatro cantos e desentorta por homografia. A pergunta é a partir
de quando isso paga; medido num tabuleiro sintético, contando quantas das 64 casas ainda
caem na cor que deveriam:

| giro | recorte pelo bbox | recorte pelos cantos |
|---:|---:|---:|
| 1° a 3° | 64 | 64 |
| 4° | 62 | **64** |
| 5° | 57 | **64** |
| 6° | 46 | **64** |
| 10° | 23 | **64** |

**Até 3° o bbox serve** e a homografia não paga nada — que é o caso de todo o material medido
até aqui, PDF nativo ou digitalização bem-comportada. A partir de 4° ela é a diferença entre
ler o diagrama e ler metade de duas casas por casa. Está guardada porque o acervo não é só
este, não porque alguma página de hoje precise dela.

### O que fica, e o que não muda

- **Fica** `core/deteccao_de_tabuleiro.py`, com `detectar`, `localizar` (mesma forma de
  saída de `diagrama.localizar`, para poder trocar um pelo outro) e `endireitar`.
- **Fica** `medir_rotulos.py --por-contorno [--piso-xadrez 12.0]`, que é como esta tabela se
  refaz.
- **A ordem de leitura é a de `diagrama.ordem_de_leitura`**, importada, não reimplementada:
  duas ordens fazem o "diagrama 2" da tela não ser o `[Diagram "2"]` da exportação, que é
  metade do que a F95 corrigiu.
- **No caminho de produção, `localizar` continua sendo quem responde** — é quem acerta 50
  de 50. O detector ganhou uma porta estreita ao lado dele, e não o lugar dele: só a página
  que chega sem contorno nenhum passa por ela. Ver "A porta", adiante.

### O laço que travava a página, e o teto que não é a saída

`merge_vertical_boxes` era o único estágio que explicava as páginas de minutos — todos os
outros somam menos de 1 s nelas. O laço de dentro varria a página inteira para cada caixa e
**cada fusão o reiniciava**, e é a segunda metade que pesa: numa página de trama, 38.964
caixas viram 2.749, ou seja ~36 mil reinícios.

As duas condições de merge são **locais**. Nenhuma aceita distância vertical acima de
`folga_maxima`, e a prova horizontal exige sobreposição em `x` — então o candidato tem de
tocar um retângulo em volta da caixa que está crescendo. Um índice por células devolve
exatamente quem toca esse retângulo, **em ordem de índice**, que é a ordem em que o laço de
antes os encontraria: mesma escolha, mesma saída, sem olhar as outras 85 mil.

| página | caixas | saída | antes | depois |
|---|---:|---:|---:|---:|
| 198 | 11.457 | 3.745 | 9,70 s | **1,96 s** |
| 134 | 38.964 | 2.749 | 95,74 s | **21,75 s** |
| 96 | 85.903 | 2.252 | 250,81 s | **62,77 s** |

Saída idêntica, caixa a caixa, nas três. E **não fica linear**: o que o índice tira é o custo
de olhar a página inteira, e o que sobra é o de olhar a mancha — que numa página de trama é
grande.

**E o índice tem um caso em que ele é o problema.** Uma caixa do tamanho da página — a tarja
do `negativo`, a moldura de uma tabela — faz o retângulo de busca cobrir tudo, e aí percorrer
células custa mais que percorrer caixas: medido, 3.000 caixas mais **uma** do tamanho da
página saem de 0,03 s para **10,52 s**. Foi a suíte que pegou, ao dobrar de tempo.

Por isso a escolha é **por busca, e não por página**: quando as células do retângulo passam
de quantas caixas ainda restam, quem roda é a varredura direta. Com a guarda, o mesmo caso
fica em **0,20 s** — abaixo do que era antes do índice, porque a varredura direta ganhou a
parada antecipada por `y1` que a lista ordenada permite. A suíte inteira caiu de 226,94 s
para 111,60 s.

**O teto de contornos não é a outra saída, e a página 96 é o contraexemplo.** O
`MAX_CONTORNOS_DE_TEXTO` diz "acima disto a página não é de texto", e a 96 dá 85.903
contornos sendo uma página de texto comum: duas colunas de prosa, um diagrama e um painel de
sumário. Quem produz os contornos é a **trama do painel**, não a ausência de texto. Armar o
teto ali troca 63 s de espera por perder a página inteira — o texto e o diagrama junto.

**A não ser que perder o caminho não seja perder a página**, e é o que o detector desta fase
permite: ele responde nessa página em 0,76 s, e acha o diagrama. Com isso o teto deixa de ser
desistência e vira desvio — é a seção seguinte.

### A porta: o detector entra onde o `localizar` não tem do que se alimentar

O comando **Ler posição dos diagramas** passou a ter dois caminhos, e quem escolhe é o
`MAX_CONTORNOS_DE_TEXTO` — que deixou de significar "desista desta página" e passou a
significar "esta página se resolve pelo outro lado".

| página do Yusupov | contornos | antes | depois |
|---|---:|---|---|
| 11 | 1.108 | 3 diagramas, 0,43 s | 3 diagramas, 0,41 s |
| 41 | 494 | 6 diagramas, 0,44 s | 6 diagramas, 0,46 s |
| 199 | 3.745 | 2 diagramas, 2,46 s | 2 diagramas, 2,44 s |
| 222 | 574 | 6 diagramas, 0,49 s | 6 diagramas, 0,44 s |
| **97** | **85.903** | 2 diagramas, **49,64 s** | **1 diagrama, 1,44 s** |
| **135** | **38.964** | 1 diagrama, **19,72 s** | 1 diagrama, **1,46 s** |

Abaixo do teto **nada muda** — mesma contagem, mesmo tempo, mesmo caminho. As duas páginas
que trocam de caminho são as de trama, e as duas melhoram nos dois eixos.

**A 97 melhora também no que acha.** O caminho de hoje devolvia dois diagramas ali, e o
primeiro é o ornamento do "CHAPTER 10" no alto da página — 188x169 px, prova de xadrez
**-1,05**. O segundo é o diagrama de verdade, mas recortado em 588x615, com a legenda de cima
dentro. O detector devolve um só, em 572x573: quadrado, e com a grade em registro.

### A peneira da F95 vai junto, e é ela que fecha a porta

Sem ela a página 135 ganha um "diagrama" de 1.521x1.571 px que é o cabeçalho do capítulo mais
a prosa, e que ainda sai pela borda de cima da página (`y1 = -281`). Medido nas quatro páginas
de trama do livro, `pontuacao_de_tabuleiro` sobre o recorte endireitado:

| | menor | maior |
|---|---:|---:|
| os 7 tabuleiros de verdade | **40,89** | 55,28 |
| os 2 retângulos inventados | 0,10 | **1,53** |

Vinte e seis vezes de vão, e o piso da F95 (12,0) cai no meio dele. O mesmo piso que, aplicado
ao detector **em todas as páginas**, derrubava 3 diagramas bons do Darcy Lima — a diferença é
o outro prato da balança: numa página que chega sem caixa nenhuma, o que se perde ao recusar
é nada, e o que se ganha ao aceitar errado é um FEN errado na tela.

**O gabarito não se mexeu**: 50 de 50, 0 inventados. Nenhuma das 21 páginas passa do teto, e a
porta não abre onde há contorno. O que mudou lá foi o custo do preparo, pelo índice do merge —
de mediana 0,52 s e máximo 11,51 s para **0,19 s e 1,91 s**.

### O que isto abre

- **A porta abre pela contagem de contornos, que é o sinal barato.** Fica em aberto o caso
  que ela não cobre: a página que não passa do teto e mesmo assim custa caro. O gatilho por
  tempo gasto pega esse, e exige poder interromper o estágio no meio.
- **O enquadramento do detector portado** é o que o separa de ser substituto: enquanto ele
  pegar a moldura junto num livro, a peneira que o corrige derruba diagrama bom noutro.
- **O merge ainda cresce mais que linear** na mancha de trama. O índice tirou 4×; o que falta
  é não reexaminar a mesma vizinhança a cada fusão.

Cobertura: `tests/test_f96_deteccao_de_tabuleiro.py`, 16 testes — três deles pela porta do
`ler_pagina` —, mais 7 em `tests/test_f311_merge.py`, quatro dos quais comparam o merge caixa
a caixa com uma transcrição do laço original. Nenhum precisa de material.
Reproduzir: `python medir_rotulos.py`, `python medir_rotulos.py --por-contorno` e
`python medir_rotulos.py --por-contorno --piso-xadrez 12.0`.

## F97 — A moldura, o corpo em pontos, e o vão entre as filas — CONCLUÍDA

A queixa veio da primeira conversão inteira de um livro (Aagaard, *A Matter of Endgame
Technique*): o arquivo sai bom, mas o diagrama sai **do tamanho que o exportador achou**, e
sem escolha de moldura. Duas coisas que quem monta o livro decide, e que o programa decidia
por ele — uma delas escondida numa constante em centímetros.

### O tamanho: a casa é o quadrado do tipo

A fonte de diagrama mapeia caractere → casa inteira, e a casa é o quadrado do em. Então o
corpo em pontos **é** o lado da casa, e o tabuleiro mede oito vezes isso — que é o número
com que o tipógrafo de livro de xadrez trabalha. O DOCX derivava esse corpo de uma largura
fixa de 9 cm:

| escolha | corpo por casa | lado do tabuleiro |
|---|---:|---:|
| `largura_figura_cm = 9.0` (antes) | 31,9 pt | 9,0 cm |
| `corpo_pt = 16` (agora, padrão) | 16,0 pt | 4,5 cm |

9 cm é diagrama de página inteira. Num livro de finais, com dois ou três diagramas por
página, ele empurrava a prosa para a página seguinte — e não havia como dizer outro número
sem editar o código.

**O corpo vale nos dois modos e nos dois formatos, e é isso que o torna útil.** No modo de
fonte ele é o corpo da letra; no de imagem, é o que dá a largura da figura. A ponte é a
`Figura.casas_de_largura`, que cada figura traz consigo: o desenho com moldura simples tem
8,08 casas de largura, o recorte justo tem 8, e o cabeçalho reamostrado tem o que a regra de
três disser. Multiplicado pelo corpo, sai a medida na página — e **o diagrama que o porteiro
desenhou e o que ele mandou para o recorte saem do mesmo tamanho no mesmo livro**, que é a
mesma disciplina da F58 aplicada ao tamanho em vez de ao rótulo.

### O vão entre as filas, que é o defeito que se vê antes de qualquer outro

Pedido junto, e é o que sustenta o resto: o tabuleiro só é quadrado se a linha medir
exatamente uma casa. O DOCX já escrevia `w:lineRule="exact"` desde a F59 — o que faltava era
garantir que o número da entrelinha e o do corpo fossem o **mesmo**:

| campo | unidade | 16 pt |
|---|---|---:|
| `w:sz` (corpo) | meios-pontos | 32 |
| `w:line` (entrelinha) | twips | 320 |

Um corpo de 16,3 pt sairia como 16,5 no primeiro e 16,3 no segundo: 0,2 pt de vão por fila,
oito filas, meio milímetro de fenda no pé do tabuleiro. Daí o `PASSO_DO_CORPO_PT = 0.5` —
o corpo é arredondado ao meio ponto na entrada, e os dois campos passam a ser exatos.

No EPUB o mesmo problema tem outra causa: vários leitores impõem entrelinha de leitura ao
livro inteiro, por preferência do usuário. A folha ganhou o **único `!important` do
arquivo**, e ele vale só para as oito linhas do tabuleiro (`div.diagrama p`). No corpo do
texto a preferência do leitor continua mandando.

### A moldura: três feitios, e o filete mora fora do tabuleiro

`sem`, `simples` e `dupla`. A `desenhar` tinha um booleano, e a moldura era um retângulo só;
agora a geometria sai da `filetes()`, que devolve `[(recuo do caminho, espessura)]` e a
margem total. Medido no mesmo diagrama, a 352 px de tabuleiro:

| moldura | lado do PNG | arquivo |
|---|---:|---:|
| `sem` | 352 px | 5.386 B |
| `simples` | 356 px | 5.915 B |
| `dupla` | 361 px | 6.131 B |

O tabuleiro é o mesmo nos três, e é o requisito: o filete que invadisse a casa deslocaria a
grade de quem relê o desenho — a suíte, o porteiro, o `diagrama.ler` — que divide a imagem
em 8×8 **iguais**.

No modo de imagem a moldura já vem desenhada dentro do PNG. No modo de fonte ela é do
formato: `border: … double` na CSS do EPUB, e no DOCX **uma tabela de uma célula**. Não é
borda de parágrafo, e a razão é geométrica: a borda de parágrafo do Word corre de margem a
margem da coluna de texto — ela emolduraria a página, não o diagrama, que é estreito e
centrado. A borda vai no `w:tcPr` e não no `w:tblPr` porque a ordem dos filhos do `tblPr` é
fixa no esquema e o `python-docx` já escreve o `tblLook` no fim dele; acrescentar depois dá
um arquivo que o Word abre reclamando.

**A tabela trouxe um defeito junto, e ele estava a um passo de sair no arquivo**: duas
`<w:tbl>` coladas no XML o Word abre como **uma** tabela de duas filas. Numa página de
exercícios — dois diagramas seguidos, sem prosa entre eles — os dois cairiam dentro da
mesma moldura, um por cima do outro. Um parágrafo de 1 pt de entrelinha exata entre as
caixas separa, e resolve de quebra o outro caso em que o Word reclama, que é o documento
terminar em tabela.

### A pergunta: uma caixa, e não duas

As outras escolhas da exportação saem em `messagebox` encadeados, e é o que elas pedem — são
sim-ou-não e cada uma se explica sozinha. Estas duas não: uma tem três respostas, a outra é
um número, e **as duas mexem no mesmo desenho**. O `ui/dialogo_moldura.py` põe as duas na
mesma caixa, com uma amostra do tabuleiro que muda enquanto se escolhe a moldura e a medida
em centímetros ao lado do corpo em pontos — 16 pt não parece um tamanho até virar 4,5 cm.

### O que ficou de fora

- **PDF.** O pedido já o previa ("e futuramente pdf"), e não há exportador de PDF: o
  `corpo_pt` e a `moldura` atravessam `livro.extrair` e `exportar.exportar` como opções do
  documento, não do formato, e o dia em que ele existir não precisa de nova pergunta.
- **Moldura por glifo de fonte.** A Chess Merida traz caracteres de moldura, e a
  SkakNew-Diagram não — medido no `cmap`: 46 codepoints, e nenhum deles é filete. A moldura
  daqui é desenhada (PNG) ou é do formato (CSS, `w:tcBorders`), e por isso vale para
  qualquer fonte de diagrama, inclusive as que ainda não estão no repositório.

## F98 — A segunda fonte de diagrama, e as três suposições que ela derrubou — CONCLUÍDA

Até aqui "a fonte" era uma só, e por isso várias suposições sobre ela nunca precisaram ser
ditas. A Chess Merida — a fonte tradicional de diagrama, a das figuras que a maioria dos
livros imprime — disse todas de uma vez, e as três falham **em silêncio**.

### 1. O cmap: o `fitz` não enxergava um glifo sequer

A `MERIFONT.TTF` é de 1998 e traz duas tabelas de cmap: uma Mac Roman (1,0) e uma **Symbol**
(3,0), esta com os caracteres em `0xF020`–`0xF0EF` em vez de `0x20`–`0xEF`. Era o jeito de
1998 de dizer "esta fonte não tem letras, tem desenhos", e o Word ainda o entende — o
Wingdings funciona assim até hoje.

Medido: `fitz.Font(fontfile="fonts/MERIFONT.TTF")` varrido pelos **65.536 codepoints** do
plano básico encontra **zero** glifos, e `insert_text` desenha um `·` no lugar de cada peça
sem levantar erro nenhum. É exatamente o modo de falha da §4.2 da SPEC, e a checagem de
cobertura do `render_diagrama` — que existe desde a F58 justamente para isso — o pegaria; mas
pegar não é resolver.

Daí o `gerar_fonte_de_diagrama.py`, no molde do `gerar_fonte_de_simbolos.py` da F62: roda à
mão, o produto é versionado, e o `fontTools` fica sendo dependência de desenvolvimento. Ele
acrescenta as tabelas (3,1) e (0,3) construídas a partir da de símbolo, **tira** a (3,0) — se
ela ficasse, o Word continuaria tratando a fonte como de símbolo e ignorando a nova — e
renomeia a família. Os 97 contornos não são tocados, e é isso que o `--conferir` mede: se um
dia o remendo mexer num desenho, a contagem de glifos acusa.

A licença permite: a Chess Merida é freeware de Armando Hernández Marroquín (1998), e a
redistribuição em `github.com/vasiliyaltunin/chess-merida-font` é MPL-2.0, que autoriza
modificar.

### 2. A família: a chave do mapa **é** o nome de dentro do arquivo

Quem embute a fonte no DOCX escreve `<w:font w:name="…">` com a chave do mapa e pede a mesma
chave no run. A `SkakNew-Diagram` se chama `SkakNew-Diagram` por dentro, então isso nunca foi
uma regra — era uma coincidência. A Merida saiu do primeiro remendo como `Chess Merida
Diagram`, e o Word não liga uma coisa na outra: o tabuleiro sairia na fonte do usuário, sem
erro, e só se veria abrindo o arquivo.

Hoje é regra, e há teste sobre **toda** fonte do mapa — não só sobre esta.

### 3. A casa vazia: a da Merida é o espaço, e o Word não conta espaço para centrar

| | casa clara vazia | casa escura vazia |
|---|---|---|
| SkakNew-Diagram | `0` | `Z` |
| Chess Merida | **espaço** | `+` |

As oito filas do modo de fonte eram parágrafos **centrados**, e isso só funcionava porque
nenhuma fila da SkakNew começa ou termina em espaço. O Word ignora o espaço do fim da linha
ao centrar: a fila `"+ + +o+ "` seria medida com sete casas e a `" + WlV +"` com oito, e o
tabuleiro sairia em escada, meia casa por fila.

O conserto é a caixa da F97 passar a existir **sempre** — com as bordas declaradas `nil`
quando não há moldura —, com a largura escrita três vezes (`tblW`, `w:gridCol`, `tcW`) e
`tblLayout` fixo, e as filas alinhadas à esquerda dentro dela. Numa célula da largura exata
do tabuleiro o espaço deixa de ter voz no alinhamento. De brinde vem o `w:cantSplit`, que
resolve no DOCX o que o `page-break-inside: avoid` resolve no EPUB.

### O mapa, e como ele foi conferido

Ele saiu do mapa de teclado publicado com a fonte (`fonts/LEEME__D.TXT`, seção PIEZAS) e da
tabela em `fonts/Merida.jpg` — minúscula é casa clara, maiúscula é escura; brancas
`p n b r q k`, pretas `o m v t w l`. As quatro provas do `medir_fonte_diagrama.py`, que já
existiam desde a F58 e nunca tinham sido usadas numa fonte nova:

| prova | Chess Merida |
|---|---|
| fechamento | 24 combinações e as duas casas vazias, sem sobra nem falta |
| avanço | todo caractere do mapa anda 1 em (2048 unidades) |
| tinta na quina | clara 0,000; escura 0,293 — as faixas não se tocam |
| ida e volta (as redes da F7.4/F7.5) | **100,00%** de casa certa em 2.560 casas, 40 de 40 tabuleiros |

A terceira merece nota: a casa escura da SkakNew é quase sólida, e a da Merida é hachura
fina — 29% de tinta na quina. A prova mede o **vão** entre as duas faixas, e não um limiar
fixo, e é por isso que ela passou numa fonte que não existia quando foi escrita.

### A fonte fica escolhível

A lista do diálogo sai do `fontes_de_diagrama.json`, e não de uma lista escrita na tela:
fonte nova no mapa aparece sozinha, e fonte sem mapa não aparece — que é o que impede
oferecer uma que o renderizador vai recusar.

O diálogo da F97 virou `ui/dialogo_do_diagrama.py`, com três perguntas em vez de duas, e a
amostra dele deixou de ser um tabuleiro de brinquedo desenhado no `Canvas`: agora ela sai do
`render_diagrama.desenhar`, com a fonte e a moldura escolhidas, que é o mesmo código que vai
escrever o livro. O desenho de mentira mentia justamente onde a escolha importa — as peças
eram as mesmas nas duas fontes.

### O que ficou de fora

- **A moldura por glifo.** A Merida sabe desenhá-la: são oito caracteres de borda (`! " # $
  % ( ) /` na versão dupla, `1 2 3 4 5 7 8 9` na simples), num tabuleiro de 10×10 caracteres
  em vez de 8×8. Não se usa, e o motivo é que a moldura da F97 é desenhada com caneta — o que
  a faz valer para **qualquer** fonte, inclusive a SkakNew, que não tem glifo de borda nenhum.
- **As bordas com coordenada**, em `0xC0`–`0xCF` (simples) e `0xE0`–`0xEF` (dupla). Estas são
  a coisa mais interessante que a Merida traz e que a SkakNew não tem: elas resolveriam o
  rótulo em fonte de texto do modo de fonte embutida — o `<i>` dentro do `<span>` do EPUB, e
  o diagrama com coordenadas que no DOCX ainda cai para imagem. Fica anotado no mapa.

## F99 — A coordenada desenhada pela própria fonte de xadrez — CONCLUÍDA

A F98 deixou anotado que a Chess Merida tem, além dos oito pedaços da moldura, mais dezesseis
glifos que trazem o filete **com o rótulo da fila ou da coluna desenhado ao lado**. São eles
que esta fase usa, e o que eles compram é uma limitação de cada formato:

| | antes | agora |
|---|---|---|
| PNG | rótulo na `helv` do PyMuPDF | rótulo no tipo do livro |
| EPUB | `<i>` dentro de `<span>` para pôr rótulo de fonte de texto em cima de uma casa | dez linhas de texto, e acabou |
| DOCX | **diagrama com coordenada saía como imagem** | sai como texto |

A do DOCX estava escrita no docstring da `para_docx` desde a F59 — "alinhar rótulo de outra
fonte sobre as casas exigiria uma tabela de 81 células por diagrama" —, e a fase mostra que o
motivo dela era a fonte, e não o formato.

### O que os dezesseis glifos são, e como se acharam

`0xC0`–`0xC7` são as filas 1 a 8 e `0xC8`–`0xCF` as colunas `a` a `h`, na moldura simples;
`0xE0`–`0xEF` os mesmos dezesseis na dupla. O `LEEME__D.TXT` diz a faixa e não diz a ordem,
e a ordem se leu na geometria antes de se conferir no desenho:

- as oito primeiras têm a tinta de `x=~700` a `2015` e ocupam o cheio da altura — é o filete
  **vertical** com um algarismo à esquerda. A primeira delas começa em `x=896`, a mais
  estreita das oito: é o `1`.
- as oito seguintes têm a tinta de `x=0` a `2048` e vão de `y=546` a `2013` — filete
  **horizontal** com uma letra embaixo. A sétima começa em `y=300`, e não em 546: é o `g`,
  que é a única das oito com perna. Confirma que a ordem é `a`–`h`.

### O quadro, e o que ele obriga

    canto   topo topo … topo   canto
    fila 8  ┃  as oito casas ┃  direita
    …
    fila 1  ┃  as oito casas ┃  direita
    canto   col.a  …  col.h    canto

Dez linhas de dez caracteres. **O rótulo vem junto do filete, e isso não é escolha nossa**:
o glifo `0xC0` *é* a borda esquerda com um `1` ao lado. Daí a consequência que atravessa o
resto: não há coordenada sem moldura por este caminho, e `moldura="sem"` continua saindo pela
caneta e pela fonte de texto. A `grade()` devolve `None` nesse caso e no da fonte que não tem
os glifos — e devolver `None` é a resposta certa, não uma falha: a SkakNew-Diagram tem 46
codepoints e nenhum deles é filete.

**Os cantos são nomeados pelo canto do tabuleiro que fecham, e não pelo lugar da tinta**, que
é o oposto: o glifo do canto de cima à esquerda tem a tinta embaixo à direita da própria
casa, porque a casa dele fica acima e à esquerda do tabuleiro. Errar isso dá um quadro que
parece certo de longe e tem as quinas viradas para fora.

### O recorte na tinta

A grade tem dez casas de lado, mas a tinta não chega às bordas dela: o filete de cima mora no
pé da casa de cima, e o rótulo da fila ocupa pouco mais da metade da casa da esquerda. Sem
recortar, o diagrama sairia com quase uma casa de branco em cima e à direita e nada embaixo —
torto dentro da própria figura. Recorta-se pela tinta, com folga de 7% de casa.

**E o recorte é determinístico apesar de medir a tinta**: a moldura fecha o desenho dos
quatro lados, e as oito filas e as oito colunas saem em todo diagrama. A caixa da tinta é a
mesma para uma dada fonte, moldura e escala — não depende de onde estão as peças. Está preso
em teste, com um tabuleiro vazio contra um cheio.

### A cascata da CSS, que a segunda fonte tornou alcançável

Achado no caminho, e não é da coordenada: a família da fonte morava em `div.diagrama p`,
regra emitida **uma vez por fonte embutida**. Enquanto havia uma fonte só, as cópias diziam
todas a mesma coisa. Com duas, a segunda venceria a primeira em cascata e o livro inteiro
sairia na última fonte declarada — inclusive os diagramas desenhados com a outra. Hoje a
regra geral sai uma vez e a família sai numa classe por fonte, escolhida pela figura.

Na prática o `livro.extrair` usa uma fonte por livro, então isto era um defeito latente e não
um defeito visto. Ficou fechado do mesmo jeito, junto com a duplicação da folha inteira.

### O que ficou de fora

- ~~**Os cantos arredondados** (`a s d f` na simples, `A S D F` na dupla) — não há como
  oferecê-los sem uma quinta resposta na caixa da F97~~ — **promovidos para a F101**, e a
  quinta resposta não foi preciso: eles não são um quarto feitio de moldura, são um eixo à
  parte, e um sim-ou-não basta.
- **A moldura em glifo sem coordenada.** Faria a SkakNew e a Merida desenharem molduras de
  geometrias diferentes para a mesma escolha do usuário, e a da caneta já vale para as duas.

## F101 — A quina redonda, e a caixinha que teria funcionado em um caso só — CONCLUÍDA

A F99 deixou os cantos arredondados de fora dizendo que não havia como oferecê-los sem uma
quinta resposta na caixa. Havia: eles não são um quarto feitio de moldura, são um **eixo à
parte** — três feitios e um sim-ou-não. "Sem moldura arredondada" não quer dizer nada, e
cinco radiobuttons fariam o usuário procurar a combinação em vez de escolhê-la.

### O que a Merida traz, e por que não bastaria

`a s d f` acompanham a moldura simples e `A S D F` a dupla. Medido no contorno, o `a` tem
**exatamente** a caixa do `1` e o `A` a do `!`: é o mesmo canto, com a curva no lugar do
ângulo. E nenhum dos oito colide com o mapa de casas.

Mas os glifos de moldura só entram num caminho: diagrama **com coordenada**, em fonte que os
tenha. O caminho mais usado de todos — PNG sem coordenada, que é o padrão da exportação —
desenha o filete com a caneta, e ali não há glifo nenhum. Uma caixinha que só funcionasse
naquela combinação seria pior que caixinha nenhuma: o usuário marca, exporta, e nada muda.

### Então a caneta também arredonda, com o raio da fonte

| | raio |
|---|---:|
| canto simples da Merida (`a`) | 135 de 2048 unidades do em = **0,066 casa** |
| canto duplo da Merida (`A`) | 409 de 2048 = **0,200 casa** |

São esses os dois números que a caneta usa. Copiar o desenho da fonte é o que impede a
escolha de significar duas coisas — o mesmo diagrama tem a mesma quina saindo da Merida ou
da caneta, e a SkakNew, que não tem canto redondo nenhum, passa a ter um.

Na moldura dupla os dois filetes são concêntricos, e o de dentro tem de curvar mais fechado
que o de fora **exatamente pela distância que os separa**, ou os dois se cruzam na quina. O
`radius` do PyMuPDF é fração do menor lado do retângulo, e cada filete tem o seu.

E curvar a quina não mexe na medida do desenho: o filete continua ocupando a mesma margem, e
um diagrama arredondado ao lado de um reto casa. Está em teste.

### Onde ele chega, e onde não

| | quem desenha |
|---|---|
| PNG, sem coordenada | a caneta, nas duas fontes |
| PNG, com coordenada, Merida | os glifos `a s d f` / `A S D F` |
| PNG, com coordenada, SkakNew | a caneta |
| EPUB, modo de fonte, caixa | `border-radius` na CSS |
| EPUB, modo de fonte, emoldurado em glifo | a fonte |
| **DOCX, modo de fonte, caixa** | **ninguém: o Word não arredonda borda de célula** |
| DOCX, modo de fonte, emoldurado em glifo | a fonte |

A única casa vazia da tabela é a caixa do DOCX, e ela é do formato: `w:tcBorders` não tem
raio. O `para_docx` **confere** o valor mesmo sem usá-lo — sem isso um `"redondo"` passaria
calado num formato e doeria no outro, e o usuário veria dois arquivos diferentes do mesmo
livro.

### O caso que não pode cair para a caneta

Uma fonte com borda em glifo e sem a versão redonda: a `moldura_em_glifo` devolve os cantos
de quina viva, e não `None`. Devolver `None` mandaria o diagrama inteiro para o caminho da
caneta e **perderia as coordenadas em glifo** — muito mais do que se pediu ao marcar uma
caixinha. Hoje não há fonte assim no repositório, e o teste monta uma.

## F102 — Vinte e duas classes esperavam o treino, e sete delas não tinham desenho — CONCLUÍDA

Desde o treino de 21/08 a base andou e o modelo não: `training_data/` tinha **314 pastas
para 292 classes**. Uma pasta que não é classe não é dado esperando — é dado que o modelo
**não pode acertar nunca**, porque a saída correspondente não existe na rede. E como o
`CharDataset` transforma toda pasta não vazia em classe, o remédio é só um: treinar de novo.

### O que chegou, e por que nenhuma delas é rótulo errado

São 136 amostras em 22 pastas — e o treino inteiro cresceu 7.056, ou seja **as outras 6.920
foram para classes que já existiam**. As 22:

| grupo | classes | amostras |
|---|---|---:|
| pontuação | `•` | 90 |
| ângulo reto | `⨼`, `∟` | 14 |
| posicionais do Informator | `⟪`, `⟳`, `⇔`, `⊞`, `⊥`, `○` | 6 |
| peões (`$249`–`$251`) | `⯺`, `⯻`, `⯼` | 3 |
| acentuadas de nome próprio | `Ä`, `È`, `Ë`, `Ö`, `è`, `ö` | 14 |
| ligaduras de prosa | `da`, `ky`, `ru`, `tt` | 9 |

**Vinte delas têm de 1 a 5 amostras, e é por isso que a folha de contato veio antes do
treino**: uma classe nova com rótulo errado não falha alto — ela ensina o símbolo errado e
some dentro de 99,7% de acurácia, que é o defeito da F1.4. Duas mereciam a suspeita:

- `⯺ ⯻ ⯼` parecem "oo", "0-0" e um "8" deitado, ou seja parecem **roque mal recortado**.
  Não são: são os `$249`–`$251` da tabela de `core/nags.py` — peões ligados, isolados e
  dobrados —, e o desenho de cada um bate com o da SkakNew-Figurine.
- `⨼` (13 amostras) e `∟` (1) são **o mesmo ângulo reto virado**. Não é duplicata, e o que
  decide não é o nome do codepoint: o U+2A3C chama-se "interior product" e o U+221F "right
  angle", e nenhum dos dois diz de que lado fica a haste. O livro diz — à direita no `⨼`, à
  esquerda no `∟` —, e a fonte tem os dois separados, no `w` e no `v`.

### O treino, e a comparação que não é comparação

112 minutos de CPU, 608.407 amostras, melhor epoch 17 de 20 (antes, 20 de 20 — a perda de
validação parou de cair três epochs antes do fim):

| | 292 classes | 314 classes |
|---|---:|---:|
| amostras | 601.351 | 608.407 |
| desbalanceamento | — | 63.055:1 |
| validação, acurácia | **99,81%** | 99,73% |
| validação, recall macro | 98,20% (241 classes) | **98,25%** (244) |
| validação, classes zeradas | 1 | 1 |
| teste, acurácia | 99,75% | 99,75% |
| teste, recall macro | 98,73% | **99,09%** |
| temperatura da calibração | 2,5209 | 1,9054 |

**Os dois primeiros números não se comparam, e é honesto dizer isso em vez de comemorar o
macro.** Cada treino sorteia o próprio split a partir da própria base; o conjunto de
validação de agora tem 22 classes que o de antes não tinha e 6.920 amostras a mais nas
antigas. Os 0,08 ponto de acurácia que caíram e os 0,05 que o macro subiu estão dentro do que
o próprio relatório avisa: 59 das 244 classes avaliadas têm menos de 5 amostras de
validação, e **uma amostra que muda de lado mexe 0,41 ponto no macro**.

O número que menos se mexe é o do teste — 99,75% nos dois —, e é o único que nenhuma decisão
do treino usou.

### As três que a validação alcança, e as dezenove que ela não alcança

Classes com menos de 5 amostras vão inteiras para o treino, por desenho: **70 classes ficaram
sem validação nenhuma** (eram 51), e 19 das 22 novas estão nesse grupo. Das três que sobram:

| classe | validação |
|---|---:|
| `•` | 14/14 |
| `⨼` | 2/2 |
| `Ö` | 1/1 |

Para as outras dezenove não há medida, e não adianta inventar uma. O que dá para afirmar é o
**piso**: o modelo devolve o rótulo certo em **136 de 136** dos recortes das 22 pastas —
quase todos vistos no treino, então isto não diz nada sobre generalizar. Diz que nenhuma das
22 saiu morta, que era o risco real de uma classe de uma amostra só competindo com 313
outras.

### O recorte da fonte, e os sete que não tinham desenho

O alfabeto passou de 71 para **89 símbolos fora do ASCII**, e a `NotoSansSymbols2` desenha 24
deles — os `⯺ ⯻ ⯼`, o `•` e o `○` entre eles. Os outros sete novos — `⟪ ⟳ ⨼ ⇔ ∟ ⊞ ⊥` — ela
não desenha, e sem desenho o símbolo que o modelo acabou de aprender sai **quadradinho no
EPUB**, sem erro no caminho.

A SkakNew-Figurine desenha os sete. Os pares foram decididos como manda a F62 — contra os
recortes do livro, e não contra outra fonte —, e é o `∟`/`⨼` que mostra por quê: casados pelo
nome, os dois sairiam espelhados na página e nada acusaria.

| | antes | depois |
|---|---:|---:|
| glifos no recorte | 27 | **41** |
| tamanho | 7,0 KB | 9,1 KB |
| fração da Noto inteira | 1,1% | **1,4%** |

No caminho do PDF os sete não faltam: medidas as candidatas de `chess_pdf_processor`, a
`Segoe UI Symbol` deste sistema desenha os sete, e `nags.sem_glifo()` continua desligando só
o `⯾` do `$255`.

### O `⇗` e o `⌓` entram junto, e o arco sai mais raso do que o livro

Sobrava a dívida antiga: cinco símbolos do alfabeto sem glifo no recorte. Dois deles a
SkakNew-Figurine desenha, e o custo dos dois é diferente.

O `⇗` (`$240`, diagonal) é o `G`, e bate traço por traço com as 3 amostras de `sym_8663`.

O `⌓` (`$142`, "melhor é") **não bate**, e o que mede isso é a proporção:

| | altura ÷ largura |
|---|---:|
| as 64 amostras de `sym_8979` (mediana) | 0,72 |
| `IS-TT-01`, o `e` | 0,79 |
| **`SkakNew-Figurine`, o `b`** | **0,53** |

O livro imprime um arco de laterais retas assentado numa base; o `b` é uma meia-elipse rasa.
Quem desenha o arco do livro é a `IS-TT-01` — **e ela não pode viajar dentro do arquivo**:
`fsType = 1` no `OS/2`, o "restricted license embedding" da Chess Assistant, contra
`fsType = 0` da SkakNew. Não é zelo excessivo: é o mesmo motivo pelo qual as quatro famílias
que desenham o `⩲` ficaram de fora na F62.

### O arco passa a ser desenhado, e é o primeiro glifo que este projeto escreve

O `b` chegou a entrar como par, e é raso demais: usá-lo seria trocar quadradinho por símbolo
errado, que é a mesma família de defeito do `·` da SPEC §4.2 — só que mais discreta. Copiar o
glifo da `IS-TT-01` resolveria a forma e não resolve a licença: **o que se copiaria dela não é
uma medida, é o desenho**, e o `fsType` fala do desenho.

Sobra desenhar. O arco tem três medidas, e as três saem das mesmas 64 amostras:

| | medida | em unidades de em |
|---|---:|---:|
| altura ÷ largura | 0,714 | 738 de 1034 |
| traço ÷ largura | 0,103 | 107 |
| reta das laterais ÷ altura | 0,406 | 300 |

**A largura e o avanço são os que o `b` já ocupava** (1034 e 1200), e isso é escolha: o que
estava errado era a altura, e mexer no avanço junto mudaria a entrelinha de quem já exportou
um livro. A altura que sai da proporção cai no meio da faixa dos outros emprestados — o `⊞`
tem 755, o `∟` 734, o `⊥` 725 —, o que é a confirmação de que a régua é a mesma.

O contorno é escrito em cúbicas e passa pelo mesmo `Cu2QuPen` do `emprestar`, pela mesma
razão e com o mesmo `reverse_direction`: são dois contornos, o de fora anti-horário e o
buraco horário, e é a diferença entre um arco e um retângulo arredondado maciço.

**Emprestar continua sendo preferível**, e o `desenhar` não é a porta larga: o glifo
emprestado vem de quem sabe desenhar fonte e mantém a família coerente. Este caminho é para o
caso em que a única fonte que acerta a forma proíbe embutir — hoje, um símbolo.

### O `✝` não precisava de glifo, e o script é que estava perguntando errado

Ele era o último da lista, e é o que mais tem amostra: **2.901**, a cruz cheia que estes
livros imprimem no xeque. Desenhá-lo seria trabalho perdido, e quem diz isso é a F68: o
`notacao.SINONIMOS_DE_SAIDA` está nos **três** lugares em que caractere de modelo vira texto
de arquivo — `livro`, `notacao` e `searchable_pdf` —, e nos três ele sai como `+`.

Ou seja, **nenhum arquivo que este programa escreve pode conter um `✝`**. A conta de "quem
falta desenhar" é que estava errada: o `simbolos_do_modelo` respondia com o alfabeto do
modelo, e a pergunta certa é quais caracteres **chegam a um arquivo**. Com o filtro, o
alfabeto pedido cai de 89 para 88 símbolos e a última linha do script passa a dizer

    ainda sem glifo: – —

que são travessão e meia-risca — pontuação que a fonte de texto do leitor desenha, e que o
`fonte_dos_simbolos` nem chega a pedir: ele embrulha no `<span>` da fonte de recurso **só os
caracteres que ela cobre**, e não a linha inteira.

A dívida dos "cinco sem glifo" fecha em três frentes diferentes, e nenhuma delas é a que
parecia: dois foram emprestados, um foi desenhado, e dois nunca existiram.

### O que isto abre

- **Dois símbolos ficam sem glifo no recorte, e é o certo**: `– —`. A fonte de texto do
  leitor os desenha, e o recorte só recebe o que ela não tem.
- **Nada mede o desenho contra a página**, só contra as proporções que saíram dela. Um
  diagrama impresso lado a lado com o EPUB exportado é a prova que falta, e ela é visual.
- **O `desenhar` tem um usuário só, e é assim que ele deve continuar.** O próximo símbolo
  sem glifo que aparecer se resolve procurando fonte antes de pegar a caneta.
- **Vinte classes com menos de cinco amostras não têm como ser medidas.** A `importar_letras`
  da F94 existe para exatamente isto, e o `--faltantes` aceita a lista.
- **O piso de 136/136 não é acurácia.** Enquanto essas classes não tiverem validação, o que
  se sabe delas é que existem.

Cobertura: os 9 testes de `tests/test_f62_simbolos.py` — o primeiro deles é quem cobra o
recorte desatualizado, e reprovava antes de o script rodar.
Reproduzir: `python gerar_fonte_de_simbolos.py --conferir` diz o que falta;
`python gerar_fonte_de_simbolos.py` refaz o recorte.

## F103 — Todo livro que este projeto exportou saiu com um parágrafo por linha — CONCLUÍDA

Achado ao conferir a conversão do Aagaard com a Merida: 41.877 parágrafos no DOCX, mediana de
**35 caracteres**, e nenhum passando de 120. Numa página de prosa corrida, cada linha
impressa era um parágrafo:

    [ 98] Learning anything involves a lot of repetition and looking at it trom dif+terent angles. Most will
    [ 93] know the principle of rwo weaknesses. But seeing a new example explaining it will only expand
    [ 95] your understanding othe theme. In chess nothing is absolute. We have a lot o ideas and concepts

Aquilo é um parágrafo só.

### Qual das três regras, medida nas 898 páginas

40.828 transições entre linhas, das quais **40.623 abrem parágrafo (99,5%)**. Sobram 205
continuações no livro inteiro.

| regra | disparou | em quantas páginas |
|---|---:|---:|
| **`saltou`** | **39.679×** | **898 de 898 (100%)** |
| `recuou` | 9.715× | 876 de 898 (98%) |
| `trocou` | 880× | 847 de 898 (94%) |

Sozinha: só `saltou` responde por 74,0% das quebras, `saltou`+`recuou` por outros 23,8%, só
`trocou` por 2,1% e só `recuou` por 0,2%. O `saltou` participa de 97,8% delas.

### Por que: o denominador nunca foi o certo

```python
saltou = linha.topo - anterior.topo > altura * (1 + SALTO_DE_PARAGRAFO)
```

`Linha.altura` é a **mediana da altura dos glifos daquela linha**. Numa fonte de texto isso é
a altura de x — sem ascendente nem descendente — e o passo entre linhas mede quase o triplo:

| salto ÷ altura de glifo, no Aagaard | |
|---|---:|
| p10 | 1,86 |
| **mediana** | **2,62** |
| p90 | 5,65 |
| limite | **1,6** |

O décimo percentil já passa do limite. **99,3% dos passos normais eram lidos como vão de
parágrafo.**

### E não era aquele livro

| livro | mediana | acima do limite |
|---|---:|---:|
| Aagaard · Endgame Technique | 2,60 | 99,2% |
| Aagaard · Attacking Manual I | 2,74 | 99,8% |
| Dvoretsky · Endgame Manual | 2,41 | 100,0% |
| Nunn · Secrets of Rook Endings | 1,92 | 96,3% |
| Darcy Lima · A Estratégia | 1,91 | 92,3% |
| Yusupov · Chess Evolution 1 | 2,33 | 86,1% |

A regra nunca funcionou como pretendida, em nenhum livro. Todo EPUB e DOCX que este projeto
escreveu, desde a F2.6, saiu com um parágrafo por linha impressa.

### O conserto: passo de linha, e não altura de glifo

O `_metricas_por_coluna` passa a medir também o **passo mediano de cada coluna**, dos vãos
entre topos **ordenados** — a mediana é robusta ao vão grande que um diagrama abre no meio da
coluna, mas não ao vão negativo que a ordem de leitura produz na virada. E as duas regras que
mediam em glifos passam a medir em passos.

O `recuou` muda de unidade junto, e não por simetria: `0,8 × altura de glifo` são 16 px de
limite, menos que um espaço entre palavras. Em passos são 41, que é a ordem de grandeza de um
recuo impresso. Sem isso ele viraria o novo dominante — simulado no livro inteiro, os
parágrafos parariam em 2 linhas em vez de 3.

| cenário, simulado nas 39.948 transições | quebras | linhas por parágrafo |
|---|---:|---:|
| antes | 99,5% | 1,0 |
| salto pelo passo, recuo como estava | 36,3% | 2,0 |
| **salto e recuo pelo passo** | **23,3%** | **3,0** (média 4,3) |
| salto pelo passo, recuo desligado | 21,3% | 4,0 |

**A regra nova é subconjunto estrito da antiga**: nas 39.948 transições ela concorda em 8.515
quebras, deixa de fazer 31.164 e **não inventa nenhuma**. Ela não passa a quebrar onde a
antiga não quebrava — só para de quebrar onde não havia motivo.

### Conferido no livro, e não só no sintético

Dez páginas espalhadas pelo Aagaard, com a extração de verdade, contra o cache da regra
antiga: **521 parágrafos viram 141**. A página 11 sai com 9 em vez de 38, e os dois parágrafos
de prosa dela voltam a ter 685 e 1.222 caracteres.

E a conferência que vale mais que a contagem: juntando todo o texto das duas versões e
normalizando o espaço em branco, **as duas são idênticas**. A fase reagrupa, e não reescreve.

### O teste da F61 que mudou de instrumento

`test_o_diagrama_do_alto_da_direita_nao_vem_antes_da_esquerda` contava **parágrafos** antes da
figura para provar a ordem. Isso media a ordem enquanto cada linha era um parágrafo; com as
linhas juntas, a coluna da esquerda inteira vira um bloco só e o "1 de 3" não diz mais nada
sobre onde a figura caiu. Passou a contar caracteres, que é o que a propriedade sempre quis
dizer.

## F104 — A confusão de caracteres de um livro inteiro, sem gabarito — CONCLUÍDA (instrumento)

O `medir_confusao.py` da F13 compara com `.box` feito à mão, e por isso mede dezenas de
páginas. A pergunta que a F103 deixou aberta — de onde vêm os `trom`, `rwo` e `dif+terent`
que a prosa agora mostra em parágrafos de verdade — é sobre novecentas.

A verdade passa a ser o dicionário de 310.465 palavras da F9, e a suposição é o contrato 1
da SPEC §5.8: palavra de prosa fora dele foi lida errado. `medir_confusao_no_livro.py` lê um
DOCX já escrito (segundos, sem modelo) ou o PDF (minutos, com o modelo e cache).

### O prior, que é a parte que não dá para pular

Achado o núcleo fora do dicionário, qual palavra era ele? Distância de edição sozinha não
decide: para `quicHy` ela escolhe `quiche` com a mesma facilidade com que escolhe `quickly`.
Quem desempata é a frequência **no próprio livro** — e o prior tem de sair dali porque o
léxico deste projeto é alfabético e não traz frequência nenhuma, nem ele nem os quatro
arquivos da `Lista de Palavras`.

### Três erros do instrumento, achados medindo o instrumento

**A peneira da notação parecia elegante e estava errada.** `parece_lance(nucleo + algarismo)`
lê `hxg5` e recusa `two1` — mas aceita `endgame1`, `fine1` e `ed1`, e **20.277 palavras reais
do dicionário passariam por lance**. No livro ela escondeu `dgame` (140 ocorrências, que é
`endgame`), `Khowing`, `beeause` e `exampIe` no balde dos lances. Trocada por um padrão
escrito à mão — coluna, o `x`, coluna —, e o balde caiu de 1.061 para 759.

**O alinhamento tem de ser na caixa original.** `BIack` contra `Black` é `l → I` com `I`
maiúsculo; em minúsculo vira `l → i`, que é outra troca e manda procurar outro defeito.

**Pedaço de palavra perdido não é confusão de caractere.** `dgame` é `endgame` sem duas
letras e `ustrative` é `illustrative` sem três — segmentação, não glifo trocado. Na matriz
dariam `nada → d` com peso de 140 leituras. O corte é de duas letras: `Exchang` é `Exchange`
sem o `e` final, e *aquilo* é a leitura errada de um caractere que se quer medir.

### O que o método não vê, e o relatório diz

| | |
|---|---|
| erro que produz **outra palavra real** | invisível ao dicionário — limite do método |
| palavra que o livro nunca acertou | prior zero, não se decide: 222 ocorrências |
| espaço perdido, pedaço perdido, sem candidato | 1.412 ocorrências, fora da matriz |

Uma rodada de realimentação — deixar o que a matriz já confirma explicar o duvidoso —
recupera 15% a mais e **erra**: resolve `quicHy` como `quiche`, porque `e→y` já é troca
confirmada e `kl→H` não. Foi medida e recusada; fica registrada para quem pensar nela de novo.

### O que o Aagaard mostrou

**1,01% das palavras de prosa saem erradas** (1.318 de 130.194), teto de 2,0% se tudo o que
sobrou também for erro. E o achado não é a taxa: **o erro se concentra em par de letras, e
não em glifo.**

| troca | % dos erros | em quantas palavras | onde |
|---|---:|---:|---|
| `t → r` | **23,5%** | **6** | `two`(247), `between`(49), `twice`, `Botvinnik` — todas com `tw`/`tv` |
| `l → nada` | 7,2% | 18 | `Although`, `Allowing`, `Already` — o `ll` depois de `A` |
| `l → I` | 3,9% | 34 | espalhado |
| `f → nada` | 3,6% | 12 | `Stockfish`, `defensive` |
| `c → e` | 3,3% | 23 | espalhado |
| `y → u` | 2,7% | 4 | `strategy`(29) — o `gy` final |
| `z → nada` | 2,4% | **2** | `zugzwang` |
| `n → h` | 1,1% | 3 | `Knowing`, `Knights`, `Knight` — o `Kn` |

A coluna do meio é a que decide o que fazer. Uma troca em seis palavras não é um glifo que o
modelo não sabe: é um **par** que a segmentação não separa. Espalhados de verdade só há dois,
o `l → I` e o `c → e`.

E o custo por palavra é desigual: `stockfish` sai certa em 5% das vezes, `two` em 22%,
`between` em 26% — contra `black` em 98% e `from` em 98%.

### Os seis livros

| livro | pág | prosa | fora do dicionário | taxa de erro |
|---|---:|---:|---:|---:|
| Nunn · Secrets of Rook Endings | 354 | 55.928 | 2,4% | **0,38%** |
| Aagaard · Attacking Manual I | 263 | 68.915 | 2,8% | 0,65% |
| Aagaard · Endgame Technique | 898 | 130.194 | 3,0% | 0,82% |
| Yusupov · Chess Evolution 1 | 264 | 17.564 | 6,5% | 1,33% |
| Yusupov · Complete | 2612 | 210.483 | 8,7% | 3,27% |
| Dvoretsky · Endgame Manual | 816 | 75.323 | 21,7% | **3,93%** |
| Darcy Lima · A Estratégia | 319 | 57.181 | 55,8% | recusado: português |

**Dez vezes entre o melhor e o pior**, e o que varia é o livro, não o modelo. A coluna que
prevê é a de "fora do dicionário": ela se mede antes de qualquer atribuição e diz de saída se
vale a pena continuar.

**Acima de uns 10% o instrumento encosta no próprio limite**, e o Dvoretsky mostra como. O
prior sai das palavras que o livro **acertou**; num livro em que `move` quase nunca sai certo,
o prior não conhece `move`, e `mVe` — 476 ocorrências — vai parar em `ave`. A direção do
achado continua boa (o `o` some), mas o alvo de cada atribuição, não. O relatório imprime a
fração de fora justamente para isso.

### O que os seis têm em comum, e o que é de cada um

Em comum, **caractere que some**: `o`, `l` e `i` desaparecem nos seis livros, e o `s` vira `S`
nos seis. É o único padrão que atravessa o corpus.

O resto é de cada livro, e quase sempre é **par de letras**, não glifo:

| livro | o que domina |
|---|---|
| Aagaard · Endgame Technique | `t → r` em 28% dos erros, cinco formas, todas com `tw`/`tv` |
| Aagaard · Attacking Manual I | `White` → `WThite` (74×) e `for` → `fow` (46×) |
| Yusupov · Chess Evolution 1 | `Diagram` → `Diagrram` (79×) — metade dos erros do livro |
| Yusupov · Complete | `o` some em **274 formas** — aqui é espalhado de verdade |
| Dvoretsky · Endgame Manual | `o` some (`imprtant`, `nthing`, `wrng`) e `s` vira `S` (`lSeS`) |
| Nunn · Secrets of Rook Endings | nada domina: 17% nas três maiores, o menor do corpus |

**E o maior contribuinte de quase todo livro é elemento repetido de página** — o cabeçalho
`Attacking Manual - Volume 1`, a legenda `Diagram 9-5`, o rodapé `Chapter 3`. Eles entram na
prosa e multiplicam um erro só por centenas de páginas: no Yusupov Chess Evolution as três
formas mais frequentes são metade dos erros do livro.

### O que isto abre

Três alvos, e nenhum deles é classe que falte ao alfabeto:

- **Segmentação de par**: `tw`, `Wh`, `ll` depois de maiúscula, `gy`, `Kn`, `zz`. São pares
  colados que o `findContours` entrega como um recorte só, ou parte no lugar errado.
- **O `o` que some**, que é o único defeito com peso nos seis livros — e no Yusupov Complete
  está em 274 formas diferentes, o que o separa dos pares.
- **Cabeçalho e rodapé fora da prosa.** Não é erro de leitura: é elemento de página que a
  extração não distingue do texto, e ele domina a contagem de três dos seis livros.

E uma coisa que já existe e não está ligada: `lexico.juntar_hifenizadas`, da F9.1, tem teste e
**nenhum caminho de produção a chama**. Medido, ela é quase toda do Nunn — 1.364 tokens
terminados em hífen contra ~50 nos outros livros —, e ali juntaria 490 palavras. Nos demais
não muda nada.

## F105 — O negrito do impresso chega ao arquivo — CONCLUÍDA

Todo livro que este projeto exportou saiu com um peso só. Nestes livros isso não é
detalhe de acabamento: **a notação principal é negrito e a análise secundária não é**,
e é assim que o leitor sabe qual linha é a do jogo. Sem o peso, `1.♖e1?` no meio da
prosa é indistinguível da variante que a comenta.

### A medida, e as duas normalizações

O que separa negrito de redondo é a espessura do traço. Ela sai da transformada de
distância — em cada pixel de tinta, o quanto falta para a borda —, e a conta é
`2 × média − 1`, que num traço de largura *w* vale exatamente `w/2`.

**O `− 1` não é ajuste fino.** A transformada soma meio pixel em cada borda, e esse meio
pixel pesa muito num glifo pequeno e pouco num grande: sem ele a nota de rodapé mede mais
espessa que a prosa em negrito da mesma página. Vale 0,9 ponto de acerto ponta a ponta
(98,5% contra 97,6%), e mais que dobra a folga do limiar — a razão da família mais
apertada sobe de 1,13 para 1,22.

Espessura em pixels não diz nada sozinha, e por isso ela é normalizada duas vezes:

    espessura   largura do traço ÷ altura da tinta do glifo — tira o corpo
    relativo    ÷ a espessura **daquele mesmo caractere** no resto do livro —
                tira o desenho

A segunda é o miolo da fase, e **só existe porque este projeto lê o caractere antes de
medi-lo**. Um `.` é grosso e um `l` é fino em qualquer peso; comparar os dois nunca disse
nada. Comparar `l` com `l` diz tudo.

### O gabarito: um livro, e só um

Dos oito PDF desta pasta, o Dvoretsky é o único cuja camada de texto **nomeia as fontes**
(`TimesNewRomanPS-BoldMT` × `TimesNewRomanPSMT`). Nos outros a camada veio do OCR de
fábrica, que reembutiu tudo com nomes gerados (`Fd350139`), e ali não há como saber qual
era o peso. 40 páginas sorteadas, 9.338 palavras, 12,8% delas em negrito.

| referência de cada caractere | acerta | falso |
|---|---:|---:|
| mediana da página | 63,1% | 0,04% |
| quantil da página | 92,0% | 0,06% |
| mediana do livro | 94,8% | 0,16% |
| **quantil do livro** | **97,1%** | **0,22%** |

**Quantil e não mediana**, e o motivo é do gênero: a mediana supõe que a maior parte das
aparições daquele caractere está no peso redondo, e num livro de xadrez a notação é
negrito — a mediana de `4` neste livro *é* o peso negrito, e nenhum `4` negrito passaria
da régua. O p25 pega o redondo mesmo quando ele é minoria e não estraga o caso comum.

**Do livro e não da página**, e isso custou uma segunda passada: `extrair_pagina` marca
com a página que acabou de ler, `extrair` remarca no fim com o livro inteiro. A marcação
é idempotente e a segunda é a que vale.

### A decisão é por palavra

Glifo a glifo a mesma régua acerta 83,8% com 1,35% de falso, e o que ela perde é a
pontuação — 31,3% dos sinais, contra 95,4% das letras e 99,7% dos dígitos. Um `.` tem meia
dúzia de pixels de altura, e meio pixel de erro nele é 10% de espessura.

| glifos medidos na palavra | palavras | acerta | falso |
|---|---:|---:|---:|
| 1 | 1.261 | 29,2% | 11,48% |
| 2 | 1.081 | 87,7% | 1,67% |
| 3 ou mais | 6.996 | **99,7%** | **0,02%** |

A palavra de um glifo não decide nada, e passou a não decidir. O que sobra de fora dela
são o travessão de `Nimzovitch — Tarrasch` e o `!` do lance — que *são* negrito no
impresso — e a fileira `a b c d e f g h` do diagrama, que não é. **A pontuação curta herda
dos vizinhos; a alfanumérica não herda**, e a assimetria é o artigo: herdar em toda
palavra curta vale 0,6 ponto neste livro e poria o `a` em negrito toda vez que o texto
dissesse "played 1.e4 a strong move".

### O limiar, que este livro não escolhe

Varrido nas 9.338 palavras, o alarme falso é o mesmo 0,22% de 1,02 a 1,20 — as palavras
redondas simplesmente não ocupam essa faixa. Quem escolhe são as duas populações e o
desenho das fontes:

| | |
|---|---|
| palavra redonda, percentil 99 | **1,006** |
| palavra negrito, percentil 1 | **1,167** |
| razão negrito ÷ redondo desenhada pelas fontes | **1,22 a 1,91** |

A segunda linha da tabela sai de desenhar o alfabeto nas dez famílias que o Windows traz,
nos dois pesos e em três corpos (`medir_negrito.py --fontes`). A mais apertada de todas é
a Constantia a 30 px — que é a nota de rodapé — com 1,22. **1,15 fica acima de 99 em cada
100 palavras redondas e abaixo da mais apertada das famílias.**

### O que ela não sabe, e nenhum limiar conserta

Os 0,22% que sobram têm nome: são o `B?` e o `W?` que o Dvoretsky imprime **em Arial** no
meio de uma página em Times — 12 das 18 palavras que a régua erra no livro. Ela mede peso,
e uma segunda família de traço mais gordo passa por negrito. Distinguir os dois exige
reconhecer a fonte, que é outra pergunta e outra fase.

### Ponta a ponta

Cada linha do gabarito virou um parágrafo com as espessuras medidas, e o `negrito.marcar`
de produção rodou nelas — a régua inteira, herança incluída:

| palavras | acerta | falso |
|---|---:|---:|
| 9.338 | **98,5%** | **0,22%** |

E no caminho de verdade, com a segmentação e o modelo desta casa em vez das caixas do PDF,
as páginas 101 e 102 do Dvoretsky saem com a notação principal marcada, `Tragicomedies` e
`Nimzovitch — Tarrasch` inteiros num trecho só, e a fileira de coordenadas de fora.
Conferido contra a camada de texto do livro: onde a régua **não** marcou o `1.♖h1` da
prosa, o PDF também diz que ali não há negrito.

### Onde o peso passa a viajar

`Paragrafo` ganhou dois campos. `negrito` são as fatias `(início, fim)` do texto — fatias,
e não texto marcado, para quem lê o parágrafo pelo léxico, pelo PGN ou pela escolha da
fonte dos símbolos continuar lendo o que estava escrito. E `pesos` é a espessura de cada
caractere, em `array('f')`: são 2,3 milhões de caracteres num livro de 900 páginas, 9 MB
como vetor de 4 bytes contra ~60 MB numa lista de `float`.

No EPUB o trecho sai em `<strong>`; no DOCX, em `run` com `bold`. Os dois cortes se somam
ao da fonte dos símbolos, que já existia: `1.♔g4` em negrito sai em três `run`, e os três
em negrito. **Título não recebe marca** — ele já é `<h2>` e `Heading 2`, e os dois
desenham negrito sozinhos.

Cobertura: `tests/test_f105_negrito.py`, 25 testes. Instrumento: `medir_negrito.py`, que
refaz todas as tabelas acima.

## F106 — O `I` grosso e o ponto saíam como travessão, e a rede não tinha como saber — CONCLUÍDA

Duas queixas, o mesmo defeito: "o I maiúsculo parece que quando é mais grosso é reconhecido
como —" e, no ponto, "às vezes é reconhecido como — e algumas vezes como I". A segunda é que
mostra o que estava acontecendo — um ponto não se parece com um travessão em nada.

### O que os dois classificadores recebem

`NeuralPredictor._probabilidades` e `CharacterLearner._quadrados_ate` fazem a mesma coisa com
o recorte antes de olhar para ele:

```python
img = cv2.resize(img_gray, (32, 32))
```

Sem preservar proporção. Uma barra de tinta em pé de 5×20 e uma deitada de 20×5 não chegam
*parecidas* ao classificador: chegam **iguais byte a byte** (`np.array_equal` verdadeiro). A
proporção e o tamanho do glifo são descartados antes de qualquer elo ver alguma coisa, e os
dois elos da cadeia são cegos a eles pelo mesmo motivo.

Enquanto o glifo tem branco por dentro isso não custa nada — o desenho sobrevive ao esticão.
O que quebra é o recorte que é **só tinta**: ponto, `I` de haste grossa, travessão, `|`,
quadrado. Todos viram o mesmo quadrado preto de 32×32, e a resposta a ele é sempre a mesma:

    '■' 0,3823   '—' 0,2758   'l' 0,1015   '-' 0,0543   '–' 0,0452   'I' 0,0397   '.' 0,0230

Um ponto de 2×2 e um de 8×8 devolvem `0.3822762072086334` os dois, **até o último dígito** —
é literalmente a mesma entrada. Não é a rede hesitando entre as classes: é ela lendo a
frequência de treino delas, que é o único sinal que sobrou. Das 1.111 amostras de `—` da
base, 338 já são o quadrado maciço; das 790 de `I`, 12. Foi isso que ela aprendeu a
responder, e é por isso que o mesmo ponto sai ora `—`, ora `I`.

### Por que "mais grosso"

O que salva o `I` são os vãos brancos entre as serifas, e tinta pesada os fecha. Medido no
`I` de *Introduction* do Aagaard (p. 11), engrossando o traço:

| tinta | leitura |
|---:|---|
| 0,55 (como está na página) | `I` 0,966 |
| 0,69 | `I` 0,882 |
| 0,79 | `1` 0,480 |
| 0,80 | `]` 0,525 |

Um `I` sem serifa já nasce maciço: em Arial negrito de 28 px o recorte é 100% tinta, e sai
`■` 0,29 e `—` 0,17 sem engrossar nada.

### A regra: veto, e não voto

`core/proporcao.py` guarda, por classe, a faixa de larg/alt em que ela existe, e a cadeia
consulta essa tabela antes de aceitar a leitura. **A geometria nunca escolhe o caractere —
ela recusa o impossível**, e quem escolhe entre as que sobram continua sendo o elo que leu,
pela ordem dele. Um travessão num recorte três vezes mais alto que largo não é uma leitura
duvidosa; é uma que não pode estar certa.

Isso é o contrário do canal que a **F19** mediu e descartou. Lá o desempate opinava onde o
classificador tinha sinal e discordava dele — e, com âncora forte, esse conjunto é quase todo
erro do desempate (0 acertos em 72). Aqui a regra só fala onde a entrada **provadamente não
carrega** a distinção: ela não sabe mais que a rede sobre o glifo, sabe do recorte o que a
rede não recebeu.

Pelo mesmo motivo a `fonte` da leitura não muda. A geometria não lê nada; ela veta uma
resposta e o mesmo elo dá a seguinte. Trocar a fonte para "geometria" avisaria o roteamento e
a fila de revisão de um classificador novo, e não apareceu nenhum.

### De onde vêm os números do envelope

Larg/alt por classe, nos `.box` rotulados:

| classe | n | mín | p10 | mediana | p90 | máx |
|---|---:|---:|---:|---:|---:|---:|
| `l` | 213 | 0,25 | 0,28 | 0,30 | 0,33 | 0,44 |
| `1` | 343 | 0,28 | 0,30 | 0,41 | 0,48 | 0,61 |
| `I` | 26 | 0,26 | 0,37 | 0,40 | 0,52 | 1,50 |
| `.` | 665 | 0,71 | 1,00 | 1,00 | 1,25 | 1,50 |
| `-` | 53 | 1,03 | 2,00 | 3,67 | 6,50 | 8,67 |

Os dois extremos que encostam são recortes de 30×20 e 34×33 rotulados `I` e `-` numa página
que tem seis `■` de 33×33 ao lado: são o quadrado, e não a letra nem o traço. Fora deles, `.`
não passa de 1,50 e `-` não desce de 1,67 — **o corte em 1,6 separa os 665 pontos dos 53
traços sem erro nenhum**, e o teto de 0,8 das barras em pé é folga sobre o maior `1` medido.

O `.` e o `■` são o par que a proporção não fecha: os dois são quadrados, e o que os separa é
o tamanho. Contra a mediana da altura dos boxes da página — o mesmo denominador que
`preprocess.denoise` usa, e pela mesma razão —, `.` vai de 0,15 a 0,50 e `■` de 1,22 a 1,55.
O corte em 0,7 fica no meio do vão. **Sem essa referência o teste de tamanho não roda**, e
quem lê recorte a recorte sem a página à mão fica só com a proporção.

### Medido — `medir_proporcao.py`, nas 11 páginas rotuladas (10.641 caracteres)

Na página como ela é, a regra muda **2 leituras em 10.641**:

| | |
|---|---:|
| certo → errado | **0** |
| errado → certo | 1 &nbsp;&nbsp; `.` lido `—` → `.` |
| errado → errado | 1 &nbsp;&nbsp; `I` lido `-` → `l` |

Os dois casos da queixa estavam no material rotulado, e a regra não encosta em mais nada.

Com a tinta engrossada — `cv2.erode` de 1 a 4, que é o que uma digitalização pesada faz —, na
mesma página. "Família" são os 1.306 caracteres rotulados com uma classe do envelope:

| engrossa | tinta | todos: antes → depois | família: antes → depois | mexidas | quebrou |
|---:|---:|---|---|---:|---:|
| 0 | 0,48 | 93,98% → 93,99% | 97,55% → 97,63% | 2 | **0** |
| 1 | 0,60 | 91,15% → 93,08% | 80,55% → **96,32%** | 213 | **0** |
| 2 | 0,69 | 85,03% → 87,70% | 60,41% → 80,09% | 321 | **0** |
| 3 | 0,76 | 73,87% → 77,30% | 55,74% → 75,50% | 638 | **0** |
| 4 | 0,81 | 54,68% → 57,19% | 56,81% → 76,57% | 1247 | **0** |

Em nenhum dos cinco níveis, e em nenhum dos 53.205 recortes medidos, a regra transformou uma
leitura certa em errada. Não é sorte: ela só dispara sobre resposta que o envelope diz ser
impossível, e leitura certa cabe no envelope por construção — o risco todo está em o envelope
estar apertado demais, e é por isso que ele é medido e folgado, e não escolhido.

Com o k-NN atrás da rede (`--elo cadeia`, 191.915 referências) a coluna de mexidas é a mesma
nos cinco níveis — 2, 213, 321, 638, 1247 —, e `quebrou` continua zero. O segundo elo não
acrescenta troca nenhuma nesta amostra, e a coluna `ao easyocr` diz por quê:

| engrossa | 0 | 1 | 2 | 3 | 4 |
|---|---:|---:|---:|---:|---:|
| desceram ao EasyOCR | 32 | 866 | 1.568 | 2.928 | 5.529 |

A confiança do k-NN é distância L2 absoluta, e ela **rebaixa o traço grosso por engordar** —
é a ressalva que `margem_de_confianca` já registrava. Com a tinta engrossada o recorte se
afasta de toda a base, o limiar de 0,9 não é alcançado por quase ninguém, e quem a rede não
resolveu passa direto pelo k-NN. Na página como ela é, em que 32 descem, o elo responde e a
cadeia mede 94,04% contra os 93,98% da rede sozinha.

Esses recortes entram nas duas colunas de acerto com a leitura da rede, igual dos dois lados
— eles não mudam com o veto, e é por isso que podem ser contados. Mas a partir do nível 2 são
muitos, e a **acurácia** dessas linhas deixa de ser a que produção entregaria: lá o EasyOCR
leria metade da página. O que a tabela mede ali é o veto, não a cadeia.

### O que a regra não alcança

Ela escolhe a **família**, não o membro. Num recorte maciço, `I`, `l`, `1` e `|` são o mesmo
desenho e nada no recorte os separa; a regra derruba o travessão e deixa os quatro para quem
já os ordenava. `lntroduction` continua errado — mas é erro de caixa, e `—ntroduction` era
erro de família.

O último elo da cadeia fica de fora, e não por esquecimento: o EasyOCR devolve um caractere e
nenhuma candidata, então ali não há entre o que escolher. Vetar sem substituta seria apagar a
leitura, que é pior que a leitura improvável — o elo existe justamente para o box que os
outros dois não souberam ler.

E a rede crua continua respondendo onde a pergunta não é "que caractere é este": o árbitro da
segmentação (F1.5b), que compara confiança entre cortes, e a peça do diagrama (F7.4), que é
desenho de xadrez e não letra. O envelope fala de tipografia, e ali não há tipografia sobre o
que falar.

### O conserto de verdade continua pendente

O certo é a proporção **entrar na rede**, treinada junto — recorte em caixa com a proporção
preservada, ou a razão como entrada ao lado do 32×32 —, e não pendurada depois. É a mesma
conclusão que a F14 tirou da altura relativa, e pelo mesmo motivo.

Medido no modelo de hoje, só trocar o esticão pela caixa **não** resolve sem retreinar: a
barra deitada melhora (`-` 0,654), mas a barra em pé passa a sair `T` 0,963, porque a caixa é
fora da distribuição em que ele treinou. E o `.` continuaria irresolúvel sem escala relativa
à linha. Fica para a próxima rodada de treino; até lá, o veto é a guarda.

## F107 — O tamanho do glifo se perdia na gravação, e a régua do espaço media contra a coisa errada — CONCLUÍDA

Uma revisão do reconhecimento e da conversão, pedida porque o resultado exportado estava
ruim. O que ela achou não foram dois defeitos independentes: são **duas réguas medindo
contra a referência errada**, e a segunda é a que dá para consertar hoje.

### O que a queixa era, medido

Três páginas do Seirawan rotuladas à mão, 3.255 caracteres, pelo caminho de produção
(`ler_texto`, com o mesmo `vertical.recorte_de_pe` que o livro usa):

| | |
|---|---:|
| acerto | **96,25%** |
| `s` lido `S` | 40 |
| `o` lido `0` | 38 |
| `o` lido `O` | 8 |
| `I`→`l`, `O`→`0`, `c`→`C`, `l`→`1`, `x`→`X`, `z`→`Z`, `í`→`Í`, `S`→`s` | 15 |
| todo o resto somado | 21 |

**101 dos 122 erros — 83% — são a família de caixa**, e `a`, `e`, `r`, `t`, `n`, `m`, `u`,
`p` e `d` saem a 100%. Por classe, `s` fica em 46,7% e `o` em 52,6%.

No livro inteiro isso aparece como razão de caixa: no DOCX exportado do Seirawan `S/s` é
**3,09** — em português o esperado é perto de 0,04 —, e `(O+0)/o` é **0,48** contra ~0,03.
São ~16 mil `s` maiúsculos que não existem. No Yusupov em inglês o mesmo defeito é mais
brando (`S/s` = 0,20), e é o mesmo defeito.

### Por que nenhuma guarda pega

A confiança mediana nos recortes de `s` é **0,898**, e as três candidatas são `S/s/Š`. A
rede não hesita: ela responde errado com confiança alta, então o piso de `CONF_MINIMA`
não dispara, a fila de revisão não enfileira e a coloração não colore. **Erro confiante
passa por baixo de toda a instrumentação que o projeto construiu.**

E onde ela hesita, o caractere é **apagado**: no `o` a confiança mediana é 0,672 e 11%
ficam abaixo do piso — a probabilidade se reparte entre `o`, `0` e `O` e nenhuma alcança
0,5. É o `Cmbinatin invlving bihp` que o comentário do `livro.CONF_MINIMA` já descrevia, e
é o `'o' → (nada)` 19× que o `medir_confusao_no_livro` acusa no Yusupov.

### A causa está no recorte, e dá para vê-la

Os 40 `s` que erram e os 35 que acertam têm **o mesmo tamanho** — 27×17 contra 27×18 px — e
são indistinguíveis a olho numa folha de contato. A única diferença mensurável é tinta:
0,48 nos que erram, 0,56 nos que acertam. `s` e `S` são o mesmo desenho; o que os separa é
o tamanho, e o `cv2.resize(img, (32, 32))` o descarta antes de qualquer elo ver. Não é
novidade — é o que a F14 nomeou, a F19 mediu e a F106 repetiu no fecho. O que é novo é o
tamanho da conta.

**O k-NN não é a saída, e conferi antes de recomendar.** Ele tira 100% nesses mesmos
recortes, mas 98,1% deles estão byte a byte na base dele — distância zero ao vizinho. É
memória, não generalização, e rotear por esse número seria comprar o número.

### O `learn` era o único lugar do projeto onde o tamanho se perdia

`CharacterLearner.learn` fazia `cv2.resize(img_gray, (LADO, LADO))` e gravava **isso** no
disco. Todo o resto do projeto já redimensiona na leitura — `_ler_do_disco`,
`_quadrados_ate`, o `neural_trainer` e o `dataset_check` têm todos o `if img.shape !=
(32, 32)`. E o funil da coleta guarda no tamanho recortado **de propósito**: o
`coleta._gravar` traz o comentário "gravado no tamanho em que foi recortado, e não no da
rede: quem revisa precisa enxergar o glifo, e o `learn` redimensiona de novo na hora de
promover". Ele redimensionava, e gravava o redimensionado — desfazendo no último passo o
que o funil inteiro tinha preservado.

Agora o disco fica com o recorte como ele é e a matriz do k-NN continua em 32×32. A
correção é de uma linha, mais um `np.ascontiguousarray`: enquanto o que se gravava era o
`resize`, o array era novo; passando o recorte direto, ele é a **fatia** `img[y1:y2,
x1:x2]` que o `recorte_de_pe` devolve, e o `cv2.imwrite` recusa layout não-contíguo.

**Isto não conserta nada sozinho, e é de propósito.** As 608 mil amostras que já estão em
32×32 não voltam — nelas o tamanho não é recuperável, foi descartado na gravação. O que
muda é que a base para de crescer inaproveitável.

### A régua do espaço media tinta contra tinta

O outro defeito da queixa: `2011` saía `20 1 1`, `147` saía `1 47`, `1.♕xf7!!` saía
`1 .♕xf7!!`. São **1.965 números partidos** no DOCX do Yusupov e 995 no do Seirawan.

A régua era `vão > 0,35 × largura mediana de tinta da linha`. Ela compara tinta com tinta,
e a largura de tinta **muda com o alfabeto sem que o espacejamento mude junto**: algarismo
vem com espacejamento tabular, e a caixa de tinta do `1` é um terço do avanço dele,
enquanto a mediana da linha é ditada pelas minúsculas da prosa. Medido nos `.box`
rotulados, o vão mediano entre dois algarismos vizinhos é **0,45** — já acima do limiar,
antes de qualquer espaço existir.

A referência certa é o **vão típico da própria linha**, porque a pergunta é "este vão é
maior que os que esta linha usa entre letras da mesma palavra?", e o vão típico *é* o
espacejamento: ele acompanha o alfabeto por construção.

### O gabarito, e de onde ele sai

`medir_vao.py`, em duas obras com camada de texto. **O rótulo sai da camada e é por
palavra, não por caractere**: o `rawdict` do PyMuPDF devolve a caixa de *avanço* de cada
glifo, que dá vão zero dentro da palavra e seria inútil como régua de geometria. O que a
camada tem de bom é dizer onde a palavra começa e acaba. Então a página é segmentada por
esta casa, cada caixa nossa é atribuída à palavra que a contém, e dois vizinhos na mesma
palavra são um `junto`. A geometria é sempre a nossa, o rótulo é sempre o do livro, e não
há alinhamento caractere a caractere para dar errado.

54.558 pares, 40 páginas:

| régua | Yusupov: a mais / a menos | Aagaard: a mais / a menos | soma dos erros |
|---|---:|---:|---:|
| `0,35 × largura` | 5,5% / 7,9% | 1,4% / 2,6% | 910 + 629 |
| `2,0 × vão típico`, piso `0,45 × largura` | **1,2%** / 10,9% | **0,3%** / 4,0% | **471 + 402** |

**Espaço a mais cai 4,5× e 5,1×; espaço a menos sobe.** As duas contas ficam separadas de
propósito porque não custam o mesmo: espaço a mais parte a palavra e o dicionário a perde
inteira, junto com o léxico e o PGN, que leem por palavra.

**Só reajustar a constante velha já ganharia parte disso** — `0,50 × largura` mede 545 +
439 —, e vale registrar em vez de esconder. A referência nova compra os outros 11%, e
compra sobretudo na coluna que importa: 222 espaços a mais contra 149.

### Os dois números não são quina, são planalto

| fator \ piso | 0,30 | 0,35 | 0,40 | 0,45 | 0,50 |
|---|---:|---:|---:|---:|---:|
| 2,0 | 989 | 923 | 890 | **873** | 910 |
| 2,25 | 999 | 933 | 900 | 883 | 912 |
| 2,5 | 927 | 910 | 887 | 887 | 930 |
| 3,0 | 1166 | 1164 | 1162 | 1162 | 1179 |

Soma dos dois livros. Os quatro melhores ficam a menos de 3% um do outro — é isso que faz
o par escolhido não precisar de reajuste a cada obra nova. O melhor **do Yusupov sozinho**
é (2,5; 0,45); o par que entrou é o melhor **dos dois**, e a diferença entre eles é 11 erros
em 54 mil pares.

### O piso, e onde a parte relativa não vale

O piso existe porque a referência relativa não existe em toda linha: numa linha de uma
palavra só o vão típico é o vão entre letras, e sem piso qualquer folga viraria separação —
o defeito seria simétrico ao que a régua velha tem com algarismo.

E a parte relativa **só roda com 3 vãos ou mais**, que é o limite em que ela foi medida
(o `medir_vao` pula linha com menos de 4 caixas). O motivo é anterior ao da medição: a
mediana só estima o vão de dentro da palavra enquanto a maioria dos vãos for de dentro —
medidos, 19,4% dos pares são separação. Numa faixa de duas marcas com um espaço no meio, o
único vão **é** o espaço, a mediana passa a ser ele, e o espaço sumiria. É o cabeçalho
curto de diagrama, que é onde um buraco custa o número do exercício.

### Ponta a ponta, na página

Página 11 do Yusupov, a mesma lida com as duas réguas:

| consertou | quebrou |
|---|---|
| `1 972` → `1972` | `of the` → `ofthe` |
| `1 .♕xf7!!` → `1.♕xf7!!` | `of his` → `ofhis` |
| `5. f7` → `5.f7` | |
| `fi nds` → `finds` | |

E na 17 do Seirawan: `Londres 1 982` → `Londres 1982`, `1 4 ..Be6` → `14..Be6`,
`15.Txe8 + ,` → `15.Txe8+,`.

O custo é real e tem nome: palavra curta terminada em `f` tem folga de direita, e o vão de
tinta depois dela é pequeno. Cinco consertos contra dois estragos nesta página, e a
medição de 54 mil pares diz que a proporção se mantém.

### A entrada de tamanho paga? Medida — e a resposta é "não decide"

A F14 pediu "altura relativa junto do recorte" e a F19 mediu o remédio errado: pendurar a
geometria **depois**, como desempate sobre as candidatas. As duas fecharam com a mesma
frase pendente — a altura tem de entrar **na** rede, treinada junto. `medir_tamanho.py`
mede isso, sobre os 29.822 caracteres em que o tamanho ainda é recuperável (os `.box`
rotulados, que guardam `x1 y1 x2 y2`).

**A divisão deixa um livro inteiro de fora**, e chegar a ela custou uma medição descartada.
Com páginas sorteadas, o sorteio quase sempre põe páginas do mesmo livro dos dois lados: a
rede é testada em tipografia que já viu, a família de caixa sai a 96,2% no braço de
produção e não sobra folga para nada melhorar. O erro que esta fase persegue é o do **livro
novo**, e é ele que o turno por obra encena. Seis turnos, 15 épocas:

| entrada | tudo | família de caixa | resto |
|---|---:|---:|---:|
| 32×32 esticado (produção) | 92,01% | 92,52% ±2,86% | 91,55% |
| 32×32 esticado + tamanho | 91,59% | 91,01% ±4,89% | 91,70% |
| 32×32 **encaixado** (proporção) + tamanho | **94,31%** | 92,77% ±5,02% | **94,38%** |
| 32×32 esticado + tamanho, cru | 93,26% | 92,90% ±4,13% | 93,04% |

**Na família de caixa nenhum braço se separa da dispersão** — o melhor soma +0,25 ponto com
desvio de 5 pontos entre turnos, e o placar de trocas diz o mesmo: o encaixado conserta 334
e quebra 286.

### Mas o sinal está sendo usado, e dá para ver onde

| classe | n | esticado | +tamanho | encaixado |
|---|---:|---:|---:|---:|
| `S` | 50 | 50,0% | **74,0%** | 58,0% |
| `W` | 48 | 33,3% | **83,3%** | 54,2% |
| `0` | 179 | 34,1% | 54,7% | **59,2%** |
| `O` | 36 | 69,4% | 75,0% | 63,9% |
| `c` | 872 | **97,2%** | 87,0% | 83,4% |
| `w` | 279 | **91,4%** | 90,0% | 69,9% |

Os escalares movem exatamente as maiúsculas, que é o que a F19 previu pela tabela de d'.
O que come o ganho é o outro lado do par: a minúscula piora, e como ela é 20× mais
frequente, a média da família não se mexe. O modelo passa a **confiar demais** na entrada
nova — não é que ela não carregue nada.

**Por que este material não pode decidir**: no teste inteiro dos seis turnos há 50 `S`, 48
`W`, 36 `O` e 52 `C`. Uma dúzia de amostras que muda de lado move essas linhas inteiras, e
é daí que vem o desvio de 5 pontos. O que falta não é ideia, é **maiúscula rotulada** — e é
por isso que a gravação com tamanho é pré-requisito desta resposta, e não consequência
dela. As duas metades desta fase estão nessa ordem de propósito.

### O achado que não estava na pergunta

Preservar a proporção na imagem — o recorte encaixado em 32×32 com papel em volta, em vez
de esticado — paga **+2,8 pontos no "resto"**, fora da família de caixa, onde ninguém a
tinha procurado. Ali não há maiúscula escassa e o ganho sai da dispersão. É o oposto do que
a F106 mediu ao trocar o esticão pela caixa **sem** retreinar (a barra em pé passava a sair
`T` 0,963, porque a caixa era fora da distribuição do modelo de então); treinada nela desde
o começo, a caixa ganha.

**Não entrou em produção nesta fase**, e a razão é o tamanho do compromisso: mudar a entrada
obriga a retreinar o modelo de 608 mil amostras e a mexer nos quatro lugares que
redimensionam na leitura, e o número acima sai de um modelo pequeno treinado em 22 mil.
Fica como fase própria, com a medição já feita e o instrumento já escrito — e é a única das
três pontas que **não** depende de rerrotular nada.

### Cobertura

`tests/test_f107_tamanho.py`, 14 testes. Instrumentos: `medir_vao.py`, que refaz as tabelas
da régua do espaço, e `medir_tamanho.py`, que refaz as da entrada de tamanho.

### O que esta fase não alcança

A família de caixa continua sendo 84% dos erros de leitura, e as três pontas mexeram em
duas coisas: a régua do espaço (que é conversão, não reconhecimento) e a gravação da base
(que é semente para depois). **O reconhecimento do `s` contra o `S` está como estava**, e
sai daqui com um caminho medido e um pré-requisito nomeado, não com um conserto.

## F108 — O dicionário era cego a caixa, e por isso ninguém via o `biShop` — CONCLUÍDA

Nasceu de uma pergunta: quanto o dicionário está ajudando no problema de maiúscula e
minúscula que a F107 mediu como 84% dos erros de leitura? A resposta era **zero**, por três
motivos independentes, cada um suficiente sozinho.

### 1. A consulta baixa os dois lados

```python
def conhece(self, palavra: str) -> bool:
    b = palavra.lower()
    return b in self.palavras or b in self.do_usuario
```

Contra o léxico real de 310.465 palavras, `conhece('biShop')`, `conhece('preSSure')` e
`conhece('tHe')` são **todos verdadeiros**. Para o dicionário um erro de caixa não é erro.
O `sinalizar` — que é o produto principal da F9.1 — decide por `if lex.conhece(nuc):
continue`, então `biShop` atravessava sem acender nada.

### 2. O caminho do livro não carregava o léxico

`core/livro.py` e `core/exportar.py` não importavam `lexico`. Os únicos chamadores em
produção estavam na UI: `carregar`, `aprender_da_pagina` e `suspeitas_da_pagina`. **O DOCX e
o EPUB saíam sem nenhuma ajuda de dicionário**, nem para caixa nem para nada.

### 3. O reparo da F66 existe e não estava ligado

`lexico.reparar` tem dois chamadores: `medir_reparo.py` e os testes. Nenhum em produção — e
o mesmo vale para `juntar_hifenizadas` e `partir_colada`. Ele é de **colagem**, não de
caixa: o `_casa` compara o candidato com o lido letra a letra fora da máscara, então um `S`
no meio faz a comparação falhar em vez de disparar o conserto.

### O que passava

| livro | núcleos de 3+ letras | caixa estranha | e o dicionário aceita |
|---|---:|---:|---:|
| Seirawan (pt) | 44.322 | 13.051 (29,4%) | 4.316 |
| Yusupov (en) | 20.250 | 763 (3,8%) | 441 |

E contaminava a régua: `medir_confusao_no_livro` usa o mesmo `conhece`, então **a tabela dos
seis livros da F104 não enxerga erro de caixa**. Foi por isso que ela reportou 2 casos de
`s`→`S` no Yusupov enquanto o DOCX tem `S/s` = 0,20, três vezes o normal do inglês.

### A regra não é de dicionário, é tipográfica

Três padrões são legítimos em qualquer língua de alfabeto latino — `bishop`, `Bishop`,
`BISHOP` — e `biShop` não é nenhum deles. Isso vale igual no livro em português, onde a
lista de palavras deste projeto não vale.

**A correção não escolhe entre candidatas**: para `biShop` não há duas saídas, há uma. Isso
a põe na família do veto da F106 e não na do desempate da F19 — ela recusa o impossível.
E ela **preserva o comprimento**, que não é estética: as fatias de negrito da F105 e o vetor
de espessuras são índices sobre o mesmo texto.

**O que abre parte nova é não ser letra**, e enumerar separadores foi o erro da primeira
versão. Ela partia só em hífen e apóstrofo, e a medição cobrou: `Hulak,K` e `Spassky,B` são
nome com inicial, `abandonou.Excelente` é ponto sem espaço, `mau—Bispo` usa travessão — que
não está em `HIFENS`. Nos quatro a maiúscula abre parte, e acusá-los custava palavra certa.

### O portão funciona por causa da cegueira, não apesar dela

`conhece('biShop')` é verdadeiro e `conhece('tbitBl')` é falso: baixar os dois lados separa
exatamente prosa de lixo de segmentação. É o único uso em que essa cegueira ajuda.

Medido nas caixas que **uma pessoa confirmou** — e apertar o gabarito foi necessário no meio
do caminho: o `.box` mistura `manual` com `neural`, e contra os dois juntos `defeSa` saía ao
mesmo tempo como conserto numa página e como estrago noutra, porque o palpite do modelo
tinha sido gravado como verdade. Só as de mão, 1.687 palavras:

| | conserta | estraga |
|---|---:|---:|
| regra sozinha | 36 de 51 (71%) | 6 |
| regra + portão | **18 de 51** (35%) | **1** |

O portão é o que entrou. Sem ele a regra também acende 29% das palavras de um livro em
português, que é a "tela inteira acesa" que o próprio `Lexico.sinaliza` documenta como modo
de morte de alarme.

**O preço é o idioma.** No livro em português o portão corta os consertos pela metade (29
para 15), porque `defesa` e `branco` não estão na lista inglesa. É o mesmo teto que barra
aquele livro na F104, e quem o levanta é uma lista de português.

### O `I` se acusa e não se baixa

A correção supõe que a letra certa é a **minúscula da maiúscula que se leu**: `S` no lugar
de `s`, `O` de `o`, `C` de `c`. Para o `I` isso é falso — ele entra no lugar do **`l`**, e
`I`.lower() é `i`.

Medido, das palavras que a regra acusava e não consertava, **todas** eram desta família:

    melhor lido meIhor        principal lido principaI
    exemplo lido exempIo      planos lido pIanos

Corrigi-las trocava `pIanos` por `pianos` — que é palavra, e portanto um erro que ninguém
mais vê. Trocar um erro visível por um invisível é pior que não mexer. Nenhum conserto da
medição envolve `I`, então excluí-lo da correção não custou nada.

**Acusar continua valendo, e é onde essa família paga.** `conhece('pIanos')` é verdadeiro,
então sem esta regra ela é invisível para o projeto inteiro — e é exatamente o "erro que
produz outra palavra real, que dicionário nenhum vê" que a F104 registra como limite do
método. O padrão de caixa é sinal **ortogonal** ao dicionário.

### Onde entrou

Na linha, dentro do `livro.extrair_pagina`, e não no parágrafo: ali `pesos` ainda está ao
lado do texto e a correção preserva o comprimento, então as fatias de negrito continuam
apontando para o mesmo caractere. **É a primeira vez que o dicionário entra no caminho do
livro.** Palavra partida na quebra de linha fica de fora — o núcleo de cada metade não é
palavra, e o portão não abre.

`lex=None` é o padrão em `extrair` e `extrair_pagina`, então quem já chamava continua
recebendo o de antes; a UI passa o léxico da sessão, que já inclui o `.lexico.txt` do livro.

E no `sinalizar`, a palavra conhecida com caixa estranha passa a acender com motivo próprio
— `caixa-estranha` contra `fora-do-dicionario`. Os dois não se revisam igual: um pede que se
leia a palavra, o outro já diz que letra olhar.

No Yusupov exportado isso são **441 palavras corrigidas** — `alSo`(31), `pointS`(23),
`poSition`(19), `biShop`(15), `haS`(14).

### Cobertura

`tests/test_f108_caixa.py`, 30 testes. Instrumento: `medir_caixa.py`, que refaz as tabelas
acima e mede a regra contra as caixas confirmadas à mão.

### O que esta fase não alcança

Ela conserta o **sintoma** onde o dicionário alcança, e não o reconhecimento: a rede
continua lendo `S` no lugar de `s` com 0,898 de confiança, e o que a F107 nomeou continua
de pé. Palavra fora do dicionário, palavra do idioma errado e palavra partida na quebra de
linha ficam todas como estavam.

## F109 — Uma palavra de prosa em cinco sai com defeito, e a maioria não é do modelo — CONCLUÍDA

Uma revisão da conversão para DOCX e EPUB, pedida porque o arquivo exportado continuava
ruim depois da F107 e da F108. A spec inteira está em
[`docs/SPEC-CONVERSAO.md`](docs/SPEC-CONVERSAO.md); esta fase e as quatro seguintes são o
que ela origina.

Esta é a fase dos consertos que **não dependem de decisão arquitetural nenhuma**. Cada um
tem número medido, cada um cabe em pouco código, e nenhum deles espera pelas outras.

### A queixa, medida no arquivo que o projeto produziu

`PDF/Artur Yusupov - Chess Evolution 1 …_teste-1.docx`, exportado em 2026-08-25 15:32 —
três horas e meia antes de a F108 entrar. 20.625 palavras de prosa, tirada a notação:

| família | palavras | % |
|---|---:|---:|
| o `i` partido em haste e pingo (`Wh1.te`, `exercz.ses`) | 419 | 2,03% |
| caixa homográfica, que a F108 conserta (`alSo`, `biShop`) | 490 | 2,38% |
| palavra colada (`WThite`, `hDiagram`, `FundamentalSBy`) | 952 | 4,62% |
| dígito espúrio dentro da palavra (`y0u`, `g0t`) | 1.651 | 8,00% |
| resto fora do dicionário (`Diagrram`, `thechapter`) | 667 | 3,23% |
| **com defeito** | **4.179** | **20,26%** |

A F104 mediu 1,33% neste mesmo livro. Não é contradição: aquela régua usava
`Lexico.conhece`, que baixa os dois lados e por isso **não enxerga erro de caixa** — foi o
que a F108 diagnosticou.

### Depois da F108 a queixa de caixa deixa de ser de caixa

Refeita a conta sobre o mesmo arquivo, `arrumar_caixa` conserta **517 das 1.061** palavras
com padrão de caixa ilegítimo — 48,7%, melhor do que a própria F108 estimou. Classificando
uma a uma as 544 que sobram:

| o que é | palavras |
|---|---:|
| letra colada na frente (`hDiagram`, `eDiagram`) | 108 |
| prefixo de duas ou três letras colado (`WThite`, `PKeres`) | 99 |
| letra colada atrás (`TroitzkyA`, `KamskyG`) | 84 |
| sufixo colado (`FundamentalSBy`, `YusupovAll`) | 29 |
| **caixa de verdade que a F108 recusou** | **1** |
| não classificado | 223 |

**Sobra uma.** As outras 320 são glifo colado, e a maiúscula no meio da palavra é só a
assinatura visível de um espaço que não foi posto. Quem for atrás de caixa a partir daqui
vai procurar no lugar errado — e essa é a razão de esta fase existir antes das outras.

### Os seis consertos, e no que cada um deu

Dos seis, a F115 já tinha feito o segundo — os três reparos do dicionário que o livro não
recebia — e o quarto já existia sem que a lista soubesse: `medir_prosa.py` imprime a razão de
caixa de um livro inteiro desde a F115, e é a tabela da SPEC §1 número a número. Esta fase
faz os quatro que sobravam, e um sétimo que os quatro exigiram: **o programa não sabia em que
idioma o livro estava**, e sem isso a máscara de alfabeto não tem o que mascarar.

| conserto | onde | medido |
|---|---|---|
| 1. a máscara de alfabeto por livro | `core/alfabeto.py`, `LearningService.ler_texto(idioma)` | 75 → **0** letras fora do ASCII no Yusupov |
| 2. os três reparos que o livro não recebia | F115 | — |
| 3. a fila de coordenada fora da prosa | `diagrama.caixas_dos_rotulos`, em `livro.caixas_e_diagramas` | 29 → **0** filas soltas no Yusupov |
| 4. a razão de caixa como instrumento | `medir_prosa.py`, desde a F115 | — |
| 5. cabeçalho e rodapé fora da prosa | `livro.retirar_cabecalhos` | 293 linhas no Yusupov e 220 no Aagaard, nenhuma prosa; a prosa com defeito cai de 11,92% para 11,13% |
| 6. a régua com o terceiro balde | `medir_confusao_no_livro.contar`, `medir_troca.py` | 1,32% → **3,82%**, o fator 2,89 que a §6 previu |
| 7. o idioma do livro | `livro.idioma_do_pdf`, e a pergunta na exportação | 6 dos 8 livros pela camada de texto; os 2 escaneados perguntam |

A medição de antes e depois é o Yusupov Chess Evolution 1 inteiro, 264 páginas, relido
pelo `medir_prosa.py --pdf` numa árvore em HEAD e na árvore de trabalho, com o mesmo modelo
copiado para as duas — que é a régua que a F115 deixou, e o cuidado que ela custou.

### 1. A máscara, e um número que já tinha caído antes dela

A SPEC §2.5 contou **1.112** letras acentuadas no DOCX do Yusupov. O mesmo livro relido
hoje, em HEAD, sem máscara nenhuma, dá **75, em 16 letras** — o DOCX era de 25/08, e o modelo
é o terceiro desde então (a F115 registrou os três). A maior parte da queixa era do modelo, e
o retreino a levou.

O que sobra é o que a máscara alcança: com `--idioma en`, saem **0**.
As 16 de antes eram `ô` 20×, `Š` 9×, `é` 8×, `ä` 8×, `ö` 6× — nenhuma legítima num livro em
inglês. E no Aagaard, 13 em 8 letras → 0.

Ela entra em `ler_texto` no molde exato do veto da F106, e os dois crivos valem **juntos**: a
candidata que o idioma admite ainda tem de caber no recorte, e sem candidata que passe nos
dois fica a leitura que havia — inventar uma classe que a rede não ofereceu seria o voto que
a F19 mediu e descartou. O caminho que passa não paga nada: a segunda passada pela rede só
acontece quando a primeira leitura é vetada. E o que se mascara é a **letra latina fora do
ASCII**, e não `isalpha()`: o `Δ` é letra para o Python e é símbolo de análise para o livro.

O que a máscara custa é dito em `core/alfabeto.py`: num livro em inglês, `café` e `Šahović`
saem sem o acento. A spec já tinha aceitado esse preço, e o número acima é o motivo.

### 3. A fila de coordenada, e por que a margem não a via

`Diagrama.exclusao` tira do texto a caixa **inteiramente** dentro de 1,4 alturas de caractere
em volta do tabuleiro. A letra `a`–`h` impressa a 1,2 alturas da borda tem o pé a 1,7 — a
margem não a contém, e ela chegava ao texto como uma linha de oito caracteres. É a mesma
assimetria que a F95 achou na legenda de baixo do Nunn ("nasce a 1,29 escalas e desce até
2,3"), do outro lado.

`diagrama.caixas_dos_rotulos` usa a régua de `ler_rotulos` — a caixa do tamanho de uma
marca, **contida** na largura do tabuleiro, com a borda voltada para ele dentro da faixa — e
só nos lados em que `ler_rotulos` achou rótulo. A continência é o que a separa da prosa da
coluna vizinha, que só se sobrepõe. No Yusupov relido: **29** filas soltas em
HEAD (22 delas `f g h`, que é a metade da fila que a coluna da direita deixava escapar) e **0** depois.

### 5. O cabeçalho de página, que só o livro inteiro reconhece

A F104 mediu que ele é o maior contribuinte de erro de três dos seis livros, e não é erro de
leitura: `Attacking Manual - Volume 1` no alto de toda página par multiplica um erro só por
centenas de páginas. E não é prosa — no arquivo exportado não há página, e um `Chapter 3`
solto a cada trinta linhas é ruído no meio do texto.

Numa página só ele é uma linha curta como outra qualquer. O sinal é o do livro — o mesmo
texto, na mesma margem, página atrás de página —, e por isso `retirar_cabecalhos` é uma
passada à parte no `extrair`, no molde de `partir_coladas`, e roda **antes** dela e do
negrito: o vocabulário do livro e o peso redondo de cada caractere medem-se sobre a prosa.

**E ela olha a linha impressa, e não o parágrafo — e isso foi medido, não previsto.** A
primeira versão tirava o parágrafo inteiro quando ele era uma linha só, e no Yusupov isso
bastava. No Aagaard tirou **12 em 263 páginas**: ali o cabeçalho está colado ao primeiro
parágrafo em quase toda página — `8 The Attacking Manual – Volume 1 Having thought this
through…` —, porque a régua do salto vertical (F103) não o separa do corpo. `Paragrafo`
passou a guardar onde cada linha impressa começa no texto (`inicios`) e onde o parágrafo
acaba na página (`pe`), e `_cortar` tira a linha com os dois vetores da F105 e da F115 no
mesmo passo — o teste que trava isso é o mesmo molde dos de alinhamento da F115.

Quatro réguas, e a repetição sozinha não basta:

- **na margem** — a linha começa nos 12% de cima da página, ou o parágrafo acaba nos 12% de
  baixo (`MARGEM_DE_PAGINA`). É o que a ordem dos blocos não diz: numa página de duas
  colunas o rodapé centrado cai na coluna da esquerda, no meio da lista. Por isso
  `Paragrafo` ganhou `topo` e `pe`, e `PaginaExtraida`, `altura`.
- **curta** (até 8 palavras), **com letra ou número** — o `=` que o filete decorativo vira
  quando é lido tem a assinatura vazia do número de página, e não é número de página —,
  **fora de parênteses** e **sem lance**. As duas últimas vieram de falsos positivos
  medidos: `(see page 43)` no alto de cinco páginas do Aagaard é remissão, e `20...♗d3!`
  passava pela régua de lance porque `parece_lance` lê `Bd3!` e o livro imprime a figurina
  — a tradução é a mesma que `notacao.Simbolo` faz, e `_lance_limpo` a faz aqui.
- **em três páginas ou mais** (`PAGINAS_DE_CABECALHO`), e não numa fração do livro: o
  cabeçalho de capítulo muda a cada capítulo, e uma fração de um livro de 2.612 páginas o
  deixaria passar inteiro.

A assinatura tira o número — `Chapter 3 · 37` e `Chapter 3 · 38` são o mesmo cabeçalho — e o
número de página sozinho vira a assinatura vazia, que é a de todo número de página. É
também o que faz `14 The Attacking M` e `100 The Attacking Ma` serem o mesmo cabeçalho
mesmo com o fim derrubado por confiança de um jeito em cada página.

O que saiu, conferido a olho:

| livro | páginas | linhas retiradas | o que eram |
|---|---:|---:|---|
| Yusupov · Chess Evolution 1 | 264 | **293** | 151 números de página; 61 números com o filete lido junto (`= 12`); `Exerc1.ses` 23× e `S0lut1.0ns` 12×, em vinte grafias — o cabeçalho traz o `i` partido da família A —; e os títulos de capítulo: `Tactics 1`, `Positional advantages`, `F1.nal`, `ndex ofgames` |
| Aagaard · Attacking Manual I | 263 | **220** | `N The Attacking M` 91× com o fim derrubado por confiança; `Chap` e `Cha` 97×, idem; `Chapter 9 229` 13×; `face 13` (o *Preface*). Nenhum número de página solto: ali ele está dentro do cabeçalho |

Duas rodadas antes desta tiveram falso positivo, e as duas réguas que os mataram estão
acima: seis linhas de variação (`20...♗d3!`) e cinco remissões (`(see page 43)`), as onze no
Aagaard. Nesta rodada não há linha de prosa nas duas listas.

A prosa com defeito do Yusupov (`medir_prosa.py`, as cinco famílias) cai de **11,92% para
11,13%** só com o cabeçalho fora — e é o que a F104 tinha dito: o cabeçalho mal lido
multiplicado por 264 páginas era a forma mais frequente de erro do livro.

E o que foi retirado **não é silencioso**, pela mesma razão do reparo da F115: cada página
guarda o texto em `PaginaExtraida.cabecalhos`, e o relatório do fim da exportação diz
quantos saíram e os três mais frequentes.

### 6. A régua, com o balde que faltava

`medir_confusao_no_livro.contar` devolve quatro coisas onde devolvia três. A palavra que o
dicionário conhece **e** tem a caixa estranha (`lexico.caixa_estranha`) não é acerto nem entra
no prior: vai para o balde dela. Refeito sobre o `_teste-1.docx`:

| | palavras | % |
|---|---:|---:|
| prosa | 17.692 | |
| atribuída a uma confusão de caractere (o número publicado) | 234 | 1,32% |
| caixa errada, que `conhece` absolvia | **441** em 215 formas | 2,49% |
| as duas | 675 | **3,82%** |

`alSo` 31×, `pointS` 23×, `poSition` 19×, `biShop` 15× — as mesmas formas que a §6 contou à
mão, no mesmo número. **A tabela dos seis livros da F104 continua não testada**: ela precisa
das duas colunas, e refazê-la é reler seis livros com o modelo de hoje, que não é o modelo
dela. O instrumento está pronto para quem o fizer.

`medir_troca.py` deixou de baixar os dois lados, e ganhou a coluna `caixa`. Refeito nas
páginas rotuladas, com o modelo de hoje:

| lista | palavras | pego | escondido | só caixa | recall | alarme |
|---|---:|---:|---:|---:|---:|---:|
| idioma | 73.447 | 36 | 59 | **16** | 37,9% | 6,8% |
| idioma + nomes | 310.465 | 31 | 64 | **16** | 32,6% | 3,8% |

Um quarto dos erros que a lista esconde é só de caixa — os que ela **nunca** poderia pegar,
porque não tem caixa, e que a F108 pega por outro caminho. Os números não se comparam com a
tabela da F9.1 (58,5% e 53,8%): o modelo é outro, e a régua é outra. E a lista de escondidos
mostra o que a F9.1 já avisava sobre a verdade remontada — `'theory' <- 'theoy'` é o
**rótulo** com a letra a menos, não a leitura.

E a inicial trocada, que nenhum instrumento via, ganhou a tabela em `medir_prosa.py`: a taxa
de inicial maiúscula por letra. No Yusupov relido ela diz `b` 49,5%, `v` 49,3%, `d` 42,9% —
que é `Black`, `Very` e `Diagram`, e é legítimo. É o que a §6 previu: **ela só fala contra um
livro nativo**, e a comparação fica para quem tiver o par.

### 7. O idioma do livro

`lexico.carregar` tinha `idioma="en"` e `exportar.para_epub` tinha `IDIOMA_PADRAO = "en"`,
e ninguém passava outra coisa a nenhum dos dois: todo livro deste projeto era inglês. A
máscara de alfabeto não pode viver com isso — a máscara errada apaga o `ç` de um livro
inteiro.

`livro.idioma_do_pdf` lê a **camada de texto** do PDF em quarenta páginas espalhadas pelo
livro e conta palavras que só um dos dois idiomas escreve (`the`, `with` / `que`, `não`).
Nunca chuta: responde só com três vezes mais ocorrências de um lado. Nos oito livros do
corpus:

| livro | camada | resposta |
|---|---|---|
| Yusupov · Chess Evolution 1 | sim | en |
| Yusupov · Complete | sim | en |
| Aagaard · Attacking Manual I | sim | en |
| Nunn · Secrets of Rook Endings | sim | en |
| Dvoretsky · Endgame Manual | sim | en |
| Darcy Lima · A Estratégia | sim | **pt** |
| Seirawan · Xadrez Vitorioso | não | `None` |
| Razuvaev · Akiba Rubinstein | não | `None` |

Os dois `None` são as duas digitalizações de verdade (F110), e ali a exportação **pergunta**
— uma caixa a mais, e só nesse caso. O idioma vai para três lugares: a máscara
(`leitor_de_texto`), o `dc:language` do EPUB, e o `<w:lang>` do DOCX, que era uma das doze
linhas da tabela da F111 e entrou aqui porque o parâmetro já estava na mão.

### O que esta fase não alcança

O mesmo que ela disse ao abrir: **a família A** (o `i` partido, 350 palavras no Yusupov
relido) e **a família D** (o dígito dentro da palavra, 456), que são de segmentação e de
reconhecimento e estão na F110, na F112 e na F113. Da família C, o que `partir_coladas` não
alcança.

### Onde está

- `core/alfabeto.py`, novo — a máscara. `LearningService.ler_texto` ganhou `idioma`, e
  `leitor_de_texto` o prende para o livro inteiro.
- `diagrama.caixas_dos_rotulos`, nova, chamada de `livro.caixas_e_diagramas` depois do
  ornamento e antes da legenda.
- `livro.retirar_cabecalhos`, nova, com `Paragrafo.topo`, `Paragrafo.linhas_impressas`,
  `PaginaExtraida.altura` e `PaginaExtraida.cabecalhos`; chamada do `extrair` antes de
  `partir_coladas`.
- `livro.idioma_do_pdf`, nova. `ui/main_window.py` a chama, pergunta quando ela não
  responde, e passa o idioma aos três consumidores; o relatório do fim diz o idioma e os
  cabeçalhos retirados. `exportar.para_docx` ganhou `idioma`.
- `medir_confusao_no_livro.py` (o terceiro balde), `medir_troca.py` (a coluna `caixa`) e
  `medir_prosa.py` (`--idioma`, a fila de coordenadas, as letras fora do ASCII, a inicial
  maiúscula por letra e os cabeçalhos retirados) são a régua desta fase.

`tests/test_f109_alfabeto_e_cabecalho.py`, 35 testes, e um a mais na F104 para o balde. A
suíte sai de 1.850 para 1.886, verde.

---

## F110 — O livro já trazia o texto, e o projeto o leu da imagem — CONCLUÍDA (a camada tipográfica; o OCR de fábrica continua no OCR)

`core/livro.py:1124`, na docstring de `extrair_pagina`, na letra: *"Uma página do PDF vira
parágrafos e figuras, **lendo só a imagem**."*

### O que isso custa, medido nos oito livros

Página com mais de 200 caracteres de camada de texto:

| livro | páginas | com camada | % |
|---|---:|---:|---:|
| Dvoretsky · Endgame Manual | 816 | 815 | **99,9%** |
| Nunn · Secrets of Rook Endings | 354 | 352 | 99,4% |
| Darcy Lima · A Estratégia | 319 | 317 | 99,4% |
| Aagaard · Attacking Manual I | 263 | 236 | 89,7% |
| Yusupov · Chess Evolution 1 | 264 | 214 | 81,1% |
| Yusupov · Complete | 2.612 | 1.992 | 76,3% |
| Seirawan · Xadrez Vitorioso | 230 | **0** | 0% |
| Razuvaev · Akiba Rubinstein | 604 | **0** | 0% |

**3.926 das 5.462 páginas — 72% — já trazem o texto, e o projeto reconhece todas elas a
partir do pixel.** O pior livro da tabela da F104, o Dvoretsky com 3,93%, tem camada em 815
das 816 páginas.

### E a camada é boa — a mesma prosa, pelos dois caminhos

Filtro idêntico dos dois lados: linha com pelo menos 25 caracteres e pelo menos 90% de
latim básico, que é o que separa prosa de tabuleiro.

| caminho | linhas de prosa | palavras | fora do dicionário |
|---|---:|---:|---:|
| camada de texto do PDF (`fitz`) | **2.711** | 16.306 | **3,13%** |
| OCR → o DOCX exportado | 313 | 5.234 | **7,49%** |

São 2,4× a taxa de erro. E o outro número é pior: o OCR produz **313 linhas que parecem
prosa contra 2.711**, com o mesmo filtro — oito em cada nove linhas saem tão danificadas
que nem chegam a ser julgadas.

> **camada:** `Artur's systematic and professional approach to analysing games was the decisive factor`
>
> **DOCX:** `Diagrram 2-5 We can see the difference between the bishops; the kni ht 8 id t t f th hit`

### As duas peças já existem e não se falam

`core/chess_pdf_processor.py` percorre `page.get_text("dict")`, distingue span de prosa de
span de diagrama (`is_diagram_span`, `is_block_a_diagram`) e mapeia a codificação própria
das fontes de xadrez para Unicode; `core/mapa_glifos.py` guarda esses mapas; a §4.2 da SPEC
descreve tudo. Só que esse caminho existe para **escrever outro PDF**, e o caminho do livro
nunca o chama.

O que falta é uma função que devolva `PaginaExtraida` em vez de escrever PDF. O
intermediário não muda, e por isso `exportar.py` não muda.

*Corrigido na implementação (2026-09-22): as duas peças não faziam o que o parágrafo acima
diz.* `is_diagram_span` é um esboço que devolve sempre `False`, e `is_block_a_diagram` exige
quatro linhas num bloco — no Dvoretsky cada casa é um bloco de uma linha só: simulado na
p. 21 (`analisar_substituicao(dry_run=True)`), nenhum diagrama é reconhecido e os 128 spans
de Chess-Merida entram como figurina solta, cada casa apagada e reescrita. `mapa_glifos` não
guarda mapa nenhum: ele reescreve o ToUnicode de uma cópia do PDF, com o modelo de glifos. A
função nova (`core/pdf_nativo.py`) não usa nenhuma das duas.

### A escolha é por página, e o de hoje fica de reserva

Página sem camada, ou com camada que a régua recuse, cai no OCR de sempre. O Seirawan e o
Razuvaev — 834 páginas, e as únicas digitalizações de verdade do corpus — continuam
inteiramente no caminho de hoje.

### O que se perde, e tem de ser dito em voz alta

**A procedência por caractere.** Quem lê do texto não tem box, não tem confiança, não
alimenta a coleta e não enfileira na revisão. A página lida do texto **sai do circuito de
treino**, e o relatório precisa dizer quantas páginas vieram de cada caminho — senão a base
de treino encolhe em silêncio e ninguém liga uma coisa à outra.

### O que esta fase não alcança

Os 28% de páginas sem camada, que são o Seirawan e o Razuvaev inteiros. Ali só a F112
ajuda.

### O que a régua achou: 72% com camada, e um livro só com o texto do livro (2026-09-22)

A tabela da abertura contou **camada**, e camada não é texto do livro. Seis dos oito livros
são digitalizações que passaram pelo Acrobat: o ClearScan vetoriza o glifo digitalizado numa
fonte sintetizada (`Fd350139`) e dá a ela o Unicode que o OCR dele achou — a prosa quase
limpa, a notação ilegível, que é o que a docstring de `core/livro.py` documenta —, e o Paper
Capture põe o OCR como texto **invisível** sobre a imagem. A régua de `core/pdf_nativo.py`
recusa pelo que o OCR de fábrica deixa no arquivo, e não pela qualidade do texto (uma régua
de dicionário aprovaria a prosa do ClearScan). `scripts/medir_camada.py`, as 8.334 páginas de
`PDF/` em ~23 s:

| livro | páginas | lidas da camada | recusadas, e por quê |
|---|---:|---:|---|
| Dvoretsky · Endgame Manual (2025) | 816 | **815** | 1 sem camada (a capa) |
| Nunn · Secrets of Rook Endings | 354 | 0 | 352 fonte do ClearScan, 1 invisível, 1 sem camada |
| Darcy Lima · A Estratégia | 319 | 0 | 318 texto invisível (Paper Capture), 1 sem camada |
| Aagaard · Attacking Manual I | 263 | 0 | 243 fonte do ClearScan, 15 sem camada, 5 invisível |
| Yusupov · Chess Evolution 1 | 264 | 0 | 209 fonte do ClearScan, 51 invisível, 4 sem camada |
| Yusupov · Complete | 2.612 | 0 | 1.873 fonte do ClearScan, 416 invisível, 322 sem camada |
| Seirawan · Xadrez Vitorioso | 230 | 0 | 230 sem camada |
| Razuvaev · Akiba Rubinstein | 604 | 0 | 604 sem camada |

As cópias "mapeamento corrigido" e a amostra do ABBYY em `Convertidos/` também saem inteiras
recusadas. **As quatro páginas de referência do A/B continuam indo ao OCR** — o corpus de
medição não muda (`test_a_regua_recusa_as_digitalizacoes_do_corpus`). E o livro que a régua
aceita é justamente o pior da F104 (3,93% fora do dicionário pelo OCR).

### O Dvoretsky, lido do arquivo

O PDF é nascido digital: Times New Roman no texto, as figurinas na `SemFigNormal` (o `K`
*é* o rei; a chave de símbolos da p. 788 dá `²`→`⩲`, `™`→`□`, `…`→`Δ`, `„`→`⇄`, `§`→`♙`), e
cada diagrama em **Chess-Merida, uma casa por glifo** — `*` casa clara vazia, `+` escura, `l`
rei preto em casa clara —, com os rótulos `8`–`1` e `a`–`h` em Arial em volta, o número do
diagrama embaixo e a letra de quem joga (`W`, `B`, `W?`, `B?`) embaixo dele. Medido nos
1.273 diagramas: **315 de 315** letras concordam com o primeiro lance do texto que as segue.

`pdf_nativo.extrair` no livro inteiro, 815 páginas em **53 s** (66 ms/página, quase tudo o
desenho dos diagramas):

| | |
|---|---|
| diagramas | **1.273**, todos com o FEN decodificado da fonte — a paridade das casas é a prova do mapa |
| orientação | confirmada pelas coordenadas nos 1.273 |
| lado a jogar | lido da legenda em 1.235 (780 `w`, 455 `b`); 38 por convenção, declarada |
| legendas | todo tabuleiro com a sua, inclusive as 25 que a paginação mandou para a página seguinte e as de dois diagramas lado a lado |
| títulos | os 15 capítulos como `<h1>` (`Chapter 1 Pawn Endgames`), 488 títulos de seção e 334 cabeçalhos de diagrama como `<h2>` |
| mobília | nenhuma linha de conteúdo retirada (o livro não imprime cabeçalho nem número de página na camada) |

A camada contra o OCR de produção, **nas mesmas 12 páginas** (21, 22, 46, 100, 158, 250,
350, 450, 550, 650, 750, 783), com a camada como referência — num livro nascido digital ela
é o texto que o autor escreveu (`scripts/medir_camada.py --comparar`):

| | OCR (cadeia + Tesseract) | camada |
|---|---:|---:|
| CER prosa / notação / total | 1,52% / 1,82% / **1,58%** (WER 2,97%) | 0 por construção |
| diagramas com a posição certa | 20 de 20 | 20 de 20 |
| diagramas com o lado certo | **13 de 20** — os 7 outros saíram `w` onde a legenda diz `B` | 20 de 20 |
| tempo por página | 3,71 s | **0,08 s** (46×) |

O EPUB das páginas 15–60 lidas da camada passa no `epubcheck` 5.3.0 sem uma mensagem, com o
sumário por capítulo (`Foreword`, `Chapter 1 Pawn Endgames`) que a F111 deixou para cá.

### Onde está

- `core/pdf_nativo.py`, novo. A régua (`avaliar_pagina`, `avaliar`, `amostrar`: texto
  invisível, fonte do ClearScan ou do Tesseract, glifo sem Unicode, fonte de xadrez sem mapa,
  produtor de OCR, página girada, texto sobre a imagem da página inteira); a página
  (`extrair_pagina`: glifos do `rawdict`, colunas pela régua do OCR —
  `BoxService.detectar_colunas` —, parágrafo por recuo/salto/corpo, hífen de fim de linha só
  sai com o dicionário, negrito da fonte, figurina herdando o negrito do lance, título de
  capítulo pelo corpo e de seção isolado na coluna, diagrama da fonte com rótulos, cabeçalho,
  legenda e lado, imagem embutida lida por `diagrama.ler` com o porteiro da F58 quando é
  tabuleiro); o livro (`ligar_legendas`, `retirar_mobilia`, `extrair` → `Extracao` com as
  páginas e os vereditos — sem modelo nem Tesseract).
- `core/livro.py`: `extrair(camada="nunca"|"auto"|"sempre")` escolhe por página; o padrão é
  `"nunca"`, para os instrumentos do OCR não passarem a medir outra coisa.
  `PaginaExtraida.leitura` (`"imagem"`/`"camada"`) e `Figura.marcas` (o `x` das casas-chave).
  `retirar_cabecalhos` pula a página da camada — a assinatura vazia de `2019.` e de `1-17`
  somava com a dos números de página e apagava 16 linhas de conteúdo do Dvoretsky.
- `core/editorial_adapters.py` leva `leitura` e `marks` de ida e de volta, e a evidência da
  página da camada é `pdf_text`; `core/editor/importar_ir.py` passa as marcas ao diagrama do
  editor; `core/editorial_legacy.OpcoesDeLeitura.camada`.
- A caixa de exportação ganha "Ler do próprio PDF as páginas nascidas digitais", ligada e
  lembrada, com a amostra da régua; o relatório das duas exportações conta as páginas da
  camada. A caixa do livro cresceu 7 px (578), e a do documento editorial ficou nos 655 — o
  quadro novo foi para a coluna da direita, que era a mais baixa.
- `scripts/medir_camada.py`: a régua nos livros, e `--comparar` para a camada contra o OCR.
- `tests/test_f110_camada.py`, 51 testes (os do corpus pulam sem o PDF), dois deles pela janela: a caixa e a ação de menu inteira.

### A revisão

Uma revisão independente do módulo, com os dois defeitos que confirmou reproduzidos em PDF
sintético: **o glifo solto da fonte de diagrama vazava para a prosa** — a casa vazia `+`
fora de tabuleiro saía como `+` no meio da frase (agora só a peça solta fica, como figurina;
o resto some) — e **a legenda livre do diagrama de cima engolia o cabeçalho do de baixo**
quando os dois estão empilhados perto (agora a linha centrada na janela de cabeçalho do
tabuleiro de baixo é dele). Das quatro possíveis, três foram corrigidas: o **número solto**
(`37`) deixou de ser legenda estrita — era o fólio do pé virando legenda do último diagrama,
e o do alto sendo religado da página anterior; só vale colado ao tabuleiro —, a vizinhança
que junta glifos em tabuleiro caiu de 1,5 para 1,2 casa (dois diagramas lado a lado a menos
de meia casa viravam um grupo só), e o redesenho do lado religado ganhou a mesma proteção
dos outros. A quarta era contagem de caracteres fora por um espaço, corrigida. Cada
correção tem teste, e os dois confirmados foram conferidos falhando sem ela. O livro inteiro
saiu idêntico depois.

### O que se perde, cumprido

A página da camada não tem box nem confiança por glifo: não entra na coleta, não enfileira
linha na revisão, e o relatório diz quantas vieram da camada. Os mapas de fonte são os vistos
num PDF — Chess-Merida/MERIFONT, SkakNew-Diagram, SemFig —; um diagrama numa fonte de xadrez
sem mapa manda a página inteira para o OCR, e acrescentar uma fonte é uma linha em
`FONTES_DE_DIAGRAMA` (mais o mapa em `core/dados/fontes_de_diagrama.json`).

### O que fica

A prosa do ClearScan. Ela é quase limpa e a notação dele não é; ler a prosa da camada e o
lance do OCR na mesma linha é outra fase, e precisa de medida antes — a `FusionEngine`, que
preferia a camada na notação, foi o que a revisão de 2026-09-18 derrubou.

---

## F111 — O arquivo abre no Word e não é um livro — CONCLUÍDA

Isto não é reconhecimento. É o arquivo julgado como arquivo, e é o único defeito que o
usuário vê **mesmo quando o OCR acerta**.

### Não há capítulo

O DOCX tem 390 parágrafos com estilo `Heading 2`, e **todos são legenda de diagrama** —
`Diagram 1-3`, `Ex. 1-6`. O painel de navegação do Word mostra 390 legendas e nenhum
capítulo. `Paragrafo.titulo` existe desde a F2.6, quem o marca hoje é a faixa do diagrama,
e nada detecta título de seção na página.

O EPUB é pior, e há um exportado para conferir — o `Kasparov - The Dynamic Benko Gambit
(2012).epub` da raiz:

| | |
|---|---:|
| XHTML no arquivo, um por página do PDF | 322 |
| entradas no `nav.xhtml` | **322**, e todas dizem "Página N" |
| títulos, todos `h2`, todos legenda de diagrama | 122 |
| `dc:creator` | **ausente** |
| `dc:identifier` | **`pyboxeditor`** |

O Yusupov Complete, de 2.612 páginas, sai com um sumário de 2.612 entradas de número de
página.

**E nada disso é erro que um validador acuse — medido, e não suposto.** Rodado o
`epubcheck` 5.3.0 (instalado nesta máquina, Java 25):

| arquivo | válido | mensagens |
|---|---|---:|
| Kasparov · Benko Gambit, modo de imagem, 322 páginas | **sim** | **0** |
| diagrama em modo de fonte, SkakNew-Diagram | **sim** | **0** |
| diagrama em modo de fonte, ChessMerida-Diagram | **sim** | **0** |

Controle negativo, para o zero valer alguma coisa: tirado o `dc:language` de uma cópia, ele
acusa `RSC-005`; posto um `&` solto num XHTML, acusa `RSC-016` como fatal. A ferramenta
funciona — o arquivo é que está conforme.

**Um arquivo pode estar conforme e não ser um livro.** Nenhum defeito desta fase é
alcançável por validador de esquema: são de **editoração**, e quem os pega é o Ace da DAISY
ou uma pessoa abrindo o arquivo.

E o `dc:identifier` é defeito de conformidade, não de gosto: ele é o `unique-identifier` da
publicação e está literal em **todo** livro que este projeto exporta. Dois livros saem com a
mesma identidade, e o leitor que os catalogue por ela trata os dois como um só.

### O itálico é perdido inteiro

**0 runs em itálico e 0 `smallCaps` em 36.442 runs.** Onde o PDF declara o estilo — o
Dvoretsky e o Darcy Lima são os dois cujas fontes não são subconjuntos anônimos —, o
itálico é 1,6% a 4,0% dos caracteres e o negrito 9,6% a 11,3%. Num livro de xadrez o
itálico marca variação, comentário e nome de abertura; o versalete marca nome de jogador.

O negrito chega ao arquivo desde a F105 — 12.436 runs, 17,5% dos caracteres. O itálico não
tem sequer campo onde morar: `Paragrafo` tem `negrito` e `pesos`, e nada mais. **A F105 é o
molde**: ela mediu se o sinal existia antes de projetar a detecção, e o mesmo método serve
para a inclinação.

### O que mais se perde

Nenhuma aspa curva no arquivo — 0 contra 17 aspas retas. `dcterms:modified` fixo em
`2026-01-01T00:00:00Z`.

### O que já está certo, e não se mexe

O EPUB é EPUB 3 com `nav` declarado, `dc:language` do **livro** e não do programa, `alt`
das figuras com o FEN da posição, fonte de símbolos embutida só quando o texto precisa, e
`ibooks:specified-fonts` para o Apple Books não trocar a fonte do tabuleiro. O DOCX embute
fonte com a ofuscação do ECMA-376 §15.2.13, casa corpo e entrelinha em meio ponto para o
tabuleiro fechar quadrado, e põe o FEN no `descr` do `docPr`.

**A mecânica dos dois formatos é competente.** O que falta é estrutura de livro e atributo
do impresso — não OOXML nem OPF.

### Os defeitos de arquivo, todos reproduzidos

| defeito | onde | conserto |
|---|---|---|
| `<dc:creator>python-docx</dc:creator>`, `dcterms:created` em **2013-12-23**, e o `thumbnail.jpeg` **byte a byte** igual ao do `default.docx` da biblioteca | `ui/main_window.py:1819-1823` é o único chamador e não passa `autor` | passar autor e datas |
| as oito linhas do diagrama entram no XHTML **sem escape** — **latente**: as duas fontes de hoje (`0ABJNOPQRSZabklnoprs` e ` +BKOPRTVWblmnopqrtv`) só emitem caractere seguro; dispara no dia em que uma terceira mapear `<`, `>` ou `&` | `exportar.py:288` e `:300` | `html.escape`, como as outras seis saídas do módulo já fazem |
| figurina em célula de tabela sai **sem a fonte** no DOCX: o run vem sem `w:rPr` e o Word desenha `♖` na Calibri | `exportar.py:1025-1027` — `celula.text` | o caminho gêmeo do EPUB acerta e tem teste (`test_f72_tabela_no_epub.py:233-244`) |
| diagrama em modo de fonte **sem texto alternativo nenhum** — 501 tabelas no livro medido | `exportar.py:957-1003` | `w:tblCaption` e `w:tblDescription` |
| **nenhum FEN chega ao `descr`**: os 151 do caminho de imagem são duas cordas só, `Cabeçalho do diagrama` (120×) e `Diagrama` (31×) | `exportar.py:251-262` devolve o FEN; ele chega vazio | achar por que `figura.fen` vem vazio |
| `lang` ausente no `<html>` e no `nav.xhtml` — a regra `html-has-lang` do axe **não aceita `xml:lang`**, e mapeia para WCAG 3.1.1 nível A | `exportar.py:421-423` e `:632-635` | duas linhas |
| `dc:identifier` literal `pyboxeditor` em **todo** livro exportado | `exportar.py:517` | uma URN por livro |
| `dcterms:modified` fixo em `2026-01-01T00:00:00Z` | `exportar.py:627` | `SOURCE_DATE_EPOCH`, caindo para a data corrente |
| `<h2>` **sem `id`**, e nenhum `<h1>` no livro inteiro — pular de nada para `h2` é violação de hierarquia | `exportar.py:412` | âncora, e promover capítulo a `h1` |
| hífen de fim de linha chega ao arquivo — **49 medidos** (`be- cause`, `oppo- nent`) | `livro.py:862` | `juntar_hifenizadas`, que a F109 liga |
| o DOCX sai no template nu: Carta, Calibri 11, `<w:ind>` = 0 em 8.499 parágrafos, sem justificação — e o EPUB do mesmo livro sai justificado com recuo de 1,2 em | `exportar.py:941` é um `Document()` nu | um desenho de página só para os dois formatos |
| ~~`para_docx` **não tem parâmetro de idioma**, e `<w:lang>` aparece 0 vez~~ — **feito na F109 §7**, junto com o idioma do livro | `exportar.py:845-850` | passar o idioma que o EPUB já recebe |

### A acessibilidade deixou de ser opcional na Europa em 28/06/2025

EPUB Accessibility 1.1, Recomendação W3C de 17/10/2024, §2.2, na letra: *"All EPUB
publications MUST include Schema.org accessibility metadata in the package document that
exposes their accessible properties, **regardless of whether** the publications also meet
the accessibility or optimization requirements."* Este projeto não escreve nenhum
`schema:*`.

### O que entrou, linha a linha

A tabela dos defeitos de arquivo era de doze linhas, e a acessibilidade e a cobertura eram
mais duas seções. Está tudo feito, menos o itálico — que não é defeito de arquivo, é
reconhecimento, e tem a F105 por molde. E entrou o que a tabela chamava de "não há
capítulo", que é a única coisa desta fase que **lê a página**.

| defeito | o que entrou |
|---|---|
| `<dc:creator>python-docx</dc:creator>`, `dcterms:created` em 2013, miniatura da biblioteca | `_propriedades_do_docx`: título, autor, data de hoje (ou `SOURCE_DATE_EPOCH`), descrição vazia — e a miniatura sai **pela relação**, não pelo zip: o `python-docx` só escreve a parte que alguém aponta |
| as oito linhas do diagrama sem escape no XHTML | `html.escape` nas duas saídas de `_diagrama_em_texto`, com teste que põe `<&>` numa linha e passa o XHTML pelo `ElementTree` |
| figurina em célula sem a fonte no DOCX | a célula é escrita por `escrever_paragrafo`, o mesmo caminho da prosa, com `p=celula.paragraphs[0]` |
| diagrama em modo de fonte sem texto alternativo | `w:tblCaption="Diagrama"` e `w:tblDescription=<FEN>` no `tblPr` da `_caixa_do_diagrama` — os dois últimos filhos do esquema, e por isso cabem depois do `tblLook` |
| nenhum FEN chega ao `descr` | **não era defeito**: os 151 do livro medido eram todos `origem="recorte"`, e o recorte não tem posição lida — `Figura.fen` é "quando ela foi lida e mereceu confiança". O DOCX medido foi exportado sem redesenhar |
| `lang` ausente no `<html>` e no `nav.xhtml` | `lang` ao lado do `xml:lang`, nos dois |
| `dc:identifier` literal `pyboxeditor` | `identificador_de`: `urn:uuid:` de um UUID v5 sobre autor e título — o mesmo livro exportado de novo mantém a identidade, e dois livros nunca a repartem |
| `dcterms:modified` fixo em `2026-01-01` | `agora()`: `SOURCE_DATE_EPOCH` quando existe, e a hora corrente quando não. Serve ao DOCX também |
| `<h2>` sem `id`, e nenhum `<h1>` | `ancora()`: `t{página}-{n}` nos dois níveis; o capítulo (`Paragrafo.nivel == 1`) sai `<h1>` e `Heading 1`, e o `nav.xhtml` lista **os capítulos** com âncora — e cai para "Página N" só no livro sem capítulo detectado |
| hífen de fim de linha no arquivo | F115 |
| o DOCX no template nu | `_desenho_da_pagina`: Georgia 11, justificado, recuo de 1,2 em, margem de 2,2 cm — o que a CSS do EPUB já dizia. O primeiro parágrafo depois de figura, tabela ou título sai sem recuo, como o `p.primeira` de lá |
| `para_docx` sem idioma | F109 §7 |

E os três da F115:

| defeito | o que entrou |
|---|---|
| `exportar.trechos` descarta faixa fora de ordem | `sorted(negrito)` na entrada, com teste |
| duas tabelas coladas viram uma no Word | o `separador()` de 1 pt que o diagrama em modo de fonte já tinha sai também depois de toda `Tabela` |
| símbolo que a fonte de recurso não cobre sai mudo | `simbolos_sem_fonte(texto)`, e o relatório do fim da exportação lista o que ficou mudo |

### A acessibilidade, declarada

`schema:accessMode` (`textual`, e `visual` quando há figura), `accessModeSufficient`
`textual`, `accessibilityFeature` `alternativeText`, `structuralNavigation` e
`readingOrder`, `accessibilityHazard` `none`, e um `accessibilitySummary` que diz de onde o
texto veio. É o que o arquivo oferece, e nem mais nem menos: a EPUB Accessibility 1.1 §2.2
pede a declaração, não a conformidade — e o que o Ace da DAISY reprovava era a ausência dela.

### O capítulo, pela altura da linha — medido, e desligado

`Paragrafo.titulo` tinha um marcador só, a faixa do diagrama, e o painel do Word mostrava
390 legendas e nenhum capítulo. O mecanismo entrou inteiro: `Paragrafo.nivel`, o `<h1>` com
âncora, o `Heading 1`, e o `nav.xhtml` que lista os capítulos em vez das páginas. O que
ficou **desligado** foi quem os marca — e foi medido antes de ficar.

O sinal do capítulo é o corpo: a `Linha` traz a mediana da altura das caixas dela, e
`_metricas_por_coluna` traz a da coluna. A régua (`_e_titulo`): uma linha só, com
**1,7 vezes** a altura da coluna, curta, de letras, sem lance, e no terço de cima da página.
Ligada por `medir_prosa.py --capitulos`, nos dois livros inteiros:

| livro | corpo do título, pela camada de texto | a régua achou | e eram |
|---|---:|---:|---|
| Yusupov · Chess Evolution 1 | 19,6 pt sobre 11 — **1,78×** | 20 em 264 páginas | 8 títulos (`CONTENTS`, `Preface`, `Exerc1.ses`, `CHAPTER`, `Scor1.n`, `Mate 1.n three m`…) e 12 que não são: `fyu scred less`, `ffyou scred less than 11pz.nts,` — a caixa de pontuação dos exercícios, prosa em corpo maior |
| Aagaard · Attacking Manual I | 12,7 pt sobre 10 — **1,27×** (`A sneak preview`) | 1 (`Preface`, 17,2 pt) | o capítulo dele está abaixo de qualquer régua de altura que não inunde |

E o que a régua devolve, quando acerta a página, é o que o OCR lê num corpo de exibição:
`S()lut1.()ns`, `Sc0r1.n`, `C♖APER` — o `o` vira `()` e o `i` vira `1.`, que é a família A
da F109 em glifo grande. Antes da régua de letras ela achava 60, com todos os `Solutions`
dentro; com a régua, os `Solutions` saem junto com o lixo, porque não têm 70% de letras. Não
há régua tipográfica que separe um título mal lido de um pedaço mal lido.

**O capítulo é da F110.** A camada de texto do PDF traz as duas coisas que faltam aqui — o
corpo em pontos e o texto limpo —, e ali `Preface` a 17,2 pt e `Exercises` a 19,6 pt são uma
comparação de número. `DETECTAR_CAPITULOS = False` em `core/livro.py` guarda a régua e o
motivo, e o sumário cai para "Página N" enquanto não há capítulo — que é o que havia.

### O que esta fase não alcança

**O itálico.** Zero runs em 36.442, e ele não tem sequer campo onde morar. A F105 mediu se o
sinal do negrito existia antes de projetar a detecção, e o mesmo método serve para a
inclinação — é uma fase, e não uma linha desta tabela.

**A aspa curva** e a licença das duas fontes de xadrez, que não é de código.

### Cobertura

`tests/test_f111_arquivo.py`, 28 testes. Dois deles abrem **toda** parte XML dos dois
formatos com o `ElementTree` — é o que o precedente da F59 pedia —, e um roda o `epubcheck`
5.3.0 sobre o EPUB em modo de fonte, com tabela e com capítulo, e exige retorno zero (pulado
quando ele não está instalado, e ele entrou no `requirements-dev.txt`; conferido à mão que
um EPUB sem `dc:language` devolve 1 e `RSC-005`). A suíte sai de 1.886 para 1.946, verde.

---

## F112 — A geometria decide a caixa, e um dos dois caminhos não pede rótulo nenhum — CONCLUÍDA (o caminho de Baird; o com rótulo continua esperando o rótulo)

A causa que a F14 nomeou, a F19 mediu, a F107 destravou e ninguém ainda consertou. Ela
responde por **2.141 palavras, 10,4% da prosa** do livro medido.

`c/C`, `o/O`, `s/S`, `u/U`, `v/V`, `w/W`, `x/X`, `z/Z`, `p/P`, `k/K` e `j/J` são **o mesmo
desenho**. O que os separa é o tamanho relativo à linha, e o recorte é redimensionado para
32×32 antes de o classificador o ver: **a informação que decide foi jogada fora antes da
decisão**. O mesmo vale para `o/0`, `l/1/I` e `g/9`.

### O que já está medido, e é muito

`core/altura_relativa.py` (F19), em distância entre médias por desvio combinado:

| par | d'(topo) | d'(base) | d'(altura) |
|---|---:|---:|---:|
| `s`/`S` | **3,78** | 0,60 | 3,18 |
| `o`/`0` | **3,24** | 0,60 | 2,66 |
| `w`/`W` | **3,10** | 0,20 | 2,78 |
| `c`/`C` | **3,00** | 0,30 | 1,82 |

**O discriminante é o topo**, e a razão é tipográfica: todo glifo se apoia na mesma linha de
base, então a base não distingue nada. O desempate *a posteriori* da F19 não pagou porque
só dispara onde a geometria e a âncora discordam, e com âncora forte esse conjunto é quase
todo erro da geometria.

A F107 tirou o pré-requisito do caminho — o tamanho deixou de se perder na gravação — e
mediu o que a entrada nova rende: `S` de 50,0% para **74,0%**, `W` de 33,3% para **83,3%**.
E achou que preservar a proporção no recorte, encaixado em 32×32 com papel em volta em vez
de esticado, paga **+2,8 pontos fora da família de caixa**.

### O que falta é maiúscula rotulada, e o corpus explica por quê

Páginas com `.box` rotulado à mão, cruzadas com a taxa de erro da F104:

| livro | rotuladas | erro (F104) |
|---|---:|---:|
| Kasparov · Benko Gambit | 8 | — |
| Darcy Lima · A Estratégia | 5 | recusado: português |
| Nunn · Secrets of Rook Endings | 4 | **0,38%** — o melhor |
| Seirawan · Xadrez Vitorioso | 3 | — |
| Aagaard · Attacking Manual I | 3 | 0,65% |
| Aagaard · Positional Play | 3 | — |
| Aagaard · Practical Chess Defence | 2 | — |
| Petrosian System | 1 | — |
| **Yusupov · Chess Evolution 1** | **0** | **1,33%** |
| **Yusupov · Complete** | **0** | **3,27%** |
| **Dvoretsky · Endgame Manual** | **0** | **3,93%** |

**Os três piores livros da tabela não têm uma página rotulada.** Todo limiar deste projeto
— a folga do diacrítico, a régua do espaço, o envelope de proporção da F106, o piso de
`CONF_MINIMA` — foi medido nos livros que já saem bem.

E há a prova direta, porque o projeto exportou os dois. Medido com a mesma régua, partindo
no hífen como a F108 parte:

| livro | páginas rotuladas | palavras | caixa ilegítima | `S/s` |
|---|---:|---:|---:|---:|
| **Kasparov** · Benko Gambit (o `.epub` da raiz) | **8** | 39.418 | **0,32%** | **0,047** |
| **Yusupov** · Chess Evolution 1 (o `.docx`) | **0** | 41.144 | **2,58%** | **0,203** |

**Oito vezes a taxa, e quatro vezes a razão `S/s`** — mesmo pipeline, mesmo modelo, mesma
semana. O 0,047 do Kasparov é o valor normal de um texto em inglês; o do Yusupov não é.

E isso não é observação de estilo: torna hipótese em inverificável. A hipótese natural para
a família A é que o separador de glifo colado corta o pingo do `i`, e o próprio projeto
documenta o resíduo (`box_service.py:1488`, *"quinze casos em 5.747"*). Rodado o caminho de
produção em três páginas rotuladas do Kasparov, com e sem o separador, contando boxes
dentro de cada `i`/`j` do gabarito:

| | 0 box | 1 box |
|---|---:|---:|
| com separador | 8 | **151** |
| sem separador | 12 | 147 |

**O pingo não se parte ali, e o separador melhora.** A hipótese não foi refutada — ela é
inverificável, porque o livro que exibe o defeito não tem gabarito. É a mesma lição que o
ROADMAP já registrou três vezes, agora no nível do corpus e não da métrica.

**Rotular três páginas do Yusupov Complete e três do Dvoretsky é o pré-requisito desta
fase**, e não consequência dela — a mesma ordem que a F107 estabeleceu.

### E há um caminho que não pede rótulo nenhum, que a F19 não tentou

Baird 1992 (*Document Image Defect Models and Their Uses*), p.7: *"The input to the shape
classifier is an image of an isolated character, **without size or baseline context**."* —
igual a este projeto. E p.8, o algoritmo:

> Each alternative symbol interpretation implies a text size (estimated from per-class
> statistics collected during training): the median of these sizes, weighted by confidence,
> is selected as the line's dominant text size. **This size is then used to prune the
> interpretations.**

**A F19 pendurou a geometria depois, para desempatar contra a âncora, e mediu que não paga.
Baird faz o contrário**: cada candidata *propõe* um tamanho, a linha vota qual é o tamanho
dela, e o tamanho **poda** as candidatas. Não exige retreinar nada — só as estatísticas por
classe, que saem da base de 626.181 recortes.

O mesmo artigo, p.8 §5, nomeia o que este projeto chama de veto: *"We have experimented
principally with **veto filters** … These include all-alphabetic or all-numeric rules (quite
effective on Latin languages)"* — e "dígito não entra em palavra de prosa" mataria a família
D, que são 8% da prosa.

E há a resposta do Tesseract para a caixa, que também não pede treino (R. Smith, ICDAR 2007,
p.632 §6): o *permuter* **gera a melhor palavra de cada regime de caixa** — top dictionary,
top UPPER case, top lower case with optional initial upper, top numeric, top classifier — e
escolhe a de menor distância total, cada categoria com sua constante. A regra tipográfica da
F108 deixaria de ser regra imperativa que precisa de exceção para `Nf3` e passaria a ser
**uma hipótese concorrente**.

### O que esta fase alcança e nenhuma outra alcança

O Seirawan e o Razuvaev. São 834 páginas sem uma linha de camada de texto, e ali não há
língua para consultar nem contexto para pedir: quem lê é o pixel.

### Antes de começar, a premissa foi remedida — e tinha mudado

Os 10,4% da prosa são de 2026-08-25, e **a prosa deixou de ser da cadeia** desde então: a
fusão por palavra da OCR-11/12 (`livro._fundir_por_palavra`) guarda o lance da âncora e toma
a prosa do Tesseract. Medido com o `medir_prosa.py --epub` nos dois livros que o usuário
exportou em 2026-09-23 com o app aberto, nenhum deles visto pelo modelo:

| livro | palavras de prosa | família B (caixa) | `S/s` | `C/c` | `(O+0)/o` |
|---|---:|---:|---:|---:|---:|
| Rabinovich · The Russian Endgame Handbook | 68.066 | 16 (0,02%) | 0,019 | 0,017 | 0,069 |
| Stean · Simple Chess | 17.407 | 5 (0,03%) | 0,041 | 0,041 | 0,068 |

`S/s` de inglês normal é 0,047 (o Kasparov, F108). E na notação, que continua com a cadeia:
no Rabinovich, **2** lances com a coluna em maiúscula e **2** `X` de captura em 26.656
lances; no Stean, **10** `X` em 3.314, e os roques saem `0-0` 8 vezes e `O-O` 4.

**Onde a caixa da cadeia ainda chega ao arquivo**, então: o lance; a célula de tabela e o
cabeçalho do diagrama, que o motor não cobre; e a página inteira quando não há Tesseract —
a exportação deixa seguir sem ele, e ali a p. 30 do Aagaard sai com 25% de CER na prosa. É
para esses lugares que esta fase serve, e é neles que ela se mede.

### O que entrou

`core/geometria_da_linha.py`, que é a p. 8 de Baird: **cada leitura propõe uma altura de
x** (um `s` de 20 px diz "20", um `S` de 20 px diz "14"), a linha vota a dela pela mediana
ponderada pela confiança, a base sai de uma reta robusta (Theil-Sen) pelas bases que as
leituras propõem, e a leitura que não cabe no corpo votado é trocada pela candidata da rede
que cabe. A tabela das classes — onde o corpo de cada uma começa e acaba, em alturas de x
acima da base — está em `core/dados/geometria_das_classes.json`, 82 classes medidas nas
páginas rotuladas por `medir_geometria.py --gravar`.

O livro a liga por um parâmetro, `candidatas(recorte, k)`, em `livro.extrair`,
`extrair_pagina`, `_ler_linha`, `_texto_da_linha` e `_faixa_em_texto`. `None` é o padrão,
como o `probabilidade` da F69: quem chama sem ele lê como antes. As duas exportações da
janela (Livro e Documento editorial, por `OpcoesDeLeitura.candidatas`) passam
`learning_service.candidatas`, e o `scripts/processar_editorial.py` também. **A linha passa a
ser classificada inteira antes de ser montada**: o coletor, o marcador e o piso de confiança
recebem a leitura já podada.

Três escolhas, e cada uma saiu de medida.

**A medida é o corpo de tinta dentro do recorte, e não a caixa.** A primeira varredura usou a
caixa, e as quebras reais tinham uma causa só: o pingo do `i` entrava na caixa da letra
anterior (`w|ith`, `v|isão`, `ha|v|ing`), e o `w` ficava com o topo de um `W`. O corpo é a
faixa de linhas com tinta de maior massa: o pingo e o acento destacados ficam de fora, e a
caixa frouxa é aparada à tinta. Com isso as dez quebras reais daquela varredura sumiram. E
veio de brinde o que a F19 media como impossível: o corpo do `i` é a haste, com o topo na
altura de x, e passa a haver o que o separe do `1` (a F19 mediu d' = 0,01 para `i/1` com a
caixa inteira) e do `l` — que a tabela mede largo, com desvio 0,18, e por isso só cai
quando a haste lida fica abaixo da altura votada.

**Só se troca dentro de um grupo de mesmo desenho**: `c/C`, `o/O/0`, `s/S`, `u/U`, `v/V`,
`w/W`, `x/X`, `z/Z`, `p/P`, `9/g/q`, `,/'/’/‘`, `./,` e `i/l/1/I`. Baird poda toda
interpretação que não cabe; aqui a rede já acerta 98% e é melhor que a geometria em tudo o
que não é tamanho, e solta a poda trocava `)` por `J`, `H` por `R` e `♔` por `♗`. O ponto e o
apóstrofo não são grupo: o ponto alto costuma ser o pingo de um `i` partido (família A da
F109), e trocá-lo por `'` não conserta nada.

**Dígito só vira letra dentro de palavra, e letra só vira dígito dentro de número**, pelo
vizinho de caixa na régua do espaço da linha. Livro de algarismo de texto põe o `1` e o `0`
na altura de x, e sem a trava `1.e4` sairia `i.e4`. É o filtro *"all-alphabetic or
all-numeric"* que o próprio Baird descreve na §5, reduzido ao vizinho. Entre as candidatas
que cabem, vence a do tipo do vizinho — o `O` e o `0` têm o mesmo corpo.

**A troca sai com a massa do grupo** entre as candidatas, e não com a probabilidade da
substituta: a rede não separa os dois lados do par, e o `o` que ela deu 0,08 contra 0,9 do
`O` seria derrubado pelo piso do livro — a troca viraria buraco. Pelo mesmo motivo a leitura
**fraca que cabe enquanto o resto do grupo não cabe** sobe para a massa do grupo: é o `o`
repartido entre `o`, `0` e `O` que nenhum alcançava 0,5 e o livro apagava (F107, *"Cmbinatin
invlving bihp"*).

### Medido

**Nas páginas rotuladas, com a população do livro.** `medir_geometria.py` segmenta como o
`livro.caixas_e_diagramas`, corta as linhas como o `quebrar_em_linhas`, lê pelo
`leitor_de_texto` e casa cada caixa com o gabarito pelo centro. **Cada livro é medido com a
tabela estimada nos outros**, porque é o caso da produção: o livro exportado não está nas
páginas rotuladas. 31.956 caracteres, 7 livros:

| | leitura | no texto (com o piso de confiança) |
|---|---:|---:|
| sem a poda | 98,07% | 97,74% |
| com a poda | **98,26%** | **97,94%** |

91 trocas no texto: **73 consertos**, 10 neutras e 8 quebras. **As 8 quebras são todas erro
do gabarito**, conferidas a olho: `Marin's` rotulado com vírgula, `Chéron,` com apóstrofo,
`Seirawan` com `W` duas vezes, `sacrifíCio`, e o `0` de `c0ntrajogo`, `0s peões` e
`Glossári0`. Os consertos: `l`→`i` 23, `0`→`o` 20, `'`→`,` 9, o `o` que o piso apagava 9,
`c`→`C` 6. Nenhum livro piora; o Seirawan, que é escaneado e em português, vai de 95,98% para
**97,21%**.

Isto é o piso do ganho, e não o ganho: são as páginas em que o modelo treinou (F117), e ali
a rede já erra pouca caixa.

**No corredor do corpus, no modo de produção** (`scripts/rodada_do_corpus.py`, fusão por
palavra): nenhuma página piora, e o que muda é a notação, que é o que a cadeia ainda decide.

| página | antes | depois | notação antes | notação depois |
|---|---:|---:|---:|---:|
| Aagaard p. 30 | 1,37% | **1,30%** | 3,14% | 2,93% |
| Nunn p. 237 (tabela) | 1,87% | **1,76%** | 3,63% | 3,39% |
| Yusupov p. 34 | 0,71% | 0,71% | 0,76% | 0,76% |
| Yusupov p. 47 | 2,50% | 2,50% | 0,00% | 0,00% |
| **corpus** | 1,62% | **1,59%** | 1,99% | **1,88%** |

No texto: `58.♘xc4?` volta a ter a vírgula, e a célula `w♖g1,` volta a ser `W♖g1,`. A
rodada sem a poda (`--sem-geometria`) reproduz a de 2026-09-22 casa por casa, que é a prova
de que a linha classificada inteira antes de montada não mudou nada por si.

**Só com a cadeia, sem Tesseract** (`ab_ocr_livro.py --modos glifo`): Aagaard p. 30 de
**18,92% para 16,18%** (prosa 24,87% → 21,51%, notação 6,69% → 5,23%) e Nunn p. 237 de 8,29%
para 7,88% — `c0uld`→`could`, `w0n`→`won`, `Morales'`→`Morales,`, `W:W1n`→`W:Win`.

**Num livro que o modelo não viu, só com a cadeia** (`medir_prosa.py --pdf`, Yusupov Chess
Evolution 1, p. 8–47): palavras de prosa com defeito de **14,38% para 13,51%** (520 → 491),
a família D (dígito dentro da palavra) de **5,28% para 1,87%**, `(O+0)/o` de 0,084 para
0,065 e `V/v` de 0,060 para 0,041. O `S/s` já estava normal (0,045) nos dois lados: o `S` de
0,203 que a F107 mediu era do modelo de agosto, e os retreinos o levaram.

### O que não entrou, com o número

- **A tolerância única** — desvio de 0,12 para toda classe, em vez do medido. Pega o `s`
  lido `S`, que a tabela deixa passar, mas quebrou o `l` de "clássico" no Darcy Lima, cuja
  fonte tem ascendente curto. No protótipo (a mesma população, com a régua de vizinho de
  antes), +73 −9 contra +64 −5 no texto, com uma quebra real. Ficou a tolerância medida, e
  o `s` lido `S` fica — `test_o_s_lido_maiusculo_fica_porque_a_tabela_mistura_fontes` diz
  isso na letra.
- **Por que o `S` fica**: a altura de caixa alta sobre a de x é da fonte, e varia de 1,32
  (Darcy Lima) e 1,37 (Seirawan) a 1,41 (Kasparov), 1,45 (Nunn), 1,63 (Aagaard, *Practical
  Chess Defence*) e 1,67 (*Attacking Manual*). A tabela de todos junta as seis, o `S` fica
  com desvio 0,15, e o `s` lido `S` cai a 2,8 desvios, abaixo do veto. **A tabela por livro
  é o próximo passo**, e ela não pede rótulo: sai das maiúsculas sem par do próprio livro.
  *Medida na F123 antes de ser feita: sai certa sem rótulo, e não paga — ver lá.*
- **A adaptação por linha** — a altura de caixa alta e a de ascendente estimadas das
  maiúsculas e algarismos sem par da própria linha. No mesmo protótipo, +65 −6 contra
  +64 −5: não paga nas páginas rotuladas, e a linha é pouco material. É a mesma ideia da
  tabela por livro, com uma linha no lugar do livro.
- **A janela** («Detectar e Preencher»). A cadeia dela tem k-NN, rede e EasyOCR, e a troca
  precisa de uma fonte própria na fila de revisão; o `medir_cadeia.py` precisa aprender a
  poda antes. Fica como a F117 ficou para a F116. *Entrou na F123.*
- **O caminho com rótulo** continua esperando três páginas do Yusupov Complete e três do
  Dvoretsky.

### Um achado de passagem

Na janela, o veto de tamanho da F106 compara o maior lado do recorte com a mediana da altura
dos boxes da página (`proporcao.altura_de_referencia`). **Num sumário de pontilhado os
pontos são a maioria dos boxes**, a mediana vira a altura de um ponto, e o próprio ponto é
vetado como grande demais: na p. 8 do Seirawan, 1.429 dos 2.172 boxes saíam `'` com
`ler_texto(recorte, referencia)`. O caminho do livro não passa `referencia` e não é afetado.
Registrado aqui, e consertado na F121.

### Onde está

- `core/geometria_da_linha.py` e `core/dados/geometria_das_classes.json`.
- `core/livro.py` — `candidatas` do `extrair` ao `_texto_da_linha`.
- `core/editorial_legacy.py` — `OpcoesDeLeitura.candidatas`; `ui/main_window.py` — as duas
  exportações a passam.
- `medir_geometria.py` refaz a tabela das páginas rotuladas e grava a de produção;
  `medir_prosa.py`, `scripts/rodada_do_corpus.py` e `scripts/ab_ocr_livro.py` ganharam
  `--sem-geometria`, para o A/B.

Cobertura: `tests/test_f112_geometria.py`, 28 testes — o corpo sem o pingo e com a caixa
aparada, a reta robusta, a linha sem ascendente, a troca dentro do grupo e nunca fora dele,
o dígito só em palavra e o zero entre algarismos, vírgula e apóstrofo, a confirmação da
leitura fraca, a exportação da janela ligando a poda, e a tabela gravada medindo o que a
tipografia diz. Os dublês de `_texto_da_linha` em `test_ocr_fusao_por_palavra.py` e
`test_f72_tabela_no_epub.py` ganharam o parâmetro, e o `_Aprendizado` de
`test_processar_editorial.py`, o método — a página nascida digital não chega à poda.

---

## F113 — Onde não há corte, não há corte errado — MEDIR ANTES DE DECIDIR

A aposta mais forte no papel e a de maior risco na prática, e por isso ela entra no ROADMAP
como **medição**, e não como decisão.

### A ideia

Um segundo motor que lê a **linha inteira**, sem segmentar caractere, treinado nas páginas
rotuladas do próprio projeto. O caminho por caractere fica com o xadrez — diagrama,
figurina e notação.

Ele resolve por construção o que as outras fases resolvem por conserto: onde não há corte,
não há corte errado; onde não há régua de espaço, não há espaço espúrio; e um decodificador
que vê a linha inteira desempata `s`/`S` pelo contexto que o glifo isolado não tem.

### O motor: Calamari, e o Kraken está fora por uma razão que não é qualidade

| motor | licença | Windows | entrada de treino |
|---|---|---|---|
| **Calamari** 2.3.1 (12/11/2024) | GPL-3.0 | **sim** — o PyPI declara "OS Independent" | imagem de linha + `.gt.txt` |
| Kraken | Apache-2.0 | **não** | imagem de linha + `.gt.txt` |

README oficial do Kraken, conferido em 25/08/2026, verbatim: *"Kraken can be run on Linux or
Mac OS X (both x64 and ARM)."* Windows não aparece em lugar nenhum, e este projeto roda em
Windows 10.

Três detalhes para quem escrever o script: os modos de `--resize` são `union`/`new`/`fail`
na documentação 6.0.0 e **não** `add`/`both`, que são nomes da série 3.0; o Kraken **aceita**
o mesmo par imagem-de-linha + `.gt.txt` do Calamari, e não exige ALTO nem PageXML; e a regra
das "800 linhas" vale para *"printed script with a small grapheme inventory such as Arabic or
Hebrew"*, não para 314 classes.

E o Calamari traz de fábrica, em dois comandos, a **votação por confiança** de Reul, Wick,
Springmann e Puppe (arXiv:1711.09670) — treinar N modelos em dobras diferentes e somar as
confianças de cada caractere e das alternativas. O precedente de escala é o ISRI (Rice et
al., 1996), que levou cinco motores de 90,10–98,83% para **99,15%**.

### Modelo de visão-linguagem: não, e o número é claro

arXiv:2606.13108 (PP-OCRv6, 11/06/2026, CC BY 4.0), Tabela 7: PP-OCRv6_medium (34,5 M
parâmetros) **93,20**; Kimi-K2.6 85,00; Qwen3-VL-235B 80,56; GPT-5.5 **78,00**. E a razão
que decide, verbatim: *"A critical advantage of specialized OCR models over VLMs is the
absence of text hallucination — generating text not present in the input image."*

**Para este projeto isso é requisito, não preferência.** Um OCR que erra deixa `biShop`, que
o dicionário acusa e a razão de caixa mede; um modelo que alucina deixa uma frase plausível
e errada, que nenhum instrumento deste projeto tem como pegar.

### O que torna isso barato de testar

**O `.box` deste projeto é o formato do Tesseract** — `core/avaliacao_pagina.py:52` diz
isso na letra: *"Lê um `.box` do Tesseract"*. As páginas rotuladas convertem para
transcrição de linha agrupando por linha e concatenando, sem escrever conversor. E há
626.181 recortes rotulados em 314 classes para sintetizar linha onde faltar.

### O que se perde, e é estrutural

A caixa por caractere na prosa, e com ela a edição de box na UI, a coleta e a fila de
revisão para o texto lido por esse caminho. **Procedência por caractere e leitura por linha
são incompatíveis**, e escolher uma é escolher o que a UI pode oferecer sobre aquele texto.
É a mesma perda da F110, pela mesma razão.

### O número que decide

Converter as páginas para transcrição de linha, afinar um motor de linha, e medir contra
o pipeline de hoje **nas mesmas páginas**. Nada além disso decide esta fase.

---

## F114 — O motor de linha já estava instalado, e o projeto o chamava letra por letra — CONCLUÍDA (instrumento)

A SPEC §7.1 comparava seis motores de linha por licença, runtime e entrada de treino, e
**nenhuma linha daquela tabela tinha número medido nestes livros**. O único que este projeto
já havia medido era o EasyOCR (F17: 72,9% para 89,5%), e foi com esse número sozinho que a
F18 decidiu a trava. Comparar candidatos exige rodá-los na mesma faixa, contra a mesma
verdade, no mesmo processo — e não havia instrumento que fizesse isso.

### O achado, e por que ele não é defeito

`tesseract --version` responde **5.5.0.20241111, com 161 idiomas**, neste ambiente. O
Tesseract 5 é LSTM: um reconhecedor de **linha**. E o `core/services/ocr_service.py` o invoca
com `config = "--psm 10"` — *"treat the image as a single character"*.

**Registrar isso como defeito seria erro, e quase foi.** Os dois chamadores são de caractere
— `auto_fill_characters` em `ui/main_window.py:2243` e a ação de box selecionado em `:3000`
—, e para eles o `psm 10` é o modo certo. O achado é outro: **a capacidade de linha nunca foi
exercida**. Exercê-la custa uma string trocada num script de medição, nenhuma dependência e
nenhum download. Se tivesse ido para a tabela de defeitos da SPEC §8, alguém trocaria para
`psm 7` em produção e quebraria a leitura por caractere.

### A tabela

Medido em **10.508 boxes com rótulo, 473 linhas de 10 páginas rotuladas**, com a segmentação
de produção (árbitro da F1.5b) e o `ler_pagina` de produção:

| motor | acerto/box, âncora própria | acerto/box, âncora vazia | CER | linha exata | ms/linha |
|---|---:|---:|---:|---:|---:|
| EasyOCR `english_g2` | **89,54%** | 65,33% | 12,26% | 25,7% | 34,8 |
| Tesseract `--psm 7` | 88,38% | **70,71%** | 10,56% | 32,1% | 138,2 |
| Tesseract `--psm 13` | 87,63% | 67,87% | 12,18% | 27,9% | 137,1 |
| RapidOCR `PP-OCRv6_rec_small` | — *sem modo por caractere* | 56,34% | **8,64%** | **34,3%** | 23,5 |
| docTR `crnn_vgg16_bn` | — *sem modo por caractere* | 46,31% | 16,63% | 16,2% | 57,0 |
| Calamari 2.3.1 `antiqua_historical` | — *sem modo por caractere* | 13,09% | 50,42% | 2,5% | — |
| Kraken 7.1 `CATMuS-Print Tiny` | — *sem modo por caractere* | 48,02% | 19,41% | 21,6% | 16,4 † |
| PaddleOCR `PP-OCRv6_medium_rec` | — *sem modo por caractere* | 55,82% | **8,64%** | 33,3% | 165,0 † |
| *(a cadeia de hoje)* | **97,60%** | — | — | — | — |

**Ninguém passa, e a margem não é de fração**: 8 pontos no melhor arranjo, 27 no pior. A
trava da F18 fica onde está, e a conclusão da §7.1 deixa de ser previsão.

### A âncora, que quase fez a tabela mentir

O `ler_pagina` distribui a string da linha alinhando-a contra a **âncora** — uma leitura com
um item por box. A primeira versão deste instrumento usou âncora **vazia** e apresentou o
resultado como comparável ao 89,5% da F17. Não é: a F17 ancorou na leitura por caractere, e
diz isso na letra — *"A leitura por caractere é a âncora, e resolve"*. A diferença é de
quinze pontos, e teria entrado aqui como se fosse a mesma medida.

A âncora virou argumento, e a tabela ganhou as duas colunas, porque **a ordem entre os dois
primeiros depende dela**:

- com âncora própria a coluna compara dois *compostos* — linha do Tesseract mais `psm 10` do
  Tesseract contra linha do EasyOCR mais caractere do EasyOCR —, e o EasyOCR ganha por 1,2;
- com âncora vazia os dois correm sem muleta, e o `--psm 7` ganha por **5,4 pontos**.

Trocar de âncora vale **24,2 pontos ao EasyOCR contra 17,7 ao Tesseract**, o que diz onde
está a força de cada um: a do EasyOCR é o modo por caractere, não a leitura de linha. **O CER
e a linha exata não dependem de âncora**, e neles o `--psm 7` ganha do EasyOCR e do
`--psm 13`. Dos quatro, quem ganha é o RapidOCR — e pela seção seguinte se vê que ganhar CER
e perder acerto por box é uma coisa só.

### O instrumento se validou sozinho

O EasyOCR com âncora própria deu **89,54%** contra os **89,5%** que a F17 registrou. Quatro
centésimos, refazendo com um comando uma medida de meses atrás. É a lacuna que o
`medir_cadeia.py` declara no cabeçalho — *"refazer qualquer uma delas hoje é reescrever o
instrumento antes de medir"* — fechada para a F17.

### O RapidOCR lê a melhor linha e distribui a pior

Instalado depois da primeira tabela (`pip install rapidocr onnxruntime`, oito pacotes, nenhum
substituindo `numpy`, `torch` ou `opencv`), ele roda o `PP-OCRv6_rec_small.onnx` — o modelo da
tabela da SPEC §7.2 — sem paddlepaddle. Tem o **menor CER (8,64%)**, a **maior taxa de linha
perfeita (34,3%)** e é o **mais rápido** dos quatro (23,5 ms contra 34,8 do EasyOCR). E tem o
**pior** acerto por box: 56,34% contra 70,71% do `--psm 7` no mesmo pé.

Não são resultados em conflito: são o mesmo fato. Onde o EasyOCR **troca** a figurina por
letra errada, o RapidOCR a **omite**.

    esperado  9.Bb4Qe3✝10.Kh1Qx411.Be7Rxc6
    lido      9.xb4e3t10.h1xe411.e7xc6

Uma troca custa um caractere e não mexe no comprimento. **Uma omissão encurta a string, e com
ela todo box seguinte da linha anda uma casa** — o descompasso que o `distribuir` documenta
como *"qualquer descompasso desloca a linha inteira em silêncio"*. O CER cobra 1 pela
omissão; o acerto por box cobra o resto da linha.

**Isso o torna o candidato mais forte para segunda opinião, e o mais fraco para ler sozinho.**
Com uma âncora de um item por box — que é o que a cadeia neural é — o alinhamento reabsorve a
omissão, e é exatamente o mecanismo da F17.

### O `medium` do PP-OCRv6 não compra nada aqui, e isso é sobre transferir benchmark

O PaddleOCR roda o `PP-OCRv6_medium_rec` — 34,5 M de parâmetros, a primeira linha da tabela
do SPEC §7.2, com 93,20 — contra o `PP-OCRv6_rec_small` de 7,7 M que o RapidOCR roda e que
aquela tabela pontua em 88,20:

| | modelo | parâmetros | §7.2 | CER | acerto/box | linha exata | ms/linha |
|---|---|---:|---:|---:|---:|---:|---:|
| RapidOCR | `PP-OCRv6_rec_small` | 7,7 M | 88,20 | **8,64%** | **56,34%** | **34,3%** | **23,3** |
| PaddleOCR | `PP-OCRv6_medium_rec` | 34,5 M | 93,20 | **8,64%** | 55,82% | 33,3% | 165,0 |

**CER igual até o centésimo, e o `medium` pior nas outras duas colunas** — por 4,5× os
parâmetros, 7× o tempo e 104,8 MB de runtime. Conferido linha a linha, os dois concordam em
**79,5% das 473** ignorando espaço, e o espaço é o que a distribuição apaga.

Os cinco pontos entre os dois níveis foram medidos em OCR de documento **geral**; estas faixas
são dominadas por notação, onde a parede é a figurina e capacidade a mais não ajuda. **O
número do §7.2 vale para o que ele mede, e não chega até aqui** — é a mesma cautela que a
§7.4 registra sobre Baird: o padrão transfere, o número não.

**E isto corrige uma frase que eu havia escrito nesta fase.** Ela dizia que o PaddleOCR ficava
sem número "por escolha, porque o RapidOCR já roda o mesmo `PP-OCRv6`". A conclusão estava
certa e o raciocínio, errado: o PP-OCRv6 é uma família de três níveis que o §7.2 pontua
separadamente, e o RapidOCR roda o menor. A linha sai igual **por medição**, não por serem a
mesma coisa.

### A ponte se validou sozinha

O RapidOCR foi medido duas vezes — uma em processo, pelo motor de dentro, e outra pelo par
`--exportar`/`--predicoes`, com os PNGs indo e as predições voltando. As duas deram
**56,34% / 8,64% / 34,3%**, idênticas até o centésimo. É o que autoriza pôr na mesma tabela os
motores que rodam neste interpretador e os três que rodam em `venv` separado.

### O Kraken roda em Windows, e a §7.1 o excluía sem ter tentado

**Esta é a correção mais cara desta fase**, porque não é um número novo: é uma premissa
derrubada. A §7.1 cortou o Kraken citando o README — *"Kraken can be run on Linux or Mac OS
X"* — e o classificador `Operating System :: POSIX` do PyPI. Nenhuma das duas fontes foi
testada, e este projeto roda em Windows 10.

**Testado, ele roda.** `pip install kraken` instala a 7.1 com torch 2.13.0 no Python 3.13
daqui; `import kraken`, `kraken.rpred` e `kraken.lib.models` importam; `kraken --version`
responde; e o reconhecimento devolve texto certo numa faixa real. Varridos os `.py` do wheel
de 5,1 MB, não há um só import de `fcntl`, `resource`, `pwd`, `grp` ou `termios`.

Os três atritos de Windows que existem **não estão no caminho de reconhecimento**: o
`htrmopo` abre `iso15924.txt` sem declarar codificação e quebra em cp1252 (`PYTHONUTF8=1`
resolve); o `kraken get` grava com *"invalid path"* (baixar do Zenodo contorna); e o
`kraken -I '*.png'` devolve os arquivos expandidos ao parser do click como subcomandos (a API
não passa por ali, e é o que o `rodar_kraken.py` faz).

**E ele lê prosa moderna de verdade**, com o `CATMuS-Print Tiny`, treinado em impresso latino
do século XV ao XX:

    esperado  the force of the break... f6-f4. It was safer
    kraken    the force of the break... f6-f4. It was safer
    calamari  the force oſ he brea . S. ſ. It vvas afer

**A escolha da §7.1 fica em aberto por causa disto.** O Calamari ganhou por eliminação de um
candidato só, e a eliminação caiu:

| | Calamari 2.3.1 | Kraken 7.1 |
|---|---|---|
| licença | GPL-3.0 | **Apache-2.0** |
| runtime novo | **TensorFlow** | nenhum — torch, já em produção |
| instala no Python 3.13 do projeto | **não** | **sim** |
| entrada de treino | imagem + `.gt.txt` | imagem + `.gt.txt` |
| modelo pronto de impresso moderno | **não existe** | **CATMuS-Print** |
| CER medido nestes livros | 50,42% | **19,41%** |
| votação por confiança pronta | **sim** (§7.6) | não, no mesmo formato |

A única vantagem que resta ao Calamari é a votação do §7.6 — e ela foi medida abaixo, sem
render. **Isto não escolhe o Kraken**: escolher motor de linha é a F113, e ela pede um modelo
afinado nestes livros, não um pretreinado. O que esta fase estabelece é que a razão pela qual
o Kraken estava fora **não existe**, e que a decisão precisa ser refeita com ele dentro.

### O Calamari não roda neste Python, e o número dele mede outra coisa

**O impedimento é de resolução, não de esforço.** O `calamari-ocr` 2.3.1 pede
`tensorflow>=2.4.0`, e o `ocrd-fork-tfaip` 1.2.7 que ele exige pina `tensorflow<2.16.0`. Para
o Python 3.13 deste projeto **só existem o TensorFlow 2.20.0 e o 2.21.0**: `ResolutionImpossible`.
O pip aceita `calamari-ocr` sem versão e resolve para a **1.0.5**, outra geração do produto —
medi-la e chamá-la de 2.3.1 seria atribuir número à coisa errada. Isto é mais duro que o custo
de runtime da tabela: não é que o Calamari **traga** TensorFlow, é que a versão da tabela **não
roda no interpretador deste projeto**.

Medi-lo exigiu um `venv` à parte em Python 3.11, com TensorFlow 2.15.1 e numpy 1.26.4, e a
ponte `--exportar`/`--predicoes` que o `medir_linha.py` ganhou nesta rodada. A chave é o
**sha1 dos bytes da faixa**, então o motor de fora recebeu exatamente as mesmas 473 tiras e o
resultado voltou pelo mesmo `ler_pagina` e pelo mesmo cálculo de CER. Pôr o torch no 3.11 só
para o árbitro da segmentação seriam 2,5 GB para nada.

**E o modelo é de outro século.** O pacote não traz nenhum, e os do Calamari 2.x são todos de
impresso histórico — `antiqua_historical`, `fraktur_*`, `gt4histocr`, `historical_french`,
`idiotikon`. Não há inglês moderno. Com o `antiqua_historical`, o mais próximo por ser família
romana, a primeira linha já denuncia:

    the force oſ he brea . S. ſ. It vvas afer

`ſ` e `vv` — o s longo e o duplo-v do impresso antigo, num livro de 2012. Nas piores linhas
ele perde metade dos caracteres:

    esperado  IwouldliketoproceedunderthemottoofaDutchchessclub:Let'sPlayChess!
    lido      Iouneopoceeduneremouootauncness

**Os 13,09% medem o descasamento de domínio, não o motor**, e registrá-los como veredito seria
o erro que a SPEC §7.5 aponta em Eken et al.: número colhido fora do problema. O que a linha
diz é que **motor de linha pronto sem modelo do domínio não serve** — e que a entrada de
treino, terceira coluna da tabela da §7.1, deixa de ser conveniência para virar o requisito
principal.

### A votação da §7.6, medida pela primeira vez

O `antiqua_historical` vem em **cinco dobras**, e a §7.6 chama a votação por confiança de
melhor razão ganho por trabalho. O mecanismo é o prometido: um comando, cinco `--checkpoint`,
nenhuma configuração. O ganho, não:

| | acerto/box | CER | linha exata | 473 linhas em |
|---|---:|---:|---:|---:|
| cinco dobras, com votação | 13,09% | 50,42% | **2,5%** | 24 s |
| uma dobra só | **13,56%** | **48,96%** | 1,9% | **6 s** |

**A votação piorou o CER e o acerto por box, melhorou a linha exata, e custou 4× o tempo.**
Isto **não refuta a §7.6**: o precedente do ISRI leva cinco motores de 90,10–98,83% para
99,15%, e aqui são cinco dobras a ~50% de CER. Votação aproxima quem já está perto, e não há
consenso a extrair de cinco leituras erradas. O que fica medido é o **preço** — 4× — e que a
peça está pronta e é barata de acionar. O ganho dela continua por medir, e só um modelo de
domínio o mediria.

### O docTR é o último em tudo, e a causa é de tamanho

O `crnn_vgg16_bn` declara `input_shape (3, 32, 128)` — **128 pixels de largura**. Ele é um
reconhecedor de **palavra**, e uma faixa de linha destes livros passa de mil pixels: entra
esmagada em oito vezes. O CTC responde repetindo trecho.

    esperado  11.Kg2Nbd712.Re1Ng413.Re2
    lido      11.dg20bd7_12.He109413.He129413.He2

`13.He1` sai duas vezes; noutra linha o `27.` sai duplicado. É **texto que não está na
imagem** — a falha que a SPEC §7.2 recusa, aqui por acidente de escala e não por prior de
linguagem.

**E isso qualifica a lição da F17, que não é universal.** A F17 aprendeu a pular o detector,
porque o CRAFT do EasyOCR não achava texto num recorte já cortado. Aquela lição vale para
reconhecedor de **linha** — o `english_g2` e o PP-OCR recebem a faixa inteira sem problema.
Para um reconhecedor de **palavra**, o detector é quem parte a linha em pedaços do tamanho
que o modelo espera, e pulá-lo é o erro. **O 46,31% é o piso do docTR, não o veredito sobre
ele**: o número justo sai do `ocr_predictor` inteiro sobre a faixa, e esta fase não o rodou.

### Uma linha do gabarito parece errada

Entre as três piores do RapidOCR:

    esperado  T?eseCondeampledidwhiTemanageTo
    lido      thesecondexampledidWhitemanageto

O **rótulo** é que parece corrompido, e o motor leu certo. É uma linha em 315 e não move
número nenhum desta fase, mas penaliza os quatro motores igualmente e sugere que o gabarito
tem ao menos um defeito. Registrado para quem for rotular de novo.

### Dois defeitos dos motores, que a tabela não mostra

**O `--psm 13` inventa texto.** O modo "raw line" não faz análise de layout e despeja
caractere depois do fim: `Foreword5` sai `Forewordi—(its—'"s—s—s—sSS`. Em linha curta é
ruinoso, e é a espécie de falha que a SPEC §7.2 recusa por princípio. O `--psm 7` não a tem,
e é por isso que ele, e não o 13, é o candidato.

**Os três destroem notação, pelo mesmo motivo.** As figurinas estão fora do alfabeto dos
três: `12...Ra6;12...Ra7` sai `12_Ea6;12_Eal` no EasyOCR, `Nge518.Nxe5` sai `DgeS18.AxeS` no
Tesseract. É o que o filtro do `em_bloco` existia para pegar e que a F36 mediu não pagar.
**Nenhum motor de linha geral resolve a trilha de lance** — ela tem gramática e legalidade,
que é o caminho da F1.7 e não este.

### O que isto diz à F113

A F113 fecha com *"converter as páginas para transcrição de linha, afinar um motor de linha,
e medir contra o pipeline de hoje nas mesmas páginas"*. **Esta fase dá o piso desse número
sem afinar nada**, e o piso é 8 pontos abaixo da cadeia. Não decide a F113 — motor afinado
nas fontes destes livros é outra coisa que motor pronto —, mas diz de quanto o afinamento
precisa: **8,6 pontos de CER a fechar** a partir do melhor motor pronto, e não um ajuste
fino.

### O que continua sem número

**Nada, entre os candidatos da §7.1.** Os sete motores daquela seção têm linha medida nas
mesmas 473 faixas. O que sobra sem medir é motor **afinado** nestes livros, e isso é a F113.

**†** o tempo dos três motores que rodam fora deste interpretador foi medido no `venv` deles,
e não pela ponte — ela mediria o custo de consultar um dicionário. O Calamari fica sem número
de tempo porque tem dois: 51 ms por linha com as cinco dobras, 13 ms com uma só.

**Os dois adaptadores escritos às cegas passaram**, e isso vale como nota de método. O
`rapidocr` e o `doctr` foram escritos só da documentação, com o pacote ausente, e nenhum dos
dois precisou de conserto: `use_det=False` aceito e `txts`/`scores` onde a documentação
prometia num; `[(texto, confiança)]` do `recognition_predictor` no outro. Dá para preparar o
instrumento antes de decidir se a dependência entra.

**E as duas instalações foram limpas.** `pip install rapidocr onnxruntime` trouxe oito
pacotes e `pip install python-doctr`, dezesseis; nenhuma tocou em `numpy`, `torch`,
`torchvision`, `opencv` ou `pillow`. O dry-run antes do docTR existiu porque ele declara
`torch<3.0.0,>=2.0.0`, e um rebaixamento de torch levaria o EasyOCR e a rede junto.

### Onde está

`medir_linha.py`, e a tabela na SPEC §7.1 sob "E agora a tabela tem número". Ele reaproveita
a `Pagina` do `medir_cadeia.py` e o `ler_pagina` de produção — a população de boxes é a mesma
das outras tabelas —, e a distância de edição sai do `notacao._alinhar`, que já é a DP que o
`distribuir` usa desde a F17.

**Sem cobertura de teste, como os outros `medir_*.py`**: o `pytest.ini` restringe a coleta a
`tests/`, e instrumento de medição não entra lá. O que o protege de mentir é a validação
acima — se a linha do EasyOCR sair de 89,5%, o instrumento mudou.

---

## F115 — O caractere derrubado escrevia dois espaços, e os reparos do dicionário nunca viam a palavra inteira — CONCLUÍDA

Uma revisão do OCR e da conversão, pedida depois da F114. Saíram quatro consertos no
`core/livro.py`, dois instrumentos, e **um quinto achado que ficou medido e sem conserto** —
porque as duas correções candidatas foram medidas e as duas custam mais do que rendem.

Os quatro consertos são de **montagem do texto**, e não de reconhecimento. É o que a F109
§4.1 chama de "os reparos que existem e o livro não recebe": ela listou quatro funções e uma
só tinha chamador em produção. **Esta fase liga as três que faltavam**, e a lista fecha.

Elas não entraram do mesmo jeito, e a diferença é o que cada uma custa. As três primeiras são
baratas e ficam sempre ligadas. A quarta — o reparo de colagem da F66 — é exata e **doze
vezes e meia mais lenta**, e por isso entra como pergunta na janela de exportação, com o
padrão em não.

---

### O achado que ficou em pé, e as duas réguas que caíram

A revisão apontou `livro._na_faixa` como permissiva demais. Ela recolhe para o cabeçalho do
diagrama toda caixa cujo **pé** caia dentro de 1,4 alturas de caractere acima da borda do
tabuleiro e que apenas **se sobreponha** a ele na horizontal — e num livro de coluna única
toda linha de prosa se sobrepõe. A última linha do parágrafo acima de cada diagrama sairia
do parágrafo e viraria `<h2>` no EPUB e `Heading 2` no DOCX.

A evidência era o `Kasparov - The Dynamic Benko Gambit (2012).epub` da raiz, que é saída
deste projeto. Contados nele:

| | |
|---|---:|
| `<h2>` no arquivo | 122 |
| deles com figurina de xadrez — são notação, não cabeçalho | **111** |
| deles contendo `Diagram` ou `Ex.` | **0** |
| deles com palavra de dicionário de quatro letras ou mais | **0** |

`♘c7`, `4.♘e2!?`, `9...♖a3`. Nenhum é cabeçalho de diagrama.

Aquele EPUB é de 18/08/2026 e a F103 é de 24/08 — ele sai com um parágrafo por linha
impressa, que é a assinatura do defeito que a F103 fechou, e portanto é saída de um código
que não existe mais. Por isso ele **não decide nada sobre hoje**, e foi preciso remedir.

#### O defeito existe, e a primeira varredura não o viu

Medido no código de hoje, com o classificador de produção, em 60 páginas sorteadas de cada um
dos oito livros de `PDF/` (480 páginas, semente fixa). "Prosa" é a linha recolhida que **não**
parece cabeçalho de diagrama:

| livro | linhas recolhidas | delas, prosa |
|---|---:|---:|
| **Darcy Lima · A Estratégia** (pt) | 15 | **12** |
| **Dvoretsky · Endgame Manual** | 9 | **6** |
| Nunn · Secrets of Rook Endings | 1 | 1 |
| Yusupov · Chess Evolution 1 | 71 | 1 |
| Yusupov Complete | 60 | 3 |
| Razuvaev · Akiba Rubinstein | 3 | 0 |
| Aagaard · Attacking Manual I | 0 | 0 |
| Seirawan · Xadrez Vitorioso | 0 | 0 |
| **total** | **159** | **23** |

**O defeito é de dois livros, e num deles é quase tudo o que a faixa recolhe**: 12 de 15 no
Darcy Lima, 6 de 9 no Dvoretsky. Nos dois Yusupov, que são 131 das 159 linhas, a faixa acerta
— o que ela recolhe são os `Diagram 12-1 △` que ela existe para recolher, e as 4 marcadas como
prosa são `Diagram` mal lido (`I]iagram 2f3`, `Dagram19`).

No Darcy Lima o que se perde é `um par de Cavalos como n`, `es no campo adversário`, `entar
peões dobrados q`, `a]uda do outro Bispo Um` — pedaços do **meio** de uma linha de prosa,
cortados onde o tabuleiro começa e onde ele acaba. Uma linha a cada cinco páginas, e cada uma
vira `<h2>` no EPUB ou um PNG que ninguém pesquisa.

**A primeira varredura desta revisão disse "0 em 240 páginas", e o erro foi meu, na régua.**
Ela perguntou *"há palavra de dicionário de quatro letras nesta linha?"*, e essa pergunta é
cega duas vezes: o dicionário do projeto é inglês, e o livro em que o defeito acontece é em
português; e notação não tem palavra de dicionário, que é o caso do Kasparov. Refeita a
pergunta como *"isto parece cabeçalho de diagrama?"*, o defeito apareceu na primeira página
que o tinha. **É a terceira vez que este ROADMAP registra "a propriedade medida não era a que
interessava", agora na régua da própria revisão.**

#### As duas réguas candidatas, e as duas caem

Com o defeito medido, foram medidas também as duas correções óbvias — **antes** de escrever
qualquer uma:

| régua | prosa salva (de 23) | cabeçalhos perdidos |
|---|---:|---:|
| a linha tem de caber no retângulo de exclusão | 6 | 4 |
| a linha continua fora da faixa (há texto de página na mesma altura) | 22 | **99** |

A primeira quase não alcança, e perde quase tanto quanto salva: o pedaço de prosa que a faixa
captura é justamente o que se sobrepõe ao tabuleiro, e ele **cabe** na exclusão.

A segunda alcança quase tudo e destrói o recurso: nos dois Yusupov o cabeçalho do diagrama
está na mesma altura da coluna vizinha e do diagrama ao lado, então "há texto de página nesta
altura" é verdade para 99 cabeçalhos legítimos — **quatro vezes e meia** o que ela salva.

**`_na_faixa` fica como está**, e não por falta de evidência do defeito — por falta de uma
régua que o separe. As duas que se apresentavam foram medidas e as duas custam mais do que
rendem.

**A direção que sobra, para quem pegar isto:** o que separa o cabeçalho da linha de prosa não
é largura nem vizinhança horizontal, é o **vão vertical acima dele**. O cabeçalho é apartado
do parágrafo; a linha de prosa está a um passo de linha da anterior. O passo por coluna já é
calculado — `_metricas_por_coluna`, F103 —, só que depois, e a faixa é decidida antes. Ligar
os dois é a fase, e não uma linha.

---

### 1. O caractere derrubado por confiança escrevia dois espaços

`_texto_da_linha` derruba o caractere abaixo de `CONF_MINIMA`, e a régua do espaço não
olhava para isso: ela corria entre caixas **vizinhas** e escrevia um espaço por vão que
passasse do limiar. Um glifo derrubado entre dois vãos largos passava por dois, e escrevia
dois espaços.

    antes    'kni  ht'      por `knight` com o `g` fraco
    depois   'kni ht'

O vão continua sendo medido onde ele existe — entre caixas vizinhas. O que mudou é **quando
ele é escrito**: enquanto nada sai, o espaço fica pendente, e sai uma vez só quando o
próximo caractere sai.

**O que este conserto não faz, e precisa ser dito:** ele não devolve `kniht`. Os vãos em
volta do buraco continuam sendo os da página, e quando eles são largos de verdade — que é o
caso da linha degradada em que o defeito aparece — há separação ali. Suprimir o espaço por
inteiro colaria `White ✝ moves` em `Whitemoves`, e há teste travando isso.

| espaços duplos na prosa | antes | depois |
|---|---:|---:|
| Yusupov · Chess Evolution 1 (264 págs.) | **472** | **0** |
| Nunn · Secrets of Rook Endings (354 págs.) | **26** | **0** |

---

### 2. Os reparos do dicionário sobem da linha para o parágrafo

A F108 ligou `lexico.arrumar_caixa` em `extrair_pagina`, uma linha de cada vez, e o
comentário dela dizia na letra que a palavra partida pelo hífen ficava de fora: *"o núcleo de
cada metade não é palavra, o portão não abre, e a correção não acontece"*. A própria F108
registrou isso em "o que esta fase não alcança".

`lexico.juntar_hifenizadas` existe desde a F9.1, tem teste, tem medição própria — a F104
estimou 490 junções no Nunn — e **não tinha um chamador em produção**. É o segundo dos "três
reparos prontos" que a F109 §4.1 lista, e o primeiro a ser ligado desde que ela os listou.

Os dois reparos passaram para `_paragrafo_de`, que é a única altura em que a palavra que o
livro imprimiu existe inteira. O vetor de espessuras da F105 anda junto: cada caractere que
sai do texto — o hífen, e o espaço que separava as duas linhas — sai também do vetor, senão
`negrito.marcar` pula o parágrafo em silêncio.

| hífen de fim de linha que ainda formaria palavra | antes | depois |
|---|---:|---:|
| Yusupov · Chess Evolution 1 | **13** | **3** |
| Nunn · Secrets of Rook Endings | **1.212** | **9** |

O Nunn é o livro que hifeniza: `dia-gram` 88×, `be-cause` 48×, `fol-lowed` 48×, `zug-zwang`
44×, `posi-tion` 43×. **A F104 estimou 490 e o número é 2,5× isso.**

**O que sobra não é junção perdida — é o teto da régua.** Conferidos um a um, os 9 do Nunn e
os 3 do Yusupov são `the a-, b- or c-files` e `the c5- and f6–pawns`: hífen e palavra
seguinte na **mesma** linha impressa, onde não há quebra para juntar. `juntar_hifenizadas` só
olha o fim de uma linha contra o começo da seguinte, e o texto exportado não guarda mais onde
a linha acabava — daí o contador ser um teto, e estar documentado como tal.

**E a junção recusa o que tem de recusar.** No Yusupov há 12 pares `palavra- palavra`; os que
o dicionário junta são `be-cause`, `king-side`, `follow-ing`, `dan-ger`, `oppo-nent` e
`compensa-tion`, e os outros são `light-squared` e `dark-squared` — hífen de verdade, que
continua no lugar. O critério é o da F9.1 e não tem limiar: junta se o resultado for palavra.

**A caixa também passou a alcançar a palavra partida**, e é ganho de graça: `bi-` + `Shop`
não abre o portão de `conhece` em nenhuma das duas linhas, e `biShop` abre.

---

### 3. A palavra colada, e o portão que a lista de 310 mil exigiu

`lexico.partir_colada` é o **terceiro e último** dos reparos que a F109 §4.1 listou como
"existem, têm teste, e não têm consumidor em produção". Ele acha onde faltou um espaço —
`ofthe` vira `of the` — e traz três condições da F9.1: a palavra não pode estar no dicionário,
tem de partir em duas que estão, e a lacuna no ponto de corte tem de ser a **maior de dentro da
palavra**.

Para a terceira condição existir foi preciso um vetor novo ao lado do de espessuras: a **lacuna
antes de cada caractere**, em larguras medianas da linha, que `_texto_da_linha` mede onde o box
e o caractere que ele virou existem lado a lado — o mesmo lugar e o mesmo motivo da F105. O
normalizador não decide nada, e é bom que não decida: as três condições comparam lacunas *da
mesma palavra* umas com as outras, então dividir todas pela mesma largura não muda resposta
nenhuma.

#### As três condições foram medidas sobre texto rotulado, e o OCR é outra população

Ligado como está escrito, o reparo dá **148 cortes em 200 páginas** do Nunn e do Yusupov, e
erra cerca de **29**:

    ofstud     -> of stud        theresult  -> the result       (bons)
    fering     -> feri ng        fmnt       -> fm nt            (erros)
    Wncura,    -> Wn cura,       Bemer—     -> Bem er—          (erros)

A causa é a lista. `partir_colada` exige que as duas metades estejam no dicionário, e o deste
projeto tem **310.465 palavras** — nele existem `ng`, `fm`, `nt`, `er` e `feri`. Na verdade
rotulada, que é onde a F9.1 mediu os 7 de 7, o único defeito é o espaço que faltou; na saída do
modelo há `fering` e `Wncura`, que também decompõem. **A condição não ficou fraca: a população
mudou.**

Isto não é achado novo — é o mesmo que `medir_lexico._parte_em_palavras` documenta na letra:
*"contra a lista grande esta função mentia: `Benko` decompõe em `ben`+`ko` e `queenside` em
`queen`+`side`, porque uma lista desse tamanho tem lixo de duas e três letras para todo lado"*.
E o remédio é o dele: **o vocabulário do próprio material**.

#### O quarto portão, e por que ele obriga a uma passada à parte

As duas metades precisam ter sido vistas **soltas, duas vezes**, no material lido
(`VISTAS_PARA_CORTAR`). Medido nas mesmas 200 páginas:

| | cortes | dos quais errados (conferidos à mão) |
|---|---:|---:|
| sem o portão | 148 | ~29 |
| com o portão | 117 | ~7 |

Ele mata dois terços do erro e custa 9 cortes bons. Uma aparição só não separa: a metade
espúria costuma aparecer uma vez, dentro da própria palavra colada de outra página.

**E é ele que faz o reparo ser uma passada à parte, e não mais uma linha do `_paragrafo_de`.**
O vocabulário só existe depois de o livro inteiro estar lido, e numa página só quase nada
aparece duas vezes. `livro.partir_coladas` é o molde do `negrito.marcar` (F105) e pela mesma
razão: o `extrair_pagina` chama com a página que acabou de ler, o `extrair` chama com todas, e
é essa que vale. É idempotente — depois do corte as metades estão no dicionário, e a primeira
condição as recusa.

Para isso o `Paragrafo` guarda as lacunas como guarda os pesos: a medida sai da linha, e a
decisão espera o livro.

#### O que rendeu, e com que precisão

No Yusupov inteiro são **103 trechos partidos** e no Nunn **371**. Conferidos: no Yusupov 99
dos 103 estão certos — os 4 errados são a fila `a b c d e f g h` do tabuleiro vazando para a
prosa, que é o defeito 3 da F109 e não deste reparo. Numa amostra de 40 dos 371 do Nunn, 40
estão certos.

    ofthe    -> of the        Ifyou       -> If you        NewYork  -> New York
    Nextis   -> Next is       equallywell -> equally well  toplay   -> to play

O efeito na tabela está na seção seguinte.

#### Um resíduo que o corte revelou, e não criou

O contador de hífens pendentes do `medir_prosa.py` sobe de 9 para 16 no Nunn, e a subida é
**boa notícia lida direito**: antes o texto trazia `ofdia- gram` e `ofan- other`, e a
remontagem dava `ofdiagram`, que não é palavra — `juntar_hifenizadas` recusava, certo. Com o
corte a esquerda vira `dia-` e `an-`, e agora `diagram` e `another` são palavras.

**São ~7 junções que a ordem dos reparos deixa na mesa**, porque o hífen se junta durante a
montagem da página, com as linhas na mão, e o corte só acontece depois, com o livro. Juntar de
novo no fim exigiria saber onde as linhas acabavam, e isso não sobrevive ao parágrafo — a não
ser pelo próprio vetor de lacunas, que traz `nan` no primeiro caractere de cada linha. Fica
registrado, com o caminho, e não entra por 7 palavras em 354 páginas.


---

### 4. O reparo de colagem, que a F66 recusou e a F69 destravou

`lexico.reparar` é o quarto da lista da F109 §4.1, e o único que **nunca teve chamador em
produção nenhum** — nem a UI, ao contrário do que aquela seção registrou; os únicos
consumidores eram `medir_reparo.py` e os testes.

Ele apaga o que veio de um box largo demais para um glifo, ancora no resto e procura no
dicionário a palavra que cabe naquele molde: `Dmamic` vira `D` + máscara + `amic`, e só
`dynamic` cabe.

#### Por que ele estava desligado, e o que mudou

**A F66 mediu e recusou**, na letra: *"62,5% de precisão é inaceitável para algo que reescreve
o texto em silêncio"*, e concluiu *"o código fica, e `livro` não o chama"*. Sem prova visual o
reparo escolhe por comprimento, e por essa régua `drazic` ganha de `dynamic` — casa sem
esconder caractere nenhum.

**A F69 construiu a prova** — perguntar ao modelo quanto ele dá a uma letra naquele pedaço de
papel — e mediu que ela separa as duas populações. Mas a F69 saiu marcada "(instrumento)": a
prova ficou escrita, medida, e sem ligar em lado nenhum.

Faltava uma coisa antes de ligar, e ela está dita na própria F69: **a régua é uma
probabilidade, e por isso ela não atravessa uma calibração.** `NOTA_MINIMA` = 0,5 foi medida em
dois modelos, e o de hoje é um terceiro — 314 classes, T = 1,825.

#### A régua remedida, e o vão que encolhe

`medir_reparo.py --nota 0.0 0.5`, nas mesmas páginas rotuladas:

| | reparos | precisão pelo rótulo automático |
|---|---:|---:|
| sem régua (nota ≥ 0) | 29 | 48% |
| **com a régua de 0,5** | **19** | 63% |

**E o rótulo automático é teto, não verdade** — é o mesmo aviso que a F66 e a F69 deixaram.
Lidos um a um os 19 que passam, os 7 que ele chama de errados são rótulo **truncado**: ele diz
`eample` onde o reparo escreve `example`, `tonamt` onde escreve `tournament`, `Wadering` onde
escreve `Wandering`, `wit` onde escreve `with`, `Bo` onde escreve `Benko`. **Os 19 estão
certos.**

O vão continua existindo, e continua encolhendo:

| modelo | aceitos | recusados | vão |
|---|---|---|---:|
| 249 classes, softmax cru (F69) | 0,884 – 1,000 | 0,000 – 0,004 | **221×** |
| 258 classes, T = 2,0993 (F69) | 0,777 – 0,998 | 0,000 – 0,052 | **15×** |
| **314 classes, T = 1,825 (hoje)** | **0,847 – 0,999** | **0,000 – 0,259** | **3,3×** |

O 0,5 continua dentro dele, e não precisou mexer. **Mas a tendência é o que vale registrar: 221
→ 15 → 3,3.** A régua não é mais "qualquer ponto do vão"; ela ainda tem folga dos dois lados, e
quem retreinar de novo tem de refazer esta tabela antes de confiar nela.

Do lado recusado, 8 são erro de verdade — `wehave` → `behave` e `Ifwe` → `Iftime`, que são
palavras lidas **certas** às quais falta só o espaço, mais `fChess` → `lichess` e três de lance
ou nome. E 2 são acerto perdido: `Dg6nce` → `Defence` com 0,001 e `Kfer` → `Safer` com 0,259.
**Quem reescreve texto em silêncio paga em recall, não em precisão**, e as duas palavras
continuam fora do dicionário, então a fila de revisão continua vendo-as.

#### O que ele acha num livro, e o que ele custa

30 páginas do Nunn, o caminho de produção inteiro:

| | |
|---|---:|
| palavras reparadas | 8 |
| extração sem o reparo | **77 s** |
| extração com o reparo | **964 s** |

    Wncura      -> Vancura        suffets     -> suffers
    fmnt        -> front          Shakhrwtny  -> Shakhmatny
    Bemer—      -> Berner—        'Vancara    -> 'Vancura

As oito estão certas — `Vancura` é a posição de torre mais citada deste livro e `Shakhmatny` é
a revista que ele cita.

**E são doze vezes e meia o tempo.** A prova pergunta ao modelo letra por letra e posição por
posição, e paga isso por candidato do dicionário; num livro de 300 páginas a diferença é entre
minutos e horas.

#### Por isso ele entra como pergunta, e o padrão é não

`extrair` e `extrair_pagina` ganharam `probabilidade`, e **sem ele o reparo não roda** — não
por acidente, mas porque rodar sem prova é exatamente a configuração que a F66 mediu em 62,5% e
recusou. A janela de exportação pergunta, com o custo escrito nela, e o padrão é **não**.

**E ele deixou de ser silencioso**, que era a outra metade da objeção da F66: a
`PaginaExtraida` conta os reparos e o relatório do fim da exportação diz quantas palavras o
dicionário trocou. Quem exportar pode conferi-las.

**Otimizar a prova não foi tentado, e não deve ser tentado de olho.** O custo está no
`provar_letras` da F69, que varre ±40% da largura de uma letra em passos de 20% — e essa
varredura é o que faz a prova funcionar onde não há vale no perfil, que é um quarto das
colagens. Cortar candidato ou passo muda o número das duas tabelas acima, e quem mexer ali
refaz as duas.

---

### A tabela das cinco famílias, refeita

Os dois livros inteiros, relidos com o modelo, o mesmo dos dois lados — o `model_meta.json`
da árvore de trabalho foi copiado para a árvore em HEAD, porque o do HEAD aponta para outro
`.pth` e a comparação mediria o modelo em vez do código.

As colunas são as três, na ordem em que os reparos entraram: o livro como estava, com o
espaço e o hífen (§1 e §2), e com o corte de palavra colada (§3).

| família | Yusupov antes | +espaço/hífen | +corte | Nunn antes | +espaço/hífen | +corte |
|---|---:|---:|---:|---:|---:|---:|
| A. o `i` partido | 350 | 350 | 350 | 155 | 155 | 155 |
| B. caixa homográfica | 0 | 0 | 0 | 14 | 14 | 15 |
| C. palavra colada | 795 | 793 | **691** | 2.360 | **1.895** | **1.553** |
| D. dígito espúrio | 456 | 456 | 456 | 496 | 496 | 495 |
| E. resto fora do dicionário | 501 | 501 | 501 | 383 | **327** | 327 |
| **com defeito** | **12,55%** | 12,54% | **11,92%** | **6,51%** | 5,61% | **4,93%** |

**O Nunn cai de 6,51% para 4,93% — um quarto do erro do livro — e o Yusupov de 12,55% para
11,92%.** A diferença entre os dois é o hífen: o Nunn hifeniza e o Yusupov quase não, e por
isso a coluna do meio move um e não move o outro. O corte move os dois, porque espaço perdido
não depende de tipografia — depende da régua do espaço, que é a mesma em todo livro.

A família B do Nunn sobe de 14 para 15, e é ganho disfarçado: `ofwheTher` era uma palavra
colada e virou `of wheTher`, que é uma palavra de prosa com caixa errada. O defeito não
nasceu; ele saiu de trás do outro, e agora está numa família onde alguém pode alcançá-lo.

**Duas coisas a registrar sobre a tabela em si.** A família B do Yusupov sai em zero porque a
F108 já está ligada dos dois lados, e a razão `S/s` deste livro é hoje **0,078** contra os
0,203 que a SPEC §1 mediu no DOCX exportado três horas antes da F108. E esta régua mede
12,55% onde a spec mediu 20,26% no mesmo livro: **a diferença é de definição, e não de
conserto** — a spec classificou à mão, sobre um arquivo, e este instrumento exige que a
palavra tenha duas letras e caracteres de prosa, o que tira a linha de fonte de diagrama que
a própria spec §2.7 mediu como contaminação da conta.

---

### O instrumento

`medir_prosa.py`, que é a conta da SPEC §1 escrita. Lê de quatro lugares — um DOCX, um EPUB,
o PDF relido com o modelo, ou um texto que ele mesmo gravou — e devolve as cinco famílias, a
razão de caixa e os dois defeitos que o texto denuncia sozinho.

**Ele foi validado contra a spec antes de decidir qualquer coisa**, e a validação é forte: a
tabela de razão de caixa do `_teste-1.docx` sai **igual número a número** à da SPEC §1 —
`S/s` = 0,203, `W/w` = 0,311, `J/j` = 1,452, `V/v` = 0,162, `Z/z` = 0,164, `K/k` = 0,148,
`P/p` = 0,077, `C/c` = 0,048, `(O+0)/o` = 0,194 — e a família A sai em 2,09% contra os 2,03%
da spec. No EPUB do Kasparov, `S/s` = **0,047**, que é o valor que a spec §2.2 registra como
o normal de um texto em inglês.

Três réguas dele foram escolhidas por medição, e as três estão documentadas no arquivo:

- **a colagem exige quatro letras de sobra.** Com três, a família C dava 1.785 palavras no
  Kasparov e engolia a E inteira: numa lista de 310.465 palavras quase todo trio de letras
  existe, e `phoros` "decompunha" em `ros`.
- **o dígito é procurado na palavra, e não no núcleo.** `lexico.nucleo` apara o que não é
  letra das **pontas** — é o que ele deve fazer, porque é o que vai ao dicionário —, e com
  isso `lut1` vira `lut` e `1nto` vira `nto`: metade da família D sumia para a E. Vale 224
  palavras neste livro.
- **o hífen é contado pela remontagem verdadeira.** A primeira versão casava as letras
  iniciais do token seguinte e contava `nor- mal1y` como junção de `normal`; o núcleo daquele
  token é `mal1y` inteiro, e a remontagem dá `normal1y`, que não é palavra. A régua frouxa
  dizia 13 junções pendentes no Nunn onde havia 1.

---

### O que esta fase não alcança, e onde isso está

**A faixa que come prosa**, que é o achado desta fase sem conserto: 12 linhas em 60 páginas
do Darcy Lima e 6 em 60 do Dvoretsky. As duas réguas candidatas estão medidas e recusadas
acima, e a direção que sobra — o vão vertical acima da linha, contra o passo da coluna —
está dita lá. `medir_faixa.py` é o que a próxima tentativa tem de bater.

As famílias A, D e o que sobra de C e E — 1.998 palavras no Yusupov, 11,9% da prosa, e 2.545
no Nunn. Elas são de segmentação e de reconhecimento, e estão na F110, na F112 e na F113.

Dos quatro reparos que a F109 §4.1 listou **não fica nenhum**: a lista fecha aqui. O que
fica em aberto é a **régua** do quarto deles — o vão da prova visual encolheu de 221× para
3,3× em três modelos, e quem retreinar refaz `medir_reparo.py --nota` antes de confiar nela.
E fica o custo: doze vezes e meia é caro demais para ser padrão, e otimizá-lo exige refazer
as duas tabelas da §4.

E ficam as ~7 junções de hífen que o corte revelou e a ordem dos reparos não alcança — ver o
fim da §3, que traz o caminho: o `nan` que o vetor de lacunas deixa no primeiro caractere de
cada linha é a marca de onde a linha começava.

E ficam os defeitos de escrita do arquivo que esta revisão levantou e que não são desta fase.
Seis já estavam na F111. **Três não estavam**, e ficam registrados aqui:

- **`exportar.trechos` descarta faixa de negrito fora de ordem, em silêncio.** Com `(10,15)`
  antes de `(2,5)`, a segunda some. Hoje é latente — `negrito._juntar` emite ordenado —, e
  ordenar na entrada fecha a porta.
- **duas tabelas coladas viram uma quando o Word abre o arquivo.** O diagrama em modo de
  fonte já tem o parágrafo de 1 pt que as separa (`exportar.py:1000`); o bloco `Tabela` não
  tem. Tabela seguida de diagrama em modo de fonte sai fundida, e livro que termina em tabela
  fica sem o separador que o Word pede.
- **símbolo que a fonte de recurso não cobre sai mudo.** `fonte_dos_simbolos` escolhe a de
  maior cobertura e o que sobra sai sem `<span>` nenhum, sem nada no relatório do fim da
  exportação dizendo quais foram.

E dois que a revisão conferiu e que estão **certos**, para ninguém os caçar de novo: o nome de
família que o `fontTable.xml` escreve bate com o nome interno das três fontes embutidas
(`SkakNew-Diagram Regular` → `SkakNew-Diagram`), e a ofuscação da fonte no DOCX segue a norma.

---

### Onde está

Tudo em `core/livro.py`:

- `_texto_da_linha` — o espaço pendente (§1) e o vetor de lacunas (§3). Devolve quatro
  coisas onde devolvia três.
- `_juntar_no_hifen`, nova, e `_paragrafo_de` — os dois reparos que se decidem com a
  palavra na mão (§2), e o `lex` que desce pelo `_agrupar_em_paragrafos`.
- `partir_coladas` e `vocabulario`, novas, e `VISTAS_PARA_CORTAR` — o reparo que se decide
  com o livro na mão (§3). Chamadas do `extrair_pagina` e do `extrair`, no molde do
  `negrito.marcar`.
- `_reparar_texto`, nova, e o `probabilidade` que desce do `extrair` até ela (§4) — o reparo
  que se decide com o **papel** na mão. `PaginaExtraida.reparos` e `.cortes` contam o que foi
  trocado, e `ui/main_window.py` pergunta antes e mostra depois.
- `Linha.lacunas` e `Paragrafo.lacunas` — a medida sai da linha e espera o livro.

Dois instrumentos. `medir_prosa.py` refaz a tabela das cinco famílias e é o critério de
aceitação desta fase. `medir_faixa.py` é o que recusou as duas réguas da faixa, e está
versionado justamente por isso: **uma recusa sem instrumento é uma opinião**, e a próxima
pessoa a olhar a faixa precisa poder refazer as duas colunas antes de escrever a terceira
régua.

`tests/test_f115_buraco_e_hifen.py`, 37 testes — os 10 dos dois primeiros consertos falham
no código de antes, conferido rodando o próprio arquivo contra uma árvore em HEAD. A prova do
§4 é injetada como a da F69, e por isso nenhum teste pede modelo treinado. A suíte inteira sai
de 1.813 para 1.850, verde.

---

## F116 — A trava da linha protegia o elo cuja confiança não diz nada — CONCLUÍDA

Saiu de uma revisão do «Detectar e Preencher (Neural)» de ponta a ponta. A revisão achou
quatro defeitos de código, que entraram antes desta fase (commit `7af07ac`: sem modelo a ação
seguia com o k-NN em silêncio; os boxes eram regenerados antes do `_busy`; `self.boxes` era
lido da thread de trabalho; um recorte com erro perdia a página inteira), e uma hipótese que
pedia medição. Esta fase é a hipótese.

### A hipótese

A trava da leitura por linha (F18, F20, F21) compara `cf >= trava` e não olha quem respondeu.
Ela existe para a linha (89,5%) não passar por cima da rede (97,6%) — e faz isso bem. Só que
a mesma comparação vale para o **último** elo da cadeia, o `easyocr`, cuja confiança a F48
mediu como plana: mediana 0,97 no erro e no acerto, e é por isso que ele entra inteiro na
fila de revisão. Plana e alta, ela passava pela trava sempre. O elo que acerta 29% no caminho
neural e 44% no híbrido, no que lhe sobra, ficava **protegido** do único conserto que tem, que
é a linha. A trava feita para o elo forte estava servindo ao elo fraco.

### Medido

`medir_cadeia.py --sem-trava-para`, nas 10 páginas rotuladas, 10.508 caracteres, com o modelo
e a base da árvore de trabalho (167.056 referências). As duas pontas saem do **mesmo processo**,
sobre as mesmas respostas memorizadas — só o roteamento muda.

| caminho | trava | segurando toda fonte | isentando `easyocr` | trocas novas | conserto / quebra / neutra |
|---|---:|---:|---:|---:|---:|
| neural | 0,70 | 97,32% | **97,37%** | 8 | 6 / 0 / 2 |
| híbrido | 0,30 | 97,43% | **97,58%** | 37 | 17 / 1 / 19 |

A conta que decide não é o total, porque o elo responde 0,4% e 1,6% dos boxes. É o que muda
nos boxes que ele respondeu:

| caminho | boxes do `easyocr` | travados | acerto antes | acerto isentando |
|---|---:|---:|---:|---:|
| neural | 38 | 35 | 28,95% | **44,74%** |
| híbrido | 165 | 165 | 44,24% | **53,94%** |

Quase todos travados, como a F48 previa: a confiança plana e alta é justamente a que passa
por `cf >= trava`. E a linha ganha do elo com folga nos dois caminhos — 6 consertos contra 0
quebras, 17 contra 1.

**A trava do resto não muda de lugar.** Varrida com a isenção ligada, a do híbrido continua
melhor em 0,30 (97,58%, caindo para 97,22% em 0,60 e 93,87% em 0,99, o mesmo desenho da
F23). A do neural dá 97,43% em 0,80 contra 97,37% em 0,70 — 6 caracteres, dentro do platô que
a F25 já chamou de platô, e o 0,70 fica.

**O acerto de produção do neural saiu 97,32%, e a F25 tinha 97,52%.** Não é regressão: o
modelo e a base são outros (314 classes, 167 mil referências contra 86 mil). Só a comparação
dentro da mesma rodada vale, e é a que está nas tabelas.

### O que entrou

- `FONTES_SEM_TRAVA = frozenset({"easyocr"})` em `ui/main_window.py`, ao lado das travas e
  com a tabela. **Só o `easyocr`**: o `learner` e o `neural` têm confiança que ordena (F51,
  separação 0,795 e 0,634), e neles a trava faz o que a F20 mediu.
- `ler_pagina` ganhou `fontes_sem_trava`, opcional e `None` por omissão — o contrato dos
  outros chamadores não muda. `_preencher_por_linha` o passa, e ele é o laço das duas ações
  «Detectar e Preencher» (Neural e Híbrido). A ação «EasyOCR por linha» também passa por ali,
  mas roda sem trava, então nada muda nela.
- **O PDF pesquisável fica de fora.** O `reconhecer` dele devolve `(char, confiança)` sem a
  fonte, e a trava do `_ler_boxes` é `conf < conf_linha_maxima` — não há como isentar por
  fonte sem mudar o contrato. A F40 mediu aquele laço em 97,52% contra 97,50% da janela; a
  diferença que esta fase abre entre os dois é de ~0,05 ponto e fica registrada.

### O instrumento estava quebrado desde a F106

A primeira rodada morreu com `AttributeError: '_Memo' object has no attribute 'candidatas'`.
O veto geométrico da F106 pede `learner.candidatas` e `predictor.predict_topk` quando a
primeira leitura não cabe no recorte, e o envelope de memorização do `medir_cadeia.py` não
tinha nenhum dos dois. O veto dispara em ~2 recortes em 10 mil — o bastante para toda rodada
cair. **Ninguém rodou o instrumento depois da F106**, e é a mesma lição da F38: o botão
desligado só aparece quando alguém aperta.

Consertado, e junto entrou o `altura_de_referencia` que as duas ações passam desde a F106 e o
`Cadeia.leitor` não passava — sem ele o veto de tamanho (ponto contra quadrado) ficava
desligado na medição e ligado na janela. `test_memo_serve_as_candidatas_que_o_veto_geometrico_pede`
guarda o envelope, e `test_rodar_isenta_da_trava_o_que_producao_isenta` guarda que toda
tabela do instrumento continue medindo produção.

### Onde está

- `ui/main_window.py` — `FONTES_SEM_TRAVA` e a chamada em `_preencher_por_linha`.
- `core/leitura_de_linha.py` — o parâmetro em `ler_pagina`.
- `medir_cadeia.py` — `--sem-trava-para`, `tabela_sem_trava`, o `_Memo` com `candidatas` e
  `predict_topk`, e o `altura_de_referencia` no `Cadeia.leitor`.

Reproduzir: `python medir_cadeia.py --neural --sem-trava-para` e
`python medir_cadeia.py --sem-trava-para`. Cobertura: `tests/test_detectar_e_preencher_neural.py`
(4 testes da isenção, 17 no arquivo) e `tests/test_f23_medir_cadeia.py` (2 novos, 27).

---

## F117 — A máscara de alfabeto chega à tela, e a cadeia passa a ter um crivo só — CONCLUÍDA

O último item da revisão do «Detectar e Preencher (Neural)» (ver F116). A F109 pôs a máscara
de alfabeto em `LearningService.ler_texto`, e só o caminho do livro a chama. As duas ações da
tela leem pela cadeia de `ocr_service`, que não a tinha: na janela, `É` e `ê` continuavam
competindo com `E` e `e` num livro em inglês. Havia duas implementações de "rede mais veto"
— o passo 1 de `fallback_chain_detalhado` e o `ler_texto` —, e um crivo que entrava numa e
não na outra é exatamente o defeito que a F1.5 registrou para os dois caminhos da cadeia.

### O que entrou

**A máscara na cadeia, com a forma do veto da F106.** `fallback_chain_detalhado` (e
`fallback_chain`) ganham `idioma`, `None` por omissão. Com ele, `cabe` passa a ser "o idioma
admite **e** a geometria admite", e a segunda passada escolhe entre as candidatas filtradas
pelos dois crivos. A regra é a mesma do `ler_texto` — filtra e escolhe entre as que sobram,
nunca inventa classe —, e a fonte da leitura não muda: a máscara não lê nada.

**Vale para o k-NN também**, e o `ler_texto` não o alcançava. As classes dele são as mesmas
pastas de `training_data`, com as mesmas letras acentuadas, e a margem do vencedor derrubado
sai `SEM_MARGEM`, como no veto geométrico.

**A tela pergunta o idioma uma vez por documento.** `MainWindow._idioma_do_livro` é a
pergunta que a exportação já fazia (camada de texto do PDF; sem ela, o usuário diz), agora num
lugar só. `idioma_da_sessao` a faz na **primeira ação que precisa**, e não na abertura — quem
abre um PDF para arrastar boxes não responde sobre idioma —, e esquece junto com o léxico.
Imagem solta fica sem idioma, que é a regra de `core.alfabeto`: página avulsa não sabe de que
livro é, e máscara sem opinião é a cadeia de antes, nunca a máscara errada. O diálogo de fim
das duas ações diz que máscara valeu.

### Medido, e o número é pequeno de propósito

`medir_cadeia.py --idioma en`, nas 10 páginas rotuladas, 10.508 caracteres, contra a cadeia
sem máscara no mesmo processo:

| caminho | sem máscara | com máscara | leituras fora do alfabeto | trocas |
|---|---:|---:|---:|---:|
| neural | 97,37% | 97,37% | 1 → 0 | 1, errada antes e depois |
| híbrido | 97,58% | 97,58% | 0 → 0 | 0 |

**Uma leitura em 10.508, e a F109 contou 1.112 num livro.** Não é contradição: as páginas
rotuladas são as mesmas em que o modelo treinou e de que a base do k-NN foi colhida — o k-NN
responde nelas consultando a própria cópia (F23, "as 2 limpas"), e a rede as viu. A letra
acentuada vence **em livro que o modelo não viu**, que é onde a F109 a mediu e onde a tela
vai ser usada. O instrumento não tem como ver isso, e o número que sustenta a máscara
continua sendo o da F109; o que esta tabela diz é o que a F106 disse do veto geométrico —
**ela não quebra nada onde não tem o que fazer**.

A única troca é um `ça` (ligadura) lido onde a verdade é `a`: a máscara derruba, nenhuma
candidata da rede passa do limiar, e o EasyOCR lê `c`. Errado antes e depois.

### O custo, que é decisão da F109 e fica registrado

`ACENTUADAS["en"]` é vazio, e um livro de xadrez em inglês escreve `Réti`, `Grünfeld`,
`Sämisch`. Com a máscara ligada eles saem `Reti`, `Grunfeld`, `Samisch` — a candidata seguinte
é a letra sem acento, e é a que a máscara escolhe. A F109 pagou isso por 1.112 leituras
erradas num livro só, e esta fase não reabre a conta; quem reabrir tem o `--idioma` para
medir.

### Onde está

- `core/services/ocr_service.py` — `idioma` na cadeia, e os dois crivos em `cabe`/`escolher`.
- `ui/main_window.py` — `_idioma_do_livro`, `idioma_da_sessao`, `_frase_do_idioma`; as duas
  ações passam `idioma=`; a exportação usa a mesma pergunta.
- `medir_cadeia.py` — `--idioma`, `Cadeia.idioma`, `tabela_mascara`; `tabela_linha` ganhou
  o sujeito da frase.

Cobertura: `tests/test_f117_mascara_na_cadeia.py`, 13 testes — a rede e o k-NN caem para a
candidata admitida, os dois crivos valem juntos, sem idioma nada muda e ninguém paga segunda
passada; a janela não pergunta para imagem, não pergunta com camada de texto, pergunta uma vez
por digitalização e de novo no próximo documento. Suíte: 1918.

---

## F118 — A palavra sem uma letra de âncora arrastava o dicionário inteiro — CONCLUÍDA

Exportar o *Grandmaster Preparation — Calculation* do Aagaard (475 páginas, digitalização
sem camada de texto) parava na 6ª página do PDF, o *Foreword*. Não travada: multiplicando.
Só acontece com o reparo de colagem ligado — a pergunta da F115 na exportação —, e por isso
o livro inteiro sai normalmente respondendo "não" a ela.

O reparo da F66/F69 apaga o que veio do box largo e **ancora no resto**: `Dmamic` vira
`D` + máscara + `amic`, e o dicionário tem uma palavra só nesse molde. No fim do prefácio
está `on the offer.`, e o OCR leu `0n thc 0ffcx.` — os **quatro** boxes do núcleo `ffcx`
saíram largos. Máscara sobre a palavra inteira, âncora nenhuma.

**Sem âncora o molde não estreita nada, e a busca deixa de ter fundo.** `_casa` não tem
pedaço para comparar e aceita toda palavra daquele comprimento; e como o trecho começa em 0,
o `_candidatos` também perde a inicial (`inicial = None`) e vai buscar no balde
`(comprimento, None)`, que é o dicionário inteiro. Medido nessa página:

| palavra lida | trechos | candidatos |
|---|---|---:|
| `ffcx` (de `offer.`) | `[(0, 4)]` — o núcleo inteiro | **100.310** |
| `ffes` (de `offers`) | `[(0, 2)]` | 2.004 |
| `Quaity` | `[(0, 1), (4, 6)]` | 40 |
| `somc` | `[(2, 3)]` | 23 |
| as demais da página | — | 0 a 5 |

Cada candidato é cobrado uma varredura de `provar_letras`, que são `5^(n-1)` partições —
3.125 para um trecho de seis letras. É esse produto que não termina.

### O que entrou

**Uma recusa, no ponto em que a máscara é decidida**, antes de `_indice_por_forma` e antes
da prova. É a mesma régua do `MAX_TRECHOS` e do `MIN_PARA_REPARAR` levada ao extremo — "sobra
pouca letra conhecida, o dicionário casa com qualquer coisa" —, e a diferença é que aqui não
sobra letra nenhuma. O `MAX_TRECHOS` já dizia que nesse caso o reparo desiste de qualquer
jeito **depois de pagar a busca**; agora desiste antes.

Vale para os dois caminhos, com prova e sem: o que falta é âncora, e o comprimento da F66
tem o mesmo nada em que se apoiar.

### Medido

**A trava não toca em nada do que o projeto mede.** Nas 11 páginas que `paginas_rotuladas`
devolve, 98 palavras chegam ao reparo — passam do `MIN_PARA_REPARAR`, não estão no
dicionário, têm box largo e cabem no `MAX_TRECHOS` — e **nenhuma delas tem o núcleo inteiro
mascarado**. Não é
arredondamento: a condição nova não dispara uma vez sequer no corpus rotulado, e a tabela do
`medir_reparo.py --prova` sai igual dos dois lados.

    suspeita=1.5  nota=0.5  consertadas=12  estragadas=7  intocadas=75   (antes)
    suspeita=1.5  nota=0.5  consertadas=12  estragadas=7  intocadas=75   (depois)

A coluna `estragadas` é teto e não conta — a F69 registra por quê: em três das sete páginas
o rótulo à mão está incompleto, e reparo certo aparece ali como estrago.

Na página que parava, o efeito é o que se espera de tirar 100.310 candidatos da conta:

| página 6 do PDF (índice 5) | antes | depois |
|---|---|---|
| com reparo de colagem | não termina em 10 min | **65,1 s** |
| sem reparo de colagem | 1,0 s | 1,0 s |

Os 65,1 s que sobram continuam sendo o custo do reparo que a F115 registrou (~12×), e não o
desta fase.

**E a página sai com 0 reparos aceitos**, dos dois lados. É o número que fecha o argumento:
nem o `ffcx` nem o `ffes` sustentam troca na prova visual, e não sustentariam mesmo que a
busca terminasse — molde que não estreita não tem o que entregar. O trabalho que a exportação
não conseguia terminar não estava produzindo nada.

### O que fica registrado, e não entrou

O `ffes` da mesma página arrasta 2.004 candidatos **com** âncora: duas letras conhecidas,
trecho começando em 0, `inicial = None` outra vez. É bem menos que 100 mil e termina, mas é
a mesma forma, e um teto de candidatos — "acima de N é empate, e empate manda desistir" —
resolveria as duas. Não entrou porque seria uma régua nova sem a varredura que a escolhe,
e este é o defeito que a `NOTA_MINIMA` documenta como caro de fazer direito. Quem for medi-lo
tem o `medir_reparo.py --exemplos` e a distribuição de candidatos por palavra.

### Onde está

- `core/lexico.py` — `reparar`, a recusa antes da busca.

Cobertura: `tests/test_f118_mascara_sem_ancora.py`, 6 testes — o núcleo todo mascarado
desiste, a prova nem é consultada, o caminho sem prova desiste igual, uma âncora só basta
(no começo ou no fim), e `reparos_da_pagina` não devolve a palavra. Suíte: 1952.

---

## F119 — A prova do reparo perguntava à rede uma letra de cada vez, e a exportação passava horas no sumário — CONCLUÍDA

"O Exportar/livro pelo nosso OCR parece travar" (2026-09-23). A sessão aberta era a do
**Documento editorial** — o mesmo leitor (`livro.extrair`) e a mesma caixa do "Livro" — sobre
*The Russian Endgame Handbook* do Rabinovich (525 páginas, ClearScan: a régua da F110 recusa
a camada e tudo vai ao OCR), com o reparo de colagem ligado. Ela estava **na página 4 havia
mais de uma hora**, com seis núcleos ocupados, a memória parada e nenhuma operação de disco:
nem o PNG que o `pytesseract` grava por página.

Achado sem instalar nada: a pilha da thread da tarefa lida de fora pela tabela
`_Py_DebugOffsets` que o CPython 3.13 põe no começo do `_PyRuntime`. Todas as amostras
diziam o mesmo:

    extrair_pagina → _reparar_texto → lexico.reparar → prova_de_reparo.provar
      → provar_letras → probabilidade_de → SimpleCNN.forward

A página 4 é o sumário. Na linha 7, `B. Mate with the queen........ l8`, o OCR leu
`Matewith`; os boxes largos mascaram sete das oito letras, o trecho começa em 0, o
`_candidatos` perde a inicial e vai ao balde `(comprimento, None)` — a forma que a F118
registrou e deixou de fora —, e o dicionário devolve **22.852 candidatos**, cada um cobrado
uma varredura de `provar_letras`. A ~27 candidatos por segundo, catorze minutos numa palavra.
O sumário do livro tem 35 palavras assim nas páginas 4 a 7 (`Bish()p`, `F()rcing`,
`maj()rity` — o `o` desta fonte sai `()`), de 1.612 a 22.852 candidatos, e nenhuma sai com
reparo.

### Por que não o teto de candidatos da F118

A F118 sugeriu "acima de N é empate" e não o pôs por falta da varredura. A varredura foi
feita — as 12 páginas de `paginas_rotuladas`, com a prova — e **reprova o teto**: 8 dos 20
reparos aceitos vêm de mais de mil candidatos. São as palavras curtas e comuns em que a
colagem pega a primeira letra, justamente as que o balde sem inicial arrasta inteiro:

| lido | candidatos | reparo aceito |
|---|---:|---|
| `wih` | 12.768 | `with` (0,849) |
| `kiow` | 12.680 | `know` (0,989) |
| `rwo` | 3.434 | `two` (0,997) |
| `tbe` | 2.566 | `the` (0,981) |
| `fow` | 1.812 | `few` (0,999) |
| `Bawo` | 420 | `Benko` (0,983) |

Qualquer teto abaixo de 12.768 perde o `with`; abaixo de 1.812, perde os cinco. O número de
candidatos não mede se o molde estreita; mede o tamanho do balde.

### O que entrou

**O custo deixou de ser por candidato.** A nota não muda — a rede é determinística —, só
deixa de ser recalculada:

- `NeuralPredictor._probabilidades` guarda o softmax **por recorte** (a temperatura na chave;
  o `load` esvazia). A prova pergunta ao mesmo pedaço de papel por uma letra de cada vez, e
  cada pergunta era uma passada da rede para ler uma posição do mesmo vetor.
- `prova_de_reparo` passa a ter três memórias: a do trecho, que já havia; a das letras que
  cabem num box (`por_box`); e a do recorte e letra (`provar_letras(pedacos=)`), que antes
  valia só dentro de uma chamada.

**A barra do "Documento editorial" diz a página.** A fachada não tem canal de progresso, e
a ação rodava com a barra girando e "Carregando modelo neural..." o livro inteiro — quarenta
minutos de leitura e uma página presa eram a mesma tela. `ExtratorDeLivro` e
`pipeline_de_producao` recebem `progresso=`, e a barra passa a ser determinada.

**O "Cancelar" alcança o reparo.** O token era consultado entre páginas; com a prova ligada,
cancelar esperava a página acabar. A `probabilidade` que chega a `livro.extrair` consulta o
cancelamento antes de perguntar à rede, nas duas ações.

### Medido

O corpus rotulado sai **idêntico palavra a palavra** — as 101 palavras que chegam à busca,
os 20 reparos, as notas e as contagens de prova —, e o tempo das 11 páginas cai de mais de
15 minutos (a rodada antiga foi interrompida no prazo, ainda na p. 11 do *Practical Chess
Defence*, entre o `xf6er` de 7.129 candidatos e o `rwo` de 3.434) para **36 s**.

No sumário do Rabinovich, com o reparo ligado (`py -3.13`, o interpretador do app):

| página | antes | só `pedacos` | as três memórias | sem reparo |
|---|---|---:|---:|---:|
| 4 | mais de 1 h, sem terminar | 76,8 s | **20,6 s** | 12,7 s |
| 5 | — | 95,4 s | **24,1 s** | 16,7 s |
| 6 | — | 88,2 s | **22,9 s** | 12,5 s |
| 7 | — | 40,5 s | **13,6 s** | 9,1 s |

O `Matewith` sozinho: ~14 min → 12,5 s → **1,7 s**. Na janela de verdade (ação editorial,
reparo ligado, páginas 3 a 6), a barra vai de "página 0/4" a "4/4", a ação inteira leva
72,7 s e o laço do Tk volta a cada 32 ms (p99 128 ms) durante a exportação toda.

Sem o reparo o livro já saía: as 525 páginas em 43,5 min (4,9 s por página, máximo 17 s).
Era o reparo que prendia, e a barra parada que não deixava ver.

### O que fica registrado, e não entrou

- **A thread da interface ainda para antes da caixa**: a carga do modelo no
  `_avisar_do_modelo` (2,5 s, uma vez por sessão — o docstring já aceita) e a régua da
  camada (`pdf_nativo.amostrar`), que levou 5,5 s no livro do Darcy Lima e 0,1 a 0,5 s nos
  outros. Passa do limite em que o Windows escreve "Não está respondendo" só nesse livro.
- **`provar_letras` ainda enumera `5^(n-1)` partições por candidato.** Com as memórias, o
  que sobra é Python (1,7 s no `Matewith`); se um dia pesar, é um máximo de mínimos numa
  cadeia, e sai por programação dinâmica.
- **O Tesseract é chamado sem prazo.** Nenhuma página travou nele aqui, mas um executável
  que não volta prende a tarefa do mesmo jeito. *Entrou na F124.*
- **O `o` lido `()` no sumário do ClearScan** é da leitura, não do reparo.

### Onde está

- `core/neural_trainer.py` — `NeuralPredictor._probabilidades` e `RECORTES_GUARDADOS`.
- `core/services/box_service.py` — `provar_letras(pedacos=)`, `prova_de_reparo` com
  `por_box` e `pedacos`.
- `core/editorial_legacy.py` — `ExtratorDeLivro(progresso=)`, `pipeline_de_producao(progresso=)`
  e a `probabilidade` que consulta o token.
- `ui/main_window.py` — o progresso e a barra determinada do "Documento editorial"; a
  `probabilidade` cancelável do "Livro".

Cobertura: `tests/test_f119_prova_por_recorte.py` (5 testes — a letra repetida não volta à
rede, a nota é a mesma com e sem a memória e por box, o vetor serve a todas as letras, o
`load` esvazia, e `provar_letras` sem `pedacos` é o de antes), dois em
`tests/test_fachada_de_producao.py` (o progresso de cada página, o cancelamento dentro da
prova) e um em `tests/test_f26_livro.py` (a barra determinada com a página). Suíte: 3013
(`-m "not slow"`).

---

## F120 — O diagrama em fonte saía 7×8: a casa clara da Merida era o espaço da ponta de um parágrafo — CONCLUÍDA

"Os diagramas do livro ficaram no formato 7x8" (2026-09-23), com o *The Russian Endgame
Handbook* do Rabinovich exportado em EPUB com os diagramas na Chess Merida, e um diagrama
do plugin ChessMeridaOCR do Sigil ao lado como o certo. O que o usuário colou da p. 368:

    <p>T + +l+</p>

    <p>+ + + +</p>

Sete caracteres por fila. A posição é `1r4k1/8/5PK1/8/8/8/R7/8`, e a oitava fila na Merida é
` T + +l+` — **na Chess Merida a casa clara vazia é o espaço** (a SkakNew usa o `0`), e
como a cor alterna, toda fila começa ou termina numa casa clara. Só `r+ + + +` começa numa
peça e termina numa casa escura; era a única com oito no que ele colou.

### Onde a casa sumia

Não no programa. O EPUB no disco, lido às 21h, tinha `<p> T + +l+</p>` — oito casas — e a
folha pedia `white-space: pre`, que o Chromium respeita: desenhado no Edge, o tabuleiro
fechava 8×8. O `sigil_v6.ini` tinha esse EPUB no topo dos recentes, e o recuo com uma linha
em branco entre os `<p>` do que ele colou é o do **"Mend and Prettify" do Sigil**, que apara o
começo e o fim do conteúdo de cada bloco de texto e deixa só o `<pre>` intacto. Às 22:11 o
arquivo foi regravado pelo Sigil, e aí sim: os 944 diagramas do livro com fila de sete.

O mesmo acontece em qualquer programa que trate o `<p>` como parágrafo — e é o que ele é —,
e no leitor que não aplica a folha do livro: sem o `white-space: pre`, o espaço da ponta de um
parágrafo cai como cai o de qualquer outro. O diagrama dependia de uma única declaração de CSS
para existir, e dizia isso como `<p>`.

### Por que o `<pre>`, e não trocar o espaço

- **O `&#160;` na ponta** não é espaço para o HTML, mas a `ChessMerida-Diagram.ttf` não
  tem U+00A0: o leitor pegaria o espaço fixo da `monospace` (0,6 em), e a fila andaria
  meia casa. Dar o glifo à fonte exigiria trocar a fonte de todo livro já exportado.
- **O `*`**, que o `LEEME__D.TXT` da própria Merida lista como a outra tecla da casa
  clara ("[espacio] ó *"), não é branco: o glifo tem um ponto de 25 unidades (em 2048) no
  canto de baixo — invisível no papel, um pixel cinza em cada casa clara numa tela de 300 ppi.
- **A moldura em glifo** (`$ T + +l+%`, como o plugin do Sigil faz) protege as pontas, mas
  só quando há moldura: a "sem" continuaria exposta, e a SkakNew nem tem glifo de borda.

O `<pre>` é o elemento do HTML para texto pré-formatado: quem arruma o código não mexe no
que ele contém — o diagrama do plugin, que é um `<pre>` e passou pelo mesmo Sigil, chegou
com as filas inteiras —, e sem folha nenhuma o leitor já o desenha com o espaço.

### O que entrou

- **As filas num `<pre>` só**, dentro do mesmo `div.diagrama`, nos dois escritores —
  `exportar._diagrama_em_texto` e `dialeto.div_do_diagrama`, que continuam dando o mesmo
  tabuleiro (R5). A régua das coordenadas vira `<span class="colunas">` na última linha, e
  nenhuma quebra logo depois do `<pre>`: o analisador de HTML come a primeira, o de XML não.
- **A folha pega os dois**: `div.diagrama pre, div.diagrama p` e a regra da família por
  fonte idem (`seletor_do_tabuleiro`). O `p` fica pelos diagramas de antes que o editor
  guardar como ilha.
- **O editor lê as duas formas** (`_filas_do_pre`, `_filas_dos_paragrafos`), e a
  orientação sai de `_reproduz`, que aceita a fila **aparada**: o FEN do `title` manda na
  posição e o tabuleiro é redesenhado dele ao gravar, então a fila de sete ainda decide a
  orientação sem virar "revisar". Uma casa trocada no meio continua "revisar".
- **A folha de um livro de antes aprende o `pre` ao ser gravada**: `fontes.regras_para_o_pre`
  repete no bloco `pybox:fontes` as regras que a folha escreve para o `p` das filas — o corpo
  que o livro escolheu, a entrelinha, a família —, sem tocar no resto da folha; o PDF do
  editor põe as mesmas no `user_css`. Sem isso, o livro reaberto sairia com o `<pre>` na
  `monospace` do leitor e com a margem de 1 em que o `pre` tem de fábrica.

### Medido

No `fitz.Story` (o motor do PDF do editor), com a folha e a fonte do próprio EPUB, contando
as casas desenhadas por fila da p. 368:

| marcação | intacta | aparada como o Sigil |
|---|---|---|
| um `<p>` por fila (antes) | 8 em todas | **7** em sete filas, 8 em `r+ + + +` |
| um `<pre>` (agora) | 8 em todas | 8 em todas |

No Edge (Chromium), as cinco formas lado a lado: a de antes intacta fecha 8×8, a do disco
depois do Sigil é a de listras verticais que o usuário viu, e a de agora fecha 8×8 intacta e
aparada.

O livro inteiro, já estragado pelo Sigil, **numa cópia**: `epub.ler` em 5,5 s lê os 944
diagramas como "ok" (nenhum vira ilha nem "revisar"); `epub.escrever` em 1,5 s grava 944
`<pre>`, todos com oito filas de oito, e a folha ganha no bloco `pybox:fontes` o
`div.diagrama pre { … font-size: 16pt; … white-space: pre; }` e a família da Merida. Ou
seja: **o livro que já passou pelo Sigil se conserta abrindo e salvando no editor**, sem
exportar de novo do PDF.

### O que fica registrado, e não entrou

- **`test_adapter_sem_perdas::test_o_epub_do_round_trip_e_byte_identico` oscila.** O
  `z.writestr(nome, …)` carimba cada entrada do zip com a hora local, e o
  `SOURCE_DATE_EPOCH` que o teste põe só vale para o `dcterms:modified`: dois EPUBs gravados
  dos dois lados de uma virada de 2 s saem diferentes. Caiu uma vez aqui, com a máquina
  carregada, e passou de novo sozinho e na mesma ordem. *Consertado depois (PD-00 de
  `docs/ROADMAP_PENDENCIAS.md`): o `exportar` carimba toda entrada do zip com um instante
  só, em UTC; `tests/test_exportacao_reprodutivel.py`.*
- **Um `div.diagrama` de fora, sem FEN no `title`, com fila aparada continua virando ilha**:
  `render_diagrama.fen_de_linhas` exige oito casas. Todo diagrama que o projeto escreve leva
  o FEN no `title`.
- **A moldura sem coordenada continua na CSS** (`caixa`, F99), e não em glifo como no plugin
  do Sigil. Com o `<pre>`, as duas sobrevivem ao "Mend and Prettify".

### Onde está

- `core/exportar.py` — `_diagrama_em_texto`.
- `core/editor/dialeto.py` — `div_do_diagrama`.
- `core/estilo_do_livro.py` — `CSS_DO_DIAGRAMA`, `CSS_DA_FONTE_DO_DIAGRAMA` e
  `seletor_do_tabuleiro`.
- `core/editor/xhtml.py` — `diagrama_de_div`, `_filas_do_pre`, `_filas_dos_paragrafos` e
  `_reproduz`.
- `core/editor/fontes.py` — `regras_para_o_pre` e o bloco de `embutir`.
- `core/editor/pdf_io.py` — `_css` e `_fontes`.

Cobertura: `tests/test_f120_diagrama_em_pre.py` (11 testes — as filas no `<pre>` com oito
casas, o desenho do `fitz.Story` intacto e aparado nas duas marcações, a folha, coordenada e
moldura em glifo no `<pre>`, a ida e volta pelo editor, o livro de antes aparado voltando
inteiro nas duas orientações, a casa trocada que continua "revisar", as regras do `pre` só
quando faltam, a folha de antes regravada e desenhada 8×8, e o PDF do editor do livro de
antes); `test_f59`, `test_f99`, `test_f111` e `test_editor_epub_completo` passam a pedir o
`<pre>`, e o golden `tests/dados/editor/capitulo.xhtml` mudou só no diagrama. Contra o
código de antes, 8 dos 11 testes novos falham. Suíte: 3052 (`-m "not slow"`), e os testes
`slow` do `epubcheck` passam; o EPUB novo do exportador sai do `epubcheck` sem erro.

---

## F121 — O pontilhado do sumário virava a régua de tamanho, e o ponto saía apóstrofo — CONCLUÍDA

Achado de passagem da F112. Na janela, o veto de tamanho da F106 compara o maior lado do
recorte com `proporcao.altura_de_referencia` — a mediana da altura dos boxes da página —, e
é ela que separa o `.` (até 0,7 da referência) do `■` (daí para cima). **Num sumário de
pontilhado os pontos são a maioria dos boxes**, e a mediana vira a altura de um ponto. Na
p. 8 do Seirawan, que é rotulada:

- 1.838 dos 2.173 boxes são `.` (85%), e a mediana é 6 px — a de um ponto;
- o ponto mede de 0,83 a 1,83 da referência, e nenhum dos 1.838 cabe como `.`;
- `ler_texto(recorte, referencia, idioma="pt")` lê **1.431 dos 2.173 boxes como `'`**, e a
  página sai com 14,40% de acerto. Sem a referência, 1.836 dos 1.838 pontos saem `.`.

E o par que o veto existe para separar se invertia: com a referência na altura do ponto, um
ponto de 6×6 cabe como `■`. O caminho do livro (`core/livro.py`) não passa `referencia` e
nunca foi afetado; afetados são as duas ações «Detectar e preencher» e todo `ler_texto` com
referência.

### Por que não o percentil, nem "o que não é miúdo perto das letras da página"

Foram as duas saídas que o achado apontou, e as duas foram medidas no mesmo material: as 27
páginas com `.box` (as 12 de `paginas_rotuladas` e outras 15 em `PDF/`) e as 18 primeiras
páginas de cada um dos nove livros de `PDF/` — 161, renderizadas e segmentadas como a janela
faz, porque é nelas que moram os sumários.

| régua | p. 8 do Seirawan | páginas com `.box` em que a referência muda (de 27) | primeiras páginas em que muda (de 161) |
|---|---:|---:|---:|
| a mediana (F106) | 6 | — | — |
| p75 | 7 | 25 | 153 |
| mediana dos boxes acima de 0,4 do p90 | 28 | 13 | 48 |
| portão pelo 20º box mais alto | 28 | 1 | 10 |
| **a linha (esta fase)** | **28** | **1** | **8** |

- **O percentil não alcança.** Na p. 8 os pontos são 85% dos boxes, e o p75 ainda é de
  ponto (7 px). Subir o percentil só empurra o defeito para o sumário seguinte, de mais
  pontos.
- **"O que não é miúdo perto do topo da página" conserta a p. 8 e mexe em outras doze**,
  cinco delas entre as onze em que o envelope da F106 foi medido (Kasparov pp. 13, 14, 33,
  57 e 128). O motivo é tipográfico: a mediana de uma página de texto mora na fronteira entre
  as letras de altura de x e as altas, e tirar os miúdos — até 12% dos boxes nas páginas
  com `.box` — basta para ela pular para as altas (Darcy Lima p. 204, de 44 para 54). Na
  página de rosto do Seirawan (p. 4), cujo título ocupa 15% dos boxes, ia de 35 para 55 —
  para 90 com o corte em 0,5.
- **O portão pelo 20º box mais alto** — trocar só quando a mediana é menor que um quarto
  dele — muda só a p. 8 entre as rotuladas, mas tem margem de nada: o ponto de sumário mede
  de 0,11 a 0,18 desse box, e as páginas de abertura, em que o 20º box é letra de título
  (*Calculation* pp. 12 e 16, Seirawan p. 6), de 0,28 a 0,31. A abertura do capítulo 1 do
  Yusupov (p. 9, diagramas ao lado do texto) já dá 0,24, e a referência dela ia de 19 para
  31.

A raiz das três é a mesma: **a distribuição das alturas sozinha não separa o sumário da
página de rosto.** "85% de boxes pequenos e 15% bem maiores" descreve as duas — na p. 8, os
pontos e as letras dos títulos; na p. 4, o texto e as letras do título. O que as separa não
está no histograma: é o ponto do pontilhado **morar dentro da altura das letras da própria
linha**, porque ele liga o título ao número da página, e o texto da página de rosto não
morar na linha do título.

### O que entrou

`proporcao.altura_de_referencia` pergunta à linha. A mediana continua sendo a referência, até
o último pixel, **menos quando ela é de miúdos**: se a maioria dos boxes da altura da mediana
tem o centro dentro da faixa vertical de alguma letra — um box de 2,5 a 10 vezes a mediana —,
a referência passa a ser a mediana dessas letras. As faixas das letras se unem e cada centro
é procurado por bisseção, na thread da interface como antes: 1,2 ms na p. 8 (2.220 boxes) e
4,7 ms na página maior da varredura, a capa do Seirawan com 5.530.

Os dois números da faixa estão em `LETRA_SOBRE_O_MIUDO`, e os dois saíram de medida:

- **Embaixo, 2,5.** O `.` mais gordo que a F106 mediu vai a 0,50 da mediana e a maiúscula a
  1,4, então a maiúscula da linha dele passa de 2,8 vezes o ponto. Em 2 a regra já dispara
  em duas páginas comuns: a p. 7 do *Attacking Manual*, cujo `J` desce da base e mede 2,05
  vezes a mediana — três `J` cobrem 57% dos boxes da altura dela numa página de 236 —, e a
  abertura do capítulo 1 do *Calculation* (p. 16). **De 2,5 a 4, as páginas que disparam são
  as mesmas.**
- **Em cima, 10.** O ponto mais fino medido é 0,15 da mediana, e a maiúscula dá 9,3 vezes
  ele. Acima disso não é letra — é moldura, fio de tabela, figura —, e a faixa de uma moldura
  abrigaria a página inteira. De 8 a 15 as páginas que disparam são as mesmas; em 6 sai uma
  das capas.

Duas escolhas de forma. A faixa é só vertical, sem o `x`: as colunas se somam, e tanto faz —
pergunta-se se o miúdo está na altura de uma letra, e não de qual. E ela pede o **centro** do
miúdo, e não ele inteiro: o ponto que desce um pixel abaixo da base continua na linha.

### Medido — `medir_referencia.py`

**Onde a referência muda.** Nas 27 páginas com `.box`, em uma: a p. 8 do Seirawan, de 6 para
28 — tanto com os boxes do gabarito quanto com os que a janela gera (`--gerados`). Nas outras
26 ela é a mediana de antes, e por isso o `medir_proporcao.py` sai **idêntico, byte a byte**,
antes e depois: as 12 páginas rotuladas, 11.628 caracteres, os cinco níveis de engrossamento
e a lista de exemplos. O `medir_cadeia.py` segmenta essas 12 páginas do jeito dele
(`segmentar(..., "arbitrado")`), e com esses boxes a referência também é a mesma nas 12.

Nas 161 primeiras páginas dos nove livros, em oito:

| página | boxes | referência | leituras que mudam |
|---|---:|---:|---|
| Seirawan p. 8 — sumário | 2.220 | 6 → 28 | 1.858 (`'`→`.` 1.448, `,`→`.` 236, `i`→`.` 108) |
| Darcy Lima p. 2 — índice | 2.736 | 11 → 57 | 2.004 (`'`→`.` 1.692, `,`→`.` 155, `*`→`.` 135) |
| Darcy Lima p. 3 — índice | 2.798 | 11 → 54 | 1.812 (`'`→`.` 1.434, `,`→`.` 282) |
| Darcy Lima p. 4 — índice | 2.850 | 11 → 57 | 1.881 (`'`→`.` 1.419, `,`→`.` 370) |
| Yusupov CE1 p. 14 — exercícios | 592 | 6 → 30 | 6: os pontos de `Ex. 1-1` a `Ex. 1-6` |
| Darcy Lima, Razuvaev e Seirawan p. 1 — capas | 596 a 5.530 | 4–6 → 14–33 | 154, 182 e 3.617: cisco de foto |

Na p. 14 do Yusupov a mediana é o cisco da hachura dos seis diagramas, e as seis leituras que
mudam são, uma por uma, o ponto de `Ex.` — cinco saíam `'` e uma `*`. Nas capas a regra
dispara porque o cisco da foto também mora na altura dos blocos maiores; ali não há texto a
ler de um jeito nem do outro. **A maior fração sem disparo** é 0,50, a da outra página de
exercícios do Yusupov (p. 15) — a regra pede mais da metade —, e numa página de texto é 0,29:
a abertura do capítulo 1 que o portão pelo 20º box errava. Nas páginas com `.box`, 0,14. Os
sumários ficam em 0,99 e 1,00.

**O par.** O `.` e o `■` rotulados das 27 páginas, em múltiplos da referência:

| | `.` (3.194) | do lado errado do corte 0,7 | `■` (6) | do lado errado |
|---|---|---:|---|---:|
| antes | 0,15 a 1,83 | 1.839 | 1,22 a 1,55 | 0 |
| depois | 0,15 a 1,14 | **1** | 1,22 a 1,55 | 0 |

Na p. 8, os pontos vão de 0,83–1,83 para **0,18–0,39**. O único `.` que sobra acima do corte
é o `♗` de `13.♗d4`, na p. 20 do Kasparov, rotulado `.` — erro do gabarito, um recorte de
33×33. O vão da F106 continua onde estava.

**A leitura, com o gabarito** (`ler_texto`, rede e veto, `idioma="pt"`), na p. 8: 1.837
leituras mudam, e a página vai de **14,40% para 98,85%**. Pelo rótulo são 1.836 consertos e
uma quebra — e a quebra é do gabarito: o box rotulado `,` que agora sai `.` (0,91) é um ponto
do pontilhado logo depois de "Índice". Ele saía `,` porque o veto recusava o ponto.

### O que fica registrado, e não entrou

- **O quebrador de linhas da janela usa a mesma mediana**, para `CAIXA_CURTA`,
  `FOLGA_DE_LINHA` e `FOLGA_DE_COLUNA` (`leitura_de_linha.quebrar_em_linhas`). Na p. 8 ele dá
  22 linhas com a mediana de ponto e 21 com a das letras: uma quebra a mais, não conferida
  contra gabarito. O `preprocess.denoise`, que a F106 cita como "o mesmo denominador", não
  muda nada ali: o piso de 2 px² decide com as duas medianas.
- **O miúdo que não mora em linha nenhuma** — cisco entre as linhas de uma página suja — não
  é pontilhado, e a referência fica com a mediana; um teste diz isso na letra. É a pergunta
  que separa o sumário da página de rosto, e ela não sabe responder outra coisa.
- **O caminho do livro não passa referência** (F106) e continua sem o teste de tamanho: não
  chegam lá nem o defeito nem a correção.

### Onde está

- `core/proporcao.py` — `altura_de_referencia`, `_letras_que_abrigam` e `LETRA_SOBRE_O_MIUDO`.
- `medir_referencia.py` refaz as tabelas: as páginas com `.box` (com `--gerados`, a partir dos
  boxes da janela), `--primeiras 18` para as primeiras páginas de cada livro, `--pdf ...
  --paginas` para uma página qualquer.

Cobertura: `tests/test_f121_pontilhado.py`, 11 testes. Os sete do sumário falham sem a
correção: o ponto cabe como `.` e não como `■`, a referência é a das letras, a cadeia da
janela e o `ler_texto` leem `.`, 90% de pontos ainda acham as letras, e o ponto um pixel
abaixo da base continua na linha. Os outros quatro prendem o que ela não pode mexer: a página
comum fica com a mediana até o pixel, a página de rosto não troca o texto pelo título, a
moldura não abriga a página, e o miúdo fora das linhas não é pontilhado. Suíte: 2.993 e 12
puladas, com as `slow`.

---

## F122 — A moldura do diagrama em texto sai da própria fonte, e a SkakNew ganhou a dela — CONCLUÍDA

"Gostaria que a opção de borda dos diagramas Chess-Merida-Diagram e Skak-New-Diagram sejam
feitas com a própria fonte" (2026-09-24), com o exemplo do plugin ChessMeridaOCR do Sigil:

    !""""""""#
    $ + + + +%
    …
    /(((((((()

Até aqui a moldura sem coordenada saía **por fora do texto**: a borda da CSS no
`div.diagrama.caixa` do EPUB e a borda da célula no DOCX. Só com coordenada, e só na Merida,
a grade de dez em glifo entrava (F99). A Merida sempre teve os oito pedaços das duas
molduras e as quinas redondas; a SkakNew de 2004 não tinha glifo de borda nenhum — a `skak`
do LaTeX desenha o filete por fora.

### O que entrou

- **Uma decisão só**: `render_diagrama.linhas_do_diagrama(fen, fonte, orientação, moldura,
  cantos, coordenadas) → (linhas, emolduradas)`. Com moldura e com os glifos dela, a grade;
  com coordenada, a grade rotulada, se a fonte tiver o rótulo; senão, as oito linhas de
  sempre. Quem escrevia a decisão à mão passou a chamá-la: `livro`, `pdf_nativo`,
  `editorial_legacy` (a figura redesenhada da revisão), e no editor o XHTML e o DOCX. A
  `grade` ganhou `com_rotulos=False`, que troca a `filas`/`colunas` pela `esquerda`/`base`:
  a do exemplo do usuário sai idêntica, caractere a caractere.
- **A SkakNew com moldura** (`gerar_moldura_da_skaknew.py`): 24 glifos — os oito pedaços da
  simples e da dupla e as quatro quinas redondas de cada —, desenhados no script com as
  proporções da Merida (vão 17, filete 49, entrelinha da dupla 51, filete de fora 83, em
  1000; o raio é o `RAIO_DO_CANTO` que o projeto já usava). **Só se acrescenta**: os 47
  glifos de 2004 guardam os bytes, o cmap só ganha codepoints livres, e a cópia é um
  superconjunto da original, que fica em `fonts/SkakNew-Diagram-original.otf`. A LPPL
  permite modificar e pede que se diga: a tabela de nomes diz, e a família continua
  `SkakNew-Diagram` porque é a chave do mapa e o nome que o DOCX pede no run. A dupla usa
  as teclas da Merida (`! " # $ % / ( )`); a simples e as quinas não podem (`1`–`5` são as
  sobreposições desta fonte, `a s A S` são peças) e ficaram em `[ = ] { } 7 8 9` e
  `g h d f` / `G H D F` — o mapa diz, e o script recusa tecla ocupada.
- **O editor lê a moldura** (`render_diagrama.moldura_da_grade`): a grade diz qual moldura
  é, a quina e se traz rótulo — antes, dez linhas eram "coordenada, moldura simples", e a
  dupla voltava simples. O `div.diagrama caixa` não diz qual é, e a regra da folha diz
  (`dialeto.moldura_da_folha`, lida pelo `epub.ler` antes dos capítulos): **o livro
  exportado sem moldura continua sem**; o que tinha a da CSS ganha a da fonte ao ser gravado.
- **O livro com a SkakNew de 2004 embutida ganha a nova** (`fontes.desatualizada`): mesmo
  nome de arquivo e mesma família, e o `@font-face` do livro continuaria desenhando `[` e
  `=` com uma fonte que não os tem. Ao gravar o EPUB e o HTML, os bytes da do livro são
  trocados pelos do projeto, no mesmo lugar; o PDF leva a do projeto. Só troca a que não
  desenha tudo o que o mapa promete.

### O que o navegador achou e o `fitz` não

Desenhadas pelo `fitz`, as molduras da SkakNew fechavam. **No Edge, a de cima e a de baixo
saíam tracejadas.** O charstring do CFF guarda o avanço como diferença do `nominalWidthX` —
107 nesta fonte —, ou não guarda nada quando ele é o `defaultWidthX`; o `T2CharStringPen`
escreve o número cru, e cada peça andava 1107. O `fitz` lê o avanço do `hmtx` (1000), o
Edge o do CFF. O `--conferir` passou a medir os dois (`T2WidthExtractor`), e pega a fonte
errada: "anda 1107 no CFF, e o `hmtx` diz 1000".

### Por que o PNG continua com o filete da caneta

A grade em glifo, recortada na tinta, sai 3,4% mais larga que as oito casas na simples — e
a F97 mede que o diagrama desenhado e o recorte da página, que convivem no mesmo livro,
tenham quase o mesmo tamanho (menos de 2%). A caneta desenha a mesma moldura, com o raio da
Merida (F101); com coordenada na Merida o PNG continua sendo a grade, como desde a F99.

### Medido

- O exemplo do usuário: `grade("8/5k2/8/5K2/5P2/8/8/8", Merida, dupla, reto,
  com_rotulos=False)` é a mesma lista de dez linhas que ele colou.
- A SkakNew nova nas quatro provas do `medir_fonte_diagrama.py`: fechamento, avanço, tinta e
  ida e volta pelas duas redes — 128 de 128 casas nas 24 combinações e 2560 de 2560 nos 40
  tabuleiros do corpus.
- No Edge, as seis molduras (as três da Merida e as três da SkakNew, inclusive a do exemplo)
  fecham; no `fitz.Story`, cada fila da grade tem dez casas nas duas fontes.
- Um livro de antes com a folha em "sem", "simples" e "dupla arredondada": relido "sem" e
  regravado com oito linhas; relido "simples" e regravado com `1222222223`; relido "dupla
  arredondada" e regravado com `A""""""""S`.
- O golden do DOCX do editor mudou só no diagrama da SkakNew: dez linhas, `[========]` no
  topo, e a célula com a borda `nil`.

### O que fica registrado, e não entrou

- **A SkakNew não tem rótulo em glifo.** Com coordenada ela continua com a moldura da CSS e
  da caneta e com o `a`–`h` em fonte de texto, e no DOCX cai para imagem. Desenhar rótulo
  pede contornos de letra e algarismo, e copiá-los de outra fonte mistura licenças.
- **O Word de uma máquina com a SkakNew original instalada** usa a instalada, que não tem a
  moldura, em vez da embutida — o nome da família é o mesmo. O EPUB não tem esse problema:
  o `@font-face` manda.
- **O exportador escapa o `"` da dupla** (`&quot;`, pelo `html.escape`) e o editor não; o
  conteúdo é o mesmo, e o `<pre>` dos dois só difere na grafia.

### Onde está

- `core/render_diagrama.py` — `grade(com_rotulos=)`, `linhas_do_diagrama`, `moldura_da_grade`.
- `gerar_moldura_da_skaknew.py`, `fonts/SkakNew-Diagram.otf` (a cópia) e
  `fonts/SkakNew-Diagram-original.otf`; `core/dados/fontes_de_diagrama.json` (`molduras` e o
  sha da SkakNew).
- `core/livro.py`, `core/pdf_nativo.py`, `core/editorial_legacy.py` — a decisão pela
  `linhas_do_diagrama`.
- `core/editor/xhtml.py` (`diagrama_de_div(caixa=)`, `ler(caixa=)`), `core/editor/dialeto.py`
  (`moldura_da_folha`), `core/editor/epub.py`, `core/editor/docx_io.py`,
  `core/editor/docx_leitura.py`, `core/editor/fontes.py` (`caracteres_do_mapa`,
  `desatualizada`, `embutir(ler_dados=)`), `core/editor/html_io.py`, `core/editor/pdf_io.py`.

Cobertura: `tests/test_f122_moldura_na_fonte.py` (31 testes — o exemplo do usuário, as oito
combinações de fonte, moldura e quina indo e voltando, o "sem" e a SkakNew com coordenada, a
SkakNew como superconjunto e o gerador reprodutível, a tinta de cada peça do lado do
tabuleiro, o EPUB e o DOCX, o desenho do `fitz.Story`, a leitura pelo editor, o livro de
antes com a moldura da folha, a SkakNew de 2004 trocada no EPUB e no PDF, e o pipeline do
`livro`); `test_f120_diagrama_em_pre.py` e `test_fila_de_suspeitas.py` passam a esperar a
grade, e o golden do DOCX do editor foi regravado.

---

## F123 — A geometria da linha chega à janela, e a tabela por livro foi medida antes de ser feita — CONCLUÍDA

Os dois próximos passos que a F112 deixou registrados. A poda de Baird entrou só no caminho do
livro, onde a âncora é a rede sozinha; o «Detectar e Preencher (Neural)» lê pela cadeia de
`ocr_service` — rede, k-NN e EasyOCR — e depois pela linha do EasyOCR, com a trava da F18, e
continuava pondo na tela o `c0uld` que a exportação já não punha no livro. E a tabela por
livro, "sem rótulo, das maiúsculas sem par do próprio livro", era a resposta registrada para o
`s` lido `S` que a tabela única deixa passar.

### A tabela por livro, medida antes: sai certa sem rótulo, e não paga

Nas páginas rotuladas, depois da poda da F112 (tabela de fora do livro), sobram 557 erros em
31.956 caracteres, e **140 são dentro de um grupo de mesmo desenho** — o teto de qualquer
geometria. Dos 140, o que uma tabela por livro alcança é o `s` lido `S` (11, e quatro deles
são o gabarito: `Sergey` e `Samets` rotulados em minúscula) e o `i` lido `l` (12). O resto
não é dela: o `I`/`l`/`1` a geometria não separa (os topos ficam a 0,1 altura de x), o `P`
mistura a letra e a figurina do peão, e os doze `0` lidos `o` são todos o gabarito —
`c0mf0rtable`, `c0luna`, `Glossári0`, os mesmos que a F112 conferiu.

A estimativa sem rótulo funciona. Tirada das leituras do próprio livro — as maiúsculas sem
par e sem figurina (`ADEFGHLMTY`) e as ascendentes `bdhk` com confiança de 0,9 ou mais, na
linha que a poda ajusta —, a altura da caixa alta sai 1,36 no Darcy Lima, 1,39 no Seirawan,
1,42 no Kasparov, 1,45 no Nunn, 1,58 no *Practical Chess Defence* e 1,64 no *Attacking
Manual*, contra 1,32 / 1,37 / 1,41 / 1,45 / 1,63 / 1,67 que a F112 mediu pela verdade, com
desvio abaixo do `PISO` em todos.

O que ela conserta não:

| tabela | no texto | consertos | quebras | neutras |
|---|---:|---:|---:|---:|
| de fora do livro (a da F112) | 97,94% | 73 | 8 | 10 |
| por livro, nas classes que a tabela já tem (`SCOWV` e `l`) | 97,95% | 78 | 10 | 11 |
| por livro, e criando `U`, `X`, `Z` | 97,94% | 81 | 16 | 11 |

**Três caracteres em 31.956**, e todos os `S`→`s` num livro só, o Seirawan (`YaSSer
SeiraWan`, `DeniSe`, `ASpretas`) — duas das três quebras são o gabarito (`defeSa`, `suaS
Torres`). Criar as classes que faltam custa seis `u` lidos certo que viram `U` onde a linha
votou o corpo baixo. E na exportação a prosa vem do Tesseract (F112): o `s` lido `S` chega ao
livro só na página sem motor. **Não entrou.**

### O que entrou

**Um gancho na leitura da linha.** `leitura_de_linha.ler_pagina(podar=)` recebe
`(linha, âncora) -> {índice: (char, confiança, fonte)}` e corrige a âncora da linha inteira
**antes** de a linha do EasyOCR ser lida: a poda precisa de todos os boxes para votar o corpo
da linha, e o `ler_caractere` vê um de cada vez. O alinhamento corre contra a âncora corrigida,
e a trava vale para o que a poda escreveu como vale para o resto. Com `ao_falhar`, um erro
dentro dela deixa a linha como estava.

**`geometria_da_linha.poda_da_ancora(página, candidatas)`** é esse gancho para a janela, com
duas diferenças do livro, cada uma pela razão da janela:

- **só a leitura da rede é trocada** — as candidatas são dela, e trocar a resposta do k-NN pela
  da rede seria outro elo lendo, não a geometria podando; a rede nem é consultada para esses
  boxes. As leituras dos outros elos votam o corpo da linha como qualquer outra;
- **sem confirmação**: no livro, a leitura fraca que é a única do grupo a caber sobe para a
  massa do grupo porque o piso de confiança a apagaria do texto; na janela ela não some — vai
  para a fila de revisão, e subir a confiança a esconderia de lá.

**A troca sai com fonte própria, `geometria`, e entra sempre na fila de revisão**
(`FONTES_SEMPRE_REVISADAS`), pelo critério da F48–F55, que é a separação e não o acerto: a
confiança da troca é a massa do grupo, e a rede não separa os membros de um grupo — é por isso
que ele é grupo. O número diz o desenho, não qual dos dois; régua plana por construção.

**Só a ação neural poda.** O «Híbrido» não carrega a rede para ler, e as candidatas são dela.
`_preencher_por_linha(poda=)` monta o gancho na thread de trabalho, depois de `preparar`
carregar o modelo, com as candidatas pela porta do serviço (`learning_service.candidatas`, a
mesma das duas exportações), e o diálogo de fim ganha a linha "Corrigidos pela geometria".

**O instrumento aprendeu a poda.** `medir_cadeia.py` mede a ação por omissão (F116): o caminho
neural dele passa a podar como a ação poda (`rodar(podar=DA_ACAO)`, `poda_da_acao`), e
`--geometria` compara com a cadeia sem a poda, com a tabela de cada obra estimada nas outras
(`tabelas_de_fora`, que usa **todas** as páginas rotuladas para estimar — oito das doze que o
instrumento mede são do Kasparov, e a tabela dele sairia só das três do Aagaard). E
`medir_poda_na_janela.py` mede onde o `medir_cadeia` não alcança — ver abaixo.

### Medido

**Nas páginas rotuladas a poda não tem o que fazer**, e é a mesma razão da F117: o k-NN
responde nelas consultando a cópia do próprio glifo (F23) e a rede treinou nelas.
`medir_cadeia.py --neural --geometria --idioma en`, 12 páginas, 11.486 boxes:

| cadeia da janela | acerto | trocas | na fila | erro sem fila |
|---|---:|---:|---:|---:|
| sem poda | 97,54% | 0 | 437 | 209 |
| poda, tabela de fora da obra | 97,54% | 4 | 438 | 208 |
| poda, tabela gravada (a da ação) | 97,53% | 9 | 442 | 205 |

Com a tabela de fora, as quatro trocas são um conserto e uma quebra na mesma página do
*Practical Chess Defence* — a vírgula e o apóstrofo, uma para cada lado — e dois `1` lidos
`i` onde a verdade é `a` e `h`, errados antes e depois. Com a gravada, que viu estas páginas,
entram mais cinco: quatro `I` lidos `i` onde a verdade é `n` (a haste de um `n` partido) e um
`w` que vira `W`. **O acerto não se mexe, e a fila sim**: o erro que a rede tinha lido com
confiança e a geometria recusou passa a ser visto — os que escapam da fila vão de 209 para
205.

**No livro que a janela não viu, ela conserta.** `medir_poda_na_janela.py` roda a mesma cadeia
nas quatro páginas do corpus de referência (`benchmarks/ocr_corpus_v1.json`), que nenhuma base
copia: em 5.468 boxes mudam 49 — **48 trocas da geometria, 47 consertos e uma neutra, nenhuma
quebra** —, e um box que a linha do EasyOCR realinhou por tabela, errado antes e depois.
Conferido a olho contra a transcrição; a pista do instrumento dá 47 consertos, 1 quebra (é o
box realinhado) e 1 sem alinhamento (a neutra).

| página | mudaram | o que eram |
|---|---:|---|
| Aagaard p. 30 | 12 | `c0uld`, `w0n` ×2, `t0`, `Morales'`, `Pawn`, `smith`, `posit1on`, `w1t1h`, `s1inp]e`; a neutra dentro de `t!1rcat` e o box realinhado |
| Yusupov p. 34 | 1 | `Solut1.ons` |
| Yusupov p. 47 | 33 | a haste do `i` lida `1` com o pingo em box próprio: `Th1.s`, `p1.eces`, `pos1.t1.on`, `D1.agram` |
| Nunn p. 237 | 3 | `w♖g1`, `w=white` — a célula `W:` da tabela, que o motor não cobre |

São 0,86 ponto de acerto por box nessas páginas, e a rede tinha lido cada um desses com
confiança acima da trava: a linha do EasyOCR não podia tocá-los. **O custo é a fila**: a troca
entra sempre, e a fila de revisão das quatro páginas vai de 1.313 marcações para 1.357 — onze
por página, quase todas já certas. É o preço de a janela não esconder uma decisão que a linha
tomou pelo usuário, e é pequeno perto da fila que já existe nesses livros (40% dos boxes do
Yusupov p. 47).

### O que fica registrado, e não entrou

- **O «Híbrido»**. A âncora dele é k-NN e EasyOCR, e as candidatas do k-NN (`candidatas`) têm
  outra escala — a confiança dele é distância, e a massa de um grupo não quer dizer nada ali.
- **A tabela por livro** — medida acima.
- **O pingo do `i` em box próprio** (a família A da F109) continua saindo `.` depois da haste:
  `Thi.s`. A poda conserta a haste e não junta os dois; é a régua do diacrítico.

### Onde está

- `core/leitura_de_linha.py` — `ler_pagina(podar=)`.
- `core/geometria_da_linha.py` — `poda_da_ancora` e `FONTE`.
- `ui/main_window.py` — `_preencher_por_linha(poda=)` e a ação neural.
- `ui/confidence.py` — `FONTES_SEMPRE_REVISADAS`.
- `medir_cadeia.py` — `--geometria`, `tabela_geometria`, `tabelas_de_fora`, `poda_da_acao`,
  `DA_ACAO`, `Pagina.obra`; `medir_poda_na_janela.py` (novo).

Cobertura: `tests/test_f123_poda_na_janela.py` (12 testes — a poda corrige a âncora antes da
linha e a linha é alinhada contra a âncora corrigida, sem gancho nada muda, o erro do gancho
com e sem `ao_falhar`, o `0` da rede no corpo de `o` trocado com a fonte própria e só ele
consultando a rede, a leitura do k-NN e do EasyOCR que fica sem consultar a rede, a leitura
fraca que não é confirmada na janela, a linha curta, a fila de revisão, só a ação neural
passando a poda, o instrumento medindo a ação por omissão, e a janela de verdade aplicando a
troca e contando no diálogo). Todos os 12 passam por um nome que esta fase criou (`podar=`,
`poda_da_ancora`, `FONTE`, `DA_ACAO`, `poda=`), e nenhum passa contra o código de antes. Suíte:
3095 (`-m "not slow"`).

---

## F124 — O Tesseract ganha prazo, e o livro desiste do executável que não volta — CONCLUÍDA

Registrado na F119: *o Tesseract é chamado sem prazo*. Nenhuma página travou nele aqui, mas
um executável que não volta prende a exportação do mesmo jeito que o reparo de colagem
prendia — a barra parada, a CPU parada, nada no relatório —, e a F119 mostrou quanto custa
descobrir de fora o que um processo preso está fazendo.

### Quanto ele leva, medido antes de escolher o prazo

Dezesseis páginas de nove livros, a 300 dpi, pelo `OCRService` de produção:

| chamada | típico | pior |
|---|---:|---:|
| página inteira (`--psm 3`, com a segunda passada da trama) | 0,7 – 3,1 s | **19,3 s** (Yusupov p. 47, o painel sobre a trama) |
| faixa de uma linha (`--psm 7`) | 0,16 – 0,24 s | 0,24 s |

**O prazo é o do processo que não volta, e não o do lento**: dez vezes o pior caso medido,
para nenhuma página de verdade perder o motor por pressa — `PRAZO_DA_PAGINA_S = 180`,
`PRAZO_DA_FAIXA_S = 30`, e `PRAZO_DO_CARACTERE_S = 10` para o recorte isolado da janela.

### O que entrou

**Cada chamada ao Tesseract leva o prazo dela** (`image_to_data(timeout=)`, que o pytesseract
0.3.10 cumpre matando o processo). O estouro sobe como `TesseractSemResposta` — e não como
`MotorIndisponivel`, porque o executável existe e responde nas outras imagens: é aquela que
ele não fechou. Um `RuntimeError` que não é de prazo continua subindo como está.

**A página segue com a cadeia própria e diz por quê**, pelo caminho que a falha do motor já
tinha (`PaginaExtraida.motor_indisponivel`): "página: o Tesseract não respondeu em 180 s". A
faixa conta o estouro como falha comum — três seguidas a desligam na página.

**E o livro desiste do motor que não volta.** Sem isso, um executável preso custaria a cada
página o prazo dela e o de três faixas — quatro minutos e meio por página, ou 22 horas num
livro de 300. `livro.extrair` embrulha os dois leitores num disjuntor
(`_disjuntor_do_motor`): depois de `PAGINAS_SEM_RESPOSTA_ATE_DESISTIR` (2) páginas seguidas
sem resposta, os dois levantam `MotorIndisponivel` sem chamar o motor, e o resto do livro sai
com a cadeia própria no tempo dela. Uma página que responde zera a conta: a página de trama
que o Tesseract não fecha é uma página, e a seguinte ainda o paga. O estado é do livro, e não
do `OCRService`, que vive entre uma exportação e outra.

### Medido

Com o Tesseract de verdade e o prazo baixado a 0,05 s, as páginas 237–239 do Nunn pelo
caminho da exportação: a primeira registra o estouro da página e o de três faixas, a segunda
estoura a página e desliga o motor, e a terceira nem o chama — "desligado para o resto do
livro". As três saem, 5,8 s contra 14,0 s com o motor, e nenhum processo `tesseract.exe` fica
para trás. Com os prazos de produção nada muda: o pior caso medido fica a um nono do prazo.

### O que fica registrado, e não entrou

- **A sondagem da caixa de exportação** (`tesseract_disponivel`: `--version` e
  `--list-langs`) continua sem prazo, e roda na thread da interface. Ela não lê imagem — só
  trava com o executável quebrado —, e o pytesseract não aceita prazo nessas duas chamadas;
  resolver é chamá-las por `subprocess` com `timeout`.
- **A janela não tem disjuntor.** O `PRAZO_DO_CARACTERE_S` limita cada box, e a tarefa se
  cancela entre um e outro; um executável preso custaria dez segundos por box até o usuário
  cancelar.

### Onde está

- `core/services/ocr_service.py` — `TesseractSemResposta`, `PRAZO_DA_PAGINA_S`,
  `PRAZO_DA_FAIXA_S`, `PRAZO_DO_CARACTERE_S`, e o `prazo` em `_erro_do_tesseract`,
  `_linhas_do_tesseract` e `tesseract_ocr_conf`.
- `core/livro.py` — `PAGINAS_SEM_RESPOSTA_ATE_DESISTIR`, `_disjuntor_do_motor`, ligado em
  `extrair`.

Cobertura: `tests/test_f124_prazo_do_tesseract.py` (9 testes — cada chamada pede o prazo do
seu tamanho, o estouro da página e da faixa sobe com nome e prazo e não como indisponibilidade,
o caractere isolado também tem prazo, outro `RuntimeError` não vira prazo, a página sem
resposta sai com a cadeia e registra, duas páginas seguidas desligam o motor para o livro e a
faixa não é mais pedida, a página que responde zera a conta, e a indisponibilidade não é
confundida com falta de resposta). Suíte: 3104 (`-m "not slow"`).

---

## F125 — O aplicativo ganha um bundle desktop reproduzível — CONCLUÍDA

O único item de implementação que permanecia explicitamente fora do roadmap era
o empacotamento independente. A entrega usa `pyboxeditor.spec` em modo **onedir**:
preserva `assets/`, `core/dados/`, `fonts/` e `pieces/` na topologia que o código
já usa, mas não incorpora `custom_model.pth`, pesos treinados grandes ou o
executável do Tesseract. Esses recursos continuam sendo distribuídos pelos seus
contratos próprios.

O extra `[desktop]` instala o PyInstaller; `scripts/verificar_empacotamento.py`
confere a árvore antes do build. O build real de 2026-09-25 terminou em
`dist/PyBoxEditor/`, e o executável iniciou o modo editor com fechamento
automático e código 0. A cobertura estrutural fica em
`tests/test_empacotamento.py`.

---
