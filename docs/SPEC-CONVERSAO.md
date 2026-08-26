# A conversão para DOCX e EPUB — o que sai errado, e o que a substitui

Versão do documento: 1.0
Data: 2026-08-25
Escopo: o caminho que vai da página do PDF ao arquivo `.docx` e `.epub`

Documento companheiro: [`SPEC.md`](SPEC.md) (especificação de implementação) e
[`../ROADMAP.md`](../ROADMAP.md). As fases que esta spec origina estão no ROADMAP a
partir da F109.

---

## 0. Como ler este documento

Ele nasceu de uma queixa: **"muitos problemas de caixa alta e baixa misturadas, trocas
de letras"** no DOCX exportado. A queixa está certa, e o número dela é pior do que o
projeto registrava — mas **a causa não é a que o nome dela sugere**, e é isso que este
documento serve para mostrar.

Tudo aqui foi medido no arquivo que o projeto de fato produziu, e não inferido por
leitura de código. O arquivo é
`PDF/Artur Yusupov - Chess Evolution 1 …_teste-1.docx`, exportado em **2026-08-25 15:32**
— três horas e meia antes de a F108 entrar (commit `68e1d89`, 19:24). Onde a F108 muda o
resultado, o texto diz quanto, porque a conta foi refeita sobre o mesmo arquivo.

Os instrumentos são de `medir_*.py` onde já existiam, e estão nomeados onde precisam ser
escritos.

---

## 1. A queixa, medida

O DOCX tem 298.868 caracteres, 8.499 parágrafos, 36.442 runs, 501 tabelas (os tabuleiros
em texto), 151 imagens e 263 quebras de página. Fora dos tabuleiros sobram 266.804
caracteres de prosa.

Classificando as **20.625 palavras de prosa** com mais de dois caracteres, tirada a
notação de xadrez — que não é palavra e não deve ser julgada por dicionário:

| família | palavras | % da prosa | exemplos |
|---|---:|---:|---|
| A. o `i` partido em haste e pingo | 419 | 2,03% | `Wh1.te`, `whz.ch`, `exercz.ses`, `dec1.s1.ve` |
| B. caixa homográfica — a F108 conserta | 490 | 2,38% | `alSo`, `pointS`, `biShop`, `poSition` |
| C. palavra colada — a caixa é só o sintoma | 952 | 4,62% | `WThite`, `hDiagram`, `FundamentalSBy` |
| D. dígito espúrio dentro da palavra | 1.651 | 8,00% | `y0u`, `g0t`, `po1nt`, `lut1` |
| E. resto fora do dicionário | 667 | 3,23% | `Diagrram`, `thechapter`, `rspeat` |
| **com defeito** | **4.179** | **20,26%** | |
| limpas | 16.446 | 79,74% | |

**Uma palavra de prosa em cinco sai com defeito.** A F104 mediu 1,33% neste mesmo livro,
e a diferença não é contradição: aquela régua usava `Lexico.conhece`, que baixava os dois
lados e por isso **não enxergava erro de caixa** — é o que a F108 diagnosticou —, e
contava só a palavra que o dicionário recusava inteira.

### A razão de caixa, na prosa

| par | maiúsculas | minúsculas | razão |
|---|---:|---:|---:|
| `S`/`s` | 1.340 | 6.589 | **0,203** |
| `W`/`w` | 598 | 1.924 | **0,311** |
| `J`/`j` | 122 | 84 | **1,452** |
| `V`/`v` | 256 | 1.580 | 0,162 |
| `Z`/`z` | 49 | 298 | 0,164 |
| `K`/`k` | 265 | 1.796 | 0,148 |
| `P`/`p` | 241 | 3.127 | 0,077 |
| `C`/`c` | 238 | 4.971 | 0,048 |
| `(O+0)`/`o` | 1.630 | 8.394 | 0,194 |

O `S/s` = 0,203 reproduz na vírgula o que a F107 mediu para este livro. O **`J/j` = 1,452
é novo** e não estava na lista da F107 — há mais `J` maiúsculo que `j` minúsculo num livro
em inglês. E `1` aparece 6.837 vezes contra 4.405 `l`, que é a assinatura da família A.

### O que a F108 alcança, medido no mesmo arquivo

Das **1.061 palavras com padrão de caixa ilegítimo** — nem toda minúscula, nem toda
maiúscula, nem inicial maiúscula —, `lexico.arrumar_caixa` conserta **517 (48,7%)**, que
é melhor do que a própria F108 estimou.

Dos 544 que sobram, classificados um a um:

| o que é | palavras |
|---|---:|
| letra colada na frente, e a palavra de trás existe (`hDiagram`) | 108 |
| prefixo de duas ou três letras colado (`WThite`, `PKeres`) | 99 |
| letra colada atrás (`TroitzkyA`, `KamskyG`) | 84 |
| sufixo colado (`FundamentalSBy`, `YusupovAll`) | 29 |
| **caixa de verdade que a F108 recusou** | **1** |
| não classificado (leitura errada de fato) | 223 |

**Depois da F108, a queixa de "caixa" deixa de ser de caixa.** Sobra **uma** palavra em
que o problema é a caixa; 320 são glifo colado, e a maiúscula no meio da palavra é só a
**assinatura visível de um espaço que não foi posto**. Quem for atrás de caixa a partir
daqui vai procurar no lugar errado.

---

## 2. As causas, em ordem de peso

### 2.1 O livro já trazia o texto, e o projeto o leu da imagem

`core/livro.py:1124`, na docstring de `extrair_pagina`, na letra:

> Uma página do PDF vira parágrafos e figuras, **lendo só a imagem**.

Medido nos oito livros de `PDF/`, contando página com mais de 200 caracteres de camada
de texto:

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
partir do pixel.** O pior livro da tabela da F104, o Dvoretsky com 3,93%, tem camada em
815 das 816 páginas.

E a camada é boa. Filtrando dos **dois** lados pela mesma régua — linha com pelo menos 25
caracteres e pelo menos 90% de latim básico, que é o que separa prosa de tabuleiro:

| caminho | linhas de prosa | palavras | fora do dicionário |
|---|---:|---:|---:|
| camada de texto do PDF (`fitz`) | **2.711** | 16.306 | **3,13%** |
| OCR → o DOCX exportado | 313 | 5.234 | **7,49%** |

São 2,4× a taxa de erro. E o outro número é pior que esse: o OCR produz **313 linhas que
parecem prosa contra 2.711**, com o mesmo filtro — oito em cada nove linhas saem tão
danificadas que nem chegam a ser julgadas.

Lado a lado, o mesmo livro:

> **camada:** `Artur's systematic and professional approach to analysing games was the decisive factor`
>
> **DOCX:** `Diagrram 2-5 We can see the difference between the bishops; the kni ht 8 id t t f th hit`

**As duas peças que resolvem isso já existem e não se falam.**
`core/chess_pdf_processor.py` percorre `page.get_text("dict")`, distingue span de prosa de
span de diagrama (`is_diagram_span`, `is_block_a_diagram`) e mapeia a codificação própria
das fontes de xadrez para Unicode; `core/mapa_glifos.py` guarda esses mapas; a §4.2 da SPEC
descreve tudo. Só que esse caminho existe para **escrever outro PDF**, e o caminho do livro
— que escreve DOCX e EPUB — nunca o chama.

### 2.2 O corpus de calibração não contém os livros que saem mal

Páginas com `.box` rotulado à mão, por livro, cruzadas com a taxa de erro da F104:

| livro | páginas rotuladas | taxa de erro (F104) |
|---|---:|---:|
| Kasparov · Benko Gambit | 8 | — |
| Darcy Lima · A Estratégia | 5 | recusado: português |
| Nunn · Secrets of Rook Endings | 4 | **0,38%** — o melhor do corpus |
| Seirawan · Xadrez Vitorioso | 3 | — |
| Aagaard · Attacking Manual I | 3 | 0,65% |
| Aagaard · Positional Play | 3 | — |
| Aagaard · Practical Chess Defence | 2 | — |
| Petrosian System | 1 | — |
| **Yusupov · Chess Evolution 1** | **0** | **1,33%** |
| **Yusupov · Complete** | **0** | **3,27%** |
| **Dvoretsky · Endgame Manual** | **0** | **3,93%** |

**Os três piores livros da tabela não têm uma página rotulada.** Todo limiar deste projeto
— a folga do diacrítico (`FOLGA_DE_DIACRITICO` = 0,30), a régua do espaço, o envelope de
proporção da F106, o piso de `CONF_MINIMA` — foi medido em Kasparov, Aagaard e Nunn, que
são justamente os livros que já saem bem.

E há a prova direta, porque o projeto exportou os dois. `Kasparov - The Dynamic Benko
Gambit (2012).epub`, na raiz, é saída deste projeto — 322 páginas, 601 imagens. Medido nele
com exatamente a mesma régua do §1, partindo no hífen como a F108 parte:

| livro | páginas rotuladas | palavras | caixa ilegítima | `S/s` |
|---|---:|---:|---:|---:|
| **Kasparov** · Benko Gambit | **8** | 39.418 | **0,32%** | **0,047** |
| **Yusupov** · Chess Evolution 1 | **0** | 41.144 | **2,58%** | **0,203** |

**Oito vezes a taxa de caixa ilegítima, e quatro vezes a razão `S/s`** — mesmo pipeline,
mesmo modelo, mesma semana. O `S/s` = 0,047 do Kasparov é o valor normal de um texto em
inglês; o do Yusupov não é.

O que sobra de erro no Kasparov também informa: `vlaWhr`, `VaWh`, `wiTh`, `VeseTh` — são as
classes `ligature_Wh` e `ligature_Th` disparando onde não devem, que é a mesma família do
`WThite` e o assunto do fim do §2.5.

Isto tem consequência imediata e verificável. A hipótese natural para a família A é que o
separador de glifo colado corta o pingo do `i`, e o próprio projeto documenta esse resíduo
(`core/services/box_service.py:1488`: *"o pingo do 'i' sobre o braço do 'w' … quinze casos
em 5.747"*). Rodei o caminho de produção em três páginas rotuladas do Kasparov, com e sem
o separador, contando quantos boxes de produção caem dentro de cada `i`/`j` do gabarito:

| | 0 box | 1 box |
|---|---:|---:|
| com separador | 8 | **151** |
| sem separador | 12 | 147 |

**O pingo não se parte ali, e o separador melhora.** A hipótese não foi refutada — ela é
**inverificável com o material que existe**, porque o livro que exibe o defeito não tem
gabarito. É a mesma lição que o ROADMAP já registrou três vezes ("a propriedade medida não
era a que interessava"), agora no nível do corpus e não da métrica.

### 2.3 O classificador decide sozinho o que só a linha sabe

Esta é a causa que a F14 nomeou, a F19 mediu, a F107 destravou e ninguém ainda consertou.
Ela responde pelas famílias B e D — **2.141 palavras, 10,4% da prosa**.

`c/C`, `o/O`, `s/S`, `u/U`, `v/V`, `w/W`, `x/X`, `z/Z`, `p/P`, `k/K` e `j/J` são **o mesmo
desenho**. O que os separa é o tamanho relativo à linha, e o recorte é redimensionado para
32×32 antes de o classificador o ver — **a informação que decide foi jogada fora antes da
decisão**. O mesmo vale para `o/0`, `l/1/I` e `g/9`, que é a família D.

`core/altura_relativa.py` (F19) já mediu qual é o sinal, em distância entre médias por
desvio combinado:

| par | d'(topo) | d'(base) | d'(altura) |
|---|---:|---:|---:|
| `s`/`S` | **3,78** | 0,60 | 3,18 |
| `o`/`0` | **3,24** | 0,60 | 2,66 |
| `w`/`W` | **3,10** | 0,20 | 2,78 |
| `c`/`C` | **3,00** | 0,30 | 1,82 |

**O discriminante é o topo, e a razão é tipográfica**: todo glifo se apoia na mesma linha
de base, então a base não distingue nada; o que muda é até onde ele sobe. Três desvios de
separação é sinal forte — e mesmo assim o desempate *a posteriori* da F19 não pagou, porque
ele só dispara onde a geometria e a âncora discordam, e com âncora forte esse conjunto é
quase todo erro da geometria. A conclusão registrada lá é a certa: **a altura tem de entrar
na rede, treinada junto**.

A F107 tirou o pré-requisito do caminho — o tamanho deixou de se perder na gravação — e
mediu o que a entrada nova rende: `S` de 50,0% para **74,0%**, `W` de 33,3% para **83,3%**.
E achou de brinde que preservar a proporção no recorte, encaixado em 32×32 com papel em
volta em vez de esticado, paga **+2,8 pontos fora da família de caixa**.

Sobra o que a F107 nomeou e não resolveu: **falta maiúscula rotulada**. Cinquenta `S`, 48
`W` e 36 `O` no conjunto de teste inteiro é pouco para decidir, e uma dúzia de amostras que
troque de lado move a tabela toda. Ver §2.2 — o material que falta é do mesmo tipo.

### 2.4 A régua do espaço é um número por linha

`core/diagrama.py:719`, `limiar_de_espaco`:

    largura = float(np.median([b.width for b in emfila])) or 1.0
    piso = largura * PISO_DO_VAO
    vaos = [b.x1 - a.x2 for a, b in zip(emfila, emfila[1:])]
    ...
    return max(max(float(np.median(vaos)), 0.0) * FATOR_DO_VAO, piso)

**Um limiar para a linha inteira.** Mas o vão medido é entre a *tinta* de um glifo e a
tinta do seguinte, e quanto de avanço cada glifo gasta em tinta é propriedade **da
classe**: o `1`, o `l`, o `i` e o `.` gastam pouco, e o vão à direita deles mede quase um
espaço sem haver espaço. A distribuição de vãos de uma linha é bimodal — dentro da palavra
e entre palavras —, e um limiar tirado da mediana não separa duas modas cuja posição
depende de quem está de cada lado.

Medido no DOCX exportado:

- **5.894 espaços espúrios entre dígitos.** `2011` sai `20 1 1`; `Diagram 1-11` sai
  `Diagram 1-1 1`. O `1` está à esquerda em 29,8% deles contra 22,0% de participação dele
  no texto — 1,35× a mais do que a frequência explica.
- **304 palavras coladas** que partem em duas do dicionário (`thechapter`, 21×).
- **146 parágrafos de prosa que são só a fila de coordenada do diagrama** —
  `a b c d e f g h` (28×), e também partida: `f g h` (24×), `a b c d e` (23×). É daqui que
  saem os `hDiagram`, `eDiagram`, `gDiagram` e `fDiagram` da família C: a letra de coluna
  do tabuleiro cola na legenda da figura.

A F107 já consertou esta régua uma vez, trocando "tinta contra tinta" por "vão contra o vão
típico da linha". O conserto foi na direção certa e **não alcança o defeito de classe**.

### 2.5 O alfabeto é o mesmo em todo livro

`model_meta.json` tem **314 classes**: 139 `ligature`, 113 `sym`, 26 `lower`, 26 `upper` e
10 `digit`. Todas as 314 estão disponíveis em todo recorte de todo livro.

O Yusupov Chess Evolution 1 é em inglês. No DOCX exportado dele há **17 letras acentuadas
distintas, em 1.112 ocorrências** — inclusive `ã`, `õ` e `ç`. `Š` sai 185 vezes, `É` 404,
`ê` 409. **Nenhuma é legítima**, e todas são baratas de matar: são classes que o livro não
usa e que competem no softmax com a classe certa.

Isto não pede modelo novo nem treino. `core/services/learning_service.py` já expõe
`candidatas` → `NeuralPredictor.predict_topk`, e o veto da F106 já é exatamente a forma
"filtre as candidatas e escolha entre as que sobram". Uma máscara de alfabeto por livro
entra no mesmo lugar, com o mesmo formato, e o custo de execução é o de um teste de
pertinência.

**As 139 classes de ligadura merecem a mesma pergunta.** Elas são 44% do alfabeto, e
existem para o par que a segmentação não separa. É um remédio que escala mal — o inglês e
o português juntos têm centenas de pares plausíveis —, e ele tem efeito colateral medido:
`White` sai `WThite` 27 vezes neste livro, que é a `ligature_Wh` disparando onde não devia.

### 2.6 O que o impresso tem e o arquivo não recebe

Isto não é reconhecimento — é o arquivo julgado como arquivo.

**Itálico: perdido inteiro.** O DOCX exportado tem **0 runs em itálico** e **0
`smallCaps`** em 36.442 runs. Onde o PDF declara o estilo — o Dvoretsky e o Darcy Lima são
os dois cujas fontes não são subconjuntos anônimos —, o itálico é **1,6% a 4,0% dos
caracteres** e o negrito 9,6% a 11,3%. Num livro de xadrez o itálico marca variação,
comentário e nome de abertura; o versalete marca nome de jogador. O negrito chega ao
arquivo desde a F105 — 12.436 runs, **19,6% dos caracteres de prosa**. O itálico não tem
sequer campo onde morar: `Paragrafo` tem `negrito` e `pesos`, e nada mais.

Esses 19,6% levantam uma pergunta que esta spec **não responde**: os dois livros que
declaram estilo trazem 9,6% e 11,3% de negrito, e a saída do Yusupov traz o dobro disso.
Não é comparação válida — são livros diferentes, e o Yusupov não declara estilo nenhum —,
mas é barato conferir se a régua da F105 está disparando demais, e está na §5.

**Não há capítulo.** O DOCX tem 390 parágrafos com estilo `Heading 2`, e **todos são
legenda de diagrama** (`Diagram 1-3`, `Ex. 1-6`). O painel de navegação do Word mostra 390
legendas e nenhum capítulo. `Paragrafo.titulo` existe desde a F2.6 e quem o marca hoje é a
faixa do diagrama; nada detecta título de seção na página.

**O EPUB é um despejo de páginas**, e há um exportado para conferir: o
`Kasparov - The Dynamic Benko Gambit (2012).epub` da raiz.

| | |
|---|---:|
| XHTML no arquivo, um por página do PDF | 322 |
| entradas no `nav.xhtml` | **322**, e todas dizem "Página N" |
| títulos, todos `h2`, todos legenda de diagrama | 122 |
| `dc:creator` | **ausente** |
| `dc:identifier` | **`pyboxeditor`** |

O Yusupov Complete, de 2.612 páginas, sairia com um sumário de 2.612 entradas de número de
página e nenhum capítulo.

**E nada disso é erro que um validador acuse — agora medido, e não suposto.** Rodado o
`epubcheck` 5.3.0 sobre o EPUB de produção do Kasparov e sobre os dois modos de diagrama:

| arquivo | válido | mensagens |
|---|---|---:|
| Kasparov · Benko Gambit, modo de imagem, 322 páginas | **sim** | **0** |
| diagrama em modo de fonte, SkakNew-Diagram | **sim** | **0** |
| diagrama em modo de fonte, ChessMerida-Diagram | **sim** | **0** |

Zero erro e zero advertência nos dois modos e nas duas fontes. **Controle negativo, para o
zero valer alguma coisa:** removido o `dc:language` de uma cópia, o validador acusa
`RSC-005`; posto um `&` solto num XHTML, acusa `RSC-016` como fatal. A ferramenta está
funcionando — o arquivo é que está conforme.

**Um arquivo pode estar conforme e não ser um livro.** O `nav` existe, o idioma está
declarado, o `dc:identifier` está presente, e mesmo assim não há por onde navegar e o leitor
não tem unidade de leitura. Nenhum defeito desta seção é alcançável por validador de
esquema: eles são de **editoração**, e quem os pega é o Ace da DAISY, que confere
acessibilidade, ou uma pessoa abrindo o arquivo.

E o `dc:identifier` é um defeito de conformidade e não de gosto: ele é o
`unique-identifier` da publicação, e **está literal em todo livro que este projeto
exporta**. Dois livros diferentes saem com a mesma identidade, e o leitor que os catalogue
por ela vai tratá-los como um só.

**Tipografia.** Nenhuma aspa curva no arquivo — 0 contra 17 aspas retas.
`dcterms:modified` é fixo em `2026-01-01T00:00:00Z`. `lexico.juntar_hifenizadas` existe
desde a F9.1, tem teste, e **nenhum caminho de produção a chama**; a F104 mediu que no Nunn
ela juntaria 490 palavras. Ver §4.1 — ela não está sozinha.

**O `alt` com o FEN existe no código e não chega ao arquivo.** `_alternativo`
(`exportar.py:251-262`) devolve o FEN, e o caminho de imagem o escreve no `descr` do
`docPr`. Mas no DOCX medido os 151 `descr` são **duas cordas só** — `Cabeçalho do
diagrama` (120×) e `Diagrama` (31×). **Nenhum FEN, nem um.** E as 501 tabelas do arquivo
são todas diagrama em modo de fonte, que não recebe `descr`, `w:tblCaption` nem
`w:tblDescription` — ali não há texto alternativo nenhum. O EPUB escreve nos dois modos; o
DOCX, num só.

**A identidade do arquivo é a da biblioteca.** No `docProps/core.xml` do DOCX de produção:
`<dc:creator>python-docx</dc:creator>`, `<dc:description>generated by python-docx</dc:description>`,
`dcterms:created` e `dcterms:modified` em **`2013-12-23T23:15:00Z`**. E o
`docProps/thumbnail.jpeg` é **byte a byte** o do `default.docx` da biblioteca. A causa é
`ui/main_window.py:1819-1823`, o único chamador da exportação, que passa `titulo`,
`diagramas`, `corpo_pt`, `moldura` e `cantos` — e não passa `autor`. O `titulo`, no arquivo
medido, é literalmente `..._teste-1`.

**Os dois formatos discordam da mesma prosa.** O DOCX sai no template nu do `python-docx`
— Carta, Calibri 11, 10 pt depois de cada parágrafo, `<w:ind>` = 0 em 8.499 parágrafos, sem
justificação. O EPUB do mesmo livro sai justificado com recuo de 1,2 em
(`exportar.py:34-35`). O mesmo livro, dois desenhos de página.

**O idioma não chega ao DOCX**, e não é esquecimento de encanamento: `para_docx`
(`exportar.py:845-850`) **não tem parâmetro de idioma**. `<w:lang>` aparece 0 vez no
documento. E `lexico.carregar` tem `idioma="en"` por omissão que nenhum ponto do programa
jamais muda — não há onde escolher outro idioma.

**O que já está certo, e vale dizer para não se mexer nele.** O EPUB é EPUB 3 com `nav`
declarado e `dc:language` do **livro** e não do programa, fonte de símbolos embutida só
quando o texto precisa, e `ibooks:specified-fonts` para o Apple Books não trocar a fonte do
tabuleiro. O DOCX embute fonte com a ofuscação do ECMA-376 — **§17.8.1, e não a §15.2.13
que o comentário do código cita; a §15.2.13 define a Font Part, não o algoritmo** — e casa
corpo e entrelinha em meio ponto para o tabuleiro fechar quadrado. Não ofuscar a fonte no
EPUB também está certo: a norma torna o `encryption.xml` obrigatório para quem ofusca, e
ofuscar é apostar que o leitor implementou a desofuscação, que a EPUB Reading Systems 3.3
põe como *should* e não como *must*.

A mecânica dos dois formatos é competente onde foi construída de propósito. O que falta é
**estrutura de livro**, **atributos do impresso** e **tudo o que o template padrão decide
por omissão** — não OOXML nem OPF.

### 2.7 As réguas que medem o projeto contam erro de caixa como acerto

Este achado não é sobre o arquivo exportado: é sobre os **números com que o projeto decide**.
E ele é da mesma família da F108 — a cegueira a caixa de `Lexico.conhece` não ficou só no
caminho do livro, ela entrou nos instrumentos.

**A tabela dos seis livros da F104 subestima o erro por um fator de 2,89.**
`medir_confusao_no_livro.py:274-276` faz `if lx.conhece(nucleo): conhecidas += 1` — e
`conhece` (`core/lexico.py:119-121`) baixa os dois lados. Chamando o `contar` e o `medir` do
próprio módulo sobre o DOCX do Yusupov, com o léxico real de 310.465 palavras:

| | ocorrências | formas |
|---|---:|---:|
| prosa contada | 17.692 | |
| fora do dicionário | 1.266 | 616 |
| atribuídas → a taxa publicada | 234 | → **1,32%** |
| **erro de caixa, que não entra em nenhuma das linhas acima** | **441** | 215 |

`alSo` 31×, `pointS` 23×, `poSition` 19×, `biShop` 15×, `haS` 14×. Somando, **675 de
17.692 = 3,82%**, contra os 1,32% publicados — **2,89×**.

**E há um segundo mecanismo, pior que a subestimação.** A mesma linha que absolve a palavra
faz `prior[nucleo.lower()] += 1`: o `alSo` mal lido **vota a favor de si mesmo** no prior
que depois vai atribuir os erros. O erro se auto-alimenta na régua que deveria acusá-lo.

Junto disso, 83 das 1.266 "fora do dicionário" (6,6%) são linha de fonte de diagrama que
entrou na prosa — o mesmo vazamento do §2.4, agora contaminando a medição.

**A régua que decidiu o tamanho da lista de palavras (F9.1) tem o mesmo defeito, e pior.**
`medir_troca.py:104` compara `normalizar(lido).lower() != normalizar(certo).lower()`, e o
`total += 1` acontece na **linha 103, antes** da comparação. Então `also` lido `alSo` não
sai da conta: **entra no denominador como acerto**. O par (recall, alarme falso) que
escolheu entre `idioma` e `idioma+nomes` foi medido com a família dominante de erro
reclassificada como acerto — e a lista de nomes é a que mais tem a perder, porque são
237.018 formas Capitalizadas que `carregar` baixa e funde, e que depois de baixadas
absolvem toda palavra comum lida com inicial maiúscula.

A contraprova de que é assimetria e não convenção: `medir_lexico.py:97-98` faz a mesma
comparação **sem** `.lower()` de nenhum lado.

**E existe um erro de caixa que nenhum instrumento do projeto vê: a inicial trocada.**
`Also` por `also` é padrão legítimo — `caixa_estranha` não acende, `conhece` não acende, a
razão `S/s` mal se move. O instrumento que o enxerga é a **taxa de Titlecase por letra**,
comparada contra um livro nativo:

| letra | DOCX Yusupov (OCR) | EPUB nativo Kasparov |
|---|---:|---:|
| **`S`** | **21,5%** (131/609) | **3,7%** (50/1.352) |
| `T` | 16,3% | 18,8% |
| `V` | 12,6% | — |
| `N` | 10,8% | 4,2% |
| `O` | 10,4% | 5,9% |
| `C` | 5,8% | — |
| `P` | 0,9% | 1,6% |
| `G` | 1,2% | 1,3% |
| `R` | 0,4% | 2,7% |
| **global** | **7,6%** | **7,8%** |

**A comparação contra o nativo é obrigatória, e o `T` mostra por quê**: ele é alto nos dois
livros (16,3% contra 18,8%), então sem o piso ao lado seria a primeira suspeita e é o mais
inocente. O `S` é o oposto — 2,8× a global do próprio livro e **5,8× a mesma letra no livro
nativo**. Excesso estimado: **~85 ocorrências**, contra as 234 que a régua reporta como o
total de erros do livro. Mais de um terço a mais, invisível a toda peça do projeto.

**Consequência prática.** A tabela dos seis livros do ROADMAP e a conclusão "dez vezes de
diferença entre o melhor e o pior" estão medidas sobre um instrumento que não vê cerca de
dois terços dos erros deste livro. Não é que a conclusão esteja errada — é que ela não foi
testada. Antes de qualquer fase desta spec mudar código de reconhecimento, **a régua precisa
de um terceiro balde**, e a tabela precisa de duas colunas novas em vez de um número
corrigido.

---

## 3. Os caminhos, como escolha

Quatro caminhos, formulados para serem comparáveis. Não são fases: são apostas
arquiteturais, e três delas podem correr em paralelo porque tocam partes diferentes.

### Caminho A — a camada de texto primeiro, o pixel como exceção

A página que traz o texto é lida do texto; o OCR fica para a que não traz, e para o que a
camada não sabe dizer — o tabuleiro, que continua sendo desenho.

- **Resolve**: as cinco famílias de uma vez, em 72% das páginas do corpus. A taxa de erro
  cai de 7,49% para 3,13% na medida de §2.1, e o número de linhas utilizáveis multiplica
  por 8,7.
- **Não resolve**: Seirawan e Razuvaev, que são digitalizações de verdade — 834 páginas do
  corpus, e são exatamente as que o OCR existe para atender.
- **Custa**: pouco, e é a razão de ele vir primeiro. `core/chess_pdf_processor.py` já
  percorre os spans, já separa prosa de diagrama, já mapeia a fonte de xadrez; o que falta
  é uma função que devolva `PaginaExtraida` em vez de escrever PDF. O intermediário não
  muda, e por isso `exportar.py` não muda.
- **Quebra**: nada. É um caminho a mais, escolhido por página, com o de hoje como reserva.
- **Perde**: a procedência por caractere. Quem lê do texto não tem box, não tem confiança e
  não alimenta a coleta nem a fila de revisão. **A página lida do texto sai do circuito de
  treino**, e isso precisa ser dito no relatório em vez de acontecer calado.

### Caminho B — a geometria dentro da rede

O escalar de topo e de tamanho entra como entrada do classificador, treinado junto, e o
recorte passa a ser encaixado em vez de esticado.

- **Resolve**: as famílias B e D, 10,4% da prosa, **onde nenhuma outra coisa resolve** — no
  glifo de xadrez e no livro sem camada de texto não há língua para consultar nem contexto
  para pedir. É a única resposta que serve ao Seirawan.
- **Não resolve**: A, C e E.
- **Custa**: retreinar 626.181 amostras, mexer nos pontos que redimensionam na leitura, e —
  o preço de verdade — **rotular maiúscula**, que é trabalho humano. A F107 já mediu que sem
  isso o modelo passa a confiar demais na entrada nova e a minúscula piora.
- **Quebra**: a compatibilidade do `.pth`. A F7.3 já tem a régua para isso.
- **Perde**: nada, se o rótulo vier.

### Caminho C — um reconhecedor de linha para a prosa

Um segundo motor, que lê a **linha inteira** sem segmentar caractere, treinado nas páginas
rotuladas do próprio projeto. O caminho por caractere fica com o xadrez.

- **Resolve**: A, C, D e boa parte de B, e resolve **por construção** — onde não há corte,
  não há corte errado; onde não há régua de espaço, não há espaço espúrio; e um
  decodificador que vê a linha inteira desempata `s`/`S` pelo contexto que o glifo isolado
  não tem.
- **Não resolve**: o diagrama, a figurina e a notação, que continuam no caminho de hoje.
- **Custa**: uma dependência, um pipeline de treino, e um árbitro entre os dois motores.
- **Quebra**: nada, se entrar como segundo caminho. O `.box` deste projeto **é o formato do
  Tesseract** — `core/avaliacao_pagina.py:52` diz isso na letra —, então as páginas
  rotuladas convertem para transcrição de linha sem escrever conversor.
- **Perde**: a caixa por caractere na prosa, e com ela a edição de box na UI, a coleta e a
  fila de revisão para o texto lido por esse caminho. É a mesma perda do Caminho A, pela
  mesma razão, e ela é estrutural: **procedência por caractere e leitura por linha são
  incompatíveis**, e escolher uma é escolher o que a UI pode oferecer sobre aquele texto.

### Caminho D — o intermediário da exportação

Enriquecer `PaginaExtraida`/`Paragrafo` com o que falta — itálico, versalete, nível de
título, capítulo — e reagrupar o EPUB por capítulo em vez de por página.

- **Resolve**: a §2.6 inteira. Não toca em uma linha de reconhecimento.
- **Não resolve**: nada de §2.1 a §2.5.
- **Custa**: pouco no formato, porque o `exportar.py` já é competente, e mais na
  **detecção** — quem decide que uma linha é título, e que um itálico é itálico.
- **Quebra**: nada.
- **Perde**: nada.

### O que recomendo

**A, depois D, depois B — e C como aposta medida, não como decisão tomada.**

O Caminho A é o único em que o argumento é aritmético em vez de arquitetural: 72% das
páginas do corpus têm o texto certo dentro do arquivo, o projeto já sabe extraí-lo, e a
medida lado a lado está em §2.1. Nenhum ganho de modelo compete com deixar de reconhecer o
que já está escrito.

O Caminho D vem em seguida porque é o único cujo defeito o usuário vê **mesmo quando o OCR
acerta**: um EPUB de 2.612 entradas de "Página N" é ruim com 100% de acurácia.

O Caminho B tem duas pontas, e a §7.4 acrescentou a segunda: a de Baird, em que cada
candidata propõe um tamanho e a linha poda as candidatas, **não pede rótulo nenhum**. É a
que deve ser tentada primeiro. A outra ponta — a geometria treinada dentro da rede — é cara
e o preço dela é rotulagem — e mesmo assim ela é **inevitável**: sem ela o Seirawan e o
Razuvaev, que são 834 páginas e os únicos livros que realmente precisam de OCR, continuam
como estão.

O Caminho C não deve ser decidido nesta spec. Ele é a resposta mais forte no papel e a de
maior risco na prática, e a §5 diz o que medir para decidi-lo por número.

---

## 4. Os consertos baratos, que não esperam caminho nenhum

Estes cabem antes de qualquer decisão arquitetural, e cada um tem número.

| conserto | o que mata | evidência | custo |
|---|---|---|---|
| **Máscara de alfabeto por livro** | 1.112 caracteres espúrios só neste livro | §2.5 | baixo — entra em `candidatas`, no formato do veto da F106 |
| **Ligar `partir_colada`** | até 304 palavras coladas neste livro, da família C | §4.1 | baixo — falta a chamada |
| **Ligar `juntar_hifenizadas`** | 490 palavras no Nunn | F104, e ela já tem teste | baixo — falta a chamada |
| **Ligar `reparar` (F66) no caminho do livro** | a família E, que é o resto fora do dicionário | §4.1 | baixo — falta a chamada |
| **A fila de coordenada fora da prosa** | 146 parágrafos, e os `hDiagram` da família C | §2.4 | baixo — a faixa do diagrama já é território conhecido (`livro.MARGEM_DIAGRAMA`) |
| **Razão de caixa como teste de aceitação** | não conserta; **acusa** | §1 | baixo — a conta já está escrita |
| **Cabeçalho e rodapé fora da prosa** | a F104 mediu que é o maior contribuinte de três dos seis livros | F104 | médio — o sinal é forte: o mesmo texto na mesma posição em centenas de páginas |

### 4.1 Três reparos prontos, e o livro recebe um

`core/lexico.py` tem uma caixa de ferramentas de reparo inteira, construída, testada e
medida ao longo da F9 e da F66:

| função | onde | o que faz | quem a chama |
|---|---|---|---|
| `arrumar_caixa` | `lexico.py:506` | baixa a maiúscula interna | **`livro.py:1199`** (F108, ontem) |
| `partir_colada` | `lexico.py:318` | acha onde faltou o espaço | só `medir_lexico.py` |
| `juntar_hifenizadas` | `lexico.py:269` | junta a palavra partida na quebra de linha | só `medir_lexico.py` |
| `reparar` / `reparos_da_pagina` | `lexico.py:815` | conserta a leitura contra a forma do dicionário | só a UI |

**O caminho do livro chama exatamente uma das quatro.** As outras três existem com teste,
com medição própria e sem consumidor em produção — `partir_colada` foi medida em 7 de 7
junções reais, com as três condições que a blindam contra falso positivo.

Isto não é acidente isolado: é o mesmo achado que a F108 registrou ("o caminho do livro não
carregava o léxico", "o reparo da F66 existe e não estava ligado"), e a F108 ligou uma. **O
caminho que escreve o arquivo é o último a ser ligado a qualquer coisa** — e é o único que
o usuário vê. Vale como regra para as fases seguintes: função nova sem chamada no
`livro.py` não está pronta.

E `partir_colada` acerta em cheio a família C. Medido no DOCX, **304 palavras partem em
duas palavras do dicionário** (`thechapter`, 21×) — e ela precisa das lacunas entre
caracteres, que o caminho do livro tem porque tem os boxes.

A **razão de caixa** merece uma linha a mais. Ela é o instrumento que faltava: mede-se sem
gabarito, num livro inteiro, em segundos, e um `S/s` de 0,203 num livro em inglês acusa o
defeito sem que ninguém precise abrir a página. É a irmã da coluna "fora do dicionário" da
F104 — barata, calculável antes de tudo, e preditiva.

---

## 5. O que medir antes de decidir

No espírito do projeto: nenhuma destas decisões precisa ser tomada por convicção.

1. **Quanto da camada de texto se aproveita, por livro.** Instrumento novo,
   `medir_camada.py`: para cada livro, fração de páginas com camada, fração de spans de
   prosa contra spans de fonte de xadrez, e a taxa "fora do dicionário" dos dois lados. É a
   medida de §2.1 generalizada, e ela decide o Caminho A sozinha.
2. **O `.box` das páginas que saem mal.** Rotular três páginas do Yusupov Complete e três do
   Dvoretsky. É a medida que não existe, é o pré-requisito de tudo em §2.2, e sem ela
   nenhuma das hipóteses da família A é verificável.
3. **A régua do espaço contra a classe.** `medir_vao.py` já existe (F107). Acrescentar a
   pergunta: o vão à direita de cada classe, normalizado pelo passo da linha. Se a
   distribuição do `1`, do `l` e do `i` estiver deslocada, a §2.4 está provada e o conserto
   é um limiar por par em vez de por linha.
4. **A máscara de alfabeto.** Rodar o alfabeto restrito contra o irrestrito nas 11 páginas
   rotuladas. É barato e o resultado é imediato.
5. **O reconhecedor de linha, num teste de uma página.** Converter as páginas `.box` para
   transcrição de linha, afinar um motor de linha, medir contra o pipeline de hoje **nas
   mesmas páginas**. Só esse número decide o Caminho C.
6. **Itálico: existe sinal?** Antes de projetar detecção, medir se o recorte carrega
   inclinação separável. A F105 fez exatamente isso para o negrito, e o método serve.
7. **O negrito está disparando demais?** `medir_negrito.py` já existe. A pergunta nova é a
   taxa por livro contra a do impresso, onde o PDF a declare — hoje a saída marca 19,6%
   dos caracteres de prosa, e os dois livros que declaram estilo trazem 9,6% e 11,3%.

---

## 6. Critérios de aceitação

Um livro exportado é aceitável quando, medido na prosa e fora da notação:

- **razão de caixa** dentro de um envelope por idioma — em inglês e em português, `S/s`
  abaixo de 0,08 e `(O+0)/o` abaixo de 0,06;
- **palavras com padrão de caixa ilegítimo** abaixo de 0,5% — hoje são 2,58% antes da F108
  e 1,32% depois;
- **espaço espúrio entre dígitos** abaixo de 100 por livro — hoje são 5.894;
- **nenhum parágrafo de prosa** que seja só fila de coordenada — hoje são 146;
- o EPUB tem **capítulo**, e o sumário tem menos entradas que o livro tem páginas;
- o DOCX abre no Word sem reparo, com teste que verifique isso e não por inspeção;
- o EPUB **continua** passando no `epubcheck` — hoje ele passa com zero mensagens (§2.6), e
  o critério é não regredir, com o validador dentro do teste em vez de rodado à mão;
- o EPUB passa no `ace` da DAISY, que é o que hoje reprovaria: sem `schema:*`, sem `lang`,
  sem `<h1>`.
---

## 7. O que existe de melhor hoje, fora deste projeto

Levantado em 25 e 26 de agosto de 2026, com cada fonte aberta e conferida contra a
primária. O que não se sustentou está marcado como tal — inclusive coisas que a primeira
passada deu por certas.

### 7.1 O motor de linha: Calamari, e não Kraken

| motor | licença | Windows | entrada de treino |
|---|---|---|---|
| **Calamari** 2.3.1 (12/11/2024) | GPL-3.0 | **sim** — o PyPI declara "OS Independent" | imagem de linha + `.gt.txt` |
| Kraken | Apache-2.0 | **não** | imagem de linha + `.gt.txt` |

**O Kraken está fora, e não por qualidade.** O README oficial diz na letra: *"Kraken can be
run on Linux or Mac OS X (both x64 and ARM)"* — Windows não aparece em lugar nenhum, e
este projeto roda em Windows 10.

Três detalhes que mudam quem for escrever o script: os modos de `--resize` são
`union`/`new`/`fail` na documentação 6.0.0, e **não** `add`/`both`, que são nomes da série
3.0; o Kraken **aceita** o mesmo par imagem-de-linha + `.gt.txt` do Calamari, e não exige
ALTO nem PageXML; e a regra das "800 linhas para afinar" vale para *"printed script with a
small grapheme inventory such as Arabic or Hebrew"*, não para um alfabeto de 314 classes —
a própria página avisa que *"There is no hard rule for the amount of training data"*.

### 7.2 Modelo de visão-linguagem: não, e o número é claro

arXiv:2606.13108 (PP-OCRv6, submetido em 11/06/2026, CC BY 4.0, PaddlePaddle). A Tabela 7,
num banco de OCR de documento:

| modelo | parâmetros | pontuação |
|---|---:|---:|
| PP-OCRv6_medium | 34,5 M | **93,20** |
| PP-OCRv6_small | 7,7 M | 88,20 |
| PP-OCRv6_tiny | 1,5 M | 86,80 |
| Kimi-K2.6 | — | 85,00 |
| Qwen3-VL-235B | 235 B | 80,56 |
| GPT-5.5 | — | 78,00 |

Um modelo de 34,5 milhões de parâmetros ganha de todos os de bilhões. E a razão que o
artigo dá é a que importa aqui: *"A critical advantage of specialized OCR models over VLMs
is the absence of text hallucination — generating text not present in the input image."*

**Para este projeto isso não é preferência, é requisito.** Um OCR que erra deixa `biShop`,
que o dicionário acusa e a razão de caixa mede. Um modelo que alucina deixa uma frase
plausível e errada, que nenhum instrumento deste projeto tem como pegar — e num livro de
xadrez a alucinação cai justamente onde o texto é mais previsível e menos verificável.

### 7.3 A caixa: o permuter do Tesseract é a resposta, e ela não pede treino

R. Smith, *An Overview of the Tesseract OCR Engine*, ICDAR 2007, p.632 §6, verbatim:

> the linguistic module (mis-named the permuter) chooses the best available word string in
> each of the following categories: Top frequent word, Top dictionary word, Top numeric
> word, **Top UPPER case word, Top lower case word (with optional initial upper)**, Top
> classifier choice word. The final decision for a given segmentation is simply the word
> with the lowest total distance rating, where each of the above categories is multiplied
> by a different constant.

**Ele não classifica a caixa: gera uma palavra por regime de caixa e escolhe a mais
barata.** A regra tipográfica da F108 deixa de ser uma regra imperativa que precisa de
exceção para `Nf3` e passa a ser **uma hipótese concorrente**.

O projeto já tem as três peças: `predict_topk` com probabilidade, o léxico da F108, e a
regra de caixa. O desenho é: sobre a palavra remontada, gerar as hipóteses — crua do
argmax, a de maior probabilidade no léxico, toda-minúscula, toda-minúscula com inicial
maiúscula, toda-maiúscula, toda-numérica —, **admitindo só a hipótese cujos caracteres
estejam todos entre as candidatas daquele recorte**, e escolher pela soma de custos com uma
constante por categoria. Aplicado **só na trilha de prosa**; a de lance tem gramática e
legalidade.

E o Tesseract confirma o mecanismo pelo outro lado (ICDAR 2007 §7): *"the adaptive
classifier uses isotropic baseline/x-height normalization … The baseline/x-height
normalization makes it easier to distinguish upper and lower case characters."*

### 7.4 Baird 1992: o par `0`/`O` e `1`/`l`/`I` é metade dos erros, e a saída é a treliça

*Document Image Defect Models and Their Uses*, PDF lido na íntegra. p.6: em 100 famílias
tipográficas, pelo menos 95% de acerto na primeira escolha e 99,5% dentro das três
primeiras; e *"Half of these top-choice errors are due to confusions that are arguably
inevitable in any integrated multiple-typeface classifier: i.e. among 0 O, 1 l I, ] J {},
and ' '."* — que são, na letra, as famílias B e D do §1.

**A ressalva importa e é do próprio artigo**: *"These engineering benchmarks were computed
under the assumption that all symbols occur with equal probability."* A proporção de metade
foi medida num regime em que os pares raros estão super-representados. O padrão transfere;
o número, não.

**E o algoritmo de Baird é diferente do que a F19 tentou, o que o torna a novidade desta
seção.** p.7: *"The input to the shape classifier is an image of an isolated character,
without size or baseline context."* p.8:

> Each alternative symbol interpretation implies a text size (estimated from per-class
> statistics collected during training): the median of these sizes, weighted by confidence,
> is selected as the line's dominant text size. This size is then used to prune the
> interpretations.

A F19 pendurou a geometria **depois**, para desempatar contra a âncora, e mediu que não
paga. Baird faz o contrário: cada candidata **propõe** um tamanho, a linha vota qual é o
tamanho dela, e o tamanho **poda** as candidatas. Isso não exige retreinar nada — só as
estatísticas por classe, que saem da base de 626.181 recortes. **É a única ponta desta spec
que ataca a família B sem depender de rotular maiúscula.**

E a p.8 §5 nomeia o que este projeto chama de veto: *"We have experimented principally with
veto filters … These include all-alphabetic or all-numeric rules (quite effective on Latin
languages), punctuation prefix/suffix patterns, dictionary and word-list lookup, and
regular expression patterns."* A regra "dígito não entra em palavra de prosa" — que mataria
a família D, 8% da prosa — é literalmente um dos exemplos dele.

### 7.5 O que se derrubou

- **Truecaser de quatro classes por palavra: não.** O artigo que sustentaria a ideia
  (arXiv:2108.11943, Google, 2021) é justamente uma crítica a essa abordagem.
- **Pós-corretor seq2seq de caractere: não.** Ele não tem como garantir que não inventa
  palavra. Os reparos que este projeto já tem preservam o comprimento por invariante
  testada; um seq2seq não preserva nada. E os casos que estragaram texto nesta auditoria
  (`McNab` virando `Mcnab`) são erro de **política** — qual padrão de caixa é legítimo —, e
  política se conserta com uma condição.
- **A literatura de OCR de xadrez não serve de referência.** Eken et al. (IAJIT 15(1),
  jan/2018, pp. 29–36) reporta 95–100% por classe, mas o conjunto são as trinta primeiras
  páginas de **um** livro, com corte 70/30 aleatório **dentro do mesmo livro** — mesma
  fonte, mesmo corpo, mesmo escaneamento —, e as 30 classes são dígitos, `a`–`h`,
  pontuação e as seis figurinas: **nenhuma letra maiúscula**. O problema de caixa está
  definido para fora do conjunto.
- **O `99,995%` de Baird & Thompson não deve ser citado.** O trabalho existe — *"Reading
  Chess"*, IEEE TPAMI 12(6), 1990, pp. 552–559, confirmado por fonte independente —, e
  validar por legalidade é técnica canônica. Mas a cifra resistiu a duas buscas e continua
  sem fonte primária acessível.

### 7.6 Votação por confiança, que é a melhor razão ganho por trabalho

Reul, Wick, Springmann e Puppe (arXiv:1711.09670): treinar N modelos em dobras diferentes e
somar as confianças de cada caractere e de suas alternativas relevantes. O Calamari traz
isso pronto, em dois comandos. O precedente maior é o ISRI (Rice et al., 1996), que levou
cinco motores de 90,10–98,83% para **99,15%** em cartas comerciais.

Ressalva conferida: o intervalo de ganho que circula — de 16% a 62% — mistura três linhas
de base diferentes e não deve ser citado como um número só.

### 7.7 Escrever DOCX e EPUB: ficar onde está, e fechar as lacunas

- **`python-docx` 1.2.0 (16/06/2025, MIT) — ficar, com versão fixada.** Ela não faz sumário
  (a issue #723 está aberta desde 20/09/2019), e os forks `skelmis-docx` e `python-docx-ng`
  trocariam biblioteca parada e testada por biblioteca ativa e não testada. O sumário sai em
  XML cru — um campo `TOC` mais `updateFields` no `settings.xml`, arquivo que este projeto
  já sabe editar.
- **Pandoc: não como escritor.** Ele **não embute fonte em DOCX**, e é isso que decide: o
  tabuleiro em texto na fonte de xadrez não sobreviveria à travessia. Serve como
  **conferente** — `pandoc saida.docx -t markdown` num teste de regressão dá texto estável
  para comparar entre versões, e pega perda de negrito que nenhuma asserção de XML pega.
- **Validação, que hoje não existe no teste.** Nenhum teste abre o arquivo gerado e o
  valida como arquivo; todos conferem por substring. O docstring de
  `tests/test_f59_fonte_embutida.py` narra o precedente: um `<Default>` inserido fora do
  `<Types>` passou por todas as substrings e tinha deixado de ser XML. O `epubcheck` 5.3.0
  **já está instalado neste ambiente** (`pip install epubcheck==5.3.0`, 33,5 MB, pede Java;
  há Java 25 aqui) e já foi rodado — ver §2.6, onde deu zero. Ele **não está no
  `requirements.txt`**, e é decisão sua se entra como dependência de teste. Faltam o
  `openxml-audit` para o lado do DOCX e o `ace` da DAISY 1.4.6 para acessibilidade (pede
  Node 20). **`epubcheck` e Ace conferem coisas diferentes, e o que falta neste EPUB é
  justamente o que só o Ace vê** — o `epubcheck` já deu zero.
- **Acessibilidade deixou de ser opcional na Europa em 28/06/2025.** EPUB Accessibility 1.1
  (Recomendação W3C de 17/10/2024), §2.2, na letra: *"All EPUB publications MUST include
  Schema.org accessibility metadata in the package document that exposes their accessible
  properties, regardless of whether the publications also meet the accessibility or
  optimization requirements."* O EPUB deste projeto não escreve nenhum `schema:*`. E o
  `<html>` traz `xml:lang` sem `lang` — a regra `html-has-lang` do axe **não aceita
  `xml:lang` como alternativa**, e ela mapeia para WCAG 3.1.1, nível A.

### 7.8 hOCR: o intermediário que guarda o que este projeto joga fora

Esta é a recomendação de arquitetura que veio de fora, e a que eu não teria proposto
sozinho.

O `BoxEntry` calcula caractere, caixa, confiança, ângulo e polaridade; o `Paragrafo` guarda
texto e fatias de negrito. **Tudo o mais é descartado na passagem** — `core/livro.py:599`
apaga o caractere, e a confiança vira um contador por página. E a geometria descartada é
exatamente a que o §2.3 diz que falta.

O **hOCR** guarda tudo isso por norma: `bbox` e `baseline` na `ocr_line`, `x_bboxes` e
`x_confs` no `ocrx_cinfo` — confiança **por caractere, em ponto flutuante**. O **ALTO**
carrega negrito por palavra nativamente, como atributo de esquema desde 2009, que é o que a
F105 construiu do zero.

E há precedente de escala: **o Internet Archive resolveu o mesmo problema com hOCR como
fonte única**, gerando os derivados a partir dela.

A proposta é modesta e não pede migração: um `core/hocr.py` que **escreva** hOCR a partir do
que o `extrair_pagina` já tem. O primeiro consumidor natural é o `core/searchable_pdf.py`,
que é o que mais se parece com hOCR e o que menos trabalho dá para migrar. Duas ideias do
ALTO valem mesmo sem adotar o formato: o vocabulário fechado de estilos (`bold`,
`smallcaps`, `superscript`) como valores canônicos do projeto, e a separação entre margem e
mancha.

---

## 8. Os defeitos de arquivo que cabem numa tarde

Nenhum destes é decisão arquitetural. Todos foram reproduzidos.

| defeito | onde | conserto |
|---|---|---|
| `<dc:creator>python-docx</dc:creator>`, data de 2013, miniatura da biblioteca | `ui/main_window.py:1819-1823` não passa `autor` | passar autor e datas |
| as oito linhas do diagrama entram no XHTML **sem escape** — **latente**: as duas fontes de hoje só emitem caractere seguro e o `epubcheck` dá zero nas duas; dispara no dia em que uma terceira fonte mapear `<`, `>` ou `&` | `exportar.py:288` e `:300` | `html.escape`, como as outras seis saídas do módulo já fazem |
| figurina em célula de tabela sai **sem a fonte** no DOCX | `exportar.py:1025-1027` — `celula.text` cria run sem `rPr` | o caminho gêmeo do EPUB já acerta e tem teste |
| diagrama em modo de fonte sem texto alternativo — 501 tabelas | `exportar.py:957-1003` | `w:tblCaption` e `w:tblDescription` |
| nenhum FEN chega ao `descr` — 151 figuras, duas cordas | §2.6 | achar por que `figura.fen` vem vazio |
| `lang` ausente no `<html>` e no `nav.xhtml` | `exportar.py:421-423` e `:632-635` | duas linhas |
| `dc:identifier` literal `pyboxeditor` em todo livro | `exportar.py:517` | uma URN por livro |
| `dcterms:modified` fixo em `2026-01-01` | `exportar.py:627` | `SOURCE_DATE_EPOCH`, caindo para a data corrente |
| `<h2>` sem `id`, e nenhum `<h1>` no livro inteiro | `exportar.py:412` | âncora, e promover capítulo a `h1` |
| hífen de fim de linha chega ao arquivo — 49 medidos | `livro.py:862` | `juntar_hifenizadas`, §4.1 |

E uma questão que não é de código: **não há licença arquivada para as duas fontes de xadrez
que o programa embute**. A Noto tem o `OFL.txt` ao lado; estas não têm. Ofuscação não é
licença — a própria norma do EPUB diz que ela não protege nada.
