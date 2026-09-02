"""
F109 — os consertos que não dependiam de decisão nenhuma, e ficaram soltos.

Quatro peças, cada uma com o número que a justificou:

    a máscara de alfabeto     17 letras acentuadas em 1.112 ocorrências num
                              livro em inglês, e nenhuma legítima
    o rótulo fora da margem   146 parágrafos que eram só `a b c d e f g h`
    o cabeçalho de página     o maior contribuinte de erro de três dos seis
                              livros da F104, e não é erro de leitura
    o idioma do livro         é o que liga a máscara, e o programa não o
                              perguntava a ninguém

E a régua (§6): `contar` ganhou o terceiro balde em
`test_f104_confusao_no_livro.py`, que é onde ela mora.

Rodar sem pytest:      python tests/test_f109_alfabeto_e_cabecalho.py
"""

import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import numpy as np
import pytest

from core import alfabeto, diagrama, exportar, lexico, livro
from core.box_model import BoxEntry
from core.services.learning_service import LearningService


# ----------------------------------------------------------------------
# §1 — a máscara de alfabeto
# ----------------------------------------------------------------------

def test_o_ingles_nao_escreve_letra_acentuada():
    assert not alfabeto.permitido("É", "en")
    assert not alfabeto.permitido("ê", "en")
    assert not alfabeto.permitido("Š", "en")


def test_o_portugues_escreve_as_suas_e_nao_as_dos_outros():
    assert alfabeto.permitido("ç", "pt")
    assert alfabeto.permitido("Ã", "pt")
    assert not alfabeto.permitido("Š", "pt")
    assert not alfabeto.permitido("ö", "pt")


def test_a_ligadura_e_julgada_letra_a_letra():
    assert not alfabeto.permitido("ça", "en")
    assert alfabeto.permitido("ça", "pt")
    assert alfabeto.permitido("fi", "en")


def test_o_que_nao_e_letra_latina_passa_sempre():
    """
    `Δ` é letra para `isalpha()` e é símbolo de análise para o livro. A
    figurina, o dígito e a pontuação não são de idioma nenhum.
    """
    for c in "Δ♔±□7.—":
        assert alfabeto.permitido(c, "en"), c
        assert alfabeto.permitido(c, "pt"), c


def test_sem_idioma_a_mascara_nao_opina():
    assert alfabeto.permitido("É", None)
    assert alfabeto.permitido("É", "")
    assert alfabeto.permitido("É", "xx"), "idioma que o módulo não conhece"


def test_filtrar_mantem_a_ordem_de_quem_leu():
    cand = [("É", 0.9), ("E", 0.8), ("ê", 0.7), ("e", 0.6)]
    assert alfabeto.filtrar(cand, "en") == [("E", 0.8), ("e", 0.6)]
    assert alfabeto.filtrar(cand, None) == cand


class _PredictorFalso:
    """A rede de mentira: a primeira leitura e as candidatas, na ordem dada."""
    loaded = True

    def __init__(self, candidatas):
        self.candidatas = list(candidatas)
        self.consultas = 0

    def predict(self, _crop):
        return self.candidatas[0]

    def predict_topk(self, _crop, k=3):
        self.consultas += 1
        return self.candidatas[:k]


def _lex(*palavras):
    return lexico.Lexico(palavras=set(palavras))


def _servico(*candidatas):
    svc = LearningService()
    svc._predictor = _PredictorFalso(candidatas)
    return svc


# Um recorte de proporção neutra, que a geometria da F106 não veta.
_RECORTE = np.zeros((20, 14), np.uint8)


def test_a_letra_acentuada_cai_para_a_candidata_que_o_idioma_admite():
    svc = _servico(("É", 0.90), ("E", 0.85), ("F", 0.10))
    assert svc.ler_texto(_RECORTE, idioma="en") == ("E", 0.85)


def test_sem_idioma_a_leitura_sai_como_veio_e_sem_segunda_passada():
    svc = _servico(("É", 0.90), ("E", 0.85))
    assert svc.ler_texto(_RECORTE) == ("É", 0.90)
    assert svc._predictor.consultas == 0, "o caminho de sempre não paga nada"


def test_no_portugues_o_acento_fica():
    svc = _servico(("ç", 0.90), ("c", 0.85))
    assert svc.ler_texto(_RECORTE, idioma="pt") == ("ç", 0.90)
    assert svc._predictor.consultas == 0


def test_sem_candidata_admitida_fica_a_leitura_que_havia():
    """Inventar uma classe que a rede não ofereceu seria o voto da F19."""
    svc = _servico(("É", 0.90), ("Ê", 0.85), ("È", 0.80))
    assert svc.ler_texto(_RECORTE, idioma="en") == ("É", 0.90)


def test_a_mascara_e_a_geometria_valem_juntas():
    """
    A candidata que o idioma admite ainda tem de caber no recorte: o travessão
    não cabe num recorte em pé (F106), e a escolha pula para a seguinte.
    """
    svc = _servico(("É", 0.90), ("—", 0.85), ("E", 0.80))
    assert svc.ler_texto(np.zeros((19, 8), np.uint8), idioma="en") == ("E", 0.80)


def test_o_leitor_prende_o_idioma():
    svc = _servico(("É", 0.90), ("E", 0.85))
    ler = svc.leitor_de_texto("en")
    assert ler(_RECORTE) == ("E", 0.85)
    assert svc.leitor_de_texto(None)(_RECORTE) == ("É", 0.90)


# ----------------------------------------------------------------------
# §3 — o rótulo que a margem não alcançou
# ----------------------------------------------------------------------

_TABULEIRO = (100, 100, 500, 500)
_ESCALA = 20.0


def _caixa(x1, y1, x2, y2):
    return BoxEntry("", x1, y1, x2, y2)


def test_a_letra_abaixo_do_tabuleiro_e_rotulo():
    # Pé a 1,7 alturas da borda: a margem de 1,4 não a contém, e ela escapava.
    letra = _caixa(130, 522, 142, 534)
    achadas = diagrama.caixas_dos_rotulos(
        _TABULEIRO, _ESCALA, diagrama.Rotulos(("abaixo",)), [letra])
    assert achadas == [letra]


def test_o_numero_a_esquerda_e_rotulo_so_se_ha_rotulo_daquele_lado():
    numero = _caixa(80, 130, 92, 142)
    so_abaixo = diagrama.Rotulos(("abaixo",))
    assert diagrama.caixas_dos_rotulos(_TABULEIRO, _ESCALA, so_abaixo,
                                       [numero]) == []
    dos_dois = diagrama.Rotulos(("esquerda", "abaixo"))
    assert diagrama.caixas_dos_rotulos(_TABULEIRO, _ESCALA, dos_dois,
                                       [numero]) == [numero]


def test_a_prosa_da_coluna_vizinha_nao_e_rotulo():
    """
    A prosa só se **sobrepõe** ao tabuleiro; o rótulo está contido nele. Uma
    palavra que começa fora da largura do tabuleiro não é rótulo, por mais
    perto da borda que esteja.
    """
    de_fora = _caixa(90, 522, 104, 534)            # começa antes do x1
    larga = _caixa(130, 522, 190, 534)             # mais larga que uma marca
    longe = _caixa(130, 560, 142, 572)             # além da faixa de 1,4
    achadas = diagrama.caixas_dos_rotulos(
        _TABULEIRO, _ESCALA, diagrama.Rotulos(("abaixo",)),
        [de_fora, larga, longe])
    assert achadas == []


def test_sem_rotulo_nenhuma_caixa_e_tirada():
    letra = _caixa(130, 522, 142, 534)
    assert diagrama.caixas_dos_rotulos(_TABULEIRO, _ESCALA, diagrama.Rotulos(),
                                       [letra]) == []


# ----------------------------------------------------------------------
# §5 — o cabeçalho e o rodapé de página
# ----------------------------------------------------------------------

def _paragrafo(texto, topo, linhas=1, altura_da_linha=20, **kw):
    """Um parágrafo de `linhas` linhas iguais, com `topo` e o pé calculado."""
    if linhas > 1:
        texto = " ".join([texto] * linhas)
    # Uma linha por cópia do texto: o início de cada cópia.
    passo = (len(texto) + 1) // linhas
    inicios = [k * passo for k in range(linhas)]
    return livro.Paragrafo(texto, topo=topo, pe=topo + linhas * altura_da_linha,
                           inicios=inicios, **kw)


def _pagina(numero, *blocos, altura=1000):
    return livro.PaginaExtraida(numero=numero, blocos=list(blocos),
                                altura=altura)


def _livro(cabecalho="Attacking Manual - Volume 1", rodape=True, paginas=3):
    saida = []
    for n in range(paginas):
        blocos = [_paragrafo(cabecalho, 40),
                  _paragrafo("A prosa da página, que muda.", 200, linhas=4),
                  _paragrafo(f"E mais prosa, na página {n}.", 600, linhas=2)]
        if rodape:
            blocos.append(_paragrafo(str(37 + n), 950))
        saida.append(_pagina(n, *blocos))
    return saida


def test_o_cabecalho_repetido_sai_e_a_prosa_fica():
    paginas = _livro()
    retirados = livro.retirar_cabecalhos(paginas)
    assert retirados == {"Attacking Manual - Volume 1": 3, "37": 1, "38": 1,
                         "39": 1}
    for p in paginas:
        assert [b.texto[:7] for b in p.blocos] == ["A prosa", "E mais "]
        assert len(p.cabecalhos) == 2


def test_o_numero_de_pagina_e_um_cabecalho_so():
    """`37`, `38` e `39` são o mesmo rodapé: a assinatura tira o número."""
    assert livro._assinatura("37") == livro._assinatura("212") == ""
    assert (livro._assinatura("Chapter 3 · 37")
            == livro._assinatura("Chapter 3 · 38") == "chapter")


def test_em_duas_paginas_nao_e_cabecalho():
    paginas = _livro(paginas=2)
    assert livro.retirar_cabecalhos(paginas) == {}
    assert all(len(p.blocos) == 4 for p in paginas)


def test_fora_da_margem_a_repeticao_nao_basta():
    """
    A primeira linha de um capítulo que se repete — `Solutions` no alto de
    três páginas — mas começa onde a prosa começa. É prosa.
    """
    paginas = [_pagina(n, _paragrafo("Solutions", 300),
                       _paragrafo("prosa", 400, linhas=3))
               for n in range(3)]
    assert livro.retirar_cabecalhos(paginas) == {}


def test_o_cabecalho_colado_ao_paragrafo_sai_e_o_paragrafo_fica():
    """
    O caso do Aagaard: a régua do salto (F103) junta o cabeçalho ao primeiro
    parágrafo da página. Sai a linha, e não o parágrafo — com os vetores da
    F105 e da F115 no mesmo passo.
    """
    def pagina(n):
        texto = "Chapter 4 95 A prosa que segue, e que muda."
        p = livro.Paragrafo(texto, topo=40, pe=140,
                            inicios=[0, 13, 29],
                            pesos=np.arange(len(texto), dtype=float),
                            lacunas=np.arange(len(texto), dtype=float),
                            negrito=[(0, 7), (13, 20)])
        return _pagina(n, p)

    paginas = [pagina(n) for n in range(3)]
    retirados = livro.retirar_cabecalhos(paginas)
    assert retirados == {"Chapter 4 95": 3}
    p = paginas[0].blocos[0]
    assert p.texto == "A prosa que segue, e que muda."
    assert p.inicios == [0, 16]
    assert list(p.pesos) == list(range(13, 43))
    assert list(p.lacunas) == list(range(13, 43))
    assert p.negrito == [(0, 7)], "a fatia cortada sai; a outra anda"
    assert paginas[0].cabecalhos == ["Chapter 4 95"]


def test_o_rodape_colado_ao_ultimo_paragrafo_sai_pelo_pe():
    """O parágrafo começa no meio da página e **acaba** na margem de baixo:
    é o pé que o põe na margem, e a última linha é que sai."""
    def pagina(n):
        texto = f"A prosa que acaba na margem. Chapter 4 {95 + n}"
        return _pagina(n, livro.Paragrafo(texto, topo=700, pe=980,
                                          inicios=[0, 29]))

    paginas = [pagina(n) for n in range(3)]
    livro.retirar_cabecalhos(paginas)
    assert paginas[1].blocos[0].texto == "A prosa que acaba na margem."
    assert paginas[1].blocos[0].inicios == [0]
    assert paginas[1].cabecalhos == ["Chapter 4 96"]


def test_um_paragrafo_so_de_uma_linha_nao_e_alto_e_baixo_ao_mesmo_tempo():
    paginas = [_pagina(n, _paragrafo("37", 40, altura_da_linha=950))
               for n in range(3)]
    livro.retirar_cabecalhos(paginas)
    assert paginas[0].blocos == [] and paginas[0].cabecalhos == ["37"]


def test_o_lance_como_o_livro_o_imprime_nao_e_cabecalho():
    """
    `parece_lance` lê `Bd3!`, e o livro imprime `20...♗d3!`. Medido no
    Aagaard: seis linhas de variação no alto da página saíam como cabeçalho
    porque a assinatura delas — `♗d`, `g` — se repetia em três páginas.
    """
    for linha in ("20...♗d3!", "19.g6", "17.♔b1?!", "15.0—0—0"):
        assert not livro._candidato_a_cabecalho(linha), linha
    assert livro._candidato_a_cabecalho("Chapter 4 95")


def test_a_remissao_entre_parenteses_nao_e_cabecalho():
    """`(see page 43)` no alto de cinco páginas do Aagaard é remissão."""
    assert not livro._candidato_a_cabecalho("(see page 43)")


def test_a_linha_com_lance_nao_e_cabecalho():
    paginas = [_pagina(n, _paragrafo("1.e4 e5 2.♘f3", 40),
                       _paragrafo("prosa", 400, linhas=3))
               for n in range(3)]
    assert livro.retirar_cabecalhos(paginas) == {}


def test_o_rodape_de_duas_colunas_esta_no_meio_da_lista():
    """
    Na página de duas colunas o rodapé centrado cai na coluna da esquerda, e
    na lista de blocos ele fica antes da coluna da direita. Quem o acha é a
    posição, e não a ordem.
    """
    paginas = [_pagina(n,
                       _paragrafo("coluna da esquerda", 100, linhas=5),
                       _paragrafo(str(10 + n), 960),
                       _paragrafo("coluna da direita", 100, linhas=5))
               for n in range(3)]
    livro.retirar_cabecalhos(paginas)
    for p in paginas:
        assert [b.texto.split(" ")[2] for b in p.blocos] == ["esquerda",
                                                             "direita"]


def test_a_faixa_do_diagrama_e_a_figura_ficam_de_fora():
    """`titulo=True` é a faixa (F67), e ela já sai como cabeçalho de outra
    coisa; a figura não tem texto para repetir."""
    paginas = [_pagina(n, _paragrafo("Diagram 1-1", 40, titulo=True),
                       livro.Figura(b"", 10, 10),
                       _paragrafo("prosa", 400, linhas=3))
               for n in range(3)]
    assert livro.retirar_cabecalhos(paginas) == {}


def test_o_filete_lido_como_simbolo_nao_e_rodape():
    """`=` no pé de três páginas tem a assinatura vazia do número de página, e
    não é número de página: é o filete decorativo lido. Fica onde está."""
    paginas = [_pagina(n, _paragrafo("prosa", 400, linhas=3),
                       _paragrafo("=", 960))
               for n in range(3)]
    assert livro.retirar_cabecalhos(paginas) == {}


def test_a_pagina_sem_altura_nao_e_julgada():
    paginas = [_pagina(n, _paragrafo("Cabeçalho", 40), altura=0)
               for n in range(3)]
    assert livro.retirar_cabecalhos(paginas) == {}


def test_o_paragrafo_de_verdade_sai_com_a_posicao_e_os_inicios():
    linhas = [livro.Linha(topo=120, esquerda=10, altura=20, texto="uma"),
              livro.Linha(topo=150, esquerda=10, altura=20, texto="duas")]
    p = livro._paragrafo_de(linhas)
    assert p.topo == 120 and p.pe == 170 and p.linhas_impressas == 2
    assert p.texto == "uma duas" and p.inicios == [0, 4]


def test_a_juncao_no_hifen_nao_desalinha_os_inicios():
    lex = _lex("embarrassment")
    linhas = [livro.Linha(topo=120, esquerda=10, altura=20, texto="em-"),
              livro.Linha(topo=150, esquerda=10, altura=20,
                          texto="barrassment aqui")]
    p = livro._paragrafo_de(linhas, lex)
    assert p.texto == "embarrassment aqui"
    assert p.inicios == [0, 2]


# ----------------------------------------------------------------------
# O idioma do livro
# ----------------------------------------------------------------------

def _pdf_com(tmp, nome, texto, paginas=3):
    caminho = os.path.join(tmp, nome)
    doc = fitz.open()
    for _ in range(paginas):
        pagina = doc.new_page()
        pagina.insert_text((72, 72), texto)
    doc.save(caminho)
    doc.close()
    return caminho


def test_a_camada_de_texto_diz_o_idioma():
    en = "the white king and the black rook of this position is not on the "
    pt = "de que o rei das brancas e a torre das pretas não para um e uma "
    with tempfile.TemporaryDirectory() as tmp:
        assert livro.idioma_do_pdf(_pdf_com(tmp, "en.pdf", en * 6)) == "en"
        assert livro.idioma_do_pdf(_pdf_com(tmp, "pt.pdf", pt * 6)) == "pt"


def test_sem_camada_de_texto_o_idioma_nao_e_chutado():
    """A digitalização de verdade não tem camada, e a máscara errada apagaria o
    `ç` do livro inteiro: sai `None`, e quem chama pergunta."""
    with tempfile.TemporaryDirectory() as tmp:
        assert livro.idioma_do_pdf(_pdf_com(tmp, "vazio.pdf", "")) is None
        # Pouco texto também não decide.
        assert livro.idioma_do_pdf(_pdf_com(tmp, "pouco.pdf", "the of and",
                                            paginas=1)) is None


# ----------------------------------------------------------------------
# F111 — o idioma chega ao DOCX
# ----------------------------------------------------------------------

def test_o_docx_declara_o_idioma_no_estilo_base():
    paginas = [livro.PaginaExtraida(numero=0,
                                    blocos=[livro.Paragrafo("A prosa.")])]
    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_docx(paginas, os.path.join(tmp, "l.docx"),
                                     idioma="pt")
        estilos = zipfile.ZipFile(caminho).read("word/styles.xml").decode()
    assert 'w:lang w:val="pt"' in estilos


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
