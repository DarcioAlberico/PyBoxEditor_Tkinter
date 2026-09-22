from PIL import Image

from core.linha_review import adicionar_ou_corrigir, corrigir, descartar, ler_manifesto


def test_correcao_atualiza_manifesto_e_historico(tmp_path):
    (tmp_path / "images").mkdir()
    Image.new("L", (20, 20), 255).save(tmp_path / "images" / "a.png")
    (tmp_path / "rec_gt.txt").write_text("images/a.png\ttexto errado\n", encoding="utf-8")
    assert corrigir(tmp_path, "images/a.png", "texto correto")
    assert ler_manifesto(tmp_path)[0].texto == "texto correto"
    assert (tmp_path / "correcoes_linhas.jsonl").exists()


def test_descarte_preserva_imagem_e_remove_do_treino(tmp_path):
    (tmp_path / "images").mkdir()
    imagem = tmp_path / "images" / "a.png"
    Image.new("L", (20, 20), 255).save(imagem)
    (tmp_path / "rec_gt.txt").write_text("images/a.png\tlixo\n", encoding="utf-8")
    assert descartar(tmp_path, "images/a.png", "sujeira")
    assert ler_manifesto(tmp_path) == []
    assert imagem.exists()
    assert (tmp_path / "linhas_descartadas.jsonl").exists()


def test_adicionar_ou_corrigir_nao_duplica_a_mesma_imagem(tmp_path):
    (tmp_path / "images").mkdir()
    Image.new("L", (20, 20), 255).save(tmp_path / "images" / "a.png")
    assert adicionar_ou_corrigir(tmp_path, "images/a.png", "um")
    assert adicionar_ou_corrigir(tmp_path, "images/a.png", "dois")
    assert len(ler_manifesto(tmp_path)) == 1
    assert ler_manifesto(tmp_path)[0].texto == "dois"
