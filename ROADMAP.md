# PyBoxEditor — Roadmap

Versão do documento: 1.0
Data: 2026-08-03
Escopo: OCR de livros de xadrez em PDF (editor de boxes + rede neural + substituição de glifos)

Documento companheiro: [`docs/SPEC.md`](docs/SPEC.md) (especificação de implementação)
Spec anterior (módulo de glifos): [`Substituição de Glifos de Xadrez.md`](Substituição%20de%20Glifos%20de%20Xadrez.md)

---

## Sumário executivo

O projeto tem uma arquitetura boa (services desacoplados da UI, dataclass de domínio,
pipeline de fallback neural → k-NN → EasyOCR) e uma base de treino relevante
(127.264 amostras, 105 classes). Mas ~~hoje **ele não roda**~~ — na abertura deste
documento não rodava: cinco defeitos de runtime bloqueavam o caminho principal, e a
funcionalidade-carro-chefe (substituição de glifos de xadrez) **corrompia o PDF em
silêncio**.

Todos os itens P0 abaixo foram reproduzidos executando o código, não inferidos por leitura.

| Fase | Tema | Resultado esperado | Status |
|------|------|--------------------|--------|
| **F0** | Desbloqueio | O app abre, edita e salva sem exceção | **concluída** (F0.1–F0.4) |
| **F1** | Qualidade de OCR | Acurácia medível; segmentação e leitura corretas | **concluída** (F1.1–F1.9, F1.5b) |
| **F2** | Saída PDF | PDF pesquisável, sem rasterizar o documento | **concluída** (F2.1–F2.4) |
| **F3** | Produtividade | Revisão de 2.000 caracteres/página deixa de ser inviável | **concluída** (F3.1–F3.9) |
| **F4** | UI | Interface responsiva, sem congelar | **concluída** (F4.1–F4.8) |
| **F5** | Higiene | Dependências corretas, código morto removido, testes | **concluída** (F5.1–F5.4) |
| **F6** | Saída de partidas | A notação lida vira `.pgn` que abre num programa de xadrez | **concluída** (F6.1) |
| **F7** | Diagramas, desempenho e integridade | Posição impressa vira FEN; o k-NN sai do caminho; o modelo não se descasa | **concluída** (F7.1–F7.5) |
| **F8** | Texto girado e diagramas conferíveis | O rótulo vertical é lido; o diagrama vira tabuleiro editável que alimenta o treino | **concluída** (F8.1–F8.3) |
| **F9** | Léxico do texto corrido | Palavra fora do dicionário é sinalizada para revisão; o usuário acrescenta as suas | **concluída** (F9.1, F9.2) |
| **F10** | Texto em negativo | O nome dos jogadores na tarja preta deixa de ser um borrão e vira texto | **concluída** (F10.1) |
| **F11** | Texto sobre trama | O quadro de pontuação deixa de apagar o texto da página; a régua da página para de desabar | **concluída** (F11.1) |
| **F12** | Duas linhas num box | O descendente que encosta na linha de baixo deixa de engolir um caractere | **concluída** (F12.1) |
| **F15** | O dpi da renderização | O render para de jogar fora a resolução que está no arquivo | **concluída** (F15.1) |

> **Re-medido em 2026-08-07, com a F12.** Nas 10 páginas rotuladas o pipeline dá **94,4
> de F1** (94,9% de recall, 94,0% de precisão, 323 boxes espúrios), contra 94,1 antes. O
> ganho é do corte de linha, e a conta de onde vem o que ainda falta está na F12.1: 231
> caracteres colados na horizontal, 348 lidos errado com o box certo.

**Onde o projeto ficou, em números medidos e não estimados.** Nas 9 páginas rotuladas
à mão (7 do Kasparov + 2 do Aagaard, ~9.400 caracteres), o pipeline completo dá
**93,8 de F1** — 94,5% de recall e 93,0% de precisão. O classificador sozinho, medido
em recorte já segmentado, dá **99,83%** no conjunto de teste. A distância entre os dois
números é o trabalho que sobra, e ele é de **segmentação**, não de modelo.

> Estes dois números são de **2026-08-04**, com o modelo de 103 classes. Re-medido em
> **2026-08-06**, com o modelo de 119 classes e 10 páginas rotuladas, o pipeline dá
> **94,2 de F1** (94,6% de recall, 93,7% de precisão). As duas re-medidas estão na F1.5b
> (segmentação e F1) e na F1.9 (calibração e triagem), e a conclusão estrutural não mudou:
> a distância que sobra é de segmentação.

Do outro lado do pipeline, a F6.1 fecha o caminho: as mesmas páginas rendem partidas de
**32, 27, 24, 20 e 12 lances** exportadas em PGN, com a abertura do livro saindo certa em
todas.

Cobertura: **1.035 testes**, `pytest` na raiz, 78 segundos.

> As digitalizações não estão no repositório (`ilovepdf_pages-to-jpg/` é material com
> direitos autorais). Num clone limpo sobram 2 páginas rotuladas com imagem, não 9, e os
> números acima **não** serão reproduzidos. `medir_paginas.py` e `calibrar_modelo.py`
> rodam com o conjunto que encontrarem — só medem menos.

---

## F0 — Desbloqueio (crítico) — CONCLUÍDA

> Sem esta fase nada mais importa: o programa quebra ao carregar qualquer box.

**Aplicada em 2026-08-03**, branch `fix/f0-desbloqueio` (4 commits sobre a baseline
`54bf80d`). Cobertura em `tests/test_f0_smoke.py` — 11 testes, dos quais 9 reprovam
na baseline e passam no código corrigido.

Verificação final: fluxo completo do editor sobre uma página real de 1310×1900
(abrir → detectar 764 boxes → editar → dividir → excluir → undo/redo → arrastar →
salvar → recarregar) sem nenhuma exceção.

### F0.1 — `BoxEntry` acessado como dicionário — corrigido
`ui/main_window.py:569` faz `b['x1']` num dataclass.

```
TypeError: 'BoxEntry' object is not subscriptable
```

`update_sidebar()` roda em **todo** carregamento, seleção e edição. O app morre assim
que existe um único box. **Este é o bug que impede o uso do programa.**

Mesma falha em três outros pontos:

| Arquivo | Linha | Chamada | Erro | Recurso quebrado |
|---------|-------|---------|------|------------------|
| `ui/main_window.py` | 569 | `b['x1']` | `TypeError` | Tudo |
| `ui/canvas_view.py` | 205, 216 | `boxes[i].copy()` | `AttributeError` | Mover/redimensionar box |
| `core/services/learning_service.py` | 52–56 | `b.get("char")`, `b["x1"]` | `AttributeError` | Aprender com Página Atual |
| `core/services/learning_service.py` | 137–141 | passa `dict` a `merge_vertical_boxes` | `AttributeError` | Treinamento Batch |

**Causa raiz:** houve migração de `dict` para `BoxEntry` que parou no meio. A correção
não é só trocar sintaxe — é fechar a migração e travá-la com teste.

### F0.2 — Substituição de glifos escreve `·` no lugar das peças — corrigido

`core/chess_pdf_processor.py:92` usa `fontname="helv"` (Helvetica Base-14, Latin-1).
Essa fonte não tem os glifos U+2654–U+265F. O PyMuPDF **não levanta erro**: troca cada
peça por `·`.

Verificado:

```
insert_text(..., "♔♕♖♗♘", fontname="helv")  →  texto extraído: '·····'
```

O usuário roda a conversão, vê "Concluído", e recebe um PDF destruído.

**Correção verificada** — embutir uma fonte Unicode:

```python
page.insert_font(fontname="chessuni", fontfile=r"C:\Windows\Fonts\seguisym.ttf")
# resultado: '♔♕♖♗♘♙♚♛♜♝♞♟'  (12/12 preservados)
```

`seguisym.ttf` existe nesta máquina. Ainda assim, a fonte deve ser **empacotada** no
projeto (`assets/fonts/`) — depender de fonte do sistema quebra em outro computador.
Ver SPEC §4.2.

### F0.3 — Undo/redo perde estado — corrigido

Verificado: o projeto mistura dois padrões incompatíveis.

- `apply_char`, `auto_fill_characters` → snapshot **depois** da mutação (correto)
- `on_mutation_start`, `delete_selected_box`, `generate_boxes_opencv` → snapshot **antes**

No padrão "antes", o estado novo nunca entra no histórico:

```
add B → undo → ['A']      (ok por acidente)
      → redo → ['A']      ✗ deveria ser ['A','B'] — o B some para sempre
```

**Correção:** um único padrão — `snapshot()` sempre *após* a mutação, com o estado
inicial gravado ao abrir a imagem. Ver SPEC §6.1.

### F0.4 — `requirements.txt` inutilizável — corrigido

- `PyMuPDF>=1.23.0` está gravado em **UTF-16**; o pip lê como `P y M u P D F`
- `torch` e `easyocr` — usados no código, **ausentes** do arquivo
- `pydantic` e `python-Levenshtein` — listados, não instalados, não usados

Ou seja: `pip install -r requirements.txt` não reproduz o ambiente.

---

## F1 — Qualidade de OCR

### F1.1 — ~~O modelo cobre 5 das 12 peças~~ — PREMISSA ERRADA, corrigida

**Investigado em 2026-08-03. O item estava errado, e o erro foi da análise inicial
(minha).** A base não está faltando 7 classes: ela está **completa para o domínio**.

Duas razões, verificadas no material real do usuário:

**1. Peão não tem letra em notação algébrica.** Um lance de peão escreve-se `e4`, nunca
com figurina. Os codepoints ♙ (U+2659) e ♟ (U+265F) são inalcançáveis — 2 das 7.

**2. O livro usa um único conjunto de figurinas para os dois lados.** Ampliando uma
linha real do Kasparov:

```
17...♞e5  18.♛c2  ♞a6  19.♞c4  ♞b4
```

`17...` é lance das **pretas** e `19.` é lance das **brancas** — e os dois cavalos usam
o **mesmo glifo de contorno**. A dama aparece preenchida porque é assim que a fonte
desenha dama, não por ser preta. Os 5 codepoints "pretos" não existem como desenho
próprio — as outras 5 das 7.

Sobram exatamente **K, Q, R, B, N**: as únicas peças que ganham letra na notação, e
exatamente as classes que o modelo tem.

Medições que sustentam isso:

| Classe | Amostras | Tinta média | Desvio |
|---|---:|---:|---:|
| ♔ `sym_9812` | 2643 | 30,0% | 5,5% |
| ♕ `sym_9813` | 1899 | 41,9% | 6,0% |
| ♖ `sym_9814` | 845 | 48,7% | 7,9% |
| ♗ `sym_9815` | 352 | 33,8% | 4,9% |
| ♘ `sym_9816` | 1768 | 33,2% | 5,8% |

Desvios de 5–8% e sem bimodalidade: cada classe tem **um** estilo visual, não duas
variantes misturadas.

**O que foi feito.** `searchable_pdf.PECAS` esperava os 12 símbolos; 7 nunca casavam.
Passou a conter os 5 reais, com o porquê documentado, e há teste travando isso — se
alguém "consertar" de volta para 12, o filtro volta a ter entradas mortas.

**O que a investigação revelou de verdade.** Rodando o modelo sobre notação real, as
figurinas isoladas saem com confiança **1,000**. Os únicos erros foram boxes em que a
figurina ficou **fundida com a coordenada seguinte** (`♞e5` e `♞a6` num box só), e aí a
classificação erra. Isso é **segmentação** — F1.5 e F1.6 —, não classe faltante.

**E a lacuna que sobra é outra.** Decidir se um ♘ reconhecido é peça branca ou preta é
**visualmente impossível**: o glifo é o mesmo. Depende da paridade do número do lance
(`18.` é das brancas, `18...` das pretas) ou da legalidade da posição. Ou seja, é
exatamente a **F1.7**, e não trabalho de reconhecimento de imagem.

### F1.2 — Desbalanceamento extremo, sem compensação — CONCLUÍDA

| Classe | Amostras |
|--------|---------:|
| `lower_e` | 25.075 |
| `lower_a` | 16.861 |
| `lower_h` | 10.608 |
| … | |
| `upper_X`, `upper_Y`, `upper_Z` | **1** |
| `lower_ä` | **0** (pasta vazia, mas ocupa índice de classe) |

Proporção de 25.075:1. Com `CrossEntropyLoss` sem pesos e `shuffle=True` puro
(`neural_trainer.py:186,191`), o modelo aprende a nunca arriscar classes raras —
o custo de errar um `e` domina o gradiente.

**Concluída em 2026-08-03.** `WeightedRandomSampler` no treino, augmentation
gerada sob demanda e piso de amostras que **reporta em vez de excluir**.

#### Medir exigiu construir o holdout antes

O item afirmava que o modelo nunca arrisca classes raras. Rodando o
`custom_model.pth` atual sobre a base, o recall dá ~100% em **todas** as 103
classes, inclusive nas de 1 amostra — mas isso é medido sobre o próprio treino e
não prova nem refuta nada. É exatamente o que a F1.3 diz.

Então foi preciso separar um holdout: 20% de cada classe com 5 amostras ou mais
(teto de 200 por classe), semente fixa, 121.020 amostras de treino contra 5.768
de avaliação, 8 epochs, as quatro configurações no mesmo split.

Com holdout, o item se confirma **no sentido, não na magnitude**: o modelo não
ignora as classes raras em bloco — ele acerta 77,2% das que têm menos de 20
amostras —, mas 5 classes ficam em zero e o recall macro fica quase 8 pontos
abaixo da acurácia global.

| Configuração | Acurácia (micro) | Recall macro | Classes zeradas |
|---|---:|---:|---:|
| como estava (sorteio uniforme) | 96,58% | 88,66% | 5 |
| `class_weight` na loss | 96,20% | 88,60% | 4 |
| `WeightedRandomSampler` 1/n | 97,90% | **97,22%** | **0** |
| `WeightedRandomSampler` 1/√n ← adotado | **98,63%** | 96,71% | 1 |

Recall macro por tamanho da classe, do estado anterior para o adotado:

| Amostras de treino | Classes | Antes | Depois |
|---|---:|---:|---:|
| ≥ 1.000 | 17 | 99,9% | 99,9% |
| 100–999 | 24 | 98,0% | 99,3% |
| 20–99 | 12 | 78,8% | **97,1%** |
| < 20 | 26 | 77,2% | **92,1%** |

Não há troca: o micro **sobe** junto com o macro, e as classes grandes ficam onde
estavam. Por isso o 1/√n foi preferido ao 1/n, que ganha 0,5pp de macro e devolve
0,7pp de micro — e as 10 classes mais comuns, que sozinhas são 79,6% da base, caem
de 99,9% para 99,6%.

Essa tabela veio de um laço de treino escrito à parte, para variar as quatro
configurações. Rodando de novo pelo `NeuralTrainer` de verdade, com o split sem as
classes truncadas do estudo do piso: **99,50% de acurácia global e 97,89% de recall
macro**, uma classe zerada — o `✝`, que tem 1 amostra no holdout, ou seja 0 de 1.
Os números saem mais altos que os da tabela porque lá seis classes foram
deliberadamente reduzidas a 1–20 amostras, e elas puxam as duas médias para baixo em
todas as quatro linhas igualmente. A tabela serve para **comparar**; esta rodada
serve para confirmar que o caminho de produção é o que foi medido.

#### A SPEC oferecia duas saídas e uma delas não funciona

§5.3 dizia "`WeightedRandomSampler` **ou** `class_weight` na loss", como se
fossem equivalentes. Pesar a loss não mudou nada (88,60% contra 88,66% do
baseline). Reescalar o gradiente não resolve quando a classe rara aparece em 1 de
cada mil lotes: o pico raro é em boa parte absorvido pela normalização do Adam. O
sampler muda **o que o modelo vê**, e é isso que conta.

#### O bloqueio maior era memória, e não estava no item

`CharDataset` materializava 8 variantes de cada amostra em float32 dentro do
construtor. Na base real: 127.263 originais viram 1.145.367 arrays de 4 KB.

| | Antes | Depois |
|---|---:|---:|
| RAM do dataset | **4,89 GB** | **133 MB** |
| Tempo de carga | 2,2 min | 24,7 s |
| Amostras por epoch | 1.145.367 | 127.263 |

(O "antes" foi medido com 1/8 da base — 628 MB para 15.958 originais — e
extrapolado; a máquina tem 16 GB, com 3,8 GB livres na hora da medição. Ou seja,
o treino da base inteira provavelmente nunca rodou.)

E isso não é só otimização: **é o que faz o balanceamento funcionar**. Com as
cópias congeladas no construtor, o sampler sorteia sempre as **mesmas 9 imagens**
de uma classe rara, dezenas de vezes por epoch. Sob demanda, cada sorteio dá uma
variante nova — e sai por 53 µs, 7 s por epoch de 127 mil.

Como um epoch deixou de valer 9 passadas, ele voltou ao significado usual e ficou
~9× mais rápido. O diálogo de treino passou a dizer isso.

Um detalhe que precisou de cuidado: 1 sorteio em cada 9 devolve a amostra
**intacta**. Era a proporção do desenho antigo (1 original para 8 cópias), e é
imagem limpa que chega na hora de predizer — `apply_random_augmentation` deixa
passar sem tocar só 0,9% das vezes.

#### O piso de 10 amostras reporta, não exclui

A SPEC §5.3 pedia excluir do treino as classes abaixo do piso. Conferindo quais
cairiam, a proposta não se sustenta: das 33 classes com menos de 10 amostras,
estão lá `'K'` (6), `'Q'` (5) e os símbolos de anotação de xadrez
`±` `∓` `∞` `□` `■` `△` `▼`. São raras porque aparecem pouco no texto, não porque
sejam lixo — e são vocabulário do domínio. Excluir significaria o modelo nunca
poder produzi-las, e o pipeline não cai no fallback quando a rede erra com
confiança: ele grava o caractere errado.

A medição confirma que dá para aprendê-las: com balanceamento, a faixa de menos
de 20 amostras (26 classes reais) vai a 92,1% e nenhuma fica zerada.

Para ver quanto é pouco demais, seis classes de 100+ amostras foram truncadas no
treino, mantendo 50 no holdout:

| Amostras de treino | Antes | Depois |
|---:|---:|---:|
| 1 | 0% | 74% |
| 2 | 12% | 60% |
| 3 | 92% | 98% |
| 5 | 56% | 62% |
| 10 | 98% | 100% |
| 20 | 94% | 98% |

**Isto é ilustração, não curva.** É uma rodada por configuração e uma classe por
tamanho: 3 amostras dando 98% e 5 dando 62% é variância, não é o efeito do
tamanho. O que se sustenta é o extremo (1–2 amostras é pouco em qualquer
configuração) e o agregado das 26 classes reais da faixa.

A explicação de por que tão pouco basta é o domínio: é uma fonte só. O modelo não
precisa generalizar entre estilos de letra, precisa tolerar ruído de digitalização
— que é o que a augmentation dá.

#### Dois defeitos achados no caminho

1. **A pasta `_quarentena` virava classe.** O `dataset_check` da F1.4 põe PNG
   suspeito em `training_data/_quarentena`, e o `CharDataset` a lia como classe.
   Pior: ordenada, `_` vem antes das letras, então ela ficava com o **índice 0** e
   deslocava o mapa inteiro. Reproduzido contra o código do commit anterior — o
   primeiro arquivo em quarentena corromperia o modelo seguinte em silêncio.
2. **Pasta vazia ocupava uma saída da rede.** É o caso `lower_ä` citado no item.
   Um neurônio que nunca pode estar certo continua competindo em toda predição.
   Pastas sem amostra legível deixaram de receber índice.

#### O que esta fase não resolve

A acurácia continua sendo medida sobre o treino, e o "melhor modelo" continua
sendo escolhido por *training loss* — é a F1.3, e o holdout usado aqui foi
montado à mão para medir, não faz parte do produto. O rótulo na barra de status
passou a dizer `Acc(treino)`, porque com o sampler esse número **cai** (as
classes raras deixaram de ser arredondamento) e chamá-lo de "Acc" faria parecer
piora.

E o modelo em uso (`custom_model.pth`, de março) **não foi retreinado** — os
ganhos acima aparecem no próximo treino.

Cobertura: `tests/test_f12_balanceamento.py`, 24 testes.

### F1.3 — A acurácia reportada não significa nada — CONCLUÍDA

`neural_trainer.py:389` calcula acurácia sobre o **próprio conjunto de treino, já
aumentado**. Não existe split de validação. O "Acc: 98%" exibido ao usuário não diz
se o modelo generaliza — e com o desbalanceamento acima, prever sempre as 10 classes
mais comuns já daria número alto.

Pior: `torch.save` em `neural_trainer.py:395` usa *training loss* como critério de
"melhor modelo". Isso seleciona o ponto de maior overfitting.

**Concluída em 2026-08-03.** `core/avaliacao.py` com split estratificado 80/15/5,
early stopping por perda de validação, checkpoint pela melhor epoch de validação e
relatório com matriz de confusão. Menu **Ferramentas → Relatório do último treino**.

#### O treino real, com o código de produção

15 epochs sobre a base inteira. A divisão saiu em **101.827 / 19.081 / 6.355**.

| | Validação | Teste |
|---|---:|---:|
| Acurácia global | 99,86% | **99,84%** |
| Recall macro | 97,45% | **98,41%** |
| Classes zeradas | 1 | — |

O teste é o número que vale: ele não entrou em nenhuma decisão do treino, nem no
checkpoint nem no early stopping. A validação entrou, então já está um pouco
contaminada como estimativa.

As confusões que apareceram são exatamente as que a SPEC §5.4 previa que a matriz
revelaria:

| | | |
|---|---|---:|
| `,` lido como `'` | e o inverso | 3x / 2x |
| `.` lido como `-` | e o inverso | 3x / 2x |
| `1` lido como `l` | e o inverso | 2x / 1x |
| `W` lido como `w` | | 3x |
| `✝` lido como `+` | e o inverso | 1x / 1x |
| `f` lido como `f7` | a ligadura da F1.4 | 1x |

#### Com 15 epochs os dois critérios coincidiram; com 25 não

Na primeira rodada a perda de treino caiu monotonicamente (0,6047 → 0,0377) e a de
validação também terminou no mínimo: **os dois critérios apontaram a epoch 15**. Em
15 epochs o modelo ainda não tinha começado a piorar, então o "ponto de maior
overfitting" ainda não havia chegado — o defeito era real, mas não se manifestava.

Deixando rodar até 25 epochs, ele se manifestou:

| epoch | perda(treino) | perda(val) |
|---:|---:|---:|
| 17 | 0,0296 | **0,0049** ← gravada |
| 22 | **0,0246** | 0,0058 |

A perda de treino continuou caindo enquanto a de validação subia. O critério antigo
teria gravado a epoch 22 — o modelo que decorou mais. O early stopping cortou na 22
e o que ficou em disco é a 17.

#### Uma armadilha de leitura que o relatório passou a avisar

O recall macro **não** teve pico na epoch de menor perda:

| epoch | perda(val) | acurácia(val) | macro(val) |
|---:|---:|---:|---:|
| 8 | 0,0063 | 99,82% | **98,99%** |
| 10 | 0,0056 | 99,86% | 97,78% |
| 15 | **0,0055** | 99,86% | 97,45% |

A tentação é trocar o critério para o recall macro. Medindo antes de mexer: das 79
classes avaliáveis, 9 têm **1** amostra de validação e 14 têm de 2 a 4. Com 79
classes, uma única amostra que muda de lado mexe **1,27 ponto** no macro — e a
oscilação toda, de 97,15% a 98,99%, cabe em uma amostra e meia. É ruído.

A perda de validação usa as 19.081 amostras e por isso é estável; o macro é uma
média por classe sobre conjuntos minúsculos. O critério ficou como a SPEC pedia, e o
relatório passou a dizer quantas classes estão nessa situação e quanto vale uma
amostra, para ninguém ler ruído como melhora. O teste dá macro **maior** que a
validação (98,41% contra 97,45%) pelo mesmo motivo: são amostras diferentes,
poucas por classe.

O caminho para tornar o macro confiável não é trocar o critério — é coletar mais
amostras das classes raras.

#### Decisões que não estavam na SPEC

- **Classe com menos de 5 amostras não é dividida.** São **24 das 103**, e elas vão
  inteiras para o treino. Tirar 15% de uma classe de 3 deixa o treino com 2 para
  medir mal 1. O relatório lista as 24 pelo nome, em primeiro lugar, e o log do
  treino avisa: uma acurácia de validação que ignora um quarto das classes em
  silêncio seria o mesmo defeito deste item, com outra roupa.
- **O conjunto de teste não tem piso de 1 amostra por classe** — serve para um único
  número final, não para recall por classe.
- **Os pesos do sampler da F1.2 passaram a vir das contagens do treino**, não da base
  inteira: contar amostras que o modelo não vai ver subestimaria as classes raras.
- **Base pequena demais para dividir continua treinando**, e avisa que voltou ao
  critério ruim. É o caso de quem começou a coletar hoje.

#### O modelo em uso foi retreinado

`custom_model.pth`, que era de março, foi refeito pelo caminho de produção
(`LearningService.train_neural`, 25 epochs, paciência 5). Parou por early stopping na
epoch 22 e gravou a 17: **99,85% de validação, 99,83% de teste, 97,54% de recall
macro**. O modelo anterior está em `custom_model_2026-08-03_antes_f13.pth`.

`model_meta.json` foi de 105 para **103 classes** — as duas pastas vazias que a F1.4
removeu deixaram de ocupar índice, como a F1.2 previu.

Conferido depois do retreino, com uma amostra real de cada classe:

| Classe | Amostras na base | Predição | Confiança |
|---|---:|---|---:|
| `♔` | 2.643 | `♔` | 1,000 |
| `♘` | 1.768 | `♘` | 1,000 |
| `e` | 25.075 | `e` | 1,000 |
| `K` | **6** | `K` | 1,000 |
| `±` | **5** | `±` | 1,000 |

As duas últimas são as classes que a SPEC §5.3 mandava excluir do treino.

#### O que fica em aberto

- O modelo é treinado com 80% dos dados e fica assim. Retreinar na base inteira
  depois de descobrir a melhor epoch recuperaria os 20%, ao custo de dobrar o tempo.
- ~~`model_meta.json` está no git e `custom_model.pth` não. É exatamente o
  descasamento que a SPEC §5.5 descreve~~ — **fechado pela F7.3**: o metadado passou a
  levar o SHA-256 dos pesos, e um par trocado é recusado em vez de ler letra errada.

Cobertura: `tests/test_f13_validacao.py`, 25 testes.

### F1.4 — Classe corrompida no dataset — CONCLUÍDA

A pasta `training_data/sym_f7/` tem **127 amostras**. Mas:

```python
folder_to_char("sym_f7")  →  chr(int("f7"))  →  ValueError  →  "?"
```

São 127 amostras treinando o modelo a prever literalmente `"?"`. O nome veio de um
`char_to_folder` hexadecimal antigo que o `folder_to_char` atual não sabe reverter
(`core/learner.py:69-73`).

O mesmo caminho engole erro em `ligature_hex_*`, que retorna `"?"` por TODO
não implementado (`learner.py:56`).

**Concluída em 2026-08-03.**

**O que `sym_f7` era.** Minha hipótese inicial (`f7` em hexadecimal = `÷`) estava
errada. Olhando as amostras, são literalmente **"f7"** — a casa de xadrez, num box
de dois caracteres. E colidiam com `sym_63`, que é o `?` de verdade: duas classes
distintas ensinando o mesmo símbolo.

**Ganho imediato, sem retreinar.** O índice 79 do modelo já treinado foi aprendido
com as 127 imagens de "f7", mas o `model_meta.json` o rotulava `"?"`. Corrigido o
rótulo, o modelo existente acerta **127/127** dessas amostras — antes, todas saíam
como `?`.

Também entrou:

- ida e volta nome↔caractere consertada: `'f7'` caía no ramo hexadecimal porque o
  teste era `isalpha()`; o hex passou a ter largura fixa (com largura variável,
  `'ab'+'c'` e `'a'+'bc'` geram o mesmo nome)
- `folder_to_char(..., strict=True)` levanta em vez de devolver `"?"` — devolver
  `"?"` em silêncio foi o que deixou o defeito passar
- `core/dataset_check.py` com validação e migração, ligadas ao treino (que agora
  falha alto) e a um item de menu **Verificar base de treino**

**Dois bugs de encoding descobertos no caminho:**

1. `NeuralPredictor.load()` abria o `model_meta.json` **sem encoding**, caindo no
   cp1252 do Windows. Funcionava por acaso porque o `json.dump` padrão escapa tudo
   em ASCII — bastou gravar o arquivo em UTF-8 de verdade para o carregamento do
   modelo quebrar.
2. `cv2.imwrite` e `cv2.imread` **falham em caminho não-ASCII no Windows** e
   devolvem `False`/`None` sem levantar erro. É a explicação da pasta `lower_ä`
   estar vazia: alguém tentou salvar amostras de "ä" e o OpenCV as descartou em
   silêncio.

**Erro meu, com custo real:** a primeira versão da migração usou `cv2.imread` para
detectar PNG corrompido. Como ele também falha em caminho não-ASCII, ela marcou
como ilegíveis 7 PNGs válidos num teste — e os apagou. Na base real isso custou
**1 arquivo** (a única amostra de `lower_ü`, classe já inutilizável com 1 amostra).
Corrigido: a leitura passa por `open()` + `cv2.imdecode`, o que separa
"não consegui abrir o caminho" de "não é uma imagem", e a migração **põe em
quarentena em vez de apagar**.

Resultado na base real: 105 → 103 classes, 0 problemas graves, 127.263 amostras.

Cobertura: `tests/test_f14_dataset.py`, 24 testes.

### F1.5 — Pré-processamento fraco para material escaneado — CONCLUÍDA

Threshold fixo em **180**, replicado em três lugares
(`box_service.py:20`, `learning_service.py:127`, `neural_pdf_processor.py:17`).

Sem: Otsu, threshold adaptativo, deskew, remoção de ruído, normalização de DPI.
Para páginas escaneadas com iluminação irregular — o caso normal em livro digitalizado —
isso perde caracteres inteiros nas bordas.

Detalhe irônico: `core/opencv_autobox.py:17` **já implementa Otsu** com filtros de
tamanho melhores. O arquivo nunca é importado. Está morto.

**Concluída em 2026-08-03.** `core/preprocess.py` com `binarize` (auto/otsu/
adaptive/fixed), `deskew`, `denoise` e `normalize_dpi`. O Otsu veio do
`opencv_autobox.py` arquivado na F5.1, como previsto.

**Minha primeira heurística de "auto" estava errada.** Ela testava bimodalidade do
histograma para escolher entre Otsu e adaptativo. Numa página com sombra de
encadernação o histograma **é** bimodal — metade escura contra metade clara — e o
Otsu devolve quase metade da página como tinta. Medido nesse cenário:

| Método | Tinta resultante |
|---|---:|
| limiar fixo 180 | 61,3% |
| Otsu | 47,6% |
| adaptativo | **3,1%** |

O critério passou a avaliar o **resultado**, não o histograma: se a fração de tinta
não é plausível para texto (0,05%–35%), cai no adaptativo.

#### Separação de glifos colados — o que a F1.1 apontou

Em notação figurina o espaçamento é apertado e os contornos se tocam:
`findContours` devolvia `♞e5` como **um** box, e o classificador lia um caractere
errado. Era a origem de todos os erros de figurina na página real.

**O critério é a largura do vale, não a profundidade.** Medido (mediana de
caractere = 19 px), contando colunas com tinta abaixo de 30% do pico:

| Caso | Largura do vale | Fundo (% do pico) |
|---|---:|---:|
| `♞e5` (3 glifos) | **10** | 8% |
| `♞a6` (3 glifos) | **10** | 10% |
| `W` (1 glifo) | 2 | 25% |
| `♛` (1 glifo) | **0** | 41% |

Cortar por profundidade partiria a coroa da dama, que tem vales fundos entre as
pontas. A largura separa os casos com folga.

Validação em 8 páginas reais:

| | |
|---|---:|
| Boxes | 8.501 → 9.059 |
| Boxes largos (suspeitos de colados) | 660 → 427 (**35% resolvidos**) |
| Pedaços estreitos novos (corte falso) | **0** |

O efeito no texto: `17...♞e5` saía como um único `♕` errado; agora sai `♘k5` — a
figurina certa e dois dos três caracteres. O que resta (`e`→`k`) é confusão do
classificador, não de segmentação: é F1.2 e F1.3.

35% é honesto — nem todo box largo é glifo colado (`W`, `♛`, travessões são
legitimamente largos), e alguns colados não têm vale largo o bastante para cortar
com segurança. Zero cortes falsos é a propriedade que importa.

Cobertura: `tests/test_f15_preprocess.py`, 20 testes.

#### Correção durante a F1.7 — a escala do limiar era global

**"Zero cortes falsos" acima está errado, e o erro era da medida.** A propriedade
verificada era "nenhum pedaço estreito novo", e as duas metades de uma figurina
partida ao meio são largas demais para caírem nela. O separador partia glifos
inteiros desde o início e a validação não tinha como ver.

O gatilho: o limiar de candidato a corte era `mediana_da_página * 1.6`. Estes
livros misturam tamanhos de fonte — a linha principal da partida é maior que o
texto das variantes. Medido na página 0108: mediana de 21 px na linha principal
contra 17 px nas variantes, com a mediana da página em 17. A figurina de cavalo,
de 32 px, passava do limiar e era partida no vale interno do contorno, e
`1.d4 Nf6` saía `1.d4 N□f6`.

A referência passou a ser **a mediana da linha, nunca abaixo da global**
(`BoxService._largura_de_referencia`). O piso não é enfeite: a mediana de uma
linha mede também quais caracteres calharam de cair nela, e uma linha cheia de
`i`, `l` e pontuação tem mediana pequena sem ser fonte pequena. A mediana da
linha pura leva os cortes falsos de 221 para 182 mas *piora* a página 0020
(2 → 9); com o piso caem para 162 e a 0020 melhora (2 → 1).

Revalidação nas **páginas rotuladas à mão** — 9 hoje (7 do Kasparov + 2 do
Aagaard, 9.369 caracteres) — em vez do proxy de "boxes largos". Com o rótulo dá
para separar corte bom de corte falso, que é o que faltava.

> **As digitalizações não estão no repositório** — `ilovepdf_pages-to-jpg/` é
> material com direitos autorais e fica ignorada, para treino local só. Num clone
> limpo sobram 2 páginas com imagem (as do Aagaard), não 9, e os números abaixo
> **não** serão reproduzidos. `medir_paginas.py` e `calibrar_modelo.py` usam o
> conjunto que encontrarem, então rodam mesmo assim — só medem menos.

| | recall | precisão | F1 | cortes bons | cortes falsos |
|---|---:|---:|---:|---:|---:|
| separador desligado | 94,1% | **93,0%** | **93,5** | — | — |
| escala global (antes) | 93,8% | 87,5% | 90,5 | 80 | 257 |
| escala local (agora) | 94,0% | 88,5% | 91,2 | 73 | **182** |

**Precisão e recall dizem coisas diferentes aqui.** Partir um glifo quase não
mexe no recall — o pedaço da esquerda ainda casa com o rótulo — mas despeja um
caractere inventado no texto a cada corte. Medir só por recall foi o segundo
motivo de o defeito ter passado.

**O que a revalidação mostrou, e não era o esperado: o separador não se paga em
nenhuma das páginas.** Desligado ele dá 93,5 de F1 contra 91,2 com a correção.
Os cortes falsos ainda superam os bons por 2,5:1. A correção é real — 257 → 182
cortes falsos, e o `N□f6` do relato sumiu — mas ela reduz um prejuízo, não o
inverte.

A razão é que o critério não tem como decidir. Medidos os dois grupos na página
0108, o vale de colagem e o vale interno de glifo são indistinguíveis:

| | largura do vale | fundo (% do pico) | menor pedaço (medianas) |
|---|---:|---:|---:|
| colagem de verdade | 7 colunas | 13,3% | 0,62 |
| glifo inteiro (`♘`, `♖`, `m`) | 7 colunas | 10,5% | 0,62 |

Também foram medidos e descartados: largura do pai, número de faixas de tinta na
coluna de corte e posição vertical da ponte — todos com as duas populações
sobrepostas. As medidas originais da F1.5 (`♞e5` com vale de 10 colunas contra
`♛` com 0) valem para a figurina **colada em texto figurino**; onde a figurina
aparece isolada entre texto normal, a folga desaparece.

Consequência prática: `separar_colados` continua ligado por padrão, mas o número
que manda é o da página. Para material como estes livros, desligar rende mais que
qualquer ajuste do critério — e um separador que se pague vai precisar de outra
coisa que não a projeção de tinta (componentes conexos, ou o próprio
classificador pontuando o corte).

Cobertura: `tests/test_f15_preprocess.py`, 26 testes, incluindo a página 0108 no
conjunto de validação. `core/avaliacao_pagina.py` mede página contra `.box`
rotulado e é reusável pela F1.7.

### F1.5b — O separador parte figurina em negrito — CONCLUÍDA

**Concluída em 2026-08-04.** A segunda das duas saídas previstas acima — "o próprio
classificador pontuando o corte" — foi a que funcionou. A primeira (componentes conexos)
foi descartada sem escrever código: `findContours` roda com `RETR_EXTERNAL`, então cada
box **já é** um componente conexo, e glifo colado é colado de verdade. Não havia o que
separar por ali.

O árbitro é o classificador comparando a pontuação do box inteiro com a **menor** das
partes. A menor, e não a média: basta um pedaço sem sentido para o corte ter sido
estrago. Nos 255 candidatos que a projeção propõe nas 9 páginas rotuladas, separados pelo
que o rótulo à mão diz:

| grupo (pelo rótulo) | inteiro | menor parte | partes > inteiro |
|---|---:|---:|---:|
| colagem de verdade (n=73) | 0,604 | 0,857 | 57,5% |
| glifo inteiro (n=182) | 1,000 | 0,481 | 6,6% |

**A F1.9 é o que tornou isto possível, e não era óbvio.** A F1.1 tinha registrado que o
modelo erra com confiança 1,000, o que sugeria uma pontuação inútil para decidir qualquer
coisa. A F1.9 mediu melhor: a AUROC entre certo e errado é 0,89 — a confiança **ordena**
bem, o que ela não faz é ter escala honesta. Ordenar é tudo de que o árbitro precisa.

| modo | recall | precisão | F1 | cortes bons | cortes falsos |
|---|---:|---:|---:|---:|---:|
| desligado | 94,1% | 93,0% | 93,5 | — | — |
| escala global (pré-F1.7) | 93,8% | 87,5% | 90,5 | 80 | 257 |
| sem árbitro (F1.7) | 94,0% | 88,5% | 91,2 | 73 | 182 |
| **com árbitro** | 94,5% | 93,0% | **93,8** | 23 | **2** |

**A margem exigida é 0,30, e quem decidiu foi o F1 da página, não a contagem de cortes.**
As duas medidas discordam: a margem 0,00 rende mais cortes bons (42 contra 23) e parecia
melhor, mas o que chega ao texto diz outra coisa — 93,7 contra 93,8. Varrendo a margem, o
F1 tem máximo em 0,30 e desce para 93,5 em 1,00, que é exatamente o valor de "desligado".
**Esse pico no meio é o que prova que o árbitro faz algo**: se fosse só uma maneira lenta
de cortar menos, a curva seria monótona.

**O tamanho do ganho, dito sem enfeite: +0,3 de F1 sobre não separar.** O que mudou de
fato foi o *sinal* — manter o separador ligado custava 2,3 pontos e agora rende 0,3. A
segmentação por projeção continua fraca para este material; o árbitro a torna inofensiva
e levemente positiva, não a conserta. Os cortes falsos caíram de 182 para 2.

**O padrão de `separar_colados` deixou de ser `True`.** Passou a ser `"auto"`: separa só
se houver árbitro. Com `True` como padrão, qualquer chamador sem modelo carregado ficaria
com a única configuração que a medição reprova — e nada na saída denunciaria, porque os
boxes continuariam saindo, só que partidos no lugar errado. `True` segue disponível para
reproduzir as medições da F1.5.

O `medir_paginas.py` passou a chamar `dividir_glifos_colados` de verdade nos modos `local`
e `arbitrado`, em vez da cópia que mantinha. Era uma cópia divergente que deixou a F1.5
medir uma coisa e a aplicação fazer outra.

#### Re-medida em 2026-08-06: o árbitro quase não se paga mais

`medir_paginas.py` sobre o modelo de 119 classes e as 10 páginas rotuladas — a tabela
acima foi medida com 103 classes e 9 páginas:

| modo | recall | precisão | F1 | cortes bons | cortes falsos |
|---|---:|---:|---:|---:|---:|
| desligado | 94,4% | 93,7% | 94,1 | — | — |
| escala global | 94,3% | 88,8% | 91,5 | 86 | 263 |
| escala local, sem árbitro | 94,4% | 89,8% | 92,1 | 78 | 184 |
| **com árbitro** (o de hoje) | 94,6% | 93,7% | **94,2** | 13 | 4 |

O pipeline foi de 93,8 para **94,2 de F1**. Como o conjunto rotulado mudou de 9 para 10
páginas, a comparação é indicativa e não controlada — mas as duas colunas do meio, que não
dependem do classificador para decidir o corte, ficaram praticamente onde estavam (91,5 e
92,1 contra 90,5 e 91,2), o que sugere que o ganho é do modelo e não da página nova.

**O que encolheu foi a vantagem do árbitro: de +0,3 para +0,1 sobre não separar.** Os
cortes bons caíram de 23 para 13 e os falsos subiram de 2 para 4. Por página ele ganha em
6, perde em 3 e empata em 1, sempre por margens de ±0,4. O separador está hoje
praticamente inerte: a conclusão da F1.5b — inofensivo e levemente positivo — continua
certa, com o "levemente" mais fino ainda.

**A explicação são as 16 classes novas, e elas foram intencionais** — confirmado pelo dono
dos dados em 2026-08-06 e registrado na SPEC §5.2, item 6. Seis são casa de xadrez
(`ligature_e4`, `ligature_f6`, …): um box de dois caracteres colados passou a ter classe
própria, então o classificador pontua alto o box **inteiro** e o árbitro recusa o corte.
Ou seja, o separador não regrediu — ele foi **substituído**, e por algo que resolve o caso
que ele nunca resolveu (a colagem sem vale largo o bastante para cortar com segurança, que
a F1.5 mediu como indistinguível do vale interno de glifo).

Isso torna **desligar `separar_colados` uma decisão defensável**, e é a primeira vez que
ela é: o modo `off` desta mesma tabela dá 94,1 contra 94,2, então o separador cobra uma
passada de projeção de tinta e uma segunda classificação por candidato para render 0,1
ponto. Não desliguei — o padrão `"auto"` da F1.5b não está errado, está caro, e a troca é
de quem paga o processamento.

**A atribuição, essa não dá mais para medir.** Separar o efeito das classes novas do
efeito da página rotulada nova exigiria rodar o modelo de 103 classes nas mesmas 10
páginas, e os pesos dele foram sobrescritos pelos dois retreinos da madrugada, sem cópia.
A F1.3 guardou `custom_model_2026-08-03_antes_f13.pth` antes de trocar de modelo; estes
retreinos não guardaram nada. Vale como regra para o próximo: **copiar o `.pth` antes de
retreinar**, senão o número que o ROADMAP cita deixa de ter modelo que o produza.

A pior página continua sendo a 0020 (88,1 de F1 contra 94,2 do conjunto), como na F1.5.

Cobertura: `tests/test_f15b_arbitro.py`, 15 testes.

### F1.7 — Validar notação contra as regras do xadrez — CONCLUÍDA

Ideia trazida do [DocuVision-AI](https://github.com/betulkizilkaya/DocuVision-AI)
(MIT, projeto acadêmico), avaliado em 2026-08-03. Era o único item realmente aplicável
daquele projeto ao nosso.

Eles usam `python-chess` para pontuar qual bloco de texto da página é a notação. Para
nós o uso mais forte é outro: **desambiguar caracteres de baixa confiança**. Se a rede
hesita entre dois candidatos, o tabuleiro decide qual é possível.

Numa posição típica (após 1.e4 e5 2.Nf3 Nc6) há **27 lances legais**, contra centenas de
notações que o OCR poderia produzir. A legalidade descarta a maioria esmagadora das
leituras erradas — de graça, sem treino.

Não resolve tudo: `Nbd2` e `Nfd2` podem ser ambos legais na mesma posição. A legalidade
**estreita** o conjunto, nem sempre decide.

**Não copiar o código deles.** O `fix_chess_moves` do DocuVision é o oposto do que
queremos:

```python
text = re.sub(r"2d3", "Bd3", text)
text = re.sub(r"2e7", "Ne7", text)
```

São remendos decorados para os erros de um corpus específico — frágeis e intransferíveis.
A versão principiada é justamente o teste de legalidade.

**Concluída em 2026-08-04.** `core/notacao.py`, com item de menu
**Ferramentas → Validar notação de xadrez**. A dependência custa 1,3 MB instalados, e
não os 5,9 MB que este item estimava.

#### Duas afirmações deste item não sobreviveram à medição

**1. A tabela de exemplos estava errada.** Ela dizia "verificado aqui", mas não tinha
sido rodada: na posição citada (`1.e4 e5 2.Nf3 Nc6`) os **dois** lados de todos os
quatro pares são ilegais — `Nf3` porque o cavalo já está em f3, `Bb4` porque nenhum
bispo alcança b4. O princípio vale; os exemplos é que não. Nas posições certas:

| Posição | Par | Resultado |
|---|---|---|
| `1.e4 e5` | `Nf3` / `Nf8` | só `Nf3` |
| `1.e4 e5` | `Nf3` / `Rf3` | só `Nf3` |
| `1.e4 e5` | `Qh5` / `Qh9` | só `Qh5` |
| `1.d4 Nf6 2.c4 e6 3.Nc3` | `Bb4` / `Bh4` | só `Bb4` |

**2. A dependência da F3.2 não existe na prática.** O item dizia "sem saber quais
caracteres são duvidosos, não há o que desambiguar". Medindo a confiança na página
real, contra o `.box` rotulado à mão:

| | Amostras | Confiança mediana |
|---|---:|---:|
| Caracteres **certos** | 1.219 | 1,000 |
| Caracteres **errados** | 163 | **1,000** |

O modelo é superconfiante: só **19%** dos erros ficam abaixo de 0,9, e um corte em 0,9
já leva junto 3% dos acertos. A ponderação por confiança ficou no código — é o desenho
certo quando a confiança significa alguma coisa — mas hoje é praticamente inerte.
**Quem faz o trabalho é a legalidade, sozinha.** Calibrar o modelo é o que destravaria
essa parte, e virou item novo (F1.9).

#### O que a página real exigiu, e não estava previsto

**Espaço não dá para inferir só pela lacuna.** Os algarismos desta fonte têm avanço
tabular: a lacuna mediana depois de `'1'` é **10 px**, contra 1–2 px depois de letras.
Medido nos 1.404 boxes da página:

| Limiar | Dígitos partidos ("15" vira "1 5") | Palavras coladas |
|---|---:|---|
| 0,5× largura mediana | 71 | nenhuma |
| 0,8× | 38 | várias (`2.c4c53.d5`) |
| 1,2× | 23 | muitas |

As distribuições se sobrepõem, então nenhum limiar único resolve. A saída foi um limiar
normal mais uma segunda passada que **só junta palavras inteiramente numéricas** —
"20 1 0" vira "2010" e "Game 85" continua com o espaço.

**Reconhecer o lance por expressão regular quebra no primeiro caractere errado.** A
primeira versão casava a forma exata do SAN. Com o `□` que o classificador insere em
`N□f6` o padrão não casa nada, o lance some, e a análise da página real terminava com
**1 lance lido**. Como todo lance vai ser confrontado com os lances legais de qualquer
jeito, o pedaço passou a ir inteiro e é a legalidade que decide — com uma peneira
barata (tamanho ≤ 8, inicial plausível, contém uma casa) para não confundir prosa com
lance.

**Metade do texto destes livros são variantes.** "12.Re1 Qa5 12...Ra6; 12...Ra7;
12...Nb6 13.Qc2" — lidas em sequência, todas menos a primeira são ilegais. Cada lance
jogado guarda a posição de antes, e um número que já passou rebobina para lá.

Mas depois da variante o texto volta à principal **sem marcar**: de fora, "13." tanto
continua a variante quanto retoma a linha principal. Em vez de adivinhar, o analisador
carrega todas as posições plausíveis e deixa o lance seguinte desempatar. Quando mais
de uma sobrevive, ele se declara incerto e **não corrige nada** — só reporta. Foi isso
que eliminou a única correção falsa que a primeira versão produzia (`e6` virando `e5`).

#### Quanto rende

Sobre 25 páginas do livro, com o modelo retreinado na F1.3:

| | Com o divisor de glifos | Sem ele |
|---|---:|---:|
| Lances lidos | 491 | 524 |
| Já legais | 77,8% | **93,5%** |
| **Corrigidos pela legalidade** | **15,7%** | 0,8% |
| Ambíguos (reportados, não corrigidos) | 5,5% | 5,2% |
| Sem solução | 1,0% | 0,6% |

A coluna da esquerda é o pipeline com o separador de glifos **como estava em
2026-08-04**, antes do conserto; a da direita, com ele desligado. A leitura honesta é
que **quase todo o ganho medido da F1.7 era conserto de estrago da F1.5**: com a
entrada limpa, 93,5% dos lances já são legais e sobra pouco para corrigir.

Sinal de que as correções estão certas, sem gabarito: se uma estivesse errada, o
tabuleiro divergiria e o lance seguinte falharia. Depois de cada correção vêm **3 lances
legais (mediana)**, e só 15 das 77 são seguidas de zero.

Isolando o mecanismo da qualidade atual do OCR — três partidas reais, caracteres
corrompidos de propósito com as confusões que o modelo comete, 12 sementes:

| Corrupção | Recuperados | Corrigiu errado | Não decidiu | Invisível |
|---|---:|---:|---:|---:|
| 5% | 34,3% | 6,0% | 43% | 16% |
| 20% | 36,8% | 3,4% | 45% | 15% |
| 50% | 31,8% | 4,7% | 48% | 15% |

Ou seja: a legalidade recupera **cerca de um terço** do estrago, erra em ~5% e se
declara indecisa no resto. Entre as correções que ela decide fazer, **87% estão certas**.
"Invisível" são as corrupções que por acaso produzem outro lance legal — aí não há o que
perceber.

#### Um defeito da F1.5 apareceu no caminho

`BoxService.dividir_glifos_colados` compara a largura do box com a mediana da **página
inteira**. Quando a página mistura tamanhos — e nestes livros a linha principal é maior e
em negrito —, os caracteres em negrito passam do limite e viram candidatos a corte. O `N`
em negrito tem um vale interno largo e é partido em dois; o segundo pedaço vira `□`.
Medido nesta página, contra o gabarito:

| | Acerto do OCR | Boxes |
|---|---:|---:|
| `separar_colados=True` | 83,3% | 1.487 (102 espúrios) |
| `separar_colados=False` | **88,2%** | 1.385 |

A validação da F1.5 não pegou porque a propriedade verificada era "zero pedaços estreitos
novos", e as duas metades de um `N` em negrito são largas o bastante. Está registrado como
item próprio, fora desta fase.

#### O que fica em aberto

- Distinguir linha principal de variante resolveria os 5,2% ambíguos. O sinal existe:
  medida a densidade de tinta por palavra, a principal fica em 0,52–0,64 e as variantes
  em 0,34–0,52 — separa, mas com sobreposição, e depende da imagem da página.
- Caractere **faltando** vira sugestão, não edição: não há box para apontar. Só o caso
  inverso (box sobrando) vira edição automática, esvaziando o caractere.

Cobertura: `tests/test_f17_notacao.py`, 28 testes.

### F1.8 — Mascarar diagramas antes de detectar boxes — CONCLUÍDA

Também sugerido pela leitura do DocuVision (`mask_board_regions`). Hoje só tratamos
diagramas em PDF de **texto** (`is_block_a_diagram`); em página escaneada, o tabuleiro
vira milhares de boxes de lixo — o pipeline de lote apenas descarta boxes acima de 150 px,
o que não pega as casas individuais.

Detectar a região do tabuleiro e mascará-la antes da detecção de contornos evita o
problema na origem. Não é preciso YOLO (que o DocuVision usa): análise de contornos e
detecção de linhas com Hough bastam para uma grade 8×8.

**Concluída em 2026-08-04, e o problema era muito menor do que o descrito acima.**

**O tabuleiro não vira milhares de boxes.** `findContours` roda com `RETR_EXTERNAL`, e o
tabuleiro destes livros tem moldura preta fechada: as 64 casas e as peças são contornos
*filhos* e nunca são devolvidos. Medido em 8 páginas com diagrama, o tabuleiro sai como
**um** box de ~479×478 — um, não mil:

| página | boxes na página | boxes dentro do tabuleiro |
|---|---:|---:|
| 0144 | 1.609 | **1** |
| 0151 | 1.548 | **1** |
| 0109 | 1.622 | **1** |

E esse box não atrapalha o que se temia: a detecção de colunas da F1.6 devolve o mesmo
número de faixas com ele e sem ele, nas 8 páginas, e nenhuma delas ganha elemento
transversal por causa dele.

Por isso **não há detecção de grade nem transformada de Hough** aqui. Seria maquinário
para um problema que não existe neste formato — e maquinário que teria de ser mantido e
que erra em página torta. O que sobra é um punhado de blocos grandes demais para serem
caractere, e um limiar de tamanho resolve:

`BoxService.descartar_blocos_nao_texto` descarta o contorno que passa de **4× a altura
mediana de caractere nos dois eixos**. Nos dois eixos porque um travessão é largo e
legítimo. Relativo, e não os `w > 150 or h > 150` do pipeline de lote, que dependem do DPI:
a 600 dpi aquilo corta letra de verdade, a 150 dpi deixa o tabuleiro passar.

Medido nas 9 páginas rotuladas:

| | boxes | espúrios | casados com rótulo |
|---|---:|---:|---:|
| sem o descarte | 9.540 | 336 | 9.204 |
| com o descarte | 9.521 | **317** | **9.204** |

19 boxes descartados, 19 espúrios a menos, e **nenhum** caractere de verdade perdido.

**O descarte acontece depois do `merge_vertical_boxes`, e a ordem foi medida.** O box do
diagrama absorve os respingos à volta dele durante o merge — borda serrilhada da
digitalização, legenda encostada — e descartá-lo depois leva esse lixo junto. Descartando
antes, os respingos sobram soltos: na página 0108 os espúrios iam de 11 para **29**, pior
que não fazer nada. `test_descarte_acontece_depois_do_merge` fixa a ordem.

Cobertura: `tests/test_f15_preprocess.py`, 6 testes novos (32 no total do arquivo).

### F1.9 — Calibrar a confiança do modelo — CONCLUÍDA

Saiu da medição da F1.7: a confiança mediana de um caractere **errado** é 1,000, igual à
de um certo. O `softmax` de uma CNN treinada com augmentation pesada é conhecidamente
superconfiante, e aqui isso custa em três lugares — a cor por confiança da F3.2 pinta de
verde o que está errado, o filtro "só pendentes" da F3.3 não mostra os erros, e a
ponderação por confiança da F1.7 fica inerte.

*Temperature scaling* sobre o conjunto de validação que a F1.3 já monta resolve com um
único parâmetro e sem retreinar. Medida a usar: erro de calibração esperado antes e
depois, e a fração de erros que um corte em 0,9 passa a pegar.

**Concluída em 2026-08-04.** `core/calibracao.py`, `calibrar_modelo.py`, e a temperatura
gravada em `model_meta.json` e aplicada por `NeuralPredictor.predict`. Duas coisas do
plano acima estavam erradas, e as duas foram medidas antes de mudar o desenho.

#### O conjunto de validação é o lugar errado para calibrar

O split que a F1.3 monta sai de `training_data`, que é recorte já segmentado e limpo.
Medido ali com o modelo em uso:

| | acurácia | ECE | confiança mediana de um erro |
|---|---:|---:|---:|
| split de validação (19.317) | 99,93% | **0,0003** | 0,72 |
| split de teste (6.436) | 99,89% | 0,0010 | 0,93 |
| 9 páginas reais (9.274) | 95,32% | **0,0315** | 0,85 |

Não há o que calibrar no split — a temperatura ajustada ali dá **0,995**, ou seja, não
faz nada. A miscalibração é um efeito de **mudança de distribuição**, não de `softmax`
quente: a página traz recorte mal segmentado, glifo colado e fonte não vista, e é lá que
a confiança é consumida. A temperatura passou a ser ajustada nas páginas rotuladas, com
validação **leave-one-page-out** — ajustar e medir nas mesmas 8 páginas daria um número
bonito e falso.

#### Calibrar não faz o filtro achar mais erro

A temperatura divide os logits: muda o **valor** da confiança, não a **ordem** entre as
amostras. Como triagem é "olhe os N mais duvidosos", o que ela consome é a ordem. A AUROC
entre certo e errado confirma:

| T | 0,5 | 1,0 | 2,0 | 4,0 | 8,0 |
|---|---:|---:|---:|---:|---:|
| AUROC | 0,860 | 0,862 | 0,868 | 0,878 | 0,876 |

Então o ganho de "pegar mais erros" que aparece ao subir a temperatura é exatamente o que
se obteria mexendo no limiar com T = 1. **A promessa de que calibrar destrava a F3.3 não
se sustenta** — o que decide onde pôr o corte é a curva de triagem, não o ECE:

| corte | da página revisada | dos erros achados | erros que escapam |
|---:|---:|---:|---:|
| 0,50 | 0,8% | 16,1% | 364 |
| 0,70 | 2,2% | 38,7% | 266 |
| **0,90** (o de hoje) | **4,0%** | **52,5%** | 206 |
| 0,999 | 13,6% | 70,7% | 127 |

O `LIMIAR_ALTO = 0,90` de `ui/confidence.py` já está num ponto defensável: revisando 4%
da página o revisor acha metade dos erros. Subir para 0,999 troca +10 pontos de esforço
por +18 de erros achados. Ficou como está — a escolha é de quem revisa, e agora está
medida.

#### O que a calibração entrega

O número exibido passa a ser honesto, que importa porque a UI mostra "95%" para uma
pessoa decidir. Com T = **1,968**:

| | ECE | NLL | confiança média | AUROC |
|---|---:|---:|---:|---:|
| T = 1 | 0,0315 | 0,8879 | 0,9847 | 0,8620 |
| T = 1,968 | **0,0222** | **0,4837** | 0,9669 | 0,8673 |

Leave-one-page-out, que é o número que vale: ECE de **0,0349 → 0,0307**, com 6 das 9
páginas melhorando. Modesto e real. A leitura não muda em nenhum caractere — dividir os
logits não muda quem vence.

Escolha de critério: a temperatura é ajustada minimizando **ECE**, não NLL. A NLL é
dominada por poucos erros catastroficamente confiantes e pede uma temperatura bem mais
alta; amaciar todo o resto para acomodá-los piora o ECE. O que se quer calibrar é o
número exibido.

Retreinar **zera** a temperatura no metadado, de propósito: ela é ajustada para um
conjunto de pesos, e herdá-la aplicaria uma correção medida sobre outra rede.
`python calibrar_modelo.py --gravar` reajusta.

#### Re-medida em 2026-08-06, e a curva de triagem se moveu

O modelo foi retreinado naquele dia e passou de 103 para **119 classes** — entraram 16
pastas de ligadura, várias delas casa de xadrez (`ligature_e4`, `ligature_f2`,
`ligature_f6`) — **intencionais**, e o porquê está na SPEC §5.2, item 6. O conjunto
rotulado também cresceu: **10 páginas, 10.435 caracteres** (8 do Kasparov + 2 do Aagaard).

`calibrar_modelo.py --gravar` sobre o par novo:

| | acima (103 classes, 9 páginas) | 2026-08-06 (119 classes, 10 páginas) |
|---|---:|---:|
| acurácia na página real | 95,32% | **96,04%** |
| T ajustado (critério ECE) | 1,968 | **2,122** |
| ECE: T=1 → calibrado | 0,0315 → 0,0222 | 0,0311 → **0,0140** |
| NLL: T=1 → calibrado | 0,8879 → 0,4837 | 0,9537 → 0,4776 |
| AUROC (T=1) | 0,8620 | 0,8589 |
| Leave-one-page-out | 0,0349 → 0,0307 (6 de 9 melhoram) | 0,0327 → **0,0223** (10 de 10) |

A calibração rende bem mais do que rendia: a melhora de ECE fora da amostra triplicou e
nenhuma página piorou. As duas conclusões estruturais da fase continuam de pé — a
temperatura não mexe na ordenação (AUROC de 0,853 a 0,875 entre T=0,5 e T=8) e o que ela
entrega é o número exibido, não a leitura, que não muda em nenhum caractere.

**Uma ressalva de leitura que o número anterior não tinha:** o T de cada dobra saiu
idêntico (2,122) nas dez. Cada dobra retém ~90% dos caracteres e o ótimo não se move, o
que faz do leave-one-page-out aqui um teste fraco — mede estabilidade da temperatura, não
generalização para página nova.

**O que se moveu foi a triagem, e ela desmente o parágrafo do `LIMIAR_ALTO` acima.**

| corte | da página revisada | dos erros achados | erros que escapam |
|---:|---:|---:|---:|
| 0,70 | 1,1% | 22,3% | 321 |
| **0,90** (o de `ui/confidence.py`) | **2,4%** | **39,7%** | 249 |
| 0,99 | 5,4% | 54,7% | 187 |
| 0,999 | 16,4% | 70,9% | 120 |

O ponto registrado acima era 4,0% da página achando 52,5% dos erros. Neste modelo o mesmo
0,90 revisa 2,4% e acha **39,7%** — para achar metade dos erros o corte tem de ser 0,99.
O `LIMIAR_ALTO` **não foi mexido**: a escolha é de quem revisa, e trocá-lo sem medir o
custo real de revisão seria substituir um número medido por um palpite. Mas quem decidir
agora decide sobre esta tabela, não sobre a de cima.

**O F1 do pipeline foi re-medido junto, e está na F1.5b:** 93,8 → **94,2**. Vale ler os
dois lados — a acurácia de caractere subiu 0,7 ponto e o F1 da página subiu 0,4, mas a
vantagem do árbitro do corte caiu de +0,3 para +0,1, o que a acurácia sozinha não
mostraria.

**Dois detalhes operacionais que custaram confusão ao medir.** O `appy.py` aberto
reescreveu o par duas vezes em sete minutos (01:47:30 e 01:54:13), então um par conferido
como casado deixou de estar casado sem ninguém tocar em nada — a trava da F7.3 protege da
leitura errada, não da surpresa. E a temperatura gravada só passa a valer quando a
aplicação **recarrega** o modelo: a janela que estava aberta seguiu com o predictor em
memória de antes.

Cobertura: `tests/test_f19_calibracao.py`, 21 testes.

### F1.6 — Ordenação de leitura ignora colunas — CONCLUÍDA

`sort_boxes_reading_order` (`box_service.py:36`) agrupava por sobreposição vertical.
Livros de xadrez são fortemente diagramados, muitos em duas colunas. O algoritmo
intercalava as colunas linha a linha, produzindo texto embaralhado — numa página real do
Kasparov a partida saltava do lance 19 para o 43 e voltava para o 20.

O DocuVision confirma que o problema é real, mas a solução dele não vale a cópia: mede a
brancura de uma faixa fixa (42%–58% da largura) e assume duas colunas iguais. Um perfil de
projeção vertical acha as calhas em qualquer posição e com qualquer número de colunas.

**Concluída em 2026-08-03** (`f2b3990`). Esta seção ficou sem a marca até 2026-08-08, e o
resto dela é o registro que faltava.

**O perfil é dos boxes, não dos pixels.** `detectar_colunas` projeta a ocupação das caixas
no eixo X e procura vãos sem conteúdo nenhum. O vão que interessa é onde não há
*caractere*, e medir assim funciona igual em página escaneada e em imagem já limpa — o
perfil de tinta veria a trama de fundo e a sujeira de borda.

**O limiar é relativo à largura mediana de caractere** (`3x`, com piso de 2% da largura da
página e de 4 px), e não absoluto: uma calha de verdade é muito mais larga que o espaço
entre palavras. É o que separa "duas colunas" de "um parágrafo justificado com vãos
grandes", e o teste que trava isso monta as duas situações.

**Elemento que atravessa a calha não pertence a coluna nenhuma.** Título, diagrama largo,
tarja de nome: viram separador horizontal — o que está acima é lido coluna a coluna,
depois vem ele, depois o que está abaixo. Sem essa regra o título entraria no meio de uma
das colunas e levaria a outra metade da página junto.

**Uma pilha de texto girado é um elemento só** (F8.1, que veio depois e mexeu aqui). Cada
letra dela cai numa linha de texto diferente; sem o tratamento, o rótulo vertical ao lado
do diagrama entrava letra a letra no meio de seis linhas do parágrafo vizinho.
`_ordenar_com_pilhas` troca a pilha por uma caixa que a representa, ordena a página com o
algoritmo de sempre e desfaz a troca no fim — a pilha entra pelo lugar que ocupa, sem que
a ordem precise saber que ela existe.

Medido na página 0021 do Kasparov, que é de duas colunas: **9 saltos entre colunas antes,
1 depois** — e 1 é o certo, que é a passagem da coluna da esquerda para a da direita.

Cobertura: `tests/test_f16_colunas.py`, 14 testes. O último roda sobre a página real e é
pulado em clone sem as digitalizações.

---

## F2 — Saída de PDF

### F2.1 — O PDF de saída é rasterizado — CONCLUÍDA

`neural_pdf_processor.py:104-118` converte cada página em imagem RGB, desenha os
símbolos por cima e salva tudo como PDF de imagens.

Consequências:

- **texto selecionável some** — inclusive o texto que estava perfeito no original
- **busca deixa de funcionar** no arquivo inteiro
- **tamanho explode** (páginas viram bitmaps)
- não há **camada de texto** — o resultado não é um PDF de OCR, é um álbum de fotos

Para uma ferramenta cujo propósito é OCR, essa é a lacuna estrutural mais séria.

**Concluída em 2026-08-03.** `core/searchable_pdf.py` escreve uma camada de texto
invisível (`render_mode=3`) sobre a página original **preservada**.
`core/neural_pdf_processor.py`, que rasterizava, foi removido.

Verificado com uma página real do Kasparov (Benko Gambit, pág. 11) e o modelo neural
de verdade:

| | Entrada | Saída |
|---|---:|---:|
| Tamanho | 661 KB | 1153 KB |
| Caracteres extraíveis | **0** | **3025** |
| Imagem original | — | preservada |

2379 boxes detectados, 2376 reconhecidos, 16 s de processamento.

Três modos: `searchable` (só a camada, padrão), `replace` (desenha as peças
reconhecidas por cima do original, sem rasterizar) e `both`.

Decisões que vieram da implementação:

- **Páginas que já têm texto são puladas.** Escrever OCR por cima duplicaria o
  conteúdo e a busca devolveria cada trecho duas vezes. É a heurística `is_scanned`
  que a SPEC §4.1 previa.
- **Subset da fonte.** A `seguisym.ttf` tem 2,3 MB e era embutida inteira. Medido em
  200 inserções: 1342 KB sem subset contra 70 KB com. Na página real, levou a saída de
  2416 KB para 1153 KB.
- **O PDF só é gravado no fim**, então cancelar não deixa arquivo pela metade.

**Pendência honesta:** o crescimento de 661 KB para 1153 KB é inteiramente a camada de
texto — verificado que abrir e salvar sem mexer mantém 661 KB. São ~200 bytes por
caractere, porque cada `insert_text` gera um bloco gráfico completo. Agrupar caracteres
em linhas cortaria isso bastante, mas depende da ordem de leitura da F1.6.

Cobertura: `tests/test_f21_pdf_pesquisavel.py`, 14 testes.

**O que esta fase não resolve:** a *qualidade* do reconhecimento. Na página real saiu
"The D[]namic B[]do Gambit" em vez de "The Dynamic Benko Gambit" — é o problema da F1
(desbalanceamento, sem split de validação), não da F2. A F2.1 garante que o texto
existe e é pesquisável; a F1 é que o fará estar certo.

### F2.2 — Dependência do Poppler é desnecessária — CONCLUÍDA

`pdf_service.py` usa `pdf2image`, que exige o binário externo **Poppler** no PATH —
fonte recorrente de erro no Windows (o próprio código tem tratamento especial para
isso em `main_window.py:980-986`).

Mas o projeto **já depende de PyMuPDF**, que renderiza páginas nativamente:

```python
pix = page.get_pixmap(dpi=300)
```

Unificar em PyMuPDF elimina uma dependência nativa e simplifica a instalação.

**Concluída em 2026-08-04.** `pdf2image` saiu do `requirements.txt` e do código; o
`pdf_service.py` renderiza com `fitz`. A mensagem de erro específica de Poppler em
`main_window.py` virou código morto e foi removida — o que sobrar ali agora é defeito
no arquivo, e a mensagem do próprio PyMuPDF diz mais que um texto genérico.

**A escala teve de ser preservada, e isso não era detalhe.** O
`pdf2image.convert_from_bytes` usava 200 dpi por omissão, e os limiares da F1.5 são
relativos à largura mediana de caractere medida nessa escala. Renderizar noutro dpi
mudaria todos eles sem erro nenhum aparecer. Conferido contra o Poppler, na mesma página
real convertida para PDF:

| | tamanho | largura mediana de caractere | boxes |
|---|---|---:|---:|
| Poppler (antes) | 1167×1836 | 11 px | 1.359 |
| PyMuPDF (agora) | 1167×1836 | **11 px** | 1.371 |

Diferença média de 4,4 níveis de cinza por pixel, nas bordas dos glifos — dois
rasterizadores não fazem anti-aliasing igual. Os 12 boxes de diferença (0,9%) saem daí.
O número que a segmentação consome, a mediana, é o mesmo.

**O documento é aberto a cada chamada, e isso é de propósito.** `load_page` roda dentro
da thread de trabalho da F4.1 ao mesmo tempo que a UI pode pedir outra página; um
`fitz.Document` guardado no serviço seria estado compartilhado entre as duas, e documento
do PyMuPDF não é seguro para acesso concorrente. Abrir a partir dos bytes é barato — o
PyMuPDF lê o xref sob demanda. Há teste com 12 threads simultâneas e outro que reprova se
o serviço voltar a guardar um `Document`.

De quebra, PDF protegido por senha agora diz o motivo: antes abria, devolvia 0 páginas e
o erro saía como "o PDF não tem páginas".

Cobertura: `tests/test_f22_pdf_nativo.py`, 17 testes.

### F2.3 — Faltam relatório e dry-run — CONCLUÍDA

A spec v1.0 pede (RF-06 e RNF-04) e não foram implementados:

- relatório JSON/CSV das substituições (página, bbox, fonte, antes, depois, avisos)
- modo dry-run que detecta e reporta sem alterar o arquivo

Num conversor que reescreve PDFs, dry-run não é conforto — é a única forma de conferir
antes de destruir.

**Concluída em 2026-08-04.** `core/relatorio_pdf.py` e `analisar_substituicao`, que
devolve o relatório; `substitute_chess_glyphs` continua com a assinatura antiga por cima
dela. A UI pergunta "simular antes?" antes de escolher o arquivo de saída.

**Dry-run e conversão são a mesma travessia.** É isso que dá sentido à conferência: mesma
detecção de diagrama, mesmos avisos, mesmo cálculo de encolhimento de corpo — a simulação
só não escreve. Se as duas divergissem, conferir a simulação não diria nada sobre a
conversão, e `test_simular_e_converter_veem_a_mesma_coisa` reprova se isso acontecer. Em
dry-run nem o `insert_font` roda, porque ele já altera o documento.

Os relatórios saem ao lado do PDF, e a simulação usa `_simulacao` em vez de `_relatorio`
no nome para os dois poderem conviver e serem comparados. O CSV vai com BOM: sem ele o
Excel no Windows lê UTF-8 como cp1252 e transforma os símbolos de peça em lixo.

Além dos avisos que a SPEC pede, o relatório registra os **blocos que a heurística de
diagrama ignorou**. É a heurística com mais chance de errar, e descartar o bloco em
silêncio não deixava rastro nenhum de que ele existiu.

#### A primeira simulação de verdade achou dois defeitos

Era exatamente para isso que a fase existia.

**1. O aviso de confiança disparava em toda notação normal.** A primeira versão contava
como "desconhecido" todo caractere fora do perfil de mapeamento, e `Nf3` tem só o `N` no
perfil — saía com confiança 0,33 e aviso, sendo um lance perfeitamente comum. Um aviso
que dispara sempre é o mesmo que não avisar. A conta passou a considerar também a
`NOTACAO_ESPERADA` (coluna, fila, captura, xeque, promoção, roque, anotação), que
atravessa sem tradução e **assim mesmo está certa**. `Nf3` agora dá 1,00; `wyz` dá 0,00.

**2. A letra de coluna vira peça.** Medido: `Bb5` sai como `♗♝5`. O `B` maiúsculo é o
bispo, certo — mas o `b` minúsculo, que ali é a **coluna b**, também está no
`DEFAULT_MAPPING_PROFILE` (minúsculas = peças pretas) e virou bispo preto. Não é defeito
do relatório, é do perfil, e é anterior a esta fase: passava despercebido porque ninguém
via o antes e o depois. Fica como motivação concreta da F2.4 — nas fontes figurinas as
minúsculas realmente codificam peças pretas, então o perfil sozinho não tem como
distinguir os dois usos sem olhar o contexto.

Cobertura: `tests/test_f23_relatorio_dryrun.py`, 22 testes.

### F2.4 — Perfis de mapeamento por fonte — CONCLUÍDA

A spec v1.0 §10 pede perfis por livro/editora. O código tem um único
`DEFAULT_MAPPING_PROFILE` hardcoded (`chess_pdf_processor.py:12`). Fontes que mapeiam
peças fora do padrão KQRBNP (comum em Chess Diagram TTF) ficam sem solução.

**Concluída em 2026-08-04.** `core/perfis.py` e `config/profiles/*.json`, com seleção
automática por `font_patterns` e override manual (`analisar_substituicao(perfil=...)`).
Os limiares de detecção de diagrama, antes literais em `is_block_a_diagram`, vieram
junto — também são por livro, porque fonte com subset e nome aleatório (`ABCD+F1`) muda
a proporção de spans que aquela conta enxerga.

#### O motivo concreto não era o do roadmap

O roadmap justificava a fase com "fontes fora do padrão KQRBNP". O motivo que apareceu
medindo foi outro, e mais grave: **a convenção erra dentro do próprio livro.** A
simulação da F2.3 mostrou `Bb5` saindo como `♗♝5` — o `B` é o bispo, certo, mas o `b`,
que ali é a **coluna b**, também estava no perfil (minúscula = peça preta) e virou bispo
preto.

E, pela F1.1, estes livros usam **um conjunto só de figurinas para os dois lados**: quem
diz a cor é a paridade do lance, não o glifo. Para eles a convenção de minúsculas
simplesmente não vale. Daí os dois perfis que acompanham o projeto:

| perfil | mapeia | `Bb5` vira |
|---|---|---|
| `10_figurina_unica` | só maiúsculas | **`♗b5`** |
| `20_duas_caixas` | as duas caixas (o antigo padrão) | `♗♝5` |

**Não dá para escolher entre os dois por heurística**, e é por isso que vira perfil e não
regra: nas fontes figurinas de verdade as minúsculas **são** peças pretas, e num livro
que use as duas caixas o `figurina_unica` perderia todas as peças pretas. Dentro de um
diagrama, `rnbqkbnr` é a fileira 8 inteira e não tem coluna nenhuma no meio. É decisão
por livro.

O número no nome do arquivo é a precedência — `10_` ganha de `20_` numa fonte que case
com os dois —, o que evita inventar um campo de prioridade.

**Perfil quebrado interrompe a carga, não é pulado.** Pular faria a conversão cair no
padrão em silêncio, e o usuário veria o livro convertido com o mapeamento errado sem
nenhum aviso — que é o mesmo tipo de falha silenciosa que a F2.3 veio combater. A
validação recusa chave de mais de um caractere (a substituição é caractere a caractere,
então uma chave de dois nunca casaria e o perfil ficaria inerte), modo desconhecido e
limiar de diagrama fora de faixa.

O relatório da F2.3 ganhou a coluna `perfil`: sem ela, dois livros convertidos com
perfis diferentes produzem relatórios indistinguíveis.

Cobertura: `tests/test_f24_perfis.py`, 20 testes.

---

## F3 — Produtividade

O gargalo real: uma página de livro tem ~2.000 caracteres. Hoje a revisão é
**um Enter por caractere**, sem filtro, sem pistas visuais.

| # | Melhoria | Impacto |
|---|----------|---------|
| F3.1 | ~~Modo digitação contínua~~ — **CONCLUÍDA** | Corta metade das teclas |
| F3.2 | ~~Cor por confiança~~ — **CONCLUÍDA** | O olho vai direto ao suspeito |
| F3.3 | ~~Filtros na lista~~ — **CONCLUÍDA** | Revisar 80 boxes em vez de 2.000 |
| F3.4 | ~~Autosave + recuperação de crash~~ — **CONCLUÍDA** | O `crash_log.txt` existe por um motivo |
| F3.5 | ~~Atalhos~~ — **CONCLUÍDA** | Fluxo sem mouse |
| F3.6 | ~~Aplicar a todos os semelhantes~~ — **CONCLUÍDA** | Ganho de ordem de grandeza |
| F3.7 | ~~Boxes persistem por página de PDF~~ — **CONCLUÍDA** | Evita perda silenciosa de trabalho |
| F3.8 | ~~Snapshot do histórico a cada tecla~~ — **CONCLUÍDA** | 15,8 ms por tecla viram 0,24 |
| F3.9 | ~~Ir direto para uma página; o botão que sumia~~ — **CONCLUÍDA** | A janela cabe na tela e os botões param de ser empurrados para fora |
| F3.10 | ~~O diálogo de salvar propunha o nome errado~~ — **CONCLUÍDA** | Toda página do livro propunha `livro.box` |
| F3.11 | ~~O merge vertical atravessava a linha de texto~~ — **CONCLUÍDA** | +1,2 de recall e +0,7 de F1, em todas as páginas |

**F3.2 — concluída em 2026-08-03.** O pipeline já calculava a confiança em
`fallback_chain` e a descartava (`char, source, _`). Agora `BoxEntry` guarda
`confidence` e `source`, o canvas e a lista lateral pintam por essa escala, e há legenda
e contador de pendentes.

Três decisões que mudaram o resultado:

- **"Sem informação" não é confiança baixa.** Um box vindo de um `.box` não traz
  confiança (o formato do Tesseract não guarda isso). Pintá-lo de vermelho diria
  "confira este" quando o certo é "não sei" — e encheria a tela de falso alarme ao abrir
  um arquivo salvo. Ganhou cor própria (azul) e fica fora da fila de revisão.
- **Corrigir um box tem que tirá-lo do vermelho.** Digitar um caractere grava
  `confidence=1.0, source="manual"`. Sem isso a cor nunca convergiria e a revisão não
  teria fim visível.
- **A confiança do EasyOCR era jogada fora**: `fallback_chain` devolvia `0.0` fixo para
  esse elo (`ocr_service.py:155`), com um comentário dizendo que a lib não fornecia o
  dado. Fornece — é o terceiro item de cada resultado de `readtext(detail=1)`. O
  Tesseract também passou a reportar confiança, via `image_to_data`.

Limitação conhecida: salvar e recarregar **perde** a confiança, porque o `.box` do
Tesseract não tem onde guardá-la. Os boxes voltam como "sem informação", que é o
comportamento honesto. Persistir isso é natural na F3.4, junto do sidecar de autosave.

Cobertura: `tests/test_f32_confianca.py`, 12 testes.

**F3.3 — concluída em 2026-08-03.** Painel de filtros na barra lateral (busca por
caractere, só pendentes, só vazios, por origem), contador "mostrando N de M", e
`F3`/`Shift+F3` para saltar entre pendências, com volta ao chegar na ponta.

Medido na página real: **416 de 764 boxes** entram no filtro "só pendentes" — é a
diferença entre reler a página inteira e conferir o que está duvidoso.

O risco desta fase era estrutural: com filtro, a lista deixa de mapear 1:1 com
`self.boxes`. Um erro no mapeamento linha→índice faria o usuário editar o caractere
errado sem perceber. Toda seleção passa por `linha_do_box()` / `_visiveis`, e há teste
dedicado (`test_clicar_na_lista_filtrada_seleciona_o_box_certo`).

Detalhe que os testes pegaram: `"" in "a"` é verdadeiro em Python, então boxes vazios
passavam por qualquer busca de caractere. A busca trata o texto digitado como conjunto
("e" acha os 'e', "aeiou" acha qualquer vogal) e diferencia maiúscula de minúscula,
porque o OCR também diferencia.

Corrigir um box com "só pendentes" ativo o tira da lista; a lista encolhe e o cursor
fica na mesma posição, que já é o próximo pendente — sem pular nenhum.

Cobertura: `tests/test_f33_filtros.py`, 18 testes.

**F3.1 — concluída em 2026-08-03.** `F2` liga a digitação contínua: a tecla aplica o
caractere e avança sozinha. Fora do modo, rotular custa duas teclas (o caractere e o
Enter) — numa página de 2.000 caracteres são 2.000 teclas a mais.

Três teclas fazem o fluxo de revisão inteiro:

| Tecla | Ação |
|---|---|
| qualquer imprimível | aplica e avança |
| **Espaço** | pula sem alterar |
| **Backspace** | volta um box |
| `Esc` | sai do modo |

O Espaço não estava na spec e mudou o fluxo: na revisão a maioria dos caracteres já
está certa, então dá para passar por eles sem digitar nada e só corrigir os errados.

**Conflito que precisou ser resolvido:** `d` estava ligado a "dividir box" na janela
inteira. Com o modo digitação isso viraria bug — digitar 'd' partiria um box em dois.
Passou para `Ctrl+D`, como a SPEC §7.6 já previa. O guard antigo
(`_on_key_split_safe`) só testava `tk.Entry` e não cobria `ttk.Entry` nem `Combobox`.

O modo tira o foco do campo de texto e o põe no canvas — senão o `Entry` consumiria as
teclas antes de o binding da janela ver o evento, e o modo simplesmente não funcionaria.

Verificado com despacho real do Tk (`event_generate`), não só chamando os handlers:
a precedência de bindings é exatamente onde este desenho poderia furar em silêncio.

Cobertura: `tests/test_f31_digitacao.py`, 15 testes.

**F3.4 — concluída em 2026-08-03.** Rascunho automático em
`<documento>.pyboxsession.json`, gravado a cada 25 alterações, com oferta de
recuperação ao reabrir. `Ctrl+B` grava na hora.

A medição mudou o desenho. Gravar do jeito ingênuo (`asdict` + JSON na thread da UI):

| Sessão | Custo |
|---|---:|
| 1 página, 764 boxes | 6 ms |
| 5 páginas, 10 mil boxes | 74 ms |
| 20 páginas, 40 mil boxes | **292 ms** |
| 50 páginas, 100 mil boxes | **746 ms** |

Acima de poucas páginas isso violaria o critério da F4.1. Duas mudanças resolveram:

- **Formato de tuplas em vez de dicts** — `asdict` sozinho custava 98 ms dos 292. Com
  tuplas a conversão cai para 23 ms e o arquivo encolhe de 3,9 MB para 1,7 MB.
- **Snapshot na UI, encode e escrita numa thread própria** — o rascunho não passa pelo
  `BackgroundTask`: não é operação do usuário, não tem progresso, não é cancelável e não
  pode disputar a vaga única com o OCR.

Medido depois: **22,9 ms** de bloqueio para 40 mil boxes, 12× melhor que os 292 ms.

Outras decisões:

- **Escrita atômica** (temporário + `os.replace`). Travar durante o autosave não pode
  deixar um rascunho corrompido — é justamente o cenário para o qual ele existe.
- **Fila de tamanho 1**, o pedido novo descarta o antigo: só interessa o estado atual.
- **O rascunho some quando não é mais necessário**: ao salvar de verdade, ao recusar a
  recuperação e ao aceitar descartar alterações. Sobreviver a um descarte explícito
  faria o trabalho ressuscitar na abertura seguinte.
- **Rascunho recuperado não é sobrescrito pelo `.box` do disco** — ele é mais recente.

Isso também fecha a limitação registrada na F3.2: o rascunho guarda `confidence` e
`source`, que o `.box` do Tesseract não tem onde guardar.

Cobertura: `tests/test_f34_autosave.py`, 13 testes.

**Custo colateral medido:** `_commit_change` gastava ~15,7 ms numa página de 2.000 boxes
só no `deepcopy` do histórico — ou seja, ~15 ms por tecla no modo digitação contínua.
Ficou registrado como o próximo gargalo natural e virou a **F3.8**.

**F3.7 — concluída em 2026-08-03.** `_load_pdf_page` fazia `self.boxes = []` sem aviso
nem confirmação: navegar para a próxima página apagava tudo que havia sido digitado,
em silêncio. Reproduzido no código anterior antes de corrigir.

O que entrou:

- `core/services/document_service.py` — `DocumentSession` guarda os boxes de todas as
  páginas visitadas e registra quais têm alterações não gravadas
- virar a página arquiva o trabalho da página que sai e restaura o da que entra
- `_commit_change()` como ponto único de mutação (aproveita o invariante estabelecido
  na F0.3: toda alteração passa por um snapshot)
- título marca `*` quando há trabalho pendente, e mostra arquivo e página
- confirmação ao abrir outro documento ou fechar a janela com pendências
- **"Salvar todas as páginas"** (Ctrl+Shift+S) — grava um par `.box`/`.png` por página
  com boxes, seguindo a convenção `livro_pg003.box` que o projeto já usa em `Box/`
- PgUp/PgDn para navegar, Ctrl+S para salvar a página atual

O item de salvar tudo não era opcional: preservar boxes entre páginas sem oferecer como
gravá-los deixaria o usuário acumulando trabalho insalvável — pior que o comportamento
antigo, porque dá a impressão de estar seguro.

Cobertura: `tests/test_f37_paginas.py`, 10 testes.

**F3.6 — concluída em 2026-08-04.** Ctrl+E espalha a última correção para os boxes que
são o mesmo glifo. `core/semelhanca.py` decide quais são; `ui/dialogo_semelhantes.py`
mostra o que vai mudar antes de mudar.

**O critério é a imagem, não o caractere lido.** Casar por caractere acharia os 300 `c`
errados, mas junto viriam os `c` legítimos — e o lote os estragaria. Medido sobre todos
os pares de boxes das 9 páginas rotuladas à mão, com o `?` do rotulador (que ali é "não
sei", não o glifo) fora da conta:

| critério | limiar | precisão | cobertura |
|---|---:|---:|---:|
| imagem | 0,20 | 98,91% | 64,6% |
| imagem | 0,30 | 92,77% | 69,1% |
| imagem + mesma leitura | 0,20 | **99,29%** | 64,5% |
| imagem + mesma leitura | 0,30 | **99,30%** | 69,1% |

O segundo filtro é o caractere que os candidatos **ainda** mostram: o box de referência
já virou `e`, os outros 300 continuam em `c`. Ele não melhora o caso apertado — melhora o
afrouxado: só com imagem, ir de 0,20 a 0,30 troca 4,5 pontos de cobertura por 6 de
precisão; com a leitura junto, a precisão não se move e a cobertura sobe de graça. Dois
glifos parecidos que o OCR já leu **diferente** deixam de ser candidatos.

**A precisão não passa de ~99,3%, e não é ajuste de limiar que resolve.** O que sobra são
homóglifos de verdade — `0`×`o`, `9`×`g`, `1`×`i`, `P`×`p`, `T`×`t`, `B`×`b`, `C`×`c` —
em que as duas imagens *são* quase iguais e o OCR leu as duas igual. Quem os separa é o
contexto, que é trabalho da F1.7.

**Essa medida é que decidiu o desenho.** Um em cada ~145 boxes do lote sairia errado; num
lote de 300 são dois boxes estragados em silêncio, num box que o usuário nunca olhou, e
ainda marcados como revisados — pior que o erro do OCR que se queria corrigir. Aplicar
sem pré-visualização estava fora de questão. Daí:

- os recortes vão para a tela **ordenados por distância**, o duvidoso no fim;
- botão direito num recorte desmarca dali até o fim da fila, que é o gesto certo dada a
  ordenação: "conferir 300" vira "achar onde a fila começa a estranhar";
- o lote grava `source="lote"`, não `"manual"`. Sai da fila de revisão (confiança 1,0),
  mas continua achável pelo filtro de origem da F3.3 — apagar o rastro tornaria aquele
  resto de ~0,7% impossível de reencontrar depois.

**O modelo do lote é o box corrigido, não o selecionado.** Tanto o Enter quanto o modo
digitação da F3.1 avançam sozinhos depois de gravar, então quando o usuário pede o lote a
seleção já saiu de cima do box que ele acabou de corrigir — usar a seleção espalharia o
caractere do box *seguinte*. A correção fica guardada com a **identidade do objeto**, não
o índice: dividir ou excluir desloca índices, e o desfazer troca a lista por cópias. Nos
dois casos a referência é descartada e o casamento cai para só-imagem, que é a
degradação segura. O diálogo mostra o recorte do modelo no cabeçalho, para o caso de a
escolha não ser a esperada.

Os 300 boxes alterados são **um** `_commit_change`, logo um Ctrl+Z. Um snapshot por box
entupiria o histórico de 50 posições e deixaria o usuário sem como voltar ao estado
anterior ao lote — que é exatamente o que ele vai querer quando o lote sair errado.

Limite conhecido: a tela mostra no máximo 400 recortes (acima disso a montagem do grid
trava a janela por segundos) e **o lote aplica só o que está na tela**. A mensagem diz
quantos ficaram de fora; cortar a exibição e aplicar no resto seria mudar o que o usuário
não viu.

Cobertura: `tests/test_f36_semelhantes.py`, 49 testes.

**F3.5 — concluída em 2026-08-04.** Metade do item já tinha entrado junto com a F3.7:
Ctrl+S, Ctrl+Shift+S e PgUp/PgDn nasceram lá, porque preservar boxes entre páginas sem
oferecer como gravá-los seria pior que não preservar. Faltavam **Ctrl+O** e
**Tab/Shift+Tab**.

Ctrl+O abre um diálogo só, para PDF e imagem, e decide pela extensão. O menu mantém as
duas entradas separadas — às vezes se quer filtrar a lista —, mas um atalho que exigisse
escolher o tipo *antes* de ver o arquivo seria pior que não ter atalho.

**Tab devolve `"break"`, e isso desliga a travessia de foco do Tk na janela principal.**
É deliberado e é o custo real do item: sem o `"break"`, o Tk moveria o foco *além* de
mover o box, e o foco sairia do editor no meio da revisão. A janela é um editor de canvas
e lista, não um formulário, e o único campo que precisava de caminho próprio (a busca) já
tem o Ctrl+F. Os diálogos não são afetados: binding de tecla sobe pelo *toplevel* do
widget em foco, e o de um `Toplevel` não é a janela principal.

O Tab também leva o foco ao campo do caractere, o que fecha o ciclo "Tab, digita, Tab".
Sem isso, um Tab dado a partir da busca deixaria o usuário navegando boxes com as teclas
caindo no filtro. No modo digitação o foco não se mexe — lá quem recebe as teclas é a
janela, e roubá-lo desligaria o modo na prática.

Os aceleradores foram para os rótulos do menu: atalho que não aparece no menu é atalho
que ninguém descobre.

Cobertura: `tests/test_f35_atalhos.py`, 31 testes.

**F3.8 — concluída em 2026-08-04.** O custo que a F3.4 deixou registrado. Toda mutação
passa por `_commit_change`, que tira um snapshot; no modo digitação da F3.1 isso é uma
vez por tecla, e o `copy.deepcopy` de uma lista de dataclasses custava 15,8 ms numa
página de 2.000 boxes.

Medido, numa página de 2.000:

| forma de copiar | custo |
|---|---:|
| `copy.deepcopy(boxes)` (antes) | 15,79 ms |
| `[copy.copy(b) for b in boxes]` | 3,33 ms |
| `[b.copy() for b in boxes]` (`dataclasses.replace`) | 3,72 ms |
| `[BoxEntry(b.char, b.x1, ...) for b in boxes]` | 0,57 ms |
| `[b.as_state() for b in boxes]` — tupla (agora) | **0,19 ms** |
| reconstruir de tuplas (o custo do undo) | 0,55 ms |

O `deepcopy` fazia trabalho para um caso que não existe aqui: os campos do `BoxEntry`
são todos imutáveis (str, int, float), então não há grafo de objetos a percorrer nem
ciclo a memoizar. Ele pagava por essa generalidade a cada tecla.

Resultado ponta a ponta, com o histórico cheio (50 posições):

| | antes | agora |
|---|---:|---:|
| snapshot (2.000 boxes) | 18,15 ms | **0,24 ms** |
| undo + redo | 30,65 ms | **1,44 ms** |
| memória do histórico cheio | 21,1 MB | **10,4 MB** |

**A F3.4 previa "snapshot incremental em vez de cópia integral", e a medição diz para
não fazer isso.** Guardar só o que mudou custaria a comparação das listas (0,16 ms) mais
a cópia dos alterados — 0,17 ms contra os 0,19 ms da cópia integral. Nada, em troca de um
delta com estado próprio, que precisa acertar inserção e remoção (dividir e excluir box)
e é exatamente onde esse tipo de código erra. **O problema não era a cópia ser integral;
era ela ser profunda.**

O `DocumentSession.montar_payload` tinha chegado à mesma conclusão antes, pelo mesmo
caminho, para o rascunho em disco — e ninguém aplicou ao histórico. A diferença entre os
dois: lá a confiança é arredondada para 4 casas, para o arquivo encolher; aqui não pode
haver arredondamento nenhum, porque o undo tem de devolver o estado idêntico.

O risco desta mudança era perder campo na ida e volta. Confiança e origem não aparecem
como número exato no canvas nem na lista, e um undo que os zerasse passaria despercebido
até o box reaparecer sem cor — daí a maior parte dos testes ser igualdade exata de
estado, e não de caractere.

Cobertura: `tests/test_f38_historico.py`, 20 testes.

**F3.9 — concluída em 2026-08-05.** Relatada pelo usuário: *"tem a opção de abrir o PDF
mas não consigo avançar as páginas; gostaria de treinar a página que eu escolher"*.

**O botão não estava quebrado: ele estava fora da tela.** Perguntado o sintoma exato, o
usuário respondeu *"não aparecia o botão de próxima página"* — e aí o defeito ficou
medível. Duas causas somadas:

1. **`appy.py` abria a janela com `geometry("1600x900")` fixo.** A tela da máquina tem
   **1360×768**. A janela nascia 240 px mais larga e 132 px mais alta que o monitor, e o
   lado direito ficava fora — inalcançável, sem barra de rolagem que o trouxesse de
   volta. Agora a geometria é calculada a partir da tela (1280×648 ali), centralizada, com
   `minsize` para o usuário não conseguir encolher até sumir controle.
2. **O rótulo de página ficava entre os dois botões, e crescia com o uso.** *"Página:
   108/120 | 14 pág. com boxes, 4200 no total | 14 não salva(s)"* mede **381 px**. Como a
   barra empilha da esquerda para a direita, esse rótulo empurrava o "Próxima Página >>"
   para fora — o usuário via o botão de voltar e não o de avançar. **A ordem de
   empacotamento é a ordem de sobrevivência**: os controles foram para um grupo próprio,
   empacotado primeiro (290 px, sempre visível), o rótulo ficou curto
   (`Página: 108/120`), e o detalhe da sessão virou um rótulo próprio, empacotado por
   último — é o primeiro a ser cortado, e é o que menos falta faz, porque o mesmo dado
   está no título da janela. A barra inteira caiu de 1160 para 1033 px.

O segundo problema **não existia** até esta fase criar o campo "Ir para": ele agravou
uma barra que já estava no limite. Achá-lo foi consequência de medir em vez de supor.

E o que o usuário pediu também não existia: chegar a uma página **escolhida**. Só havia
"anterior" e "próxima", e num livro de 300 páginas alcançar a 108 são 107 renderizações e
107 esperas. O caminho existia e não servia, que na prática é o mesmo que não existir.

Entrou um campo "Ir para:" na barra de navegação, com Enter, botão e **Ctrl+G**. O número
é o que o rótulo mostra (1 a N), não o índice interno — trocar um pelo outro levaria à
página errada sem erro nenhum, e há teste para isso.

**E um terceiro defeito apareceu no caminho.** `_load_pdf_page` desistia
**em silêncio** quando havia tarefa rodando, contando com os botões desativados para
explicar. Eles não explicam: pelo teclado (PgUp/PgDn) ou pelo campo novo, o usuário
aperta e nada acontece — e a leitura natural é que virar a página quebrou. Agora a barra de status diz o motivo.

Treinar a página escolhida já funcionava assim que se chegasse nela: "Aprender com Página
Atual" opera sobre a página carregada, seja imagem ou PDF.

Cobertura: `tests/test_f37_paginas.py`, 27 testes (17 novos), incluindo regressão
para a janela caber na tela e para os controles de página serem o primeiro grupo da barra.

### F3.10 — O diálogo de salvar propunha o nome errado — CONCLUÍDA

**Concluída em 2026-08-10.** Pedido do usuário: *"quando for salvar o box seria
interessante sugerir o nome do pdf e a página"*. O que o Ctrl+S propunha era pior que não
propor nada.

O nome saía de `image_path`, que numa sessão de PDF **não é um caminho**: é o rótulo da
janela, `livro.pdf [Pág 11]`. O `os.path.splitext` disso devolve `('livro', '.pdf [Pág
11]')` — a página se perde e sobra `livro.box`, na última pasta usada. As 120 páginas do
livro propunham todas o mesmo nome, e salvar a segunda oferecia sobrescrever a primeira.
Aceitar não estragava só o `.box`: `_save_box_to_path` grava o par, então o `.png` da
página 1 era substituído pelo da 11 — o `.box` sobrevivente passa a apontar para a imagem
errada, e um `.box` só vale contra a imagem dele.

E o nome proposto **discordava do que o próprio programa grava**: "Salvar todas as
páginas" usa `session.page_stem()` → `livro_pg011.box`, na pasta do PDF. As duas rotas de
salvamento davam nomes diferentes para a mesma página. Agora as duas saem do mesmo
`page_stem`, e o diálogo abre na pasta do documento em vez da última usada.

**O PGN entrou junto porque tinha o mesmo defeito com outro sintoma.** Ele já numerava,
mas sem os zeros: `livro_pg11.pgn`. Ordenado por nome isso não cai perto do
`livro_pg011.box` que descreve — cai entre a página 109 e a 110. Os três arquivos de uma
página passam a compartilhar o radical.

Cobertura: `tests/test_f37_paginas.py` e `tests/test_f61_pgn.py`, 3 testes novos — um
deles confere que o nome proposto pelo Ctrl+S é exatamente o que "Salvar todas as
páginas" gravaria, que é o acoplamento que se quer manter.

### F3.11 — O merge vertical atravessava a linha de texto — CONCLUÍDA

**Concluída em 2026-08-10.** Relato do usuário: *"o glifo do rei sempre gera o box com o
. da linha acima, e se tiver ... pega os 3"*. Está certo, e o rei não tem nada de
especial: é só o glifo alto que a notação de xadrez põe logo depois de um ponto.

**Medido antes de mexer.** Nas 11 páginas rotuladas, **66 boxes** saíam do
`merge_vertical_boxes` cobrindo caracteres rotulados de **duas linhas diferentes**. As
figurinas são ~1,5% dos glifos da base e respondiam por ~23% desses casos.

`merge_vertical_boxes` tinha uma régua de folga só, `max(10, min(30, mediana * 0,8))`, e
ela vale para o par que justifica a função — o pingo do 'i'. Medida a folga de verdade,
em alturas medianas de box:

| par | folga medida | n |
|---|---:|---:|
| pingo do 'i' | até 0,23 | 386 |
| ponto do '?' e do '!' | até 0,23 | 27 |
| pingo do 'j' | 0,25 | 2 |
| acento, `±`, `∓`, `²` | até 0,17 | 12 |
| **`:` e `;`** | **0,43–0,45** | 9 |
| **pontuação da linha de cima** | **0,55–0,79** | 66 |

Há um vale limpo: **nada da população medida cai entre 0,25 e 0,55**, e a régua antiga
valia ~0,80 — do lado errado dele. Por isso são **duas** folgas agora, e não uma menor:

- curto + alto (o diacrítico, e o par que o ponto da linha de cima imita): **0,30**
- curto + curto (`:` e `;`, dois pontos separados por meia altura de x): **0,50**
- alto + alto: 2 px, inalterado

**A vítima é a altura, não o desenho.** A folga vai da base da linha de cima ao **topo**
do glifo de baixo: num `a` de x-height ela mede 37 px e nunca chegou perto da régua; num
`♔`, `B`, `d` ou dígito, 22. Daí a lista de atingidos ser ♔♕♖♗♘, B, R, K, Q, d, f, h, b e
os dígitos, e nunca `a`, `e`, `o`. E como o laço refaz a busca com a caixa já crescida,
bastava o primeiro ponto entrar para os vizinhos virem atrás: era assim que um `...`
entrava com os três.

**A régua antiga também não era relativa de verdade.** O `max(10, min(30, ...))` prendia
o limiar entre 10 e 30 **pixels**, então ele significava coisas diferentes conforme a
escala da página — e a contagem do defeito seguia a mediana da página sem exceção:
mediana 29 → 36 casos, 27 → 22, 23 → 11, 22 → de 1 a 3. A página mais atingida é a de
maior mediana, onde a régua abria mais. Piso e teto saíram.

**Resultado, em `medir_paginas.py`:**

| modo | recall | precisão | F1 |
|---|---|---|---|
| off | 94,5% → **95,7%** | 93,9% → **94,1%** | 94,2 → **94,9** |
| arbitrado | 94,6% → **95,8%** | 93,9% → **94,1%** | 94,3 → **94,9** |

**As 10 páginas melhoram e nenhuma piora**, nos dois modos. O ganho é maior exatamente
onde a medição do defeito era maior: a página 0020 (36 casos) sobe +2,7 de F1 e +4,5 de
recall, a 0057 (22 casos) sobe +1,0. Depois da correção, os merges que cobrem dois
rotulados são **100% da mesma linha** — o que sobra são glifos que já vinham colados num
contorno só, que é assunto da F13.

Nenhum diacrítico foi perdido: os merges de `i` até subiram de 386 para 397, porque o
laço guloso não gasta mais o pingo dentro de uma caixa errada.

Cobertura: `tests/test_f311_merge.py`, 11 testes — a cobertura do merge que a seção 8.2
do SPEC listava como pendente desde a F5.3. Dois deles falham no código anterior.

---

## F4 — Interface

### F4.1 — A UI congela em toda operação pesada — CONCLUÍDA

Todo processamento roda na thread do Tkinter com `self.parent.update()` no meio do
laço (`main_window.py:436, 491, 546`). Durante OCR de uma página, treino ou lote:

- janela marcada como "Não Responde" pelo Windows
- **não há como cancelar**
- `update()` reentrante durante processamento é uma fonte clássica de corrupção de
  estado no Tk (pode reentrar num handler no meio da mutação da lista de boxes)

**Concluída em 2026-08-03.** Worker em `threading.Thread` + fila; a UI só lê a fila via
`after()`. Não sobrou nenhum `parent.update()` em `ui/`.

Onze operações convertidas: os quatro preenchimentos por OCR, as duas conversões de PDF,
treino, lote, importação, "salvar todas as páginas" e **o carregamento de página do PDF**.

Este último não estava na lista original e acabou sendo o mais importante: medi **948 ms**
para renderizar uma página de um PDF sintético *simples* — quase 10× o critério de 100 ms,
e um scan de livro a 300 dpi é bem pior. Como virar a página é a operação mais frequente
do app, era o congelamento que o usuário mais sentia.

Também entrou `ui/status_bar.py` (F4.2), recriado como `Frame` com mensagem, barra de
progresso e botão Cancelar. Sumiram os dois improvisos: o progresso escrito no título da
janela e os `Toplevel` que cada operação longa criava por conta própria.

Cancelamento tem duas formas, conforme o parcial sirva ou não:

- `h.cancelled` + `break` — os preenchimentos por OCR devolvem o que já reconheceram,
  em vez de jogar fora
- `h.raise_if_cancelled()` — conversão de PDF aborta de vez (o arquivo só é gravado no
  fim, então não fica nada pela metade)

O treino consulta `should_stop` a cada época e mantém salvo o melhor modelo até ali.

**Bug encontrado ao escrever os testes:** `is_running()` consultava `thread.is_alive()`,
que vira `False` no instante em que a thread enfileira o resultado — antes de `on_done`
rodar. Nessa janela dava para disparar outra tarefa por cima de um estado ainda não
aplicado. Passou a ser um estado próprio, baixado só na entrega.

Cobertura: `tests/test_f41_threads.py`, 10 testes.

### F4.2 — Progresso comunicado pelo título da janela — CONCLUÍDA

`self.parent.title(f"Processando... ({i+1}/{total})")` era um recurso improvisado.
Resolvido junto com a F4.1: `ui/status_bar.py` foi recriado como `Frame` (a versão
antiga, removida na F5.1, era um `tk.Label` e não comportava um `Progressbar`) e é
usado por todas as operações longas.

### F4.3 — Zoom automático desorienta — CONCLUÍDA

`select_box` (`main_window.py:588`) chama `zoom_to_box` **em toda seleção**, com
`margin = 10.0` e zoom mínimo forçado de 1.5×. Navegar com as setas faz a imagem
saltar e re-enquadrar a cada tecla. Perde-se completamente o contexto da linha.

**Ação:** rolar o mínimo necessário para o box ficar visível; zoom só sob comando
explícito (tecla `Z` ou duplo-clique).

**Concluída em 2026-08-04.** `CanvasView.garantir_visivel` rola o mínimo e **não toca
no zoom**; se o box já está visível, não faz nada — rolar sem necessidade era o próprio
defeito. Box maior que a janela é centralizado, porque encostar numa borda deixaria a
outra ponta fora de qualquer jeito.

Enquadrar virou comando explícito: **duplo-clique** ou **F4**. Tecla de função e não `Z`
como o roadmap sugeria: com o modo digitação ligado (F3.1), uma letra solta é capturada
por `_on_tecla_digitacao` e vira o caractere do box — F2 e F3 já são atalhos de janela
pelo mesmo motivo.

Saiu daí um `viewport()`: `winfo_width()` devolve 1 enquanto o Tk não calculou a
geometria, e o recuo para 800×600 estava duplicado. Ser um método só garante que rolar e
enquadrar concordem sobre onde é a borda — foi o que fez dois testes falharem antes,
medindo uma borda diferente da que o código usava.

### F4.5 — Sem indicação de trabalho não salvo — JÁ ESTAVA FEITA

Verificado em 2026-08-04: o item está implementado e a descrição abaixo estava velha.
`_update_title` marca o título quando `session.is_dirty()`, e `_confirm_discard()` guarda
os três caminhos que o item pedia — sair (`_on_close`), abrir outro arquivo e trocar de
página. Veio junto com a sessão de várias páginas da F3.7.

### F4.4 — `update_sidebar` reconstrói a lista inteira a cada tecla — CONCLUÍDA

`delete(0,"end")` + N `insert()` a cada seleção (`main_window.py:564`). Com 2.000
boxes, cada seta pressionada refaz 2.000 linhas. A digitação engasga.

**Ação:** atualizar só as linhas alteradas, ou migrar para `ttk.Treeview` virtualizado.

**Concluída em 2026-08-04**, pelo primeiro caminho — sem trocar de widget.

O que destrava é notar que **navegar não muda o conteúdo da lista**, só qual linha está
marcada. Guardando o que foi desenhado (`_linhas_desenhadas`) dá para comparar e não
fazer nada. Medido com um `Listbox` de verdade e 2.000 boxes:

| | por seta pressionada |
|---|---:|
| antes (refaz tudo) | **94,5 ms** |
| depois (só o que mudou) | **2,9 ms** |

33× — e os 94 ms eram o engasgo do enunciado, muito acima do limiar em que a digitação
começa a parecer travada. Editar um caractere custa 3,2 ms e toca **uma** linha.

Três caminhos, por custo: conteúdo igual não faz nada; conteúdo diferente com o mesmo
tamanho reescreve só as linhas que mudaram; tamanho diferente (box criado, excluído,
filtro que corta) refaz tudo, que é raro e não vale a complicação de um *diff*.

O `Listbox` do Tk não troca o texto de uma linha no lugar, daí o `delete`+`insert` na
mesma posição. E a seleção não sobrevive a isso: ela é reposta no fim, com um
`selection_clear` antes para o caminho rápido e o lento terminarem iguais.

Os testes contam as operações que chegam ao `Listbox`, com um dublê no lugar dele.
Contar operações é estável; cronometrar numa máquina compartilhada não é — o número de
milissegundos acima serve para dimensionar o ganho, não para reprovar num CI.

### F4.6 — Colisão de tecla — CONCLUÍDA

`d` está ligado a "dividir box" na janela inteira (`main_window.py:209`). O guard
`_on_key_split_safe` só testa `isinstance(focus_widget, tk.Entry)` — não cobre
`ttk.Entry`, `Text` ou `Spinbox`. Digitar "d" no lugar errado divide um box.

**Concluída em 2026-08-04, com o diagnóstico corrigido.** Duas coisas acima já não valiam:

1. **`d` já era `Ctrl+D`.** A colisão descrita — digitar "d" e partir um box — foi
   resolvida antes, em alguma fase anterior.
2. **`ttk.Entry` nunca foi o buraco.** Medido: `ttk.Entry` e `ttk.Spinbox` **herdam** de
   `tk.Entry`, então o `isinstance` já os cobria. Quem escapava era `tk.Text`,
   `tk.Spinbox` e `ttk.Combobox`.

O defeito real era outro, e mais interessante: **havia dois guards de foco no mesmo
arquivo**, um completo (`_on_tecla_digitacao`, que listava `tk.Text` e `ttk.Combobox`) e
o do Ctrl+D, que ficou para trás. Guard duplicado é guard que sai de sincronia. Agora há
um só, `_foco_em_campo_de_texto`, usado pelos três atalhos que precisam dele — e um teste
reprova se alguém escrever um `isinstance` de foco por fora.

Ele também trata o `KeyError` que `focus_get()` levanta quando o foco está noutra
aplicação: sem isso o atalho morreria com exceção em vez de simplesmente disparar.

### F4.7 — O Ctrl+D parte 'ba' de cima a baixo — CONCLUÍDA

Relatado pelo usuário: num box com duas letras de alturas diferentes — `ba`, `it`, `ll` —
o Ctrl+D devolve as metades **uma embaixo da outra**. Junto vieram dois pedidos: que o
atalho valha também com o foco no campo do caractere, e que a lista da direita mostre
qual caractere está selecionado.

**Concluída em 2026-08-07.**

#### O corte

A regra era a proporção do box: mais largo que alto corta em X, senão em Y, sempre no
meio. O `b` tem ascendente e o `a` não, então a união das duas sai mais **alta** que
larga — e a regra manda cortar no eixo errado. Não é um caso de canto: são as letras
estreitas e altas do inglês corrido, e elas estão em toda linha de texto.

**A medição.** As 9 páginas rotuladas dão a população de graça: unindo cada par de
caracteres vizinhos da verdade rotulada num box só, sai exatamente o box que o usuário
manda dividir — 5.747 pares lado a lado e 57 empilhados. "Corte bom" é cair a menos de
10% do lado do box da fronteira verdadeira.

| regra | H: eixo errado | H: corte bom | V: eixo errado | V: corte bom |
|---|---|---|---|---|
| geometria (antes) | 534 (9,3%) | 61,6% | 0 (0,0%) | 94,7% |
| vale de tinta | 15 (0,3%) | 98,6% | 0 (0,0%) | 94,7% |

Os 534 têm cara: `it` (72), `is` (47), `ti` (43), `le` (23), `la` (21), `ll` (20). É a
lista de sintomas que o relato descreve.

**A coluna dos empilhados é a que impede a troca de um erro por outro.** Seria fácil
"consertar" cortando sempre em X e nunca mais errar o caso relatado; a coluna V mostra
que o eixo Y continua sendo escolhido onde ele é o certo, com o mesmo acerto de antes.

**O que faz funcionar não é olhar a tinta, é como medir o vale.** A fundura de um vale é
medida contra o **menor dos dois picos que o ladeiam**, e não contra o pico geral do
perfil. Sem isso o perfil por linha de `ba` — pouca tinta na faixa do ascendente, muita
embaixo — pontuaria como vale fundo, que é a mesma resposta errada de antes com mais
aritmética. Comparado com o pico de cima, que é o próprio ascendente, pontua zero.

Duas escolhas menores, ambas medidas: a margem que protege as pontas do box tem platô
entre 0,10 e 0,20 e piora a partir de 0,25 (fixada em 0,15); e binarizar o **recorte**
com Otsu sai igual a binarizar a página (15 erros contra 17) e poupa a folha inteira a
cada tecla.

O que sobra de erro é o pingo do `i` sobre o braço do `w`: em `wi` e `vi` há um vale
horizontal real embaixo do pingo. Quinze casos em 5.747.

#### O atalho no campo do caractere

O guard da F4.6 cala o Ctrl+D em todo campo de texto, e para a busca e o número da página
isso está certo — não há box por trás deles. O campo do caractere é o oposto: ele *é* o
box selecionado.

**A binding é do widget, não da janela, e isso não é estilo.** A tecla passa pelo widget,
pela classe e só então pelo toplevel, e a binding de classe do `Entry` trata `Control-d`
apagando o caractere à direita do cursor. Tratado na janela, o atalho dividiria o box **e**
comeria o que estava escrito, porque a de classe já teria rodado. No widget, com `"break"`,
nenhuma das outras roda.

#### A seta da lista

`►` numa coluna fixa, à esquerda da marca do léxico. **Não é enfeite do realce do
Listbox: é o que sobra dele.** O `tk.Listbox` nasce com `exportselection` ligado, então o
realce da linha some assim que outro widget toma a seleção do sistema — e é o que acontece
a cada `char_entry.select_range`, isto é, a cada Tab e a cada Enter do fluxo de revisão.
Quem estava digitando ficava sem saber qual caractere estava editando.

`▶` (U+25B6) é o desenho óbvio e **não existe na Consolas** — medido, não suposto: o Tk
não avisa, cai numa fonte de reserva que não é monoespaçada, e a coluna sai do prumo.
`►` (U+25BA) está lá. É o mesmo defeito do `·` da SPEC §4.2 e dos NAGs que nenhuma fonte
desenha (SPEC §7.1), e o teste que o trava mede a fonte em vez de decorar a resposta.

**O custo, dito sem enfeite: a F4.4 deixa de valer zero.** A seta mora no texto da linha,
então andar de box reescreve a linha que perdeu a seta e a que ganhou — seis operações de
lista por tecla, contra as 2.000 que a F4.4 existe para não deixar voltar. O teste que
afirmava "zero" passou a afirmar o teto novo, com o número escrito.

### F4.8 — O rótulo do box responde `?` ao `⩲` — CONCLUÍDA

Relatado pelo usuário: digitado o `⩲` no box, o retângulo amarelo logo abaixo dele — o
rótulo que mostra o caractere lido — exibe uma interrogação. Em toda a volta o símbolo
aparece certo: na lista lateral, no campo Caractere, no botão da barra rápida.

**Concluída em 2026-08-07.**

#### Não era o caractere: era o negrito

A primeira suspeita — o `⩲` não estar chegando ao box — se descarta em uma linha: o
`canvas_view` só escreve `?` quando `b.char` está vazio, e nesse caminho ele está com o
U+2A72 gravado. O que a tela desenha é outra coisa: **o retângulo com "?" dentro, que é
como o Tk mostra glifo ausente**. Parece um ponto de interrogação a 12 pt.

E aí vem o que faz o defeito ser só deste rótulo. O Tk tem fonte de reserva: pedir `Arial`
e mandar desenhar um `⩲` normalmente funciona, porque ele procura o glifo em outra
família. **No peso negrito ele desiste.** Medido dentro do app, num `Canvas` e num `Label`,
com o mesmo tamanho e as mesmas famílias:

| família | peso normal | negrito |
|---|---|---|
| Arial | `⩲` | retângulo |
| Consolas | `⩲` | retângulo |
| Segoe UI | `⩲` | retângulo |
| Segoe UI Symbol | `⩲` | `⩲` |

São seis dos 23 da barra rápida que caem assim: `⩲`, `⩱`, `∓`, `⇄`, `⌓` e `⨀` — os que só
uma fonte de símbolos desenha. Os outros 17, `±` e `∞` inclusive, a `Arial` tem por conta
própria e nunca dependeram da reserva. É por isso que a lista lateral (`Consolas 9`), os
botões e o campo Caractere sempre mostraram o símbolo certo: são todos peso normal. O
rótulo do box era o único negrito da interface que mostra um NAG.

#### O conserto

`canvas_view.FONTE_ROTULO` passa a pedir `Segoe UI Symbol` — a mesma família que o
`dialogo_diagrama` usa nas peças e que `resolve_chess_font` escolhe para o PDF, e a única
das quatro que atravessa o negrito. O tamanho e o peso do rótulo não mudam.

O teste mede em vez de decorar, como o dos NAGs e o do `►` da F4.7: pega a família que
`FONTE_ROTULO` declara, acha o arquivo dela no disco e pergunta ao `missing_glyphs` se ela
cobre os 23 símbolos da barra. Família nova sem medição é falha com o motivo escrito, não
caixa vazia descoberta pelo usuário — o defeito do `·` da SPEC §4.2 outra vez.

### F4.9 — Depois do Ctrl+D, o cursor não estava no campo — CONCLUÍDA

**Concluída em 2026-08-10.** Pedido do usuário: *"quando uso Ctrl+D para dividir um box
seria interessante que a caixa de caracteres receba o foco, assim posso digitar a letra
imediatamente sem ter que fazer clique de mouse"*.

`split_box` devolve as duas metades **sem char nenhum** — o passo seguinte a dividir é
sempre digitar. O atalho existe para não tirar a mão do teclado, e terminava obrigando ao
mouse.

**Metade já estava feita, e é o que explica o defeito.** A F4.7 pôs o foco no campo, mas
na *binding* `_on_key_split_no_campo` — o Ctrl+D disparado **de dentro** do campo. A
outra rota, `_on_key_split_safe`, é a do canvas e da lista, que é justamente onde a mão
está depois de escolher o box; e a terceira, o item de menu "Dividir box selecionado",
não passava por binding nenhuma. Três rotas para a mesma ação, uma delas com o foco certo.

O foco passou para `split_selected_box`, que é a ação: quem divide leva o cursor junto,
venha o comando de onde vier. A binding do campo ficou só com o `"break"`, que continua
sendo a razão de ela existir — sem ele a binding de classe do `Entry` apagaria o
caractere à direita do cursor além de dividir.

**No modo digitação o foco não se mexe**, pela mesma regra do Tab (F3.5): lá quem recebe
as teclas é a janela, e tirar o foco do canvas desligaria o modo na prática — o oposto do
que o pedido queria.

Cobertura: `tests/test_f47_corte.py`, 4 testes novos, 2 deles falham no código anterior.
Os outros dois guardam o modo digitação e o caso sem box selecionado.

---

## F5 — Higiene do código

### F5.1 — Código morto (7 arquivos, 211 linhas) — CONCLUÍDA

| Arquivo | Situação |
|---------|----------|
| `ui/sidebar.py` | Nunca importado. Ainda chama `controller.apply_char(c)` com assinatura errada |
| `ui/menu_bar.py` | Nunca importado — menu está inline em `main_window` |
| `ui/status_bar.py` | Nunca importado (e faz falta, ver F4.2) |
| `core/opencv_autobox.py` | Nunca importado — **e tem a melhor binarização do projeto** (F1.5) |
| `core/box_io.py` | Nunca importado. Formato de 5 campos, **incompatível** com o de 6 campos usado em `main_window` |
| `core/image_loader.py` | 6 linhas, nunca importado |
| `core/tesseract_utils.py` | Nunca importado |

`box_io.py` era o mais perigoso: dois formatos `.box` incompatíveis convivendo no mesmo
projeto. Quem usasse o módulo errado leria lixo.

**Aplicada em 2026-08-03.** Os 7 arquivos foram removidos; 211 linhas a menos. Os 15
módulos restantes importam, os 11 testes passam e o fluxo completo do editor continua
rodando sobre a página real.

Ao executar, dois deles se revelaram piores do que "mortos" — estavam **quebrados**, e
a recomendação anterior da SPEC (§9.2, "ligar em vez de apagar") não se sustentava:

| Arquivo | O que apareceu ao conferir |
|---------|----------------------------|
| `ui/menu_bar.py` | chama `controller.load_box_dialog` e `controller.generate_autobox` — **métodos que não existem**. Quebraria se ligado |
| `ui/sidebar.py` | chama `controller.apply_char(c)` com um argumento; `MainWindow.apply_char` não aceita nenhum |
| `ui/status_bar.py` | é um `tk.Label`; a F4.2 precisa de algo que comporte um `ttk.Progressbar`, ou seja um `Frame` |
| `core/image_loader.py` | devolve RGB; o app trabalha em grayscale (`'L'`) em todo lugar |
| `core/tesseract_utils.py` | tinha `menu_bar.py` como único consumidor — caiu junto |

Nada foi perdido: o histórico guarda tudo. O Otsu do `opencv_autobox.py`, que a F1.5
vai querer, sai com `git show 6a4b7a1:core/opencv_autobox.py`.

Fica pendente a consolidação do formato `.box` num módulo próprio (SPEC §2.3) — a F5.1
removeu o leitor divergente, não unificou o que sobrou.

### F5.2 — Formato `.box` perde dados — CONCLUÍDA

`_save_box_to_path` (`main_window.py:709`) grava `ch[0]` — **trunca ligaduras
silenciosamente**. Um box marcado como `fi` é salvo como `f`. E `~` é usado como
marcador de vazio, então um `~` real vira vazio na volta.

**Concluída em 2026-08-04.** O formato passou a morar em `core/formato_box.py`,
com `ler`/`escrever` e as versões em memória (`ler_texto`/`escrever_texto`). Isso
também fecha a consolidação que a F5.1 deixou pendente: havia dois leitores
divergentes (`main_window._load_box_from_path` e `avaliacao_pagina.carregar_box`,
que separava por `" "` em vez de espaço em branco), e agora os dois chamam o
mesmo código. `carregar_box` ficou como reexportação para não quebrar quem já a
importava.

**Era um defeito a mais do que o item dizia.** Além da ligadura e do `~`, um box
cujo caractere é **espaço** deixava a linha com 5 campos, e o leitor descartava a
linha inteira (`if len(parts) < 6: continue`) — o box sumia sem aviso. É a
mesma classe de perda, e escapava pelo mesmo motivo: o primeiro campo era gravado
cru num formato separado por espaço.

O escape resolve os três de uma vez. Na escrita, `\`, `~`, espaço e tabulação
saem como `\\`, `\~`, `\s` e `\t`; o primeiro campo fica sem espaço em branco por
construção, e a linha sempre tem 6 campos. A string inteira é gravada, sem
`char[0]` — o Tesseract aceita mais de um caractere no primeiro campo (é assim
que ele próprio representa ligadura), então gravar `fi` é *mais* compatível com o
formato, não menos.

**Arquivo antigo continua lendo igual**, e isso foi verificado, não suposto: os
5.349 boxes de `Box/*.box` têm exatamente 6 campos, nenhum com barra invertida,
nenhum com `~`. Um `~` sozinho segue significando vazio, que é o que os arquivos
antigos queriam dizer. A ambiguidade do `~` real não tem como ser desfeita
retroativamente — só deixa de ser criada daqui em diante.

Cobertura: `tests/test_f52_formato_box.py`, 64 testes, quase todos na forma
`ler(escrever(x)) == x`.

### F5.3 — Sem testes — CONCLUÍDA

Nenhum teste automatizado. `test_chess_pdf.py` era um stub que imprimia "a sintaxe está
correta" e não testava nada — a função de teste estava comentada. `test_draw.py` e
`test_fonts.py` eram scripts manuais.

Os quatro bugs de F0.1 seriam pegos por um único teste que constrói um `BoxEntry` e
chama `update_sidebar`.

**Fechada pelas próprias fases, e não por um mutirão de testes.** Cada uma trouxe o
arquivo que trava o que ela decidiu — `test_f0_smoke.py` nasceu com 11 testes, dos quais 9
reprovavam na baseline, e daí em diante nenhuma fase entrou sem cobertura. São **1.031
testes** em 2026-08-08, `pytest` na raiz, 72 segundos. Os scripts manuais saíram na F5.4.

O padrão que se firmou no caminho vale mais que o número: **teste que mede em vez de
decorar**. `missing_glyphs` pergunta à fonte se ela desenha o símbolo em vez de guardar a
resposta (F4.8), `nags.sem_glifo` mede a cobertura na montagem do menu, e a guarda da base
de ocupação compara a sessão consigo mesma em vez de congelar um tamanho que cresce de
propósito (F7.5). Número congelado num teste vira ritual de atualizar número.

### F5.4 — Arquivos de desenvolvimento no repositório — CONCLUÍDA

`debug_imports.py`, `debug_runner.py`, `debug_simulation.py`, `debug_tk.py`,
`crash_log.txt`, `full_log.txt`, `test_image.png`, `test_emj.png`, `test_sym.png`,
`Novo Documento de Texto.txt`, `training_data_2/` (138 PNGs soltos, fora do padrão
de pastas por classe).

O projeto também ~~**não é um repositório git**~~ — passou a ser, no começo da F0.
Sem controle de versão, refatorar era apostar.

**Concluída em 2026-08-04.** Saíram 10 arquivos: os quatro `debug_*.py`,
`detect_fonts.py` (uma sondagem de PDF com a página 10 fixa no código),
`migrate_training_data.py`, os três `test_*.py` da raiz e o `Novo Documento de
Texto.txt`. Os logs, os PNGs de teste e o `training_data_2/` já estavam cobertos
pelo `.gitignore` desde a F0.4 — não estavam no repositório, estão só no disco de
quem desenvolveu.

Conferido antes de apagar, e não era formalidade: `appy.py` **é o ponto de
entrada da aplicação** e por pouco não entrou na lista pelo nome. O único
importador de qualquer um dos removidos era o `debug_runner.py`, que importava o
`appy` e saiu junto. `calibrar_modelo.py` e `medir_paginas.py` ficam: são as
ferramentas que produzem os números deste documento.

Dois eram pior que inúteis:

- **`migrate_training_data.py` tinha a própria cópia de `char_to_folder`**, do
  formato antigo, divergente da de `core/learner.py`. É a mesma classe de defeito
  que a F5.1 e a F5.2 removeram, e o estrago que essa função faz quando erra está
  registrado na F1.4: 127 amostras de `f7` treinando a classe `?` por meses.

- **`test_draw.py` quebrava o `pytest`.** Chamado da raiz, o pytest coletava
  `test_draw.py::test_font` — um script manual — e lia `font_name` e
  `output_name` como fixtures inexistentes. A coleta da raiz também custava 67
  segundos, contra 25 de execução em `tests/`. Entrou um `pytest.ini` com
  `testpaths = tests`, para a próxima raiz chamada `test_*.py` não refazer o
  estrago.

O que sobrou na raiz: `.gitignore`, `ROADMAP.md`, `requirements.txt`,
`requirements-dev.txt`, `pytest.ini`, o doc de substituição de glifos, `appy.py`,
`calibrar_modelo.py`, `medir_paginas.py` e `model_meta.json`.

O `requirements-dev.txt` é novo e fecha um buraco que ninguém tinha registrado: o
`pytest` não estava em arquivo nenhum. Quem clonasse o repositório não tinha como
saber o que instalar para rodar a suíte — e o `requirements.txt` é declaradamente
só de produção.

**Uma correção de fato, achada ao conferir a lista.** Este item descrevia o
`training_data_2/` como "138 PNGs soltos, fora do padrão de pastas por classe".
**Não é isso.** São 70 soltos mais **68 pastas de classe com 192.600 imagens**, no
formato certo — uma base *maior* que a `training_data/` (103 classes, 128.850). E
há indício de que os rótulos vieram do modelo, não de humano: o formato é o que o
`batch_extract_and_classify` grava, e a classe maior é `digit_1` (16.962) acima de
`lower_e` (16.090), quando em texto de livro o `e` domina com folga — excesso de
`1` é a assinatura do classificador confundindo `l`, `i` e `I`, a mesma confusão
medida na F3.6.

Nada no código lê a pasta, então ela é inerte. O risco é ela **parecer** serviço
pendente e alguém mesclá-la na base de treino: seriam 192 mil rótulos do próprio
modelo realimentando o treino, com os erros junto — a F1.4 mostra o estrago que
127 amostras mal rotuladas fazem. A decisão é de quem gerou os dados; até lá, fora
do treino e fora do repositório. Detalhes na SPEC §5.2.

---

## Ordem de execução

**Todos os itens de F0 a F12 estão concluídos** — a F9 fechou em 2026-08-06 com a F9.2, e
a F10 (texto em negativo) e a F11 (texto sobre trama) no mesmo dia. A ordem dentro da F9 foi a que o item mandava:
mediu-se primeiro quanto do erro era alcançável, e a contagem não encerrou a fase, mas
dimensionou-a — o dicionário do livro apaga 9,2% do alarme falso, não a maioria dele.

```
F0  desbloqueio      F0.1 BoxEntry   F0.2 fonte Unicode   F0.3 undo/redo
                     F0.4 requirements.txt

F1  reconhecimento   F1.1 cobertura de peças (a premissa do item estava errada)
                     F1.2 balanceamento (25.075:1)   F1.3 split de validação
                     F1.4 saneamento do dataset      F1.5 pré-processamento
                     F1.5b árbitro do corte          F1.6 ordem de leitura
                     F1.7 validação por legalidade   F1.8 mascarar diagramas
                     F1.9 calibrar a confiança

F2  saída de PDF     F2.1 PDF pesquisável   F2.2 remover Poppler
                     F2.3 relatório e dry-run   F2.4 perfis por fonte

F3  produtividade    F3.1 digitação contínua   F3.2 cor por confiança
                     F3.3 filtros e navegação  F3.4 autosave e recuperação
                     F3.5 atalhos              F3.6 aplicar aos semelhantes
                     F3.7 boxes por página     F3.8 custo do snapshot

F4  interface        F4.1 threads       F4.2 barra de status
                     F4.3 rolagem       F4.4 lista incremental
                     F4.5 aviso de não salvo (já estava feita)
                     F4.6 colisão de tecla

F5  higiene          F5.1 código morto  F5.2 formato .box
                     F5.3 testes        F5.4 limpeza de arquivos
```

**Onde a ordem mudou, e por quê.** A fila original punha F1.8 antes de F1.9, e a
F1.5b não existia. Três medições reordenaram tudo:

1. A **F1.1** mostrou que o limitador era segmentação, não o modelo: o
   classificador acerta figurina isolada com confiança 1,000, e os erros vinham de
   figurina fundida com a coordenada seguinte. Retreinar antes de arrumar a
   segmentação renderia pouco.
2. A **F1.7**, medindo a página real, mostrou que o separador da F1.5 partia o `N`
   em negrito e custava 4,9 pontos sozinho — daí a F1.5b, que não estava prevista.
3. A **F1.8** desceu na fila e encolheu: o item supunha que o tabuleiro viraria
   milhares de boxes de lixo, e medindo deu **um** box por diagrama.

**~~F1.7 depende de F3.2~~** — não dependia. A F3.2 gravou a confiança, mas a
confiança gravada não distinguia certo de errado, e a legalidade acabou fazendo o
trabalho sozinha.

**A ordem entre F1.9 e F1.5b acabou sendo a que importava, e por acaso.** A F1.9
mediu que a confiança do modelo **ordena** certo e errado bem (AUROC 0,89), mesmo
sem ter escala honesta. Sem esse número, a F1.5b não teria sido tentada: a leitura
que se tinha, vinda da F1.1, era "o modelo erra com confiança 1,000", o que fazia
a pontuação parecer imprestável para arbitrar qualquer coisa.

**O que continua valendo depois de tudo isto.** O gargalo de qualidade segue sendo
a segmentação, não o classificador. Nas 9 páginas rotuladas o pipeline dá 93,8 de
F1; o modelo, medido em recorte já segmentado, dá 99,8%. A distância entre os dois
números é o trabalho que sobrou, e ele é de detecção de caixa — nenhum retreino o
alcança.

**O custo que a F3.4 deixou em aberto foi fechado pela F3.8**, e a solução prevista
não era a certa: o problema não era a cópia ser integral, era ela ser profunda.
Trocar `copy.deepcopy` por tupla levou o snapshot de 18,15 ms para 0,24 ms numa
página de 2.000 boxes; um snapshot incremental teria rendido 0,02 ms a mais, com
estado próprio para errar.

**A dependência que travava o retreino saiu inteira, e o retreino foi feito.** F1.2 e
F1.3 estão prontas — o sorteio compensa o desbalanceamento, o número exibido é medido
em dados que o modelo não viu, e o checkpoint deixou de ser o ponto de maior
overfitting. `custom_model.pth` foi refeito em 2026-08-04: 99,83% no conjunto de
teste, contra nenhum número confiável antes.

---

## F6 — Saída de partidas

### F6.1 — Exportar PGN — CONCLUÍDA

**Concluída em 2026-08-04.** Estava em "fora de escopo"; subiu porque a F1.7 já tinha
construído quase tudo de que precisava. `core/pgn.py`, menu Ferramentas → "Exportar
partidas em PGN...".

O `analisar` já percorria o texto com um tabuleiro na mão, corrigia pela legalidade e
sabia onde uma partida começa. Faltava **guardar o que ele descobria**: `LanceLido`
declarava um campo `numero` que nunca era preenchido nem lido. Agora cada lance carrega
`numero`, `san` (o lance efetivamente empurrado), `partida` e `fen_antes`.

Medido nas 9 páginas rotuladas: partidas de **32, 27, 24, 20 e 12 lances**, com a
abertura do livro (`d4 Nf6 c4 c5 d5 b5 cxb5 a6`, o Benko) saindo certa em todas.

**O que sai é só a linha principal, e a regra que a define é o número da jogada.** Numa
variante o livro repete um número que já passou — "12.Re1 Qa5 12...Ra6; 12...Ra7;
12...Nb6 13.Qc2" traz o `12...` quatro vezes. Um lance entra se a jogada dele vier
depois da última aceita. É a mesma informação que o tipógrafo usou para o leitor humano
entender que aquilo era um desvio.

**O número sozinho não bastou, e o teste que mostrou isso vale registrar.** Em
`3.Bb5 a6 3...Nf6 4.Ba4 Nf6`, o `3...Nf6` era corretamente descartado — mas o
analisador seguia *de dentro* da variante, e o `4.Ba4` chegava com número de linha
principal tendo saído do outro ramo. `Ba4` é legal nos dois, então a validação por
legalidade não pegava: o PGN saía com sete lances, abria sem erro e estava errado.

**Um PGN errado que carrega é pior que um PGN curto.** Uma partida que abre no programa
de xadrez ninguém confere; ela vira fato. Por isso cada lance guarda a posição de onde
saiu (`fen_antes`), e a montagem só o aceita se essa posição for a que a repetição da
partida alcançou. Onde não for, a partida é cortada ali e o relatório diz por quê. No
exemplo, saem seis lances certos em vez de sete com um errado.

Não tentei reconstruir as variantes aninhadas dentro do PGN, embora o formato suporte. O
`analisar` navega variante rebobinando o tabuleiro para uma posição guardada, e essa
estrutura não sobrevive na lista de lances — remontá-la seria adivinhação, e uma variante
posta no ramo errado é pior que uma variante ausente, pela mesma razão de sempre: parece
certa.

Os cabeçalhos que a página não tem como saber ficam em `"?"`. **O nome dos jogadores
está na página**, mas lê-lo é reconhecer prosa, não notação — e um `White` errado é pior
que um `White` ausente, porque o programa o exibe como fato. O `Event` recebe o arquivo e
a página, que é verificável.

Cobertura: `tests/test_f61_pgn.py`, 36 testes. A maioria é sobre o que a exportação
**recusa** fazer, e todo PGN gerado é relido com o `python-chess` — um arquivo malformado
só aparece quando outro programa tenta abri-lo.

---

## F7 — Diagramas e desempenho

### F7.1 — Ler a posição dos diagramas — CONCLUÍDA

**Concluída em 2026-08-04.** `core/diagrama.py`, menu Ferramentas → "Ler posição dos
diagramas...". Estava em "fora de escopo" desde a spec v1.0.

**Os diagramas já estavam localizados, e ninguém tinha notado.** A F1.8 descarta
contornos grandes demais para serem caractere, e o tabuleiro sai como **um** contorno —
ele tem moldura fechada e `findContours` roda com `RETR_EXTERNAL`, então casas e peças
são contornos filhos e não são devolvidos. `localizar` só recolhe o que a F1.8 jogava
fora, filtrando por "quase quadrado" (um travessão também é descartado por tamanho, e
não é tabuleiro). Nas 9 páginas rotuladas: 25 diagramas.

**A grade é o recorte dividido por 8, e isso foi verificado, não suposto.** O padrão de
cores do tabuleiro é conhecido de antemão — casa (linha+coluna) par é clara — e serve de
prova: uma grade deslocada quebraria o xadrez das cores imediatamente.

#### O fundo, e a surpresa que ele deu

Medir tom absoluto não serve, e a razão só apareceu ao olhar os 25: **casa escura tem
dois desenhos diferentes** nestes livros. Cinza chapado no Kasparov, **hachura diagonal**
no Aagaard. A moda de uma casa hachurada é branca, e os quatro diagramas hachurados
saíam com "zero casas escuras" — 87,7% de acerto no padrão do tabuleiro, com a falha
concentrada neles.

O que resolve: para cada diagrama e cada cor de casa, o fundo é a **mediana pixel a
pixel** das 32 casas daquela cor. As vazias são maioria, então a mediana *é* a casa
vazia — chapada ou hachurada, tanto faz. Tudo mais trabalha sobre o resíduo
(`casa - fundo`). O limiar entre vazia e ocupada é de Otsu **por diagrama e por cor**:
com limiar global, casa hachurada vazia (resíduo até 60) passava à frente de peça em
diagrama chapado. Com o limiar local, a contagem ficou entre 12 e 28 peças nos 25 —
nenhuma impossível.

#### Duas correções óbvias que pioraram

Medido contra **128 casas transcritas à mão** (dois diagramas, com a grade de
coordenadas desenhada por cima para não errar de casa):

| variante | acerto por casa |
|---|---:|
| resíduo + HOG + legalidade (o de hoje) | **94,5%** |
| \+ canal de sinal para a cor da peça | 90,6% |
| detecção por energia de borda | 93,0% |

A primeira parecia certa: o HOG usa orientação módulo 180 e magnitude absoluta, logo
descarta o sinal, e torre branca virava torre preta. Dar-lhe o sinal por fora **subiu** os
erros de cor de 3 para 5. A segunda também: peça branca em casa clara quase some no
resíduo — é branca por dentro, traço fino em volta — e a borda a acha; mas troca 3
omissões por 4 falsos positivos.

**A métrica óbvia apontava para o lado errado.** A concordância com meus próprios rótulos
de agrupamento dava 98,1% para a variante com sinal, contra 94,7% para a que ficou. Ela
premia reproduzir o agrupamento, não acertar. Quem decidiu foi a legalidade da posição.

#### A legalidade arbitra, como na F1.7

Uma posição real tem exatamente um rei de cada cor, no máximo oito peões por lado,
nenhum peão na 1a ou 8a fila, no máximo dezesseis peças por cor. São restrições sobre a
posição **inteira** — mais fortes que as da F1.7, que valiam para um lance de cada vez.
`_arbitrar` troca a casa mais barata: a de menor diferença entre a pontuação da leitura
atual e a da que resolve. Leva de 17 para **24 dos 25** os diagramas cuja posição é
possível.

**A primeira versão desfazia a própria correção**, e um teste de três casas pegou: sem
rei branco, ela promovia a casa mais barata a `K`; na volta seguinte faltava o rei preto,
e a mesma casa era outra vez a mais barata — agora para virar `k`, porque acabara de
perder a pontuação original. Oscilava até o teto de voltas e devolvia a leitura inicial.
Cada casa resolvida passou a ficar travada.

#### O que isto não entrega, e a interface diz

**94,5% por casa são ~3,5 casas erradas em 64.** Uma posição com três casas erradas é
uma posição errada. E **passar nas provas de legalidade não é prova de estar certo**:
elas contam peças, não reconhecem bispo lido como peão — por isso o número que vale é o
das 128 casas transcritas, não os 24/25.

Daí o diálogo pôr o recorte impresso e a leitura **lado a lado, na mesma escala**,
marcando de vermelho o que a legalidade trocou e de laranja o que ficou duvidoso. Mesma
decisão da F3.6, mesmo motivo: o que o programa não tem como garantir, ele mostra.

Lado a jogar, roque e en passant não estão desenhados no tabuleiro. O FEN assume brancas
a jogar sem roque, e **avisa que assumiu** — a convenção não pode passar por leitura.

O modelo são 361 amostras rotuladas (`training_data_diagrama/`, gravadas como imagem
para poderem ser olhadas), HOG reduzido a 32 dimensões por PCA, voto de 3 vizinhos.
Banco completo e PCA-32 dão o mesmo acerto (94,5%) e o segundo ocupa 260 KB contra
2,55 MB. Rede neural não: são 361 amostras de dois livros, ela decoraria. As classes
magras são `B`, `Q` e `b`, com 7 a 11 amostras — são as que mais erram, e mais diagramas
ajudam essas primeiro. `treinar_diagrama.py` refaz o modelo.

Cobertura: `tests/test_f71_diagrama.py`, 47 testes.

### F7.2 — O k-NN deixa de custar 21 s por página — CONCLUÍDA

**Concluída em 2026-08-05.** Estava em "fora de escopo" como *"substituir o k-NN linear
por índice FAISS/KD-tree"*. **A primeira pergunta não era como acelerar, e sim se o elo
se paga** — a F1.5b ensinou a perguntar isso antes.

**Ele se paga.** Medido nas 9 páginas rotuladas: a rede fica abaixo de 0,8 (o gatilho do
k-NN) em 3,5% dos caracteres; nesses 366 casos difíceis, a cadeia com o k-NN acerta
88,5% contra 72,4% da rede sozinha — **59 caracteres a mais**. Ao contrário do separador
de glifos, este elo fica.

O que custava caro era a implementação:

| | antes | agora |
|---|---:|---:|
| carregar as referências | 141 s (a frio) | **0,26 s** |
| uma predição | 415 ms | **3,7 ms** |
| numa página de 2.000 caracteres | ~21 s | **0,25 s** |
| memória | 155 MB | 89 MB |

Três mudanças, e **nenhuma altera a resposta** — verificado contra a implementação
anterior em 200 consultas reais: mesmo caractere, diferença de confiança 0,000000.

- **86% das referências eram duplicata byte a byte** — 151.114 imagens, 21.823
  distintas. Terceira vez que este projeto encontra o número: o rascunho da F3.8, a
  `training_data_2` e agora a base principal. Texto impresso na mesma fonte e no mesmo
  corpo cai no mesmo PNG de 32×32.
- **A busca virou conta de matriz**, com `||a-b||² = ||a||² + ||b||² - 2a·b` e as normas
  pré-calculadas. O laço com `cv2.norm` por referência era o grosso dos 415 ms.
- **A matriz ficou em cache** ao lado da base, com impressão digital pela contagem de
  arquivos por pasta. Contar custa 0,2 s; olhar a data de cada arquivo custaria 5,2 s e
  só pegaria a mais um arquivo *substituído* sem mudar a contagem — que nada aqui faz.

**FAISS ou KD-tree não são precisos, e isso foi medido.** Reduzir para 32 dimensões por
PCA desce de 3,7 ms para 0,1 ms — mas muda a resposta em 4 de 200 consultas. A 3,7 ms
uma página gasta 0,25 s; não há o que comprar com uma dependência nova e uma
aproximação.

#### Dois defeitos calados que apareceram no caminho

**Ligadura nunca era aprendida.** A guarda do `learn` era `len(char) != 1`, então um box
marcado `fi` era descartado em silêncio — apesar de o `char_to_folder` ter um ramo
`ligature_*` para exatamente isso. Mesma família da F5.2, achada pelo mesmo motivo: ao
mexer no código, perguntar o que ele joga fora.

**Dezesseis imagens idênticas com rótulos diferentes.** `1`/`l` (4), `V`/`v` (3),
`W`/`w` (3), `'`/`,` (2), `0`/`o`, `4`/`d`, `P`/`p`, `N`/`♘`. É a medição da F3.6 na sua
forma mais dura: depois do recorte na moldura do glifo e do redimensionamento, o que
distinguia os dois caracteres **não existe mais**, e alguém rotulou o mesmo pixel de dois
jeitos. `dataset_check.rotulos_contraditorios` passou a reportar, como **aviso e não
erro**: nenhum treino melhora removendo um dos lados, porque os dois rótulos estão certos
para alguma ocorrência daquele desenho. Quem escolhe é o contexto, e isso é a F1.7.

Cobertura: `tests/test_f72_knn.py`, 35 testes.

### F7.3 — O metadado amarrado ao modelo que ele descreve — CONCLUÍDA

**Concluída em 2026-08-05.** Fecha o que a F1.3 deixou em aberto e a SPEC §5.5 descreve.

`model_meta.json` está no git e `custom_model.pth` não (`*.pth` é ignorado, são 2,5 MB
de binário). Quem clona recebe o metadado **sem** o modelo que ele descreve — e basta
aparecer um `.pth` de outra rodada, com o mesmo número de classes, para o par ficar
trocado.

**O estrago de um par trocado é calado.** `idx_to_char` traduz índice em caractere;
índices de outro treino apontam para as letras erradas. Nada levanta, nada avisa — o OCR
só passa a ler outra coisa. É a família do defeito da F1.4, em que 127 amostras treinaram
a classe errada por meses.

Contagem de classes diferente **já** falhava alto: `SimpleCNN(num_classes)` recusa pesos
de outro formato. O que faltava era **mesma contagem e ordem diferente** — exatamente o
que acontece ao acrescentar e remover uma pasta na mesma rodada, que é o cenário de quem
está mexendo na base agora.

O `model_meta.json` ganhou `schema_version`, `modelo_sha256` (SHA-256 dos pesos),
`classes_sha256` e `treinado_em`. Na carga, a impressão dos pesos é conferida.

**Recusar, e não avisar.** Um par trocado devolve caracteres errados sem sintoma; "seguir
com aviso" na prática é seguir. Já um metadado **anterior** a esta fase carrega
normalmente, com aviso: ele funcionava antes, e recusá-lo agora quebraria quem já tem um
modelo treinado sem ter feito nada de errado.

A mensagem passou a dizer o motivo. Antes qualquer falha virava *"Modelo neural não
encontrado"* — que, num par trocado, manda o usuário procurar um arquivo que está lá.

Cobertura: `tests/test_f73_modelo.py`, 16 testes.

#### Uma hipótese do roadmap que a medição derrubou

Antes desta fase, medi o sinal que a F1.7 registrou para **distinguir linha principal de
variante** — o que resolveria os 5,2% de lances ambíguos e destravaria a F6.1, que hoje
corta a partida quando a leitura entra numa variante. O roadmap dizia: *"medida a
densidade de tinta por palavra, a principal fica em 0,52–0,64 e as variantes em
0,34–0,52"*.

Medido nas páginas rotuladas, usando a regra de número de jogada como rótulo (um número
que retrocede **é** variante), com 133 lances de linha principal contra 31 de variante:

| medida (normalizada pela página) | principal | variante | AUROC |
|---|---:|---:|---:|
| densidade de tinta | 1,006 | 0,965 | 0,570 |
| altura do caractere | 1,000 | 0,983 | 0,548 |
| largura do caractere | 1,000 | 1,000 | 0,577 |
| altura × densidade | 1,019 | 0,948 | **0,669** |

**Nenhuma separa** (0,5 é o acaso). Por página a densidade chega a 0,467 — abaixo do
acaso. O sinal existia na fatia em que foi medido originalmente e não generaliza.

Terceira vez que uma hipótese plausível deste projeto cai na medição, depois do separador
de glifos por projeção (F1.5b) e do canal de sinal para a cor da peça (F7.1). Fica
registrado para ninguém tentar de novo pelo mesmo caminho: **quem separa linha de
variante não é a tipografia.**

### F7.4 — O banco de vizinhos vira rede — CONCLUÍDA

Proposto pelo usuário: *"acho que pytorch pth é mais eficiente para reconhecer os
diagramas de xadrez"*. **Concluída em 2026-08-07.** O argumento contra estava escrito
no cabeçalho do `treinar_diagrama.py`, e é do tipo que se escreve sem medir:

> O modelo é um banco de vizinhos, não uma rede: são poucas centenas de amostras de
> dois livros, e uma rede treinada nisso decoraria.

#### O protocolo primeiro, porque é ele que muda a resposta

A base tem 833 amostras rotuladas em 90 diagramas de quatro procedências. Duas casas do
mesmo diagrama saíram do mesmo recorte, com a mesma fonte, a mesma digitalização e o
mesmo fundo estimado — deixar uma no treino e a outra no teste mede memorização, e é o
que o leave-one-out da F8.3 fazia. Ele mesmo avisava; **esta fase mediu o quanto**:

| protocolo | k-NN | rede |
|---|---:|---:|
| leave-one-out solto (o do relatório) | 93,5% | — |
| 5 folds agrupados por diagrama | 93,8% | 98,8% |
| **um livro inteiro deixado de fora** | **86,9%** | **98,0%** |

A terceira linha é a pergunta que o programa faz na prática: abro um PDF novo, ele lê?

**A vantagem da rede cresce no teste difícil**, de +5,0 para +11,1 pontos. É o contrário
do que a decoreba produziria — o argumento de 2026 estava exatamente ao contrário do que
os dados dizem.

Por livro:

| livro deixado de fora | n | k-NN | rede |
|---|---:|---:|---:|
| Yusupov, *Chess Evolution 1* | 345 | 83,5% | 97,7% |
| Aagaard, *GrandMaster Preparation* | 84 | 96,4% | 100,0% |
| Kasparov, *Dynamic Benko Gambit* | 47 | 78,7% | 97,9% |
| base original da F7.1 | 357 | 89,1% | 97,5% |

#### Não era o PCA, e isso foi verificado antes de trocar

Antes de propor um classificador novo, a pergunta barata: dá para tirar isso do k-NN
mexendo só nele? No mesmo protocolo de livro deixado de fora —

| variante do k-NN | livro novo |
|---|---:|
| PCA 32, k=3 (o de produção) | 86,9% |
| PCA 128, k=3 | 88,2% |
| PCA 256, k=3 | 88,5% |
| sem PCA, sobre o HOG cru, k=1 | **89,2%** |

O teto é 89,2%. O gargalo não é a redução de dimensão, é HOG mais vizinho mais próximo
como representação. O que o k-NN errava eram as peças de desenho detalhado — dama 80,8%,
cavalo 83,7%, dama preta 86,5% —, exatamente o que uma silhueta de gradientes borra.

#### A rede foi dimensionada pelo tamanho do arquivo

Decisão de produto, não de modelagem: o `.gitignore` manda `*.pth` para fora porque o
modelo de caracteres tem 2,6 MB, e o banco de vizinhos que a rede substitui tinha 231 KB
e **vinha versionado** — um clone novo lia diagramas sem baixar nada.

| rede | parâmetros | arquivo | livro novo |
|---|---:|---:|---:|
| `SimpleCNN` (a de 126 caracteres) | 620.300 | 2.423 KB | 97,8% |
| `RedeDiagrama` | 35.820 | 140 KB | **98,0%** |
| `RedeDiagrama` com média global | 24.300 | 95 KB | 81,4% |
| `RedeDiagrama` com metade dos canais | 12.156 | 47 KB | 96,0% |

A camada densa de 2.048 para 256 da `SimpleCNN` é 85% dos parâmetros dela e não paga em
12 classes de glifo impresso. A exceção nominal no `.gitignore` é o que mantém a
propriedade — o modelo gravado tem 152 KB.

**A terceira linha é a que ensina alguma coisa.** Trocar o achatamento por média global
economiza 11 mil parâmetros e derruba 16,6 pontos: onde a tinta está dentro da casa é
informação, e a média joga fora exatamente isso.

#### Três consequências que não estavam no pedido

1. **A temperatura da F1.9 passou a valer aqui.** A rede acerta 98% e diz 99,9% em quase
   tudo, e é dessa confiança que a janela de diagramas tira o laranja de "duvidoso" —
   sem calibrar, o laranja pararia de aparecer justamente quando fosse útil. Ajustada
   nos diagramas de teste (1,41 na base atual) e gravada no `.pth`. Não muda leitura
   nenhuma; muda o número exibido. Com ela, 6,6% das casas lidas ficam abaixo de 0,80.
2. **O árbitro da legalidade passou a custar em logaritmo.** "Quanto custa trocar esta
   casa" é razão entre evidências, não diferença: com a rede confiante, `0,9999 −
   0,0000001` empata com `0,999 − 0,001` em ponto flutuante e o "mais barato" viraria o
   primeiro índice da lista.
3. **O treino passou de ~2 s para ~40 s**, porque são duas redes por rodada — a que
   mede não vê os diagramas de teste, a que fica vê tudo. Medir na segunda seria medir a
   memória dela. O comando da janela ganhou progresso: quarenta segundos sem sinal de
   vida parecem travamento.

#### O que a troca NÃO conserta, e o número que prova

Nas 11 páginas rotuladas, 25 diagramas: **15** saem com posição possível antes do árbitro
(o k-NN fazia 17, e a diferença é ruído em 25) e **25** depois (o k-NN fazia 23).

A legalidade mede sobretudo a decisão vazia/ocupada, que é o Otsu de `_residuos` e não
mudou: um rei que ele não viu quebra a posição por mais certo que o classificador esteja.
O ganho da rede está em **qual peça é**, não em **se há peça** — e os 94,5% por casa da
F7.1 incluem as duas coisas, então não viram 98% por troca de classificador.

**Um caso conferido à mão, porque ele mostra o defeito inteiro.** O primeiro diagrama da
página 0013 do Kasparov sai com FEN legal, aceito pelo `python-chess`, sem nenhuma casa
arbitrada — e tem **duas casas erradas**, nenhuma delas do classificador:

- **f5 tem um peão branco e a leitura diz vazia.** Peão branco em casa clara é o caso
  que a F7.1 já registrava: é branco por dentro, traço fino em volta, e quase some no
  resíduo.
- **h2 está vazia e a leitura põe um peão.** O falso positivo simétrico, na casa escura.

É a demonstração mais limpa que este projeto tem do aviso da F7.1: **passar nas provas de
legalidade não é prova de estar certo.** Aqui as provas passaram todas — um rei de cada
cor, contagem plausível, nenhum peão na ponta — porque a omissão e o falso positivo se
compensam na contagem. Quem quiser o próximo ganho de verdade ataca o Otsu de ocupação,
não o classificador.

#### O que muda no relatório de treino

O aviso "uma correção é um voto em três; com duas a casa vira" era a aritmética do k-NN,
medida numa página real. Com a rede não há vizinho: o gradiente de uma amostra entre 833
é diluído por 80 épocas de todas as outras. O relatório passou a dizer o que vale agora —
uma correção isolada só muda a leitura de uma casa que já estava em dúvida, e o que move
o ponteiro é conferir diagramas inteiros das classes magras. Um teste reprova se o texto
do k-NN sobreviver à troca.

Cobertura: `tests/test_f71_diagrama.py` e `tests/test_f83_treino_diagrama.py`, 92 testes.

### F7.5 — O Otsu de ocupação — CONCLUÍDA

A F7.4 terminou dizendo onde estava o próximo ganho, e o usuário mandou ir:
**quem decide se a casa tem peça não é classificador nenhum, é um limiar de
Otsu sobre a força do resíduo.** Ele sobreviveu intacto desde a F7.1.

**Concluída em 2026-08-07.**

#### O que faltava era gabarito, não ideia

Seis anos de fase e nenhum número media essa decisão. Os 94,5% por casa da F7.1
misturavam ocupação e identidade; a F7.4 melhorou só a segunda e disse isso.
Sem separar as duas, qualquer conserto aqui seria palpite.

Então a primeira metade desta fase foi transcrever à mão as **1.600 casas** dos
25 diagramas rotulados, com a grade de coordenadas desenhada por cima do recorte
ampliado — o método da F7.1, em 25 diagramas em vez de 2. Está em
`tests/dados/ocupacao_diagramas.txt`, 25 linhas de 64 caracteres, e é o primeiro
gabarito de ocupação que este projeto tem.

**A transcrição foi conferida contra uma segunda opinião, e as duas se
corrigiram.** Ao resolver os conflitos que `conferir` levantou, descobriu-se que
os arquivos `diag_NN_casa.png` da base da F7.1 são **estes mesmos 25 diagramas**,
numerados na mesma ordem — isto é, uma rotulagem independente das mesmas casas.
Cruzando:

- 4 conflitos, todos reais. Três eram erros de digitação meus (um `.` no lugar de
  um `#`, que desloca a fileira inteira); um era da base — `diag_13_b2.png`
  rotulado `P` numa casa que está **vazia à vista**, um falso positivo do Otsu
  que o "conferi este diagrama inteiro" gravou como peça.
- Depois das correções, **zero** casas em que a F7.1 diz ocupada e a transcrição
  diz vazia. E 195 no sentido contrário — peças que nunca viraram amostra.

#### A medição, e a linha que mudou o rumo

| decisão | omissões | falsos+ | acerto |
|---|---:|---:|---:|
| Otsu (F7.1) | 86 | 38 | 92,25% |
| **melhor limiar possível, com o gabarito na mão** | — | — | **98,25%** |
| rede dedicada | 6 | 5 | **99,31%** |

**A linha do meio é a que mandou trocar de abordagem em vez de afinar a que
havia.** O oráculo — o melhor corte por diagrama e cor de casa, escolhido com os
rótulos — já ficava 6 pontos acima do Otsu. A *medida* não era o problema; achar
o corte **sem rótulo** era. Foi o que evitou a semana que se gastaria inventando
uma força de resíduo melhor.

Nenhuma regra sem supervisão fecha essa distância:

| regra de limiar, sobre a mesma medida | acerto |
|---|---:|
| Otsu (o de hoje) | 92,25% |
| Otsu no logaritmo | 92,06% |
| mediana + 2 MAD | 93,06% |
| maior salto relativo | 93,56% |
| limiar fixo sobre medida adimensional (força/contraste) | 93,44% |

E trocar a medida também não: das nove testadas (força central, tinta aberta,
maior componente conexo, desvio, tinta preenchida, mínimo…), a melhor tem AUROC
0,9598 contra 0,9338 da atual — nada perto do que falta. Uma regressão logística
sobre cinco delas chega a 97,8%. A rede sobre o resíduo chega a 99,3%.

**Os piores diagramas são os de hachura**, e a explicação fecha: o tracejado
diagonal corre contínuo pelo tabuleiro, então cada casa o pega numa fase
diferente, a mediana das 32 sai borrada e toda casa vazia tem resíduo alto.

#### Duas redes, e a medição é que separou

A primeira tentativa foi uma classe a mais na rede da F7.4 — "vazia" como
décima terceira. Medido na mesma população e no mesmo protocolo agrupado por
diagrama:

| desenho | omissões | falsos+ | acerto |
|---|---:|---:|---:|
| 13 classes (peças + vazia) | 13 | 22 | 97,81% |
| **rede binária dedicada** | 6 | 5 | **99,31%** |

Três vezes mais erro na versão "simples". Duas redes, então — e as bases também
são duas, o que **não** é arrumação:

| base de treino da rede de ocupação | acerto |
|---|---:|
| casas transcritas (vazias e ocupadas do mesmo tabuleiro) | **99,31%** |
| casas vazias + as 833 amostras de peça que já existiam | 91,88% |

Quase o Otsu de volta. O motivo é o que torna esta fase generalizável: **as peças
da base de identidade são justamente as que o Otsu já achava.** Treinar nelas
ensina a rede a concordar com o limiar que ela veio substituir. A rede só aprende
a achar o que o leitor perde se vir as casas que o leitor **perdeu** — e é por
isso que a base de ocupação precisa de tabuleiro inteiro conferido, não de
recortes de peça.

Tamanho da base, medido: o platô começa em 16 amostras por classe por diagrama
(634 amostras, 99,31%), e abaixo disso cai — 6+6 dá 99,06%. A base foi aparada
para 787 amostras, 3,8 MB, escolhidas espaçadamente na ordem das casas (as
primeiras seriam as fileiras de trás, que são as mais limpas).

#### O ciclo da F8.3 ganha o que lhe faltava

`colher` gravava só casa ocupada, e o motivo estava escrito: *"o modelo tem 12
classes de peça e nenhuma de casa vazia; corrigir um falso positivo conserta o
FEN e não tem onde ser aprendido"*. Era o **buraco mais caro do ciclo** — o Otsu
inventava 38 peças e perdia 86, e nenhuma dessas 124 correções chegava a modelo
nenhum. Agora o "conferi este diagrama inteiro" grava as 64 casas na base de
ocupação, ocupadas e vazias.

#### A guarda da base parava de valer no primeiro diagrama conferido

A base de verdade precisa de guarda contra o que a própria suíte pode escrever
nela sem querer: um teste de diálogo que esquecia de apontar `PASTA_OCUPACAO`
para uma pasta temporária gravava 64 casas sintéticas a cada execução, e nada
acusava — amostra a mais não quebra treino nenhum, só envenena o modelo devagar.
É o defeito da F1.4 na forma que esta fase podia criá-lo.

**A guarda existia e estava escrita como contagem fixa, `(400, 387)`.** É a
medida errada, e o parágrafo acima diz por quê: a base **cresce de propósito**, a
cada diagrama que o usuário confere. Com 25 diagramas conferidos ela já não é
787, e a suíte reprovava por trabalho bem feito. Pior: o conserto de rotina
virava "atualizar o número", que é justamente o gesto que deixaria passar a
gravação acidental. Aconteceu — 1.720 vazias e 1.116 ocupadas contra as 787
congeladas, todas de páginas de verdade.

**O que a guarda passa a comparar é a sessão consigo mesma**: os nomes de
arquivo que a suíte encontrou ao começar contra os que deixou no fim. Nomes, e
não contagem, porque gravar uma amostra e apagar outra fecharia a conta.

> **Esta versão durou uma execução, e o defeito dela é instrutivo.** Ela reprovou
> na primeira suíte rodada com o **app aberto**: o usuário conferiu dois diagramas
> do Yusupov enquanto os testes rodavam, 128 casas foram para a base, e a guarda
> apontou para trabalho legítimo feito noutro processo. Comparar a pasta não
> distingue quem escreveu. A guarda de hoje embrulha `treino_diagrama.gravar`
> durante a sessão e **recusa** quem tenta escrever na base de verdade — vigia o
> processo, não o disco, e protege o dado em vez de relatar o estrago depois de
> feito. Só passa por esse caminho quem esqueceu de redirecionar a pasta.

**Ela mora no `conftest`, e não num teste, por causa da ordem.** O pytest roda
os arquivos em ordem alfabética, e quem mais mexe na base —
`test_f83_treino_diagrama.py` — vem depois do `test_f75_ocupacao.py`. Um teste
no meio da fila só cobriria a parte da suíte que já passou. O teste continua
existindo, com o nome que se procura, como sinal cedo; quem fecha a conta é a
sessão. Conferido plantando uma amostra a partir de um teste: a guarda reprova e
diz o nome do arquivo.

#### O resultado, ponta a ponta

| | antes (F7.4) | agora |
|---|---:|---:|
| ocupação, em diagrama fora do treino | 92,25% | **99,31%** |
| posição possível **sem** o árbitro | 15/25 | **23/25** |
| posição possível com o árbitro | 25/25 | 25/25 |

**A linha do meio é a que diz que a leitura melhorou de verdade**, e não que o
árbitro passou a remendar mais. E o caso concreto que a F7.4 registrou como o
limite dela — o primeiro diagrama da página 0013, com um peão branco em f5 que a
leitura não via e um que ela inventava em h2 — sai agora com as duas casas
certas, e sem nenhuma arbitrada.

O que sobra naquele diagrama é uma torre preta em e1 lida como branca: erro de
**identidade**, que é a outra rede.

Cobertura: `tests/test_f75_ocupacao.py`, 16 testes.

### F7.6 — Seis diagramas na página, doze anunciados — CONCLUÍDA

**Concluída em 2026-08-10.** Relato do usuário, com as páginas na mão: no *Chess
Evolution 1* do Yusupov, a página 220 saiu com os três diagramas certos e a 221 — que
tem **seis** — foi anunciada com **doze**.

Reproduzido de primeira. As doze caixas são os seis tabuleiros de 577×579 e mais seis de
**35 a 44 px**, que são caracteres soltos.

**A causa é uma régua que o projeto já sabia ser instável, no único lugar que ainda a
usava.** `localizar` tirava o tamanho mínimo da mediana simples das alturas dos boxes:

| | pág 220 | pág 221 |
|---|---:|---:|
| boxes na página | 1.746 | 632 |
| `preprocess.escala_de_texto` | 30 | 57 |
| **mediana simples das alturas** | 19 | **5** |
| mínimo daí (6 caracteres) | 114 px | **30 px** |

A 221 é quase só diagrama: quatro linhas de texto e seis tabuleiros. A maioria dos
contornos passa a ser o **hachurado de dentro das casas**, de 5 px — e a mediana mede a
trama, não o texto. Com o mínimo em 30 px, um caractere de 39 entra como tabuleiro.

É exatamente a armadilha que `descartar_blocos_nao_texto` documenta desde a F11, com a
saída escrita no próprio docstring dela: *"quem tem a imagem passa
`preprocess.escala_de_texto`, que pesa por tinta e não desaba"*. `ler_pagina` tem a
imagem e não passava; `localizar` era o último lugar do pipeline decidindo por mediana
simples. Agora passa, e vale para os **dois** filtros — o descarte de não-texto também
era refeito ali sem escala, e com mediana 5 ele jogava fora 58 boxes de texto legítimo.

**O saldo, medido em 41 páginas seguidas (200 a 240):** 142 "diagramas" viram **90**.
Doze páginas mudam, e em todas o que sai tem de 36 a 64 px:

| página | antes | agora | o que sumiu |
|---|---:|---:|---|
| 221, 222, 232, 202, 203 | 11–12 | 6 | 5 ou 6 caracteres soltos |
| 205, 216, 236 | 8, 4, 5 | **0** | a página não tem diagrama nenhum |
| 227 | 3 | 2 | um contorno de 58×64 |

As três que foram a zero são o caso que mais incomoda e o mais claro: elas não têm
tabuleiro, e o programa anunciava oito.

**Nada de verdade se perdeu, e isso é medido e não argumentado.** Em 88 páginas espalhadas
pelo livro inteiro (de 3 em 3), a mudança **removeu 72 caixas e não acrescentou nenhuma**:

| maior lado da caixa removida | quantas |
|---|---:|
| até 49 px | 70 |
| 50 a 99 px | 2 |
| **acima de 100 px** | **0** |

A maior que saiu tem 62×67 px. Os tabuleiros deste livro têm 577. Não há como a mudança
ter custado um diagrama — a faixa onde eles vivem não foi tocada.

Cobertura: `tests/test_f71_diagrama.py`, 4 testes novos, 3 deles falham no código
anterior. Um monta a página que é quase só diagrama — seis tabuleiros, o miudinho das
casas e quatro linhas de texto — e cobra que sem a escala o mínimo desabe, que é a única
forma de o teste continuar valendo se alguém mexer na régua de novo.

---

## F8 — Texto girado e diagramas conferíveis

Três pedidos da mesma conversa, e eles não são o mesmo trabalho: o primeiro é de
reconhecimento, os outros dois são de interface e de dados. Ficam em três fases
que se entregam sozinhas, na ordem em que foram pedidos — a F8.1 não depende das
outras duas, e a F8.3 só faz sentido depois da F8.2, porque é a correção feita
lá que vira amostra aqui.

| fase | o que entrega | depende de |
|---|---|---|
| **F8.1** | o texto impresso na vertical é lido, e para de estragar o texto em volta | — |
| **F8.2** | o diagrama abre numa janela com tabuleiro **editável** | F7.1 |
| **F8.3** | a correção do tabuleiro vira amostra, e o modelo de diagrama retreina | F8.2 |

### F8.1 — Ler o texto impresso na vertical — CONCLUÍDA

**Concluída em 2026-08-05.** `core/vertical.py`, `BoxEntry.angulo`, e a marcação
entra sozinha na geração de boxes quando há modelo carregado.

**O programa lia esse texto errado sem dizer que leu.** Rótulos como *"Analysis
diagram"* saem impressos girados 90° ao lado do diagrama. Medido com o modelo em
uso, nos 10.606 caracteres rotulados à mão:

| recorte | acerto |
|---|---:|
| de pé (linha de base) | **94,40%** |
| o mesmo, girado 90° | **8,38%** |
| girado e desgirado | 94,40% |

Os 8,38% não são "não leu": são outra letra, com confiança de leitura normal e
origem `neural` como qualquer outra. A terceira linha diz o resto: **girar por
múltiplo de 90° é transposição**, não reamostragem — as respostas voltam
idênticas uma a uma (100,00%), então o custo do conserto é zero e o que faltava
era só saber para que lado girar.

#### O estrago não parava no rótulo

Colando uma linha real de 17 caracteres, girada, na margem de uma página real —
mesma fonte, mesmo scan:

- **A segmentação colava a pilha.** O `merge_vertical_boxes` funde caixas
  alinhadas em x e encostadas em y, que é exatamente a descrição de duas letras
  vizinhas de um rótulo girado: 17 caracteres saíam como **7 boxes**.
- **A ordem de leitura espalhava.** Cada letra da pilha cai numa linha de texto
  diferente, e o rótulo entrava letra a letra no meio de **6 linhas** do
  parágrafo vizinho.

Ponta a ponta, com o pipeline de produção e o mesmo classificador, em três
páginas com uma linha real colada girada:

| | boxes | caracteres certos (de 47) |
|---|---:|---:|
| antes | 7, 10 e 2 | **1** |
| depois | 16, 13 e 15 | **34** |

#### A geometria propõe, o classificador dispõe

Geometria sozinha não separa um rótulo girado de uma **coluna de primeiras
letras de parágrafo**: as duas são caixas empilhadas dividindo a faixa de x. O
que as separa é o vão — entre letras ele é de espaço de letra; entre linhas, de
entrelinha. `candidatos` recolhe pilhas plausíveis e **quem decide o ângulo é o
classificador**, pela confiança média da pilha inteira. É o critério da F1.5b,
onde o árbitro confirma cada corte, e o da F7.1, onde a legalidade arbitra.

Medido em 1.312 linhas reais simuladas nos quatro ângulos: o argmax da média
acerta o ângulo impresso em **99,7%**, com folga mediana de 0,074 sobre o melhor
concorrente. A única falha é um empate de 0,001.

**Sem árbitro a fase não faz nada**, e isso é a lição da F1.5b levada a sério:
lá, separar glifo colado sem quem confirmasse custava 2,3 pontos de F1. Marcar
ângulo por geometria pura teria o mesmo defeito, e o dano seria maior — mexeria
em texto normal para acertar o raro.

#### O limiar que a medição escolheu

O vão máximo entre letras da pilha foi varrido em 81 páginas reais contra a
linha colada. É um joelho, não uma preferência (a contagem é com o piso de
quatro caixas, que era o de então):

| vão (em alturas medianas) | pilhas propostas em página normal | a pilha colada |
|---|---:|---|
| 0,7 | 25 | sai partida (9 de 16 caixas) |
| **0,8** | **103** | **sai inteira** |
| 0,9 | 554 | inteira |

E aí apareceu o motivo de a pilha mínima ser **cinco caixas e não quatro**: com
quatro, essas 81 páginas — que não têm texto vertical nenhum — davam **5 pilhas
aceitas por engano**, e as cinco eram **colunas de peças dentro do diagrama**.
Uma coluna de quatro peças é alta, estreita, encostada e de vão zero: passa em
toda a geometria, e com quatro amostras a média da confiança ainda é ruído.

#### A varredura completa achou o falso positivo que importava

Nas 81 páginas de amostra, nenhuma candidata de cinco ou mais era aceita. Nas
**322** páginas do livro inteiro, três eram — e as três merecem estar aqui,
porque duas não são o que a amostra sugeria:

| o que era | caixas | dano |
|---|---:|---|
| coluna de peças dentro do diagrama | 5 | nenhum: não é texto |
| **primeiras letras de linhas seguidas** | 5 | 5 caracteres reais lidos deitados |
| **primeiras letras de linhas seguidas** | 9 | 9 caracteres reais lidos deitados |

O caso que a fase precisava recusar por construção — a coluna de letras iniciais
de linhas de uma variante apertada — estava passando. **A diferença entre as
duas coisas é estrutural, e não estatística: letra de linha horizontal tem
vizinha ao lado; letra de linha vertical tem vizinha em cima e embaixo.** Uma
pilha em que mais da metade das caixas tem outro caractere encostado ao lado não
é palavra girada.

Só conta vizinha do tamanho de um caractere, e isso não é detalhe: o box do
diagrama fica encostado no rótulo que esta fase existe para ler, e contá-lo como
vizinho recusaria justamente o caso alvo.

Com a regra, nas mesmas 322 páginas:

| | candidatas propostas | aceitas por engano |
|---|---:|---:|
| antes | 116 | 3 |
| depois | **7** | **0** |

E a linha colada continua saindo inteira e lida — o que a regra tirou foi só
texto normal que nunca deveria ter sido proposto.

**Página sem texto vertical sai idêntica.** Não "parecida": comparando a lista
de boxes gerada com e sem a fase, em 11 páginas reais com o modelo carregado, os
caracteres e as quatro coordenadas batem um a um. É o que se espera de uma fase
que só age sobre o que ela mesma marca — e é o único jeito de afirmar que ela
não cobra nada de quem não tem rótulo girado.

#### O ângulo é do texto, e vai junto até o PDF

`BoxEntry.angulo` são graus anti-horários do **texto impresso** — a convenção do
PDF, e não a do recorte: 90 sobe (lê-se de baixo para cima), 270 desce. Quem
classifica pede o glifo de pé a `vertical.endireitar`, num lugar só.

O ângulo atravessa tudo o que guarda box: `as_state` (desfazer), o rascunho de
autosave e o `.box`, que ganhou um **sétimo campo** — escrito só quando o ângulo
não é zero, de modo que uma página sem texto girado grava o arquivo byte a byte
igual ao de antes. Na saída, a camada invisível do PDF entra girada, com o
`rotate` do PyMuPDF conferido contra a direção do texto extraído (0,-1 para 90°)
e não suposto. E a base de referência do k-NN aprende o glifo **de pé**: guardar
um 'A' deitado sob o rótulo 'A' envenenaria a vizinhança para todo mundo, e o
aprendizado é justamente a via por onde uma correção do usuário entra.

No canvas, um traço marca o lado que é o topo do glifo. Sem ele, a leitura de um
rótulo vertical — que sai de baixo para cima — pareceria embaralhada sem motivo.

#### O que esta fase não entrega

**180° não é candidato.** Livro impresso não traz linha de cabeça para baixo, e
cada ângulo a mais é uma chance a mais de virar uma pilha curta pelo lado
errado. A medição mostra que o classificador *saberia* separá-lo (99,7% também):
ele fica de fora por não existir no material.

**Texto em ângulo que não seja múltiplo de 90° continua sem leitura.** Nada aqui
gira por interpolação, e não deve: seria reamostrar o glifo antes de
classificá-lo, que é o oposto do que a terceira linha da primeira tabela
comprou.

**A medição é de material montado, não colhido.** As páginas deste repositório
não têm texto vertical; o que existe é a linha real colada girada. O ângulo, a
fonte e o scan são reais, o *lugar* é montado — e um rótulo com espaçamento
muito diferente pode partir a pilha em duas, caso em que saem duas pilhas
seguidas em vez de uma.

Cobertura: `tests/test_f81_vertical.py`, 48 testes. `medir_vertical.py` refaz as
quatro medições acima.

### F8.2 — O diagrama vira uma janela com tabuleiro editável — CONCLUÍDA

**Concluída em 2026-08-05.** `core/tabuleiro_edicao.py`, `ui/dialogo_diagrama.py`
reescrito, e um botão **Diagramas...** na barra do editor.

**Mostrar sem deixar corrigir devolvia o trabalho para fora do programa.** A F7.1
põe o recorte impresso ao lado da leitura e marca o que a legalidade trocou —
mas 94,5% por casa são ~3,5 casas erradas em 64, e quem via um bispo lido como
peão copiava um FEN errado ou desistia.

O que entrou:

- **Um botão, e não só o menu.** Ler diagrama é ação de página; Ferramentas
  guarda configuração. O menu continua onde estava.
- **Clicar seleciona; quem escreve é a tecla ou a paleta.** Um clique que já
  apagasse a casa faria da conferência um campo minado. Com uma peça escolhida
  na paleta o clique passa a pintar, e clicar nela de novo volta ao modo seguro.
  Botão direito esvazia, arrastar move, `Ctrl+Z` desfaz.
- **A casa corrigida vira autoridade** — confiança 1,0 e cor própria (verde) —
  do mesmo jeito que o box digitado vira `source="manual"` na F3.2.
- **Trocar de diagrama e voltar não perde a correção**, pelo mesmo compromisso da
  F3.7 com as páginas: o que o usuário fez não se perde por navegar.

#### A legalidade ficou mais forte porque agora alguém pode responder

A F7.1 arbitra por contagem — um rei de cada cor, oito peões, dezesseis peças.
Aqui a checagem passou a ser a do `python-chess` inteira (`Board.status()`), e a
diferença **não é de rigor, é de informação**: com o lado a jogar preenchido,
"o rei de quem não está a jogar está em xeque" vira uma pergunta que tem
resposta. Era impossível de fazer enquanto o lado a jogar fosse convenção.

O mesmo vale para o roque, e ele cobrou uma decisão: só é oferecido o que a
posição comporta (rei em e1 e torre em h1 para o `K`). O `python-chess` derruba
um direito impossível na hora de escrever o FEN, então marcar a caixa e ver `-`
na saída seria pior do que não oferecer.

**O que o usuário informou não vira leitura.** O aviso da F7.1 dizia que o FEN
assume brancas a jogar, sem roque; informado o lado ou o roque, ele passa a dizer
que vieram de quem editou. En passant continua fora, e o aviso diz isso também.

#### Uma marca que deixa de valer, e um teste que travava a suíte

**Corrigir apaga o vermelho da legalidade.** Aquela marca dizia "isto aqui eu
troquei sozinho", o que deixa de ser verdade assim que a mão passa por ali —
manter as duas contaria a casa duas vezes no resumo e pintaria de vermelho
justamente o que o usuário acabou de escolher.

**O teste do botão pendurou a suíte inteira**, e o motivo vale registro para o
próximo teste de UI: apertar o botão executa o caminho de verdade, que sem imagem
aberta abre um `showinfo` **modal** — e ninguém clica em OK. Pior, a saída óbvia
não funcionaria: trocar `win.extrair_diagramas` por um dublê não muda nada,
porque o `command` é ligado ao método na construção. O teste passaria sem provar
coisa nenhuma. O jeito certo é o do `_App` da F3.6: substituir o `messagebox` e
conferir onde o botão chega.

#### Depois: as figuras do livro e o clique que alterna

Duas correções pedidas depois de a janela existir, e as duas são sobre o gesto
custar menos.

**As peças passaram a vir de `pieces/`** (`wK.png`, `bP.png`, …) em vez dos
glifos Unicode da fonte do sistema. O desenho da fonte é o que estiver
instalado, e ele não se parece com o do livro que está ao lado na mesma janela —
que é justamente a comparação que a F7.1 pôs ali. É **tudo ou nada**: faltando
um arquivo, o tabuleiro volta inteiro aos glifos e a legenda diz por quê. Dez
figuras e dois glifos no meio confundiriam mais que doze glifos, e uma janela
que some com as peças porque um arquivo mudou de lugar é pior que uma janela
feia.

**O clique com a peça escolhida alterna.** Clicar de novo na casa que já tem
aquela peça esvazia; clicar outra vez põe de volta. Com isso a paleta basta para
os dois movimentos da conferência — trocar a peça errada e apagar a que não
existe — sem trocar de ferramenta no meio. Casa com **outra** peça é
substituída, e não esvaziada; e a borracha não alterna, porque alternar exigiria
uma peça para pôr de volta e ela não tem nenhuma.

#### O que esta fase não entrega

**A correção ainda morre na tela.** `TabuleiroEdicao.correcoes()` já devolve as
casas mexidas à mão — é o que a F8.3 vai colher —, mas nada as grava ainda.

O FEN sai por cópia; não há caminho de volta dele para a página. Os contadores de
lance são sempre `0 1`, e en passant é sempre `-`.

**O estado do tabuleiro mora fora da janela**, em `core/tabuleiro_edicao.py`,
pelo mesmo motivo que a F7.1 pôs a leitura em `core/diagrama.py`: o que tem regra
precisa de teste, e teste de widget não é teste de regra. Dos 57 testes desta
fase, 40 não abrem janela nenhuma.

Cobertura: `tests/test_f82_tabuleiro.py`, 66 testes.

### F8.3 — Treino só de diagramas, alimentado pelas correções — CONCLUÍDA

**Concluída em 2026-08-05.** `core/treino_diagrama.py`, o botão "Guardar
amostras" na janela de diagramas e Ferramentas → "Treinar modelo de
diagramas...". `treinar_diagrama.py` virou uma casca fina sobre o módulo.

**A correção morria na tela.** A F8.2 deixou corrigir a casa; a única forma de
crescer a base continuava sendo recortar casas à mão, e as 357 amostras de hoje
saíram todas assim.

- **A amostra é o resíduo**, e não o recorte: o modelo lê `casa - fundo`, e
  guardar a casa crua faria ele aprender o papel do livro. Um teste compara o
  que foi para o disco com o resíduo que o próprio leitor calcula.
- **Silêncio não é confirmação.** Casa que ninguém tocou só entra por um
  "conferi o diagrama inteiro" explícito — decisão da F2.3, e sem ela a base
  cresceria enviesada para o que o modelo já acerta, que é justamente o que não
  precisa de amostra.
- **Casa esvaziada não vira amostra**, e não é esquecimento: o modelo tem 12
  classes de peça e nenhuma de casa vazia. Quem decide vazia/ocupada é o limiar
  de Otsu da F7.1, antes do classificador; corrigir um falso positivo conserta o
  FEN e não tem onde ser aprendido.
- **O nome da amostra é determinístico e leva a procedência** (página, diagrama,
  caixa, casa). Conferir o mesmo diagrama duas vezes regrava em vez de duplicar,
  e `gravar` apaga a mesma procedência das outras classes — sem isso, uma casa
  corrigida de bispo para cavalo deixaria a mesma imagem rotulada das duas
  maneiras, que é o defeito da F1.4.

#### Uma correção é um voto em três, e isso foi medido

O ciclo foi rodado inteiro numa página real: ler o diagrama, corrigir uma casa,
guardar, retreinar, reler. **A casa continuou saindo errada.**

A amostra nova é o vizinho mais próximo (similaridade 0,990) — mas a leitura
soma a similaridade dos **três** mais próximos, e dois vizinhos antigos somam
1,876. Com duas correções parecidas a soma vira e a casa passa a ler o que foi
corrigido:

| correções guardadas | como a casa passa a ser lida |
|---:|---|
| 0 | `p` (errado) |
| 1 | `p` |
| **2** | **`Q`** |

Não é defeito: é a aritmética do classificador da F7.1, e é o que faz o "vai
progredindo" ser progressivo em vez de uma amostra mandar sozinha. **O relatório
de treino diz isso**, porque é depois de treinar que a expectativa se forma — e
quem corrige uma casa, retreina e não vê mudança conclui que nada funciona.

#### O número que mostra progresso, e o que ele não é

Com 357 amostras não há conjunto de teste que se sustente: separar 20% deixaria
uma classe magra com duas amostras. A medida é *leave-one-out* com o mesmo voto
de 3 vizinhos da leitura — **96,6%** hoje, em 0,3 s.

**Ele é otimista, e o relatório avisa.** A base do PCA usa todas as amostras
(refazê-la a cada uma custaria ~30 s) e amostras quase idênticas se ajudam. Serve
para comparar rodadas, não para prometer acerto em livro novo — é a lição da
F1.3, que é a única razão de este número existir com um aviso colado.

**E ele derrubou o que a F7.1 supunha.** Lá ficou escrito que as classes magras
`B`, `Q` e `b` "são as que mais erram". Em leave-one-out elas acertam 100%, e
quem erra é o cavalo branco: `N` 67%, `q` 89%, `n` 91%. As duas coisas convivem —
7 amostras de bispo podem ser 7 gêmeos, e aí o LOO premia o gêmeo — mas quem
quiser conferir diagramas para ajudar o modelo agora sabe que o alvo é o cavalo.

#### O defeito que estava tornando a F7.1 inalcançável

Ao rodar o ciclo numa página real, nenhum diagrama aparecia. O motivo estava no
comando desde a F7.1: `extrair_diagramas` passava `self.boxes` para `localizar`,
e **o tabuleiro não está nessa lista** — `generate_boxes_opencv` descarta o
contorno grande antes de devolver (F1.8). Pedia-se que ela achasse entre os
contornos justamente aquele que já tinha sido tirado.

Medido em 6 páginas reais com diagrama: **0 encontrados**, contra 2 ou 3 por
página gerando os contornos sem o descarte. O comando respondia sempre "nenhum
diagrama encontrado nesta página", e o texto ainda sugeria que a culpa era da
borda da página. Agora ele faz a própria passada de contornos, sem descarte e
sem separar glifo colado (0,36 s numa página de 1.605 boxes).

**Três testes da F7.1 passavam com o comando quebrado**, e o motivo merece ficar
registrado: eles montavam `win.boxes` à mão, incluindo o box do tabuleiro — uma
entrada que o caminho de produção nunca produz. Teste que fabrica a entrada
perfeita mede a função, não o programa.

#### O que esta fase não entrega

**Nada mede se a base cresceu para melhor.** O leave-one-out compara rodadas na
própria base; para saber se o livro passou a ser lido melhor seria preciso
transcrever casas à mão de novo, como as 128 da F7.1.

Uma amostra guardada só vale depois de treinar, e o treino é manual. O `.npz`
guarda a impressão da base (F7.3 aplicada aqui), então dá para saber que ele
está velho — mas ninguém avisa sozinho ainda.

Cobertura: `tests/test_f83_treino_diagrama.py`, 37 testes.

### F8.4 — Um corpus de outro projeto vira 45 mil amostras — CONCLUÍDA

**Concluída em 2026-08-10.** O usuário largou na raiz do projeto a pasta
`Diagramas-outro-projeto/`, de um OCR de diagramas dele que "já está com uma precisão
muito boa", e pediu para avaliar o aproveitamento. São 3.439 recortes de tabuleiro de
800×800 com o FEN de cada um — e fecham o item que a F8.3 deixou aberto duas seções
acima: *"nada mede se a base cresceu para melhor"*.

#### Duas coisas precisavam ser verdade, e foram medidas antes de mexer em nada

**Domínio.** Não são renders sintéticos: são recortes de scan de livro, com casas
hachuradas e fontes de peça variadas — `1937 Kemeri`, `Euwe/Kramer 1956`,
`Reinfeld 1977`, `Karpov 2011`, Yusupov, Polgar. Um deles vem amarelado. É o material
que o nosso leitor enfrenta.

**Alinhamento.** `_casas_do_recorte` divide o recorte em 8×8 **iguais**, então o corte
precisa ser a borda do tabuleiro; moldura de 2% desloca toda casa. Medido antes de
escrever uma linha de importador: **ocupação 99,81%** em 9.600 casas, 4 falsos positivos
e 14 omissões. Divisão desalinhada não produz esse número. Consumo direto, sem recortar.

#### A medição que justificou a fase

Nosso leitor contra 346 tabuleiros do split `test` do corpus, que a importação deixa de
fora de propósito:

| | antes | depois |
|---|---:|---:|
| ocupação (há peça?) | 99,51% | 99,38% |
| **identidade (qual peça?)** | **76,42%** | **99,62%** |
| **tabuleiro inteiro certo** | **23,41%** | **92,49%** |

Os 0,13 ponto a menos na ocupação não são desta fase: o modelo "antes" é o commitado em
7 de agosto, e a base de ocupação já mudou desde então pelas confirmações do usuário
(F8.3). Ver a nota sobre o teto de passos abaixo, onde a atribuição foi medida em vez de
suposta.

Os 76,42% são a ressalva que o relatório de treino imprime desde a F7.4 — *"ainda assim
é otimista para um livro novo, que traz outra fonte de peças"* — medida pela primeira
vez. Contra os ~98% que a medição interna informava.

**E a causa é visível no resíduo.** O erro dominante era `p → b`: 671 de ~1.180. Os
livros do corpus usam um peão de **pescoço fino e cabeça redonda**, forma que na nossa
base existe só na classe do bispo; nossos peões são blocos maciços. O modelo votava
bispo porque nunca tinha visto aquele peão. O corpus contém precisamente as fontes que
faltavam.

#### Só as peças entram, e o motivo é a mesma medição

O corpus tem 51.589 peças e 168.507 casas vazias. As vazias ficaram de fora: a rede de
ocupação já faz 99,5% **neste mesmo corpus**, e importar 168 mil amostras para a pergunta
que está resolvida custaria toda a memória do treino sem mover o número que está errado.
Entraram 45.256 amostras de peça, e a base de identidade foi de 1.649 para 46.905.

#### O conferidor é a outra rede

A defesa da F8.3 era "silêncio não é confirmação" — só entra a casa que a mão tocou.
Aqui não há mão nenhuma: são 45 mil rótulos alheios de uma vez. A defesa que sobra é a
ocupação, que é **independente** do que se quer aprender (diz *se* há peça, não *qual*) e
acerta 99,5% aqui. Tabuleiro em que ela discorda do FEN em mais de 3 casas não entra.

Recusou 56 de 3.091, e achou um defeito real: alguns recortes de 800×800 incluem a
**legenda de avaliação impressa abaixo do tabuleiro** (`△  +−`). A divisão 8×8 sai
comprimida, toda casa fica deslocada — e o FEN continua dizendo com segurança o que há
em cada uma. Amostra torta com rótulo confiante é o defeito da F1.4, que não avisa que
está errada.

#### O gêmeo, e o único rótulo contraditório do corpus

O primeiro treino com a base importada acusou, pelo `conferir` da F8.3, **a mesma imagem
rotulada como `B` e como `P`**. Vale registrar como foi achado, porque a defesa acima não
alcança este caso: as duas linhas dizem "há peça em c2", então a ocupação concorda com as
duas. Quem pegou foi a conferência de rótulo contraditório, que a F1.4 deixou instalada.

Perseguindo, apareceu a causa e uma segunda coisa mais frequente: **o corpus tem 3.439
linhas para 3.264 imagens distintas.** 164 imagens aparecem sob mais de um nome. Nas duas
linhas do conflito o arquivo é byte a byte o mesmo, e os FENs diferem só em c2 —
`PPB1Q2P` contra `PPP1Q2P`. Ampliado, c2 é peão: uma das duas linhas está errada.

O gêmeo não é só desperdício. `grupo_da_amostra` agrupa pela marca da procedência, e dois
nomes são dois grupos: as mesmas casas poderiam cair uma no treino e outra no teste, que é
exatamente o que a F7.4 mediu inflando o número. A importação passou a deduplicar **por
conteúdo da imagem**, e onde os FENs discordam saem todas as cópias — não há como saber
qual está certa, e "fica a primeira" seria escolher no cara ou coroa.

**Deduplicar por FEN seria o erro simétrico**, e há teste contra ele: a mesma posição
impressa em dois livros são duas amostras legítimas, e são justamente as que ensinam a
fonte nova.

#### O treinador precisou aguentar 28 vezes mais base

- **`_deslocar` sem laço.** Era um `torch.roll` por amostra; com 46.905 são tantas
  chamadas por época quanto amostras, e cada uma custa mais em despacho do Python do que
  no deslocamento. Virou indexação circular no lote inteiro: **12× mais rápido e idêntico
  bit a bit** ao laço com o mesmo sorteio — há teste cobrando a identidade, não a
  semelhança.
- **O platô da F7.4 fixou passos, não passadas.** As 80 épocas foram medidas com 833
  amostras; repeti-las numa base 28 vezes maior pediria 59 mil passos de gradiente. O
  teto agora é em passos e as épocas saem dele. Medido na base combinada:

  | épocas | passos | treino | identidade | tabuleiros inteiros |
  |---:|---:|---:|---:|---:|
  | 2 | 2.932 | 33 s | 99,68% | 91,88% |
  | 4 | 5.864 | 61 s | 99,68% | 91,88% |
  | 8 | 11.728 | 120 s | 99,66% | 91,59% |
  | 16 | 23.456 | 272 s | 99,72% | 92,17% |

  O platô começa em **duas** passadas: de 2 a 16 a diferença é 0,06 ponto, sem tendência,
  e o custo quadruplica. `MIN_EPOCAS = 4` é o meio do platô, mesmo critério da F7.4.
- **`PASSOS = 7920` é o que a maior base do repositório já gastava**, e o primeiro valor
  estava errado — vale registrar, com a correção junto. Tirei 4.160 da base de **peças**
  (1.649 amostras × 80 épocas ÷ lotes de 32), que ela deixa intacta por construção. A de
  **ocupação** tem 3.156, é maior, e o teto a cortou de 80 épocas para 42 sem teste
  nenhum reclamar — o teste que escrevi cobria 833 e 1.649, e a base de ocupação nem
  estava na conta.

  **Atribuí o corte a uma queda que ele não causou, e a medição me desmentiu.** A
  ocupação caíra de 99,51% para 99,38% no split de teste, e o corte era o suspeito
  óbvio. Medido na mesma base, 42 épocas dá **99,88%** e 80 dá **99,79%** em 150
  tabuleiros do corpus — a favor das 42. A diferença dos 0,13 ponto vem de outro lugar:
  o `.pth` commitado foi treinado em 7 de agosto e a impressão digital da base de
  ocupação já não bate com a dele, porque o usuário confirmou diagramas desde então. É a
  F8.3 funcionando, e o efeito disso neste corpus nunca tinha sido medido.

  O valor mudou mesmo assim, e não porque o corte fazia mal: **um padrão que altera em
  silêncio o treino de uma base que já existia é o defeito**, e o acerto medido dele foi
  sorte, não desenho. O teste agora cobra os três tamanhos (833, 1.649 e 3.156).
- **Duas pastas, lidas juntas.** `training_data_diagrama/` é conferida à mão, tem 1.649
  amostras e viaja no repositório; `training_data_diagrama_corpus/` tem 45 mil, vem de
  rótulo alheio e o `.gitignore` a mantém fora, junto com os 2,8 GB do corpus. Separadas
  no disco, dá para dizer de qual veio uma mudança no número — é a separação que o léxico
  faz entre `palavras` e `do_usuario`. O corpus entra sozinho **se existir**: sem isso, a
  janela treinaria largando 45 mil amostras em silêncio e gravaria por cima do modelo bom
  um treinado com 3% dos dados.

#### E os nossos livros, que viraram 3,6% da base?

A pergunta que 42 mil amostras de outra procedência levantam: o modelo passou a ler os
livros deles às custas dos nossos? `_pesos_das_classes` equilibra por **classe**, não por
origem, e as nossas fontes ficaram em 3,6% dos dados.

Medido com 20% dos **nossos** diagramas fora dos dois treinos:

| treinado com | amostras | épocas | acerto nos nossos diagramas |
|---|---:|---:|---:|
| só a nossa base | 1.364 | 80 | 98,25% |
| a nossa + o corpus | 43.811 | 6 | **99,30%** |

Melhorou, e os dois erros que sumiram eram `p → b` — o mesmo defeito que o corpus veio
consertar, presente também nos nossos livros e escondido pelo tamanho da base. O que
sobra são dois `R → r`, que é distinguir torre branca de preta num scan escuro.

#### O que a fase não promete

**O split de teste compartilha livro com o de treino.** Nenhum dos 18 dias de captura é
exclusivo do teste, então a tabela acima mede "livro cuja fonte a base já viu". Não há
vazamento de imagem — 0 das 348 de teste é idêntica a alguma de treino —, mas 8,9% das
posições do teste têm o mesmo FEN de alguma do treino, em imagem diferente.

O número honesto de **fonte nova** é o leave-one-book-out: tirar um dia de captura
inteiro do treino e medir nele.

| dia fora | amostras no treino | tabuleiros | identidade | tabuleiros inteiros |
|---|---:|---:|---:|---:|
| 20260227 | 36.696 | 120 | 99,78% | 95,83% |
| 20260301 | 36.566 | 120 | 100,00% | 99,17% |
| 20260726 | 46.275 | 39 | 94,86% | 51,28% |

O terceiro é o que vale ler: são 40 tabuleiros, e tirá-los quase não muda o treino — a
fonte continua sozinha contra 46 mil amostras de outras, e ainda assim 94,86%. Os 51% de
tabuleiro inteiro são aritmética, não desastre: ~15 peças por tabuleiro a 95% cada dão
0,95¹⁵ ≈ 46%.

**A procedência do corpus é fina.** `source_pdf` só está preenchido em 243 das 3.439
linhas, então separar por **livro** — que é o corte honesto — não dá para todos; o dia de
captura é o proxy disponível. Dentro da nossa base, `grupo_da_amostra` continua garantindo
que duas casas do mesmo tabuleiro não fiquem em lados opostos.

**Os rótulos não são todos conferidos à mão.** O `settings.json` do outro projeto aponta
um preditor remoto de FEN e um leitor local; 126 linhas trazem `corrected_by` de
`ocr-aceito` ou `ocr-corrigido`. O filtro de ocupação pega o rótulo grosseiramente errado,
não o que troca uma peça por outra.

Cobertura: `tests/test_f84_corpus.py` (11 testes, dos quais 5 são sobre o que **não**
entra) e 8 testes novos em `tests/test_f83_treino_diagrama.py`. `medir_diagramas.py` refaz
a medição da fase.

---

## F9 — Léxico do texto corrido — CONCLUÍDA (F9.1, F9.2 e F9.3)

> Ideia trazida pelo usuário em 2026-08-06: o ABBYY FineReader usa dicionário, e deixa
> acrescentar palavras próprias. **Ajuda, sim** — reordenar hipóteses de palavra inteira
> contra um léxico é a segunda etapa padrão de todo OCR maduro, e o Tesseract, que já
> está na cadeia de fallback, traz a dele (`load_system_dawg`, `load_freq_dawg`,
> `--user-words`).
>
> O que muda quando a ideia encosta *neste* projeto são três coisas, e vale escrevê-las
> antes de alguém codificar: metade do texto já tem um dicionário melhor que qualquer
> lista de palavras; a metade que sobra nunca recebeu correção nenhuma; e o ganho mais
> provável não é corrigir, é **triar**.

### F9.1 — Dicionário do texto corrido — FEITA

#### A metade que já está resolvida, e não por lista de palavras

A F1.7 confronta cada lance com as regras do xadrez. Aquilo **é** um dicionário, e um que
nenhuma lista alcança, porque depende de contexto: `Nf3` é palavra válida numa posição e
impossível na seguinte. Uma lista estática não tem como dizer isso — e, aplicada à
notação, faria o oposto do que se quer. `Bxf6`, `exd5` e `Rd1` não são palavra de idioma
nenhum, e um dicionário que insista em aproximá-las da palavra mais parecida destrói
justamente a parte do livro que o projeto existe para ler.

Então a primeira decisão de desenho é uma fronteira — e ela **já está no código**:
`notacao._fatiar` classifica cada pedaço da linha em `lance` ou `outro`, e
`parece_lance` é a peneira que separa "counterplay" de "N□f6". O léxico é dono dos
pedaços `outro`; a legalidade continua dona dos `lance`. Nenhum dos dois toca no
material do outro.

O resto do maquinário também está pronto, e por outro motivo: `palavras_da_pagina` já
recorta palavra por palavra a partir dos boxes (com o limiar de espaço e a segunda
passada dos números que a F1.7 mediu), `Simbolo` amarra cada caractere ao box de onde
veio, `custo_da_troca` é distância de edição ponderada pela confiança, e
`Correcao`/`aplicar` já sabem editar box sem inventar box. É o padrão que a SPEC §1
registra: o que parece trabalho novo é, em boa parte, trabalho já feito por outro motivo.

#### O que um léxico enxerga da lista de erros que já foi medida

A F1.3 registrou as confusões do modelo no conjunto de teste. Separadas pelo que uma
lista de palavras teria como perceber:

| Confusão medida (F1.3) | O léxico enxerga? | Por quê |
|---|---|---|
| `1` ↔ `l` | **sim** | `p1ay` não é palavra; `play` é |
| `f` → `f7` (a ligadura da F1.4) | **sim** | palavra com casa de xadrez no meio não é palavra |
| `W` ↔ `w` | em parte | só onde a caixa é impossível na posição |
| `,` ↔ `'` | **não** | pontuação não está dentro de palavra |
| `.` ↔ `-` | **não** | idem |
| `✝` ↔ `+` | **não** | idem |

Metade da lista, portanto, está fora do alcance por construção. Isso não desqualifica o
item — mas desqualifica a expectativa de que dicionário conserte OCR em geral.

#### Onde está o ganho provável, e é triagem antes de correção

A F1.9 mediu o teto da triagem por confiança, e a re-medida de 2026-08-06 o baixou: no
corte 0,90 de `ui/confidence.py`, revisando 2,4% da página o revisor acha **39,7%** dos
erros, e para achar metade é preciso ir a 0,99 (5,4% da página). O limitador é que a
confiança **ordena** razoavelmente (AUROC 0,86–0,87) e nada mais — não existe corte que
ache os erros restantes por um preço aceitável.

"Palavra fora do dicionário" é um sinal **independente da confiança**, e é isso que o
torna interessante: um erro lido com confiança 1,000 dentro de uma palavra impossível
continua visível para o léxico. Somado ao filtro da F3.3 ("só palavras fora do
dicionário"), é um segundo eixo de triagem sobre a mesma página.

O número que decide se o item se paga é a **precisão desse sinal**: de cada 100 palavras
sinalizadas, quantas contêm erro de verdade. Nome próprio, notação e abreviação de livro
de xadrez vão inflar o falso alarme, e é por isso que a F9.2 não é enfeite.

#### A armadilha, e ela já custou duas vezes neste projeto

Um léxico que **edita** é perigoso do jeito pior: ele troca um erro visível por uma
palavra plausível e errada. `Nimzowitsch` não está em lista de idioma nenhum, e um
corretor que force a palavra mais próxima entrega prosa limpa e falsa — o revisor não
tem como desconfiar. É a mesma forma de falha da F0.2 (o `·` que a Helvetica escrevia em
silêncio) e da F1.5 (o separador que partia glifo bom e ninguém via, porque a medida
olhava só o recall).

Daí os contratos, todos derivados de lições já pagas:

1. **Fora do dicionário significa "não mexer", nunca "aproximar da palavra mais
   parecida".** Palavra desconhecida é sinalizada. O ABBYY faz assim, e é o motivo de o
   dicionário do usuário existir por lá.
2. **Os candidatos vêm do classificador, não do alfabeto.** É a lição da F1.5b — a
   geometria propõe, o classificador dispõe. Aqui: o léxico propõe, o classificador
   arbitra. Sem isso, "trocar `l` por `1`" e "trocar `l` por `q`" custam o mesmo, e a
   correção passa a inventar caractere que nenhum box sustenta.
3. **Só box sobrando vira edição** — o contrato 5 da F1.7, pelo mesmo motivo: caractere
   faltando não tem box para apontar, e vira sugestão.
4. **Nada acontece sem dicionário carregado**, como em `dividir_glifos_colados` e em
   `core/vertical.py`. O padrão é não agir.

O contrato 2 é a única lacuna real de código: `LearningService.predict_neural` e
`NeuralPredictor.predict` devolvem `Tuple[str, float]` — **um** caractere. Falta um
`predict_topk`, e é pré-requisito de qualquer correção; para a triagem do parágrafo
anterior, não é.

#### O que medir antes de escrever o léxico

Na ordem, e a primeira medição pode encerrar o item:

1. ~~**Quanto do erro é alcançável.**~~ — **medido em 2026-08-06, ver abaixo: 43,5%.
   A fase segue.**
2. **A precisão da sinalização**, como acima.
3. **F1 da página com e sem o léxico, mais a contagem de correções boas e ruins
   separadas**, na forma da tabela da F1.5b. Medir só por recall é o que deixou o
   defeito da F1.5 passar: uma edição ruim quase não mexe no recall e despeja uma
   palavra inventada no texto. `core/avaliacao_pagina.py` já mede página contra `.box`
   rotulado, então o arnês existe.

Um detalhe que a medição vai encontrar: estes livros são em **inglês**, e o texto do
programa é em português. O idioma do léxico é escolha explícita do perfil (SPEC §4.5), não
adivinhação — dicionário do idioma errado é pior que nenhum.

#### Medida 1 (2026-08-06): 43,5% do erro é alcançável, e a fase segue

`medir_lexico.py`, nas 10 páginas rotuladas, com o modelo de 119 classes e o pipeline de
produção (separador arbitrado). Dos **336 caracteres lidos errado**:

| onde o erro cai | n | do erro | quem resolve |
|---|---:|---:|---|
| **dentro de palavra de prosa (≥2 letras)** | **146** | **43,5%** | **o léxico** |
| núcleo não é palavra (`2010`, `0-0`, pontuação) | 68 | 20,2% | ninguém, por lista |
| dentro de lance | 57 | 17,0% | a legalidade (F1.7) |
| palavra de uma letra só | 36 | 10,7% | ninguém — está no dicionário de qualquer jeito |
| fora do núcleo (pontuação das pontas) | 24 | 7,1% | ninguém |
| número de jogada | 5 | 1,5% | a legalidade |

Mais **129 boxes espúrios dentro de palavra**, que o léxico pode esvaziar pelo contrato 3
— um caractere a mais numa palavra é tão visível quanto um trocado. Os **236 caracteres
perdidos** (sem box) ficam fora: viram sugestão, não edição.

Não é fatia magra, então a F1.8 não se repetiu aqui. Mas três correções ao denominador
saíram da conferência, e as três **reduzem** o número:

- **8 dos 336 não são erro nenhum: são ligadura certa que o metro pune.** `comparar` casa
  um box gerado com **um** rotulado, então um box que cobre `e4` colado casa com o `e`;
  ler `e4` — a leitura certa, e a razão de a classe existir — sai como erro *e* deixa o
  `4` como perdido. Suspeitei que fossem os 68 casos de ligadura e medi: são 8. O metro
  subestima o modelo de 119 classes, mas por 2,4%, não por um quinto.
- **17 têm verdade `'?'`** — quem rotulou à mão não conseguiu ler o glifo. Não é erro do
  modelo, e em pelo menos um caso (`'the'` contra verdade `'?he'`) o modelo leu certo e o
  humano não.
- Descontando os dois, sobram **311 erros reais** e a fatia alcançável fica em ~44% — a
  conclusão não se move.

**Um defeito da minha própria medida, achado olhando os exemplos.** A primeira versão
recortava o núcleo da palavra pelo texto **lido**, e com isso `Mov6` (verdade `Move`) e
`3awn` (verdade `Pawn`) caíam em "fora do núcleo": o caractere errado virou dígito e
deixou de ser borda alfabética. São os erros mais alcançáveis que existem e a medida os
jogava fora. O núcleo passou a ser recortado da **verdade**. É o mesmo formato de erro que
a F1.5 cometeu com "zero pedaços estreitos novos" — a propriedade medida não era a
propriedade que interessava.

**O que a divisão por caixa diz sobre a F9.2, e é mais do que se esperava:** dos 146
alcançáveis, **62 (42,5%) estão em palavra Capitalizada** — `Gavilov`, `Andekin`,
`Nimzowitsch`. Um dicionário genérico não tem nenhuma delas. A F9.2 deixou de ser
complemento e passou a responder por perto de metade do alcance da fase.

**A fronteira com a notação vaza em 18 pedaços**, e a medida diz de que jeito: são lances
tão maltratados que `parece_lance` os rejeita (`BG7`, `K;5`, `;xa2`, `Rag`) e caem no lado
do léxico. Nenhum deles está no dicionário, então pelo contrato 2 viram **alarme falso, e
não estrago** — é a primeira medição que sustenta aquele contrato em vez de só argumentar
por ele. Com correção automática agressiva, seriam 18 lances reescritos como palavra.

**Um custo das classes novas que ninguém havia contado.** Em **60 dos 336 erros** (18%) o
modelo prediz uma ligadura onde a verdade tem um caractere só, injetando um caractere no
texto — `f6` no lugar de `5`, `Th` no lugar de `d`. É o maior balde depois de `PALAVRA`.
Não reverte a decisão da SPEC §5.2 item 6, que rendeu +0,4 de F1 no total; mostra onde ela
cobra, e é alvo de coleta de amostra, não de desenho.

#### Medida 2 (2026-08-06): o piso de alarme falso é 12,1%, e um terço dele não é da lista

`medir_lexico.py --lista <arquivo>`, com `words_alpha.txt` do `dwyl/english-words`
(370.105 palavras, 4,23 MB, domínio público). A medida **não usa o modelo**: constrói as
palavras sobre a verdade rotulada e pergunta quantas a lista não tem. Toda palavra que
está certa na página e falta na lista viraria alarme falso, então isto é o piso do falso
positivo, medido antes de existir léxico.

| | |
|---|---:|
| palavras de prosa na verdade | 1.170 (598 distintas) |
| fora da lista | 141 (126 distintas) |
| **piso de alarme falso** | **12,1%** |
| das ausências, Capitalizadas | 46 (32,6%) |

De quem é a ausência — atribuição aproximada, e o método está no código:

| | n | | exemplos |
|---|---:|---:|---|
| vocabulário de verdade ausente | 111 | 78,7% | `Benko`, `Tromso`, `Elo`, `queenside`, `manoeuvres` |
| espaço perdido na segmentação | 18 | 12,8% | `ofthe`, `Ofcourse`, `BenkoGambit`, `protecttheisolatedpawns` |
| pedaço de palavra partida | 12 | 8,5% | `barrassment`, `ghting`, `equa`, `comfo` |

**Três coisas dentro do balde "vocabulário" que não são vocabulário**, e é o achado que
muda trabalho:

1. **Fragmento de notação virando palavra de prosa** — `Nc`, `Rxf`, `xe`, `rb`, `tt`. Um
   lance cujo dígito caiu noutro pedaço perde a casa, `parece_lance` o rejeita por falta
   de `[a-h][1-8]`, e ele entra na prosa. **Isto está medido sobre a verdade rotulada, sem
   OCR nenhum**: a fronteira não vaza só por causa de leitura ruim, vaza por fatiamento.
2. **A lista é americana** — `manoeuvres` está certa e falta. Uma lista só de en-US
   sinaliza a grafia britânica de um livro britânico (Quality Chess é escocesa).
3. **Nome próprio e vocabulário de xadrez**, que é a F9.2 confirmada por outro caminho:
   `Benko` sozinho aparece 6 vezes em 10 páginas.

**Consequência para a ordem da fase.** Somando espaço perdido, palavra partida e fragmento
de notação, perto de **um terço do alarme falso não se conserta com lista nenhuma** — é
`notacao.palavras_da_pagina` e o fatiamento. Arrumar a fronteira de palavra passou a vir
**antes** de escrever o léxico, e tem a vantagem de ser medível sobre a verdade rotulada,
sem modelo e em segundos.

**Duas atribuições erradas minhas no caminho, e a segunda é a mesma lição da primeira.** O
teste de "espaço perdido" decompõe a palavra ausente em palavras conhecidas. Rodado contra
as 370 mil, ele dizia 60,3% — porque uma lista desse tamanho tem lixo de duas e três
letras para tudo: `Benko` decompõe em `ben`+`ko`, `queenside` em `queen`+`side`. Passou a
decompor contra o **vocabulário das próprias páginas**, e caiu para 12,8%. O teste de
"pedaço de palavra" tinha o mesmo vício (`Elo` como prefixo de `elope`) e exige agora 4
letras e folga de 2. Em ambos os casos o erro era medir contra um universo grande demais
para o sinal ser sinal.

**A lista ainda não entrou no repositório.** 4,23 MB é dez vezes o que a SPEC §5.8
estimava, e o tamanho tem uma troca não medida: lista maior baixa o alarme falso e
**esconde mais erro** — `glans` está nela, então `plans` lido `glans` passaria batido. O
número que falta é alarme falso contra erro achado por tamanho de lista, e ele precisa de
uma lista ordenada por frequência, que esta não é.

> Resolvido pela medida 3: a lista entrou, e a troca que faltava é a tabela dela.

#### Medida 3 (2026-08-06): a lista do ABBYY entrou, e a troca que faltava tem números

O usuário mantinha, para o ABBYY FineReader, um dicionário de xadrez com nomes de
jogadores. É a fonte que a F9.2 pedia, e chegou pronta. `importar_lexico.py` a traz para
`assets/lexico/`; `medir_troca.py` roda o OCR de verdade e classifica cada palavra de prosa
lida — é o arnês que faltava, porque `medir_lexico --lista` mede sobre a verdade e por isso
só enxerga o alarme falso:

| | palavras | recall | alarme falso | precisão |
|---|---:|---:|---:|---:|
| `words_alpha` (medida 2, referência) | 370.105 | — | 12,1% | — |
| **idioma** — as minúsculas do ABBYY | 73.447 | 58,5% | 12,1% | 39,2% |
| **idioma + nomes** — o arquivo como veio | 310.465 | **53,8%** | **5,8%** | **47,1%** |
| idem, tokenizando `m.lois` em `lois` | 508.289 | 49,1% | 4,8% | 49,5% |
| idem, mais as outras cinco listas | 516.498 | 48,1% | 4,7% | 49,5% |
| só os nomes | 237.018 | 95,3% | 87,5% | 9,5% |

*Recall* é dos 106 erros de OCR dentro de palavra de prosa; *alarme falso* é sobre as
1.102 palavras lidas; *precisão* é quanto do que se sinaliza é erro de verdade. A coluna
de alarme falso sobre a **verdade** (`medir_lexico --lista`, sem modelo) dá 12,1% / 8,8% /
8,0% / 7,9%, e com os reparos de fronteira do `core.lexico` cai para 8,9% / 6,0% / 5,2%.

**A troca existe e é suave**: de 73 mil para 516 mil palavras, o alarme falso cai 7,4
pontos e o recall cai 10,4. Não há joelho na curva — cada palavra a mais compra silêncio e
vende um erro. **A escolha é o arquivo como veio**, 310.465 palavras: é onde o alarme falso
já caiu mais da metade e o recall ainda está acima de 50%.

**73.447 palavras dão o mesmo 12,1% de alarme falso que as 370.105 da medida 2**, com um
quinto do tamanho — e sem o defeito registrado lá: `manoeuvres` está nela, porque um
dicionário montado sobre livros de xadrez britânicos não é americano.

**O que decide idioma de nome próprio é a caixa da entrada original.** O ABBYY guarda
palavra comum nas duas caixas (`build` e `Build`) e nome próprio só na Capitalizada
(`Andretti`). A primeira tentativa separou por subtração — o dicionário menos a lista de
jogadores — e o alarme falso saltou de 8,8% para **62,7%**: `MegaDatabase(Jogadores)` tem
time e torneio (`Aachen Hoern U20`), então subtraí-la levava inglês junto.

**Duas escolhas que a medida mandou desfazer.** Metade do arquivo é inicial colada a
sobrenome (`m.lois`, `P.Puustinenasi`); partir no ponto para colher `lois` acrescenta 198
mil palavras e troca 4,7 pontos de recall por 1,0 de alarme falso. E das seis listas da
pasta, **só uma é lida**: `Chess-Dic-68 with MegaDatabePlayers` contém 99,8% dos tokens de
`MegaDatabase(Jogadores palavras unicas)`, e somar as outras cinco rendeu 0,1 ponto.

**O tamanho deixou de ser objeção.** 0,94 MB comprimido (0,21 do idioma, 0,74 dos nomes)
contra os 4,23 MB que barraram a lista anterior. `core.lexico._ler` abre `.gz` e texto
puro pelo sufixo.

**Uma medição errada no caminho, e é a mesma de sempre.** A primeira rodada dizia que a
lista grande escondia *mais* erro que a pequena por uma margem absurda, com exemplos como
`difficult` lido onde a verdade seria `diffcult` e `King` onde seria `ng`. Não era erro de
OCR: a verdade é remontada dos pares de `comparar`, e box gerado sem par contribui string
vazia, truncando a verdade. Pedaço com box sem par passou a não ser medível — são 154, e
sobram 1.102 palavras. Terceira vez na fase que a propriedade medida não era a que
interessava; as outras duas estão na F1.5 e na medida 1.

**O que continua sem número.** Nenhuma destas listas é ordenada por frequência, então a
poda que baixaria o tamanho sem custar recall — tirar `glans` e manter `plans` — continua
impossível de fazer com critério.

#### O módulo

`core/lexico.py`: carregar lista de palavras, dizer se uma palavra é conhecida,
sinalizar as que não são, e — só com árbitro — propor a troca cujos candidatos saem do
`predict_topk`. Filtro novo na F3.3 e um relatório no padrão da F1.7 (propõe, marca, não
reescreve calado).

**Sem dependência nova.** Um `set` de palavras mais candidatos vindos do top-k resolve.
`pyspellchecker` e `hunspell` estão descartados de propósito: o gerador de candidatos
deles varre o alfabeto inteiro, que é exatamente o modo de falha do contrato 2. A lista
de 50–100 mil palavras dá algumas centenas de KB e tem de ser **empacotada** no
repositório — a `assets/fonts/DejaVuSans.ttf` da SPEC §9.2 ainda não foi, e é a mesma
armadilha.

Sub-problema conhecido, para não ser descoberto na hora: palavra partida por hífen no
fim da linha ("counter-" / "play") só existe como palavra depois de a F1.6 ter posto as
linhas em ordem.

#### Ligado na revisão (2026-08-06)

`lexico.suspeitas_da_pagina` é o único caminho da UI até o dicionário, e roda
`notacao._fatiar` antes de consultar — o contrato 1 num lugar só. Na tela: sublinhado
roxo sob o box, coluna `*` na lista, contador de palavras e o alternador **"só fora do
dicionário"** ao lado de "só pendentes".

Duas decisões que a integração forçou, e as duas saem de número já medido:

1. **O sublinhado não substitui a cor do box.** A cor é a confiança do caractere; o
   léxico julga a palavra. O caso que só o dicionário pega é o box **verde**, de
   confiança 1,000 — pintá-lo apagaria o dado que já estava lá.
2. **Com o filtro ligado, o `F3` anda por todos os visíveis**, não só pelos que
   `precisa_revisao` aponta. Pelo mesmo motivo: quase nenhuma palavra fora do
   dicionário é "pendente", e o `F3` responderia "nada pendente" com a tela cheia de
   marcas.

Custo medido: 9,5 ms numa página de 1.589 boxes, contra 0,36 ms da chave de cache — e
`update_sidebar` está no caminho da tecla do modo digitação, onde a F3.8 já teve de
matar um `deepcopy` de 15,8 ms. Com cache, 2,2 ms por chamada; a carga das listas é
preguiçosa (294 ms na primeira página, zero em quem só abre um `.box`).

#### Achado à espera de medida: 9,2% do alarme é palavra composta

Das 153 suspeitas nas 10 páginas rotuladas, **14 são compostas cujas partes estão
todas no dicionário**: `high-quality`, `move-orders` e nomes de tabela de torneio
(`Gavrilov,Alexey`). O `nucleo` só tira pontuação das pontas, então elas chegam
inteiras e nenhuma lista as tem.

**A correção óbvia é uma armadilha, e é o que vale registrar.** Partir a palavra em
todo caractere não-alfabético e aceitá-la se as partes forem conhecidas calaria 18
suspeitas — mas entre elas `cons1der`, `log1cal` e `wh1ch`, que são o alvo canônico da
fase: `cons`+`der` estão as duas na lista de 310 mil. Partir **só** em `-`, `,` e
apóstrofo cala 14 e não toca em nenhuma das 12 com dígito.

Não foi implementado: falta rodar o `medir_troca.py` com a regra para saber o que ela
**esconde**, e é essa a metade que a medida 2 esqueceu de perguntar. Quatro das 14 são
fragmento e não composta legítima (`er,Fr`, `Bosboom-Van`), então a regra tem custo.

### F9.2 — Dicionário do usuário — CONCLUÍDA

**Concluída em 2026-08-06.** `core/lexico.py` ganhou a lista por livro, e ela é
alimentada pelo mesmo "Aprender com Página Atual" que já alimenta o k-NN.

A premissa: as palavras que uma lista genérica **não** tem são justamente as que se
repetem num livro de xadrez. Nome de jogador (Yusupov, Nimzowitsch, Botvinnik), nome de
abertura (Benoni, Benko, Grünfeld, Najdorf), vocabulário do jogo (zugzwang, fianchetto,
outpost), editora e série. Sem elas, a sinalização da F9.1 acusa erro em toda página e o
revisor aprende a ignorá-la — que é o modo de morte de qualquer alarme.

#### O que a medição diz, e ela é modesta

`medir_lexico.py --usuario` mede deixando **uma página de fora**: aprende o vocabulário
das outras e conta o alarme falso na que sobrou. Medir na mesma página em que se aprendeu
responderia 100% por construção.

| | ocorrências | alarme falso |
|---|---:|---:|
| sem dicionário do usuário | 142 | 12,1% |
| com o das outras páginas | 129 | **11,0%** |
| com o das outras páginas **do mesmo livro** | 129 | 11,0% |

**O dicionário do livro apaga 9,2% do alarme falso**, e não mais — bem abaixo do que este
item prometia. O motivo está medido, e é o teto, não a implementação:

    das 128 palavras distintas que acendem nas 10 páginas
      4    aparecem em mais de uma página   <- tudo que um dicionário de livro alcança
      124  aparecem numa página só          <- fora do alcance de qualquer lista

E das 4 repetidas, **uma** é vocabulário de verdade (`benko`, em 4 páginas); as outras
três — `ofthe`, `ofa`, `xe` — são espaço perdido e fragmento, defeito de segmentação que
o dicionário não deve calar e que a regra do box digitado à mão não deixa entrar.

**A amostra é rala para esta pergunta, e vale dizer em vez de esconder.** As 10 páginas
rotuladas são esparsas (13, 14, 20, 22, 33, 57, 108, 128 do Kasparov), e o vocabulário de
um livro se repete dentro de um capítulo. Uma sonda na camada de texto do livro inteiro do
Yusupov sugere repetição bem maior, mas **não é citável como medida**: aquela camada
codifica figurina como letra, então `parece_lance` não peneira a notação e `xf`, `gxf` e
`cxd` entram como se fossem palavra. Medir isso direito pede páginas rotuladas
consecutivas, que não existem.

#### Onde a lista mora — e por que não é no perfil

Este item previa `config/profiles/<nome>.json`, da F2.4, e a implementação divergiu por um
motivo que só aparece ao ler o código: **o perfil é escolhido por padrão de fonte, não por
livro**. `perfis.escolher` casa `font_patterns` contra o nome da fonte do PDF, e dois
livros compostos na mesma fonte caem no mesmo perfil — guardar ali daria a um livro do
Kasparov o vocabulário de um do Yusupov, que é o contrário do motivo da fase. Os dois
perfis que existem também são versionados e comentados à mão, e reescrevê-los a cada
palavra aprendida encheria o `git status` do usuário.

Ficou ao lado do documento, como o rascunho da F3.4:

    livro.pdf              -> livro.lexico.txt
    pasta/pagina-0012.jpg  -> pasta/lexico.txt        (a lista é da pasta, não da página)

Texto puro, uma palavra por linha, ordenado. O formato é escolha de desenho: é assim que o
usuário tira à mão a palavra que entrou errada, e **sem esse escape não haveria como
tirar** — não há tela que mostre "esta palavra deixou de acender".

#### O que entra, e as quatro coisas que não entram

A regra é a da F8.3: **silêncio não é confirmação**. Entra a palavra de prosa que tem pelo
menos um box digitado à mão — é o que separa `Nimzowitsch`, que o revisor leu e corrigiu,
de `Kdinovsb`, que o OCR inventou e ninguém olhou. Um box basta: o revisor corrige a letra
errada, não a palavra inteira.

Não entram, e cada recusa fecha um jeito de a lista calar o alarme que ela deveria dar:

1. **A palavra que ninguém tocou**, ainda que lida com confiança 1,000 — que é a confiança
   mediana de um erro (F1.9).
2. **A palavra com box vazio dentro dela.** Box sem caractere não vira símbolo, então
   `Kalinovsky` com um buraco chega como `Kalinvsky` e entraria assim. Quem acha o buraco é
   a geometria, porque o texto já não o mostra. Isto recusa também o box esvaziado **de
   propósito** — `apply_char` grava `source=""` nos dois casos, e entre não aprender uma
   palavra boa e aprender uma furada, o barato é o primeiro.
3. **A palavra com dígito no meio.** `p1ay` é o caso canônico da fase.
4. **Notação**, pelo contrato 1 da SPEC §5.8 — e é o caso mais provável de todos, porque
   lance é o que o revisor mais corrige.

#### Um defeito que a fase criou e fechou no caminho

`Lexico.vazio` era o critério de "não agir", e a F9.2 tornou alcançável o caso em que ele
mente: um livro com `.lexico.txt` ao lado e **sem** `assets/lexico/` instalado tem dezenas
de palavras contra centenas na página — `vazio` diria falso e a tela inteira acenderia.
Entrou `Lexico.sinaliza`, que é `bool(palavras)`: acusar palavra desconhecida exige a lista
geral. As duas fronteiras (`juntar_hifenizadas`, `partir_colada`) continuam olhando
`vazio`, e de propósito — elas só agem quando o resultado **é** palavra conhecida, então
lista curta as deixa quietas em vez de barulhentas.

Cobertura: `tests/test_f92_dicionario.py`, 25 testes, dos quais 10 são sobre o que **não**
entra na lista.

### F9.3 — Salvar a página também alimenta o dicionário — CONCLUÍDA

**Concluída em 2026-08-10.** Pedido do usuário: *"seria possível, assim que terminar de
fazer uma revisão dos boxes de uma página, o programa adicionar palavras novas no
dicionário desta página?"*

A coleta já existia inteira desde a F9.2 — `palavras_confirmadas` e `aprender_da_pagina`,
com as quatro recusas acima. O que faltava era **quando**: ela rodava só dentro de
"Aprender com Página Atual".

**A F9.2 escolheu esse gatilho por um motivo que continua válido, e mesmo assim
insuficiente.** O raciocínio registrado era: é a mesma confirmação sobre a mesma página, e
um segundo item de menu pediria que o usuário se lembrasse de dois. Certo — mas
"Aprender com Página Atual" é **opcional**, e quem revisa uma página e a salva sem mandar
aprender não deixava nada para a página seguinte. O dicionário do livro só crescia para
quem também estava alimentando o k-NN.

Salvar é o outro momento em que o usuário declara ter terminado com a página, e é o
**obrigatório** dos dois. Entrou nos dois caminhos: Ctrl+S e "Salvar todas as páginas".

**Nenhuma regra de admissão mudou, e é isso que torna o gatilho novo seguro.** O filtro
mora em `palavras_confirmadas`, não no comando: salvar uma página que o usuário só folheou
não ensina nada, porque nenhuma palavra dela tem box digitado à mão. Sem essa separação, o
gatilho novo — que agora é rotina, e não mais um ato deliberado — envenenaria a lista
sozinho. Há teste para exatamente isso.

Três decisões menores:

- **Depois da gravação, não antes.** Se o `.box` não escreveu, o usuário não terminou com
  a página coisa nenhuma, e o dicionário não deve ter aprendido dela.
- **Uma escrita por comando, não por página.** "Salvar todas as páginas" recolhe de todas
  e grava a lista uma vez só; reescrevê-la a cada página desfaria N vezes a edição de quem
  mexe no arquivo à mão entre uma página e outra, que é o escape que `salvar_do_usuario`
  existe para preservar.
- **Na thread da UI.** O recolhimento roda no `concluir`, não no `trabalho`: léxico e cache
  de suspeitas são estado da janela. É a mesma razão que já estava escrita em "Aprender com
  Página Atual".

O diálogo de sucesso passa a dizer quantas palavras entraram e lista as oito primeiras — o
arquivo é o lugar do vocabulário, o diálogo é só o aviso de que algo mudou. E a lista
lateral e o canvas são redesenhados na hora: a palavra aprendida deixa de acender ali
mesmo, não na próxima vez que algo os redesenhasse.

Cobertura: `tests/test_f92_dicionario.py`, 5 testes novos (30 no total), 3 deles falham no
código anterior. Os outros dois guardam as recusas contra o gatilho novo.

### O que a F9 não promete

Não melhora a notação (é a F1.7 que faz isso, e ela já está feita). Não alcança a
pontuação, que é metade das confusões medidas. E não ataca o gargalo: na última medição do
pipeline (2026-08-04, 9 páginas rotuladas) a distância entre os 93,8 de F1 e os 99,83% do
classificador em recorte já segmentado continua sendo **segmentação**, e nenhum dicionário
a conserta.

A F9.2 acrescentou um limite que só a medição mostrou: **o dicionário do livro alcança a
palavra que se repete, e nas páginas rotuladas 124 das 128 que acendem aparecem uma vez
só.** Ele apaga 9,2% do alarme falso. O resto do alarme não é vocabulário — é espaço
perdido, fragmento de palavra e nome próprio visto uma vez, e cada um desses tem dono
noutro lugar do pipeline.

---

## F10 — Texto em negativo — CONCLUÍDA

### F10.1 — Ler o texto da tarja preta ou colorida — CONCLUÍDA

**Concluída em 2026-08-06.** `core/negativo.py`, `BoxEntry.negativo`, e a troca entra
sozinha na geração de boxes — sem depender de modelo carregado, ao contrário da F8.1.

**Aqui o programa não lia errado: não lia.** O cabeçalho da partida vem numa tarja —
*"J.Bolbochan – L.Pachman"* em branco sobre preto no Yusupov, *"Section 1 – 9.♘f3"* em
branco sobre cinza no Kasparov. `binarize` deixa a tinta em branco, então a tarja inteira
vira um borrão de tinta, `findContours` com RETR_EXTERNAL devolve **um** box e os
caracteres de dentro não chegam a existir. Medido na página 33 do *Chess Evolution 1*,
antes da fase:

| | antes | depois |
|---|---:|---:|
| tarjas na página | 6 | 6 |
| boxes dentro delas | **6** (um por tarja, 663x55) | **115** |
| caracteres lidos | **0** | 6 nomes de jogador |

Não é caso raro: são 264 páginas com tarja em quase toda partida e todo exercício, e o
nome do jogador é justamente o que a F9.2 quer no dicionário do usuário.

#### O que o classificador lê lá dentro

Seis tarjas conferidas caractere a caractere contra a imagem (a camada de texto do PDF
"editable" **não serve de verdade** — ela própria traz `Boibochan` e `Stefnit`):

| lido | impresso | acerto |
|---|---|---:|
| `K.Emmrich-B.Moritz` | K.Emmrich – B.Moritz | 18/18 |
| `-J.Bolb0chan-L.Pachman` | J.Bolbochan – L.Pachman | 20/21 |
| `Em.Lanker-WSteinitz` | Em.Lasker – W.Steinitz | 18/20 |
| `S.Tarrasch-S.Tart@0wer` | S.Tarrasch – S.Tartakower | 20/23 |
| `M.Td-Miller` | M.Tal – Miller | 10/12 |
| `S.Urusov-Kdinovsb` | S.Urusov – Kalinovsky | 15/19 |
| **total** | | **101/113 = 89,4%** |

Contra 0% antes, e os erros que sobram têm dois nomes: `o`→`0` (o modelo viu pouca
serifa em negrito) e letras coladas que viram uma só (`al`→`d` em *Tal*, *Salwe*,
*Kalinovsky*). O segundo é o defeito da F1.5b, agora alcançável — antes não havia box
para o separador cortar.

#### O livro inteiro, e as três tarjas que a apara não pegou

As 264 páginas do *Chess Evolution 1*: **438 faixas propostas, 438 aceitas**, e todas as
438 são tarja de verdade — auditadas pelo tamanho (a tarja de coluna deste livro mede
660, 670, 775 ou 790 px de largura) e visualmente nas três que fogem disso, que são
*G.Kasparov – I.Smirin*, *T.Barnes – P.Morphy* e *Y.Averbakh & V.Chekhover*.

Essas três fogem por um motivo, e ele valeu uma correção: nelas a tira decorativa é
**escura** o bastante para que suas linhas passem de `SOLIDO`, a apara para na primeira
linha da *tira* em vez da tarja, e a hachura entra no recorte — 119, 112 e 22 boxes para
nomes de ~20 caracteres. A rede que faltava é `na_linha`: os componentes que já se sabe
serem caractere dizem onde está a linha de texto, e o que cai fora dela é decoração.
Depois dela, 21, 55 e 19. Nas outras 435 tarjas e nas 19 do Kasparov, nada muda.

#### Falso positivo: zero em 588 páginas, e não foi de graça

O risco desta fase não é deixar de ler; é **inventar**. Faixa cheia também é foto,
logotipo e — o caso perigoso — palavra em negrito com sublinhado, onde o sublinhado gruda
as letras num componente cheio e largo. Aceitá-la substituiria por lixo um texto que o
caminho normal já lia certo.

Varredura das 324 páginas do Kasparov (scan real) com auditoria visual de tudo que foi
aceito:

| versão | propostas | aceitas | falsos positivos |
|---|---:|---:|---:|
| só apara + conteúdo | 66 | 17 | 0, mas **2 tarjas perdidas** |
| sem a apara como condição | 66 | 39 | **22** (palavra sublinhada) |
| com as duas réguas | 25 | **19** | **0** |

As duas réguas saíram de tabela, não de escolha, e as populações não se tocam:

| | proporção (larg/alt) | altura (em caracteres medianos) |
|---|---|---|
| tarja de verdade | 5,34 – 13,70 | 2,57 – 28,50 |
| palavra sublinhada | 3,00 – 4,72 | 0,41 – 1,21 |
| **limiar** | **4,0** | **2,0** |

**Uma régua não bastou, e as duas se cobrem.** A mediana de altura da página afunda onde
há pontilhado de sumário — na página 6 do Kasparov ela cai a 8 px com a letra medindo 22,
e o fragmento `ening` do título em negrito chega a 2,75 alturas. Quem o recusa é a
proporção (3,09). O caminho oposto — trocar a mediana pelo percentil 75 — resolvia esse
caso e criava outro pior: nas páginas de exercício do Yusupov o percentil 75 vai a 30 px,
o piso passa a 60, e as tarjas de 55 px que são o alvo da fase eram todas recusadas.

#### Três decisões que a medição forçou

**1. A polaridade é do box, e a página não se mexe.** `BoxEntry.negativo` é a mesma
escolha do `angulo` da F8.1: quem classifica quer o glifo como o modelo o viu no treino,
e `vertical.recorte_de_pe` é o funil das duas voltas. Inverter a região na página seria
mais simples e está descartado de propósito — o usuário confere o box contra a página
impressa, e mexer no que ele vê para consertar o que o modelo lê troca um problema de
leitura por um de revisão.

**2. Aparar a faixa é obrigatório; exigir que a apara funcione, não.** Acima da tarja do
Yusupov há uma tira decorativa hachurada, clara o bastante para virar tinta na inversão:
ela encosta no topo das letras e funde meia linha num componente só — 88 componentes numa
tarja de 20 caracteres, dois deles com metade da tarja cada. A apara acha o retângulo
cheio pelas bordas (linha de tarja tem ~100% de tinta, linha de hachura tem 55%–75%). Mas
**a primeira versão recusava a faixa que não tinha borda cheia**, e isso custou a tarja
*"6...♘bd7"* da página 264 do Kasparov: cinza-clara, legível, nove caracteres, e a
binarização marcando só 60%–87% dela. Hoje, faixa sem borda cheia volta inteira e quem
julga é o conteúdo.

**3. A lista tem de voltar ordenada por (y1, x1).** Foi o defeito mais caro da fase e
nenhum teste o anteciparia: `merge_vertical_boxes` mede a distância vertical como
`b2.y1 - b1.y2` e **aceita valor negativo**. Devolvendo as caixas novas no fim da lista,
uma letra da tarja casa com um box do outro lado da página, a caixa resultante atravessa
tudo e passa a absorver a coluna inteira — os 1.889 boxes da página 33 saíram do merge
como **27**. `test_a_lista_volta_ordenada` guarda essa porta.

#### O que esta fase não entrega

**Tarja mais curta que 4:1 não é vista.** Um rótulo colorido de uma palavra só fica
abaixo do limiar de proporção, onde ele é indistinguível de uma palavra em negrito com
sublinhado — e essa palavra o caminho normal já lê certo. O preço está medido e é este.

**Tarja de três linhas não é vista.** O glifo é medido contra a altura da faixa, então a
razão cai a cada linha a mais: a de duas linhas do Kasparov passa em 0,31 contra um piso
de 0,30 — raspando. A correção óbvia (deduzir a altura da linha agrupando os próprios
componentes) é a mesma que aceitaria a palavra sublinhada, cujos vazados se agrupam tão
bem quanto letras; por isso o limite ficou registrado em vez de corrigido.

**Não há árbitro, e a diferença para a F8.1 é deliberada.** Lá, marcar ângulo por
geometria pura mexeria em texto que já estava certo, e por isso o classificador vota.
Aqui a faixa recusada continua rendendo o que rendia antes da fase — nada —, e o risco de
inventar está coberto por duas réguas medidas em 588 páginas. Se aparecer material em que
elas não bastem, o padrão do árbitro está pronto para ser aplicado.

**Fundo colorido é lido como fundo escuro, não como cor.** A página chega em tom de
cinza; uma tarja azul ou vinho vira um retângulo cinza-escuro e entra pelo mesmo caminho.
Tarja de tom **claro** com texto escuro não é caso desta fase — ali o texto é tinta, e o
caminho normal já o lê.

**O custo é de 0,4 ms por página** no scan do Kasparov (2,9 ms a 300 dpi no Yusupov),
contra 267 ms da página inteira. Ele é pago em toda página, inclusive nas que não têm
tarja: o que roda sempre é uma varredura de caixas cheias e largas, e a inversão só
acontece em candidato.

Cobertura: `tests/test_f10_negativo.py`, 31 testes. `medir_negativo.py` refaz as medições
acima — com `--imagens` para scans, com o caminho de um PDF para o resto.

---

## F11 — Texto sobre trama de meio-tom — CONCLUÍDA

### F11.1 — O quadro de pontuação deixa de ser um borrão — CONCLUÍDA

**Concluída em 2026-08-06.** `core/trama.py`, mais `preprocess.escala_de_texto` e
`preprocess.remover_textura`.

O quadro *"Scoring"* que fecha cada capítulo do Yusupov é um painel chapado, e o
escaneamento o devolve como uma nuvem de pontos. O estrago é em dois tempos, e nenhum
deles aparece como erro — aparece como texto que não existe.

**1. A trama envenena a régua.** Medido na página 18:

| | |
|---|---:|
| contornos na página | 6.765 |
| deles com 6x6 px ou menos | **95,8%** |
| mediana das alturas | **2 px** |

Com mediana 2, o limite de `descartar_blocos_nao_texto` fica em 8 px, e o que ele
descarta deixa de ser o diagrama e passa a ser **o texto**. A página saía com o título e
o parágrafo em pedaços e o painel inteiro vazio.

**2. A trama solda.** Os pontos encostam nas letras e as letras umas nas outras: o painel
sai como **um** contorno de 1049x390, e o que estava escrito dentro dele não chega a
existir como box.

#### A régua que não desaba

`escala_de_texto` mede a altura de caractere **por massa de tinta**: o ponto de trama tem
~4 px de tinta e uma letra tem ~200. Medido em 6 páginas:

| página | 17 | 35 | 30 | 33 | 42 | 31 |
|---|---:|---:|---:|---:|---:|---:|
| mediana simples | 2 | 2 | 18 | 18 | 19 | 4 |
| **ponderada por tinta** | **25** | **27** | **34** | **37** | **36** | **57** |

Duas correções que a medição obrigou, e as duas são sobre *qual população medir*:

- **Componentes conexos, não contornos externos.** Naquela população o diagrama é um
  componente só com dezenas de milhares de pixels de tinta, e a mediana ponderada
  aterrissa nele — 390 e 579 px, medido.
- **Bloco fica de fora**, pela regra de que caractere não ocupa 1% de uma página. Sem
  isso a ponderação tem um furo que uma montagem de teste expôs: uma trama que soldou
  numa malha só é *um* componente enorme e vira ela própria a mediana (250 px). Nas
  páginas reais o texto em volta ainda pesava mais, mas depender disso é depender de a
  página ter texto suficiente.

#### Rebinarizar o recorte é o que desfaz a solda

É a manobra da F10 com a polaridade normal, e o motivo é o histograma: na página inteira
o papel branco domina e o Otsu global corta abaixo da trama, que vira tinta e gruda em
tudo. Dentro do painel o papel some da conta e sobram duas populações — trama (tom ~99) e
texto (tom ~5). Ali o Otsu corta em **143**, acima da trama: medido, **71 componentes com
tamanho de caractere onde antes havia zero**.

**O que impede o diagrama de virar 32 boxes de peça** é uma peneira do domínio, com
margem larga: *tabuleiro é quadrado*. Os seis diagramas das páginas 30 e 31 medem
578x579, 579x579 e 580x584 — proporção 1,00 a 1,01. O painel mede 1049x390 — 2,69. O
limiar é 1,5, e nada no material cai entre 1,3 e 2,6. A cobertura por células diria o
mesmo com margem estreita (99,9% no painel contra 82%–91% nos diagramas) e por isso não
é usada.

E a fase é **segura por construção**: só olha dentro de bloco que o descarte ia jogar
fora de qualquer jeito. O pior caso é continuar sem o texto.

#### Não regrediu nada, e isso foi medido no mesmo processo

| | recall | precisão | F1 | espúrios |
|---|---:|---:|---:|---:|
| antes (F11 desligada no mesmo processo) | 94,5% | 93,7% | 94,1 | 332 |
| **depois** | 94,5% | 93,7% | **94,1** | **331** |

As tarjas da F10 continuam em 19 nas 324 páginas do Kasparov, e nas páginas com diagrama
`trama.candidatos` devolve **zero**.

#### O que esta fase não entrega

**A palavra do painel sai colada.** A trama liga letra a letra dentro da palavra, e o
Otsu local não desfaz isso — o que sai são caixas de palavra, não de caractere. É box
utilizável para revisão, e é menos do que a página limpa dá.

**A trama solta continua virando box.** `remover_textura` apaga o componente que é
pequeno **e** claro — as duas coisas, porque pequeno sozinho comeria o ponto final (que
mede o mesmo e é escuro: tom 6–29 contra 77–112 da trama). Na página 18 isso leva os
boxes de 6.765 para 3.117, e sobram ~390 minúsculos que o revisor ainda vê.

**Três discriminadores foram medidos e recusados**, e o registro vale mais que o código
que não entrou:

| ideia | por que não |
|---|---|
| densidade de vizinhos pequenos | não separa: 78%–84% dos pequenos das páginas *limpas* também têm 4+ vizinhos |
| porosidade (papel na janela) | tarja chapada do Kasparov dá 0,36–0,48, trama do Yusupov 0,45–0,69 — sobrepostas |
| segundo Otsu na página toda | corta em ~50 em **toda** página e comeria o contorno anti-serrilhado de todo glifo |

Cobertura: `tests/test_f11_trama.py`, 15 testes. Metade cobra o que **não** pode mudar: o
diagrama continua um bloco descartado, a pontuação escura sobrevive à limpeza, e a página
sem trama sai byte a byte igual.

---

## F12 — O box que engoliu duas linhas — CONCLUÍDA

### F12.1 — Partir o box que cobre duas linhas — CONCLUÍDA

**Concluída em 2026-08-07.** `BoxService.dividir_linhas_coladas`, no pipeline entre o
descarte de bloco e o separador de glifo colado.

**A fase começou por uma medição, não por uma ideia.** Com F0–F11 fechadas, o gargalo
declarado continuava sendo segmentação — 94,1 de F1 no pipeline contra 99,83% do
classificador em recorte já segmentado. Faltava saber *de que* é feita essa distância, e
a conta é esta, nas 10 páginas rotuladas (10.613 caracteres):

| o que falta para 100% de recall | |
|---|---:|
| **colado com o vizinho** (o caractere não ganhou box) | **231** |
| box desalinhado | 5 |
| lido errado (o box estava certo, o modelo errou) | 348 |

| os 331 boxes espúrios | |
|---|---:|
| **sobra perto do texto** | **243** |
| respingo | 45 |
| pedaço de glifo partido | 33 |
| fora do texto | 10 |

O que fez a fase existir foi o *formato* das sobras: `'g' 21x71`, `'♗x' 73x86`, `'♖' 22x71`
— altura 71 e 86 onde a mediana de caractere é 34. **São dois caracteres de linhas
diferentes num box só**: o descendente de uma linha ('y', 'g', 'p') encosta na de baixo.

É o defeito simétrico ao da F1.5b — lá dois vizinhos horizontais se tocam e o contorno sai
largo; aqui o toque é vertical e o contorno sai alto. Só que este não tinha tratamento
nenhum.

#### Proibir o merge não resolveria

Dos 131 boxes altos das páginas rotuladas, só **29** nascem em `merge_vertical_boxes`; os
outros 102 já vêm assim do `findContours`, porque os glifos se tocam de verdade no papel.
É preciso cortar, e o corte é o da F1.5b transposto: `_cortes_do_perfil` já acha vale numa
direção, e passar o recorte transposto o faz olhar na outra — a manobra de
`vertical.fundir_pingos`.

O corte acha **todos os 71** boxes que cobrem rótulos de duas linhas. Nenhum escapa.

#### A lasca é o que decide se a fase paga

Cortar e emitir os dois pedaços **piora** o resultado. Medido com o resto do pipeline
idêntico:

| | recall | precisão | F1 | espúrios |
|---|---:|---:|---:|---:|
| sem cortar (antes da fase) | 94,50% | 93,66% | 94,08 | 331 |
| cortar e emitir os dois pedaços | 94,96% | 92,96% | **93,95** | 441 |
| cortar, descartar pedaço < 0,8 escala | 94,84% | 93,93% | 94,38 | 333 |
| cortar, descartar pedaço < 0,9 escala | 94,81% | 94,13% | 94,47 | 320 |
| **cortar, descartar pedaço < 1,0 escala** | 94,80% | 94,17% | **94,48** | 319 |
| cortar, descartar pedaço < 1,2 escala | 94,74% | 94,24% | 94,49 | 317 |

Emitir a lasca — o pedaço curto que sobra da linha vizinha — custa 2,2 boxes espúrios por
caractere recuperado. Descartá-la converte o mesmo corte em ganho dos dois lados. O valor
é **1,0** por estar no meio do platô 0,9–1,2 (não numa quina) e por caber numa frase:
pedaço mais curto que um caractere não é caractere.

**No pipeline completo, o F1 vai de 94,1 para 94,4** (recall 94,5% → 94,9%, precisão
93,7% → 94,0%, espúrios 331 → 323).

#### Sem árbitro, e a diferença para a F1.5b foi medida

Na F1.5b o classificador é o que salva o corte: box largo é comum e o perfil sozinho
acerta 28,6%. Aqui a geometria já é decisiva — box 1,6 vez mais alto que um caractere é
anômalo por construção, são 109 em 10 páginas — e submeter o corte ao árbitro **derruba** o
ganho:

| | F1 | espúrios |
|---|---:|---:|
| corte sem árbitro | **94,48** | 319 |
| corte com árbitro (margem 0,30) | 94,06 | 337 |

O que o árbitro recusa é justamente o corte certo, porque a lasca da linha vizinha pontua
baixo e a regra dele olha a **menor** parte. Ele não entrou no código: a medida está aqui
e o código fica sem a configuração reprovada.

#### O que esta fase não alcança

**Os 231 colados na horizontal continuam lá**, e são o dobro do que esta fase ataca. O
separador da F1.5b já considera 143 deles (são largos o bastante para virar candidato) e
os recusa; os outros 88 são estreitos demais para ele sequer olhar. Melhorá-lo é mexer no
árbitro, cuja margem já foi varrida e fixada por F1 na própria F1.5b — é pesquisa, não
ajuste, e fica registrada como o próximo alvo natural.

**E 348 caracteres são lidos errado com o box certo** — esses não são segmentação, são
modelo, e nenhum corte os alcança.

Cobertura: `tests/test_f12_linhas.py`, 12 testes. Um terço é sobre a lasca, que é a
metade não óbvia da fase.

---

## F13 — Os colados na horizontal — MEDIDA, sem implementação

A F12 fechou apontando o alvo: *"os 231 colados na horizontal continuam lá, e são o dobro
do que esta fase ataca"*. Esta fase foi medi-los antes de propor corte nenhum, que é como
a F12 e a F1.5b começaram. **A medição desaconselhou o caminho óbvio**, e é isso que fica
registrado.

`medir_colados.py` classifica cada rótulo que não ganhou box, e a divisão é a que importa.

#### Primeiro: são 153, não 231

| o que falta para 100% de recall | F12 (registrado) | hoje |
|---|---:|---:|
| colado com o vizinho | 231 | **153** |
| box desalinhado | 5 | 10 |
| sem box nenhum (sumiu na binarização) | — | 52 |

A explicação mais provável é o **árbitro**, que é o próprio classificador: o modelo foi de
119 para 143 classes em 07/08, e as classes novas são justamente ligaduras e colagens
(`ff`, `ffl`, `+-`, `♗x`). Um árbitro que conhece a colagem pontua diferente e endossa
cortes que antes recusava. Não está verificado — o modelo de 119 classes não existe mais
no disco —, e por isso fica como explicação e não como conclusão.

A linha "sem box nenhum" não existia na conta da F12; são 52 caracteres que a binarização
perde inteiros, e não é assunto de corte.

#### A divisão que decide o ataque

| dos 153 colados | |
|---|---:|
| o separador da F1.5b **olha e recusa** | 104 |
| **estreito demais para ele olhar** | 49 |

O separador só considera box mais largo que `fator_largo` (1,6) vezes a largura de
referência da linha. Os 49 nunca chegam ao árbitro — nenhum ajuste de margem os alcança.

E o formato deles é o achado: **caractere fino grudado em largo.** Os pares mais
frequentes entre os estreitos são `.R` (5), `,h`, `,b`, `.K`, `ik`, `if`, `is`, `,n`,
`,,`, `''`. Um ponto colado num `R` acrescenta uns poucos pixels a um box de 20 — a razão
fica em 1,2 e o box nunca vira candidato. A largura é o gatilho errado para esta família.

| largura do pai, em referências da linha | colados |
|---|---:|
| abaixo de 1,0 | 4 |
| 1,0 a 1,2 | 14 |
| 1,2 a 1,4 | 13 |
| 1,4 a 1,6 | 15 |
| 1,6 a 2,0 (candidato) | 43 |
| 2,0 a 3,0 (candidato) | 59 |
| acima de 3,0 (candidato) | 5 |

#### Baixar o limiar de candidatura não paga, e está medido

O caminho óbvio é abrir a candidatura para alcançar os 49. Varrido com
`medir_paginas.py --fatores`, resto do pipeline idêntico:

| `fator_largo` | recall | precisão | F1 | espúrios | cortes bons | cortes falsos |
|---|---:|---:|---:|---:|---:|---:|
| **1,60 (hoje)** | 95,0% | 93,9% | **94,4** | 338 | 21 | 6 |
| 1,40 | 95,0% | 93,9% | 94,5 | 338 | 23 | 6 |
| 1,20 | 95,1% | 93,9% | 94,5 | 344 | 27 | 9 |
| 1,10 | 95,1% | 93,8% | 94,4 | 350 | 28 | 9 |
| 1,00 | 95,1% | 93,8% | 94,4 | 352 | 28 | 11 |

**O ganho máximo é 0,1 de F1, e some abaixo de 1,2.** Recall sobe um décimo — meia dúzia
de caracteres em 10.613 — e os espúrios sobem junto. Não é o platô da F12 (0,9 a 1,2, com
0,4 de F1 em jogo); é ruído em volta do valor atual. **O código fica com 1,6**, e a
varredura fica aqui para não ser refeita.

O que isto diz é que os 49 não são um problema de *limiar*: eles precisariam de um gatilho
que não seja a largura do box — um apêndice fino na borda tem assinatura própria no perfil
de tinta, e é outra fase, com outra medição, se algum dia pagar.

#### O que sobra, em ordem de tamanho

| | quantos |
|---|---:|
| lido errado com o box certo (modelo, não segmentação) | ~348 |
| colado que o árbitro olha e recusa | 104 |
| sem box nenhum (binarização) | 52 |
| colado estreito demais para o separador olhar | 49 |

O maior alvo deixou de ser segmentação. `medir_colados.py` e o `--fatores` de
`medir_paginas.py` ficam no repositório: a conta se refaz sozinha depois de cada retreino,
e ela mudou uma vez sem que ninguém percebesse.

---

## F14 — Os lidos errado com o box certo — MEDIDA

A F13 terminou dizendo que o maior alvo deixou de ser segmentação. `medir_confusao.py`
é a matriz de confusão **na página real**, que é o que faltava para saber onde mexer.

**Não serve a matriz do treino.** `core.avaliacao` já produz uma, e ela mede outra coisa:
recorte já segmentado, limpo, da mesma base em que o modelo treinou — ali o número é
99,8%. Na página o mesmo modelo dá 96,95%, e a diferença é justamente o assunto.

#### A conta

Nas 10 páginas rotuladas, 10.398 boxes casaram com um rótulo:

| | |
|---|---:|
| lidos certo | 10.081 (96,95%) |
| **lidos errado** | **317** |
| — confusão (a classe existe no modelo) | 313 |
| — classe que o modelo não tem | 4 |

São 317, e não os ~348 da F12 — mesma deriva dos colados, e a mesma explicação
provável: o modelo mudou de 119 para 143 classes em 07/08. **Só 4 são classe faltando**
(`◼`, `d6`, `ar`, e um vazio), então o alvo é confusão de verdade, não vocabulário.

#### As seis famílias

313 pares soltos não dizem o que fazer; seis famílias dizem.

| família | erros | | exemplos |
|---|---:|---:|---|
| **resto** | 130 | 41,5% | `R`→`;` (6), `?`→`t` (6), `u`→`d` (6) |
| **ligadura disparada** | 41 | 13,1% | `T`→`Th` (5), `f`→`f2` (4), `f`→`fi` (4), `4`→`e4` (4) |
| **ligadura (outra)** | 40 | 12,8% | `m`→`an` (9), `B`→`♗x` (7), `s`→`an` (3) |
| **homóglifo** | 37 | 11,8% | `9`→`g` (8), `0`→`o` (8), `1`→`i` (8), `i`→`1` (7) |
| **caixa alta/baixa** | 35 | 11,2% | `P`→`p` (6), `B`→`b` (5), `s`→`S` (4), `C`→`c` (4) |
| **pontuação** | 30 | 9,6% | `.`→`-` (18), `'`→`,` (5), `½`→`/` (4) |

**As ligaduras somam 81 — 26% dos erros, e é a maior família nomeável.** São as classes
acrescentadas no retreino de 07/08 competindo com o caractere isolado: o modelo vê um `T`
e emite `Th`, vê um `f` e emite `f2`. **É candidato a regressão do próprio retreino**, e
uma que teria passado despercebida: o mesmo retreino provavelmente melhorou a segmentação,
porque o árbitro do separador é este modelo (F13). O saldo entre as duas coisas não está
medido, e não dá para medir — o modelo de 119 classes não existe mais no disco.

**Homóglifo mais caixa somam 72 (23%), e não são erro de treino: são o mesmo desenho.**
Um `0` e um `o` da mesma fonte diferem em altura, não em traço; `P` e `p` também. O
recorte de 32x32 que o classificador recebe é normalizado em escala, então a informação
que separaria os dois **foi jogada fora antes de ele ver**. Nenhuma quantidade de amostra
conserta isso — é altura relativa à linha, e ela não está na entrada.

O maior par isolado é `.`→`-` (18), e essa é a pior classe do lote junto de `P` (41,7% de
recall, 5/12) e `?` (50,0%, 18/36).

#### O que a confiança já denuncia hoje

| corte | erros pegos | acertos revisados à toa | erros que escapam |
|---:|---:|---:|---:|
| 0,500 | 41 | 10 | 276 |
| 0,700 | 98 | 123 | 219 |
| 0,900 | 175 | 816 | 142 |
| 0,990 | 229 | 2.834 | 88 |
| 0,999 | 260 | 4.410 | 57 |

Confiança mediana de um erro: **0,8587**. De um acerto: **0,9994**. O corte de 0,700 é o
melhor negócio da tabela — 98 erros por 123 falsos alarmes — e já está disponível pelo
filtro da barra lateral.

#### O que esta medição não decide

Ela não escolhe o remédio, e de propósito. As três famílias grandes pedem coisas
diferentes: ligadura pede rever se as classes novas se pagam (e a medição do saldo exige
guardar o modelo anterior, coisa que o `.gitignore` impede hoje); homóglifo e caixa pedem
**entrada nova** — altura relativa à linha junto do recorte —, que é mudar a arquitetura;
e os 130 do "resto" pedem olhar um a um antes de qualquer teoria.

---

## F15 — O dpi que jogava fora um terço da página — CONCLUÍDA

A pergunta que abriu esta fase era outra: **o que dá para fazer com a imagem antes do
reconhecimento** — tirar ruído, melhorar nitidez. A resposta acabou não sendo um filtro
novo, e sim que o pipeline descartava resolução que já estava no arquivo.

### O que os PDFs são

| Livro | imagem embutida | dpi nativo | renderizado a 200 |
|---|---|---:|---|
| Yusupov, *Chess Evolution 1* | PNG **1 bit** | ~282 | reduz para 71% |
| Aagaard, *Attacking Manual I* | JPEG cor, 8 bit | ~152 | **amplia** para 132% |
| Yusupov_Complete | PNG 1 bit | ~180 | reduz para 90% |

O `DPI_PADRAO = 200` não veio de medição: veio de o `pdf2image` usar 200 por omissão
(F2.2). O comentário que ficou no lugar avisava que mexer nele "mudaria silenciosamente
todos os limiares relativos" da F1.5, e por isso ninguém mexeu.

### F15.1 — Renderizar a 300 — FEITA

Nas 10 páginas rotuladas (~12.000 caracteres), F1 do pipeline inteiro com o modelo de
produção:

| dpi | recall | precisão | F1 | espúrios |
|---:|---:|---:|---:|---:|
| 150 | 87,9% | 89,1% | 88,5 | 438 |
| **200** *(o de antes)* | 93,5% | 93,2% | **93,3** | 310 |
| 250 | 94,8% | 94,3% | 94,6 | 312 |
| **300** *(o de agora)* | 95,8% | 94,8% | **95,3** | 321 |

**+2,0 de F1.** Para escala: a F12 inteira valeu 0,3.

O ganho é de resolução real, e aparece em **todas** as sete páginas do Kasparov, cuja
digitalização tem 300 dpi de verdade: +4,1 +3,6 +3,1 +2,8 +2,9 +2,0 +2,0. Nenhuma exceção.

**Ampliar além do nativo não custa nada, e isso corrigiu a hipótese de partida.** A
proposta era "renderizar no nativo de cada documento e não passar disso". Errado: as três
páginas do Aagaard vêm de uma imagem de ~152 dpi e a 300 vão igual ou melhor que a 200
(+0,2 +0,3 +0,2), enquanto a 150 — praticamente o nativo delas — perdem de 2,4 a 4,0. O
nativo diz onde há ganho a colher, não onde parar. Por isso o valor é fixo e alto, e não
por documento.

Também responde à ressalva que estava no `pdf_service`: os limiares relativos da F1.5 e da
F1.7 aguentam a mudança de escala, e o F1 sobe monotonicamente de 150 a 300.

**Nenhum retreino foi preciso.** A tabela acima é do modelo atual classificando recortes de
300 dpi — o ganho já está líquido da diferença de escala contra a base de treino.

#### O rascunho de autosave precisou de migração

O `.pyboxsession.json` guarda coordenadas em **pixels da renderização** e é restaurado
sozinho na abertura. Trocar o dpi sem mais nada devolveria todo rascunho anterior com cada
box a dois terços da posição, em silêncio. O sidecar passou a registrar o dpi e a
reescalar na leitura; rascunho sem o campo é assumido em 200, que é o único valor que
existiu. O `schema` **continua 1**: subi-lo faria `ler_autosave` recusar exatamente os
rascunhos que ele existe para salvar.

Cobertura: `tests/test_f34_autosave.py`, 4 testes novos.

### O que esta fase deixou aberto

**O risco que a medição não pega, e é o mais importante desta seção.** Nenhuma página do
Yusupov está entre as 10 rotuladas, e é justamente ela que piora a 300 dpi. O livro é um
PNG de **1 bit**: o pontilhado de meio-tom, que a 200 dpi virava cinza na média do
downsample, na resolução cheia volta a ser ponto separado. Medido na página 18:

| dpi | contornos de lixo |
|---:|---:|
| 200 | 139 |
| 282 | 4.970 |
| 300 | 5.973 |

Pior, o **tom** de que `preprocess.remover_textura` depende é fabricado por aquele
downsample. A folga entre o tom da trama e o do texto cai de 103 (a 200 dpi) para 6 (a
300), abaixo do `TEXTURA_FOLGA_DE_TOM = 40` — a F11 deixa de disparar. Os +2,0 de F1 são
reais nos livros medidos; **num livro 1-bit com painel de meio-tom o saldo desta fase não
está medido, e provavelmente é negativo.**

**O remédio existe em protótipo e não entrou.** Um descreening explícito, aplicado só na
região de trama, leva o lixo da página 18 de 4.970 para 433 a 282 dpi e para 168 a 400,
preservando o texto — e não encosta em página limpa: em 40 combinações de página e dpi das
rotuladas, o resultado sai byte a byte igual. A região é achada por densidade de componente
minúsculo com histerese (semente 0,10, crescimento 0,03, lidos de tabela: a densidade
máxima numa página limpa é 0,078 e a da página 18 é 0,149–0,195), e o período do
pontilhado é medido **dentro** da região — medi-lo na página inteira devolve o passo do
caractere e o filtro come o texto (medido: numa página limpa o lixo subiu de 14 para 437).

Não entrou porque **não tem uma única medição de F1 que o justifique**: as páginas onde ele
age não estão rotuladas. Rotular uma página do Yusupov com painel de pontuação é o que
destrava tanto medir o risco acima quanto aprovar o remédio.

**O `.box` antigo carregado à mão.** `save_all_pages` grava `.box` e `.png` em par, então
os pares seguem coerentes. Mas um `.box` de 200 dpi carregado pelo menu sobre uma página
renderizada a 300 fica 1,5x fora de lugar, e o formato do Tesseract não tem onde dizer a
escala. O risco já existia — um `.box` só vale contra a imagem dele — mas ficou provável.

**Custo.** 2,25x os pixels por página; renderização, segmentação e classificação sobem
juntas.

---

## F16 — O EasyOCR usado como detector — CONCLUÍDA

O último elo da cadeia acertava **53,6%**. Medido nos 2.278 caracteres das 10 páginas
rotuladas, com o `.box` à mão como verdade e o recorte na **escala real da página** — e
não nos 32x32 já normalizados da `training_data`, que medem outra coisa.

### A conta

| | acerto | ignorando caixa | custo |
|---|---:|---:|---:|
| como estava (`readtext`) | 53,6% | 64,3% | 61,9 ms |
| `recognize()` no lugar de `readtext()` | 66,7% | 77,9% | 30,5 ms |
| + `quantize=False` | 66,9% | 77,7% | 15,8 ms |
| + `allowlist` | 66,9% | 77,7% | 15,4 ms |
| **+ faixa vertical da linha** | **74,2%** | 78,9% | 16,3 ms |

Conferido depois pelo caminho de produção (`OCRService` + `faixas_de_linha`, como a UI os
chama): **74,9%**, e 3,5x mais rápido.

### O CRAFT rodava de novo, e só atrapalhava — 13,1 pontos

`readtext` detecta antes de reconhecer, e o box já viera do OpenCV: pagava-se a detecção
duas vezes. O CRAFT é detector de texto **em cena**, e num recorte de um caractere ele
frequentemente não acha nada — a tabela de confusão do baseline era dominada por leitura
vazia (`.` 123, `t` 81, `o` 64, `l` 51 lidos como nada; ~410 casos, 18% da amostra). Com
`recognize` e a caixa declarada como a imagem inteira, o detector sai do caminho.

### Normalizar a altura apaga a caixa alta — 7,3 pontos

É a F14 de novo, e agora no outro elo: `preprocess_for_easyocr` redimensiona todo recorte
para 64 px, então `c` e `C` chegam ao modelo como **a mesma imagem**. Dando a faixa
vertical da linha em vez do box justo, o glifo mantém a altura relativa: `s` por `S` (79),
`c` por `C` (40) e `w` por `W` (25) somem da lista de confusões. A coluna "ignorando
caixa" mal se move (77,7 para 78,9) — o ganho é caixa, e nada além disso.

A faixa é **vizinhança de um salto** (`box_service.faixas_de_linha`): cada box olha quem
se sobrepõe a ele em y e para. Fecho transitivo levaria a faixa a atravessar a página por
uma corrente de sobreposições parciais. Bloco alto fica de fora, e box girado (F8.1) fica
com a própria caixa — lá a faixa da linha é horizontal, e misturar as duas voltas trocaria
um ganho medido por um caso não medido.

### O que **não** rendeu

- **`allowlist`: 0,0 ponto.** O alfabeto do livro é quase o charset inteiro do
  `english_g2`. Só valeria com um subconjunto de verdade.
- **Contraste agressivo (`contrast_ths=0.7`): -1,3 ponto.** Piora.
- **`decoder="beamsearch"`: +0,6 ponto**, mas dispara `RuntimeWarning: overflow` dentro do
  `easyocr/utils.py`. Ganho marginal em caminho barulhento; ficou de fora.

### Dois defeitos que a medição não pega

- **O cache do reader ignorava os argumentos** (`if self._reader is None`): a segunda
  chamada com outro idioma ou com `gpu=True` recebia calada o reader da primeira. Agora a
  chave é `(idiomas, gpu)`.
- **A verificação de TLS era desligada no processo inteiro, para sempre.** A primeira
  chamada de OCR fazia `ssl._create_default_https_context = ssl._create_unverified_context`
  como efeito colateral, afetando toda requisição HTTPS do programa, e nunca religava.
  Continua valendo onde era preciso — o download do modelo em rede corporativa — e é
  restaurado no `finally`.

### O que fica em aberto

**Ler a linha inteira, e não o caractere.** O `english_g2` é um CRNN treinado em
palavra/linha; usá-lo caractere a caractere descarta o modelo de linguagem implícito que é
a força dele. Medido em 6.783 caracteres, com o espaço tirado dos dois lados (o `.box` não
tem box de espaço, e sem isso cada um contaria como erro):

| | CER | custo |
|---|---:|---:|
| por caractere (o melhor acima) | 27,3% | 16,0 ms/char |
| **linha inteira** | **13,4%** | **2,1 ms/char** |

Metade do erro e 7,6x mais rápido. O mecanismo aparece nos exemplos — `Bib1i0g[aPhY` vira
`Bibliography`, `F0reW0rd` vira `Foreword` —, e são exatamente as confusões residuais que
sobraram (`o` por `0` 92, `l` por `1` 53, `p` por `P` 26, `v` por `V` 17): as que só o
contexto resolve, e por caractere não há contexto com que resolvê-las.

**Duas ressalvas antes de fazer.** Cobre **81% das linhas / 76,4% dos caracteres** — as que
estão inteiras no alfabeto do EasyOCR; as outras são as linhas de notação com figurinha
(♗, ♘) e ligadura, que é o coração do livro e onde a rede própria já vai bem. E a linha
devolve uma string onde o programa precisa de um caractere por box: dá para reaproveitar
`notacao._alinhar`, aceitando a leitura só quando o comprimento bate com o número de boxes
e caindo no modo por caractere quando não bate. Sem esse recuo, um caractere a menos
desloca a linha inteira.

**O `searchable_pdf` ainda não passa a faixa.** `gerar_pdf_pesquisavel` chama
`fallback_chain` com o recorte justo, então o caminho de PDF inteiro tem os 13,1 pontos do
`recognize` mas não os 7,3 da faixa.

---

## F17 — Ler a linha, e não o caractere — CONCLUÍDA

A F16 parou em 74,9% e a lista de confusões que sobrou dizia o que faltava: `o` por `0`
(92), `l` por `1` (53), `p` por `P` (26), `v` por `V` (17). Nenhum desses é decidível
olhando um glifo de cada vez — `0` e `o` da mesma fonte diferem em altura, `1` e `l` em
quase nada. São pares que só o contexto separa, e por caractere não há contexto nenhum.

O `english_g2` é um CRNN treinado em palavra e linha. Usá-lo caractere a caractere
descartava o modelo de linguagem implícito que é a força dele.

### A conta

Medido em 8.758 caracteres das páginas rotuladas, pelo módulo de produção:

| | acerto |
|---|---:|
| por caractere (a F16) | 72,9% |
| **por linha, com alinhamento** | **89,5%** |

Só nas linhas que estão 100% dentro do alfabeto do EasyOCR (76,4% dos caracteres): 91,7%.
Os exemplos dizem o mecanismo melhor que a tabela — `Bib1i0g[aPhY` vira `Bibliography`,
`F0reW0rd` vira `Foreword`, `LeVe1` vira `Level`.

### O problema é distribuir a string pelos boxes

A linha devolve uma string; o programa precisa de um caractere por box. Não há de onde
tirar a posição de cada um: o `recognize` devolve **uma** caixa para a faixa inteira, e a
saída do CTC não expõe o passo de tempo.

**A regra estrita — aceitar só quando o comprimento bate — cobre pouco.** Medido, bate em
151 das 275 linhas (54,9%); a política que cai no modo por caractere nas outras dá 80,4%.
Nas linhas em que bate, a leitura por linha acerta 91,1% — o problema era aproveitar isso
nas outras 45%.

**A leitura por caractere é a âncora**, e resolve. Ela tem, por construção, exatamente um
item por box; alinhar a string da linha contra ela (`notacao._alinhar`, a mesma distância
de edição da F1.7) distribui os caracteres sem precisar de posição na imagem. O desvio
mais comum é a linha trazer caractere **a mais** que boxes (+1 em 34 linhas, +2 em 29), e
o alinhamento os descarta.

Custo: a linha custa 1,5 ms por caractere, mas a âncora é obrigatória, então o total fica
em torno do dobro do caminho por caractere sozinho. É o preço dos 16,6 pontos.

### O buraco na âncora, que quase passou

`"".join` de uma lista com leitura vazia **encurta a string**, e aí o índice devolvido pelo
alinhamento deixa de ser o índice do box: tudo depois dele anda uma casa. A primeira
medição tinha esse defeito e ainda assim dava 91,2% — o erro é raro o bastante para não
aparecer na média, e teria entrado em produção como um deslocamento silencioso de linha.
O vazio agora vira `MARCA_DE_VAZIO` (`\x00`), que não existe em página nenhuma, nunca casa
com nada e por isso sempre cede a vez para o que a linha leu. Corrigido, 91,7%.

### A confiança sai da concordância, não da linha

O `recognize` devolve uma confiança para a faixa inteira, e distribuí-la igual por todos os
boxes seria inventar precisão que não foi medida. O que existe de verdade é a concordância
entre as duas leituras: quando linha e caractere dizem o mesmo, uma corrobora a outra e
vale a **maior**; quando divergem, a linha venceu mas há dúvida real, e vale a **menor** —
que é o que põe o box na fila de revisão em vez de escondê-lo.

Medido, a confiança resultante separa: dos caracteres com confiança ≥ 0,5 o acerto é
**95,8%**; abaixo disso, **66,9%**. Ela é informativa, e não decorativa.

### O filtro de alfabeto não serve num preenchimento

`em_bloco` sabe recusar linha com glifo fora do alfabeto do EasyOCR, mas olha `b.char` — e
num preenchimento o box ainda não tem caractere. Então na prática a linha é lida em bloco
mesmo onde há figurinha e ligadura. **Medido de propósito nesse cenário**, que é o que o
programa faz: 89,5% sem filtro nenhum contra 91,7% com. O alinhamento aguenta as linhas de
notação — a figurinha vira caractere a mais e é descartada.

Fica de fora, e volta ao modo por caractere: linha com box **girado** (F8.1) ou em
**negativo** (F10). Nos dois a faixa da linha deixa de ser um retângulo em pé na página.

### Onde está

`core/leitura_de_linha.py` (`distribuir`, `confianca`, `em_bloco`, `ler_pagina`),
`OCRService.easyocr_linha_conf` e duas entradas novas no menu Ferramentas: **Preencher
caracteres (EasyOCR por linha)** e **Detectar e Preencher (EasyOCR por linha)**. As ações
por caractere ficaram, porque são o outro lado da comparação e custam metade.

Cobertura: `tests/test_f17_leitura_de_linha.py`, 28 testes.

---

## F18 — A leitura por linha no PDF pesquisável — CONCLUÍDA, e rende quase nada

A F17 deu 16,6 pontos e o `searchable_pdf` tinha ficado de fora. Levá-la para lá era o
passo óbvio. **Não é**, e a medição é o assunto desta fase.

### Lá o EasyOCR não é o leitor

No `searchable_pdf` o `reconhecer` é a cadeia inteira. Medido nas páginas rotuladas, com
os boxes gerados pelo OpenCV — como o próprio módulo os monta, e não com os boxes da
verdade:

| fonte | boxes | | acerto |
|---|---:|---:|---:|
| neural | 2.472 | 98,9% | 97,6% |
| easyocr | 17 | **0,7%** | — |
| learner | 11 | 0,4% | — |

Os 16,6 pontos da F17 foram medidos contra o EasyOCR **sozinho** (72,9% para 89,5%). Aqui
ele é o último recurso de 0,7% dos casos, e a rede — que responde o resto — está 8 pontos
acima dele.

### A varredura do limiar

2.278 caracteres, cadeia completa carregada. A linha só troca o caractere de um box cuja
confiança da cadeia esteja abaixo do corte:

| a linha manda quando | acerto |
|---|---:|
| nunca (o de antes) | 97,50% |
| confiança < 0,70 | **97,54%** |
| confiança < 0,90 | 97,50% |
| confiança < 0,99 | 97,32% |
| **sempre** | **90,21%** |

O melhor caso é **+0,04 ponto — um caractere em 2.278**. No corte de 0,90 a linha mexeu em
2 boxes: consertou 1 e quebrou 1. E mandar sempre custa **7,3 pontos**, porque seria trocar
a rede a 97,6% pelo EasyOCR a 89,5%.

Ficou o corte de 0,70, que é o melhor da tabela e por acaso o mesmo que a F14 apontou como
o melhor negócio da triagem por confiança. `ler_linha` é opcional: sem ele o caminho é
byte a byte o de antes, e nenhum chamador antigo paga nada.

**Está registrado aqui para não ser refeito.** Um dia alguém vai olhar a F17 e a F16, ver
que o PDF pesquisável usa a cadeia, e propor de novo levar a linha para lá. A resposta é
esta tabela: o gargalo do `searchable_pdf` não é o último elo, é a rede e a segmentação.

### O defeito que isto desenterrou, e esse valeu a fase inteira

Ao ligar o `searchable_pdf` no `distribuir`, a asserção da F17 estourou: **a cadeia neural
emite ligadura** (`fi`, `♗x`) num box só, e `"".join` deixava a âncora **maior** que o
número de boxes. É o mesmo deslocamento silencioso de linha do vazio da F17, pelo lado
oposto — e nunca apareceria no caminho só-EasyOCR, porque lá `easyocr_ocr_conf` trunca no
primeiro caractere.

A ligadura agora entra na âncora pela primeira letra, para o alinhamento ter onde encaixar,
e **fica fora da troca**: um box que a cadeia leu como ligadura é justamente o que o EasyOCR
não sabe escrever, e deixá-lo ser sobrescrito trocaria `♗x` por `B`.

Cobertura: 4 testes em `tests/test_f21_pdf_pesquisavel.py`, 2 em
`tests/test_f17_leitura_de_linha.py`.

---

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

## Fora de escopo (registrado para depois)

- ~~Extração de FEN dos diagramas~~ — **promovida para F7.1** (feita)
- ~~Exportação PGN da notação reconhecida~~ — **promovida para F6.1** (feita)
- ~~Modelo de linguagem sobre notação de xadrez~~ — **promovido para F1.7** depois de
  avaliar o DocuVision-AI (ver abaixo)
- ~~Substituição do k-NN linear de `CharacterLearner` por índice FAISS/KD-tree~~ —
  **promovida para F7.2**, e o índice não foi preciso: dedup mais busca vetorizada
  deram 112x sem aproximar nada
- Empacotamento com PyInstaller
