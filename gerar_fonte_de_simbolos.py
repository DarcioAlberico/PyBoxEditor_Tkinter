"""
Recorta da fonte de símbolos só os glifos que o modelo sabe ler (F62).

A `NotoSansSymbols2` tem 641 KB e ~2.600 codepoints; o alfabeto do modelo tem
**40 símbolos fora do ASCII**, e ela desenha 14 deles. Embutir a fonte inteira
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
conflito com esta, que tem 14 glifos.

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


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def simbolos_do_modelo(caminho: str = None) -> str:
    """Os caracteres fora do ASCII que o modelo pode emitir."""
    caminho = caminho or os.path.join(RAIZ, "model_meta.json")
    with open(caminho, encoding="utf-8") as f:
        meta = json.load(f)
    alfabeto = meta["idx_to_char"]
    letras = alfabeto.values() if isinstance(alfabeto, dict) else alfabeto
    return "".join(sorted({c for c in "".join(letras) + EXTRAS if ord(c) > 127}))


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
    antes = os.path.getsize(args.origem) / 1024
    depois = os.path.getsize(args.destino) / 1024
    tem = cobertura(args.destino, chars)
    print(f"\n{os.path.basename(args.destino)}: {len(tem)} símbolos, "
          f"{depois:.1f} KB (era {antes:.0f} KB — {depois / antes:.1%})")
    return 0 if len(tem) == len(pedidos) else 1


if __name__ == "__main__":
    raise SystemExit(main())
