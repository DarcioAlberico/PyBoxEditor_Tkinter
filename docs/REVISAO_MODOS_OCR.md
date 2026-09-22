# Revisão dos modos de OCR e da sua integração — 2026-09-18

Escopo: todos os caminhos de reconhecimento do PyBoxEditor (glifo, linha,
híbrido, fusão por palavra, editorial, diagramas, PDF pesquisável), como eles
se integram na interface e nas exportações, e o que os separa de um produto
de qualidade profissional. Complementa a [revisão geral de 2026-09-17](REVISAO_GERAL_OCR_XADREZ.md)
e o [ROADMAP_OCR](ROADMAP_OCR.md); os números abaixo são desta data.

Método: oito revisões independentes sobre o mesmo código (mapa dos modos,
arquitetura de integração, falhas silenciosas, diagramas, interface, testes,
treino/ML, defeitos Python), consolidadas por consenso; cada achado foi
verificado no código (arquivo:linha) e, onde havia instrumento, medido —
`scripts/ab_ocr_livro.py` nas quatro páginas de referência e a suíte de
testes. Depois, duas rodadas de correção com revisão adversarial das
próprias mudanças.

## 1. Resultado executivo

O produto tem **um** caminho de leitura de qualidade medida — `core/livro.py`:
cadeia própria de glifos ancorando o lance, Tesseract lendo a prosa, fusão
palavra a palavra — e **uma biblioteca paralela** (`core/editorial_*`,
`core/ocr_phase3/4/7/8.py`, `ocr_layout`, `ocr_hybrid`, `ocr_fusion`,
`ocr_context`, `ocr_review`, `ocr_export`) que o roadmap dava por
"implementada" e que, no ponto em que a interface a expunha, **não lia
página digitalizada**: o menu "Processar Documento Editorial" devolvia um
bloco vazio, sem aviso, na mesma página em que "Exportar Livro" sai a 2,4%
de erro por caractere. O risco central não era falta de motor: era o motor
medido ficar fora do documento editorial, da fila de revisão e do PDF
pesquisável, e o motor não medido estar a um clique de distância.

Nesta data, com as correções desta revisão:

| página (modo `palavra`) | CER total antes | CER total depois |
|---|---:|---:|
| Aagaard, *Calculation*, p. 30 | 2,40% | **1,37%** |
| Nunn, *Secrets of Rook Endings*, p. 237 (tabela) | 8,19% | **1,87%** |
| Yusupov, *Chess Evolution 1*, p. 34 (duas colunas) | 0,71% | 0,71% |
| Yusupov, *Chess Evolution 1*, p. 47 (painel sobre trama) | 2,50% | 2,50% |

E o menu editorial passou a usar o mesmo leitor: a p. 30 pela fachada sai
com os mesmos 1,37%, com caixa por parágrafo e PDF pesquisável invisível na
escala certa.

**Veredito sobre "qualidade AAA"**: o reconhecimento de lance, figurina,
diagrama e tabela está acima do que ABBYY/Acrobat entregam nestes livros, e a
prosa fundida está abaixo de 1% de erro em três das quatro páginas. O que
falta para o rótulo é o que a seção 5 lista. Os três primeiros itens saíram —
a exportação por um diálogo só (4.4), a fila de revisão com o recorte e as
alternativas (4.5) e o diagrama sem convenção silenciosa (4.6) —; ficam o
adapter sem perdas, a OCR-14, o corpus de referência maior que quatro
páginas, o cache do caminho novo, a poda da biblioteca paralela, a interface
e os testes de aceitação.

## 2. O mapa dos modos

| Modo (como o usuário vê) | Reconhecedor | Segmentação | Fusão | Saída | Estado |
|---|---|---|---|---|---|
| Reconhecer → Detectar e reconhecer (Neural) | CNN própria → k-NN → EasyOCR (`OCRService.fallback_chain_detalhado`) | `BoxService` (contornos, trama, negativo) + `leitura_de_linha` | veto geométrico + máscara de alfabeto | boxes na tela | produção, medido (97,4% nas páginas rotuladas) |
| Reconhecer → Híbrido (k-NN + EasyOCR) | k-NN → EasyOCR, sem CNN | idem | idem | boxes | produção |
| Reconhecer → EasyOCR por linha / por caractere | EasyOCR | idem | `leitura_de_linha.distribuir` | boxes | produção |
| Reconhecer → Preencher: Tesseract / EasyOCR / PaddleOCR / EasyOCR-linha / CRNN | um motor sobre os boxes existentes | boxes da tela | nenhuma | boxes | produção; o CRNN atrás de portão (ver 4.3) |
| Arquivo → Exportar → Livro (EPUB/DOCX) | CNN/k-NN por glifo + Tesseract página/faixa | `livro.caixas_e_diagramas`, `_tabela_da_pagina` | `livro._fundir_por_palavra` (lance da âncora, prosa do motor) + corretor de prosa | `PaginaExtraida` → `exportar.py` | **o caminho medido** |
| Arquivo → Exportar → Documento editorial | os mesmos, por `core/editorial_legacy` | idem | idem | `EditorialDocument` → JSON/HTML/TXT/PDF; EPUB/DOCX por `exportar.py` | ligado nesta revisão (antes: vazio) |
| Arquivo → Exportar → PDF pesquisável | `fallback_chain` por box + EasyOCR por linha | `BoxService` | nenhuma | PDF com camada invisível (`searchable_pdf`) | produção, sem a fusão por palavra |
| Reconhecer → Ler posição dos diagramas | duas CNNs por casa (ocupação, peça) + `_arbitrar` | `diagrama.localizar` / `deteccao_de_tabuleiro` | legalidade só troca a casa mais barata | FEN no diálogo 8×8 | produção (tabuleiro inteiro 92,5% no corpus F8.4) |
| `scripts/processar_editorial.py --usar-engines` | Tesseract + EasyOCR + PaddleOCR (+ CRNN) por `Phase3Processor` | `ocr_layout.LayoutAnalyzer` | `FusionEngine` por linha inteira | `EditorialDocument` | só por script; perde para `livro.py` (ver 3.1) |
| `ocr_hybrid.HybridOCRPipeline`, `ocr_fusion`, `ocr_context`, `ocr_review`, `ocr_export`, `abbyy_ocr` | — | — | — | — | **só em testes** (código morto) |

## 3. Achados de consenso

### 3.1 Integração (P0)

- **Dois produtos que não se falam.** `livro.py → exportar.py` (medido) e
  `EditorialPipeline → editorial_export.py` (IR, fila, HTML) eram caminhos
  disjuntos; o `legacy_extractor` da fachada só existia como dublê de teste
  (`tests/test_editorial_pipeline.py`). *Corrigido nesta revisão para a
  interface: `core/editorial_legacy.py`.*
- **A fachada sozinha não lê scan.** `EditorialPipeline._process_page` monta
  `Phase4Processor(Phase3Processor())` sem reconhecedor de linha; sem camada
  de texto, `Phase3Processor._specs` trata a página como uma linha vazia
  (`core/ocr_phase3.py:582-593`). Fixado por teste (`test_fachada_de_producao`).
- **Onde o pipeline novo perderia para `livro.py`** mesmo com motores: fusão
  por linha inteira onde 23 das 25 linhas da p. 30 são mistas
  (`ocr_phase3.py:611-613, 707-709`); em notação a `FusionEngine` prefere a
  camada de texto do PDF (`:348-359`), que é o OCR de fábrica que
  `livro.py:11-17` documenta como lixo; `ocr_layout.detectar_colunas` apaga a
  calha com a linha que a cruza (`ocr_layout.py:120-138`); sem tabela, trama,
  negativo, régua, célula fechada; diagramas sem porteiro, sem orientação,
  sem redesenho (`ocr_phase4.py:323-327, 362, 552-555`).
- **Três exportadores para os mesmos formatos** (`exportar.py`,
  `editorial_export.py`, `ocr_export.py`), dois resolvedores de posição de
  diagrama (`diagrama._arbitrar` vs `ocr_phase4.resolve_position`), duas
  segmentações, duas filas, três alinhamentos de texto. O Invariante 10 do
  `CONTEXT.md` (mesma sequência de blocos em todo formato) não vale hoje.
- **Configuração implícita**: idioma fixo `"en"` no menu editorial
  (corrigido), `.pth` literal em quatro lugares, `engine="native"` sem efeito,
  duas `ExportOptions` homônimas, cache inerte (`cache_dir=None`) e chave sem
  os pesos reais.
- **Memória e cancelamento** no caminho novo: `DocumentSource.evidences()`
  rasteriza todas as páginas antes de processar e relê o PDF por página para
  o `sha256` (`editorial_pipeline.py:163, 217-243`); `process()` chama
  `inspect()` de novo (`:708`).

### 3.2 Falhas silenciosas (P0/P1)

- **Tesseract ausente era página sem texto.** `OCRService` devolvia `""`/`[]`
  em `except Exception` (`ocr_service.py:108-112, 155-163`), e os `except`
  escritos acima para esse caso eram letra morta. *Corrigido:
  `MotorIndisponivel`, sondagem antes da exportação, registro por página,
  linha no relatório.*
- PDF da Fase 6: `failed_items: 0` fixo, bbox em pixels usado como pontos,
  texto **visível** por cima do scan (`editorial_export.py:241-267`). *Corrigido.*
- Modelo neural que não carrega: `self.erro` vazio e "veja o console" num
  app sem console (`neural_trainer.py:756-763`). *Corrigido.*
- `torch.load` sem `weights_only=True` no CRNN e no modelo de glifos, ao
  contrário de `diagrama.py:1313`. *Corrigido.*
- Cache guarda o resultado vazio de um motor indisponível e não invalida
  quando o motor é instalado (`ocr_runtime.py`, `editorial_pipeline.py:772-787`).
- `predict_neural` devolvia `"?"` — um NAG real — como sentinela. *Corrigido.*
- Erros de tarefa só num `messagebox` efêmero; exceções em callbacks do Tk
  iam para um `stderr` que o app por atalho não tem. *Corrigido em `appy.py`.*

### 3.3 Modelos e treino

- **O CRNN de linha não é utilizável**: 333 linhas de treino contra 1.136 de
  validação, perda de validação subindo, **CER 96%** na validação
  (`text_line_training_report.txt`) — e estava a um "Sim" de virar o leitor
  de faixa da exportação e num botão que escreve direto nos boxes. Alfabeto
  derivado do corpus (sem figurinas pretas nem metade dos NAGs), confiança
  média sobre os passos de blank, sem temperatura, sem seed no `torch`, sem
  gate de promoção. *Corrigido o que é contrato: portão de produção
  (`linha_trainer.modelo_utilizavel`, CER ≤ 15%), seed, `weights_only`,
  confiança só dos caracteres emitidos, CER gravado nos metadados.* O modelo
  em si continua fora de produção até ser retreinado com dados suficientes.
- A calibração do modelo de glifos e do de diagramas é de produção
  (`core/calibracao.py`, temperatura aplicada). `ocr_phase7.calibrate_domains`,
  `split_corpus` e `evaluate_holdout` estão implementados e testados, mas
  nenhum treinador real os chama; `linha_sintetica.gerar` pode vazar texto
  da validação para o treino.
- Splits: `CorpusSplit.validate` não checava o holdout e
  `dividir_documentos` o reabsorvia. *Corrigido.*
- Dois *path traversal* em código que lê manifesto/pacote de terceiros
  (`ocr_phase8.ModelPackage._safe_name`, `ocr_corpus._path_relativo`). *Corrigido.*

### 3.4 Diagramas

- Reconhecedor forte e medido (ocupação 99,3%, identidade 98,0%
  leave-one-book-out, tabuleiro inteiro 92,5%, porteiro a 0,98).
- **A correção manual não volta para o livro**: "Usar este FEN" no diálogo
  8×8 só copia para a área de transferência (`main_window.py:4548-4555`).
- **`w - - 0 1` é convenção silenciosa** nos dois caminhos; a legenda
  ("Black to move") nunca é lida; a spec promete o contrário
  (`SPEC_IMPLEMENTACAO_OCR.md:250`). Orientação desconhecida não é sinalizada
  no diálogo legado quando não há rótulos. *Corrigido em 4.6.*
- Fase 4 exporta diagrama **sem imagem** (`editorial_export.py:85-98`), a
  revisão de diagrama da Fase 5 é uma caixa de texto sobre o FEN, e o estado
  `unresolved` é invisível no artefato em modo `clean`. *Corrigido em 4.6*
  (a revisão de diagrama já abre o `DialogoDiagrama` desde 4.5).

### 3.5 Interface

- 40 comandos num "Ferramentas" único; sem Editar/Exibir/Ajuda; "(OCR)"
  querendo dizer Tesseract; fase do roadmap no rótulo. *Reorganizado por
  etapa, com mnemônicos (Alt+letra) e Ajuda → Atalhos.*
- `Delete`/`Backspace` apagavam o box enquanto o usuário editava o campo
  "Caractere"; as setas da rotulagem trocavam de linha com o foco no texto e
  perdiam a edição; `_run_task` ignorava o `False` de `task.start()`;
  cancelar o processamento editorial dava **erro** (`OCRCancelled` não era
  `Cancelled`). *Corrigidos.*
- Processo sem DPI awareness (medido `GetProcessDpiAwareness = 0`): o scan
  chegava borrado em monitor a 125–150%. *Corrigido.*
- **"Exportar Livro" é um assistente de até 14 caixas modais** em sequência,
  sem memória entre exportações; `config/settings.py` nunca é instanciado.
- Não há fila global de suspeitas no fluxo principal; a fila editorial não
  mostra o recorte, não filtra, não faz lote e edita FEN por `askstring`;
  confiança e motivos aparecem como números e códigos (`low_confidence`).
- Trabalho pesado na thread do Tk em `generate_boxes_opencv`,
  `extrair_diagramas`, `avaliar_modelo_linhas`, `validar_dataset_linhas`,
  `save_box_file` (PNG a 300 dpi), `DialogoSemelhantes`.
- Canvas abre em zoom 1,0 no canto; roda = zoom, logo sem rolagem vertical;
  nenhum estado persiste (geometria, último diretório, filtros).

### 3.6 Testes

- Os 25 arquivos novos das Fases 0–8 são sintéticos (nenhum toca página
  real); dois furos de produto passariam: `side_to_move` sempre `"w"` e a
  ausência do teste de aceitação da Fase 6 (mesma sequência de blocos nos
  quatro formatos). Marcadores `ml`/`gui` declarados e nunca usados.
  `test_linha_predictor_conf` lê o peso da raiz do repositório.
- *Acrescentados nesta revisão: motor indisponível (9), fachada de produção
  (10), guardas da janela (3), prosa colada ao lance (26), menu por fluxo
  (4), registro de engines (2).* Suíte: 2.252 → 2.306 testes, verde.

## 4. O que foi feito nesta revisão

### 4.1 Precisão de leitura (`core/livro.py`)

Os 35 tokens que sobravam na p. 237 do Nunn eram quase todos o mesmo defeito
em três formas, e a régua nova é lexical e geométrica, não estatística:

- `_partir_prosa_colada_ao_lance`: o token com figurina que **não** tem forma
  de lance inteiro (`W:W1n(1♖d1!)`, `Draw(1...♖h2!)`) é partido onde o lance
  começa, se o que vem antes é palavra (duas letras, sem figurina). A prosa
  vai para o motor e o lance fica com a âncora, que é a regra de sempre.
- `_colar_numero_de_lance` ganhou o parêntese partido do número
  (`( 1...♔h6`), a reticência com espaço no meio (`1 . ..♖d2`), o sinal
  partido do lance (`♖e8 !`) e o `l` que é `1` (`(l...♖a2!)`);
  `RE_NUMERO_PARTIDO` aceita `(` antes e exige caractere depois dos pontos
  (o `I ...` de um diálogo em prosa fica como está).
- `_espacos_do_motor`: o espaço impresso que a régua da cadeia não viu
  (`(1♖d1!)` por `(1 ♖d1!)`) entra quando o vão entre duas palavras do motor
  cai num vão entre dois boxes da âncora — evidência dos dois lados —, nunca
  antes de pontuação, entre peça e casa, nem em volta do traço do roque e do
  resultado (`O-O`, `1–0`), que o motor perde com frequência.

A revisão adversarial das próprias regras pegou dois furos antes de entrarem:
`I...exchange` viraria `1...exchange` (o `l`→`1` passou a exigir a casa
inteira) e `O-O` viraria `O - O` (o traço entrou na lista do que cola).

Medido (`scripts/ab_ocr_livro.py`, modo `palavra`; os dois modos de
controle também melhoram):

| página | CER prosa | WER prosa | CER notação | WER notação | CER total |
|---|---:|---:|---:|---:|---:|
| Aagaard p. 30 antes | 1,33% | 2,90% | 4,60% | 11,36% | 2,40% |
| Aagaard p. 30 depois | **0,51%** | **2,42%** | **3,14%** | 11,36% | **1,37%** |
| Nunn p. 237 antes | 5,80% | 10,30% | 11,38% | 24,66% | 8,19% |
| Nunn p. 237 depois | **0,54%** | **1,82%** | **3,63%** | **8,22%** | **1,87%** |
| Yusupov p. 34 | 0,66% | 2,34% | 0,76% | 3,39% | 0,71% |
| Yusupov p. 47 | 2,92% | 5,66% | 0,00% | 0,00% | 2,50% |

O que sobra na p. 237 é da cadeia e da segmentação, não da fusão: a fila de
cabeçalho da tabela (`W♔d1 W♔c1 W♔b1`, bloco baixo e largo que
`trama.candidatos` recusa), os dois `*` (classe que a cadeia não tem),
`1..♖b2?` (um ponto perdido), `-see` e `w♖g1`. Na p. 30 sobram os erros
confiantes da cadeia no lance, que são a OCR-14.

### 4.2 Integração: o leitor medido dentro da fachada

`core/editorial_legacy.py` monta o `legacy_extractor` da `EditorialPipeline`
com os leitores da exportação de livro (`ExtratorDeLivro`,
`OpcoesDeLeitura`, `pipeline_de_producao`). O menu "Documento editorial"
passa a perguntar intervalo de páginas e idioma, sondar o Tesseract, ler
pela fusão por palavra e escrever JSON/HTML/TXT/PDF pelo IR e EPUB/DOCX pelo
escritor histórico (o único que embute fonte de símbolos e redesenha
diagramas). O adapter legado passou a carregar a caixa do parágrafo, a
largura/dpi da página e o aviso do motor que faltou; o PDF pesquisável do IR
sai invisível, escalado e com contagem real de falhas (verificado: 297
palavras na camada da p. 30, pixels idênticos aos do original).

### 4.3 Portões e falhas que deixaram de ser silenciosas

`MotorIndisponivel` e `tesseract_disponivel()` em `OCRService`;
`PaginaExtraida.motor_indisponivel`, `largura`, `dpi`; sondagem antes da
exportação e linha no relatório; `linha_trainer.modelo_utilizavel` com
`CER_MAXIMO_EM_PRODUCAO = 0,15` e os três pontos que o consultam (registro de
engines, pergunta da exportação, botão de preenchimento); `OCRCancelled` é um
`Cancelled`; `_decision_requires_review` deixa de pôr todo bloco automático
na fila; `CorpusSplit.validate` e `dividir_documentos` respeitam o holdout;
`_safe_name` e `_path_relativo` recusam raiz, drive e `..`; `to_dict` do
treino grava a proveniência; carimbos em UTC.

### 4.4 Interface

**Uma caixa só para exportar** (`ui/dialogo_de_exportacao.py`, item 1 da
lista de 5, feito em 2026-09-18): formato, destino, páginas, idioma, estado
do Tesseract, reparo de colagem, modelo de linha (atrás do portão), coleta
com teto, diagramas (redesenho, fonte embutida, coordenadas, e o painel com
a amostra de verdade) — no lugar das catorze `messagebox` encadeadas. O que
se escolheu volta preenchido da próxima vez (`Settings`, chave
`exportacao`), de modo que exportar o mesmo livro de novo é abrir a caixa e
confirmar; o botão só libera com o formulário consistente, e cancelar é
desistir. `OpcoesDeExportacao` é o que a ação consome, e a mesma caixa
serve o documento editorial com mais formatos. Cabe em 768 px de altura
(1136×586). `test_f26_livro` migrou do dublê por título para o dublê da
caixa; `test_dialogo_de_exportacao` fixa o contrato (20 testes).

Menu por etapa (Arquivo → Exportar; Editar; Reconhecer com o modo
recomendado primeiro; Revisar; Modelo; PDF; Notação; Ferramentas; Ajuda com
a lista de atalhos), mnemônicos, guardas de foco em Delete/Backspace e nas
setas da rotulagem, `_run_task` que recusa a segunda tarefa e avisa, DPI
awareness e `tk scaling`, `report_callback_exception` gravando o
`crash_log` com carimbo e mostrando o caminho (a mesma exceção repetida num
handler de movimento vai só para o log, sem tempestade de caixas), o botão
"OCR (box)" dizendo por que o Tesseract faltou, o diálogo de rotulagem
consultando o mesmo portão do modelo de linha, mojibake corrigido em 14
linhas de cinco arquivos, "Próximo" com acento.

### 4.5 A fila de suspeitas com evidência (item 2, 2026-09-19)

O adapter do leitor medido (`core/editorial_adapters.py`) marcava todo bloco
`automatic` a 1,0, e a fila de um livro inteiro saía **vazia**; a da fachada
nova punha o livro inteiro dentro. Agora cada linha impressa do parágrafo
vira uma `Evidence` com as duas leituras (a âncora da cadeia própria e a
linha do motor, como hipóteses), a caixa da linha na página e os motivos de
suspeita — em código, para a fila ordenar, e **em frase**, para o revisor
ler. Para isso o leitor passou a guardar de que registros de roteamento cada
parágrafo saiu (`Paragrafo.registros`, paralelo a `inicios` e cortado junto
por `_cortar`), a caixa de cada linha no registro (`caixa`) e a do tabuleiro
na figura (`Figura.caixa`).

A régua é `core/editorial_suspeitas.py`, lexical e geométrica como as de
`livro.py`, e cada regra existe por um resíduo de 4.1: o token com figurina
que não tem forma de lance (`25♖xc7!`, `57..♖xc4?`, `w♖g1`, `1..♖b2?`); o
que começa como número de lance e não é lance (`26...g16`); o lance de peão
que o motor leu diferente da cadeia (`gxh5` × `a6`, com a peça fora da
comparação — o motor a lê como letra — e só com o motor acima de 0,6); a
linha vazia que a cadeia derrubou e o motor leu (`*`); a prosa que ficou
com a cadeia porque o motor não confirmou ou não devolveu a linha; o
resultado partido no fim da linha de lances (`35.♔h3 1`); a figurina sem
casa no fim da linha (`4.♘e5 ♕`); o sinal que não é de prosa (`El]`, `[n`,
`§.Tarrasch`, `opponent,s`, a aspa que abre e não fecha); a linha que é um
sinal só (`:`, `/`, o cisco da trama). A avaliação colada ao lance
(`3.♕h4+–`, `6.♘e5++–`) **não** é lance malformado — sem isso a p. 34 do
Yusupov entrava inteira.

Medido com `scripts/fila_de_suspeitas.py` (lê pela fachada, imprime a fila e
confere cada linha suspeita contra a referência humana):

| página | blocos na fila | linhas suspeitas | erro real | falso positivo | erros fora da fila |
|---|---:|---:|---:|---:|---:|
| Aagaard p. 30 | 4 de 5 | 8 | 8 | 0 | 3 (`⩲`/`±`, `♕c1`/`♕e1`, `Bur`) |
| Nunn p. 237 | 3 de 11 | 4 | 4 | 0 | 1 (`—see`) |
| Yusupov p. 34 | 5 de 30 | 5 | 5 | 0 | 2 (`Solutions f7`, `33`) |
| Yusupov p. 47 | 6 de 16 | 6 | 6 | 0 | 5 (`CHAPTER )`, `🗸`, `. -`, `:`, `— German`) |

Os 23 apontados são erros; o que escapa é o erro confiante da cadeia num
lance bem formado (a OCR-14, item 5) e cisco tipográfico. A fila aceita um
teto por página (`build_review_queue(limite_por_pagina=N)`), e o impacto
segue a spec: diagrama recusado, depois a linha perdida e o lance, depois a
palavra, depois o sinal.

A sessão (`core/editorial_review.py`): **desfazer é uma pilha** — cada
`undo` volta um passo do revisor, um lote (`aceitar semelhantes`, eventos
com o mesmo `batch:<id>`) volta inteiro, e o bloco volta ao **estado** de
antes (`ReviewEvent.before_status`), de modo que o aceito e desfeito
reaparece na fila; era "o último evento que não é undo", e dois `undo`
voltavam o mesmo passo. `substituir_linha` troca uma linha do bloco pela
leitura escolhida; `semelhantes` são os itens do mesmo tipo e motivos.

A janela (`ui/dialogo_revisao_editorial.py`): o recorte da página no lugar
do bloco e, linha a linha, no lugar de cada linha (`ProvedorDePaginas`
rasteriza a origem na escala em que ela foi lida, quatro páginas em memória);
as linhas do bloco com as duas leituras e "Usar cadeia"/"Usar motor"; o
motivo em frase; filtro por página e tipo e teto por página; lote com
amostra e contagem; o valor editável (Ctrl+Enter salva); teclas que não
valem com o foco no texto; cabe em 768 px (1180×600, encostada no alto). O
diagrama abre no `DialogoDiagrama` ao lado do recorte impresso
(`leitura_de_fen` monta a posição do IR) e o FEN que sai de lá entra no
documento. **"Exportar com as correções"** regrava o arquivo da exportação:
os formatos do IR pelo documento revisado, o EPUB/DOCX pelas
`PaginaExtraida` com a revisão aplicada (`aplicar_revisao`: texto, filas,
FEN redesenhado com a fonte do livro, bloco rejeitado fora) — o FEN revisado
**volta** para a exportação. Testes: `test_editorial_suspeitas` (32, a régua e o
leitor), `test_fila_de_suspeitas` (15), `test_dialogo_revisao_editorial` (15),
`test_revisao_na_janela` (5).

### 4.6 Diagrama sem convenção silenciosa (item 3, 2026-09-22)

Um tabuleiro desenhado não contém o lado a jogar, e o FEN **exige** o campo.
Até aqui os três caminhos o preenchiam com `w` em silêncio — `Leitura.fen`, o
`TabuleiroEdicao` e o `resolve_position` da Fase 4 —, e um FEN abre em qualquer
programa de xadrez e vira fato: "brancas a jogar" por convenção é o tipo de
afirmação que ninguém confere e que muda um final inteiro.

A página costuma dizer, e a peneira é `core/lado_a_jogar.py`: "White to play"
e "Black to move" (o Nunn imprime um dos dois embaixo de cada diagrama), "as
brancas jogam", "juegan las negras", a figurina no lugar da palavra (`♔ to
play`) e os dois NAGs da família "Lado" do `core/nags.py` — o `▼` do `➤ Ex.
22-4 ◀ ★★ ▼` é a única coisa naquela página do Yusupov que diz de quem é a
vez. **Legenda que fala dos dois lados não decide nada**: a p. 237 do Nunn
abre com `W=White to play B=Black to play`, que é a chave de uma tabela e não
a vez de um diagrama; ali o resultado é `ambigua` e fica a convenção.

Onde isso entra:

- **O caminho legado.** `diagrama.ler_pagina` lê o título do diagrama e grava
  `Leitura.lado_a_jogar`; `fen()` sai com ele e o aviso da convenção é trocado
  pelo que diz de onde o lado veio. `livro._figura_do_diagrama` lê a legenda de
  baixo **e o cabeçalho de cima** (que a `figura` passou a ler *antes* do
  desenho, porque o indicador de lado faz parte dele) e grava
  `Figura.lado_a_jogar`/`lado_origem`; o FEN sai com o lado e o desenho ganha o
  quadradinho de quem joga — que a ED-05 já sabia desenhar, e que só agora tem
  quando desenhar (DEC-06).
- **A Fase 4.** `resolve_position` deixou de assumir: sem lado explícito, lê a
  legenda das `annotations`; sem ela, o `w` sai com `side_to_move_source =
  "assumed"`, `reason_code` e aviso. `Phase4Processor` associa a legenda por
  geometria (`legendas_do_diagrama`: a linha encostada na borda, dentro de uma
  folga de 35% da altura do tabuleiro e cobrindo um quarto da largura dele) —
  "White to play" é uma linha como outra qualquer para a Fase 3, e só a posição
  dela diz que fala **deste** diagrama. `DiagramResult.review` aceita o lado
  informado por quem revisa, e aí o aviso sai.
- **O carimbo.** `exportar._alternativo` escreve `<FEN> — pretas a jogar (da
  legenda)` ou `… (assumido: a página não diz)`; a exportação editorial põe a
  mesma ressalva na `figcaption`, mais `data-side-source`, e o **"não revisado"
  sai em todos os modos, inclusive no limpo** — o modo limpo tira a
  proveniência, que é para quem revisa, não a ressalva, que é para quem lê.
- **O diálogo legado** (`ui/dialogo_diagrama.py`) avisa quando a orientação não
  foi confirmada: sem coordenadas em volta, a leitura assume brancas embaixo, e
  um diagrama impresso do lado das pretas sai plausível, legal e espelhado —
  quem confere casa a casa não desconfia, porque a leitura bate com a tela e as
  duas estão erradas do mesmo jeito. O lado lido da legenda chega ao diálogo
  marcado (`TabuleiroEdicao.lado_origem`), e o aviso deixa de dizer "veio de
  quem editou" sobre o que a página afirmou.
- **A figura que faltava.** `EditorialExporter` desenha o tabuleiro a partir do
  FEN quando o bloco não traz PNG — que é o caso de **todo** diagrama da Fase 4,
  que guarda a posição e o hash do recorte, não os pixels. O `<figure>` dela
  saía com legenda e sem figura, no HTML da exportação editorial e no da
  fachada; hoje o DOCX também leva a imagem, e o relatório da exportação acusa
  o diagrama que ficou sem nenhuma e quantos saíram sem revisão.

**O `alt` é lido de volta**, e isso limitou o formato: o editor de livros
reconstrói o diagrama do EPUB pelo `alt` (`core/editor/xhtml.py`), então o FEN
vai inteiro e na frente, e a ressalva atrás de um ` — `. `lado_a_jogar.do_alt`
faz o caminho de volta e **só devolve o lado quando ele foi lido**: o que o
escritor declarou convenção não volta como leitura, que é a DEC-06 valendo no
round-trip. De quebra, o EPUB reaberto no editor agora traz o lado a jogar que
a página dizia, em vez de perdê-lo.

Aceite: `tests/test_lado_a_jogar.py` (41), com os dois critérios do roadmap em
`test_legenda_black_to_move_termina_o_fen_em_b` e
`test_nenhum_diagrama_sai_sem_imagem`. A suíte inteira: 2.865 passando. O A/B
das quatro páginas não mexeu — Aagaard p30 1,37% · Yusupov p34 0,71% · p47
2,50% · Nunn p237 1,87%, os mesmos de 2026-09-18.

## 5. O que fica, em ordem

Cada item tem critério de aceite; nenhum é pré-requisito de outro fora da
ordem indicada.

1. ~~Um diálogo de exportação no lugar das 14 caixas~~ — feito (4.4).
2. ~~**Fila de suspeitas com evidência** (`core/editorial_review.py`,
   `ui/dialogo_revisao_editorial.py`): recorte pelo bbox da página,
   alternativas (âncora × motor, do `roteamento`), motivo em linguagem
   humana, lote com amostra e desfazer em pilha; o diagrama abre o
   `DialogoDiagrama`, e o FEN revisado **volta** para a exportação. Aceite:
   nas quatro páginas a fila contém os resíduos listados em 4.1 e mais nada
   além de N por página; `undo` duas vezes volta dois passos.~~ — feito
   (4.5): 23 linhas apontadas nas quatro páginas, 23 erros, 0 falsos
   positivos; o que escapa é a OCR-14 e cisco tipográfico.
3. ~~**Diagrama sem convenção silenciosa**: lado a jogar da legenda quando
   houver ("White/Black to move", "brancas jogam"), senão marcado no alt e
   na figcaption; aviso de orientação não confirmada no diálogo legado;
   imagem do diagrama no export da Fase 4 e sinal de "não revisado" mesmo em
   modo limpo. Aceite: teste com "Black to move" na legenda termina o FEN em
   `b`; nenhum diagrama sai sem imagem.~~ — feito (4.6): `core/lado_a_jogar.py`
   lê a legenda nos dois caminhos, o carimbo sai no `alt`, na `figcaption` e no
   diálogo, e o diagrama sem PNG é desenhado do FEN na exportação.
4. **Adapter sem perdas e inverso** (`editorial_adapters.py`): `Evidence`
   por linha com as duas leituras e confiança derivada do `roteamento`,
   `negrito` como runs, `casas_de_largura`, `origem` como `kind` próprio,
   `pagina_editorial_para_extraida`. Aceite: round-trip
   `PaginaExtraida → IR → PaginaExtraida` igual; EPUB byte-idêntico.
5. **OCR-14** — os erros confiantes da cadeia no lance (`⩲`/`±`, `♕e1`/`♕c1`,
   `g16`/`gxh6`, `1–0`): fine-tuning direcionado do modelo de glifos, medido
   no mesmo A/B; o CRNN só volta com dataset por livro, split de
   `ocr_phase7`, seed, confiança calibrada e `evaluate_holdout` contra a
   fusão atual.
6. **Corpus de referência**: as quatro páginas viram trinta, por livro e por
   família de layout, conferidas contra o impresso; `benchmarks/` ganha o
   relatório por rodada. Só depois disso a promessa "superior ao ABBYY nestes
   livros" pode ser escrita.
7. **Cache e memória do caminho novo**: `evidences()` como gerador, `sha256`
   uma vez, `inspect()` fora de `process()`, chave com a assinatura dos três
   pesos, `cache_dir` padrão em `config.paths.data_dir()`.
8. **Poda**: apagar `ocr_hybrid`, `ocr_fusion`, `ocr_context`, `ocr_review`,
   `ocr_export`, `_page_from_text`; rebaixar `Phase3Processor`/`FusionEngine`/
   `ocr_layout` a biblioteca de inspeção; reescrever
   `ROADMAP_IMPLEMENTACAO_OCR.md` separando "em produção" de "biblioteca".
9. **Interface**: `Exibir` (ajustar à janela ao abrir, roda = rolar, Ctrl+roda
   = zoom, `+ − 0 F`), estado persistente (geometria, último diretório,
   filtros), trabalho pesado fora da thread do Tk nos seis handlers
   listados em 3.5, `ui/tema.py` com tokens de cor e `ttk.Style`, e os
   caminhos relativos ao cwd (`training_data_linhas`,
   `text_line_training_report.txt`) resolvidos por `config.paths`.
10. **Testes de aceitação**: uma página → IR → HTML/DOCX/EPUB/PDF com a mesma
    sequência de blocos; tabela nos quatro formatos; duas colunas ponta a
    ponta; cache invalidado por troca de modelo; fusão preservando figurina;
    tela de revisão por teclado; `smoke_test_installation` real;
    `treinar_pacote` sem escrever fora do `tmp_path`.
