"""Build do aplicativo desktop com PyInstaller.

Uso (Windows, a partir da raiz do projeto)::

    python -m pip install -e ".[desktop]"
    python -m PyInstaller --noconfirm --clean pyboxeditor.spec

O resultado é um diretório ``dist/PyBoxEditor``. O Tesseract continua sendo
uma dependência externa e os pesos grandes de OCR continuam sendo distribuídos
como pacotes verificáveis, não embutidos silenciosamente no executável.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve()


def _data(diretorio: str) -> tuple[str, str]:
    """Copia uma árvore para o mesmo caminho relativo no bundle."""
    origem = ROOT / diretorio
    return str(origem), diretorio.replace("\\", "/")


# O código usa caminhos relativos à raiz do projeto (por exemplo, ``pieces/``
# e ``core/dados/``), portanto os recursos precisam conservar essa topologia.
datas = [
    _data("assets"),
    _data("core/dados"),
    _data("fonts"),
    _data("pieces"),
]

# Os imports locais feitos dentro de handlers também são encontrados pela
# análise do script. Não usar ``collect_submodules`` aqui: isso importaria
# módulos de treino opcionais, Torch e plugins de terceiros que não fazem parte
# do caminho do aplicativo.
hiddenimports = []


a = Analysis(
    [str(ROOT / "appy.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest", "tests", "PyQt5", "PyQt6", "PySide2", "PySide6",
        # Extras ML/OCR são opcionais no wheel e têm seus próprios pacotes de
        # pesos. O bundle base continua funcional com Tesseract externo.
        "torch", "torchvision", "tensorflow", "keras", "easyocr",
        "paddle", "paddleocr", "sklearn", "scipy", "pandas", "skimage",
        "h5py", "shapely", "transformers", "modelscope",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name="PyBoxEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="PyBoxEditor",
)
