"""
Testes da F61 — o livro de duas colunas deixa de sair misturado.

A ordem de leitura respeita colunas desde a F1.6, mas a régua da calha (`3 ×
largura mediana de caractere`) nunca foi medida contra livro nenhum: no Nunn ela
nunca acha a calha, e no Kasparov acha em algumas páginas e não em outras.
Página lida como coluna única sai com a linha da esquerda intercalada com a da
direita — medido, 95 saltos entre colunas em 10 páginas rotuladas, onde o certo
são 7.

E achar a calha não bastava. Havia mais três lugares onde a coluna não existia:

  - `quebrar_em_linhas` não cortava ao passar de uma coluna para a outra, e a
    última linha da esquerda saía colada na primeira da direita;
  - a margem que abre parágrafo era a mediana das esquerdas da **página**, que
    numa página de duas colunas não é margem de nenhuma das duas;
  - a figura entrava pela altura na página, e o diagrama do alto da direita vinha
    antes de quase toda a coluna da esquerda.

Rodar sem pytest:      python tests/test_f61_duas_colunas.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

from core import livro
from core.box_model import BoxEntry
from core.leitura_de_linha import quebrar_em_linhas
from core.services.box_service import BoxService


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _linha(x_ini, y, n, larg=17, alt=22, passo=20, rotulo=""):
    return [BoxEntry(f"{rotulo}{i}" if rotulo else "",
                     x_ini + i * passo, y, x_ini + i * passo + larg, y + alt)
            for i in range(n)]


def _duas_colunas(calha=19, linhas=20, n=32):
    """
    A geometria do Nunn: calha de 19 px onde o caractere mediano tem 17.

    É a página em que a régua de antes falhava — `19 < 3 × 17` —, e é o caso que
    obriga a régua a ser medida e não arbitrada.
    """
    esquerda = 0
    largura = n * 20 - 3
    direita = largura + calha
    boxes = []
    for i in range(linhas):
        y = i * 30
        boxes += _linha(esquerda, y, n, rotulo=f"e{i}_")
        boxes += _linha(direita, y, n, rotulo=f"d{i}_")
    return boxes


# ----------------------------------------------------------------------
# A régua da calha
# ----------------------------------------------------------------------

def test_a_calha_estreita_do_nunn_e_achada():
    """19 px de calha com caractere de 17: a régua de antes pedia 51."""
    boxes = _duas_colunas()
    colunas = BoxService.detectar_colunas(boxes)
    assert len(colunas) == 2, f"a calha de 19 px não foi vista: {colunas}"


def test_a_regua_de_antes_nao_achava():
    """
    Fixa o número que abriu a fase, e não o comportamento: se um dia a régua
    mudar de forma, este teste é o que diz que a de antes está sendo comparada.
    """
    boxes = _duas_colunas()
    larguras = sorted(b.x2 - b.x1 for b in boxes)
    mediana = larguras[len(larguras) // 2]
    assert len(BoxService.detectar_colunas(boxes, calha_minima=mediana * 3)) == 1


def test_espaco_entre_palavras_continua_fora():
    """A régua desceu de 3,0 para 0,8, e o espaço entre palavras tem de sobrar."""
    boxes = []
    for y in (0, 30, 60):
        boxes += _linha(0, y, 6) + _linha(130, y, 6) + _linha(260, y, 6)
    assert len(BoxService.detectar_colunas(boxes)) == 1, \
        "o espaço entre palavras virou calha"


# ----------------------------------------------------------------------
# A faixa estreita demais para ser coluna
# ----------------------------------------------------------------------

def test_sumario_nao_vira_tres_colunas():
    """
    Número do capítulo, título, número da página: três blocos com calha larga
    entre eles, e **uma** coluna. Sem o piso de largura, o livro exportado sai
    com dez números, dez títulos e dez páginas em vez de dez linhas.
    """
    boxes = []
    for i in range(10):
        y = i * 30
        boxes += _linha(0, y, 1, rotulo=f"n{i}_")        # o número do capítulo
        boxes += _linha(120, y, 30, rotulo=f"t{i}_")     # o título
        boxes += _linha(800, y, 2, rotulo=f"p{i}_")      # a página
    assert len(BoxService.detectar_colunas(boxes)) == 1, \
        "a tabela de duas casas virou colunas"


def test_a_faixa_estreita_se_funde_e_nenhum_box_se_perde():
    boxes = []
    for i in range(10):
        y = i * 30
        boxes += _linha(0, y, 1) + _linha(120, y, 30) + _linha(800, y, 2)
    saida = BoxService.sort_boxes_reading_order(list(boxes))
    assert len(saida) == len(boxes)
    assert {id(b) for b in saida} == {id(b) for b in boxes}


def test_a_coluna_larga_sobrevive_a_fusao():
    """A fusão é da faixa estreita, e não de toda faixa."""
    colunas = BoxService.detectar_colunas(_duas_colunas())
    largura = max(z for _a, z in colunas) - min(a for a, _z in colunas)
    for a, z in colunas:
        assert (z - a) >= largura * BoxService.COLUNA_MINIMA


# ----------------------------------------------------------------------
# A linha que atravessava a calha
# ----------------------------------------------------------------------

def test_a_linha_corta_ao_trocar_de_coluna():
    """
    O defeito: a sequência **sobe** ao passar para a coluna vizinha, e as duas
    regras de antes — desceu, voltou para a esquerda — deixavam passar.
    """
    boxes = BoxService.sort_boxes_reading_order(_duas_colunas(linhas=6))
    for i, linha in enumerate(quebrar_em_linhas(boxes)):
        rotulos = {b.char.split("_")[0][0] for b in linha}
        assert len(rotulos) == 1, f"a linha {i} atravessou a calha: {rotulos}"


def test_a_virgula_nao_corta_a_linha():
    """
    A régua de subir é contra o topo da **linha**, e não contra a caixa
    anterior. Contra a anterior, a letra depois de uma vírgula abre linha nova:
    a vírgula mora na base e a letra começa acima do topo dela.
    """
    linha = _linha(0, 0, 3)
    virgula = BoxEntry(",", 60, 16, 66, 26)          # baixa, colada na base
    depois = _linha(75, 0, 3)
    saida = quebrar_em_linhas(linha + [virgula] + depois)
    assert len(saida) == 1, f"cortou dentro da linha: {[len(s) for s in saida]}"


def test_a_pilha_girada_continua_inteira():
    """A 90° o texto se lê de baixo para cima; subir ali é o andamento normal."""
    pilha = []
    for i in range(5):
        b = BoxEntry(f"v{i}", 100, 200 - i * 24, 120, 220 - i * 24)
        b.angulo = 90
        pilha.append(b)
    assert len(quebrar_em_linhas(pilha)) == 1, "a pilha girada virou 5 linhas"


# ----------------------------------------------------------------------
# A margem que abre parágrafo
# ----------------------------------------------------------------------

def test_a_margem_e_de_cada_coluna():
    linhas = ([livro.Linha(topo=i * 30, esquerda=100, altura=20,
                           texto="esq", coluna=0) for i in range(5)]
              + [livro.Linha(topo=i * 30, esquerda=900, altura=20,
                             texto="dir", coluna=1) for i in range(5)])
    metricas = livro._metricas_por_coluna(linhas)
    assert metricas[0][0] == 100
    assert metricas[1][0] == 900


def test_a_coluna_da_direita_nao_vira_uma_linha_por_paragrafo():
    """
    Com a margem da página, toda linha da direita parece recuada — e cada uma
    virava um parágrafo. Medido antes: 54 parágrafos em 56 linhas.
    """
    linhas = ([livro.Linha(topo=i * 30, esquerda=100, altura=20,
                           texto=f"e{i}", coluna=0) for i in range(6)]
              + [livro.Linha(topo=i * 30, esquerda=900, altura=20,
                             texto=f"d{i}", coluna=1) for i in range(6)])
    paragrafos = livro._agrupar_em_paragrafos(linhas)
    assert len(paragrafos) == 2, [p.texto for p in paragrafos]


def test_a_troca_de_coluna_abre_paragrafo():
    """
    O salto vertical não pega o fim da coluna: ali ele é **negativo**, porque a
    leitura volta ao topo da página.
    """
    linhas = [livro.Linha(topo=900, esquerda=100, altura=20, texto="fim da esquerda",
                          coluna=0),
              livro.Linha(topo=40, esquerda=900, altura=20, texto="topo da direita",
                          coluna=1)]
    paragrafos = livro._agrupar_em_paragrafos(linhas)
    assert len(paragrafos) == 2, [p.texto for p in paragrafos]


def test_o_recuo_continua_abrindo_paragrafo_dentro_da_coluna():
    linhas = [livro.Linha(topo=0, esquerda=100, altura=20, texto="a", coluna=0),
              livro.Linha(topo=30, esquerda=100, altura=20, texto="b", coluna=0),
              livro.Linha(topo=60, esquerda=140, altura=20, texto="c", coluna=0)]
    assert len(livro._agrupar_em_paragrafos(linhas)) == 2


def test_a_coluna_de_quem_cai_na_calha_e_a_mais_proxima():
    colunas = [(0, 400), (500, 900)]
    assert livro._coluna_de(100, colunas) == 0
    assert livro._coluna_de(700, colunas) == 1
    assert livro._coluna_de(430, colunas) == 0      # dentro da calha, à esquerda
    assert livro._coluna_de(480, colunas) == 1      # dentro da calha, à direita
    assert livro._coluna_de(50, []) == 0


# ----------------------------------------------------------------------
# A página inteira
# ----------------------------------------------------------------------

#: Prosa de comprimento irregular, para o espaço entre palavras **não** cair no
#: mesmo x em todas as linhas. Repetir a mesma frase abre uma calha falsa no
#: meio da coluna: é o caso patológico que a projeção da página inteira não
#: separa, e ele não acontece em livro nenhum.
_PROSA = ["o cavalo salta para", "uma casa qualquer, e", "depois disso a torre",
          "chega ao fim; entao", "as brancas ganham a",
          "partida sem apuros!", "mas ha um detalhe:"]


def _pdf_de_duas_colunas(diagrama_na_direita=False):
    """
    Uma página com duas colunas de prosa e, se pedido, um tabuleiro no alto da
    coluna da direita.
    """
    doc = fitz.open()
    p = doc.new_page(width=420, height=460)
    for i in range(14):
        p.insert_text((30, 40 + i * 16), _PROSA[i % len(_PROSA)], fontsize=9)
    primeira = 200 if diagrama_na_direita else 40
    for i in range(14 if not diagrama_na_direita else 7):
        p.insert_text((230, primeira + i * 16), _PROSA[-(i % len(_PROSA)) - 1],
                      fontsize=9)
    if diagrama_na_direita:
        p.draw_rect(fitz.Rect(240, 30, 400, 190), width=2)
        for j in range(8):
            for k in range(8):
                if (j + k) % 2:
                    p.draw_rect(fitz.Rect(240 + j * 20, 30 + k * 20,
                                          260 + j * 20, 50 + k * 20),
                                fill=(0.75, 0.75, 0.75))
    return doc


def _blocos(pagina):
    return [("texto", b.texto) if isinstance(b, livro.Paragrafo)
            else ("figura", b.origem) for b in pagina.blocos]


def test_a_pagina_de_duas_colunas_e_lida_como_duas():
    doc = _pdf_de_duas_colunas()
    try:
        extraida = livro.extrair_pagina(doc[0], lambda r: ("x", 0.99), dpi=200)
    finally:
        doc.close()
    assert extraida.colunas == 2, f"leu {extraida.colunas} coluna(s)"


def test_o_texto_da_esquerda_sai_inteiro_antes_do_da_direita():
    """
    A queixa da fase, medida no que sai: com uma coluna só, a linha 1 da
    esquerda vinha seguida da linha 1 da direita.
    """
    doc = _pdf_de_duas_colunas()
    try:
        extraida = livro.extrair_pagina(doc[0], lambda r: ("x", 0.99), dpi=200)
        img = livro._pagina_cinza(doc[0], 200)
        boxes, _tab, _esc, _resp, colunas = livro.caixas_e_diagramas(
            img, lambda r: ("x", 0.99))
    finally:
        doc.close()

    assert len(colunas) == 2
    ordem = [livro._coluna_de((min(b.x1 for b in linha)
                               + max(b.x2 for b in linha)) / 2, colunas)
             for linha in quebrar_em_linhas(boxes)]
    saltos = sum(1 for a, b in zip(ordem, ordem[1:]) if a != b)
    assert saltos == 1, f"a leitura pulou entre colunas {saltos} vezes"
    assert extraida.caracteres > 0


def test_o_diagrama_do_alto_da_direita_nao_vem_antes_da_esquerda():
    """
    Intercalar pela altura na página põe o diagrama do topo da direita antes de
    quase toda a coluna da esquerda — que é texto que se lê muito antes dele.
    """
    doc = _pdf_de_duas_colunas(diagrama_na_direita=True)
    try:
        extraida = livro.extrair_pagina(doc[0], lambda r: ("x", 0.99), dpi=200,
                                        diagramas="recorte")
    finally:
        doc.close()

    blocos = _blocos(extraida)
    assert any(tipo == "figura" for tipo, _ in blocos), (
        f"o tabuleiro não virou figura, e sem ele não há o que medir: {blocos}")

    # **Medido em caracteres, e não em parágrafos** (F103). Contar parágrafos
    # media a ordem enquanto cada linha era um parágrafo; desde que as linhas
    # se juntam, a coluna da esquerda inteira pode sair como um bloco só, e o
    # "1 de 3" que isto passaria a ver não diz nada sobre onde a figura caiu.
    # A página põe 14 linhas na esquerda e 7 na direita: a maior parte do texto
    # tem de estar antes da figura.
    primeira = next(i for i, (tipo, _) in enumerate(blocos) if tipo == "figura")
    antes = sum(len(t) for tipo, t in blocos[:primeira] if tipo == "texto")
    total = sum(len(t) for tipo, t in blocos if tipo == "texto")
    assert antes > total / 2, (
        f"a figura do topo da direita veio no meio da esquerda: "
        f"{antes} de {total} caracteres antes dela")


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = 0
    for nome, teste in testes:
        try:
            teste()
            print(f"  ok   {nome}")
        except AssertionError as erro:
            falhas += 1
            print(f"  FALHA {nome}: {erro}")
    print(f"\n{len(testes) - falhas}/{len(testes)} passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
