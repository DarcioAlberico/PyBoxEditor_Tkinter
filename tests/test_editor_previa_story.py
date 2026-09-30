"""
Testes de `core/editor/previa_story.py` (ED-14): a cópia marcada com a linha da fonte, os
recursos resolvidos pelo OPF e buscados uma vez, o capítulo longo em várias fatias e o mapa
linha ↔ retângulo nos dois sentidos. Sem Tk.

Rodar sem pytest:      python tests/test_editor_previa_story.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.editor import previa_story as ps


def _xhtml(corpo: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
            '<head>\n<title>t</title>\n<link rel="stylesheet" type="text/css" href="../Styles/e.css"/>\n'
            '</head>\n<body epub:type="bodymatter">\n' + corpo + "</body>\n</html>\n")


def test_marcar_linhas_poe_id_so_onde_falta_e_conta_a_linha_da_tag():
    texto = '<body>\n<h1>T</h1>\n<p id="alvo">a</p>\n<div\n class="x"><p>b</p></div>\n<span>c</span>\n</body>'
    marcado, ids = ps.marcar_linhas(texto)
    assert ids == {"__l2": 2, "alvo": 3, "__l4": 4, "__l5": 5}
    assert '<h1 id="__l2">' in marcado and '<p id="alvo">' in marcado
    assert '<div id="__l4"\n class="x"><p id="__l5">' in marcado
    assert "<span>" in marcado                       # o que não é bloco fica como está
    # dois blocos na mesma linha não repetem o id
    marcado, ids = ps.marcar_linhas("<p>a</p><p>b</p>")
    assert len(ids) == 2 and set(ids.values()) == {1}
    assert marcado.count('id="__l1') == 2


def test_resolver_leva_ao_caminho_do_opf():
    assert ps.resolver("Text", "../Images/a.png") == "Images/a.png"
    assert ps.resolver("", "Images/a.png") == "Images/a.png"
    assert ps.resolver("Text", "http://x/a.png") == "http://x/a.png"
    assert ps.resolver("Text", "#nota") == "#nota"


def _png(largura: int = 40, altura: int = 20) -> bytes:
    import fitz

    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, largura, altura), False)
    pix.clear_with(200)
    return pix.tobytes("png")


def test_imagem_e_fonte_vem_dos_recursos_uma_vez_so():
    pedidos = []
    png = _png()

    def recursos(href):
        pedidos.append(href)
        return png if href == "Images/a.png" else None

    montador = ps.Montador(recursos=recursos)
    texto = _xhtml('<p>antes</p>\n<figure><img src="../Images/a.png" alt="a"/></figure>\n<p>depois</p>\n')
    folhas = [("Styles/e.css", '@font-face { font-family: X; src: url("../Fonts/x.ttf"); }\np { margin: 0; }')]
    d1 = ps.desenhar(texto, "Text/c.xhtml", folhas, montador=montador)
    d2 = ps.desenhar(texto, "Text/c.xhtml", folhas, montador=montador)
    assert sorted(pedidos) == ["Fonts/x.ttf", "Images/a.png"]        # a fonte que falta não é pedida de novo
    assert "Images/a.png" in montador.dados
    # a imagem entrou no desenho: a figura tem altura
    for d in (d1, d2):
        figura = [r for linha, _p, r in d.posicoes if linha == 10]
        assert figura and figura[0][3] - figura[0][1] > 10
    import fitz

    doc = fitz.open("pdf", d1.pdf)
    assert doc[0].get_images()


def test_capitulo_longo_vai_em_fatias_e_o_mapa_ida_e_volta():
    corpo = "".join(f"<p>Parágrafo {k} com texto bastante para ocupar uma linha inteira da prévia.</p>\n"
                    for k in range(120))
    texto = _xhtml(corpo)
    d = ps.desenhar(texto, "Text/c.xhtml", largura_pt=300)
    assert d.paginas > 1
    linhas = [linha for linha, _p, _r in d.posicoes]
    assert linhas[0] == 9 and linhas[-1] == 128
    paginas = {p for _l, p, _r in d.posicoes}
    assert paginas == set(range(d.paginas))
    # ida: a linha leva ao bloco; volta: o meio do retângulo devolve a linha
    for alvo in (9, 70, 128):
        linha, pagina, (x0, y0, x1, y1) = d.posicao_da_linha(alvo)
        assert linha == alvo
        assert d.linha_em(pagina, (x0 + x1) / 2, (y0 + y1) / 2) == alvo
    # entre dois blocos (na margem) vale o último acima
    linha, pagina, (x0, y0, x1, y1) = d.posicao_da_linha(70)
    assert d.linha_em(pagina, 2, y1 + 0.5) == 70


def test_o_bloco_mais_interno_ganha_o_clique():
    texto = _xhtml('<div class="caixa">\n<p>dentro</p>\n</div>\n')
    d = ps.desenhar(texto, "Text/c.xhtml")
    _l, pagina, (x0, y0, x1, y1) = d.posicao_da_linha(10)
    assert d.linha_em(pagina, (x0 + x1) / 2, (y0 + y1) / 2) == 10


def test_marcacao_importada_desenha_sem_ilhas():
    # o livro do immersive-translate: spans e data-* que o modo texto não entende
    corpo = ('<p class="calibre1" data-imt_insert_failed="1">46.<span class="notranslate '
             'immersive-translate-target-translation-theme-none">Rxf5 exf5</span></p>\n')
    d = ps.desenhar(_xhtml(corpo), "Text/c.xhtml")
    import fitz

    texto = fitz.open("pdf", d.pdf)[0].get_text()
    assert "46.Rxf5 exf5" in texto.replace("\n", "")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
