"""
As constantes de estilo do livro — CSS, corpos, molduras, fontes (ED-00).

**Saíram de `core/exportar.py` sem mudar de nome.** O `exportar` importa
`core.livro`, que traz numpy, cv2 e o serviço de boxes; a CSS do EPUB e o corpo
do diagrama são só texto e números, e o editor de livros (`core/editor/`) precisa
deles num processo que não carrega o OCR (SPEC_EDITOR DEC-07). O `exportar` os
reimporta daqui, então `exportar.CSS`, `exportar.CORPO_PADRAO_PT`,
`exportar.classe_da_fonte` etc. continuam valendo para quem já os usava.

Os comentários vieram junto: são a medição que justifica cada número.
"""

from __future__ import annotations

CSS = """\
body { font-family: serif; line-height: 1.45; margin: 0 6%; }
p { margin: 0 0 0.35em; text-indent: 1.2em; text-align: justify; }
p.primeira { text-indent: 0; }
figure { margin: 1.2em 0; text-align: center; page-break-inside: avoid; }
img { max-width: 88%; height: auto; }
hr.pagina { border: 0; border-top: 1px solid #ccc; margin: 1.6em 0 1em; }
table { border-collapse: collapse; margin: 1.2em auto; width: 100%; }
td { border: 1px solid #666; padding: 0.3em 0.45em; vertical-align: top; }
td p { text-indent: 0; text-align: left; margin: 0; }
"""

#: O corpo do diagrama, em pontos **por casa** (F97).
#:
#: **A casa é o quadrado do em da fonte**, então o corpo é a casa e o tabuleiro
#: mede oito vezes isso: 16 pt dão 128 pt de lado, que são 4,5 cm — o diagrama
#: de coluna dos livros de xadrez. Era 9 cm fixos, que é o diagrama de página
#: inteira, e num livro de finais isso empurrava a prosa para a página seguinte.
#:
#: Vale para os dois modos e para os dois formatos, e é isso que o torna útil:
#: no modo de fonte ele é o corpo da letra, e no modo de imagem é o que dá a
#: largura da figura, pela `Figura.casas_de_largura`. Um livro em que o porteiro
#: mandou metade dos diagramas para o recorte sai com os dois do mesmo tamanho.
CORPO_PADRAO_PT = 16.0

#: O corpo é arredondado a este passo, em pontos.
#:
#: **Não é preciosismo: é o que mantém o tabuleiro quadrado no DOCX** — que é
#: exatamente o que se pede dele. O Word escreve o corpo em meios-pontos
#: (`w:sz`) e a entrelinha em twips (`w:line`), e o tabuleiro em texto só fecha
#: quando os dois dizem o **mesmo** número: entrelinha maior que o corpo abre
#: uma faixa branca entre as filas, e menor sobrepõe as casas. Um corpo de
#: 16,3 pt sairia como 16,5 no `w:sz` e 16,3 no `w:line`, e essa diferença de
#: 0,2 pt por fila é meio milímetro de vão no fim do tabuleiro. No passo de meio
#: ponto os dois campos são exatos, e a conta fecha.
PASSO_DO_CORPO_PT = 0.5

#: A moldura do tabuleiro **em texto**, na CSS do EPUB.
#:
#: Em `em`, e não em pontos, para acompanhar o corpo escolhido. O `double` do
#: CSS só se parte em dois filetes acima de uns 3 px, e é por isso que o dobro
#: aqui é mais que o dobro: abaixo disso o navegador desenha um traço grosso e
#: só. O `padding` afasta a moldura do tabuleiro como o vão do PNG afasta.
MOLDURA_NA_CSS = {
    "sem": "",
    "simples": "border: 0.06em solid #000; padding: 0.30em;",
    "dupla": "border: 0.16em double #000; padding: 0.24em;",
}

#: A quina redonda, na CSS do EPUB — acrescentada à moldura, e não no lugar
#: dela (F101).
#:
#: Em `em`, como a moldura, para acompanhar o corpo escolhido. O número é maior
#: que o raio do PNG de propósito: ali o filete encosta no tabuleiro, e aqui há
#: o `padding` entre um e outro, então a mesma quina precisa de uma curva mais
#: aberta para parecer a mesma.
RAIO_NA_CSS = {"sem": "", "simples": " border-radius: 0.20em;",
               "dupla": " border-radius: 0.40em;"}

#: A moldura do tabuleiro em texto, no DOCX: `(w:val, w:sz)` da borda da célula.
#: O `w:sz` é em oitavos de ponto, e o `double` do Word já são dois filetes.
#: `nil` é borda declarada como ausente, que não é o mesmo que borda omitida —
#: omitida, o estilo da tabela ainda pode pôr uma.
MOLDURA_NO_DOCX = {"sem": ("nil", 0), "simples": ("single", 6),
                   "dupla": ("double", 12)}

def corpo_valido(pt) -> float:
    """
    O corpo em pontos, conferido e arredondado ao `PASSO_DO_CORPO_PT`.

    Recusa o que não é número e o que não é positivo, em vez de deixar passar:
    um corpo zero escreveria um livro inteiro de tabuleiros invisíveis, e o
    arquivo abriria sem reclamar de nada.
    """
    try:
        valor = float(pt)
    except (TypeError, ValueError):
        raise ValueError(f"corpo inválido: {pt!r} (use um número de pontos)") from None
    if not valor > 0:
        raise ValueError(f"corpo inválido: {pt!r} (tem de ser maior que zero)")
    return round(valor / PASSO_DO_CORPO_PT) * PASSO_DO_CORPO_PT or PASSO_DO_CORPO_PT

#: Os dois jeitos de pôr o diagrama no arquivo (F59).
#:
#: **`png` é o padrão, e o motivo não é preguiça.** No modo `fonte` o tabuleiro
#: é texto de verdade — escala sem perder nada e pesa uns 200 bytes —, mas
#: depende de o leitor respeitar a fonte embutida. Leitor que força a fonte do
#: usuário (é opção de menu no Kindle e em vários outros) transforma o tabuleiro
#: em `rmblkans`. O PNG não tem essa aresta: quem abre o arquivo não precisa da
#: fonte.
#:
#: **Não é o mesmo eixo do `diagramas` do `livro`.** Lá se decide se o diagrama
#: *nasce* desenhado ou recortado (F58); aqui, se o desenho *sai* como imagem ou
#: como texto. Os valores não se cruzam de propósito: passar um pelo outro
#: levanta erro na hora, em vez de escrever um arquivo estranho.
MODOS_DE_DIAGRAMA = ("png", "fonte")

#: O tabuleiro em texto, no EPUB.
#:
#: `line-height: 1` e `letter-spacing: 0` **não são estilo, são a montagem**: a
#: casa é o quadrado do em da fonte, então qualquer entrelinha ou espaçamento
#: abre uma linha branca entre as filas. O `text-indent: 0` desfaz o recuo de
#: parágrafo que o corpo do livro usa, e que aqui empurraria a primeira fila.
#:
#: **O `display: table` é o que alinha a fileira de letras com as colunas.** Com
#: as linhas centradas uma a uma, a das letras `a`–`h` — que é feita de caixas
#: de 1 em, e não de glifos — fica 1,3 px fora das casas, medido no navegador:
#: as duas linhas têm larguras que diferem por um arredondamento, e centrar cada
#: uma reparte essa diferença pela metade. Encaixotar tudo num bloco que encolhe
#: até o conteúdo e centrar **o bloco** faz as duas começarem no mesmo x.
#:
#: **O `!important` da entrelinha é o único do arquivo, e ele é o pedido.** Um
#: tabuleiro de fonte só é quadrado se a linha medir exatamente o corpo — a casa
#: é o quadrado do em —, e vários leitores impõem entrelinha de leitura ao livro
#: inteiro por preferência do usuário. No corpo do texto isso é bem-vindo; nas
#: oito linhas do tabuleiro abre uma faixa branca entre as filas e o diagrama
#: deixa de fechar. Só estas oito linhas se defendem, e o resto do livro
#: continua obedecendo ao leitor.
#:
#: **A moldura mora numa classe à parte porque nem todo diagrama a quer por
#: fora** (F99). O que sai com coordenada numa fonte que tem glifo de borda já
#: traz o filete dentro do próprio texto, e uma borda de CSS por cima seria a
#: segunda moldura. A folha é do livro inteiro e a decisão é de cada figura, e é
#: por isso que ela é uma classe e não uma regra em `div.diagrama`.
CSS_DO_DIAGRAMA = """\
div.diagrama { display: table; margin: 1.2em auto; page-break-inside: avoid; }
div.diagrama.caixa { %(moldura)s }
div.diagrama p { font-family: monospace; font-size: %(corpo)spt;
  line-height: 1 !important; letter-spacing: 0; margin: 0; padding: 0;
  text-indent: 0; text-align: left; white-space: pre; }
div.diagrama span.rot { display: inline-block; width: 0.92em; text-align: right;
  padding-right: 0.12em; }
div.diagrama span.col { display: inline-block; width: 1em; text-align: center; }
div.diagrama i { font-family: serif; font-style: normal; font-size: 0.4em;
  vertical-align: 0.35em; }
"""

#: A fonte de xadrez, e a regra que a liga aos diagramas **dela** (F99).
#:
#: **Sai uma vez por fonte, e por isso a família não pode morar na regra geral.**
#: Enquanto havia uma fonte só, `div.diagrama p { font-family: … }` repetida
#: dizia sempre a mesma coisa. Com duas, a segunda cópia venceria a primeira em
#: cascata e o livro inteiro sairia na última fonte declarada — inclusive os
#: diagramas desenhados com a outra. A regra é escolhida pela classe da figura,
#: que é a única coisa que sabe de que fonte cada diagrama saiu.
CSS_DA_FONTE_DO_DIAGRAMA = """\
@font-face { font-family: "%(familia)s"; font-weight: normal; font-style: normal;
  src: url("fonts/%(arquivo)s"); }
div.diagrama.%(classe)s p { font-family: "%(familia)s", monospace; }
"""

def classe_da_fonte(nome: str) -> str:
    """O nome da fonte como classe de CSS — o que não serve vira `-`."""
    seguro = "".join(c if (c.isascii() and (c.isalnum() or c in "-_")) else "-"
                     for c in nome)
    return f"fonte-{seguro}"

#: Extensão → tipo de mídia da fonte, como o EPUB 3 os nomeia.
TIPOS_DE_FONTE = {".otf": "font/otf", ".ttf": "font/ttf", ".woff": "font/woff"}

#: Abaixo disto o caractere não precisa da fonte de recurso.
#:
#: **É o corte entre "letra" e "símbolo", e ele foi medido no alfabeto do
#: modelo** (230 classes, 40 delas fora do ASCII). Abaixo de U+2000 estão `©`,
#: `±`, `²`, `½` e as letras acentuadas — que qualquer fonte de texto desenha, e
#: que ficariam feias numa fonte de símbolos. Acima estão as figurinas e os
#: sinais de xadrez, e ali a fonte do leitor é moeda: medido, a Times New Roman
#: não tem uma figurina sequer, e a DejaVu Serif também não.
PISO_DO_SIMBOLO = 0x2000

#: O idioma que vai no `dc:language` do EPUB.
#:
#: **É o idioma do livro, e não o do programa** — a mesma distinção que a §5.8
#: da SPEC faz para o léxico (`lexico.idioma`, "en", com a nota "o idioma dos
#: livros, não o do programa"). Era `"pt"` fixo, e todo livro do Yusupov saía
#: declarado em português: o leitor de tela lia notação inglesa com fonemas
#: portugueses, e a hifenização do EPUB quebrava as palavras pelas regras
#: erradas.
IDIOMA_PADRAO = "en"

CSS_DOS_SIMBOLOS = """\
@font-face { font-family: "%(familia)s"; font-weight: normal; font-style: normal;
  src: url("fonts/%(arquivo)s"); }
span.sim { font-family: "%(familia)s", serif; }
"""

#: O que este módulo exporta com o nome de sempre em `core/exportar.py`.
__all__ = [
    "CSS", "CORPO_PADRAO_PT", "PASSO_DO_CORPO_PT", "MOLDURA_NA_CSS", "RAIO_NA_CSS",
    "MOLDURA_NO_DOCX", "corpo_valido", "MODOS_DE_DIAGRAMA", "CSS_DO_DIAGRAMA",
    "CSS_DA_FONTE_DO_DIAGRAMA", "classe_da_fonte", "TIPOS_DE_FONTE", "PISO_DO_SIMBOLO",
    "IDIOMA_PADRAO", "CSS_DOS_SIMBOLOS",
]
