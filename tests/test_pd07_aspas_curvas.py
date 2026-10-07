"""
PD-07 (`docs/ROADMAP_PENDENCIAS.md`) — a aspa curva na exportação.

A F111 contou 0 aspas curvas contra 17 retas num livro exportado. A troca é de
um caractere por um, só na saída (EPUB, DOCX, sumário), e o texto da página —
léxico, PGN, régua do corpus — fica como o OCR o leu.
"""

import sys
import zipfile

import pytest

from core import exportar
from core.exportar import aspas_curvas
from core.livro import PaginaExtraida, Paragrafo, Tabela

ABRE2, FECHA2, ABRE1, FECHA1 = "“", "”", "‘", "’"


@pytest.mark.parametrize("reta, curva", [
    ('He said "go" now.', f"He said {ABRE2}go{FECHA2} now."),
    ('"Start', f"{ABRE2}Start"),
    ('("x")', f"({ABRE2}x{FECHA2})"),
    ('end."', f"end.{FECHA2}"),
    ("don't", f"don{FECHA1}t"),
    ("the rook's file", f"the rook{FECHA1}s file"),
    ("the 'untouchable' pawns", f"the {ABRE1}untouchable{FECHA1} pawns"),
    ("in the '90s", f"in the {FECHA1}90s"),
    ('o "Rei" e a d\'água', f"o {ABRE2}Rei{FECHA2} e a d{FECHA1}água"),
    ("sem aspa nenhuma", "sem aspa nenhuma"),
    (f"já {ABRE2}curva{FECHA2}", f"já {ABRE2}curva{FECHA2}"),
])
def test_a_regra_do_compositor(reta, curva):
    assert aspas_curvas(reta) == curva
    assert len(aspas_curvas(reta)) == len(reta), "um caractere por um"


def _epub(tmp_path, blocos):
    destino = str(tmp_path / "a.epub")
    exportar.para_epub([PaginaExtraida(numero=0, blocos=blocos)], destino,
                       titulo="Teste")
    with zipfile.ZipFile(destino) as z:
        alvo = [n for n in z.namelist() if n.startswith("OEBPS/pagina")][0]
        return z.read(alvo).decode("utf-8"), z.read("OEBPS/nav.xhtml").decode("utf-8")


def test_o_epub_sai_com_aspa_curva_e_o_negrito_no_lugar(tmp_path):
    p = Paragrafo('The "key squares" are those.', negrito=[(4, 17)])
    xhtml, _nav = _epub(tmp_path, [p])
    assert f"The <strong>{ABRE2}key squares{FECHA2}</strong> are those." in xhtml
    assert p.texto == 'The "key squares" are those.', "a página fica como foi lida"


def test_a_celula_e_o_sumario_tambem(tmp_path):
    blocos = [Paragrafo("The 'Lucena' position", titulo=True, nivel=1),
              Tabela([['W: "Win"', "x"]])]
    xhtml, nav = _epub(tmp_path, blocos)
    assert f"W: {ABRE2}Win{FECHA2}" in xhtml
    assert f"The {ABRE1}Lucena{FECHA1} position" in nav


def test_o_docx_sai_com_aspa_curva(tmp_path):
    pytest.importorskip("docx")
    destino = str(tmp_path / "a.docx")
    exportar.para_docx([PaginaExtraida(numero=0, blocos=[
        Paragrafo('He said "go", and it\'s done.', italico=[(8, 12)])])],
        destino, titulo="Teste")
    from docx import Document
    runs = [r for p in Document(destino).paragraphs for r in p.runs]
    texto = "".join(r.text for r in runs)
    assert f"He said {ABRE2}go{FECHA2}, and it{FECHA1}s done." in texto
    assert [r.text for r in runs if r.italic] == [f"{ABRE2}go{FECHA2}"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
