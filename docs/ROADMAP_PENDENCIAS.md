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
| PD-07 | **metade já existia** | 2026-09-29 | A camada de texto já faz capítulo pelo corpo (`pdf_nativo._capitulo` → `nivel=1`). Nas páginas digitalizadas, `DETECTAR_CAPITULOS = False` continua pelo motivo que a F111 mediu. Falta a aspa curva. |
| PD-10 | **recusada** | 2026-09-29 | A F123 já tinha recusado com medida: no «Híbrido» as candidatas são do k-NN, cuja confiança é distância, e a massa do grupo não quer dizer nada ali. O pingo do `i` (`Thi.s`) segue pendente e pede uma régua de diacrítico. |
| PD-12 | **recusada** | 2026-09-29 | A F116 mediu o que ela abriria: cerca de 0,05 ponto (97,52% contra 97,50%). Não compensa mudar o contrato de `reconhecer`. |
