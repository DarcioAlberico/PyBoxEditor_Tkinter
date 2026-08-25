"""
Onde a régua do espaço erra, e contra que referência ela devia medir (F107).

A régua até a F107 era `vão > 0,35 x largura mediana de tinta da linha`
(`VAO_DE_ESPACO`, em `core/diagrama.py`). Ela comparava **tinta com tinta**, e é
aí que ela quebra: algarismo vem com espacejamento tabular — a caixa de tinta
do `1` é um terço do avanço dele —, enquanto a mediana da linha é ditada pelas
minúsculas da prosa. Medido nos `.box` rotulados, o vão mediano entre dois
algarismos vizinhos é **0,45**: já acima do limiar, antes de qualquer espaço
existir. É por isso que `2011` saía `20 1 1` e `147` saía `1 47` — 1.965 números
partidos no Yusupov exportado, 995 no Seirawan.

A régua que entrou é `diagrama.limiar_de_espaco`, e é ela que este instrumento
mediu para escolher os dois números que ela usa.

    python medir_vao.py --pdf "PDF/.../livro editable.pdf" --paginas 20
    python medir_vao.py --pdf "..." --cache pares.npy --varrer

**O gabarito sai da camada de texto, e por palavra — não por caractere.** O
`rawdict` do PyMuPDF devolve a caixa de *avanço* de cada glifo, e não a de
tinta: entre dois caracteres da mesma palavra ela dá vão zero, o que tornaria a
camada inútil como régua de geometria. O que ela tem de bom é outra coisa —
**onde a palavra começa e acaba**. Então a página é segmentada por esta casa, e
cada caixa nossa é atribuída à palavra da camada que a contém. Dois vizinhos na
mesma palavra são um `junto`; em palavras diferentes, um `separado`. A
geometria é sempre a nossa, o rótulo é sempre o do livro, e não há alinhamento
caractere a caractere para dar errado.

Caixa que não cai em palavra nenhuma — respingo, figurinha, coordenada de
diagrama — **sai da conta em vez de virar rótulo palpite**: é a mesma regra que
o `medir_confusao` usa para classe que o modelo não tem.

Reproduz a F107 no ROADMAP.
"""

import argparse
import os
import sys
from typing import List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz

from core import livro
from core.box_model import BoxEntry
from core.diagrama import FATOR_DO_VAO, PISO_DO_VAO, VAO_DE_ESPACO
from core.leitura_de_linha import quebrar_em_linhas
from core.services.learning_service import LearningService

#: O dpi da leitura. O mesmo do `livro.extrair`, e não é detalhe: a régua é
#: relativa, mas a segmentação não é.
DPI = 300


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def palavras_da_camada(page: "fitz.Page", dpi: int = DPI):
    """[(x0, y0, x1, y1, texto)] em pixels da página renderizada."""
    escala = dpi / 72.0
    saida = []
    for x0, y0, x1, y1, texto, *_ in page.get_text("words"):
        saida.append((x0 * escala, y0 * escala, x1 * escala, y1 * escala, texto))
    return saida


def _palavra_de(b: BoxEntry, palavras) -> Optional[int]:
    """O índice da palavra que contém o centro da caixa, ou `None`."""
    cx, cy = (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2
    for i, (x0, y0, x1, y1, _t) in enumerate(palavras):
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return i
    return None


def pares_da_pagina(page: "fitz.Page", classificar, dpi: int = DPI):
    """
    [(vão, largura mediana, avanço mediano, vão mediano, separado?)] da página.

    Um item por par de caixas vizinhas na mesma linha, com as três referências
    candidatas medidas **na linha daquele par** — é assim que a régua as usaria.
    """
    img = livro._pagina_cinza(page, dpi)
    boxes, _tab, _esc, _resp, _col = livro.caixas_e_diagramas(img, classificar)
    palavras = palavras_da_camada(page, dpi)
    if not palavras:
        return []

    saida = []
    for linha in quebrar_em_linhas(boxes):
        if len(linha) < 4:
            continue
        larguras = [b.x2 - b.x1 for b in linha]
        largura = float(np.median(larguras)) or 1.0
        avancos = [b.x1 - a.x1 for a, b in zip(linha, linha[1:])]
        avanco = float(np.median(avancos)) or 1.0
        vaos = [b.x1 - a.x2 for a, b in zip(linha, linha[1:])]
        vao_tipico = float(np.median(vaos))
        # Mediana zero ou negativa é linha de glifos colados: a referência
        # relativa não existe ali, e o piso é quem responde. Ver `regra_nova`.
        vao_tipico = vao_tipico if vao_tipico > 0 else 0.0

        indices = [_palavra_de(b, palavras) for b in linha]
        for (a, b), ia, ib in zip(zip(linha, linha[1:]), indices, indices[1:]):
            if ia is None or ib is None:
                continue
            saida.append((b.x1 - a.x2, largura, avanco, vao_tipico, ia != ib))
    return saida


# ----------------------------------------------------------------------
# As réguas
# ----------------------------------------------------------------------

def regra_atual(vao, largura, avanco, vao_tipico) -> bool:
    """`vão > 0,35 x largura mediana de tinta`. A de produção até a F107."""
    return vao > largura * VAO_DE_ESPACO


def regra_nova(vao, largura, avanco, vao_tipico) -> bool:
    """
    A de produção desde a F107 — a mesma conta de `diagrama.limiar_de_espaco`.

    **A referência certa é o vão, e não a largura.** A pergunta é "este vão é
    maior que os vãos que esta linha usa entre letras da mesma palavra?", e a
    largura do glifo não responde a isso — ela muda com o alfabeto (algarismo
    tabular, `l`, `m`) sem que o espacejamento mude junto. O vão típico da
    linha muda junto por construção: ele **é** o espacejamento.

    Os dois números saem da varredura do `--varrer`; o piso é o que impede a
    régua de inventar espaço na linha que não tem nenhum. Ver `FATOR_DO_VAO`,
    onde a tabela mora.

    O `VAOS_PARA_A_MEDIANA` da produção não aparece aqui porque não pode
    aparecer: `pares_da_pagina` pula linha com menos de 4 caixas, então tudo o
    que este instrumento mede já tem 3 vãos. A guarda existe lá justamente para
    a régua não sair da faixa que estes números cobrem.

    **A conta é repetida aqui de propósito**, e não importada do `diagrama`: o
    instrumento precisa avaliar a régua sobre pares já medidos, sem as caixas
    à mão, e amarrá-lo à assinatura da função de produção o impediria de varrer
    o par de constantes. O que a trava contra divergência é
    `test_a_regra_do_instrumento_e_a_de_producao`, que compara as duas sobre a
    mesma linha — é o mesmo arranjo da F5.2.
    """
    return vao > max(vao_tipico * FATOR_DO_VAO, largura * PISO_DO_VAO)


REGRAS = (("atual  (0,35 x largura)", regra_atual),
          (f"nova   ({FATOR_DO_VAO} x vão típico, piso {PISO_DO_VAO})",
           regra_nova))


def avaliar(pares) -> None:
    sep = np.array([p[4] for p in pares], dtype=bool)
    print(f"pares medidos: {len(pares)}   "
          f"separados de verdade: {int(sep.sum())} ({sep.mean():.1%})\n")

    print(f"{'régua':<38} {'acerto':>8} {'espaço a mais':>14} {'espaço a menos':>15}")
    for nome, fn in REGRAS:
        disse = np.array([fn(*p[:4]) for p in pares])
        acerto = (disse == sep).mean()
        # "A mais" é o defeito que parte a palavra — `20 1 1`. "A menos" é o
        # que cola duas — e as duas contas saem separadas de propósito: elas
        # não custam o mesmo ao leitor nem ao dicionário.
        a_mais = int((disse & ~sep).sum())
        a_menos = int((~disse & sep).sum())
        print(f"{nome:<38} {acerto:>7.2%} {a_mais:>11} ({a_mais/max(1,(~sep).sum()):>4.1%})"
              f" {a_menos:>10} ({a_menos/max(1,sep.sum()):>4.1%})")


def varrer(pares) -> None:
    """
    A grade das três referências candidatas, para o par de números não ser chute.

    **As duas colunas de erro não se somam**, e é por isso que a tabela não traz
    "acerto" sozinho. Espaço a mais parte a palavra (`20 1 1`) e o dicionário a
    perde inteira; espaço a menos cola duas (`theking`) e o dicionário perde as
    duas. A leitura da tabela é escolher o ponto em que a soma das duas é menor
    **e** a de "a mais" não estoura, que é a que o léxico e o PGN mais sentem.
    """
    sep = np.array([p[4] for p in pares], dtype=bool)
    n_junto, n_sep = int((~sep).sum()), int(sep.sum())

    def linha(nome, disse):
        a_mais = int((disse & ~sep).sum())
        a_menos = int((~disse & sep).sum())
        print(f"{nome:<34} {(disse == sep).mean():>7.2%}"
              f" {a_mais:>7} ({a_mais/max(1,n_junto):>5.1%})"
              f" {a_menos:>7} ({a_menos/max(1,n_sep):>5.1%})"
              f" {a_mais + a_menos:>7}")

    vao = np.array([p[0] for p in pares], dtype=float)
    largura = np.array([p[1] for p in pares], dtype=float)
    avanco = np.array([p[2] for p in pares], dtype=float)
    tipico = np.array([p[3] for p in pares], dtype=float)

    cab = f"{'régua':<34} {'acerto':>7} {'a mais':>16} {'a menos':>16} {'soma':>7}"
    fatores = (0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.80,
               1.0, 1.5, 2.0, 2.5, 3.0, 4.0)
    for titulo, ref, com_piso in (
            ("contra a LARGURA de tinta (a régua até a F107)", largura, False),
            ("contra o AVANÇO mediano da linha", avanco, False),
            (f"contra o VÃO típico da linha, com piso {PISO_DO_VAO} x largura",
             tipico, True)):
        print(f"\n{titulo}\n{cab}")
        for k in fatores:
            limite = ref * k
            if com_piso:
                limite = np.maximum(limite, largura * PISO_DO_VAO)
            linha(f"  k = {k}", vao > limite)


def grade(pares) -> None:
    """
    Fator x piso, na soma dos dois erros — é esta grade que escolheu o par.

    **O que ela mostra não é um mínimo, é um planalto.** (2,0; 0,45), (2,25;
    0,45), (2,5; 0,40) e (2,5; 0,45) ficam a menos de 3% um do outro, e é isso
    que faz o par escolhido não ser uma quina: um livro novo não o desloca para
    fora da vizinhança, e não vale reajustá-lo a cada obra.
    """
    sep = np.array([p[4] for p in pares], dtype=bool)
    vao = np.array([p[0] for p in pares], dtype=float)
    largura = np.array([p[1] for p in pares], dtype=float)
    tipico = np.array([p[3] for p in pares], dtype=float)

    pisos = (0.30, 0.35, 0.40, 0.45, 0.50)
    print("\nsoma dos dois erros, fator x piso\n")
    print(f"{'fator':<8}" + "".join(f"{p:>9}" for p in pisos))
    melhor = None
    for f in (1.5, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5):
        somas = []
        for p in pisos:
            disse = vao > np.maximum(tipico * f, largura * p)
            soma = int((disse & ~sep).sum()) + int((~disse & sep).sum())
            somas.append(soma)
            if melhor is None or soma < melhor[0]:
                melhor = (soma, f, p)
        print(f"{f:<8}" + "".join(f"{s:>9}" for s in somas))
    soma, f, p = melhor
    print(f"\nmelhor nesta amostra: fator {f}, piso {p} — soma {soma}."
          f"  Em produção: fator {FATOR_DO_VAO}, piso {PISO_DO_VAO}.")


def main(argv=None) -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--pdf", required=True, help="um PDF com camada de texto")
    ap.add_argument("--paginas", type=int, default=12,
                    help="quantas páginas medir (padrão 12)")
    ap.add_argument("--pular", type=int, default=8,
                    help="quantas páginas pular no começo (padrão 8)")
    ap.add_argument("--varrer", action="store_true",
                    help="a grade das três referências, e não só as duas réguas")
    ap.add_argument("--cache", default=None,
                    help="onde guardar os pares medidos, para varrer sem "
                         "resegmentar a página")
    args = ap.parse_args(argv)

    if args.cache and os.path.exists(args.cache):
        pares = [tuple(l) for l in np.load(args.cache)]
        print(f"{len(pares)} pares do cache {args.cache}\n")
        avaliar(pares)
        if args.varrer:
            varrer(pares)
            grade(pares)
        return 0

    svc = LearningService()
    if not svc.load_predictor():
        print("modelo neural não carregou:", svc.motivo_do_modelo())
        return 1

    doc = fitz.open(args.pdf)
    try:
        pares = []
        fim = min(len(doc), args.pular + args.paginas)
        for n in range(args.pular, fim):
            novos = pares_da_pagina(doc[n], svc.ler_texto)
            pares.extend(novos)
            print(f"  página {n + 1}: {len(novos)} pares", flush=True)
    finally:
        doc.close()

    if not pares:
        print("nenhum par medido — o PDF tem camada de texto?")
        return 1

    if args.cache:
        np.save(args.cache, np.array(pares, dtype=float))

    print()
    avaliar(pares)
    if args.varrer:
        varrer(pares)
        grade(pares)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
