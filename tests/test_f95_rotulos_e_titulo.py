"""
F95 — o tabuleiro dentro do painel, e o que está impresso em volta dele.

Três coisas, e as três nasceram da mesma medição: o comando "Ler posição dos
diagramas" foi passado por 21 páginas de 5 livros reais e comparado com o que
está impresso nelas.

1. **O tabuleiro aninhado.** A página 199 do Yusupov põe os dois diagramas do
   capítulo dentro de um painel sombreado. Com `RETR_EXTERNAL` o painel é o
   contorno e os tabuleiros são filhos dele — 2 impressos, 0 achados.
2. **A ordem.** Seis diagramas em duas colunas saíam por fila, e a fila trocava
   de sentido por um pixel de diferença entre o topo de um e o do outro.
3. **O que está em volta.** Os rótulos `a`–`h` e `8`–`1`, que dizem se o livro
   traz coordenadas — e para que lado o diagrama está virado —, e o título, que
   num livro fica acima e noutro abaixo.

Os testes aqui montam a página em memória: um tabuleiro desenhado casa a casa,
com ou sem moldura, com ou sem rótulo. É o único jeito de a suíte exercitar isto
sem as digitalizações, que não estão no repositório.

Rodar sem pytest:      python tests/test_f95_rotulos_e_titulo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest

from core import diagrama
from core.box_model import BoxEntry


LADO = 480          # 8 casas de 60 px
ESCALA = 20         # altura de caractere da página de mentira


def _tabuleiro(lado=LADO, moldura=3, tom_escuro=150):
    """Um tabuleiro de verdade: 8x8 alternando, com moldura fechada."""
    img = np.full((lado, lado), 255, np.uint8)
    casa = lado // 8
    for r in range(8):
        for c in range(8):
            if (r + c) % 2:
                img[r * casa:(r + 1) * casa, c * casa:(c + 1) * casa] = tom_escuro
    if moldura:
        cv2.rectangle(img, (0, 0), (lado - 1, lado - 1), 0, moldura)
    return img


def _pagina(largura=900, altura=1200):
    return np.full((altura, largura), 255, np.uint8)


def _colar(pagina, recorte, x, y):
    a, l = recorte.shape[:2]
    pagina[y:y + a, x:x + l] = recorte
    return (x, y, x + l, y + a)


def _escrever(pagina, texto, x, y, escala=ESCALA):
    """Texto na página, e a caixa de cada caractere — como o pipeline as dá."""
    caixas = []
    fonte, grossura = cv2.FONT_HERSHEY_SIMPLEX, 2
    tamanho = escala / 22.0
    passo = int(escala * 0.9)
    for i, ch in enumerate(texto):
        if ch == " ":
            continue
        cv2.putText(pagina, ch, (x + i * passo, y), fonte, tamanho, 0,
                    grossura, cv2.LINE_AA)
        (l, a), _base = cv2.getTextSize(ch, fonte, tamanho, grossura)
        caixas.append(BoxEntry(ch, x + i * passo, y - a, x + i * passo + l, y))
    return caixas


def _rotular(pagina, caixa, escala=ESCALA):
    """As letras a–h embaixo e os números 8–1 à esquerda, como o livro imprime."""
    x1, y1, x2, y2 = caixa
    casa = (x2 - x1) / 8.0
    caixas = []
    for i, ch in enumerate("abcdefgh"):
        caixas += _escrever(pagina, ch, int(x1 + i * casa + casa / 2 - escala / 3),
                            int(y2 + escala * 1.1), escala)
    for i, ch in enumerate("87654321"):
        caixas += _escrever(pagina, ch, int(x1 - escala * 1.2),
                            int(y1 + i * casa + casa / 2 + escala / 3), escala)
    return caixas


def _classificador_perfeito(pagina, caixas):
    """
    Um classificador que acerta sempre: acha na página o recorte que recebeu e
    responde o caractere que estava escrito ali.

    Não é trapaça, e a busca é o motivo: o que estes testes medem é a
    **geometria** — qual tinta é rótulo, qual é título, de que lado ela está.
    Pôr a rede de verdade no meio faria o teste falhar quando ela errasse uma
    letra, que é outro assunto e tem outra medida (`medir_paginas.py`).

    A busca é por casamento exato porque o recorte sai da própria página, mas o
    retângulo dele **não** é o que `_escrever` devolveu: ele vem do componente
    conexo achado na banda, apertado na tinta e um ou dois pixels diferente. Por
    isso casar pelo canto da caixa não serve, e a caixa que responde é a que
    contém o canto encontrado.
    """
    def classificar(recorte):
        if not recorte.size or recorte.shape[0] > pagina.shape[0]:
            return "?", 0.0
        onde = cv2.matchTemplate(pagina, recorte, cv2.TM_SQDIFF)
        _menor, _maior, (x, y), _canto = cv2.minMaxLoc(onde)
        meio = (x + recorte.shape[1] / 2, y + recorte.shape[0] / 2)
        for b in caixas:
            if b.x1 - 2 <= meio[0] <= b.x2 + 2 and b.y1 - 4 <= meio[1] <= b.y2 + 4:
                return b.char, 0.99
        return "?", 0.0
    return classificar


# ----------------------------------------------------------------------
# A prova do xadrez
# ----------------------------------------------------------------------

def test_o_tabuleiro_pontua_e_o_texto_nao():
    """
    O vão medido em 49 tabuleiros de 5 livros: de 19,7 para cima é tabuleiro,
    de 3,1 para baixo é texto. O piso mora no meio dele.
    """
    pagina = _pagina()
    _escrever(pagina, "texto qualquer nesta pagina", 40, 100)
    de_texto = diagrama.pontuacao_de_tabuleiro(pagina[0:480, 0:480])
    de_tabuleiro = diagrama.pontuacao_de_tabuleiro(_tabuleiro())

    assert de_tabuleiro > diagrama.PISO_DO_XADREZ
    assert de_texto < diagrama.PISO_DO_XADREZ


def test_a_grade_deslocada_derruba_a_pontuacao():
    """
    A mesma conta responde "a grade está no lugar?", e é o que autoriza usá-la
    para escolher entre dois recortes do mesmo tabuleiro.
    """
    tabuleiro = _tabuleiro()
    casa = LADO // 8
    certo = diagrama.pontuacao_de_tabuleiro(tabuleiro)
    torto = diagrama.pontuacao_de_tabuleiro(tabuleiro[casa // 2:, casa // 2:])

    assert certo > abs(torto) * 2, (
        f"grade certa {certo:.1f} não se distingue da deslocada {torto:.1f}")


def test_recorte_pequeno_demais_nao_pontua():
    assert diagrama.pontuacao_de_tabuleiro(np.zeros((10, 10), np.uint8)) == 0.0


# ----------------------------------------------------------------------
# O tabuleiro que não é contorno externo
# ----------------------------------------------------------------------

def _pagina_com_painel():
    """
    Um tabuleiro dentro de um painel fechado — a página 199 do Yusupov em
    miniatura. O painel é o contorno externo; o tabuleiro é filho dele.
    """
    pagina = _pagina()
    cv2.rectangle(pagina, (60, 60), (760, 1140), 0, 4)      # o painel
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    binaria = cv2.threshold(pagina, 200, 255, cv2.THRESH_BINARY_INV)[1]
    return pagina, binaria, caixa


def test_sem_a_imagem_o_tabuleiro_do_painel_continua_invisivel():
    """O defeito, escrito como teste: é o que a segunda passada existe para ver."""
    pagina, _binaria, _caixa = _pagina_com_painel()
    painel = BoxEntry("", 60, 60, 764, 1144)
    assert diagrama.localizar([painel], escala=ESCALA) == []


def test_com_a_imagem_o_tabuleiro_do_painel_aparece():
    pagina, binaria, caixa = _pagina_com_painel()
    painel = BoxEntry("", 60, 60, 764, 1144)

    achados = diagrama.localizar([painel], escala=ESCALA,
                                 imagem=pagina, binaria=binaria)

    assert len(achados) == 1, f"esperava um tabuleiro, veio {achados}"
    x1, y1, x2, y2 = achados[0]
    assert abs(x1 - caixa[0]) <= 4 and abs(y1 - caixa[1]) <= 4
    assert abs(x2 - caixa[2]) <= 4 and abs(y2 - caixa[3]) <= 4


def test_a_segunda_passada_nao_inventa_tabuleiro_em_pagina_de_texto():
    """
    A prova que a fase toda depende de não falhar: 20 páginas sem diagrama
    aninhado não ganharam nenhum. Aqui, uma página de texto e uma moldura
    quadrada vazia — que é grande, quadrada e cheia, e não é tabuleiro.
    """
    pagina = _pagina()
    _escrever(pagina, "prosa corrida da pagina", 40, 100)
    cv2.rectangle(pagina, (200, 300), (680, 780), 0, -1)     # quadrado preto
    binaria = cv2.threshold(pagina, 200, 255, cv2.THRESH_BINARY_INV)[1]

    assert diagrama.localizar([], escala=ESCALA, imagem=pagina,
                              binaria=binaria) == []


def test_o_tabuleiro_que_ja_era_contorno_externo_nao_sai_em_dobro():
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    binaria = cv2.threshold(pagina, 200, 255, cv2.THRESH_BINARY_INV)[1]

    achados = diagrama.localizar([BoxEntry("", *caixa)], escala=ESCALA,
                                 imagem=pagina, binaria=binaria)
    assert achados == [caixa]


# ----------------------------------------------------------------------
# A ordem de leitura
# ----------------------------------------------------------------------

def test_um_pixel_nao_troca_a_fila():
    """
    O caso medido: na página 221 do Yusupov o diagrama da direita começa em
    y=358 e o da esquerda em y=359.
    """
    esquerda = (291, 359, 868, 937)
    direita = (1128, 358, 1706, 937)
    assert diagrama.ordem_de_leitura([direita, esquerda])[0] == esquerda


def test_duas_colunas_saem_coluna_a_coluna():
    """
    Conferido nos rótulos que esta fase passou a ler: `Ex. 22-1` a `Ex. 22-6`
    no Yusupov, `①` a `⑥` no Aagaard — nos dois a numeração desce a coluna da
    esquerda antes de começar a da direita.
    """
    caixas = [(291, 359, 868, 937), (1128, 358, 1706, 937),
              (289, 1162, 866, 1741), (1126, 1162, 1704, 1741),
              (288, 1965, 864, 2544), (1124, 1965, 1702, 2544)]
    ordenadas = diagrama.ordem_de_leitura(caixas)
    assert [c[0] for c in ordenadas] == [291, 289, 288, 1128, 1126, 1124]


def test_uma_fila_so_sai_da_esquerda_para_a_direita():
    """Coluna a coluna cobre o caso de uma fila: são duas colunas de um."""
    esquerda, direita = (100, 200, 580, 680), (700, 205, 1180, 685)
    assert diagrama.ordem_de_leitura([direita, esquerda]) == [esquerda, direita]


# ----------------------------------------------------------------------
# Os rótulos das casas
# ----------------------------------------------------------------------

def test_o_tabuleiro_sem_rotulo_diz_que_nao_tem():
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)

    rotulos = diagrama.ler_rotulos(pagina, caixa, ESCALA)

    assert not rotulos.presentes
    assert rotulos.lados == ()
    assert rotulos.orientacao is None, "sem rótulo não há como saber o lado"


def test_o_tabuleiro_com_rotulo_diz_de_que_lados():
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    _rotular(pagina, caixa)

    rotulos = diagrama.ler_rotulos(pagina, caixa, ESCALA)

    assert rotulos.presentes
    assert set(rotulos.lados) == {"esquerda", "abaixo"}


def test_achar_o_rotulo_nao_precisa_de_classificador():
    """
    É o que faz a exportação poder escolher "como no livro" sem carregar a rede
    de texto: a prova de que há coordenadas é geométrica, uma marca por raia.
    """
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    _rotular(pagina, caixa)

    rotulos = diagrama.ler_rotulos(pagina, caixa, ESCALA, classificar=None)

    assert rotulos.presentes
    assert rotulos.colunas == "" and rotulos.filas == ""


def test_prosa_ao_lado_do_tabuleiro_nao_e_rotulo():
    """
    O que separa rótulo de texto vizinho é a raia: rótulo tem uma marca em cada
    uma das oito, prosa não tem. Medido, quem não rotula chega a quatro raias.
    """
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    _escrever(pagina, "linha de prosa", 120, 200 + LADO + int(ESCALA * 1.2))

    rotulos = diagrama.ler_rotulos(pagina, caixa, ESCALA)

    assert "abaixo" not in rotulos.lados


def test_os_rotulos_lidos_dizem_o_lado_do_tabuleiro():
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    caixas = _rotular(pagina, caixa)

    rotulos = diagrama.ler_rotulos(pagina, caixa, ESCALA,
                                   _classificador_perfeito(pagina, caixas))

    assert rotulos.colunas == "abcdefgh"
    assert rotulos.filas == "87654321"
    assert rotulos.orientacao == "branca"


def test_o_rotulo_invertido_denuncia_o_diagrama_das_pretas():
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    caixas = []
    x1, y1, x2, y2 = caixa
    casa = (x2 - x1) / 8.0
    for i, ch in enumerate("hgfedcba"):
        caixas += _escrever(pagina, ch,
                            int(x1 + i * casa + casa / 2 - ESCALA / 3),
                            int(y2 + ESCALA * 1.1))
    for i, ch in enumerate("12345678"):
        caixas += _escrever(pagina, ch, int(x1 - ESCALA * 1.2),
                            int(y1 + i * casa + casa / 2 + ESCALA / 3))

    rotulos = diagrama.ler_rotulos(pagina, caixa, ESCALA,
                                   _classificador_perfeito(pagina, caixas))

    assert rotulos.orientacao == "preta"


def test_rotulo_ilegivel_nao_afirma_orientacao():
    """
    A régua é conservadora porque errar aqui gira um FEN que estava certo.
    Sem letra lida, a resposta é `None` — e `None` não é "brancas embaixo".
    """
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    _rotular(pagina, caixa)

    rotulos = diagrama.ler_rotulos(pagina, caixa, ESCALA,
                                   lambda recorte: ("?", 0.0))

    assert rotulos.presentes, "a geometria continua achando o rótulo"
    assert rotulos.orientacao is None


# ----------------------------------------------------------------------
# O título
# ----------------------------------------------------------------------

def test_o_titulo_acima_do_tabuleiro():
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    caixas = _escrever(pagina, "Ex221", 120, 200 - int(ESCALA * 0.4))

    titulo = diagrama.ler_titulo(pagina, caixa, ESCALA,
                                 _classificador_perfeito(pagina, caixas),
                                 boxes=caixas)

    assert titulo.lado == "acima"
    assert titulo.texto.replace(" ", "") == "Ex221"


def test_o_titulo_abaixo_do_tabuleiro():
    """
    O Nunn põe o número do diagrama embaixo, e por seis fases ninguém olhou
    para esse lado — a `livro._faixa_acima` só procurava acima.
    """
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    caixas = _escrever(pagina, "437", 120, 200 + LADO + int(ESCALA * 1.3))

    titulo = diagrama.ler_titulo(pagina, caixa, ESCALA,
                                 _classificador_perfeito(pagina, caixas),
                                 boxes=caixas)

    assert titulo.lado == "abaixo"
    assert titulo.texto.replace(" ", "") == "437"


def test_o_lado_que_tem_rotulo_nao_vira_titulo():
    """Sem isto, `abcdefgh` sairia como o nome do diagrama."""
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    caixas = _rotular(pagina, caixa)
    rotulos = diagrama.ler_rotulos(pagina, caixa, ESCALA)

    titulo = diagrama.ler_titulo(pagina, caixa, ESCALA,
                                 _classificador_perfeito(pagina, caixas),
                                 boxes=caixas, rotulos=rotulos)

    assert titulo.lado != "abaixo"


def test_o_titulo_devolve_as_caixas_que_consumiu():
    """
    Quem exporta precisa tirá-las do texto da página: a legenda de baixo começa
    dentro da margem de exclusão e acaba fora dela, então chega ao texto — e
    sairia duas vezes no livro.
    """
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    caixas = _escrever(pagina, "437", 120, 200 + LADO + int(ESCALA * 1.3))

    titulo = diagrama.ler_titulo(pagina, caixa, ESCALA, boxes=caixas)

    assert {id(b) for b in titulo.caixas} <= {id(b) for b in caixas}
    assert len(titulo.caixas) == len(caixas)


def test_sem_nada_em_volta_nao_ha_titulo():
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)

    titulo = diagrama.ler_titulo(pagina, caixa, ESCALA, boxes=[])

    assert not titulo
    assert titulo.lado == ""


def test_a_caixa_do_titulo_sai_mesmo_sem_o_texto():
    """
    "Não há título" e "há, e o modelo não deu conta" são coisas diferentes: no
    segundo caso quem exporta ainda pode recortá-lo como imagem, que é o que a
    F60 fazia.
    """
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    caixas = _escrever(pagina, "Ex221", 120, 200 - int(ESCALA * 0.4))

    titulo = diagrama.ler_titulo(pagina, caixa, ESCALA,
                                 lambda recorte: ("?", 0.0), boxes=caixas)

    assert titulo.texto == ""
    assert titulo.caixa is not None
    assert bool(titulo) is True


# ----------------------------------------------------------------------
# A orientação chega ao FEN
# ----------------------------------------------------------------------

def _leitura_de_teste(orientacao):
    """
    `ler` sem rede: as duas redes são substituídas por respostas fixas.

    O que se mede aqui é o giro das casas, e ele acontece depois das redes.
    """
    return orientacao


def test_orientacao_invalida_e_recusada():
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    with pytest.raises(ValueError):
        diagrama.ler(pagina, caixa, orientacao="de lado")


def test_o_giro_leva_a_casa_de_um_canto_ao_outro(monkeypatch):
    """
    Um diagrama impresso do lado das pretas tem a casa de cima à esquerda
    valendo `h1`, e não `a8`. O FEN sai o da posição; quem guarda o desenho do
    livro é `Leitura.orientacao`.
    """
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)

    # A casa (0,0) do recorte tem peça, e é um rei branco. As duas redes
    # respondem isso, e nada mais.
    monkeypatch.setattr(diagrama, "_probabilidade_de_peca",
                        lambda residuo: {k: (0.99 if k == (0, 0) else 0.01)
                                         for k in residuo})

    def pontuar(residuos):
        pontos = np.zeros((len(residuos), len(diagrama.SIMBOLOS)), np.float32)
        pontos[:, diagrama.SIMBOLOS.index("K")] = 1.0
        return pontos

    monkeypatch.setattr(diagrama, "_pontuar", pontuar)

    de_branca = diagrama.ler(pagina, caixa, orientacao="branca")
    de_preta = diagrama.ler(pagina, caixa, orientacao="preta")

    assert [c.nome for c in de_branca.ocupadas] == ["a8"]
    assert [c.nome for c in de_preta.ocupadas] == ["h1"]
    assert de_preta.orientacao == "preta"
    assert any("pretas" in a for a in de_preta.avisos)


def test_as_64_casas_saem_na_ordem_do_tabuleiro(monkeypatch):
    """
    Quem lê `leitura.casas[0]` espera `a8`, esteja o diagrama virado para que
    lado for. É o contrato que o giro não pode quebrar.
    """
    pagina = _pagina()
    caixa = _colar(pagina, _tabuleiro(), 120, 200)
    monkeypatch.setattr(diagrama, "_probabilidade_de_peca",
                        lambda residuo: {k: 0.01 for k in residuo})

    for orientacao in ("branca", "preta"):
        casas = diagrama.ler(pagina, caixa, orientacao=orientacao).casas
        assert len(casas) == 64
        assert [(c.linha, c.coluna) for c in casas] == [
            (r, c) for r in range(8) for c in range(8)]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
