"""
A caixa pela geometria da linha (F112): a tabela das classes, e quanto a poda
rende nas páginas rotuladas.

    python medir_geometria.py             # a medida, com a tabela de fora do livro
    python medir_geometria.py --gravar    # e grava core/dados/geometria_das_classes.json
    python medir_geometria.py --exemplos 40

**A população é a do livro, e não a do gabarito.** As caixas saem de
`livro.caixas_e_diagramas`, as linhas de `quebrar_em_linhas` e a leitura do
`leitor_de_texto` — o que `_texto_da_linha` vê —, e a verdade de cada caixa vem
do `.box` rotulado casado pelo centro (`avaliacao_pagina.comparar`). A primeira
versão desta medida usou as caixas do gabarito, e a geometria delas não é a de
produção: uma caixa corrigida à mão costuma ser mais larga que a tinta, e as
quebras que ela mostrava eram da caixa.

**A tabela que mede um livro não viu esse livro.** Cada livro é medido com a
tabela estimada nos outros (`estimar_tabela`), porque é o caso da produção: o
livro exportado não está nas páginas rotuladas. A gravada (`--gravar`) usa
todos.

**A coluna `quebra` é teto, e não conta.** Conferido a olho em 2026-09-24, as
quebras da medida eram todas erro do gabarito — `Marin's` rotulado com vírgula,
`Chéron,` com apóstrofo, `Seirawan` com `W`, `defeSa`, `c0ntrajogo`. O
`--exemplos` imprime cada troca com a linha, para quem for conferir de novo.

As páginas rotuladas são as mesmas em que o modelo treinou (F117), e ali a
rede já erra pouco caixa: o que esta medida diz é que a poda **não quebra** e
conserta o que sobra. O ganho de verdade é no livro que o modelo não viu, e
esse se mede sem gabarito, pela razão de caixa do `medir_prosa.py`.

Reproduz a F112 no ROADMAP. Sem cobertura de teste, como os outros `medir_*.py`
(o `pytest.ini` restringe a coleta a `tests/`); a peça de produção que ele
chama, `core.geometria_da_linha`, tem a dela.
"""

import argparse
import datetime
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import diagrama, formato_box, geometria_da_linha as gl, livro, vertical
from core.avaliacao_pagina import comparar, normalizar
from core.calibracao_de_pagina import MIN_ROTULADOS, paginas_rotuladas
from medir_tamanho import _ler_cinza, livro_de, paginas_com_box

#: Os livros do corpus rotulado que estão em português — a máscara de
#: alfabeto (F109) é a do idioma, e o leitor de produção a aplica.
EM_PORTUGUES = ("Darcy Lima", "Xadrez Vitorioso")


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def paginas():
    """`[(imagem, .box)]` — as de `paginas_com_box` e as de `paginas_rotuladas`."""
    achadas = {box: img for img, box in paginas_com_box(".")}
    for img, box in paginas_rotuladas("."):
        achadas.setdefault(box, img)
    return sorted((img, box) for box, img in achadas.items())


class Caixa:
    """Uma caixa de produção com o que a poda precisa e a verdade ao lado."""

    __slots__ = ("box", "recorte", "leitura", "topk", "verdade")

    def __init__(self, box, recorte, leitura, topk, verdade):
        self.box, self.recorte = box, recorte
        self.leitura, self.topk, self.verdade = leitura, topk, verdade


def coletar(servico):
    """`{livro: [linha de Caixa, ...]}` pelo caminho do livro."""
    por_livro = defaultdict(list)
    for img_p, box_p in paginas():
        img = _ler_cinza(img_p)
        if img is None:
            continue
        rotulados = [b for b in formato_box.ler(box_p, img.shape[0])
                     if b.char and b.x2 > b.x1 and b.y2 > b.y1
                     and getattr(b, "source", "") != "neural"]
        if len(rotulados) < MIN_ROTULADOS:
            continue
        obra = livro_de(box_p)
        idioma = "pt" if obra.startswith(EM_PORTUGUES) else "en"
        classificar = servico.leitor_de_texto(idioma)
        boxes, _tab, _esc, _resp, _col = livro.caixas_e_diagramas(img, classificar)
        pares = comparar(boxes, rotulados).pares
        verdade = {id(boxes[i]): rotulados[j].char for i, j in pares}
        n = 0
        for linha in livro.quebrar_em_linhas(boxes):
            caixas = []
            for b in linha:
                recorte = vertical.recorte_de_pe(img, b)
                if recorte.size == 0:
                    continue
                caixas.append(Caixa(b, recorte, classificar(recorte),
                                    servico.candidatas(recorte, k=gl.CANDIDATAS),
                                    verdade.get(id(b))))
            n += len(caixas)
            if caixas:
                por_livro[obra].append(caixas)
        print(f"  {os.path.basename(box_p)}: {n} caixas, {len(pares)} com verdade "
              f"[{idioma}]", flush=True)
    return por_livro


def amostras_da_tabela(linhas):
    """As linhas como `estimar_tabela` as quer: `[(glifo, verdade)]`."""
    for linha in linhas:
        yield [(gl.medir(c.recorte, c.box), c.verdade)
               for c in linha if c.verdade]


def podar(linha, tabela):
    """A poda de produção sobre uma linha, com o top-k já guardado."""
    topk = {id(c.recorte): c.topk for c in linha}
    return gl.podar([c.box for c in linha], [c.recorte for c in linha],
                    [c.leitura for c in linha],
                    lambda recorte, _k: topk[id(recorte)],
                    limiar_de_espaco=diagrama.limiar_de_espaco(
                        [c.box for c in linha]),
                    limiar_de_confirmacao=livro.CONF_MINIMA, tabela=tabela)


def medir(por_livro, tabela_de):
    """Totais, por livro, e as trocas — com a tabela que `tabela_de(livro)` der."""
    total = Counter()
    por_obra = {}
    trocas = []
    for obra, linhas in sorted(por_livro.items()):
        conta = Counter()
        tabela = tabela_de(obra)
        for linha in linhas:
            mudou = podar(linha, tabela)
            for i, c in enumerate(linha):
                if c.verdade is None:
                    conta["sem_verdade_tocada"] += i in mudou
                    continue
                v = normalizar(c.verdade)
                lida, conf = c.leitura
                nova, conf_nova = mudou.get(i, (lida, conf))
                antes = normalizar(lida or "")
                depois = normalizar(nova or "")
                # No texto, o que a confiança derruba não sai (`CONF_MINIMA`).
                texto_antes = antes if conf >= livro.CONF_MINIMA else ""
                texto_depois = depois if conf_nova >= livro.CONF_MINIMA else ""
                conta["n"] += 1
                conta["antes"] += antes == v
                conta["depois"] += depois == v
                conta["texto_antes"] += texto_antes == v
                conta["texto_depois"] += texto_depois == v
                if texto_antes != texto_depois:
                    tipo = ("conserto" if texto_depois == v else
                            "quebra" if texto_antes == v else "neutra")
                    conta[tipo] += 1
                    conta["tocou"] += 1
                    trocas.append((tipo, obra, c, texto_antes or "∅",
                                   texto_depois or "∅", linha))
        por_obra[obra] = conta
        total.update(conta)
    return total, por_obra, trocas


def _pct(a, n):
    return f"{100.0 * a / n:6.2f}%" if n else "   —   "


def relatar(total, por_obra, trocas, exemplos):
    n = total["n"]
    print(f"\n{n} caixas com verdade, {len(por_obra)} livros "
          "(cada um medido com a tabela dos outros)\n")
    print(f"{'':44s} {'leitura':>9s} {'no texto':>9s}")
    print(f"{'sem a poda':44s} {_pct(total['antes'], n)} {_pct(total['texto_antes'], n)}")
    print(f"{'com a poda':44s} {_pct(total['depois'], n)} {_pct(total['texto_depois'], n)}")
    print(f"\ntrocas no texto: {total['tocou']}  consertos {total['conserto']}  "
          f"quebras {total['quebra']} (teto — ver o cabeçalho)  neutras {total['neutra']}")
    print(f"caixas sem verdade tocadas: {total['sem_verdade_tocada']}")
    print(f"\n{'livro':46s} {'n':>6s} {'antes':>8s} {'depois':>8s} {'+':>4s} {'-':>4s}")
    for obra, conta in por_obra.items():
        print(f"{obra[:46]:46s} {conta['n']:6d} {_pct(conta['texto_antes'], conta['n'])}"
              f" {_pct(conta['texto_depois'], conta['n'])} {conta['conserto']:4d}"
              f" {conta['quebra']:4d}")
    tipos = Counter((t, a, d) for t, _o, _c, a, d, _l in trocas)
    print("\npor troca:")
    for (t, a, d), k in sorted(tipos.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"  {t:9s} {a!r} → {d!r}  {k}")
    if exemplos:
        print("\nexemplos:")
        for t, obra, c, a, d, linha in trocas[:exemplos]:
            lida = "".join((x.leitura[0] or "·") for x in linha)
            print(f"  {t:9s} {a!r}→{d!r} (verdade {c.verdade!r})  {obra[:28]}  {lida[:70]}")


def main(argv=None):
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--gravar", action="store_true",
                    help=f"grava a tabela de todos os livros em {gl.CAMINHO_DA_TABELA}")
    ap.add_argument("--exemplos", type=int, default=0)
    args = ap.parse_args(argv)

    from core.services.learning_service import LearningService
    servico = LearningService()
    if not servico.load_predictor():
        print(servico.motivo_do_modelo())
        return 1
    print("lendo as páginas rotuladas pelo caminho do livro...")
    por_livro = coletar(servico)

    fora = {obra: gl.estimar_tabela(amostras_da_tabela(
                [l for outra, ls in por_livro.items() if outra != obra for l in ls]))
            for obra in por_livro}
    relatar(*medir(por_livro, lambda obra: fora[obra]), args.exemplos)

    if args.gravar:
        todas = [l for ls in por_livro.values() for l in ls]
        tabela = gl.estimar_tabela(amostras_da_tabela(todas))
        dados = gl.dados_da_tabela(
            tabela,
            nota=("Onde o corpo de tinta de cada classe comeca e acaba, em alturas "
                  "de x acima da base da linha (F112). Gerado por "
                  "medir_geometria.py --gravar -- nao editar a mao."),
            gerado_em=datetime.date.today().isoformat(),
            livros=len(por_livro),
            caracteres=sum(1 for l in todas for c in l if c.verdade))
        with open(gl.CAMINHO_DA_TABELA, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=True, indent=1)
            f.write("\n")
        gl.carregar_tabela.cache_clear()
        print(f"\ntabela gravada: {len(tabela)} classes em {gl.CAMINHO_DA_TABELA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
