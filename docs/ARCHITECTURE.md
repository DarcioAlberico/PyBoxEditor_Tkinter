# Arquitetura

Como o PyBoxEditor está montado em 2026-10-06, depois das fases F0–F125 do `ROADMAP.md`,
ED-00–ED-18 do editor e PD-00–PD-20 das pendências. O que cada peça mediu está nos
roadmaps; aqui ficam as camadas, as fronteiras e o caminho que um livro percorre. A seção
"Controladores da janela" é a nota original deste arquivo (fase 2 da F4) e continua valendo.

## Três produtos, uma base

```
appy.py ──┬── ui/main_window.py ──── core/services/* ──── core/livro.py, pdf_nativo.py, diagrama.py
          │        │                                        │
          │        ├── Exportar → Livro ─────────────────── core/exportar.py (EPUB, DOCX)
          │        ├── Exportar → Documento editorial ───── core/editorial_legacy → editorial_pipeline
          │        │        ├── Revisar (fila de suspeitas) ─ core/editorial_review.py, editorial_suspeitas.py
          │        │        └── HTML, TXT, PDF pesquisável ── core/editorial_export.py, searchable_pdf.py
          │        └── Abrir no editor ─────────────────── core/editor/importar_ir.py
          │
          └── --editor ── ui/editor/janela.py ──── core/editor/* (modelo, XHTML, EPUB, DOCX, HTML, PDF, PGN)
```

1. **A janela principal** (`ui/main_window.py`) edita boxes e lê a página digitalizada.
   Ela fala só com as fachadas de `core/services/`: `BoxService` (segmentação e geometria
   dos boxes), `OCRService` (a rede de glifos, o Tesseract, o EasyOCR, o leitor de linha),
   `LearningService` (modelos e bases de treino), `PDFService` (páginas por PyMuPDF),
   `DocumentService` e `HistoryService` (o documento aberto e o desfazer), `TaskService`
   (trabalho fora da thread do Tk).
2. **O documento editorial** é a representação do livro reconstruído, independente do
   formato de saída: `core/editorial_model.py` (IR versionado, eventos de revisão imutáveis),
   `editorial_adapters.py` (a ida `PaginaExtraida → IR` e a volta, sem perdas),
   `editorial_review.py` e `editorial_suspeitas.py` (a fila com evidência e o diário),
   `editorial_export.py` (HTML, TXT e PDF pesquisável do IR) e `editorial_quality_gate.py`
   (o gate estrutural de release). A fachada `editorial_pipeline.EditorialPipeline` é
   montada por `editorial_legacy.pipeline_de_producao` com o leitor de `livro.py`.
3. **O editor de livros**: `core/editor/` é o núcleo sem Tk — `modelo.py`, o dialeto
   XHTML+CSS (`dialeto.py`, `xhtml.py`), os formatos (`epub.py`, `docx_io.py`,
   `docx_leitura.py`, `html_io.py`, `txt_io.py`, `pdf_io.py`, `pgn_io.py`), ortografia,
   tipografia, sumário, índices, relatórios e validação —, e `ui/editor/` é a janela:
   `JanelaDoEditor`, o `TextoRico` do modo texto, o `EditorDeCodigo`, menus declarativos,
   painéis e diálogos atrás de um ponto de injeção (`dialogos.py`).

`config/paths.py` resolve todo caminho de dado (pasta do usuário, modelos, bases de linhas,
raízes de um wheel instalado) e `config/settings.py` guarda as preferências; nenhum módulo
usa nome solto resolvido no cwd. `scripts/` são os instrumentos e `scripts/medidas/`, as
medições de uma fase cada, rodadas da raiz do projeto.

## O caminho de produção do OCR

A tabela completa, com quem chama cada etapa e o número medido, está em
`docs/ROADMAP_IMPLEMENTACAO_OCR.md` ("O caminho de produção"); em resumo:

| Etapa | Onde |
|---|---|
| Ler a página digitalizada | `core/livro.py`: a cadeia própria de glifos (`LearningService.leitor_de_texto`) ancora o lance, o Tesseract de página lê a prosa, `_fundir_por_palavra` junta palavra a palavra com o roteamento de `core/ocr_routing.py`; tabela, trama, negativo, colunas, o corretor de prosa e o reparo pela camada do ClearScan |
| Ler o PDF nascido digital | `core/pdf_nativo.py` (F110), escolhido por página por `livro.extrair(camada="auto")` |
| Diagramas | `core/diagrama.py` (duas CNNs por casa, arbitragem, porteiro, orientação pelas coordenadas, redesenho), `deteccao_de_tabuleiro.py`, o lado a jogar por `lado_a_jogar.py` |
| A caixa de cada letra | `core/geometria_da_linha.py` (F112), ligada nas exportações e na poda da janela (F123) |
| A fachada e o IR | `editorial_legacy.pipeline_de_producao` → `EditorialPipeline` → `editorial_adapters` |
| A revisão | `editorial_review`, `editorial_suspeitas`, `ui/dialogo_revisao_editorial.py`; o FEN revisado volta ao livro por `editorial_legacy.aplicar_revisao` |
| Escrever | EPUB e DOCX por `core/exportar.py` (embute a fonte dos símbolos, redesenha os diagramas); HTML, TXT e PDF pesquisável por `editorial_export.py`; o PDF pesquisável do menu por `searchable_pdf.py` |
| O editor | `core/editor/importar_ir.py` leva o documento editorial ao modelo do editor, com a origem de cada bloco |
| Treino | `ocr_phase7.CorrectionDataset`, `ocr_training.treinar_pacote`, o portão `linha_trainer.modelo_utilizavel` |

**Biblioteca de inspeção, não produção:** o pacote `core/biblioteca/` — `ocr_phase3.py`,
`ocr_phase4.py`, `ocr_layout.py` e `abbyy_ocr.py` (a integração com o FineReader, mantida
por ser integração com um programa instalado). A fachada sem leitor atravessa essa
biblioteca e, numa página digitalizada, não lê texto — é o caminho do `inspect`, dos testes
das fases e da comparação de motores por script (`processar_editorial.py --biblioteca`).
`ocr_structure.py`, que só o teste alcançava, foi apagado em 2026-10-06. O `ocr_engines`
(adapters e o ensemble por consenso) fica em `core/` porque o ensemble entra em produção
como opt-in.

## Como uma exportação atravessa o sistema

"Exportar → Documento editorial" num PDF digitalizado:

1. A janela monta a fachada com `pipeline_de_producao` e roda numa tarefa do
   `TaskService`, com cancelamento (`ocr_runtime.CancellationToken`).
2. Para cada página, `livro.extrair` decide pela régua se a camada de texto do PDF é
   tipográfica (`pdf_nativo`) ou OCR de fábrica; se não é, segmenta a imagem, lê os glifos,
   chama o Tesseract na prosa e funde por palavra; acha e lê os diagramas.
3. `editorial_adapters.pagina_extraida_para_pagina` transforma cada `PaginaExtraida` em
   blocos do IR, com evidência por linha, confiança, negrito e itálico como runs, e a
   origem de cada bloco.
4. O documento é validado (`EditorialDocument.validate`) e gravado em JSON; a fila de
   suspeitas nasce dele, e cada decisão humana vira um evento no diário.
5. Os escritores leem o IR (e, para EPUB e DOCX, as páginas do leitor com as revisões
   aplicadas) e escrevem a mesma sequência de blocos em cada formato
   (`tests/test_aceitacao_formatos.py` confere o Invariante 10).
6. "Abrir no editor" chama `importar_ir` e o livro aparece na `JanelaDoEditor`, capítulo a
   capítulo, com as marcas de página.

## Controladores da janela (fase 2 da F4)

- `DocumentController`: sessão aberta, página atual, boxes, seleção, histórico, undo/redo
  e disparo de autosave.
- `NavigationController`: quantidade de páginas, página atual e validação de limites. Não
  depende de Tkinter nem de `PDFService`.
- `TaskController`: ciclo de vida de uma tarefa em segundo plano. A janela depende desta
  fachada, enquanto a fila/thread continua encapsulada em `BackgroundTask`.

`MainWindow` conserva aliases compatíveis (`session`, `history`, `boxes`, `selected_index`
e `current_pdf_page`), mas eles são propriedades que delegam aos controladores: não há uma
segunda cópia do estado na janela. Contratos: toda alteração editável chama
`_commit_change`; undo/redo restauram uma lista nova e sincronizam a página; troca de
página nunca aceita índice fora do documento; trabalho pesado não toca em widgets, e os
callbacks de UI chegam só pelo ciclo de vida de `TaskController`; os controladores não
importam módulos opcionais de OCR, Torch ou EasyOCR.

## Fronteiras e regras que os testes guardam

- As dezesseis invariantes de `CONTEXT.md`: a imagem e o texto originais nunca são
  destruídos; a correção manual tem precedência; notação e diagrama são domínios de xadrez;
  toda saída aponta de volta para a página e a região; confiança prioriza e não autoriza;
  a mesma decisão alimenta todos os formatos; o diário não apaga decisões; dado sintético
  não contamina o holdout real; peso sem checksum não vai a produção.
- Cores só em `ui/tema.py` (`tests/test_tema.py`); caminhos só por `config.paths`
  (`tests/test_caminhos_do_treino_de_linhas.py`); a suíte não grava na pasta do usuário
  (`tests/conftest.py`); todo texto é UTF-8 sem BOM (`tests/test_codificacao.py`); a
  exportação é reprodutível com `SOURCE_DATE_EPOCH` (`tests/test_exportacao_reprodutivel.py`).
- O que fica fora do git e por quê está no `.gitignore`: bases de treino soltas, pesos
  grandes, PDFs de livros, bases sintéticas.

## Dívidas conhecidas

Medidas em `docs/ANALISE_GERAL_2026-10-06.md`: `MainWindow` com 170 métodos e 53
importações do projeto, `TextoRico` com 202 e `JanelaDoEditor` com 175; dezessete ciclos
diretos de importação (`livro` ↔ `pdf_nativo`, `editorial_legacy` ↔ `editorial_pipeline`,
`ui/editor/dialogos` ↔ seis vizinhos). A ordem do que fazer está no mesmo documento. O
`core` sem logging foi resolvido no item 5: `core/log.py` é o tronco `pyboxeditor`, o
arquivo `pyboxeditor.log` fica na pasta de dados, e os módulos do editor entram sob
`pyboxeditor.editor`, que o painel Mensagens ecoa.

**Os escritores de EPUB e DOCX.** São dois por decisão medida (ED-12, "convive", re-medida
em 2026-10-06): `core/exportar.py` é a primeira saída do OCR — sai direto das
`PaginaExtraida`, sem editor, e é o que a fila de revisão regrava — e `core/editor/` é o
escritor do editor de livros, que faz o que o histórico não faz (PDF, PGN, proveniência,
fontes pelo mapa). O terceiro, `editorial_export._epub`/`_docx`, escreve o IR só na
biblioteca e é o único que carrega o sinal "não revisado" do diagrama (§4.6); dobrá-lo
sobre o `exportar.py` pede que esse sinal chegue lá antes (PD-21 em
`docs/ROADMAP_PENDENCIAS.md`).
