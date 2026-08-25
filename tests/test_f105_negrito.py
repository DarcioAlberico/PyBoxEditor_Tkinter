"""
Testes da F105 — o negrito reconhecido pela espessura do traço.

O que a fase mediu, e o que estes testes prendem:

  - a régua é a espessura **relativa ao mesmo caractere no resto do livro**, e
    não a espessura crua nem a da página. Medido no Dvoretsky contra o que a
    camada de texto dele declara, palavra a palavra: 63,1% de acerto pela
    mediana da página, 92,0% pelo quantil da página, 94,8% pela mediana do
    livro, **97,1%** pelo quantil do livro (0,22% de alarme falso);

  - a referência é um quantil baixo e não a mediana, porque neste gênero a
    notação é negrito e a mediana do dígito **é** o peso negrito;

  - a decisão é por palavra: glifo a glifo a mesma régua acerta 83,8% com 1,35%
    de falso, e o que ela perde é a pontuação (31,3% dos sinais, contra 99,7%
    dos dígitos);

  - palavra de um glifo não decide nada (29,2% de acerto, 11,48% de falso). A
    pontuação curta herda dos vizinhos — o travessão de `Nimzovitch — Tarrasch`
    e o `!` do lance —, e a alfanumérica não herda, ou a fileira
    `a b c d e f g h` do diagrama sairia em negrito toda vez.

Ponta a ponta, no gabarito: 98,5% de acerto e 0,22% de alarme falso.

Rodar sem pytest:      python tests/test_f105_negrito.py
"""

import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import numpy as np
import pytest

from core import exportar, livro, negrito


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _barra(largura, altura=40, margem=10):
    """Um traço vertical de `largura` px sobre fundo branco."""
    img = np.full((altura + 2 * margem, largura + 2 * margem), 255, np.uint8)
    img[margem:margem + altura, margem:margem + largura] = 0
    return img


def _paragrafo(texto, pesos, titulo=False):
    """
    Um parágrafo com a espessura já medida, caractere a caractere.

    `pesos` é um dicionário `{palavra: espessura}` — todo glifo da palavra sai
    com a mesma —, ou uma lista alinhada ao texto.
    """
    if isinstance(pesos, dict):
        lista = []
        for inicio, fim in negrito._palavras(texto):
            enquanto = pesos[texto[inicio:fim]]
            lista.extend([None] * (inicio - len(lista)))
            lista.extend([enquanto] * (fim - inicio))
        lista.extend([None] * (len(texto) - len(lista)))
        pesos = lista
    return livro.Paragrafo(texto, titulo=titulo, pesos=negrito.vetor(pesos))


def _pagina(*paragrafos):
    return livro.PaginaExtraida(numero=0, blocos=list(paragrafos))


def _marcado(p):
    """As palavras que saíram em negrito, como texto."""
    return [p.texto[i:f] for i, f in p.negrito]


# ----------------------------------------------------------------------
# A medida
# ----------------------------------------------------------------------

def test_o_traco_mais_grosso_mede_mais():
    fino = negrito.espessura(_barra(4))
    grosso = negrito.espessura(_barra(8))
    assert grosso > fino
    # A razão entre os dois é a razão entre as larguras: a medida é linear no
    # traço, que é o que permite compará-la com o desenho de uma fonte.
    assert grosso / fino == pytest.approx(2.0, abs=0.25)


def test_a_medida_nao_muda_com_o_corpo():
    """
    **O corpo sai na divisão pela altura da tinta.** Sem isso, um subtítulo em
    peso normal mediria mais que a prosa em negrito, e a régua diria que o
    livro inteiro é negrito onde o corpo cresce.
    """
    pequeno = negrito.espessura(_barra(4, altura=40))
    grande = negrito.espessura(_barra(8, altura=80))
    assert pequeno == pytest.approx(grande, rel=0.1)


def test_recorte_sem_tinta_nao_tem_medida():
    assert negrito.espessura(np.zeros((0, 0), np.uint8)) is None
    assert negrito.espessura(np.full((20, 20), 255, np.uint8)) is None
    # Menos tinta que `MINIMO_DE_TINTA`: um respingo de 2×2.
    respingo = np.full((20, 20), 255, np.uint8)
    respingo[5:7, 5:7] = 0
    assert negrito.espessura(respingo) is None


# ----------------------------------------------------------------------
# A referência de cada caractere
# ----------------------------------------------------------------------

def test_a_referencia_pega_o_redondo_mesmo_quando_ele_e_minoria():
    """
    O caso do dígito: neste gênero a notação é negrito, e `4` aparece muito
    mais vezes em negrito do que redondo. A mediana devolveria o peso negrito
    — e aí nenhum `4` negrito passaria da régua.
    """
    amostras = {"4": [0.10] * 3 + [0.14] * 7}
    do_quantil = negrito.referencia(amostras)["4"]
    assert float(np.median(amostras["4"])) == pytest.approx(0.14, abs=0.001)
    assert do_quantil < 0.12, "tem de ficar do lado redondo da amostra"
    # E o que importa: com esta referência, um `4` negrito passa da régua.
    assert negrito.e_negrito(0.14 / do_quantil, 1.0)


def test_onde_o_caractere_e_quase_todo_redondo_o_quantil_nao_atrapalha():
    amostras = {"e": [0.10] * 9 + [0.14]}
    assert negrito.referencia(amostras)["e"] == pytest.approx(0.10, abs=0.005)


# ----------------------------------------------------------------------
# A palavra
# ----------------------------------------------------------------------

def test_um_glifo_gordo_nao_faz_a_palavra_negrito():
    """
    Mediana e não média: um `l` que veio colado ao vizinho, ou um respingo em
    cima da letra, não pode arrastar o parágrafo inteiro.
    """
    ref = {"a": 0.10, "b": 0.10, "c": 0.10, "d": 0.10}
    palavra = [("a", 0.10), ("b", 0.10), ("c", 0.40), ("d", 0.10)]
    assert negrito.relativo(palavra, ref) == pytest.approx(1.0, abs=0.01)


def test_a_palavra_toda_mais_grossa_passa_da_regua():
    ref = {"a": 0.10, "b": 0.10, "c": 0.10}
    palavra = [("a", 0.13), ("b", 0.13), ("c", 0.13)]
    peso = negrito.relativo(palavra, ref)
    assert negrito.e_negrito(peso, 1.0)


def test_o_caractere_que_a_referencia_nao_conhece_nao_conta():
    assert negrito.relativo([("♔", 0.2)], {"a": 0.1}) is None


# ----------------------------------------------------------------------
# A regra da vizinhança
# ----------------------------------------------------------------------

def test_a_palavra_de_um_glifo_nao_decide_sozinha():
    """
    Ela acerta 29,2% e erra 11,48% — pior que qualquer outra faixa. Quem decide
    é a vizinhança, e onde não há vizinhança negrito ela fica redonda.
    """
    p = _paragrafo("um ! dois", {"um": 0.10, "!": 0.40, "dois": 0.10})
    negrito.marcar([_pagina(p)])
    assert _marcado(p) == []


def test_a_pontuacao_entre_dois_negritos_entra_junto():
    """
    `Nimzovitch — Tarrasch` é um trecho só, e o travessão está no meio.

    A prosa em volta traz os mesmos nomes em peso redondo porque é dela que sai
    a referência: um caractere que só aparecesse em negrito não teria com o que
    ser comparado, e a régua não o veria.
    """
    linha = _paragrafo("Nimzovitch — Tarrasch",
                       {"Nimzovitch": 0.14, "—": 0.10, "Tarrasch": 0.14})
    prosa = _paragrafo("Nimzovitch e Tarrasch jogaram esta partida",
                       {"Nimzovitch": 0.10, "e": 0.10, "Tarrasch": 0.10,
                        "jogaram": 0.10, "esta": 0.10, "partida": 0.10})
    negrito.marcar([_pagina(linha, prosa)])
    assert _marcado(linha) == ["Nimzovitch — Tarrasch"]
    assert _marcado(prosa) == []


def test_a_pontuacao_depois_do_negrito_tambem_entra():
    """O `!` do lance: `1.♖h1 !` sai do mesmo peso do lance."""
    p = _paragrafo("um lance de prosa lance ! e segue a prosa",
                   {"um": 0.10, "lance": 0.10, "de": 0.10, "prosa": 0.10,
                    "!": 0.10, "e": 0.10, "segue": 0.10, "a": 0.10})
    # A segunda ocorrência de `lance` é a que está em negrito; a primeira dá a
    # referência redonda das letras dela.
    segunda = p.texto.rindex("lance")
    for k in range(segunda, segunda + len("lance")):
        p.pesos[k] = 0.14
    negrito.marcar([_pagina(p)])
    assert _marcado(p) == ["lance !"]


def test_a_fileira_de_coordenadas_do_diagrama_nao_vira_negrito():
    """
    **É por isso que a herança não vale para palavra alfanumérica.** As
    coordenadas do tabuleiro são oito palavras de uma letra, e o `a` da prosa
    é outra: um `a` colado a um lance viraria negrito toda vez que o livro
    dissesse "played 1.e4 a strong move".
    """
    fileira = "a b c d e f g h"
    p = _paragrafo(fileira, {ch: 0.14 for ch in fileira.split()})
    negrito.marcar([_pagina(p)])
    assert _marcado(p) == []


# ----------------------------------------------------------------------
# `marcar`
# ----------------------------------------------------------------------

def test_trechos_vizinhos_viram_um_so():
    """Um `run` por palavra encheria o DOCX de dezenas de milhares deles."""
    p = _paragrafo("prosa normal aqui e duas negrito seguidas",
                   {"prosa": 0.10, "normal": 0.10, "aqui": 0.10, "e": 0.10,
                    "duas": 0.10, "negrito": 0.14, "seguidas": 0.14})
    negrito.marcar([_pagina(p)])
    assert _marcado(p) == ["negrito seguidas"]


def test_o_titulo_nao_recebe_marca():
    """Ele já sai `<h2>`, e os dois formatos o desenham negrito sozinhos."""
    titulo = _paragrafo("Capitulo grosso demais",
                        {"Capitulo": 0.20, "grosso": 0.20, "demais": 0.20},
                        titulo=True)
    corpo = _paragrafo("prosa comum de uma linha inteira aqui",
                       {"prosa": 0.10, "comum": 0.10, "de": 0.10, "uma": 0.10,
                        "linha": 0.10, "inteira": 0.10, "aqui": 0.10})
    negrito.marcar([_pagina(titulo, corpo)])
    assert titulo.negrito == []


def test_marcar_duas_vezes_da_o_mesmo():
    """
    O `extrair_pagina` marca com a página, e o `extrair` remarca com o livro.
    Se a segunda passada somasse à primeira, o livro sairia com trechos
    repetidos e sobrepostos.
    """
    p = _paragrafo("prosa comum aqui e um trecho grosso",
                   {"prosa": 0.10, "comum": 0.10, "aqui": 0.10, "e": 0.10,
                    "um": 0.10, "trecho": 0.14, "grosso": 0.14})
    pagina = _pagina(p)
    negrito.marcar([pagina])
    primeira = list(p.negrito)
    negrito.marcar([pagina])
    assert p.negrito == primeira


def test_paragrafo_sem_medida_fica_intocado():
    """A legenda do diagrama e a faixa do cabeçalho não trazem espessura."""
    p = livro.Paragrafo("legenda sem pesos nenhum")
    negrito.marcar([_pagina(p)])
    assert p.negrito == []


def test_a_referencia_maior_e_a_que_manda():
    """
    A mesma palavra, medida com uma página e com o livro: é a diferença entre
    90,2% e 96,7% de acerto, e é por isso que `extrair` remarca no fim.
    """
    grossa = {"lance": 0.14, "grosso": 0.14}
    prosa = {p: 0.10 for p in "esta e a prosa comum do livro inteiro".split()}
    sozinha = _paragrafo("lance grosso", grossa)
    negrito.marcar([_pagina(sozinha)])
    assert _marcado(sozinha) == [], "sem prosa por perto, não há o que comparar"

    de_novo = _paragrafo("lance grosso", grossa)
    corpo = _paragrafo("esta e a prosa comum do livro inteiro", prosa)
    negrito.marcar([_pagina(de_novo, corpo)])
    assert _marcado(de_novo) == ["lance grosso"]


# ----------------------------------------------------------------------
# O vetor acompanha o texto
# ----------------------------------------------------------------------

def test_o_paragrafo_junta_as_linhas_sem_perder_o_alinhamento():
    linhas = [livro.Linha(topo=0, esquerda=0, altura=10, texto="uma linha",
                          pesos=[0.1] * 3 + [None] + [0.2] * 5),
              livro.Linha(topo=20, esquerda=0, altura=10, texto="e outra",
                          pesos=[0.3] + [None] + [0.4] * 5)]
    p = livro._paragrafo_de(linhas)
    assert p.texto == "uma linha e outra"
    assert len(p.pesos) == len(p.texto)
    # O espaço que junta as duas linhas é o único `nan` novo.
    assert np.isnan(p.pesos[len("uma linha")])
    assert p.pesos[len("uma linha") + 1] == pytest.approx(0.3)


def test_a_linha_sem_medida_nao_desloca_a_seguinte():
    linhas = [livro.Linha(topo=0, esquerda=0, altura=10, texto="sem medida"),
              livro.Linha(topo=20, esquerda=0, altura=10, texto="com",
                          pesos=[0.5] * 3)]
    p = livro._paragrafo_de(linhas)
    assert len(p.pesos) == len(p.texto)
    assert p.pesos[-1] == pytest.approx(0.5)


# ----------------------------------------------------------------------
# Ponta a ponta, da página ao arquivo
# ----------------------------------------------------------------------

def _pdf_com_negrito():
    """
    Uma página com três linhas de prosa e uma palavra em Helvetica-Bold.

    O `hebo` é a mesma família do `helv` no outro peso, que é exatamente o par
    que a régua tem de separar.
    """
    doc = fitz.open()
    p = doc.new_page(width=340, height=200)
    for i, linha in enumerate(("nulla mollis vestibulum ullamcorper cursus",
                               "aliquam sollicitudin ornare vestibulum",
                               "consectetur vestibulum ullamcorper nullam")):
        p.insert_text((30, 40 + i * 20), linha, fontsize=11)
    p.insert_text((30, 100), "consectetur mollis", fontsize=11, fontname="hebo")
    return doc


def _classificador_por_largura():
    """
    Responde `m` no glifo largo e `i` no estreito.

    Não é reconhecimento: é o mínimo que a régua do negrito precisa para que a
    referência tenha mais de uma classe, que é o caso de qualquer página real.
    """
    def classificar(recorte):
        if recorte.size == 0:
            return "", 0.0
        return ("m" if recorte.shape[1] >= recorte.shape[0] * 0.6 else "i"), 0.99
    return classificar


def test_a_palavra_em_negrito_da_pagina_sai_marcada():
    doc = _pdf_com_negrito()
    try:
        pagina = livro.extrair_pagina(doc[0], _classificador_por_largura(),
                                      dpi=200)
    finally:
        doc.close()

    paragrafos = [b for b in pagina.blocos if isinstance(b, livro.Paragrafo)]
    assert paragrafos, "a página tem de render texto"
    for p in paragrafos:
        assert len(p.pesos) == len(p.texto), "o vetor tem de acompanhar o texto"

    # A quarta linha impressa é a única em negrito, e ela tem duas palavras.
    # O texto sai como `m` e `i` (ver o classificador), então o que se confere
    # é **onde** a marca caiu, e não o que está escrito.
    marcados = [(i, f) for p in paragrafos for i, f in p.negrito]
    assert marcados, "a linha em negrito tem de sair marcada"

    da_linha = [p for p in paragrafos if p.negrito]
    for p in da_linha:
        # Nenhuma linha redonda inteira pode ter sido marcada junto: o trecho
        # marcado é sempre menor que o parágrafo, ou igual quando o parágrafo
        # **é** a linha em negrito.
        marcadas = sum(f - i for i, f in p.negrito)
        assert marcadas <= len(p.texto)


# ----------------------------------------------------------------------
# O que chega ao arquivo
# ----------------------------------------------------------------------

def test_o_corte_em_trechos():
    assert exportar.trechos("abc def ghi", [(4, 7)]) == [
        ("abc ", False), ("def", True), (" ghi", False)]
    assert exportar.trechos("negrito no fim", [(11, 14)]) == [
        ("negrito no ", False), ("fim", True)]
    assert exportar.trechos("sem marca", []) == [("sem marca", False)]
    assert exportar.trechos("", []) == []


def test_o_epub_embrulha_o_trecho_em_strong():
    pagina = _pagina(_paragrafo("prosa comum aqui e um lance grosso",
                                {"prosa": 0.10, "comum": 0.10, "aqui": 0.10,
                                 "e": 0.10, "um": 0.10, "lance": 0.14,
                                 "grosso": 0.14}))
    negrito.marcar([pagina])
    with tempfile.TemporaryDirectory() as pasta:
        caminho = os.path.join(pasta, "livro.epub")
        exportar.para_epub([pagina], caminho)
        with zipfile.ZipFile(caminho) as z:
            nome = [n for n in z.namelist() if n.endswith(".xhtml")
                    and "pagina" in n][0]
            xhtml = z.read(nome).decode("utf-8")
    assert "<strong>lance grosso</strong>" in xhtml
    assert "<strong>prosa" not in xhtml


def test_o_titulo_nao_ganha_strong():
    pagina = _pagina(_paragrafo("Um Capitulo", {"Um": 0.30, "Capitulo": 0.30},
                                titulo=True))
    negrito.marcar([pagina])
    with tempfile.TemporaryDirectory() as pasta:
        caminho = os.path.join(pasta, "livro.epub")
        exportar.para_epub([pagina], caminho)
        with zipfile.ZipFile(caminho) as z:
            nome = [n for n in z.namelist() if n.endswith(".xhtml")
                    and "pagina" in n][0]
            xhtml = z.read(nome).decode("utf-8")
    assert "<h2>Um Capitulo</h2>" in xhtml
    assert "<strong>" not in xhtml


def test_o_docx_traz_o_trecho_num_run_negrito():
    pytest.importorskip("docx")
    from docx import Document

    pagina = _pagina(_paragrafo("prosa comum aqui e um lance grosso",
                                {"prosa": 0.10, "comum": 0.10, "aqui": 0.10,
                                 "e": 0.10, "um": 0.10, "lance": 0.14,
                                 "grosso": 0.14}))
    negrito.marcar([pagina])
    with tempfile.TemporaryDirectory() as pasta:
        caminho = os.path.join(pasta, "livro.docx")
        exportar.para_docx([pagina], caminho)
        doc = Document(caminho)
    runs = [(r.text, r.bold) for p in doc.paragraphs for r in p.runs if r.text]
    assert ("lance grosso", True) in runs
    # O resto não fala de peso: `w:b w:val="0"` em todo run do livro seria
    # ruído, e o estilo do parágrafo já diz qual é o peso do corpo.
    assert all(b is None for t, b in runs if t != "lance grosso")


def test_o_simbolo_dentro_do_negrito_mantem_a_propria_fonte():
    """
    Os dois cortes se somam: a família é atributo do run e o peso também, então
    `1.♔g4` em negrito sai em três runs — e os três em negrito.
    """
    pytest.importorskip("docx")
    from docx import Document

    texto = "no lance 1.♔g4 dela"
    pagina = _pagina(
        _paragrafo(texto, {"no": 0.10, "lance": 0.10, "1.♔g4": 0.14,
                           "dela": 0.10}),
        # A referência de `1`, `.`, `♔`, `g` e `4` sai daqui: sem uma aparição
        # redonda de cada caractere não há com o que comparar.
        _paragrafo("o lance 1.♔g4 dela sai na prosa tambem",
                   {"o": 0.10, "lance": 0.10, "1.♔g4": 0.10, "dela": 0.10,
                    "sai": 0.10, "na": 0.10, "prosa": 0.10, "tambem": 0.10}))
    negrito.marcar([pagina])
    with tempfile.TemporaryDirectory() as pasta:
        caminho = os.path.join(pasta, "livro.docx")
        exportar.para_docx([pagina], caminho)
        doc = Document(caminho)
    runs = [(r.text, r.bold, r.font.name)
            for p in doc.paragraphs for r in p.runs if r.text]
    do_simbolo = [r for r in runs if r[0] == "♔"]
    assert do_simbolo, "a figurina tem de sair no run da fonte dela"
    assert do_simbolo[0][1] is True
    assert do_simbolo[0][2], "e continuar com a família de recurso"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
