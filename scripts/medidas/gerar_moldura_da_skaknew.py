"""
Dá à SkakNew-Diagram os glifos de moldura que ela não tem (F122).

A moldura do diagrama em texto passou a ser desenhada pela própria fonte, como
a Chess Merida sempre soube fazer (`! " # $ % / ( )` e `1 2 3 4 5 7 8 9`): o
tabuleiro sai numa grade de dez por dez, e o filete é glifo, e não borda de CSS
ou célula de tabela. A SkakNew de 2004 tem 46 codepoints e nenhum deles é borda
— a `skak` do LaTeX desenha o filete por fora, com `\\rule` —, e por isso esta
cópia ganha 24 glifos: as oito peças da moldura simples e as oito da dupla, e as
quatro quinas redondas de cada uma.

**Os glifos são desenhados aqui, e não copiados.** São retângulos e quartos de
anel, e os números abaixo são os da moldura da Merida (o vão até o tabuleiro, a
espessura do filete, o espaço entre os dois da dupla, o raio da quina) levados
do em de 2048 para o de 1000. As duas fontes saem com a mesma moldura, e o
`RAIO_DO_CANTO` do `render_diagrama` já dizia esses raios em casas.

**Só se acrescenta.** Os 47 glifos de 2004 ficam com os bytes que tinham, e o
cmap ganha entradas só em codepoints que a fonte não usava — a cópia é um
superconjunto da original, e quem a usar com a `skak` vê a mesma fonte. É o que
o `--conferir` mede. As teclas vêm do `fontes_de_diagrama.json`, que é quem o
resto do projeto lê: a dupla usa as da Merida; a simples e as quinas redondas
não podem (`1`–`5` são as sobreposições desta fonte, e `a s A S` são peças), e o
script recusa tecla ocupada.

**A licença permite, e pede que se diga.** A SkakNew é LPPL 1.2 ou posterior
(© 2004–2009 Ulrich Dirr), e a 1.3c pede que a versão modificada se identifique
como tal e aponte para a original: a tabela de nomes diz que a moldura foi
acrescentada pelo PyBoxEditor, e a original fica em
`fonts/SkakNew-Diagram-original.otf`. **A família continua `SkakNew-Diagram`**,
e não por descuido: é a chave do mapa, a classe do CSS e o nome que o DOCX pede
no run — trocá-la separaria a fonte embutida do texto no Word (ver o cabeçalho
do `gerar_fonte_de_diagrama.py`).

    python gerar_moldura_da_skaknew.py
    python gerar_moldura_da_skaknew.py --conferir     # só confere, não escreve

**Roda uma vez, e o produto é versionado**, como o `gerar_fonte_de_diagrama.py`:
o `fontTools` é dependência de desenvolvimento.
"""

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from typing import List, Tuple

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ORIGEM = os.path.join(RAIZ, "fonts", "SkakNew-Diagram-original.otf")
DESTINO = os.path.join(RAIZ, "fonts", "SkakNew-Diagram.otf")
MAPAS = os.path.join(RAIZ, "core", "dados", "fontes_de_diagrama.json")
FAMILIA = "SkakNew-Diagram"

#: O sha256 da SkakNew de 2004, como veio do CTAN — a origem tem de ser ela.
SHA_DA_ORIGINAL = "bb0a3c03aba60f88f5b81d4dd76fbbf5ccc190978e481bd2c9c915789dd2aea1"

#: A data que vai no `head.modified` da cópia (ver `acrescentar`).
DATA_DA_MOLDURA = "Thu Sep 24 00:00:00 2026"

EM = 1000

#: A moldura da Chess Merida, medida no contorno e levada de 2048 para 1000 unidades.
#: Distâncias contadas a partir da borda do tabuleiro, para fora.
VAO = 17          # do tabuleiro ao filete (Merida: 35)
FILETE = 49       # o filete da simples, e o de dentro da dupla (Merida: 100)
ENTRE = 51        # entre os dois filetes da dupla (Merida: 104)
EXTERNO = 83      # o filete de fora da dupla (Merida: 171)

#: As faixas de tinta de cada moldura, `(de, até)` a partir do tabuleiro.
FAIXAS = {
    "simples": [(VAO, VAO + FILETE)],
    "dupla": [(VAO, VAO + FILETE), (VAO + FILETE + ENTRE, VAO + FILETE + ENTRE + EXTERNO)],
}

#: O quarto de círculo em Bézier cúbica: 4/3·(√2 − 1).
KAPPA = 0.5522847498

PECAS = ("canto_ne", "topo", "canto_no", "esquerda", "direita", "canto_se", "base", "canto_so")
QUINAS = ("canto_ne", "canto_no", "canto_se", "canto_so")


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ----------------------------------------------------------------------
# O desenho
# ----------------------------------------------------------------------

Ponto = Tuple[int, int]


@dataclass
class Contorno:
    """Um contorno fechado: o ponto de partida e os trechos (`("L", p)` ou `("C", c1, c2, p)`)."""

    inicio: Ponto
    trechos: list

    def espelhado(self, em_x: bool, em_y: bool) -> "Contorno":
        """Refletido dentro da casa; refletir num eixo só inverte o sentido, e ele é desinvertido."""
        def f(p):
            return (EM - p[0] if em_x else p[0], EM - p[1] if em_y else p[1])
        novo = Contorno(f(self.inicio), [(t[0], *map(f, t[1:])) for t in self.trechos])
        return novo.invertido() if em_x != em_y else novo

    def invertido(self) -> "Contorno":
        pontos = [self.inicio] + [t[-1] for t in self.trechos]
        trechos = list(self.trechos)
        if pontos[-1] != pontos[0]:
            trechos.append(("L", self.inicio))
            pontos.append(self.inicio)
        novos = []
        for i in range(len(trechos) - 1, -1, -1):
            t = trechos[i]
            novos.append(("L", pontos[i]) if t[0] == "L" else ("C", t[2], t[1], pontos[i]))
        return Contorno(pontos[-1], novos)

    def desenhar(self, caneta) -> None:
        caneta.moveTo(self.inicio)
        trechos = self.trechos
        if trechos and trechos[-1][0] == "L" and trechos[-1][1] == self.inicio:
            trechos = trechos[:-1]          # o `closePath` já volta ao início
        for t in trechos:
            if t[0] == "L":
                caneta.lineTo(t[1])
            else:
                caneta.curveTo(t[1], t[2], t[3])
        caneta.closePath()


def _r(v: float) -> int:
    return int(round(v))


def faixa_de_cima(de: int, ate: int) -> Contorno:
    """O `topo`: a casa de cima do tabuleiro, com a tinta no pé dela."""
    return Contorno((0, de), [("L", (EM, de)), ("L", (EM, ate)), ("L", (0, ate))])


def faixa_da_esquerda(de: int, ate: int) -> Contorno:
    """A `esquerda`: a casa à esquerda do tabuleiro, com a tinta no lado direito dela."""
    return Contorno((EM - ate, 0), [("L", (EM - de, 0)), ("L", (EM - de, EM)), ("L", (EM - ate, EM))])


def canto_reto(de: int, ate: int) -> Contorno:
    """O `canto_ne` (o de cima à esquerda do tabuleiro): um L com o vértice no pé direito da casa."""
    return Contorno((EM - ate, ate), [("L", (EM - ate, 0)), ("L", (EM - de, 0)), ("L", (EM - de, de)),
                                      ("L", (EM, de)), ("L", (EM, ate))])


def canto_redondo(de: int, ate: int) -> Contorno:
    """O `canto_ne` de quina redonda: um quarto de anel com o centro no canto do tabuleiro."""
    k = KAPPA
    return Contorno((EM, ate), [
        ("C", (_r(EM - k * ate), ate), (EM - ate, _r(k * ate)), (EM - ate, 0)),
        ("L", (EM - de, 0)),
        ("C", (EM - de, _r(k * de)), (_r(EM - k * de), de), (EM, de)),
    ])


def _da_peca(peca: str, de: int, ate: int, redonda: bool = False) -> Contorno:
    if peca in QUINAS:
        base = canto_redondo(de, ate) if redonda else canto_reto(de, ate)
        return base.espelhado(peca in ("canto_no", "canto_so"), peca in ("canto_se", "canto_so"))
    if peca == "topo":
        return faixa_de_cima(de, ate)
    if peca == "base":
        return faixa_de_cima(de, ate).espelhado(False, True)
    if peca == "esquerda":
        return faixa_da_esquerda(de, ate)
    if peca == "direita":
        return faixa_da_esquerda(de, ate).espelhado(True, False)
    raise ValueError(f"peça desconhecida: {peca}")


def glifos_da_moldura(teclas: dict) -> List[Tuple[str, str, List[Contorno]]]:
    """`[(nome do glifo, tecla, contornos)]` das duas molduras, com as quinas redondas."""
    saida = []
    for moldura, faixas in FAIXAS.items():
        pecas = teclas[moldura]
        for peca in PECAS:
            saida.append((f"moldura.{moldura}.{peca}", pecas[peca],
                          [_da_peca(peca, de, ate) for de, ate in faixas]))
        for peca in QUINAS:
            saida.append((f"moldura.{moldura}.{peca}.redonda", pecas["cantos_arredondados"][peca],
                          [_da_peca(peca, de, ate, redonda=True) for de, ate in faixas]))
    return saida


def teclas_do_mapa(caminho: str = MAPAS) -> dict:
    with open(caminho, encoding="utf-8") as f:
        bruto = json.load(f)["fontes"][FAMILIA]
    if "molduras" not in bruto:
        raise SystemExit(f"o {caminho} não diz as teclas da moldura da {FAMILIA}")
    return bruto["molduras"]


# ----------------------------------------------------------------------
# A fonte
# ----------------------------------------------------------------------

def acrescentar(caminho_origem: str, caminho_destino: str, teclas: dict) -> dict:
    """Escreve a cópia com a moldura. Devolve o que dizer de volta."""
    from fontTools.misc.timeTools import timestampFromString
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.ttLib import TTFont

    fonte = TTFont(caminho_origem)
    ocupados = set(fonte.getBestCmap())
    cff = fonte["CFF "].cff
    topo = cff.topDictIndex[0]
    charstrings = topo.CharStrings
    ordem = list(fonte.getGlyphOrder())
    glifos_antes = len(ordem)

    novos = glifos_da_moldura(teclas)
    for nome, tecla, _ in novos:
        if ord(tecla) in ocupados:
            raise SystemExit(f"a tecla {tecla!r} de {nome} já desenha outra coisa na {FAMILIA} — "
                             "a cópia deixaria de ser um superconjunto da original")
        ocupados.add(ord(tecla))

    # **A largura dentro do CFF não é a do `hmtx`, e o Edge lê a do CFF.** O
    # charstring guarda o avanço como diferença do `nominalWidthX` (107 nesta
    # fonte), ou não guarda nada quando ele é o `defaultWidthX` (1000); o
    # `T2CharStringPen` escreve o número cru. Com o 1000 cru, cada peça andava
    # 1107 e a moldura saía tracejada no navegador — e inteira no `fitz`, que lê
    # o `hmtx`. O `--conferir` mede as duas larguras.
    privado = topo.Private
    largura = (None if EM == getattr(privado, "defaultWidthX", 0)
               else EM - getattr(privado, "nominalWidthX", 0))
    for nome, tecla, contornos in novos:
        caneta = T2CharStringPen(width=largura, glyphSet=None)
        limites = BoundsPen(None)
        for contorno in contornos:
            contorno.desenhar(caneta)
            contorno.desenhar(limites)
        glifo = caneta.getCharString(private=topo.Private, globalSubrs=cff.GlobalSubrs)
        if charstrings.charStringsAreIndexed:
            charstrings.charStringsIndex.items.append(glifo)
            charstrings.charStrings[nome] = len(charstrings.charStringsIndex.items) - 1
        else:
            charstrings.charStrings[nome] = glifo
        ordem.append(nome)
        fonte["hmtx"].metrics[nome] = (EM, _r(limites.bounds[0]))
        for tabela in fonte["cmap"].tables:
            if tabela.isUnicode():
                tabela.cmap[ord(tecla)] = nome

    # A ordem dos glifos e o charset do CFF são a mesma lista no fontTools: um
    # `append` num e um `setGlyphOrder` noutro dariam o nome duas vezes.
    topo.charset = ordem
    fonte.setGlyphOrder(ordem)
    fonte["maxp"].numGlyphs = len(ordem)

    nomes = fonte["name"]
    aviso = (" Moldura em glifo (24 glifos) acrescentada pelo PyBoxEditor em 2026 (F122); "
             "a original está em fonts/SkakNew-Diagram-original.otf e no pacote skaknew do CTAN.")
    for registro in list(nomes.names):
        if registro.nameID == 0:
            nomes.setName(registro.toUnicode().split(" Moldura em glifo")[0] + aviso, 0,
                          registro.platformID, registro.platEncID, registro.langID)
        elif registro.nameID == 3:
            nomes.setName(f"{FAMILIA}; moldura acrescentada pelo PyBoxEditor", 3,
                          registro.platformID, registro.platEncID, registro.langID)
        elif registro.nameID == 5:
            nomes.setName("Version 1.001 2004 initial release; moldura PyBoxEditor 1", 5,
                          registro.platformID, registro.platEncID, registro.langID)

    # A data da modificação é a da F122, e não a hora de rodar: o `fontTools`
    # carimba o `head` a cada gravação, e o mesmo script daria um sha por rodada —
    # o do `fontes_de_diagrama.json` deixaria de conferir.
    fonte["head"].modified = timestampFromString(DATA_DA_MOLDURA)
    fonte.recalcTimestamp = False

    pasta = os.path.dirname(os.path.abspath(caminho_destino))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    fonte.save(caminho_destino)
    fonte.close()
    return {"antes": glifos_antes, "novos": len(novos)}


def conferir(caminho: str, origem: str = ORIGEM, teclas: dict | None = None) -> list:
    """As queixas sobre a cópia. Lista vazia é cópia boa."""
    import fitz
    from fontTools.misc.psCharStrings import T2WidthExtractor
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.ttLib import TTFont

    if not os.path.exists(caminho):
        return [f"{caminho} não existe — rode o script sem --conferir"]
    if not os.path.exists(origem):
        return [f"{origem} não existe — a original tem de ficar ao lado da cópia"]
    teclas = teclas or teclas_do_mapa()
    queixas = []
    with open(origem, "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != SHA_DA_ORIGINAL:
            queixas.append(f"{origem} não é a SkakNew de 2004 (sha256 diferente)")

    copia, original = TTFont(caminho), TTFont(origem)
    try:
        if copia["head"].unitsPerEm != EM:
            queixas.append("o em mudou — a casa deixaria de ser o quadrado do em")
        cs_copia = copia["CFF "].cff.topDictIndex[0].CharStrings
        cs_original = original["CFF "].cff.topDictIndex[0].CharStrings
        for nome in original.getGlyphOrder():
            a, b = cs_original[nome], cs_copia[nome]
            a.compile()
            b.compile()
            if bytes(a.bytecode) != bytes(b.bytecode):
                queixas.append(f"o glifo {nome} mudou — a cópia deixou de ser a original mais a moldura")
        cmap_original, cmap_copia = original.getBestCmap(), copia.getBestCmap()
        for codigo, nome in cmap_original.items():
            if cmap_copia.get(codigo) != nome:
                queixas.append(f"U+{codigo:04X} mudou de glifo — a cópia deixou de ser um superconjunto")
        novos = glifos_da_moldura(teclas)
        if copia["maxp"].numGlyphs != original["maxp"].numGlyphs + len(novos):
            queixas.append(f"{copia['maxp'].numGlyphs} glifos, e deviam ser "
                           f"{original['maxp'].numGlyphs} + {len(novos)}")
        conjunto = copia.getGlyphSet()
        topo = copia["CFF "].cff.topDictIndex[0]
        for nome, tecla, _ in novos:
            if cmap_copia.get(ord(tecla)) != nome:
                queixas.append(f"a tecla {tecla!r} não aponta para {nome}")
                continue
            extrator = T2WidthExtractor(getattr(topo.Private, "Subrs", []), topo.CharStrings.globalSubrs,
                                        topo.Private.nominalWidthX, topo.Private.defaultWidthX)
            extrator.execute(cs_copia[nome])
            if extrator.width != EM:
                queixas.append(f"{nome} anda {extrator.width} no CFF, e o `hmtx` diz {EM}")
            avanco, _lsb = copia["hmtx"][nome]
            limites = BoundsPen(conjunto)
            conjunto[nome].draw(limites)
            x0, y0, x1, y1 = limites.bounds
            if avanco != EM or x0 < 0 or y0 < 0 or x1 > EM or y1 > EM:
                queixas.append(f"{nome} sai da casa: avanço {avanco}, tinta {limites.bounds}")
        # A de 2004 já vem na versão 2, com as faixas de página de código que o
        # Word exige para usar a fonte embutida (a Merida de 1998 era a 0 e teve
        # de subir, ED-09); a cópia só não pode ficar abaixo dela.
        if copia["OS/2"].version < original["OS/2"].version:
            queixas.append(f"a OS/2 desceu para a versão {copia['OS/2'].version}")
    finally:
        copia.close()
        original.close()

    f = fitz.Font(fontfile=caminho)
    faltando = [t for _, t, _ in glifos_da_moldura(teclas) if not f.has_glyph(ord(t))]
    if faltando:
        queixas.append(f"o fitz não acha {''.join(faltando)!r}")
    return queixas


def main() -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--conferir", action="store_true", help="só confere o que já está escrito")
    ap.add_argument("--origem", default=ORIGEM)
    ap.add_argument("--destino", default=DESTINO)
    args = ap.parse_args()

    teclas = teclas_do_mapa()
    if not args.conferir:
        if not os.path.exists(args.origem):
            print(f"não achei {args.origem} — a SkakNew de 2004 tem de estar ali")
            return 1
        info = acrescentar(args.origem, args.destino, teclas)
        print(f"escrito {args.destino} ({os.path.getsize(args.destino):,} B) — "
              f"{info['antes']} glifos da original + {info['novos']} da moldura")

    queixas = conferir(args.destino, args.origem, teclas)
    for queixa in queixas:
        print(f"  ! {queixa}")
    if queixas:
        return 1
    with open(args.destino, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    print(f"confere. sha256 {sha}")
    print("ponha este sha no core/dados/fontes_de_diagrama.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
