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
| **F1** | Qualidade de OCR | Acurácia medível; segmentação e leitura corretas | **concluída** (F1.1–F1.9, F1.4b, F1.5b) |
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

Cobertura: **1.614 testes**, `pytest` na raiz, 189 segundos.

> As digitalizações não estão no repositório (`ilovepdf_pages-to-jpg/` é material com
> direitos autorais). Num clone limpo sobram 2 páginas rotuladas com imagem, não 9, e os
> números acima **não** serão reproduzidos. `medir_paginas.py` e `calibrar_modelo.py`
> rodam com o conjunto que encontrarem — só medem menos.

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

## As fases concluídas, e onde está cada uma

O corpo de cada fase — o que entrou, o que foi medido, onde está no código — mora em
`docs/historico/`, movido para lá em 2026-10-06 (item 8 da análise geral) para o arquivo vivo
voltar a caber numa leitura. As fases novas continuam a entrar aqui, antes do "Fora de escopo";
quando este arquivo crescer de novo, outra faixa vai para o histórico.

- [`docs/historico/ROADMAP_F0-F18.md`](docs/historico/ROADMAP_F0-F18.md) — F0 a F18, 4807 linhas
- [`docs/historico/ROADMAP_F19-F93.md`](docs/historico/ROADMAP_F19-F93.md) — F19 a F93, 4861 linhas
- [`docs/historico/ROADMAP_F94-F125.md`](docs/historico/ROADMAP_F94-F125.md) — F94 a F125, 4729 linhas

| Fase | Título | Arquivo |
|---|---|---|
| F0 | Desbloqueio (crítico) | `ROADMAP_F0-F18.md` |
| F1 | Qualidade de OCR | `ROADMAP_F0-F18.md` |
| F2 | Saída de PDF | `ROADMAP_F0-F18.md` |
| F3 | Produtividade | `ROADMAP_F0-F18.md` |
| F4 | Interface | `ROADMAP_F0-F18.md` |
| F5 | Higiene do código | `ROADMAP_F0-F18.md` |
| F6 | Saída de partidas | `ROADMAP_F0-F18.md` |
| F7 | Diagramas e desempenho | `ROADMAP_F0-F18.md` |
| F8 | Texto girado e diagramas conferíveis | `ROADMAP_F0-F18.md` |
| F9 | Léxico do texto corrido — CONCLUÍDA (F9.1, F9.2 e F9.3) | `ROADMAP_F0-F18.md` |
| F10 | Texto em negativo | `ROADMAP_F0-F18.md` |
| F11 | Texto sobre trama de meio-tom | `ROADMAP_F0-F18.md` |
| F12 | O box que engoliu duas linhas | `ROADMAP_F0-F18.md` |
| F13 | Os colados na horizontal — MEDIDA, sem implementação | `ROADMAP_F0-F18.md` |
| F14 | Os lidos errado com o box certo — MEDIDA | `ROADMAP_F0-F18.md` |
| F15 | O dpi que jogava fora um terço da página | `ROADMAP_F0-F18.md` |
| F16 | O EasyOCR usado como detector | `ROADMAP_F0-F18.md` |
| F17 | Ler a linha, e não o caractere | `ROADMAP_F0-F18.md` |
| F18 | A leitura por linha no PDF pesquisável — CONCLUÍDA, e rende quase nada | `ROADMAP_F0-F18.md` |
| F19 | A altura relativa à linha — MEDIDA, e o remédio não é este | `ROADMAP_F19-F93.md` |
| F20 | A leitura por linha no «Detectar e Preencher (Neural)» | `ROADMAP_F19-F93.md` |
| F21 | A leitura por linha no «Híbrido/Ref» — CONCLUÍDA, e aqui ela rende | `ROADMAP_F19-F93.md` |
| F22 | O modelo calibrado, e as travas remedidas contra ele | `ROADMAP_F19-F93.md` |
| F23 | O limiar que se justificava por outro limiar | `ROADMAP_F19-F93.md` |
| F24 | O voto e a margem — MEDIDAS, e as duas voltaram | `ROADMAP_F19-F93.md` |
| F25 | A calibração que o retreino apagou, e os dois usos da confiança | `ROADMAP_F19-F93.md` |
| F26 | O aviso que faltava, e o canal que ninguém lia | `ROADMAP_F19-F93.md` |
| F27 | O treino calibra sozinho no fim | `ROADMAP_F19-F93.md` |
| F28 | O aviso nos outros caminhos | `ROADMAP_F19-F93.md` |
| F29 | Quanto a calibração mexe na segmentação — MEDIDA, e mexe quase nada | `ROADMAP_F19-F93.md` |
| F30 | A margem 0,00, medida direito — MEDIDA, e o 0,30 fica | `ROADMAP_F19-F93.md` |
| F31 | Quanto custa um corte falso na revisão — MEDIDA | `ROADMAP_F19-F93.md` |
| F32 | O lado do ganho, e um erro de aritmética meu na F31 — MEDIDA | `ROADMAP_F19-F93.md` |
| F33 | A margem do árbitro cai para 0,00 | `ROADMAP_F19-F93.md` |
| F34 | A segmentação duplicada do instrumento | `ROADMAP_F19-F93.md` |
| F35 | O `DISTANCIA_MAXIMA`, o último sem tabela — MEDIDO, e está certo | `ROADMAP_F19-F93.md` |
| F36 | O filtro de glifo que ninguém alimentava — MEDIDO, e ele custa | `ROADMAP_F19-F93.md` |
| F37 | A altura relativa apontada ao k-NN — MEDIDA, e a premissa estava invertida | `ROADMAP_F19-F93.md` |
| F38 | Os botões que não giravam | `ROADMAP_F19-F93.md` |
| F39 | O último limiar sem tabela, no outro caminho — CONCLUÍDA, e ele cai para 0,30 | `ROADMAP_F19-F93.md` |
| F40 | O outro laço ganha instrumento — CONCLUÍDA, e a F18 se confirma | `ROADMAP_F19-F93.md` |
| F41 | Duas definições de "página rotulada", e uma tabela publicada sobre a errada | `ROADMAP_F19-F93.md` |
| F42 | O `contexto` que falta no laço do PDF — MEDIDO, e não paga | `ROADMAP_F19-F93.md` |
| F43 | Um número serve dois usos — MEDIDO, e separá-los rende pouco (números refeitos na F47) | `ROADMAP_F19-F93.md` |
| F44 | A margem chega ao box, e o corte da revisão muda — DESFEITA na F47 | `ROADMAP_F19-F93.md` |
| F45 | O ponto cego do EasyOCR — MEDIDO, e a concordância o abre | `ROADMAP_F19-F93.md` |
| F46 | O limiar do híbrido remedido — MEDIDO, e o 0,30 fica por um motivo novo | `ROADMAP_F19-F93.md` |
| F47 | A margem não ganha da confiança, e as duas fases que disseram que sim estavam medindo e… | `ROADMAP_F19-F93.md` |
| F48 | O ponto cego do EasyOCR fecha, e sem dado novo | `ROADMAP_F19-F93.md` |
| F49 | Salvar e reabrir zerava a fila de revisão | `ROADMAP_F19-F93.md` |
| F50 | O léxico é aditivo, e agora está medido | `ROADMAP_F19-F93.md` |
| F51 | A régua de cada fonte, medida — e a mais plana é a que cobre a página | `ROADMAP_F19-F93.md` |
| F52 | A trava contra o instrumento copiar a regra de produção | `ROADMAP_F19-F93.md` |
| F53 | A regra da F48 valia onde não foi medida, e a cor discordava da fila | `ROADMAP_F19-F93.md` |
| F54 | A outra régua da rede desarruma um quarto da ordem e não separa um erro a mais — MEDIDA | `ROADMAP_F19-F93.md` |
| F55 | O número que isentou o leitor era da outra ação, e a isenção estava certa por outro motivo | `ROADMAP_F19-F93.md` |
| F56 | A ação que deixava escapar 803 erros tem uma fonte só, e o orçamento de hoje bastaria a… | `ROADMAP_F19-F93.md` |
| F57 | A régua de `easyocr_so` não é a confiança dele, é concordar com o k-NN — MEDIDA | `ROADMAP_F19-F93.md` |
| F58 | O diagrama deixa de ser recorte e passa a ser desenho | `ROADMAP_F19-F93.md` |
| F59 | O modo de fonte embutida — CONCLUÍDA (com uma verificação em aberto) | `ROADMAP_F19-F93.md` |
| F60 | O cabeçalho do diagrama volta, como faixa | `ROADMAP_F19-F93.md` |
| F61 | O livro de duas colunas deixa de sair misturado | `ROADMAP_F19-F93.md` |
| F62 | A fonte que desenha os símbolos vai junto | `ROADMAP_F19-F93.md` |
| F63 | O apóstrofo deixava a prosa em pedaços | `ROADMAP_F19-F93.md` |
| F64 | O apóstrofo deixa de abrir banda sozinho | `ROADMAP_F19-F93.md` |
| F65 | O apóstrofo deixa de virar troca de coluna | `ROADMAP_F19-F93.md` |
| F66 | O erro de OCR dos "títulos em negrito" — MEDIDO, e o reparo não paga | `ROADMAP_F19-F93.md` |
| F67 | O `⩱`, o `⩲` e a faixa que ninguém podia pesquisar | `ROADMAP_F19-F93.md` |
| F68 | O `✝` era o `+` do xeque | `ROADMAP_F19-F93.md` |
| F69 | A prova visual do reparo, e o comprimento deixa de decidir — CONCLUÍDA (instrumento) | `ROADMAP_F19-F93.md` |
| F70 | Uma letra do cabeçalho apagava a calha da página inteira | `ROADMAP_F19-F93.md` |
| F71 | A tabela não saía partida: não saía | `ROADMAP_F19-F93.md` |
| F72 | A tabela sai como tabela | `ROADMAP_F19-F93.md` |
| F93 | A pasta de revisão passa a ter régua, e o teto pegava uma página só | `ROADMAP_F19-F93.md` |
| F94 | A letra que o OCR não consegue aprender sozinho | `ROADMAP_F94-F125.md` |
| F95 | O diagrama dentro do painel, e o que está impresso em volta dele | `ROADMAP_F94-F125.md` |
| F96 | O detector vindo de fora, e o laço que travava a página — CONCLUÍDA: o de casa ganha, o… | `ROADMAP_F94-F125.md` |
| F97 | A moldura, o corpo em pontos, e o vão entre as filas | `ROADMAP_F94-F125.md` |
| F98 | A segunda fonte de diagrama, e as três suposições que ela derrubou | `ROADMAP_F94-F125.md` |
| F99 | A coordenada desenhada pela própria fonte de xadrez | `ROADMAP_F94-F125.md` |
| F101 | A quina redonda, e a caixinha que teria funcionado em um caso só | `ROADMAP_F94-F125.md` |
| F102 | Vinte e duas classes esperavam o treino, e sete delas não tinham desenho | `ROADMAP_F94-F125.md` |
| F103 | Todo livro que este projeto exportou saiu com um parágrafo por linha | `ROADMAP_F94-F125.md` |
| F104 | A confusão de caracteres de um livro inteiro, sem gabarito — CONCLUÍDA (instrumento) | `ROADMAP_F94-F125.md` |
| F105 | O negrito do impresso chega ao arquivo | `ROADMAP_F94-F125.md` |
| F106 | O `I` grosso e o ponto saíam como travessão, e a rede não tinha como saber | `ROADMAP_F94-F125.md` |
| F107 | O tamanho do glifo se perdia na gravação, e a régua do espaço media contra a coisa errada | `ROADMAP_F94-F125.md` |
| F108 | O dicionário era cego a caixa, e por isso ninguém via o `biShop` | `ROADMAP_F94-F125.md` |
| F109 | Uma palavra de prosa em cinco sai com defeito, e a maioria não é do modelo | `ROADMAP_F94-F125.md` |
| F110 | O livro já trazia o texto, e o projeto o leu da imagem — CONCLUÍDA (a camada tipográfic… | `ROADMAP_F94-F125.md` |
| F111 | O arquivo abre no Word e não é um livro | `ROADMAP_F94-F125.md` |
| F112 | A geometria decide a caixa, e um dos dois caminhos não pede rótulo nenhum — CONCLUÍDA (… | `ROADMAP_F94-F125.md` |
| F113 | Onde não há corte, não há corte errado — MEDIR ANTES DE DECIDIR | `ROADMAP_F94-F125.md` |
| F114 | O motor de linha já estava instalado, e o projeto o chamava letra por letra — CONCLUÍDA… | `ROADMAP_F94-F125.md` |
| F115 | O caractere derrubado escrevia dois espaços, e os reparos do dicionário nunca viam a pa… | `ROADMAP_F94-F125.md` |
| F116 | A trava da linha protegia o elo cuja confiança não diz nada | `ROADMAP_F94-F125.md` |
| F117 | A máscara de alfabeto chega à tela, e a cadeia passa a ter um crivo só | `ROADMAP_F94-F125.md` |
| F118 | A palavra sem uma letra de âncora arrastava o dicionário inteiro | `ROADMAP_F94-F125.md` |
| F119 | A prova do reparo perguntava à rede uma letra de cada vez, e a exportação passava horas… | `ROADMAP_F94-F125.md` |
| F120 | O diagrama em fonte saía 7×8: a casa clara da Merida era o espaço da ponta de um parágrafo | `ROADMAP_F94-F125.md` |
| F121 | O pontilhado do sumário virava a régua de tamanho, e o ponto saía apóstrofo | `ROADMAP_F94-F125.md` |
| F122 | A moldura do diagrama em texto sai da própria fonte, e a SkakNew ganhou a dela | `ROADMAP_F94-F125.md` |
| F123 | A geometria da linha chega à janela, e a tabela por livro foi medida antes de ser feita | `ROADMAP_F94-F125.md` |
| F124 | O Tesseract ganha prazo, e o livro desiste do executável que não volta | `ROADMAP_F94-F125.md` |
| F125 | O aplicativo ganha um bundle desktop reproduzível | `ROADMAP_F94-F125.md` |

## Fora de escopo (registrado para depois)

- ~~Extração de FEN dos diagramas~~ — **promovida para F7.1** (feita)
- ~~Exportação PGN da notação reconhecida~~ — **promovida para F6.1** (feita)
- ~~Modelo de linguagem sobre notação de xadrez~~ — **promovido para F1.7** depois de
  avaliar o DocuVision-AI (ver abaixo)
- ~~Substituição do k-NN linear de `CharacterLearner` por índice FAISS/KD-tree~~ —
  **promovida para F7.2**, e o índice não foi preciso: dedup mais busca vetorizada
  deram 112x sem aproximar nada
