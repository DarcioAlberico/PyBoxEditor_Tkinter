"""Só o que o `pyproject.toml` não sabe dizer: os dados que viajam no wheel **quando existem**.

A seção estática `[tool.setuptools.data-files]` quebrava o build num clone limpo —
`error: can't copy 'custom_model.pth': doesn't exist or not a regular file` —, porque os
pesos treinados ficam fora do git de propósito (`.gitignore`; `docs/SETUP.md`: pesos viajam
como pacote verificável). Aqui a lista é calculada: o wheel construído da árvore de trabalho
leva para `share/PyBoxEditor` os modelos que ela tiver, que é onde
`config.paths._raizes_de_recursos` os procura num ambiente instalado; o da CI, que não os
tem, constrói sem eles e o aplicativo abre no modo básico. Todo o resto da configuração
continua no `pyproject.toml`.
"""
from pathlib import Path

from setuptools import setup

#: Os mesmos cinco nomes que a seção estática listava (F125).
DADOS_DO_MODELO = (
    "custom_model.pth",
    "model_meta.json",
    "text_line_model.pth",
    "text_line_model.json",
    "ocr_language_model.json",
)

RAIZ = Path(__file__).resolve().parent
existentes = [nome for nome in DADOS_DO_MODELO if (RAIZ / nome).is_file()]

setup(data_files=[("share/PyBoxEditor", existentes)] if existentes else [])
