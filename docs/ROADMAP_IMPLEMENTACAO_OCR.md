# Roadmap de implementação — OCR editorial de xadrez

Este roadmap complementa `docs/ROADMAP_OCR.md` e reorganiza o trabalho em torno
do produto final: um documento editorial único que pode ser revisado e exportado
para PDF, DOCX, EPUB e HTML.

## Status de implementação

- **Fase 0: implementada** — manifesto `pyboxeditor.ocr-corpus/v1`, hash de
  arquivos, split por documento, validação, benchmark reproduzível e holdout
  local em `benchmarks/ocr_corpus_v1.json`.
- **Fase 1: implementada** — IR editorial versionado, round-trip JSON, eventos
  imutáveis de revisão e adapters para `PageResult` e `PaginaExtraida`. Desde
  2026-09-22 (item 4 de `REVISAO_MODOS_OCR.md` §4.7) o adapter da
  `PaginaExtraida` é **sem perdas e tem volta**
  (`pagina_editorial_para_extraida`): a origem da figura virou tipo de bloco
  (`caption`, `figure`), `casas_de_largura`, as linhas impressas do parágrafo e
  o negrito como `run` sobrevivem, e o EPUB escrito da página que passou pelo
  IR sai byte a byte igual ao da original.
- **Fase 2: implementada** — `EditorialPipeline` em
  `core/editorial_pipeline.py`, ingestão de PDF/imagem/memória, evidência com
  hash e camada textual, inspeção de layout, roteamento persistido, cache,
  cancelamento cooperativo, adapter legado e exportação operacional JSON/HTML/TXT.
- **Fase 3: implementada** — `core/ocr_phase3.py` com adapters de linha,
  calibração versionada, alinhamento de caractere/token, fusão conservadora,
  decoder linguístico, parser SAN/LAN com variantes/comentários e integração
  automática da camada PDF como hipótese na `EditorialPipeline`.
- **Fase 4: implementada** — `core/ocr_phase4.py` com detecção de tabuleiro,
  orientação sem chute, top-k por casa, filtro de legalidade, FEN auditável,
  setas/destaques/legendas, estado de revisão e métricas próprias. A fachada
  `EditorialPipeline` agora incorpora regiões `diagram` junto do texto. Desde
  2026-09-22 (item 3 de `REVISAO_MODOS_OCR.md` §4.6) o **lado a jogar também
  é sem chute**: sai da legenda associada por geometria
  (`legendas_do_diagrama`) ou da revisão, e o `w` de convenção vai declarado
  em `side_to_move_source`, no aviso e no `alt`/`figcaption` do arquivo
  exportado — que passou a levar a imagem do tabuleiro, desenhada do FEN
  quando não há recorte.
- **Fase 5: implementada** — fila editorial, diário de eventos, retomada, lote,
  undo e interface de revisão em `core/editorial_review.py`.
- **Fase 6: implementada** — HTML, EPUB3, DOCX e PDF pesquisável em
  `core/editorial_export.py`, com modos fiel, limpo e híbrido.
- **Fase 7: implementada** — coleta versionada, active learning, splits sem
  vazamento, calibração por domínio e manifestos verificáveis em
  `core/ocr_phase7.py`.
- **Fase 8: implementada** — contrato de cache semântico, orçamento efetivo de
  recursos, pacotes verificáveis de modelos, smoke test de wheel e benchmark
  protocolado em `core/ocr_phase8.py`.
- O holdout inicial contém 3 livros/4 páginas e referencia artefatos locais
  ignorados pelo Git por tamanho/licenciamento. A expansão para treino e
  validação continua sendo uma tarefa de dados, não uma mudança de contrato.

## Metas de produto

1. Preservar evidência original e tornar cada decisão auditável.
2. Reconhecer prosa, notação, figurinas, NAGs, diagramas e tabelas com roteamento
   específico.
3. Reduzir revisão humana por página sem aceitar correção silenciosa perigosa.
4. Exportar os mesmos dados para todos os formatos.
5. Medir qualidade por livro, domínio, dificuldade e formato.

## Fase 0 — congelar vocabulário, corpus e baseline (P0)

Entregas:

- manter [`CONTEXT.md`](../CONTEXT.md) como glossário canônico;
- criar manifesto versionado por documento, página, idioma, fonte, scan e
  domínios presentes;
- separar treino, validação e teste por documento-fonte;
- guardar referência humana, imagem, camada PDF e saída de ABBYY/Acrobat quando
  licenciável;
- executar baseline atual, Tesseract, camada textual e motores comerciais;
- registrar CER/WER, caixas, ordem de leitura, notação, FEN, diagramas e tempo.

Aceite: qualquer alteração futura produz relatório comparável e nenhum recorte
do teste final entra no treino.

## Fase 1 — documento editorial intermediário (P0)

Entregas:

- `core/editorial_model.py` com blocos tipados e proveniência;
- conversores de `PageResult` e `PaginaExtraida` para o IR;
- schema versionado e serialização JSON;
- decisões e correções como eventos imutáveis;
- validação de invariantes: origem, ordem, IDs e referências.

Aceite: uma página processada pelos dois caminhos atuais produz um único IR
validável; diferenças aparecem como warnings, não como perda silenciosa.

## Fase 2 — pipeline de produção e roteamento (P0)

Entregas:

- `DocumentSource` para PDF nativo, PDF escaneado e imagem;
- `PageEvidence` com camada textual, raster, DPI, hash e metadados;
- análise de layout com regiões spanning, colunas, tabela, painel e diagrama;
- roteador por região/domínio com decisão e motivo persistidos;
- `EditorialPipeline.process()` como única fachada pública;
- adaptação gradual de `core/livro.py`, sem reescrita big-bang.

Aceite: o script `scripts/processar_editorial.py` usa a fachada; nenhuma nova
feature da Fase 2 chama diretamente um engine ou reconstrói texto por conta
própria. O caminho histórico da UI continua disponível durante a migração e
entra no adapter `legacy_extractor` sem uma reescrita big-bang.

## Fase 3 — precisão de prosa, notação e fusão (P0)

Entregas:

- aproveitar camada textual do PDF como hipótese;
- reconhecer linha inteira com modelo treinado e adapters opcionais;
- alinhamento com inserção, remoção, substituição e ligadura;
- fusão por caractere/token com calibração por domínio;
- decoder linguístico conservador, preservando `original_text`;
- parser de notação para SAN/LAN, variantes e comentários.

Aceite: melhoria estatisticamente significativa de CER/WER no teste de prosa e
notação, sem piorar exatidão de símbolos e sem alterar decisões manuais.

## Fase 4 — diagramas como objeto de xadrez (P0)

Entregas:

- detector de tabuleiro e orientação;
- candidatos por casa com top-k e confiança calibrada;
- restrições de legalidade como filtro de candidatos;
- FEN, lado a jogar, roque, en passant e coordenadas;
- setas/destaques/legendas como metadados de diagrama;
- revisão visual de oito por oito casas com comparação de hipóteses.

Aceite: métricas separadas para FEN exato, acerto por casa, orientação e
associação legenda-diagrama; nenhum diagrama é exportado sem estado de revisão.

Implementação: `core/ocr_phase4.py` fornece `BoardDetector`,
`DiagramProcessor`, `Phase4Processor`, `resolve_position` e `diagram_metrics`.
O adapter `LegacySquareRecognizer` reutiliza os modelos de `core/diagrama.py`;
quando pesos ou candidatos faltam, a saída é `unresolved` e entra em revisão,
sem derrubar a página nem inventar peças.

## Fase 5 — fila de revisão e UX editorial (P0/P1)

Entregas:

- fila global de suspeitas por impacto e severidade;
- tela sincronizada original/recorte/hipótese/alternativas/resultado;
- ações aceitar, editar, rejeitar, adiar, revisar em lote e desfazer;
- atalhos de teclado por tipo de revisão;
- revisão específica de notação e diagrama;
- autosave de eventos, retomada e filtro por página/capítulo/domínio.

Aceite: um revisor consegue resolver um lote sem abrir diálogos desconectados e
consegue voltar da saída para a evidência que originou cada trecho.

## Fase 6 — exportação comum (P0)

Entregas:

- HTML semântico e acessível como formato de referência;
- EPUB 3 derivado do HTML/IR, com navegação, fontes e alt text/FEN;
- DOCX com estilos, runs, tabelas, imagens, captions e metadados;
- PDF pesquisável com camada coordenada e relatório de falhas;
- modo “imagem fiel”, “edição limpa” e “híbrido”;
- pré-visualização comparativa e validação estrutural.

Aceite: os quatro alvos recebem a mesma sequência de blocos e as diferenças são
apenas as limitações explícitas do formato.

## Fase 7 — treino, active learning e calibração (P1)

Entregas:

- coleta de correções com versão de dataset;
- amostragem ativa por incerteza e impacto editorial;
- corpus sintético separado de holdout real;
- split por livro/editor/fonte/layout;
- calibração por domínio e relatório de confiabilidade;
- checksum, manifesto e compatibilidade de cada peso.

Aceite: uma rodada de correções melhora o teste de livros não vistos, não apenas
o conjunto que gerou as correções.

## Fase 8 — performance, distribuição e benchmark comercial (P1/P2)

Entregas:

- cache invalidado por versão de código, schema, modelo e configuração;
- limites efetivos de memória e workers por engine;
- pacotes de modelo instaláveis e verificados;
- wheel/installer com smoke test em máquina limpa;
- comparação protocolada com ABBYY/Acrobat;
- relatório de qualidade, latência, memória e custo de revisão.

Aceite: instalação limpa reproduz a mesma saída do ambiente de desenvolvimento e
o benchmark pode ser executado por outra pessoa a partir do manifesto.

## Ordem das entregas verticais

Cada etapa deve atravessar uma fatia completa:

`uma página difícil → IR → revisão → HTML → DOCX/EPUB/PDF → benchmark`.

Depois repetir para duas colunas, notação, diagrama, tabela e livro completo.
Isso evita construir cinco exportadores sobre um contrato ainda instável.

## Definition of Done global

- testes unitários, de integração e de aceitação do fluxo passam;
- benchmark do corpus fechado é executado e arquivado;
- nenhum domínio excede o limite de regressão aprovado;
- correções manuais são reversíveis e rastreáveis;
- saída é validada estrutural e visualmente;
- modelo, schema, configuração e versão entram no relatório;
- documentação e instruções de operação são atualizadas;
- a instalação limpa possui pesos ou declara claramente o fallback.
