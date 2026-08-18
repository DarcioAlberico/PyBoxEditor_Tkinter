"""
Testes da F58 — o diagrama redesenhado a partir do FEN.

O que estes testes prendem é o **mapa da fonte**: qual caractere desenha qual
peça em qual cor de casa. Errar uma letra ali não quebra nada — produz um
tabuleiro bonito com a peça errada, que é o pior defeito possível numa
exportação de livro, porque ninguém o vê.

Por isso as provas são três, e independentes umas das outras:

  - o mapa **fecha** (24 combinações e as duas casas vazias, uma vez cada);
  - a posição inicial sai **letra por letra** igual à que a página 3 do
    `fonts/SkakNew.pdf` imprime — é a documentação da própria fonte;
  - renderizar e **reler com as duas redes** devolve o mesmo FEN.

Rodar sem pytest:      python tests/test_f58_render_diagrama.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io

import numpy as np
import pytest
from PIL import Image

from core import render_diagrama as rd
from medir_fonte_diagrama import conferir_avanco, conferir_fechamento, conferir_tinta

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"

#: As oito linhas como a página 3 do `fonts/SkakNew.pdf` as imprime. É a
#: documentação da fonte, e o mapa não pode divergir dela.
DOCUMENTADA = ["rmblkans", "opopopop", "0Z0Z0Z0Z", "Z0Z0Z0Z0",
               "0Z0Z0Z0Z", "Z0Z0Z0Z0", "POPOPOPO", "SNAQJBMR"]


def _imagem(png: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(png)).convert("L"))


# ----------------------------------------------------------------------
# O mapa
# ----------------------------------------------------------------------

def test_o_mapa_fecha():
    """Sem isto, uma peça sai desenhada por dois caracteres e outra por nenhum."""
    assert conferir_fechamento(rd.carregar()) == []


def test_todo_caractere_do_mapa_e_uma_casa_inteira():
    """
    Glifo de avanço zero desenha **sobre** a casa anterior — é destaque, não
    casa. Um deles no mapa produziria uma linha de sete casas e um borrão.
    """
    assert conferir_avanco(rd.carregar()) == []


def test_a_cor_da_casa_esta_medida_na_tinta_e_nao_suposta():
    """
    A casa escura pinta o quadrado inteiro e a clara não. Trocar as duas letras
    de uma peça dá um tabuleiro em xadrez invertido, que só se vê olhando.
    """
    queixas, claras, escuras = conferir_tinta(rd.carregar())
    assert queixas == []
    assert max(claras)[0] < min(escuras)[0]


def test_a_posicao_inicial_sai_igual_a_documentacao_da_fonte():
    """
    É a âncora do mapa inteiro: a página 3 do `fonts/SkakNew.pdf` imprime estas
    oito linhas, e delas saem 26 dos caracteres. Se esta comparação quebrar, o
    mapa deixou de descrever a fonte que está no disco.
    """
    assert rd.linhas(INICIAL) == DOCUMENTADA


def test_a8_e_clara_e_a1_e_escura():
    assert rd.cor_da_casa(0, 0) == "clara"       # a8
    assert rd.cor_da_casa(7, 0) == "escura"      # a1
    assert rd.cor_da_casa(0, 1) == "escura"      # b8


def test_girar_o_tabuleiro_nao_muda_a_cor_das_casas():
    """
    Inverter fila e coluna ao mesmo tempo conserva a paridade. Se alguém trocar
    a conta por outra que não conserve, o tabuleiro preto embaixo sai com as
    casas invertidas — e continua parecendo um tabuleiro.
    """
    de_pretas = rd.linhas(INICIAL, orientacao="preta")
    assert de_pretas == [linha[::-1] for linha in reversed(DOCUMENTADA)]

    # e continuam 32 casas de cada cor, alternadas
    fonte = rd.carregar()
    escuras = sum(1 for linha in de_pretas for ch in linha
                  if fonte.casas[ch][1] == "escura")
    assert escuras == 32


# ----------------------------------------------------------------------
# O desenho
# ----------------------------------------------------------------------

def test_o_lado_do_tabuleiro_e_multiplo_de_oito():
    """
    Quem relê o desenho divide a imagem em 8×8 **iguais** (a F8.4 mediu o
    estrago de uma moldura de 2%). Um pixel de resto desloca a última fila.
    """
    png, largura, altura = rd.desenhar(INICIAL, lado_px=350, moldura=False)
    assert largura == altura == 352
    assert largura % 8 == 0
    assert _imagem(png).shape == (352, 352)


def test_as_coordenadas_nao_saem_por_padrao():
    """
    A opção existe porque o livro impresso as traz; o arquivo que se lê no
    tablet não precisa delas. O padrão é sem — e é o padrão que este teste
    prende, não a possibilidade.
    """
    _png, largura, altura = rd.desenhar(INICIAL, lado_px=352)
    com, largura_com, altura_com = rd.desenhar(INICIAL, lado_px=352,
                                               coordenadas=True)
    assert largura == altura, "sem coordenadas, o desenho é o tabuleiro e mais nada"
    assert largura_com > largura and altura_com > altura


def test_a_moldura_fica_fora_do_tabuleiro():
    """
    Se o filete entrasse por dentro, comeria a primeira fila de casas — e a
    releitura passaria a dividir 8×8 sobre um tabuleiro que já perdeu a borda.
    """
    _png, com, _a = rd.desenhar(INICIAL, lado_px=352, moldura=True)
    _png2, sem, _a2 = rd.desenhar(INICIAL, lado_px=352, moldura=False)
    assert com > sem


def test_o_png_sai_pequeno():
    """
    Desenho de linha em 4 tons. A `livro.TONS_DA_FIGURA` mede a mesma conta para
    o recorte; aqui vale mais, porque não há papel para guardar.
    """
    png, _l, _a = rd.desenhar(INICIAL, lado_px=352)
    assert len(png) < 20_000, f"{len(png)} bytes para um tabuleiro de 352 px"


# ----------------------------------------------------------------------
# As reclamações
# ----------------------------------------------------------------------

def test_fonte_sem_mapa_reclama_com_o_que_ha():
    with pytest.raises(rd.FonteDesconhecida) as erro:
        rd.carregar("Fonte Que Não Existe")
    assert rd.FONTE_PADRAO in str(erro.value)


def test_fonte_que_nao_desenha_o_que_o_mapa_promete_reclama():
    """
    É o modo de falha da SPEC §4.2, aqui: fonte errada não levanta erro sozinha
    — ela devolve um tabuleiro de 64 casas em branco, que passa por diagrama até
    alguém olhar de perto. A `NotoSansSymbols2` serve de cobaia porque não tem
    uma letra latina sequer.
    """
    mapas = json.load(open(rd.CAMINHO_MAPAS, encoding="utf-8"))
    mapas["fontes"]["Cobaia"] = dict(mapas["fontes"][rd.FONTE_PADRAO],
                                     arquivo="assets/fonts/NotoSansSymbols2-Regular.ttf")
    with tempfile.TemporaryDirectory() as tmp:
        caminho = os.path.join(tmp, "mapas.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(mapas, f)
        original = rd.CAMINHO_MAPAS
        rd.CAMINHO_MAPAS = caminho
        rd.esquecer()
        try:
            with pytest.raises(rd.FonteIncompleta):
                rd.carregar("Cobaia")
        finally:
            rd.CAMINHO_MAPAS = original
            rd.esquecer()


def test_fen_torto_reclama_antes_de_desenhar():
    with pytest.raises(ValueError):
        rd.linhas("rnbqkbnr/pppppppp/8 w - - 0 1")
    with pytest.raises(ValueError):
        rd.linhas(INICIAL, orientacao="de lado")


# ----------------------------------------------------------------------
# A ida e volta — o mapa conferido pelo instrumento que já existe
# ----------------------------------------------------------------------

def _ler(png: bytes):
    from core import diagrama
    try:
        return diagrama.ler(_imagem(png))
    except diagrama.ModeloAusente:
        pytest.skip("modelo não construído (rode treinar_diagrama.py)")


def test_ida_e_volta_na_posicao_inicial():
    png, _l, _a = rd.desenhar(INICIAL, lado_px=352, moldura=False)
    assert _ler(png).fen() == INICIAL


def test_ida_e_volta_nas_quatro_combinacoes_que_a_documentacao_nao_mostra():
    """
    A posição inicial não tem dama preta em casa clara, rei preto em escura,
    dama branca em escura nem rei branco em clara — são as quatro que o mapa
    fechou **por eliminação**, e portanto as únicas sem confirmação direta na
    página 3 do PDF da fonte. Esta posição põe as quatro no tabuleiro.
    """
    fen = "3k4/8/2q5/8/8/8/8/3KQ3 w - - 0 1"
    letras = set("".join(rd.linhas(fen)))
    assert {"j", "q", "K", "L"} <= letras, "a posição não exercita as quatro"

    png, _l, _a = rd.desenhar(fen, lado_px=352, moldura=False)
    assert _ler(png).fen() == fen


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
