"""
Testes da F2.6 — o livro lido só do nosso OCR, e exportado.

Esta fase é a primeira que **ignora a camada de texto do PDF**. As outras
trabalham sobre ela; aqui a página é lida como imagem e o que sai é EPUB ou
DOCX. O que os testes fixam são as decisões que a medição forçou, cada uma
descoberta por um estrago concreto no Yusupov:

  - o retângulo do tabuleiro cresce antes de excluir, senão os rótulos `a`–`h`
    viram linhas de um caractere;
  - o respingo é cortado por **área**, e não por altura, senão o livro sai sem
    pontuação;
  - a página que é imagem sai inteira como figura, senão custa 160 s e devolve
    ruído.

Rodar sem pytest:      python tests/test_f26_livro.py
"""

import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import numpy as np
from PIL import Image

from core import exportar, livro
from core.box_model import BoxEntry
from core.services.box_service import BoxService


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _classificador(char="a", confianca=0.99):
    """
    Responde sempre o mesmo. O modelo de verdade não entra na suíte.

    Serve porque o que estes testes medem é a **montagem** — onde quebra a
    linha, onde entra o espaço, o que é excluído —, e não o reconhecimento.
    """
    return lambda recorte: (char, confianca)


def _pagina(texto_linhas=("Uma linha de prosa comum.",), diagrama=False,
            largura=300, altura=400):
    """Uma página PDF com texto e, se pedido, um quadrado do tamanho de um tabuleiro."""
    doc = fitz.open()
    p = doc.new_page(width=largura, height=altura)
    for i, linha in enumerate(texto_linhas):
        p.insert_text((30, 40 + i * 16), linha, fontsize=10)
    if diagrama:
        # Quase quadrado e grande, que é o que o `localizar` procura. Hachurado
        # por dentro para gerar contorno como um tabuleiro de verdade.
        p.draw_rect(fitz.Rect(40, 150, 200, 310), width=2)
        for j in range(8):
            for k in range(8):
                if (j + k) % 2:
                    p.draw_rect(fitz.Rect(40 + j * 20, 150 + k * 20,
                                          60 + j * 20, 170 + k * 20),
                                fill=(0.75, 0.75, 0.75))
    return doc


def _cinza(page, dpi=150):
    return livro._pagina_cinza(page, dpi)


# ----------------------------------------------------------------------
# O ponto de entrada do BoxService
# ----------------------------------------------------------------------

def test_o_estagio_de_antes_do_descarte_ainda_tem_o_tabuleiro():
    """
    É a razão de o ponto de entrada existir: o descarte da F1.8 joga fora o
    contorno grande do tabuleiro, e é justamente ele que o `diagrama.localizar`
    procura.
    """
    doc = _pagina(diagrama=True)
    try:
        img = Image.fromarray(_cinza(doc[0]))
        antes, _th, escala, _cinza_arr = BoxService.boxes_antes_do_descarte(img)
        depois = BoxService.generate_boxes_opencv(img)
    finally:
        doc.close()

    def maior(boxes):
        return max((b.x2 - b.x1) * (b.y2 - b.y1) for b in boxes) if boxes else 0

    assert antes, "o estágio anterior ao descarte veio vazio"
    assert maior(antes) > maior(depois) * 4, (
        "o bloco grande do tabuleiro deveria estar antes do descarte e não depois")
    assert escala > 0


def test_o_ponto_de_entrada_e_o_mesmo_caminho_do_generate():
    """
    Se as duas rotas divergirem, o diagrama passa a ser procurado num estágio
    que não é o que o resto do pipeline produz — que foi o defeito que este
    ponto de entrada veio consertar.
    """
    doc = _pagina(texto_linhas=("Prosa numa linha.", "E outra linha aqui."))
    try:
        img = Image.fromarray(_cinza(doc[0]))
        antes, _th, escala, _c = BoxService.boxes_antes_do_descarte(img)
        completo = BoxService.generate_boxes_opencv(img)
    finally:
        doc.close()

    # tudo que sobreviveu ao descarte tem de estar no estágio anterior
    caixas_antes = {(b.x1, b.y1, b.x2, b.y2) for b in antes}
    faltando = [b for b in completo
                if (b.x1, b.y1, b.x2, b.y2) not in caixas_antes]
    assert len(faltando) <= len(completo) * 0.2, (
        "o estágio anterior não contém o que o caminho completo devolve")


def test_pagina_com_contorno_demais_devolve_vazio():
    """
    Era: 160 segundos numa página só.

    O `merge_vertical_boxes` é quadrático. Medido no Yusupov a 300 dpi, a
    página 11 dá 2.131 contornos e 0,4 s; a página 8, que é quase toda imagem,
    dá 78.558 e **160 s**.
    """
    ruido = np.random.default_rng(7).integers(0, 255, (300, 300), dtype=np.uint8)
    img = Image.fromarray(ruido)

    vazio, _th, _e, _c = BoxService.boxes_antes_do_descarte(img, max_contornos=50)
    assert vazio == []

    cheio, _th, _e, _c = BoxService.boxes_antes_do_descarte(img, max_contornos=None)
    assert cheio, "sem limite, a página deveria devolver as caixas"


# ----------------------------------------------------------------------
# Extração
# ----------------------------------------------------------------------

def test_o_texto_da_pagina_vira_paragrafo():
    doc = _pagina(texto_linhas=("Primeira linha da prosa.",
                                "Segunda linha da mesma prosa."))
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150)
    finally:
        doc.close()

    paragrafos = [b for b in p.blocos if isinstance(b, livro.Paragrafo)]
    assert paragrafos, "nenhum parágrafo saiu da página"
    assert p.caracteres > 0
    assert not p.pagina_de_imagem


def test_o_vao_entre_caracteres_vira_espaco():
    """Sem isto o livro sai com as palavras coladas: 'Thiscounter-attack'."""
    doc = _pagina(texto_linhas=("aaa bbb ccc ddd",))
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150)
    finally:
        doc.close()

    junto = " ".join(b.texto for b in p.blocos if isinstance(b, livro.Paragrafo))
    assert " " in junto, f"não separou palavra nenhuma: {junto!r}"
    assert junto.count("x") >= 12, junto


def test_a_pagina_de_imagem_sai_inteira_como_figura():
    """
    O limiar é baixado no teste em vez de se forjar uma página com 78 mil
    contornos: o que importa fixar é **o que a extração faz** quando a página
    passa do limite, e não quanto ruído é preciso para chegar lá — isso já está
    em `test_pagina_com_contorno_demais_devolve_vazio`.
    """
    doc = _pagina(texto_linhas=("Isto seria texto numa página normal.",))
    original = BoxService.MAX_CONTORNOS_DE_TEXTO
    BoxService.MAX_CONTORNOS_DE_TEXTO = 3
    try:
        extraida = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150)
    finally:
        BoxService.MAX_CONTORNOS_DE_TEXTO = original
        doc.close()

    assert extraida.pagina_de_imagem
    assert len(extraida.blocos) == 1
    assert isinstance(extraida.blocos[0], livro.Figura)
    assert extraida.caracteres == 0
    assert extraida.blocos[0].largura > 100, "a figura não é a página inteira"


def test_o_diagrama_sai_como_figura_e_o_miolo_dele_nao_vira_texto():
    doc = _pagina(texto_linhas=("Texto antes do diagrama.",), diagrama=True)
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150)
    finally:
        doc.close()

    figuras = [b for b in p.blocos if isinstance(b, livro.Figura)]
    assert figuras, "o tabuleiro não virou figura"
    assert p.diagramas >= 1
    assert figuras[0].largura > 50 and figuras[0].altura > 50


def test_a_margem_do_diagrama_alcanca_os_rotulos_das_casas():
    """
    Era: oito linhas contendo só "8", "7", "6"... na página 10 do Yusupov.

    O `diagrama.localizar` devolve a borda do **tabuleiro**, e as letras `a`–`h`
    embaixo e os números `8`–`1` ao lado moram fora dela. Sem margem eles não
    são excluídos e entram no texto como linhas de um caractere.
    """
    escala = 30
    tabuleiro = (100, 100, 400, 400)
    forma = (600, 600)
    com_margem = livro._com_margem(tabuleiro, escala * livro.MARGEM_DIAGRAMA, forma)

    # um "8" rente à borda esquerda do tabuleiro, como o livro imprime
    rotulo = BoxEntry("", 100 - int(escala * 0.9), 200,
                      100 - int(escala * 0.2), 200 + escala)

    assert not livro._dentro(rotulo, tabuleiro), "o teste não está fora da borda"
    assert livro._dentro(rotulo, com_margem), (
        "a margem não alcança o rótulo da casa — ver MARGEM_DIAGRAMA")

    # ...e a margem não é tão larga que engula o texto da coluna ao lado
    prosa = BoxEntry("", 480, 200, 520, 230)
    assert not livro._dentro(prosa, com_margem), "a margem engoliu o texto vizinho"


def test_o_recorte_por_area_preserva_a_pontuacao():
    """
    Era: cortando por **altura**, o livro saía sem pontuação nenhuma —
    `5.♔xf2` virava `5♔d2` e `G.Levenfish` virava `G Levenfish`. Um ponto final
    é baixo, mas não é respingo.
    """
    # Os tamanhos são os medidos na página 10 do Yusupov, cuja escala é 44.
    escala = 44
    minima = livro.MIN_AREA_GLIFO * escala * escala

    def area(b):
        return (b.x2 - b.x1) * (b.y2 - b.y1)

    ponto = BoxEntry("", 0, 0, 8, 8)         # 0,033 · escala²
    hifen = BoxEntry("", 0, 0, 14, 3)        # 0,022 · escala²
    respingo = BoxEntry("", 0, 0, 2, 2)      # 0,0021 · escala², a faixa da régua

    assert area(ponto) >= minima, "o limiar de área derruba o ponto final"
    assert area(hifen) >= minima, "o limiar de área derruba o hífen"
    assert area(respingo) < minima, "o limiar deixa passar o respingo da régua"


def test_onde_ha_respingo_demais_o_texto_e_ornamento():
    """
    A régua de meio-tom do cabeçalho passa pelo limiar de área em fragmentos, e
    nem confiança a tira. O que a denuncia é a companhia.
    """
    escala = 20
    juntos = [BoxEntry("", 100 + i, 100, 102 + i, 102)
              for i in range(livro.RESPINGOS_DE_ORNAMENTO)]
    celulas = livro._celulas_de_ornamento(juntos, escala)
    assert celulas, "não marcou a célula cheia de respingo"
    assert livro._celula(BoxEntry("", 100, 100, 110, 110), escala) in celulas
    assert livro._celula(BoxEntry("", 900, 900, 910, 910), escala) not in celulas

    poucos = juntos[:livro.RESPINGOS_DE_ORNAMENTO - 1]
    assert not livro._celulas_de_ornamento(poucos, escala), (
        "marcou ornamento com respingo de menos")


def test_extrair_reclama_de_arquivo_inexistente():
    try:
        livro.extrair("nao_existe_xyz.pdf", _classificador())
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("deveria reclamar de arquivo inexistente")


# ----------------------------------------------------------------------
# Exportação
# ----------------------------------------------------------------------

def _paginas_de_teste():
    return [
        livro.PaginaExtraida(
            numero=0,
            blocos=[livro.Paragrafo("Primeiro parágrafo com ♖xf3 e ♕d5."),
                    livro.Figura(_png_pequeno(), 40, 40),
                    livro.Paragrafo("Depois da figura.")],
            caracteres=50, diagramas=1),
        livro.PaginaExtraida(numero=1,
                             blocos=[livro.Paragrafo("Só texto na segunda.")],
                             caracteres=20),
    ]


def _png_pequeno():
    import io as _io
    buffer = _io.BytesIO()
    Image.fromarray(np.full((40, 40), 200, dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_o_epub_tem_a_forma_que_o_formato_exige():
    """
    O `mimetype` vai primeiro e **sem compressão** — é a única exigência
    posicional do EPUB, e um zip que comprima essa entrada é recusado por
    leitor que valide.
    """
    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_epub(_paginas_de_teste(),
                                     os.path.join(tmp, "livro.epub"),
                                     titulo="Teste", autor="Autor")
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
            assert nomes[0] == "mimetype"
            assert z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
            assert z.read("mimetype") == b"application/epub+zip"
            assert "META-INF/container.xml" in nomes
            assert "OEBPS/content.opf" in nomes
            assert "OEBPS/nav.xhtml" in nomes
            assert sum(1 for n in nomes if n.endswith(".xhtml")) == 3  # 2 + nav
            assert sum(1 for n in nomes if n.endswith(".png")) == 1

            opf = z.read("OEBPS/content.opf").decode("utf-8")
            assert "<dc:title>Teste</dc:title>" in opf
            assert "<dc:creator>Autor</dc:creator>" in opf
            pagina = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
            assert "♖xf3" in pagina
            assert "<img" in pagina


def test_o_epub_escapa_o_que_e_marcacao():
    paginas = [livro.PaginaExtraida(
        numero=0, blocos=[livro.Paragrafo("1<2 & 3>2 <script>x</script>")])]
    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_epub(paginas, os.path.join(tmp, "x.epub"))
        with zipfile.ZipFile(caminho) as z:
            xhtml = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
    assert "<script>" not in xhtml
    assert "&lt;script&gt;" in xhtml


def test_o_docx_abre_de_volta_com_texto_e_imagem():
    from docx import Document

    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_docx(_paginas_de_teste(),
                                     os.path.join(tmp, "livro.docx"),
                                     titulo="Teste")
        doc = Document(caminho)

    texto = "\n".join(p.text for p in doc.paragraphs)
    assert "♖xf3" in texto
    assert "Só texto na segunda." in texto
    assert len(doc.inline_shapes) == 1, "a figura não entrou no DOCX"
    assert doc.core_properties.title == "Teste"


def test_o_formato_sai_da_extensao():
    with tempfile.TemporaryDirectory() as tmp:
        epub = exportar.exportar(_paginas_de_teste(), os.path.join(tmp, "a.epub"))
        docx = exportar.exportar(_paginas_de_teste(), os.path.join(tmp, "a.docx"))
        assert zipfile.is_zipfile(epub) and zipfile.is_zipfile(docx)


def test_formato_invalido():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            exportar.exportar(_paginas_de_teste(), os.path.join(tmp, "a.txt"))
        except ValueError as e:
            assert "formato" in str(e)
        else:
            raise AssertionError("aceitou um formato inválido")


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = []
    for nome, fn in testes:
        try:
            fn()
            print(f"  PASS  {nome}")
        except Exception as e:
            falhas.append(nome)
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")
    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
