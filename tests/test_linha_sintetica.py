from pathlib import Path

from PIL import Image

from core.linha_sintetica import gerar


def test_gera_manifesto_e_imagens(tmp_path):
    origem = tmp_path / "origem"
    (origem / "images").mkdir(parents=True)
    Image.new("L", (100, 30), 255).save(origem / "images" / "a.png")
    (origem / "rec_gt.txt").write_text("images/a.png\t1. e4 ♞f3\n", encoding="utf-8")
    destino = tmp_path / "sintetico"
    resumo = gerar(origem, destino, por_linha=2, semente=7)
    assert resumo["linhas_geradas"] == 2
    linhas = (destino / "rec_gt.txt").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2
    assert all(Path(destino / linha.split("\t", 1)[0]).exists() for linha in linhas)
