"""Só o que o `pyproject.toml` não sabe dizer: os dados que viajam no wheel como `data-files`.

A seção estática `[tool.setuptools.data-files]` quebrava o build num clone limpo —
`error: can't copy 'custom_model.pth': doesn't exist or not a regular file` —, porque os
pesos treinados ficam fora do git de propósito (`.gitignore`; `docs/SETUP.md`: pesos viajam
como pacote verificável). Aqui a lista é calculada: o wheel construído da árvore de trabalho
leva para `share/PyBoxEditor` os modelos que ela tiver, que é onde
`config.paths._raizes_de_recursos` os procura num ambiente instalado; o da CI, que não os
tem, constrói sem eles e o aplicativo abre no modo básico. Todo o resto da configuração
continua no `pyproject.toml`.

**As fontes de diagrama e as peças também vão** (RG-02a, R-41 da revisão geral 2): sem
elas, o programa instalado não desenhava diagrama nenhum e o tabuleiro perdia as figuras.
`fonts/` e `pieces/` não são pacotes, então vão como `data-files` e são achadas por
`config.paths.recurso()`. As fontes saem da lista do `core/dados/fontes_de_diagrama.json`
— um glob `*.otf`/`*.ttf` levaria as originais e as de conferência, e perderia no Linux as
de extensão maiúscula —, com as licenças que as próprias notas citam.
"""
import json
from pathlib import Path

#: Os mesmos cinco nomes que a seção estática listava (F125).
DADOS_DO_MODELO = (
    "custom_model.pth",
    "model_meta.json",
    "text_line_model.pth",
    "text_line_model.json",
    "ocr_language_model.json",
)

#: As licenças que as notas do `fontes_de_diagrama.json` citam ("ver fonts/SkakNew.pdf";
#: o mapa de teclado e a licença da Merida em `fonts/LEEME__D.TXT`).
LICENCAS_DAS_FONTES = ("fonts/SkakNew.pdf", "fonts/LEEME__D.TXT")

RAIZ = Path(__file__).resolve().parent


def arquivos_de_dados(raiz: Path) -> list[tuple[str, list[str]]]:
    """Os `data_files` do wheel: `(destino, [arquivos relativos à raiz])`, só os que existem."""
    def existentes(nomes):
        return [n for n in nomes if (raiz / n).is_file()]

    mapas = json.loads((raiz / "core" / "dados" / "fontes_de_diagrama.json").read_text(encoding="utf-8"))
    fontes = [dado["arquivo"] for dado in mapas["fontes"].values()
              if not Path(dado["arquivo"]).is_absolute()]
    pecas = sorted(p.relative_to(raiz).as_posix() for p in (raiz / "pieces").glob("*.png"))
    grupos = [
        ("share/PyBoxEditor", existentes(DADOS_DO_MODELO)),
        ("share/PyBoxEditor/fonts", existentes(fontes + list(LICENCAS_DAS_FONTES))),
        ("share/PyBoxEditor/pieces", existentes(pecas)),
    ]
    return [(destino, nomes) for destino, nomes in grupos if nomes]


if __name__ == "__main__":
    from setuptools import setup

    setup(data_files=arquivos_de_dados(RAIZ))
