"""
Mede o escritor do editor contra o escritor histórico (`core/exportar.py`) sobre as
mesmas páginas lidas (ED-12; SPEC_EDITOR §16: "a ED-12 mede antes de decidir").

O que se compara, para EPUB e DOCX: o tempo de escrita, o tamanho do arquivo e o que
saiu (capítulos, parágrafos, diagramas) — do `exportar.exportar(paginas, …)` de um lado,
e do caminho do editor (`importar_ir.de_paginas` → `epub.escrever` / `docx_io.escrever`)
do outro; o PDF paginado (`pdf_io`) só o editor faz, e entra na tabela sozinho. Com
`--sintetico`, as páginas são geradas aqui (prosa, títulos, notação, um diagrama
desenhado e uma tabela por página); com `--pdf <arquivo.pdf>`, a leitura é a do leitor
de produção (`core.livro.extrair`), que carrega o modelo neural — demora minutos.

Os números saem no console em Markdown, para colar no "Registro" da ED-12:

    .venv/Scripts/python.exe scripts/medir_editor_vs_exportar.py --sintetico [--paginas 30] [--repeticoes 3]

A decisão (substitui / convive / não substitui) é do registro, não do script: ele só
mede. O critério que o registro usa está no fim do `main`.
"""

from __future__ import annotations

import argparse
import io
import os
import statistics
import sys
import tempfile
import time
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

FEN_LOPEZ = "r1bqkbnr/1ppp1ppp/p1n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4"


def paginas_sinteticas(n: int):
    """`n` `PaginaExtraida` com título, prosa, notação, um diagrama desenhado e uma tabela."""
    from core import livro as livro_mod, render_diagrama

    png, largura, altura = render_diagrama.desenhar(FEN_LOPEZ.split()[0], lado_px=256)
    linhas = render_diagrama.linhas(FEN_LOPEZ.split()[0], render_diagrama.carregar(render_diagrama.FONTE_PADRAO),
                                    "branca")
    paginas = []
    for k in range(n):
        blocos = [livro_mod.Paragrafo(f"Capítulo {k + 1}", titulo=True, nivel=1)]
        for i in range(6):
            blocos.append(livro_mod.Paragrafo(
                f"Parágrafo {i + 1} da página {k + 1}: " + "a prosa do livro segue por aqui, com frases inteiras "
                "e uma palavra em negrito. " * 3, negrito=[(10, 17)]))
        blocos.append(livro_mod.Paragrafo(f"Kasparov – Karpov, partida {k + 1}", titulo=True, nivel=2))
        blocos.append(livro_mod.Paragrafo("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O"))
        blocos.append(livro_mod.Figura(png, largura, altura, fen=FEN_LOPEZ, origem="render", linhas=list(linhas),
                                       fonte=render_diagrama.FONTE_PADRAO))
        blocos.append(livro_mod.Tabela([["Jogador", "Pontos"], ["A", "1"], ["B", "½"]]))
        paginas.append(livro_mod.PaginaExtraida(numero=k, blocos=blocos, largura=1200, altura=1700, dpi=200))
    return paginas


def paginas_do_pdf(caminho: str):
    from core import livro as livro_mod

    return list(livro_mod.extrair(caminho))


def _tempo(funcao, repeticoes: int) -> float:
    tempos = []
    for _ in range(repeticoes):
        inicio = time.perf_counter()
        funcao()
        tempos.append(time.perf_counter() - inicio)
    return statistics.median(tempos)


def _conteudo_epub(caminho: str) -> dict[str, int]:
    with zipfile.ZipFile(caminho) as z:
        nomes = z.namelist()
        xhtml = [n for n in nomes if n.endswith((".xhtml", ".html"))]
        textos = "".join(z.read(n).decode("utf-8", "replace") for n in xhtml)
    return {"capitulos": len(xhtml), "paragrafos": textos.count("<p"), "diagramas": textos.count("diagrama"),
            "imagens": len([n for n in nomes if n.endswith(".png")]),
            "fontes": len([n for n in nomes if n.lower().endswith((".ttf", ".otf"))])}


def _conteudo_docx(caminho: str) -> dict[str, int]:
    with zipfile.ZipFile(caminho) as z:
        doc = z.read("word/document.xml").decode("utf-8", "replace")
        nomes = z.namelist()
    return {"capitulos": doc.count("Heading1") + doc.count("Heading 1") or doc.count("<w:pStyle w:val=\"Heading1\""),
            "paragrafos": doc.count("<w:p>") + doc.count("<w:p "), "diagramas": doc.count("<w:drawing>"),
            "imagens": len([n for n in nomes if n.startswith("word/media/")]),
            "fontes": len([n for n in nomes if n.startswith("word/fonts/")])}


def medir(paginas, repeticoes: int = 3) -> list[dict]:
    from core import exportar
    from core.editor import docx_io, epub, importar_ir, pdf_io

    pasta = tempfile.mkdtemp(prefix="pbe-medir-")
    linhas: list[dict] = []
    # o caminho do editor: as páginas viram Livro uma vez (também medido)
    t_modelo = _tempo(lambda: importar_ir.de_paginas(paginas, document_id="medida", titulo="Medida", idioma="pt"),
                      repeticoes)
    livro, _rel = importar_ir.de_paginas(paginas, document_id="medida", titulo="Medida", idioma="pt")
    linhas.append({"formato": "modelo", "quem": "editor (`importar_ir.de_paginas`)", "tempo_s": t_modelo,
                   "tamanho_kb": 0, "conteudo": {"capitulos": len(livro.capitulos),
                                                 "blocos": sum(len(c.blocos) for c in livro.capitulos)}})
    for formato in ("epub", "docx"):
        legado = os.path.join(pasta, f"legado.{formato}")
        t_legado = _tempo(lambda: exportar.exportar(paginas, legado, formato=formato, titulo="Medida", autor="",
                                                    diagramas="png"), repeticoes)
        conteudo = _conteudo_epub(legado) if formato == "epub" else _conteudo_docx(legado)
        linhas.append({"formato": formato, "quem": "histórico (`exportar.exportar`)", "tempo_s": t_legado,
                       "tamanho_kb": os.path.getsize(legado) / 1024, "conteudo": conteudo})
        saida = os.path.join(pasta, f"editor.{formato}")
        if formato == "epub":
            escrever = lambda: epub.escrever(livro, saida)          # noqa: E731
        else:
            escrever = lambda: docx_io.escrever(livro, saida)       # noqa: E731
        t_editor = _tempo(escrever, repeticoes)
        conteudo = _conteudo_epub(saida) if formato == "epub" else _conteudo_docx(saida)
        linhas.append({"formato": formato, "quem": f"editor (`{'epub' if formato == 'epub' else 'docx_io'}.escrever`)",
                       "tempo_s": t_editor, "tamanho_kb": os.path.getsize(saida) / 1024, "conteudo": conteudo})
    pdf = os.path.join(pasta, "editor.pdf")
    t_pdf = _tempo(lambda: pdf_io.escrever(livro, pdf), repeticoes)
    rel = pdf_io.escrever(livro, pdf)
    linhas.append({"formato": "pdf", "quem": "editor (`pdf_io.escrever`) — o histórico não faz", "tempo_s": t_pdf,
                   "tamanho_kb": os.path.getsize(pdf) / 1024,
                   "conteudo": {"paginas": rel.metadados.get("paginas", 0), "capitulos": rel.capitulos}})
    return linhas


def tabela(linhas: list[dict]) -> str:
    saida = ["| Formato | Quem escreve | Tempo (mediana) | Tamanho | O que saiu |", "|---|---|---|---|---|"]
    for li in linhas:
        conteudo = ", ".join(f"{k} {v}" for k, v in li["conteudo"].items())
        tamanho = f"{li['tamanho_kb']:.0f} KB" if li["tamanho_kb"] else "—"
        saida.append(f"| {li['formato']} | {li['quem']} | {li['tempo_s'] * 1000:.0f} ms | {tamanho} | {conteudo} |")
    return "\n".join(saida)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mede o escritor do editor contra o histórico.")
    parser.add_argument("--sintetico", action="store_true", help="páginas geradas aqui (sem OCR)")
    parser.add_argument("--pdf", default="", help="um PDF lido pelo leitor de produção (carrega o modelo)")
    parser.add_argument("--paginas", type=int, default=30)
    parser.add_argument("--repeticoes", type=int, default=3)
    args = parser.parse_args(argv)
    if not args.sintetico and not args.pdf:
        parser.error("diga --sintetico ou --pdf <arquivo>")
    paginas = paginas_do_pdf(args.pdf) if args.pdf else paginas_sinteticas(args.paginas)
    linhas = medir(paginas, args.repeticoes)
    origem = f"`{os.path.basename(args.pdf)}`" if args.pdf else f"{args.paginas} páginas sintéticas"
    saida = io.StringIO()
    saida.write(f"Medição de {origem}, {args.repeticoes} repetições (mediana):\n\n")
    saida.write(tabela(linhas) + "\n")
    texto = saida.getvalue()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
