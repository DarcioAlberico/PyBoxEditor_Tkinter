# Roteiro — o DOCX do editor de livros no Word e no LibreOffice (ED-09)

O que `core/editor/docx_io.escrever` produz é conferido pelos testes **no XML do zip**
(`tests/test_editor_docx.py`). Este roteiro é a outra metade: abrir o arquivo nos
programas de verdade, porque é o Word quem decide se as sete costuras das notas, o
sumário pré-renderizado e a fonte embutida valem (SPEC_EDITOR §15, "Nota por OOXML
direto"). O arquivo de prova é o livro sintético de `tests/editor_livros.livro_completo`:

```
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0, 'tests'); import editor_livros; from core.editor import docx_io; from core.editor.conversao import OpcoesDeConversao; docx_io.escrever(editor_livros.livro_completo(), 'completo.docx', OpcoesDeConversao(modo_de_diagrama='fonte'))"
```

Marcar cada linha com a data, o programa e a versão. **AAA só quando as duas colunas
estão preenchidas.** O que não se pôde conferir fica dito, não suposto.

| # | O que olhar | Como saber que está certo | Word | LibreOffice |
|---|---|---|---|---|
| 1 | O arquivo abre | Sem caixa de "conteúdo ilegível" nem "reparar" | ✅ 2026-09-21, Word 16.0.14334 (abre sem diálogo; `DisplayAlerts` desligado e nenhuma exceção) | — não instalado nesta máquina |
| 2 | Notas de rodapé e de fim | A nota de rodapé no pé da página 2, a de fim no fim do documento; a referência sobrescrita; os estilos são os **do Word** ("Texto de nota de rodapé", "Ref. de nota de rodapé"), sem "…1" duplicado | ✅ `Footnotes.Count == 1`, `Endnotes.Count == 1`; estilos resolvidos aos nativos (`BuiltIn == True`) | — |
| 3 | Link dentro da nota | "link" na nota de rodapé é hiperlink clicável | ✅ `word/_rels/footnotes.xml.rels` com o relacionamento; o Word conta 8 hiperlinks | — |
| 4 | Sumário | "Sumário" seguido das seis entradas (níveis 1–3) com número de página; `F9`/atualizar campo refaz os números; cada entrada leva ao título | ✅ `TablesOfContents.Count == 1`; após `Update()`: Capítulo um, Título 2, Título 3, Capítulo dois, Seção, Subseção; páginas 2/2/2/9/9/9 | — |
| 5 | Referências cruzadas | "Tabela 1", "Figura 1", "Diagrama 1", "Capítulo um" são campos `REF`, e `Ctrl+clique` vai ao alvo | ✅ `REF _Ref1 \h => Tabela 1`, `_Ref2 => Figura 1`, `_Ref3 => Diagrama 1`, `_Ref4 => Capítulo um` | — |
| 6 | Legendas com `SEQ` | "Tabela 1: Resultados" acima da tabela, "Figura 1: A foto" e "Diagrama 1: Posição" abaixo; estilo Legenda (nativo) | ✅ `SEQ Tabela/Figura/Diagrama \* ARABIC => 1`; estilo "Legenda" `BuiltIn` | — |
| 7 | Cabeçalhos par e ímpar, rodapé | Páginas ímpares: o título do capítulo (`STYLEREF 1`); pares: "Livro completo"; número de página no rodapé | ✅ `OddAndEvenPagesHeaderFooter == True`; ímpar "Capítulo um"/"Capítulo dois", par "Livro completo", rodapé 1…9 (PDF exportado pelo Word) | — |
| 8 | Página e margens | 140 × 210 mm; margens 15/12/18/20 mm (superior, externa, inferior, interna), espelhadas; hifenização ligada | ✅ 396,85 × 595,3 pt; t/b/l/r = 42,5/51/56,7/34 pt; `MirrorMargins == True`; `AutoHyphenation == True` | — |
| 9 | Marcas de página | Doze marcadores `pg-11`…`pg-22` e `pg-7` (Inserir → Indicador, com os ocultos), **sem** quebra de página; uma quebra só antes de "Depois da quebra." | ✅ 28 marcadores com os ocultos (`_Ref1-4`, `_Toc1-10`, `bm_1_alvo`, `pg-*`); 1 `w:br type="page"` | — |
| 10 | Listas | Marcadores (disco/círculo aninhado), lista alfabética começando em **c)**, romana | ✅ `Lists.Count == 3`; no PDF: "c) primeiro", "d) segundo", "i." | — |
| 11 | Tabela | Grade, primeira fila repetida como cabeçalho, "Pontos" à direita, 80% da largura | ✅ `Tables.Count` inclui a tabela; `tblHeader` no XML; PDF confere | — |
| 12 | Figuras | PNG a 120 pt, SVG rasterizado; texto alternativo ("Uma foto", "Um desenho") em Formatar imagem → Texto Alt | ✅ 3 imagens inline em `fonte`, 6 em `png`; `descr` no XML | — |
| 13 | Diagrama em imagem | `descr` = FEN; legenda "Diagrama 1: Posição" | ✅ | — |
| 14 | Diagrama em fonte (SkakNew) | Tabuleiro 8×8 numa caixa com filete, **sem** dobrar a oitava casa | ✅ com a folga de 1,5 pt (`FOLGA_DA_CAIXA_PT`): 0,5 pt dobrava, 1 pt não — medido | — |
| 15 | Diagrama em fonte com coordenadas (Merida) | Moldura e coordenadas em glifo, dez colunas; do lado das pretas (h…a, 1…8) | ✅ **só depois** de a `OS/2` da `ChessMerida-Diagram.ttf` subir para a versão 3 (`gerar_fonte_de_diagrama.py`): com a versão 0 o Word embute e ignora, e as casas saem em Arial | — |
| 16 | SkakNew com coordenadas | Cai para PNG (com aviso no relatório): a fonte não tem moldura em glifo | ✅ imagem com `descr` = FEN; aviso "não desenha coordenadas em glifo" | — |
| 17 | Realce e cor | "escuro" em branco sobre azul-escuro; "amarelo" sobre amarelo; "arial" vermelho a 9 pt | ✅ no PDF | — |
| 18 | Estilos de caractere | Lance/NAG sem revisão ortográfica (`noProof`); Figurina na fonte de símbolos; ilha em cinza (`Ilha`) | ✅ no PDF (♕ e ♘ na "Simbolos de Xadrez" embutida) | — |
| 19 | Fontes embutidas | Arquivo → Informações não pede fonte; sem a fonte instalada o tabuleiro continua certo | ⚠️ parcial: a `SkakNew-Diagram` está instalada nesta máquina (fontes do usuário), e o Word a usa em vez da embutida — conferir numa máquina sem ela; a Merida (não instalada) veio da embutida | — |
| 20 | Modo `png` e notas no fim | `OpcoesDeConversao(modo_de_diagrama="png", notas="fim")`: 4 imagens de diagrama; as duas notas viram notas de fim | ✅ `final_png.docx` (modo `png`) abre no Word com 6 imagens inline; as notas no fim estão conferidas no XML pelo teste `test_o_modo_png_as_notas_no_fim…` | — |

## Como conferir por automação (o que foi feito aqui)

O Word foi acionado por COM em PowerShell (`New-Object -ComObject Word.Application`,
invisível, `DisplayAlerts = 0`): `Documents.Open`, contagens (`Footnotes`, `Endnotes`,
`Fields`, `Bookmarks` com `ShowHidden`, `TablesOfContents`, `Hyperlinks`, `Lists`,
`InlineShapes`), `Fields.Update()`, `TablesOfContents(1).Update()` e
`ExportAsFixedFormat(pdf, 17)`; o PDF foi lido com o PyMuPDF (fontes usadas e páginas
rasterizadas). Um documento que o Word abre sem diálogo com `DisplayAlerts = 0` e
sem exceção é um documento que ele não considerou corrompido.

## Pendências honestas

- **LibreOffice** não está instalado nesta máquina: a coluna fica vazia até alguém
  abrir o `completo.docx` nele (Writer 7+) e preencher as vinte linhas.
- **Fontes embutidas numa máquina sem a SkakNew**: a linha 19 só confere de verdade
  onde a fonte não está instalada.
- `exportar.para_docx` (a exportação de hoje, F97/F99) dobra a oitava casa da SkakNew no
  mesmo Word — a folga de 1,5 pt entrou só no `docx_io`; a ED-12 decide se leva para lá
  (os testes F97/F99 fixam a largura exata em twips).
