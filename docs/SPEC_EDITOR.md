# A janela de edição e a conversão para HTML, EPUB e DOCX — especificação

Versão do documento: 1.3
Data: 2026-09-19
Status: **especificação — nada implementado**; o registro do que for feito fica em
[`ROADMAP_EDITOR.md`](ROADMAP_EDITOR.md), e onde os dois discordarem o ROADMAP vale
(mesma convenção da [`SPEC.md`](SPEC.md) §0).
Companheiros: [`ROADMAP_EDITOR.md`](ROADMAP_EDITOR.md) (fases `ED-nn`),
[`SPEC-CONVERSAO.md`](SPEC-CONVERSAO.md) (o que sai errado do OCR e chega ao arquivo),
[`SPEC_IMPLEMENTACAO_OCR.md`](SPEC_IMPLEMENTACAO_OCR.md) §10 (contratos dos exportadores),
[`../CONTEXT.md`](../CONTEXT.md) (glossário e invariantes do domínio).

**Histórico.** A v1.0 (2026-09-19) passou por duas voltas de revisão adversarial
independente — arquitetura e viabilidade em Tk, editoração digital (EPUB 3, OOXML,
paridade com Sigil e Word), acessibilidade e UX, verificabilidade e execução a frio —,
oito pareceres ao todo, com 28 achados críticos, 111 maiores e 93 menores (a terceira
volta não achou crítico nenhum). Esta v1.3 incorpora os que se confirmaram no ambiente (`.venv`, Tk 8.6.15, Windows) e registra na
§15 os que viraram limite declarado. Os que mais mudaram o desenho: o `tk.Text` desenha
**uma** fonte por caractere e não tem sublinhado ondulado (DEC-03, §13.2); o EPUB 3 não
aceita `&nbsp;` nem as demais entidades nomeadas, e o `expat` só as resolve com
`SetParamEntityParsing` (DEC-07); `id` é único por **capítulo**, não por livro (INV-01);
o `ReviewEvent` do documento editorial transporta só o valor da decisão, não o formato
(DEC-10); a marca de página **impressa** não é uma quebra de página (§6.1); validar
notação exige segmentar as partidas (§11.3); o tema `vista` do `ttk` não desenha anel de
foco (§13.2); atalhos colidiam entre si, com os mnemônicos de menu e com as ligações da
classe `Text` (§7.4); e os testes de interface não podem digitar teclas numa janela
retirada da tela (§14).

---

## 0. Como ler este documento

Está escrito **antes** da implementação, no futuro do imperativo. Cada decisão de
arquitetura tem um número (`DEC-nn`) e um "por quê"; cada critério de aceite tem um
(`AC-nnn`) e um jeito de verificar; cada fase do ROADMAP cita os dois. Quem for
implementar uma fase lê a seção "contexto para começar do zero" dela no ROADMAP, que
aponta as seções daqui que importam.

**Dois princípios que valem em toda seção**, herdados do projeto:

1. *O que tem regra mora em `core/` e tem teste sem display; o widget só desenha e
   despacha* (é a regra de `core/tabuleiro_edicao.py`, e é o que torna o editor testável).
2. *Nenhuma falha é silenciosa*: arquivo que não abre, XHTML que não é bem-formado,
   entidade que o parser não conhece, fonte sem o glifo, diagrama sem FEN, atalho que a
   classe `Text` do Tk consumiria por baixo — tudo aparece na tela com o motivo, e nada
   vira um arquivo "quase certo" (invariante 5 do `CONTEXT.md`).

---

## 1. O problema

Hoje o fluxo é **PDF → OCR → arquivo**, sem parada no meio. Quem precisa trocar uma
palavra, devolver um itálico que o OCR não lê, corrigir um bispo lido como peão, partir
um capítulo ou escrever um prefácio faz isso **no Word ou no Sigil, fora do programa** —
e perde, nessa saída, tudo o que só o programa sabe:

- o **FEN** do diagrama (no DOCX sobra a imagem ou o texto na fonte; a posição, não);
- a **proveniência** (página e caixa de origem de cada bloco — invariante 4 do
  `CONTEXT.md`);
- o **diário de revisão** (a decisão editada fora não vira evento — invariante 9);
- a **fonte dos símbolos** e o mapa de figurinas (`♕` no Word sem a fonte vira caixa);
- e, na próxima exportação, **tudo**: o arquivo é reescrito do zero e a correção some.

A [`SPEC-CONVERSAO.md`](SPEC-CONVERSAO.md) mediu o tamanho do trabalho que sobra para a
mão humana: **uma palavra de prosa em cinco com defeito** no livro que sai pior, **zero
runs em itálico** em 36.442, aspas retas onde o impresso tem curvas, e o versalete dos
nomes de jogador perdido inteiro. Parte disso as fases seguintes do OCR vão reduzir; o
resto é revisão editorial — e o programa não tem um lugar para ela.

A janela desta spec é esse lugar. Nela o livro se edita **por dentro**, com os objetos de
xadrez como objetos, e **os formatos saem do mesmo livro editado** (invariante 6).

---

## 2. Escopo

### 2.1 Dentro

- Uma **janela própria** (`Toplevel`), aberta pelo menu da janela principal, ao fim de
  uma exportação de livro ("Abrir no editor"), ou sozinha (`appy.py --editor livro.epub`).
- **Modo texto**: edição rica, à maneira do WordPad e do Word — caractere, parágrafo,
  estilos, listas, tabelas, imagens, notas, links, referências cruzadas, quebras,
  localizar/substituir, ortografia, tipografia, contagem, zoom, invisíveis (§8).
- **Modo código**: edição do XHTML/CSS do livro à maneira do Sigil — navegador do livro,
  editor com realce, bem-formado e "consertar", localizar/substituir com regex em vários
  arquivos e buscas salvas, clipes, sumário, metadados, capa, semântica, relatórios,
  validação com epubcheck, pré-visualização, pontos de verificação (§9).
- **Objetos de xadrez** nos dois modos: diagrama com FEN, lado a jogar, marcas e setas,
  editor de posição, diagrama a partir dos lances (com variantes e partidas), validação
  de notação, figurinas ao digitar, NAGs por código, numeração e referências, índice de
  jogadores/partidas/aberturas, chave de símbolos, PGN (§11).
- **Conversão**: escrever EPUB 3, HTML (arquivo único ou pasta), DOCX, PDF paginado e
  TXT; **abrir** EPUB, HTML/XHTML, DOCX, TXT e o JSON do documento editorial (§10).
- **Ponte com o pipeline**: o livro exportado pelo OCR abre no editor com a proveniência
  de cada bloco; salvar de volta gera eventos de revisão (§10.6.5, DEC-10).

### 2.2 Fora (com o motivo)

- Paginação WYSIWYG na tela — o `tk.Text` não pagina; a página existe no PDF e no DOCX.
- Impressão direta — o Tk não imprime; "Imprimir…" gera o PDF paginado e o abre.
- **Ofuscação de fontes no EPUB** — `exportar.ofuscar` é a ofuscação do **Word**
  (ECMA-376 §17.8.1); a do EPUB é outra (IDPF, SHA-1 do identificador, 1040 bytes,
  `META-INF/encryption.xml`), nenhuma das fontes embutidas a exige, e o EPUB de hoje não
  ofusca. Sai do escopo.
- **Negrito e formato na ponte com o documento editorial** — o `ReviewEvent` de
  `core/editorial_model.py` não tem campo para estilo, e `editorial_legacy` zera o
  negrito de todo parágrafo revisado; a ponte transporta só o texto (DEC-10, §10.7). Abrir
  esse canal é pedido registrado na fase ED-pré, do usuário.
- Controle de alterações estilo Word, comentários de revisor, edição simultânea.
- EPUB 2 como saída (sai EPUB 3 com NCX de compatibilidade), layout fixo, MathML,
  escrita da direita para a esquerda, áudio e vídeo.
- Índice remissivo genérico do Sigil — o índice de um livro de xadrez é de jogadores,
  partidas e aberturas, e esse **está** dentro (§11.9).
- Régua de recuos e tabulações do WordPad — o EPUB não representa tabulações, e os recuos
  se editam pela caixa Parágrafo e pelo painel.
- Plugins, macros, mala direta, atalhos personalizáveis, "Salvar uma cópia", colunas,
  espaçamento entre caracteres, kerning e ligaduras por trecho, estilos de tabela,
  ordenar, converter texto em tabela, desenhos, unidades de medida, visualizar impressão
  (= o PDF), capitulares (uma regra `::first-letter` cabe na folha do livro).
- Arrastar arquivos sobre a janela — não há `tkdnd`.
- Reescrever o OCR. Melhorá-lo é assunto do [`ROADMAP_OCR.md`](ROADMAP_OCR.md).

### 2.3 Suposições (a confirmar com o usuário; nada aqui foi lido do código)

- Interface em **português do Brasil**; teclado de referência ABNT2 (é o que decide, na
  §7.4, contra `Ctrl+Alt`, que é o `AltGr`).
- Leitores-alvo do EPUB: Calibre, Apple Books, Thorium, Kindle por "Enviar para o
  Kindle"; DOCX para **Word 2016+** e LibreOffice.
- Livros de um idioma por vez (`en` ou `pt`), como a caixa de exportação já supõe.
- Um usuário, uma máquina, Windows — o registro de fontes por processo (`ui/fontes.py`)
  só existe lá (§15).

### 2.4 Decisões bloqueantes

Nenhuma. As escolhas que mudariam o desenho estão nas decisões (§4) com o motivo.

---

## 3. Glossário do editor

Complementa o `CONTEXT.md`; a mesma palavra tem o mesmo sentido nos dois.

- **Livro**: a unidade que a janela abre, edita e salva — capítulos, recursos, folhas de
  estilo, metadados, sumário, marcos e formato de página. Na sessão é um objeto
  (`Livro`, §5); no disco é um **EPUB** (DEC-01).
- **Capítulo**: um arquivo XHTML do livro, com nome, título, blocos e notas. É a unidade
  que o modo texto mostra por vez e que o modo código abre numa aba.
- **Bloco**: parágrafo, título, lista, tabela, figura, diagrama, citação, quebra de
  página, marca de página impressa, separador ou ilha bruta. Tem `id` (único no
  capítulo), estilo, atributos preservados e, quando veio do OCR, origem.
- **Trecho**: corrida de texto com o mesmo formato de caractere dentro de um bloco — ou
  uma **ilha inline**, ou uma referência de nota, ou uma marca de página inline.
- **Dialeto**: o vocabulário XHTML+CSS que o modo texto sabe editar e que os
  exportadores sabem escrever (§6).
- **Ilha bruta**: um pedaço de XHTML fora do dialeto, preservado (de bloco ou inline) e
  editável só no modo código (DEC-02).
- **Recurso**: imagem, fonte, folha de estilo ou arquivo avulso do livro.
- **Projeto**: o livro aberto mais o que a sessão sabe dele — caminho, sujo, histórico,
  rascunho, recentes, pontos de verificação, documento editorial ligado.
- **Painel**: área acoplável (navegador, sumário, estilos, propriedades, xadrez, busca,
  resultados, mensagens, validação).
- **Calha**: a coluna à esquerda do editor onde ficam os números de linha (código) e os
  ícones de aviso (texto) — desenhada num `Canvas` alinhado por `dlineinfo`.
- **Estilo**: nome de parágrafo ou de caractere que mapeia para elemento+classe no
  dialeto e para um estilo nomeado no DOCX (§6.3).
- **Clipe**: trecho de código guardado com nome (o *clip* do Sigil). **Busca salva**: o
  *Search Editor* do Sigil. **Ponto de verificação**: o *checkpoint* do Sigil.
- **Estilo de tela**: a folha interna com que o modo texto desenha o dialeto.

---

## 4. Decisões de arquitetura

### DEC-01 — O livro no disco é um EPUB; na sessão, é o modelo de blocos

"Salvar" grava um **EPUB 3 válido**. HTML, DOCX, PDF e TXT são **exportações**.

Na sessão, o capítulo em edição no modo texto vive como **modelo de blocos** (§5), e no
modo código como **texto XHTML** (`Capitulo.texto_cru`); uma folha de estilo em edição
vive como `Recurso.texto_cru`. A passagem entre modos é o par de funções puras
`xhtml.ler(texto) → Capitulo` e `xhtml.escrever(capitulo) → texto`, com o contrato da
§6.5. O modo ativo é o dono: `texto_cru` não-nulo significa que a aba está em código e o
texto manda; a troca para texto o converte e o zera. **OPF, `nav.xhtml` e NCX são
sempre regenerados** do modelo ao salvar, e por isso abrem em código **somente leitura**
(editar o manifesto à mão criaria uma segunda verdade sobre os recursos).

**Consequência.** Trocar de modo ou salvar com um XHTML que não é bem-formado, ou com
um prefixo de namespace não declarado, é recusado com linha e coluna (AC-004); trocar de
modo com uma construção fora do dialeto vira ilha, não perda (DEC-02).

### DEC-02 — Um dialeto explícito, e ilhas brutas para o resto

O modo texto edita **só** o vocabulário da §6. Qualquer elemento fora dele vira **ilha
bruta** — de bloco (um `<svg>`, uma tabela aninhada) ou **inline** (um `<cite>`, um
`<span epub:type>`, um `<img>` no meio do parágrafo): o XHTML original fica guardado, o
modo texto mostra um objeto cinza com o nome do elemento (de bloco) ou um glifo
reservado com dica (inline) — *"conteúdo fora do dialeto — editável no modo código
(F11)"* —, e o modo código o edita normalmente.

Atributos que o dialeto **conhece e preserva**: `id`, `class`, `lang`, `xml:lang`,
`title`, `dir`, `epub:type`, `role`, `aria-label` e os `data-*` da §6. Qualquer outro
atributo faz o elemento virar ilha. Sinônimos aceitos ao ler e normalizados ao escrever:
`<b>`→negrito, `<i>`→itálico, `<strike>`/`<del>`→tachado, `<ins>`→sublinhado.

**Por quê.** O Sigil **removeu** a *Book View* na versão 1.0 porque um WYSIWYG sobre HTML
arbitrário é insustentável; sobre um dialeto fechado é sustentável. A ilha inline existe
porque, num livro importado, um `<cite>` no meio do parágrafo é comum.

### DEC-03 — `tk.Text` com tags é a superfície do modo texto

O capítulo é desenhado num `tk.Text`. As regras que a v1.0 não tinha:

**Uma fonte por caractere.** O Tk aceita uma única `-font` por caractere; quando duas
tags definem fonte, só a de maior prioridade vale. Por isso os atributos **próprios** do
trecho ficam em **tags-marcador sem `-font`** (`b`, `i`, `vers`, `sobre`, `sub`,
`fam:<nome>`, `corpo:<pt>`) — são elas que dizem o que é do trecho e o que é herdado do
estilo do parágrafo —, e a fonte que se vê é uma **tag derivada** `fonte:<família>:
<corpo>:<b><i><sobre|sub|vers>`, calculada de estilo ⊕ marcadores, com um `tkfont.Font`
por combinação em cache, e **descartada** em `dump_para_blocos` como as tags de tela.
Tags independentes para o que o Tk trata à parte: `u`, `s`, `cor:`, `fundo:`, `offset`
(sobrescrito/subscrito) e as de parágrafo (`justify`, `lmargin1/2`, `rmargin`,
`spacing1/2/3`). Versalete não existe no Tk: na tela sai o texto **inalterado** num
corpo 0,85 (`vers`); o arquivo sai certo (§15).

**Identidade de bloco.** Um bloco é o **intervalo entre a sua marca e a próxima** —
`mark` `bloco:<id>` (gravidade `left`) até a marca seguinte ou `end`. Um bloco pode ter
vários `\n` por dentro: o `\n` de item de lista, de parágrafo de citação e de quebra de
linha suave leva a tag `quebra`+`protegido` (o `tk.Text` só quebra linha com `\n`, e um
`⏎` sem `\n` não quebraria). `dump(mark=True)` dá a ordem; marcas coincidentes = bloco
apagado (a mais nova sobrevive); `enter()` cria bloco novo (`dividir_paragrafo` +
`id_novo()`) **fora** de lista, citação e nota, e item/parágrafo interno **dentro**; após
`<<Modified>>` as tags de parágrafo são reaplicadas no intervalo da marca (o Tk só herda
tag presente nos dois vizinhos). `dump_para_blocos` converte o `\n` com `quebra` em
`quebra_antes` do trecho seguinte, o `\n` de item em novo `ItemDeLista`, e descarta as
tags de tela.

**Objetos.** Diagrama, figura, tabela, ilha de bloco e ilha inline entram por
`image_create(name=<id>)` ou `window_create`, e um `RegistroDeObjetos` liga o nome ao
bloco (ou ao `Trecho(ilha=…)`) — é de lá que o `dump` os recupera byte a byte. Todo bloco
sem objeto próprio na fase corrente é desenhado por um **`ObjetoGenerico`** (caixa cinza
com o tipo do bloco, protegida), de modo que um capítulo com diagramas abre e sobrevive
ao `dump` antes de a ED-05 existir.

**Faixas protegidas.** O `tk.Text` não tem "somente leitura por faixa": marcador de
lista, referência de nota, invisível, objeto, ilha inline, marca de página e ícone de
calha levam a tag `protegido`, e uma guarda única (`_pode_editar`) é aplicada **pela
API** — `inserir`, `apagar`, `apagar_selecao`, `enter`, `backspace` — que é o que todo
handler de tecla chama e o que os testes chamam. `backspace()` no início de um item de
lista diminui o nível; no nível 1, sai da lista. Busca, ortografia e contagem leem o
**modelo**, nunca o widget.

**Ligações de teclado.** O `Text` é criado com `undo=False` (o desfazer é da DEC-04). A
classe `Text` do Tk 8.6.15, medida no Windows, já liga `Ctrl+D` (apaga), `Ctrl+H`
(apaga para trás), `Ctrl+I` (tab), `Ctrl+K` (apaga até o fim), `Ctrl+O` (abre linha),
`Ctrl+T` (troca), `Ctrl+Space` (âncora), `Ctrl+Shift+Space` (estende a seleção),
`Ctrl+Tab`/`Ctrl+Shift+Tab` (saída de foco), `Ctrl+Next/Prior/Home/End`, `Ctrl+/` e
`Ctrl+A` (`<<SelectAll>>`), `Shift+Insert`/`Ctrl+Insert`/`Shift+Delete`
(`<<Paste>>`/`<<Copy>>`/`<<Cut>>`), `Insert` e o botão do meio (`<<PasteSelection>>`).
`Ctrl+BackSpace`/`Ctrl+Delete` **não** estão na classe (só `Meta-…`, que o Windows não
gera): cairiam no `BackSpace`/`Delete` simples e apagariam um caractere — por isso são
comandos do editor ("apagar palavra", pela API, respeitando `protegido`). Toda ligação do editor entra numa *bindtag*
própria (`EditorAtalhos`) posta **antes** de `Text`, todo handler devolve `"break"`, os
comandos de área de transferência ligam-se aos eventos virtuais (`<<Cut>>`, `<<Copy>>`,
`<<Paste>>`, `<<Undo>>`, `<<Redo>>`, `<<SelectAll>>`) e `<Key-Insert>`/`<<PasteSelection>>`
são neutralizados. O `ttk.Notebook` **não** recebe `enable_traversal()` (ligaria
`Control-Next/Prior` por conta própria).

**Calha.** Um `Canvas` à esquerda, alinhado por `dlineinfo`, desenha os ícones de aviso
(`!` suspeito, `✗` notação ilegal, `?` ortografia da linha) — é a "margem" que o Tk não
tem.

### DEC-04 — Desfazer próprio, por bloco e por capítulo, no projeto

`core/editor/historico.py: Historico(limite=200, coalescencia_s=0.7,
relogio=time.monotonic)` — pilha por `capitulo.arquivo` de `(ids, antes, depois)` sobre o
modelo; `TextoRico.ponto()` delega; desfazer num capítulo **não desenhado** restaura o
modelo e marca a aba para recarregar. Nasce na ED-00 porque ED-01 e ED-03 (mesma onda) o
consomem.

### DEC-05 — Pré-visualização própria, mais o navegador do sistema; renderizador HTML embutido é opcional

O painel "Prévia" é o **próprio modo texto, somente leitura**, sincronizado por
`Bloco.linha_fonte`. "Abrir no navegador" grava o capítulo numa pasta temporária e
chama o navegador do sistema. `tkinterweb` (extra `[editor-previa]`) vira uma terceira
aba quando instalado.

### DEC-06 — O diagrama é bloco de primeira classe

Um diagrama é `fen + lado + apresentação`. **O lado a jogar é campo próprio**
(`Diagrama.lado`: `"w"`, `"b"` ou `""` = desconhecido): o FEN guarda a posição, mas
`chess.Board(posição)` assume brancas, e todo diagrama recuperado do EPUB de hoje, de um
DOCX ou do OCR ganharia "Brancas jogam" sem evidência. Lado desconhecido → sem indicador,
sem legenda de lado, aviso; o editor de posição, `posicao_apos` e "Legenda sugerida"
propõem o lado (o número do lance seguinte diz: `23…` → pretas).

No XHTML ele sai como o projeto já sai **mais** os `data-*` da §6.1. Ao **ler**:

- `figure` com `data-fen` → `Diagrama` completo;
- `figure > img` **sem** `data-fen` cujo `alt` passa em `fen_valido` (é o que
  `exportar._alternativo` escreve hoje) → `Diagrama(modo="png", lado="", estado=
  "revisar", aviso="orientação não registrada")`;
- `figure > img` com `alt` que não é FEN → `Figura`;
- `div.diagrama` nu (fonte): o de hoje traz o FEN em `title` e `aria-label`
  (`exportar._alternativo`) → FEN daí, e a **orientação é a que reproduz as linhas
  lidas** (`linhas(fen, fonte, o)` para `o` em branca/preta); só um `div` de fora, sem
  `title` que seja FEN, passa por `render_diagrama.fen_de_linhas` (que devolve a
  orientação quando os glifos de moldura ou os `span.rot` a dizem) — e só sem título
  **e** sem rótulo fica `estado="revisar"`, porque as oito linhas de um diagrama do lado
  das pretas decodificam para a posição girada.

`alt` gerado (`alt_de`) é a lista de peças por idioma ("Brancas: Rei g1, Dama d1, …;
Pretas: …"), e o FEN fica em `data-fen` e `title`.

### DEC-07 — Nenhuma dependência nova obrigatória; e o `core/editor` é leve

- **O parser XML.** O `expat` sem DTD rejeita `&nbsp;`, `&mdash;` e toda referência
  nomeada do HTML, e o EPUB 3 também as rejeita (`epubcheck` `RSC-016`), embora os EPUBs
  do Sigil, do Calibre e do Word as usem. O leitor próprio (`core/editor/xhtml.py`) usa
  `xml.parsers.expat` com `namespace_separator=" "` (prefixo não declarado é erro),
  `SetParamEntityParsing(XML_PARAM_ENTITY_PARSING_ALWAYS)` **antes** de
  `UseForeignDTD(True)` (sem isso o handler nunca é chamado), um
  `ExternalEntityRefHandler` que ignora o `systemId` e injeta as entidades de
  `html.entities.html5` (só as chaves terminadas em `;`, com valores multi-codepoint
  como referências numéricas concatenadas), um `SkippedEntityHandler` que **levanta**
  `ErroDeXhtml("entidade desconhecida")`, comentários e PIs preservados, e
  `CurrentLineNumber` para `linha_fonte`. **Ao escrever**, fora de ilha sai o caractere
  (U+00A0); **dentro de ilha, toda referência nomeada é reescrita como numérica**
  (`&nbsp;` → `&#160;`) — é o único byte que uma ilha muda, e é o que o EPUB 3 exige.
  A ilha é recortada do **texto-fonte em bytes UTF-8** por `CurrentByteIndex`: no
  `StartElementHandler` é o `<`; no `EndElementHandler` de um elemento com conteúdo é o
  início de `</x>` (a fatia vai até o `>` seguinte), e de um elemento **vazio**
  (`<br/>`, `<img …/>`) já aponta **depois** do `/>` — a fatia termina aí.
- **O peso das importações.** `core/exportar.py` importa `core.livro` (numpy, cv2);
  `core/render_diagrama.py` importa `fitz` e `PIL`; `core/tabuleiro_edicao.py` importa
  `core.diagrama` (cv2) no topo; `core/lexico.py` → `core.notacao` → `box_service` (cv2);
  `appy.py` importa `ui.main_window` no topo; `NAGS_POR_FAMILIA` mora em
  `ui/main_window.py`. Nenhum módulo de `core/editor/` os importa no topo: as constantes
  de estilo saem para `core/estilo_do_livro.py` (sem importação pesada; `exportar` as
  importa de lá com os mesmos nomes); `NAGS_POR_FAMILIA` vai para `core/nags.py`;
  `core/tabuleiro_edicao.py` ganha `from __future__ import annotations` e
  `TYPE_CHECKING` para as anotações, e `Casa`/`Leitura` saem para um módulo leve
  (`core/diagrama_modelo.py`, reexportado por `core.diagrama`) — sem isso o editor de
  posição carrega `cv2` ao abrir; `appy.py` importa `MainWindow` dentro de `main()`; `render_diagrama`, `exportar`,
  `livro`, `notacao`, `lexico` e `tabuleiro_edicao` são importados dentro de função em
  `core/editor/*` e `ui/editor/*`. Um teste em subprocesso confere `sys.modules` (e é
  repetido pelas fases que tocam nesses módulos).

`python-docx` continua extra `[docx]`; `epubcheck` vira `[epub-validacao]`; `tkinterweb`
é `[editor-previa]`. O realce é próprio (§9.2).

### DEC-08 — UTF-8 sem BOM em tudo, e XHTML sempre bem-formado ao salvar

Todo arquivo escrito é UTF-8 sem BOM, com `<?xml version="1.0" encoding="utf-8"?>` nos
XHTML (a declaração é regenerada: um `standalone="yes"` de origem não sobrevive, e não
faz falta) e `xmlns:epub="http://www.idpf.org/2007/ops"` no `<html>` sempre que `epub:`
aparecer em qualquer atributo — inclusive dentro de ilhas e em `texto_cru`. Salvar com
capítulo mal-formado é **recusado** com a linha; o rascunho (§7.6) grava o que houver.

### DEC-09 — A janela é separada da principal e não a bloqueia

`JanelaDoEditor` é um `Toplevel` próprio; a principal guarda `self.editor`. Ligações:
"Arquivo → Editor de livro…"; o botão "Abrir no editor" na `DialogoDeConclusao` (que
substitui o `messagebox.showinfo` de conclusão, que não aceita botão); o `TaskController`
da principal para tarefas longas (sozinho, o editor cria o seu). Fechar a principal ou o
processo com o editor sujo passa pela mesma guarda "salvar / descartar / cancelar".

### DEC-10 — A ponte com o documento editorial é por eventos, só de valor, e é opcional

Um livro que veio do pipeline traz em cada bloco a `Origem` (§5). Ao salvar, o editor
usa o diário que o pipeline já convencionou — `documento.metadata["review_journal_path"]`
(`<arquivo>.review.jsonl`), criado com a mesma regra quando não existe — e abre
`ReviewSession.from_journal(documento, ReviewJournal(caminho))`, que repete os eventos
anteriores (senão `apply_review` recusaria todo bloco já revisado na fila com "valor
anterior não confere"). Para cada bloco com origem cujo **valor** difere da decisão
atual, `sessao.edit(origem.bloco_id, after, reason_codes=("editor",))`, com `after` no
formato do IR: texto para parágrafo; para diagrama, o **dicionário inteiro** da decisão
com `fen`/`orientation` trocados (senão `png_base64` e `font` se perdem); `rows` para
tabela. Bloco com origem **apagado** → `sessao.reject(...)` (sai com `("rejected",)`);
blocos **fundidos** → `edit` no primeiro e `reject` nos demais (`origem.fundidas`);
bloco novo → sem evento, listado no relatório. O documento projetado passa a ser
`sessao.document`. **Formato não viaja**: o `ReviewEvent` não tem campo de estilo, e o
negrito/itálico editado é perda declarada (§2.2, §10.7). Um livro aberto de um EPUB
qualquer não tem documento editorial e a ponte não existe.

**Duas verdades, uma resposta.** Enquanto o editor estiver aberto sobre a exportação da
sessão, "Exportar com as correções" da fila de revisão fica desabilitado com o aviso *"o
livro está no editor; exporte por ele"*. A proveniência só sobrevive no EPUB e no JSON.

### DEC-11 — Um capítulo por vez no modo texto

O modo texto desenha **o capítulo atual**; as abas se criam ao abrir pelo navegador.
Busca, substituição, ortografia, relatórios e desfazer operam no livro inteiro pelo
modelo.

### DEC-12 — Estilos nomeados são a ponte entre os três formatos

Cada estilo (§6.3) existe **em três lugares** com o mesmo nome: modelo, dialeto e DOCX.
Formatação direta é permitida, mas o painel e a exportação favorecem o estilo nomeado.

---

## 5. Modelo de dados

Módulo: `core/editor/modelo.py`. Sem Tkinter, sem PyMuPDF, sem `docx`, sem `numpy`.
Tudo é `@dataclass(kw_only=True)` — a base `Bloco` tem defaults e as filhas têm campos
obrigatórios —, com `to_dict`/`from_dict` e validação em `__post_init__`. Listas com
`field(default_factory=list)`. Defaults numéricos e de nome de fonte são **literais
locais** com um teste que os confere contra `core/estilo_do_livro.py` e
`core/render_diagrama.py`.

```python
@dataclass(kw_only=True)
class Trecho:
    texto: str = ""
    negrito: bool = False
    italico: bool = False
    sublinhado: bool = False
    tachado: bool = False
    versalete: bool = False
    posicao: str = ""            # "" | "sobre" | "sub"
    familia: str = ""            # "" (herdada) | "simbolos" | nome de fonte de diagrama | outra família
    corpo_pt: float | None = None
    cor: str = ""                # "#rrggbb"
    fundo: str = ""              # realce, "#rrggbb"
    classe: str = ""             # classes CSS extras
    lang: str = ""               # lang/xml:lang do trecho
    titulo: str = ""             # title
    link: str = ""               # href; "" sem link
    ref: str = ""                # "" | "diagrama" | "figura" | "tabela" | "titulo": referência
                                 #   cruzada cujo texto é regenerado (§11.7)
    nota: str = ""               # id da Nota referenciada (o texto "¹" é regenerado)
    papel: str = ""              # "" | "lance" | "nag" | "figurina" | "comentario" | "jogador" | "abertura"
    nag: int | None = None       # código do NAG quando papel == "nag"
    chave: str = ""              # chave de índice quando papel in ("jogador", "abertura"): "Wely, Loek van" / "C42"
    codigo: bool = False         # <code>
    quebra_antes: bool = False   # <br/> antes deste trecho
    pagina: int | None = None    # marca de página impressa inline (<span epub:type="pagebreak"/>) antes do trecho
    ilha: str = ""               # ilha inline: o fragmento XHTML; texto == ""

@dataclass(kw_only=True)
class Origem:
    page_id: str                 # EditorialPage.page_id (é o que apply_review exige)
    bloco_id: str                # EditorialBlock.id
    pagina: int                  # índice da página (0-based)
    caixa: tuple[int, int, int, int] | None = None
    fundidas: list["Origem"] = field(default_factory=list)

@dataclass(kw_only=True)
class Bloco:
    id: str = field(default_factory=id_novo)   # "b-<8 hex>"; único no capítulo (INV-01)
    id_persistente: bool = False # escrever emite `id` só quando True
    classe: str = ""
    extras: dict[str, str] = field(default_factory=dict)   # lang, title, dir, epub:type, role…
    origem: Origem | None = None
    linha_fonte: int | None = None   # fora da igualdade

@dataclass(kw_only=True)
class Paragrafo(Bloco):
    trechos: list[Trecho]
    estilo: str = "corpo"
    alinhamento: str = ""        # "" | "esquerda" | "centro" | "direita" | "justificado"
    recuo_primeira_em: float | None = None
    recuo_esquerda_em: float | None = None
    recuo_direita_em: float | None = None
    antes_em: float | None = None
    depois_em: float | None = None
    entrelinha: float | None = None
    manter_com_proximo: bool = False
    manter_linhas: bool = False

@dataclass(kw_only=True)
class Titulo(Paragrafo):
    nivel: int = 1               # 1–6; __post_init__ força id_persistente = True

@dataclass(kw_only=True)
class ItemDeLista:
    paragrafos: list[Paragrafo]
    filhos: "Lista | None" = None

@dataclass(kw_only=True)
class Lista(Bloco):
    ordenada: bool
    itens: list[ItemDeLista]
    inicio: int = 1
    marcador: str = ""           # "" | "disco" | "circulo" | "quadrado" | "decimal" | "alfa" | "romano"

@dataclass(kw_only=True)
class Celula:
    blocos: list[Paragrafo]
    cabecalho: bool = False
    alinhamento: str = ""

@dataclass(kw_only=True)
class Tabela(Bloco):
    filas: list[list[Celula]]
    primeira_fila_cabecalho: bool = False
    legenda: list[Trecho] = field(default_factory=list)
    numero: int | None = None
    largura_pct: int | None = None

@dataclass(kw_only=True)
class Figura(Bloco):
    recurso: str                 # href como está no OPF
    alt: str = ""
    legenda: list[Trecho] = field(default_factory=list)
    numero: int | None = None
    largura_pt: float | None = None
    alinhamento: str = "centro"

@dataclass(kw_only=True)
class Diagrama(Bloco):
    fen: str                     # posição (campo 1) mais os campos padrão; a autoridade do lado é `lado`
    lado: str = ""               # "w" | "b" | "" (desconhecido)
    orientacao: str = "branca"
    coordenadas: bool = False
    lado_indicador: str = ""     # "" | "marca" | "legenda"
    marcas: list[str] = field(default_factory=list)
    setas: list[tuple[str, str]] = field(default_factory=list)
    fonte: str = FONTE_PADRAO
    moldura: str = MOLDURA_PADRAO
    cantos: str = CANTO_PADRAO
    corpo_pt: float = CORPO_PADRAO_PT
    modo: str = "png"            # "png" | "fonte"
    numero: int | None = None
    legenda: list[Trecho] = field(default_factory=list)
    alt: str = ""                # vazio → alt_de
    recorte: str = ""            # href do recorte impresso
    estado: str = "ok"           # "ok" | "revisar"
    aviso: str = ""

@dataclass(kw_only=True)
class Citacao(Bloco):
    blocos: list[Paragrafo]

@dataclass(kw_only=True)
class Nota:                      # mora em Capitulo.notas; referenciada por Trecho.nota
    id: str = field(default_factory=id_novo)
    tipo: str = "rodape"         # "rodape" | "fim"
    blocos: list[Paragrafo]

@dataclass(kw_only=True)
class QuebraDePagina(Bloco): ... # quebra pedida pelo usuário: quebra no DOCX e no PDF

@dataclass(kw_only=True)
class MarcaDePagina(Bloco):      # página do impresso: NÃO quebra; é marcador
    pagina: int

@dataclass(kw_only=True)
class Separador(Bloco): ...

@dataclass(kw_only=True)
class IlhaBruta(Bloco):
    xhtml: str
    elemento: str

@dataclass(kw_only=True)
class Capitulo:
    arquivo: str                 # href relativo ao OPF, como lido
    titulo: str = ""
    blocos: list[Bloco] = field(default_factory=list)
    notas: list[Nota] = field(default_factory=list)
    folhas: list[str] = field(default_factory=list)   # hrefs das CSS, na ordem dos <link>
    idioma: str = ""
    semantica: str = ""          # epub:type do <body>
    cabeca_extra: str = ""
    texto_cru: str | None = None
    avisos: list[str] = field(default_factory=list)
    namespaces: dict[str, str] = field(default_factory=dict)   # prefixos declarados além de epub e dos conhecidos
    # `notas` fica de rodapé primeiro, depois de fim (a ordem do XHTML); `normalizar_notas()` impõe

@dataclass(kw_only=True)
class Recurso:
    caminho: str                 # href relativo ao OPF, como lido
    tipo_mime: str
    dados: bytes | None = None   # None = ainda no zip; lido sob demanda
    texto_cru: str | None = None # folha em edição no modo código: dono quando não-nulo
    propriedades: str = ""

@dataclass(kw_only=True)
class EntradaDeSumario:
    rotulo: str
    destino: str                 # "Text/cap-0001.xhtml#id"
    filhos: list["EntradaDeSumario"] = field(default_factory=list)

@dataclass(kw_only=True)
class Pessoa:
    nome: str
    papel: str = "aut"
    file_as: str = ""

@dataclass(kw_only=True)
class Metadados:
    titulo: str
    autores: list[Pessoa] = field(default_factory=list)
    colaboradores: list[Pessoa] = field(default_factory=list)
    idioma: str = "en"
    identificador: str = ""
    editora: str = ""
    data: str = ""
    descricao: str = ""
    assuntos: list[str] = field(default_factory=list)
    direitos: str = ""
    colecao: tuple[str, int] | None = None
    capa: str = ""
    fonte_impressa: str = ""     # ISBN/urn do impresso (pageBreakSource / dc:source)
    modificado: str = ""
    extras: list[tuple[str, str, str]] = field(default_factory=list)

@dataclass(kw_only=True)
class FormatoDePagina:
    largura_mm: float = 156.0
    altura_mm: float = 234.0
    margens_mm: tuple[float, float, float, float] = (20.0, 18.0, 20.0, 22.0)   # superior, externa, inferior, interna
    espelhadas: bool = True      # w:mirrorMargins; medianiz na interna
    cabecalho_par: str = "titulo"        # "" | "titulo" | "capitulo"
    cabecalho_impar: str = "capitulo"
    numerar_paginas: bool = True
    hifenizar: bool = False      # `hyphens: auto` na folha padrão, `w:autoHyphenation` no DOCX, o mesmo no PDF

@dataclass(kw_only=True)
class OrigemDoLivro:
    documento_editorial: str = ""
    pdf: str = ""
    diario: str = ""             # o review_journal_path

@dataclass(kw_only=True)
class Livro:
    metadados: Metadados
    capitulos: list[Capitulo] = field(default_factory=list)
    recursos: dict[str, Recurso] = field(default_factory=dict)
    folhas: list[str] = field(default_factory=list)   # a primeira é a padrão
    sumario: list[EntradaDeSumario] = field(default_factory=list)
    marcos: list[tuple[str, str]] = field(default_factory=list)
    opf: str = "OEBPS/package.opf"    # caminho no zip, como lido
    nav: str = "nav.xhtml"       # relativo ao OPF, como lido
    ncx: str = ""                # "" = sem NCX
    pagina: FormatoDePagina = field(default_factory=FormatoDePagina)
    origem: OrigemDoLivro = field(default_factory=OrigemDoLivro)   # persistida no OPF como meta pybox:*
```

### 5.1 Invariantes do modelo

- **INV-01** `Bloco.id` e `Nota.id` são únicos **por capítulo** (é a regra do XHTML; um
  EPUB do Calibre tem `id="title"` em todo capítulo). `id_novo()` é único no livro.
  Links internos resolvem como `arquivo#id`; `#id` nu é do capítulo corrente.
- **INV-02** Recursos, folhas, capa, `link`, `ref`, `nota` apontam para o que existe; o
  que não aponta é **aviso**, nunca apagado.
- **INV-03** `Diagrama.fen` é sintaticamente válido (`fen_valido`); legalidade é aviso.
- **INV-04** `Tabela.filas` é retangular.
- **INV-05** `ler(escrever(c))` é igual a menos de ids gerados e `linha_fonte`
  (`modelo.igual`).
- **INV-06** `escrever` produz XML bem-formado com todo prefixo declarado; `ler` recusa
  o contrário com linha e coluna.
- **INV-07** Nenhuma operação destrói uma ilha; mover, copiar, colar e desfazer a
  carregam intacta (a menos da normalização de entidades, DEC-07).
- **INV-08** Um bloco com `origem` mantém a origem por toda edição de texto; só a perde
  quando apagado ou fundido (`origem.fundidas`).
- **INV-09** `texto_cru` não-nulo (capítulo ou recurso) é o dono.
- **INV-10** Uma `MarcaDePagina` ou `Trecho.pagina` nunca vira quebra de página em
  exportação; só `QuebraDePagina` quebra.

`Livro.validar()` levanta `ValueError` citando o id para INV-01, INV-03 e INV-04, e
devolve a lista de avisos para INV-02.

### 5.2 Operações puras (em `modelo.py`)

`id_novo`, `fen_valido`, `igual`, `dividir_paragrafo`, `juntar_paragrafos` (através de
uma `MarcaDePagina`, a marca vira `Trecho.pagina`), `aplicar_formato`, `limpar_formato`,
`texto_de`, `trechos_normalizados`, `mudar_estilo`, `mudar_caixa`, `inserir_bloco`,
`mover_bloco`, `converter`, `dividir_capitulo(cap, i)` (leva cada nota para o capítulo
da sua referência, por `Trecho.nota`), `juntar_capitulos`, `dividir_por_titulo`,
`renumerar_notas`, `numerar_objetos(livro, tipo, por_capitulo)` (diagramas, figuras,
tabelas; regenera o texto dos `ref`). As operações de nível **livro** (dividir e juntar
capítulo reescrevendo espinha, sumário, marcos e links; renomear; anexar) moram em
`core/editor/livro_ops.py`.

---

## 6. O dialeto XHTML/CSS

### 6.1 Blocos

| Modelo | XHTML | Observações |
|---|---|---|
| `Paragrafo` estilo `corpo` | `<p>` | o `<p>` de `exportar._xhtml_da_pagina` |
| `Paragrafo` estilo `primeira` | `<p class="primeira">` | |
| outros estilos | `<p class="<estilo>">` | `notacao`, `comentario`, `legenda`, `nota`, `cabecalho-diagrama`, `epigrafe`, `assinatura`, `destaque` |
| formatação direta | `style="text-align; text-indent; margin-left; margin-right; margin-top; margin-bottom; line-height; page-break-after:avoid; page-break-inside:avoid"` | nesta ordem |
| `Titulo` n | `<hn id="…">` | `id` sempre persistente |
| `Lista` | `<ol start>`/`<ul>` + `<li>`; `style="list-style-type"` | `<li><p>…</p><p>…</p></li>`; sublista no `<li>` |
| `Tabela` | `<table style="width:n%" data-numero>`, `<caption>`, `<thead>`/`<tbody>`, `<tr>`, `<th>`/`<td style="text-align">` | `<th>` só quando marcado |
| `Figura` | `<figure class="esq|centro|dir" data-numero><img src alt style="width:…pt"/><figcaption/></figure>` | |
| `Diagrama` | `<figure class="diagrama" data-fen data-lado data-orientacao data-coordenadas data-indicador data-marcas data-setas data-fonte data-moldura data-cantos data-corpo data-modo data-numero data-recorte data-estado data-aviso title="<fen>">` com `<img src alt/>` (png) ou o `div.diagrama` de `exportar._diagrama_em_texto` (fonte; `p.colunas`, `span.rot`, `span.col`, `<i>` lidos como parte opaca do diagrama), depois `<figcaption/>` | ler aceita as formas nuas de hoje (DEC-06) |
| `Citacao` | `<blockquote>` com `<p>` | |
| `Nota` rodapé | `<aside epub:type="footnote" role="doc-footnote" id="<id>"><p/></aside>` no fim do `<body>` | referência: `<a epub:type="noteref" role="doc-noteref" href="#<id>"><sup>n</sup></a>` ↔ `Trecho.nota` |
| `Nota` fim | `<section epub:type="endnotes" role="doc-endnotes"><ol><li epub:type="endnote" id="<id>"><p/></li></ol></section>` no fim do capítulo | `doc-endnote` só é permitido em `li` (DPUB-ARIA 1.1); a referência é a mesma |
| `QuebraDePagina` | `<hr class="quebra" style="page-break-after:always"/>` | quebra no DOCX/PDF |
| `MarcaDePagina` | `<hr class="pagina" data-pagina="n" epub:type="pagebreak" role="doc-pagebreak" id="pg-n" aria-label="n"/>` | **não** quebra; entra na `page-list`; `doc-pagebreak` é permitido em `hr` |
| `Trecho.pagina` | `<span epub:type="pagebreak" role="doc-pagebreak" id="pg-n" aria-label="n"/>` | a página que muda no meio do parágrafo |
| `Separador` | `<hr/>` | |
| `IlhaBruta` | o fragmento original | |

Todo bloco pode levar `id` (persistente quando referenciado, quando veio com `id`, ou
quando tem `origem`), `class`, `lang`/`xml:lang`, `title`, `dir`, `epub:type`, `role` —
em `extras`. A `Origem` sai como `data-origem-pagina="<page_id>" data-origem-bloco=
"<bloco_id>" data-origem-caixa="x0,y0,x1,y1" data-origem-fundidas="<page_id>|<bloco_id> …"`
(o prefixo `origem-` é o que a distingue da `data-pagina` da marca de página impressa),
e a suspeita como `data-suspeito="<motivos>"`. `Capitulo.idioma` → `lang`/`xml:lang` do
`<html>`; `semantica` → `<body epub:type>`; `folhas` → `<link rel="stylesheet">`.

### 6.2 Trechos

| Atributo | XHTML | DOCX (run) |
|---|---|---|
| `negrito` | `<strong>` (lê `<b>`) | `bold` |
| `italico` | `<em>` (lê `<i>`) | `italic` |
| `sublinhado` | `<u>` (lê `<ins>`) | `underline` |
| `tachado` | `<s>` (lê `<strike>`, `<del>`) | `strike` |
| `versalete` | `<span class="versalete">` | `small_caps` |
| `posicao` | `<sup>`/`<sub>` | `superscript`/`subscript` |
| `familia="simbolos"` | `<span class="sim">` | família de `fonte_dos_simbolos` |
| `familia=<fonte de diagrama>` | `<span class="<classe_da_fonte(familia)>">` | run na fonte |
| outra família / `corpo_pt` / `cor` / `fundo` | `style="font-family; font-size; color; background-color"` | `font.name` / `font.size` / `font.color` / `<w:shd w:fill>` (exato; `highlight` só nas 16 do Word) |
| `lang` / `titulo` | `lang`+`xml:lang` / `title` no `span` | `w:lang` / — |
| `link` | `<a href>` | hiperlink (`Hyperlink`) |
| `ref` | `<a class="ref" data-ref="<tipo>" href="…#id">Diagrama 12</a>` | `REF _Ref<n> \h` (marcador só em torno de rótulo+número) |
| `nota` | `<a epub:type="noteref" role="doc-noteref" href="#id"><sup>n</sup></a>` | `w:footnoteReference`/`w:endnoteReference` |
| `papel="lance"` | `<span class="lance">` | `Lance` (`noProof`) |
| `papel="nag"` + `nag` | `<span class="nag" data-nag="14">` | `NAG` (`noProof`) |
| `papel="figurina"` | `<span class="fig">` | `Figurina` |
| `papel="comentario"` | `<span class="com">` | `Comentario` (caractere) |
| `papel="jogador"|"abertura"` + `chave` | `<span class="jogador" data-chave>` / `<span class="abertura" data-eco>` | `Jogador`/`Abertura` |
| `codigo` | `<code>` | monoespaçada |
| `quebra_antes` | `<br/>` | `WD_BREAK.LINE` |
| `pagina` | `<span epub:type="pagebreak" …/>` | `w:bookmarkStart w:name="pg-n"` |
| `ilha` | o fragmento (entidades numéricas) | estilo `Ilha` |

**Um `<span>` por trecho**, classes na ordem `sim | lance | nag | fig | com | jogador |
abertura | versalete | <classe>`, `style` na ordem `font-family, font-size, color,
background-color`. Aninhamento canônico de fora para dentro: `a` → `span` → `strong` →
`em` → `u` → `s` → `sup`/`sub` → `code`.

### 6.3 Estilos nomeados

| Estilo | Elemento+classe | DOCX | Uso |
|---|---|---|---|
| `corpo` | `p` | `Normal` | prosa |
| `primeira` | `p.primeira` | `Primeira` | após título/figura |
| `titulo1`…`titulo6` | `h1`…`h6` | `Heading 1`…`6` (com `w:lang`) | |
| `notacao` / `comentario` | `p.notacao` / `p.comentario` | `Notacao` (`noProof`) / `Comentario` | |
| `legenda` | `figcaption`/`caption`/`p.legenda` | `Caption` com `SEQ` | |
| `citacao` | `blockquote > p` | `Quote` | |
| `nota` | `aside > p` / `li > p` | `footnote text` / `endnote text` (styleId `FootnoteText`/`EndnoteText`, **nomes do Word**, para não duplicar) | |
| `destaque` | `p.destaque` | `Destaque` (`w:pBdr` + `w:shd`) | |
| `epigrafe`, `assinatura`, `cabecalho-diagrama` | `p.<nome>` | homônimo | |

Estilos de caractere: `Lance`, `NAG`, `Figurina`, `Simbolo`, `Versalete`, `Jogador`,
`Abertura`, `Hyperlink`, `footnote reference`, `endnote reference`. A folha padrão do
livro novo nasce de `estilo_do_livro.CSS` (texto pronto) + `CSS_DO_DIAGRAMA %
{"corpo", "moldura"}` (molde) + as regras dos estilos; `@font-face` gerado ao escrever.

### 6.4 A CSS que o modo texto lê

`core/editor/css_minima.py` lê as folhas de `Capitulo.folhas` em cascata, só seletores
de elemento, classe e elemento.classe, e só: `font-weight`, `font-style`,
`font-variant`, `font-size` (`pt`/`em`/`%`), `font-family`, `text-align`, `text-indent`,
`margin-*`, `line-height`, `color`, `background-color`, `text-decoration`, `border`
(presença), `hyphens`, `!important` tolerado. `@font-face` mapeia família → arquivo (fonte de EPUB
de fora é extraída e registrada por `ui/fontes.registrar_arquivo`, que devolve o nome
interno). `@media`, `@import`, seletores compostos e o resto são pulados **sem perder**:
`escrever(folha, css_original)` só substitui as regras tocadas.

### 6.5 Contrato de ida e volta

- **R1** `canonico(escrever(ler(x))) == canonico(x)` para XHTML do dialeto — `canonico`
  normaliza espaço entre blocos, ordem de atributos, aninhamento, `&nbsp;` ≡ `&#160;` ≡
  U+00A0, e ignora `id` `b-[0-9a-f]{8}` sem referência.
- **R2** `igual(ler(escrever(c)), c)` para capítulos do dialeto.
- **R3** Uma ilha (de bloco ou inline), um comentário e uma PI atravessam `ler` →
  `escrever` byte a byte, **exceto** referências nomeadas dentro da ilha, que saem
  numéricas (DEC-07).
- **R4** `escrever` nunca emite `style`/`class` vazios, `<span>` sem atributo, nem `id`
  não persistente.
- **R5** Os EPUBs que `exportar.para_epub` gera hoje abrem sem ilha, e os diagramas
  voltam como `Diagrama` (`alt` = FEN no `png`; linhas no `fonte`).

---

## 7. A janela

### 7.1 Disposição

```
┌ Menu: Arquivo Editar Exibir Inserir Formatar Xadrez Ferramentas Livro Ajuda ───────────┐
│ [barra de arquivo] [barra de formatação — texto] / [barra de código — código]          │
│ [barra de xadrez: ♔ ♕ ♖ ♗ ♘ ♙ · ± ∓ ⩲ ⩱ !? … · Diagrama · Posição · Validar]            │
├───────────┬───────────────────────────────────────────────────┬────────────────────────┤
│ Navegador │ ┌ abas: cap-0001.xhtml · estilo.css ───────────────┐ │ Propriedades          │
│ ───────── │ │ calha │ MODO TEXTO (tk.Text rico)                 │ │ ─────────────────── │
│ Sumário   │ │       │ ou MODO CÓDIGO (realce + prévia)          │ │ Xadrez (tabuleiro,  │
│ ───────── │ └────────────────────────────────────────────────────┘ │  paleta, posição)   │
│ Estilos   │ ┌ Busca · Resultados · Mensagens · Validação ────────┐ │                     │
│           │ └────────────────────────────────────────────────────┘ │                     │
├───────────┴───────────────────────────────────────────────────┴────────────────────────┤
│ status: cap 3/41 · linha 120, col 8 · 2.310 palavras · en · MODO TEXTO · salvo 14:02   │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

- Painéis em `ttk.PanedWindow`; esconder um painel com foco devolve o foco ao editor;
  layout em `Settings` (chave `editor`, dict). Ordem de tabulação **lógica fixa**
  (Navegador → Sumário → Estilos → Editor → Propriedades → Xadrez → Busca → Resultados →
  Mensagens), independente do encaixe (§15).
- O modo é da **aba**; `F11` alterna; o modo aparece na barra de status, no título da
  aba e na cor da calha; troca de modo e salvamento são ecoados no painel Mensagens.
- A barra de xadrez insere no texto o trecho/bloco e no código o XHTML. Só figurinas
  **brancas** na barra (na notação impressa os lances das pretas usam a mesma figurina);
  as pretas ficam na caixa de símbolos, para legendas.
- Um item de menu desabilitado mostra a fase que o entrega na **barra de status** ao ser
  percorrido (`<<MenuSelect>>`) — o `tk.Menu` não tem dica.

### 7.2 Como a janela abre

1. **Janela principal → Arquivo → Editor de livro…**
2. **Ao fim de "Exportar livro"** (e, depois da ED-11, das outras exportações e da fila):
   a `DialogoDeConclusao` tem "Abrir arquivo", "Abrir pasta" e "Abrir no editor" (EPUB
   → o arquivo; outros → o livro montado das `PaginaExtraida`, §10.6.5), com o
   `EditorialDocument` da sessão.
3. **`appy.py --editor [arquivo] [--fechar-apos N] [--diagnostico-modulos]`**: só o
   editor, com `_declarar_dpi`, sem `MainWindow` nem modelo neural.

### 7.3 Menus

Todos os itens existem nos dois modos; o que não se aplica fica desabilitado. **Cada
comando tem um lar**; um segundo item é *alias* declarado (`alias_de`) na tabela de
`ui/editor/menus.py`, uma seção por fase. **Mnemônicos** fixos, sem letra de peça em
nenhum dos dois mapas (`KQRBNP` e `RDTBCP`): **A**rquivo, **E**ditar, E**x**ibir,
**I**nserir, **F**ormatar, Xadre**z**, Ferra**m**entas, **L**ivro, Aj**u**da (o precedente
de desempate é `ui/main_window.py`: Re**v**isar, Aj**u**da). `Shift+F10` e a tecla de
menu (`App` no Windows, `Menu` no X11) abrem o menu de contexto do controle focado; toda
ação de contexto tem item de menu. A tabela da §7.4 é a **única fonte** dos
aceleradores. Entre parênteses, a fase.

**Arquivo**: Novo livro · Novo a partir de modelo… (título, autor, idioma → Metadados;
ED-02) · Abrir… · Abrir recente ▸ · Salvar · Salvar como… · Reverter ao salvo · Ponto de
verificação ▸ (criar, comparar, restaurar; ED-01/02) · Fechar aba · Fechar livro (ED-02) ·
Importar ▸ (HTML/XHTML, TXT, EPUB para dentro do livro: ED-10 · DOCX: ED-12 · JSON
editorial: ED-11) · Exportar… (caixa com o formato, como `ui/dialogo_de_exportacao.py`:
EPUB, HTML único, HTML pasta, TXT: ED-10 · DOCX, PDF, PGN: ED-12) · Imprimir… (ED-12) ·
Sair.

**Editar**: Desfazer · Refazer · Apagar palavra ▸ (ED-03) · Recortar · Copiar · Colar ·
Colar sem formatação · Colar como XHTML (ED-04) · Selecionar tudo · Selecionar parágrafo · Selecionar bloco
(ED-03) · Localizar… · Substituir… · Localizar próximo/anterior · Ir para… (ED-06) ·
Seguir link (ED-04) · Maiúsculas/minúsculas ▸ · Pincel de formatação (ED-03) ·
Autocompletar · Comentar/descomentar (ED-07) · Preferências… (ED-13).

**Exibir**: Modo texto · Modo código (ED-02) · Prévia (ED-08) · Capítulo seguinte /
anterior · Painel seguinte / anterior · Foco no editor (ED-02) · Navegador · Sumário ·
Estilos · Propriedades · Xadrez · Busca e mensagens · Barra de formatação · Barra de
xadrez (ED-02; a barra de xadrez é preenchida na ED-05) · Mostrar invisíveis (ED-03) ·
Quebra automática de linha (ED-02) · Largura de leitura ▸ (ED-03) · Zoom ▸ (ED-03/07) ·
Tela cheia (ED-02) · Números de linha · Realce da linha atual (ED-07).

**Inserir**: Diagrama… (alias) · Imagem… · Tabela… · Link… (ED-04) · Referência…
(ED-05) · Âncora (id)… · Nota de rodapé · Nota de fim · Quebra de linha · Quebra de
página · Separador · Ilha de XHTML… (ED-04) · Espaço inseparável · Hífen inseparável · Hífen
opcional · Código Unicode ↔ caractere (ED-06) · Capítulo novo (alias) · Dividir capítulo
aqui (ED-04) · Sumário como página do livro (ED-08) · Figurina ▸ · NAG ▸ (ED-05) ·
Símbolo… (ED-06) · Clipe ▸ (ED-07).

**Formatar**: Fonte… · Negrito · Itálico · Sublinhado · Tachado · Versalete · Sobrescrito
· Subscrito · Aumentar fonte · Diminuir fonte · Cor… · Realce ▸ · Parágrafo… · Alinhar ▸
· Recuar / Diminuir recuo · Entrelinha ▸ · Marcadores · Numeração · Estilo ▸ · Aplicar
estilo de caractere ▸ · Novo estilo a partir da seleção… · Modificar estilo… · Selecionar
tudo com este estilo · Limpar formatação de caractere · Limpar formatação de parágrafo
(ED-03) · Propriedades do objeto… (`Alt+Enter`; ED-04) · Propriedades do diagrama…
(alias) · Tabela ▸ (ED-04) · Folhas de estilo do livro… (ED-08).

**Xadrez**: Inserir diagrama… · Editar posição… · Diagrama a partir dos lances · Girar ·
Coordenadas · Lado a jogar ▸ (brancas, pretas, desconhecido; indicador nenhum/marca/
legenda) (ED-05) · Marcas e setas… (ED-05b) · Validar notação (seleção / capítulo / livro) ·
Figurinas ao digitar · Figurinas ↔ letras ▸ · Marcar lances · Marcar NAGs · Marcar
jogador/abertura… · Numerar ▸ (diagramas, figuras, tabelas; por livro/por capítulo) ·
Cabeçalho em legenda · Legenda sugerida (ED-05b) · Paleta de figurinas · Paleta de NAGs ·
Fonte dos símbolos… · Fonte de diagrama do livro… (ED-05) · Chave de símbolos (ED-05b) ·
Índice ▸ (jogadores, partidas, aberturas; ED-12) · Exportar PGN do capítulo… (ED-12).

**Ferramentas**: Verificar ortografia… · Dicionário do livro… (ED-06) · Tipografia… ·
Juntar palavras hifenizadas (ED-06b) · Contagem de palavras · Estatísticas do livro…
(ED-06) · Buscas salvas… (ED-06b) · Relatórios ▸ (ED-08) · Verificar bem-formado ·
Consertar HTML · Reformatar XHTML · Reformatar CSS (ED-07) · Validar EPUB (ED-08) ·
Apagar recursos não usados… · Apagar classes CSS não usadas… (ED-08) · Clipes… (ED-07).

**Livro**: Metadados… · Capa… · Sumário ▸ (gerar, editar, gravar) · Semântica do capítulo
▸ · Marcos… · Vincular folhas de estilo… · Adicionar arquivo… · Adicionar cópia · Novo
capítulo · Nova folha de estilo · Renomear… · Renomear vários… · Excluir · Mover para
cima/baixo · Juntar com o anterior · Juntar em capítulos por título… · Dividir em
capítulos por título… · Dividir nos marcadores · Ordenar por nome · Abrir com… (ED-08;
dividir/juntar nascem em ED-01/ED-04/ED-10) · Formato de página… (ED-12).

**Ajuda**: Atalhos de teclado… · O dialeto do livro · Sobre (ED-02/ED-13).

### 7.4 Atalhos

Regras: os do Word onde o Word tem um; os do Sigil onde o Sigil tem um; **nenhum
`Ctrl+Alt`** (`AltGr`); **nenhum `Alt+letra`** (mnemônicos); um acorde, um comando por
modo, e o mesmo acorde só muda de sentido entre modos quando o sentido é análogo (†).
Acordes com dígito e `Shift` são casados por **keycode**, porque o keysym depende do
layout. Todo item da tabela tem um item de menu (AC-ED02-1), exceto os marcados como
**nativos** (`Ctrl+Tab`) e os **contextuais** (`Enter` sobre objeto, que despacha para
a ação principal do objeto e não é um comando).

| Atalho | keysym Tk | Ação | Modo |
|---|---|---|---|
| `Ctrl+N` / `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` | | novo / abrir / salvar / salvar como | ambos |
| `Ctrl+Shift+E` | | exportar… (caixa) | ambos |
| `Ctrl+P` | | imprimir (PDF paginado) | ambos |
| `Ctrl+W` / `Ctrl+Shift+W` | | fechar aba / fechar livro | ambos |
| `Ctrl+Z` / `Ctrl+Y` | `<<Undo>>`/`<<Redo>>` | desfazer / refazer | ambos |
| `Ctrl+X` / `Ctrl+C` / `Ctrl+V` / `Ctrl+Shift+V` | `<<Cut>>`/`<<Copy>>`/`<<Paste>>` | recortar / copiar / colar / colar sem formatação | ambos |
| `Ctrl+A` | `<<SelectAll>>` | selecionar tudo | ambos |
| `Ctrl+F` / `Ctrl+H` / `F3` / `Shift+F3` | | localizar / substituir / próximo / anterior (com "circular") | ambos |
| `Ctrl+G` | | ir para… | ambos |
| `Ctrl+B` / `Ctrl+I` / `Ctrl+U` | | negrito / itálico / sublinhado (código: envolve a seleção em `<strong>`/`<em>`/`<u>`) † | ambos |
| `Ctrl+Shift+K` | | versalete | texto |
| `Ctrl+=` / `Ctrl+Shift+=` | `equal` / `plus` | subscrito / sobrescrito | texto |
| `Ctrl+Shift+>` / `Ctrl+Shift+<` | `greater` / `less` | aumentar / diminuir fonte | texto |
| `Ctrl+D` | | Fonte… | texto |
| `Ctrl+L` / `Ctrl+E` / `Ctrl+R` / `Ctrl+J` | | alinhar esquerda / centro / direita / justificar | texto |
| `Ctrl+M` / `Ctrl+Shift+M` | | recuar / diminuir recuo | texto |
| `Ctrl+1` / `Ctrl+5` / `Ctrl+2` | keycode | entrelinha 1 / 1,5 / 2 | texto |
| `Alt+1`…`Alt+6` / `Ctrl+Shift+N` | keycode | título 1…6 / estilo corpo | texto |
| `Ctrl+Shift+L` / `Ctrl+Shift+O` | | marcadores / numeração | texto |
| `Ctrl+Space` | `space` | limpar formatação de caractere (texto) · autocompletar (código) † | ambos |
| `Ctrl+Q` | | limpar formatação de parágrafo | texto |
| `Ctrl+BackSpace` / `Ctrl+Delete` | | apagar palavra anterior / seguinte (Editar → Apagar palavra ▸) | ambos |
| `Ctrl+K` | | link | ambos |
| `Enter` sobre objeto | `Return` | ação principal (diagrama → editor de posição; tabela → primeira célula; referência de nota → a nota; demais → propriedades) | texto |
| `Alt+Enter` | `Return` | propriedades do objeto/parágrafo (o do Explorer; `Enter` não é letra) | texto |
| `Shift+Enter` | `Return` | quebra de linha suave | texto |
| `Ctrl+Enter` | `Return` | quebra de página (texto) · dividir capítulo (código, Sigil) † | ambos |
| `Ctrl+Shift+Enter` | `Return` | dividir capítulo | texto |
| `Ctrl+Shift+Space` / `Ctrl+Shift+-` / `Ctrl+-` | `space` / `underscore` / `minus` | espaço inseparável / hífen inseparável / hífen opcional | texto |
| `Ctrl+Shift+X` | | código Unicode ↔ caractere | texto |
| `Ctrl+Shift+D` / `Ctrl+Shift+P` / `Ctrl+Shift+G` | | inserir diagrama / editar posição / diagrama a partir dos lances | ambos |
| `Ctrl+Shift+F` | | foco na paleta de figurinas (setas, `Enter`, `Esc`) | ambos |
| `F7` | | ortografia | ambos |
| `Ctrl+Shift+8` | keycode | invisíveis | texto |
| `Ctrl+KP_Add` / `Ctrl+KP_Subtract` / `Ctrl+0` | `KP_Add` / `KP_Subtract` / keycode | zoom (mais `Ctrl+roda`, conveniência de mouse fora da tabela) | ambos |
| `F11` / `F12` | | alternar modo / prévia | ambos / código |
| `Ctrl+PageDown` / `Ctrl+PageUp` | `Next` / `Prior` | capítulo seguinte / anterior | ambos |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | | **sair do editor** (nativo do `Text`; listado para constar em "Ajuda → Atalhos") | ambos |
| `Ctrl+T` / `F8` | | sumário / metadados | ambos |
| `Alt+F7` / `Alt+F8` / `Alt+F9` | | bem-formado / consertar / validar EPUB | código |
| `Ctrl+Shift+I` / `Ctrl+/` / `Ctrl+Shift+J` | `slash` | reformatar / comentar / clipes | código |
| `F6` / `Shift+F6` | | painel seguinte / anterior | ambos |
| `Shift+F10` / tecla de menu | `F10` / `App` (Windows) e `Menu` (X11) | menu de contexto (`Shift+F10` com `break`, senão `tk::WinMenuKey` abre a barra) | ambos |
| `F1` | | atalhos | ambos |
| `Esc` | `Escape` | foco de volta ao editor; fecha a busca; sai de tabela, objeto ou nota | ambos |

Numa **tabela**: `Tab`/`Shift+Tab` entre células; seta para cima na primeira fila e para
baixo na última saem para o bloco vizinho; `Esc` sai. Sobre um **objeto**: `Enter`,
`Alt+Enter`, `Del`.

### 7.5 Barra de status e mensagens

Capítulo, posição, contagem, idioma, modo, estado, último aviso. As mudanças que
importam — modo, salvo, erro de validação, exportação — vão também ao painel
**Mensagens** (texto percorrível), o canal redundante que o Tk permite (§15).

### 7.6 Sessão, rascunho, recentes, pontos de verificação

- **Sujo**: título com `•`.
- **Rascunho**: `Rascunho(gravador, relogio=time.monotonic)` com `tique()` a cada
  segundo (`after`); a cada 60 s sujo grava `<livro>.epub.autosave.json` (modelo em
  `to_dict`, `texto_cru`, recursos novos em base64); livro sem caminho em
  `data_dir()/rascunhos/<uuid>.json`; restauração oferecida ao abrir; apagado ao salvar;
  forçado ao fechar a principal ou o processo com o editor sujo.
- **Pontos de verificação**: cópia datada em `<livro>.checkpoints/`, comparar
  (`difflib` por arquivo) e **restaurar**.
- **Recentes**: dez, poda os inexistentes.
- **Preferências** (`Settings.get("editor", {})`, um dict plano com as chaves `layout`,
  `recentes`, `estilo_de_tela`, `largura_de_leitura`, `zoom`, `tema_codigo`,
  `tabulacao`, `idioma_ortografia` (nasce de `Metadados.idioma`), `fonte_diagrama`,
  `modo_diagrama`, `figurinas_ao_digitar`, `ncx`, `intervalo_rascunho`, `clipes`,
  `buscas`, `diretorios`).

---

## 8. Modo texto

### 8.1 Seleção e cursor

Seleção por mouse e teclado como no WordPad; um objeto é selecionável como um
caractere; `Enter`/`Alt+Enter`/`Del`/`Esc` da §7.4; setas atravessam objetos e ilhas
inline; "Seguir link" no menu e no contexto (o `Ctrl+clique` é a conveniência de mouse).

### 8.2 Formatação de caractere

| Ação | Sem seleção | Com seleção | Modelo |
|---|---|---|---|
| negrito, itálico, sublinhado, tachado, versalete, sobrescrito, subscrito | formato pendente | alterna: se **todo** o intervalo tem, tira; senão põe — sobre o **marcador próprio**, sem XOR com o estilo do parágrafo | `aplicar_formato` |
| família, corpo, cor, realce, aumentar/diminuir fonte | pendente | aplica | idem |
| estilo de caractere | pendente | aplica `papel`/`familia`/`versalete` | idem |
| pincel de formatação | copia o formato do cursor; o próximo clique/arrasto aplica | idem | idem |
| limpar formatação de caractere | — | zera tudo menos `link`/`nota`/`ref` | `limpar_formato` |
| link / maiúsculas | caixa / palavra sob o cursor | intervalo | `link` / `mudar_caixa` |

Realce escuro (`#000000`, `#000080`, `#800000`, `#008000` das 16 do Word) desenha o
texto em branco na tela (luminância do fundo < 0,18) e sai com `color:#fff` no arquivo;
o relatório de conversão lista realces abaixo de 4,5:1.

### 8.3 Formatação de parágrafo

Alinhamento, recuos, espaçamento, entrelinha, manter com o próximo, manter linhas,
estilo — na caixa Parágrafo e no painel Propriedades (com **"Aplicar"**). Desenho:
`justify`, `lmargin1/2`, `rmargin`, `spacing1/2/3`.

### 8.4 Estilos

Painel com os estilos da §6.3 e os das folhas; aplicar; "Novo estilo a partir da
seleção" grava na folha padrão; "Modificar estilo…" abre a regra em código; "Selecionar
tudo com este estilo".

### 8.5 Listas

Nível por `Tab`/`Shift+Tab` no início do item; `Enter` em item vazio sai; `BackSpace`
no início diminui o nível; marcador protegido regenerado no `dump`.

### 8.6 Tabelas

Grade de `tk.Text` embutida (`window_create`); células `TextoRico` por `carregar_blocos`
com as tags criadas uma vez; altura por `count -displaylines` no `<<Modified>>`; setas e
roda saem da célula; `Tab`/`Shift+Tab`; `Tab` na última cria fila; `Esc` sai; `Enter`
sobre a tabela entra na primeira célula. Sem mesclar, sem aninhar, ≤ 400 células (senão
ilha). Legenda com número (`SEQ Tabela` no DOCX).

### 8.7 Imagens

PNG/JPEG/GIF/SVG (SVG rasterizado no DOCX/PDF com aviso); largura; `alt` (aviso quando
vazio); legenda com número; alinhamento; colar imagem (`ImageGrab`, por callable
injetado) → `Images/colada-<n>.png`.

### 8.8 Notas

Referência protegida (`Trecho.nota`); rodapé ou fim; edição na faixa de notas no fim do
capítulo (marcas `nota:<id>`; `sincronizar()` devolve `Capitulo` com blocos e notas) ou
no painel; `Enter` sobre a referência vai à nota, `Esc` volta; numeração por capítulo na
tela, contínua no DOCX; dividir o capítulo leva a nota junto da referência.

### 8.9 Links, âncoras e referências

Link para URL, `arquivo#id`, nota; âncora = `id` persistente; referência cruzada
(`Trecho.ref`) com texto regenerado (§11.7); quebrados no relatório.

### 8.10 Quebras e capítulos

Quebra suave (`Shift+Enter`, `⏎`); **quebra de página** (`Ctrl+Enter`, desenhada "— quebra
de página —"); **marca de página impressa** (desenhada "— página 27 —", **não** quebra);
"Dividir capítulo aqui" / "Juntar com o anterior" via `livro_ops`.

### 8.11 Colar

`AreaDeTransferencia(ler_sistema, gravar_sistema, ler_imagem)` — módulo de `core/` com
os acessos ao sistema **injetados** pelo widget. Copiar/recortar põe no sistema só o
texto plano e guarda o modelo no buffer do processo; colar é interno quando o texto do
sistema é idêntico ao do último copiar. `Ctrl+Shift+V` força texto; "Colar como XHTML"
(`consertar` + `ler_fragmento`); imagem → recurso; `CF_HTML` na ED-13.

### 8.12 Localizar e substituir

Uma caixa para os dois modos: texto, maiúsculas, palavra inteira, regex (`re`, `\1`),
*dotall*, *mínimo*, "espaço casa também o inseparável", **circular**, escopo (seleção,
capítulo, livro, arquivos marcados, abas abertas, texto marcado), direção, substituir /
substituir e localizar / substituir todos (contagem por arquivo) / contar / listar. No
modo texto busca no texto dos trechos; no código, no XHTML cru. Histórico das 20;
**buscas salvas** com grupos e execução em lote.

### 8.13 Ortografia

`lexico.sugestoes(palavra, lex, n=5)` (**novo**; `difflib.get_close_matches` sobre
`_indice_por_forma`); dicionário do livro em `<livro>.lexico.txt`
(`caminho_do_usuario(caminho, e_pdf=True)` faz `splitext` — o PDF e o EPUB do mesmo livro
compartilham o dicionário, de propósito); exclusões: notação, figurinas, NAGs, números,
`papel="lance"`, ilhas; `lang` do trecho escolhe o léxico; `F7` com Ignorar / Ignorar
todas / Adicionar / Trocar. Português na ED-06b (`assets/lexico/pt.txt.gz`).

### 8.14 Tipografia

Aspas curvas por idioma, reticências, travessão em intervalos e resultados, espaço
inseparável entre número e lance e em "Diagrama 12", hífen inseparável em `O-O`, com as
exceções de xadrez (`O-O`/`0-0` não viram travessão; `+-`/`-+` são NAG); prévia por
ocorrência; "Juntar palavras hifenizadas" (`lexico.juntar_hifenizadas`); hifenização por
`FormatoDePagina.hifenizar` (persistido como `<meta property="pybox:hifenizar">`):
a tipografia grava `hyphens: auto` na folha padrão a partir dele, e `docx_io`/`pdf_io`
o leem.

### 8.15 Contagem, invisíveis, zoom e largura

Contagem do capítulo e do livro. Invisíveis são caracteres inseridos `invisivel+protegido`
(`¶`, `→`, `⏎`, `°`), descartados no `dump`, com conversão de posição por
`ui/editor/dump.indice_de(itens, bloco_id, deslocamento)`. Zoom só na superfície de
edição. "Largura de leitura como página" (~65 caracteres, faixa cinza).

---

## 9. Modo código

| Recurso do Sigil | Aqui | Fase |
|---|---|---|
| Book Browser | Navegador: árvore na disposição do livro; arrastar reordena; contexto completo (renomear, renomear vários, excluir, adicionar arquivo/cópia, novo capítulo/folha, capa, semântica, mover, juntar, dividir, abrir com…) | ED-08 |
| Code View | Realce, números de linha, linha atual, casamento, auto-indentação, `</` completa, `Ctrl+Space`, comentar, zoom, `Ctrl+B/I/U` envolvendo a seleção; dobra — não (§15) | ED-07 |
| Preview | DEC-05 | ED-08 |
| Go to link/style, and back | `abrir_alvo` injetado; troca de aba real na ED-08 | ED-07 |
| TOC painel / Generate / Edit / HTML TOC | Painel Sumário; gerar com níveis; editor; "ao dividir"; página de sumário | ED-08 |
| Metadata Editor / Add Cover / Semantics | §5 `Metadados`; capa com invólucro SVG (`properties="svg"`, `cover-image`, `<meta name="cover">`, marco); semântica (§9.7) e marcos | ED-08 |
| Split at Cursor / at Markers / Merge | `Ctrl+Enter` (código), `<hr class="divisao"/>`, "Juntar com o anterior" | ED-04 / ED-10 |
| Find & Replace / Search Editor | §8.12 | ED-06 / ED-06b |
| Clips / Clip Editor | grupos, `\1`…`\9`, barra, também no texto | ED-07 |
| Special Characters | caixa por categoria com busca por nome | ED-06 |
| Insert Image / File / Link / ID | sim | ED-07 |
| Spellcheck | nós de texto; sugestões | ED-06 |
| Well-Formed check | `expat` com namespaces; linha, coluna | ED-07 |
| Mend / Reformat HTML / Reformat CSS | `lxml.html` ou `html.parser` próprio; `canonico`; CSS | ED-07 |
| Validate with epubcheck | `Alt+F9`; sem Java, mensagem | ED-08 |
| Reports | arquivos, imagens, classes, links e referências, **caracteres**, fontes/glifos, diagramas | ED-08 |
| Delete unused media / styles | sim | ED-08 |
| Checkpoints | criar, comparar, **restaurar** | ED-01 |
| Save As | sim | ED-01 |
| Index Editor / Plugins / Save a Copy / Font obfuscation | — (§2.2) | — |
| Preferences | §7.6 | ED-13 |

### 9.1 Abas

Uma por arquivo; XHTML alterna texto/código; CSS só código (`Recurso.texto_cru`); OPF,
NCX e `nav.xhtml` **somente leitura** (regenerados, DEC-01).

### 9.2 Realce

Tokenizador por regex com estados e **estado por linha**; re-tokeniza da linha alterada
até o estado convergir (e até o fim da faixa visível); temas claro/escuro ≥ 4,5:1.

### 9.3 Edição

Auto-indentação, `Tab` = dois espaços, `Ctrl+/`, `Ctrl+Shift+I`, `</` completa,
`Ctrl+Space` (tags e classes das folhas — `EditorDeCodigo(master, linguagem,
folhas=(), abrir_alvo=None)`), ir para linha, `Ctrl+K`, ir ao link/estilo e voltar.

### 9.4 Busca em código

Texto cru de todos os arquivos; resultados por arquivo/linha; buscas salvas.

### 9.5 Operações no livro

`livro_ops`: renomear, renomear vários, excluir (devolve quem apontava), mover, dividir,
juntar, juntar por título (sintetiza `MarcaDePagina(n)` do `<title>`/nome
`pagina-NNNN` na fronteira de cada arquivo, porque o XHTML de hoje não tem `hr.pagina`),
dividir por título, dividir nos marcadores, ordenar, vincular folhas, anexar, adicionar
cópia, abrir com programa externo.

### 9.6 Prévia

`Previa(atraso_ms=300)` (o teste usa `0` + `update()`); mal-formado mantém a anterior;
clique → `linha_fonte`.

### 9.7 Semântica

`cover`, `titlepage`, `copyright-page`, `dedication`, `epigraph`, `foreword`, `preface`,
`introduction`, `toc`, `bodymatter`, `chapter`, `glossary`, `bibliography`, `index`,
`appendix`, `acknowledgments`, `colophon`, `endnotes`.

### 9.8 Relatório de links e referências

Links quebrados, `ref` sem alvo, notas sem referência, âncoras sem quem as aponte.

---

## 10. Conversão

### 10.1 EPUB 3

**A disposição do arquivo aberto é preservada** (`Livro.opf`, `nav`, `ncx` e os `href`
tal como lidos; o EPUB de hoje é `OEBPS/content.opf`, `pagina-NNNN.xhtml`, `estilo.css`,
`imagens/`, `fonts/`); a estrutura `OEBPS/package.opf` + `Text/Styles/Images/Fonts` é do
livro novo e dos recursos novos. `mimetype` primeiro; OPF regenerado no lugar
(manifesto, espinha, `properties`, `<meta name="cover">` e `<guide>` com o NCX);
`nav.xhtml` regenerado (`toc`, `landmarks`, `page-list` das marcas de página); NCX
opcional com `<spine toc="ncx">` e `dtb:uid`; metadados com `file-as`, papéis, coleção,
`dcterms:modified`, `dc:source`/`pageBreakSource` de `fonte_impressa`, e os de
acessibilidade **calculados**: `accessMode textual` sempre e `visual` quando há imagem;
`accessModeSufficient textual` só se toda figura e diagrama têm `alt`; `pageBreakMarkers`
(mais `printPageNumbers` legado) quando há `page-list`; `structuralNavigation` só com
títulos de verdade; `accessibilityHazard none`; um `accessibilitySummary` que não repete
as *features*; `ibooks:specified-fonts` com fonte embutida; `OrigemDoLivro` como
`<meta property="pybox:…">` com prefixo declarado. Fontes usadas copiadas com
`@font-face` relativo; diagramas `png` em `Images/diag-<hash>.png`. Validação estrutural
e `epubcheck`.

### 10.2 HTML

Arquivo único (CSS inline, `data:`; um `<section role="doc-chapter" id="<arquivo>">` por
capítulo, links internos reescritos para `#<arquivo>__<id>`) ou pasta. HTML5 sem
declaração XML nem `xmlns:epub`; `epub:type` → `role` DPUB-ARIA (o do `<body>` vai para
a `section`).

### 10.3 DOCX (escrever)

`python-docx`, reaproveitando `_propriedades_do_docx`, `_desenho_da_pagina`,
`_idioma_do_estilo`, `_embutir_fontes_no_docx`, `_caixa_do_diagrama`, `MOLDURA_NO_DOCX`,
`PASSO_DO_CORPO_PT`. Estilos criados uma vez (o `default.docx` do `python-docx` 1.2 não
tem `Hyperlink`, notas, `TOC 1`…`6` nem os nossos): `Primeira`, `Notacao`, `Comentario`,
`Destaque`, `Lance`, `NAG`, `Figurina`, `Jogador`, `Abertura`, `Ilha`, `Hyperlink`,
`footnote text`/`footnote reference`/`endnote text`/`endnote reference` (nomes do Word),
`TOC 1`…`TOC 6`; `noProof` nos de xadrez; `w:lang` em todos.

| Modelo | DOCX |
|---|---|
| parágrafo | estilo + `paragraph_format` (keep_with_next, keep_together, widow_control) |
| `Titulo` | `Heading n` + marcador `_Toc<n>` |
| `Lista` | `numbering.xml`: `abstractNum` por marcador com `w:lvlText` e `w:ind` por nível; `num` por lista com `startOverride` |
| `Tabela` | `Table Grid`, `tblHeader`, legenda `Caption` com `SEQ Tabela` e marcador `_Ref<n>` em torno de "Tabela n" |
| `Figura` / `Diagrama png` | `add_picture` (SVG rasterizado); `docPr/@descr` = `alt` / FEN; legenda com `SEQ` |
| `Diagrama fonte` | tabela 1×1 na fonte embutida; **com coordenadas e fonte sem moldura em glifo, cai para PNG com aviso** |
| `Nota` | as sete costuras: `footnotes.xml`/`endnotes.xml` com separadoras `-1`/`0`, `w:footnotePr` em `settings.xml`, `Override`, relacionamento, estilos, `w:footnoteReference` no corpo |
| `QuebraDePagina` / `MarcaDePagina` / `Trecho.pagina` | `WD_BREAK.PAGE` / `w:bookmarkStart w:name="pg-n"` **sem quebra** / idem |
| `ref` | `REF _Ref<n> \h` |
| sumário | `w:sdt` pré-renderizado com `w:instrText TOC \o "1-3" \h \z \u`, uma entrada por título (`w:hyperlink w:anchor="_Toc<n>"` + `PAGEREF _Toc<n> \h`), e `w:updateFields` |
| cabeçalho/rodapé | `w:evenAndOddHeaders`: par = título, ímpar = `STYLEREF "Heading 1"`; rodapé `PAGE`; `w:mirrorMargins` e `Livro.pagina` |
| realce | `w:shd` exato; texto branco sobre fundo escuro |

### 10.4 DOCX (ler)

Parágrafos, títulos, runs (incl. `w:shd`, `w:lang`), listas, tabelas, imagens, notas de
rodapé e fim (OOXML), quebras, hiperlinks, marcadores `pg-n` → `MarcaDePagina`,
diagrama em fonte (corpo **e** tabela 1×1) por `fen_de_linhas` (lado `""`), imagem com
`descr` FEN → `Diagrama(modo="png")`, o resto com aviso; `dividir_por_titulo`.

### 10.5 PDF paginado

`fitz.Story` por capítulo com a CSS do livro, `Livro.pagina` (dois `rect`s alternados
para margens espelhadas, cabeçalhos par/ímpar, numeração), fontes via `Archive`,
`Document.set_toc` do sumário por `Story.element_positions`, `set_metadata`,
`insert_link` para links internos. É o "Imprimir…".

### 10.6 Abrir / importar

1. **EPUB**: qualquer, disposição preservada, entidades aceitas, `id` repetido entre
   capítulos aceito.
2. **HTML/XHTML**: → livro dividido por `h1`; "Consertar" com aviso; `<b>`/`<i>`
   normalizados com registro.
3. **DOCX**: §10.4.
4. **TXT**: parágrafos por linha em branco; `#` título (opção); `[Diagrama n: FEN]`.
5. **JSON editorial / `PaginaExtraida`** (`core/editor/importar_ir.py`): `paragraph` →
   `Paragrafo` (`bold_spans` → negrito); `heading` → `Titulo`; `caption` → `Paragrafo(
   estilo="legenda")`; `diagram` → `Diagrama` (chaves reais do dicionário: `fen`,
   `origin`, `warning`, `width`, `height`, `orientation`, `lines`, `font`, `coordinates`,
   `framed_lines`, `png_base64`, `bbox`; `lado=""`; o `png_base64` do recorte vira
   `recorte`) — `diagram` **sem `fen`** ou `origin == "faixa"` → `Figura` com aviso;
   `table` → `Tabela`; `chess_sequence` → `Paragrafo` estilo `notacao`; `page_break` e
   toda nova `EditorialPage` → `MarcaDePagina(pagina = page_index + 1)` (índice do PDF,
   não o fólio); `header`/`footer` ignorados com aviso; `unknown` → `Paragrafo` + aviso.
   `Origem(page_id, bloco_id, pagina, caixa)` em todo bloco; suspeitos com
   `extras["data-suspeito"]`. Um capítulo por `heading` nível 1, ou um por página. O
   diário é o `review_journal_path` (DEC-10).
6. **Anexar** EPUB (`livro_ops.anexar`).

### 10.7 Perdas conhecidas

| De → para | Perde | Como aparece |
|---|---|---|
| modelo → documento editorial (ponte) | **negrito, itálico e todo formato** (DEC-10) | relatório ao salvar |
| modelo → DOCX | `classe` livre, `epub:type`, ilhas (texto), CSS fora da mínima, `origem` | relatório |
| modelo → HTML/PDF/TXT | `origem` | — |
| DOCX → modelo | caixas de texto, formas, campos, comentários, controle de alterações, cabeçalho/rodapé | relatório |
| EPUB de fora → texto | tudo fora do dialeto é ilha | objetos/glifos |
| ilha → EPUB | referências nomeadas viram numéricas | — |
| tela | versalete, paginação, CSS fora da mínima, sublinhado por estilo | §15 |

### 10.8 Relatório de conversão

`core/editor/conversao.py: RelatorioDeConversao` (formato, arquivos, avisos, e as oito
contagens: capítulos, blocos, diagramas por modo, figuras, notas, ilhas, fontes
embutidas, tempo) devolvido por **toda** `ler(caminho) -> (Livro, Relatorio)` e
`escrever(...) -> Relatorio` de `epub`, `html_io`, `docx_io`, `txt_io`, `pdf_io`,
`importar_ir`, e mostrado na `DialogoDeConclusao`. `OpcoesDeConversao` (mesmo módulo):
`modo_de_diagrama` (`png`/`fonte`, para DOCX e PDF), `corpo_pt`, `fonte`, `moldura`,
`cantos`, `sumario` (campo TOC no DOCX), `notas` (`rodape`/`fim`), `idioma`, `ncx`
(escrever o `toc.ncx`), `pasta_de_imagens` — a hifenização vem de `Livro.pagina`.

---

## 11. Xadrez no editor

### 11.1 O bloco diagrama na tela

`render_diagrama.desenhar` no lado do zoom (cache pelos parâmetros), com indicador de
lado, marcas e setas, número e legenda. `Enter` abre o editor de posição; `Alt+Enter`
as propriedades, agrupadas em **Posição** (FEN, lado a jogar — brancas/pretas/
desconhecido —, orientação, coordenadas), **Aparência** (`PainelDoDiagrama`; modo;
indicador) e **Identificação** (número, legenda, alt, estado/aviso); recorte ao lado
quando houver.

### 11.2 Editor de posição

`ui/editor/tabuleiro.py: TabuleiroEditavel` — extraído de `ui/dialogo_diagrama.py`
(`TabuleiroEdicao.de_fen(fen)` novo em `core/tabuleiro_edicao.py`, com `core.diagrama`
importado dentro de função). Teclado: setas movem a casa selecionada, cujo anel é de
**dois tons** (2 px `#000` por dentro, 1 px `#fff` por fora — ≥ 3:1 sobre qualquer casa
nas duas paletas); `K Q R B N P` põem a peça branca e `Shift+letra` a preta (a cor vem de
`event.state & 0x1`, nunca da caixa do caractere — o Caps Lock inverteria); no idioma
`pt` o mapa é `R D T B C P` e aparece na caixa; `Delete`/`BackSpace`/`0` limpam; `F`
gira; `Tab` leva aos controles (lado a jogar, roque, FEN); `Enter` confirma; `Esc`
cancela. Mouse como hoje. "Posição inicial", "Limpar", "Espelhar", "Colar FEN", "Copiar
FEN"; legalidade como aviso com ícone e texto; paleta do tabuleiro `#F0D9B5/#B58863`
com opção de alto contraste `#FFFFFF/#7A7A7A`.

### 11.3 Diagrama a partir dos lances — e a segmentação das partidas

`core/editor/xadrez.py`. Só participam parágrafos `notacao` e `comentario` e trechos
`papel="lance"` — nunca `corpo` ("after Nf3 the bishop…" não é linha). `tokens()`
separa o número do lance (`23.`, `23…`, `23...`) do lance, porque
`notacao.parece_lance("1.e4")` é falso, e usa o `…` para inferir o lado. **Uma partida
(segmento) começa** num `Titulo`, num número `1.`, ou num `Diagrama` cujo FEN difere da
posição corrente — que re-sincroniza a linha e avisa "diagrama n não bate com a linha"
(é o erro de OCR mais comum). `posicao_apos(blocos, ate)` monta a árvore de variantes
(pilha em `(`/`)`/`[`/`]`; cada variante parte da posição anterior ao lance que a abre)
e devolve a posição da **linha que contém o cursor** e o lado proposto; o primeiro lance
ilegal interrompe e é mostrado.

### 11.4 Validação de notação

`validar(blocos)`: a mesma travessia por **todas** as linhas de **todos** os segmentos,
com `notacao._melhor_lance_legal(board, lido, confiancas=[1.0]*len(lido))` para a
sugestão; resultado no painel Resultados (lista clicável genérica de
`ui/editor/resultados.py`), e no texto como **fundo laranja com padrão** (`bgstipple
gray25` + `relief raised`, tag `notacao-ilegal`) mais o `✗` na calha — o Tk não desenha
sublinhado tracejado (§13.2). Não corrige sozinho.

### 11.5 Figurinas e letras

Tabelas `en`/`pt`/figurinas; conversão só em tokens de lance; leitura aceita figurinas
pretas, escrita emite as brancas. **Figurinas ao digitar**: em `notacao`/`comentario`,
ao fechar um token que parece lance, a letra vira figurina (como o ChessBase);
`familia="simbolos"` quando a fonte do texto não a desenha.

### 11.6 Símbolos e NAGs

Paleta com `nags.FAMILIAS`, os 23 da barra rápida (`nags.NAGS_POR_FAMILIA`, movido de
`ui/main_window.py`, e reexportado lá) e, **só quando importável**, `chess_symbols`
(que ainda não está no git — ED-pré); insere símbolo **e código** (`Trecho.nag`).
"Marcar NAGs" atribui `papel="nag"`+`nag` ao que veio digitado ou do OCR quando o
símbolo é unívoco (`nags.POR_CODIGO` invertido) e lista os ambíguos (`=`, `∞`). Botões
reais ≥ 24×24 px, setas/`Enter`/`Esc`, tooltip, símbolo sem glifo pela fonte de recurso.

### 11.7 Numeração, legendas e referências

`numerar_objetos` para diagramas, figuras e tabelas; `Trecho.ref` com texto regenerado;
"Legenda sugerida" (ED-05b): "Diagrama 12: após 23…♖xe4 — Pretas jogam" (lado inferido
do número seguinte, proposto e não imposto); "Cabeçalho em legenda" converte o `h2` da
F67.

### 11.8 PGN

Uma partida por segmento (§11.3); STR completo com `?`/`*`; `[SetUp "1"]`+`[FEN]` quando
começa em diagrama; variantes, comentários `{}`, NAGs por `Trecho.nag` (`$14`) e os
sem código como `{símbolo}` com aviso; resultado normalizado.

### 11.9 Índice de jogadores, partidas e aberturas

`papel="jogador"|"abertura"` com `Trecho.chave` (`"Wely, Loek van"`, `"C42"`), marcados
por "Marcar jogador/abertura…" (sugestão automática dos cabeçalhos "Nome – Nome"); a
página (`epub:type="index"`, `role="doc-index"`) lista por chave com links ao `id` do
título ou diagrama mais próximo e o número da partida.

### 11.10 Chave de símbolos

Página `epub:type="glossary"` com os NAGs usados (marcados e digitados), rótulo de
`nags.rotulo`.

---

## 12. Critérios de aceite globais

Uma função por AC em `tests/test_editor_ac_globais.py`; **toda ação nos testes é feita
pelo comando** (§14).

**AC-001 — Abrir, editar, salvar, reabrir.** EPUB de `exportar.para_epub` (2 capítulos,
3 diagramas nos dois modos, tabela, negrito): abrir, trocar uma palavra, mudar a posição
de um diagrama (`png`, recuperado pelo `alt`), salvar, reabrir → palavra e FEN novos;
`epubcheck` limpo (quando disponível); nenhuma ilha; mesmos nomes de entrada no zip;
recursos não tocados com bytes iguais. Obrigatório.

**AC-002 — Os formatos saem do mesmo livro.** Exportar EPUB, HTML e DOCX → `texto_de`
idêntico; DOCX com `Heading 1`, itálico, imagem; HTML com `data-fen`. Obrigatório.

**AC-003 — Modo texto ↔ código sem perda.** Capítulo com todos os blocos e trechos, ilha
`<svg>`, ilha inline `<cite>`, `&nbsp;`, comentário: `alternar_modo()` × 10 → canônico
igual; ilhas e comentário byte a byte (entidade da ilha numérica). Obrigatório.

**AC-004 — Nenhuma falha silenciosa.** Tag aberta, e também `epub:type` sem
`xmlns:epub`: `alternar_modo()`/`salvar()` recusam com linha e coluna na barra,
Mensagens e Validação; cursor no erro; hash do arquivo igual. Obrigatório.

**AC-005 — Desempenho.** Livro de 300 capítulos-página, 300 mil caracteres, 500
diagramas: abrir ≤ 3 s, capítulo ≤ 0,5 s, modo ≤ 1 s, busca ≤ 2 s, salvar ≤ 5 s, RSS ≤
600 MB — `scripts/medir_editor.py` na máquina de referência (`docs/OPERATIONS.md`), teste
`slow`. Importante.

**AC-006 — Tudo pelo teclado.** Menus por mnemônico (`entrycget(i, "underline")` +
`invoke` com diálogos injetados); painéis por `F6` (teste `gui` com `deiconify`);
diagrama inserido e posição editada pelo mapa da §11.2; foco visível — `highlightthickness
≥ 2` nos `tk`, e nos `ttk` o **`AnelDeFoco`** (um `Frame` com `highlightthickness=2`
alternado em `<FocusIn>`/`<FocusOut>`, porque no tema `vista` `Button.focus` não tem
`focuscolor`); roteiro `docs/roteiros/editor_teclado.md`. Obrigatório.

**AC-007 — Codificação.** `ç`, `♕`, `⩲`, `—`, `&nbsp;` → UTF-8 sem BOM, declaração,
intactos, nenhum `Ã`, nenhuma entidade nomeada no zip. Obrigatório.

**AC-008 — A ponte.** Livro do pipeline: editar o texto de dois blocos com origem, um
sem, apagar um quarto com origem, salvar → no diário do `review_journal_path`, dois
eventos `reviewed` (`before`/`after` corretos, `reason_codes` `("editor",)`, `user`
`"editor"`) e um `rejected`; documento projetado atualizado; `original_value`
preservado; um bloco já editado na fila recebe evento com `before` igual ao `after` da
fila. Obrigatório.

**AC-009 — O diagrama nunca perde a posição.** Salvar EPUB; DOCX em `fonte` e `png`;
ler os dois → mesmo FEN e `lado=""` quando não registrado. Importante.

**AC-010 — Rascunho.** `tique()` com relógio a 61 s; destruir a janela; reabrir → oferta;
texto e imagem colada de volta. Obrigatório.

---

## 13. Qualidade

### 13.1 Desempenho

Orçamentos do AC-005 e: tecla ≤ 50 ms, realce 200 KB ≤ 200 ms, `dump` ≤ 100 ms, tabela
20×20 ≤ 1 s. `scripts/medir_editor.py` nasce na ED-03 e cresce; os `assert` moram num
teste `slow` (marker registrado no `pyproject.toml`), fora do gate padrão
(`-m "not slow"`).

### 13.2 Acessibilidade

- Teclado em tudo (AC-006), menu de contexto por `Shift+F10`/`App`, editor de posição.
- Foco visível: `highlightthickness ≥ 2` (`tk`) e `AnelDeFoco` (`ttk`), conferidos em
  cada fase que cria widget.
- Contraste ≥ 4,5:1 em texto e realce; ≥ 3:1 entre traço da peça e casa; anel de seleção
  de dois tons; realce escuro com texto branco.
- Nenhuma informação só por cor — **com o que o Tk desenha**: ortografia = sublinhado
  contínuo vermelho (`underline` + `underlinefg`, o Tk não tem ondulado); notação
  ilegal = fundo laranja com padrão `bgstipple` + relevo + `✗` na calha; suspeito = fundo
  amarelo + `!` na calha; diagrama ilegal = ícone + texto; ilha = rótulo + dica.
- Alvos ≥ 24×24 px com respiro; botões reais com `text`, tooltip e eco na barra de
  status.
- Zoom só na superfície de edição; DPI por monitor declarado.

### 13.3 Erros

Duas camadas: erro de entrada previsível → mensagem simples com o que fazer; falha
interna → traceback dobrado e "Copiar", rotulada como defeito do programa.

### 13.4 Registro

Logger `pyboxeditor.editor` → painel Mensagens (INFO).

---

## 14. Testes

- **Sem display**: modelo, dialeto, xhtml, css, epub, docx, html, pdf, importar_ir,
  xadrez, busca, ortografia, historico, conversao, sumario, livro_ops, dump, tags —
  unitários e propriedades (`tests/editor_gerador.py`).
- **Widgets** com `conftest.raiz_tk()`: a janela é `withdraw`n e **não recebe teclas**;
  os testes **chamam o comando** (`texto.alternar("negrito")`, `texto.inserir("xyz")`,
  `janela.comandos["salvar"]()`), e um teste à parte confere as ligações: `menus.montar`
  guarda `(menu, item) → nome_do_comando`, o teste troca `comandos[nome]` por um espião
  e chama `menu.invoke(i)`; para os acordes, `event_generate` só num teste `gui` com
  `deiconify()` + `focus_force()`, conferindo texto **e** `index("insert")` após cada
  acorde emacs da DEC-03.
- **Golden files** em `tests/dados/editor/` (XHTML na ED-00, DOCX na ED-09).
- **epubcheck** gated (pula sem Java). **Desempenho** só `slow`. **Roteiros** em
  `docs/roteiros/`.

---

## 15. Riscos e limites (honestos)

| Risco/limite | Consequência | Mitigação |
|---|---|---|
| `tk.Text` não pagina, não faz CSS, uma fonte por caractere, sem versalete, sem sublinhado ondulado/tracejado, sem margem | tela ≠ leitor; avisos por fundo e calha, não por estilo de traço | estilo de tela, CSS mínima, PDF, calha, §13.2 |
| Bloco com vários `\n` (lista, citação, quebra suave) | identidade por marca, não por linha | DEC-03 |
| Tabela como grade de widgets | pesada; sem mesclar | ilha acima de 400 células |
| Entidades nomeadas | EPUB 3 as rejeita | ilha reescrita em numéricas (DEC-07) |
| `ReviewEvent` sem estilo | formato não chega ao documento editorial | perda declarada; pedido em ED-pré |
| `ttk` tema `vista` | sem `focuscolor` | `AnelDeFoco` |
| Leitor de tela | controle alcançável chega mudo | botões com `text`, tooltip, eco; limite não resolvido |
| Barra de status só visual | mudanças não anunciadas | eco no painel Mensagens |
| Ordem de Tab fixa | pode diferir da posição visual | compromisso declarado |
| Fontes só no Windows | fora dele, símbolo na tela pode sair caixa | aviso |
| Ortografia em português | só na ED-06b | dicionário do usuário |
| Nota por OOXML direto | risco de o Word recusar | roteiro no Word e no LibreOffice; fallback parágrafo |
| `fitz.Story` subconjunto de CSS | PDF ≠ EPUB em CSS avançada | relatório |
| `fen_de_linhas` sem rótulo | orientação ambígua; lado desconhecido | `estado="revisar"`, `lado=""` |
| Dobra de blocos | não há | capítulo curto, ir para linha |
| Trabalho paralelo na árvore | arquivos não commitados; `main_window.py` com WIP | ED-pré; integração só do que está no HEAD; `git add -p` |

---

## 16. Não objetivos

Ser um navegador; ser o Word; corrigir o OCR; reescrever `core/exportar.py` (a ED-12
mede antes de decidir).

---

## 17. O que "AAA" quer dizer aqui

Aprova quando todas as respostas são "sim": **completude** (cada recurso pedido tem
seção, fase e AC, ou está na §2.2/§16 com o motivo); **consistência** (um nome, um
sentido; citação por símbolo onde há trabalho paralelo; tudo verificado por `grep`);
**verificabilidade** (cenário, ação, resultado observável, método; nada por tecla em
janela sem foco); **executabilidade a frio** (nada que uma fase usa nasce depois);
**honestidade** (todo limite na §15 com mitigação); **aderência** (invariantes do
`CONTEXT.md` 1, 4, 5, 6, 8, 9, 11 e regras da `SPEC.md` em todo módulo novo).
