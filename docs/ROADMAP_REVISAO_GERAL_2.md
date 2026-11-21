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
Estado: em andamento. Base `a2bfc82`, na árvore principal (os arquivos da fase não têm
diff do usuário).
- Commit 1 (os `return` nus): `tests/test_testes_honestos.py` falhou primeiro com os 29
  `return` de 27 testes, a contagem da spec; trocados por `pytest.skip` com motivo. Na
  exportação limpa do `HEAD` pulam 6 dos 11 de dado — `training_data/`,
  `ilovepdf_pages-to-jpg/*0021.jpg` e a página 0108 ficam fora do git; os outros cinco
  dependem do `model_meta.json`, que é rastreado, e de fontes do Windows, presentes aqui
  (na CI Linux pulam). Os 16 de display pulam com o motivo quando a falta de display é
  simulada (`raiz_tk` → `None`, `TEM_DISPLAY = False`, por um plugin de pytest de
  conferência): 16 skipped, 8 passed. Suíte da exportação limpa: 3637 passed, 28 skipped.
- Próximo passo: commit 2 (as quatro asserções fracas e o golden).
### RG-01b
### RG-02a
### RG-02b
### RG-03
### RG-04
### RG-05
### RG-05b
### RG-06
### RG-07
### RG-08
### RG-09
### RG-10
### RG-11
### RG-12
### RG-13
### RG-14
### RG-15
### RG-16
### RG-16b
### RG-17
### RG-18
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
