# Roadmap — o que sobrou dos outros roadmaps

Versão: 1.0
Data: 2026-09-29
Status: em execução

Documento de fechamento. Reúne, num lugar só, o que os quatro roadmaps anteriores
registraram como aberto e não retomaram:
[`../ROADMAP.md`](../ROADMAP.md) (fases `F`), [`ROADMAP_EDITOR.md`](ROADMAP_EDITOR.md)
(`ED-`), [`ROADMAP_OCR.md`](ROADMAP_OCR.md) (`OCR-`) e
[`ROADMAP_IMPLEMENTACAO_OCR.md`](ROADMAP_IMPLEMENTACAO_OCR.md) com a §5 de
[`REVISAO_MODOS_OCR.md`](REVISAO_MODOS_OCR.md). As fases daqui usam o prefixo `PD-`
para não colidir com a numeração `F`, que o usuário continua usando em paralelo. Cada
fase cita a origem (fase e linha do documento de origem, em 2026-09-29).

## Princípios

- **Medir antes de decidir** continua valendo: uma regra nova só entra com a tabela que a
  escolhe (o molde é o da F118→F119, onde o teto de candidatos sugerido foi medido e
  **reprovado** — não reintroduzir).
- Toda fase termina com teste que falha sem ela, a suíte `-m "not slow"` verde no `.venv`,
  e uma seção de registro aqui.
- Mexer só no que a fase precisa; a árvore tem trabalho alheio sem commit. Commit apenas a
  pedido, com `git add` seletivo.
- O que depende de **dado do usuário** (rótulo, transcrição, conferência à mão) ou de
  **retreino** do modelo fica na Onda 6: está escrito o que falta, e ninguém o simula.

## Visão geral

| Onda | Fases | Natureza | Depende de |
|---|---|---|---|
| 0 | PD-00 | Trazer para a árvore o que já está pronto em worktrees | — |
| 1 | PD-01, PD-02 | Robustez da interface (nada trava a thread do Tk) | — |
| 2 | PD-03, PD-04, PD-05 | Tabela e layout | — |
| 3 | PD-06, PD-07, PD-08, PD-09 | Exportação e tipografia | — |
| 4 | PD-10, PD-11, PD-12 | Texto corrido | — |
| 5 | PD-13, PD-14 | Medidas que podem virar produção | medição |
| 6 | PD-15 … PD-19 | Bloqueadas | rótulo, retreino, material externo |

---

## Onda 0 — o que está pronto e solto

### PD-00 — Integrar os worktrees

Trabalho feito, testado e nunca levado à árvore principal:

- **F121** (worktree `elegant-napier-6cb645`): a referência do veto de tamanho pergunta à
  linha — o sumário pontilhado deixa de sair `'` (ROADMAP F112, "achado de passagem").
- **Zip com data em UTC** (worktree `beautiful-grothendieck-cd2add`): EPUB/DOCX
  byte-idênticos — fecha a oscilação de `test_o_epub_do_round_trip_e_byte_identico` (F120).
- **`tests/conftest.py`** (worktree `angry-bell-bc2ffb`): a suíte deixa de gravar no
  `%LOCALAPPDATA%` do usuário.

**Aceite:** os três testes novos (`test_f121_pontilhado.py`, `test_exportacao_reprodutivel.py`,
`test_pasta_de_dados_da_suite.py`) passam na árvore principal junto com a suíte.

---

## Onda 1 — nada trava a thread da interface

### PD-01 — A sondagem do Tesseract com prazo, e o disjuntor na janela

Origem: F124, "O que fica registrado" (ROADMAP.md ~14343).

- `tesseract_disponivel` chama `--version`/`--list-langs` por `subprocess.run(timeout=)`
  em vez do pytesseract (que não aceita prazo nessas chamadas); prazo curto, e o
  executável que não responde conta como indisponível, com motivo.
- A janela ganha o disjuntor que o `livro.extrair` já tem: depois de N boxes/páginas
  seguidos com `TesseractSemResposta`, desiste do motor para o resto da tarefa e avisa.

**Aceite:** com um executável falso que dorme, a sondagem volta dentro do prazo; o
preenchimento da janela para de consultar o motor depois do limite.

### PD-02 — A régua da camada fora da thread, e a prova por programação dinâmica

Origem: F119, "O que fica registrado" (~13885).

- `pdf_nativo.amostrar` (5,5 s no livro do Darcy Lima) sai da thread do Tk: a caixa de
  exportação abre na hora e a régua chega depois.
- `provar_letras` deixa de enumerar `5^(n-1)` partições: é um máximo de mínimos numa
  cadeia, e sai por programação dinâmica — com resultado **idêntico** ao atual (teste de
  equivalência contra a enumeração em entradas pequenas).

---

## Onda 2 — tabela e layout

### PD-03 — As três pendências da tabela

Origem: F72 (~9524, 9631–9640).

- duas tabelas na mesma página saem como duas;
- a célula de duas linhas guarda a quebra;
- a moldura da tabela deixa de virar box descartado na janela.

### PD-04 — O título de duas linhas sobre a calha

Origem: F70 (~9418). Primeiro contar quantas páginas do corpus têm o caso; só então
consertar.

### PD-05 — A coluna larga sem moldura (glossário)

Origem: F61/F70 (~8603, 9423). Distinguir tabela sem moldura de duas colunas. Medir antes.

---

## Onda 3 — exportação e tipografia

### PD-06 — Itálico

Origem: F111 (~12373). No molde da F105 (negrito): um campo para o run itálico, detecção
pela inclinação do traço ou pela camada de texto (F110) quando houver, e saída em
EPUB/DOCX/HTML.

### PD-07 — Capítulos pela camada de texto, e a aspa curva

Origem: F111 (~12366–12377). `DETECTAR_CAPITULOS` volta a ligar onde a camada tipográfica
(F110) diz o corpo do título; aspa reta vira curva na exportação.

### PD-08 — O cabeçalho do diagrama como texto

Origem: F60 (~8482). A faixa acima do diagrama sai pesquisável (texto), com `alt` que diz
o que é.

### PD-09 — A SkakNew no DOCX e no Word

Origem: F59 (~8438), F122 (~14115).

- conferir no Word (COM) se a SkakNew-Diagram CFF embutida renderiza; se não, converter
  com fontTools e renomear a família (LPPL);
- a SkakNew ganha rótulo de coordenada em glifo, e o DOCX deixa de cair para imagem;
- o escape do `"` igual no exportador e no editor.

---

## Onda 4 — texto corrido

### PD-10 — A poda geométrica no «Híbrido», e o pingo do `i`

Origem: F123 (~14266–14269).

### PD-11 — A faixa que come prosa, e as junções de hífen

Origem: F115 (~13475–13491).

### PD-12 — A isenção por fonte no PDF pesquisável

Origem: F116 (~13601). O contrato de `reconhecer` passa a carregar a fonte.

---

## Onda 5 — medidas que podem virar produção

### PD-13 — A régua do `easyocr_so`

Origem: F57 (~8120). Validar fora da amostra o corte "concorda com o k-NN" (como na F56) e
medir o custo (+75% na ação «OCR (EasyOCR)»). Entra só se as duas contas fecharem.

### PD-14 — A prosa do ClearScan

Origem: F110 (~12199). Prosa da camada tipográfica e lance do OCR na mesma linha. Medir.

---

## Onda 6 — bloqueadas (o que falta está escrito, e não é código)

### PD-15 — Rótulos do usuário

- F112 com rótulo: 3 páginas do Yusupov Complete e 3 do Dvoretsky.
- F15: uma página do Yusupov com painel de pontuação (remoção do meio-tom).
- F46: páginas na faixa de distância 1.400–1.700.
- Revisão §5 item 5 (OCR-14): conferir a quarentena dos erros confiantes.
- Revisão §5 item 6: transcrever páginas das famílias imagem, tabela, trama, negativo e
  diagramas (menos de 3 cada).

### PD-16 — Retreino

- F106/F107: recorte em 32×32 sem esticar (+2,8 pontos medidos).
- F94: efeito da semente de letras.
- F69/F115: refazer a `NOTA_MINIMA` com `medir_reparo.py --nota`.
- F1.3: retreino em 100% dos dados na melhor época.

### PD-17 — Motor de linha afinado (F113)

Afinar o Kraken nestes livros; depende do corpus da PD-15.

### PD-18 — OCR-17

Comparação com Acrobat/ABBYY: depende de ter as saídas deles.

### PD-19 — Antigas

F8 (ângulo não múltiplo de 90°, sem material), F1.7 (linha principal × variante),
F9.2 (lista de palavras sem frequência — precisa de uma fonte de frequências).

---

## Registro de execução

| Fase | Status | Data | O que divergiu |
|---|---|---|---|
| PD-00 | **feita** | 2026-09-29 | Os três patches aplicaram limpo. A seção F121 entrou no `ROADMAP.md` entre a F120 e a F122, e o parágrafo da F112 e a nota da F120 passaram a apontar para o conserto. |
| PD-01 | **feita** | 2026-09-29 | A sondagem saiu do pytesseract e passou a chamar o executável por `_sondar` (`Popen` + `communicate(timeout=)`, `PRAZO_DA_SONDAGEM_S = 10`); `--list-langs` sem resposta também conta como indisponível. O disjuntor da janela ficou por box (`BOXES_SEM_RESPOSTA_ATE_DESISTIR = 2`). Antes, o primeiro prazo vencido derrubava a tarefa inteira e perdia o que já estava lido. Os dois disjuntores só existem no «OCR (Tesseract)», a única ação da janela que consulta o motor por box. |
| PD-02 | **feita** | 2026-09-29 | `_esperar_sem_travar`: a sondagem roda numa thread e a interface processa eventos depois de 0,2 s. Nesse intervalo, `_busy` recusa outra tarefa e o fechamento pede para aguardar. Vale para a régua da camada, o idioma e o Tesseract da caixa de exportação, e para a sondagem do `_confirmar_motor_de_prosa`. `provar_letras` passou a usar programação dinâmica, com a nota igual bit a bit à da enumeração (400 casos aleatórios no teste). |
| PD-03 | **parcial** | 2026-09-29 | A célula guarda o `\n`: sai `<br/>` no EPUB e no HTML do IR, quebra no run do DOCX e `quebra_antes` no editor. O texto corrido e a evidência do IR continuam com espaço. **Não entraram:** (1) duas tabelas na mesma página, porque não há caso no material e a marca `moldura` é booleana (separar exigiria um id por bloco em `trama`, `box_service` e `livro`); (2) a pontuação miúda, que já estava resolvida no código (o retângulo da tabela pega o que a marca não pegou), faltava só o registro; (3) a moldura como box descartado, que não chega a nenhuma saída. |
| PD-06 | **feita (camada)** | 2026-09-29 | O itálico vem pela bandeira `TEXT_FONT_ITALIC` ou pelo nome da fonte e vai para `Paragrafo.italico`. Sai `<em>` no EPUB e no HTML do IR, `run.italic` no DOCX, `italic_spans` no IR (só quando há) e itálico no editor. Medido: 4,4% dos glifos no Dvoretsky e 2,0% no Darcy Lima, e zero nos outros livros. Nas p. 21–60 do Dvoretsky caiu nas 12 regras e definições que o livro destaca. **O OCR continua sem itálico**: detectar pela inclinação precisa de régua medida (a F105 é o molde) e de página rotulada com itálico. |
| PD-07 | **feita** | 2026-09-29 | A detecção de capítulo pela camada já existia (`pdf_nativo._capitulo`, `nivel=1`). Nas páginas digitalizadas, `DETECTAR_CAPITULOS = False` continua pelo motivo que a F111 mediu. **Aspa curva:** `exportar.aspas_curvas` troca um caractere por um, então as fatias de negrito e itálico continuam valendo. Vale no parágrafo, no título, na célula e no sumário do EPUB, e no DOCX. O texto da página fica como o OCR leu. |
| PD-08 | **já feita (F67)** | 2026-09-29 | A faixa do cabeçalho já sai como título pesquisável desde a F67. Volta a ser imagem quando uma letra é fraca, por escolha medida lá (o buraco seria o número do exercício). |
| PD-09 | **feita (Word)** | 2026-09-29 | **O Word 16 usa a SkakNew-Diagram CFF embutida.** Conferido por COM com a família renomeada para um nome que não existe no sistema: o tabuleiro sai com as peças, e sem o embutimento cai em Calibri. Não é preciso converter para TrueType. **Achado de passagem:** o DOCX do exportador de livro quebrava toda fila do tabuleiro no Word (a oitava casa descia), nas duas fontes, e isso já estava no HEAD. A caixa tinha a largura exata e o teste lia o XML, não o Word. Corrigido com `FOLGA_DA_CAIXA_PT = 1,5`, a folga que o editor já usa desde a ED-09. **Não entraram:** coordenada em glifo na SkakNew e a diferença no escape do `"` (as duas de baixo valor). |
| pingo do `i` | **medido, não compensa** | 2026-09-29 | A família A caiu de 2,03% (F109) para **0,18%** no Yusupov CE1, p. 8–60 (9 palavras em 4.877, e várias delas são nomes abreviados, como `M.Tal` e `T.Von`). Uma régua de diacrítico nova não se paga nesse resíduo. |
| PD-20 | **feita** (nova) | 2026-09-29 | Apareceu na medição do pingo. As aberturas de lição do Yusupov (p. 9, 19, 29, 37, 47, 57) têm prosa sobre trama, e a cadeia própria lê a letra partida em duas: `tlie`, `vvith`, `niake`, `bisliop`, `diagona[`, `veryr`. `livro._corrigir_juncoes` desfaz as junções `li`→`h`, `vv`→`w`, `ni`→`m`, `rn`→`m`, `Li`→`u`, `[`→`l`, `yr`→`y`. Só atua nas linhas que ficam com a cadeia própria, só em palavra que o léxico não conhece, e só quando há uma única variante conhecida que seja comum (`zipf` ≥ 3,5) ou termo de xadrez (`pawns` tem 2,99; `ther`, que é lixo, tem 3,10). `tl`→`d`, `cl`→`d` e `ii`→`u` foram medidas e recusadas. **Resultado (Yusupov p. 8–60):** palavras com defeito de 651 para 520 (13,35% → 10,62%), com 143 trocas conferidas uma a uma e uma duvidosa (`niar`→`mar`). **Controle negativo:** zero trocas em 228 mil palavras de texto limpo (camada do Dvoretsky, do Aagaard e do Nunn). |
| PD-13 | **feita** | 2026-09-29 | **As duas condições que a F57 deixou estão atendidas.** (1) Fora da amostra: a tabela `--regua` ganhou a coluna em que o corte de cada página é ajustado nas outras, ao orçamento de hoje delas. "Concorda, e a confiança dentro" pega **2.918 erros em 4.731 marcados, contra 2.079 em 4.741**. Nos boxes que a base não tem, são 1.444 contra 1.092. (2) Custo: aceito, mais uma consulta ao k-NN por box lido na ação «OCR (EasyOCR)». **Em produção entrou a regra conservadora:** a leitura que o k-NN não confirma sai `easyocr_discorda`, que está em `FONTES_SEMPRE_REVISADAS`, e a confiança continua a do EasyOCR. Na medição ela marca 5.657 de 11.484 (hoje 4.739) e pega 2.928 dos 2.977 erros; os que escapam caem de 898 para 49. **Registrado, não embarcado:** a binária pura ("só o que o k-NN não confirma") marcaria 3.018 e pegaria 2.897, mais barata, mas tiraria da fila boxes que hoje são revisados. A ação «por linha» não mudou, porque a F55 mediu outra separação lá. |
| PD-14 | **feita** | 2026-09-29 | `scripts/medir_prosa_da_camada.py` mede, contra a referência, as três páginas do corpus com camada ClearScan. **A camada inteira perde:** a prosa dela tem 30% de CER e a notação 56%, contra 13% e 3% da produção, porque a ordem de leitura dela cruza colunas e tabelas. **A palavra dela ganha:** `livro.reparar_pela_camada` troca só a palavra de prosa que o OCR leu e o léxico não conhece pela palavra alinhada da camada, desde que essa seja conhecida, parecida (`SEMELHANCA_DA_CAMADA = 0,5`) e se encaixe de ponta a ponta (`_pontas_casam`). Essa última trava recusa o pedaço (`ofstud`→`study`, `J.Nunn`→`Nunn`), achado na listagem de 12 mil palavras e não na medida. Com o léxico ligado dos dois lados, a p. 47 do Yusupov (trama) vai de 11,51% para **9,93%** de CER na prosa, e as outras duas saem iguais. Na listagem (Nunn p. 20–40, Yusupov p. 8–30) são 103 trocas, todas certas (`B1ack`, `r00k`, `xiuares`, `()therwise`, `Brudoky`). Só vale com a camada ligada (`extrair(camada="auto")`, o modo da exportação), e só na página recusada por fonte do ClearScan (`Veredito.clearscan`). O Paper Capture (texto invisível, Darcy Lima) não foi medido e fica de fora. |
| PD-10 | **recusada** | 2026-09-29 | A F123 já tinha recusado com medida: no «Híbrido» as candidatas são do k-NN, cuja confiança é distância, e a massa do grupo não quer dizer nada ali. O pingo do `i` (`Thi.s`) segue pendente e pede uma régua de diacrítico. |
| PD-12 | **recusada** | 2026-09-29 | A F116 mediu o que ela abriria: cerca de 0,05 ponto (97,52% contra 97,50%). Não compensa mudar o contrato de `reconhecer`. |
| PD-04 | **feita** (maior que o previsto) | 2026-10-05 | **Contado antes:** o "título de duas linhas" quase não existe — a mobília (d1c0b22) já o tirava da conta. O que sobrava eram **blocos de largura inteira que não são mobília**: no Nunn, o título de seção com o sumário dele no meio da página (duas colunas em cima, cinco linhas de lado a lado, duas embaixo); no Yusupov, o quadro «Scoring» e o parágrafo em itálico do fim de todo capítulo. A página saía de uma coluna, intercalada. `BoxService._calha_por_blocos` parte a página pelos vãos verticais (`FOLGA_ENTRE_BLOCOS = 0,8` passo), toma cada bloco de `FILEIRAS_DA_SEMENTE = 6`+ como semente, julga cada vão dela sozinho e fica com a calha que mais linhas respeitam; o bloco que a atravessa sai, na ordem de leitura, no lugar dele (`_colunas_e_transversais`). Só entra quando a régua da F70 dá uma coluna. **Travas, cada uma achada no A/B do corpus inteiro** (3.200 páginas; instrumento de sessão, não versionado): sem elas a regra mexia em 166 páginas do Rubinstein (tabela de lances brancas \| pretas entre parágrafos), 7 do Seirawan e 4 do Darcy Lima, que são de coluna única. `_colunas_de_texto` exige tinta de `COLUNA_DE_TEXTO = 0,35` da largura em cada coluna, colunas encostadas nas margens (`COLUNA_NA_MARGEM = 0,08`, contando só blocos de 2+ fileiras — o número da página no canto completava a margem), um terço das fileiras começando na margem, e calha a menos de `CALHA_FORA_DO_MEIO = 0,08` do meio. A primeira versão também chamava de transversal todo bloco menor com caixa na calha e mexia em páginas que a F70 já lia certo (as três linhas do alto do Nunn, apartadas por um diagrama, saíam de lado a lado): transversal agora é só o bloco que a conta rejeitou. **Resultado:** Nunn 19 páginas consertadas, Yusupov Complete 8 (amostra de 1 em 5), CE1 2; Seirawan, Calculation, Attacking e Dvoretsky **0** mudanças; restam 5 no Rubinstein (páginas de foto: o ruído da foto vira "coluna", a legenda de largura inteira sai inteira, no lugar) e 2 no Darcy (texto contornando diagrama: o texto sai contíguo). Fica fora a p. 151 do Yusupov Complete. Testes: `tests/test_pd04_bloco_sobre_a_calha.py` (geometria + Nunn, Yusupov e Darcy quando estão na máquina). |
| PD-05 | **feita** | 2026-10-05 | **Medido antes:** a varredura das páginas de várias colunas (instrumento de sessão; razão entre a tinta da coluna mais estreita e a da mais larga) achou um defeito antigo maior que o glossário: a **régua adaptada** (calha de 0,55 caractere, feita para os 13 px do Yusupov) aceitava um espaço entre palavras de 16 px alinhado no texto justificado, e a página de coluna única saía com uma "coluna" de 10% da largura — o começo de cada linha lido antes de todo o resto. Agora a calha adaptada só vale se toda faixa tiver `COLUNA_DE_TEXTO` da largura. Páginas de várias colunas: Seirawan 25 → 17, Rubinstein 55 → 40, e as duas perdas fora deles também eram erro (o índice do Calculation, nome \| páginas, passa a sair fileira a fileira; a bibliografia do Attacking Manual); Nunn, Yusupov, CE1 e Dvoretsky **iguais**. **O glossário, na segunda passada:** `BoxService._e_tabela` lê fileira a fileira as duas faixas em que a estreita tem tinta de menos de `TABELA_RAZAO = 0,40` da larga, 5+ linhas (`TABELA_LINHAS`) e metade delas com par na mesma altura do outro lado (`TABELA_PAR`). Medido antes de cortar: as tabelas ficam de 0,15 a 0,34 (glossário do Darcy 0,20, «List of symbols» do Attacking 0,27, torneios e lances do Rubinstein 0,33–0,34, títulos de lance pendurados do Seirawan 0,15); o primeiro caso que não é tabela está a 0,40 (as grades de diagramas com legenda do Attacking, onde nenhuma leitura serve, e ficam como estavam); a coluna de texto mais desigual, as soluções do Yusupov, passa de 0,5. Três faixas ou mais não entram, e os índices de três colunas do Calculation não mudam. **A/B no corpus inteiro: mudam exatamente as 5 páginas-alvo, e nenhuma outra.** |
| PD-11 | **feita** | 2026-10-05 | **Medido antes** na amostra da F115 (60 págs/livro, semente 11): das 23 linhas de prosa que a faixa comia, o `_devolver_a_linha_de_prosa` do Khenkin (c5289df) já tinha devolvido quase todas — Dvoretsky 6 → 0. Sobravam as do Darcy Lima (5), e a causa era uma só: a vizinhança só devolvia letra pega **pelo pé**, e a letra **dentro** do retângulo de exclusão acima do tabuleiro (`criação.`, à esquerda dele) ficava presa e quebrava a corrente — `A essência deste método` virava título (p. 144). Agora a letra dentro da exclusão e acima da borda do tabuleiro também pode voltar. Darcy 8 → 3 linhas recolhidas (as 5 de prosa e os pontos soltos voltam; sobram «Peões» e `♘ ♙`); Calculation perde 2 vírgulas soltas; os cabeçalhos dos dois Yusupov (129 e 102), Nunn e Razuvaev ficam idênticos. A direção do vão vertical acima da linha não precisou ser usada. As junções de hífen da F115 estão na PD-20 e no 85edc47. |
| PD-16 (recorte encaixado) | **medida, recusada com a base de hoje** | 2026-10-05 | **Antes de retreinar, duas premissas caíram.** (1) 56% da base (356.209 de 630.909 PNGs) foi gravada já esticada em 32×32, antes da F107, com nome UUID e sem rastro de página: a proporção não é recuperável, e as letras são justamente as mais esticadas (`s` 95%, `o` 95%, `S`/`0`/`W`/`g`/`k` 98–99%, `x` 100%); 76 das 316 classes só existem esticadas. (2) O +2,8 da F107 foi do braço encaixado **com** tamanho; o só-imagem não tinha sido medido. `medir_tamanho.py` ganhou `--so-imagem` e `--misto`; 7 turnos, um livro de fora, 15 épocas: esticado (produção) 93,70% (família de caixa 92,53%); encaixado com a base toda original **95,55%** (94,20%); **misto — cada amostra esticada com a fração real da classe dela, lido encaixado, que é o que o retreino daria — 93,36% (90,06%)**, quebrando 538 acertos da família e consertando 369 (`W` 0%, `c` 78,7%). O ganho existe, mas só com a base regravada em tamanho original, e o que falta regravar é a rotulagem feita na tela: vai para a Onda 6 como dado do usuário. O modelo de produção não mudou. |
| PD-16 (F1.3, base inteira) | **medida, empate — produção mantida** | 2026-10-06 | `NeuralTrainer.train(base_inteira=True)`: 100% das amostras (630.909, 316 classes, já com o que foi rotulado depois de 25/08) por 24 epochs fixas — a melhor epoch do último treino com validação — e grava a última; sem relatório, porque a validação mediria o que o modelo viu (`tests/test_pd16_base_inteira.py`). 150 min de CPU, T = 1,926. **Comparado com a produção:** corpus de referência, CER total 1,59% contra 1,59% (prosa 1,44% → 1,29%, notação 1,88% → 2,16%, Aagaard p. 30 1,30% → 1,71%, além da tolerância da rodada); páginas rotuladas por caractere 94,46% contra 94,46%, com 10 consertos e 11 quebras em 11.597. Os 20% a mais de amostras são dos mesmos livros, e o erro que sobra é o de livro novo (93,7% com um livro de fora, na medida da PD-16 encaixado). Não troca o modelo. O modo fica para o próximo retreino que tiver base nova de verdade. |
| PD-19 (F9, poda por frequência) | **medida, recusada** | 2026-10-06 | O bloqueio era a falta de frequência, e ela existe desde a PD-20 (`wordfreq`). `medir_troca.py --poda` tira da parte de idioma as palavras abaixo de um `zipf` e mantém os nomes inteiros, rodando o OCR de verdade nas páginas rotuladas: de zipf 0,5 a 2,5 o recall fica em 35,0% (35 erros pegos em todos os cortes) e o alarme falso sobe de 4,0% para 5,0%. Nenhum erro de OCR desta amostra cai numa palavra rara da lista — a hipótese `glans`-por-`plans` não aparece —, então a poda só custa. **Achado de passagem:** os "erros escondidos" que o arnês lista são quase todos erro da **verdade rotulada**: no `Kasparov…_page-0020.box`, `Nirst` (y≈162), `prospectt` (y≈412), `diagonaL` (y≈464), `seCond` e `whiTe` (y≈1760); no `_page-0108.box`, `frst` (y≈928); e `theoy`, `Opn`, que a busca por linha não localizou. É dado do usuário (Onda 6): corrigidos, sobem o recall medido do léxico. |
| PD-19 (F1.7) | **encerrada pela medida da F7** | 2026-10-06 | Linha principal × variante por tipografia já foi medida e refutada (AUROC 0,55–0,67 nas páginas rotuladas); a regra que vale é a do número de jogada que retrocede, e ela já está no analisador. Nada a fazer. |
