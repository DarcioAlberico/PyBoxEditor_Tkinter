# Roadmap — Revisão geral 2

Versão: 0.6 (veredito dos críticos e cinco re-análises aplicados)
Data: 2026-11-20
Base: `master` em `6627e30`
Spec: [SPEC_REVISAO_GERAL_2.md](SPEC_REVISAO_GERAL_2.md) (requisitos `R-nn`; veredito na §7)

As fases usam o prefixo `RG-` para não colidir com `F`, `ED-`, `OCR-` e `PD-`. Os
requisitos recusados (R-35, R-45) não têm fase; o antigo R-47 é a lista de decisões da
§10 da spec. As `PD-nn` que esta revisão abrir vão para o
[`ROADMAP_PENDENCIAS.md`](ROADMAP_PENDENCIAS.md), no formato da tabela de lá (citando a
fase RG e o requisito), com o próximo número livre conferido na hora do commit, não na
hora de escrever; se o usuário usar o mesmo número, o dele fica e o nosso vai para o
próximo.

## A ordem

0. **Antes da RG-01, um commit só com esta spec, este roadmap e a lista de documentos do
   `README.md` (`:92-103`) com os dois** (quando o usuário aprovar): sem ele, um worktree
   em `HEAD` não tem os documentos nem o registro. A base das fases passa a ser esse
   commit, e nele se tira a contagem de base da suíte do AbbyChessCraft (passo 10).
1. **Primeiro o que torna confiável a prova de todas as outras** (Onda 0): enquanto um
   teste passar sem medir e o wheel sair incompleto com a CI verde, nenhuma fase seguinte
   prova nada.
2. **Depois as funções únicas que várias fases usam** (Onda 1): a escrita atômica serve à
   Onda 2 e a todo gravador que vier depois; o caminho seguro e os tetos ficam aqui
   também porque o R-05 é de severidade alta e a `dados_de` do EPUB é comum com a RG-06.
3. **Depois por dano**, pela severidade da spec: perda do dado do usuário (Ondas 2, 3 e
   4), saída errada calada (Ondas 5, 6 e 7), o resto (Onda 8). Dentro de um mesmo dano,
   vem antes a fase de que outras dependem.

Toda fase depende da RG-01 e da RG-02a; a RG-01b e a RG-02b não bloqueiam nenhuma.

## Como uma fase fecha

1. O teste que falha hoje é escrito primeiro e falha pelo motivo do requisito.
2. A menor mudança que o faz passar; a função única antes dos chamadores. Uma fase pode
   fechar em vários commits — um por requisito, na ordem que a fase diz —, cada um com a
   suíte verde e `Suíte: N passed`. A invariante e o termo do glossário que a fase torna
   verdade entram no `CONTEXT.md` no commit dela (I-17 na RG-03, I-18 na RG-04, I-19 na
   RG-07, I-20 na RG-10; cada termo com a fase que o usa), e o parágrafo do gate no
   `CLAUDE.md` muda no mesmo commit que muda o gate (RG-01, RG-01b, RG-02a, RG-02b); a
   RG-19 só confere.
3. Quando a fase abre uma função grande, o comportamento dela é fixado por teste antes
   de mexer (princípio 6 da spec).
4. `compileall`; `ruff check core ui appy.py config scripts` (e `tests`, a partir da
   RG-01); a suíte `-m "not slow"` (5–7 min) e o `-m "slow and not gui"` (~25 s) no
   `.venv` — sem editar arquivo enquanto ela roda. Durante a fase, só os testes do arquivo
   (`-p no:cacheprovider`); a suíte inteira no commit; a da exportação limpa só antes de
   push.
5. Fases que mexem na leitura — a Onda 6 inteira, a RG-02a (as raízes de `config.paths`
   resolvem `core/dados`) e a RG-18 (`core/vertical.py`, `ocr_service.py`) — medem antes
   da primeira edição e no commit (~3 min as duas pontas), com os PDFs do manifesto
   (`benchmarks/corpus_v2/source/{aagaard,nunn,yusupov}.pdf`; do Yusupov, o
   `editable.pdf` do corpus, não o "mapeamento corrigido"):
   - **portão**: `scripts/rodada_do_corpus.py --comparar-com <rodada da base> --rotulo
     RG-nn` sai 0; rodadas de tentativa com `--rodadas preview_ocr/ab/rodadas`, e só a
     que fecha a fase vai para `benchmarks/rodadas/` e entra no commit;
   - **identidade** (onde a fase não deve mudar o texto): `scripts/ab_ocr_livro.py <pdf>
     --modos palavra --paginas … --referencia … --saida preview_ocr/ab/RG-nn-antes` e
     `…-depois` em cada um dos três PDFs, e `git diff --no-index` das duas pastas sem
     diferença;
   - num worktree, `--manifesto` com o caminho absoluto do `benchmarks/corpus_v2.json` da
     árvore principal e o PDF do A/B também pelo caminho absoluto (as fontes e os PDFs são
     ignorados pelo git e não existem no worktree);
   - **sem piora** = nenhuma página do corpus sobe mais que 0,1 ponto de CER e o total
     também não (a regra do `portao_do_modelo.comparar`, não só a página a página do
     `--comparar-com`), contra **duas** rodadas — a do commit de base da fase e a da base
     da revisão (`benchmarks/rodadas/2026-11-19-1805.json`, ou a que o commit dos
     documentos registrar) —, para que a folga não se acumule entre fases; e, no A/B,
     nenhuma das quatro páginas sobe de CER (tolerância zero). **Idêntico** = `git diff
     --no-index` vazio, depois de o "antes" rodado duas vezes sair igual a si mesmo
     (senão, registrar o que varia e comparar o resto);
   - **se piora**: a mudança que piora não entra; uma rodada de diagnóstico, no máximo; se
     a piora vem de rótulo errado da referência (o molde da PD-19), registrar a prova e
     perguntar ao usuário, sem corrigir a referência; senão, a edição sai e o registro diz
     "medido e recusado", com os números — o molde da F119 (o teto da F118 reprovado) e
     da PD-16 (o retreino de 11-09 recusado). Nunca se afrouxa a tolerância nem se regrava
     golden ou referência para passar;
   - se a base muda no meio da fase (o usuário commita em `core/livro.py` ou troca o peso
     — `model_meta.json` com `treinado_em` novo), o "antes" é refeito sobre a base nova
     depois do `rebase`: medida de outro commit ou de outro peso não compara.
6. Tempo se mede com a máquina quieta, nunca com uma suíte rodando ao lado.
7. O registro da fase (no fim deste arquivo) é aberto no primeiro commit dela e
   atualizado a cada commit: estado (`em andamento`, `fechada`, `parada: motivo`,
   `transferida: PD-nn`), commit de base, worktree, onde estão as medidas de antes,
   commits feitos e próximo passo. Medida nunca no diretório temporário da sessão.
8. Commit no `master` com `git add` de caminhos explícitos; mensagem no molde da casa.
   Fase que corre em paralelo com outra vai num worktree próprio (com
   `custom_model.pth`, `text_line_model.pth` e `text_line_model.json` copiados, e o
   `model_meta.json` também se `git diff --quiet model_meta.json` acusar diferença; o
   `.venv` é o da árvore principal); a segunda a chegar faz `git rebase master`, roda a
   suíte de novo e só então `git merge --ff-only`. Push só a pedido; antes dele, a suíte
   numa exportação limpa do `HEAD`.
9. Fase que mexe em arquivo com diff do usuário na árvore (hoje `core/livro.py` e
   `docs/ROADMAP_OCR.md`) mede num worktree em `HEAD` e entra no `master` montando o
   índice à mão (`git hash-object -w` da versão do `HEAD` com o patch da fase e
   `git update-index --cacheinfo`), sem tocar no diff dele. Fase da Onda 6 acrescenta ao
   `ROADMAP_OCR.md`, o diário de leitura dele, uma entrada curta com a rodada e o registro
   RG-nn, pelo mesmo índice montado à mão.
10. **O AbbyChessCraft.** Ele importa este `core` pela instalação editável do
    `C:\Python-Chess2\AbbyChessCraft\.venv`, que aponta a árvore principal: o que entra no
    `master` vale para ele na próxima abertura. As fases da tabela abaixo mexem no que ele
    chama; correm num worktree e, antes do `merge --ff-only`, rodam a suíte dele contra o
    `core` da fase — cwd em `C:\Python-Chess2\AbbyChessCraft`, `$env:PYTHONPATH =
    "<worktree>"`, `.venv\Scripts\python.exe -c "import core; print(core.__file__)"`
    apontando o worktree, e `.venv\Scripts\python.exe -m pytest -q -n 4 -p
    no:cacheprovider` (~1 min, com `test_contrato_do_core.py`, `test_privados_do_core.py`
    e `test_golden_exportacao.py`). A contagem dele vai ao registro, antes e depois, e o
    pronto de cada fase da tabela inclui a suíte dele verde contra a fase, com a mesma
    contagem. Falha dele não se conserta lá (este repositório não edita o
    AbbyChessCraft): a fase preserva o que ele usa (princípio 8 da spec), ou para e
    pergunta ao usuário. Golden dele nunca se regrava daqui.

| Fase | O que o AbbyChessCraft usa e a fase toca |
|---|---|
| RG-02a | a fonte de diagrama (`render_diagrama.carregar`), agora por `config.paths.recurso`; `projeto_dir()/"training_data"` montado à mão por ele (`leitor.py:63-65`): a `PYBOXEDITOR_TRAINING_DIR` não chega lá, e o registro diz isso; os tetos do R-08 admitem as versões do site-packages que ele usa (PyMuPDF 1.26.6, Pillow 12.0.0, python-docx 1.2.0) |
| RG-03 | `lexico._ler` (nome privado com contrato), no mesmo módulo que ganha a escrita atômica |
| RG-04 | o `OCRService` (R-48) |
| RG-05b | `LearningService._predictor` e `_get_learner` (nomes privados com contrato); `BoxService.split_box` e `clamp_box`, chamados pelo `editar_boxes.py` dele |
| RG-14 | `pdf_nativo.extrair`, `juntar_entre_paginas` (o invólucro dele depende de `seguinte.blocos[0] is primeiro` e do texto `fim + " " + começo`) e `lados_pelos_lances`; `PaginaExtraida` e `Paragrafo` montados por ele |
| RG-15 | `Paragrafo` com medidas montado por ele (a P-2 fica na suíte) |
| RG-16 | `pdf_nativo.amostrar` (decide a oferta da camada; o R-25 muda a amostra de 41 a 79 páginas) e o `OCRService` (confiança 0, grafema) |
| RG-20 | `BoxService.sort_boxes_reading_order` e `notacao.e_token_de_notacao` (mudam de lugar com delegado) |

## Desfazer uma fase

Desfazer é `git revert` dos commits da fase, nunca `reset` no `master` (o usuário commita
na mesma árvore; depois de push, só revert). Cada fase se desfaz sozinha, salvo:

- **RG-07**: o diário de nome novo some para o código revertido, que só procura
  `<saida>.review.jsonl` — antes de reverter, copiar o diário mais novo de cada saída para
  esse nome; o preferível é consertar para a frente;
- **RG-10 e RG-11**: rascunho e EPUB gravados com `extras` ou ids renumerados abrem no
  código velho sem o que ele não conhece (o `de_dict` do editor, `modelo.py:1190-1201`,
  ignora campo desconhecido): perda calada — reverter a RG-10 só junto com a RG-11, da
  última para a primeira, e avisar o usuário;
- **RG-02a**: a base de treino achada pela raiz do projeto, e não pelo cwd, recebe
  amostras que o código velho não vê se o app foi aberto de outra pasta.

Fase de que outra depende (tabela da visão geral) só se reverte com as dependentes, da
última para a primeira. Campo novo em formato persistido (rascunho, checkpoint, evento do
diário) tem padrão, e o pronto da RG-05, da RG-06, da RG-07 e da RG-10 inclui que o
rascunho, o checkpoint e o diário gravados na base abrem.

## Visão geral

| Onda | Fases | O que resolve | Depende de |
|---|---|---|---|
| 0 | RG-01 → RG-02a; RG-01b e RG-02b fora do caminho crítico | O gate vê o que deveria | o commit dos documentos |
| 1 | RG-03 → RG-04 | As funções únicas da fronteira | — |
| 2 | RG-05 ∥ RG-05b ∥ RG-06 | Preferências, rascunho, a imagem de origem, a base de treino, os boxes fora da página e o EPUB salvo | RG-03; a RG-06 também da RG-04 |
| 3 | RG-07 → RG-08 | O diário de revisão | RG-03 (o mesmo `editorial_model.py`); corre ao lado da Onda 2 |
| 4 | RG-09 → RG-10 → RG-11 | Fidelidade do editor | RG-04, RG-06 |
| 5 | RG-12 → RG-13 | Tarefa sobre estado vivo | a RG-13 também das RG-05, RG-05b e RG-06 |
| 6 | RG-14 → RG-15 → RG-16 → RG-16b | Leitura | o passo 9 enquanto o diff do usuário estiver em `core/livro.py`; só a RG-16b (cache do R-24 e R-23, no trecho do diff) espera o commit dele |
| 7 | RG-17 | Exportação editorial | RG-04, RG-07, RG-08, RG-14 |
| 8 | RG-18 ∥ RG-20, depois RG-19 | Silêncios, ortografia, documentos | a RG-18 das RG-13, RG-16 e RG-17 (não da RG-16b); a RG-19 por último |

Em paralelo (cada uma num worktree): a Onda 3 ao lado da Onda 2; a RG-05, a RG-05b e a
RG-06, cada uma ao lado das outras (a RG-05 e a RG-06 tocam ambas
`core/editor/projeto.py`, e o passo 8 cobre isso); a RG-18 ao lado da RG-20. A Onda 6 só
corre ao lado de outra onda num worktree, porque o A/B pede a árvore quieta. O resto é em
série.

Requisito → fase: R-38, R-40 → RG-01 · R-39 → RG-01b · R-08, R-41, R-43 → RG-02a · R-42 →
RG-02b · R-01 → RG-03 · R-05, R-06, R-07, R-48 → RG-04 · R-02, R-04, R-52, R-55 → RG-05 ·
R-53, R-54 → RG-05b · R-03, R-31 → RG-06 · R-09, R-10, R-11, R-12 → RG-07 · R-13 → RG-08 ·
R-27 → RG-09 · R-26, R-51 → RG-10 · R-28, R-29, R-30 → RG-11 · R-14, R-15 → RG-12 · R-16,
R-17, R-18, R-19 → RG-13 · R-20, R-21 → RG-14 · R-22 → RG-15 · R-24 (a trama), R-25 →
RG-16 · R-24 (o cache), R-23 → RG-16b · R-32, R-33, R-34, R-36 → RG-17 · R-37 → RG-18 ·
R-46 → RG-20 · R-44 → RG-19.

## Onda 0 — O gate vê o que deveria

Linux só se testa por push (esta máquina não tem WSL nem Docker); por isso o que depende
da CI fica na RG-02b, fora do caminho crítico.

### RG-01. Testes que não medem, pulam
- Requisitos: R-38, R-40.
- Entrega, em quatro commits: (1) os 29 `return` nus de 27 testes (11 por falta de dado,
  16 por falta de display) viram `pytest.skip` com motivo, e
  `tests/test_testes_honestos.py` recusa `return` nu antes da primeira asserção e fora de
  `except` num `test_*`; (2) as quatro asserções fracas conferem o valor que o nome
  promete, e o golden de `test_editor_xhtml.py:365` falha se ausente; (3)
  `--strict-markers` e `-ra` no `pytest.ini`, os quatro marcadores mortos e o bloco
  `[tool.pytest.ini_options]` fora, o piso do `epubcheck` igual no `pyproject.toml` e no
  `requirements-dev.txt`; (4) `ruff check tests` limpo (`--fix` para os 25 F401; ignore de
  E741 por arquivo onde o nome é deliberado; os 4 F841 e 2 E731 à mão), com o parágrafo
  do gate no `CLAUDE.md` no mesmo commit.
- Pronto quando: na exportação limpa os 11 testes de dado aparecem SKIPPED com motivo;
  os 16 de display aparecem SKIPPED num teste que força `_sem_display`/`TEM_DISPLAY` por
  `monkeypatch` (esta máquina e a CI têm display); o teste dos `return` está verde; as
  quatro asserções falham contra um objeto vazio do tipo certo;
  `pytest --strict-markers --collect-only` e `ruff check tests` sem erro.
- Risco: um teste que hoje "passa" pode falhar ao ganhar asserção — é achado, não
  regressão; registrar.

### RG-01b. Teste de comportamento, não de grafia
- Requisito: R-39. Fora do caminho crítico: o `getsource` dá falso vermelho, não falso
  verde.
- Entrega: a lista nominal congelada com os 19 testes de hoje e conferida por teste; a
  conversão para espião ou `monkeypatch` a partir de `test_f43_navegacao` e `test_f123`,
  cada teste convertido saindo da lista no mesmo commit; se a lista zerar, o mesmo commit
  tira do `CLAUDE.md` a regra de não editar com a suíte rodando.
- Pronto quando: a lista tem só os testes sem chamada observável, cada um com
  justificativa; a contagem (27 chamadas, 19 testes) registrada antes e depois.

### RG-02a. O que se distribui é o que se testa
- Requisitos: R-41, R-43, R-08. Depois da RG-01: as duas mexem em `pyproject.toml` e
  `requirements-dev.txt`.
- Entrega: `config/profiles/*.json` como package-data de `config`; as fontes listadas em
  `core/dados/fontes_de_diagrama.json` (mais as licenças) e `pieces/` como `data-files`,
  achadas por `config.paths.recurso(relativo)` nos três lugares que hoje usam `__file__`;
  `RECURSOS_OBRIGATORIOS` estendida, com a regra de árvore → nome no wheel;
  `config/profiles` no `pyboxeditor.spec` e no teste do spec; `config.paths` sem o cwd na
  frente das raízes, e `dado_do_projeto("training_data")` nos chamadores, sem o cwd na
  frente (o `test_caminhos_do_treino_de_linhas.py:55` muda junto);
  `PYBOXEDITOR_TRAINING_DIR`, fixada pelo `tests/conftest.py` num diretório temporário; no
  wheel, a base gravável fica na pasta de dados do usuário; a docstring de
  `tests/conftest.py:89` acompanha; teto de versão no PyMuPDF, no Pillow e no
  python-docx; `constraints.txt` das dependências declaradas; piso 3.11
  (`requires-python >= 3.11`, `target-version = "py311"`), com o parágrafo do gate no
  `CLAUDE.md` no mesmo commit; `weights_only=True` no `calibrar_modelo.py`.
- Pronto quando: na exportação limpa, `py -3.13 -m build --wheel --no-isolation` (o
  `.venv` não tem o pacote `build`), `py -3.13 -m venv --system-site-packages` num
  diretório de rascunho e `pip install --no-deps` do wheel; num cwd fora do projeto,
  `python -c` confere que `core.__file__` está no venv (o Python do sistema tem o
  projeto instalado em modo editável, que não pode ser o medido), que
  `render_diagrama.carregar` não levanta, que as peças carregam e que
  `perfis.carregar_todos()` não volta vazio; com `chdir` para outra pasta, a base certa é
  usada e `core/dados/*.pth` e `custom_model.pth` no cwd não sombreiam os do projeto
  (teste); a suíte não toca a base real; A/B idêntico; `py -3.11 -m compileall` limpo
  (prova o piso); a suíte do AbbyChessCraft verde contra a fase (passo 10).

### RG-02b. A CI roda o que a suíte tem
- Requisito: R-42, mais a linha do lint de `tests` (`ci.yml:37`) da RG-01 e o
  `-c constraints.txt` da RG-02a.
- Entrega: CI com `-c constraints.txt`, `epub-validacao`, `tesseract-ocr`, os testes
  `gui` sob Xvfb, `tests` no lint e o índice CPU do torch; o parágrafo do gate no
  `CLAUDE.md` no mesmo commit.
- Ao abrir, pede ao usuário a autorização para a série de pushes de prova (o conserto de
  CI já levou seis commits no PR #3, e o push leva junto os commits ainda locais — 8 em
  2026-11-20); sem ela, a fase fica aberta no registro e as outras seguem.
- Pronto quando: o run da CI fica registrado, verde nas versões da matriz, com os
  arquivos `gui` rodando e sem "epubcheck ausente" nem "tesseract ausente" no resumo de
  pulados (contagem de pulados antes e depois).
- Risco: o Tesseract do apt pode ler diferente nos oito testes.

## Onda 1 — As funções únicas da fronteira

### RG-03. Escrita atômica
- Requisito: R-01.
- Entrega: `gravar_atomico` e `escrita_atomica` num módulo do `core` (com `duravel`,
  nova tentativa do `os.replace` e modo de arquivo novo); a troca dos vinte e dois pontos
  listados na spec (o `formato_box` montando o texto antes de abrir) e dos três que já
  usam `mkstemp`; teste de interrupção no meio para cada um; teste por AST sobre `core`,
  `ui` e `config` que recusa o `.tmp` de nome fixo e o `mkstemp` fora do módulo, com lista
  nominal vazia; a I-17 no `CONTEXT.md`.
- Pronto quando: o teste de interrupção e o teste por AST estão verdes; o acréscimo do
  diário de revisão (`editorial_review.py:342`) é a exceção declarada no próprio teste; o
  tempo do rascunho do editor registrado antes e depois; a suíte do AbbyChessCraft verde
  contra a fase (passo 10, pelo `lexico`).

### RG-04. Caminho seguro, tetos, texto legal e TLS
- Requisitos: R-05, R-06, R-07, R-48, um commit cada, nesta ordem (o R-48 não toca os
  arquivos dos outros três). Depois da RG-03: as duas tocam `epub.py`, `html_io.py`
  (`escrever_pasta` grava pela escrita atômica) e `txt_io.py`.
- Entrega: `caminho_seguro(raiz, relativo)` usado na leitura do zip, na pasta HTML (pelo
  `nome_no_zip` relativo ao `commonpath` do livro, que mantém o leiaute de hoje) e em
  `_trazer_do_disco` (relativo de qualquer profundidade, sem absoluto, UNC nem letra de
  unidade, só extensões de recurso); tetos de pacote; `ParseError` → `ValueError`; OPF
  tolerante a entidades; `texto_legal_em_xml()`, pública, nos dois escritores e nos
  importadores, onde o texto vira nó XML; TXT com BOM UTF-16; o EasyOCR sem troca do
  contexto TLS, com trava no cache e a mensagem de como instalar os pesos à mão; a I-18
  no `CONTEXT.md`.
- Pronto quando: os cenários estão na suíte — `../../ESCAPOU.txt`; OPF em `OEBPS/opf/`
  com `../Text/` exportando dentro da pasta e o `test_editor_html.py:92-113` verde;
  entrada `..` no zip; HTML com `../img/a.png` (embute), com `../../x.txt` e com caminho
  absoluto (não embutem); DOCX de 300 MB de zeros; `ParseError`; OPF com `&nbsp;`; `\x0c`
  no EPUB e no DOCX do OCR e no EPUB do editor, com negrito e itálico no lugar; `\ud800`;
  UTF-16; contexto TLS não relaxado durante o download simulado (o
  `test_f16_easyocr.py:203` invertido); a suíte do AbbyChessCraft verde contra a fase
  (passo 10, pelo `OCRService`). A RG-10 reconfere `escrever_pasta` com a ida e volta.

## Onda 2 — O dado do usuário: janela, base de treino e EPUB salvo

### RG-05. Preferências, buscas salvas, rascunho e a imagem de origem
- Requisitos: R-52 primeiro (o mais grave da re-análise 4: regrava em cinza o scan
  original, sem pergunta), depois R-02, R-04 e R-55, um commit cada.
- Entrega: o PNG do par não é regravado quando é o próprio arquivo de origem
  (`samefile`, ou `normcase(realpath)`), nem listado como gravado; `Settings` distingue
  `OSError` de JSON inválido, guarda o inválido ao lado, e o `save()` mescla um nível
  abaixo quando os dois lados são dicionários (cobre os três gravadores da chave
  `editor`; o `test_fase9_settings_atomicos.py:69` muda junto); a busca salva ilegível é
  guardada como veio; ao abrir outro arquivo, o rascunho só sai quando a sessão nova
  existe, e ao fechar a janela sai no `destroy`; falhas de gravação do rascunho e de
  `remover_autosave` em WARNING; a falha do rascunho no fechamento do editor
  (`ui/editor/janela.py:2910`) loga e fecha; a página esvaziada conta como suja e salva
  vazia; o rascunho mais velho que o EPUB é oferecido com aviso; `Rascunho.restaurar`
  religa a ponte e avisa se não conseguir; o rascunho da janela principal grava
  `as_state()` e lê por `from_state`.
- Pronto quando: os testes do PNG colorido com dpi (bytes iguais depois do Ctrl+S e do
  "Salvar todas" de uma sessão de imagem, também com a origem `Pagina.PNG`) e da origem
  num PDF (o par sai inteiro); os cenários dos dois editores, do arquivo bloqueado, da
  busca ilegível e do seletor cancelado; a falha do gravador e a de `remover_autosave` em
  WARNING (`caplog`); o `OSError` no rascunho do editor que não impede o fechamento; a
  página esvaziada que sai como `.box` vazio; o rascunho mais velho que o EPUB oferecido
  com aviso; a ponte religada e os campos `negativo`, `moldura` e `margem` de volta depois
  da recuperação — tudo na suíte; o rascunho antigo, de oito campos, e as preferências
  gravados na base abrem.

### RG-05b. A base de treino e os boxes degenerados
- Requisitos: R-53, R-54, um commit cada. Corre ao lado da RG-05 (arquivos disjuntos:
  `core/learner.py`, `core/coleta.py`, `ui/treino.py`, `ui/canvas_view.py`,
  `core/vertical.py`, `core/services/box_service.py`,
  `core/services/learning_service.py`); passo 10.
- Entrega: o learner com a impressão digital da carga mais as amostras que ele gravou, e
  `salvar_cache` que não grava quando o disco diverge; a promoção pelo learner do serviço,
  salvando o cache e pulando o recorte repetido, com a contagem no `Promocao`;
  `recorte_de_pe` limitando o box à imagem e devolvendo vazio para o que sai dela; o
  aprendizado pulando recorte vazio e contando; o canvas limitando o box à imagem por um
  `clamp_box` que preserva todos os campos; `split_box` devolvendo o box inteiro, sem
  levantar, para largura menor que 2; o `release` fazendo commit só se as coordenadas
  mudaram.
- Pronto quando: os sete cenários da spec estão na suíte (os dois do R-53 e o do cache
  sem reler o disco; os cinco do R-54, com o box inteiro à esquerda da página, que não
  vira amostra); a suíte do AbbyChessCraft verde contra a fase.

### RG-06. O EPUB salvo é íntegro e o livro aberto não muda
- Requisitos: R-03, R-31. Depois da RG-04: o teto e o portão caem na mesma `dados_de`.
- Entrega: a montagem levanta dentro do `with escrita_atomica(...)` com a lista dos
  recursos do manifesto que não se leem, e o destino não muda; a opção explícita "salvar
  sem estes recursos"; o checkpoint (`projeto.py:239`) e a diferença (`:264`) pela mesma
  regra; o `Recurso` guarda o nome de origem no zip e `dados_de` lê por ele, o que cobre
  `renomear` e `renomear_varios`; o escritor trabalha numa cópia do livro.
- Pronto quando: os cenários da origem apagada (falha com a lista, e salva sem eles com a
  opção) e do renomear estão na suíte, e o de `marcos` e `ncx` do modelo antes e depois de
  gravar (com sucesso e com falha); o rascunho e o checkpoint gravados na base abrem.

## Onda 3 — O diário de revisão

### RG-07. Diário com identidade e transação
- Requisitos: R-09, R-10, R-11, R-12.
- Entrega: primeiro, num commit próprio, `scripts/medidas/medir_lote_de_revisao.py`
  (documento de 300 páginas × 12 blocos, 200 edições; grava o tempo e o documento final
  em JSON), rodado na base, com o tempo no registro desta fase; depois, leitura só por
  `\n` que pula a linha inválida com WARNING, e `\n` escrito antes de acrescentar se o
  arquivo não termina nele (sem truncar); `fsync` por lote; a identidade no nome
  (`<saida>.<sha12>.review.jsonl`) e `caminho_do_diario` procurando por ele, com o
  caminho guardado no JSON (`review_journal_path`) e no EPUB (`origem.diario`) seguindo a
  mesma regra; os três casos do `except` separados (truncado, outro documento, conflito
  de valor, este pela cadeia por alvo); o diário sem sha no nome lido antes do com sha e
  nunca escrito; `before_reason_codes`; `undo`/`batch:` reservados; lote validado antes;
  `aplicar_lote(eventos)` e a ponte com um lote por salvamento, sem evento para capítulo
  em modo código (com aviso) e descendo nos blocos aninhados com origem própria; a I-19
  no `CONTEXT.md`.
- Pronto quando: os cenários da spec estão na suíte (U+2028, linha truncada e evento
  seguinte lido, outro livro, mesmo livro com leitura diferente, a cadeia E1/E2, diário
  sem sha no nome com as correções dele ainda aplicadas, caminho guardado no JSON e no
  EPUB, desfazer com motivos, `reason_codes` reservados, lote com alvo inexistente,
  desfazer um salvamento inteiro, modo código, bloco aninhado); os sete testes que contam
  linhas do diário continuam verdes; o diário gravado na base abre, só para leitura. A
  abertura de uma cópia de um diário real do usuário é medida registrada, fora do pronto;
  em 2026-11-20 não há nenhum `*.review.jsonl` na máquina, e ela fica para quando houver.
- Risco: mudança de nome do diário — o leitor ainda abre o antigo, só para leitura; o
  escritor só grava no nome novo.

### RG-08. Aplicar em lote
- Requisito: R-13. Depois da RG-07, que muda `gravar_eventos`, `apply_batch` e
  `from_journal`.
- Entrega: aplicação de N eventos sobre uma cópia, com uma validação e ids num conjunto;
  a ponte relê só a cauda do diário a partir do último deslocamento que conhece.
- Pronto quando: o `medir_lote_de_revisao.py`, rodado no commit de abertura desta fase (o
  "antes" dela, já sobre a RG-07) e no de fechamento, na mesma máquina (o revisor mediu
  54,6 s na base), dá menos de 2 s, e os dois JSON do documento final são iguais byte a
  byte; o Ctrl+S com 200 eventos anteriores lê só a cauda e vê o evento que outro
  gravador acrescentou (testes), e o tempo dele, medido por script com `Projeto.salvar`
  sobre o livro do Dvoretsky convertido por `scripts/pdf_para_editor.py`
  (`--camada sempre`), fica registrado antes e depois.

## Onda 4 — Fidelidade do editor

### RG-09. O sumário acha as âncoras
- Requisito: R-27. Antes da RG-10, que aumenta o que vai para ilha.
- Entrega: índice de âncoras calculado na gravação, a partir do modelo (ids de bloco,
  ilhas, XHTML dos capítulos em modo código; os `extras` da RG-10 entram nele quando
  chegarem); entrada sem destino vira rótulo e mantém os filhos; sem regeneração sem
  aviso.
- Pronto quando: o nav com `<h2 id>` em ilha, `<a id>` inline e entrada sem `href` sai com
  as três; capítulo em modo código mantém as suas; a regeneração avisa.

### RG-10. Ida e volta sem perda silenciosa
- Requisitos: R-26, R-51.
- Ao abrir, o usuário indica a pasta e os livros do corpus (no mínimo dez, de pelo menos
  três produtores; há EPUBs de terceiros na máquina, mas escolhê-los é dele).
- Entrega, em seis commits: (1) `scripts/medidas/medir_ida_e_volta_epub.py` (atributos,
  elementos e arquivos perdidos por EPUB) e `config.paths.corpus_de_epubs()`, rodado
  antes (o script pula com aviso se a pasta não existe); (2) `extras` com `id`, `class`,
  `lang` e `dir` em lista, item, tabela, linha, célula, imagem, corpo e raiz, e o `media`
  do `<link>`, com o `class` fundido ao do dialeto e os ids no índice de âncoras e na
  deduplicação, e a I-20 no `CONTEXT.md`; (3) `extras` do pacote, ids do manifesto e
  atributos do `itemref`; (4) a codificação declarada honrada; (5) o R-51, com a §10.1 da
  `SPEC_EDITOR.md` atualizada; (6) o script rodado depois e `escrever_pasta` reconferida.
- Pronto quando: o teste `ler → escrever → ler` por atributo citado na spec e o de
  acessibilidade estão na suíte, e o `test_editor_epub_completo.py:146` continua verde; o
  rascunho gravado na base (sem `extras`) abre; a medida do corpus, antes e depois, está
  registrada; cada perda não declarada que sobrar é listada no registro com o requisito
  que a cobriria (vira uma `PD-nn`). "Declarada" é a perda que o relatório de conversão do
  editor já avisa ao usuário.

### RG-11. Ids, espinha, busca e notação
- Requisitos: R-28, R-29, R-30. Depois da RG-10: o `_ler_do_zip` e o `modelo.py` são
  tocados pelas duas.
- Entrega: deduplicação de ids e de espinha na leitura, com aviso; marca de página por
  número; quantificador pelo analisador do `re`; NFC com mapa de deslocamentos; desfazer
  no modo código; caixa por palavra através de trechos; aspa depois de NBSP; o percurso
  de tokens unificado, com a variante antes do primeiro lance pendendo dele; cabeçalho
  PGN numa linha.
- Pronto quando: os cenários da spec estão na suíte.

## Onda 5 — Tarefa sobre estado vivo

### RG-12. A tarefa loga e não aplica sobre o que mudou
- Requisitos: R-14, R-15.
- Entrega: log com traceback no `runner` de `BackgroundTask`; o preenchimento aplica por
  identidade aos boxes capturados no início; a detecção confere a posição do histórico e,
  se mudou, não aplica e avisa; "Salvar todas" com cópia, marcando salva só a página igual
  à cópia. A edição não é travada.
- Pronto quando: o teste com `caplog` da tarefa que levanta e os testes dirigidos de
  apagar durante "Preencher boxes", editar durante a detecção e editar durante "Salvar
  todas" estão na suíte; o teste do Ctrl+S de hoje
  (`test_trabalho_fora_da_interface.py:270-301`) continua verde.

### RG-13. Diálogos, fechamento e o editor
- Requisitos: R-16, R-17, R-18, R-19, um commit cada, nesta ordem. Depois das RG-05 (o
  contrato de `_confirm_discard` e o `_fechar_pelo_parent` do editor), RG-05b (o
  `ui/treino.py` e o `release` do canvas, que o R-19 também usa), RG-06 (a validação
  chama `epub.escrever`) e RG-12 (o `ui/reconhecimento.py` e o `ui/documento.py` que ela
  muda).
- Entrega: rotulagem e revisão editorial religam em todo desfecho, cancelam ao fechar e o
  modal tem o próprio Cancelar; `try/finally` na conclusão; fechar confirma antes de
  cancelar e espera a thread; `_motivo_de_espera()` como decisão única, usada pelo
  `_busy()` e pelo `_load_pdf_page` (aviso na barra de status, e o
  `test_f37_paginas.py:494` verde); `JanelaDoEditor.fechar` cancela os `after`; vigia
  resiliente; validação do EPUB em tarefa e pasta temporária removida; os quatro pequenos
  da janela principal.
- Pronto quando: abrir e fechar o editor embutido não gera `bgerror`; cada diálogo tem
  teste de falha e de fechamento no meio; os três testes do R-17, os quatro do R-19 e os
  da vigia, do cursor e do `mkdtemp` do R-18 estão na suíte.

## Onda 6 — Leitura (cada fase com A/B e corpus)

### RG-14. Passadas de livro num lugar
- Requisitos: R-20, R-21. Na árvore principal o A/B mediria junto o trabalho não
  commitado do usuário em `core/livro.py`: ao abrir a Onda 6, perguntar a ele se o
  commita; se não, a fase segue o passo 9 (worktree em `HEAD`, índice montado à mão).
- Entrega: `passadas_de_livro()`, pública, e o guarda por página nos dois caminhos,
  relançando o cancelamento e registrando a página com falha num campo que a conclusão e
  a fila mostram; `juntar_entre_paginas` e `lados_pelos_lances` com a mesma assinatura, e
  `-1` nos registros que vêm da página seguinte; a evidência do ensemble no registro da
  faixa, sem o atalho por `last_result`, e o motor chamado uma vez em
  `leitor_de_faixa_com_ensemble`.
- Pronto quando: os testes da página da camada e da página do OCR que levantam, do
  cancelamento no meio da página e da estatística do ensemble estão na suíte; A/B das
  quatro páginas e rodada do corpus registrados, sem piora (idênticos no que é do R-21);
  o Yusupov inteiro antes e depois, com parágrafos juntados, lados trocados por
  `lados_pelos_lances` e FEN 531/541 sem piora (é a medida das passadas entre páginas,
  que o A/B não vê); a suíte do AbbyChessCraft verde contra a fase (passo 10).

### RG-15. As medidas da linha acompanham o texto
- Requisito: R-22. Depois da RG-14, que mexe no mesmo `core/livro.py` (`extrair` e o
  invólucro da faixa), para que um A/B não contamine o outro; segue o passo 9 se o diff
  do usuário ainda estiver na árvore (as três passagens, em `livro.py:3238`, `:3363` e
  `:4192`, ficam fora do trecho dele, `livro.py:2326-2435`).
- Entrega: as três passagens com `_transferir_medidas`; pulo do negrito contado e logado;
  a propriedade P-2 conferida em toda passada pela suíte, nunca por `assert` no tipo.
- Pronto quando: os três cenários e a P-2 estão na suíte; A/B e corpus iguais ou
  melhores; negrito das páginas de referência medido antes e depois; a suíte do
  AbbyChessCraft verde contra a fase (passo 10).

### RG-16. A trama e os pequenos da leitura
- Requisitos: o R-24 na trama (`ocr_service.py`) e o R-25, em dois commits nesta ordem.
  Depois da RG-15.
- Entrega: (1) tabela de consulta por rótulo na trama, conferida byte a byte; (2) os seis
  pequenos, cada um com seu teste, e A/B onde mudam a saída.
- Pronto quando: saída byte a byte idêntica nas páginas de referência no commit (1), com
  o tempo antes e depois registrado — as quatro páginas e
  `scripts/ab_ocr_livro.py benchmarks/corpus_v2/source/yusupov.pdf --modos palavra
  --paginas 96` (o `tempo_s` do `relatorio.json`); os testes de (2) na suíte; A/B e corpus
  sem piora em (2); a suíte do AbbyChessCraft verde contra a fase (passo 10).

### RG-16b. O cache do corretor e o idioma
- Requisitos: o R-24 no cache do corretor e o R-23, em dois commits nesta ordem. Os dois
  caem no trecho do diff do usuário (`_corrigir_prosa_contextual`, `livro.py:2430`) e
  esperam o commit dele; nada depende desta fase.
- Entrega: (1) cache por `(palavra, idioma)`, conferido byte a byte; (2)
  `idioma_normalizado()`, remendos por idioma e o idioma em toda chamada.
- Pronto quando: saída idêntica e tempo por página antes e depois em (1); os testes de
  (2) na suíte, com A/B e corpus sem piora.

## Onda 7 — Exportação editorial

### RG-17. Uma ordem, revisão inteira
- Requisitos: R-32, R-33, R-34, R-36; primeiro o teste dos seis formatos, depois um
  commit por requisito, nesta ordem.
- Entrega: ordem decidida no `EditorialDocument` e seguida por `aplicar_revisao`; tabela
  irregular e vazia; título e idioma padrão; FEN, lado e orientação revisados aplicados
  (o lado sem redesenhar a figura); `revisao_pendente` pelo status; o mapa do lado com
  todas as origens (`"usuario"` incluída); `_bloco_de_volta` com
  `header`/`footer`/`caption`; a imagem da página com log e conferência pelo
  `source_sha256` da identidade (RG-07); `editorial_pipeline` indexado por `page_id`; uma
  só `ExportOptions`, com `paginas` revisadas, fixada por teste; `_faixas` num lugar.
- Pronto quando: os seis formatos na mesma ordem e os cenários da spec na suíte.

## Onda 8 — Silêncios, ortografia, documentos

### RG-18. Os silêncios que mudam a saída falam
- Requisito: R-37. Depois das RG-13, RG-16 e RG-17, que reescrevem parte do código da
  lista (`janela.py:2946`, `operacoes.py:709`, `original.py:156`, `ocr_service.py`,
  `_faixas`).
- Entrega: cada item da lista fechada loga pelo nível da regra e conta o que descartou;
  as capturas largas se estreitam; a varredura por AST de `ui` com lista nominal.
- Pronto quando: cada item que muda saída tem teste com `caplog`; a lista nominal tem só
  os handlers que a fase decide manter mudos, cada um justificado; a contagem de handlers
  é feita ao abrir e ao fechar a fase (17 em 2026-11-20: os 16 da lista do R-37 e o
  `ui/editor/xadrez.py:88`, que fica mudo); A/B idêntico (`vertical.py` e
  `ocr_service.py` estão na leitura).

### RG-20. A ortografia não puxa o OpenCV
- Requisito: R-46.
- Entrega: a ordenação de leitura num módulo leve, com delegado no `BoxService`; a
  `ortografia` importa `e_token_de_notacao` de `notacao`.
- Pronto quando: o teste de `sys.modules` está na suíte e a cópia saiu; a suíte do
  AbbyChessCraft verde contra a fase (passo 10).

### RG-19. Documentos
- Requisito: R-44. Por último, para descrever o estado final.
- Entrega: o CER pela última rodada registrada, com arquivo, data e hash do corpus; os
  nomes de classe reais; o `ARCHITECTURE.md` com os ciclos de hoje e os módulos novos; o
  docstring do `editorial_pipeline`; o `ROADMAP_PENDENCIAS.md` com as PD abertas pela
  revisão, as transferidas incluídas; o piso 3.11 em `README.md:8` e `docs/SETUP.md:5`;
  a exceção de cor do `ui/editor` no `CLAUDE.md`. Confere o parágrafo do gate (mudado nas
  RG-01, RG-01b, RG-02a e RG-02b), as invariantes 17 a 20 e o glossário no `CONTEXT.md`
  (entrados nas RG-03, RG-04, RG-07 e RG-10).
- Pronto quando: o teste dos caminhos citados nos documentos está na suíte; cada
  afirmação da lista do R-44 foi corrigida e conferida por `grep`; a linha de base da §2
  da spec foi re-medida e registrada.

## Quando a revisão fecha

A revisão fecha quando cada fase está `fechada` ou `transferida: PD-nn`. Uma fase que fica
`parada` à espera do usuário por duas ondas seguidas, ou ao chegar a vez da RG-19, é
transferida: o que falta vira uma `PD-nn` com o requisito, o que já entrou e o próximo
passo, e o registro dela diz `transferida: PD-nn`. As candidatas são a RG-16b, a RG-02b e
a RG-10 (se o corpus não vier); a medida do diário real, fora do pronto da RG-07, vira
`PD-nn` se não houver diário até a RG-19. A RG-19 roda sobre o que fechou e cita as
transferidas.

Fechar pede: a suíte numa exportação limpa do `HEAD` verde, com a contagem; a linha de
base da §2 da spec re-medida (suíte, pulados com motivo, `return` nus, wheel, cobertura,
CRAP) no registro da RG-19; a suíte do AbbyChessCraft (passo 10) verde; o push pedido ao
usuário (ele leva os commits locais), e a CI registrada se ele autorizar. Spec e roadmap
ganham "Estado: fechada em <data>" no cabeçalho e ficam em `docs/`.

## Registro

Uma subseção por fase, aberta no primeiro commit dela (passo 7 do fechamento): estado,
commit de base, worktree, onde estão as medidas de antes, commits, o que foi medido
antes e depois, a contagem da suíte e o próximo passo. Cada fase edita só a sua.

### Commit dos documentos
Estado: fechada. Commit `a2bfc82` (2026-11-20), com a lista de documentos do README; sem
push. Suíte da exportação limpa: 3640 passed, 22 skipped. Base do AbbyChessCraft (`91a4576`)
contra o `core` da árvore principal: 2915 passed, 6 failed, 3 skipped (97 s). Cinco das
falhas são de leiaute Qt dele (`test_espaco.py` ×4, `test_estilo.py`); a sexta,
`test_editar_boxes.py::test_dividir_empilhados_de_verdade_continua_no_eixo_do_core`, falha
também contra o `HEAD` limpo: o `split_box` daqui parte sempre lado a lado desde o `97e3d98`,
e ele conta com o corte de cima para baixo nos boxes empilhados. É anterior à revisão e
fica com o usuário; o passo 10 compara com estas seis.

### RG-01
Estado: fechada (2026-11-20). Base `a2bfc82`, na árvore principal (os arquivos da fase não
têm diff do usuário); commits `6c824cc`, `f784a74`, `cec0d9e` e o do commit 4. Um desvio
do pronto, registrado: "os 11 de dado aparecem SKIPPED na exportação limpa" vale para 6 —
os outros 5 dependem de arquivo rastreado ou de fonte do Windows, e rodam de verdade aqui.
- Commit 1 (os `return` nus): `tests/test_testes_honestos.py` falhou primeiro com os 29
  `return` de 27 testes, a contagem da spec; trocados por `pytest.skip` com motivo. Na
  exportação limpa do `HEAD` pulam 6 dos 11 de dado — `training_data/`,
  `ilovepdf_pages-to-jpg/*0021.jpg` e a página 0108 ficam fora do git; os outros cinco
  dependem do `model_meta.json`, que é rastreado, e de fontes do Windows, presentes aqui
  (na CI Linux pulam). Os 16 de display pulam com o motivo quando a falta de display é
  simulada (`raiz_tk` → `None`, `TEM_DISPLAY = False`, por um plugin de pytest de
  conferência): 16 skipped, 8 passed. Suíte da exportação limpa: 3637 passed, 28 skipped.
- Commit 2 (asserções e golden): `faixa_da_linha` confere o tamanho cortado na borda e o
  miolo; a face confere tinta, fundo e glifos distintos para `a`, `s`, `o` (um `.notdef`
  sai igual para os três); o zoom é conferido chamando o duplo-clique com um espião;
  `plausivel` exige `is True` e o contraste sem o rei branco; o golden ausente falha em vez
  de se regravar. Os cinco falham contra a função testada devolvendo um vazio do tipo
  certo (plugin de conferência). Suíte da exportação limpa: 3637 passed, 28 skipped.
- Commit 3 (configuração do pytest): `--strict-markers` e `-ra` no `pytest.ini`; as marcas
  `unit`, `integration`, `ml` e `export` (sem uso) e o bloco `[tool.pytest.ini_options]`
  do `pyproject.toml` fora; `epubcheck>=5.0` nos dois arquivos (o instalado é o 5.3.0).
  `pytest --strict-markers --collect-only` sem erro (3719 coletados, com o teste não
  rastreado do usuário). Suíte da exportação limpa: 3637 passed, 28 skipped; `slow and not
  gui`: 10 passed, 8 skipped.
- Commit 4 (lint dos testes): os 63 erros do `ruff check tests` zerados — 25 F401 pelo
  `--fix`, conferidos um a um (sobras como o `from ui.main_window import MainWindow` que a
  PD-22 deixou órfão nos testes de fonte; nenhum era o objeto do teste); 4 F841 que eram
  sobras (um `binarize` sem uso, um `TemporaryDirectory` vazio, um `rng`, um `win`); 2
  E731 viraram `def`; os 32 E741 são `l` de "linha", ignorados em `tests/**` no
  `pyproject.toml`. O `CLAUDE.md` passa a mandar o `ruff` com `tests` e diz das marcas e
  do `pytest.skip`. Os 27 arquivos tocados: 720 passed. `compileall` limpo. Suíte da
  exportação limpa: 3637 passed, 28 skipped; `slow and not gui`: 10 passed, 8 skipped.
- O `ci.yml:37` (o lint de `tests` na CI) fica para a RG-02b, como o roadmap diz.
- Próximo passo da revisão: a RG-02a (a RG-01b corre fora do caminho crítico).
### RG-01b
### RG-02a
Estado: fechada (2026-11-20), em três commits (`f9d2095`, `de26c74` e o do R-08), levados
ao `master` por `git merge --ff-only`. Base `70936c5`, no worktree `.claude/worktrees/rg02a` (destacado, com
`custom_model.pth` e `text_line_model.*` copiados; `model_meta.json` igual ao do `HEAD`),
porque a fase toca o que o AbbyChessCraft chama (passo 10). Medida de antes em
`preview_ocr/ab/RG-02a-antes` do worktree, rodada duas vezes: textos e roteamentos
idênticos, só o tempo do `relatorio.json` varia.
- Commit 1 (R-43): `config.paths.pasta_de_treino()` (`PYBOXEDITOR_TRAINING_DIR`; na árvore
  do projeto, a `training_data/` ao lado do código; instalado, a pasta de dados do
  usuário); o cwd sai de `_raizes_de_recursos` e de `dado_do_projeto`; `LearningService`,
  `CharacterLearner`, `CharDataset`, `NeuralTrainer`, `NeuralPredictor`, `coleta.promover`
  e `import_character_images` sem nome solto; o `conftest` fixa a base da suíte numa
  pasta temporária. `tests/test_pasta_de_treino.py` falhou primeiro pelo motivo certo (o
  cwd ganhava do projeto). A/B idêntico ao de antes (só o tempo varia). Suíte do
  worktree: 3649 passed, 25 skipped.
- Commit 2 (R-41): `config.paths.recurso()` (o projeto, depois o `share`), usado pelas três
  leituras por `__file__` (`render_diagrama` ×2 e `ui/pecas.py`) e por uma quarta que a
  spec não contava, `core/editor/fontes.arquivo_da_fonte_de_diagrama`; o `setup.py` leva
  as duas fontes do `fontes_de_diagrama.json`, as licenças (`SkakNew.pdf`, `LEEME__D.TXT`)
  e as 12 peças como `data-files`, e só chama o `setup()` como `__main__`; os perfis como
  package-data de `config`; `RECURSOS_OBRIGATORIOS` com as fontes e os perfis,
  `nome_no_wheel` e `verificar_wheel` (`--wheel`); `config/profiles` no spec do
  PyInstaller. Medido: o wheel construído de uma cópia limpa (`py -3.13 -m build --wheel
  --no-isolation`) sai completo pela regra; instalado num venv e importado de fora do
  projeto, o `core` vem do venv, a fonte de diagrama e as peças de `share/PyBoxEditor`,
  os 2 perfis carregam e a base de treino vai para a pasta de dados do usuário. A/B
  idêntico. Suíte do worktree: 3658 passed, 25 skipped. A conferência do wheel na CI
  (`ci.yml`) passa a usar o `--wheel` na RG-02b.
- Commit 3 (R-08): teto no PyMuPDF (`<3`), no Pillow (`<13`) e no python-docx (`<2`), que
  admitem as versões do AbbyChessCraft; `constraints.txt` com as dependências declaradas,
  nas versões em que a suíte passa (a CI passa a usá-lo na RG-02b); piso 3.11 no
  `requires-python` e no `target-version` do `ruff`, com o `README.md`, o `docs/SETUP.md` e
  o parágrafo do gate no `CLAUDE.md` no mesmo commit; `weights_only=True` no
  `calibrar_modelo.py`. `py -3.11 -m compileall` limpo; o wheel do estado final
  reconstruído e conferido de novo. Suíte do worktree: 3663 passed, 25 skipped; `slow and
  not gui`: 11 passed, 7 skipped.
- AbbyChessCraft contra o `core` do worktree (passo 10): 2915 passed, 6 failed, as mesmas
  seis da base.
- Próximo passo da revisão: a RG-03 (a RG-01b e a RG-02b correm fora do caminho crítico).
### RG-02b
### RG-03
Estado: fechada (2026-11-21), em dois commits (`934e351` e o dos gravadores), levados ao
`master` por `git merge --ff-only`. Base `b5f3dbd`, no worktree `.claude/worktrees/rg03` (destacado, com
`custom_model.pth` e `text_line_model.*` copiados; `model_meta.json` igual ao do `HEAD`),
porque a fase toca o `lexico`, cujo `_ler` o AbbyChessCraft usa sob contrato (passo 10).
- Commit 1 (o módulo): `core/escrita_atomica.py` com três formas — `gravar_atomico`,
  `escrita_atomica` (arquivo aberto) e `caminho_temporario` (para a biblioteca que grava
  por nome: `torch.save`, `fitz`, `python-docx`, `Pillow`, `zipfile`) —, a terceira além
  das duas da spec, porque metade dos 25 pontos grava assim. `tests/test_escrita_atomica.py`
  falhou primeiro (módulo ausente); 15 passed, 1 skipped (o do modo do arquivo, que o
  Windows não guarda, roda na CI). Suíte do worktree: 3672 passed, 26 skipped.
- Commit 2 (os gravadores): os 22 pontos da spec e os 3 que já usavam `mkstemp` passam
  pelo módulo; o `formato_box` monta o texto antes de abrir; o cache do OCR grava sem
  `fsync` (`duravel=False`); o `_pdf` editorial fecha o documento num `finally`.
  `tests/test_gravadores_atomicos.py`: a varredura por AST (sem `.tmp` de nome fixo nem
  `mkstemp` fora do módulo; lista nominal vazia) acusa, contra o `HEAD`, os 13 `.tmp` e os 4
  `mkstemp` que a spec listou, e nenhum depois; o caso de interrupção de cada um dos 23
  gravadores (a troca final falhando) deixa o arquivo de antes intacto e nenhum temporário
  — contra os gravadores antigos, 24 dos 25 testes falham. Os dois `torch.save` do treino
  de linhas ficam só com a varredura (o caso pediria um treino inteiro). O acréscimo do
  diário de revisão não é pego pela regra, que mira o temporário próprio, e fica fora de
  propósito (R-09). A invariante 17 e o termo "escrita atômica" entram no `CONTEXT.md`.
  Medido: o rascunho do editor de um livro de 300 capítulos (9,6 MB) grava em 1134 ms de
  mediana antes e 1140 e 1127 ms depois — o `fsync` some no custo da serialização. Suíte do
  worktree: 3697 passed, 26 skipped; `slow and not gui`: 11 passed, 7 skipped.
- AbbyChessCraft contra o `core` do worktree (passo 10): 2915 passed, as mesmas 6 falhas.
- Próximo passo da revisão: a RG-04.
### RG-04
Estado: fechada (2026-11-21), em quatro commits (`d82c212`, `2b66593`, `917ac7e` e o do
R-48), levados ao `master` por `git merge --ff-only`. Base `6e57dab`, no worktree `.claude/worktrees/rg04` (destacado, com os
pesos copiados; `model_meta.json` igual ao do `HEAD`), porque o R-48 toca o `OCRService`,
que o AbbyChessCraft chama (passo 10).
- Commit 1 (R-05): `core/caminho_seguro.py` (`e_relativo_seguro`, `caminho_seguro`,
  `CaminhoInseguro`); a leitura do EPUB deixa de fora, com aviso, a entrada que sai do
  pacote; a pasta HTML grava pelo nome no zip relativo à raiz comum do OPF, dos capítulos e
  do manifesto, e o `index.html` linka pelo mesmo mapa; os recursos da pasta passam pela
  escrita atômica; `_trazer_do_disco` recusa absoluto, unidade e UNC e só embute a
  extensão do recurso pedido. A invariante 18 entra no `CONTEXT.md`.
  `tests/test_caminho_seguro.py`: os quatro cenários falharam primeiro pelo motivo certo
  (o `ESCAPOU.txt` em `out/`, o `Text/c.html` fora da pasta, o `../sobra.txt` de volta no
  EPUB, o `.txt` embutido); o `test_editor_html.py:92-113` continua verde. Suíte do
  worktree: 3713 passed, 26 skipped.
- Commit 2 (R-06): `core/teto_de_pacote.py` (256 MB por entrada, 1 GB no total, conferidos
  pelo `ZipInfo.file_size` antes de ler), usado pelo `_Pacote` do DOCX, pela leitura, pelo
  `dados_de` e pela validação do EPUB; o `document.xml` mal formado vira `ValueError`; o OPF
  com entidade do HTML abre por `xhtml.entidades_em_numericas`, a mesma tabela dos
  capítulos. `tests/test_teto_de_pacote.py`: contra o código de antes, 5 de 6 falham (o
  sexto confere os valores dos tetos); com tetos reduzidos no teste, a entrada grande
  demais é recusada sem nenhum `ZipFile.read` dela. Suíte do worktree: 3719 passed, 26
  skipped.
- Commit 3 (R-07): `core/texto_legal.py` (`texto_legal_em_xml`, pública, com a contagem em
  WARNING `uma_vez` por origem), aplicada onde o texto vira nó XML: no XHTML já serializado
  de cada página do EPUB do OCR, no `add_run` do DOCX do OCR, no trecho e no atributo do
  editor, e no texto do TXT importado; o TXT com BOM UTF-16 passa a ser lido como UTF-16.
  `tests/test_texto_legal_em_xml.py`: contra o código de antes, os quatro cenários falham
  (o EPUB mal formado, o DOCX que levanta, o `\ud800` do editor, o TXT com NUL); o negrito
  fica no lugar no EPUB e no DOCX. Suíte do worktree: 3724 passed, 26 skipped.
- Commit 4 (R-48): o EasyOCR deixa de trocar o `ssl._create_default_https_context`; a
  falha de certificado no download vira `RuntimeError` dizendo como instalar os pesos à
  mão; o cache de leitores ganha uma trava. O `test_f16_easyocr.py`, que exigia o remendo
  ligado durante o download, foi invertido; os três testes novos falharam primeiro (o
  contexto desligado, o `URLError` cru, o leitor carregado duas vezes por duas threads).
  Suíte do worktree: 3726 passed, 26 skipped; `slow and not gui`: 11 passed, 7 skipped.
- AbbyChessCraft contra o `core` do worktree (passo 10): a primeira rodada deu uma sétima
  falha, `test_lote.py::test_g1_fechar_com_o_lote_ativo_guarda_o_ponto_e_nao_rele_nada`,
  com a suíte daqui rodando ao lado; sozinho, esse teste passou três vezes contra este
  `core` e três contra o da árvore principal, e a suíte dele, rodada de novo com a máquina
  quieta, deu 2915 passed e as mesmas 6 falhas da base. É instabilidade de carga dele,
  não da fase.
- Próximo passo da revisão: a Onda 2 (RG-05, RG-05b, RG-06).
### RG-05
Estado: fechada (2026-11-21), em quatro commits (`920acca`, `b372cb0`, `147e32b` e o do
R-55). Base `15af852`, no worktree `.claude/worktrees/onda2` (destacado, com os pesos
copiados), o mesmo da RG-05b e da RG-06; vai ao `master` com elas, no fim da Onda 2.
- Commit 1 (R-52): `_write_box_pair` não regrava o PNG do par quando ele é a própria imagem
  aberta (`_mesmo_arquivo`: `samefile` com os dois no disco, o caminho real normalizado
  senão), e o aviso de sucesso diz "a imagem de origem, mantida como estava". O PNG de um
  par com outro nome, e o das páginas do PDF, saem como antes. `tests/test_imagem_de_origem.py`:
  contra o código de antes, três dos quatro falham pelo motivo certo (o byte 25 do PNG, o
  tipo de cor, passa de RGB a cinza; no Ctrl+S, no "Salvar todas" e com `Pagina.PNG`); o
  quarto, o par com outro nome, já passava. Suíte do worktree: 3730 passed, 26 skipped.
- Commit 2 (R-02): o `Settings` separa o arquivo que não abre (`OSError`: não é regravado,
  WARNING) do que não é JSON (trocado, com a cópia em `settings.json.corrompido`); o
  `save()` mescla um nível abaixo quando o disco e o valor novo são dicionários, o que
  cobre os três gravadores da chave `editor` (`janela.py`, `clipes.py`, `projeto.py`) sem
  API nova. As buscas salvas: o item que esta versão não lê (sem nome, escopo
  desconhecido, não dicionário) fica em `Colecao.ilegiveis` e volta ao disco como veio; a
  opção desconhecida de uma busca que se lê continua ignorada ao rodar (ED-06b) e volta ao
  disco com ela (`BuscaSalva.desconhecidas`, `como_dict`). O
  `test_fase9_settings_atomicos.py` passa a conferir o `.corrompido`.
  `tests/test_preferencias_nao_se_perdem.py`: contra o código de antes, os sete falham (o
  arquivo vira `{'x': 1}`, sem `.corrompido`, a busca do primeiro editor apagada pelo
  layout do segundo, as três ilegíveis e a opção nova apagadas). Suíte do worktree: 3737
  passed, 26 skipped.
- Commit 3 (R-04): "Descartar" deixa o descarte pendente (`Documento._descarte_pendente`),
  e o rascunho só sai em `_efetivar_descarte`, quando a sessão nova existe (antes do
  `_tentar_recuperar`, para o mesmo arquivo reaberto não oferecer o que se descartou) ou
  no `_on_close`, antes do `destroy`; a falha do gravador vai ao log (WARNING, `uma_vez`
  por rascunho) e ao título ("rascunho não gravado") enquanto durar; a de
  `remover_autosave` é WARNING, salvo o arquivo que já não existe; a página esvaziada
  conta como suja (`dirty_pages` sem o filtro de "tem boxes"), entra no rascunho vazia,
  volta vazia e salva o `.box` vazio, pelo Ctrl+S e pelo "Salvar todas"
  (`pages_to_save`). No editor, o `OSError` do rascunho ao fechar pela principal loga e
  segue para a guarda, e o rascunho mais velho que o EPUB é oferecido com o aviso.
  `tests/test_rascunho_nao_some_antes_da_hora.py`: contra o código de antes, sete dos oito
  falham; o oitavo (fechar a janela com "Descartar" apaga o rascunho) já passava e fica de
  guarda. Suíte do worktree: 3745 passed, 26 skipped.
- Commit 4 (R-55): `Rascunho.restaurar` religa a ponte, como `Projeto.abrir`, e o projeto
  restaurado nasce com relatório, para o aviso da ponte desligada chegar à janela (que
  mostra os avisos do relatório do projeto que instala); o rascunho da janela principal
  grava `BoxEntry.as_state()` (onze campos, a confiança arredondada) e lê por
  `from_state`, com a escala aplicada depois. `tests/test_rascunho_restaura_tudo.py`:
  contra o código de antes, três dos quatro falham (a ponte que não volta, o aviso que não
  chega, `negativo`/`margem`/`moldura` perdidos); o quarto, o rascunho antigo de oito
  campos, já carregava e fica de guarda. Suíte do worktree: 3749 passed, 26 skipped.
### RG-05b
Estado: fechada (2026-11-21), em dois commits (`9ec6bd0` e o do R-54), no worktree da
RG-05 (`.claude/worktrees/onda2`), depois dela; vai ao `master` no fim da Onda 2.
- Commit 1 (R-53): o `CharacterLearner` guarda a impressão digital esperada (a da carga
  mais um por PNG que ele grava em `learn`), e `salvar_cache` grava essa, ou nada (INFO)
  quando a do disco diverge — a sessão seguinte relê a base uma vez e grava o cache
  certo; a promoção pula o recorte que a classe já tem (forma e bytes: o mesmo desenho em
  outro tamanho é outra amostra), conta em `Promocao.repetidos` e salva o cache; a janela
  promove pelo learner do serviço e diz quantos ficaram de fora. A matriz e as predições
  não mudam (o que muda é quando o cache se grava), por isso sem A/B.
  `tests/test_base_de_treino_uma_vez.py`: contra o código de antes, três dos quatro
  falham (a sessão seguinte sem `b`, a base relida do disco depois da promoção, 3 → 6
  no disco); o quarto, aprender e reabrir pelo cache, já passava e guarda o custo que o
  cache existe para evitar. Suíte do worktree: 3753 passed, 26 skipped.
- Commit 2 (R-54): `recorte_de_pe` limita o box à página e devolve o recorte vazio para o
  que sai dela; `learn_from_boxes` pula o vazio, conta (`ultimos_pulados`, INFO) e salva
  o cache do lote; `clamp_box` por `replace`, com todos os campos; `split_box` devolve
  `[box]` com menos de 2 px ao longo da leitura, e o Ctrl+D diz "estreito demais"; o
  canvas para o box movido na borda sem mudar o tamanho, corta na borda o redimensionado
  (`_na_pagina`, pelo `clamp_box`, com os 3 px de mínimo para dentro) e o novo, e o
  `release` só faz commit se o box mudou. `tests/test_box_fora_da_pagina.py`: contra o
  código de antes, os oito falham (o recorte que deu a volta, com 600 px de tinta da
  borda direita; o `cv2.resize` que derruba o lote; `margem` e `moldura` perdidas; o box
  de largura zero; o box a −110; o canto a 400×300; o clique que sujou a página). A/B de
  identidade (`recorte_de_pe` está na leitura): `preview_ocr/ab/RG-05b-antes` (exportação
  limpa do `9ec6bd0`, com os pesos) contra `RG-05b-depois`, nas quatro páginas — só o
  `tempo_s` do `relatorio.json` difere. Suíte do worktree: 3761 passed, 26 skipped.
- AbbyChessCraft contra o `core` do worktree (passo 10; ele chama `split_box` e
  `clamp_box`): 2915 passed e as mesmas 6 falhas da base.
### RG-06
Estado: fechada (2026-11-21), em dois commits (`b381a29` e o do R-31), no worktree da
Onda 2, depois da RG-05b; a onda inteira vai ao `master` por `git merge --ff-only`.
- Commit 1 (R-03): o recurso que não se lê na montagem levanta `epub.RecursosIlegiveis`
  (subclasse de `OSError`, com a lista) antes de gravar — o destino não muda, e o projeto
  continua apontando para o arquivo de antes —; `sem_ilegiveis=True` grava sem eles, com
  aviso, e eles saem do livro aberto; a janela do editor pergunta ("Salvar sem eles?";
  "Não" não grava nada). `Recurso.nome_de_origem` guarda a entrada do zip de onde os
  bytes vêm (posto pelo leitor, lido por `dados_de` e `descarregar`), e a gravação no
  destino o atualiza: renomear e `renomear_varios` não perdem mais a imagem. A gravação
  em cópia passa `destino=False` (o checkpoint, a diferença, a exportação, a validação),
  sem trocar a origem do livro — e o checkpoint segue a regra do salvar. Diferente do que
  a spec escreveu ("dentro do `with escrita_atomica`"), a recusa vem antes de abrir o
  destino, o que dá o mesmo aceite (o destino não muda) sem temporário a descartar.
  `tests/test_epub_salvo_nao_perde_recurso.py`: contra o código de antes (com a classe
  nova posta à mão para o teste carregar), os quatro do `core` falham (nada levanta com a
  origem apagada, nem no checkpoint; a imagem renomeada some do zip, também com
  `renomear_varios`); o quinto, na janela, confere a pergunta. Suíte do worktree: 3766
  passed, 26 skipped.
- Commit 2 (R-31): `epub.escrever` monta e grava uma cópia do livro (`copy.deepcopy`;
  os bytes não se copiam), e a opção `ncx` vale na cópia; com `destino`, voltam ao livro
  aberto só a origem, o `ncx`, o nav e o identificador sorteados, e o nome de origem dos
  recursos. O `test_editor_epub.py::test_recursos_sao_lidos_sob_demanda…` fixava que a
  gravação carregava todos os recursos no livro aberto; agora ela os carrega na cópia, e
  o teste confere que o livro aberto fica só com o que já tinha. O sumário ainda sai
  podado no arquivo (R-27, Onda 4), não mais no livro aberto.
  `tests/test_escritor_nao_muda_o_livro.py`: contra o código de antes, os quatro falham
  (o marco podado no sucesso, o `ncx` trocado na falha, o identificador da cópia
  devolvido ao livro, o checkpoint que poda os marcos do livro aberto). Suíte do
  worktree: 3770 passed, 26 skipped; `slow and not gui`: 11 passed, 7 skipped.
- AbbyChessCraft contra o `core` do worktree, no fim da onda (passo 10): 2915 passed e as
  mesmas 6 falhas da base.
- Próximo passo da revisão: a Onda 3 (RG-07 em diante, o diário de revisão).
### RG-07
Estado: em andamento (2026-11-21). Base `1a923bb`, no worktree `.claude/worktrees/onda3`
(destacado, com os pesos copiados), o mesmo da RG-08.
- Commit 1: `scripts/medidas/medir_lote_de_revisao.py` — 200 edições (`ReviewSession.edit`,
  diário em memória) num documento de 300 páginas × 12 parágrafos, com os ids de evento e
  o relógio fixos, para o documento final sair igual em toda rodada; grava
  `documento_final.json` e `tempo.json`. Na base, nesta máquina: **17,16 s** (o revisor
  mediu 54,6 s noutra condição; a régua da RG-08 é a desta máquina), em
  `preview_ocr/ab/lote-RG-07-base` da árvore principal (ignorado pelo git).
- Commit 2 (R-09): `ReviewJournal.read` separa as linhas só por `\n` e pula a que não se
  lê com WARNING (o número da linha e o erro); a gravação, se o arquivo não termina em
  `\n`, escreve um antes do evento, sem truncar nada, e termina em `fsync`.
  `tests/test_diario_leitura_tolerante.py`: contra o código de antes, os três falham (o
  `JSONDecodeError` do U+2028 e o da linha truncada; nenhum `fsync`). Os sete testes que
  contam linhas do diário seguem verdes. Suíte do worktree: 3773 passed, 26 skipped.
- Commit 3 (R-10): `editorial_review.caminhos_do_diario`/`abrir_diario` — a escrita vai
  para `<saida>.<sha12>.review.jsonl`; o diário sem sha no nome é lido antes e nunca
  escrito (`ReviewJournal(anteriores=…)`, sem evento repetido); o de sha diferente, no
  caminho guardado ou ao lado, não é lido nem escrito, com aviso; sem `source_sha256` o
  nome fica como era (o documento sintético dos testes, que por isso continuam contando
  as linhas do mesmo arquivo). `from_journal` não levanta mais pelo diário: pula o evento
  de outro `document_id` e resolve o conflito de valor por alvo, pela cadeia que termina
  no último evento; o que ficou de fora vai para `ReviewSession.avisos` e WARNING. A
  janela grava o `review_journal_path` pela regra e mostra os avisos ao abrir a revisão;
  a ponte do editor (`caminho_do_diario`, `gravar_eventos`) usa a mesma regra para o
  caminho guardado no JSON e no EPUB. Os dois `except (ValueError, KeyError)` saíram. A
  I-19 entrou no `CONTEXT.md`. `tests/test_diario_com_identidade.py`: contra o código de
  antes (com as funções novas imitando o nome único de antes), os oito falham. Dois
  testes antigos mudaram: `test_editor_importar_ir.py` conferia a frase do aviso antigo
  ("não é deste documento"), e o `_App` de `test_revisao_na_janela.py` não capturava
  `showwarning` — o aviso novo abria a caixa de verdade e o teste esperava 137 s; agora
  ele captura e o teste confere o aviso. Suíte do worktree: 3781 passed, 26 skipped.
- Commit 4 (R-11): `ReviewEvent.before_reason_codes` (gravado e lido; vazio no evento
  antigo); o evento de desfazer leva as marcas (`undo`, `batch:<id>`) e depois os motivos
  de antes, e `apply_review` deixa na decisão só os motivos (`_motivos_da_decisao`); `undo`
  e `batch:` são recusados vindos de fora (`_recusar_reservados`; `apply_batch` e `undo`
  os usam por dentro). O `test_editorial_review_phase5.py` conferia que o desfazer
  deixava `("undo",)` na decisão; agora confere a marca seguida dos motivos de antes.
  `tests/test_desfazer_devolve_os_motivos.py`: contra o código de antes, os seis falham (o
  item que sai da fila, no passo, no lote e em dois passos; os três motivos reservados
  aceitos). Suíte do worktree: 3787 passed, 26 skipped.
- Commit 5 (R-12): `ReviewSession._aplicar_varios` monta e aplica os eventos num documento
  de trabalho e só então grava todos (`ReviewJournal.append_lote`, uma gravação e um
  `fsync`); `apply_batch` confere os alvos antes, e `undo` desfaz o passo numa transação;
  `Pedido` + `aplicar_lote` (status, motivos e metadata por evento; alvos, status e
  motivos reservados conferidos antes). A ponte grava um lote por salvamento; desce nos
  blocos de lista, citação e nota (não na célula de tabela) e não conta o contêiner sem
  origem como bloco novo; o capítulo em modo código não gera evento — as origens dele
  saem do próprio `texto_cru` (ou, se ele não se lê, dos blocos de antes da troca) — e o
  salvamento avisa. Três testes antigos conferiam os motivos da ponte como `("editor",)`;
  agora conferem `editor` mais uma marca `batch:` só, a mesma no salvamento inteiro.
  `tests/test_lote_transacional_e_ponte.py`: contra o código de antes (com `Pedido` e
  `aplicar_lote` imitando o lote evento a evento), os cinco falham — o lote que deixa a
  metade, dois passos onde devia haver um, o salvamento em dois passos, o modo código que
  rejeita 9 blocos, o bloco da citação "apagado". Suíte do worktree: 3792 passed, 26
  skipped.
- O diário gravado na base abre: um diário escrito pelo core da árvore principal
  (`1a923bb`, nome sem sha, linhas CRLF, eventos sem `before_reason_codes`, com edição,
  lote, aceite e desfazer), aberto pelo core do worktree, aplica tudo (b0 corrigido, b1 e
  b2 aceitos, b3 de volta a `automatic`, dois passos desfazíveis), sem aviso; a edição
  seguinte vai para `saida.cccccccccccc.review.jsonl`, e o arquivo antigo fica com o mesmo
  sha256 (`scratchpad\diario_da_base.py` da sessão). A abertura de um diário real do
  usuário segue fora do pronto: não há nenhum `*.review.jsonl` na máquina.
- Estado: fechada (2026-11-21), em cinco commits (`d48bb09`, `a1dbce8`, `0acb649`,
  `a0400c7`, `98140f6`), no worktree da Onda 3.
### RG-08
Estado: fechada (2026-11-21), em dois commits (`b370e06` e o do R-13), no worktree da
Onda 3, sobre a RG-07 (`98140f6`); a onda inteira vai ao `master` por `merge --ff-only`.
- Commit 1 (abertura): a régua corrigida. O `medir_lote_de_revisao.py` da RG-07 media 200
  edições interativas, e cada edição é uma foto nova do documento por natureza — não é
  o que o R-13 conserta. Agora ele mede, com os mesmos 200 eventos: `interativo` (a
  referência de antes), `reabrir` (`from_journal` sobre o diário, o que a janela e a
  ponte fazem a cada abertura) e `lote` (`aplicar_lote`, o salvamento do editor), e grava
  o documento **reaberto**. Antes, nesta máquina: interativo 18,14 s, **reabrir 18,41 s,
  lote 19,30 s**; uma segunda rodada, 17,90/18,50/20,33 s, com o `documento_final.json`
  igual byte a byte (`preview_ocr/ab/lote-RG-08-antes` e `-antes2`).
- Commit 2 (R-13): `EditorialDocument.apply_reviews` e `AplicacaoDeRevisao` — uma cópia
  por lote, os blocos e os ids indexados, uma validação no fim; `apply_review` é o lote de
  um. A sessão monta os eventos do lote sobre o aplicador (`bloco` dá o estado corrente
  do alvo), e `from_journal` aplica tudo de uma vez — e nada, sem cópia, quando não há
  evento novo. `ReviewJournal.read_cauda` lê só o que o diário recebeu desde a última
  leitura (a linha sem `\n` fica para a próxima; o arquivo que encolheu é relido do
  começo); a ponte lê sempre por ela, devolve o diário em `RelatorioDaPonte.journal`, e
  o `Projeto` o passa ao salvamento seguinte (e o esquece ao religar o documento).
  `tests/test_lote_de_revisao_em_tempo_linear.py`: os seis falham contra a abertura (a
  API nova não existe; a prova de comportamento é a medida). Medido nesta máquina: a
  régua dá **reabrir 18,41 → 0,11 s e lote 19,30 → 0,11 s**, com o `documento_final.json`
  igual byte a byte ao de antes (`preview_ocr/ab/lote-RG-08-depois`); o interativo segue
  em 18,55 s, por natureza. O Ctrl+S do Dvoretsky inteiro convertido pela camada (816
  páginas, 11.935 blocos; `scripts/pdf_para_editor.py --camada sempre`, 79 s), por
  `scratchpad\medir_ctrl_s_dvoretsky.py` da sessão: o salvamento com 200 edições cai de
  **295,2 s (ponte 266,5 s) para 34,0 s (ponte 1,4 s)**; o de uma edição com 200 a 202
  anteriores fica igual — 30,9/31,2/31,0 s antes (ponte 1,6/1,3/1,3 s), 30,8/30,4/30,8 s
  depois (ponte 1,5/1,2/1,3 s): ler a cauda poupa a releitura das linhas, que com 200 é
  barata, e sobra a foto do documento, que a spec manda manter; os ~30 s do salvamento são
  a gravação do EPUB, fora do R-13. Uma primeira versão copiava o documento mesmo sem
  evento novo na cauda e deixava a ponte do salvamento de um evento em 2,9 s; corrigida
  antes do commit. Suíte do worktree: 3798 passed, 26 skipped; `slow and not gui`: 11
  passed, 7 skipped.
- AbbyChessCraft contra o `core` do worktree, no fim da onda (passo 10): 2915 passed e as
  mesmas 6 falhas da base.
- Próximo passo da revisão: a Onda 4 (a fidelidade do editor).
### RG-09
Estado: fechada (2026-11-21), em um commit. Base `d82f74a`, no worktree
`.claude/worktrees/onda4` (destacado, com os pesos copiados), o mesmo da RG-10 e da RG-11.
- `sumario.ancoras_do_livro`: o índice de âncoras calculado na gravação, do modelo — ids
  de bloco e de nota, ids de dentro das ilhas de bloco (`IlhaBruta.xhtml`) e inline
  (`Trecho.ilha`), e, no capítulo em modo código, os ids do próprio `texto_cru`; os
  `extras` da RG-10 entram nele quando chegarem. `destinos_quebrados` o usa, e a entrada
  sem destino é rótulo (não conta como quebrada). A gravação transforma a entrada
  quebrada em rótulo, mantendo os filhos, com o aviso ("mantida como rótulo"); o nav
  escreve o rótulo em `<span>` (o leitor já o lia); o NCX, que não tem rótulo sem
  destino, aponta o navPoint para o primeiro destino dos filhos, e deixa de fora o rótulo
  sem destino e sem filhos. Gerar o sumário dos títulos — na leitura de um livro sem ele
  e na gravação — passa a avisar. `tests/test_sumario_acha_as_ancoras.py`: contra o código
  de antes, os cinco falham (o `<h2 id>` da ilha, o `<a id>` inline e o rótulo dados como
  quebrados; a âncora do modo código idem; a subárvore que saía com a entrada; a
  regeneração calada; o NCX de um sumário inteiro regenerado). Suíte do worktree: 3803
  passed, 26 skipped.
### RG-10
Estado: fechada (2026-11-21), em seis commits (`54813f1`, `a4ff7f2`, `5699a54`, `e21352b`,
`26802bf` e o da medida de depois), no worktree da Onda 4, depois da RG-09.
- O corpus, escolhido pelo usuário em 2026-11-21: 12 EPUBs de seis produtores, copiados
  (os originais ficam onde estavam) para `C:\Python-Chess2\corpus_epub`, ao lado do
  projeto — Quality Chess (Adams & Hurtado *Think Like a Super-GM*, 2022; Flores Rios
  *Chess Structures*, 2015, em português; Schandorff *GM Repertoire 7*, 2010), New In
  Chess (Grooten *Finais de xadrez*, 2022; Sakaev & Landa vol. 1, 2016; Erwich *1001
  Exercises*, 2021, em português), Chess Evolution (TMEM 1 e 2, 2016), Batsford (Gufeld &
  Stetsko *Giuoco Piano*, 1996; Engqvist *300 Most Important Chess Positions*) e Kindle
  sem DRM (*100 Endgames You Must Know*, *Imagination in Chess*). O Erwich e o Engqvist
  propostos estavam no OneDrive, só na nuvem (o provedor não estava rodando): foram as
  cópias locais dos mesmos livros.
- Commit 1: `scripts/medidas/medir_ida_e_volta_epub.py` e `config.paths.corpus_de_epubs()`
  (`../corpus_epub`, ou `PYBOXEDITOR_CORPUS_EPUB`; sem a pasta, avisa e sai 0). Lê e grava
  cada livro sem edição e conta, por livro, os `elemento@atributo`, os elementos e os
  atributos do OPF do original que faltam no gravado, e os arquivos do zip; guarda os
  avisos de leitura e de gravação (a perda declarada). **Antes**, nos 12: 731 atributos,
  1093 elementos, 65 atributos do OPF e 0 arquivos perdidos; os mais frequentes,
  `body@class` 302, `li@class` 132, `html@imt-state` 90, `a@dir`/`a@lang` 36,
  `body@dir`/`body@lang` 16, `html@dir` 16, `html@epub:prefix` 9, `li@id` 3; os elementos,
  `b` 728 (todos do Grooten) e `p` 360 (todos do Schandorff), mais `style` 4 e `meta` 1; no
  OPF, `xmlns:*` do `metadata`, `opf:role`/`opf:file-as`/`opf:scheme` dos `dc:*`, o
  `guide` (`reference@*`), `spine@page-map` e `spine@page-progression-direction`
  (`preview_ocr/ab/ida-e-volta-antes`).
- Commit 2 (R-26, os elementos): `extras` em `ItemDeLista` e `Celula`, `extras_das_filas`
  em `Tabela`, `extras_da_imagem` em `Figura`, e `extras_do_corpo`, `extras_da_raiz` e
  `midia_das_folhas` em `Capitulo`. O `li`, o `tr`, o `td` e o `th` guardam `id`, `class`,
  `lang`, `xml:lang` e `dir` — com eles, a lista e a tabela continuam editáveis, em vez de
  virarem ilha —, e outro atributo qualquer ainda leva o bloco a ilha; o `img` da figura
  guarda também o `title`, que se perdia; o `body` e o `html`, que não viram ilha, guardam
  tudo o que o escritor não gera; o `<link>` guarda o `media`. O dialeto não escreve
  `class` nesses elementos, então não há o que fundir. Os ids desses `extras` entram no
  índice de âncoras do sumário (RG-09). Os campos novos nascem vazios: o rascunho gravado
  antes deles abre. A I-20 entrou no `CONTEXT.md`. `tests/test_ida_e_volta_dos_atributos.py`:
  contra o código de antes, dois dos quatro falham — a lista e a tabela que viravam ilha
  pelo `lang`/`dir` do item e da célula, e o `id` do `img` fora do índice de âncoras; os
  outros dois (o atributo desconhecido ainda levando a ilha, o rascunho sem `extras`)
  guardam o que não podia mudar. Suíte do worktree: 3807 passed, 26 skipped (uma falha de
  `init.tcl` do Tcl numa rodada parcial, que passou sozinha e na suíte inteira).
- Commit 3 (R-26, o pacote): `Livro.extras_do_pacote` e `extras_da_espinha`;
  `id_no_manifesto` e `extras_do_item` em `Capitulo` e `Recurso`; `extras_do_itemref` em
  `Capitulo`; `Metadados.atributos` (os do elemento além do `id`, pela chave de `ids`). O
  leitor guarda o `xml:lang` e o `dir` do pacote (o `xml:lang` só quando difere do
  `dc:language`, senão é o que o escritor já põe), o `page-progression-direction` da
  espinha, o `id` e o `properties` do `itemref`, o `fallback` do `item`, o `opf:scheme` do
  identificador e o `xml:lang` dos `dc:*`; o escritor devolve tudo e grava cada item com o
  id que ele tinha (o `_item` já aceitava o id; ninguém o passava) — o `refines="#c1"` e
  o `fallback` voltam a apontar. `modelo.igual` ignora o `id_no_manifesto` e o
  `nome_de_origem`, como já ignorava a `linha_fonte` (é onde o conteúdo mora, não o
  conteúdo): sem isso, o livro relido de `test_editor_epub.py` deixava de ser igual ao
  novo. `tests/test_ida_e_volta_do_pacote.py`: contra o código de antes, os dois falham
  (a espinha sem `page-progression-direction`, o `c1` renomeado para `c1.xhtml`); a
  segunda volta sai igual à primeira. Suíte do worktree: 3809 passed, 26 skipped.
- Commit 4 (R-26, a codificação): o capítulo que não passa pelo analisador (o malformado,
  que abre em modo código) é decodificado pela codificação que declara
  (`_texto_pela_declaracao`), e a declaração passa a dizer `utf-8`, que é como ele será
  gravado; codificação que o Python não conhece cai no UTF-8, como antes, com INFO. O
  capítulo bem-formado já vinha certo: o `expat` do Python aceita qualquer codec, inclusive
  o Windows-1252. `tests/test_codificacao_declarada.py`: contra o código de antes, um dos
  três falha (o ISO-8859-1 malformado, com `A��o`); os outros dois guardam o caminho do
  analisador. Suíte do worktree: 3812 passed, 26 skipped.
- Commit 5 (R-51): `Metadados.de_terceiro` e `acessibilidade_declarada`. Na leitura, o
  `schema:accessibilitySummary` e o `schema:accessibilityHazard` do arquivo ficam guardados;
  o livro cujo resumo começa pelo do editor (`RESUMO_DO_EDITOR`) é do editor, e o resto é
  de terceiro. Na gravação, o de terceiro sai com o resumo e os perigos que declarou — sem
  perigo declarado, `unknown`, e sem resumo inventado (o do editor faria a próxima abertura
  tomá-lo por dele) —; o criado aqui segue `none` com o resumo calculado. `accessMode` e
  `accessibilityFeature` continuam calculados; `conformsTo` e `certifiedBy` já voltavam
  pelos extras dos metadados, e o teste os confere. A §10.1 da `SPEC_EDITOR.md` acompanha.
  `tests/test_acessibilidade_da_editora.py`: contra o código de antes, os dois do livro de
  terceiro falham (o resumo trocado e o `flashing` virando `none`; o sem declaração saindo
  `none`); o do livro criado aqui passa nos dois, com o `test_editor_epub_completo.py:146`.
  Suíte do worktree: 3815 passed, 26 skipped.
- Commit 6 (a medida de depois): nos mesmos 12 livros, **126 atributos** (eram 731), 1093
  elementos (iguais), **54 atributos do OPF** (eram 65) e 0 arquivos perdidos
  (`preview_ocr/ab/ida-e-volta-depois`). Livro a livro, nove dos doze saem com 0
  atributos perdidos. O que sobra, arquivo por arquivo (`scratchpad\onde_perde.py` da
  sessão):
  - **Grooten, 121 atributos, todos no `nav.xhtml`**, mais 4 `<style>` e 1 `<meta>` da
    cabeça dele (cada capítulo tem os mesmos e os guarda; o total perdido é exatamente o de
    um arquivo): o nav de terceiro é regenerado por decisão da §10.1, sem aviso — **perda
    não declarada**, a **PD-25**;
  - **Grooten, 708 dos 728 `<b>`**: o `<b>` em volta de um `<span>` com atributo que o
    dialeto não conhece (os `data-imt-*` da extensão Immersive Translate) — o `span` vira
    ilha inline e o negrito de fora some, sem aviso: **perda não declarada**, a **PD-24**;
  - **Schandorff, 360 `<p>`**: viram 45 diagramas (`figure` + `pre`) e 640 `strong` — a
    conversão desenhada dos diagramas em texto (F120), não perda;
  - **Gufeld, 5 `html@lang`**: o `lang=""` vazio, que não diz nada (o escritor não grava
    atributo vazio);
  - **no OPF, 54**: as declarações `xmlns:*` (o escritor declara onde usa), o `opf:role` e
    o `opf:file-as` (gravados como `<meta refines>`, o equivalente do EPUB 3), o `guide`
    (vira `landmarks`) — conversão do EPUB 2 para o 3, não perda.
  As duas perdas não declaradas que sobram entraram no `ROADMAP_PENDENCIAS.md` como
  **PD-24** (o formato do trecho em volta de ilha inline) e **PD-25** (avisar, ou levar, o
  que o nav de terceiro tinha além do sumário). `html_io.escrever_pasta` reconferida nos 12
  (`scratchpad\conferir_pasta_html.py`): todos viram pasta sem erro, e o `id` de item de
  lista que há no corpus (o do *100 Endgames*) chega à pasta.
### RG-11
Estado: fechada (2026-11-21), em três commits (`72674a2`, `7817824` e o do R-30), no
worktree da Onda 4, depois da RG-10; a onda inteira vai ao `master` por `merge --ff-only`.
- Commit 1 (R-28): `modelo.deduplicar_ids` — os blocos e as notas na ordem do capítulo, e
  depois os ids dos `extras` (RG-10): o segundo `x` vira `x-2` (sem colidir com um `x-2`
  que já exista), com aviso; o leitor de XHTML a chama ao fim de cada capítulo. A leitura
  do EPUB deixa de fora, com aviso, a entrada repetida da espinha. Juntar capítulos
  deduplica a marca de página pelo número. `tests/test_ids_e_espinha_repetidos.py`:
  contra o código de antes, os quatro falham (a espinha com o capítulo duas vezes, que
  não salvava; `x` e `x` sem renumerar; as duas marcas da página 27; o leitor sozinho). A
  suíte deste commit rodou numa exportação limpa do índice dele (o `modelo.py` com só o
  trecho do R-28), porque a primeira rodada foi invalidada: editei o worktree para o R-29
  com ela em curso, e ela foi parada sem resultado. Suíte da exportação: 3819 passed, 26
  skipped.
- Commit 2 (R-29), os cinco itens:
  - o quantificador mínimo por um leitor da sintaxe do `re` (`_quantificadores_minimos`:
    escape, classe e cabeçalho de grupo ficam; `{m,n}` conta; o que já é mínimo ou
    possessivo não dobra), e não mais por regex sobre o regex;
  - a busca em NFC: o padrão e o texto em NFC, com o mapa de deslocamentos de volta ao
    texto original (`_nfc_com_mapa`), na busca dos blocos e na do código;
  - "Substituir tudo" num capítulo em modo código grava o XHTML de antes e de depois
    (`historico.XHTML_DO_CAPITULO`; `historico.aplicar` troca o `texto_cru`), e a aba em
    modo código, quando a pilha do widget se esgota, desfaz e refaz por esse ponto;
  - a caixa por palavra decide o começo de palavra no parágrafo inteiro, atravessando os
    trechos;
  - a aspa depois de qualquer espaço, o inseparável também, abre.
  De passagem, três testes meus (este, `test_diario_leitura_tolerante.py` da RG-07 e
  `test_teto_de_pacote.py` da RG-04) tinham U+00A0, U+2028 ou U+0301 literais, invisíveis
  na leitura; viraram escapes. `tests/test_busca_e_substituicao_rg11.py`: contra o código
  de antes, oito dos dez do `core` falham (o `(?:` e o `(?P<` que não compilavam; o `\*`
  que virava opcional; o `.+` que não ficava mínimo; o `café` em NFD; o ponto vazio; o
  `NimzoWItsch`; a aspa); os dois que passavam (a classe `[*+?]` e o `{2,3}`) guardam o
  que já estava certo; o da janela confere o Ctrl+Z. Suíte da exportação deste commit:
  3830 passed, 26 skipped.
- Commit 3 (R-30): `xadrez.Linha` — a posição ao longo da linha com a pilha das variantes,
  que guarda a posição de antes da variante **e** a de antes do lance (para `1.e4 (1.d4)
  (1.c4)` sair as duas do mesmo lugar) — passa a ser o percurso de `segmentos` (que jogava
  os lances da variante no tabuleiro da linha e não dava profundidade ao `1.` que abre
  partida), `posicao_apos` e `validar`. O `pgn_io` segue com a árvore de nós do
  `chess.pgn`, que já tinha pilha, e ganha o que faltava: a variante aberta antes do
  primeiro lance pende dele (o lance seguinte da linha é promovido a principal), e o
  cabeçalho sai numa linha (`_uma_linha`). `tests/test_notacao_com_variantes.py`: contra o
  código de antes, os quatro falham (a partida partida em dois pela variante; a segunda
  variante seguida dada como ilegal; a variante virando a linha do PGN; o `[White
  "Kasparov,` partido). Suíte do worktree: 3834 passed, 26 skipped; `slow and not gui`: 11
  passed, 7 skipped.
- AbbyChessCraft contra o `core` do worktree, no fim da onda (passo 10): 2915 passed e as
  mesmas 6 falhas da base.
- Próximo passo da revisão: a Onda 5 (tarefa sobre estado vivo).
### RG-12
Estado: fechada (2026-11-21), em dois commits (`c807be7` e o do R-15). Base `6ab5455`, no
worktree `.claude/worktrees/onda5` (destacado, com os pesos copiados), o mesmo da RG-13.
- Commit 1 (R-14): o `runner` de `BackgroundTask` loga o erro com o traceback
  (`log.error(..., exc_info=True)`, com o nome da função de trabalho) antes de entregá-lo à
  janela; o cancelamento não vira erro. `tests/test_tarefa_loga_o_erro.py`: contra o código
  de antes, o da tarefa que levanta falha (nenhum registro com traceback); o do
  cancelamento já passava e fica de guarda. Suíte do worktree: 3836 passed, 26 skipped.
- Commit 2 (R-15): "Preencher boxes" guarda os boxes do começo e aplica o resultado a cada
  um deles por identidade, só no que ainda está na página; a detecção de boxes guarda a
  página e a `HistoryService.versao` (nova: cresce a cada snapshot, undo, redo e reset) e,
  se alguma mudou, descarta o resultado e avisa; "Salvar todas" grava cópias tiradas na
  thread da janela e marca salva só a página que continua igual à cópia, e o léxico
  aprende das cópias, o que foi gravado. A edição não é travada.
  `tests/test_tarefa_sobre_estado_vivo.py`: contra o código de antes, três dos quatro
  falham (`['a', 'b']` em vez de `['b', 'c']`; a detecção que apagou a edição do meio; o
  `.box` com a edição feita depois de mandar salvar); o quarto, a detecção sem edição no
  meio, aplica nos dois. O teste do Ctrl+S (`test_trabalho_fora_da_interface.py`) segue
  verde. Suíte do worktree: 3840 passed, 26 skipped.
### RG-13
Estado: fechada (2026-11-21), em quatro commits (`7ee5b26`, `d8ab142`, `ce6f5ba` e o
do R-19), no worktree da Onda 5, depois da RG-12.
- Commit 1 (R-16): a rotulagem religa o pré-OCR em sucesso, falha, cancelamento e recusa
  (o `_run_task` que devolve `False` não chama desfecho nenhum); a geração de boxes, a
  página carregada e a página com erro conferem `winfo_exists`; a troca de página que a
  janela recusa solta `_pagina_rodando`; fechar no meio cancela a tarefa que o diálogo
  disparou. A revisão editorial, modal, ganha o próprio "Cancelar operação" (a janela
  passa `task.cancel` e `task.is_running`) e cancela ao fechar. A caixa de conclusão fecha
  em `finally`. `tests/test_dialogos_religam.py`: contra o código de antes, os sete falham
  (os três desfechos do pré-OCR, o fechamento no meio, a bandeira presa, a revisão sem
  Cancelar, a caixa que fica aberta). Suíte do worktree: 3847 passed, 26 skipped.
- Commit 2 (R-17): `MainWindow._motivo_de_espera()` — o motivo de esperar (a sondagem, que
  não é tarefa, ou a tarefa rodando), sem efeito colateral — vira a decisão única: o
  `_busy` o usa para a caixa, e o `_load_pdf_page` para recusar com "Aguarde (…)" na barra
  de status, sem arquivar a página nem desabilitar os botões. Fechar a janela confirma a
  tarefa **e** o descarte antes de cancelar, e então espera a thread
  (`BackgroundTask.esperar`/`TaskController.esperar`, prazo de 10 s, WARNING se estoura)
  antes do `destroy`. `tests/test_fechar_e_navegar_com_tarefa.py`: contra o código de antes,
  os três falham (a tarefa cancelada pelo descarte recusado, a janela destruída com a
  thread no meio, a página que não virou sem aviso); o `test_f37_paginas.py` da PgDn
  segue verde. Suíte do worktree: 3850 passed, 26 skipped.
- Commit 3 (R-18): `JanelaDoEditor._cancelar_afters`, chamada no `fechar` antes do
  `destroy`, cancela todo `after` cujo comando é da janela ou de um widget dela — e não só
  os três que a spec citava: a medida (`scratchpad\after_depois_de_fechar.py` da sessão)
  achou, depois de fechar, o `esvaziar` do painel de mensagens e dois
  `_ajustar_propriedades`, cada um disparando um `bgerror` ("invalid command name"). A
  vigia de "Abrir com…" segue com o `OSError` do `open` (INFO, tenta na próxima volta) e
  reagenda em `finally`. A validação do EPUB vai para uma tarefa, sobre uma foto do livro
  tirada na thread da interface, e o cursor volta em todo desfecho; o resultado fica em
  `operacoes.ultima_validacao`, e o `test_editor_validacao.py`, que esperava a resposta
  síncrona, passa a esperar a tarefa. A pasta do `mkdtemp` sai no fechamento do editor.
  `tests/test_editor_sem_after_orfao.py`: contra o código de antes, os quatro falham (o
  `…esvaziar` órfão — a primeira versão do teste chamava `raiz.update()` antes de conferir,
  o órfão disparava ali e o teste passava por acaso; agora confere antes e captura o
  `bgerror` depois, e cancela antes os órfãos que outro teste deixou no interpretador —; a
  vigia morta no `PermissionError`; o cursor "watch"; a pasta que ficava). Suíte do
  worktree: 3854 passed, 26 skipped.
- Commit 4 (R-19): suja passa a ser a posição do histórico diferente da salva — cada
  entrada do `HistoryService` leva um id (`posicao`, que não muda com o corte do limite),
  o `DocumentController` guarda a `posicao_salva` (marcada pela janela ao abrir, virar
  para a página limpa e salvar, por Ctrl+S ou "Salvar todas"; `None` na página suja), e
  o Ctrl+Z/Ctrl+Y que chega nela limpa a página e o que sai dela a suja. "Aprender com a
  página" ensina o léxico no `concluir`, depois de as amostras gravarem, e das cópias. O
  lote vai uma página por vez (`PDFService.iterar_paginas`, gerador que não guarda o
  livro), uma chamada de `batch_extract_and_classify` por página, e a imagem que não abre
  vai para o log (WARNING, com o nome) e para o aviso do fim ("N imagem(ns)
  ilegível(is)"). O relator do Tk não grava de novo a mesma exceção dentro da janela de
  silêncio — nem log, nem arquivo, nem `stderr` —, e conta as repetições quando vier a
  próxima diferente. `tests/test_pequenos_da_janela.py`: contra o código de antes, os
  cinco falham (desfazer até o estado aberto deixava a página suja; o léxico aprendia a
  página cuja gravação falhou; o lote chamava uma vez com as duas imagens, `[2]` em vez de
  `[1, 1]`; trinta registros de um arrasto; o `iterar_paginas` que não existia).
  Suíte do worktree: 3859 passed, 26 skipped.
- Próximo passo da revisão: a Onda 6 (a leitura: RG-14, RG-15, RG-16, RG-16b).
### RG-14
Estado: fechada (2026-11-25), em três commits (`3657a1a`, `e5f6d31` e o da junção). Base `ffc3ec3` — o trabalho do usuário em `core/livro.py`
(o lance descritivo), commitado por ele ter aprovado na abertura da onda; não há diff dele na
árvore, e o passo 9 deixa de valer. Worktree `.claude/worktrees/onda6` (destacado, com os
pesos). Medidas de antes: `preview_ocr/ab/RG-14-antes` e `RG-14-antes2` (idênticas, só o
`tempo_s` varia), `preview_ocr/ab/rodadas/2026-11-25-1341.json` (corpus 0,91%),
`2026-11-25-1350.json` (o mesmo com `--usar-ensemble`, 0,91%) e
`preview_ocr/ab/RG-14-yusupov-antes` (o livro inteiro).
- Commit 1 (R-20): `pdf_nativo.passadas_de_livro`, pública, chamada pelos dois caminhos —
  legendas e mobília da camada, as passadas da imagem (cabeçalhos, coladas, negrito, por
  `da_imagem`), e por fim `juntar_entre_paginas` e `lados_pelos_lances`, que só rodavam sem
  OCR; as assinaturas ficam, com um `lex=None` novo e por nome na primeira. O guarda por
  página: a da camada que levanta (a régua também, `avaliar_com_guarda`) vai ao OCR, a do
  OCR sai como imagem com o motivo em `PaginaExtraida.falha` (campo novo, com padrão; no IR,
  só quando há), que vai para a fila (`page_failed`), os avisos e as duas conclusões;
  `Cancelled` passa; e se nenhuma página se lê, o primeiro erro sobe. O registro que vem da
  página seguinte vira `-1`. A página com falha não se junta nem passa lance adiante.
  - **O que o Yusupov inteiro mostrou** (`scripts/medidas/medir_passadas_de_livro.py`, 264
    páginas, novo; antes: 0 junções, 0 lados, 531 FEN de 540): ligadas como estavam, as duas
    passadas faziam **4 junções, as 4 falsas** (`olutions`, `xercises` duas vezes e `nn`: o
    título sem a inicial), e **9 lados, 3 errados** contra o triângulo que o livro imprime ao
    lado de cada diagrama (pp. 88, 179 e 248 — a 248 piorava). Pela regra do "se piora", uma
    rodada de diagnóstico: a página da imagem só se junta se abrir por palavra do dicionário
    (a de uma ou duas letras, de uma lista; sem dicionário, nada se junta), e
    `lado_a_jogar.pelo_lance` exige que o lance de depois seja **jogável** na posição — nos
    três casos errados ele é impossível. Depois: **0 junções** (a rodada gravada tem 1, o
    `nn`, que a lista das curtas tirou em seguida; a regra só retira), **6 lados, os 6 certos
    pelo triângulo impresso**, FEN 531 de 540, texto das páginas igual. No Aagaard pp. 10–70:
    **3 junções, as 3 verdadeiras, e 8 lados, 8 de 8 certos** pelo triângulo. Nos dois livros,
    14 lados que saíam por convenção agora saem lidos. No Dvoretsky pela camada (815 páginas,
    1.273 diagramas) nenhum lado vem do lance, e nada muda; o *Odds & Ends*, de que a régua
    nasceu, não está nesta máquina — os casos dele na suíte seguem verdes (um tabuleiro de
    teste ganhou o peão do lance seguinte, que a régua nova confere).
  - Achado da fase: `livro._cortar` devolvia `ndarray` em `pesos`/`lacunas`, e
    `juntar_entre_paginas` pedia `typecode` — no OCR, o livro com cabeçalho corrente cairia
    fora do guarda. `_cortar` devolve `array`, e a soma não depende do tipo.
  - A/B das quatro páginas idêntico (`RG-14-depois`), corpus 0,91% página a página.
    `tests/test_passadas_de_livro.py`: contra o código de antes falham os do guarda, da falha
    na fila e na conclusão, das passadas no OCR, do título sem inicial, do lance impossível e
    do cabeçalho cortado; os quatro que passam (o cancelamento no `livro.extrair`, o livro em
    que nada se lê e o `-1` no adaptador) são guardas. Suíte: 3928 passed.
- Commit 2 (R-21): a evidência do ensemble viaja no quinto campo do registro da faixa, que
  `_registro_da_faixa` já levava em `palavras.metadata` — a que tem o que conferir (engine
  que faltou, leituras que não concordam) e a do consenso aceito; a faixa que o principal não
  leu leva a dela num registro sem texto, que não entra na fusão. `_source_reader` e o atalho
  por `last_result` saem. O motor principal é chamado uma vez por faixa: a leitura dele entra
  no ensemble no lugar do adapter (que relia a faixa pelo `--psm 3`, e não pelo 7 medido).
  `tests/test_fachada_de_producao.py`: contra o código de antes, os três falham (a divergência
  fora do registro, o Tesseract chamado duas vezes, a estatística que não chega pelo
  `extrair`); os dois testes que liam `last_result` passam a ler o registro. A/B idêntico
  (`RG-14-depois`), corpus idêntico com e sem `--usar-ensemble` (`2026-11-25-1513.json`),
  rodada da fase `benchmarks/rodadas/2026-11-25-1553.json` (0,91%, igual à base da revisão e à da fase).
  Suíte: 3930 passed.
- AbbyChessCraft contra o worktree: 2915 passed, 6 failed, os mesmos seis da base.
- Commit 3 (R-20, depois da RG-16: a medida em português que a RG-16b pede mostrou): no *A
  Estratégia no Xadrez* pp. 40–80, quatro junções, duas boas (pp. 50 e 75; nesta, `bloqué` +
  `do`, a palavra que a paginação partiu sem hífen) e duas coladas na legenda ou na sobra de
  uma linha que fecha a página (`Cavalo bloqueia Rei bloqueia`, `,`). A página da imagem só
  recebe a continuação num parágrafo de duas linhas impressas ou mais: remedido, ficam as
  duas boas daqui e as três do Aagaard, e saem as duas coladas; o Yusupov segue com zero.
  Suíte: 3966 passed.
### RG-15
Estado: fechada (2026-11-25), num commit. Base `e5f6d31`, o worktree da RG-14; o "antes" é o
"depois" dela (`RG-14-depois`, `RG-14-yusupov-depois2`, `RG-14-aagaard-depois`).
- A linha da cadeia corrigida leva as medidas (`_transferir_medidas`, agora com quantos
  vetores houver) e também o **box de cada caractere**, que o reparo de colagem indexa;
  `_paragrafo_de` leva as medidas e os começos das linhas (`_transferir_inicios`);
  `partir_coladas` empurra os começos e o negrito por cada espaço que entra; e
  `negrito.marcar` conta e loga (WARNING) por página o parágrafo que pula.
  `tests/test_texto_e_medidas.py`: os três cenários, o box, o pulo, e a P-2 conferida antes e
  depois de **toda** passada, nos dois caminhos; contra o código de antes, oito dos dez falham
  (os outros dois são o caminho da camada e a cadeia sem correção).
- Medido no Yusupov inteiro: **82 parágrafos pulados → 0**, 4.172 → 4.294 trechos em negrito,
  FEN e lados iguais; no Aagaard pp. 10–70, 2 → 0 e 1.299 → 1.320, texto igual. Negrito das
  páginas de referência: p. 34 36 → 36, p. 47 45 → 45, p. 30 45 → 45, Nunn p. 237 8 → 8.
  **E um achado**: os começos de linha velhos faziam `retirar_cabecalhos` cortar letra do
  texto. Voltam o `S` de `Solutions` (pp. 95, 132), o `E` de `Exercises` (194, 212, 242), o
  `22` de `22...♗a4` (88) e o `t` de `that` (38) — era a raiz das quatro junções falsas da
  RG-14, que agora são zero também por isso. Em troca, quatro sobras de uma letra que o corte
  errado levava ficam (`E` na 15, `nn` na 126, `s` na 236, `w` na 191), e o lixo de ornamento que
  o corte levava junto com a inicial volta com ela.
- A/B das quatro páginas idêntico (`RG-15-depois`); rodada
  `benchmarks/rodadas/2026-11-25-1621.json`, 0,91% página a página, igual às duas bases.
  Suíte: 3940 passed. AbbyChessCraft: na RG-16, com a mesma árvore.
### RG-16
Estado: fechada (2026-11-25), em dois commits (`2b91ad4` e o do R-25). Base `3862d4a`, o mesmo
worktree.
- Commit 1 (R-24, a trama): `ocr_service._sem_miudezas`, uma tabela por rótulo no lugar do
  laço que comparava a página com cada componente. `tests/test_trama_por_tabela.py`: a máscara
  byte a byte igual à do laço, em três densidades, e nenhuma comparação da página com rótulo.
  Saída idêntica nas quatro páginas (`RG-16-antes`/`RG-16-depois`) e na p. 96 (`RG-16-p96-*`);
  tempo, com a máquina quieta: pp. 34 + 47 do Yusupov 39,4 → 23,4 s, p. 30 4,8 → 4,6, p. 237
  4,0 → 4,1; a p. 96 do script (1,8 s nos dois) não tem trama — a da spec é o índice 96, a
  97 impressa, com 123 mil componentes. No livro inteiro são 30 páginas com trama; a mais
  pesada (107, 147 mil componentes), **14,65 s → 0,024 s** só da limpeza, com a mesma máscara.
  Suíte: 3944 passed.
- Commit 2 (R-25): `amostrar` arredonda o passo para cima e não corta (o livro de 41 a 79
  páginas entra até o fim); o Tesseract de um caractere aceita a confiança 0 (o -1 continua
  sendo "não leu") e devolve o primeiro grafema, composto; o cache dos nomes de glifo leva o
  `mtime`; `render_diagrama.esquecer` solta a largura da grade; `pdf_nativo.paginas_pedidas`
  valida o intervalo antes da primeira página, nos dois `extrair` (o negativo lia do fim,
  calado); a tabela da geometria que existe e não se lê fala uma vez (WARNING) e não fica no
  cache. `tests/test_pequenos_da_leitura.py`: contra o código de antes, 14 dos 20 falham (os
  outros seis são os totais que já davam certo e a tabela que não existe). A amostra nos 14
  PDFs desta máquina dá o mesmo veredito (Dvoretsky 39/40 → 38/39, os outros 0); A/B idêntico
  (`RG-16-depois2`); rodada `benchmarks/rodadas/2026-11-25-1636.json`, 0,91% página a página.
  Suíte: 3964 passed. AbbyChessCraft contra o worktree (RG-15 e RG-16): 2915 passed, 6
  failed, os mesmos seis da base.
### RG-16b
Estado: fechada (2026-11-25), em dois commits (`cbc549e` e o do R-23). Base `831e012` (o trabalho do usuário que ela esperava está
no master em `ffc3ec3`), o mesmo worktree.
- Commit 1 (R-24, o cache): `livro._aproximar` lembra a resposta da busca aproximada por
  palavra e idioma, presa ao vocabulário de que saiu, com teto. `tests/test_cache_do_corretor.py`:
  a mesma resposta da busca em 120 palavras (as comuns e as deformadas delas), a repetida
  perguntada uma vez, o idioma à parte. Saída idêntica nas quatro páginas (`RG-16b-antes`/
  `RG-16b-cache`) e em 21 páginas do Aagaard (10–30), que caem de **74,0 para 55,0 s** (3,5 →
  2,6 s por página), com a máquina quieta. Suíte: 3971 passed.
- Commit 2 (R-23): `alfabeto.idioma_normalizado` (`pt-BR`, `pt_BR`, `PT` e `por` são `pt`) é a
  chave em `alfabeto.permitido`, no corretor, nas junções, na legenda da camada e no pacote do
  Tesseract; os remendos de frase (`REMENDOS_DE_FRASE`), o `of'a` e as trocas diretas
  (`arc` → `are`) são do inglês e só valem nele; `_paragrafo_de` e `_agrupar_em_paragrafos`
  recebem o idioma da leitura. `tests/test_idioma_num_lugar.py`: contra o código de antes, 25
  dos 29 falham (os outros são o `pt` e o `en` curtos, que já davam certo). A/B idêntico
  (`RG-16b-depois`); rodada `benchmarks/rodadas/2026-11-25-1703.json`, 0,91% página a página,
  igual às duas bases; em português, *A Estratégia no Xadrez* pp. 40–70, nenhuma palavra muda:
  nenhum dos padrões do inglês aparecia ali. Suíte: 4000 passed, e `slow and not gui` 11
  passed. AbbyChessCraft: 2915 passed, 6 failed, os mesmos seis da base.
- A Onda 6 está fechada. Próximo passo da revisão: a Onda 7 (RG-17, a exportação editorial).
### RG-17
Estado: fechada (2026-11-25), em quatro commits (`c3cfe35`, `3ed62ab`, `9f4d52c` e o do R-36).
Base `a56ebbc`, worktree `.claude/worktrees/onda7`
(destacado, com os pesos copiados). A fase não mexe na leitura: sem A/B.
- Commit 1 (R-32): `EditorialDocument` ordena as páginas por `page_index` na construção
  (estável), `aplicar_revisao` devolve na mesma ordem, e o HTML, o TXT e o PDF deixam de
  ordenar por conta própria; a invariante 10 do `CONTEXT.md` diz a ordem.
  `tests/test_uma_ordem_de_paginas.py`, com as páginas 9, 2 e 5 nos seis formatos, pela
  fachada (com leitura e de volta do IR) e pelo exportador: contra o código de antes falham o
  EPUB, o DOCX e o JSON; HTML, TXT e PDF já ordenavam. O `test_adapter_sem_perdas` que
  comparava byte a byte um EPUB de páginas fora de ordem passa a dá-las em ordem. Suíte: 4020
  passed.
- Commit 2 (R-33): `exportar._filas_retangulares` (a largura da maior fila, as curtas
  completadas, a tabela sem célula pulada) no EPUB e no DOCX; título e idioma vazios levam o
  padrão (`TITULO_PADRAO`, `IDIOMA_PADRAO`) nos dois e no HTML, e o PDF de origem sem título
  deixa o do documento. `tests/test_tabela_titulo_e_idioma.py`: contra o código de antes, os
  dez falham (o `IndexError` da tabela vazia, a célula que sumia, o `<dc:title>` vazio). Suíte:
  4030 passed.
- Commit 3 (R-34): `editorial_export.lado_revisado`, `posicao_revisada` e
  `orientacao_revisada` dizem o que o revisor mudou (contra `decision.original_value`), e valem
  nos dois ramos (as páginas do leitor, `_figura_revisada`, e a volta do IR, `_desenho_velho`),
  no HTML, no TXT e na importação do editor. O lado troca `lado_a_jogar`/`lado_origem` e o
  campo do FEN sem redesenhar — com **uma exceção à letra da spec**: a figura que já é desenho
  e traz o indicador do lado de antes se redesenha, senão o arquivo diria as duas coisas; o
  recorte nunca. A orientação só redesenha o que é desenho, e a posição, sempre (no ramo do IR
  o recorte com a posição trocada saía com o desenho velho; o HTML também). `_redesenhar` leva
  o indicador e as marcas, que apagava. `revisao_pendente` pergunta primeiro à decisão; o mapa
  do lado tem todas as origens (`"usuario"` ↔ `manual`), e o `ambiguous` não volta como lido.
  - Achado: o diálogo da fila gravava só o `fen`, e o lado que o revisor marcava ficava no
    campo dele, com o `side_to_move` velho ao lado. Os diários já gravados são assim, e por
    isso o lado se deduz também do campo que **mudou** — o `w` que já estava é convenção; o
    diálogo passa a gravar os campos (`com_fen_revisado`).
  - `tests/test_revisao_do_diagrama.py`: contra o código de antes (com substitutos para os
    nomes novos), 27 dos 31 falham; os outros são guardas (aceitar não inventa lado, o
    pendente continua pendente, desfazer). Um teste do diálogo passa a esperar os campos do
    lado. Numa execução avulsa, `test_dialogo_revisao_editorial` teve uma falha que não se
    repetiu em dez (cinco no código novo, cinco no de antes) nem na suíte; a mensagem não foi
    guardada. Suíte: 4061 passed.
- Commit 4 (R-36): `Paragrafo.papel` (`header`/`footer`/`caption`) volta do IR e vai de novo;
  no EPUB e no DOCX o cabeçalho e o rodapé ficam fora do corpo (o relatório diz quantos) e a
  legenda sai como legenda; a imagem da página loga a falha e confere o `source_sha256` uma
  vez (o PDF trocado no mesmo caminho não dá imagem); `page_id` casa o resultado com a página;
  `faixas_do_estilo` é uma só; e há **uma `ExportOptions`** (a de `editorial_export`, com
  `paginas` revisadas, fixada por teste), um `ExportReport` e um conjunto de formatos: a
  janela passa a aplicar a revisão antes de chamar a fachada.
  - O item do `page_id` não muda resultado: `from_pages` já recusa índice repetido e o
    enriquecimento grava o índice por cima, de modo que não achei cenário que falhasse; ficou a
    chave única pedida, e o teste (fora de ordem, com uma página que levanta) é guarda.
  - `tests/test_pequenos_do_editorial.py`: contra o código de antes, oito dos onze falham (os
    outros são guardas: sem identidade a imagem sai, o casamento por página, o JSON padrão). O
    `test_pd21` que fixava as páginas cruas passa a fixar as revisadas. Suíte: 4072 passed.
- `slow and not gui`: 11 passed. AbbyChessCraft contra o worktree: 2915 passed, 6 failed, os
  mesmos seis da base (o `Paragrafo` ganhou um campo no fim, com padrão).
- A Onda 7 está fechada. Próximo passo da revisão: a Onda 8 (RG-18 e RG-20, depois a RG-19).
### RG-18
Estado: fechada (2026-11-25), num commit. Base `65a096b`, worktree `.claude/worktrees/onda8`
(destacado, com os pesos copiados), o mesmo da RG-20 e da RG-19.
- Os `except` largos de `ui` de corpo só `pass`: 17 em 2026-11-20, **16 ao abrir** (o do cursor
  em `operacoes.py` já tinha ido na RG-13) e **1 ao fechar**, o do rótulo de espera em
  `ui/editor/xadrez.py`, justificado na lista nominal que a varredura por AST confere.
- Cada item da lista fala: WARNING onde a saída ou a preferência muda (o árbitro do texto
  girado, a amostra que não se lê, a linha que não é box, o rascunho, os pesos do EasyOCR e do
  Paddle, o recorte recusado, a imagem e a ênfase do IR, a preferência que não grava ou não se
  lê, a sondagem da camada, os motivos da suspeita, o gancho do token), INFO no que se espera e
  DEBUG no que só interessa a quem depura; `uma_vez` no que se repete. As capturas se
  estreitaram ao que o comentário justifica: o cancelamento e o erro de programa passam pelo
  árbitro, e o `KeyError`/`TypeError` do Paddle sobem. Duas contas se corrigem: `prune` só soma
  o byte que saiu, e `aplicar_payload` só conta a página que voltou (a barra de status dizia
  recuperada a descartada).
- `tests/test_silencios_que_falam.py`: contra o código de antes, 28 dos 30 falham (os outros são
  guardas do silêncio: o arquivo inteiro não avisa). Na primeira suíte, um dos testes falhou por
  outro ter posto o tronco do log em INFO; consertado no teste.
- A/B das quatro páginas idêntico (`RG-18-antes`/`RG-18-depois`); rodada
  `benchmarks/rodadas/2026-11-25-1815.json`, 0,91% página a página. Suíte: 4102 passed.
### RG-20
### RG-19

## Re-análises deste documento

| Rodada | Lente | Achados | Efeito |
|---|---|---|---|
| Crítico (2) | mérito dos requisitos | — | v0.1 → v0.2 (fases RG-21 e RG-22 saíram com R-45 e R-47) |
| 1 | verdade factual: ~100 afirmações | 4 (contagem de `return`, `pieces/` já na constante, a RG-11 de então não mexe em `extrair_pagina`, quatro entregas mais curtas que o requisito) | corrigidos |
| 2 | coerência e sequência | 33 (9 de dependência, 1 que fecharia a RG-03 vermelha, 10 de pronto verificável, 3 da regra da ordem, 3 da casa) | v0.3: ordem por dano (a fidelidade do editor subiu para a Onda 4), dependências completas, fases renumeradas |
| 3 | exequibilidade nesta máquina | 18 (4 que parariam o plano: documentos fora do git, pronto dependente de push, `ff-only` contra o diff do usuário, paralelo sem `rebase`) | v0.4: commit dos documentos antes da RG-01; RG-01b, RG-02a/b e RG-16b; comandos exatos de A/B, rodada e wheel; registro aberto no primeiro commit |
| 4 | o que o plano esqueceu | 6 lacunas (3 bloqueantes: o AbbyChessCraft, a régua de "sem piora", o fim da revisão) | v0.5: passo 10 e a tabela do AbbyChessCraft; "sem piora" e "se piora"; "Desfazer uma fase"; "Quando a revisão fecha"; numeração das PD; invariantes e gate no commit de cada fase; RG-05b e R-52/R-55 na RG-05 |
| 5 | leitura final: correspondência por script (50 requisitos, cada um numa fase), consistência, forma, codificação | 21 (4 contradições: a RG-19 escrevendo o que o passo 2 manda escrever na fase, "Desfazer" prometendo prontos que as fases não tinham, `split_box`/`clamp_box` fora da tabela do AbbyChessCraft, o passo 10 só numa fase; 12 de consistência e completude; 5 de forma) | v0.6: corrigidos, mais os ajustes de R-52 a R-55 da spec; UTF-8 sem BOM, LF, sem mojibake |
