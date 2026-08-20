"""
Testes da F72 — a tabela sai como tabela, e não como texto corrido.

A F71 tirou a tabela de dentro da moldura que a engolia, e ela passou a sair na
ordem certa — mas como prosa: as células uma atrás da outra, sem nada que
dissesse onde uma acabava e a outra começava. No livro de finais do Nunn a
tabela **é** o conteúdo: `W: Win (1 ♖e1!)` na casa de `B♖h2` × `W♔d1` é a
informação, e um parágrafo por linha com as colunas separadas por espaço não a
preserva.

O caminho tem três pedaços, e cada um tem o seu teste aqui:

  - a **marca**: o `trama.aplicar` diz quais boxes vieram de dentro de uma
    moldura, e ela precisa sobreviver ao merge — foi ali que se perdeu primeiro;
  - a **grade**: as réguas da moldura, buscadas na imagem, porque a moldura não
    sobrevive à troca do bloco pelo conteúdo;
  - a **saída**: `<table>` no EPUB, com os símbolos ainda na fonte que os
    desenha.

Rodar sem pytest:      python tests/test_f72_tabela_no_epub.py
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from PIL import Image

from core import exportar, livro, trama
from core.box_model import BoxEntry
from core.livro import PaginaExtraida, Paragrafo, Tabela
from core.services.box_service import BoxService


# ----------------------------------------------------------------------
# A marca
# ----------------------------------------------------------------------

def test_a_marca_sobrevive_ao_merge():
    """
    **É onde ela se perdia.** O `merge_vertical_boxes` constrói uma caixa nova,
    e o que não for copiado ali some calado: medido na página 236 do Nunn, os
    277 boxes lidos de dentro da tabela chegavam marcados e saíam sem marca.
    """
    corpo = BoxEntry("i", 10, 40, 20, 60, moldura=True)
    pingo = BoxEntry("", 12, 30, 18, 36, moldura=True)
    saida = BoxService.merge_vertical_boxes([pingo, corpo])
    assert all(b.moldura for b in saida), "o merge apagou a marca"


def test_basta_um_dos_dois_ter_a_marca():
    """O pingo e o corpo do 'i' são o mesmo caractere."""
    corpo = BoxEntry("i", 10, 40, 20, 60, moldura=True)
    pingo = BoxEntry("", 12, 30, 18, 36)
    assert BoxService.merge_vertical_boxes([pingo, corpo])[0].moldura


def test_quem_nao_veio_de_moldura_continua_sem_marca():
    normal = BoxEntry("a", 0, 0, 20, 20)
    assert not BoxService.merge_vertical_boxes([normal])[0].moldura


# ----------------------------------------------------------------------
# A grade
# ----------------------------------------------------------------------

def _pagina_com_tabela(filas=3, colunas=4, x0=60, y0=300, larg=780, alt=560):
    """
    Uma tabela com moldura fechada e divisórias, como a do Nunn.

    O texto vai **dentro** das células, que é o que a grade tem de separar.
    """
    img = np.full((900, 900), 245, np.uint8)
    for k in range(4):
        cv2.putText(img, "ABCDEFGH", (40, 60 + k * 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, 15, 2)

    cv2.rectangle(img, (x0, y0), (x0 + larg, y0 + alt), 15, 3)
    for i in range(1, colunas):
        x = x0 + i * larg // colunas
        cv2.line(img, (x, y0), (x, y0 + alt), 15, 3)
    for j in range(1, filas):
        y = y0 + j * alt // filas
        cv2.line(img, (x0, y), (x0 + larg, y), 15, 3)

    for j in range(filas):
        for i in range(colunas):
            x = x0 + i * larg // colunas + 18
            y = y0 + j * alt // filas + 55
            cv2.putText(img, "Win", (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 15, 2)
    return img


def test_a_grade_sai_da_moldura():
    img = _pagina_com_tabela(filas=3, colunas=4)
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))
    marcados = [b for b in boxes if b.moldura]
    assert marcados, "a F71 não abriu a moldura"

    regiao = (min(b.x1 for b in marcados), min(b.y1 for b in marcados),
              max(b.x2 for b in marcados), max(b.y2 for b in marcados))
    horizontais, verticais = livro._grade(img, regiao)
    assert len(livro._celulas(horizontais)) == 3
    assert len(livro._celulas(verticais)) == 4


def test_sem_grade_nao_ha_tabela():
    """
    **Moldura não é tabela.** O painel de pontuação da F11 vem marcado igual e
    não tem divisória nenhuma; sem grade, o conteúdo segue como parágrafo.
    """
    img = np.full((900, 900), 245, np.uint8)
    cv2.rectangle(img, (60, 300), (840, 700), 15, 3)
    for k in range(3):
        cv2.putText(img, "Maximum number of points", (90, 380 + k * 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, 15, 2)
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))
    assert livro._tabela_da_pagina(img, boxes, lambda r: ("x", 1.0), 0.0,
                                   None, 0) is None


def test_a_tabela_vira_matriz_de_celulas():
    img = _pagina_com_tabela(filas=3, colunas=4)
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))
    achado = livro._tabela_da_pagina(img, boxes, lambda r: ("x", 1.0), 0.0,
                                     None, 0)
    assert achado is not None, "a grade estava lá e a tabela não saiu"

    tabela, usados, topo, _fracos = achado
    assert len(tabela.linhas) == 3
    assert all(len(fila) == 4 for fila in tabela.linhas), "matriz não retangular"
    assert usados, "nenhum box foi consumido pela tabela"

    # **A maioria, e não todas.** O que enche a célula é a recuperação da F71, e
    # ela perde: o filtro de altura de `trama.glifos` deixa de fora a pontuação
    # miúda, e o que encosta na divisória vai junto com ela. Medido na página
    # 236 do Nunn, 3 células vazias em 24 — e duas delas são vazias no papel,
    # onde está impresso `*`. O que esta fase garante é a **grade**.
    cheias = sum(1 for fila in tabela.linhas for c in fila if c)
    assert cheias >= 10, f"só {cheias} de 12 células têm texto"


def test_a_celula_se_le_linha_a_linha():
    """
    **A ordem de leitura da página não serve dentro da célula.** Ela procura
    colunas, e numa célula de duas linhas curtas acha: o vão vertical entre as
    palavras passa por calha e a célula sai lida coluna a coluna. Medido na
    página 236 do Nunn com o modelo de verdade, a primeira célula saía
    `w win ( 1 B Draw ( l ♖e 1` — as duas linhas dela intercaladas.
    """
    img = np.full((900, 900), 245, np.uint8)
    for k in range(4):
        cv2.putText(img, "ABCDEFGH", (40, 60 + k * 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, 15, 2)
    cv2.rectangle(img, (60, 300), (840, 700), 15, 3)
    cv2.line(img, (450, 300), (450, 700), 15, 3)
    cv2.line(img, (60, 500), (840, 500), 15, 3)
    # Cada célula com duas linhas, e o que as distingue é a **altura**: alta em
    # cima, baixa embaixo. O vão entre os dois grupos de cada linha é o que a
    # régua de coluna confundiria com calha.
    for x in (95, 485):
        for y, corpo in ((370, 1.3), (455, 0.5)):
            cv2.putText(img, "HH   HH", (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                        corpo, 15, 2)
        for y, corpo in ((570, 1.3), (655, 0.5)):
            cv2.putText(img, "HH   HH", (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                        corpo, 15, 2)

    def por_altura(recorte):
        """A linha de cima é alta e a de baixo é baixa — não precisa modelo."""
        if recorte.size == 0:
            return "", 0.0
        return ("A" if recorte.shape[0] > 22 else "b"), 1.0

    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))
    achado = livro._tabela_da_pagina(img, boxes, por_altura, 0.0, None, 0)
    assert achado is not None

    conferidas = 0
    for fila in achado[0].linhas:
        for celula in fila:
            texto = celula.replace(" ", "")
            if "A" not in texto or "b" not in texto:
                continue
            conferidas += 1
            assert texto.index("b") > texto.rindex("A"), \
                f"a célula não saiu linha a linha: {celula!r}"
    assert conferidas, "nenhuma célula tinha as duas linhas para conferir"


def test_os_boxes_da_tabela_saem_da_prosa():
    """Consumido pela tabela é o que não pode virar parágrafo também."""
    img = _pagina_com_tabela()
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))
    _t, usados, _topo, _f = livro._tabela_da_pagina(
        img, boxes, lambda r: ("x", 1.0), 0.0, None, 0)
    ids = {id(b) for b in usados}
    assert len(ids) < len(boxes), "a tabela levou a página inteira"


# ----------------------------------------------------------------------
# A saída
# ----------------------------------------------------------------------

def _epub_de(blocos, caminho):
    pagina = PaginaExtraida(numero=0, blocos=blocos)
    exportar.para_epub([pagina], caminho, titulo="Teste")
    with zipfile.ZipFile(caminho) as z:
        alvo = [n for n in z.namelist() if n.startswith("OEBPS/pagina")][0]
        return z.read(alvo).decode("utf-8"), z.read("OEBPS/estilo.css").decode("utf-8")


def test_a_tabela_sai_como_table_no_epub(tmp_path):
    tabela = Tabela([["B♖h2", "W: Win"], ["B♖a2", "W: Draw"]])
    xhtml, css = _epub_de([tabela], str(tmp_path / "t.epub"))

    assert "<table>" in xhtml and "</table>" in xhtml
    assert xhtml.count("<tr>") == 2
    assert xhtml.count("<td>") == 4
    assert "border-collapse" in css, "sem CSS a tabela sai sem fio"


def test_a_celula_nao_vira_paragrafo():
    """O defeito que a fase fecha, visto de fora."""
    tabela = Tabela([["a", "b"], ["c", "d"]])
    pagina = PaginaExtraida(numero=0, blocos=[tabela])
    xhtml = exportar._xhtml_da_pagina(pagina, [])
    assert "<p>" not in xhtml and 'class="primeira"' not in xhtml


def test_a_figurina_da_celula_ganha_a_fonte(tmp_path):
    """
    **O texto da página passou a incluir as células** (F72). Sem isso o alfabeto
    que escolhe a fonte dos símbolos não via o que estava dentro da tabela, e a
    figurina saía nua na célula e vestida no parágrafo da mesma página.
    """
    blocos = [Paragrafo("texto qualquer"),
              Tabela([["B♖h2", "W: Win (1 ♖e1!)"]])]
    xhtml, _css = _epub_de(blocos, str(tmp_path / "t.epub"))
    assert '<span class="sim">♖</span>' in xhtml, \
        "a figurina da célula saiu sem a fonte que a desenha"


def test_o_texto_da_pagina_inclui_as_celulas():
    pagina = PaginaExtraida(numero=0, blocos=[
        Paragrafo("prosa"), Tabela([["um", "dois"], ["tres", "quatro"]])])
    assert "quatro" in pagina.texto and "prosa" in pagina.texto


def test_o_docx_aceita_a_tabela(tmp_path):
    """Só que não quebre: o DOCX não pode estourar num bloco que não conhece."""
    import pytest
    pytest.importorskip("docx")

    pagina = PaginaExtraida(numero=0, blocos=[
        Paragrafo("prosa"), Tabela([["um", "dois"], ["tres", "quatro"]])])
    caminho = str(tmp_path / "t.docx")
    exportar.para_docx([pagina], caminho, titulo="Teste")

    from docx import Document
    doc = Document(caminho)
    assert len(doc.tables) == 1
    assert doc.tables[0].cell(1, 1).text == "quatro"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
