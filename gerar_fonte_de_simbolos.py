"""
Recorta da fonte de símbolos só os glifos que o modelo sabe ler (F62).

A `NotoSansSymbols2` tem 641 KB e ~2.600 codepoints; o alfabeto do modelo tem
**89 símbolos fora do ASCII**, e ela desenha 24 deles. Embutir a fonte inteira
num EPUB de xadrez é levar o bloco de dominós, o de I Ching e o de alquimia
para desenhar seis figurinas — medido, o EPUB de três páginas passou de 19 KB
para 327 KB só por causa dela.

    python gerar_fonte_de_simbolos.py
    python gerar_fonte_de_simbolos.py --conferir     # só confere, não escreve

**Roda uma vez, e o produto é versionado.** O `fontTools` não entra em produção
por isto: o `requirements.txt` deste projeto é declaradamente só do que o
aplicativo importa, e quem exporta um livro não precisa recortar fonte. Ele é
dependência de desenvolvimento, como o `pytest`.

**A família é renomeada, e não é capricho.** Subset é modificação, e a OFL pede
que a versão modificada não se passe pela original — além do mais, uma família
com o nome da Noto instalada na máquina de quem abre o arquivo entraria em
conflito com esta, que tem 41 glifos.

Quando o alfabeto do modelo crescer, este script tem de rodar de novo. Quem
avisa é o `tests/test_f62_simbolos.py`, que compara a cobertura do subset com o
`model_meta.json` — e, enquanto ninguém roda, o `exportar` cai sozinho para a
fonte inteira, que continua no repositório.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RAIZ = os.path.dirname(os.path.abspath(__file__))
ORIGEM = os.path.join(RAIZ, "assets", "fonts", "NotoSansSymbols2-Regular.ttf")
DESTINO = os.path.join(RAIZ, "assets", "fonts", "SimbolosDeXadrez.ttf")

#: O nome novo da família. Ver o cabeçalho: subset é modificação.
FAMILIA = "Simbolos de Xadrez"

#: O que o modelo pode emitir, mais o que o exportador escreve por conta
#: própria. O `⯹` está aqui porque a SPEC §4.2 o documenta como o símbolo que
#: **nenhuma** das 559 famílias deste sistema desenha — se um dia entrar no
#: alfabeto, a fonte já o traz.
EXTRAS = "⯹"

#: A fonte de onde vêm os glifos que a Noto não tem.
FIGURINE = os.path.join(RAIZ, "fonts", "SkakNew-Figurine.otf")

#: Símbolo → o caractere que o desenha na `SkakNew-Figurine`.
#:
#: **A Noto não desenha nenhum destes.**
#: Varridos os 578 arquivos de `C:\\Windows\\Fonts` e da pasta do usuário, o `⩱`
#: e o `⩲` — "ligeira vantagem" de cada lado, que é o símbolo mais comum destes
#: livros depois das figurinas — aparecem em quatro famílias: Segoe UI Symbol e
#: Cambria (Microsoft), CBArialLink (ChessBase) e AqChessUnicode. Nenhuma pode
#: viajar dentro de um EPUB.
#:
#: A saída é a fonte que **já está no repositório**: a SkakNew-Figurine é LPPL,
#: desenha todos eles, e o que falta a ela é só o `cmap` — como toda fonte de
#: xadrez antiga, ela põe símbolo em posição de letra. Aqui o glifo é copiado e
#: **remapeado para o codepoint certo**, que é o contrário do que este projeto
#: inteiro desfaz nos PDFs de entrada: lá a letra mente sobre o desenho; aqui o
#: desenho passa a ter o nome verdadeiro.
#:
#: **Os pares foram decididos contra os recortes de treino, e não contra outra
#: fonte.** A primeira tentativa casou `⩲` com o `e` e `∓` com o `h`, olhando a
#: folha de contato — e as duas estavam erradas. O que decide é o que o livro
#: imprime, e disso este projeto tem gabarito: as pastas `training_data/sym_*`
#: guardam os recortes de cada classe, tirados das páginas.
#:
#: Postos lado a lado, os quatro da família do `±` se separam pela contagem de
#: barras, e não pela forma geral:
#:
#:     ±  (sym_177)     mais, uma barra embaixo      →  'c'
#:     ⩲  (sym_10866)   mais, duas barras embaixo    →  'f'
#:     ∓  (sym_8723)    uma barra em cima, mais      →  'e'
#:     ⩱  (sym_10865)   duas barras em cima, mais    →  'g'
#:
#: O `h` e o `i`, que quase entraram aqui, são os pares de dois caracteres
#: `+−` e `−+` ("brancas ganham", "pretas ganham") — no alfabeto do modelo eles
#: são ligadura, não símbolo.
#:
#: O `→` ("com ataque", `sym_8594`, o `A`) e o `⨀` (zugzwang, `sym_10752`, o
#: `D`) entraram depois, pela mesma régua. O `⨀` teve um candidato a mais: a
#: **própria Noto desenha o `⊙` (U+2299)**, mesma forma, e reaproveitá-lo
#: pouparia até a conversão de contorno. Posto ao lado do recorte do livro, o
#: traço da Noto é grosso demais — o livro imprime o círculo fino, que é o `D`.
#: O atalho não apareceria no código e apareceria na página.
#:
#: O `⨀` é U+2A00 porque é assim que o modelo o emite; a convenção do Informator
#: é o U+2299. Trocar o rótulo é retreinar, e não é serviço deste script, que
#: desenha o alfabeto que existe.
#:
#: O `±` fica de fora porque é U+00B1: abaixo do `PISO_DO_SIMBOLO`, e portanto
#: desenhado pela fonte de texto do leitor, que o tem.
#:
#: **Os sete posicionais entraram com as 314 classes.** São os `$32`, `$239`,
#: `$241`, `$243`, `$245` e `$254` do `core/nags.py` — coluna, centro, flanco da
#: dama, final, "com" e vantagem de desenvolvimento —, mais o `⨼`, que não tem
#: NAG. Todos os sete estão fora da Noto (o `--conferir` os lista em "fora do
#: alcance dela"), e a SkakNew-Figurine desenha os sete.
#:
#: O par que obriga a olhar o recorte é o `∟`/`⨼`: **são o mesmo ângulo reto
#: virado**, e a fonte tem os dois lado a lado, no `v` e no `w`. Casar pelo
#: nome do codepoint não resolve — o U+2A3C chama-se "interior product" e o
#: U+221F "right angle", e nenhum dos dois nomes diz de que lado fica a haste.
#: Quem diz é o livro: as 13 amostras de `sym_10812` têm a haste à direita
#: (`w`) e a de `sym_8735` à esquerda (`v`). Trocar os dois sairia sem erro
#: nenhum no caminho, e com o símbolo espelhado na página.
#:
#: **O `⇗` e o `⌓` fecham a lista dos que a Noto não alcança**, e os dois não
#: custam o mesmo. O `⇗` (`$240`, diagonal) é o `G` da SkakNew e bate traço por
#: traço com as 3 amostras de `sym_8663`.
#:
#: O `⌓` (`$142`, "melhor é") **não bate em nenhuma fonte que se possa embutir**,
#: e por isso ele saiu daqui para o `DESENHADOS`, adiante.
EMPRESTADOS = {
    "⩲": "f",      # ligeira vantagem das brancas
    "⩱": "g",      # ligeira vantagem das pretas
    "∓": "e",      # vantagem das pretas
    "∞": "k",      # posição pouco clara
    "↑": "C",      # com iniciativa
    "→": "A",      # com ataque
    "⇄": "V",      # com contra-jogo
    "⨀": "D",      # zugzwang
    "⟳": "t",      # vantagem de desenvolvimento ($32)
    "⇔": "H",      # coluna ($239)
    "⊞": "I",      # centro ($241)
    "⟪": "M",      # flanco da dama ($243)
    "⊥": "L",      # final ($245)
    "∟": "v",      # "com" ($254) — haste à esquerda
    "⨼": "w",      # o mesmo ângulo com a haste à direita, e sem NAG
    "⇗": "G",      # diagonal ($240)
}

#: O `⌓` do `$142` ("melhor é"), medido nas 64 amostras de `training_data/sym_8979`
#: e desenhado a partir dessas medidas, em unidades de em (as três fontes deste
#: script são upem 1000, e é por isso que `emprestar` copia o `hmtx` sem escalar).
#:
#: **Nenhuma fonte que se possa embutir desenha este arco.** O livro imprime um
#: arco de laterais retas assentado numa base; o `b` da SkakNew — que foi o par
#: até aqui — é uma meia-elipse rasa. A única do disco que acerta a forma é a
#: `IS-TT-01` (o `e`), e ela tem `fsType = 1` no `OS/2`: "restricted license
#: embedding", da Chess Assistant. Contra `fsType = 0` da SkakNew e a OFL da
#: Noto, ela não pode viajar dentro do EPUB — e um glifo copiado dela seria a
#: fonte viajando do mesmo jeito, com outro nome.
#:
#: | | altura ÷ largura |
#: |---|---:|
#: | as 64 amostras (mediana) | **0,714** |
#: | `IS-TT-01`, o `e` | 0,79 |
#: | `SkakNew-Figurine`, o `b` | 0,53 |
#:
#: As outras duas medidas saem das mesmas amostras: o traço tem **0,103** da
#: largura, e a reta das laterais sobe até **0,406** da altura — daí para cima é
#: arco. As três proporções são o que o `tests/test_f62_simbolos.py` cobra, e não
#: os números absolutos abaixo.
#:
#: **A largura e o avanço são os que o `b` já ocupava** (1034 e 1200), de
#: propósito: o que estava errado era a altura, e mexer no avanço junto mudaria a
#: entrelinha de quem já exportou um livro. A altura que sai da proporção — 738 —
#: cai no meio da faixa dos outros símbolos emprestados (o `⊞` tem 755, o `∟`
#: 734, o `⊥` 725), o que é a confirmação de que a régua é a mesma.
ARCO = {
    "x": 83,             # mesmo lado esquerdo do glifo que ele substitui
    "largura": 1034,
    "avanco": 1200,
    "altura": 738,       # 0,714 x largura
    "traco": 107,        # 0,103 x largura
    "reta": 300,         # 0,406 x altura: daqui para cima é arco
}

#: Símbolo → o que desenha o contorno dele. Ver `desenhar`.
DESENHADOS = {"⌓": ARCO}

#: Emprestados que entram espelhados na horizontal.
#:
#: **Só o `⇄`, e a mesma comparação com o recorte do livro é que pegou**: a
#: SkakNew desenha a seta de cima apontando para a esquerda, e tanto o livro
#: quanto o nome do codepoint (U+21C4, "rightwards arrow over leftwards arrow")
#: querem a de cima para a direita. É o glifo do U+21C6, que é outro símbolo.
#: Espelhar custa uma matriz e devolve exatamente o que a página imprime.
ESPELHADOS = {"⇄"}

#: Erro máximo, em unidades de em, ao converter contorno cúbico (CFF) em
#: quadrático (TrueType). Um milésimo do em é menos que um pixel a 300 dpi num
#: corpo de 12 pt.
ERRO_DA_CONVERSAO = 1.0


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def simbolos_do_modelo(caminho: str = None) -> str:
    """
    Os caracteres fora do ASCII que podem **chegar a um arquivo**.

    Não é a mesma coisa que o alfabeto do modelo, e a diferença é o `✝`. Ele é
    classe de treino — 2.901 amostras, a cruz cheia que estes livros imprimem no
    xeque —, e mesmo assim **nenhum arquivo pode contê-lo**: a F68 pôs o
    `notacao.SINONIMOS_DE_SAIDA` nos três lugares em que caractere de modelo
    vira texto de arquivo (`livro`, `notacao`, `searchable_pdf`), e nos três ele
    sai como `+`.

    Sem este filtro o script pedia um glifo que ninguém pode alcançar, e o
    `ainda sem glifo` da última linha cobrava para sempre uma dívida paga.
    """
    from core.notacao import SINONIMOS_DE_SAIDA

    caminho = caminho or os.path.join(RAIZ, "model_meta.json")
    with open(caminho, encoding="utf-8") as f:
        meta = json.load(f)
    alfabeto = meta["idx_to_char"]
    letras = alfabeto.values() if isinstance(alfabeto, dict) else alfabeto
    return "".join(sorted({c for c in "".join(letras) + EXTRAS
                           if ord(c) > 127 and c not in SINONIMOS_DE_SAIDA}))


def cobertura(caminho: str, chars: str) -> str:
    """Os caracteres que esta fonte desenha, dentre os pedidos."""
    import fitz

    fonte = fitz.Font(fontfile=caminho)
    return "".join(c for c in chars if fonte.has_glyph(ord(c)))


def recortar(origem: str, destino: str, chars: str) -> str:
    """Escreve o subset. Devolve o caminho."""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    opcoes = subset.Options()
    # Os registros de nome sobrevivem ao corte porque é neles que a família é
    # renomeada logo abaixo; sem `name_IDs`, o subset os poda e a fonte sai sem
    # nome nenhum — o que o Word trata como fonte inválida.
    opcoes.name_IDs = ["*"]
    opcoes.name_legacy = True
    opcoes.notdef_outline = True
    opcoes.recalc_bounds = True

    fonte = TTFont(origem)
    subs = subset.Subsetter(options=opcoes)
    subs.populate(text=chars)
    subs.subset(fonte)

    # O nome novo em todos os registros que o nomeiam: família (1), nome
    # completo (4) e PostScript (6). Deixar um deles com o nome antigo faz o
    # Word e o leitor de EPUB discordarem sobre que fonte é esta.
    nomes = fonte["name"]
    for id_nome, valor in ((1, FAMILIA), (4, FAMILIA),
                           (6, FAMILIA.replace(" ", "")), (16, FAMILIA)):
        for registro in list(nomes.names):
            if registro.nameID == id_nome:
                nomes.setName(valor, registro.nameID, registro.platformID,
                              registro.platEncID, registro.langID)
    fonte.save(destino)
    return destino


def emprestar(destino: str, origem: str = FIGURINE,
              pares: dict = None) -> list:
    """
    Copia glifos de outra fonte para dentro do recorte, no codepoint certo.

    **O contorno muda de forma no caminho**: a SkakNew-Figurine é CFF, com
    curvas cúbicas, e o recorte é TrueType, com quadráticas. O `Cu2QuPen`
    converte; o `reverse_direction` existe porque as duas convenções giram o
    contorno em sentidos opostos, e um glifo com o giro trocado sai **vazado** —
    o miolo vira buraco e o buraco vira miolo, sem erro nenhum no caminho.
    """
    from fontTools.misc.transform import Transform
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont

    pares = pares or EMPRESTADOS
    doador = TTFont(origem)
    alvo = TTFont(destino)
    glifos_do_doador = doador.getGlyphSet()
    cmap_do_doador = doador.getBestCmap()

    novos = []
    for simbolo, letra in pares.items():
        nome_origem = cmap_do_doador.get(ord(letra))
        if nome_origem is None:
            raise KeyError(f"{origem} não tem {letra!r}, que desenharia {simbolo}")
        nome = f"uni{ord(simbolo):04X}"
        avanco, _lsb = doador["hmtx"][nome_origem]
        caneta = TTGlyphPen(alvo.getGlyphSet())
        # Espelhar inverte o giro do contorno junto, e o `reverse_direction`
        # tem de acompanhar: com os dois ligados, o glifo sairia vazado.
        espelha = simbolo in ESPELHADOS
        destino_da_caneta = Cu2QuPen(caneta, ERRO_DA_CONVERSAO,
                                     reverse_direction=not espelha)
        if espelha:
            destino_da_caneta = TransformPen(
                destino_da_caneta, Transform(-1, 0, 0, 1, avanco, 0))
        glifos_do_doador[nome_origem].draw(destino_da_caneta)

        alvo.setGlyphOrder(alvo.getGlyphOrder() + [nome])
        alvo["glyf"].glyphs[nome] = caneta.glyph()
        alvo["hmtx"].metrics[nome] = doador["hmtx"][nome_origem]
        for tabela in alvo["cmap"].tables:
            tabela.cmap[ord(simbolo)] = nome
        novos.append(simbolo)

    alvo.save(destino)
    return novos


#: Quanto a alça de uma Bézier cúbica anda para aproximar um quarto de elipse.
#: O valor clássico, 4/3·(√2−1): erro máximo de 0,027% do raio.
ALCA_DA_ELIPSE = 0.5522847498


def _contorno_do_arco(caneta, medidas: dict, dentro: bool = False) -> None:
    """
    Um dos dois contornos do arco — o de fora, ou o buraco de dentro.

    O de fora sai no sentido do CFF (anti-horário), que é o que o
    `Cu2QuPen(reverse_direction=True)` de `desenhar` espera, e o de dentro no
    contrário: é a diferença entre um arco e um retângulo arredondado maciço.
    """
    x0, largura, altura = medidas["x"], medidas["largura"], medidas["altura"]
    traco, reta = medidas["traco"], medidas["reta"]
    if dentro:
        x0, largura = x0 + traco, largura - 2 * traco
        base, topo = traco, altura - traco
    else:
        base, topo = 0, altura
    meio = x0 + largura / 2.0
    rx, ry = largura / 2.0, topo - reta
    k = ALCA_DA_ELIPSE
    direita, esquerda = x0 + largura, x0
    if dentro:
        caneta.moveTo((direita, base))
        caneta.lineTo((esquerda, base))
        caneta.lineTo((esquerda, reta))
        caneta.curveTo((esquerda, reta + ry * k), (meio - rx * k, topo), (meio, topo))
        caneta.curveTo((meio + rx * k, topo), (direita, reta + ry * k), (direita, reta))
    else:
        caneta.moveTo((esquerda, base))
        caneta.lineTo((direita, base))
        caneta.lineTo((direita, reta))
        caneta.curveTo((direita, reta + ry * k), (meio + rx * k, topo), (meio, topo))
        caneta.curveTo((meio - rx * k, topo), (esquerda, reta + ry * k), (esquerda, reta))
    caneta.closePath()


def desenhar(destino: str, pares: dict = None) -> list:
    """
    Escreve no recorte os glifos que este script desenha, em vez de emprestar.

    **É a saída para o símbolo que nenhuma fonte distribuível desenha certo.**
    Emprestar é sempre preferível — o glifo emprestado vem de uma fonte
    desenhada por quem sabe, e mantém a família coerente. Este caminho existe
    para o caso em que a única fonte que acerta a forma proíbe embutir, e é o do
    `⌓` (ver `ARCO`): o que se copiaria dela não é uma medida, é o desenho.

    O contorno é cúbico e passa pelo mesmo `Cu2QuPen` do `emprestar`, pela mesma
    razão — o recorte é TrueType e só tem quadráticas — e com o mesmo
    `reverse_direction`, porque ele é escrito na convenção do CFF.
    """
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont

    pares = pares or DESENHADOS
    alvo = TTFont(destino)

    novos = []
    for simbolo, medidas in pares.items():
        nome = f"uni{ord(simbolo):04X}"
        caneta = TTGlyphPen(alvo.getGlyphSet())
        destino_da_caneta = Cu2QuPen(caneta, ERRO_DA_CONVERSAO,
                                     reverse_direction=True)
        _contorno_do_arco(destino_da_caneta, medidas, dentro=False)
        _contorno_do_arco(destino_da_caneta, medidas, dentro=True)

        if nome not in alvo.getGlyphOrder():
            alvo.setGlyphOrder(alvo.getGlyphOrder() + [nome])
        alvo["glyf"].glyphs[nome] = caneta.glyph()
        alvo["hmtx"].metrics[nome] = (medidas["avanco"], medidas["x"])
        for tabela in alvo["cmap"].tables:
            tabela.cmap[ord(simbolo)] = nome
        novos.append(simbolo)

    alvo.save(destino)
    return novos


def main() -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--origem", default=ORIGEM)
    ap.add_argument("--destino", default=DESTINO)
    ap.add_argument("--conferir", action="store_true",
                    help="não escreve: só diz o que o subset atual cobre")
    args = ap.parse_args()

    chars = simbolos_do_modelo()
    print(f"alfabeto do modelo: {len(chars)} símbolos fora do ASCII")
    print(f"  {' '.join(chars)}")

    pedidos = cobertura(args.origem, chars)
    print(f"\n{os.path.basename(args.origem)} desenha {len(pedidos)} deles: "
          f"{' '.join(pedidos)}")
    de_fora = [c for c in chars if c not in pedidos]
    if de_fora:
        print(f"  fora do alcance dela: {' '.join(de_fora)}")

    if args.conferir:
        if not os.path.exists(args.destino):
            print(f"\n{os.path.basename(args.destino)} não existe ainda")
            return 1
        tem = cobertura(args.destino, chars)
        falta = [c for c in pedidos if c not in tem]
        print(f"\n{os.path.basename(args.destino)}: {len(tem)} de {len(pedidos)}"
              f"  ({os.path.getsize(args.destino) / 1024:.1f} KB)")
        if falta:
            print(f"  **faltando**: {' '.join(falta)} — rode sem --conferir")
        return 1 if falta else 0

    recortar(args.origem, args.destino, pedidos)
    emprestados = emprestar(args.destino)
    print(f"\nemprestados da {os.path.basename(FIGURINE)}: "
          f"{' '.join(emprestados)}")
    desenhados = desenhar(args.destino)
    print(f"desenhados aqui: {' '.join(desenhados)}")

    antes = os.path.getsize(args.origem) / 1024
    depois = os.path.getsize(args.destino) / 1024
    tem = cobertura(args.destino, chars)
    print(f"\n{os.path.basename(args.destino)}: {len(tem)} símbolos, "
          f"{depois:.1f} KB (era {antes:.0f} KB — {depois / antes:.1%})")
    ainda_falta = [c for c in chars if c not in tem and ord(c) >= 0x2000]
    if ainda_falta:
        print(f"  ainda sem glifo: {' '.join(ainda_falta)}")
    esperado = len(pedidos) + len(emprestados) + len(desenhados)
    return 0 if len(tem) >= esperado else 1


if __name__ == "__main__":
    raise SystemExit(main())
