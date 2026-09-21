"""
Testes da capa (ED-08; SPEC_EDITOR §9 "Add Cover", §10.1): `livro_ops.definir_capa` cria o
invólucro SVG, `properties="svg"`, `cover-image`, `<meta name="cover">` e o marco `cover`
(AC-ED08-4); a ida e volta pelo EPUB; `epubcheck` limpo (`slow`); e "Livro → Capa…" na
janela, a partir de uma imagem do livro ou do disco.

Rodar sem pytest:      python tests/test_editor_capa.py
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import epub, livro_ops, validacao
from editor_ambiente import Janela


def test_ac4_definir_capa_poe_o_involucro_svg_o_cover_image_o_meta_e_o_marco(tmp_path):
    livro = editor_livros.livro_completo()
    arquivo = livro_ops.definir_capa(livro, "Images/foto.png")
    assert arquivo == "Text/capa.xhtml" and livro.capitulos[0].arquivo == arquivo
    cap = livro.capitulos[0]
    assert cap.semantica == "cover" and cap.linear is False and 'epub:type="cover"' in cap.texto_cru
    assert 'viewBox="0 0 40 30"' in cap.texto_cru and 'xlink:href="../Images/foto.png"' in cap.texto_cru
    assert livro.metadados.capa == "Images/foto.png" and ("cover", arquivo) in livro.marcos
    # definir de novo troca a imagem no mesmo arquivo, sem duplicar
    livro_ops.definir_capa(livro, "Images/desenho.svg")
    assert [c.arquivo for c in livro.capitulos].count(arquivo) == 1 and "desenho.svg" in livro.capitulos[0].texto_cru
    assert livro.marcos.count(("cover", arquivo)) == 1
    with pytest.raises(ValueError):
        livro_ops.definir_capa(livro, "Images/nada.png")
    # no EPUB: properties="svg" na capa, cover-image na imagem, meta cover, o itemref linear="no"
    caminho = str(tmp_path / "capa.epub")
    epub.escrever(livro, caminho)
    with zipfile.ZipFile(caminho) as z:
        opf = z.read(livro.opf).decode("utf-8")
    assert 'href="Text/capa.xhtml" media-type="application/xhtml+xml" properties="svg"' in opf
    assert 'href="Images/desenho.svg" media-type="image/svg+xml" properties="cover-image"' in opf
    assert '<meta name="cover" content="desenho.svg"/>' in opf and 'idref="capa.xhtml" linear="no"' in opf
    relido, _rel = epub.ler(caminho)
    assert relido.metadados.capa == "Images/desenho.svg" and relido.capitulos[0].semantica == "cover"
    assert ("cover", "Text/capa.xhtml") in relido.marcos and relido.capitulos[0].linear is False


def test_dimensoes_da_imagem_por_cabecalho():
    png = editor_livros._png_40x30()
    assert livro_ops.dimensoes_da_imagem(png) == (40, 30)
    gif = b"GIF89a" + (12).to_bytes(2, "little") + (7).to_bytes(2, "little") + b"\x00" * 10
    assert livro_ops.dimensoes_da_imagem(gif) == (12, 7)
    jpeg = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xc0\x00\x11\x08" + (30).to_bytes(2, "big") + (40).to_bytes(2, "big") + b"\x03\x01\x22\x00")
    assert livro_ops.dimensoes_da_imagem(jpeg) == (40, 30)
    assert livro_ops.dimensoes_da_imagem(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 500"/>') == (300,
                                                                                                                  500)
    assert livro_ops.dimensoes_da_imagem(b"lixo") is None


@pytest.mark.slow
def test_ac4_a_capa_passa_no_epubcheck(tmp_path):
    if validacao.comando_do_epubcheck() is None:
        pytest.skip("sem Java/epubcheck")
    livro = editor_livros.livro_completo()
    livro_ops.definir_capa(livro, "Images/foto.png")
    caminho = str(tmp_path / "capa.epub")
    epub.escrever(livro, caminho)
    r = validacao.validar(caminho, livro.opf)
    assert r.valido, [str(m) for m in r.erros]


def test_na_janela_a_capa_vem_de_uma_imagem_do_livro_ou_do_disco(tmp_path):
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        # pela lista de imagens (o índice 0 é a primeira imagem)
        t.caixas.escolha_resposta = 0
        arquivo = j.executar("capa")
        assert arquivo == "Text/capa.xhtml" and livro.metadados.capa == "Images/foto.png" and j.projeto.sujo
        assert j.navegador.exists(arquivo) and "(capa)" in j.navegador.item("Images/foto.png", "text")
        assert "[cover]" in j.navegador.item(arquivo, "text")
        # do disco: a imagem entra no livro e vira a capa
        caminho = tmp_path / "nova.png"
        caminho.write_bytes(editor_livros._png_40x30())
        assert j.executar("capa", str(caminho)) == arquivo
        assert livro.metadados.capa == "Images/nova.png" and "Images/nova.png" in livro.recursos
        # a capa abre em código, só com o invólucro
        aba = j.abrir_capitulo(arquivo)
        assert aba.modo == "codigo" and "<svg" in aba.widget.texto_todo()
        # salvar e reler
        j.executar("salvar")
        relido, _rel = epub.ler(t.epub)
        assert relido.metadados.capa == "Images/nova.png" and relido.capitulos[0].arquivo == arquivo


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
