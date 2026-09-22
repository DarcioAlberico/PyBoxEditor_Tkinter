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
falta para o rótulo é o que a seção 5 lista. Os quatro primeiros itens saíram, e o 5 e o 6 estão pela metade —
a exportação por um diálogo só (4.4), a fila de revisão com o recorte e as
alternativas (4.5), o diagrama sem convenção silenciosa (4.6) e o adapter sem
perdas, com a volta para o leitor (4.7); do 5 saiu o garimpo do resíduo
confiante (4.8), do 6 o corredor da rodada e a régua de famílias (4.9), e o 7
inteiro (4.10) —; ficam o dado do 5 e do 6 (conferir a quarentena, transcrever
as páginas), a poda da biblioteca paralela, a interface e os testes de
aceitação.

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
  *Metade corrigida em 4.10*: a chave passou a levar os três pesos, então
  treinar o modelo invalida o gravado; o motor de prosa continua fora da chave,
  porque quem o chama é o caminho legado, que não passa pelo cache.
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

### 4.7 O adapter sem perdas, e a volta (item 4, 2026-09-22)

A ida — `PaginaExtraida` → IR — existe desde a Fase 1. A volta não existia, e a
falta dela custava duas coisas: o documento revisado só sabia virar arquivo
pelos escritores do IR (os dois que embutem fonte de símbolos e redesenham
diagrama, `exportar.para_epub` e `para_docx`, pedem `PaginaExtraida`), e quem
queria os dois mundos guardava a lista de páginas ao lado do IR
(`ExtratorDeLivro.ultimas_paginas`) torcendo para as duas não divergirem. Um IR
gravado e reaberto noutra sessão não tinha como sair em EPUB.

O que a ida perdia, e passou a levar:

- **`origem` da figura vira tipo de bloco.** Três das quatro origens de
  `livro.Figura` não são um tabuleiro: a `faixa` é o cabeçalho impresso acima do
  diagrama e a `pagina` é a página inteira que virou imagem. As quatro iam como
  `diagram`, e o resultado era `<figure data-fen="None">` em cima de uma imagem
  de cabeçalho — e o editor procurando posição onde não há. Agora `faixa` é
  `caption`, `pagina` é `figure` (tipo novo do IR) e só `render`/`recorte` são
  `diagram`; os três escritores de HTML, o DOCX e o importador do editor
  ganharam o ramo correspondente.
- **`casas_de_largura`** (`squares_wide`): é o que faz o corpo em pontos valer
  para a imagem (F97). Sem ela o diagrama que ia e voltava saía noutro tamanho
  no mesmo livro.
- **As linhas impressas do parágrafo** (`line_starts`, `routing_rows`): o
  parágrafo que voltava não sabia mais de que linhas tinha saído, e com elas ia
  a fila de revisão.
- **`fen` vazio em vez de nulo** no recorte sem posição: quem escreve o arquivo
  convertia o `None` para texto, e saía `data-fen="None"`.
- **O negrito como `run`.** O adapter guarda as faixas em `style["bold_spans"]`
  desde a Fase 1 e os escritores do IR as ignoravam: o parágrafo saía inteiro em
  redondo. Hoje o HTML sai com `<strong>` e o DOCX com `run` em negrito
  (`trechos_em_negrito`).

A volta é `pagina_editorial_para_extraida` / `documento_para_paginas_extraidas`.
O que ela **não** repõe são `Paragrafo.pesos` e `Paragrafo.lacunas` — as medidas
por caractere que `partir_coladas` e `negrito.marcar` consomem *dentro* de
`livro.extrair`, antes de existir IR; guardá-las seria gravar dois floats por
caractere de livro num JSON para ninguém os ler, e
`editorial_legacy._bloco_revisado` já as descarta pela mesma razão quando o
texto muda. As páginas voltam **na ordem em que o documento as traz**, e não
ordenadas por `page_index`: quem exporta uma seleção passa a lista na ordem que
quer, e o EPUB numera os arquivos por ela.

Com a volta, `aplicar_revisao` passou a aceitar página que o leitor desta sessão
não leu: ela vem do próprio documento (onde o valor do bloco **já é** o
revisado), e só o diagrama desenhado é redesenhado com a fonte do livro. É o que
permite exportar EPUB e DOCX de um IR de outra sessão.

Aceite: `tests/test_adapter_sem_perdas.py` (14), com os dois critérios em
`test_o_round_trip_devolve_a_pagina_igual` (uma página com as quatro origens de
figura, tabela, título e parágrafo com negrito volta bloco a bloco igual) e
`test_o_epub_do_round_trip_e_byte_identico` (com `SOURCE_DATE_EPOCH`, que é a
convenção de build reprodutível da F111). Suíte inteira: 2.878 passando.

### 4.8 O garimpo dos erros confiantes (item 5, primeira metade, 2026-09-22)

A OCR-14 é o resíduo que nada alcança: a cadeia lê `±` onde está impresso `⩲`,
`♕c1` por `♕e1`, e **com confiança 1,00** — a medição da F22 já registrara
mediana 1,00 nos tokens errados, que é o que derrubou a ideia de gatear uma
segunda opinião pela confiança. Para o programa não são dúvida; são afirmação.
A fila de suspeitas (4.5) pega o que hesita, e por construção não pega isto.

O que resolve é treino dirigido, e treino dirigido precisa antes de uma lista:
*que par de glifos a cadeia troca, quantas vezes, e onde está cada recorte*.
Ela não existia. Agora existe:

- **`core/ocr14.py`** alinha o que a cadeia leu com a referência humana — tokens
  pela mesma régua do A/B (`ocr_ab.alinhar_tokens`), caracteres dentro do token
  depois — e devolve, por divergência, o esperado, o lido, a confiança, o
  domínio (lance ou prosa) e **a caixa do glifo na página**. A dobra tipográfica
  é a do A/B, feita caractere a caractere para o mapa das caixas não escorregar
  quando ela cresce (`…` vira `...`). Troca, buraco (a cadeia comeu) e invenção
  (a cadeia pôs) são espécies próprias: são material de treino diferente.
- **`scripts/erros_confiantes.py`** roda isso sobre as páginas de referência,
  lendo **só pela cadeia** (sem Tesseract, sem fusão: o que se mede é o
  classificador, que é o que se quer treinar), imprime a tabela de confusão e as
  classes que mais ganhariam com amostra nova, e com `--recortes` põe cada
  recorte trocado numa **quarentena** por classe esperada. Quarentena, e não
  `training_data/`: o rótulo veio de um alinhamento, não de olho humano, e
  `core/coleta.py` documenta em detalhe por que rotular sozinho é treinar o
  modelo no próprio erro.

**O que as quatro páginas dizem** (2026-09-22, cadeia sozinha, piso 0,90):

| página | confiantes na página | em lance | o que aparece |
|---|---:|---:|---|
| Aagaard p. 30 | 177 | **23** | `±` por `⩲`; `a` por `♘`; `w` por `c` |
| Nunn p. 237 (tabela) | 281 | **137** | `(`/`!`/`)` das células, `♖` e `♔` inventados |
| Yusupov p. 34 | 38 | **9** | o `1` e o `-` de `1-0` comidos |
| Yusupov p. 47 | 140 | **4** | idem |

Duas leituras destes números, e as duas importam:

1. **A conta é do classificador, não do livro.** A fusão por palavra dá a prosa
   ao motor e guarda o lance da cadeia, então os 154 erros de prosa da p. 30 não
   chegam ao arquivo — o CER de notação do modo `palavra` ali é 3,14%, e não o
   que estes 177 sugeririam. É por isso que o padrão do script é `--dominio
   notation`: o erro confiante **em lance** é o que sobrevive à exportação.
2. **O maior bolo é a página de tabela do Nunn**, onde a cadeia sozinha se perde
   na pontuação das células (`W: Win (1 ♖e1!)`). Fine-tuning de glifo não é a
   resposta ali — a resposta é a célula, que a F72 já trata e que o roteador já
   manda ao motor. O resíduo de verdade, o que o item 5 descreve, são as 23 da
   p. 30 e as 13 do Yusupov.

**O que fica do item 5**, e por que não foi feito aqui: a etapa do meio é
humana. A quarentena precisa ser conferida antes de virar base, e trinta e seis
recortes de quatro páginas não movem um classificador de 317 classes com 19 mil
amostras por figurina — `⩲` já tem 1.974 e `±`, 789, então o par não é falta de
classe, é discriminação fina. O caminho é o item 6 (o corpus de trinta páginas)
alimentando esta mesma peneira, e só então o fine-tuning, medido no A/B das
mesmas páginas com `evaluate_holdout` da `ocr_phase7`.

Aceite: `tests/test_ocr14.py` (15), de mesa — montam a leitura caractere a
caractere, sem PDF, sem modelo e sem torch.

### 4.9 A rodada do corpus, e o eixo em que ele cresce (item 6, 2026-09-22)

O item 6 pede trinta páginas no lugar de quatro, **por livro e por família de
layout**, e o relatório por rodada em `benchmarks/`. Transcrever vinte e seis
páginas é trabalho humano e continua sendo; o que dava para fazer — e que
faltava para esse trabalho valer — foi feito:

- **`core/familias_de_pagina.py`** diz a que família uma página lida pertence:
  imagem, tabela, trama, negativo, duas colunas, diagramas, notação, prosa. As
  seis primeiras saem da própria `PaginaExtraida` (colunas, tabelas, diagramas,
  domínio das linhas); a **trama** e o **negativo** não estão nela e não vão
  estar — a primeira é propriedade da imagem, a segunda do desenho do cabeçalho
  —, e vêm do rótulo humano do manifesto. Uma página pertence a várias famílias,
  e `principal` escolhe a **mais rara**, que é a que justifica transcrevê-la:
  prosa há em toda página; tabela, em quatro de um livro inteiro.
- **`scripts/rodada_do_corpus.py`** lê o manifesto congelado, roda o leitor de
  produção em cada página com referência, e grava a rodada em
  `benchmarks/rodadas/<data>.json` com três coisas que a tabela por página não
  dava: o **total do corpus** ponderado pelo tamanho de cada página (a média de
  páginas faria uma de doze tokens pesar como uma de trezentos, e o número que
  uma promessa comercial citaria é o do livro); a **cobertura por família**, que
  diz o que o corpus ainda não mede; e a **comparação com a rodada anterior**,
  com saída diferente de zero quando uma página piora além da tolerância.

**A primeira rodada (2026-09-22)**, que é também a linha de base do portão:

| página | família | CER prosa | CER notação | CER total |
|---|---|---:|---:|---:|
| aagaard-calculation-p030 | notação | 0,51% | 3,14% | 1,37% |
| nunn-rook-endings-p237 | tabela | 0,54% | 3,63% | 1,87% |
| yusupov-evolution-1-p034 | duas colunas | 0,66% | 0,76% | 0,71% |
| yusupov-evolution-1-p047 | trama | 2,92% | 0,00% | 2,50% |
| **corpus (4 páginas)** | | **1,44%** | **1,99%** | **1,62%** |

Os quatro números por página são os mesmos de 2026-09-18 — o corredor novo não
mudou o leitor —, e o **1,62% do corpus inteiro não existia**: era a média de
quatro páginas de tamanhos diferentes, feita à mão, ou não era feita.

**A cobertura diz o que falta**, e é a resposta ao item 6 em uma linha: com
mínimo de três páginas por família, faltam **imagem, tabela, trama, negativo e
diagramas** — cinco das oito. O caminho para cada página nova está no fim de
`preview_ocr/referencia/LEIA-ME.txt`: rascunho pelo A/B, revisão à mão contra a
imagem (um rascunho não conferido não é referência, é a opinião do programa
sobre si mesmo), e a entrada no manifesto.

**Onde a rodada mora.** `benchmarks/ocr_corpus_v1.json` e as rodadas não estão
no Git — a pasta `benchmarks/` ficou fora da ED-pré por ser trabalho de outra
ferramenta, e não é este commit que decide isso. O relatório de cada rodada é
gravado ali e fica à mão de quem mede.

Aceite: `tests/test_corpus_de_referencia.py` (12), de mesa — páginas de
mentira, sem PDF e sem modelo, inclusive o portão (uma página que piora 0,13
ponto percentual derruba a rodada; dentro da tolerância, não).

### 4.10 O custo do caminho novo (item 7, 2026-09-22)

Quatro defeitos de custo, todos invisíveis numa página e caros num livro.
Medido pela fachada em oito páginas de um PDF de 7,5 MB, a 300 dpi:

| | antes | depois |
|---|---:|---:|
| tempo | 5,9 s | **2,8 s** |
| pico de memória | 268 MB | **110 MB** |
| leituras integrais do PDF | 18 | **1** |

- **O `sha256` da origem era recalculado a cada acesso.** É uma propriedade, e
  `_evidences_pdf` a lia **uma vez por página** para pôr no `metadata` de cada
  evidência: oito páginas custavam 18 leituras integrais do arquivo, 135 MB
  hasheados. Num livro de 300 páginas e 100 MB seriam 600 leituras e 60 GB.
  Agora é calculado uma vez por objeto — que é congelado, e a origem não muda
  debaixo dele — e em pedaços de 1 MB, para o livro não precisar caber na
  memória só para ser identificado.
- **`evidences()` segurava todas as páginas na mão.** A lista mantinha o raster
  de cada uma viva até o fim — 8 MB por página a 300 dpi, 2,4 GB num livro de
  300 —, enquanto quem consome processa uma e esquece. Virou gerador, e o que
  `process` retém depois de mandar a página para o lote é a evidência **sem
  pixels** (`sem_raster`), com as medidas guardadas. Com um trabalhador, que é
  o padrão, há um raster vivo por vez; com vários, o `ThreadPoolExecutor`
  submete tudo de uma vez e o custo volta a ser o de antes — é o preço do
  paralelismo, e não uma regressão do laço. A validação da origem continua
  adiantada: quem chama espera o erro onde chamou, não na primeira iteração.
- **`process` rasterizava o documento uma segunda vez** só para pôr a inspeção
  no `metadata` (`self.inspect(source, options)`), e de quebra relia o arquivo
  para o `sha256`. Mas `_enrich_page` já grava layout, roteamento, tipo de
  origem, dpi, hash e camada textual em toda página processada — inclusive na
  que veio do cache, que os carrega no JSON. A inspeção passou a ser derivada
  dali (`PageInspection.da_pagina`), e sai **idêntica** à que a segunda passada
  produzia: conferido campo a campo nas páginas 30 e 31 do Aagaard. O que
  faltava era o roteamento das regiões **do layout** (o resultado processado
  roteia as regiões que leu, que não são as mesmas), e `_enrich_page` passou a
  gravá-lo também — de graça, porque os `specs` já estavam calculados ali.
- **O cache não guardava nada, e não sabia de que modelo era o que guardava.**
  `cache_dir` vazio queria dizer "sem cache", e não "no lugar de sempre":
  `scripts/processar_editorial.py` pedia cache por padrão e não guardava nada,
  e ninguém via, porque um cache que nunca acerta é indistinguível de um que
  não existe. Agora o padrão é `config.paths.cache_ocr_dir()` — na área do
  usuário, porque o cwd de quem abre por atalho não é a raiz do projeto — e
  **os três pesos entram na chave** (`custom_model.pth`, `diagrama_modelo.pth`,
  `ocupacao_modelo.pth`): sem eles, treinar o modelo e reprocessar o mesmo PDF
  servia a leitura do modelo velho como se fosse a do novo. É o mesmo defeito
  que a §3.2 anotou sobre o motor ausente — a página lida sem o Tesseract
  voltava depois de instalá-lo.

Duas decisões de borda que vale registrar: a assinatura dos pesos custa um
sha256 por arquivo e só é paga quando **há** cache para acertar (`use_cache`
falso não paga); e a suíte aponta `PYBOXEDITOR_CACHE_DIR` para uma pasta
temporária de sessão (`tests/conftest.py`), pela mesma razão da guarda da base
de ocupação: pasta de verdade não é lugar de teste, e um teste servindo
resultado gravado por outro é pior que lento.

O que **não** foi feito, e fica anotado: a pasta do cache não é podada por
ninguém. Cada página é um JSON de alguns KB e a chave inclui os pesos, então
uma troca de modelo deixa o que ficou para trás sem uso — apagar a pasta é
seguro a qualquer momento.

Aceite: `tests/test_pipeline_cache_e_memoria.py` (13).

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
4. ~~**Adapter sem perdas e inverso** (`editorial_adapters.py`): `Evidence`
   por linha com as duas leituras e confiança derivada do `roteamento`,
   `negrito` como runs, `casas_de_largura`, `origem` como `kind` próprio,
   `pagina_editorial_para_extraida`. Aceite: round-trip
   `PaginaExtraida → IR → PaginaExtraida` igual; EPUB byte-idêntico.~~ — feito
   (4.7): a `Evidence` por linha saiu em 4.5, e o resto aqui; o round-trip
   devolve a página bloco a bloco igual e o EPUB sai byte a byte igual.
5. **OCR-14** — os erros confiantes da cadeia no lance (`⩲`/`±`, `♕e1`/`♕c1`,
   `g16`/`gxh6`, `1–0`): fine-tuning direcionado do modelo de glifos, medido
   no mesmo A/B; o CRNN só volta com dataset por livro, split de
   `ocr_phase7`, seed, confiança calibrada e `evaluate_holdout` contra a
   fusão atual. **Metade feita** (4.8): o garimpo existe
   (`core/ocr14.py`, `scripts/erros_confiantes.py`) e mediu o resíduo nas
   quatro páginas — 23 erros confiantes em lance na p. 30 do Aagaard, 13 no
   Yusupov, e a página de tabela do Nunn, que é outro assunto. O que falta é
   dado: conferir a quarentena à mão e alimentá-la com o item 6, porque
   trinta e seis recortes não movem um classificador em que `⩲` já tem 1.974
   amostras e `±`, 789 — o par não é falta de classe, é discriminação fina.
6. **Corpus de referência**: as quatro páginas viram trinta, por livro e por
   família de layout, conferidas contra o impresso; `benchmarks/` ganha o
   relatório por rodada. Só depois disso a promessa "superior ao ABBYY nestes
   livros" pode ser escrita. **O corredor está feito** (4.9): a rodada mede o
   corpus inteiro, pondera o total (1,62% de CER nas quatro), diz a cobertura
   por família e derruba a rodada em que uma página piora; o caminho de cada
   página nova está no fim de `preview_ocr/referencia/LEIA-ME.txt`. **Falta a
   transcrição**: cinco das oito famílias — imagem, tabela, trama, negativo e
   diagramas — têm menos de três páginas.
7. ~~**Cache e memória do caminho novo**: `evidences()` como gerador, `sha256`
   uma vez, `inspect()` fora de `process()`, chave com a assinatura dos três
   pesos, `cache_dir` padrão em `config.paths.data_dir()`.~~ — feito (4.10):
   oito páginas passaram de 5,9 s / 268 MB / 18 leituras do PDF para 2,8 s /
   110 MB / 1 leitura, com a inspeção derivada saindo idêntica à que a segunda
   passada produzia. Falta poda da pasta do cache, anotada lá.
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
