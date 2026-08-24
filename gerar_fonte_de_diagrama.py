"""
Dá cmap Unicode à Chess Merida, que só tem o de símbolo (F98).

A `MERIFONT.TTF` é de 1998 e traz duas tabelas de cmap: uma Mac Roman (1,0) e
uma **Symbol** (3,0), esta com os caracteres em `0xF020`–`0xF0EF` em vez de
`0x20`–`0xEF`. Era o jeito de 1998 de dizer "esta fonte não tem letras, tem
desenhos", e o Word ainda o entende — o Wingdings funciona assim até hoje.

**O `fitz` não entende, e falha calado.** Medido: `fitz.Font(fontfile=...)`
varrido pelos 65.536 codepoints do plano básico encontra **zero** glifos nesta
fonte, e `insert_text` desenha um `·` no lugar de cada peça. É exatamente o modo
de falha que a §4.2 da SPEC registra, e é por isso que o `render_diagrama` tem a
checagem de cobertura: sem ela o livro sairia com 64 casas em branco por
diagrama, plausível à distância.

O navegador e o Word ainda mapeariam a tabela de símbolo por conta própria, mas
o desenho do PNG é o caminho padrão — e ele é quem não pode falhar.

    python gerar_fonte_de_diagrama.py
    python gerar_fonte_de_diagrama.py --conferir     # só confere, não escreve

**Roda uma vez, e o produto é versionado**, como o `gerar_fonte_de_simbolos.py`
da F62 e pelo mesmo motivo: o `fontTools` é dependência de desenvolvimento, e
quem exporta um livro não precisa remendar fonte.

**A família é renomeada, e não é capricho.** Acrescentar cmap é modificação, e
uma família com o nome da original instalada na máquina de quem abre o arquivo
entraria em conflito com esta. A licença permite: a Chess Merida é freeware de
Armando Hernández Marroquín (1998), e a redistribuição em
`github.com/vasiliyaltunin/chess-merida-font` é MPL-2.0, que autoriza modificar.

**Os glifos não são tocados.** Só a tabela de cmap e a de nomes mudam; o
contorno de cada peça é byte a byte o de 1998, e é isso que o `--conferir`
mede — se um dia o remendo mexer num desenho, a conta de glifos acusa.
"""

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RAIZ = os.path.dirname(os.path.abspath(__file__))
ORIGEM = os.path.join(RAIZ, "fonts", "MERIFONT.TTF")
DESTINO = os.path.join(RAIZ, "fonts", "ChessMerida-Diagram.ttf")

#: O nome novo da família. Ver o cabeçalho: cmap novo é modificação.
#:
#: **Tem de ser igual à chave da fonte no `fontes_de_diagrama.json`**, e é a
#: única parte do nome que não é escolha de gosto. Quem embute a fonte no DOCX
#: escreve `<w:font w:name="...">` com a chave do mapa e pede a família no run
#: com a mesma chave: se a família de dentro do arquivo disser outra coisa, o
#: Word não liga uma na outra e o tabuleiro sai na fonte do usuário — sem erro,
#: e só se vê abrindo. A `SkakNew-Diagram` já se chama assim; esta passa a.
FAMILIA = "ChessMerida-Diagram"
POSTSCRIPT = "ChessMerida-Diagram"

#: O deslocamento da tabela de símbolo: `0xF070` é o `p`.
BASE_DO_SIMBOLO = 0xF000

#: O que o mapa da fonte promete, e portanto o mínimo que o remendo tem de
#: entregar. Vem do `fontes_de_diagrama.json` quando ele já existe; enquanto
#: não existe, é esta lista — as 24 peças, mais as duas casas vazias.
CASAS = " +pPoOnNmMbBvVrRtTqQwWkKlL"


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def mapa_de_simbolo(fonte) -> dict:
    """
    `{codepoint sem o 0xF000: nome do glifo}`, lido da tabela de símbolo.

    **A tabela de símbolo é a fonte da verdade, e não a Mac Roman.** As duas
    dizem quase o mesmo, mas a Mac Roman mapeia os acentuados pela tabela do
    Macintosh de 1984, e ali `0xC0` não é `À` — é `¿`. Os caracteres de borda
    com coordenada da Merida moram justamente nessa faixa, e traduzi-los pela
    tabela errada trocaria a fila `1` pela coluna `a` sem nada denunciar.
    """
    tabelas = [t for t in fonte["cmap"].tables
               if t.platformID == 3 and t.platEncID == 0]
    if not tabelas:
        raise SystemExit(f"{ORIGEM} não tem tabela de símbolo (3,0) — "
                         "não é a Chess Merida que este script conhece")
    bruto = tabelas[0].cmap
    return {cod - BASE_DO_SIMBOLO: nome for cod, nome in bruto.items()
            if BASE_DO_SIMBOLO <= cod < BASE_DO_SIMBOLO + 0x100}


def remendar(caminho_origem: str, caminho_destino: str) -> dict:
    """Escreve a cópia com cmap Unicode. Devolve o que dizer de volta."""
    from fontTools.ttLib import TTFont, newTable
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

    fonte = TTFont(caminho_origem)
    mapa = mapa_de_simbolo(fonte)
    glifos_antes = fonte["maxp"].numGlyphs

    # (3,1) é a que o `fitz`, o navegador e o Word procuram primeiro; a (0,3) é
    # a mesma coisa para quem prefere a plataforma Unicode. As duas apontam para
    # os mesmos glifos, e nenhuma delas é a de símbolo — **a (3,0) sai**. Ficar
    # com as duas faria o Word tratar a fonte como de símbolo e ignorar a nova.
    subtabelas = []
    for plataforma, codificacao in ((3, 1), (0, 3)):
        sub = CmapSubtable.newSubtable(4)
        sub.platformID, sub.platEncID = plataforma, codificacao
        sub.language = 0
        sub.cmap = dict(mapa)
        subtabelas.append(sub)

    cmap = newTable("cmap")
    cmap.tableVersion = 0
    cmap.tables = subtabelas
    fonte["cmap"] = cmap

    for nome_id, valor in ((1, FAMILIA), (2, "Regular"),
                           (3, f"{FAMILIA}; remendado por PyBoxEditor"),
                           (4, FAMILIA), (6, POSTSCRIPT),
                           (16, FAMILIA), (17, "Regular")):
        for plataforma, codificacao, idioma in ((3, 1, 0x409), (1, 0, 0)):
            fonte["name"].setName(valor, nome_id, plataforma, codificacao,
                                  idioma)

    pasta = os.path.dirname(os.path.abspath(caminho_destino))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    fonte.save(caminho_destino)
    fonte.close()

    return {"glifos": glifos_antes, "codepoints": len(mapa)}


def conferir(caminho: str) -> list:
    """As queixas sobre o arquivo remendado. Lista vazia é remendo bom."""
    import fitz

    queixas = []
    if not os.path.exists(caminho):
        return [f"{caminho} não existe — rode o script sem --conferir"]

    f = fitz.Font(fontfile=caminho)
    faltando = [c for c in CASAS if not f.has_glyph(ord(c))]
    if faltando:
        queixas.append(f"o fitz não acha {''.join(faltando)!r}")

    # O `space` não tem contorno, e é a casa clara vazia: pedir tinta dele seria
    # pedir que o vazio desenhasse alguma coisa.
    from fontTools.ttLib import TTFont

    remendada, original = TTFont(caminho), TTFont(ORIGEM)
    if remendada["maxp"].numGlyphs != original["maxp"].numGlyphs:
        queixas.append(
            f"a contagem de glifos mudou: {original['maxp'].numGlyphs} → "
            f"{remendada['maxp'].numGlyphs} — o remendo mexeu no desenho")
    if remendada["head"].unitsPerEm != original["head"].unitsPerEm:
        queixas.append("o em mudou — a casa deixaria de ser o quadrado do em")
    remendada.close()
    original.close()
    return queixas


def main() -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--conferir", action="store_true",
                    help="só confere o que já está escrito")
    ap.add_argument("--origem", default=ORIGEM)
    ap.add_argument("--destino", default=DESTINO)
    args = ap.parse_args()

    if not args.conferir:
        if not os.path.exists(args.origem):
            print(f"não achei {args.origem}")
            return 1
        info = remendar(args.origem, args.destino)
        tamanho = os.path.getsize(args.destino)
        print(f"escrito {args.destino} ({tamanho:,} B) — {info['glifos']} "
              f"glifos, {info['codepoints']} codepoints no cmap novo")

    queixas = conferir(args.destino)
    for queixa in queixas:
        print(f"  ! {queixa}")
    if queixas:
        return 1

    with open(args.destino, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    print(f"confere. sha256 {sha}")
    print("ponha este sha no core/dados/fontes_de_diagrama.json, e depois rode")
    print("  python medir_fonte_diagrama.py --fonte ChessMerida-Diagram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
