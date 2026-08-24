"""
EPUB e DOCX a partir do que o `livro` extraiu (F2.6).

Os dois formatos saem do **mesmo intermediário** — a lista de `PaginaExtraida`
—, e é de propósito: o trabalho difícil é ler a página, não escrever o arquivo.
Trocar de formato aqui custa uma função; trocar a extração custaria o módulo
inteiro.

**EPUB sai com a biblioteca padrão.** Um EPUB é um zip com XHTML dentro, e
escrevê-lo à mão são cem linhas — contra uma dependência a mais no
`requirements.txt`, que este projeto recusa quando não precisa (ver a nota do
`pyspellchecker` no ROADMAP). O DOCX é o contrário: o OOXML tem relacionamento,
tipo de conteúdo e parte de mídia para cada imagem, e errar um detalhe dá um
arquivo que o Word recusa abrir sem dizer por quê. Ali a dependência
(`python-docx`) paga.
"""

import html
import os
import zipfile
from typing import List, Optional, Sequence, Tuple

import fitz

from core.livro import Figura, PaginaExtraida, Paragrafo, Tabela
from core.render_diagrama import MOLDURA_PADRAO, normalizar_moldura

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def largura_em_pt(figura: Figura, corpo_pt: float) -> Optional[float]:
    """
    A largura desta figura na página, em pontos — ou `None` se não dá para saber.

    `None` é a página que virou imagem inteira: ali não há tabuleiro por dentro,
    e o corpo por casa não diz nada sobre o tamanho dela.
    """
    if not figura.casas_de_largura:
        return None
    return round(figura.casas_de_largura * corpo_pt, 2)


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

#: O recorte da fonte de símbolos, com os glifos que o modelo sabe ler.
#:
#: 5,2 KB contra os 641 da fonte inteira, e os mesmos 15 símbolos. Sai do
#: `gerar_fonte_de_simbolos.py`, que roda à mão e versiona o produto; se ele não
#: existir, ou se o alfabeto crescer além dele, o `fonte_dos_simbolos` cai
#: sozinho para a fonte inteira.
SUBSET_DOS_SIMBOLOS = os.path.join(_RAIZ, "assets", "fonts",
                                   "SimbolosDeXadrez.ttf")

CSS_DOS_SIMBOLOS = """\
@font-face { font-family: "%(familia)s"; font-weight: normal; font-style: normal;
  src: url("fonts/%(arquivo)s"); }
span.sim { font-family: "%(familia)s", serif; }
"""

_CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _alternativo(figura: Figura) -> str:
    """
    O texto alternativo da figura — o FEN, quando ele existe.

    **É acessibilidade e busca no mesmo campo.** Um diagrama redesenhado sabe a
    posição que desenhou; pô-la no `alt` faz o leitor de tela dizer algo além de
    "imagem" e faz o tabuleiro aparecer numa busca por FEN. O recorte não sabe
    de nada, e por isso continua com o rótulo genérico.
    """
    if figura.origem == "faixa":
        return "Cabeçalho do diagrama"
    return figura.fen or "Diagrama"


def em_fonte(figura: Figura) -> bool:
    """Esta figura pode sair como texto? Só o desenho pode; o recorte, nunca."""
    return bool(figura.linhas and figura.fonte)


def _diagrama_em_texto(figura: Figura) -> str:
    """
    O tabuleiro como oito linhas de texto na fonte de xadrez.

    As coordenadas entram em **fonte de texto**, e não é escolha: a
    SkakNew-Diagram tem 46 codepoints e nenhum deles é `a`–`h`, `7` ou `8` — as
    letras que sobrariam para rótulo desenham casa. Daí o `<i>` dentro do
    `<span>`: o `span` mede uma casa na fonte do tabuleiro, e o `i` desenha o
    rótulo pequeno, centrado nela.
    """
    from core import render_diagrama

    titulo_do_alt = html.escape(_alternativo(figura))
    familia = classe_da_fonte(figura.fonte or "")
    if figura.linhas_emolduradas:
        # Dez linhas de dez caracteres, e nada em volta: o filete e o `a`–`h`
        # são glifos da mesma fonte (F99). É o caso simples, e o que o resto
        # desta função existe para contornar quando a fonte não o permite.
        miolo = "\n".join(f"<p>{linha}</p>" for linha in figura.linhas or [])
        return (f'<div class="diagrama {familia}" title="{titulo_do_alt}" '
                f'aria-label="{titulo_do_alt}" role="img">\n{miolo}\n</div>')

    # Os rótulos saem do mesmo lugar que os do PNG, e não de uma lista escrita
    # aqui: o diagrama impresso do lado das pretas tem as `linhas` giradas
    # (F95), e um `a`–`h` fixo rotularia `h8` como `a1` sem nada denunciar.
    letras, filas = render_diagrama.rotulos(figura.orientacao)
    linhas = []
    for i, linha in enumerate(figura.linhas or []):
        if figura.coordenadas:
            linha = f'<span class="rot"><i>{filas[i]}</i></span>{linha}'
        linhas.append(f"<p>{linha}</p>")
    if figura.coordenadas:
        # A classe é obrigatória, e não enfeite: um seletor por elemento
        # (`p.colunas span`) pegava junto o `span.rot` desta mesma linha e o
        # alargava de 0,92 em para 1 em — 2,69 px medidos no navegador, que é o
        # tabuleiro andando para um lado e as letras para o outro.
        colunas = "".join(f'<span class="col"><i>{c}</i></span>' for c in letras)
        linhas.append(f'<p class="colunas"><span class="rot"></span>'
                      f'{colunas}</p>')
    return (f'<div class="diagrama caixa {familia}" title="{titulo_do_alt}" '
            f'aria-label="{titulo_do_alt}" role="img">\n' + "\n".join(linhas)
            + "\n</div>")


def _xhtml_da_pagina(pagina: PaginaExtraida, imagens: Sequence[str],
                     diagramas: str = "png", simbolos: str = "",
                     idioma: str = IDIOMA_PADRAO,
                     corpo_pt: float = CORPO_PADRAO_PT) -> str:
    corpo, i = [], 0
    primeiro = True
    for bloco in pagina.blocos:
        if isinstance(bloco, Tabela):
            # **Sem `<th>`, e não é descuido.** Nada aqui sabe se a primeira
            # fila é cabeçalho: o que se mediu foi a grade, e a grade não diz o
            # que a célula significa. Marcar cabeçalho por posição erraria em
            # toda tabela que começa com dado — e o leitor de tela anunciaria
            # "coluna: W: Win" como se fosse título (F72).
            filas = []
            for fila in bloco.linhas:
                celulas = "".join(
                    f"<td>{_com_simbolos(c, simbolos) if simbolos else html.escape(c)}</td>"
                    for c in fila)
                filas.append(f"<tr>{celulas}</tr>")
            corpo.append("<table>\n" + "\n".join(filas) + "\n</table>")
            primeiro = True
        elif isinstance(bloco, Figura):
            if diagramas == "fonte" and em_fonte(bloco):
                corpo.append(_diagrama_em_texto(bloco))
            else:
                # A largura vai no próprio `img`, e não na CSS: o corpo por casa
                # é do livro, mas quantas casas a figura tem é de cada figura
                # (F97). O `max-width` da folha continua de rede para a tela
                # estreita.
                pt = largura_em_pt(bloco, corpo_pt)
                estilo = f' style="width:{pt:g}pt"' if pt else ""
                corpo.append(f'<figure><img src="{imagens[i]}"{estilo} '
                             f'alt="{html.escape(_alternativo(bloco))}"/></figure>')
            i += 1
            primeiro = True
        else:
            texto = (_com_simbolos(bloco.texto, simbolos) if simbolos
                     else html.escape(bloco.texto))
            if bloco.titulo:
                # O `titulo` existe na `Paragrafo` desde a F2.6 e os dois
                # exportadores o ignoravam: todo cabeçalho saía como parágrafo
                # comum, e sem `<h2>` o sumário do leitor não tem por onde
                # navegar. Hoje nada o marca — a marcação é trabalho de quem
                # detectar título na página —, mas o campo deixou de ser letra
                # morta do lado de cá.
                corpo.append(f"<h2>{texto}</h2>")
                primeiro = True
                continue
            classe = ' class="primeira"' if primeiro else ""
            corpo.append(f"<p{classe}>{texto}</p>")
            primeiro = False
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" '
        f'xml:lang="{html.escape(idioma)}">\n'
        f"<head><title>Página {pagina.numero + 1}</title>"
        '<link rel="stylesheet" type="text/css" href="estilo.css"/></head>\n'
        "<body>\n" + "\n".join(corpo) + "\n</body>\n</html>\n"
    )


def _familia(caminho: str) -> str:
    """
    O nome da família, como a CSS e o Word a pedem.

    O `fitz` devolve `'Noto Sans Symbols2 Regular'` — com o estilo no fim —, e
    família é `'Noto Sans Symbols2'`, que é o mesmo nome que `ui/fontes.py`
    registra no Windows para a tela poder pedi-la.
    """
    nome = fitz.Font(fontfile=caminho).name
    for estilo in (" Regular", " Book", " Normal"):
        if nome.endswith(estilo):
            return nome[:-len(estilo)]
    return nome


def fonte_dos_simbolos(texto: str) -> Optional[Tuple[str, str, str]]:
    """
    (família, caminho, caracteres) da fonte de recurso que este texto precisa.

    **Só embute quando faz falta, e a falta é medida no próprio texto.** A
    `NotoSansSymbols2` tem 641 KB e serve para 14 dos 40 símbolos do alfabeto do
    modelo; um livro que não traga nenhum deles não deve carregá-la.

    A escolha da fonte não é nova: é a `FONTES_DE_SIMBOLO` da §4.2 da SPEC, a
    mesma que o PDF pesquisável usa, e pelo mesmo motivo — medidas as 559
    famílias deste sistema, o bloco de anotação de xadrez do Unicode 11 não
    existe em nenhuma outra.

    **O subset vem primeiro, e a fonte inteira fica de rede.** O recorte tem 5,2
    KB contra 641, e cobre os mesmos 15 símbolos — mas ele é produto de um
    script que roda à mão (`gerar_fonte_de_simbolos.py`), e alfabeto de modelo
    cresce. Escolher pela cobertura, e não pela ordem, faz o dia em que o modelo
    aprender um símbolo novo custar 641 KB no arquivo em vez de um quadradinho
    na página.
    """
    from core.chess_pdf_processor import FONTES_DE_SIMBOLO

    precisa = sorted({c for c in texto if ord(c) >= PISO_DO_SIMBOLO})
    if not precisa:
        return None

    melhor = None
    for caminho in [SUBSET_DOS_SIMBOLOS] + list(FONTES_DE_SIMBOLO):
        if not os.path.exists(caminho):
            continue
        fonte = fitz.Font(fontfile=caminho)
        cobertos = "".join(c for c in precisa if fonte.has_glyph(ord(c)))
        if cobertos and (melhor is None or len(cobertos) > len(melhor[2])):
            melhor = (_familia(caminho), caminho, cobertos)
        if melhor and len(melhor[2]) == len(precisa):
            break
    return melhor


def _com_simbolos(texto: str, simbolos: str) -> str:
    """
    O texto com os símbolos embrulhados no `<span>` da fonte de recurso.

    Embrulha **corridos**, e não um a um: `♗xb7` tem uma figurina só, mas
    `♕xd5 ♖e1` tem duas seguidas em outros trechos, e um `<span>` por caractere
    dobraria o tamanho do XHTML sem mudar um pixel.
    """
    saida, corrente = [], []
    for ch in texto:
        if ch in simbolos:
            corrente.append(ch)
            continue
        if corrente:
            saida.append(f'<span class="sim">{html.escape("".join(corrente))}</span>')
            corrente = []
        saida.append(html.escape(ch))
    if corrente:
        saida.append(f'<span class="sim">{html.escape("".join(corrente))}</span>')
    return "".join(saida)


def fontes_usadas(paginas: Sequence[PaginaExtraida]) -> dict:
    """`{nome da fonte: caminho do arquivo}` das figuras que podem sair em texto."""
    from core import render_diagrama

    nomes = {b.fonte for p in paginas for b in p.blocos
             if isinstance(b, Figura) and em_fonte(b)}
    return {nome: render_diagrama.carregar(nome).arquivo
            for nome in sorted(n for n in nomes if n)}


def para_epub(paginas: Sequence[PaginaExtraida], caminho: str, *,
              titulo: str = "Livro", autor: str = "",
              identificador: str = "pyboxeditor",
              diagramas: str = "png", idioma: str = IDIOMA_PADRAO,
              corpo_pt: float = CORPO_PADRAO_PT,
              moldura=MOLDURA_PADRAO) -> str:
    """
    Escreve o EPUB. Devolve o caminho.

    O `mimetype` vai **primeiro e sem compressão**, que é a única exigência
    posicional do formato: leitor que valide o arquivo procura a assinatura nos
    primeiros bytes, e um zip que comprima essa entrada é recusado.

    Em `diagramas="fonte"` o tabuleiro sai como texto e a fonte de xadrez vai
    embutida — o que a licença da SkakNew-Diagram (LPPL 1.2+) permite. Quem não
    tem texto para sair, sai como imagem do mesmo jeito: o recorte do scan não
    vira letra.

    `corpo_pt` é o tamanho da **casa**, em pontos, e vale nos dois modos: no de
    fonte é o corpo da letra, no de imagem é o que dá a largura da figura (F97).
    `moldura` só tem efeito no modo de fonte — no de imagem ela já veio
    desenhada dentro do PNG.
    """
    if diagramas not in MODOS_DE_DIAGRAMA:
        raise ValueError(f"modo de diagrama inválido: {diagramas!r} "
                         f"(use um de {MODOS_DE_DIAGRAMA})")
    # A moldura do modo de imagem já veio desenhada no PNG (é o `livro` que a
    # pede ao renderizador); aqui ela só tem trabalho no modo de fonte. Mas é
    # conferida nos dois, para um erro de digitação não passar batido no livro
    # em que ela não teria efeito.
    moldura = normalizar_moldura(moldura)
    corpo_pt = corpo_valido(corpo_pt)

    embutidas = fontes_usadas(paginas) if diagramas == "fonte" else {}

    # A fonte dos símbolos entra nos **dois** modos, e não é opção: as figurinas
    # e os sinais de avaliação estão no texto corrido, não no diagrama. Medido no
    # alfabeto do modelo, a Times New Roman não desenha uma figurina sequer.
    recurso = fonte_dos_simbolos("".join(p.texto for p in paginas))
    simbolos = recurso[2] if recurso else ""

    arquivos, imagens_por_pagina = [], []
    for pagina in paginas:
        nomes = []
        for j, bloco in enumerate(b for b in pagina.blocos if isinstance(b, Figura)):
            if diagramas == "fonte" and em_fonte(bloco):
                # Sai como texto: não há PNG para pôr no zip nem no manifesto.
                # O lugar na lista fica, porque o índice é o da figura.
                nomes.append(None)
                continue
            nome = f"imagens/fig-{pagina.numero + 1:04d}-{j + 1}.png"
            arquivos.append((f"OEBPS/{nome}", bloco.png))
            nomes.append(nome)
        imagens_por_pagina.append(nomes)

    css = CSS
    fontes_no_zip = dict(embutidas)
    if embutidas:
        css += CSS_DO_DIAGRAMA % {"corpo": f"{corpo_pt:g}",
                                  "moldura": MOLDURA_NA_CSS[moldura]}
    for nome, origem in embutidas.items():
        css += CSS_DA_FONTE_DO_DIAGRAMA % {
            "familia": nome, "arquivo": os.path.basename(origem),
            "classe": classe_da_fonte(nome)}
    if recurso:
        fontes_no_zip[recurso[0]] = recurso[1]
        css += CSS_DOS_SIMBOLOS % {"familia": recurso[0],
                                   "arquivo": os.path.basename(recurso[1])}
    for origem in fontes_no_zip.values():
        with open(origem, "rb") as f:
            arquivos.append((f"OEBPS/fonts/{os.path.basename(origem)}", f.read()))

    capitulos = []
    for pagina, imagens in zip(paginas, imagens_por_pagina):
        nome = f"pagina-{pagina.numero + 1:04d}.xhtml"
        capitulos.append(nome)
        arquivos.append((f"OEBPS/{nome}",
                         _xhtml_da_pagina(pagina, imagens, diagramas, simbolos,
                                          idioma, corpo_pt).encode("utf-8")))

    itens = [f'<item id="c{i}" href="{n}" media-type="application/xhtml+xml"/>'
             for i, n in enumerate(capitulos)]
    itens += [f'<item id="img{i}" href="{n[len("OEBPS/"):]}" media-type="image/png"/>'
              for i, (n, _d) in enumerate(arquivos) if n.endswith(".png")]
    itens += [f'<item id="fnt{i}" href="fonts/{os.path.basename(o)}" '
              f'media-type="{TIPOS_DE_FONTE.get(os.path.splitext(o)[1].lower(), "font/otf")}"/>'
              for i, o in enumerate(fontes_no_zip.values())]
    itens.append('<item id="css" href="estilo.css" media-type="text/css"/>')
    itens.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
                 'properties="nav"/>')
    espinha = "".join(f'<itemref idref="c{i}"/>' for i in range(len(capitulos)))

    # O `ibooks:specified-fonts` é o que faz o Apple Books respeitar a fonte
    # embutida em vez de trocá-la pela do leitor. Sem ele o tabuleiro sai como
    # `rmblkans` lá, e só lá — que é o pior tipo de defeito de formato.
    prefixo = (' prefix="ibooks: http://vocabulary.itunes.apple.com/rdf/ibooks/'
               'vocabulary-extensions-1.0/"' if fontes_no_zip else "")
    ibooks = ('<meta property="ibooks:specified-fonts">true</meta>\n'
              if fontes_no_zip else "")

    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        f'unique-identifier="pub-id"{prefixo}>\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f'<dc:identifier id="pub-id">{html.escape(identificador)}</dc:identifier>\n'
        f"<dc:title>{html.escape(titulo)}</dc:title>\n"
        f'<dc:language>{html.escape(idioma)}</dc:language>\n'
        + (f"<dc:creator>{html.escape(autor)}</dc:creator>\n" if autor else "")
        + '<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>\n'
        + ibooks
        + "</metadata>\n<manifest>\n" + "\n".join(itens) + "\n</manifest>\n"
        f"<spine>{espinha}</spine>\n</package>\n"
    )

    nav = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
           '<html xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Sumário</title>'
           "</head><body><nav epub:type=\"toc\"><h1>Sumário</h1><ol>"
           + "".join(f'<li><a href="{n}">Página {i + 1}</a></li>'
                     for i, n in enumerate(capitulos))
           + "</ol></nav></body></html>\n")

    pasta = os.path.dirname(os.path.abspath(caminho))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", _CONTAINER)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/estilo.css", css)
        for nome, dados in arquivos:
            z.writestr(nome, dados)
    return caminho


#: A chave do XOR que ofusca a fonte embutida no DOCX. É **fixa de propósito**:
#: o valor não protege nada — ele viaja no próprio arquivo, dentro do
#: `w:fontKey` —, e um GUID sorteado a cada execução faria dois DOCX do mesmo
#: livro diferirem byte a byte sem diferirem em nada.
GUID_DA_FONTE = "{B0C5A7D2-3E14-4F68-9A2B-7C6D5E4F3A21}"

#: Como o OOXML chama uma fonte embutida.
TIPO_OFUSCADO = "application/vnd.openxmlformats-officedocument.obfuscatedFont"
REL_DE_FONTE = ("http://schemas.openxmlformats.org/officeDocument/2006/"
                "relationships/font")


def ofuscar(dados: bytes, guid: str = GUID_DA_FONTE) -> bytes:
    """
    A fonte no formato que o Word embute (ECMA-376 §15.2.13).

    **Não é criptografia, e não pretende ser**: os 32 primeiros bytes do arquivo
    saem em XOR com os 16 bytes do GUID, aplicados duas vezes, e o GUID vai
    escrito ao lado no `fontTable.xml`. Serve para que o arquivo dentro do zip
    não seja uma fonte instalável com um duplo clique — é uma trava de
    conveniência, não de licença.

    Os bytes do GUID entram **na ordem inversa** da representação em texto. É a
    parte que se erra em silêncio: um arquivo ofuscado com a ordem trocada
    continua sendo um zip válido, e só o Word reclama, na hora de abrir.
    """
    chave = bytes.fromhex(guid.strip("{}").replace("-", ""))[::-1]
    cabeca = bytearray(dados[:32])
    for i in range(len(cabeca)):
        cabeca[i] ^= chave[i % len(chave)]
    return bytes(cabeca) + dados[32:]


def _inserir(texto: str, marca: str, trecho: str) -> str:
    """Insere `trecho` **antes** da primeira ocorrência de `marca`."""
    corte = texto.index(marca)
    return texto[:corte] + trecho + texto[corte:]


def _embutir_fontes_no_docx(caminho: str, fontes: dict) -> None:
    """
    Põe as fontes dentro do .docx, do jeito que o Word as espera.

    **Sai pela camada do zip, e não pela do `python-docx`.** A biblioteca sabe
    acrescentar parte e relacionamento, mas escreve o tipo de conteúdo como
    `Override` por nome de parte, enquanto o Word escreve `Default` por extensão
    — e aqui a diferença não se testa sem o Word na mão. Reescrever o zip custa
    trinta linhas e produz exatamente o que ele produz.

    São quatro costuras, e faltar qualquer uma dá um arquivo que abre sem a
    fonte (ou não abre):

        [Content_Types].xml         a extensão `.odttf` e o tipo dela
        word/fonts/fonteN.odttf     a fonte, ofuscada
        word/fontTable.xml (+rels)  o nome da família ligado ao arquivo
        word/settings.xml           `w:embedTrueTypeFonts`, sem o qual o Word
                                    ignora tudo o que está acima
    """
    with zipfile.ZipFile(caminho) as z:
        itens = [(info.filename, z.read(info.filename)) for info in z.infolist()]
    conteudo = dict(itens)

    tipos = conteudo["[Content_Types].xml"].decode("utf-8")
    if "odttf" not in tipos:
        # **Depois da tag de abertura do `<Types>`, e não depois do primeiro
        # `>` do arquivo**, que é o fim da declaração XML — ali o `<Default>`
        # vira um segundo elemento na raiz, e o arquivo deixa de ser XML. O Word
        # engole; o `python-docx` não, e foi ele que acusou.
        abertura = tipos.index(">", tipos.index("<Types")) + 1
        tipos = (tipos[:abertura] + f'<Default Extension="odttf" '
                 f'ContentType="{TIPO_OFUSCADO}"/>' + tipos[abertura:])
        conteudo["[Content_Types].xml"] = tipos.encode("utf-8")

    tabela = conteudo["word/fontTable.xml"].decode("utf-8")
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships">']
    for i, (nome, origem) in enumerate(sorted(fontes.items()), start=1):
        alvo = f"fonte{i}.odttf"
        with open(origem, "rb") as f:
            conteudo[f"word/fonts/{alvo}"] = ofuscar(f.read())
        rels.append(f'<Relationship Id="rIdFonte{i}" Type="{REL_DE_FONTE}" '
                    f'Target="fonts/{alvo}"/>')
        tabela = _inserir(
            tabela, "</w:fonts>",
            f'<w:font w:name="{nome}">'
            f'<w:embedRegular r:id="rIdFonte{i}" w:fontKey="{GUID_DA_FONTE}"/>'
            f"</w:font>")
    rels.append("</Relationships>")

    conteudo["word/fontTable.xml"] = tabela.encode("utf-8")
    conteudo["word/_rels/fontTable.xml.rels"] = "".join(rels).encode("utf-8")

    ajustes = conteudo["word/settings.xml"].decode("utf-8")
    if "embedTrueTypeFonts" not in ajustes:
        # A ordem dos elementos de `CT_Settings` é fixa no esquema, e este vem
        # logo depois do `w:zoom` — fora de lugar, o Word acusa arquivo corrompido.
        marca = "/>" if "<w:zoom" in ajustes else ">"
        alvo = ajustes.index("<w:zoom") if "<w:zoom" in ajustes else 0
        corte = ajustes.index(marca, alvo) + len(marca)
        ajustes = ajustes[:corte] + "<w:embedTrueTypeFonts/>" + ajustes[corte:]
        conteudo["word/settings.xml"] = ajustes.encode("utf-8")

    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, dados in conteudo.items():
            z.writestr(nome, dados)


def _caixa_do_diagrama(doc, moldura: str, largura_pt: float):
    """
    A célula de largura fixa onde o tabuleiro em texto mora (F97, F98).

    **Uma tabela de uma célula, e não borda de parágrafo.** A borda de parágrafo
    do Word corre de margem a margem da coluna de texto: ela emolduraria a
    página, não o diagrama, que é estreito. A tabela mede o tabuleiro, centra-se
    na coluna, e a borda dela cai onde o filete do PNG cai.

    **E ela existe mesmo sem moldura, o que não é desperdício — é o alinhamento
    (F98).** Antes as oito filas eram parágrafos centrados soltos, e isso só
    funcionava porque a casa vazia da SkakNew-Diagram é o `0` e o `Z`. A casa
    clara vazia da Chess Merida é o **espaço**, e o Word não conta espaço no fim
    da linha para centrar: a fila `"+ + +o+ "` seria medida com sete casas e a
    `" + WlV +"` com oito, e o tabuleiro sairia em escada, meia casa por fila.
    Numa caixa da largura exata do tabuleiro, as filas saem alinhadas à esquerda
    e o espaço deixa de ter voz no alinhamento.

    A largura é escrita **três vezes** — `tblW`, `w:gridCol` e `tcW` —, com
    `tblLayout` fixo. É o que tira o autoajuste do caminho: em autoajuste quem
    decide a largura é o Word, na hora de abrir, e uma célula mais larga que o
    tabuleiro poria a moldura longe dele.

    A borda vai no `w:tcPr` e não no `w:tblPr` porque a ordem dos filhos do
    `tblPr` é fixa no esquema e o `python-docx` já escreve o `tblLook` no fim
    dele — acrescentar depois dá um arquivo que o Word abre reclamando. No
    `tcPr` a ordem que interessa é `tcW`, `tcBorders`, `tcMar`, e é essa que sai
    daqui.

    A margem da célula é zerada de propósito: o padrão do Word é 0,19 cm dos
    dois lados, e ela afastaria a moldura do tabuleiro de um jeito que o PNG não
    faz — o mesmo diagrama sairia com dois enquadramentos conforme o modo.

    O `w:cantSplit` é de graça e resolve o que o `page-break-inside: avoid` do
    EPUB resolve lá: tabuleiro partido entre duas páginas.
    """
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    val, sz = MOLDURA_NO_DOCX[moldura]
    largura = Pt(largura_pt)
    tabela = doc.add_table(rows=1, cols=1)
    tabela.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabela.autofit = False
    tabela.columns[0].width = largura
    # O `python-docx` deixa o `tblW` em `auto w=0`, e com `tblLayout` fixo o
    # Word ainda usaria a grade — mas "três vezes a mesma largura" só é verdade
    # se esta também disser.
    tblw = tabela._tbl.tblPr.find(qn("w:tblW"))
    if tblw is not None:
        tblw.set(qn("w:type"), "dxa")
        tblw.set(qn("w:w"), str(int(largura.twips)))

    linha = tabela.rows[0]
    linha.height = None
    linha._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))

    celula = tabela.cell(0, 0)
    celula.width = largura
    props = celula._tc.get_or_add_tcPr()
    bordas = OxmlElement("w:tcBorders")
    for lado in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{lado}")
        b.set(qn("w:val"), val)
        b.set(qn("w:sz"), str(sz))
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "000000")
        bordas.append(b)
    props.append(bordas)
    margens = OxmlElement("w:tcMar")
    for lado in ("top", "left", "bottom", "right"):
        m = OxmlElement(f"w:{lado}")
        m.set(qn("w:w"), "0")
        m.set(qn("w:type"), "dxa")
        margens.append(m)
    props.append(margens)
    return celula


def para_docx(paginas: Sequence[PaginaExtraida], caminho: str, *,
              titulo: str = "Livro", autor: str = "",
              largura_figura_cm: float = 9.0,
              diagramas: str = "png",
              corpo_pt: float = CORPO_PADRAO_PT,
              moldura=MOLDURA_PADRAO) -> str:
    """
    Escreve o DOCX. Devolve o caminho.

    A figura entra com largura medida, e não no tamanho em pixels: o recorte sai
    a 300 dpi e teria 700 px de largura, que o Word põe como 700 pontos e
    estoura a página. Quem manda na medida é o `corpo_pt` — o tamanho da casa —,
    pela `Figura.casas_de_largura`; o `largura_figura_cm` ficou para a figura
    que não tem tabuleiro por dentro, que é a página inteira virada imagem.

    Em `diagramas="fonte"` o tabuleiro sai como parágrafos de texto na fonte de
    xadrez, que vai embutida — oito, ou dez quando as linhas já trazem a moldura
    e as coordenadas em glifo (F99). **Diagrama com coordenadas numa fonte que
    não tem esses glifos continua saindo em imagem** mesmo nesse modo: alinhar
    rótulo de outra fonte sobre as casas exigiria uma tabela de 81 células por
    diagrama — no EPUB isso são três linhas de CSS, aqui não.

    `moldura` (F97) só tem efeito nesse mesmo modo, pela `_caixa_do_diagrama`, e
    só quando o texto não traz a sua: no modo de imagem o filete já veio
    desenhado dentro do PNG, e no de fonte emoldurada ele está no próprio texto.
    """
    if diagramas not in MODOS_DE_DIAGRAMA:
        raise ValueError(f"modo de diagrama inválido: {diagramas!r} "
                         f"(use um de {MODOS_DE_DIAGRAMA})")
    moldura = normalizar_moldura(moldura)
    corpo_pt = corpo_valido(corpo_pt)

    import io as _io
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    def em_texto(bloco: Figura) -> bool:
        """
        Esta figura sai como texto?

        **Diagrama com coordenada saía sempre em imagem, e desde a F99 não
        mais** — quando a fonte tem os glifos de borda com rótulo, as dez linhas
        já trazem o `a`–`h` e o `8`–`1` desenhados, e não há o que alinhar. Com
        a SkakNew-Diagram continua caindo para imagem: a fonte tem 46 codepoints
        e nenhum deles é `a`–`h`, `7` ou `8`, e pôr rótulo de outra fonte sobre
        as casas exigiria uma tabela de 81 células por diagrama.
        """
        if not (diagramas == "fonte" and em_fonte(bloco)):
            return False
        return bloco.linhas_emolduradas or not bloco.coordenadas

    def familia_do_run(run, familia: str) -> None:
        """O `w:rFonts` tem quatro atributos, e o `font.name` só escreve um."""
        run.font.name = familia
        fontes = run._element.get_or_add_rPr().get_or_add_rFonts()
        for atributo in ("hAnsi", "cs", "eastAsia"):
            fontes.set(qn(f"w:{atributo}"), familia)

    recurso = fonte_dos_simbolos("".join(p.texto for p in paginas))
    simbolos = recurso[2] if recurso else ""

    def escrever_paragrafo(texto: str):
        """
        Um parágrafo, com os símbolos em runs de outra fonte.

        **No DOCX não há `unicode-range`**: a fonte é atributo do run, então o
        texto tem de ser partido onde a família muda. Partir por corridos e não
        por caractere mantém o XML legível e o arquivo menor.
        """
        p = doc.add_paragraph()
        if not simbolos:
            p.add_run(texto)
            return p
        pedaco, e_simbolo = "", False
        for ch in texto + "\0":
            atual = ch in simbolos
            if ch != "\0" and atual == e_simbolo:
                pedaco += ch
                continue
            if pedaco:
                run = p.add_run(pedaco)
                if e_simbolo:
                    familia_do_run(run, recurso[0])
            pedaco, e_simbolo = ch, atual
        return p

    doc = Document()
    doc.core_properties.title = titulo
    if autor:
        doc.core_properties.author = autor

    # A casa é o quadrado do em, então o corpo da fonte **é** a casa: o que o
    # usuário pediu em pontos entra aqui sem conta nenhuma (F97). Era derivado
    # de uma largura em centímetros, e o arredondamento dessa conta é justamente
    # o que abria vão entre as filas.
    corpo = Pt(corpo_pt)

    usadas = {}
    for i, pagina in enumerate(paginas):
        if i:
            doc.add_page_break()
        for bloco in pagina.blocos:
            if isinstance(bloco, Figura) and em_texto(bloco):
                usadas[bloco.fonte] = None
                # A largura é a das linhas, e não oito fixo: as emolduradas
                # têm dez caracteres. E a moldura da caixa sai quando o texto
                # já traz a sua — senão o diagrama ganharia duas (F99).
                colunas = max(len(linha) for linha in bloco.linhas)
                caixa = _caixa_do_diagrama(
                    doc, "sem" if bloco.linhas_emolduradas else moldura,
                    corpo_pt * colunas)
                for i_linha, linha in enumerate(bloco.linhas):
                    # A célula já nasce com um parágrafo vazio, e ele é o da
                    # primeira fila: um `add_paragraph` aqui deixaria uma linha
                    # em branco por cima do tabuleiro.
                    p = (caixa.paragraphs[0] if i_linha == 0
                         else caixa.add_paragraph())
                    # **À esquerda, e não centrado** (F98): a célula tem a
                    # largura do tabuleiro, e centrar aqui devolveria a voz ao
                    # espaço do fim da fila — ver `_caixa_do_diagrama`.
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    p.paragraph_format.space_before = Pt(0)
                    p.paragraph_format.space_after = Pt(0)
                    # Entrelinha **exata e igual ao corpo**, e não múltipla:
                    # no automático o Word acrescenta o vão da fonte e abre uma
                    # faixa branca entre as filas, que é o mesmo defeito que o
                    # `line-height: 1` do EPUB evita. É o mesmo `corpo` do run
                    # de propósito — e é por isso que ele foi arredondado ao
                    # meio ponto na entrada (ver `PASSO_DO_CORPO_PT`): a casa é
                    # o quadrado do em, e o tabuleiro só fecha quadrado quando a
                    # linha mede exatamente uma casa.
                    p.paragraph_format.line_spacing = corpo
                    run = p.add_run(linha)
                    run.font.size = corpo
                    # Sem o `hAnsi`, o Word desenha a fonte pedida só até o
                    # primeiro caractere que julgue não-ASCII.
                    familia_do_run(run, bloco.fonte)
                # **Duas tabelas coladas no XML viram uma só quando o Word
                # abre o arquivo**, e a página de exercícios é exatamente isso:
                # dois diagramas seguidos, sem prosa entre eles, que sairiam
                # dentro da mesma moldura, um por cima do outro. Um parágrafo
                # entre as duas separa — e ele vai de 1 pt de entrelinha exata,
                # que é o que o Word aceita como separador sem abrir vão
                # visível. Serve de segunda coisa: documento que termina em
                # tabela é o outro caso em que ele reclama.
                vao = doc.add_paragraph()
                vao.paragraph_format.space_before = Pt(0)
                vao.paragraph_format.space_after = Pt(0)
                vao.paragraph_format.line_spacing = Pt(1)
            elif isinstance(bloco, Figura):
                pt = largura_em_pt(bloco, corpo_pt)
                forma = doc.add_picture(
                    _io.BytesIO(bloco.png),
                    width=Pt(pt) if pt else Cm(largura_figura_cm))
                # O texto alternativo do OOXML mora no `docPr` da forma, e o
                # `python-docx` não o expõe — daí descer ao XML. Vale o desvio
                # pelo mesmo motivo do EPUB: é o FEN que o leitor de tela lê e
                # que a busca do Word encontra.
                forma._inline.docPr.set("descr", _alternativo(bloco))
                doc.paragraphs[-1].alignment = 1   # centralizado
            elif isinstance(bloco, Tabela):
                # `Table Grid` é o único estilo de grade que o template padrão
                # do Word traz; sem estilo nenhum a tabela sai sem fio e o
                # leitor não vê onde uma célula acaba.
                t = doc.add_table(rows=len(bloco.linhas),
                                  cols=len(bloco.linhas[0]))
                try:
                    t.style = doc.styles["Table Grid"]
                except KeyError:
                    pass
                for fila, textos in zip(t.rows, bloco.linhas):
                    for celula, texto in zip(fila.cells, textos):
                        celula.text = texto
            else:
                p = escrever_paragrafo(bloco.texto)
                if bloco.titulo:
                    p.style = doc.styles["Heading 2"]

    pasta = os.path.dirname(os.path.abspath(caminho))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    doc.save(caminho)

    embutir = {}
    if usadas:
        from core import render_diagrama
        embutir = {nome: render_diagrama.carregar(nome).arquivo
                   for nome in usadas}
    if recurso:
        embutir[recurso[0]] = recurso[1]
    if embutir:
        _embutir_fontes_no_docx(caminho, embutir)
    return caminho


FORMATOS = {"epub": para_epub, "docx": para_docx}


def exportar(paginas: Sequence[PaginaExtraida], caminho: str, *,
             formato: Optional[str] = None, **kw) -> str:
    """Escreve no formato pedido, ou no que a extensão do caminho indicar."""
    if formato is None:
        formato = os.path.splitext(caminho)[1].lstrip(".").lower()
    if formato not in FORMATOS:
        raise ValueError(f"formato inválido: {formato!r} "
                         f"(use um de {tuple(FORMATOS)})")
    return FORMATOS[formato](paginas, caminho, **kw)
