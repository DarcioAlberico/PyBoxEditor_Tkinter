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
(127.264 amostras, 105 classes). Mas hoje **ele não roda**: cinco defeitos de
runtime bloqueiam o caminho principal, e a funcionalidade-carro-chefe
(substituição de glifos de xadrez) **corrompe o PDF em silêncio**.

Todos os itens P0 abaixo foram reproduzidos executando o código, não inferidos por leitura.

| Fase | Tema | Resultado esperado | Status |
|------|------|--------------------|--------|
| **F0** | Desbloqueio | O app abre, edita e salva sem exceção | **concluída** (branch `fix/f0-desbloqueio`) |
| **F1** | Qualidade de OCR | Acurácia medível; segmentação e leitura corretas | **concluída** (F1.1–F1.9) |
| **F2** | Saída PDF | PDF pesquisável, sem rasterizar o documento | **concluída** (F2.1–F2.4) |
| **F3** | Produtividade | Revisão de 2.000 caracteres/página deixa de ser inviável | parcial (F3.1–F3.4 e F3.7 feitas) |
| **F4** | UI | Interface responsiva, sem congelar | parcial (F4.1–F4.3, F4.5 e F4.6 feitas; falta F4.4) |
| **F5** | Higiene | Dependências corretas, código morto removido, testes | parcial (F5.1 e F5.3 feitas) |

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
- `model_meta.json` está no git e `custom_model.pth` não (`*.pth` é ignorado). É
  exatamente o descasamento que a SPEC §5.5 descreve, e continua em aberto lá.

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

Cobertura: `tests/test_f19_calibracao.py`, 21 testes.

### F1.6 — Ordenação de leitura ignora colunas

`sort_boxes_reading_order` (`box_service.py:36`) agrupa por sobreposição vertical.
Livros de xadrez são fortemente diagramados, muitos em duas colunas. O algoritmo vai
intercalar as colunas linha a linha, produzindo texto embaralhado.

O DocuVision confirma que o problema é real, mas a solução dele não vale a cópia: mede a
brancura de uma faixa fixa (42%–58% da largura) e assume duas colunas iguais. Um perfil de
projeção vertical acha as calhas em qualquer posição e com qualquer número de colunas.

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
| F3.5 | **Atalhos** — Ctrl+S, Ctrl+O, PgUp/PgDn (páginas), Tab/Shift+Tab | Fluxo sem mouse |
| F3.6 | **Aplicar a todos os semelhantes** — corrigiu um `e`, corrige os 300 iguais | Ganho de ordem de grandeza |
| F3.7 | ~~Boxes persistem por página de PDF~~ — **CONCLUÍDA** | Evita perda silenciosa de trabalho |

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

**Custo colateral medido, ainda em aberto:** `_commit_change` gasta ~15,7 ms numa página
de 2.000 boxes só no `deepcopy` do histórico — ou seja, ~15 ms por tecla no modo
digitação contínua. Está dentro do critério, mas é o próximo gargalo natural
(snapshot incremental em vez de cópia integral).

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

### F4.4 — `update_sidebar` reconstrói a lista inteira a cada tecla

`delete(0,"end")` + N `insert()` a cada seleção (`main_window.py:564`). Com 2.000
boxes, cada seta pressionada refaz 2.000 linhas. A digitação engasga.

**Ação:** atualizar só as linhas alteradas, ou migrar para `ttk.Treeview` virtualizado.

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

### F5.2 — Formato `.box` perde dados

`_save_box_to_path` (`main_window.py:709`) grava `ch[0]` — **trunca ligaduras
silenciosamente**. Um box marcado como `fi` é salvo como `f`. E `~` é usado como
marcador de vazio, então um `~` real vira vazio na volta.

### F5.3 — Sem testes

Nenhum teste automatizado. `test_chess_pdf.py` é um stub que imprime "a sintaxe está
correta" e não testa nada — a função de teste está comentada. `test_draw.py` e
`test_fonts.py` são scripts manuais.

Os quatro bugs de F0.1 seriam pegos por um único teste que constrói um `BoxEntry` e
chama `update_sidebar`.

### F5.4 — Arquivos de desenvolvimento no repositório

`debug_imports.py`, `debug_runner.py`, `debug_simulation.py`, `debug_tk.py`,
`crash_log.txt`, `full_log.txt`, `test_image.png`, `test_emj.png`, `test_sym.png`,
`Novo Documento de Texto.txt`, `training_data_2/` (138 PNGs soltos, fora do padrão
de pastas por classe).

O projeto também **não é um repositório git**. Sem controle de versão, refatorar é
apostar.

---

## Ordem de execução

```
CONCLUÍDAS
  F0.1  BoxEntry (4 pontos)            F3.7  boxes por página + aviso
  F0.2  fonte Unicode do PDF           F4.1  threads
  F0.3  undo/redo                      F4.2  barra de status
  F0.4  requirements.txt               F3.2  cor por confiança
  F5.3  teste de fumaça                F3.3  filtros e navegação
  F5.1  remover código morto           F3.1  digitação contínua
  F2.1  PDF pesquisável                F3.4  autosave e recuperação
  F1.4  saneamento do dataset          F1.1  cobertura de peças (premissa era errada)
  F1.6  ordem de leitura e colunas     F1.5  pré-processamento e glifos colados
  F1.2  balanceamento (25.075:1)       F1.3  split de validação
  F1.7  validação por legalidade

PRÓXIMAS — qualidade de reconhecimento
  F1.5b divisor de glifos parte 'N' em negrito   ← custa 4,9pp de acerto
  F1.9  calibrar a confiança (o erro sai com 1,000 de confiança)
  F1.8  mascarar diagramas antes de detectar

DEPOIS
  F2.2  remover Poppler          ← searchable_pdf.py já usa só PyMuPDF
  F2.3  relatório e dry-run
  F2.4  perfis de mapeamento por fonte
  F3.5  atalhos restantes        F3.6  aplicar a todos os semelhantes
  F4.3–F4.6  polimento de UI     F5.2  formato .box    F5.4  limpeza de arquivos
```

**O que a F1.1 mudou nas prioridades.** A investigação mostrou que o classificador
acerta figurinas isoladas com confiança 1,000; os erros vieram de boxes em que a
figurina foi **fundida com a coordenada seguinte**. Ou seja, o limitador de qualidade
hoje é **segmentação** (F1.5 e F1.6), não o modelo. Retreinar antes de arrumar a
segmentação renderia pouco.

**A dependência que travava o retreino saiu inteira, e o retreino foi feito.** F1.2 e
F1.3 estão prontas — o sorteio compensa o desbalanceamento, o número exibido é medido
em dados que o modelo não viu, e o checkpoint deixou de ser o ponto de maior
overfitting. `custom_model.pth` foi refeito em 2026-08-04: 99,83% no conjunto de
teste, contra nenhum número confiável antes.

**O que a F1.7 mudou nas prioridades.** Medindo a página real, o limitador voltou a ser
segmentação: o separador de glifos da F1.5 parte o `N` em negrito e custa 4,9 pontos de
acerto, sozinho. E a confiança do modelo não distingue acerto de erro (mediana 1,000 nos
dois casos), o que deixa inerte tanto a ponderação da F1.7 quanto a cor da F3.2 e o
filtro da F3.3 — daí a F1.9. Os dois valem mais que a F1.8.

**~~F1.7 depende de F3.2~~** — **não dependia.** A F3.2 gravou a confiança, mas a
confiança gravada não distingue certo de errado, então a legalidade acabou fazendo o
trabalho sozinha. Medição no item.

---

## Fora de escopo (registrado para depois)

- Extração de FEN dos diagramas (a spec v1.0 §3 já marca como fase posterior)
- Exportação PGN da notação reconhecida
- ~~Modelo de linguagem sobre notação de xadrez~~ — **promovido para F1.7** depois de
  avaliar o DocuVision-AI (ver abaixo)
- Substituição do k-NN linear de `CharacterLearner` (varre 127k referências por
  predição — O(n) por caractere) por índice FAISS/KD-tree
- Empacotamento com PyInstaller
