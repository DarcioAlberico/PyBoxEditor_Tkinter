# Roadmap — a janela de edição e a conversão para HTML, EPUB e DOCX

Versão: 1.3
Data: 2026-09-19
Status: **ED-00, ED-01, ED-02, ED-03, ED-04, ED-06, ED-06b, ED-07, ED-08, ED-09 e ED-10 implementadas** (2026-09-21)
Documento complementar a [`SPEC_EDITOR.md`](SPEC_EDITOR.md) v1.2 (a especificação; este
roadmap cita as seções dela por número) e a [`../ROADMAP.md`](../ROADMAP.md) (o registro
histórico do projeto — as fases daqui usam o prefixo `ED-` para não colidir com a
numeração `F` de lá).

**Histórico.** Três voltas de revisão adversarial (oito pareceres) — ver o cabeçalho da
spec. A v1.3 (terceira volta, sem crítico) fixou: o `div.diagrama` de hoje traz o FEN em
`title`; `data-origem-*`; `alt_de` na ED-00; a calha do código na própria ED-07;
contexto e verificação em ED-05b/06b/09b/13; `Ctrl+BackSpace`/`Delete` como comandos;
`hifenizar` no formato de página; ED-05 sem depender de `chess_symbols`; inserir
link/id/imagem no código; `test_nags.py` na ED-05; o `slow` rodado na ED-03. A v1.2: `historico`, `conversao` e `sumario` (núcleo) nascem na ED-00 porque
fases paralelas os consomem; a ED-02 integra na janela principal **só o que está no
HEAD** (o resto vai para a ED-11, que depende da ED-pré); a ED-10 passa a depender da
ED-02 e as fases só de `core/` (ED-09, ED-09b) não ligam menu — os itens de DOCX/PDF/PGN
são ligados na ED-12; toda verificação de interface é por comando, e a de acordes por um
teste `gui` à parte; `scripts/medir_editor.py` nasce na ED-03; estimativas refeitas.

## Objetivo

Pôr, entre o OCR e o arquivo, uma janela em que o livro se edita por dentro — modo
texto à maneira do WordPad e do Word, modo código à maneira do Sigil, objetos de xadrez
como objetos — e escrever EPUB, HTML, DOCX, PDF paginado e TXT **do mesmo livro
editado**.

## Estado conhecido (o que se reaproveita, e onde está)

Arquivos **commitados** (citação por linha é estável):

- `core/exportar.py`: CSS (`CSS` — texto pronto; `CSS_DO_DIAGRAMA`,
  `CSS_DA_FONTE_DO_DIAGRAMA`, `CSS_DOS_SIMBOLOS` — **moldes** `%(…)s`), `MOLDURA_NA_CSS`,
  `RAIO_NA_CSS`, `MOLDURA_NO_DOCX`, `CORPO_PADRAO_PT`, `PASSO_DO_CORPO_PT`,
  `IDIOMA_PADRAO`, `TIPOS_DE_FONTE`, `PISO_DO_SIMBOLO`, `classe_da_fonte`, `corpo_valido`,
  `_alternativo` (escreve o FEN no `alt`), `fontes_usadas`, `fonte_dos_simbolos`,
  `_embutir_fontes_no_docx`, `_diagrama_em_texto`, `_caixa_do_diagrama`, `trechos`,
  `_por_familia`, `identificador_de`, `agora`, `_propriedades_do_docx`,
  `_desenho_da_pagina`, `_idioma_do_estilo`, `para_docx`, `para_epub`. O EPUB de hoje:
  `OEBPS/content.opf`, `pagina-NNNN.xhtml`, `estilo.css`, `imagens/`, `fonts/`,
  `nav.xhtml`; **sem** `hr.pagina` (só a regra CSS).
- `core/render_diagrama.py`: `Fonte` (`casas`, `molduras`, `moldura_em_glifo`),
  `carregar`, `fontes`, `desenhar(fen, *, fonte=, lado_px=, moldura=, cantos=,
  orientacao=, coordenadas=)`, `linhas(fen, fonte: Fonte, orientacao)` (8 linhas),
  `grade(fen, fonte, orientacao, moldura, cantos)` (10 linhas com rótulo nos glifos),
  `rotulos`, `_casas_do_fen`, `cor_da_casa`, constantes.
- `core/tabuleiro_edicao.py` (`TabuleiroEdicao`; importa `core.diagrama` no topo — cv2),
  `ui/dialogo_diagrama.py` (`DialogoDiagrama`), testes `tests/test_f82_tabuleiro.py`,
  `tests/test_f71_diagrama.py`, `tests/test_f83_treino_diagrama.py`.
- `ui/dialogo_do_diagrama.py: PainelDoDiagrama`; `ui/dialogo_de_exportacao.py`.
- `core/nags.py` (`TABELA`, `FAMILIAS`, `POR_CODIGO`, `rotulo`, `desenhavel`, `sem_glifo`);
  `ui/fontes.py`; `ui/pecas.py`.
- `core/lexico.py` (`carregar`, `Lexico.conhece`, `_indice_por_forma` — função de módulo,
  `juntar_hifenizadas`, `caminho_do_usuario` — faz `splitext`, `salvar_do_usuario`;
  importa `core.notacao` → `box_service` → cv2), `core/notacao.py` (`parece_lance` —
  falso para `"1.e4"`, `e_token_de_notacao`, `_melhor_lance_legal(board, lido,
  confiancas)`), `python-chess`.
- `core/livro.py:159-386`; `config/settings.py` (`Settings.get/set`, dict plano);
  `config/paths.py`; `core/services/document_service.py:30-90`; `core/services/
  task_controller.py`; `appy.py` (`_declarar_dpi`; importa `MainWindow` no topo).
- `tests/conftest.py: raiz_tk()`; `tests/test_f35_atalhos.py`; `tests/test_dialogo_de_exportacao.py`;
  `tests/test_f111_arquivo.py`; `tests/test_f58_render_diagrama.py`,
  `test_f59_fonte_embutida.py`, `test_f97_moldura_e_corpo.py`, `test_f99_coordenada_em_glifo.py`.

Arquivos **não commitados** (trabalho paralelo de outra ferramenta; citar por símbolo):

- `ui/main_window.py`: `NAGS_POR_FAMILIA` (nível de módulo), `_build_menu_notacao`,
  `_busy`, `_run_task`, `lexico_da_sessao`, `exportar_livro_action` + `concluir` (**está
  no HEAD**), `processar_documento_editorial_action` + `concluir` e
  `_exportar_documento_revisado` (**não estão no HEAD**), `revisar_documento_editorial_action`.
- `core/editorial_model.py` (`ReviewEvent` sem campo de estilo; `apply_review` exige
  `before == decision.value`), `core/editorial_review.py` (`ReviewSession.edit(target_id,
  value, reason_codes)`, `reject`, `from_journal(documento, journal)`,
  `ReviewJournal.append`), `core/editorial_adapters.py`, `core/editorial_legacy.py`
  (`_bloco_revisado` zera `negrito`), `core/chess_symbols.py`, `CONTEXT.md`,
  `tests/test_menu_por_fluxo.py`, `tests/test_guardas_da_janela.py`,
  `tests/test_editorial_review_phase5.py`, `scripts/smoke_release.py`.

Ambiente: Python 3.13 (`.venv/Scripts/python.exe`), Tk 8.6.15 (tema `vista`), PyMuPDF
1.27 (`fitz.Story`), `python-docx` 1.2 (sem notas; sem `Hyperlink`/`TOC n`), `lxml`,
`epubcheck` 5.3 (Java).

## Princípios de execução

1. **Uma fase, um ou mais commits no `master` (um por sessão)**, só com os arquivos da
   fase; num arquivo compartilhado, as hunks do editor entram por `git add -p` e o SHA de
   base fica no Registro. Mensagem em português, uma frase.
2. **Verde antes de commitar**: `ruff check core ui` e a suíte (`-m "not slow"`).
3. **Nada de dependência nova obrigatória** (DEC-07); extras no `pyproject.toml`.
4. **UTF-8 sem BOM**; crivo `grep -rn "Ã[§£©¡³ªº]"`.
5. **Regra em `core/editor/`, widget em `ui/editor/`**; nada pesado no topo (DEC-07);
   `AC-ED02-7` (subprocesso) é repetido por toda fase que toca módulos pesados.
6. **Português nos nomes**; docstring de módulo explica o porquê.
7. **Testes de interface por comando**; ligações num teste `gui` à parte (§14).
8. **`ui/editor/menus.py`: uma seção por fase, só cresce**; cada fase liga os seus
   comandos por `janela.registrar_comandos(modulo)`.
9. **Registro de execução** atualizado ao fim de cada fase.

## Grafo de dependências e paralelismo

```
ED-pré  (commit da camada editorial — do usuário)  ─────────────────────────────┐
ED-00 modelo, dialeto, xhtml, css mínima, estilo_do_livro, historico, conversao, sumario
 ├── ED-01 livro no disco (EPUB, projeto, rascunho, recentes, checkpoints, livro_ops)
 │    └── ED-02 janela, abas, menus, atalhos, resultados, conclusão, integração (HEAD)  ◄── ED-03, ED-07
 │         ├── ED-04 objetos, notas, propriedades, colar, dividir/juntar
 │         │    ├── ED-05 xadrez ── ED-05b marcas, setas, legenda, chave
 │         │    └── ED-11 ponte com o documento editorial  ◄── ED-05, ED-pré
 │         ├── ED-06 busca, ortografia, símbolos, contagem ── ED-06b tipografia, pt, buscas salvas
 │         ├── ED-08 livro no modo código  ◄── ED-07
 │         └── ED-10 HTML + EPUB completos + importadores + TXT (menus)
 ├── ED-03 texto rico (widget, tags, objetos, calha, medir_editor)
 ├── ED-07 editor de código (widget, realce, consertar, clipes)
 ├── ED-09 DOCX escrever (core) ── ED-09b DOCX ler (core)
ED-12 PDF, PGN, índice, itens de menu DOCX/PDF/PGN, relatório único, medição  ◄── ED-05, ED-09b, ED-10
ED-13 qualidade AAA  ◄── todas
```

| Onda | Fases |
|---|---|
| 1 | ED-00 (ED-pré a qualquer momento) |
| 2 | ED-01 · ED-03 · ED-07 · ED-09 |
| 3 | ED-02 · ED-09b |
| 4 | ED-04 · ED-06 · ED-10 (dividem `ui/editor/menus.py` só por acréscimo de seção — princípio 8) |
| 5 | ED-05 · ED-06b · ED-08 (idem) |
| 6 | ED-05b · ED-11 · ED-12 |
| 7 | ED-13 |

**Unidade**: uma sessão ≈ 4 h de agente, um commit. ED-00 4 · ED-01 3 · ED-02 3 · ED-03
4 · ED-04 3 · ED-05 3 · ED-05b 1 · ED-06 3 · ED-06b 2 · ED-07 2 · ED-08 4 · ED-09 3 ·
ED-09b 2 · ED-10 3 · ED-11 2 · ED-12 3 · ED-13 3 — **48 sessões**, 7 ondas.

## Protocolo de mudança do plano

Dividir → `ED-nnb`; inserir → `ED-nn.5`; pular/abandonar → status e motivo; divergir da
spec → registrar na fase, não editar a spec.

---

## ED-pré — A camada editorial entra no git

**Quem faz:** o usuário. **Bloqueia:** ED-11 (e a parte da ED-02 que toca
`processar_documento_editorial_action` — que por isso foi para a ED-11).
**Resultado:** o commit do usuário com **tudo que `import ui.main_window` alcança** (os
`core/editorial_*.py`, `core/ocr_*.py` e `core/services/ocr_service.py` modificados,
`core/linha_trainer.py`, `core/editorial_pipeline.py`, `ui/dialogo_rotulagem.py`,
`ui/dialogo_revisao_*.py`, `core/ocr_phase7.py`, `core/ocr_training.py`,
`core/chess_symbols.py`, `CONTEXT.md`, os três testes e `scripts/smoke_release.py`).
**Pedido registrado** (para uma versão futura da ponte): `ReviewEvent.metadata`,
`apply_review` fundindo em `block.metadata`, `_bloco_revisado` lendo `bold_spans`.

### Verificação

```
git worktree add --detach ../pbe-pre HEAD
cd ../pbe-pre && ../PyBoxEditor_Tkinter/.venv/Scripts/python.exe -c "import ui.main_window, appy"
../PyBoxEditor_Tkinter/.venv/Scripts/python.exe -m pytest tests/test_menu_por_fluxo.py tests/test_guardas_da_janela.py tests/test_editorial_review_phase5.py -q -p no:cacheprovider -o addopts=""
```

---

## ED-00 — Modelo, dialeto, XHTML, CSS mínima, `estilo_do_livro`, histórico, conversão, sumário

**Prioridade:** P0 · **Dependências:** nenhuma · **Paralelizável com:** nada
**Resultado:** o núcleo puro que todas as outras fases consomem — testável sem display,
leve, com ida e volta sem perda no dialeto, entidades HTML aceitas e reescritas, ilhas
preservadas, e os EPUBs de hoje abrindo com os diagramas de volta.

### Contexto para começar do zero

Ler: spec §3, §4 (DEC-01, DEC-02, DEC-04, DEC-06, DEC-07, DEC-08), §5, §6, §10.8;
`core/editorial_model.py` (estilo de dataclass); `core/exportar.py` 30–273 (constantes e
moldes; `_alternativo`), 274–380, 450–514 (`_xhtml_da_pagina`), 600–810 (`para_epub`:
o nav de hoje); `core/render_diagrama.py` 143–205 (`Fonte`), 279–330 (`linhas`),
354–410 (`grade`); `xml.parsers.expat` (`SetParamEntityParsing`, `UseForeignDTD`,
`ExternalEntityRefHandler`, `SkippedEntityHandler`, `CurrentByteIndex`,
`CurrentLineNumber`, `namespace_separator`).

### Entregas

- `core/editor/__init__.py`, `ui/editor/__init__.py`; `pyproject.toml`: pacotes
  `core.editor` e `ui.editor`; marker `slow` em `markers`.
- `core/estilo_do_livro.py`: as constantes de estilo **movidas** de `core/exportar.py`
  (`CSS`, `CSS_DO_DIAGRAMA`, `CSS_DA_FONTE_DO_DIAGRAMA`, `CSS_DOS_SIMBOLOS`,
  `MOLDURA_NA_CSS`, `RAIO_NA_CSS`, `MOLDURA_NO_DOCX`, `CORPO_PADRAO_PT`,
  `PASSO_DO_CORPO_PT`, `IDIOMA_PADRAO`, `TIPOS_DE_FONTE`, `PISO_DO_SIMBOLO`,
  `MODOS_DE_DIAGRAMA`, `classe_da_fonte`, `corpo_valido`), com os comentários que as
  acompanham; `exportar.py` as importa de lá (mesmos nomes; nenhum teste muda).
- `core/editor/modelo.py`: §5 completa (`kw_only`, `default_factory`, `Titulo` força
  `id_persistente`), `validar()` (INV-01 por capítulo, INV-03, INV-04 levantam; INV-02
  avisa), `id_novo`, `fen_valido`, `igual`, operações da §5.2, `to_dict`/`from_dict`.
- `core/editor/dialeto.py`: tabelas da §6; atributos conhecidos; sinônimos; ordem
  canônica; `css_padrao(corpo_pt, moldura, cantos)` (aplica `%` **só** aos moldes);
  `atributos_de_diagrama`/`diagrama_de_atributos`; `atributos_de_origem`/
  `origem_de_atributos` (`data-origem-pagina`, `-bloco`, `-caixa`, `-fundidas` — o
  prefixo evita a colisão com a `data-pagina` da marca de página).
- `core/editor/xhtml.py`: `ler(texto: str | bytes) -> Capitulo` (parser `expat` da
  DEC-07 na letra: namespaces, entidades, `SkippedEntityHandler` que levanta,
  comentários/PIs, `linha_fonte`, ilhas por bytes com a regra dos elementos vazios),
  `ErroDeXhtml(linha, coluna, mensagem)`, `escrever(capitulo) -> str` (entidades da
  ilha reescritas em numéricas; `xmlns:epub` quando há `epub:`), `canonico(texto,
  — é `escrever(ler(texto))`; a entidade nomeada nunca sobrevive, o EPUB 3 a proíbe)`,
  `bem_formado(texto)`, `ler_fragmento`/`escrever_fragmento`,
  `diagrama_de_div(div) -> Diagrama` (FEN do `title`/`aria-label`
  quando é FEN; orientação a que reproduz as linhas; `fen_de_linhas` só sem título),
  `diagrama_de_img(figure) -> Diagrama | Figura` (DEC-06).
- `core/editor/dialeto.py: alt_de(diagrama, idioma="pt") -> str` (a lista de peças por
  cor, DEC-06) — nasce aqui porque `xhtml.escrever` e `epub.escrever` a usam; a ED-05 só
  a consome.
- `core/editor/css_minima.py`: `ler`, `cascata`, `Folha.estilo_de`, `escrever`.
- `core/editor/historico.py`: `Historico(limite=200, coalescencia_s=0.7,
  relogio=time.monotonic)` por capítulo.
- `core/editor/conversao.py`: `RelatorioDeConversao` (§10.8), `OpcoesDeConversao`.
- `core/editor/sumario.py`: `gerar_dos_titulos(livro, niveis)`, `escrever_nav(livro)`
  (`toc`, `landmarks`, `page-list`), `ler_nav`, `escrever_ncx`, `ler_ncx`,
  `pagina_de_sumario(livro)`.
- `core/render_diagrama.py: fen_de_linhas(linhas, fonte: Fonte | str) -> tuple[str,
  str | None]` (posição, orientação lida dos glifos de moldura da grade de 10 ou `None`).
- `tests/editor_gerador.py`; `tests/dados/editor/` (XHTML golden).
- Testes: `tests/test_editor_modelo.py`, `_xhtml.py`, `_css_minima.py`, `_historico.py`,
  `_conversao.py`, `_sumario.py`, `tests/test_estilo_do_livro.py`.

### Critérios de aceite

- **AC-ED00-1** R2: 200 capítulos gerados → `igual(ler(escrever(c)), c)`.
- **AC-ED00-2** R1: 50 XHTML gerados (com `&nbsp;`, `&#160;` e U+00A0 misturados) →
  `canonico(escrever(ler(x))) == canonico(x)`.
- **AC-ED00-3** R3: `<svg>` (com `&nbsp;` dentro), `<div style>`, tabela aninhada,
  `<cite>` inline, `<br/>`, `<img alt="a>b"/>`, `<!-- c -->` e uma PI atravessam
  `ler`→`escrever` byte a byte **exceto** o `&nbsp;` da ilha, que sai `&#160;`; um
  documento com `standalone="yes"` **lê** (a declaração é regenerada sem ele);
  `ET.fromstring(escrever(...))` passa e o `epubcheck` (quando disponível) não acusa
  `RSC-016`.
- **AC-ED00-4** R5: EPUB de `exportar.para_epub` (negrito, títulos 1 e 2, diagrama
  `png`, diagrama `fonte` com coordenadas e sem moldura, um do lado das pretas com
  coordenadas, tabela, `span.sim`) → zero ilhas; o `png` volta como `Diagrama` pelo
  `alt` com `estado="revisar"` e `lado=""`; o `fonte` volta com o FEN do `title`, a
  orientação deduzida das linhas e `estado="ok"` — com e sem coordenadas; um
  `div.diagrama` **sem** `title` e sem rótulo (montado no teste) volta pelas linhas com
  `estado="revisar"`; um `img` com `alt="Diagrama"` volta `Figura`.
- **AC-ED00-5** INV-06: `<p>aberto` → `ErroDeXhtml` linha 1 e coluna certa;
  `<span epub:type="x">` sem `xmlns:epub` → `ErroDeXhtml("prefixo não declarado")`;
  `&nbsp;` **passa**; `&naoexiste;` → `ErroDeXhtml("entidade desconhecida")`.
- **AC-ED00-6** `css_minima.ler(css_padrao(16, "simples", "reto"))`: `text-indent: 1.2em`
  em `p`, `text-indent: 0` em `p.primeira`, `!important` tolerado; `@media print`, `p >
  span.x` e `@import` preservados byte a byte por `escrever` com uma regra alterada;
  `cascata` de duas folhas: a segunda vence.
- **AC-ED00-7** `validar()`: id duplicado **no mesmo capítulo** levanta; o mesmo id em
  dois capítulos passa; FEN inválido e tabela não retangular levantam; recurso ausente
  avisa.
- **AC-ED00-8** Subprocesso: importar `core.editor.modelo`, `dialeto`, `xhtml`,
  `css_minima`, `historico`, `conversao`, `sumario` deixa `fitz`, `numpy`, `cv2`, `PIL`,
  `tkinter` fora de `sys.modules`; `exportar.CSS is estilo_do_livro.CSS`.
- **AC-ED00-9** Para 50 FENs legais nas duas fontes: `fen_de_linhas(linhas(fen, fonte),
  fonte) == (posicao, None)`; `fen_de_linhas(grade(fen, fonte, "preta", "simples",
  "reto"), fonte) == (posicao, "preta")` na Chess Merida (a SkakNew não tem grade e o
  caso é pulado com registro).
- **AC-ED00-10** `Historico`: dez pontos desfeitos um a um devolvem os blocos iniciais;
  refazer devolve os finais; dois pontos a 300 ms (relógio injetado) no mesmo bloco são
  um; capítulos independentes.
- **AC-ED00-11** `escrever_nav` de um livro com 3 títulos, 2 marcos e 12 `MarcaDePagina`
  → `nav.xhtml` com `toc`, `landmarks` e `page-list` de 12 entradas; `ler_nav` devolve o
  mesmo sumário; `escrever_ncx` tem `dtb:uid` = identificador.

### Verificação

```
.venv/Scripts/python.exe -m ruff check core/editor core/estilo_do_livro.py core/exportar.py core/render_diagrama.py tests/test_editor_modelo.py tests/test_editor_xhtml.py tests/test_editor_css_minima.py tests/test_editor_historico.py tests/test_editor_conversao.py tests/test_editor_sumario.py tests/test_estilo_do_livro.py
.venv/Scripts/python.exe -m pytest tests/test_editor_modelo.py tests/test_editor_xhtml.py tests/test_editor_css_minima.py tests/test_editor_historico.py tests/test_editor_conversao.py tests/test_editor_sumario.py tests/test_estilo_do_livro.py tests/test_f111_arquivo.py tests/test_f58_render_diagrama.py tests/test_f59_fonte_embutida.py tests/test_f97_moldura_e_corpo.py tests/test_f99_coordenada_em_glifo.py -q -p no:cacheprovider -o addopts=""
```

(os cinco `test_f*` consomem as constantes que saem de `exportar.py` e o
`render_diagrama` que ganha `fen_de_linhas`; a suíte inteira roda antes do commit.)

### Saída

AC verdes, suíte verde, commit(s) `ED-00`. **Reversão**: apagar `core/editor/`,
`ui/editor/`, `core/estilo_do_livro.py` (devolvendo as constantes) e as linhas do
`pyproject.toml`.

### Registro — 2026-09-19 — IMPLEMENTADA

Entregue em `core/estilo_do_livro.py`, `core/editor/{modelo,dialeto,xhtml,css_minima,
historico,conversao,sumario}.py`, `render_diagrama.fen_de_linhas` (+ `mapa_da_fonte`),
`tests/editor_gerador.py`, `tests/dados/editor/capitulo.xhtml` e sete arquivos de teste
(79 testes). Medido: 300 capítulos gerados atravessam `escrever ∘ ler` com **zero**
diferenças e em idempotência (2,7 s no total); os EPUBs de `exportar.para_epub` nos dois
modos abrem sem ilha e com todo diagrama de volta — em `fonte`, com FEN, orientação e
`estado="ok"` (o `title` já trazia o FEN); em `png`, pelo `alt`, com `estado="revisar"`.

**O que divergiu da spec, e por quê:**

- **A entidade nomeada da ilha vira numérica na leitura**, e não só na escrita: um
  modelo que guardasse `&nbsp;` divergiria do arquivo a cada gravação, e `igual` não
  fecharia. `canonico` ficou sem `manter_entidades` (não há o que manter: o EPUB 3 a
  proíbe).
- **`Capitulo.namespaces`** (novo campo): os prefixos declarados no `<html>` que não são
  `epub` nem conhecidos (`xlink`, `m`, …) — uma ilha pode usá-los, e o escritor precisa
  redeclará-los. Os conhecidos são redeclarados só quando uma ilha os usa (regex sobre
  as ilhas, não sobre o corpo: `m:` casava dentro de prosa).
- **`Capitulo.normalizar_notas`**: as notas ficam de rodapé primeiro, depois de fim — é a
  ordem do XHTML (`aside` antes de `section`), e sem ela a ida e volta trocava a ordem.
- **`papel="comentario"` ↔ `span.com`** (a §6.2 não tinha classe para ele).
- **Parágrafo dentro de `blockquote`/nota** volta com `estilo="citacao"`/`"nota"` (a
  classe não vai ao `<p>`; o contêiner é quem diz o estilo).
- **`Tabela`** normaliza na construção: `primeira_fila_cabecalho` ⇔ todas as células da
  primeira fila `cabecalho` (as duas coisas ditas de dois jeitos).
- **`MarcaDePagina.id` = `pg-<n>`** por construção (é a âncora da `page-list`).
- **`historico.Ponto.indices`** (id → posição no "antes"): sem isso um bloco apagado e
  desfeito voltava no fim do capítulo.
- **`render_diagrama.mapa_da_fonte`**: o mapa sem conferir o arquivo da fonte — ler um
  diagrama em texto não pode depender de a fonte estar instalada.
- **`dividir_por_titulo`** em `modelo.py` é por capítulo (puro); o de nível livro fica
  em `livro_ops` (ED-01), como o roadmap já dizia para `dividir`/`juntar`.
- **`xhtml.analisar`** (a árvore com deslocamentos) é pública: `sumario.ler_nav`/`ler_ncx`
  a usam, e a ED-07 ("bem-formado", "consertar") também vai usar.
- O `alt` gerado (`dialeto.alt_de`) e o `title` = FEN do diagrama são reconhecidos na
  leitura e **não** voltam como próprios do usuário (senão a idempotência quebrava).

---

## ED-01 — O livro no disco: EPUB, projeto, rascunho, recentes, pontos de verificação, operações de livro

**Prioridade:** P0 · **Dependências:** ED-00 · **Paralelizável com:** ED-03, ED-07, ED-09
**Resultado:** abrir e salvar qualquer EPUB preservando a disposição; projeto, sujo,
histórico, rascunho, recentes, pontos de verificação (criar/comparar/restaurar) e as
operações de nível livro — sem janela.

### Contexto para começar do zero

Ler: spec §4 (DEC-01, DEC-04, DEC-08), §5 (`Livro`, `Recurso.texto_cru`, `Capitulo.
texto_cru`, `OrigemDoLivro`), §7.6, §9 (Checkpoints), §9.5, §10.1, §10.6.1;
`core/exportar.py:600-810`; `core/services/document_service.py:30-90`; `config/settings.py`.

### Entregas

- `core/editor/epub.py`: `ler(caminho) -> (Livro, RelatorioDeConversao)` (container →
  OPF → tudo; `Livro.opf/nav/ncx` e `href` tal como lidos; recursos sob demanda;
  `pybox:*` → `OrigemDoLivro`; `id` repetido entre capítulos aceito), `escrever(livro,
  caminho) -> RelatorioDeConversao` (atômico; `mimetype`; OPF/nav/NCX regenerados no
  mesmo caminho; `dcterms:modified`; capítulos por `xhtml.escrever` ou `texto_cru` após
  `bem_formado`; folhas por `Recurso.texto_cru` ou `dados`; `<link>` relativo;
  diagramas `png` por `render_diagrama.desenhar` com cache por hash; `pybox:*`),
  `validar_estrutura`, `novo_livro(titulo, autor, idioma)`.
- `core/editor/livro_ops.py`: `renomear`, `renomear_varios(padrao)`, `excluir`
  (devolve quem apontava), `mover`, `anexar`, `dividir(livro, href, i_bloco) -> str`
  e `juntar(livro, href)` (chamam o modelo e reescrevem espinha, sumário, marcos, links
  `arquivo#id`, folhas), `juntar_por_titulo(livro, nivel)` (sintetiza `MarcaDePagina(n)`
  do `<title>`/nome `pagina-NNNN` na fronteira), `dividir_por_titulo`,
  `dividir_nos_marcadores`, `ordenar`, `vincular_folhas`, `adicionar_copia`.
- `core/editor/projeto.py`: `Projeto` (livro, caminho, sujo, `historico`, `salvar`,
  `salvar_como`, `reverter`, `fechar`, `checkpoint()`, `diferenca(cp)`, `restaurar(cp)`),
  `Rascunho(gravador, relogio)` com `tique()`, `Recentes`.
- Testes: `tests/test_editor_epub.py`, `_projeto.py`, `_livro_ops.py`.

### Critérios de aceite

- **AC-ED01-1** `escrever(ler(e))` do EPUB de `para_epub`: mesmos capítulos, recursos
  (bytes iguais), metadados, **nomes de entrada** (OPF/nav no lugar); `epubcheck` limpo.
- **AC-ED01-2** EPUB "de fora" (`content.opf`, CSS com `@media`, `<svg>`, `&nbsp;`, NCX
  sem nav, `refines`, duas folhas por capítulo, `id="title"` em dois capítulos): abre;
  `Capitulo.folhas` na ordem; o que não é dialeto sobrevive byte a byte (entidade da
  ilha numérica).
- **AC-ED01-3** `mimetype` primeiro, `ZIP_STORED`; XHTML UTF-8 sem BOM (AC-007).
- **AC-ED01-4** `Capitulo(texto_cru="<p>aberto")` e `Recurso(texto_cru="p{")`: salvar
  recusa (`ErroDeXhtml`; para CSS, aviso e grava — CSS não é XML) e o hash do arquivo
  não muda no caso do XHTML.
- **AC-ED01-5** Rascunho a 61 s (relógio injetado) → arquivo; restaura texto e recurso
  colado; `salvar` apaga; livro sem caminho em `data_dir()/rascunhos/`.
- **AC-ED01-6** Recentes: onze → dez; apagado some.
- **AC-ED01-7** Exceção injetada em `escrever` deixa o original intacto.
- **AC-ED01-8** `reverter` volta ao disco e limpa sujo; `checkpoint()` cria a cópia,
  `diferenca` lista o capítulo alterado, `restaurar` devolve o livro do checkpoint.
- **AC-ED01-9** `renomear` reescreve links, sumário, marcos, manifesto; `renomear_varios
  ("cap-%03d")` renumera três; `excluir` devolve `["Text/cap-0002.xhtml#x"]`; `anexar`
  renomeia colisões e reescreve os links do anexado.
- **AC-ED01-10** `dividir` no meio de um capítulo com uma nota antes e outra depois:
  dois capítulos, cada um com a sua nota, sumário e links `arquivo#id` atualizados;
  `juntar` devolve o original (ids preservados); `juntar_por_titulo` de 12 "páginas" com
  3 `<h1>` → 3 capítulos com 12 `MarcaDePagina`; `dividir_nos_marcadores` parte em três.

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_epub.py tests/test_editor_projeto.py tests/test_editor_livro_ops.py -q -p no:cacheprovider -o addopts=""
```

### Registro — 2026-09-19 — IMPLEMENTADA

Entregue em `core/editor/{epub,livro_ops,projeto}.py`, `tests/editor_livros.py` (os três
livros de prova: o EPUB de hoje, um "de fora" à moda do Sigil/Calibre e um modelo à mão)
e `tests/test_editor_{epub,livro_ops,projeto}.py` (31 testes; o `epubcheck` roda em três
deles quando há Java). Medido: o EPUB de `exportar.para_epub` nos dois modos volta ao
disco com **as mesmas entradas**, os recursos byte a byte, os capítulos `igual` e o
`epubcheck` a zero; o "de fora" idem — `refines`, `calibre:*`, `linear="no"`, NCX sem
nav, `<svg>` com `&nbsp;`, `id="title"` em dois capítulos, arquivo fora do manifesto,
`META-INF/*`, tudo de volta.

**O que divergiu da spec, e por quê:**

- **`Diagrama.imagem` / `imagem_chave`** (campos novos): o EPUB de hoje volta com o PNG
  já desenhado (`imagens/fig-0001-1.png`), e regravar sem mexer no diagrama **reutiliza**
  a imagem em vez de redesenhar — redesenhar trocaria em silêncio a orientação que o
  EPUB de hoje não registra (DEC-06) e custaria segundos por gravação. A chave
  (`dialeto.chave_do_diagrama`) guardada na leitura é o que diz se o diagrama ainda é o
  da imagem; mudou (orientação, lado, fonte…), o PNG canônico `diag-<chave>.png` é
  desenhado na pasta de imagens do livro (`epub.pasta_de_imagens`), com cache por chave.
  O leitor só preenche `imagem` quando o nome **não** é o canônico, para a R2 da ED-00
  continuar fechando.
- **`width` em pontos no `<img>` do diagrama em imagem** (`xhtml.largura_do_png_pt`,
  `render_diagrama.largura_em_casas`): o EPUB de hoje o tinha (F97) e o leitor da ED-00
  o descartava — sem ele o PNG de 528 px sairia em tamanho natural. A conta é fechada
  no caminho da caneta e medida uma vez por fonte/moldura/cantos no da grade.
- **`Capitulo.linear`**, **`Livro.nav_na_espinha`**, **`Recurso.no_manifesto`**,
  **`Pessoa.id`**, **`Metadados.ids`/`prefixos`**, **`Livro.zip_de_origem`**: o que
  "preservar a disposição" exige de fato — `linear="no"` da capa e das notas, o nav que o
  Sigil põe na espinha, o `META-INF/com.apple.ibooks.display-options.xml` e a sobra fora
  do manifesto, os `id` que os `refines` dos extras apontam, o `prefix` do `<package>`, e
  de onde ler o `Recurso.dados is None`. `Metadados.extras` ficou `(elemento, atributos,
  texto)` na letra do OPF — é o que faz um `title-type` ou um `calibre:series` voltar
  sem o modelo saber o que são.
- **`FormatoDePagina.hifenizar`** (a spec v1.3 já o tinha; faltava no modelo) e a
  **persistência de `Livro.pagina`** como `pybox:pagina` (JSON) ao lado dos `pybox:*` da
  origem, só quando difere do padrão — sem isso o formato escolhido para o DOCX se
  perdia ao reabrir o EPUB.
- **`epub.descarregar`**: a gravação carrega todo recurso para copiá-lo; `Projeto.salvar`
  solta de novo os que estão no zip recém-gravado, senão o rascunho de 60 s levaria
  400 imagens em base64.
- **`href` codificado como URL** ao escrever (`xhtml`, `sumario`) e decodificado ao ler:
  `Text/cap%201.xhtml` no OPF é o arquivo `cap 1.xhtml` do zip, e o modelo guarda o nome
  do arquivo. Sem isso o link do EPUB de fora apontava para capítulo inexistente.
- **`noteref` para nota noutro arquivo é ilha** (correção no leitor da ED-00): virava
  `Trecho.nota` com um id que não existe no capítulo e saía `href="#notas.xhtml#n1"`
  (o `epubcheck` pegou). Só o `href="#id"` do próprio capítulo é `Trecho.nota` (DEC-02).
- **Metadados de acessibilidade e `ibooks:specified-fonts` não são carregados** do OPF
  lido: são recalculados a cada gravação (§10.1). O `schema:` **não** é declarado no
  `prefix` (é reservado no EPUB 3.3; o `epubcheck` avisa quando se redeclara).
- **`juntar_por_titulo`** primeiro parte cada página no título que não a abre (senão a
  prosa antes do `<h1>` iria para o capítulo errado), depois junta; a `MarcaDePagina`
  sintetizada vem do `<title>` "Página N" ou do nome `pagina-NNNN`, e o `titulo` "Página
  N" do capítulo resultante é apagado para o `titulo_efetivo` ser o do `<h1>`.
- **`excluir`** devolve, além do `arquivo#id` de quem apontava, `sumário: rótulo`,
  `marco: tipo` e `capa` — e limpa esses três, porque um nav que aponta para nada é EPUB
  inválido; o `Trecho.link` fica (INV-02).
- **O checkpoint de livro sem caminho** vai para `data_dir()/rascunhos/<uuid>.checkpoints/`
  (a spec só previa `<livro>.checkpoints/`).
- `ErroDeXhtml` de um `texto_cru` mal-formado ao salvar traz o **arquivo** na mensagem.

---

## ED-02 — A janela: abas, menus, atalhos, resultados, caixa de conclusão e integração com o HEAD

**Prioridade:** P0 · **Dependências:** ED-01, ED-03, ED-07 · **Paralelizável com:** ED-09b
**Resultado:** a `JanelaDoEditor` com painéis, abas, todos os menus da §7.3 (o que não
existe, desabilitado com a fase na barra de status), todos os atalhos da §7.4 na bindtag
certa, barra de status, Mensagens com o logger, painel Resultados genérico,
`DialogoDeConclusão`, e as três portas de entrada — a da principal só no que está no HEAD.

### Contexto para começar do zero

Ler: spec §7, §13.2, §13.3, §13.4, §14; `ui/main_window.py` (`_build_menu` — procurar
`menubar = tk.Menu` —, `exportar_livro_action` e o seu `concluir`); `appy.py`;
`ui/editor/texto_rico.py` (ED-03) e `ui/editor/codigo.py` (ED-07): ambos expõem
`carregar`, `sincronizar`, `sujo`, `foco()`, `posicao()`, `comandos`, `<<Mudou>>`,
`<<CursorMoveu>>`; `tests/test_f35_atalhos.py`.

### Entregas

- `ui/editor/atalhos.py`: tabela da §7.4 `(atalho, keysym_ou_keycode, comando, modos,
  rótulo)`; `ligar(widget, tabela, comandos)` na bindtag `EditorAtalhos` com `"break"`,
  eventos virtuais para a área de transferência, neutralização de `<Key-Insert>` e
  `<<PasteSelection>>`, `<Key-App>`/`<Key-Menu>`/`<Shift-F10>`; `verificar_unicidade`;
  `texto_de_ajuda`.
- `ui/editor/menus.py`: tabela declarativa por fase com `alias_de`; mnemônicos da §7.3;
  `montar(janela, comandos) -> (tk.Menu, mapa (menu, item) → nome)`; `<<MenuSelect>>` →
  barra de status com a fase do item desabilitado; menu de contexto.
- `ui/editor/janela.py`: `JanelaDoEditor(parent, projeto=None, task_controller=None,
  documento_editorial=None)`: painéis, calha, status, `comandos`, `registrar_comandos`,
  `abrir`, `novo`, `novo_de_modelo`, `salvar`, `salvar_como`, `reverter`, `fechar_aba`,
  `fechar`, `alternar_modo`, `ir_para_capitulo`, `capitulo_seguinte/anterior`,
  `painel_seguinte/anterior`, `foco_no_editor`, `tela_cheia`, `quebra_automatica`,
  `exportar` (caixa de formato; os formatos entram nas fases), layout em
  `Settings.get("editor")`, guarda ao fechar (também no `parent`), `TaskController`
  próprio, `Rascunho.tique` por `after`, logger → Mensagens, erros em duas camadas,
  `AnelDeFoco` para `ttk`.
- `ui/editor/abas.py`, `ui/editor/barra.py` (arquivo, formatação, e a **barra de
  xadrez vazia**, preenchida na ED-05), `ui/editor/resultados.py` (lista clicável
  genérica: arquivo, bloco/linha, mensagem, callback), `ui/dialogo_de_conclusao.py`.
- Integração (só HEAD, `git add -p`): `_build_menu` ganha "Arquivo → Editor de livro…";
  `self.editor`; o `concluir` de `exportar_livro_action` passa a `DialogoDeConclusao`
  com "Abrir no editor" quando o formato foi EPUB; `appy.py`: `from ui.main_window import
  MainWindow` desce para `main()`; `--editor [arquivo] [--fechar-apos N]
  [--diagnostico-modulos]`.
- Testes: `tests/test_editor_janela.py`, `_atalhos.py`, `_menus.py`, `_resultados.py`,
  `tests/test_dialogo_de_conclusao.py`.

### Critérios de aceite

- **AC-ED02-1** Para cada linha da §7.4 que não é nativa nem contextual há item de
  menu; o teste troca `comandos[nome]` por um espião, chama `menu.invoke(i)` pelo mapa e
  confere; `verificar_unicidade` passa; "Ajuda → Atalhos" lista todas (inclusive
  `Ctrl+Tab` nativo e `Enter` contextual).
- **AC-ED02-2** Todo item da §7.3 existe com `underline`; mnemônicos da §7.3; nenhum em
  `{K,Q,R,B,N,P,D,T,C}`; repetidos são `alias_de`; item desabilitado escreve a fase na
  barra de status ao `<<MenuSelect>>`.
- **AC-ED02-3** (`gui`, `deiconify`+`focus_force`) sobre "abc" no `TextoRico` e no
  `EditorDeCodigo`: `Ctrl+D, H, I, K, O, T, Space, Shift+Space, /, A, Tab, Next, Prior`,
  `Shift+Insert`, `Insert`: texto continua `"abc\n"`, `index("insert")` não muda, e o
  espião do comando do editor foi chamado onde há comando; `Ctrl+BackSpace` e
  `Ctrl+Delete` chamam o espião de `apagar_palavra` (e não o `backspace()` simples).
- **AC-ED02-4** Abrir o EPUB do AC-ED01-1: primeira aba em texto; `alternar_modo()` ida
  e volta sem mudar o canônico (AC-003, com `ObjetoGenerico` para os diagramas).
- **AC-ED02-5** `alternar_modo()` sobre tag aberta e sobre `epub:type` sem `xmlns`:
  fica em código; barra, Mensagens e Validação com linha/coluna; cursor na linha.
- **AC-ED02-6** Guarda ao fechar (resposta injetável), também via `WM_DELETE_WINDOW`
  do `parent`.
- **AC-ED02-7** `subprocess`: `appy.py --editor livro.epub --fechar-apos 1
  --diagnostico-modulos` imprime `sys.modules` sem `torch`, `easyocr`, `cv2`, `numpy`.
- **AC-ED02-8** `ValueError` de comando → caixa de entrada; `RuntimeError` → caixa de
  falha; janela viva.
- **AC-ED02-9** Layout persiste; esconder o painel focado devolve o foco (`gui`).
- **AC-ED02-10** `DialogoDeConclusao` lista as ações e o callback recebe o caminho;
  abrir/salvar geram INFO em Mensagens.
- **AC-ED02-11** `novo_de_modelo("Título", "Autor", "pt")` → `metadados.idioma == "pt"`
  e `Settings.get("editor")["idioma_ortografia"] == "pt"`.
- **AC-ED02-12** `AnelDeFoco`: um `ttk.Button` embrulhado mostra `highlightthickness == 2`
  no `<FocusIn>` e `0` no `<FocusOut>`; `painel_seguinte()` percorre a ordem lógica da
  §7.1 (`gui`).

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_janela.py tests/test_editor_atalhos.py tests/test_editor_menus.py tests/test_editor_resultados.py tests/test_dialogo_de_conclusao.py tests/test_f35_atalhos.py -q -p no:cacheprovider -o addopts=""
```

### Registro — 2026-09-21 — IMPLEMENTADA

Entregue em `ui/editor/{atalhos,menus,janela,abas,barra,resultados,mensagens,dialogos}.py`,
`ui/dialogo_de_conclusao.py`, `appy.py --editor`, a integração na janela principal
(`abrir_editor_de_livro`, "Arquivo → Editor de livro…", `DIALOGO_DE_CONCLUSAO` no fim de
"Exportar livro") e cinco arquivos de teste (30 testes, dois deles `gui`). Medido: a
janela se constrói em 0,09 s e abre o EPUB de hoje em 0,09 s; `appy.py --editor
livro.epub --fechar-apos 1 --diagnostico-modulos` imprime "nenhum" (sem torch, easyocr,
cv2, numpy, fitz, PIL, docx nem `ui.main_window`). Conferido na tela com o processo
DPI-aware: 1280×648 cabe na tela de 1360×768 a 125%, nos dois modos.

**O que divergiu da spec, e por quê:**

- **A bindtag da janela é `EditorJanela<caminho da toplevel>`**, e não `EditorAtalhos`:
  esse nome já é o do modo código (ED-07), e `bind_class` é global ao interpretador —
  duas janelas com a mesma bindtag despachariam para os comandos da última. A tabela da
  §7.4 ganhou um **escopo** por acorde: `janela` (arquivo, exibir, navegação, ajuda —
  entra na frente dos editores **e** na própria janela, para valer com o foco em
  qualquer painel), `editor` (recortar, colar, negrito… — só na frente dos editores,
  senão `Ctrl+V` numa caixa de busca colaria no capítulo) e `fundo` (`Esc` — só na
  janela, depois de o widget ter a sua vez: fecha a lista de sugestões antes de devolver
  o foco).
- **Acorde de outro modo devolve `"break"`**, não `None`: `Ctrl+Shift+Space` no código
  caía no `Ctrl+Space` do próprio widget (o Tk casa `<Control-space>` com o Shift a mais)
  e abria as sugestões. Um acorde, um comando por modo — só o que a tabela não conhece
  (o `<Control-Key>` genérico com outro dígito) segue para o widget. E `Ctrl+Tab`/
  `Ctrl+Shift+Tab` ("nativos") são tratados por `ligar` — `tk_focusNext`/`Prev` —,
  porque o `<Tab>` do texto rico casaria com eles e inseriria um tabulador.
- **`Ctrl+T` é `sumario_editar`** (Livro → Sumário → Editar…, ED-08) e **`F8` é
  `metadados`**, que a ED-02 entrega no mínimo (título, autor, idioma; a caixa completa,
  com capa, editora e coleção, é da ED-08). A §7.4 dizia só "sumário / metadados".
- **Três itens fora da §7.3**: "Exibir → Alternar modo" (o `F11` precisava de um item,
  AC-ED02-1; "Modo texto"/"Modo código" continuam) e "Editar → Ir ao alvo do link" /
  "Voltar do alvo" (o *Go to link/style, and back* da §9, que o menu de contexto do código
  usa — e toda ação de contexto tem item). O menu de contexto é montado da mesma tabela
  (`menus.CONTEXTO`).
- **`<<MenuSelect>>` numa entrada desabilitada**: o Tk não ativa entrada desabilitada
  (`activate` deixa a ativa em `none`), então a entrada sob o mouse vem de `index @y`.
- **`modos_do_comando`** (novo): um comando registrado só para um modo — `inserir_link`,
  `inserir_ancora`, `inserir_imagem`, `dividir_capitulo` e `ir_para` existem no código
  desde a ED-07; no texto chegam na ED-04/ED-06, e o item diz "no modo texto chega na
  ED-04". Os acordes consultam a mesma disponibilidade (`_Despacho`).
- **Espaço e hífens inseparáveis chegaram agora** (a §7.3 os punha na ED-06): são um
  `inserir` do editor ativo. O menu de contexto, os botões e os acordes passam todos por
  `executar(nome)`, e é ali que as duas camadas de erro moram (§13.3): `ValueError` →
  `Caixas.entrada`; o resto → `Caixas.falha` com o traceback dobrado e "Copiar".
  `Caixas` (`ui/editor/dialogos.py`) é o ponto de injeção único dos testes.
- **O modo código fica com a pilha de desfazer própria** (a decisão que a ED-07 deixou):
  é por operação de texto; a `Historico` do projeto é por bloco, e converter uma na outra
  a cada tecla não vale o que custa. O texto rico usa a `Historico` do projeto.
- **`EditorDeCodigo` ganhou `<<Mudou>>`, `<<CursorMoveu>>`** (o roadmap dizia que os dois
  editores os expunham; o código não os gerava) **e os três toggles** `numeros_de_linha`,
  `realce_da_linha`, `quebra_automatica` — os itens de Exibir que a §7.3 atribuía à ED-07.
- **`core/services/__init__.py` ficou preguiçoso**: importava `box_service`,
  `ocr_service` e `pdf_service` no topo, e `TaskController` trazia cv2, numpy e fitz
  para o editor (AC-ED02-7 reprovava). Os nomes do pacote continuam existindo, por
  `__getattr__`. As operações de arquivo desta fase são síncronas, com o cursor de espera;
  o `TaskController` próprio existe para as tarefas longas das fases seguintes (validar
  EPUB, exportar).
- **Mensagens de outra thread vão por fila esvaziada por `after`**: chamar `after` de
  outra thread fora do `mainloop` levanta "main thread is not in main loop" (era engolido
  em silêncio). Na thread da interface, o registro entra na hora.
- **O caderno de baixo é um painel só** ("Busca e mensagens"), e uma lateral sem painel
  visível some da janela e volta quando um reaparece; `insert` no fim de um
  `PanedWindow` vazio é erro no Tk — `_por_em` faz `add` nesse caso.
- **O painel Estilos exige um `TextoRico` na construção**: há um de reserva, escondido;
  a troca de aba aponta `texto_rico` para o editor ativo.
- **`nav.xhtml` e o NCX abrem só para leitura**, regenerados do modelo; o OPF não abre
  (ED-08). Qualquer recurso de texto (`tipo="recurso"`) edita em código e volta a
  `Recurso.texto_cru`; uma imagem avisa como se insere.
- **Salvar valida as abas de código antes de tocar o disco** (`xhtml.bem_formado`): o erro
  vai para Validação com o arquivo, linha e coluna, e o cursor vai à linha; a recusa é
  erro de entrada, não defeito.
- **Rascunho**: fechar a principal força a gravação **antes** da guarda; "não salvar"
  apaga o rascunho (quem descartou escolheu descartar); cancelar o deixa. Abrir um EPUB
  com rascunho pendente pergunta antes de ler o disco.
- **Exportar… nesta fase é só EPUB** — uma cópia, com `zip_de_origem` preservado como no
  checkpoint; os outros formatos da caixa dizem a fase (ED-10/ED-12).
- **A integração na principal** vai pelo atributo de classe `DIALOGO_DE_CONCLUSAO` (como
  `DIALOGO_DO_DIAGRAMA`), porque a caixa é modal e `tests/test_f26_livro.py` espera o
  desfecho por `showinfo`; o teste ganhou o dublê `_conclusao_fixa`. As hunks entraram
  no índice a partir do HEAD (`git hash-object -w` + `update-index`), com o trabalho
  não commitado da árvore fora do commit.

---

## ED-03 — Texto rico: o `tk.Text` que desenha o modelo e o devolve

**Prioridade:** P0 · **Dependências:** ED-00 · **Paralelizável com:** ED-01, ED-07, ED-09
**Resultado:** `TextoRico` com identidade por marca, tags-marcador + fonte derivada,
faixas protegidas pela API, registro de objetos com `ObjetoGenerico`, calha, formatação
de caractere e parágrafo, estilos, listas, caixa, pincel, Fonte…, invisíveis, zoom,
largura, histórico — e o primeiro `scripts/medir_editor.py`.

### Contexto para começar do zero

Ler: spec §4 (DEC-03 inteira, DEC-04, DEC-11), §5, §6.3, §6.4, §8.1–§8.5, §8.15, §13.1,
§13.2, §14; `core/editor/modelo.py`, `dialeto.py`, `css_minima.py`, `historico.py`
(ED-00); `tk.Text` (`tag_configure`, `dump`, `mark_set`/`mark_gravity`, `image_create`,
`window_create`, `bindtags`, `count -displaylines`, `dlineinfo`).

### Entregas

- `ui/editor/tags.py`: marcadores (`b`, `i`, `vers`, `sobre`, `sub`, `fam:`, `corpo:`),
  independentes (`u`, `s`, `cor:`, `fundo:`, `cls:`, `lang:`, `link:`, `ref:`, `nota:`,
  `papel:`, `nag:`, `code`, `quebra`, `pagina:`), derivada `fonte:*` (cache de
  `tkfont.Font`), de parágrafo (`p:`, `h1`…, `al:`, `rec1:`, `recE:`, `recD:`, `antes:`,
  `depois:`, `entre:`, `manter`, `manterl`), de lista (`li:`), de tela (`protegido`,
  `invisivel`, `orto`, `notacao-ilegal`, `suspeito`, `sel-objeto`); `configurar`.
- `ui/editor/dump.py`: `dump_para_blocos(itens, registro, anteriores) -> (blocos, notas)`
  (pura), `indice_de(itens, bloco_id, deslocamento)`.
- `ui/editor/objetos.py`: `RegistroDeObjetos`, `ObjetoGenerico`,
  `TextoRico.inserir_objeto(bloco_ou_trecho, imagem=None, widget=None)`.
- `ui/editor/calha.py`: `Calha` (`Canvas` alinhado por `dlineinfo`; ícones por bloco).
- `ui/editor/texto_rico.py`: `TextoRico(master, estilo_de_tela, folhas, historico)`:
  `carregar(capitulo)`, `carregar_blocos(blocos)`, `sincronizar() -> Capitulo | list`,
  `inserir(texto, indice=None)`, `apagar(ini, fim)`, `apagar_selecao()`, `enter()`,
  `backspace()`, `selecionar(ini, fim)`, `alternar(atributo)`, `aplicar(**attrs)`,
  `paragrafo(**props)`, `estilo(nome)`, `estilo_de_caractere(nome)`, `lista(ordenada)`,
  `nivel(±1)`, `limpar_caractere()`, `limpar_paragrafo()`, `mudar_caixa(modo)`,
  `pincel_copiar()/pincel_aplicar()`, `aumentar_fonte()/diminuir_fonte()`,
  `estilo_no_cursor()`, `zoom(f)`, `invisiveis(b)`, `largura_de_leitura(m)`,
  `apagar_palavra(direcao)` (`Ctrl+BackSpace`/`Ctrl+Delete`, pela guarda),
  `selecionar_paragrafo()`, `selecionar_bloco()`, `ponto()`, `desfazer()`, `refazer()`,
  `sujo`, `foco()`, `posicao()`, `comandos`, `<<Mudou>>`, `<<CursorMoveu>>`; `undo=False`;
  bindtag; `_pode_editar`; marcas; reaplicação no `<<Modified>>`; `highlightthickness=2`.
- `ui/editor/estilos.py` (painel), `ui/editor/fonte.py` (`DialogoDeFonte`).
- `scripts/medir_editor.py` (v1: `carregar`, `sincronizar`, `dump`, latência de tecla
  simulada) + `tests/test_editor_desempenho.py` (`slow`).
- Testes: `tests/test_editor_dump.py`, `_tags.py`, `_texto_rico.py`, `_estilos.py`,
  `_fonte.py`.

### Critérios de aceite

- **AC-ED03-1** 100 capítulos gerados (com listas, citações, quebras suaves; sem objetos):
  `carregar` + `sincronizar` → `igual`, ids preservados.
- **AC-ED03-2** `selecionar(1, 4)` em "xabcx" + `alternar("negrito")` → `abc` negrito;
  de novo → sem; "a**b**c" + seleção "abc" → tudo negrito; num `p.comentario` (itálico
  por CSS), `alternar("italico")` **liga** o marcador `i` (não o desliga por XOR).
- **AC-ED03-3** Sem seleção, `alternar("italico")` + `inserir("xyz")` → itálico
  pendente aplicado; mover o cursor cancela; negrito+itálico desenha `fonte:*` `bold
  italic`; `dump` não devolve `fonte:*`.
- **AC-ED03-4** `estilo("titulo2")` → `Titulo(2)` persistente; `estilo("corpo")` volta;
  `mudar_caixa("alternar")` "aBc" → "AbC"; `aumentar_fonte()` sobe um passo;
  `DialogoDeFonte` devolve os atributos escolhidos (variáveis injetadas).
- **AC-ED03-5** `lista(False)`, `inserir("um")`, `enter()`, `inserir("dois")`,
  `nivel(+1)` → item aninhado (o `\n` interno é `quebra+protegido`); `enter()` em item
  vazio sai; `backspace()` no início diminui nível; marcador não sai no `dump`.
- **AC-ED03-6** `paragrafo(alinhamento="centro")` sobre três parágrafos muda os três;
  a folha `p.comentario { font-style: italic; color: #444 }` faz `fonte:*` itálica e
  `cor` cinza (`tag_cget`).
- **AC-ED03-7** Dez operações desfeitas uma a uma → capítulo inicial; refazer → final.
- **AC-ED03-8** `apagar()` que toca o marcador é recusado (texto igual); `inserir()`
  dentro de uma ilha inline é recusado; `apagar_selecao()` com o objeto selecionado
  apaga com desfazer; `ObjetoGenerico` de um `Diagrama` atravessa o `dump` intacto.
- **AC-ED03-9** `invisiveis(True)` insere `¶`/`→`/`⏎`/`°` protegidos; `sincronizar`
  não os devolve; `indice_de(itens, id, 5)` aponta o 6º caractere do modelo; `zoom(1.5)`
  só muda o estilo de tela.
- **AC-ED03-10** Pincel e `limpar_caractere()` (mantém `link`/`nota`/`ref`).
- **AC-ED03-11** Painel Estilos: novo estilo `destaque` grava `p.destaque {…}` na folha
  padrão (`Recurso.texto_cru` ou `dados`), o painel lista, "selecionar tudo com este
  estilo" seleciona 3.
- **AC-ED03-12** Foco visível em todo widget novo; `Calha` desenha um `!` na linha do
  bloco marcado `suspeito`.
- **AC-ED03-13** `scripts/medir_editor.py` imprime `carregar`/`sincronizar`/`dump` de um
  capítulo de 20 páginas; o teste `slow` confere `dump ≤ 100 ms` e `carregar ≤ 300 ms`.

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_dump.py tests/test_editor_tags.py tests/test_editor_texto_rico.py tests/test_editor_estilos.py tests/test_editor_fonte.py -q -p no:cacheprovider -o addopts="" -m "not slow"
.venv/Scripts/python.exe -m pytest tests/test_editor_desempenho.py -q -p no:cacheprovider -o addopts="" -m slow
.venv/Scripts/python.exe scripts/medir_editor.py
```

### Registro — 2026-09-19 — IMPLEMENTADA

Entregue em `ui/editor/{tags,dump,objetos,calha,texto_rico,estilos,fonte}.py`,
`scripts/medir_editor.py` e seis arquivos de teste (25 testes + 1 `slow`). Medido num
capítulo gerado de 20 páginas (200 blocos): `carregar` 90 ms, `dump` (o capítulo
inteiro relido do widget) 46 ms, tecla 1,6 ms — dentro dos orçamentos da §13.1. A ida e
volta fecha em 100 capítulos gerados sem objetos (AC-1) e os com objetos e ilhas inline
voltam intactos pelo registro. Conferido na tela com o processo DPI-aware.

**O que divergiu da spec, e por quê:**

- **O `tk.Text` é observado pelo proxy do comando Tcl** (o mesmo da ED-07), não por
  `<<Modified>>`: é ele que diz **quais blocos** um `insert`/`delete` tocou (`_tocados`),
  e a reconciliação — tags de parágrafo cobrindo o bloco inteiro, fonte derivada
  recalculada, bloco relido pelo `dump`, ponto de desfazer — corre só neles. O
  `<<Modified>>` não diz onde foi.
- **`sincronizar()` devolve o modelo em cache** (`_modelo`, mantido a cada edição pela
  API) e só relê o que está pendente; `sincronizar(reler=True)` passa tudo pelo `dump`
  — é o que os testes de ida e volta e a medição usam. Sem o cache, o "dump" de 200
  blocos custava 480 ms; com ele, o que se paga é o da edição (1,6 ms por tecla).
- **O `dump` do Tk só relata `tagon` onde a tag começa**: uma tag que vem do bloco
  anterior (dois `p:titulo4` seguidos) não aparece no intervalo do segundo. `_dump`
  do widget semeia os `tag_names` do início do intervalo — sem isso o título virava
  parágrafo na releitura.
- **`mark previous` começa antes do índice**: `_bloco_em` consulta `index+1c` para
  incluir a marca que está exatamente no índice (senão o objeto no começo do bloco
  seguinte era atribuído ao anterior, e apagar um diagrama selecionado falhava).
- **Desenhar no meio do texto usa uma marca provisória de gravidade `right`**
  (`fim_ins`): inserir numa marca de gravidade `left` deixa a marca do bloco seguinte
  presa no começo do texto novo; a marca provisória aponta o fim do que entrou, e a do
  seguinte é reposta ali.
- **Parágrafos internos** (itens de lista, parágrafos de citação) levam tags próprias:
  a formatação direta (`al:`, `rec1:`…), `pid:<id>` quando o id é persistente,
  `pcls:<classe>` e `pex:<base64 de JSON>` com `extras` e `origem` — sem elas a
  releitura perdia o que não estava em tag. A lista aninhada leva `sub:<o|n>|<marcador>|
  <início>` no item, porque `Lista.filhos` tem tipo, marcador e início próprios.
- **`modelo._fundem` compara tuplas**, não `formato()` via `para_dict`: a normalização
  de trechos roda em toda releitura, sobre milhares de trechos (era metade do tempo do
  `dump`). Mudança na ED-00, sem efeito no resultado.
- **`mudar_caixa` recebe uma cópia**: `modelo.mudar_caixa` muda o parágrafo no lugar, e
  o "antes" do ponto de desfazer é o objeto em cache.
- **Apagar tudo deixa um parágrafo vazio** (`_garantir_um_bloco`): um capítulo nunca fica
  sem bloco nem com texto órfão fora de marca.
- **Enter no fim de um título abre `corpo`** (o Word faz igual); enter em item vazio
  sai da lista — o item com conteúdo que sai (`BackSpace` no nível 1) vira parágrafo com
  o seu texto, não um parágrafo vazio.
- **`ir_para` desfaz a seleção**: `alternar` e `aplicar` a repõem (o Word mantém), e um
  `enter()` depois de mover o cursor apagava a seleção velha.
- **`markers` do pytest**: o `slow` desta fase só valeu porque a ED-07 os pôs no
  `pytest.ini` (o `pyproject.toml` é ignorado).

---

## ED-04 — Objetos no modo texto: figuras, tabelas, notas, links, quebras, ilhas, colar, propriedades, dividir/juntar

**Prioridade:** P0 · **Dependências:** ED-02 · **Paralelizável com:** ED-06, ED-10
**Resultado:** §8.6–§8.11 e o painel Propriedades com "Aplicar".

### Contexto para começar do zero

Ler: spec §8.6–§8.11, §5 (`Figura`, `Tabela`, `Nota`, `Trecho.nota`, `QuebraDePagina`,
`MarcaDePagina`, `Trecho.pagina`, `IlhaBruta`, `Trecho.ilha`, `quebra_antes`), §6.1,
§7.4 (objeto, tabela, `Enter`, `Alt+Enter`); `ui/editor/texto_rico.py`, `objetos.py`
(ED-03); `core/editor/xhtml.py` (`ler_fragmento`); `core/editor/livro_ops.py` (ED-01).

### Entregas

- `ui/editor/objetos.py`: `ObjetoDeFigura`, `ObjetoDeIlha` (+ mini-editor modal),
  `ObjetoDeIlhaInline` (glifo reservado + dica; fragmento no registro),
  `ObjetoDeQuebra` ("— quebra de página —"), `ObjetoDeMarcaDePagina` ("— página n —"),
  `ObjetoDeSeparador`.
- `ui/editor/tabela.py`: `GradeDeTabela` (§8.6; `proxima_celula()`, `sair()`,
  `entrar()`, limite 400).
- `ui/editor/propriedades.py`: painel com "Aplicar"; `Alt+Enter`; `Enter` = ação
  principal.
- Notas (§8.8): `Trecho.nota`, rodapé e fim, faixa de notas com marcas `nota:<id>`,
  `renumerar_notas`, `Enter`→nota/`Esc`→volta.
- Links, âncoras, "Seguir link" (§8.9); quebras suave/de página, marca de página
  (§8.10); "Dividir capítulo aqui"/"Juntar com o anterior" via `livro_ops`.
- `core/editor/area_de_transferencia.py: AreaDeTransferencia(ler_sistema,
  gravar_sistema, ler_imagem)`; colar texto / XHTML / imagem; `Ctrl+Shift+V`.
- "Inserir → Ilha de XHTML…", "Imagem…", "Tabela…"; seção ED-04 em `menus.py`.
- Testes: `tests/test_editor_objetos.py`, `_tabela.py`, `_propriedades.py`,
  `_area_de_transferencia.py`.

### Critérios de aceite

- **AC-ED04-1** PNG 40×30 gerado em `tmp_path` → `Figura` em `Images/`, alt vazio
  avisado, largura por "Aplicar"; salvar/reabrir mantém.
- **AC-ED04-2** Tabela 3×3 por `proxima_celula()`; inserir linha; cabeçalho; excluir
  coluna → retangular; `sair()` devolve o foco; `entrar()` vai à primeira célula;
  `colspan` vira ilha; 20×20 carrega (tempo no `medir_editor.py`).
- **AC-ED04-3** Duas notas de rodapé, apagar a primeira → `¹` renumerado e `aside` com
  o `id`; nota de fim sai em `section[epub:type=endnotes] > ol > li[epub:type=endnote]`;
  `sincronizar()` devolve blocos **e** notas editadas na faixa.
- **AC-ED04-4** Link `arquivo#id`: `seguir_link()` troca de aba e leva ao bloco;
  inexistente em vermelho no painel e no relatório.
- **AC-ED04-5** Ilha `<svg>` e ilha inline `<cite>` atravessam carregar/editar ao
  redor/`sincronizar` byte a byte; `apagar_selecao()` apaga com desfazer.
- **AC-ED04-6** Dividir e juntar pela janela chamam `livro_ops` (espião) e recarregam
  abas e sumário.
- **AC-ED04-7** Colar interno preserva negrito, figura e ilha; "Copiar" deixa só texto
  plano no `gravar_sistema`; texto de fora → parágrafos; imagem → recurso;
  `inserir_quebra_suave()` → `quebra_antes`; `inserir_quebra_de_pagina()` →
  `QuebraDePagina`; uma `MarcaDePagina` desenha "— página n —" e `juntar_paragrafos`
  através dela produz `Trecho.pagina`.
- **AC-ED04-8** Painel só grava em "Aplicar"; foco visível nos widgets novos.

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_objetos.py tests/test_editor_tabela.py tests/test_editor_propriedades.py tests/test_editor_area_de_transferencia.py -q -p no:cacheprovider -o addopts=""
.venv/Scripts/python.exe -m pytest tests/test_editor_desempenho.py -q -p no:cacheprovider -o addopts="" -m slow
.venv/Scripts/python.exe scripts/medir_editor.py
```

### Registro — 2026-09-21 — IMPLEMENTADA

Entregue em `core/editor/area_de_transferencia.py`, `ui/editor/{objetos,tabela,propriedades,proxy}.py`,
as mudanças em `ui/editor/{texto_rico,dump,tags,menus,dialogos,janela,codigo}.py`, o
`scripts/medir_editor.py` com a tabela e cinco arquivos de teste (31 testes + 1 `slow` +
1 `gui`; `tests/editor_ambiente.py` é o ambiente partilhado). Medido: a tabela de 20×20
carrega como grade em ~600 ms, o `dump` dela custa 2 ms, uma tecla numa célula 1,3 ms e o
ponto de desfazer da tabela inteira ~60 ms (adiado). Conferido na tela com o processo
DPI-aware: a grade com o cabeçalho sombreado e a célula focada, a figura com a legenda, a
caixa do SVG, "— página n —", "— quebra de página —", a faixa "Notas" e o painel.

**O que divergiu da spec, e por quê:**

- **Dois defeitos latentes das fases anteriores, consertados aqui porque a ED-04 os
  expôs.** (1) A bindtag de classe dos dois editores (`EditorAtalhosTexto`, `EditorAtalhos`)
  era ligada com closures sobre `self` — `bind_class` é global ao interpretador, e toda
  tecla ia para o **último** widget criado (duas abas, ou uma célula de tabela, e a
  digitação saía no lugar errado). Agora a classe é ligada uma vez e o handler despacha
  pelo `evento.widget` (`_INSTANCIAS`), nos dois editores. (2) O proxy do comando Tcl era
  um comando Python: um erro Tcl dentro dele (`index sel.first` sem seleção, que `selecao()`
  provoca e captura) deixa o `_tkinter` com a exceção pendente e o **`mainloop` morre** na
  volta do evento — o subprocesso da AC-ED02-7 caiu assim que o painel Propriedades leu a
  seleção. O proxy virou um `proc` Tcl (`ui/editor/proxy.py`) com ganchos Python `antes`/
  `depois` que engolem as próprias exceções; vale para o texto rico e para o código.
- **A faixa de notas são blocos comuns.** Os parágrafos de cada nota entram na `_ordem`
  depois do marco `FaixaDeNotas` (um objeto "Notas", `dump.ID_DA_FAIXA`), com a tag de
  parágrafo `dn:<id>|<tipo>` e o número como marcador protegido no primeiro; o `dump` os
  agrupa em `Nota`. O ponto de desfazer de uma edição na nota é sobre a **nota inteira**
  (`Ponto.ids` traz o id da nota; `historico.aplicar` já sabia de notas). A ordem das
  notas só é refeita (`renumerar_notas`) em edições — inserir, apagar, colar, mudar o tipo
  —, nunca ao carregar, porque a ida e volta dos 100 capítulos gerados manda. Apagar a
  última referência de uma nota (`BackSpace` seleciona, o segundo apaga) leva a nota; uma
  nota cujos parágrafos foram todos apagados fica com um vazio. `Ctrl+A` pára antes da faixa.
- **A célula de tabela é um `TextoRico(celula=True)`** com `dono`, sem calha nem barra,
  com as tags fixas configuradas sob demanda (`tags.configurar(..., preguicoso=True)`) — 400
  células pagariam 8.000 `tag configure`. O registro pergunta à grade o modelo atual
  (`RegistroDeObjetos.registrar(..., atualizar=grade.modelo)`); uma tecla numa célula
  reconcila o texto de fora com atraso (`ATRASO_DA_CELULA_MS`, 250 ms), porque reler e
  copiar uma tabela de 400 células a cada tecla custava 60 ms. `Text.count -displaylines`
  só vale com o widget mapeado (sem tela conta um caractere por linha): sem tela é
  `-lines`, e a grade refaz as alturas no `<Map>`/`<Configure>`. `celula_atual()` vale
  sem foco de verdade (o teste corre numa janela `withdraw`n).
- **`inserir_bloco_no_cursor` ao lado de `inserir_objeto`**: a quebra de página, o separador
  e a tabela do menu partem o parágrafo no cursor (no começo, entram antes; no fim, depois);
  `inserir_objeto` continua a entrar **depois** do bloco do cursor (o contrato da ED-03).
  `Enter` **sobre** um objeto (o cursor antes da janela) é a ação principal; depois dela
  (no `\n`) abre um parágrafo — é o único jeito de escrever depois de uma figura no fim.
- **Colar**: `Fragmento` leva as notas referenciadas (`notas`), que nascem de novo com id
  novo ao colar (o Word faz igual); o primeiro e o último parágrafos colados fundem-se com
  as metades do parágrafo do cursor, os do meio entram inteiros; `blocos_do_xhtml` lê o
  miolo do `body` que `consertar` embrulha (e um documento inteiro colado é lido como
  capítulo). O `ler_imagem` da janela é o `ImageGrab` do PIL, importado só ali.
- **Propriedades**: `TextoRico.alvo_das_propriedades()`/`aplicar_propriedades()` são a API;
  o painel só grava em "Aplicar" e só remonta quando o alvo (tipo, id) muda, para não
  apagar o que se está a digitar. `_reescrever_bloco` passou a guardar o "antes" à parte
  (`_antes_forcado`): a base do `dump` era o modelo antigo, e classe, `id_persistente` e
  extras aplicados perdiam-se; e mantém o cursor onde estava (redesenhar o bloco o
  empurrava para o seguinte). Um id de âncora aceita letras fora do ASCII.
- **`seguir_link` quebrado** fica vermelho no painel, entra em Resultados (com bloco e
  deslocamento) e é erro de entrada; `destino_existe` conhece âncoras, notas e recursos.
- **`delete(x, "end")` do Tk come o `\n` da linha anterior** quando `x` é cabeça de linha:
  a faixa redesenhada colava "Notas" no fim do último parágrafo — apaga-se até `end-1c`.
- **Fora da §7.3**: "Formatar → Editar ilha de XHTML…" (a ação principal da ilha precisa
  de item, como toda ação de contexto) e "Formatar → Apagar nota"; o submenu Tabela tem
  oito itens; o contexto do texto ganhou "Seguir link", "Editar ilha" e "Colar como XHTML".
  `Caixas` ganhou `abrir_imagem`, `ilha` (o mini-editor) e `tabela`.
- **A tag `objeto` deixou de pintar fundo**: com `justify=center`, o Tk pintava a faixa
  cinza da margem até a janela; cada desenho tem a sua cor.
- **`atualizar()` da janela sincroniza o painel Propriedades**: o `<<NotebookTabChanged>>`
  só chega no laço de eventos, e abrir uma aba que já existe também passa por
  `_trocou_de_aba`.

---

## ED-05 — Xadrez no editor

**Prioridade:** P0 · **Dependências:** ED-04 (e ED-pré só para `chess_symbols`, que a
paleta importa **se existir**) · **Paralelizável com:** ED-06b, ED-08
**Resultado:** §11.1–§11.7 (menos marcas/setas/legenda sugerida/chave — ED-05b): diagrama
com lado, editor de posição extraído com teclado, paleta, figurinas ao digitar,
segmentação de partidas, diagrama a partir dos lances com variantes, validação, marcar
lances/NAGs/jogador/abertura, numerar, referências, cabeçalho em legenda, fontes do
livro.

### Contexto para começar do zero

Ler: spec §4 (DEC-06, DEC-07), §5 (`Diagrama`, `Trecho.nag/chave/ref`), §6.1, §7.4,
§11.1–§11.7, §13.2; `ui/dialogo_diagrama.py`, `core/tabuleiro_edicao.py`, os três testes;
`ui/dialogo_do_diagrama.py`; `core/render_diagrama.py`; `core/nags.py`;
`core/chess_symbols.py`; `ui/main_window.py` (`NAGS_POR_FAMILIA`, `_build_menu_notacao`);
`ui/fontes.py`; `core/notacao.py`; `ui/pecas.py`.

### Entregas

- `core/nags.py: NAGS_POR_FAMILIA` (movido de `ui/main_window.py`, que o **reexporta**
  — `tests/test_nags.py` o importa de lá; `git add -p`).
- `core/diagrama_modelo.py` (`Casa`, `Leitura`, sem `cv2`; `core.diagrama` os reexporta)
  e `core/tabuleiro_edicao.py` com `from __future__ import annotations` +
  `TYPE_CHECKING` e `TabuleiroEdicao.de_fen(fen, lado="")` — é o que deixa o editor de
  posição abrir sem `cv2`.
- `ui/editor/tabuleiro.py: TabuleiroEditavel(master, tabuleiro, recorte=None,
  idioma="en", alto_contraste=False)` com o teclado da §11.2 (`mover_selecao`,
  `por_peca(letra, preta)`, `limpar_casa`, `girar`; anel de dois tons; cor por
  `event.state & 0x1`); `ui/dialogo_diagrama.py` passa a usá-lo.
- `render_diagrama.desenhar(..., lado_a_jogar=None, marcas=(), setas=())` (só o lado
  desenhado aqui).
- `ui/editor/diagrama.py`: `ObjetoDeDiagrama`, `DialogoDeDiagrama` (grupos; foco no FEN;
  lado brancas/pretas/desconhecido; recorte; legalidade como aviso).
- `ui/editor/paleta.py`: painel Xadrez e a barra de xadrez (figurinas brancas, os 23,
  `FAMILIAS`, e `chess_symbols` **quando importável**; código junto do símbolo; botões
  ≥ 24 px; setas/`Enter`/`Esc`).
- `core/editor/xadrez.py`: `tokens`, `segmentos(blocos)`, `posicao_apos(blocos, ate)
  -> (Board, lado_proposto, erro)`, `validar(blocos)`, `para_letras`,
  `figurina_ao_digitar`, `marcar_lances`, `marcar_nags`, `marcar_jogador_abertura`,
  `alt_de(diagrama, idioma)`, `legenda_de_lado`, `cabecalho_em_legenda(cap, i)`,
  `fonte_do_livro(livro, fonte)`, `fonte_dos_simbolos_do_livro(livro, familia)`.
- "Inserir → Referência…", "Xadrez → Numerar ▸" (`numerar_objetos`), seção ED-05 em
  `menus.py`.
- Testes: `tests/test_editor_xadrez.py`, `_diagrama.py`, `_tabuleiro.py`, `_paleta.py`.

### Critérios de aceite

- **AC-ED05-1** `comandos["inserir_diagrama"]()` com diálogo injetado (posição inicial,
  peão em e4, lado pretas) → `Diagrama` com FEN, `lado="b"`; salvar/reabrir mantém
  tudo; `data-lado="b"` no XHTML.
- **AC-ED05-2** `editar_posicao()`; `girar()`; coordenadas; `lado_indicador="marca"`
  desenha o quadradinho (pixel conferido); lado `""` → sem quadradinho e aviso.
- **AC-ED05-3** `posicao_apos` sobre "1.e4 e5 2.Nf3 (2.f4 exf4) Nc6 3.Bb5" → Ruy Lopez,
  lado proposto brancas; cursor após `exf4` → posição da variante; "3.Bb6" → erro em
  `Bb6`; um segundo `1.e4` após um `Titulo` começa outro segmento; um `Diagrama` cujo
  FEN difere re-sincroniza com o aviso "diagrama n não bate"; prosa em `corpo` com
  "Nf3" é ignorada.
- **AC-ED05-4** `validar` marca `Bb6` com sugestão `Bb5` (e um ilegal dentro de
  variante); o painel Resultados lista; o texto não muda; `tag_cget("notacao-ilegal",
  "bgstipple") == "gray25"` e o `✗` está na calha.
- **AC-ED05-5** `para_letras("1.♘f3 ♗b5 O-O e8=♕+", "figurinas", "pt")` == "1.Cf3 Bb5
  O-O e8=D+"; `figurina_ao_digitar` converte em `notacao`, não em `corpo`.
- **AC-ED05-6** Paleta: `⩲` → `papel="nag"`, `nag=14`, `familia="simbolos"` quando a
  fonte não desenha; `marcar_nags` marca `±` digitado e lista `=` como ambíguo.
- **AC-ED05-7** `numerar_objetos`; `ref` "Diagrama 12" → "13" após inserção; `marcar_
  jogador_abertura` sugere "Kasparov, Garry" de "Kasparov – Karpov"; `cabecalho_em_legenda`
  converte o `h2` em legenda do diagrama seguinte; `fonte_do_livro` troca `fonte` em
  todos.
- **AC-ED05-8** Teclado do tabuleiro: `mover_selecao` × 4 + `por_peca("q", False)` → dama
  em e1; `por_peca("q", True)` preta; `pt`: `por_peca("d", False)`; `limpar_casa()`;
  anel de dois tons presente nas duas paletas.
- **AC-ED05-9** Os três testes existentes verdes; AC-ED02-7 repetido (sem `cv2`).

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_xadrez.py tests/test_editor_diagrama.py tests/test_editor_tabuleiro.py tests/test_editor_paleta.py tests/test_f82_tabuleiro.py tests/test_f71_diagrama.py tests/test_f83_treino_diagrama.py tests/test_nags.py tests/test_editor_janela.py -q -p no:cacheprovider -o addopts=""
```

---

## ED-05b — Marcas, setas, legenda sugerida e chave de símbolos

**Prioridade:** P1 · **Dependências:** ED-05 · **Paralelizável com:** ED-11, ED-12

### Contexto para começar do zero

Ler: spec §11.1, §11.7, §11.10, §5 (`Diagrama.marcas/setas/aviso`); `core/render_diagrama.py:
desenhar`; `ui/editor/diagrama.py` e `core/editor/xadrez.py` (ED-05); `core/nags.py`.

### Entregas

`render_diagrama.desenhar` com marcas e setas; "Marcas e setas…"; `xadrez.legenda_sugerida`
("Diagrama 12: após 23…♖xe4 — Pretas jogam", lado inferido e **proposto**);
`xadrez.chave_de_simbolos(livro) -> Capitulo`; testes `tests/test_editor_xadrez_extras.py`.

### Critérios de aceite

- **AC-ED05b-1** `marcas=["e4"]`, `setas=[("g1","f3")]` → pixels no PNG; salvo/reaberto;
  em modo `fonte`, `Diagrama.aviso` diz "marcas e setas não saem em fonte".
- **AC-ED05b-2** Legenda sugerida certa, com o lado proposto e não gravado em `lado`.
- **AC-ED05b-3** Chave com `±`, `⩲`, `!?` (marcados e digitados), `epub:type="glossary"`.

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_xadrez_extras.py tests/test_editor_diagrama.py tests/test_f58_render_diagrama.py -q -p no:cacheprovider -o addopts=""
```

---

## ED-06 — Busca, substituição, ir para, ortografia, símbolos, contagem

**Prioridade:** P1 · **Dependências:** ED-02 · **Paralelizável com:** ED-04, ED-10

### Contexto para começar do zero

Ler: spec §8.12, §8.13, §8.15, §9.4, §13.2; `core/lexico.py`; `core/notacao.py:
e_token_de_notacao`; `ui/editor/resultados.py` (ED-02).

### Entregas

`core/editor/busca.py` (§8.12, com circular e "texto marcado"); `ui/editor/busca.py`;
`core/lexico.py: sugestoes`; `core/editor/ortografia.py` (+ `lang` do trecho);
`ui/editor/ortografia.py` (tag `orto`, contexto, `F7`, "Dicionário do livro…");
`ui/editor/simbolos.py` (+ `Ctrl+Shift+X`); `core/editor/estatisticas.py`; "Ir para…";
espaço/hífen inseparável e opcional; seção ED-06 em `menus.py`; testes
`tests/test_editor_busca.py`, `_ortografia.py`, `_estatisticas.py`, `_painel_busca.py`,
`_simbolos.py`, `tests/test_lexico_sugestoes.py`.

### Critérios de aceite

- **AC-ED06-1** "Nimzo**w**itsch" achado no adaptador de trechos e não no cru.
- **AC-ED06-2** Regex no livro inteiro: contagem por arquivo; capítulos não abertos;
  `historico.desfazer(cap)` × N restaura cada um; "circular" volta ao início.
- **AC-ED06-3** `sugestoes("knigt", lex)[0] == "knight"`; `verificar` acusa só `knigt`
  em "The knigt plays 12.Nf3 ♘c6 ±"; "Adicionar" grava em `livro.lexico.txt`; `F7` com
  respostas injetadas (Ignorar / Ignorar todas / Adicionar / Trocar) altera só o que
  deve; um trecho `lang="pt"` usa o léxico `pt` (vazio até a ED-06b → nada acusado).
- **AC-ED06-4** Ir para diagrama 7 / página 45 (`MarcaDePagina`) / linha 30.
- **AC-ED06-5** Contagem bate com o modelo.
- **AC-ED06-6** Caixa de símbolos: "BLACK CHESS" lista `♚♛♜♝♞♟`; `codigo_para_caractere
  ("2A72")` → `⩲`.
- **AC-ED06-7** NBSP grava U+00A0, invisíveis mostram `°`, busca com "espaço casa
  também o inseparável".
- **AC-ED06-8** AC-ED02-7 repetido (o `lexico` não trouxe `cv2` no topo).

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_busca.py tests/test_editor_ortografia.py tests/test_lexico_sugestoes.py tests/test_editor_estatisticas.py tests/test_editor_painel_busca.py tests/test_editor_simbolos.py -q -p no:cacheprovider -o addopts=""
```

### Registro — 2026-09-21 — IMPLEMENTADA

Entregue em `core/editor/{busca,ortografia,estatisticas,simbolos}.py`, `core/lexico.py:
sugestoes`, `ui/editor/{busca,ortografia,simbolos}.py`, as mudanças em
`ui/editor/{janela,menus,dialogos,codigo,texto_rico}.py` e seis arquivos de teste (44
testes). Conferido na tela com o processo DPI-aware: o painel Busca no caderno de baixo
(cabe na janela de 1280×648), a caixa do `F7` e a caixa de símbolos.

**O que divergiu da spec, e por quê:**

- **A busca do modo texto corre sobre `Alvo`s** (`busca.alvos_do_capitulo`): o parágrafo
  de cima, cada parágrafo interno de lista e de citação (com o **deslocamento** dentro do
  bloco, o número que `TextoRico.indice_de` entende), cada parágrafo de célula, a legenda
  de figura/tabela/diagrama e cada parágrafo de nota (que no widget é um bloco com o id
  do próprio parágrafo). Célula e legenda não são endereçáveis pelo `indice_de`: a
  ocorrência numa célula entra na célula (`grade.entrar`) e seleciona dentro dela; a de
  uma legenda seleciona o objeto. A ocorrência tem uma **chave** `(índice do alvo,
  deslocamento)` comparável com a do cursor (`ui/editor/busca.chave_do_cursor`), e é
  assim que "próximo" e "anterior" sabem de onde partir; no código a chave é o
  deslocamento em caracteres.
- **Substituir preserva o formato do primeiro caractere trocado** (`substituir_em_trechos`
  parte os trechos nas duas fronteiras e põe o texto novo no molde do primeiro de
  dentro); a referência de nota, a ilha inline e a marca de página não têm comprimento
  e ficam onde estão; um `\n` no substituto vira quebra suave. Na aba de texto a troca
  passa por `_reescrever_bloco` (parágrafo, lista, citação, parágrafo de nota, parágrafo
  de célula — pelo próprio widget da célula) ou `substituir_objeto` (legenda), e é o
  widget que registra o ponto; "Substituir todos" na aba ativa é **um** ponto composto,
  num capítulo fechado é um ponto por capítulo no `Historico` do projeto (a nota entra
  inteira, como manda a ED-04), e no código é `EditorDeCodigo.substituir_todos` (um grupo
  de desfazer). O capítulo aberto é sempre lido do widget, nunca do modelo.
- **"Texto marcado"** é uma faixa de chaves por arquivo (`Buscador.marcas`), mostrada
  com a tag `suspeito` (fundo amarelo); **"arquivos marcados"** é `janela.arquivos_marcados`,
  com "✓ " no navegador. Os dois ganharam item ("Editar → Marcar texto/arquivo para a
  busca"), e os botões do painel também (Substituir e localizar, Substituir todos,
  Contar, Listar) — seção ED-06 no fim de Editar. "Seleção" só entra na lista de escopos
  quando há seleção. O histórico das 20 vai para `Settings editor.buscas`.
- **"Ir para…" vale nos dois modos** (a ED-02 só tinha a linha, no código): linha (código)
  ou bloco (texto), diagrama, figura, tabela, página do impresso (a `MarcaDePagina` ou o
  `Trecho.pagina`, com deslocamento) e capítulo (`busca.destino`; `Caixas.ir_para`).
- **A peneira de notação foi copiada** para `core/editor/ortografia.py` (`e_notacao`), com
  um teste de paridade com `core.notacao.e_token_de_notacao`: importar `core.notacao`
  traz `box_service` e o OpenCV, e o editor abre sem eles (DEC-07). Pelo mesmo motivo
  `core/lexico.py` passou a importar `notacao` só em `_palavras_de_prosa`. Ficam de fora
  também o token com dígito, a palavra toda em maiúsculas (`FIDE`, `ECO`), o código, a
  ilha e os papéis de xadrez (lance, NAG, figurina, jogador, abertura); `Black's` e
  `Nimzo-Indian` valem por partes.
- **`lexico.sugestoes`** só compara com os baldes de `_indice_por_forma` de comprimento
  ±2 e mesma inicial (e, se nada sair, ±1 com qualquer inicial): a primeira chamada custa
  0,2 s (o índice) e as seguintes milissegundos. A inicial maiúscula é devolvida.
- **A caixa do `F7` é uma só para a verificação inteira** (`wait_variable`), com "Trocar
  todas" além das quatro ações da spec; uma troca desloca as suspeitas seguintes do mesmo
  alvo; no fim, o sublinhado `orto` é refeito com o que sobrou. No modo código as
  suspeitas vão para Resultados com a `linha_fonte` do bloco. Os léxicos são um por
  idioma (`ortografia.Lexicos`), com o dicionário do livro em todos; "Adicionar" num
  livro sem caminho é erro de entrada ("salve o livro antes"). O `pt` fica vazio e quieto
  até a ED-06b.
- **`core/editor/simbolos.py`** (a parte pura: categorias, busca por nome numa faixa fixa
  de códigos, código ↔ caractere) ao lado de `ui/editor/simbolos.py`; o `Ctrl+Shift+X`
  sem prefixo exige de 4 a 6 dígitos em limite de palavra — o Word converte `e4` em `ä`,
  e num livro de xadrez `e4` é um lance (`U+A0` continua valendo).
- **A contagem da barra de status passou a ser a de `estatisticas.contar_capitulo`**
  (notas e legendas entram): é o único jeito de "Contagem bate com o modelo" valer para a
  barra, a caixa e o `contagem` da ED-02 ao mesmo tempo.
- **`TextoRico.posicao_de(indice)`** (a `posicao()` de qualquer índice) e
  **`EditorDeCodigo.substituir_intervalo`/`substituir_todos`** nasceram aqui.

---

## ED-06b — Tipografia, dicionário de português, buscas salvas

**Prioridade:** P1 · **Dependências:** ED-06 · **Paralelizável com:** ED-05, ED-08

### Contexto para começar do zero

Ler: spec §8.12 (buscas salvas), §8.13, §8.14, §5 (`FormatoDePagina.hifenizar`);
`core/lexico.py` (`juntar_hifenizadas`, `carregar`); `core/editor/busca.py` e
`ortografia.py` (ED-06); `core/editor/css_minima.py`.

### Entregas

`core/editor/tipografia.py` (§8.14, prévia, desfazer por capítulo, "Juntar palavras
hifenizadas"; `FormatoDePagina.hifenizar` → `hyphens: auto` na folha padrão);
`assets/lexico/pt.txt.gz` (`scripts/gerar_lexico_pt.py`,
licença em `assets/lexico/LICENCAS.txt`); `core/editor/buscas_salvas.py` +
`ui/editor/buscas_salvas.py`; testes `tests/test_editor_tipografia.py`,
`tests/test_lexico_pt.py`, `tests/test_editor_buscas_salvas.py`.

### Critérios de aceite

- **AC-ED06b-1** `"quoted" 1-0 ... 12.Nf3 O-O +-` → `“quoted” 1–0 … 12. Nf3 O‑O +-`;
  `juntar_hifenizadas` sobre "cava-" / "lo" → "cavalo"; hifenização liga `hyphens:
  auto` na folha e `w:autoHyphenation` no DOCX (conferido pela ED-09).
- **AC-ED06b-2** `sugestoes("cavalu", lex_pt)` contém "cavalo".
- **AC-ED06b-3** Grupo de três buscas em lote com resumo; exportar/importar JSON.

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_tipografia.py tests/test_lexico_pt.py tests/test_editor_buscas_salvas.py tests/test_editor_css_minima.py -q -p no:cacheprovider -o addopts=""
```

### Registro — 2026-09-21 — IMPLEMENTADA

Entregue em `core/afixos.py`, `core/editor/{tipografia,buscas_salvas}.py`,
`ui/editor/{tipografia,buscas_salvas}.py`, `scripts/gerar_lexico_pt.py`,
`assets/lexico/pt.hunspell.gz` (1,3 MB) e `LICENCAS.txt`, as mudanças em `core/lexico.py`,
`core/editor/ortografia.py`, `ui/editor/{janela,dialogos}.py` e três arquivos de teste (17
testes, um `slow`). Conferido na tela com o processo DPI-aware: a caixa Tipografia com a
prévia por ocorrência e a caixa Buscas salvas.

**O que divergiu da spec, e por quê:**

- **O português não é uma lista chã (`pt.txt.gz`): é o pacote Hunspell `pt.hunspell.gz`
  + `core/afixos.py`.** Medido: a expansão completa do VERO (o dicionário do LibreOffice,
  307 mil raízes e 25 mil regras) dá 10,4 milhões de formas — 2,7 milhões sem as ênclises
  (`amá-lo-ia`), 1,8 milhão sem diminutivos e superlativos —, 27 MB comprimidos e meio
  minuto para carregar num `set`. O pacote guarda as raízes com as flags e as regras
  `SFX`/`PFX` (texto UTF-8, 1,3 MB), carrega em 0,4 s, e `Afixos.conhece` consulta ao
  contrário (da palavra para a raiz: sufixo, prefixo e prefixo+sufixo cruzados) em
  ~50 µs. Um teste `slow` confere que 400 raízes sorteadas têm toda a expansão
  reconhecida (zero faltas). `Lexico` ganhou o campo `flexoes`; as raízes vão para
  `palavras` (é o que `sugestoes` e `sinaliza` olham) — as sugestões do `pt` são raízes.
  A licença (LGPL 2.1, Raimundo Santos Moura) está em `assets/lexico/LICENCAS.txt`; o
  dicionário veio do TeXstudio instalado nesta máquina.
- **`sugestoes` desempata pelo prefixo comum**: `cavalu` tinha cinco candidatas com o
  mesmo `ratio` (`craval`, `chaval`, `cavalo`…) e o erro costuma estar no fim da palavra.
- **Tipografia propõe e só depois aplica** (`Troca` com contexto antes/depois; a caixa
  deixa desmarcar por ocorrência e por regra, e as regras escolhidas ficam em
  `Settings editor.tipografia`). O espaço inseparável entre número e lance só entra quando
  o que segue tem cara de lance (`2012. Now` não); `0-0`/`0-0-0` são roques (U+2011) e
  `0-1`/`1-0`/`½-½` resultados (U+2013); um intervalo de dígitos e um " - " espaçado viram
  meia-risca; `+-`/`-+` ficam. Código e ilha ficam fora. Na aba aberta a troca é do
  widget (um ponto composto); no capítulo fechado, `aplicar_no_capitulo` regista um
  ponto por capítulo (a nota inteira, como na busca).
- **"Juntar palavras hifenizadas"** usa `lexico.juntar_hifenizadas` como critério e cobre
  dois casos: o hífen antes de uma quebra suave e o hífen no fim de um parágrafo seguido
  do pedaço no começo do seguinte (duas trocas, uma em cada).
- **A hifenização é um bloco marcado na folha padrão** (`/* pybox:hifenizar */ … /*
  /pybox:hifenizar */`, `p { hyphens: auto; … }`) posto ou tirado por texto, sem reescrever
  o resto: `css_minima.escrever` só conhece as propriedades da CSS mínima e perderia o que
  não conhece. A caixa Tipografia tem o interruptor; `FormatoDePagina.hifenizar` continua
  o campo que o DOCX lê (`w:autoHyphenation`, conferido). Um livro sem folha só guarda o
  campo. `janela._texto_do_recurso` nasceu aqui.
- **Buscas salvas** moram em `Settings editor.buscas_salvas`; o lote é
  `Colecao.em_lote(nomes, executar)`, que recebe o "substituir todos" do `Buscador` e só
  soma (o resumo por busca e por arquivo vai a Mensagens, ao status e a uma caixa); a
  caixa é modeless e chama a janela pelos comandos internos `_buscas_salvas_*` (sem item
  de menu — são da caixa). O JSON tem `formato: pybox-buscas` e importar troca as de mesmo
  nome.

---

## ED-07 — O editor de código

**Prioridade:** P0 · **Dependências:** ED-00 · **Paralelizável com:** ED-01, ED-03, ED-09

### Contexto para começar do zero

Ler: spec §9 (Code View, Go to, Clips, Well-Formed, Mend/Reformat, Insert), §9.1–§9.3,
§13.2, §14; `core/editor/xhtml.py`, `css_minima.py`.

### Entregas

`ui/editor/realce.py` (estado por linha; temas); `ui/editor/codigo.py`
(`EditorDeCodigo(master, linguagem, folhas=(), abrir_alvo=None)`: `carregar`,
`sincronizar`, `sujo`, `foco`, `posicao`, `comandos`, números de linha num `Canvas`
**próprio** dentro de `codigo.py` (a `Calha` do modo texto é da ED-03, mesma onda), linha
atual, casamento, auto-indentação, `comentar`, `reformatar`, `completar_tag`, `sugerir`,
`envolver(tag)` (`Ctrl+B/I/U`), `inserir_link(href, texto)`, `inserir_id(id)`,
`inserir_imagem(href, alt)`, `ir_para_linha`, `verificar_bem_formado`, `consertar`,
`dividir_no_cursor`, `ir_ao_alvo`/`voltar`, zoom; `undo=False`; bindtag;
`highlightthickness=2`); `core/editor/consertar.py` (`consertar`, `reformatar_css`);
`core/editor/clipes.py` + `ui/editor/clipes.py` (grupos; também no texto — ligado na
ED-08); testes `tests/test_editor_realce.py`, `_codigo.py`, `_consertar.py`, `_clipes.py`.

### Critérios de aceite

- **AC-ED07-1** Realce certo; `<!--` na linha 10 de 200 realça as seguintes e fechá-lo
  as devolve; o tempo da faixa visível de um arquivo de 200 KB fica num teste `slow` de
  `tests/test_editor_realce.py` (o `medir_editor.py` só ganha o realce na ED-13).
- **AC-ED07-2** `verificar_bem_formado()` sobre `<p>aberto` e sobre prefixo não
  declarado → linha/coluna; `consertar()` fecha e avisa.
- **AC-ED07-3** `reformatar()` = `canonico`, idempotente;
  `reformatar_css` preserva comentários.
- **AC-ED07-4** `completar_tag()`, `sugerir()` com as classes de `folhas`, `envolver
  ("strong")` sobre a seleção.
- **AC-ED07-5** Clipe com `\1`; persistência.
- **AC-ED07-6** `dividir_no_cursor` bem-formado dos dois lados.
- **AC-ED07-7** `ir_ao_alvo()` sobre `href="cap-0002.xhtml#x"` chama `abrir_alvo(
  "cap-0002.xhtml", "x")` (espião); sobre `class="lance"` chama com a folha e a regra;
  `voltar()` retorna.
- **AC-ED07-8** Contraste ≥ 4,5:1 nos dois temas; foco visível.
- **AC-ED07-9** `inserir_link("cap-0002.xhtml#x", "ver")`, `inserir_id("x")` e
  `inserir_imagem("../Images/a.png", "alt")` deixam o XHTML bem-formado com `href`, `id`
  e `src`/`alt` presentes.

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_realce.py tests/test_editor_codigo.py tests/test_editor_consertar.py tests/test_editor_clipes.py -q -p no:cacheprovider -o addopts=""
```

### Registro — 2026-09-19 — IMPLEMENTADA

Entregue em `ui/editor/realce.py` (tokenizador de XHTML e CSS com estado por linha,
`Realce` incremental, os dois temas e `contraste`), `ui/editor/codigo.py`
(`EditorDeCodigo`), `core/editor/consertar.py` (`consertar`, `reformatar_css`),
`core/editor/clipes.py` + `ui/editor/clipes.py` e os quatro arquivos de teste (29
testes; o de desempenho é `slow`). Conferido na tela, nos dois temas, com o processo
DPI-aware.

**O que divergiu da spec, e por quê:**

- **O `tk.Text` é observado por um proxy do comando Tcl** (`rename` + `createcommand`),
  e não por `<<Modified>>`: é o único jeito de saber **onde** a edição aconteceu (linha e
  quantas linhas entraram ou saíram) — o que a re-tokenização incremental e o desfazer
  por operação precisam — e de ver as edições que o próprio `Text` faz por dentro
  (`tk::TextInsert`, colar, arrastar). Os resultados do `tk.call` chegam como
  `Tcl_Obj` e são convertidos com `str()` na hora — sem isso o proxy morre em silêncio
  (o Tcl engole a exceção do callback e devolve um `TclError` vazio a quem chamou).
- **Desfazer próprio por operação**, e não por cópia do documento: cada `insert`/`delete`
  vira uma operação reversível; a digitação contínua coalesce em 0,7 s (a janela da
  DEC-04); um comando composto (envolver, comentar, sugerir, reformatar) entra num
  **grupo** (`with self._grupo()`), senão desfazer um `envolver` devolvia o texto sem o
  miolo. A ED-02 decide se o modo código usa esta pilha ou a `Historico` do projeto.
- **A faixa visível tem no mínimo 60 linhas** a partir do topo: numa janela `withdraw`n
  o `winfo_height` é 1, e sem esse piso os testes (e a primeira pintura) não veriam
  tag nenhuma. `sincronizar(tudo=True)` pinta o documento inteiro.
- **Fechar um comentário re-tokeniza até o fim tanto quanto abri-lo** (AC-ED07-1): a
  convergência só para quando o estado no começo de uma linha *já era* o mesmo, e depois
  de abrir, todas começavam em comentário. Editar uma linha comum para na seguinte.
- **`</` completa pela pilha de elementos abertos** (regex sobre o texto até o cursor,
  sem os vazios e sem comentários/PIs) — não pelo `expat`, que exigiria o documento
  bem-formado justamente quando ele não está.
- **Tema escuro: `casamento` = `#12304d`** (o `#264f78` do rascunho dava 3,2:1 contra os
  tokens); o teste do AC-ED07-8 confere token × fundo, token × linha atual, token ×
  casamento e token × erro, nos dois temas.
- **`consertar` preserva a caixa das letras** relendo o texto cru da tag
  (`get_starttag_text`), porque o `html.parser` devolve tudo em minúsculas e um
  `viewBox` de SVG embutido não sobreviveria. O que já está bem-formado volta intacto.
- **`reformatar_css` dá `;` à última declaração do bloco** e mantém o comentário no
  lugar (antes da regra, ou colado à declaração); idempotente por teste.
- **Clipes: `\0` também é a seleção**, e um `padrao` (regex) opcional dá `\2`…`\9`;
  `Clipes.carregar` devolve os de fábrica quando nada foi gravado, e uma lista vazia
  gravada é "nenhum clipe". Padrão inválido é `ValueError` na criação.
- **Os diálogos ficam para a janela**: `Ctrl+G`, `Ctrl+K`, `Ctrl+Enter` e
  `Ctrl+Shift+J` geram `<<IrParaLinha>>`, `<<InserirLink>>`, `<<DividirNoCursor>>` e
  `<<Clipes>>`; os comandos com argumentos (`ir_para_linha(n)`, `inserir_link(href,
  texto)`, `dividir_no_cursor()` → as duas metades) são o que a ED-02 liga.
- **`pytest.ini` (F5.4) sobrepunha o `[tool.pytest.ini_options]` do `pyproject.toml`**:
  os `markers` registrados lá, inclusive o `slow` da ED-00, nunca valeram (o marcador
  saía como desconhecido). Passaram para o `pytest.ini`; `-m "not slow"` é o gate.

---

## ED-08 — O livro no modo código: navegador, sumário, metadados, capa, semântica, relatórios, validação, prévia

**Prioridade:** P0 · **Dependências:** ED-02, ED-07 · **Paralelizável com:** ED-05, ED-06b

### Contexto para começar do zero

Ler: spec §4 (DEC-05), §7.1, §9 (tabela), §9.5–§9.8, §10.1, §5 (`Metadados`, `Pessoa`);
`core/editor/epub.py`, `livro_ops.py`, `sumario.py` (ED-00/01); `core/chess_pdf_processor.
py: missing_glyphs`; `tests/test_f111_arquivo.py`; `ui/fontes.py`.

### Entregas

`ui/editor/navegador.py` (contexto completo com item de menu para cada ação);
`ui/editor/sumario.py` (painel e editor; "ao dividir"); `ui/editor/metadados.py`;
`livro_ops.definir_capa`, semântica (§9.7), marcos, vincular folhas, adicionar arquivo/
cópia, nova folha, ordenar, abrir com…; `core/editor/relatorios.py` (com **caracteres**);
`core/editor/validacao.py`; `ui/editor/previa.py` (`Previa(atraso_ms)`;
`ui/fontes.registrar_arquivo`); `pyproject.toml` extras `editor-previa`,
`epub-validacao`; "Apagar recursos/classes não usados"; "Sumário como página"; clipes no
modo texto; `abrir_alvo` real; seção ED-08 em `menus.py`; testes `tests/test_editor_
navegador.py`, `_sumario_ui.py`, `_metadados.py`, `_relatorios.py`, `_validacao.py`,
`_previa.py`, `_capa.py`, `_livro_ops_ui.py`.

### Critérios de aceite

- **AC-ED08-1** Renomear pelo navegador atualiza tudo; renomear vários; adicionar
  arquivo e cópia; nova folha; ordenar por nome; vincular folhas grava `Capitulo.folhas`;
  semântica e marcos gravados e lidos do nav.
- **AC-ED08-2** Gerar sumário 1–2 → nav com árvore e `page-list`; editar/reordenar;
  NCX coerente; "Sumário como página" cria `Text/sumario.xhtml` com `epub:type="toc"`.
- **AC-ED08-3** Metadados completos com `refines` preservados; `dcterms:modified`;
  `epubcheck` limpo.
- **AC-ED08-4** Capa com invólucro SVG, `properties="svg"`, `cover-image`, `<meta
  name="cover">`, marco; `epubcheck` limpo.
- **AC-ED08-5** Relatórios: imagem não usada; classe usada e não definida; link e `ref`
  quebrados; `♕` sem fonte; caracteres com `Ã`; diagrama `revisar`.
- **AC-ED08-6** "Apagar classes não usadas" preserva o resto byte a byte; "Apagar
  recursos não usados" remove só o não referenciado.
- **AC-ED08-7** `Previa(atraso_ms=0)` + `update()` mostra o `<p>`; mal-formado mantém;
  `ir_ao_bloco(linha)`; `abrir_alvo` real troca de aba.
- **AC-ED08-8** Sem Java, mensagem; com Java, erros com arquivo e linha.
- **AC-ED08-9** `registrar_arquivo` de uma fonte do EPUB devolve família listada em
  `tkfont.families()`; um clipe inserido no modo texto vira o modelo do fragmento.

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_navegador.py tests/test_editor_sumario_ui.py tests/test_editor_metadados.py tests/test_editor_relatorios.py tests/test_editor_validacao.py tests/test_editor_previa.py tests/test_editor_capa.py tests/test_editor_livro_ops_ui.py -q -p no:cacheprovider -o addopts=""
```

### Registro — 2026-09-21 — IMPLEMENTADA

Entregue em `core/editor/{relatorios,validacao}.py`, as operações novas de
`core/editor/livro_ops.py` (`definir_capa`, `definir_semantica`, `definir_marco`,
`novo_capitulo`, `nova_folha`, `adicionar_arquivo`, `dimensoes_da_imagem`),
`epub.texto_do_opf`, `ui/editor/{navegador,sumario,metadados,previa,operacoes}.py`,
`ui/fontes.registrar_arquivo`, as mudanças em `ui/editor/{janela,menus,dialogos}.py`, os
extras `epub-validacao` e `editor-previa` no `pyproject.toml`, e oito arquivos de teste
(33 testes, três `slow` com o epubcheck de verdade). Conferido na tela com o processo
DPI-aware: o navegador com a capa e a semântica, a prévia ao lado do código, o editor de
sumário e a caixa de metadados (616 px, cabe).

**O que divergiu da spec, e por quê:**

- **O menu Livro inteiro mora em `ui/editor/operacoes.py: OperacoesDoLivro`**, não na
  janela: o alvo de cada comando é o arquivo focado no navegador (senão a aba ativa), a
  mudança vai por `livro_ops`, e `_depois()` recarrega navegador, sumário e as abas do que
  mudou. O navegador e o sumário viraram painéis (`Navegador`, `PainelDeSumario`) que só
  chamam a janela por comando; `janela.navegador` e `janela.arvore_do_sumario` continuam
  sendo os `Treeview`. O menu de contexto do navegador é montado dos itens da barra
  (`navegador.CONTEXTO`) e ganhou o item "Abrir o arquivo do navegador" (seção ED-08 no
  fim de Livro) — toda ação de contexto tem item. Arrastar reordena a espinha por
  `reordenar_capitulos`, um comando interno sem item (como `_buscas_salvas_*`).
- **A capa é `livro_ops.definir_capa`**: o invólucro SVG do Sigil (`viewBox` do tamanho
  da imagem, lido do cabeçalho PNG/GIF/JPEG/SVG sem PIL — `dimensoes_da_imagem`), num
  capítulo `Text/capa.xhtml` em `texto_cru` com `epub:type="cover"`, `linear="no"` e
  primeiro na espinha; `properties="svg"`, `cover-image` e `<meta name="cover">` já eram
  do escritor da ED-01. Definir de novo reescreve o mesmo arquivo.
- **A semântica é um `epub:type` no corpo e um marco** (`definir_semantica`): as únicas
  (`cover`, `toc`, `bodymatter`…) saem do capítulo que as tinha; `chapter` não é marco;
  ligar a mesma de novo desliga. Num capítulo em `texto_cru` o atributo entra no `<body>`
  por texto. O submenu "Semântica do capítulo ▸" é dinâmico (✓ na atual).
- **"Sumário → Gravar"** não grava no disco (o nav é regenerado ao salvar, DEC-01):
  confere os destinos, refaz a aba de leitura do `nav.xhtml` e marca sujo. "Sumário como
  página" reescreve o `sumario.xhtml` que já existe (o capítulo com semântica `toc`).
- **O OPF abre só para leitura** (`epub.texto_do_opf`, o escritor com `montar(sem_dados=
  True)`, que não abre recurso), como o nav e o NCX.
- **Metadados completos com a forma curta preservada**: `metadados(título, autor,
  idioma)` da ED-02 continua valendo (a ED-02 tem teste). A caixa não toca em `extras`,
  `ids` e `prefixos`; uma pessoa que já existia guarda o `id` (os `refines` apontam para
  ele); uma capa que não está no livro é erro de entrada.
- **Relatórios sem `fitz` no topo**: só "Fontes e glifos" e a cobertura de "Caracteres"
  importam o `fitz` (`Font.has_glyph`), quando rodam, sobre as fontes embutidas extraídas
  para uma pasta temporária; sem fonte embutida não há o que conferir. "Apagar classes não
  usadas" corta regras pelo texto (`regras_da_folha`: um varredor que entra em `@media` e
  pula comentários e strings), nunca por `css_minima.escrever`; só regras cujos seletores
  são **todos** de classes sem uso saem. Ativar uma linha de folha em Resultados abre a
  folha na linha da regra (`dados["inicio"]`, um deslocamento → linha).
- **A validação roda o `epubcheck.jar` do pacote `epubcheck` com `--json`** (ou um
  `epubcheck` no PATH), e o `path` de cada mensagem volta como href relativo ao OPF;
  `comando=[]` é "sem epubcheck" (a mensagem da AC-ED08-8), `None` descobre. Corre
  **síncrona** com o cursor de espera (3,5 s no livro completo) — o `TaskController`
  fica para quando houver um livro em que isso doa. O `correr` é injetável
  (`operacoes.correr_epubcheck`), e é assim que o teste sem Java simula o JSON.
- **A prévia é o `TextoRico` só de leitura** sobre `xhtml.ler` (DEC-05): mal-formado mantém
  a anterior e escreve o erro no rodapé; `<<CursorMoveu>>` do código leva ao bloco pela
  `linha_fonte`; o clique devolve a linha. Os dois ficam lado a lado com `side="left"`
  nos dois (o editor é repackado): um `side="right"` depois de um `fill=both, expand`
  ficava com largura zero. O `tkinterweb` é só um extra declarado.
- **"Abrir com…" vigia o arquivo exportado** (`after` de 1,5 s) e traz de volta o que
  mudou no disco — um capítulo volta em `texto_cru`; o lançador é injetável.
- **`ui/fontes.registrar_arquivo`** lê a família na tabela `name` do TTF/OTF à mão (sem
  `fitz` nem `fontTools`) e registra com `AddFontResourceExW`; o editor a importa só
  quando precisa, porque `ui/fontes.py` traz `chess_pdf_processor` (fitz) no topo.
- **Clipes no modo texto**: o texto do clipe (com `\0`…`\9` da seleção) é lido como
  fragmento (`blocos_do_xhtml`) e entra como trechos ou blocos; `clipes` e `aplicar_clipe`
  deixaram de ser só do código.
- **Testes que a fase mexeu**: o `gui` da AC-ED02-3 passou a esperar `sumario_editar` em
  `Ctrl+T` e `substituir` em `Ctrl+H` (o editor de sumário é modal e travava a suíte); a
  AC-ED02-2 simula o "comando só de um modo" restringindo `modos_do_comando`, porque não
  sobrou comando assim; o OPF abre em vez de avisar.

---

## ED-09 — DOCX: escrever a partir do modelo (núcleo)

**Prioridade:** P0 · **Dependências:** ED-00 · **Paralelizável com:** ED-01, ED-03, ED-07
**Resultado:** §10.3 inteira, só `core/` (os itens de menu entram na ED-12).

### Contexto para começar do zero

Ler: spec §6.2/§6.3 (DOCX), §10.3, §10.7, §15; `core/exportar.py:838-1335`;
`tests/test_f111_arquivo.py`; ECMA-376 §17.11 (notas), §17.9 (numeração), §17.16.5.68
(`TOC`), §17.16.5.51/52 (`SEQ`, `REF`), §17.16.5.44 (`PAGEREF`), §17.6.8 (`evenAndOddHeaders`).

### Entregas

`core/editor/docx_io.py: escrever(livro, caminho, opcoes) -> RelatorioDeConversao`
(estilos da §10.3 com nomes do Word; `noProof`; `w:lang`; `numbering.xml` com `w:ind`;
notas — as sete costuras; `SEQ`/`_Ref`/`REF`; sumário pré-renderizado com `TOC 1`…`6`
e `PAGEREF` + `updateFields`; `evenAndOddHeaders`, `mirrorMargins`, `Livro.pagina`;
`w:shd` com texto branco em fundo escuro; SVG rasterizado; diagrama `fonte` com queda
para PNG; `docPr/@descr`; marcas de página como `bookmarkStart pg-n` **sem quebra**;
hifenização; ilhas em `Ilha`); `tests/test_editor_docx.py` (XML do zip);
`tests/dados/editor/` DOCX golden; `docs/roteiros/editor_docx.md`.

### Critérios de aceite

- **AC-ED09-1** Livro sintético completo → DOCX com todos os estilos e runs da §10.3;
  lista alfabética começando em 3 (`startOverride`); tabela com legenda `SEQ Tabela`;
  figura com `descr`; diagrama `png` com `descr` = FEN; diagrama `fonte` na tabela 1×1;
  `fonte` com coordenadas e fonte sem moldura em glifo → PNG com aviso; nota de rodapé
  e de fim reais; quebra de página **só** onde há `QuebraDePagina` (as 12 `MarcaDePagina`
  viram `bookmarkStart pg-n` e nenhuma `w:br type="page"`); hiperlink; `REF _Ref<n>`;
  sumário com uma entrada e um `PAGEREF` por título; rodapé `PAGE`; cabeçalhos par e
  ímpar; página e margens de `Livro.pagina`; `w:autoHyphenation` quando pedido.
- **AC-ED09-2** `[Content_Types].xml`, `footnotes.xml` (`-1`, `0`), `settings.xml`
  (`footnotePr`, `evenAndOddHeaders`, `mirrorMargins`, `updateFields`), rels.
- **AC-ED09-3** Sem `python-docx` → `RuntimeError` com instrução.
- **AC-ED09-4** Roteiro preenchido (Word e LibreOffice; manual; data e versões aqui).

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_docx.py tests/test_f111_arquivo.py -q -p no:cacheprovider -o addopts=""
```

### Registro — 2026-09-21 — IMPLEMENTADA

Entregue em `core/editor/docx_io.py` (`escrever(livro, caminho, opcoes) ->
RelatorioDeConversao`), `tests/editor_livros.livro_completo` (o livro sintético da
AC-ED09-1), `tests/test_editor_docx.py` (8 testes) e o golden de
`tests/dados/editor/docx_golden/` (`document.xml`, `footnotes.xml`, `endnotes.xml`,
`numbering.xml`; regrava-se com `python tests/test_editor_docx.py --gravar-golden`), e
`docs/roteiros/editor_docx.md`. Medido: o livro completo (56 blocos, 4 diagramas, 3 fontes
embutidas) sai em 0,6 s; o Word 16.0.14334 abre o arquivo sem diálogo de reparo, conta 1
nota de rodapé, 1 de fim, 22 campos, 28 marcadores, 1 sumário (atualizado: seis entradas
com página), 8 hiperlinks e 3 listas, e o PDF que ele exporta traz a Merida embutida.

**O que divergiu da spec, e por quê:**

- **Os estilos com nome interno do Word nascem `builtin`** (`add_style(..., builtin=True)`,
  sem `w:customStyle`): com `customStyle="1"` o Word 16 tratou "footnote text", "toc 1" e
  "Hyperlink" como estilos do usuário com nome reservado e criou "Texto de nota de
  rodapé1", "Sumário 11", "Hyperlink1" ao lado dos dele — exatamente a duplicação que a
  §6.3 quer evitar. Os `styleId` são limpos (`ComentarioCaractere`, `CabecalhoDeDiagrama`).
- **`STYLEREF 1`, e não `STYLEREF "Heading 1"`**, no cabeçalho ímpar: o nome do estilo
  dentro do campo é o nome **local** — no Word em português dá "Erro! Use a guia Página
  Inicial…"; o nível é o mesmo em qualquer idioma.
- **A `ChessMerida-Diagram.ttf` ganhou `OS/2` versão 3** (`gerar_fonte_de_diagrama.py`
  `subir_os2`, fonte regravada, sha novo em `fontes_de_diagrama.json`): o Word embute uma
  fonte com `OS/2` versão 0 (a de 1998) sem reclamar e **a ignora ao desenhar** — o run
  continua dizendo `ChessMerida-Diagram` e as casas saem em Arial. Medido em quatro
  variantes do mesmo DOCX pelo PDF que o Word exporta: só a `OS/2` v3 resolve; renomear
  ou apagar os registros de nome de símbolo não muda nada. Os 97 contornos continuam byte
  a byte os de 1998; PNG e EPUB não mudam (65 testes de F58/F97/F99/F59 verdes). É defeito
  de antes desta fase (o `exportar.para_docx` da F99 embute a mesma fonte).
- **A caixa do diagrama em fonte leva 1,5 pt de folga** (`FOLGA_DA_CAIXA_PT`): com a
  largura exata `corpo × colunas`, o Word 16.0.14334 dobra a oitava casa da SkakNew para
  a linha seguinte (0,5 pt dobra, 1 pt não). O `exportar.para_docx` de hoje tem o mesmo
  dobra e ficou como está — os testes F97/F99 fixam a largura em twips; a ED-12 decide.
- **`OpcoesDeConversao.notas`**: `"rodape"` (padrão) respeita o `Nota.tipo` de cada nota
  (o livro sintético tem rodapé **e** fim, como a AC pede); `"fim"` leva todas para o fim.
  A spec dizia só "decide se as notas saem no rodapé ou no fim".
- **`modo_de_diagrama` decide por todos os diagramas do livro**, como a §10.8 diz para o
  DOCX; o diagrama em fonte cai para PNG (com aviso) quando a fonte não está disponível
  ou quando tem coordenadas sem moldura em glifo (SkakNew); em `png`, o PNG já desenhado
  do livro (`Diagrama.imagem` com a chave corrente) é reaproveitado, senão
  `epub.png_do_diagrama`.
- **O capítulo abre página pelo estilo** (`Heading 1` com `pageBreakBefore`), e não por
  `w:br`: a AC-ED09-1 pede `w:br type="page"` só onde há `QuebraDePagina`. As marcas de
  página são marcadores `pg-n` no começo do parágrafo seguinte (ou num parágrafo vazio no
  fim do capítulo); `Trecho.pagina` vira o marcador no lugar do trecho.
- **Só alvo que existe vira marcador**: link ou `ref` para capítulo ou id que não há sai
  como texto, com aviso — um `w:hyperlink w:anchor` para marcador inexistente é link morto
  sem erro. Os alvos de link levam `bm_<índice do capítulo>_<id>` (o id é único por
  capítulo, INV-01); o capítulo inteiro, `bm_<índice>_inicio`.
- **A nota é escrita com os mesmos runs do corpo** e movida para a parte `footnotes.xml`
  (os parágrafos nascem no corpo e saem por `lxml`); um hiperlink dentro da nota ganha
  relacionamento na parte da nota (`word/_rels/footnotes.xml.rels`). As partes são
  `docx.opc.part.Part` relacionadas ao documento — o `python-docx` escreve o `Override`
  do `[Content_Types].xml` sozinho; o `settings.xml` recebe `footnotePr`/`endnotePr`,
  `mirrorMargins`, `autoHyphenation` e `updateFields` **na ordem do esquema**
  (`ORDEM_DOS_SETTINGS`; fora de lugar o Word acusa arquivo corrompido).
- **Numeração**: um `abstractNum` de nove níveis por lista (o marcador de cada nível vem
  da primeira sublista daquela profundidade; sem marcador, disco/círculo/quadrado ou
  decimal) e um `num` por lista com `startOverride` só nos níveis com `inicio != 1`; os
  parágrafos de continuação de um item saem sem `numPr`, recuados.
- **Sumário**: só os níveis 1–3 (o `\o "1-3"` do campo), com `PAGEREF` em cache "1…n" e
  `w:updateFields` para o Word refazer ao abrir — o Word pergunta se atualiza os campos.
- **Tabela**: legenda **antes** (convenção do Word), `tblHeader` na primeira fila quando
  `primeira_fila_cabecalho`, `largura_pct` em `tblW type="pct"`; célula de cabeçalho em
  negrito; um parágrafo de 1 pt separa tabelas coladas (o truque do `exportar`).
- **Ilha** (de bloco e inline) sai como o texto do fragmento no estilo de caractere
  `Ilha`, com aviso; SVG de figura é rasterizado pelo `fitz` a 200 dpi, com aviso;
  figura sem `alt` avisa e usa a legenda ou o nome do arquivo como `descr`.
- **Roteiro**: a coluna do Word está preenchida por automação COM (PowerShell) — o Word
  abriu, contou e exportou o PDF; a do LibreOffice fica vazia porque ele não está
  instalado nesta máquina (dito no roteiro, não suposto).

---

## ED-09b — DOCX: ler para o modelo (núcleo)

**Prioridade:** P0 · **Dependências:** ED-09 · **Paralelizável com:** ED-02

### Contexto para começar do zero

Ler: spec §10.4, §6.2 (coluna DOCX), §10.7, DEC-06; `core/editor/docx_io.py: escrever`
(ED-09) e os golden de `tests/dados/editor/`; `render_diagrama.fen_de_linhas`.

### Entregas

`docx_io.ler(caminho) -> (Livro, RelatorioDeConversao)` (§10.4; `pg-n` → `MarcaDePagina`;
`lado=""`; tabela 1×1; `descr`; `dividir_por_titulo`); `tests/test_editor_docx_ler.py`.

### Critérios de aceite

- **AC-ED09b-1** `ler(escrever(livro))`: texto idêntico por bloco; atributos da §6.2
  exceto `classe`; `papel` volta pelo estilo; `fundo` exato; `corpo_pt` a meio ponto;
  marcas de página de volta.
- **AC-ED09b-2** AC-009: FEN igual em `fonte` (tabela 1×1) e `png` (`descr`), `lado=""`.
- **AC-ED09b-3** DOCX de fora com caixa de texto e comentário: texto preservado, dois
  avisos; 3 `Heading 1` → 3 capítulos.

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_docx_ler.py tests/test_editor_docx.py -q -p no:cacheprovider -o addopts=""
```

---

## ED-10 — HTML e EPUB completos, importadores, TXT, e os seus itens de menu

**Prioridade:** P0 · **Dependências:** ED-01, ED-02 · **Paralelizável com:** ED-04, ED-06

### Contexto para começar do zero

Ler: spec §10.1, §10.2, §10.6, §10.7, §10.8, §6.1 (`MarcaDePagina`), §9.5;
`core/exportar.py:529-600, 600-810`; `core/editor/epub.py`, `livro_ops.py`, `sumario.py`.

### Entregas

`epub.py` completo (fontes copiadas com `@font-face` relativo; metadados de
acessibilidade **calculados** da §10.1; `pageBreakSource`; `page-list`; `properties`;
`validar_estrutura` completo); `core/editor/html_io.py` (`escrever_unico` com `section`
por capítulo e links `#<arquivo>__<id>`, `escrever_pasta`, `ler` com `dividir_por_
titulo` e registro dos sinônimos; `epub:type` → `role`); `core/editor/txt_io.py`;
"Importar ▸ HTML/TXT/EPUB", "Exportar… EPUB/HTML único/HTML pasta/TXT", "Dividir em
capítulos por título…", "Dividir nos marcadores" ligados — seção ED-10 em `menus.py`;
testes `tests/test_editor_epub_completo.py`, `_html.py`, `_txt.py`, `_menus_ed10.py`.

### Critérios de aceite

- **AC-ED10-1** Diagrama em `fonte` + `⩲` → duas fontes na pasta de fontes, `@font-face`
  certo, `ibooks:specified-fonts`; `accessMode visual` presente por haver imagem;
  `accessModeSufficient textual` ausente quando uma figura está sem `alt`;
  `pageBreakMarkers` com `page-list`; `structuralNavigation` ausente num livro só de
  "Página N"; `epubcheck` limpo.
- **AC-ED10-2** HTML único sem referência externa, `role="doc-footnote"`, uma `section
  role="doc-chapter"` por capítulo, link interno reescrito; pasta com `index.html`.
- **AC-ED10-3** HTML5 solto com `<b>`, `<i>`, dois `<h1>`, `<img>` relativa e `<div>`
  desconhecido → **dois** capítulos, negrito, itálico, figura, ilha, relatório com a
  normalização; `epub.escrever`+`ler` preserva.
- **AC-ED10-4** TXT ida e volta com `[Diagrama n: FEN]`.
- **AC-ED10-5** Anexar renomeia colisões; cada item de menu da seção ED-10 chama o
  comando (espião + `invoke`).

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_epub_completo.py tests/test_editor_html.py tests/test_editor_txt.py tests/test_editor_menus_ed10.py -q -p no:cacheprovider -o addopts=""
```

### Registro — 2026-09-21 — IMPLEMENTADA

Entregue em `core/editor/{fontes,html_io,txt_io}.py` (novos), `epub.py` (fontes embutidas
ao gravar, `structuralNavigation` só com título de verdade, `validar_estrutura` completo),
`consertar.py` (o fechamento opcional do HTML5), `xhtml.py` (a fatia do elemento vazio),
`relatorios.py` (as fontes necessárias contam como usadas), `ui/editor/conversoes.py`
(novo: `Conversoes`), `ui/editor/{janela,dialogos}.py`, `ui/fontes.py` (a leitura da
família mudou para o `core`) e quatro arquivos de teste (19 testes, um `slow` com o
epubcheck). Conferido na tela com o processo DPI-aware: o HTML solto importado para
dentro do livro (negrito, itálico, figura e ilha no modo texto; os dois capítulos no
navegador e no sumário) e a caixa Exportar com os sete formatos e a fase dos que faltam.

**O que divergiu da spec, e por quê:**

- **As fontes entram pelo `core/editor/fontes.py`, que lê o TTF/OTF à mão** (tabelas
  `name` e `cmap`, formatos 4 e 12 — conferido contra o `fitz` em seis fontes, zero
  diferenças) e o mapa das fontes de diagrama pelo JSON de `render_diagrama` sem
  importá-lo: a gravação do EPUB continua sem `fitz` e sem `cv2` (DEC-07). A escolha da
  fonte de símbolos é a de `exportar.fonte_dos_simbolos` (a maior cobertura, o recorte
  em empate), medida no texto. `ui/fontes.familia_do_arquivo` (ED-08) passou a delegar.
- **O `@font-face` vai num bloco marcado `/* pybox:fontes */` na folha padrão**,
  regenerado a cada gravação (como o `pybox:hifenizar` da ED-06b) e com a `src` relativa
  **à folha**; uma família que alguma folha já declara (o EPUB de hoje, com `fonts/`)
  não é declarada de novo, e a fonte que já está no livro (pelo nome do arquivo) não
  entra duas vezes. A pasta é a que o livro usa (`Fonts/` no novo, `fonts/` no de hoje).
  Sem folha padrão as fontes entram com aviso e sem `@font-face`.
- **O HTML5 sai da árvore, não do texto**: o capítulo escrito por `xhtml.escrever` é
  relido por `xhtml.analisar` e serializado como HTML5 — um `<span epub:type="pagebreak"/>`
  vazio tem de sair `<span></span>`, senão engole o parágrafo num `text/html`. Os `id`
  do arquivo único levam o prefixo `<arquivo>__` (INV-01: `id="title"` em todo capítulo
  do Calibre) e o `role` derivado fica onde o `epub:type` estava. O arquivo único ganha
  `<header>` e `<nav role="doc-toc">` gerado dos títulos quando não há sumário.
- **`html_io.ler` volta pelo nosso próprio arquivo único**: as `<section role="doc-…"
  id="<arquivo>">` viram capítulos com os ids e links desprefixados, o `<style>` inline
  vira folha `Styles/inline-n.css`, e o `role="doc-…"` sem `epub:type` ganha o
  `epub:type` de volta (para nota, marca de página e referência serem dialeto). Um
  `<p>` que só tem `<img>` vira `Figura` (no dialeto seria ilha inline, DEC-02) — é o
  jeito do HTML solto de pôr figura, e a AC-ED10-3 pede figura. O `<title>` do arquivo
  é o título do **livro**, não o do capítulo.
- **`consertar` ganhou o fechamento opcional do HTML5** (`<p>um<p>dois` são dois
  parágrafos; `li`, `td`/`th`/`tr`, `dt`/`dd`, `option`): sem isso todo HTML solto
  virava um parágrafo com o resto do arquivo dentro. O teste da ED-07 que esperava o
  aninhamento foi atualizado. E o `xhtml.analisar` tinha um defeito latente: a fatia
  de um elemento vazio seguido de `</p>` (`<img/></p>`) engolia o `</p>` — corrigido
  olhando a própria tag de abertura (`/>`).
- **O TXT é o formato mínimo que ainda volta** (cabeçalho de `txt_io.py`): `#` por
  nível, `> `, `- `/`1. ` por recuo, tabela ` | ` com `--- | ---` e legenda, `[Página n]`,
  `[Quebra de página]`, `* * *`, `[Figura n: alt]`, `[Diagrama n: FEN]` e as notas `[n]`
  no fim do capítulo; a quebra suave é quebra de linha. Na volta a figura vira parágrafo
  (o texto não carrega imagem), a ilha vira o seu texto, o `Diagrama.lado` fica `""`
  (DEC-06) e o idioma vem de fora (a janela passa o de `idioma_ortografia`).
- **"Importar" anexa ao livro aberto; sem livro aberto, vira o livro** (um projeto sem
  caminho, sujo, que "Salvar" pergunta onde gravar); "Abrir…" aceita `.html`/`.xhtml`/
  `.txt` pelo mesmo caminho. A conclusão da importação vai a Mensagens e à barra, não à
  caixa de conclusão (que tem "Abrir arquivo", coisa de exportação).
- **A exportação pode sujar o livro**: HTML e EPUB embutem as fontes e desenham os PNG
  dos diagramas, e esses recursos ficam (são do livro); quando entra recurso novo o
  projeto fica sujo e o navegador é refeito. O EPUB exportado continua sendo cópia.
- **Os relatórios contam as fontes necessárias como usadas** (`recursos_referenciados`),
  senão "Apagar recursos não usados" tirava a SkakNew de um livro sem `url()` na folha.
- **`validar_estrutura`** não aponta arquivo fora do manifesto (é aviso no epubcheck,
  e o `sobra.txt` do EPUB de fora é mantido de propósito).
- **Nada novo em `ui/editor/menus.py`**: todos os itens da fase já estavam na tabela
  (ED-02) e acordaram com o registro; a "seção ED-10" é `Conversoes.comandos`.

---

## ED-11 — A ponte com o documento editorial e o resto do fluxo de exportação

**Prioridade:** P0 · **Dependências:** ED-04, ED-05, ED-pré · **Paralelizável com:** ED-05b, ED-12

### Contexto para começar do zero

Ler: spec §4 (DEC-09, DEC-10), §5 (`Origem`, `OrigemDoLivro`), §7.2, §10.6.5, §10.7,
AC-008; `core/editorial_adapters.py: pagina_extraida_para_pagina` (as chaves reais do
`diagram`; `bold_spans` em `style`); `core/editorial_model.py` (`apply_review`);
`core/editorial_review.py` (`ReviewSession.edit`, `reject`, `from_journal`,
`ReviewJournal`); `ui/main_window.py` (`processar_documento_editorial_action` +
`concluir`; `_exportar_documento_revisado`; `revisar_documento_editorial_action`; o
`review_journal_path`).

### Entregas

`core/editor/importar_ir.py` (`de_documento`, `de_paginas` → `(Livro, Relatorio)`;
mapa da §10.6.5 na letra; `eventos_de(livro, doc) -> list[(bloco_id, after | None,
motivo)]`); `Projeto.documento_editorial`/`diario`; `salvar` com
`ReviewSession.from_journal(doc, ReviewJournal(caminho))`, `edit`/`reject`,
`sessao.document`; `ui/main_window.py` (`git add -p`): "Abrir no editor" nos `concluir`
de `processar_documento_editorial_action` e `_exportar_documento_revisado`, "Importar
JSON editorial", fila desabilita "Exportar com as correções" com o editor aberto; tag
`suspeito` + `!` na calha + motivos e leituras no painel; testes `tests/test_editor_
importar_ir.py`, `_ponte.py`.

### Critérios de aceite

- **AC-ED11-1** `EditorialDocument` sintético (3 páginas, 2 `heading` 1, `diagram` com
  `fen`+`png_base64`, `diagram` sem `fen`, `table`, `paragraph` com `bold_spans`,
  `caption`, `unknown`, `unresolved`) → 2 capítulos, `Diagrama` (`lado=""`) com
  `recorte`, `Figura` com aviso, `Tabela`, negrito, legenda, parágrafo com aviso,
  `MarcaDePagina(page_index+1)` entre páginas, `Origem` em todo bloco (escrita como
  `data-origem-*`, sem colidir com a `data-pagina` da marca), `data-suspeito`.
- **AC-ED11-2** AC-008 na letra, no `review_journal_path`, com `from_journal`.
- **AC-ED11-3** Desfazer antes de salvar não gera evento; editar/salvar/editar de
  volta/salvar → dois eventos; bloco já editado na fila → `before` igual ao `after` da
  fila.
- **AC-ED11-4** Fusão → `edit` no primeiro, `reject` no segundo, `origem.fundidas`.
- **AC-ED11-5** Suspeito com tag e `!`; painel com motivos e leituras.
- **AC-ED11-6** "Abrir no editor" após exportar DOCX monta das páginas; fila
  desabilitada com o aviso; o negrito editado **não** viaja e o relatório ao salvar o
  diz.

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_importar_ir.py tests/test_editor_ponte.py tests/test_editorial_review_phase5.py -q -p no:cacheprovider -o addopts=""
```

---

## ED-12 — PDF paginado, PGN, índice, itens de menu DOCX/PDF/PGN, relatório único, medição

**Prioridade:** P1 · **Dependências:** ED-05, ED-09b, ED-10 · **Paralelizável com:** ED-05b, ED-11

### Contexto para começar do zero

Ler: spec §10.3–§10.5, §10.8, §11.8–§11.9, §16, §5 (`FormatoDePagina`); `fitz.Story`,
`Archive`, `element_positions`, `Document.set_toc`; `core/pgn.py`; `scripts/ab_ocr_livro.py`.

### Entregas

`core/editor/pdf_io.py` (§10.5: margens espelhadas, cabeçalhos par/ímpar, `set_toc`,
`set_metadata`, `insert_link`); "Imprimir…"; `core/editor/pgn_io.py` (§11.8);
`core/editor/indice.py` (§11.9); "Formato de página…", "Exportar… DOCX/PDF/PGN",
"Importar ▸ DOCX", "Índice ▸" — seção ED-12 em `menus.py`; relatório unificado;
`scripts/medir_editor_vs_exportar.py`; testes `tests/test_editor_pdf.py`, `_pgn.py`,
`_indice.py`, `_menus_ed12.py`.

### Critérios de aceite

- **AC-ED12-1** PDF com ≥ 3 páginas de `Livro.pagina`, texto pesquisável, diagrama,
  número de página, cabeçalho par ≠ ímpar, sumário do PDF (`get_toc`) com os títulos,
  metadados, link interno funcional (`get_links`).
- **AC-ED12-2** PGN de "1.e4 e5 2.Nf3 (2.f4 exf4 {gambito}) Nc6 3.Bb5 ±" lido por
  `chess.pgn` com variante, comentário, `$14`, STR; exercício a partir de diagrama com
  `SetUp`/`FEN`; capítulo com dois segmentos → duas partidas.
- **AC-ED12-3** Índice de jogadores ordenado pela `chave` ("Kasparov, Garry" antes de
  "Wely, Loek van", e não pelo texto "Loek van Wely"), com links ao título mais próximo
  e o número da partida; `epub:type="index"`, `role="doc-index"`.
- **AC-ED12-4** Cada item da seção ED-12 chama o comando; o relatório de todo formato tem
  as oito contagens; a tabela da medição está aqui com a decisão (substitui / convive /
  não substitui).

### Verificação

```
.venv/Scripts/python.exe -m pytest tests/test_editor_pdf.py tests/test_editor_pgn.py tests/test_editor_indice.py tests/test_editor_menus_ed12.py -q -p no:cacheprovider -o addopts=""
.venv/Scripts/python.exe scripts/medir_editor_vs_exportar.py --sintetico
```

---

## ED-13 — Qualidade AAA: AC globais, desempenho, teclado, colar HTML, preferências, ajuda, gate

**Prioridade:** P0 · **Dependências:** todas
**Teto:** 3 sessões; o que exceder vai para `ED-13b` (regressões da medição).

### Contexto para começar do zero

Ler: spec §12 (todos os AC), §13, §14, §15, §17; `docs/OPERATIONS.md`;
`scripts/smoke_release.py` (`smoke_release.py <wheel> [--install]`, valida o wheel por
`core.ocr_phase8`); `tests/test_f35_atalhos.py`; `scripts/medir_editor.py` (ED-03).

### Entregas

`tests/test_editor_ac_globais.py` (AC-001…AC-010); `tests/test_editor_teclado.py` +
`docs/roteiros/editor_teclado.md`; `scripts/medir_editor.py` completo (livro do AC-005,
memória, busca, salvar) + regressões dentro do teto; `CF_HTML` por `ctypes`
(`AreaDeTransferencia` já injetada); Preferências (§7.6) e temas; "Ajuda"; `appy.py
--fechar-apos` + `scripts/smoke_release.py <wheel> --editor` (um passo **a mais** sobre o
wheel posicional: roda `appy.py --editor <livro sintético> --fechar-apos 1
--diagnostico-modulos` em subprocesso, `timeout=30`, exigindo código 0);
`docs/OPERATIONS.md` ("Editor de livro"; máquina de referência), `docs/SETUP.md`
(extras); gate com `-m "not slow"`; tabela final aqui.

### Critérios de aceite

- AC-001…AC-010 com função de teste ou roteiro preenchido.
- **AC-ED13-1** `medir_editor.py` dentro dos orçamentos (tabela aqui).
- **AC-ED13-2** Payload `CF_HTML` injetado com `<b>`, `<i>`, `<h2>`, `<img data:>` →
  negrito, itálico, título, figura.
- **AC-ED13-3** Preferência de corpo persiste em `Settings.get("editor")` e a próxima
  janela abre com ela.
- **AC-ED13-4** Release gate verde; `smoke_release.py <wheel> --editor` código 0.

### Verificação

```
.venv/Scripts/python.exe -m compileall -q appy.py core ui config scripts
.venv/Scripts/python.exe -m ruff check core ui appy.py config scripts
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -o addopts="" -m "not slow"
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -o addopts="" -m slow
.venv/Scripts/python.exe scripts/medir_editor.py
.venv/Scripts/python.exe scripts/smoke_release.py dist/pyboxeditor-0.1.0-py3-none-any.whl --editor
```

---

## Registro de execução

| Fase | Status | Data | Commit(s) | O que divergiu da spec |
|---|---|---|---|---|
| ED-pré | a fazer (usuário) | | | |
| ED-00 | **implementada** | 2026-09-19 | (ver "Registro" da fase) | entidade numérica na leitura; `Capitulo.namespaces`; notas rodapé-primeiro; `span.com`; `Ponto.indices`; `mapa_da_fonte` |
| ED-01 | **implementada** | 2026-09-19 | (ver "Registro" da fase) | `Diagrama.imagem`; `width` no PNG; `linear`, `nav_na_espinha`, `no_manifesto`, `Pessoa.id`, `Metadados.ids/prefixos`, `zip_de_origem`; `pybox:pagina`; `href` codificado; `noteref` de fora é ilha |
| ED-02 | **implementada** | 2026-09-21 | (ver "Registro" da fase) | bindtag `EditorJanela` com escopos; acorde de outro modo é `break`; `Ctrl+T`/`F8`; três itens fora da §7.3; `@y` no `<<MenuSelect>>`; `modos_do_comando`; inseparáveis agora; pilha própria do código; `core/services` preguiçoso; fila nas Mensagens; `DIALOGO_DE_CONCLUSAO` |
| ED-03 | **implementada** | 2026-09-19 | (ver "Registro" da fase) | proxy do `Text` em vez de `<<Modified>>`; modelo em cache + `sincronizar(reler=True)`; tags `pid:`/`pcls:`/`pex:`/`sub:` nos internos; `_fundem` por tupla; enter no título abre corpo |
| ED-04 | **implementada** | 2026-09-21 | (ver "Registro" da fase) | bindtag por instância e proxy em `proc` Tcl (defeitos latentes); faixa de notas como blocos `dn:`; célula = `TextoRico(celula=True)` com reconciliação adiada; `inserir_bloco_no_cursor`; `Fragmento.notas`; `_antes_forcado`; `end-1c`; itens fora da §7.3 |
| ED-05 | a fazer | | | |
| ED-05b | a fazer | | | |
| ED-06 | **implementada** | 2026-09-21 | (ver "Registro" da fase) | `Alvo` com deslocamento e chave; célula/legenda não endereçáveis; formato do primeiro caractere; um ponto composto na aba, um por capítulo fechado; texto/arquivos marcados com item; "Ir para…" nos dois modos; `e_notacao` copiada; `lexico` sem `notacao` no topo; caixa única do `F7` com "Trocar todas"; `core/editor/simbolos.py`; `Ctrl+Shift+X` exige 4 dígitos; contagem da barra = `estatisticas` |
| ED-06b | **implementada** | 2026-09-21 | (ver "Registro" da fase) | `pt.hunspell.gz` + `core/afixos.py` em vez de lista chã (10,4 M formas); `Lexico.flexoes`; desempate por prefixo; propor/aplicar com prévia; espaço só antes de lance; bloco marcado `pybox:hifenizar` na folha; buscas salvas com comandos internos |
| ED-07 | **implementada** | 2026-09-19 | (ver "Registro" da fase) | proxy do `Text`; desfazer por operação com grupos; faixa mínima de 60 linhas; `casamento` escuro; eventos virtuais para os diálogos; `markers` no `pytest.ini` |
| ED-08 | **implementada** | 2026-09-21 | (ver "Registro" da fase) | menu Livro em `operacoes.py`; navegador e sumário como painéis; capa por `definir_capa` com invólucro SVG; semântica = `epub:type` + marco; "Gravar" só refaz o nav; OPF só de leitura; forma curta de `metadados`; relatórios sem fitz no topo; classes apagadas por texto; validação síncrona com `comando=[]`; prévia = `TextoRico`; "Abrir com" vigia; clipes no texto |
| ED-09 | **implementada** | 2026-09-21 | (ver "Registro" da fase) | estilos do Word `builtin`; `STYLEREF 1`; `OS/2` v3 na Merida; folga de 1,5 pt na caixa; `notas="rodape"` respeita o tipo; quebra de capítulo pelo estilo; só alvo existente vira marcador; sumário 1–3 |
| ED-09b | a fazer | | | |
| ED-10 | **implementada** | 2026-09-21 | (ver "Registro" da fase) | fontes lidas à mão (`core/editor/fontes.py`) e bloco `pybox:fontes` na folha; HTML5 pela árvore com ids prefixados; `ler` volta pelas seções; `<p><img>` = figura; fechamento opcional no `consertar`; fatia do elemento vazio no `xhtml`; TXT mínimo que volta; importar anexa ou vira o livro; exportar pode sujar; fontes necessárias contam como usadas |
| ED-11 | a fazer | | | |
| ED-12 | a fazer | | | |
| ED-13 | a fazer | | | |
