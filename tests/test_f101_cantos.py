"""
Testes da F101 — a quina redonda da moldura, na fonte e na caneta.

A Chess Merida traz os quatro cantos numa segunda versão, de quina redonda:
`a s d f` acompanham a moldura simples e `A S D F` a dupla. Medido no contorno,
o `a` tem exatamente a caixa do `1` e o `A` a do `!` — é o mesmo canto, com a
curva no lugar do ângulo.

**Mas a fonte sozinha não bastaria, e é isso que esta suíte guarda.** O caminho
em que os glifos de moldura entram é o do diagrama com coordenada numa fonte que
os tenha; o caminho mais usado de todos — PNG sem coordenada, que é o padrão da
exportação — desenha o filete com a caneta. Uma caixinha que só funcionasse na
primeira combinação seria pior que caixinha nenhuma, então o raio foi copiado do
desenho da Merida para a caneta, e as duas fontes passam a arredondar.

Onde ele **não** chega está preso aqui também: o Word não sabe arredondar borda
de célula, e a caixa do modo de fonte é uma célula.

Rodar sem pytest:      python tests/test_f100_cantos.py
"""

import io as _io
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PIL import Image

from core import exportar, livro
from core import render_diagrama as rd

MERIDA = "ChessMerida-Diagram"
SKAK = "SkakNew-Diagram"
FEN = "3qkb2/5p2/2n5/1B2P3/3P1r2/2N5/5P2/2RQK3"


def _tinta_na_quina(png: bytes, lado: int = 6) -> int:
    """Pixels escuros no quadradinho do canto superior esquerdo do desenho."""
    imagem = Image.open(_io.BytesIO(png)).convert("L")
    quina = imagem.crop((0, 0, lado, lado))
    return sum(1 for p in quina.tobytes() if p < 128)


# ----------------------------------------------------------------------
# O eixo
# ----------------------------------------------------------------------

def test_a_quina_e_um_eixo_a_parte_da_moldura():
    """
    Três feitios e um sim-ou-não, e não cinco feitios: "sem moldura
    arredondada" não quer dizer nada.
    """
    assert rd.MOLDURAS == ("sem", "simples", "dupla")
    assert rd.CANTOS == ("reto", "arredondado")
    assert rd.CANTO_PADRAO == "reto"


def test_quina_escrita_errado_reclama():
    for valor in ("redondo", "Arredondado", True, None):
        with pytest.raises(ValueError):
            rd.normalizar_cantos(valor)


def test_a_quina_errada_reclama_nos_dois_formatos():
    """
    O DOCX não usa o valor — o Word não arredonda borda de célula —, mas
    **confere**: sem isso um `"redondo"` passaria calado num formato e doeria no
    outro, e o usuário veria dois arquivos diferentes do mesmo livro.
    """
    figura = livro.Figura(b"", 10, 10, origem="recorte")
    paginas = [livro.PaginaExtraida(numero=0, blocos=[figura])]
    with tempfile.TemporaryDirectory() as tmp:
        for escrever, ext in ((exportar.para_epub, "epub"),
                              (exportar.para_docx, "docx")):
            with pytest.raises(ValueError) as erro:
                escrever(paginas, os.path.join(tmp, f"x.{ext}"),
                         cantos="redondo")
            assert "redondo" in str(erro.value)


# ----------------------------------------------------------------------
# Na caneta — o caminho mais usado
# ----------------------------------------------------------------------

@pytest.mark.parametrize("fonte", [SKAK, MERIDA])
@pytest.mark.parametrize("moldura", ["simples", "dupla"])
def test_a_caneta_arredonda_nas_duas_fontes(fonte, moldura):
    """
    Sem coordenada não há glifo de borda em jogo: quem desenha é a caneta, e
    ela arredonda para qualquer fonte. É o caminho padrão da exportação.
    """
    reto = rd.desenhar(FEN, fonte=fonte, lado_px=352, moldura=moldura,
                       cantos="reto", tons=0)[0]
    curvo = rd.desenhar(FEN, fonte=fonte, lado_px=352, moldura=moldura,
                        cantos="arredondado", tons=0)[0]
    assert _tinta_na_quina(reto) > _tinta_na_quina(curvo), (
        "a quina redonda tinha de tirar tinta do canto")


def test_a_quina_nao_muda_o_tamanho_do_desenho():
    """
    Curvar a quina não pode mexer na medida: o filete continua ocupando a mesma
    margem, e um diagrama arredondado ao lado de um reto tem de casar.
    """
    for moldura in ("simples", "dupla"):
        medidas = {rd.desenhar(FEN, lado_px=352, moldura=moldura, cantos=c)[1:]
                   for c in rd.CANTOS}
        assert len(medidas) == 1, f"{moldura} mudou de tamanho: {medidas}"


def test_sem_moldura_a_quina_nao_tem_o_que_fazer():
    reto = rd.desenhar(FEN, lado_px=352, moldura="sem", cantos="reto")
    curvo = rd.desenhar(FEN, lado_px=352, moldura="sem", cantos="arredondado")
    assert reto == curvo


# ----------------------------------------------------------------------
# Na fonte — o diagrama com coordenada
# ----------------------------------------------------------------------

def test_a_grade_troca_os_quatro_cantos_e_mais_nada():
    fonte = rd.carregar(MERIDA)
    reta = rd.grade(FEN, fonte, "branca", "dupla", "reto")
    curva = rd.grade(FEN, fonte, "branca", "dupla", "arredondado")

    assert (reta[0][0], reta[0][-1]) == ("!", "#")
    assert (curva[0][0], curva[0][-1]) == ("A", "S")
    assert (reta[-1][0], reta[-1][-1]) == ("/", ")")
    assert (curva[-1][0], curva[-1][-1]) == ("D", "F")
    # O topo, a base, as laterais e o tabuleiro inteiro ficam onde estavam.
    assert reta[0][1:-1] == curva[0][1:-1]
    assert [l[1:-1] for l in reta[1:-1]] == [l[1:-1] for l in curva[1:-1]]
    assert [l[0] for l in reta[1:-1]] == [l[0] for l in curva[1:-1]]


def test_a_simples_usa_a_quina_fina_e_a_dupla_a_grossa():
    """Minúscula acompanha a moldura simples, maiúscula a dupla."""
    fonte = rd.carregar(MERIDA)
    simples = rd.grade(FEN, fonte, "branca", "simples", "arredondado")
    dupla = rd.grade(FEN, fonte, "branca", "dupla", "arredondado")
    assert simples[0][0] == "a" and simples[-1][-1] == "f"
    assert dupla[0][0] == "A" and dupla[-1][-1] == "F"


def test_a_fonte_sem_quina_redonda_nao_perde_as_coordenadas():
    """
    **Cair para a quina viva é melhor que cair para a caneta.** Uma fonte com
    borda em glifo e sem a versão redonda perderia as coordenadas em glifo se a
    `grade` devolvesse `None` — muito mais do que se pediu ao marcar a caixinha.
    """
    fonte = rd.carregar(MERIDA)
    sem_redondo = rd.Fonte(
        nome=fonte.nome, arquivo=fonte.arquivo, em=fonte.em, casas=fonte.casas,
        molduras={"dupla": {c: v for c, v in fonte.molduras["dupla"].items()
                            if c != "cantos_arredondados"}})
    grade = rd.grade(FEN, sem_redondo, "branca", "dupla", "arredondado")
    assert grade is not None and len(grade) == 10
    assert grade[0][0] == "!", "sem a versão redonda, fica a de quina viva"


def test_o_glifo_de_quina_redonda_entra_na_conferencia_de_cobertura():
    """Mesma disciplina do resto do mapa: promessa não conferida é casa vazia."""
    faltando = rd.sem_glifo(rd.carregar(MERIDA).arquivo, "asdfASDF")
    assert not faltando, f"a Merida não desenha {''.join(faltando)!r}"


def test_o_png_com_coordenada_muda_de_quina_e_nao_de_tamanho():
    reto = rd.desenhar(FEN, fonte=MERIDA, lado_px=352, moldura="dupla",
                       coordenadas=True, cantos="reto", tons=0)
    curvo = rd.desenhar(FEN, fonte=MERIDA, lado_px=352, moldura="dupla",
                        coordenadas=True, cantos="arredondado", tons=0)
    assert reto[0] != curvo[0], "o desenho não mudou"
    assert reto[1:] == curvo[1:], "a quina mexeu na medida"


# ----------------------------------------------------------------------
# No arquivo escrito
# ----------------------------------------------------------------------

def _figura(nome=MERIDA, coordenadas=False, moldura="dupla", cantos="reto"):
    png, largura, altura = rd.desenhar(FEN, fonte=nome, lado_px=352,
                                       moldura=moldura, cantos=cantos,
                                       coordenadas=coordenadas)
    fonte = rd.carregar(nome)
    em_grade = (rd.grade(FEN, fonte, "branca", moldura, cantos)
                if coordenadas else None)
    return livro.Figura(png, largura, altura, fen=FEN, origem="render",
                        linhas=(em_grade or rd.linhas(FEN, fonte)),
                        linhas_emolduradas=em_grade is not None, fonte=nome,
                        coordenadas=coordenadas,
                        casas_de_largura=largura * 8.0 / 352)


def test_a_css_do_epub_arredonda_a_caixa():
    tmp = tempfile.mkdtemp()
    paginas = [livro.PaginaExtraida(numero=0, blocos=[_figura()])]
    caminho = exportar.para_epub(paginas, os.path.join(tmp, "a.epub"),
                                 diagramas="fonte", moldura="dupla",
                                 cantos="arredondado")
    with zipfile.ZipFile(caminho) as z:
        css = z.read("OEBPS/estilo.css").decode("utf-8")
    assert "border-radius" in css

    outro = exportar.para_epub(paginas, os.path.join(tmp, "b.epub"),
                               diagramas="fonte", moldura="dupla")
    with zipfile.ZipFile(outro) as z:
        assert "border-radius" not in z.read("OEBPS/estilo.css").decode("utf-8")


def test_no_docx_a_quina_redonda_chega_pelo_texto_emoldurado():
    """
    O Word não arredonda borda de célula, então a caixa sai de quina viva. Onde
    a quina redonda aparece é no diagrama emoldurado em glifo — e ali quem a
    desenha é a fonte, dentro do próprio texto.
    """
    from docx import Document

    tmp = tempfile.mkdtemp()
    figura = _figura(coordenadas=True, cantos="arredondado")
    caminho = exportar.para_docx(
        [livro.PaginaExtraida(numero=0, blocos=[figura])],
        os.path.join(tmp, "a.docx"), diagramas="fonte", moldura="dupla",
        cantos="arredondado")
    doc = Document(caminho)
    assert not doc.inline_shapes
    filas = [p.text for p in doc.tables[0].cell(0, 0).paragraphs]
    assert filas[0].startswith("A") and filas[0].endswith("S")
    assert filas[-1].startswith("D") and filas[-1].endswith("F")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
