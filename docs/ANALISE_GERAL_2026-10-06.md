# Análise geral do PyBoxEditor — 2026-10-06

Levantamento feito sobre a árvore de trabalho em `master` (`f2a9fab`, igual a
`origin/master`), com a suíte rodada no `.venv`, o `ruff` e o `compileall` do gate
da CI, o grafo de importações por AST e a leitura dos documentos de revisão,
roadmap, operação e setup. Toda medida abaixo é desta data.

## Veredito

O produto está tecnicamente são: CI verde no `master`, suíte local verde, lint
limpo, tipagem alta e uma arquitetura em camadas que dá para reconhecer. O risco
dominante não está no código, está na gestão da mudança: duas semanas de trabalho
de produto viviam só na árvore, sem commit, escritas por dois agentes, e a CI
nunca tinha visto nada disso. Depois vêm o tamanho de três módulos, a biblioteca
paralela de OCR que sobrou da poda e a falta de porta de entrada na documentação.

Prontidão, no critério de auditoria de produção: **72/100, lançável com
ressalvas**. As ressalvas são a árvore sem commit e o bundle desktop, que não foi
revalidado nesta análise.

## Panorama e números

| Métrica | Medido em 2026-10-06 |
|---|---|
| Código de produto | ~99 mil linhas em 192 módulos: `core` 40 k, `core/editor` 18 k, `ui/editor` 21 k, `ui` 10 k, `core/services` 5 k, `scripts` 4 k |
| Scripts de medição na raiz | 43 arquivos, 15 mil linhas (`medir_*.py`, `gerar_*.py`, `importar_*.py`) |
| Testes | 254 arquivos, 3529 coletados, 3511 verdes em 5 min 13 s (`-m "not slow"`), 18 lentos fora do gate |
| CI | verde em Python 3.11, 3.12 e 3.13 no `f2a9fab` |
| `ruff` e `compileall` | limpos |
| Funções com anotação de tipo | `core` 96 %, `ui` 79 %, `scripts` 91 % |
| Árvore contra `HEAD` | 122 alterados, 10 apagados, 956 sem rastreio, +9533/−2425 linhas |
| Repositório | 171 MB de pack, 7085 arquivos rastreados, 6486 deles imagens de treino |
| Documentação | ~1,5 MB de markdown; só o `ROADMAP.md` tem 783 KB |

### Como o sistema está montado

São três produtos numa base só:

1. **O editor de boxes com OCR de página digitalizada.** `appy.py` abre
   `ui/main_window.py`, que fala com `core/services/*` (`BoxService`,
   `OCRService`, `LearningService`, `PDFService`, `TaskService`). O leitor medido
   é `core/livro.py`: a cadeia própria de glifos ancora o lance, o Tesseract lê a
   prosa, a fusão é palavra a palavra; `core/pdf_nativo.py` lê o PDF nascido
   digital, e `core/diagrama.py` lê o tabuleiro.
2. **O pipeline editorial.** `core/editorial_model.py` é o documento
   intermediário versionado; `editorial_adapters.py` faz a ida e a volta sem
   perdas; `editorial_review.py` e `editorial_suspeitas.py` são a fila de revisão
   com diário; a fachada `editorial_pipeline.EditorialPipeline` é montada por
   `editorial_legacy.pipeline_de_producao` sobre `livro.extrair`.
3. **O editor de livros.** `core/editor/*` (modelo, dialeto XHTML, EPUB, DOCX,
   HTML, PDF, PGN, ortografia, tipografia) e `ui/editor/*` (`JanelaDoEditor`,
   `TextoRico`, `EditorDeCodigo`, menus, painéis).

O glossário e as dezesseis invariantes de `CONTEXT.md` são um ponto forte raro. O
caminho de produção está descrito etapa por etapa, com número medido em cada uma,
em `docs/ROADMAP_IMPLEMENTACAO_OCR.md` (CER 1,59 % ponderado no holdout v2 a 300
dpi; Dvoretsky 815 de 816 páginas pela camada).

## Achados, por prioridade

### P0. Cerca de doze mil linhas de produto sem commit

A árvore carregava os itens 8 a 10 da revisão de 2026-09-23
(`docs/REVISAO_MODOS_OCR.md` §4.11–§4.13), o trabalho da outra ferramenta de 25 e
26/09 (§4.14, corpus v2, holdout, gate editorial, revisão da OCR-14), o bundle
desktop da F125, nove módulos novos em `core`, onze scripts, 36 testes e 861
amostras novas de treino. Nada disso tinha passado pela CI, e o Linux só se testa
por push.

Conferido: a árvore coleta, compila, passa no `ruff` e na suíte. Conferido também,
por `git blame` das linhas que a árvore remove de commits posteriores a 23/09, se
ela desfazia algo dos PRs #4, #5 e #6: só reescritas — as cores da confiança
migrando para `ui/tema.py`, o gancho da poda da F123 mudando de lugar sem se
desligar, o `_juntar` do `pdf_nativo` refeito. Nada revertido.

Os sete worktrees em `.claude/worktrees/` agravam: todos mesclados em `master`,
cada um com um ou dois arquivos editados e esquecidos.

### P1. O mojibake voltou, e o fim de linha está sem contrato

Dez módulos e dois documentos voltaram a trazer acentos em dupla codificação — o `á`
gravado como `Ã` seguido de `¡`: `core/corpus_planejamento.py`,
`core/editor/relatorios.py`, `core/editorial_pipeline.py`,
`core/editorial_suspeitas.py`, `core/ocr_phase3.py`, `core/ocr_phase7.py`,
`core/ocr_runtime.py`, `core/ocr_training.py`, `scripts/empacotar_modelo.py`,
`scripts/planejar_corpus.py`, `docs/OPERATIONS.md` e
`docs/ROADMAP_IMPLEMENTACAO_OCR.md`. A causa segue a mesma: a outra ferramenta
grava em cp1252. Recontados no item 2 com o crivo completo de
`scripts/conferir_codificacao.py`, eram dezenove arquivos — entre os que o grep da
análise não cobriu, `ui/main_window.py`, `scripts/preparar_fase7.py`,
`scripts/treinar_ocr_linhas.py`, `scripts/rodada_do_corpus.py` e dois testes.

Oito arquivos misturam CRLF e LF, `core.autocrlf` está ligado e não há
`.gitattributes`: cada `git diff` emite cem avisos e a próxima gravação vai trocar
o fim de linha de 120 arquivos.

### P1. Três objetos-deus e dezessete ciclos de importação

| Objeto | Tamanho |
|---|---|
| `MainWindow` (`ui/main_window.py`) | 5358 linhas, 170 métodos, importa 53 módulos do projeto |
| `TextoRico` (`ui/editor/texto_rico.py`) | 3378 linhas, 202 métodos |
| `JanelaDoEditor` (`ui/editor/janela.py`) | 2772 linhas, 175 métodos |
| `livro.extrair_pagina` | 397 linhas |
| `ocr_training.treinar_pacote` | 397 linhas |
| `MainWindow.exportar_livro_action` | 271 linhas |

`docs/ARCHITECTURE.md` descreve controladores extraídos da janela numa "fase 2",
mas a janela não encolheu desde então. Os ciclos diretos que mais pesam: `livro`
com `pdf_nativo` e com `negrito`; `editorial_legacy` com `editorial_pipeline`;
`ui/editor/dialogos.py` com seis módulos vizinhos; `ui/editor/janela.py` com
`operacoes.py`.

### P1. A biblioteca paralela ainda custa três mil linhas

A poda de 23/09 tirou cinco módulos, mas `ocr_phase3`, `ocr_phase4`, `ocr_layout`,
`ocr_structure` e `abbyy_ocr` seguem no pacote de produção, e a própria tabela do
roadmap diz por que não são produção. `ocr_structure` e `abbyy_ocr` não têm nenhum
importador fora dos testes.

Há três escritores de EPUB e DOCX: `core/exportar.py` na produção,
`core/editorial_export.py` na biblioteca e `core/editor/{epub,docx_io}.py` no
editor de livros. `tests/test_aceitacao_formatos.py` garante a mesma sequência de
blocos nos quatro formatos, mas são três lugares para cada correção de formato.

Os nomes por fase (`ocr_phase3/4/7/8`, `ocr14`, `editorial_legacy`) escondem a
responsabilidade do módulo.

### P2. Falhas silenciosas sem rastro

123 blocos `except ... pass` e 88 `except Exception`, concentrados em
`ui/editor/texto_rico.py` (16) e `ui/editor/janela.py` (12). Boa parte é guarda de
`TclError` em callback, legítima. O problema é que `core` não tem uma única chamada
de logging, enquanto a interface tem catorze; é nessa classe de supressão que o
"Exportar travando" da F119 se escondeu. O painel Mensagens do editor já ecoa o
logger `pyboxeditor.editor`, então a infraestrutura existe.

### P2. Testes largos, rápidos e com buracos conhecidos

A suíte é um ativo: verde em três versões de Python, o teste mais lento leva 17 s.
Mas onze módulos não aparecem em teste nenhum, oito deles do editor:
`ui/editor/operacoes.py` (1108 linhas), `dialogos.py`, `xadrez.py`, `original.py`,
`buscas_salvas.py`, `pdf.py`, `abas.py`, `proxy.py`, mais `core/relatorio_pdf.py`,
`ui/paleta_de_simbolos.py` e `core/ocr_rotulo.py`. Os marcadores `unit`,
`integration`, `ml` e `export` estão declarados em `pyproject.toml` e nunca usados.
Não há ferramenta de cobertura instalada. Um aviso de depreciação do Pillow
(`Image.getdata`, remoção em 2027-10) já aparece na suíte.

### P2. Higiene do repositório

Os 43 scripts da raiz são rastreados e somam 15 mil linhas fora de `scripts/`. A
raiz acumulava catorze PNGs de análise, seis logs de pytest e cinco cópias do
modelo; `build/` e `dist/` ocupam 2,6 GB em disco. O roadmap de 783 KB num arquivo
só grava um blob novo a cada edição. Não existe `README.md`, nem `CLAUDE.md` ou
`AGENTS.md`, e `docs/ARCHITECTURE.md` é anterior ao editor e ao pipeline editorial.

### P3. Segurança e reprodutibilidade, para um app desktop

Está bem: nenhum `shell=True`, todo `torch.load` com `weights_only`, subprocessos
por lista e com prazo onde importa; os caminhos Windows fixos são só candidatos de
Tesseract, ABBYY e fontes. Dois pontos a vigiar: não há lock de dependências, só
pisos de versão, e os limiares do modelo foram medidos contra versões específicas;
e o app roda no Python do sistema com torch 2.14 enquanto a suíte roda no `.venv`
com torch 2.10.

## O que fazer, nesta ordem

1. **Commitar a árvore em fatias**, seguindo a segmentação que a revisão já fez:
   §4.11, §4.12, §4.13, §4.14, F125, corpus v2 e as amostras. Dar push para a CI
   rodar no Linux. Depois esvaziar ou commitar os sete worktrees.
2. **Fechar a porta da codificação**: corrigir os doze arquivos, criar
   `.gitattributes` com `text=auto`, renormalizar uma vez e adicionar um teste que
   falha com mojibake ou byte fora de UTF-8 em arquivo rastreado.
3. **Escrever a porta de entrada**: um `README.md` com os três fluxos e um
   `CLAUDE.md` com as regras operacionais (testar no `.venv`, rodar o app pelo
   Python do sistema, não editar com a suíte rodando). Refazer `ARCHITECTURE.md`.
4. **Decidir a biblioteca**: apagar `ocr_structure` e `abbyy_ocr`, mover o resto
   para um pacote com nome de laboratório ou renomear por responsabilidade, e
   eleger um escritor canônico de EPUB — a recomendação é o do editor de livros,
   porque o caminho do PDF já termina nele.
5. **Logging em `core`**, começando pelos blocos silenciosos da exportação e do OCR.
6. **Dividir a janela principal por fluxo**, como o editor já faz com `menus.py` e
   `operacoes.py`, e quebrar o ciclo entre `livro` e `pdf_nativo`.
7. **Medir cobertura uma vez** e testar os oito módulos do editor pelos menus que
   os chamam.
8. **Arrumar a raiz**: scripts de medida para `scripts/medidas/`, lixo no
   `.gitignore`, roadmap fechado para `docs/historico/`.

## Evidência

**Conferida:** `git status`, `log`, `blame` e `worktree list`; `pyproject.toml`,
`.github/workflows/ci.yml` e `.gitignore`; mapa de módulos e grafo de importações
por AST; `ruff`, `compileall` e a suíte completa sem os lentos; as seis últimas
execuções da CI no GitHub; `docs/REVISAO_MODOS_OCR.md`,
`docs/ROADMAP_IMPLEMENTACAO_OCR.md`, `docs/OPERATIONS.md`, `docs/SETUP.md`,
`CONTEXT.md` e `docs/ARCHITECTURE.md`.

**Que falta:** número de cobertura, os 18 testes lentos, o bundle desktop
reconstruído e executado, e qualquer rodada em Linux fora da CI.

## Fechamento do item 1 (2026-10-06, mesmo dia)

A árvore foi ao git em doze commits no `master`, na ordem de dependência e seguindo a
segmentação da revisão. Cada fatia foi conferida antes do commit numa exportação limpa do
índice (`git write-tree` + `git archive`): `compileall`, `ruff` e a coleta do pytest, sem
o modelo `.pth`, sem o trabalho alheio e sem arquivos sem rastreio — a condição da CI.

| # | commit | o que leva |
|---|---|---|
| 1 | `21a7985` | A janela principal (§4.12): Exibir, estado persistente, trabalho fora da thread do Tk, `ui/tema.py`, caminhos do treino de linhas em `config.paths` |
| 2 | `a8ba133` | Corpus v2 com holdout isolado, candidatos, fila de conferência e promoção; portões de proveniência do treino de linhas, da OCR-14 e do pacote de pesos; gate estrutural do documento editorial |
| 3 | `689b573` | A poda (§4.11): os cinco módulos e os dezenove testes saem; `ocr_layout` e os docs dizem o que é biblioteca |
| 4 | `d7dd707` | O núcleo: PD-01, 02, 03, 06, 07, 09, 13, 14 e 20, o lado a jogar pela legalidade, os defeitos do item 10 em `editorial_export`, o `<pre>` da F120 e a data UTC do zip em `exportar.py` |
| 5 | `2dc759c` | Os testes de aceitação do item 10 (§4.13) |
| 6 | `c80e46a` | F120 e F122 no editor e na fonte: o `<pre>`, a moldura em glifo, a SkakNew-Diagram com 24 glifos de borda e a original guardada |
| 7 | `52937f6` | §4.14 e o resto da poda: fallback de engine, poda do cache nas duas rotas, ensemble opt-in por consenso, `processar_editorial.py` pelo leitor de produção, docs de revisão e roadmap da implementação |
| 8 | `8f102f4` | A paleta compacta de símbolos nas janelas de rotulagem e de revisão de linhas |
| 9 | `15dd8c0` | F125: o bundle desktop (`pyboxeditor.spec`, extra `[desktop]`, verificador), `data-files` do wheel, `tests/__init__.py` |
| 10 | `b36ca2c` | As amostras: 640 casas de ocupação, 221 peças de diagrama e a base de linhas com 1.301 linhas transcritas |
| 11 | (o seguinte) | O conserto do que a rodada limpa achou: os testes do corpus real pulam sem os PDFs-fonte, e o wheel constrói num clone limpo (`setup.py` no lugar do `data-files` estático) |
| 12 | (o último) | Este documento |

Os commits intermediários são coerentes em importação e coleta, mas não são
individualmente verdes na suíte inteira: arquivos que misturavam temas (o `exportar.py`
com F120 e PD, a fachada com poda e §4.14) foram para a fatia que mais os descreve, e as
mensagens dizem o que cada um carrega de outro tema. O estado final é o que a CI testa.

**Ficou fora, de propósito**, e continua na árvore sem rastreio: `fonts/AlphaDia.otf` e
`fonts/SkakNew-DiagramT.otf` (nada os referencia); os JSONs de estado do treino na raiz
(`text_line_model*.json`, `ocr_language_model.json`, `ocr_training_state.json`,
`text_line_training_report.*`), que são saída de treino sem o `.pth` que os acompanha; os
PNGs de análise e os logs de pytest da raiz; `_tmp_sintetico/`; os três PDFs-fonte de
`benchmarks/corpus_v2/source/` e a base sintética de linhas, agora no `.gitignore`; e o
par `Box/A Matter of Endgame Technique – Jacob Aagaard_pg100.{box,png}` de 17/09, uma
página rotulada à mão que nenhum manifesto referencia — decisão do usuário.

**Worktrees.** Quatro guardavam só o que já estava no `master` (medido linha a linha e
teste a teste) e foram removidos com os seus branches: `angry-bell` (o conftest fora do
AppData), `beautiful-grothendieck` (o zip em UTC), `dreamy-maxwell` (a gravura como
figura) e `elegant-napier` (a F121). A pasta vazia do `dreamy-maxwell` resistiu ao
apagamento por estar em uso por outro processo. Três ficam, porque têm trabalho que não
está no `master`:

- `dazzling-fermat` (base `86eab95`): `importar_ir._nome_de_arquivo`, o nome de recurso
  do EPUB sem acento nem espaço (PKG-010 do epubcheck) e sem colisão, com o teste;
- `sleepy-newton` (base `2b15aad`): a substituição casa a casa do `chess_pdf_processor`
  — o span conta pelo centro, o tabuleiro do Dvoretsky não é substituído — com
  `tests/test_substituicao_diagrama_casa_a_casa.py` (7 testes);
- `zealous-stonebraker` (base `3f03204`, de agosto): `folder_to_char(strict=True)` em
  `core/learner.py` recusando o nome de pasta que não fecha a ida e volta, com testes
  em `test_f14_dataset.py`. O `.git` dele pertence a Administrators e o git recusa
  abri-lo sem `safe.directory`.

**A suíte antes do push**, numa exportação limpa do `HEAD` em `b36ca2c` (`git archive`,
sem o modelo `.pth`, sem a árvore, sem arquivos sem rastreio):

| passo | resultado |
|---|---|
| `-m "not slow"` | 3489 verdes, 20 pulados, 2 vermelhos, em 4 min 29 s |
| `-m "slow and not gui"` | 9 verdes, 8 pulados, 1 vermelho |

Os três vermelhos eram da própria série, e a CI os pegaria. Os dois de
`test_corpus_v2_real.py` liam os PDFs-fonte que ficaram fora do git. O do wheel caía no
`[tool.setuptools.data-files]` da F125, que lista modelos ausentes num clone limpo
(`can't copy 'custom_model.pth'`) — o que derrubaria também o passo "Build wheel" da CI.
O commit 11 faz os dois testes pularem sem os PDFs e troca a seção estática por um
`setup.py` que só leva ao wheel os modelos que existirem. Conferido na mesma exportação:
o wheel constrói (209 arquivos, só o `model_meta.json` em `share/PyBoxEditor`, os três
recursos que a CI exige presentes) e o teste lento da instalação passa em 12 s; na árvore
o wheel leva os cinco modelos e os 14 testes ligados passam. O resultado da CI do push
fica no run do `master` no GitHub: verde nas três versões de Python (run 37551557492).

## Fechamento dos itens 2 e 3 (2026-10-06, à noite)

**Item 2, a codificação.** O crivo completo (`scripts/conferir_codificacao.py`) recontou o
mojibake: dezesseis arquivos, não doze — o grep da análise não cobria `ui/main_window.py`
(as mensagens do portão do treino), `scripts/preparar_fase7.py`, `treinar_ocr_linhas.py`,
`rodada_do_corpus.py` e dois testes. Tudo era dupla codificação reversível: nenhuma
sequência passou pelos cinco bytes que o cp1252 não tem, e `texto.encode("cp1252")
.decode("utf-8")` devolveu o original trecho a trecho. Saíram também o BOM de dois testes
e o CP850 do `fonts/LEEME__D.TXT`, que passou a UTF-8. Três ocorrências eram legítimas — o
relatório do editor detecta mojibake no texto de um livro e o explica com exemplos — e
ganharam o marcador `mojibake intencional` na linha, que o verificador respeita.
`tests/test_codificacao.py` roda sobre todo arquivo de texto rastreado (646) e falha com
byte fora de UTF-8, BOM ou mojibake; os testes unitários provam que cada defeito é pego e
que acentos, travessão, `≤`, `⩲` e `♘` passam intactos (`27b32c2`).

O fim de linha ganhou contrato: `.gitattributes` com `* text=auto eol=lf` e os binários
declarados (`f2d2933`). Os blobs já eram LF — `git ls-files --eol` não acha nenhum
`i/crlf` nem `i/mixed` —, então o commit não gera ruído no `git blame`; os 161 arquivos de
texto com CRLF ou mistos na árvore foram reescritos em LF no disco, e os cem avisos de
"LF will be replaced by CRLF" sumiram.

**Item 3, a porta de entrada.** `README.md` (os três fluxos, instalar, testar, o que está
medido, onde está o quê, os documentos), `CLAUDE.md` (as regras de quem trabalha aqui,
antes só na memória de uma sessão) e `docs/ARCHITECTURE.md` refeito (camadas, caminho de
produção, biblioteca de inspeção, o percurso de uma exportação, fronteiras, dívidas), em
`f8f3dc1`. O crivo pegou, em seguida, os exemplos literais nos docstrings do próprio
verificador e do teste, que ficaram rastreados e passaram a ser lidos; viraram descrição
(`79e66d2`).

**A suíte depois dos dois itens**, na árvore: 3516 verdes e três vermelhos, todos
consequência do próprio trabalho. Um era o crivo acusando os seus exemplos literais. Os
outros dois eram `tests/test_corpus_v2_real.py`: "hash do corpus não corresponde aos
arquivos declarados". `CorpusManifest.digest` é um SHA-256 dos bytes de cada arquivo
declarado, e o hash de 26/09 foi calculado na árvore Windows com as quatro predições em
CRLF; ao reescrevê-las em LF, a identidade do corpus mudou — e com ela a validade das
rodadas gravadas em `benchmarks/rodadas/`, o baseline com que `rodada_do_corpus.py
--comparar-com` se recusa a comparar outro corpus. Re-congelar o manifesto desfaria as
rodadas; o protocolo de benchmark é imutável por definição. Os artefatos passam a ser
guardados byte a byte (`benchmarks/** -text`), e as quatro predições voltam aos bytes
exatos que o hash conhece, no Windows e na CI — o que torna a medição reproduzível fora do
Windows, onde antes as predições saíam em LF (`3f24462`). Depois disso, os 69 testes do
corpus, do holdout, do benchmark, do pacote e da codificação passam.

Lição para o item 2 em geral: um hash sobre bytes de arquivo de texto é também um hash
sobre o fim de linha; o que está congelado por hash não se normaliza.

Push feito a pedido (`3932c92..5947aa4`); CI verde nas três versões (run 37556667777).

## Fechamento do item 4 (2026-10-06, à noite)

**A biblioteca tem um lugar com nome.** `core/biblioteca/` recebe `ocr_phase3`,
`ocr_phase4`, `ocr_layout` e `abbyy_ocr`; o docstring do pacote diz o que cada um é e por
que não é produção. O `abbyy_ocr` foi movido em vez de apagado — a §4.11 da revisão o
manteve de propósito, por ser integração com um programa instalado — e o `ocr_structure`,
que só o seu teste alcançava, saiu com o teste. Vinte e sete trocas de import em código,
testes e documentos, `core.biblioteca` na lista de pacotes do `pyproject.toml`, nenhuma
referência antiga sobrando, suíte 3512 verdes (`e6f9ec2`).

**O escritor canônico: a recomendação da análise ficou superada por uma decisão medida.**
A ED-12 (registro de 2026-09-21) já tinha medido os dois escritores e decidido
**convive**, com razão: `core/exportar.py` é a primeira saída do OCR, direto das
`PaginaExtraida`, e é o que a fila de revisão regrava; `core/editor/` faz o que o histórico
não faz. A medição de hoje (`medir_editor_vs_exportar.py --sintetico --paginas 30
--repeticoes 3`) repete a dela: EPUB em 15 ms e 172 KB pelo histórico contra 30 ms e 48 KB
pelo editor; DOCX em 260 ms contra 745 ms. O que sobra é o terceiro escritor,
`editorial_export._epub`/`_docx`, que só a biblioteca usa e é o único com o sinal "não
revisado" do diagrama que a §4.6 pinou como aceite; dobrá-lo sobre o `exportar.py` pela
volta sem perdas do IR é a simplificação certa, mas só depois que esse sinal chegar lá.
Ficou registrado como **PD-21** em `docs/ROADMAP_PENDENCIAS.md`, com a medição, a ordem
das entregas e o aceite; `docs/ARCHITECTURE.md` e `CLAUDE.md` dizem quem é dono de quê.

Duas lições de ferramenta, anotadas no `CLAUDE.md`: um script Python que regrava texto no
Windows abre com `newline="\n"`, senão o modo texto devolve CRLF e desfaz a normalização;
e a normalização de fim de linha da árvore não pode passar pelo que está `-text` no
`.gitattributes` — as predições do corpus voltaram do commit depois de um passe
descuidado.

Push a pedido (`5947aa4..7a3f451`); CI verde nas três versões (run 37559150682).

## Fechamento dos itens 5 e 6 (2026-10-06, à noite)

**Item 5, o log.** `core/log.py` é o tronco `pyboxeditor`: `logger(__name__)` dá o logger
do módulo, e os do editor (`core.editor.*`, `ui.editor.*`) entram sob `pyboxeditor.editor`,
que o painel Mensagens ecoa; `configurar()` pendura o arquivo rotativo `pyboxeditor.log` na
pasta de dados, e o `appy.main` o chama antes de abrir a janela ou o editor, registrando
também a exceção de callback do Tk e o erro fatal. Dos 302 `except` de `core`, 27 com
`pass` e 75 amplos, os 46 que engoliam em silêncio — e não reportavam por relatório, fila
ou retorno — ganharam a linha no nível certo: WARNING quando a saída mudou sem o usuário
saber, INFO para a degradação esperada, DEBUG para quem depura; `uma_vez` para o aviso que
sairia a cada parágrafo. Os cinco `print` de `core` viraram log. `tests/test_log.py` pina
a convenção e recusa `print` e logger fora do tronco em `core`. Suíte: 3518 verdes
(`cea30d6`).

**Item 6, a forma.** O modelo da página saiu de `livro.py` para `core/pagina.py` (seis
trechos, 267 linhas), com `livro` re-exportando e `pdf_nativo` tomando o modelo de lá (38
usos pelo nome) — a metade do maior ciclo (`54cfcc5`). O fluxo de exportar saiu da janela
para `ui/exportacao.py`: a classe `Exportacao`, oito métodos, 644 linhas, delegados com o
mesmo nome; a janela foi de 5.703 para 5.105 linhas, e o único teste que mudou lê a fonte
pela classe nova (commit seguinte). O que falta — boxes e reconhecimento, documento e
navegação, treino, o menu em tabela, a outra metade do ciclo — está na **PD-22** com o
tamanho de cada parte e o padrão a seguir.

Três lições do script de extração, que viraram regra do padrão na PD-22: a regex de `self.`
não cobre `getattr(self, …)` nem o `self` passado como pai de um diálogo, e os quatro casos
derrubaram a fila de revisão nos testes até virarem `self.janela`; a troca em bloco não pode
entrar numa classe aninhada no método, cujo `self` é dela — o `Token` de cancelamento ficou
com `self.janela.cancelled` e derrubou três testes do documento editorial; e um detector de
globais por nome confundiu a variável local `fontes` com o módulo `ui.fontes` — o `ruff`
acusou. A suíte inteira com os dois movimentos: 3515 verdes e as três do `Token`, que
passam depois do conserto; a confirmação em exportação limpa fica para antes do push.
