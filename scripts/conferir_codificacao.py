"""A codificação dos arquivos de texto do repositório: UTF-8 sem BOM, e sem mojibake.

O que este verificador pega, e por quê:

- **Byte fora de UTF-8.** O `requirements.txt` já teve a última linha em UTF-16 e o pip
  leu "P y M u P D F"; um `.py` em cp1252 quebra o `import` em qualquer máquina que não
  seja a que o gravou.
- **BOM.** O marcador `EF BB BF` no começo do arquivo é UTF-8 válido, mas ferramentas que
  leem byte a byte (o pip, o Tcl, um `grep`) o veem como lixo na primeira linha.
- **Mojibake.** A ferramenta que grava em cp1252 um texto que já era UTF-8 produz
  `Ã£` onde havia `ã` — cada byte da sequência UTF-8 lido como um caractere cp1252 e
  gravado de novo em UTF-8. Isso aconteceu em 2026-09-18 e voltou em 2026-09-26, em
  dezenove arquivos (`docs/ANALISE_GERAL_2026-10-06.md`, item 2). A dupla codificação
  é reversível: `texto.encode("cp1252").decode("utf-8")` devolve o original, e é o que
  `desfazer_mojibake` faz, trecho a trecho, sem tocar no que já estava certo.

Quem precisa escrever mojibake de propósito — o relatório do editor, que o detecta no
texto de um livro, e o teste dele — põe `mojibake intencional` na mesma linha (num
comentário), e a linha fica isenta da conferência e da correção.

`tests/test_codificacao.py` roda `problemas` sobre todo arquivo de texto rastreado e
falha se algum voltar. Na mão:

    python scripts/conferir_codificacao.py              # lista o que há
    python scripts/conferir_codificacao.py --corrigir   # desfaz o mojibake e tira o BOM

A lista de arquivos vem do `git ls-files`; sem o git (uma exportação do `git archive`,
por exemplo), a árvore inteira é percorrida menos as pastas que não são fonte.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

#: O que nunca é texto. Qualquer outra extensão passa pela leitura em UTF-8 — e um tipo
#: binário novo falha alto no teste, que é o aviso para acrescentá-lo aqui e no
#: `.gitattributes`.
EXTENSOES_BINARIAS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".otf", ".ttf", ".woff", ".woff2", ".pdf",
    ".pth", ".npz", ".gz", ".7z", ".zip", ".epub", ".docx", ".pyc",
})

#: Pastas que não são fonte, para quando não há `git ls-files` que diga o que é rastreado.
PASTAS_FORA = frozenset({
    ".git", ".venv", "venv", "env", "build", "dist", "__pycache__", ".claude", ".idea",
    ".pytest_cache", ".ruff_cache", "node_modules", "pyboxeditor.egg-info",
    "_tmp_sintetico", "ilovepdf_pages-to-jpg", "relatorio_treino_erros", "revisao_ocr",
    "revisao_letras", "PDF", "Diagramas-outro-projeto",
})

BOM = b"\xef\xbb\xbf"

#: A linha que traz isto é mojibake de propósito, e fica fora da conferência e da correção.
MARCADOR = "mojibake intencional"

# Os caracteres em que o cp1252 transforma os bytes de continuação do UTF-8 (0x80–0xBF):
# ` ‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ` e ` ¡¢£…¿`. Cinco bytes não existem no cp1252 e por isso
# não aparecem — o mojibake que passou por eles não é reversível, e também não ocorreu.
_CONTINUACAO = "".join(
    bytes([b]).decode("cp1252", errors="ignore") for b in range(0x80, 0xC0)
)
_CLASSE = "[" + re.escape(_CONTINUACAO) + "]"
#: Uma sequência UTF-8 lida como cp1252: o primeiro byte (`Â`/`Ã` para dois bytes,
#: `à`–`ï` para três, `ð`–`ó` para quatro) seguido dos de continuação.
MOJIBAKE = re.compile(
    "(?:[ÂÃ]" + _CLASSE
    + "|[à-ï]" + _CLASSE + "{2}"
    + "|[ð-ó]" + _CLASSE + "{3})+"
)


def arquivos_de_texto(raiz: str | os.PathLike[str] | None = None) -> list[Path]:
    """Os arquivos de texto do repositório: o que o git rastreia, menos o binário."""
    raiz = Path(raiz) if raiz is not None else Path(__file__).resolve().parents[1]
    try:
        saida = subprocess.run(["git", "ls-files", "-z"], cwd=raiz, capture_output=True,
                               check=True).stdout
        nomes = [n for n in saida.decode("utf-8", errors="surrogateescape").split("\0") if n]
        candidatos = [raiz / n for n in nomes]
    except (OSError, subprocess.CalledProcessError):
        candidatos = []
        for pasta, subpastas, nomes in os.walk(raiz):
            subpastas[:] = sorted(
                s for s in subpastas
                if s not in PASTAS_FORA and not s.startswith("training_data"))
            candidatos.extend(Path(pasta) / n for n in sorted(nomes))
    return [p for p in candidatos
            if p.suffix.lower() not in EXTENSOES_BINARIAS and p.is_file()]


def desfazer_mojibake(texto: str) -> str:
    """O texto com cada trecho em dupla codificação devolvido ao original.

    Só mexe no que casa com `MOJIBAKE` **e** volta a ser UTF-8 válido pelo caminho
    inverso; o que já estava certo — um `é` de verdade, um travessão — não casa, ou não
    sobrevive à volta, e fica como está. Duas passagens cobrem o texto codificado duas
    vezes. A linha com `MARCADOR` não é tocada.
    """
    def devolver(m: re.Match[str]) -> str:
        trecho = m.group(0)
        try:
            return trecho.encode("cp1252").decode("utf-8")
        except UnicodeError:
            return trecho

    def desfazer_linha(linha: str) -> str:
        if MARCADOR in linha:
            return linha
        anterior = None
        for _ in range(3):
            if linha == anterior:
                break
            anterior = linha
            linha = MOJIBAKE.sub(devolver, linha)
        return linha

    return "\n".join(desfazer_linha(linha) for linha in texto.split("\n"))


def problemas(caminho: str | os.PathLike[str]) -> list[str]:
    """O que há de errado com a codificação de um arquivo, em frases; vazio é "nada"."""
    caminho = Path(caminho)
    dados = caminho.read_bytes()
    achados: list[str] = []
    if dados.startswith(BOM):
        achados.append("começa com BOM")
        dados = dados[len(BOM):]
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError as erro:
        linha = dados.count(b"\n", 0, erro.start) + 1
        achados.append(f"linha {linha}: byte {dados[erro.start]:#04x} fora de UTF-8")
        return achados
    for numero, linha in enumerate(texto.split("\n"), 1):
        if MARCADOR in linha:
            continue
        m = MOJIBAKE.search(linha)
        if m and desfazer_mojibake(m.group(0)) != m.group(0):
            achados.append(f"linha {numero}: mojibake {m.group(0)!r}")
            break
    return achados


def corrigir(caminho: str | os.PathLike[str]) -> bool:
    """Tira o BOM e desfaz o mojibake, se houver; devolve se gravou. Não toca no que não lê."""
    caminho = Path(caminho)
    dados = caminho.read_bytes()
    original = dados
    if dados.startswith(BOM):
        dados = dados[len(BOM):]
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        return False
    novo = desfazer_mojibake(texto).encode("utf-8")
    if novo == original:
        return False
    caminho.write_bytes(novo)
    return True


def relatorio(caminhos: Iterable[Path], raiz: Path) -> list[str]:
    linhas = []
    for caminho in caminhos:
        for achado in problemas(caminho):
            linhas.append(f"{caminho.relative_to(raiz).as_posix()}: {achado}")
    return linhas


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--corrigir", action="store_true",
                        help="desfaz o mojibake e tira o BOM dos arquivos em que os achar")
    parser.add_argument("--raiz", default=None, help="a raiz do repositório (padrão: a deste script)")
    args = parser.parse_args(argv)
    raiz = Path(args.raiz).resolve() if args.raiz else Path(__file__).resolve().parents[1]
    caminhos = arquivos_de_texto(raiz)
    if args.corrigir:
        gravados = [c for c in caminhos if corrigir(c)]
        for c in gravados:
            print(f"corrigido  {c.relative_to(raiz).as_posix()}")
    achados = relatorio(caminhos, raiz)
    for linha in achados:
        print(linha)
    print(f"{len(caminhos)} arquivos de texto; {len(achados)} com problema")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
