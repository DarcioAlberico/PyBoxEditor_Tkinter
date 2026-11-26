# Spec — Revisão geral 2

Versão: 0.6 (veredito dos críticos e cinco re-análises aplicados)
Data: 2026-11-20
Estado: fechada em 2026-11-25 (R-39 e R-42 transferidos para a PD-26 e a PD-27, fechadas no mesmo dia)
Base: `master` em `6627e30`; números de linha da árvore de trabalho do mesmo dia
Roadmap: [ROADMAP_REVISAO_GERAL_2.md](ROADMAP_REVISAO_GERAL_2.md) (fases `RG-nn`)
Antecessora: [ANALISE_GERAL_2026-10-06.md](ANALISE_GERAL_2026-10-06.md) (a revisão geral 1)

## 1. O que é e o que não é

Levantamento de defeitos do produto inteiro, feito por oito revisões independentes
(leitura OCR, documento editorial e exportação, editor de livros, interface e threads,
falhas silenciosas, segurança de entrada, testes e CI, métricas e documentação), cada
uma com scripts de prova, e julgado requisito a requisito por dois críticos que
conferiram cada arquivo:linha no código — e, para os R-52 a R-55, achados depois, pela
re-análise 5 (§7). Esta spec diz **o que tem de ser verdade**
quando a revisão fechar; o roadmap diz em que ordem e como se prova.

Fora do escopo:

- a Onda 6 da [ROADMAP_PENDENCIAS.md](ROADMAP_PENDENCIAS.md) (PD-15…19): depende de
  rótulo, transcrição ou retreino, e ninguém a simula;
- o trabalho em andamento do usuário na árvore (`core/livro.py`, `docs/ROADMAP_OCR.md`,
  `tests/test_lance_descritivo.py`): os achados nele vão à §8 como observação; o R-23 e o
  cache do R-24, que mexem no trecho do diff dele, esperam o commit dele;
- mudar a leitura sem número: todo requisito do tema E que muda a saída só fecha com o
  A/B das páginas de referência e a rodada do corpus;
- partir função grande sem defeito (§7, R-45 recusado);
- editar o AbbyChessCraft, o outro aplicativo, que importa este `core` da árvore
  principal pela instalação editável dele: nenhum requisito muda a assinatura de um nome
  público que ele usa (princípio 8).

## 2. Linha de base medida (2026-11-20)

| Medida | Valor |
|---|---|
| Suíte `-m "not slow"` no `HEAD` limpo | 3640 passed, 22 skipped, 18 deselected, 6 min 19 s |
| `ruff check core ui appy.py config scripts`, `compileall` | limpos |
| Código de produto, árvore de trabalho (sem `core/biblioteca/`) | 197 módulos, 95.808 linhas |
| Maiores módulos | `livro.py` 4.545 (4.495 no `HEAD`; o resto é trabalho do usuário), `texto_rico.py` 3.590, `janela.py` 3.057, `pdf_nativo.py` 3.045 |
| Complexidade ciclomática > 15 / > 25 (`ruff` C901) | 81 / 17 funções (pior: `ocr_training.treinar_pacote` 47) |
| Funções com mais de 150 linhas | 18 (piores: `treinar_pacote` e `livro.extrair_pagina`, 397 cada) |
| Cobertura de linhas (`not slow`, `core`+`ui`+`config`, sem `core/biblioteca/`) | 88 % (53.567 instruções, 6.378 sem execução) |
| CRAP por função (McCabe aproximado por AST × essa cobertura) | 4.579 funções; 731 acima de 10, 130 acima de 30 |
| Piores CRAP | `Reconhecimento.auto_fill_characters_linha_treinada` 319 (cobertura 2 %), `ui/editor/busca.chave_do_cursor` 270, `CanvasView.on_left_drag` 196, `Reconhecimento.validar_notacao` 194, `exportar_livro_action.concluir` 191 |
| Duplicação | baixa: 12 grupos de clones exatos de 8–12 linhas |
| Ciclos de importação no topo do módulo | 0 (todos os 17 diretos fecham por import tardio) |
| `except` em produção (`core` sem `core/biblioteca/`, `ui`, `config`, `appy.py`) | 573 handlers, 514 que não relançam, dos quais 459 sem chamada de `log`/`uma_vez` no corpo; a maioria é legítima (`TclError`, falha devolvida por outro canal) |
| Wheel construído do `HEAD` | sem as fontes de `fonts/`, sem `pieces/` e sem `config/profiles/` |
| Testes que passam sem medir nada | 27 saem por `return` nu quando falta dado (11) ou display (16) |
| CER público (README) | 1,59 % em 2026-09-26; a rodada de 2026-11-19 (`benchmarks/rodadas/2026-11-19-1805.json`) dá 0,91 %, mas sobre outro corpus e outra régua de alinhamento — **não são comparáveis** |

## 3. Princípios

1. **Uma decisão mora num lugar.** Onde o mesmo cuidado aparece em dez arquivos (escrita
   atômica, caminho seguro, saneamento de texto, normalização de idioma, "há tarefa
   rodando"), o requisito é a função única e a troca dos chamadores, não dez remendos.
2. **A causa, não o sintoma.** Um `try` que esconde o crash não fecha requisito.
3. **Teste primeiro, e que falhe pelo motivo certo.** Todo requisito traz o teste que
   falha hoje; teste que passaria com a função devolvendo nada não conta. Exceção:
   documentação (tema K) e limpeza sem mudança de comportamento, que fecham pelo lint e
   pela suíte verde.
4. **Medido, não estimado.** Leitura: A/B e corpus. Desempenho: tempo antes e depois na
   mesma máquina. Fidelidade do editor: cenário mínimo por atributo, e a contagem num
   corpus como medida registrada.
5. **Tirar antes de pôr.** Código morto, marcador sem uso e duplicata saem antes de
   qualquer abstração nova; abstração nova só quando um defeito a pede.
6. **Função grande se parte quando um requisito já a abre**, com o comportamento fixado
   antes; o CRAP da §2 é medida para escolher onde pôr teste, não meta.
7. **Toda varredura por AST usa lista nominal.** O que existe hoje e fica entra numa
   lista com justificativa; o teste falha com qualquer ocorrência fora dela. Assim o
   aceite falha hoje (a lista começa só com o que o requisito decide manter) e não
   envelhece.
8. **O `core` tem outro cliente.** O AbbyChessCraft chama `pdf_nativo.extrair`,
   `juntar_entre_paginas`, `lados_pelos_lances`, `amostrar`, `OCRService`,
   `render_diagrama.carregar`, `BoxService.sort_boxes_reading_order`,
   `notacao.e_token_de_notacao`, auxiliares de `core.exportar` e alguns nomes privados
   com contrato (`tests/test_contrato_do_core.py` e `test_privados_do_core.py`, lá). Nome
   público que ele usa não muda de assinatura nem some — muda de lugar com delegado;
   campo novo em `PaginaExtraida`/`Paragrafo` tem padrão; a P-2 é conferida pela suíte,
   nunca por `assert` no tipo.

## 4. As causas raiz

Os temas estão agrupados por afinidade; a causa vale para o requisito principal de cada
um.

| Causa | Temas | Exemplo |
|---|---|---|
| C1. Cada gravador grava do seu jeito | A | `.tmp` de nome fixo disputado por dois processos; `os.replace` com recurso faltando |
| C2. A entrada não é conferida na fronteira | B, J | `../` do zip vira arquivo fora da pasta; `\x0c` vira XHTML inválido; `training_data` resolvido no cwd |
| C3. O diário de revisão não tem identidade nem transação | C | diário de outro livro reaproveitado; linha truncada zera a sessão de revisão |
| C4. A tarefa trabalha sobre estado vivo e não tem dono | D | resultado aplicado por posição depois de o usuário apagar um box; `after` que sobrevive à janela |
| C5. A leitura decide a mesma coisa em vários lugares | E | medidas da linha mantidas à mão em oito funções; passadas de livro em dois caminhos; idioma normalizado de três jeitos |
| C6. Ida e volta "no dialeto" sem contar a perda | F | `<li id="fn1">` volta como `<li>` |
| C7. Cada escritor decide por si a ordem e o quanto da decisão lê | G | TXT e EPUB em ordens diferentes; lado revisado ignorado |
| C8. A falha não deixa rastro | H | 459 handlers sem log, alguns mudando a saída |
| C9. O gate não vê o que deveria | I | wheel incompleto e teste que passa sem dado, ambos verdes na CI |
| C10. O que se guarda diverge do que o usuário vê | A (R-52 a R-55) | o PNG da página regravado em cinza; cache do k-NN que diz estar em dia; rascunho sem a ponte |
| — | K | documentos que ficaram para trás do código (não é defeito do produto) |
| — | L | import pesado no topo do módulo força cópia de código |

## 5. Requisitos

Notação:

- **Sev.**: *alta* = perda ou corrupção de dado do usuário, ou saída errada calada de
  alcance amplo, em fluxo normal; *média* = saída errada pontual, falha visível,
  travamento, risco de segurança que exige condição externa, ou desempenho que impede o
  uso; *baixa* = só pela API, cosmético, ou infraestrutura de desenvolvimento.
- **Prova**: `script` (reproduzido por um revisor ou pelo crítico), `lido` (no código).
- Os números são os da primeira versão e não se reaproveitam: R-35 e R-45 foram
  recusados, o R-47 virou a §10, R-49 e R-50 nunca foram usados; R-48 (desmembrado do
  R-25), R-51 (pedido pelo crítico) e R-52 a R-55 (achados na re-análise 4) moram no tema
  do assunto; no tema F, R-27 vem antes de R-26 porque é feito antes.
- O veredito de cada um está na §7.

### Tema A — O dado do usuário (C1; C10 nos R-52 a R-55)

**R-01. Uma só escrita atômica.** Sev. média. Prova: lido; script no `formato_box`.
- Evidência: `.tmp` de nome fixo em `config/settings.py:53` (a janela principal e o
  `appy.py --editor`, processos diferentes, gravam o mesmo `settings.json.tmp`),
  `core/editor/projeto.py:326`, `core/editor/pdf_io.py:328`,
  `core/services/document_service.py:77`, `core/editorial_model.py:471-478`
  (`save_json`), `core/editorial_export.py` (`_gravar_atomico`), `core/lexico.py:213`,
  `core/linha_review.py:37` (`.txt.tmp`), `core/ocr_corpus.py:290`,
  `core/ocr_runtime.py:170` (`with_suffix(".tmp")`), `core/linha_trainer.py:730`/`:741`
  e `core/ocr_phase7.py:273`; gravação direta, sem temporário, em
  `core/editor/txt_io.py:167`, `html_io.py:431`, `pgn_io.py:230`, `buscas_salvas.py:161`,
  `clipes.py:176`, `editorial_export._pdf` (`:574`, `pdf.save(target)`),
  `core/formato_box.py:223-224` (abre o `.box` com `"w"` antes de montar o conteúdo: uma
  exceção na formatação zera o arquivo — provado, de 15 para 0 bytes) e o PNG do par em
  `ui/documento.py:752`; sem `fsync` em `core/editor/epub.py:947`. São vinte e dois
  pontos.
- Exige: um módulo do `core` com duas formas — `gravar_atomico(caminho, conteudo)` para
  bytes ou texto, e `with escrita_atomica(caminho) as f:` para quem grava em fluxo (o zip
  do EPUB e do DOCX); se o bloco levanta, o temporário é descartado e o destino não muda.
  Ambas: temporário único na mesma pasta (`mkstemp`), `flush` + `os.fsync` (com
  `duravel=False` para cache descartável, como o de `ocr_runtime.py:170`), `os.replace`
  com nova tentativa breve quando o Windows o recusa porque outro processo lê o arquivo,
  LF no texto, modo do destino preservado (arquivo novo com `0o666 & ~umask`, não o 0600
  do `mkstemp`). Os vinte e dois pontos passam por ela (o `formato_box` monta o texto
  antes de abrir), e também os três que já usam `mkstemp` por conta própria
  (`core/exportar.py:795`, `:1384`, `core/editor/docx_io.py:294`). O diário de revisão,
  que só acrescenta, fica fora (R-09).
- Aceite: para cada um dos vinte e dois, a escrita interrompida no meio deixa o original
  intacto e nenhum temporário; teste por AST sobre `core`, `ui` e `config` recusa `+
  ".tmp"`, `with_suffix(... ".tmp")` e `mkstemp` fora do módulo da escrita atômica (lista
  nominal vazia); o tempo do rascunho do editor, que grava na thread do Tk a cada 60 s,
  medido antes e depois.
- Severidade: média, porque a perda exige queda do processo ou duas gravações no mesmo
  instante.

**R-02. Preferências e buscas salvas não se perdem.** Sev. alta. Prova: script.
- Evidência: `config/settings.py:68` trata `PermissionError` como JSON corrompido e o
  `save` seguinte grava o dicionário novo por cima de tudo (reproduzido: o arquivo
  inteiro vira `{'x': 1}`); `ui/editor/janela.py:2810` regrava a chave `editor` inteira a
  partir de cópia velha (reproduzido: dois editores abertos, `buscas_salvas` some), e
  `core/editor/clipes.py:172` e `projeto.py:441` gravam a mesma chave do mesmo jeito;
  `core/editor/buscas_salvas.py:86`/`:93` descarta a busca salva que não entende (sem
  `nome`, ou com opção desconhecida) e o próximo `gravar` a apaga do disco.
- Exige: `OSError` na leitura não autoriza gravar; JSON inválido é guardado ao lado
  (`.corrompido`) com `log.warning`; o `save()` relê o disco e, quando o valor do disco e
  o novo são dicionários, mescla um nível abaixo — o que cobre os três gravadores da chave
  `editor` sem API nova; a busca salva ilegível é guardada como veio e regravada intacta.
  O `test_fase9_settings_atomicos.py:69` muda de comportamento e é atualizado junto.
- Aceite: os três cenários como teste (o terceiro com uma chave desconhecida dentro de
  `opcoes`).

**R-03. O EPUB salvo não perde recurso.** Sev. alta. Prova: script.
- Evidência: `core/editor/epub.py:695-699` transforma recurso ilegível (`dados_de`,
  `:189-206`) em aviso e o `os.replace` (`:947`) acontece mesmo assim;
  `core/editor/livro_ops.py:163-240` (`renomear` → `_reescrever_hrefs`) troca
  `recurso.caminho` sem carregar os bytes, e `dados_de` procura o nome novo no zip antigo.
- Exige: por padrão a montagem levanta, dentro do `with escrita_atomica(...)` (R-01),
  com a lista dos itens do manifesto que não se leem, e o destino não muda; uma opção
  explícita "salvar sem estes recursos" substitui o aviso de hoje, para que o usuário cujo
  zip de origem foi movido não fique sem poder salvar (o checkpoint, `projeto.py:239`, e a
  diferença, `:264`, seguem a mesma regra); o `Recurso` guarda o nome de origem no zip e
  `dados_de` lê por ele, o que conserta `renomear` e `renomear_varios` (os dois passam por
  `_reescrever_hrefs`, `livro_ops.py:163`) sem carregar os bytes.
- Aceite: EPUB de origem apagado depois de aberto → salvar falha com a lista e o destino
  não muda, e com a opção explícita salva sem eles; renomear `Images/fé.png` e salvar → a
  imagem está no zip.

**R-04. O rascunho não some antes da hora.** Sev. média. Prova: lido; script na página
esvaziada.
- Evidência: `ui/documento.py:69-94` (`_confirm_discard`, descarte em `:92`) apaga o
  rascunho ao responder "Descartar", antes do seletor de arquivo (`:183`, `:264`,
  `:268`); `core/services/document_service.py:82` só mostra a falha de gravação no status,
  que é sobrescrito logo; `document_service.py:222` loga em DEBUG a falha de
  `remover_autosave` (o rascunho velho reaparece como "recuperar trabalho");
  `ui/editor/janela.py:2910` deixa o `OSError` do rascunho impedir o fechamento; a página
  da qual o usuário apagou todos os boxes não conta como suja nem entra no rascunho
  (`document_service.py:133-138`, `:211-212`; `ui/documento.py:605`, `:681`): não há como
  salvá-la vazia ("Nada para salvar"), o `.box` antigo fica e o rascunho velho volta a
  oferecer os boxes apagados (provado); o editor restaura o rascunho mostrando só a hora
  (`ui/editor/janela.py:748-761`), sem comparar com o EPUB do disco — se ele foi editado
  por fora depois do rascunho, aceitar e salvar sobrescreve a edição externa.
- Exige: ao abrir outro arquivo, o rascunho só é descartado quando a sessão nova existe;
  ao fechar a janela (`_on_close`), onde não há sessão nova, ele sai no `destroy`; falha
  de gravação do rascunho é WARNING (`uma_vez` por caminho) e indicação persistente;
  falha de `remover_autosave` é WARNING; falha do rascunho no fechamento do editor loga e
  fecha; a página esvaziada conta como suja, entra no rascunho e salva vazia; o editor
  avisa, ao oferecer o rascunho, quando o EPUB do disco é mais novo que ele.
- Aceite: cancelar o seletor depois de "Descartar" mantém o rascunho; falha do gravador
  (`:82`) e de `remover_autosave` geram WARNING (`caplog`); `OSError` no rascunho do
  editor não impede o fechamento; apagar todos os boxes de uma página e salvar deixa o
  `.box` vazio; rascunho mais velho que o EPUB é oferecido com aviso.

**R-52. Salvar o `.box` não sobrescreve a imagem de origem.** Sev. alta. Prova: script.
- Evidência: `ui/documento.py:752` (`_write_box_pair`) grava `image.save(<destino>.png)`
  com a imagem em memória, que `open_image` guarda convertida para cinza
  (`img.convert("L")`); o destino sugerido do `.box` é o nome da imagem aberta
  (`_destino_sugerido`, `:596-602`), porque numa sessão de imagem `page_stem` devolve o
  próprio nome dela (`document_service.py:315-317`). Abrir `pagina.png` e salvar com o
  nome padrão grava `pagina.png` por cima do scan original — provado pela rota real
  (`open_image` → `_destino_sugerido` → `_write_box_pair`): o original RGB a 600 dpi volta
  como `L` e sem dpi —, sem pergunta, no Ctrl+S e no "Salvar todas". Viola a invariante 1
  do `CONTEXT.md`.
- Exige: quando o PNG do par é o próprio arquivo de origem — `os.path.samefile`, se ele
  existe; senão, `normcase(realpath)` dos dois (o caminho absoluto não basta: aberto
  `Outra.PNG`, o par `Outra.png` é o mesmo arquivo no Windows, e os nomes curtos como
  `WAGNER~1` também enganam) —, ele não é regravado, e o aviso de sucesso não o lista como
  gravado; o `.box` sai ao lado dele, como hoje.
- Aceite: abrir um PNG colorido com dpi, salvar com o nome padrão: os bytes do PNG não
  mudam e o `.box` está ao lado; o mesmo no "Salvar todas" de uma sessão de imagem e com
  a origem `Pagina.PNG`; com a origem num PDF, o par continua saindo inteiro.

**R-53. A base de treino reflete o que o usuário promoveu, uma vez só.** Sev. média.
Prova: script.
- Evidência: `core/learner.py:385-394` (`salvar_cache`) grava a impressão digital do
  disco no momento de gravar, não a do momento da carga, e `core/coleta.py:587`
  (`promover`) cria um `CharacterLearner` próprio que nunca salva o cache: promover
  recortes e depois "Aprender com a página" faz o learner vivo, que não viu os PNGs
  novos, gravar um cache que diz estar em dia — a sessão seguinte o carrega sem as
  amostras (provado: com três PNGs de `lower_b` no disco, o k-NN novo não conhece `b`);
  `ui/treino.py:211` promove com `apagar=False` e `learner.py:460-464` dá UUID novo na
  colisão, de modo que promover a mesma pasta duas vezes duplica as amostras no disco (3
  → 6); o k-NN deduplica na leitura (`learner.py:330-355`), o treino da rede não.
- Exige: o learner conhece a impressão digital da carga mais as amostras que ele mesmo
  gravou, e `salvar_cache` grava essa — e não grava quando a do disco diverge dela (INFO)
  — em vez de "a da carga" pura, que faria a sessão seguinte a qualquer "Aprender" reler a
  base inteira (os 141 s que o cache existe para evitar); a janela promove pelo learner do
  serviço (`learning_service._get_learner()`), e a promoção salva o cache (sem learner,
  salva o próprio); a promoção pula o recorte cujos pixels (forma e bytes) a classe já
  tem e conta os pulados no `Promocao`.
- Aceite: os dois cenários como teste; aprender uma página e reabrir carrega do cache, sem
  reler o disco.

**R-54. Box fora da página não entra, e clique não é edição.** Sev. média. Prova: script.
- Evidência: `ui/canvas_view.py:488-492` (mover), `:522-523` (redimensionar) e `:539-545`
  (box novo) não limitam o box à imagem, e `BoxService.clamp_box` não tem chamador:
  arrastar um box para fora da página dá coordenadas negativas, o recorte sai vazio e
  `cv2.resize` levanta em `learning_service.py:85`/`learner.py:445`, abortando o
  "Aprender" no meio do lote (a amostra do primeiro box fica gravada, a do terceiro não, e
  o cache não é salvo); `core/services/box_service.py:2320` (`split_box`) num box de 1 px
  gera box de largura zero; `canvas_view.py:551-552` faz commit no histórico a cada
  clique sem movimento — selecionar um box suja a página, e 50 cliques expulsam o
  histórico real pelo limite de `history_service.py:72-73`. Pior que o recorte vazio: um
  box inteiro fora da página, à esquerda ou acima, não falha — o fatiamento com índice
  negativo dá a volta (`core/vertical.py:144`) e o recorte sai com tinta do outro lado da
  página, aprendida em silêncio com o rótulo do box. E o `clamp_box` só é chamado por um
  teste (`test_f10_negativo.py:449`) e perde `margem` e `moldura`: usado como está,
  apagaria os dois a cada arrasto.
- Exige: `recorte_de_pe` limita o box à imagem e devolve vazio para o que sai dela (um
  lugar só, para todo classificador, inclusive `.box` carregado de fora); o aprendizado
  pula recorte vazio e conta; o canvas limita o box à imagem — mover para na borda sem
  mudar o tamanho, redimensionar e box novo cortam na borda — por um `clamp_box`
  corrigido para preservar todos os campos (`dataclasses.replace`); `split_box` recusa
  largura menor que 2 devolvendo o box inteiro, sem levantar (o AbbyChessCraft chama
  `split_box` e `clamp_box`); o `release` só faz commit se as coordenadas mudaram, o que
  também serve à regra de "suja" do R-19.
- Aceite: os cinco cenários como teste, inclusive o box inteiro à esquerda da página, que
  não vira amostra.

**R-55. O rascunho restaura tudo.** Sev. média. Prova: script.
- Evidência: `core/editor/projeto.py:407-419` (`Rascunho.restaurar`, chamado em
  `ui/editor/janela.py:761`) não chama `religar_documento_editorial()`: recuperado o
  rascunho de um livro vindo do documento editorial, o `gravar_eventos` é pulado
  (`projeto.py:189`) e as correções não vão ao diário, sem aviso (provado: aberto do disco
  a ponte liga; restaurado do rascunho, não); `core/services/document_service.py:188-192`
  (`montar_payload`) e `:271-273` (`aplicar_payload`) levam só oito campos do box, e
  `negativo`, `moldura` e `margem` se perdem na recuperação — o `.box` salvo em seguida
  perde o campo 8; e o projeto restaurado tem `relatorio=None`, de modo que o aviso de
  `religar_documento_editorial` (`projeto.py:144-145`) se perderia mesmo depois do conserto.
- Exige: `restaurar` religa a ponte, e a falha em religar vai ao log (WARNING) e ao
  usuário; o rascunho da janela principal grava `BoxEntry.as_state()` e lê por
  `from_state` (que já aceita o estado curto do rascunho antigo), com o fator de escala
  aplicado depois.
- Aceite: os dois cenários como teste; rascunho antigo, de oito campos, continua
  carregando.

### Tema B — Fronteira de entrada (C2)

**R-05. Um só caminho seguro.** Sev. alta. Prova: script.
- Evidência: `core/editor/html_io.py:465-477` (`escrever_pasta`) grava em
  `os.path.join(pasta, *href.split("/"))` sem conferir: um EPUB com `../../ESCAPOU.txt`
  gravou fora da pasta, e um EPUB legítimo com OPF em `OEBPS/opf/` e capítulos em
  `../Text/` também escapa; `epub.py:152-155`, `:524-528`, `:701` regravam entradas `..`
  e absolutas; `html_io.py:862` (`_trazer_do_disco`) embute qualquer arquivo legível.
- Exige: `caminho_seguro(raiz, relativo)` único, que recusa o que sai da raiz, caminho
  absoluto, UNC e letra de unidade. A pasta HTML grava pelo nome da entrada no zip
  relativo ao `commonpath` dos `nome_no_zip` do livro (o que dá o leiaute de hoje no caso
  comum, sem `OEBPS/` na frente), passando por ele; a leitura do zip recusa a entrada que
  sai da raiz do pacote; `_trazer_do_disco` aceita relativo de qualquer profundidade
  (`../img/` de HTML legítimo em subpasta), recusa absoluto, UNC e letra de unidade, e só
  embute extensões de recurso (imagem, CSS, fonte) — é a lista de extensões que protege,
  porque o importador recebe um arquivo, não uma pasta.
- Aceite: os quatro cenários como teste (`../../ESCAPOU.txt`; o EPUB legítimo com
  `../Text/` exporta dentro da pasta, com o leiaute de `test_editor_html.py:92-113`;
  entrada `..` no zip recusada; HTML que aponta para `C:\…\segredo.txt` ou para
  `../../x.txt` não o embute, e `../img/a.png` embute).
- Severidade: alta, porque o EPUB legítimo com `../Text/` grava fora da pasta em fluxo
  normal, sem arquivo malicioso nenhum.

**R-06. Tetos na leitura de pacote.** Sev. média. Prova: script.
- Evidência: `core/editor/docx_leitura.py:200` lê o zip inteiro (DOCX de 306 KB → pico de
  631 MB); `epub.py:203`, `:474`, `:496` sem olhar `file_size`; `docx_leitura.py:205`
  deixa `ParseError` subir cru (a UI em `ui/editor/conversoes.py:223` não o trata);
  `epub.py:260` não abre OPF com `&nbsp;` (`undefined entity`).
- Exige: teto por entrada e total (somando `ZipInfo.file_size`) com mensagem; `ParseError`
  vira o `ValueError` do contrato; o OPF usa o mesmo analisador tolerante a entidades dos
  capítulos.
- Aceite: os três cenários como teste.

**R-07. Texto legal em XML na fronteira dos escritores.** Sev. média. Prova: script.
- Evidência: `core/exportar.py` (`_xhtml_da_pagina`) grava `"linha\x0c fim"` e o XHTML sai
  mal formado (`ParseError`); `para_docx` levanta `ValueError: All strings must be XML
  compatible` e a exportação cai; `core/editor/xhtml.py:1520` idem, e `\ud800` levanta
  `UnicodeEncodeError`; `core/editor/txt_io.py:358-361` lê UTF-16 como cp1252. A entrada
  real do caractere não foi demonstrada no OCR (que usa `image_to_data`); as portas são a
  camada do PDF e o TXT, HTML e DOCX importados — o requisito é defensivo, na fronteira.
  Precedente: o AbbyChessCraft já filtra exatamente esse conjunto (`_FORA_DO_XML`, em
  `abbychess/epub.py:60`); a função daqui sai pública, como oferta a ele.
- Exige: uma função `texto_legal_em_xml()` (tira C0 menos `\t\n\r`, U+FFFE/FFFF e
  surrogates soltos; a contagem vai ao log em WARNING, `uma_vez` por arquivo) chamada
  pelos dois escritores e pelos importadores do editor, sempre onde o texto vira nó XML
  (por trecho ou por run), nunca antes do cálculo das faixas de negrito e itálico, que
  ficariam deslocadas; o TXT detecta BOM UTF-16.
- Aceite: `"linha\x0c"` exporta EPUB que o `ElementTree` lê e DOCX que o `python-docx`
  grava; o editor salva EPUB legível com um bloco que tinha `\x0c`; TXT UTF-16 importa
  legível.

**R-08. Dependências com teto.** Sev. baixa. Prova: lido.
- Evidência: `requirements.txt` e `pyproject.toml` sem teto nas dependências que leem
  arquivo de terceiro — só o OpenCV (`<5`) e o PyInstaller (`<7`) têm (o PyMuPDF 2.x já
  quebrou a CI em `295f9c6`); `scripts/medidas/calibrar_modelo.py:38` usa `torch.load`
  sem `weights_only=True`. Os dois OpenCV ficam: o `easyocr` exige o `-headless`.
- Exige: teto de versão maior no PyMuPDF, no Pillow e no python-docx; um
  `constraints.txt` só das dependências declaradas, validado na matriz da CI (não tirado
  do `.venv`, que tem pacotes do Windows e experimentais); `weights_only=True` no script.
- Aceite: a CI instala com `-c constraints.txt` e fica verde nas versões da matriz.

**R-48. Nunca desligar a verificação TLS do processo.** Sev. média. Prova: lido.
- Evidência: `core/services/ocr_service.py:516-538` troca
  `ssl._create_default_https_context` por `_create_unverified_context` para o processo
  inteiro **durante** o download dos pesos do EasyOCR, que depois são desserializados — um
  intermediário na rede pode trocar o peso; o `finally` (`:537`) restaura o contexto, mas
  o remendo não é seguro entre threads (a segunda pode guardar o contexto já sem
  verificação como "anterior" e deixá-lo assim) e acontece mesmo com os modelos já em
  disco; o cache de leitores não tem trava. O `test_f16_easyocr.py:193-213` hoje **exige**
  o remendo ligado durante o download.
- Exige: sem troca do contexto global (o contexto padrão no Windows já carrega o
  repositório de certificados do sistema); se o download falhar por certificado, a
  mensagem diz como instalar os pesos à mão; cache de leitores com `Lock`.
- Aceite: durante o `Reader` simulado, `ssl._create_default_https_context` não é
  `_create_unverified_context` — o que inverte o `assert` de `test_f16_easyocr.py:203`,
  atualizado junto.
- Severidade: média, porque a exploração exige um intermediário na rede no momento do
  download.

### Tema C — Diário de revisão (C3)

**R-09. Leitura tolerante.** Sev. alta. Prova: script.
- Evidência: `core/editorial_review.py:351-352` (`read`) usa `splitlines()`, que quebra em
  U+2028 — editar um bloco para `Hello\u2028world` torna o diário ilegível; uma linha
  truncada no fim (queda no meio da escrita) levanta `JSONDecodeError`, e
  `ui/exportacao.py:296-302` abre sessão de revisão vazia sem log, que continua gravando
  no arquivo corrompido.
- Exige: linhas só por `\n`; o leitor pula qualquer linha inválida com WARNING; antes de
  acrescentar, se o arquivo não termina em `\n`, o gravador escreve um `\n` — sem truncar,
  porque a ponte do `appy --editor` e o diálogo de revisão podem escrever no mesmo diário
  e truncar destruiria o evento do outro; `fsync` por lote gravado (R-12).
- Aceite: os dois cenários como teste, e o evento gravado depois da linha truncada é lido.

**R-10. O diário tem identidade.** Sev. alta. Prova: lido.
- Evidência: o nome é `<saida>.review.jsonl` (`ui/exportacao.py:197`), o id do bloco é
  posicional (`core/editorial_adapters.py:430`) e o `document_id` é o nome do arquivo sem
  extensão (`core/editorial_pipeline.py:160`); o mesmo `except (ValueError, KeyError)`
  (`ui/exportacao.py:296-300`, `core/editor/importar_ir.py:533-537`) trata igual um diário
  truncado, um de outro livro e um conflito de valor; a sessão de revisão nova continua
  acrescentando no mesmo arquivo, e o primeiro evento estranho faz `from_journal` falhar
  para sempre.
- Exige: a identidade vai no **nome** do diário — `<saida>.<sha12>.review.jsonl`, com os
  doze primeiros dígitos do `source_sha256` —, sem linha de cabeçalho e sem migração
  (uma linha nova quebraria os sete testes que contam linhas do diário, e regravar o
  diário antigo carimbaria o sha atual num diário que pode ser de outro livro de mesmo
  nome); `caminho_do_diario` procura pelo nome com sha. Os três casos separados:
  truncado → R-09; **outro documento** (sha diferente) → o diário antigo nunca recebe
  escrita, e a sessão de revisão abre o do sha novo e avisa; **conflito de valor**
  (inclusive versão do pipeline diferente sobre o mesmo livro) → por alvo, vale a cadeia
  a partir do último evento gravado: se o valor anterior dele confere, a cadeia aplica;
  se não, o alvo é pulado com WARNING e os outros aplicam — um evento que tem sucessor
  nunca se aplica sozinho, para que uma versão da leitura que volta ao texto antigo não
  ressuscite a correção velha por cima da nova (invariante 2). O diário sem sha no nome
  não recebe mais escrita, mas os eventos dele continuam valendo: a sessão do mesmo livro
  lê o sem sha (se houver) e depois o com sha, e grava só no com sha. O caminho de diário
  já guardado — `review_journal_path` no JSON (`ui/exportacao.py:197`) e `origem.diario`
  no EPUB do editor (lido em `core/editor/projeto.py:147`, gravado em `:181`) — passa pela
  mesma regra, e não por cima dela. O id de bloco e o `document_id` ficam como estão.
- Aceite: reexportar outro livro para o mesmo destino não toca no diário antigo e avisa;
  o mesmo livro com leitura diferente aplica os alvos cuja cadeia confere e pula os
  outros com WARNING; o cenário E1 pulado, E2 gravado, leitura que volta ao texto de E1:
  vale E2; diário sem sha no nome abre e não recebe escrita, e as correções dele continuam
  aplicadas ao mesmo livro; o caminho guardado no JSON e no EPUB segue a regra.

**R-11. Desfazer devolve o que havia.** Sev. alta. Prova: script.
- Evidência: `editorial_review.py:560-575` (`undo`) grava `("undo",)` nos motivos e
  `:436-455` (`_apply`) troca os `reason_codes`; o bloco que só estava na fila por motivo
  de alto impacto (`:86`) sai dela para sempre — contra o docstring e as invariantes 9 e
  11 do `CONTEXT.md`; `edit(..., reason_codes=("undo",))` corrompe a pilha.
- Exige: o evento guarda `before_reason_codes` e o `undo` os restaura; `undo` e `batch:`
  são reservados.
- Aceite: aceitar e desfazer devolve o item à fila com os mesmos motivos e severidade;
  `edit(..., reason_codes=("undo",))` levanta `ValueError`.

**R-12. Lote transacional e a ponte do editor.** Sev. alta. Prova: script.
- Evidência: `editorial_review.py:541-554` (`apply_batch`) aplica metade e levanta;
  `core/editor/importar_ir.py:541-558` grava um evento por bloco, sem lote; `:419-441`
  só percorre os blocos de topo (`:426`), e capítulo em modo código vira um `reject` de
  cada bloco dele no documento editorial, sem aviso.
- Exige: alvos validados antes do primeiro evento; um lote por salvamento da ponte, por
  uma API nova (`aplicar_lote(eventos)`, com status por evento — `apply_batch` exige
  `confirm` e um status só), o que faz de cada Ctrl+S do editor um único passo de
  desfazer; capítulo em modo código não gera evento, e o salvamento avisa que esse
  capítulo não volta ao documento editorial; blocos aninhados com origem própria entram
  (a célula de tabela não é bloco, como diz o comentário de `importar_ir.py:426`).
- Aceite: lote com alvo inexistente não grava nada; salvar com capítulo em modo código
  não rejeita nada e avisa; um bloco aninhado com origem editado gera evento; desfazer
  depois de um salvamento desfaz o salvamento inteiro.

**R-13. Aplicar N eventos custa O(N).** Sev. média. Prova: script.
- Evidência: `core/editorial_model.py:488-515` (`apply_review`) faz `deepcopy` (`:493`) e
  `validate` (`:514`) do documento por evento, e `:491` e `editorial_review.py:582`
  (`from_journal`) conferem id duplicado com `any(...)` sobre todos os eventos: 200
  edições num documento de 300 páginas × 12 blocos levam 54,6 s; e `gravar_eventos`
  (`importar_ir.py:534`) relê e reaplica o diário inteiro **a cada salvamento** do editor
  (`core/editor/projeto.py:189-195`, a chamada na `:190`), O(N²) na sessão.
- Exige: aplicar um lote sobre **uma** cópia e validar uma vez (a cópia continua: o que
  sai da aplicação é uma foto, e a exportação em segundo plano depende disso); ids de
  evento num conjunto; a ponte relê só a cauda do diário a partir do último deslocamento
  que conhece — não reler nada perderia os eventos que o diálogo de revisão da janela
  principal acrescentou com o editor aberto.
- Aceite: o mesmo cenário em menos de 2 s, com o documento final idêntico ao do caminho
  antigo; o Ctrl+S do editor com 200 edições anteriores lê só a cauda; um evento
  acrescentado por outro gravador entre dois salvamentos é visto pelo segundo.
- Severidade: média, desempenho que impede o uso em sessão longa.

### Tema D — Tarefa em segundo plano (C4)

**R-14. Erro de tarefa vai ao log.** Sev. baixa (o erro já aparece ao usuário; falta o
traceback para quem depura). Prova: lido.
- Evidência: o `runner` de `BackgroundTask` (`core/services/task_service.py:105-107`) põe
  a exceção na fila e `ui/main_window.py:466-515` (`falhou`) a mostra em `messagebox` de
  uma linha; o traceback nunca chega a `pyboxeditor.log`.
- Exige: `log.error(..., exc_info=...)` no `runner`, o que cobre as ~25 tarefas da janela
  e as dos diálogos.
- Aceite: teste com `caplog` numa tarefa que levanta.

**R-15. A tarefa não aplica resultado sobre boxes que mudaram.** Sev. alta. Prova: lido.
- Evidência: `ui/reconhecimento.py:792` casa resultado e box por posição (`zip`): apagar
  um box durante "Preencher boxes" desloca os caracteres de todos os seguintes; `:382`
  substitui edições feitas no meio; `ui/documento.py:710`/`:720` ("Salvar todas") lê as
  listas vivas na thread e marca salva a página editada durante a gravação. Travar a
  edição durante a tarefa não serve: o Ctrl+S foi feito para deixar editar enquanto
  grava (`ui/documento.py:622-650`, teste em `test_trabalho_fora_da_interface.py:270-301`),
  um treino dura meia hora, e o `_busy()` abre `messagebox` a cada evento de arrasto.
- Exige: o resultado se aplica por identidade aos boxes capturados no início — o `zip` de
  `:792` corre sobre a lista capturada e só toca box que ainda está na página; `:382`
  guarda a posição do histórico no início e, se ela mudou, não aplica e avisa; "Salvar
  todas" grava cópias e marca salva só a página que continua igual à cópia, como
  `_salvar_box_em_tarefa` já faz.
- Aceite: apagar um box durante "Preencher boxes" não desloca os caracteres dos outros;
  editar durante a detecção de boxes faz a detecção não aplicar e avisar; editar durante
  "Salvar todas" deixa a página suja; o teste do Ctrl+S de hoje continua verde.

**R-16. Diálogo que dispara tarefa religa em todo desfecho.** Sev. média. Prova: lido.
- Evidência: `ui/dialogo_rotulagem.py:437`/`:479` sem `ao_falhar` (o botão fica preso em
  "Lendo linhas…"), `:600` não cancela e o `concluir` toca widget destruído, `:363` deixa
  a bandeira `_pagina_rodando` presa; `ui/dialogo_revisao_editorial.py:553-555` deixa o
  Cancelar da barra de status atrás do `grab_set`; `ui/dialogo_de_conclusao.py:99-106`
  não fecha se a ação levanta.
- Exige: cada diálogo religa em sucesso, falha e cancelamento, cancela a tarefa ao fechar
  e confere `winfo_exists` no `concluir`; o diálogo modal oferece o próprio Cancelar;
  `try/finally` na conclusão.
- Aceite: teste por diálogo com tarefa que falha e com fechamento no meio.

**R-17. Fechar e navegar com tarefa rodando.** Sev. média. Prova: lido.
- Evidência: `ui/documento.py:158-170` cancela antes de confirmar o descarte (recusar
  deixa a tarefa cancelada e a janela aberta) e destrói sem esperar a thread, que pode
  estar no meio de uma gravação; durante a sondagem de "Exportar livro", que não é tarefa
  e por isso não trava a navegação, PgDn entra em `_load_pdf_page`, que só consulta
  `task.is_running()`: a página é arquivada, os botões são desabilitados (`:317`) e
  `_run_task` (`ui/main_window.py:484`) recusa sem religá-los.
- Exige: confirmar tudo antes de cancelar; esperar a thread com prazo antes do `destroy`;
  um predicado sem efeito colateral, `_motivo_de_espera()` (texto do motivo, ou `None`),
  vira a decisão única de "há trabalho em curso": o `_busy()` o usa para o diálogo, e o
  `_load_pdf_page` o usa para recusar com o aviso na barra de status, como o
  `test_f37_paginas.py:494` já espera ("Aguarde").
- Aceite: testes dirigidos para os três, e o `test_f37_paginas.py:494` continua verde.
- Severidade: média, porque o fechamento no meio da gravação é escolha do usuário
  ("Cancelar e fechar").

**R-18. O editor não deixa `after` órfão nem vigia morta.** Sev. média. Prova: script.
- Evidência: `ui/editor/mensagens.py:53-57` reagenda a cada 200 ms e nunca chama
  `after_cancel` — fechar o editor embutido dispara `bgerror` (`invalid command name
  …esvaziar`); `ui/editor/original.py:237` e `texto_rico.py:656` idem; o `open` em
  `ui/editor/operacoes.py:616` sem `try` mata a vigia de "Abrir com…" no primeiro
  `PermissionError`; `:697-715` roda `epub.escrever` e o epubcheck na thread do Tk e deixa
  o cursor "watch" se `escrever` levanta; `:547` nunca apaga o `mkdtemp`.
- Exige: `JanelaDoEditor.fechar` cancela todo `after` de vida longa; a vigia captura
  `OSError` por arquivo e reagenda em `finally`; a validação roda em tarefa; a pasta
  temporária sai no fechamento.
- Aceite: abrir e fechar o editor embutido sem `bgerror` (teste com o
  `report_callback_exception` espionado); a vigia sobrevive a um `PermissionError`; o
  cursor volta ao normal quando `escrever` levanta; a pasta do `mkdtemp` não existe
  depois do fechamento.

**R-19. Pequenos da janela principal.** Sev. baixa. Prova: lido.
- Evidência e Exige, por item:
  - `core/services/document_controller.py:82-98`: Ctrl+Z/Ctrl+Y só chamam
    `store_current` e não mudam o estado de "suja". Exige: suja = posição do histórico
    diferente da posição salva (desfazer até o estado salvo não suja);
  - `ui/treino.py:244`: o léxico aprende antes de a gravação dar certo. Exige: aprende só
    depois;
  - `ui/treino.py:850`/`:858`: o lote converte o livro inteiro para a memória e descarta
    imagem ilegível sem contar. Exige: página a página, e as ilegíveis contadas no
    `concluir` e logadas;
  - `appy.py:127-145`: o relator grava no log a cada exceção de `<B1-Motion>`, um
    registro por pixel. Exige: um registro por tipo de exceção e por evento dentro da
    janela de silêncio.
- Aceite: um teste por item.

### Tema E — Leitura (C5; o que muda a saída fecha com A/B e corpus)

**R-20. Passadas de livro num lugar, com guarda por página.** Sev. alta. Prova: lido.
- Evidência: `core/livro.py:4484`/`:4509` chamam `pdf_nativo.extrair_pagina`, e `:4492`
  chama o `extrair_pagina` do OCR, sem `try`: uma página que levanta derruba a exportação
  do livro inteiro, enquanto `pdf_nativo.extrair` (`:3009-3023`) protege;
  `juntar_entre_paginas` e `lados_pelos_lances` só rodam em `pdf_nativo.py:3034-3035`, o
  caminho sem OCR, contra as docstrings (`:2767`, `:2819`).
- Exige: uma função pública `passadas_de_livro()` chamada pelos dois caminhos (o
  AbbyChessCraft tem a própria cópia, `_passadas_do_livro`, e poderá usá-la; a troca é
  dele), com `juntar_entre_paginas` e `lados_pelos_lances` mantendo a assinatura; um
  guarda por página nos dois (WARNING; a página da camada cai para o OCR, a do OCR sai
  como página com falha, num campo próprio que a conclusão e a fila mostram), que
  **relança** o cancelamento (o `OCRCancelled` que `editorial_legacy.py:212-219` levanta
  dentro de `extrair_pagina`, F119: engoli-lo faria o Cancelar parar de funcionar no meio
  da página); `juntar_entre_paginas` põe `-1` nos `registros` que vêm da página seguinte
  (`pdf_nativo.py:2789` os copia, e eles indexam o roteamento da própria página: no OCR a
  fila mostraria recortes de linha errados).
- Aceite: teste com página da camada e com página do OCR que levantam, e com o
  cancelamento no meio da página (cancela); A/B e corpus sem piora; e, como o A/B e o
  corpus leem páginas avulsas e não medem passadas entre páginas, o Yusupov inteiro antes
  e depois, com a contagem de parágrafos juntados e de lados trocados por
  `lados_pelos_lances`, e FEN 531/541 sem piora.

**R-21. A evidência do ensemble viaja no registro.** Sev. média. Prova: script.
- Evidência: o invólucro `faixa` de `core/livro.py:1334-1336` não tem `_source_reader`
  nem `last_result`, e o `ler_faixa` do ensemble (`core/editorial_legacy.py:106-129`) só
  publica a divergência por esse atributo: `estatisticas["ensemble"]` nunca é gravada no
  caminho de produção e a fila perde as divergências; o mesmo `leitor_de_faixa_com_ensemble`
  chama o motor duas vezes por faixa e tem `return` morto.
- Exige: a evidência viaja no próprio registro da faixa (o campo que `livro.py:1405` já
  lê); o atalho por `last_result` sai; o motor é chamado uma vez.
- Aceite: teste que lê pelo `extrair` com ensemble e encontra a estatística; A/B
  idêntico (a mudança não pode mexer no texto).

**R-22. O texto e as medidas da linha andam juntos.** Sev. média. Prova: script.
- Evidência: `core/livro.py:4192-4201` corrige a prosa da linha `glyph` sem
  `_transferir_medidas` (`the knight , and`: texto com 24 caracteres, `pesos` com 25);
  `_paragrafo_de` (`:3238`) idem (`Blackhasto move`: 17 contra 15); `partir_coladas`
  (`:3363-3382`) deixa `inicios` velho; `core/negrito.py` (perto de `:315`) pula o
  parágrafo de comprimentos diferentes em silêncio.
- Exige: as três passagens transferem as medidas; o pulo do negrito é contado por página
  e logado; a propriedade P-2 (§6) é conferida pela suíte em toda passada. Um tipo que
  junte texto e medidas só se aparecer divergência nova depois disso. As três passagens
  ficam fora do trecho do diff do usuário em `livro.py`, e a fase segue o passo 9 do
  roadmap enquanto ele estiver na árvore.
- Aceite: os três cenários como teste; A/B e corpus iguais ou melhores; negrito das
  páginas de referência medido antes e depois.

**R-23. Idioma num lugar.** Sev. média. Prova: script.
- Evidência: `core/livro.py:2305-2326` aplica remendos do inglês a todo idioma (`tu andas
  bem` → `tu and as bem`), e `_paragrafo_de` (`:3238`) chama sem idioma;
  `livro.py:2134` e `:2430` usam `startswith("pt")`, `pdf_nativo.py:2412` corta para dois
  caracteres, `alfabeto.permitido` exige a chave exata.
- Exige: `idioma_normalizado()` único; remendos por idioma; toda chamada passa o idioma.
  Espera o commit do trabalho do usuário (o diff dele está em `livro.py:2428-2432`).
- Aceite: `tu andas bem` intacto em `pt`; `_paragrafo_de` recebe o idioma; `pt-BR`,
  `pt_BR` e `por` dão a mesma chave em `alfabeto.permitido`; A/B e corpus sem piora.
- Severidade: média, saída errada pontual (um padrão de palavra) que o corpus não acusou.

**R-24. Desempenho da leitura.** Sev. média. Prova: script.
- Evidência: `core/services/ocr_service.py:449-451` faz `limpa[labels == i] = 255` por
  componente (24 mil componentes: 146 s; com tabela de consulta: 0,08 s);
  `core/livro.py:2466` roda `process.extract` sobre 100 mil palavras sem cache (114 ms
  por linha de 11 palavras, ~4 s por página), dentro de `_corrigir_prosa_contextual`, a
  função que o diff do usuário altera.
- Exige: tabela de consulta por rótulo; cache por `(palavra, idioma)`. O cache espera o
  commit do usuário.
- Aceite: saída byte a byte idêntica nas páginas de referência e tempo medido antes e
  depois (Yusupov p. 96 incluída).

**R-25. Pequenos da leitura.** Sev. baixa, salvo os dois que mudam a saída (`amostrar` e
a confiança 0), que são média.
- Evidência e Exige, por item (prova entre parênteses):
  - `pdf_nativo.py:803` (`amostrar` corta `[:paginas]` depois do passo: em livros de 41 a
    79 páginas o fim nunca entra) — corta antes do passo (script);
  - `ocr_service.py:274-300` (token de confiança 0 descartado; `texto[0]` parte caractere
    decomposto) — aceita confiança 0 e pega o primeiro grafema (lido);
  - `pdf_nativo.py:495-515` (cache de nomes de glifo sem mtime na chave) — a chave leva o
    `mtime` (lido);
  - `render_diagrama.py:274`/`:518` (`esquecer` não limpa a largura da grade) — limpa
    (lido);
  - `livro.py:4475` (`paginas` sem validação de intervalo) — índice fora do livro levanta
    `ValueError` antes da primeira página (lido);
  - `geometria_da_linha.py:229-235` (tabela ilegível vira "sem poda" sem log, e o
    `lru_cache` fixa o vazio) — WARNING quando o arquivo existe e não se lê, e o vazio não
    entra no cache (lido).
- Aceite: um teste por item; os que mexem na saída (`amostrar`, a confiança 0), com A/B.

### Tema F — Editor de livros: fidelidade (C6)

**R-27. O sumário não perde entradas válidas.** Sev. alta. Prova: script.
- Evidência: `core/editor/sumario.py:304-313` (`destinos_quebrados`) só conhece ids de
  bloco do modelo: `<h2 id>` dentro de ilha e `<a id>` inline viram "quebrados", toda
  âncora de capítulo em modo código também, e uma entrada sem `href` sai com a subárvore
  (`epub.py:650`); se todas caem, `epub.py:662-663` troca o sumário pelo gerado dos
  títulos sem dizer.
- Exige: índice de âncoras calculado na gravação, a partir do modelo (ids de bloco, os
  `extras` do R-26, as ilhas e o XHTML dos capítulos em modo código) — calculado na
  abertura ficaria velho depois da edição; entrada sem destino vira rótulo e mantém os
  filhos; nunca regeneração sem aviso. Entra antes de R-26, que aumenta o que vai para
  ilha e para `extras`.
- Aceite: o nav com `<h2 id>` em ilha, `<a id>` inline e entrada sem `href` sai com as
  três (a última como rótulo); capítulo em modo código mantém as suas; nenhuma
  regeneração sem aviso.

**R-26. Ida e volta sem perda silenciosa.** Sev. alta. Prova: script.
- Evidência: `core/editor/xhtml.py:404-423`, `:605`, `:687`, `:695`, `:742`,
  `:1296-1313` aceitam e descartam `id`/`class` de `li`, `tr`, `td`, `th`, os do `img` da
  figura, os do `body` e do `html`, e o `media` do `<link>` (`<li id="fn1">` volta `<li>`
  e o link `#fn1` quebra); o OPF perde `page-progression-direction`, `id` e `properties`
  do `itemref`, `fallback` do `item`, `opf:scheme` do identificador (`epub.py:358-362`) e
  `xml:lang` dos `dc:*`; o `xml:lang` do pacote vira o do `dc:language`; os ids do
  manifesto são renomeados pelo escritor (`epub.py:597`, `_id_de_manifesto`, chamado em
  `:713`: `c1` → `c1.xhtml`, quebra `refines="#c1"`); `epub.py:500` decodifica capítulo
  em ISO-8859-1 como UTF-8 com `replace` e grava U+FFFD.
- Exige: `id`, `class`, `lang` e `dir` vão para `extras` do elemento (lista, item, tabela,
  linha, célula, imagem, corpo, raiz), e o `media` do `<link>` também; só o atributo que
  o dialeto não conhece manda o elemento para ilha; o `class` de `extras` se funde ao
  `class` que o dialeto já escreve (`_comuns`, `xhtml.py:1267`), nunca como segundo
  atributo; os ids de `extras` entram no índice de âncoras do R-27 e na deduplicação do
  R-28; o pacote ganha `extras` como os metadados já têm; ids do manifesto preservados; a
  codificação declarada é honrada.
- Aceite: teste `ler → escrever → ler` com o cenário mínimo de cada atributo citado na
  Evidência. A contagem num corpus de EPUBs de terceiros (`scripts/medidas/`) é medida
  registrada no roadmap, não teste.

**R-51. O escritor não reescreve o que a editora declarou.** Sev. média. Prova: script.
- Evidência: `core/editor/epub.py:880-924` (`_acessibilidade`) substitui o
  `schema:accessibilitySummary` do livro aberto por "Livro em texto corrido, editado no
  PyBoxEditor" (`:918`/`:923`) e afirma `accessibilityHazard none` (`:917`) em qualquer
  livro (reproduzido pelo crítico: `flashing` vira `none`). O `none` é decisão registrada
  para o livro criado no editor (`SPEC_EDITOR.md:1233`, `test_editor_epub_completo.py:146`).
- Exige: em livro de terceiro, `accessibilitySummary`, `accessibilityHazard`,
  `conformsTo` e `certifiedBy` da origem são preservados; `accessMode` e
  `accessibilityFeature` continuam calculados; livro de terceiro que não declara perigo
  sai com `unknown`; livro criado aqui continua `none`. A §10.1 da `SPEC_EDITOR.md`
  acompanha.
- Aceite: EPUB com `accessibilitySummary` e `accessibilityHazard flashing` próprios sai
  com os mesmos; EPUB de terceiro sem eles sai com `unknown`; o
  `test_editor_epub_completo.py:146` continua verde.

**R-28. Livros de terceiros com ids e espinha repetidos.** Sev. média. Prova: script.
- Evidência: espinha com o mesmo `itemref` duas vezes abre e dá `ValueError: dois
  capítulos com o mesmo arquivo` ao salvar (`epub.py:480-505`); ids de bloco repetidos
  abrem e não salvam (`modelo.py:667`), e `substituir_tudo_no_capitulo` (`busca.py:507`)
  troca no primeiro bloco do id (`modelo.py:498`), não no certo; `livro_ops.py:546-553`
  deduplica marca de página só por id, e marcas da mesma página com ids diferentes
  duplicam.
- Exige: deduplicação na leitura, renumerando com aviso; espinha repetida tratada; marca
  de página deduplicada por número.
- Aceite: os três cenários como teste.

**R-29. Busca e substituição.** Sev. média. Prova: script.
- Evidência: `core/editor/busca.py:49`/`:112` (quantificador mínimo por regex sobre regex:
  `a\*b` → `a\*?b`, `(?:x)` → `(??:x)` e erro); `:117-119` sem NFC (`cafe\u0301`, em
  NFD, não acha `café`, em NFC); `:483-485` "Substituir tudo" no modo código grava ponto
  de desfazer vazio; `modelo.py:927` caixa por palavra parte a palavra na fronteira de
  trecho (`nimzo` + **w** + `itsch` → `NimzoWItsch`); `tipografia.py:51`/`:97` aspa
  depois de NBSP vira fechamento.
- Exige: quantificador pelo analisador do `re`; NFC com mapa de deslocamentos (sem ele as
  substituições caem no lugar errado); ponto de desfazer com o XHTML do capítulo antes e
  depois; a caixa por palavra opera sobre a palavra inteira do parágrafo, atravessando
  trechos; `anterior.isspace()`.
- Aceite: um teste por item.

**R-30. Notação com variantes e PGN válido.** Sev. média. Prova: script.
- Evidência: `core/editor/xadrez.py:214-219` (`segmentos`) joga os lances da variante no
  tabuleiro principal, enquanto `:284` e `:393` já têm pilha de variantes;
  `pgn_io.py:108` e `:112`/`:113` gravam cabeçalho com quebra de linha; `:166-168` deixa
  a `(` antes do primeiro lance presa na raiz.
- Exige: unificar os três percursos de tokens que já existem num só, usado por
  `segmentos`, `posicao_apos` e `pgn_io`; a variante aberta antes do primeiro lance pende
  do primeiro lance; cabeçalho com `" ".join(valor.split())`.
- Aceite: os três cenários como teste.

**R-31. O escritor do EPUB não muda o livro aberto.** Sev. baixa. Prova: lido.
- Evidência: `epub.py:648-660` e `:1014-1016` mudam `livro.sumario`, `marcos` e `ncx` do
  modelo vivo durante a gravação — na falha e também no sucesso.
- Exige: o escritor trabalha numa cópia, como `texto_do_opf` já faz.
- Aceite: teste de gravação (com sucesso e com falha) que compara `marcos` e `ncx` do
  modelo antes e depois (o sumário deixa de ser podado com o R-27).

### Tema G — Exportação do documento editorial (C7)

**R-32. Uma ordem de páginas para todos os formatos.** Sev. baixa. Prova: script.
- Evidência: `core/editorial_export.py` (`_html_body`, `_text_document`) e o PDF ordenam
  por `page_index`; EPUB e DOCX seguem `doc.pages` (invariante 10). Nenhum fluxo da
  interface produz páginas fora de ordem; só `extrair(paginas=[5, 2])`.
- Exige: o `EditorialDocument` ordena as páginas por `page_index` na construção, e
  `aplicar_revisao` (`editorial_legacy.py:427`/`:477`), que alimenta o escritor de
  produção, devolve as páginas nessa ordem; nenhum exportador reordena.
- Aceite: os seis formatos (EPUB, DOCX, HTML, TXT, PDF, JSON) na mesma ordem, por teste.

**R-33. Tabela, título e idioma.** Sev. média. Prova: script.
- Evidência: `core/exportar.py:1353-1354` (`cols=len(bloco.linhas[0])`: tabela vazia
  levanta `IndexError`) e `:1359-1360` (o `zip` trunca a fila longa e perde células);
  `exportar.py:760-761` grava `<dc:title></dc:title>` quando o título é vazio, e o mesmo
  caminho (`options.title or document.title`) deixa o `dc:language` vazio quando o idioma
  é vazio.
- Exige: `cols` pelo maior número de células, filas curtas completadas, tabela vazia
  pulada; título e idioma com padrão quando vazios.
- Aceite: os quatro cenários como teste.
- Severidade: média, porque a perda de células exige tabela irregular, que nenhum fluxo
  normal demonstrado produz.

**R-34. A revisão do diagrama vale inteira.** Sev. alta. Prova: script.
- Evidência: o ramo `Figura` de `_bloco_revisado` (`core/editorial_legacy.py:538-542`) só
  redesenha quando o FEN muda: lado e orientação revisados são ignorados e a figura sai
  carimbada "convenção"; `revisao_pendente` (`core/editorial_export.py:202-212`) ignora o
  status `reviewed` quando `value["review_required"]`; `editorial_adapters.py:361-363`
  esquece a origem `"usuario"` do lado, que `tabuleiro_edicao.py:148` produz.
- Exige: `_bloco_revisado` compara e aplica FEN, lado e orientação — o lado revisado muda
  `lado_a_jogar` e `lado_origem="usuario"` sem redesenhar (redesenhar troca o recorte do
  livro por desenho, `editorial_legacy.py:391`), e a orientação só redesenha figura que
  já é `render` ou cujo FEN mudou; `revisao_pendente` respeita o status da decisão
  primeiro; o mapa do lado cobre todas as origens.
- Aceite: diagrama revisado com lado `b` e orientação trocada chega assim ao arquivo, sem
  "não revisado".
- Severidade: alta, a revisão do usuário ignorada em silêncio (invariantes 2 e 6).

**R-36. Pequenos do editorial.** Sev. baixa. Prova: lido.
- Evidência e Exige, por item:
  - `editorial_adapters._bloco_de_volta` perde `header`/`footer`/`caption` (cabeçalho e
    rodapé entram no corpo). Exige: o tipo volta;
  - `editorial_legacy.py:292-296` engole a falha da imagem da página sem log e não
    confere se o PDF em disco é o do documento. Exige: log, e conferência pelo
    `source_sha256` da identidade (R-10);
  - `editorial_pipeline.py:868-905` indexa por `page_index`. Exige: indexa por `page_id`;
  - `_faixas` está copiado em `editorial_export.py:259` e `editorial_legacy.py:496`.
    Exige: um só;
  - `ExportOptions` existe em `editorial_export.py:36-77` e `editorial_pipeline.py:456-492`
    com `paginas` de contratos opostos (revisadas num, cruas no outro). Exige: uma só
    `ExportOptions`, com `paginas` = páginas revisadas, fixada por teste; a outra sai.
- Aceite: um teste por item que muda comportamento; a deduplicação de `_faixas` fecha pela
  suíte verde.

### Tema H — Falhas silenciosas restantes (C8)

**R-37. Os silêncios que mudam a saída falam.** Sev. média. Prova: lido.
- Evidência — lista fechada: `core/vertical.py:287` (captura larga demais em volta do
  árbitro), `ui/dialogo_rotulagem.py:501`, `ui/exportacao.py:85` (a sondagem da camada
  falha e o PDF cai no OCR sem aviso), `ui/documento.py:454` e
  `ui/dialogo_de_exportacao.py:589` (preferência não grava, e ninguém sabe),
  `ocr_runtime.py:205-210` (soma bytes que não removeu), `core/dataset_check.py:83`/`:110`,
  `core/formato_box.py:163`/`:175`/`:186`, `core/services/ocr_service.py:803`/`:809`/`:828`
  (tupla larga demais), `core/editorial_export.py:149`/`:241`/`:264` e
  `core/services/document_service.py:236-280` (`aplicar_payload` conta página
  descartada como recuperada), `core/ocr_training.py:176`/`:187`, e os 16 handlers de
  `ui` cujo corpo é só `pass` sob `except` nu ou `except Exception`: `ui/documento.py:465`
  e `:498`, `ui/editor/busca.py:470` e `:674`, `dialogo_pdf.py:324`, `janela.py:2946`,
  `operacoes.py:709` e `:1098`, `original.py:156`, `pdf.py:196`, `previa.py:150` e
  `:277`, `propriedades.py:217`, `proxy.py:81`, `tags.py:504`, `texto_rico.py:1305`.
- Fora da lista, por serem degradação esperada que não muda a saída: a área de
  transferência vazia (`ui/editor/janela.py:3032`/`:1517`), o destroy de rótulo
  (`ui/editor/xadrez.py:88`) e `ui/reconhecimento.py:612` (a tarefa reporta).
- Exige: cada item loga pela regra do `CLAUDE.md` — WARNING quando a saída ou a
  preferência muda sem o usuário saber, INFO para a degradação esperada, `uma_vez` no que
  se repete — e conta o que descartou; as capturas largas se estreitam ao que o comentário
  justifica.
- Aceite: teste com `caplog` para cada item que muda saída; varredura por AST de `ui` com
  lista nominal (princípio 7) que começa só com os handlers que este requisito decide
  manter mudos, cada um justificado.

### Tema I — O gate vê o que deveria (C9)

**R-38. Teste que não mede, pula.** Sev. baixa (infraestrutura de desenvolvimento; vem
na Onda 0 pelo princípio da ordem, não pela severidade). Prova: script.
- Evidência: 27 testes saem por `return` nu quando falta dado (11) ou display (16); quatro
  deles deram PASSED no `HEAD` limpo sem dado nenhum (`test_f15` ×2, `test_f16`,
  `test_f14`); `tests/test_editor_xhtml.py:365` regrava o golden se ele some; asserções
  fracas em `test_f17_leitura_de_linha.py:271` (só `is not None`; o nome promete que a
  faixa não sai da página), `test_f94_letras.py:156`, `test_f43_navegacao.py:209` (só
  `hasattr`), `test_f71_diagrama.py:198`.
- Exige: `pytest.skip` com motivo; teste por AST que recusa `return` nu em `test_*` antes
  da primeira asserção e fora de `except` (o de `test_f12_balanceamento.py:129` e os
  retornos de sucesso de `test_f61_pgn.py:417`, `test_f71_diagrama.py:657` e
  `test_f83_treino_diagrama.py:668` são legítimos); golden ausente falha; cada asserção
  fraca passa a conferir o valor que o nome do teste promete.
- Aceite: no `HEAD` limpo, os 27 aparecem como SKIPPED com motivo; as quatro asserções
  falham contra uma função que devolva um objeto vazio do tipo certo.

**R-39. Teste de comportamento, não de grafia.** Sev. baixa. Prova: script.
- Evidência: 27 chamadas de `inspect.getsource` em 13 arquivos, cobrindo 19 testes; são
  os do falso vermelho quando se edita com a suíte rodando.
- Exige: espião ou `monkeypatch` onde a chamada é observável; os que ficarem estão numa
  lista nominal, cada um com justificativa.
- Aceite: teste por AST que confere a lista nominal (um `getsource` fora dela falha), e a
  lista tem só os testes sem chamada observável. Quando ela zerar, a regra "não edite com
  a suíte rodando" do `CLAUDE.md` pode cair (R-44).

**R-40. Marcadores e lint dos testes.** Sev. baixa. Prova: lido.
- Evidência: `pytest.ini` sem `--strict-markers`, com `unit`/`integration`/`ml`/`export`
  sem uso; `[tool.pytest.ini_options]` morto em `pyproject.toml:54`; `ruff check tests`
  dá 63 erros e `tests` está fora do lint da CI (`ci.yml:37`); `epubcheck>=0.4`
  (`pyproject.toml:36`) contra `>=5.0` (`requirements-dev.txt:22`).
- Exige: `--strict-markers` e `-ra` no `pytest.ini`; as quatro marcas e o bloco do
  `pyproject.toml` saem; `ruff check tests` limpo, com ignores por arquivo onde o padrão
  é deliberado, e `tests` no lint da CI; o piso do `epubcheck` igual nos dois arquivos.
- Aceite: `pytest --strict-markers --collect-only` sem erro e `ruff check tests` sem
  erro, os dois na CI.

**R-41. O que se distribui leva o que o programa abre.** Sev. baixa (nenhum consumidor
usa o wheel hoje). Prova: script.
- Evidência: o wheel do `HEAD` não leva as fontes de `fonts/`, `pieces/` nem
  `config/profiles/` (`render_diagrama.carregar` levanta `FonteIncompleta`,
  `perfis.carregar_todos()` devolve `[]`); `ci.yml:54` confere três arquivos à mão;
  `RECURSOS_OBRIGATORIOS` já existe em `scripts/verificar_empacotamento.py:14` e já tem
  `pieces/wK.png`, mas não tem `config/profiles` nem as fontes; `pyboxeditor.spec:26` não
  leva `config/profiles`; o `dist/` é de 09-25, anterior à última mudança do
  `pyboxeditor.spec`. O caminho documentado é `pip install -e`; nenhum consumidor
  conhecido usa o wheel. `fonts/` tem também PDF, JPG e duas fontes não rastreadas.
- Exige: `config/profiles/*.json` como package-data de `config` (o `perfis.PASTA_PADRAO`
  atual passa a achá-los sem mais nada); as fontes e as peças, que hoje são achadas por
  `__file__` (`render_diagrama.py:66`/`:239`/`:825`, `ui/pecas.py:32`) e por isso não
  enxergariam um `data-files` em `sys.prefix/share`, passam a ser resolvidas por uma
  função `config.paths.recurso(relativo)` que procura no projeto e depois em `share`,
  usada nesses três lugares; as fontes que vão no pacote são as listadas em
  `core/dados/fontes_de_diagrama.json` mais as licenças (um glob `*.otf`/`*.ttf`
  perderia `MERIFONT.TTF` e `IS-TT-01.TTF` no Linux, que distingue caixa);
  `RECURSOS_OBRIGATORIOS` estendida e reusada na CI, com a regra escrita de como um
  caminho da árvore vira o nome dentro do wheel (`*.data/data/share/...`); o teste do
  bundle e a docstring de `tests/conftest.py:89` acompanham (R-43 mexe nas mesmas
  raízes); o `pyboxeditor.spec` leva `config/profiles`.
- Aceite: wheel construído da exportação limpa e instalado num venv limpo abre a fonte
  de diagrama, as peças e os perfis; o teste do spec confere `config/profiles`.

**R-42. A CI roda o que a suíte tem.** Sev. baixa. Prova: lido.
- Evidência: o epubcheck nunca roda na CI (seis arquivos de aceitação pulam); o Tesseract
  não está no `apt-get` (oito testes pulam em todo lugar fora desta máquina); a CI roda
  `-m "not gui and not slow"` com o Xvfb instalado, e os cinco arquivos `gui` nunca rodam;
  o 3.10 é declarado em `requires-python` e nunca testado; o `[ml]` baixa o torch com
  CUDA.
- Exige: `epub-validacao` e `tesseract-ocr` na CI; os testes `gui` rodam sob Xvfb; piso
  3.11 (`requires-python >= 3.11` e `target-version = "py311"` do `ruff`), que é o que a
  matriz testa; índice CPU do torch.
- Aceite: o resumo de pulados da CI não traz "epubcheck ausente" nem "tesseract ausente";
  os arquivos `gui` aparecem na CI; o `requires-python` bate com a matriz; o `[ml]`
  instala o torch do índice CPU.
- Risco: o Tesseract do apt pode ler diferente do desta máquina nos oito testes.

### Tema J — Caminhos de dado (C2)

**R-43. Dado e recurso resolvidos pela raiz do projeto.** Sev. média. Prova: lido.
- Evidência: `core/services/learning_service.py:42`, `core/learner.py:265`,
  `core/neural_trainer.py:271`/`:364`, `coleta.promover` e `import_character_images` usam
  `"training_data"` solto, resolvido no cwd, e a `MainWindow` (`main_window.py:188`)
  constrói o `LearningService` com esse padrão, de modo que o caminho de produção o usa;
  o próprio `config/paths._raizes_de_recursos` (`paths.py:20-25`) põe `Path.cwd()` antes
  do projeto, e um `core/dados/*.pth` ou `custom_model.pth` no cwd sombreia os do
  projeto (as fontes não passam por essas raízes e não sofrem disso).
- Exige: `config.paths.dado_do_projeto("training_data")` (`paths.py:85`, já existe) nos
  chamadores, sem o cwd na frente — hoje `dado_do_projeto` o mantém de propósito
  (`paths.py:85-99`, `test_caminhos_do_treino_de_linhas.py:55`), e esse teste muda junto;
  o cwd sai da frente das raízes de recurso; uma variável de ambiente
  (`PYBOXEDITOR_TRAINING_DIR`, no molde de `PYBOXEDITOR_CACHE_DIR`) aponta a base, e o
  `tests/conftest.py` a fixa num diretório temporário, porque `test_f26_livro.py:698`/
  `:714`/`:732` fazem `chdir(tmp)` para isolar e passariam a ler a base real; no wheel,
  onde `projeto_dir` é `site-packages` e não se grava, a base gravável fica na pasta de
  dados do usuário.
- Aceite: com `chdir` para outra pasta, o k-NN e o treino usam a base certa e
  `core/dados/*.pth` e `custom_model.pth` no cwd não sombreiam os do projeto (teste); a
  suíte não toca a base real; A/B idêntico (as raízes resolvem `core/dados`, que a leitura
  usa).

### Tema K — Documentação

**R-44. Os documentos dizem o que o código faz hoje.** Sev. baixa. Prova: lido.
- Evidência: README e `ROADMAP_IMPLEMENTACAO_OCR.md:38` citam só o CER de 09-26;
  `CLAUDE.md:51` cita `TaskService` e `ARCHITECTURE.md:26` cita `TaskService`,
  `DocumentService` e `HistoryService`, que não existem (`BackgroundTask`,
  `DocumentSession`, `HistoryManager`); `ARCHITECTURE.md` com contagem de ciclos
  contraditória e sem `core/rodada.py` e `core/portao_do_modelo.py`;
  `editorial_pipeline.py:12-13` aponta `core/ocr_phase3.py` (hoje em `core/biblioteca/`);
  `ROADMAP_PENDENCIAS.md` "em execução" com o código fechado; README com "cerca de 3.500
  testes"; `README.md:8` e `docs/SETUP.md:5` dizem Python 3.10, contra o piso 3.11 do
  R-42; `CLAUDE.md` diz "cor só em `ui/tema.py`" e o `ui/editor` tem 179 cores literais
  (70 distintas, em 22 arquivos), com exceção declarada no teste.
- Exige: o CER cita a última rodada registrada, com arquivo, data e hash do corpus, e diz
  que corpus e régua mudaram (não "o erro caiu"); os nomes de classe são os reais; o
  `ARCHITECTURE.md` conta os ciclos de hoje e cita os módulos novos; o docstring aponta
  `core/biblioteca/`; o `ROADMAP_PENDENCIAS.md` diz "código fechado, salvo as PD abertas
  pela revisão geral 2 (listadas); Onda 6 aberta"; `README.md` e `docs/SETUP.md` dizem o
  piso 3.11; o `CLAUDE.md` diz a exceção do `ui/editor`. Conferem-se — porque entram no
  commit da fase que as torna verdade — o parágrafo do gate da CI, que acompanha R-40 e
  R-42 (o `tests` no lint, o piso 3.11 e, se a lista do R-39 zerar, o fim da regra de não
  editar com a suíte rodando), e as invariantes 17 a 20 e o glossário da §9 no
  `CONTEXT.md`.
- Aceite: teste que confere que todo caminho `core/...py`, `ui/...py` e `config/...py`
  citado entre crases em `CLAUDE.md`, `README.md` e `docs/ARCHITECTURE.md` existe; o
  resto é conferido por leitura e registrado no roadmap.

### Tema L — Forma do código

**R-46. A ortografia não puxa o OpenCV.** Sev. baixa. Prova: lido.
- Evidência: `core/notacao.py:44` importa `BoxService` no topo só pela ordenação (usada
  em `:193`), o que puxa o OpenCV e força a cópia de `e_token_de_notacao` em
  `core/editor/ortografia.py`.
- Exige: a ordenação num módulo leve; a `ortografia` importa de `notacao` e a cópia sai.
- Aceite: `import core.editor.ortografia` não põe `cv2` em `sys.modules`.

## 6. Invariantes novas

Para o `CONTEXT.md`, numeradas 17 a 20 em seguida às 16 de lá (regras do domínio, sem
nome de função):

- **I-17.** Gravação interrompida deixa o arquivo anterior do usuário intacto; no diário
  de revisão, que só acrescenta, legível até o último evento completo.
- **I-18.** Nenhum caminho vindo de pacote ou de HTML importado sai da raiz dele: a raiz
  do pacote, ou a pasta que o usuário escolheu.
- **I-19.** O diário de revisão só recebe evento do documento cuja identidade ele carrega
  no nome.
- **I-20.** Nem o leitor nem o escritor do editor descartam o que não entendem: guardam
  como veio, ou avisam.

Propriedades de código, conferidas por teste (não entram no `CONTEXT.md`):

- **P-1.** Uma tarefa em segundo plano não aplica resultado sobre boxes editados depois
  que ela começou: aplica por identidade ao que sobrou, ou não aplica e avisa (R-15).
- **P-2.** O texto de uma linha e as medidas dela têm o mesmo comprimento, ou a linha
  não tem medidas (`editorial_legacy.py:523-525` zera de propósito quando o texto muda)
  (R-22).

## 7. Veredito dos críticos

Dois críticos independentes, com padrão "defeito real, causa e não sintoma, um lugar, a
menor mudança, aceite que falha hoje", conferiram cada arquivo:linha no código e
reproduziram por script R-02, R-03, R-07, R-26, R-27, R-28, R-29 e R-51. Os ajustes já
estão aplicados no texto da §5.

| Veredito | Requisitos |
|---|---|
| Aprovado como estava | R-02, R-10, R-11, R-14, R-15, R-18, R-28, R-29, R-40 |
| Aprovado com ajuste | R-01, R-03…R-09, R-12, R-13, R-16, R-17, R-19…R-27, R-30…R-34, R-36…R-39, R-41…R-44, R-46 |
| Desmembrado | R-48 (do R-25) |
| Novo, pedido pelo crítico | R-51 (metadado de acessibilidade) |
| Novo, achado na re-análise 4 e julgado na 5 | R-52 a R-55 (aprovados com ajuste) |
| Recusado | R-35, R-45 |
| Adiado para decisão do usuário | o antigo R-47 (§10) |

A tabela é o veredito dos críticos sobre a v0.1, mais as linhas das re-análises 4 e 5.
Depois dele, o texto de quase todos mudou de novo: R-02 e R-10 receberam itens
fundidos, e as re-análises completaram aceites, termos e severidades (a §12 diz o que
cada rodada mudou).

Os ajustes que mudaram o conteúdo, e não só a linha citada:

- **Itens retirados por não se sustentarem:** o `queue.Full` do R-04 (há um produtor só:
  é inalcançável); a "lista em memória antes do disco" do R-09 (`read()` lê o disco); o
  "documento vivo" do R-16 (`apply_review` devolve cópia); a "sondagem como modal" do
  R-17 (sem defeito de reentrância demonstrado); o Otsu do R-24, o `ordenar_cantos` e o
  `_cinza` do R-25 (sem medida, ou gosto); o "um só OpenCV" do R-08 (o `easyocr` exige o
  `-headless`); `Image.MAX_IMAGE_PIXELS` do R-06 (o padrão do PIL já protege); o ciclo
  `portao_do_modelo` do R-46 (fecha por import tardio, como os outros); três itens do
  R-37 que são degradação esperada; o TLS do EasyOCR saiu do R-25 para o R-48.
- **Itens fundidos:** a guarda da página do OCR (`livro.py:4492`) no R-20; os três casos
  do mesmo `except` no R-10; a busca salva apagada (do R-37) no R-02; a codificação do
  capítulo (do R-31) no R-26; o cwd das raízes no R-43; `-m "not gui"` no R-42; a dupla
  chamada do motor no ensemble (do R-36) no R-21, que tem A/B.
- **Severidades revistas**, pelo critério da notação da §5: R-01 alta → média; R-08
  média → baixa; R-12 média → alta (o modo código rejeita blocos no documento
  editorial); R-13 alta → média (desempenho); R-32 média → baixa (só a API produz
  páginas fora de ordem); R-34 média → alta (revisão ignorada calada); R-38 alta →
  média; R-41 alta → média (ninguém usa o wheel hoje). O R-23 baixou para baixa no
  crítico e voltou a média pelo critério. Na re-análise 4, pelo mesmo critério: R-14,
  R-38, R-39, R-41 e R-42 → baixa (infraestrutura de desenvolvimento, ou o erro já é
  visível); os dois itens do R-25 que mudam a saída → média; R-05 fica alta, com o motivo
  escrito.
- **Contradições resolvidas:** `fsync` por lote, não por evento (R-09 contra R-12/R-13); a
  aplicação em lote mantém a cópia (R-13 contra R-16); o R-23 e o cache do R-24 esperam
  o commit do usuário em `livro.py`, e o R-22, fora do trecho dele, segue o passo 9 do
  roadmap; R-01 ganha a forma de fluxo para os escritores de zip; R-27
  entra antes de R-26; R-31 cobre também o salvar com sucesso; R-41 e R-43 andam juntos;
  o R-17 cria a decisão única `_motivo_de_espera()`, e o R-15 aplica por identidade, sem
  travar a edição que o Ctrl+S permite; a versão do pipeline não torna o mesmo livro
  "outro documento" (R-10 contra a invariante 2); as varreduras por AST seguem uma regra
  só (princípio 7).
- **Invariantes:** a de escrita deixou de nomear função e ganhou a exceção do diário;
  "ilha" saiu da antiga I-22 (hoje I-20, que passou a valer para o escritor também);
  I-18 definiu a raiz; as antigas I-20 e I-21 viraram as propriedades P-1 e P-2, e a P-2
  ganhou "ou não tem medidas".

Recusados:

- **R-35 (bytes iguais em Windows e Linux).** O `create_system` diferente não afeta
  ninguém; a CI é só Linux e comparar exigiria um runner Windows, frágil com zlib
  diferente; a colisão de fontes por `basename` e o `w:name` sem escape são especulação,
  porque os nomes vêm do catálogo fixo. Se um dia for preciso: hash dourado de um EPUB só
  de texto, rodado pela suíte nos dois sistemas, sem passo novo de CI.
- **R-45 (CRAP < 30 nas vinte piores).** Não há defeito, só métrica aproximada; a meta se
  cumpre com cobertura sem asserção em handlers de Tk; partir `extrair_pagina` e
  `treinar_pacote` sem defeito é risco sem retorno, e a primeira está no meio de R-20 e
  R-22. Ficou o princípio 6 da §3.

## 8. Observações sobre o trabalho em andamento

O trecho não commitado de `core/livro.py` (`_corrigir_lances_descritivos`) foi lido sem
ser tocado. Três pontos para o autor, com prova:

- basta um `N.` na linha para ligar o conserto, e todo token em caixa alta que vira lance
  com uma troca vira lance: `1. PAR de peões` → `1. P4R de peões`, `Tabela 2. TAB BAR`
  → `T4B B4R`;
- só a pontuação final sai do token: `(TIC 12.` e `12. TIBD,TIC` ficam intactos;
- a docstring diz "todo em maiúsculas" e a classe aceita `l` e `|`.

## 9. Glossário novo

- **Escrita atômica**: gravação por arquivo temporário na mesma pasta e troca no fim, de
  modo que o destino tem sempre o conteúdo antigo inteiro ou o novo inteiro.
- **Identidade do diário**: os doze primeiros dígitos do `source_sha256` do livro de
  origem, no nome do diário de revisão (`<saida>.<sha12>.review.jsonl`); a versão do
  pipeline não muda a identidade.
- **Sessão de revisão**: a `ReviewSession` aberta sobre um documento editorial e o diário
  dele (não confundir com a `DocumentSession` da janela principal).
- **Rascunho**: o autosave da sessão de documento ou do editor.
- **Ilha**: a parte do XHTML que o dialeto do editor não modela e guarda como veio (no
  código, `IlhaBruta` no bloco e `Trecho.ilha` inline).
- **Capítulo em modo código**: capítulo guardado inteiro como XHTML (`Capitulo.texto_cru`,
  `blocos=[]`), porque não coube no dialeto ou foi editado no código.
- **Dialeto**: o subconjunto de XHTML que o modelo do editor representa por blocos e
  trechos.
- **Passada de livro**: transformação que olha mais de uma página (juntar parágrafo
  partido entre páginas, lado a jogar pelo lance seguinte).
- **Medidas da linha**: os vetores paralelos ao texto de uma linha (`pesos`, `lacunas`,
  `caixas`, `inicios`), um valor por caractere (não confundir com "medida", a medição de
  uma fase).

## 10. Decisões do usuário (o antigo R-47; sem requisito)

Itens que não são defeito do produto e só o dono da árvore decide:

- quatro worktrees em `.claude/worktrees/` (dois com trabalho sem commit desde setembro,
  um ilegível pelo git, um limpo);
- ~2,6 GB ignorados e removíveis (`dist/`, `build/`, `_analysis_*.png`, logs vazios) e os
  pesos datados na raiz (histórico, não lixo: candidatos a uma pasta de arquivo);
- `model_meta_2026-08-*` rastreados com o `.pth` ignorado; `classes_do_modelo.pdf` e os
  dois `fonte_*_conferencia.pdf` na raiz;
- `Box/*.png` (páginas de livro) rastreados, contra a regra do `CLAUDE.md` e o comentário
  em `.gitignore:44`;
- `model_meta_2026-11-09_recusado.json` solto, nem rastreado nem ignorado;
- o `.coverage` de 10-06 na raiz, parcial e enganoso.

## 11. Procedência

Oito revisões e dois críticos em 2026-11-20 sobre o `HEAD` `6627e30`. Os scripts de prova
ficaram no diretório temporário da sessão (`scratchpad\rev_*`, `critico1`, `critico2`,
`rodada*`, `crap.py`); os que viram teste entram no repositório pela fase que os usa.

## 12. Registro das re-análises

| Rodada | Lente | Achados | Efeito |
|---|---|---|---|
| Crítico (2) | mérito, causa, aceite, linha | 47 julgados, 8 defeitos novos | v0.1 → v0.2 |
| 1 | verdade factual: 222 citações `arquivo:linha`, 55 nomes, 16 contagens | 6 linhas, 1 contradição, 4 números | linhas e números corrigidos |
| 2 | coerência interna | 63 (26 de forma, 3 de severidade, 13 contradições, 7 de §7/§4, 5 de termos, 9 de texto) | v0.3: critério de severidade, princípio 7, R-10 sem perder correção a cada versão, glossário |
| 3 | exequibilidade e regressão: 18 sondas de aceite contra o código, chamadores e goldens | 17 aceites falham hoje como devem; R-48 passava (aceite trocado); 20 riscos | v0.4: R-15 aplica por identidade em vez de travar a edição; `_motivo_de_espera()`; R-20 relança o cancelamento; R-41 por `config.paths.recurso`; identidade do diário no nome, sem migração nem truncamento; R-13 lê a cauda; testes existentes que mudam nomeados |
| 4 | o que falta: áreas sem revisão (`box_service`, `formato_box`, `learner`, `coleta`, `canvas_view`, `projeto`, `docx_io`, `historico`), calibragem e o outro cliente do `core` | 12 defeitos, 10 provados por script; 7 severidades destoantes; o AbbyChessCraft | v0.5: R-52 a R-55 novos (o mais grave: salvar o `.box` regrava em cinza o PNG de origem); R-01 e R-04 estendidos; severidades pelo critério; princípio 8 |
| 5 | leitura final: crítico dos R-52 a R-55, consistência, forma, codificação | 4 ajustes de requisito (2 defeitos novos provados: o recorte que dá a volta na página, o `clamp_box` que perde campos), 1 regressão evitada (o cache do k-NN), a lacuna do caminho de diário guardado (R-10), 2 caracteres invisíveis, 3 linhas longas | v0.6; UTF-8 sem BOM, LF, sem mojibake (conferido por `problemas()` direto no arquivo, ainda fora do git) |
