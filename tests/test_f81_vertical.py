"""
F8.1 — texto impresso na vertical.

O risco desta fase tem dois lados, e eles puxam para lados opostos.

**Não ler.** Medido nos 10.606 caracteres rotulados, o classificador acerta
94,2% no recorte de pé e 8,4% no mesmo recorte girado 90° — e a diferença não
aparece como falha, aparece como outra letra, com confiança normal e origem
`neural`. Antes desta fase o rótulo ao lado do diagrama entrava no texto como
ruído bem-comportado.

**Mexer no que estava certo.** O caminho para ler o girado passa por proteger
essas caixas do merge, do corte de glifo colado e da ordem por linha. Se a
detecção disparar em texto normal, ela estraga a página inteira para consertar
um rótulo. Por isso metade destes testes é sobre **não** marcar: coluna de
primeiras letras, pilha curta demais, empate de confiança, ausência de árbitro.

Rodar sem pytest:      python tests/test_f81_vertical.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from core import formato_box, vertical
from core.box_model import BoxEntry
from core.services.box_service import BoxService


# ----------------------------------------------------------------------
# Apoio: um "glifo" assimétrico e um árbitro que só reconhece o de pé
# ----------------------------------------------------------------------

LADO = 20


def _glifo_l(lado=LADO):
    """Um 'L': tinta na coluna da esquerda e na linha de baixo."""
    img = np.full((lado, lado), 255, np.uint8)
    img[:, :lado // 4] = 0
    img[-lado // 4:, :] = 0
    return img


def _arbitro_de_pe(recorte):
    """
    (char, confiança) — alta só quando o 'L' está de pé.

    Mede onde está a tinta: de pé ela se concentra embaixo à esquerda e o
    canto superior direito fica limpo. É o mínimo para um teste poder falar de
    "o classificador prefere este ângulo" sem carregar o modelo real.
    """
    arr = np.asarray(recorte, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr.mean(axis=2)
    h, w = arr.shape[:2]
    if h < 2 or w < 2:
        return "", 0.0
    tinta = 255.0 - arr
    inferior_esq = tinta[h // 2:, :w // 2].mean()
    superior_dir = tinta[:h // 2, w // 2:].mean()
    escala = max(tinta.mean(), 1.0)
    nota = (inferior_esq - superior_dir) / (2 * escala)
    return "L", float(min(0.99, max(0.01, 0.5 + nota / 2)))


def _pagina_com_pilha(angulo=90, n=6, x=200, y=100, lado=LADO, folga=2):
    """
    (imagem, boxes) de uma página branca com uma pilha de 'L' girados.

    O 'L' é desenhado já girado, como o livro o imprime: `angulo` é o do texto.
    """
    altura, largura = y + n * (lado + folga) + 200, x + 400
    pagina = np.full((altura, largura), 255, np.uint8)

    glifo = _glifo_l(lado)
    # `endireitar` desfaz o ângulo; para desenhar o impresso, aplica o inverso.
    impresso = vertical.endireitar(glifo, -angulo % 360)

    boxes = []
    for i in range(n):
        topo = y + i * (lado + folga)
        pagina[topo:topo + lado, x:x + lado] = impresso
        boxes.append(BoxEntry("", x, topo, x + lado, topo + lado))
    return pagina, boxes


def _texto_normal(n=40, lado=10, largura=20, altura=30, x0=10, y0=10):
    """Boxes de caractere numa página de texto comum, 20 por linha."""
    return [BoxEntry("a", x0 + (i % 20) * largura, y0 + (i // 20) * altura,
                     x0 + (i % 20) * largura + lado,
                     y0 + (i // 20) * altura + lado)
            for i in range(n)]


# ----------------------------------------------------------------------
# Girar é transposição, e o sinal tem de estar certo
# ----------------------------------------------------------------------

def test_endireitar_desfaz_o_giro_de_90():
    glifo = _glifo_l()
    impresso = np.rot90(glifo, 1)          # o texto a 90° sai girado no AH
    assert np.array_equal(vertical.endireitar(impresso, 90), glifo)


def test_endireitar_desfaz_o_giro_de_270():
    glifo = _glifo_l()
    impresso = np.rot90(glifo, -1)
    assert np.array_equal(vertical.endireitar(impresso, 270), glifo)


def test_endireitar_a_zero_nao_toca_no_recorte():
    glifo = _glifo_l()
    assert vertical.endireitar(glifo, 0) is glifo


def test_endireitar_devolve_array_contiguo():
    """`np.rot90` devolve vista de passo negativo, e o OpenCV recusa isso."""
    girado = vertical.endireitar(_glifo_l(), 90)
    assert girado.flags["C_CONTIGUOUS"]


def test_girar_e_voltar_nao_perde_pixel():
    """Múltiplo de 90° é transposição: ida e volta é identidade, não parecida."""
    glifo = _glifo_l()
    for angulo in (90, 180, 270):
        ida = vertical.endireitar(glifo, -angulo % 360)
        assert np.array_equal(vertical.endireitar(ida, angulo), glifo)


def test_recorte_de_pe_usa_o_angulo_do_box():
    pagina, boxes = _pagina_com_pilha(angulo=90, n=1)
    boxes[0].angulo = 90
    de_pe = vertical.recorte_de_pe(pagina, boxes[0])
    assert _arbitro_de_pe(de_pe)[1] > _arbitro_de_pe(
        pagina[boxes[0].y1:boxes[0].y2, boxes[0].x1:boxes[0].x2])[1]


# ----------------------------------------------------------------------
# A geometria propõe
# ----------------------------------------------------------------------

def test_acha_a_pilha():
    _, boxes = _pagina_com_pilha(n=6)
    cadeias = vertical.candidatos(_texto_normal() + boxes)
    assert len(cadeias) == 1
    assert len(cadeias[0]) == 6


def test_pilha_curta_demais_nao_e_candidata():
    """Quatro caixas empilhadas são coluna de peça de diagrama, e foi medido."""
    _, boxes = _pagina_com_pilha(n=vertical.MIN_ITENS - 1)
    assert vertical.candidatos(_texto_normal() + boxes) == []


def test_coluna_de_primeiras_letras_nao_e_pilha():
    """
    O caso que separa geometria boa de geometria ingênua.

    As primeiras letras de linhas seguidas de um parágrafo dividem a faixa de
    x e estão empilhadas. O que as distingue é o **vão**: entre linhas ele é
    da ordem da entrelinha, não do espaço entre letras.
    """
    boxes = [BoxEntry("a", 10, 10 + i * 30, 20, 20 + i * 30) for i in range(8)]
    boxes += _texto_normal()
    assert vertical.candidatos(boxes) == []


def _coluna_de_linhas(n=6, com_vizinho=True, lado=10, passo=16, x=10, y=10):
    """
    Primeiras letras de `n` linhas seguidas de texto apertado.

    O passo é pequeno de propósito: o vão entre linhas cabe no limiar, então
    quem tem de recusar esta pilha é a regra do vizinho, e não a do vão.
    """
    coluna = [BoxEntry("a", x, y + i * passo, x + lado, y + lado + i * passo)
              for i in range(n)]
    resto = []
    if com_vizinho:
        for i in range(n):
            for k in range(1, 4):
                resto.append(BoxEntry(
                    "b", x + k * (lado + 2), y + i * passo,
                    x + k * (lado + 2) + lado, y + lado + i * passo))
    return coluna, resto


def test_coluna_de_linhas_apertadas_e_recusada_pelo_vizinho():
    """
    O falso positivo que a varredura das 322 páginas achou.

    Letra de linha horizontal tem vizinha **ao lado**; letra de linha vertical
    tem vizinha em cima e embaixo. Sem esta regra, 5 a 9 caracteres reais de
    uma coluna de variantes eram marcados como girados — e aí lidos errados e
    tirados da própria linha na ordem de leitura.
    """
    coluna, resto = _coluna_de_linhas(com_vizinho=True)
    assert vertical.candidatos(coluna + resto) == []


def test_a_mesma_coluna_sem_vizinho_continua_candidata():
    """O controle: é o vizinho que recusa, e não a geometria da pilha."""
    coluna, _ = _coluna_de_linhas(com_vizinho=False)
    assert len(vertical.candidatos(coluna)) == 1


def test_o_diagrama_ao_lado_nao_conta_como_vizinho():
    """
    O rótulo que esta fase existe para ler fica encostado no diagrama.

    Só caixa de tamanho de caractere conta como vizinha — senão a única
    vizinhança que o rótulo tem seria também o que o recusaria.
    """
    _, pilha = _pagina_com_pilha(angulo=90, n=6, x=300, y=100)
    diagrama = BoxEntry("", 60, 60, 290, 290)
    assert len(vertical.candidatos(_texto_normal() + pilha + [diagrama])) == 1


def test_pilha_larga_demais_nao_e_candidata():
    """Uma coluna baixa e gorda não é palavra girada."""
    boxes = [BoxEntry("", 10, 10 + i * 12, 90, 20 + i * 12) for i in range(6)]
    assert vertical.candidatos(boxes + _texto_normal()) == []


def test_caixas_desalinhadas_nao_formam_pilha():
    boxes = [BoxEntry("", 10 + i * 30, 10 + i * 12, 20 + i * 30, 20 + i * 12)
             for i in range(8)]
    assert vertical.candidatos(boxes + _texto_normal()) == []


def test_pagina_de_texto_comum_nao_propoe_nada():
    assert vertical.candidatos(_texto_normal(200)) == []


def test_pagina_vazia_nao_quebra():
    assert vertical.candidatos([]) == []


def test_duas_pilhas_saem_separadas():
    _, a = _pagina_com_pilha(n=6, x=200, y=100)
    _, b = _pagina_com_pilha(n=6, x=400, y=100)
    cadeias = vertical.candidatos(_texto_normal() + a + b)
    assert sorted(len(c) for c in cadeias) == [6, 6]


# ----------------------------------------------------------------------
# O classificador dispõe
# ----------------------------------------------------------------------

def test_decide_90_quando_o_classificador_prefere_90():
    pagina, boxes = _pagina_com_pilha(angulo=90)
    angulo, _ = vertical.decidir_angulo(pagina, boxes, _arbitro_de_pe)
    assert angulo == 90


def test_decide_270_quando_o_classificador_prefere_270():
    pagina, boxes = _pagina_com_pilha(angulo=270)
    angulo, _ = vertical.decidir_angulo(pagina, boxes, _arbitro_de_pe)
    assert angulo == 270


def test_pilha_de_texto_de_pe_fica_de_pe():
    """O glifo desenhado sem giro: o de pé ganha e nada é marcado."""
    pagina, boxes = _pagina_com_pilha(angulo=0)
    angulo, medias = vertical.decidir_angulo(pagina, boxes, _arbitro_de_pe)
    assert angulo == 0
    assert medias[0] >= max(medias[a] for a in vertical.ANGULOS)


def test_empate_fica_de_pe():
    """Sem folga, não mexe: estragar texto normal custa mais que não ler um rótulo."""
    pagina, boxes = _pagina_com_pilha(angulo=90)
    angulo, _ = vertical.decidir_angulo(pagina, boxes,
                                        lambda r: ("x", 0.5), margem=0.05)
    assert angulo == 0


def test_a_margem_e_exigida():
    pagina, boxes = _pagina_com_pilha(angulo=90)
    quase = vertical.decidir_angulo(pagina, boxes, _arbitro_de_pe, margem=0.99)
    assert quase[0] == 0


def test_arbitro_que_explode_nao_derruba_a_pagina():
    def ruim(recorte):
        raise RuntimeError("modelo quebrado")

    pagina, boxes = _pagina_com_pilha(angulo=90)
    novos, pilhas = vertical.aplicar(pagina, boxes, ruim)
    assert pilhas == []
    assert len(novos) == len(boxes)


# ----------------------------------------------------------------------
# `aplicar`: a fase inteira
# ----------------------------------------------------------------------

def test_aplicar_marca_o_angulo():
    pagina, boxes = _pagina_com_pilha(angulo=90)
    novos, pilhas = vertical.aplicar(pagina, boxes + _texto_normal(),
                                     _arbitro_de_pe)
    assert len(pilhas) == 1
    assert all(b.angulo == 90 for b in pilhas[0])
    assert all(b.angulo == 0 for b in novos if b.char == "a")


def test_sem_arbitro_nada_acontece():
    """A lição da F1.5b: sem quem confirme, a mudança fica desarmada."""
    pagina, boxes = _pagina_com_pilha(angulo=90)
    novos, pilhas = vertical.aplicar(pagina, boxes, None)
    assert pilhas == []
    assert all(b.angulo == 0 for b in novos)
    assert len(novos) == len(boxes)


def test_aplicar_nao_perde_box():
    pagina, boxes = _pagina_com_pilha(angulo=90)
    texto = _texto_normal()
    novos, _ = vertical.aplicar(pagina, boxes + texto, _arbitro_de_pe)
    assert len(novos) == len(boxes) + len(texto)


def test_o_pingo_ao_lado_entra_na_pilha():
    """
    Num 'i' girado o pingo fica ao lado da haste, não em cima.

    Ele não está na corrente de vizinhos — está na faixa dela —, e sem ser
    recolhido sobraria um box de ângulo 0 no meio de uma pilha girada.
    """
    pagina, boxes = _pagina_com_pilha(angulo=90, n=6, lado=LADO)
    haste = boxes[2]
    pingo = BoxEntry("", haste.x2 - 4, haste.y1 + 6, haste.x2 - 1, haste.y1 + 9)
    novos, pilhas = vertical.aplicar(pagina, boxes + [pingo], _arbitro_de_pe)
    assert all(getattr(b, "angulo", 0) == 90 for b in novos)
    assert len(novos) < len(boxes) + 1        # o pingo foi fundido na haste


# ----------------------------------------------------------------------
# A pilha como unidade: merge, corte e ordem
# ----------------------------------------------------------------------

def test_o_merge_vertical_nao_cola_a_pilha():
    """
    Era o defeito mais caro da segmentação: medido, uma linha real de 17
    caracteres colada girada na margem saía como 7 boxes.
    """
    _, boxes = _pagina_com_pilha(angulo=90, n=6, folga=1)
    for b in boxes:
        b.angulo = 90
    assert len(BoxService.merge_vertical_boxes(boxes)) == 6


def test_o_merge_vertical_continua_colando_o_pingo_do_i():
    """A proteção é só de quem está girado; o resto do merge não muda."""
    boxes = [BoxEntry("", 10, 10, 20, 13), BoxEntry("", 10, 16, 20, 30)]
    assert len(BoxService.merge_vertical_boxes(boxes)) == 1


def test_o_corte_de_glifo_colado_pula_o_girado():
    """Num glifo deitado a coluna de tinta atravessa o caractere, não entre eles."""
    binaria = np.zeros((40, 200), np.uint8)
    largo = BoxEntry("", 10, 10, 90, 30, angulo=90)
    normais = [BoxEntry("", 100 + i * 10, 10, 108 + i * 10, 30) for i in range(6)]
    saida = BoxService.dividir_glifos_colados([largo] + normais, binaria)
    assert sum(1 for b in saida if getattr(b, "angulo", 0)) == 1


def test_a_pilha_sai_inteira_na_ordem_de_leitura():
    _, pilha = _pagina_com_pilha(angulo=90, n=6, x=300, y=200)
    for b in pilha:
        b.angulo = 90
    saida = BoxService.sort_boxes_reading_order(_texto_normal(60) + pilha)
    posicoes = [i for i, b in enumerate(saida) if getattr(b, "angulo", 0)]
    assert posicoes == list(range(min(posicoes), min(posicoes) + 6))


def test_a_pilha_de_90_le_de_baixo_para_cima():
    _, pilha = _pagina_com_pilha(angulo=90, n=5)
    for i, b in enumerate(pilha):
        b.angulo, b.char = 90, "abcde"[i]
    saida = [b.char for b in BoxService.sort_boxes_reading_order(pilha)]
    assert "".join(saida) == "edcba"


def test_a_pilha_de_270_le_de_cima_para_baixo():
    _, pilha = _pagina_com_pilha(angulo=270, n=5)
    for i, b in enumerate(pilha):
        b.angulo, b.char = 270, "abcde"[i]
    saida = [b.char for b in BoxService.sort_boxes_reading_order(pilha)]
    assert "".join(saida) == "abcde"


def test_a_pilha_nao_embaralha_o_texto_em_volta():
    texto = _texto_normal(60)
    esperado = [b.char for b in BoxService.sort_boxes_reading_order(list(texto))]
    _, pilha = _pagina_com_pilha(angulo=90, n=6, x=600, y=400)
    for b in pilha:
        b.angulo = 90
    com_pilha = BoxService.sort_boxes_reading_order(texto + pilha)
    assert [b.char for b in com_pilha if not getattr(b, "angulo", 0)] == esperado


def test_pagina_sem_pilha_ordena_como_sempre():
    texto = _texto_normal(60)
    antes = BoxService.sort_boxes_reading_order(list(texto))
    assert [b.as_tuple() for b in antes] == [
        b.as_tuple() for b in BoxService.sort_boxes_reading_order(list(texto))]


# ----------------------------------------------------------------------
# O ângulo tem de sobreviver ao disco
# ----------------------------------------------------------------------

def test_o_box_grava_o_angulo_no_setimo_campo():
    linha = formato_box.formatar_linha(
        BoxEntry("A", 10, 20, 30, 40, angulo=90), altura=100)
    assert linha.split() == ["A", "10", "60", "30", "80", "0", "90"]


def test_box_de_pe_nao_ganha_campo_novo():
    """Página sem texto girado grava o arquivo byte a byte igual ao de antes."""
    linha = formato_box.formatar_linha(BoxEntry("A", 10, 20, 30, 40), altura=100)
    assert len(linha.split()) == 6


def test_ida_e_volta_pelo_disco_preserva_o_angulo():
    boxes = [BoxEntry("A", 10, 20, 30, 40, angulo=90),
             BoxEntry("b", 50, 20, 70, 40, angulo=270),
             BoxEntry("c", 80, 20, 90, 40)]
    texto = formato_box.escrever_texto(boxes, altura=100)
    voltou = formato_box.ler_texto(texto, altura=100)
    assert [b.angulo for b in voltou] == [90, 270, 0]


def test_arquivo_anterior_a_esta_fase_le_com_angulo_zero():
    box = formato_box.analisar_linha("A 10 60 30 80 0", altura=100)
    assert box.angulo == 0


def test_setimo_campo_estranho_nao_derruba_a_linha():
    """O campo é extensão nossa; perder o ângulo custa menos que perder o box."""
    box = formato_box.analisar_linha("A 10 60 30 80 0 45", altura=100)
    assert box is not None and box.angulo == 0
    box = formato_box.analisar_linha("A 10 60 30 80 0 xyz", altura=100)
    assert box is not None and box.angulo == 0


def test_o_angulo_sobrevive_ao_desfazer():
    from core.services.history_service import HistoryManager

    h = HistoryManager()
    h.snapshot([BoxEntry("A", 1, 2, 3, 4, angulo=90)])
    h.snapshot([BoxEntry("A", 1, 2, 3, 4, angulo=90),
                BoxEntry("B", 5, 6, 7, 8, angulo=270)])
    voltou, _ = h.undo()
    assert [b.angulo for b in voltou] == [90]


def test_o_angulo_sobrevive_ao_rascunho():
    from core.services.document_service import DocumentSession

    sessao = DocumentSession("pagina.png", is_pdf=False)
    sessao.store(0, [BoxEntry("A", 1, 2, 3, 4, angulo=270)])
    outra = DocumentSession("pagina.png", is_pdf=False)
    outra.aplicar_payload(sessao.montar_payload())
    assert outra.boxes_for(0)[0].angulo == 270


def test_dividir_um_box_girado_devolve_metades_giradas():
    metades = BoxService.split_box(BoxEntry("", 0, 0, 20, 60, angulo=90))
    assert [b.angulo for b in metades] == [90, 90]


# ----------------------------------------------------------------------
# Quem consome o box tem de pedir o recorte de pé
# ----------------------------------------------------------------------

def test_a_base_de_referencia_aprende_o_glifo_de_pe():
    """
    Guardar um 'A' deitado sob o rótulo 'A' envenena a vizinhança do k-NN.

    O aprendizado é a via por onde uma correção do usuário entra na base — e
    é justamente num rótulo vertical que ele mais corrige.
    """
    from PIL import Image
    from core.services.learning_service import LearningService

    class LearnerFalso:
        def __init__(self):
            self.recebidos = []

        def learn(self, crop, char):
            self.recebidos.append(np.asarray(crop))

        def salvar_cache(self):
            pass

    pagina, boxes = _pagina_com_pilha(angulo=90, n=1)
    boxes[0].char, boxes[0].angulo = "L", 90

    servico = LearningService()
    servico._learner = LearnerFalso()
    servico.learn_from_boxes(Image.fromarray(pagina), boxes)

    guardado = servico._learner.recebidos[0]
    assert _arbitro_de_pe(guardado)[1] > 0.5


def test_o_pdf_pesquisavel_escreve_o_texto_girado():
    """
    O `rotate` do PyMuPDF usa a mesma convenção do `angulo`, e isso é conferido.

    Sem girar, a camada invisível de um rótulo vertical sairia deitada por
    cima da página: a seleção no leitor cairia no caractere errado e a cópia
    sairia fora de ordem.
    """
    import fitz

    doc = fitz.open()
    pagina = doc.new_page(width=200, height=200)
    pagina.insert_text(fitz.Point(100, 100), "Ab", fontsize=12, rotate=90)
    direcoes = [linha["dir"] for bloco in pagina.get_text("dict")["blocks"]
                for linha in bloco.get("lines", [])]
    doc.close()
    assert direcoes == [(0.0, -1.0)]           # sobe na página, como o ângulo 90


def test_a_origem_do_texto_muda_com_o_angulo():
    from core.searchable_pdf import _origem_do_texto

    assert tuple(_origem_do_texto(0, 10, 20, 30, 40)) == (10, 40)
    assert tuple(_origem_do_texto(90, 10, 20, 30, 40)) == (30, 40)
    assert tuple(_origem_do_texto(270, 10, 20, 30, 40)) == (10, 20)


# ----------------------------------------------------------------------
# Ponta a ponta, com a segmentação de verdade
# ----------------------------------------------------------------------

def test_a_pagina_inteira_sai_com_a_pilha_marcada():
    """
    `generate_boxes_opencv` com árbitro: a pilha sai marcada e não colada.

    É o teste que amarra a fase — detecção, arbitragem, merge protegido e
    ordem, no caminho que a interface usa.
    """
    from PIL import Image

    pagina, _ = _pagina_com_pilha(angulo=90, n=6, x=250, y=60, lado=20, folga=3)
    # texto normal em volta, para a mediana de caractere existir
    for i in range(60):
        x, y = 10 + (i % 10) * 20, 20 + (i // 10) * 40
        pagina[y:y + 14, x:x + 10] = 0

    boxes = BoxService.generate_boxes_opencv(Image.fromarray(pagina),
                                             arbitro=_arbitro_de_pe)
    girados = [b for b in boxes if getattr(b, "angulo", 0)]
    assert len(girados) == 6
    assert all(b.angulo == 90 for b in girados)


def test_a_mesma_pagina_sem_arbitro_nao_marca_nada():
    from PIL import Image

    pagina, _ = _pagina_com_pilha(angulo=90, n=6, x=250, y=60, lado=20, folga=3)
    for i in range(60):
        x, y = 10 + (i % 10) * 20, 20 + (i // 10) * 40
        pagina[y:y + 14, x:x + 10] = 0

    boxes = BoxService.generate_boxes_opencv(Image.fromarray(pagina))
    assert all(getattr(b, "angulo", 0) == 0 for b in boxes)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
