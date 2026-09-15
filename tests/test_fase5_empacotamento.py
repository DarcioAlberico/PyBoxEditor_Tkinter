from pathlib import Path


def test_recursos_versionados_existem_no_layout_de_instalacao():
    raiz = Path(__file__).resolve().parents[1]
    assert (raiz / "assets/fonts/NotoSansSymbols2-Regular.ttf").is_file()
    assert (raiz / "assets/lexico/en.txt.gz").is_file()
    assert (raiz / "core/dados/diagrama_modelo.pth").is_file()


def test_lexico_nao_depende_do_diretorio_atual():
    from core import lexico

    assert Path(lexico.CAMINHO_PADRAO).is_absolute()
    assert Path(lexico.CAMINHO_PADRAO).is_file()

