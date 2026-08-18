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

from core.livro import Figura, PaginaExtraida, Paragrafo

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CSS = """\
body { font-family: serif; line-height: 1.45; margin: 0 6%; }
p { margin: 0 0 0.35em; text-indent: 1.2em; text-align: justify; }
p.primeira { text-indent: 0; }
figure { margin: 1.2em 0; text-align: center; page-break-inside: avoid; }
img { max-width: 88%; height: auto; }
hr.pagina { border: 0; border-top: 1px solid #ccc; margin: 1.6em 0 1em; }
"""

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
CSS_DO_DIAGRAMA = """\
@font-face { font-family: "%(familia)s"; font-weight: normal; font-style: normal;
  src: url("fonts/%(arquivo)s"); }
div.diagrama { display: table; margin: 1.2em auto; page-break-inside: avoid; }
div.diagrama p { font-family: "%(familia)s", monospace; font-size: 2.1em;
  line-height: 1; letter-spacing: 0; margin: 0; padding: 0; text-indent: 0;
  text-align: left; white-space: pre; }
div.diagrama span.rot { display: inline-block; width: 0.92em; text-align: right;
  padding-right: 0.12em; }
div.diagrama span.col { display: inline-block; width: 1em; text-align: center; }
div.diagrama i { font-family: serif; font-style: normal; font-size: 0.4em;
  vertical-align: 0.35em; }
"""

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
    filas = [str(n) for n in range(8, 0, -1)]
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
        colunas = "".join(f'<span class="col"><i>{c}</i></span>' for c in "abcdefgh")
        linhas.append(f'<p class="colunas"><span class="rot"></span>'
                      f'{colunas}</p>')
    titulo = html.escape(_alternativo(figura))
    return (f'<div class="diagrama" title="{titulo}" '
            f'aria-label="{titulo}" role="img">\n' + "\n".join(linhas)
            + "\n</div>")


def _xhtml_da_pagina(pagina: PaginaExtraida, imagens: Sequence[str],
                     diagramas: str = "png", simbolos: str = "",
                     idioma: str = IDIOMA_PADRAO) -> str:
    corpo, i = [], 0
    primeiro = True
    for bloco in pagina.blocos:
        if isinstance(bloco, Figura):
            if diagramas == "fonte" and em_fonte(bloco):
                corpo.append(_diagrama_em_texto(bloco))
            else:
                corpo.append(f'<figure><img src="{imagens[i]}" '
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
              diagramas: str = "png", idioma: str = IDIOMA_PADRAO) -> str:
    """
    Escreve o EPUB. Devolve o caminho.

    O `mimetype` vai **primeiro e sem compressão**, que é a única exigência
    posicional do formato: leitor que valide o arquivo procura a assinatura nos
    primeiros bytes, e um zip que comprima essa entrada é recusado.

    Em `diagramas="fonte"` o tabuleiro sai como texto e a fonte de xadrez vai
    embutida — o que a licença da SkakNew-Diagram (LPPL 1.2+) permite. Quem não
    tem texto para sair, sai como imagem do mesmo jeito: o recorte do scan não
    vira letra.
    """
    if diagramas not in MODOS_DE_DIAGRAMA:
        raise ValueError(f"modo de diagrama inválido: {diagramas!r} "
                         f"(use um de {MODOS_DE_DIAGRAMA})")

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
    for nome, origem in embutidas.items():
        css += CSS_DO_DIAGRAMA % {"familia": nome,
                                  "arquivo": os.path.basename(origem)}
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
                                          idioma).encode("utf-8")))

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


def para_docx(paginas: Sequence[PaginaExtraida], caminho: str, *,
              titulo: str = "Livro", autor: str = "",
              largura_figura_cm: float = 9.0,
              diagramas: str = "png") -> str:
    """
    Escreve o DOCX. Devolve o caminho.

    A figura entra com largura fixa em centímetros, e não no tamanho em pixels:
    o recorte sai a 300 dpi e teria 700 px de largura, que o Word põe como 700
    pontos e estoura a página.

    Em `diagramas="fonte"` o tabuleiro sai como oito parágrafos de texto na
    fonte de xadrez, que vai embutida. **Diagrama com coordenadas continua
    saindo em imagem** mesmo nesse modo: a fonte não tem `a`–`h` nem `7` e `8`,
    e alinhar rótulo de outra fonte sobre as casas exigiria uma tabela de 81
    células por diagrama — no EPUB isso são três linhas de CSS, aqui não.
    """
    if diagramas not in MODOS_DE_DIAGRAMA:
        raise ValueError(f"modo de diagrama inválido: {diagramas!r} "
                         f"(use um de {MODOS_DE_DIAGRAMA})")

    import io as _io
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    def em_texto(bloco: Figura) -> bool:
        return diagramas == "fonte" and em_fonte(bloco) and not bloco.coordenadas

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

    # A casa é o quadrado do em: para o tabuleiro medir a mesma largura da
    # figura, o corpo da fonte é um oitavo dela. 9 cm dão 31,9 pt por casa.
    corpo = Pt(round(largura_figura_cm / 8 * 28.3465 * 2) / 2)

    usadas = {}
    for i, pagina in enumerate(paginas):
        if i:
            doc.add_page_break()
        for bloco in pagina.blocos:
            if isinstance(bloco, Figura) and em_texto(bloco):
                usadas[bloco.fonte] = None
                for linha in bloco.linhas:
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.space_before = Pt(0)
                    p.paragraph_format.space_after = Pt(0)
                    # Entrelinha **exata**, e não múltipla: no automático o Word
                    # acrescenta o vão da fonte e abre uma faixa branca entre as
                    # filas, que é o mesmo defeito que o `line-height: 1` do
                    # EPUB evita.
                    p.paragraph_format.line_spacing = corpo
                    run = p.add_run(linha)
                    run.font.size = corpo
                    # Sem o `hAnsi`, o Word desenha a fonte pedida só até o
                    # primeiro caractere que julgue não-ASCII.
                    familia_do_run(run, bloco.fonte)
            elif isinstance(bloco, Figura):
                forma = doc.add_picture(_io.BytesIO(bloco.png),
                                        width=Cm(largura_figura_cm))
                # O texto alternativo do OOXML mora no `docPr` da forma, e o
                # `python-docx` não o expõe — daí descer ao XML. Vale o desvio
                # pelo mesmo motivo do EPUB: é o FEN que o leitor de tela lê e
                # que a busca do Word encontra.
                forma._inline.docPr.set("descr", _alternativo(bloco))
                doc.paragraphs[-1].alignment = 1   # centralizado
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
