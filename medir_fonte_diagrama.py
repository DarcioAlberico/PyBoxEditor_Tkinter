"""
Confere o mapa de uma fonte de diagrama, e imprime a folha de contato (F58).

O mapa em `core/dados/fontes_de_diagrama.json` diz o que cada caractere da fonte
desenha. Ele **não é palpite**, e este script é o que impede que vire: são quatro
provas, e cada uma falha por um motivo diferente.

    fechamento    as 24 combinações (12 peças × 2 cores de casa) mais as duas
                  casas vazias existem, uma vez cada, sem sobra nem falta
    avanço        todo caractere do mapa anda 1 em — glifo de avanço zero é
                  desenho que cai sobre a casa anterior, não é casa
    tinta         casa escura pinta o quadrado inteiro e casa clara não; é
                  medido no pixel, e não no contorno, porque é o pixel que sai
    ida e volta   renderizar o FEN e reler o desenho com as duas redes da
                  F7.4/F7.5 devolve o mesmo FEN

A quarta é a que vale mais: fecha o círculo com o instrumento que já existe, e
que foi treinado justamente neste domínio — livro impresso com estas fontes.

    python medir_fonte_diagrama.py
    python medir_fonte_diagrama.py --fonte SkakNew-Diagram --quantos 50
    python medir_fonte_diagrama.py --sem-modelo        # só as três primeiras

A folha de contato sai em `fonte_<nome>_conferencia.pdf`: todo codepoint da
fonte, ampliado, com o que o mapa diz que ele é. É para conferir com o olho uma
vez por fonte — o resto do projeto confia no JSON depois disso.
"""

import argparse
import os
import sys

import fitz
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import render_diagrama as rd


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


#: Onde estão os tabuleiros de livro com FEN conferido (F8.4).
PASTA_CORPUS = "Diagramas-outro-projeto"

PECAS = "KQRBNPkqrbnp"

NOMES = {"K": "rei branco", "Q": "dama branca", "R": "torre branca",
         "B": "bispo branco", "N": "cavalo branco", "P": "peão branco",
         "k": "rei preto", "q": "dama preta", "r": "torre preta",
         "b": "bispo preto", "n": "cavalo preto", "p": "peão preto",
         None: "casa vazia"}


# ----------------------------------------------------------------------
# 1. Fechamento
# ----------------------------------------------------------------------

def conferir_fechamento(fonte: rd.Fonte) -> list:
    """As queixas sobre o mapa. Lista vazia é mapa fechado."""
    queixas = []
    esperado = {(p, cor) for p in PECAS for cor in ("clara", "escura")}
    esperado |= {(None, "clara"), (None, "escura")}

    vistos = {}
    for ch, alvo in fonte.casas.items():
        if alvo in vistos:
            queixas.append(f"{alvo} sai de {vistos[alvo]!r} e de {ch!r}")
        vistos[alvo] = ch

    for alvo in sorted(esperado - set(vistos), key=lambda a: (a[1], str(a[0]))):
        queixas.append(f"falta caractere para {NOMES[alvo[0]]} em casa {alvo[1]}")
    for alvo in set(vistos) - esperado:
        queixas.append(f"{vistos[alvo]!r} aponta para {alvo}, que não é casa")
    return queixas


# ----------------------------------------------------------------------
# 2. Avanço — casa ou sobreposição
# ----------------------------------------------------------------------

def conferir_avanco(fonte: rd.Fonte) -> list:
    f = fitz.Font(fontfile=fonte.arquivo)
    return [f"{ch!r} anda {f.glyph_advance(ord(ch)):.3f} em, e casa anda 1"
            for ch in sorted(fonte.casas)
            if abs(f.glyph_advance(ord(ch)) - 1.0) > 0.01]


# ----------------------------------------------------------------------
# 3. Tinta — clara ou escura, medido no pixel
# ----------------------------------------------------------------------

def _cela(fonte: rd.Fonte, ch: str, lado: int = 48) -> np.ndarray:
    """O caractere sozinho, do tamanho de uma casa."""
    doc = fitz.open()
    pagina = doc.new_page(width=lado, height=lado)
    try:
        pagina.insert_text((0, lado), ch, fontsize=lado, fontname="diag",
                           fontfile=fonte.arquivo)
        pix = pagina.get_pixmap(colorspace=fitz.csGRAY, alpha=False)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height,
                                                                 pix.width).copy()
    finally:
        doc.close()


def _tinta_da_borda(cela: np.ndarray, faixa: int = 3) -> float:
    """
    Quanto o **canto** da casa está pintado, de 0 (branco) a 1 (preto).

    Mede a borda, e não a casa inteira, porque a peça mora no meio: uma torre
    grande em casa clara escurece o centro tanto quanto a hachura escurece tudo.
    Nas quinas as duas se separam.
    """
    b = faixa
    quinas = np.concatenate([cela[:b, :b].ravel(), cela[:b, -b:].ravel(),
                             cela[-b:, :b].ravel(), cela[-b:, -b:].ravel()])
    return 1.0 - float(quinas.mean()) / 255.0


def conferir_tinta(fonte: rd.Fonte):
    """(queixas, faixa das claras, faixa das escuras)."""
    claras, escuras = [], []
    for ch, (_simbolo, cor) in fonte.casas.items():
        valor = _tinta_da_borda(_cela(fonte, ch))
        (claras if cor == "clara" else escuras).append((valor, ch))
    claras.sort(); escuras.sort()
    queixas = []
    if claras and escuras and max(claras)[0] >= min(escuras)[0]:
        queixas.append(
            f"a clara mais suja ({max(claras)[1]!r}, {max(claras)[0]:.3f}) "
            f"empata com a escura mais limpa ({min(escuras)[1]!r}, "
            f"{min(escuras)[0]:.3f}) — o mapa trocou alguma cor de casa")
    return queixas, claras, escuras


# ----------------------------------------------------------------------
# 4. Ida e volta com as duas redes
# ----------------------------------------------------------------------

def _fen_de_cobertura(cor_alvo: str) -> str:
    """
    Um FEN que põe as 12 peças em casas dessa cor.

    Existe porque o corpus é de posições de livro, e posição de livro não
    garante ter, digamos, um rei preto em casa escura. As 24 combinações do mapa
    só são exercidas se alguém as montar de propósito.
    """
    grade = [[None] * 8 for _ in range(8)]
    alvos = [(i, j) for i in range(8) for j in range(8)
             if rd.cor_da_casa(i, j) == cor_alvo]
    # Reis primeiro e nas pontas, senão a posição fica ilegal e o árbitro da
    # `diagrama.ler` mexe na leitura — o que mediria outra coisa.
    ordem = ["K", "k", "Q", "q", "R", "r", "B", "b", "N", "n", "P", "p"]
    livres = [c for c in alvos if 1 <= c[0] <= 6]
    posicoes = [livres[0], livres[-1]] + livres[len(livres) // 3:-1:2]
    for peca, (i, j) in zip(ordem, posicoes):
        grade[i][j] = peca

    filas = []
    for linha in grade:
        fila, vazias = "", 0
        for casa in linha:
            if casa is None:
                vazias += 1
                continue
            if vazias:
                fila += str(vazias); vazias = 0
            fila += casa
        if vazias:
            fila += str(vazias)
        filas.append(fila)
    return "/".join(filas) + " w - - 0 1"


def _fens_do_corpus(quantos: int) -> list:
    try:
        from medir_diagramas import tabuleiros_de_teste
        itens = tabuleiros_de_teste(PASTA_CORPUS)
    except Exception:
        return []
    return [fen for _caminho, fen in itens[:quantos]]


def ida_e_volta(fonte: rd.Fonte, fens, lado_px: int = 352, tons: int = rd.TONS):
    """
    (tabuleiros, perfeitos, casas, certas, confusão) de renderizar e reler.

    Sem moldura de propósito: `diagrama._casas_do_recorte` divide a imagem em
    8×8 **iguais**, e o filete acrescenta pixel fora do tabuleiro. Aqui se mede o
    mapa, não a tolerância do leitor a moldura — essa é outra medição.
    """
    from core import diagrama as diag
    from medir_diagramas import casas_do_fen

    tabuleiros = perfeitos = casas = certas = 0
    confusao = {}
    for fen in fens:
        png, _l, _a = rd.desenhar(fen, fonte=fonte.nome, lado_px=lado_px,
                                  moldura=False, coordenadas=False, tons=tons)
        arr = np.array(Image.open(__import__("io").BytesIO(png)).convert("L"))
        verdade = casas_do_fen(fen)
        leitura = diag.ler(arr)
        tabuleiros += 1
        perfeito = True
        for casa in leitura.casas:
            esperado = verdade.get((casa.linha, casa.coluna))
            casas += 1
            if casa.simbolo == esperado:
                certas += 1
            else:
                perfeito = False
                chave = (esperado or "·", casa.simbolo or "·")
                confusao[chave] = confusao.get(chave, 0) + 1
        perfeitos += perfeito
    return tabuleiros, perfeitos, casas, certas, confusao


# ----------------------------------------------------------------------
# A folha de contato
# ----------------------------------------------------------------------

def folha_de_contato(fonte: rd.Fonte, caminho: str, exemplo: str) -> str:
    """Todo codepoint da fonte, ampliado, com o que o mapa diz que ele é."""
    f = fitz.Font(fontfile=fonte.arquivo)
    codepoints = sorted(cp for cp in f.valid_codepoints() if cp >= 0x20)

    doc = fitz.open()
    largura, altura = 595, 842                       # A4 em pontos
    margem, colunas, lado = 40, 6, 62
    passo_x = (largura - 2 * margem) / colunas
    passo_y = lado + 34

    pagina = doc.new_page(width=largura, height=altura)
    pagina.insert_text((margem, margem), f"{fonte.nome} — folha de contato",
                       fontsize=14, fontname="hebo")
    pagina.insert_text((margem, margem + 18),
                       f"{len(codepoints)} codepoints · {fonte.licenca}",
                       fontsize=7, fontname="helv")
    topo = margem + 40
    x = y = 0

    for n, cp in enumerate(codepoints):
        ch = chr(cp)
        col, lin = n % colunas, n // colunas
        x = margem + col * passo_x
        y = topo + lin * passo_y
        if y + passo_y > altura - margem:
            pagina = doc.new_page(width=largura, height=altura)
            topo = margem
            lin = 0
            y = topo
        pagina.draw_rect(fitz.Rect(x, y, x + lado, y + lado), width=0.3,
                         color=(0.7, 0.7, 0.7))
        pagina.insert_text((x, y + lado), ch, fontsize=lado, fontname="diag",
                           fontfile=fonte.arquivo)
        simbolo, cor = fonte.casas.get(ch, (None, None))
        avanco = f.glyph_advance(cp)
        if ch in fonte.casas:
            legenda = f"{NOMES[simbolo]}\ncasa {cor}"
        elif avanco < 0.01:
            legenda = "sobreposição\n(avanço zero)"
        elif abs(avanco - 1.0) > 0.01:
            legenda = f"avanço {avanco:.2f} em\n(não é casa)"
        else:
            legenda = "casa sem uso\nno mapa"
        pagina.insert_text((x, y + lado + 10), f"{ch!r}  U+{cp:04X}",
                           fontsize=6.5, fontname="hebo")
        for i, parte in enumerate(legenda.split("\n")):
            pagina.insert_text((x, y + lado + 19 + i * 8), parte, fontsize=6.5,
                               fontname="helv")

    # E as duas provas visuais: a posição inicial documentada e uma de livro.
    pagina = doc.new_page(width=largura, height=altura)
    pagina.insert_text((margem, margem), "As duas provas visuais", fontsize=14,
                       fontname="hebo")
    inicial = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"
    for i, (titulo, fen) in enumerate([
            ("posição inicial — igual à página 3 de fonts/SkakNew.pdf", inicial),
            ("uma posição qualquer, com coordenadas", exemplo)]):
        png, larg, alt = rd.desenhar(fen, fonte=fonte.nome, lado_px=320,
                                     coordenadas=bool(i), tons=0)
        y = margem + 30 + i * 380
        pagina.insert_text((margem, y), titulo, fontsize=8, fontname="helv")
        pagina.insert_image(fitz.Rect(margem, y + 8, margem + larg, y + 8 + alt),
                            stream=png)
        pagina.insert_text((margem, y + alt + 20), fen, fontsize=6.5,
                           fontname="cour")

    doc.save(caminho)
    doc.close()
    return caminho


# ----------------------------------------------------------------------

def main() -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--fonte", default=rd.FONTE_PADRAO)
    ap.add_argument("--quantos", type=int, default=40,
                    help="tabuleiros do corpus na ida e volta (0 = só os sintéticos)")
    ap.add_argument("--sem-modelo", action="store_true")
    ap.add_argument("--saida", default=None)
    args = ap.parse_args()

    fonte = rd.carregar(args.fonte)
    print(f"{fonte.nome}  ({os.path.relpath(fonte.arquivo)})")
    print(f"  {fonte.licenca}")
    print(f"  {len(fonte.casas)} caracteres de casa mapeados\n")

    falhou = False

    queixas = conferir_fechamento(fonte)
    print("1. fechamento do mapa")
    print("   " + ("fecha: 24 combinações e as duas casas vazias"
                   if not queixas else "\n   ".join(queixas)))
    falhou |= bool(queixas)

    queixas = conferir_avanco(fonte)
    print("\n2. avanço")
    print("   " + ("todo caractere do mapa anda 1 em"
                   if not queixas else "\n   ".join(queixas)))
    falhou |= bool(queixas)

    queixas, claras, escuras = conferir_tinta(fonte)
    print("\n3. tinta na quina da casa (0 = branco, 1 = preto)")
    if claras and escuras:
        print(f"   clara   {claras[0][0]:.3f} – {claras[-1][0]:.3f}   "
              f"({len(claras)} caracteres)")
        print(f"   escura  {escuras[0][0]:.3f} – {escuras[-1][0]:.3f}   "
              f"({len(escuras)} caracteres)")
        print(f"   vão     {escuras[0][0] - claras[-1][0]:+.3f}")
    print("   " + ("as duas faixas não se tocam"
                   if not queixas else "\n   ".join(queixas)))
    falhou |= bool(queixas)

    print("\n4. ida e volta (render → as duas redes → FEN)")
    if args.sem_modelo:
        print("   pulada por --sem-modelo")
    else:
        fens = [_fen_de_cobertura("clara"), _fen_de_cobertura("escura")]
        do_corpus = _fens_do_corpus(args.quantos) if args.quantos else []
        for titulo, lote in [("cobertura das 24 combinações", fens),
                             (f"{len(do_corpus)} tabuleiros do corpus (F8.4)",
                              do_corpus)]:
            if not lote:
                print(f"   {titulo}: sem material")
                continue
            try:
                tab, perf, casas, certas, confusao = ida_e_volta(fonte, lote)
            except Exception as erro:               # modelo ausente, e afins
                print(f"   {titulo}: não deu para medir — {erro}")
                falhou = True
                continue
            print(f"   {titulo}")
            print(f"      casa certa        {certas / max(1, casas):7.2%}  "
                  f"({certas} de {casas})")
            print(f"      tabuleiro inteiro {perf / max(1, tab):7.2%}  "
                  f"({perf} de {tab})")
            if confusao:
                piores = sorted(confusao.items(), key=lambda kv: -kv[1])[:5]
                print("      confusão: " + ", ".join(
                    f"{a}→{b} ({n})" for (a, b), n in piores))
            falhou |= perf < tab

    saida = args.saida or f"fonte_{fonte.nome}_conferencia.pdf"
    exemplo = "r1bqk2r/pp2bppp/2n1pn2/3p4/3P4/2N1PN2/PP2BPPP/R1BQK2R w KQkq - 0 8"
    print(f"\nfolha de contato: {folha_de_contato(fonte, saida, exemplo)}")
    return 1 if falhou else 0


if __name__ == "__main__":
    raise SystemExit(main())
