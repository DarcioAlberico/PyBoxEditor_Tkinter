"""
Mede o que a ida e volta do editor perde num corpus de EPUBs de terceiros (RG-10, R-26 da
revisão geral 2).

Cada livro da pasta (`config.paths.corpus_de_epubs()`, ou `--pasta`) é lido pelo editor
(`epub.ler`) e gravado de volta (`epub.escrever`), sem nenhuma edição; o script compara o
original com o gravado e conta, por livro:

- **atributos perdidos**, por `elemento@atributo` — ocorrências no original menos no
  gravado, somadas sobre os XHTML de mesmo nome (o `id` e o `class` de `li`, `td`, `img`,
  `body`… que o leitor aceitava e descartava);
- **elementos perdidos**, por nome, do mesmo jeito;
- **atributos perdidos do OPF** (o `itemref`, o `item`, os `dc:*`), do mesmo jeito;
- **arquivos perdidos**: entradas do zip original que não estão no gravado.

O que o relatório de conversão do editor já avisa ao usuário é perda **declarada**; o
script guarda os avisos de leitura e de gravação de cada livro ao lado das contagens.

    python scripts/medidas/medir_ida_e_volta_epub.py --saida preview_ocr/ab/ida-e-volta-antes
    python scripts/medidas/medir_ida_e_volta_epub.py --pasta outra/pasta --livros 3

Grava `<saida>/ida_e_volta.json` (por livro e o total). Sem a pasta do corpus, avisa e
sai 0: os livros são do usuário e não estão no git.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.paths import corpus_de_epubs  # noqa: E402
from core.editor import epub  # noqa: E402

#: Atributos que o escritor regenera de propósito, e cuja falta não é perda do livro.
_REGENERADOS = {"xmlns", "xmlns:epub", "xml:lang"}


class _Contador(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elementos: Counter = Counter()
        self.atributos: Counter = Counter()

    def handle_starttag(self, tag, attrs):
        self.elementos[tag] += 1
        for nome, _valor in attrs:
            if nome not in _REGENERADOS:
                self.atributos[f"{tag}@{nome}"] += 1

    handle_startendtag = handle_starttag


def _contar(dados: bytes) -> _Contador:
    contador = _Contador()
    contador.feed(dados.decode("utf-8", errors="replace"))
    return contador


def _perdas(antes: Counter, depois: Counter) -> dict[str, int]:
    return {chave: n for chave, n in sorted((antes - depois).items()) if n}


def comparar(original: str, gravado: str) -> dict:
    with zipfile.ZipFile(original) as a, zipfile.ZipFile(gravado) as b:
        nomes_a, nomes_b = set(a.namelist()), set(b.namelist())
        el_a, el_b, at_a, at_b, opf_a, opf_b = (Counter() for _ in range(6))
        for nome in sorted(nomes_a & nomes_b):
            baixo = nome.lower()
            if baixo.endswith((".xhtml", ".html", ".htm")):
                ca, cb = _contar(a.read(nome)), _contar(b.read(nome))
                el_a += ca.elementos
                el_b += cb.elementos
                at_a += ca.atributos
                at_b += cb.atributos
            elif baixo.endswith(".opf"):
                opf_a += _contar(a.read(nome)).atributos
                opf_b += _contar(b.read(nome)).atributos
        perdidos = sorted(n for n in nomes_a - nomes_b if not n.endswith("/"))
    return {"atributos": _perdas(at_a, at_b), "elementos": _perdas(el_a, el_b),
            "opf": _perdas(opf_a, opf_b), "arquivos": perdidos}


def medir(pasta: Path, livros: int | None = None) -> dict:
    caminhos = sorted(p for p in pasta.glob("*.epub"))[:livros]
    saida: dict = {"livros": {}, "total": {"atributos": Counter(), "elementos": Counter(),
                                           "opf": Counter(), "arquivos": 0}}
    with tempfile.TemporaryDirectory() as tmp:
        for caminho in caminhos:
            gravado = os.path.join(tmp, "ida_e_volta.epub")
            try:
                livro, rel_leitura = epub.ler(str(caminho))
                rel_gravacao = epub.escrever(livro, gravado)
                resultado = comparar(str(caminho), gravado)
            except Exception as erro:      # noqa: BLE001 — um livro que não vai e volta é dado da medida
                saida["livros"][caminho.name] = {"erro": f"{type(erro).__name__}: {erro}"}
                print(f"{caminho.name}: ERRO {type(erro).__name__}: {erro}")
                continue
            resultado["avisos_de_leitura"] = list(rel_leitura.avisos)
            resultado["avisos_de_gravacao"] = list(rel_gravacao.avisos)
            saida["livros"][caminho.name] = resultado
            for chave in ("atributos", "elementos", "opf"):
                saida["total"][chave].update(resultado[chave])
            saida["total"]["arquivos"] += len(resultado["arquivos"])
            print(f"{caminho.name}: {sum(resultado['atributos'].values())} atributo(s), "
                  f"{sum(resultado['elementos'].values())} elemento(s), {sum(resultado['opf'].values())} do OPF, "
                  f"{len(resultado['arquivos'])} arquivo(s) perdidos")
    for chave in ("atributos", "elementos", "opf"):
        saida["total"][chave] = dict(saida["total"][chave].most_common())
    return saida


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--pasta", type=Path, default=None)
    ap.add_argument("--livros", type=int, default=None)
    ap.add_argument("--saida", default="")
    args = ap.parse_args(argv)
    pasta = args.pasta or corpus_de_epubs()
    if not pasta.is_dir():
        print(f"AVISO: o corpus de EPUBs não existe em {pasta}; nada a medir "
              "(PYBOXEDITOR_CORPUS_EPUB reaponta a pasta).")
        return 0
    resultado = medir(pasta, args.livros)
    total = resultado["total"]
    print(f"TOTAL: {sum(total['atributos'].values())} atributo(s), {sum(total['elementos'].values())} "
          f"elemento(s), {sum(total['opf'].values())} do OPF, {total['arquivos']} arquivo(s) perdidos; "
          f"mais frequentes: {list(total['atributos'].items())[:8]}")
    if args.saida:
        os.makedirs(args.saida, exist_ok=True)
        with open(os.path.join(args.saida, "ida_e_volta.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(resultado, ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
