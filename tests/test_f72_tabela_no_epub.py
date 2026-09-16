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
# A célula pelo motor (OCR-11 e OCR-12 em produção)
# ----------------------------------------------------------------------

def test_a_celula_e_lida_pelo_leitor_quando_ha_um():
    """
    A célula passa pelo mesmo caminho da linha de prosa: o `leitor` de
    `_tabela_da_pagina` é o `ler_celula` de `extrair_pagina`, que roteia e
    funde. Sem ele a célula é só da cadeia, como era.
    """
    img = _pagina_com_tabela(filas=2, colunas=2)
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))
    rotulos = []

    def leitor(sub, rotulo):
        rotulos.append(rotulo)
        assert sub, "a célula vazia não chama o leitor"
        return f"W: Win {rotulo}", 1

    achado = livro._tabela_da_pagina(img, boxes, lambda r: ("x", 1.0), 0.0,
                                     None, 0, leitor=leitor)
    assert achado is not None
    tabela, _usados, _topo, fracos = achado
    assert rotulos == ["t0c0l0", "t0c1l0", "t1c0l0", "t1c1l0"]
    assert tabela.linhas == [["W: Win t0c0l0", "W: Win t0c1l0"],
                             ["W: Win t1c0l0", "W: Win t1c1l0"]]
    assert fracos == 4, "os derrubados da célula são os que o leitor contou"


def test_o_box_em_cima_da_regua_e_a_regua():
    """
    Geometria da tabela do Nunn (p. 237): réguas verticais em 159–164,
    313–317, 707–708, 1096–1097 e 1489–1494, glifo típico de 29 px, e os
    pedaços da divisória em 4–8 × 107–178 px, um por fila.
    """
    verticais = [(159, 164), (313, 317), (707, 708), (1096, 1097), (1489, 1494)]
    horizontais = [(420, 424), (607, 609), (793, 795)]
    pedacos = [(156, 427, 164, 604), (704, 427, 708, 583), (1098, 1204, 1100, 1277),
               (160, 1285, 167, 1416), (1490, 1170, 1496, 1277)]
    for x1, y1, x2, y2 in pedacos:
        assert livro._em_cima_da_regua(BoxEntry("", x1, y1, x2, y2),
                                       horizontais, verticais, 29), (x1, y1, x2, y2)
    # O `l` encostado à divisória tem uma altura só; a palavra larga perto da
    # régua horizontal tem altura de glifo; o pedaço de régua longe de qualquer
    # régua não é régua desta tabela.
    for x1, y1, x2, y2 in [(700, 488, 705, 517), (367, 600, 500, 629),
                           (500, 427, 505, 604)]:
        assert not livro._em_cima_da_regua(BoxEntry("", x1, y1, x2, y2),
                                           horizontais, verticais, 29), (x1, y1, x2, y2)
    # A régua horizontal partida: larga, fina e em cima dela.
    assert livro._em_cima_da_regua(BoxEntry("", 200, 606, 300, 610),
                                   horizontais, verticais, 29)


def test_a_regua_e_consumida_pela_tabela_e_nao_lida():
    """
    O pedaço da divisória entra como box de moldura (é como chega do Nunn: a
    montagem sintética não o produz, e ele é posto à mão em cima da régua do
    meio, x 448–452): a tabela o consome, e ele não é classificado nem
    sobra para a página.
    """
    img = _pagina_com_tabela(filas=2, colunas=2)
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))
    pedaco = BoxEntry("", 447, 310, 453, 570, moldura=True)
    boxes = list(boxes) + [pedaco]
    lidos = []

    def classificar(recorte):
        lidos.append(recorte.shape)
        return "x", 1.0

    achado = livro._tabela_da_pagina(img, boxes, classificar, 0.0, None, 0)
    assert achado is not None
    tabela, usados, _topo, _f = achado
    assert any(b is pedaco for b in usados), "o pedaço de régua tinha de ser consumido"
    assert not any(recorte[0] >= 200 for recorte in lidos), \
        "o pedaço de régua foi classificado como glifo"
    assert tabela.linhas == [["xxx", "xxx"], ["xxx", "xxx"]]


def test_a_celula_passa_pela_fusao_por_palavra(monkeypatch):
    """
    A cadeia lê `W:W1n` na célula e o motor tem `W:` e `Win` a 0,95 no mesmo
    lugar: a célula sai `W: Win`, com registro de roteamento rotulado por
    fila, coluna e linha — e antes das linhas da página, que não veem os
    registros que a tabela consumiu.
    """
    img = _pagina_com_tabela(filas=2, colunas=2)
    monkeypatch.setattr(livro, "_pagina_cinza", lambda page, dpi: img)
    classificar = lambda recorte: ("x", 1.0)  # noqa: E731
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))
    de_moldura = [b for b in boxes if b.moldura]
    regiao = (min(b.x1 for b in de_moldura), min(b.y1 for b in de_moldura),
              max(b.x2 for b in de_moldura), max(b.y2 for b in de_moldura))
    horizontais, verticais = livro._grade(img, regiao)
    celulas = [(xa, ya, xz, yz) for ya, yz in livro._celulas(horizontais)
               for xa, xz in livro._celulas(verticais)]

    def na_tabela(linha):
        cx = (min(b.x1 for b in linha) + max(b.x2 for b in linha)) / 2
        cy = (min(b.y1 for b in linha) + max(b.y2 for b in linha)) / 2
        return regiao[0] <= cx <= regiao[2] and regiao[1] <= cy <= regiao[3]

    def texto_da_linha(img_, linha, classificar_, conf_minima, coletor=None,
                       pagina=0, marcador_glifo=None):
        texto = "W:W1n" if na_tabela(linha) else "ABCDEFGH"
        n = len(linha)
        caixas = [min(n - 1, i * n // len(texto)) for i in range(len(texto))]
        return texto, 0, [None] * len(texto), [None] * len(texto), caixas
    monkeypatch.setattr(livro, "_texto_da_linha", texto_da_linha)

    def ler_pagina(img_):
        registros = []
        for xa, ya, xz, yz in celulas:
            dentro = [b for b in boxes if xa <= (b.x1 + b.x2) / 2 <= xz
                      and ya <= (b.y1 + b.y2) / 2 <= yz
                      and (b.y2 - b.y1) < 2 * 20]
            if not dentro:
                continue
            x1, y1 = min(b.x1 for b in dentro), min(b.y1 for b in dentro)
            x2, y2 = max(b.x2 for b in dentro), max(b.y2 for b in dentro)
            corte = x1 + (x2 - x1) * 2 // 5
            registros.append(("W: Win", 0.95, (x1, y1, x2, y2),
                              (("W:", 0.95, (x1, y1, corte, y2)),
                               ("Win", 0.95, (corte, y1, x2, y2)))))
        return registros

    pagina = livro.extrair_pagina(None, classificar, dpi=150, ler_pagina=ler_pagina,
                                  fusao="palavra")

    tabelas = [b for b in pagina.blocos if isinstance(b, Tabela)]
    assert len(tabelas) == 1
    assert tabelas[0].linhas == [["W: Win", "W: Win"], ["W: Win", "W: Win"]]
    celulas_lidas = [r for r in pagina.roteamento if r.get("celula")]
    assert [r["celula"] for r in celulas_lidas] == ["t0c0l0", "t0c1l0", "t1c0l0", "t1c1l0"]
    assert {r["fonte"] for r in celulas_lidas} == {"fusao"}
    assert celulas_lidas[0]["ancora"] == "W:W1n"
    linhas_da_pagina = [r for r in pagina.roteamento if not r.get("celula")]
    assert linhas_da_pagina and {r["texto"] for r in linhas_da_pagina} == {"ABCDEFGH"}
    assert all(r["linha"] == i for i, r in enumerate(linhas_da_pagina))


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
