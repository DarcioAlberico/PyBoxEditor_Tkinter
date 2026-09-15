# Arquitetura — fase 2

## Fronteiras introduzidas

- `DocumentController`: sessão aberta, página atual, boxes, seleção, histórico,
  undo/redo e disparo de autosave.
- `NavigationController`: quantidade de páginas, página atual e validação de
  limites. Não depende de Tkinter nem de `PDFService`.
- `TaskController`: ciclo de vida de uma tarefa em segundo plano. A janela
  depende desta fachada, enquanto a fila/thread continua encapsulada em
  `BackgroundTask`.

`MainWindow` conserva aliases compatíveis (`session`, `history`, `boxes`,
`selected_index` e `current_pdf_page`), mas agora eles são propriedades que
delegam aos controladores. Não há uma segunda cópia do estado na janela.

## Contratos

1. Toda alteração editável chama `_commit_change`, que delega o snapshot e a
   marcação de dirty ao `DocumentController`.
2. Undo/redo restauram uma lista nova e sincronizam a página da sessão.
3. Troca de página nunca aceita índices fora do documento.
4. Trabalho pesado continua proibido de tocar em widgets; callbacks de UI são
   entregues somente pelo ciclo de vida de `TaskController`.
5. Os controladores não importam módulos opcionais de OCR, Torch ou EasyOCR.

## Critério de conclusão desta fase

Os três controladores possuem testes unitários sem display, os handlers usam
uma única fonte de verdade, os testes de autosave/páginas/histórico/threads e
navegação continuam passando e a análise Ruff não encontra violações nos
arquivos alterados.
