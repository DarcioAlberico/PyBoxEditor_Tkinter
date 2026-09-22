from PIL import Image

from core.linha_trainer import _batch_sampler, _imagem


def test_batch_sampler_agrupa_larguras_proximas(tmp_path):
    registros = []
    for indice, largura in enumerate((20, 22, 100, 105)):
        caminho = tmp_path / f"{indice}.png"
        Image.new("L", (largura, 30), 255).save(caminho)
        registros.append((caminho, "a"))
    batches = list(_batch_sampler(registros, 2, 42))
    assert len(batches) == 2
    assert all(abs(_imagem(registros[b[0]][0]).shape[1]
                   - _imagem(registros[b[-1]][0]).shape[1]) < 30 for b in batches)
