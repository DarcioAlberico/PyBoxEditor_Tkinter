# Roadmap de implementação — OCR editorial de xadrez

Este roadmap complementa `docs/ROADMAP_OCR.md` e reorganiza o trabalho em torno
do produto final: um documento editorial único que pode ser revisado e exportado
para PDF, DOCX, EPUB e HTML.

**Reescrito em 2026-09-23** (item 8 de `docs/REVISAO_MODOS_OCR.md` §5). A versão
anterior dava as Fases 0–8 por "implementadas", e eram — mas não dizia que metade
delas não estava no caminho que o usuário usa: a fachada editorial, sozinha, não
lia página digitalizada, e o menu que a expunha devolvia um bloco vazio sem aviso
(§3.1 da revisão). Aqui cada peça está num de três lugares:

- **em produção** — o que a janela e os scripts de produção executam, e cuja
  qualidade é a que o usuário recebe;
- **instrumento** — o que mede a produção, e roda por script;
- **biblioteca** — código testado que a produção não chama. Serve para inspeção e
  para comparar motores, e não promete qualidade: nas quatro páginas de
  referência ele perde para o caminho de produção, e numa página digitalizada sem
  motores não lê nada.

## O caminho de produção

O gate estrutural de release do IR está em `core/editorial_quality_gate.py` e
`scripts/validar_documento_editorial.py`: valida a ordem do livro, a
proveniência, FENs, tabelas e sequências jogáveis antes da exportação. Ele é
explícito e não corrige OCR; `--exigir-resolvido` transforma blocos pendentes em
bloqueio de release.

O contrato de benchmark em `core/ocr_benchmark.py` também mede diagramas por
posição/lado a jogar, legalidade das sequências de notação e ordem completa das
regiões. `scripts/benchmark_ocr.py` expõe limites semânticos opcionais; CER
textual sozinho não libera uma rodada. `scripts/rodada_do_corpus.py` aplica os
mesmos limites quando a referência da página é JSON estruturado, mantendo o
corredor de produção e o benchmark de manifesto sob o mesmo contrato.

| etapa | onde | quem chama | medido |
|---|---|---|---|
| ler a página digitalizada | `core/livro.py`: a cadeia própria de glifos (`LearningService.leitor_de_texto`) ancora o lance, o Tesseract de página lê a prosa, `_fundir_por_palavra` junta palavra a palavra com o roteamento de `core/ocr_routing.py`; tabela, trama, negativo, colunas e o corretor de prosa | Exportar → Livro e → Documento editorial; `scripts/processar_editorial.py` | CER 1,59% ponderado nas quatro páginas do holdout v2, a 300 dpi (rodada `benchmarks/rodadas/corpus_v2_dpi300/2026-09-26-0047.json`) |
| ler o PDF nascido digital | `core/pdf_nativo.py` (F110), escolhido por página por `livro.extrair(camada="auto")` | a caixa de exportação (ligada por padrão); `processar_editorial.py` | Dvoretsky 2025: 815 de 816 páginas, 1.273 diagramas exatos |
| diagramas | `core/diagrama.py` (duas CNNs por casa, `_arbitrar`, porteiro, orientação pelas coordenadas, redesenho), `core/deteccao_de_tabuleiro.py`, o lado a jogar da legenda por `core/lado_a_jogar.py` | dentro do `livro.py`; Reconhecer → Ler posição dos diagramas | tabuleiro inteiro 92,5% no corpus da F8.4 |
| a fachada | `core/editorial_pipeline.EditorialPipeline` **montada por** `core/editorial_legacy.pipeline_de_producao`, com o `ExtratorDeLivro` como `legacy_extractor`; o cancelar é o `CancellationToken` de `core/ocr_runtime.py` | a janela, `processar_editorial.py`, `fila_de_suspeitas.py` | a p. 30 do Aagaard sai com os mesmos 1,37% do A/B |
| o documento editorial | `core/editorial_model.py` (IR versionado, eventos de revisão imutáveis) e `core/editorial_adapters.py` (`PaginaExtraida` ↔ IR sem perdas, com volta) | todos acima | round-trip bloco a bloco igual, EPUB byte a byte idêntico (§4.7) |
| a revisão | `core/editorial_review.py`, `core/editorial_suspeitas.py`, `ui/dialogo_revisao_editorial.py`; o FEN revisado volta ao livro por `editorial_legacy.aplicar_revisao` | Revisar → fila de suspeitas | 23 linhas apontadas nas quatro páginas, 23 erros, 0 falsos positivos (§4.5) |
| escrever | EPUB e DOCX por `core/exportar.py` (o escritor que embute a fonte dos símbolos e redesenha os diagramas); HTML, TXT e PDF pesquisável do documento por `core/editorial_export.py` (o texto de cada bloco por `texto_do_bloco`); JSON pela fachada; "PDF pesquisável" do menu por `core/searchable_pdf.py` | a janela; `processar_editorial.py` faz o mesmo desvio | a mesma sequência de blocos nos quatro formatos (`tests/test_aceitacao_formatos.py`) |
| o editor de livro | `core/editor/importar_ir.py`: o documento editorial vira livro no editor, com a origem de cada bloco (ED-11) | Abrir no editor | Dvoretsky inteiro: 28 capítulos, 816 marcas de página, abre em 0,9 s |
| coleta e treino | `core/ocr_phase7.CorrectionDataset` (as correções da revisão, versionadas); `core/ocr_training.treinar_pacote` com o léxico de `core/ocr_language.py`; o modelo de linha só lê se passa no portão `linha_trainer.modelo_utilizavel` (CER ≤ 15%), com hash do peso e fingerprint da base | Revisar → Preparar dataset de correções; Modelo → Treinar OCR de linhas | o artefato local atual é rejeitado porque o `.pth` é mais novo que o JSON de validação; a avaliação direta do corpus deu CER 4,19%, mas ainda não constitui um holdout/proveniência de release |

## Os instrumentos

O leitor de produção aceita `--usar-ensemble` no script operacional como modo
opt-in. A faixa só é substituída quando engines distintas concordam; conflitos
ficam na evidência da linha e não escolhem silenciosamente a maior confiança.

Todos leem pelo caminho de produção; nenhum passa pela biblioteca.

- `scripts/ab_ocr_livro.py` e `core/ocr_ab.py` — os modos de leitura sobre as
  mesmas páginas, CER e WER de prosa e de notação contra a referência humana.
- `scripts/rodada_do_corpus.py`, `core/familias_de_pagina.py` e o manifesto
  `benchmarks/corpus_v2.json` — a rodada do corpus inteiro, ponderada, que
  sai diferente de zero quando uma página piora (§4.9). `--comparar-com`
  permite fixar o baseline fora da pasta da rodada, confere o hash do corpus
  e persiste a comparação no gate do relatório.
- `scripts/fila_de_suspeitas.py` — a fila de revisão conferida contra a
  referência (§4.5).
- `scripts/erros_confiantes.py` e `core/ocr14.py` — o resíduo confiante da
  cadeia, com a caixa do glifo (§4.8).
- `scripts/medir_camada.py` — a régua da F110 e o OCR contra a camada.
- `core/ocr_benchmark.py`, `core/ocr_corpus.py` e os `scripts/benchmark_*`,
  `congelar_corpus.py`, `validar_corpus.py` — o manifesto e as métricas da Fase 0.
- `core/ocr_phase8.py` (`ModelPackage`), `scripts/empacotar_modelo.py` e
  `scripts/smoke_release.py` — os pacotes de modelo verificáveis e o smoke do
  wheel.

## A biblioteca

Nota de integracao: `core.ocr_training.treinar_pacote` agora aceita
`--calibracao`/`calibracao`, avalia um conjunto independente e persiste o
relatorio de confiabilidade por dominio. `--split-manifest` consume o manifesto
validado de `split_corpus` e o prende ao metadata do modelo; ele nao e aplicado
silenciosamente a um `rec_gt.txt` sem metadados de corpus.
As linhas antigas da tabela que dizem que nenhuma calibração e chamada devem
ser lidas como estado anterior a esta integracao.

| módulo | o que é | quem chama | por que não é produção |
|---|---|---|---|
| `core/ocr_phase3.py` | `Phase3Processor`, `FusionEngine`, `NotationParser`, `align_text`, os adapters de linha | a fachada sem leitor; `processar_editorial.py --biblioteca [--usar-engines]` | a fusão é por linha inteira, e 23 das 25 linhas da p. 30 do Aagaard são mistas; em notação ela prefere a camada do PDF, que nos livros do corpus é OCR de fábrica |
| `core/ocr_phase4.py` | `DiagramProcessor`, `resolve_position`, `Phase4Processor` | a fachada sem leitor | é um segundo resolvedor de posição, sem o porteiro, a orientação pelas coordenadas e o redesenho de `core/diagrama.py` |
| `core/ocr_layout.py` | `LayoutAnalyzer` | `EditorialPipeline.inspect` numa página sem camada de texto | `detectar_colunas` une os intervalos das linhas: uma linha que cruza a calha apaga a coluna da página inteira |
| `core/ocr_engines.py` | o registro de adapters (Tesseract, EasyOCR, PaddleOCR, CRNN) | `Phase3Processor.from_ocr_service` | é o que `--usar-engines` monta |
| `core/ocr_runtime.BatchProcessor` e o cache de páginas, com `ocr_phase8.resolve_resource_budget` | o laço por página da fachada | a fachada sem leitor | o leitor de produção lê por `livro.extrair`, que não passa por ele; o item 7 (§4.10) mediu e consertou este laço |
| `core/editorial_export.py`, EPUB e DOCX | os dois formatos escritos do IR | `EditorialPipeline.export` na biblioteca | a produção escreve esses dois pelo `exportar.py`, o único que embute a fonte dos símbolos |
| `core/ocr_phase7.py`: `calibrate_domains`, `split_corpus`, `evaluate_holdout` | calibração por domínio, splits, holdout | `core/ocr_training.py` e `scripts/treinar_ocr_linhas.py`; a janela coleta holdout e calibração | splits e vínculos físicos continuam explícitos para promoção/release (§3.3) |
| `core/ocr_structure.py` | a estrutura de documento a partir do layout | só o teste | — |
| `core/abbyy_ocr.py` | a integração opcional com o FineReader instalado | só o teste | ninguém a chama |

A biblioteca continua testada — `tests/test_ocr_phase3.py`, `test_ocr_phase4.py`,
`test_ocr_layout.py`, `test_ocr_structure.py`, `test_ocr_engines.py`,
`test_ocr_phase7.py`, `test_abbyy_ocr.py` — e a fachada sem leitor tem o seu
comportamento preso por `test_fachada_de_producao.py`: numa página digitalizada
ela devolve o bloco vazio, e o teste diz por quê.

## O que foi apagado em 2026-09-23

O baseline protocolado mais recente esta em `benchmarks/rodadas/corpus_v2_dpi300/2026-09-26-0119.json`, com gate de CER aprovado. A fila de expansao preliminar esta em `benchmarks/candidatos_v2/` e nao altera o holdout ate a revisao humana.

Código que só os testes alcançavam, e que repetia o que a produção faz de outro
jeito:

| apagado | o que era | o que a produção tem no lugar |
|---|---|---|
| `core/ocr_hybrid.py` | a OCR-12 como pipeline por linha: prosa da faixa, notação da âncora | `livro._fundir_por_palavra` — a linha destes livros é mista, e a decisão é por palavra |
| `core/ocr_context.py` | a OCR-13, o decodificador contextual por palavra (e o passo que o `Phase3Processor` montava com um modelo de língua) | o corretor de prosa do `livro.py`, que pula o token de notação |
| `core/ocr_fusion.py` | a fusão por consenso e o *beam search* por palavra | a fusão por palavra com as caixas do Tesseract |
| `core/ocr_review.py` | uma fila de palavras com `ReviewStore` e desfazer | `core/editorial_review.py`, com diário, lote e a pilha de desfazer |
| `core/ocr_export.py` | o terceiro exportador (JSON, DOCX, PDF pesquisável) | `exportar.py`, `editorial_export.py` e `searchable_pdf.py` |
| `editorial_pipeline._page_from_text` e `_words_for_line` | uma página montada da camada de texto | ninguém chamava |
| `editorial_pipeline._html_document` | um escritor de HTML do IR | o ramo `html` do `export` nunca o alcançava — o HTML já saía pelo `EditorialExporter`, uma linha acima; os itens 3 e 4 o tinham editado sem efeito |

Saíram também os 19 testes que só exercitavam esse código (os de `ocr_ab`,
`ocr_engines` e `ocr_language` que estavam nos mesmos arquivos ficaram, em
`tests/test_ocr_ab.py`, `test_ocr_engines.py` e `test_ocr_language.py`). Para
consultar o que foi apagado: `git show 71880b2:core/ocr_hybrid.py`, e assim por
diante — o `71880b2` é o último `master` que tinha os cinco.

## O que cada fase entregou, e onde está

- **Fase 0** — manifesto `pyboxeditor.ocr-corpus/v1`, hash, split por documento,
  benchmark e holdout: **instrumento**. O corpus de referência cresce pelo item 6
  da revisão, e o que falta é transcrever páginas: cinco das oito famílias de
  layout têm menos de três.
- **Fase 1** — IR versionado, round-trip JSON, eventos imutáveis, adapters:
  **produção**. O adapter da `PaginaExtraida` é sem perdas e tem volta desde
  2026-09-22 (§4.7).
- **Fase 2** — a fachada: **produção com o leitor medido dentro**; o laço próprio
  (evidência por página, cache, lotes) é biblioteca.
- **Fase 3** — fusão por linha, calibração, decoder linguístico, parser de
  notação: **biblioteca**. A produção tem a fusão por palavra e o corretor de
  prosa do `livro.py`; o modelo de linha, atrás do portão.
- **Fase 4** — diagramas como objeto de xadrez: o `DiagramProcessor` é
  **biblioteca**; o diagrama de produção é o do `core/diagrama.py`. O lado a jogar
  sem chute (`core/lado_a_jogar.py`, §4.6) vale nos dois.
- **Fase 5** — fila editorial, diário, retomada, lote, desfazer: **produção**.
- **Fase 6** — exportação comum: HTML e PDF pesquisável do IR, em **produção**;
  EPUB e DOCX pelo `exportar.py`, e os do IR ficam na biblioteca. O aceite — os
  quatro alvos com a mesma sequência de blocos — tem teste desde 2026-09-23
  (`tests/test_aceitacao_formatos.py`, item 10 da revisão), e ele achou a camada
  de texto do PDF pesquisável com a figurina trocada por `·`, a tabela em JSON e a
  figura em base64; corrigidos no mesmo dia.
- **Fase 7** — a coleta versionada (`CorrectionDataset`) e o treino com
  holdout/calibração estão em **produção**; split, vínculo físico e proveniência
  continuam portões explícitos de promoção e release (§3.3).
- **Fase 8** — pacotes de modelo e smoke do wheel são **instrumento** de
  distribuição; o orçamento de recursos serve o laço da biblioteca.

O que falta está na §5 da revisão, e é dado: conferir a quarentena dos erros
confiantes (item 5) e transcrever páginas das famílias de layout que o corpus
ainda não mede (item 6). A interface (item 9) e os testes de aceitação (item
10) saíram em 2026-09-23 (§4.12 e §4.13).

## IntegraÃ§Ã£o do ensemble no caminho principal

O consenso de engines da Fase 3 agora pode ser ativado na caixa principal de
exportaÃ§Ã£o. Livro e Documento Editorial recebem a mesma `OpcoesDeLeitura` e
consultam Tesseract, EasyOCR e PaddleOCR nas faixas de fallback; duas fontes
concordantes sÃ£o o mÃ­nimo para substituir a cadeia prÃ³pria. Conflitos e
indisponibilidade ficam na evidÃªncia e na fila de revisÃ£o. O padrÃ£o continua
desligado para preservar o caminho medido atÃ© uma rodada do corpus comprovar
ganho de precisÃ£o.

## Metas de produto

Para a promoção de pesos da Fase 7, o comando operacional exige `--holdout`
real e independente. Sem essa evidência, o CRNN pode ser inspecionado, mas não
entra no caminho de produção, mesmo que a validação interna tenha CER baixo.

1. Preservar evidência original e tornar cada decisão auditável.
2. Reconhecer prosa, notação, figurinas, NAGs, diagramas e tabelas com roteamento
   específico.
3. Reduzir revisão humana por página sem aceitar correção silenciosa perigosa.
4. Exportar os mesmos dados para todos os formatos.
5. Medir qualidade por livro, domínio, dificuldade e formato.

## Ordem das entregas verticais

Cada etapa deve atravessar uma fatia completa:

`uma página difícil → IR → revisão → HTML → DOCX/EPUB/PDF → benchmark`.

Depois repetir para duas colunas, notação, diagrama, tabela e livro completo.
Isso evita construir cinco exportadores sobre um contrato ainda instável.

Uma peça nova entra em produção quando mede melhor que a de hoje **nas mesmas
páginas** (`scripts/rodada_do_corpus.py`); até lá, é biblioteca, e este documento
diz isso.

## Definition of Done global

- testes unitários, de integração e de aceitação do fluxo passam;
- benchmark do corpus fechado é executado e arquivado;
- nenhum domínio excede o limite de regressão aprovado;
- correções manuais são reversíveis e rastreáveis;
- saída é validada estrutural e visualmente;
- modelo, schema, configuração e versão entram no relatório;
- documentação e instruções de operação são atualizadas;
- a instalação limpa possui pesos ou declara claramente o fallback.
