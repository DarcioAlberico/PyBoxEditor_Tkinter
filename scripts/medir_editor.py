"""
Mede o editor de livros: `carregar`, `sincronizar` (só o que mudou), `dump` (o
capítulo inteiro relido do widget para o modelo) e a latência de uma tecla simulada
num capítulo de ~20 páginas (ED-03; SPEC_EDITOR §13.1).

Os números saem no console; os `assert` moram em `tests/test_editor_desempenho.py`
(`slow`, fora do gate padrão). Rodar:

    .venv/Scripts/python.exe scripts/medir_editor.py [--paginas 20] [--repeticoes 3]

O capítulo é gerado por `tests/editor_gerador.py` (prosa, títulos, listas, citações,
quebras suaves; sem objetos, que a ED-04/05 medem), com cerca de dez blocos por
página. A janela é `withdraw`n: o que se mede é o widget e o modelo, não a pintura.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
import tkinter as tk

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tests"))

BLOCOS_POR_PAGINA = 10


def capitulo_de(paginas: int):
    """Um capítulo com ~`paginas` páginas, só de blocos que a ED-03 desenha por texto."""
    import editor_gerador as gerador
    from core.editor import modelo as m

    objetos = (m.Diagrama, m.Figura, m.Tabela, m.IlhaBruta, m.MarcaDePagina, m.QuebraDePagina, m.Separador)
    blocos = []
    semente = 1
    while len(blocos) < paginas * BLOCOS_POR_PAGINA:
        cap = gerador.capitulo(semente)
        for b in cap.blocos:
            if isinstance(b, objetos):
                continue
            for interno in m.blocos_do_capitulo(m.Capitulo(arquivo="x", blocos=[b])):
                if isinstance(interno, m.Paragrafo):
                    interno.trechos = [t for t in interno.trechos if not t.ilha]
            blocos.append(b)
        semente += 1
    return m.Capitulo(arquivo="Text/medida.xhtml", blocos=blocos[: paginas * BLOCOS_POR_PAGINA])


def medir(paginas: int = 20, repeticoes: int = 3) -> dict[str, float]:
    from core.editor import modelo as m
    from ui.editor.texto_rico import TextoRico

    raiz = tk.Tk()
    raiz.withdraw()
    widget = TextoRico(raiz)
    widget.pack(fill="both", expand=True)
    cap = capitulo_de(paginas)
    caracteres = sum(len(m.texto_de(b)) for b in cap.blocos)
    tempos: dict[str, list[float]] = {"carregar": [], "sincronizar": [], "dump": [], "tecla": []}
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        widget.carregar(cap)
        tempos["carregar"].append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        copia = widget.sincronizar()
        tempos["sincronizar"].append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        copia = widget.sincronizar(reler=True)
        tempos["dump"].append(time.perf_counter() - t0)
        assert m.igual(copia, cap), "o capítulo medido não fecha a ida e volta"
        # Uma tecla no meio do capítulo: inserir um caractere e reconciliar o bloco.
        meio = widget.ordem[len(widget.ordem) // 2]
        widget.ir_para(meio, 3)
        t0 = time.perf_counter()
        widget.inserir("x")
        tempos["tecla"].append(time.perf_counter() - t0)
    raiz.destroy()
    saida = {chave: statistics.median(v) for chave, v in tempos.items()}
    saida["blocos"] = len(cap.blocos)
    saida["caracteres"] = caracteres
    return saida


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mede carregar/sincronizar/dump/tecla do modo texto.")
    parser.add_argument("--paginas", type=int, default=20)
    parser.add_argument("--repeticoes", type=int, default=3)
    args = parser.parse_args(argv)
    resultado = medir(args.paginas, args.repeticoes)
    print(f"capítulo de {args.paginas} páginas: {resultado['blocos']} blocos, {resultado['caracteres']} caracteres")
    for chave in ("carregar", "sincronizar", "dump", "tecla"):
        print(f"  {chave:12s} {resultado[chave] * 1000:8.1f} ms (mediana de {args.repeticoes})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
