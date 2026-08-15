"""
F17 — ler a linha, e não o caractere.

Medido nas páginas rotuladas, pelo módulo de produção:

    por caractere (F16)                        72,9%
    por linha, com alinhamento                 89,5%
    (só nas linhas 100% no alfabeto do EasyOCR: 91,7%)
"""

import numpy as np
import pytest

from core import leitura_de_linha as ldl
from core.box_model import BoxEntry


def _boxes(chars, y1=10, y2=30, largura=8):
    return [BoxEntry(c, i * largura, y1, i * largura + largura - 1, y2)
            for i, c in enumerate(chars)]


# ----------------------------------------------------------------------
# distribuir — o coração da fase
# ----------------------------------------------------------------------

def test_comprimento_igual_e_troca_direta():
    assert ldl.distribuir(list("F0reW0rd"), "Foreword") == list("Foreword")


def test_a_linha_com_caractere_a_mais_descarta_o_sobrando():
    """
    O desvio mais comum: a linha traz caractere a mais que boxes (+1 em 34 das
    275 linhas medidas, +2 em 29). O alinhamento os descarta.
    """
    saida = ldl.distribuir(list("Level"), "Levell")
    assert len(saida) == 5, "sobrou caractere sem box"
    assert "".join(saida) == "Level"


def test_a_linha_com_caractere_a_menos_nao_encurta():
    """Faltando caractere, o box continua com o que a leitura dele disse."""
    saida = ldl.distribuir(list("Level"), "Leve")
    assert len(saida) == 5


def test_a_leitura_vazia_nao_desloca_o_indice():
    """
    O defeito que quase passou: `"".join` de uma lista com vazio encurta a
    âncora, e o índice devolvido pelo alinhamento deixa de ser o do box —
    tudo depois dele anda uma casa.
    """
    ancora = ["F", "", "r", "e", "w", "o", "r", "d"]
    saida = ldl.distribuir(ancora, "Foreword")

    assert len(saida) == len(ancora)
    assert "".join(saida) == "Foreword"
    assert saida[1] == "o", "o caractere foi parar no box errado"


def test_varios_vazios_seguidos():
    saida = ldl.distribuir(["a", "", "", "d"], "abcd")
    assert "".join(saida) == "abcd"


def test_a_marca_de_vazio_nao_vaza_para_a_saida():
    saida = ldl.distribuir(["a", "", "c"], "abc")
    assert ldl.MARCA_DE_VAZIO not in "".join(saida)


def test_texto_vazio_deixa_tudo_como_estava():
    assert ldl.distribuir(list("abc"), "") == list("abc")


def test_ligadura_ocupa_uma_casa_so_na_ancora():
    """
    O outro jeito de perder o índice do box, e este apareceu de verdade: a
    cadeia neural emite `fi` num box só, e `"".join` faria a âncora ficar
    **maior** que o número de boxes. Foi a asserção que pegou, quando o
    `searchable_pdf` passou a chamar por aqui.
    """
    saida = ldl.distribuir(["o", "fi", "c", "e"], "office")
    assert len(saida) == 4, "a ligadura virou dois boxes"


def test_a_linha_nao_sobrescreve_ligadura():
    """
    Um box lido como ligadura é justamente o que o EasyOCR não sabe escrever.
    Deixá-lo ser sobrescrito trocaria `♗x` por `B`.
    """
    saida = ldl.distribuir(["a", "♗x", "c"], "aBc")
    assert saida[1] == "♗x", "a figurina foi trocada por letra"
    assert saida[0] == "a" and saida[2] == "c"


# ----------------------------------------------------------------------
# A confiança sai da concordância
# ----------------------------------------------------------------------

def test_concordar_corrobora():
    assert ldl.confianca(True, 0.6, 0.9) == pytest.approx(0.9)


def test_divergir_manda_para_a_revisao():
    """
    A linha venceu, mas a leitura do glifo dizia outra coisa. Vale a menor —
    o box tem que aparecer na fila de revisão, não sumir dela.
    """
    assert ldl.confianca(False, 0.95, 0.30) == pytest.approx(0.30)


# ----------------------------------------------------------------------
# em_bloco — o que não é lido de uma vez
# ----------------------------------------------------------------------

def test_linha_normal_e_lida_em_bloco():
    assert ldl.em_bloco(_boxes("abc")) is True


def test_linha_de_um_box_so_nao_e_linha():
    assert ldl.em_bloco(_boxes("a")) is False


def test_box_girado_tira_a_linha_do_bloco():
    """Girada, a faixa da linha não é um retângulo em pé na página (F8.1)."""
    bs = _boxes("abc")
    bs[1].angulo = 90
    assert ldl.em_bloco(bs) is False


def test_box_em_negativo_tira_a_linha_do_bloco():
    bs = _boxes("abc")
    bs[1].negativo = True
    assert ldl.em_bloco(bs) is False


def test_figurina_tira_a_linha_do_bloco():
    bs = _boxes("ab") + [BoxEntry("♗", 30, 10, 38, 30)]
    assert ldl.em_bloco(bs, ldl.GLIFOS_QUE_DESLOCAM) is False


def test_sem_lista_nao_filtra():
    """`None` é "sem filtro", e continua sendo — é o padrão do módulo."""
    bs = _boxes("ab") + [BoxEntry("♗", 30, 10, 38, 30)]
    assert ldl.em_bloco(bs, deslocam=None) is True


# ----------------------------------------------------------------------
# F36 — o filtro que ninguém alimentava, e o que ele deve pegar
# ----------------------------------------------------------------------

def test_o_box_vazio_nao_engana_mais_o_filtro():
    """
    O furo da F36, no menor caso que o mostra.

    Numa ação «Detectar e Preencher» os boxes acabaram de ser gerados e
    `b.char` está vazio em todos. Olhando o box, o filtro não vê figurina
    nenhuma e manda a linha para o bloco; olhando a **leitura da âncora**, vê.
    """
    bs = _boxes("   ")                      # três boxes sem caractere
    for b in bs:
        b.char = ""

    assert ldl.em_bloco(bs, ldl.GLIFOS_QUE_DESLOCAM) is True
    assert ldl.em_bloco(bs, ldl.GLIFOS_QUE_DESLOCAM,
                        ["♗", "e", "4"]) is False


def test_ligadura_na_ancora_tira_a_linha_do_bloco():
    """
    A cadeia neural emite `fi` num box só (SPEC §5.2), e a linha o lê como
    dois. A ligadura entra pelo **comprimento**, e não pela lista: `fi` é feito
    de duas letras que estão no alfabeto do EasyOCR, e mesmo assim desloca.
    """
    bs = _boxes("abc")
    assert ldl.em_bloco(bs, ldl.GLIFOS_QUE_DESLOCAM, ["a", "fi", "c"]) is False


def test_simbolo_de_avaliacao_nao_tira_a_linha_do_bloco():
    """
    O que a F36 mediu e corrigiu: `±` está **fora** do alfabeto do
    `english_g2` e mesmo assim não desloca nada — sai como um caractere errado
    numa casa certa, que é o erro comum. Filtrar pelo alfabeto tirava metade das
    linhas do modo bloco por causa disto, e custava um caractere.
    """
    assert "±" not in ldl.ALFABETO_EASYOCR
    bs = _boxes("abc")
    assert ldl.em_bloco(bs, ldl.GLIFOS_QUE_DESLOCAM,
                        ["a", "±", "c"]) is True


def test_o_alfabeto_e_o_do_easyocr():
    """
    A cópia literal contra a biblioteca. `ALFABETO_EASYOCR` não está em
    produção — é o filtro largo que a F36 mediu e devolveu —, e fica pelo mesmo
    motivo que `margem_de_confianca` ficou na F24: sem ele o instrumento não
    reproduz a tabela que decidiu. Uma cópia sem conferência envelhece calada.
    """
    config = pytest.importorskip("easyocr.config")
    do_modelo = config.recognition_models["gen2"]["english_g2"]["characters"]
    assert set(ldl.ALFABETO_EASYOCR) == set(do_modelo)


def test_a_linha_com_figurina_nao_e_lida_em_bloco():
    """De ponta a ponta: a faixa não chega a ser lida, e a âncora sobrevive."""
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("xyz")
    tabela = {"x": ("♗", 0.9), "y": ("e", 0.9), "z": ("4", 0.9)}

    chamadas = []

    def ler_faixa(tira):
        chamadas.append(tira)
        return "Be4", 0.95

    saida = ldl.ler_pagina(pagina, [linha], ler_faixa=ler_faixa,
                           ler_caractere=_ler_char_falso(tabela),
                           deslocam=ldl.GLIFOS_QUE_DESLOCAM)

    assert chamadas == [], "leu a faixa de uma linha que tem figurina"
    assert [ch for _b, ch, _c, _f in saida] == ["♗", "e", "4"]


def test_sem_o_filtro_a_mesma_linha_perde_a_figurina():
    """O outro lado do teste acima: é isto que acontecia até a F36."""
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("xyz")
    tabela = {"x": ("♗", 0.9), "y": ("e", 0.9), "z": ("4", 0.9)}

    saida = ldl.ler_pagina(pagina, [linha], ler_faixa=lambda t: ("Be4", 0.95),
                           ler_caractere=_ler_char_falso(tabela))

    assert [ch for _b, ch, _c, _f in saida] == ["B", "e", "4"]


def test_nenhum_caminho_de_producao_filtra_a_linha():
    """
    **Nada em produção passa `deslocam`, e é de propósito** — mesma forma que a
    F24 deu ao `voto` e à `margem_de_confianca`.

    O filtro foi alimentado, medido nos dois caminhos e desligado: no neural ele
    quebra 6 caracteres para consertar 1. O teste existe porque a leitura óbvia
    do código é a oposta — o parâmetro está ali, a lista está ali, e ligá-los
    parece um esquecimento. Conferido na fonte porque instanciar a janela traria
    o Tk junto.
    """
    import inspect

    from core.searchable_pdf import _ler_boxes
    from ui.main_window import MainWindow

    acao = inspect.getsource(MainWindow._preencher_por_linha)
    assert "deslocam=" not in acao, "a ação voltou a filtrar a linha (ver F36)"

    pdf = inspect.getsource(_ler_boxes)
    assert "GLIFOS_QUE_DESLOCAM" not in pdf, "o PDF voltou a filtrar (ver F36)"


# ----------------------------------------------------------------------
# faixa_da_linha
# ----------------------------------------------------------------------

def test_a_faixa_cobre_a_linha_com_margem():
    pagina = np.full((60, 60), 128, dtype=np.uint8)
    tira = ldl.faixa_da_linha(pagina, _boxes("abc", y1=10, y2=30))
    assert tira.shape[0] == 20 + 2 * ldl.MARGEM
    assert tira[0, 0] == 255, "a margem tem que ser branca"


def test_a_faixa_nao_sai_da_pagina():
    pagina = np.full((20, 20), 128, dtype=np.uint8)
    bs = [BoxEntry("a", 0, 0, 40, 40)]
    assert ldl.faixa_da_linha(pagina, bs) is not None


def test_faixa_de_linha_vazia():
    assert ldl.faixa_da_linha(np.zeros((10, 10), np.uint8), []) is None


# ----------------------------------------------------------------------
# ler_pagina
# ----------------------------------------------------------------------

def _ler_char_falso(tabela, fonte="easyocr"):
    """`ler_caractere` da âncora: (char, confiança, fonte) por box."""
    def ler(b):
        ch, cf = tabela.get(b.char, ("?", 0.4))
        return ch, cf, fonte
    return ler


def test_a_linha_corrige_o_caractere():
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("Foreword"[:4])   # F o r e
    tabela = {"F": ("F", 0.9), "o": ("0", 0.5), "r": ("r", 0.8), "e": ("e", 0.7)}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("Fore", 0.88),
                           ler_caractere=_ler_char_falso(tabela))

    assert [ch for _b, ch, _c, _f in saida] == list("Fore")
    # `easyocr_linha` marca **só o box que a linha trocou**. Quem ela apenas
    # confirmou fica com a fonte de quem leu — dizer o contrário esconderia da
    # revisão que foi a rede (ou o EasyOCR) que respondeu aquele box.
    fontes = [f for *_r, f in saida]
    assert fontes == ["easyocr", "easyocr_linha", "easyocr", "easyocr"]


def test_o_box_que_a_linha_mudou_fica_com_a_confianca_menor():
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("ab")
    tabela = {"a": ("a", 0.9), "b": ("6", 0.3)}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("ab", 0.95),
                           ler_caractere=_ler_char_falso(tabela))

    confs = {ch: c for _b, ch, c, _f in saida}
    assert confs["a"] == pytest.approx(0.95), "concordaram: vale a maior"
    assert confs["b"] == pytest.approx(0.30), "divergiram: vale a menor"


def test_sem_leitura_de_linha_cai_no_caractere():
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("ab")
    tabela = {"a": ("a", 0.9), "b": ("b", 0.8)}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("", 0.0),
                           ler_caractere=_ler_char_falso(tabela))

    assert [f for *_r, f in saida] == ["easyocr", "easyocr"]
    assert [c for _b, _ch, c, _f in saida] == [0.9, 0.8]


def test_o_espaco_da_linha_nao_vira_box():
    """
    O `.box` não tem box de espaço: a linha lê "of the" onde há 5 boxes. Sem
    tirar o espaço, todo ele desloca o alinhamento.
    """
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("ofthe")
    tabela = {c: (c, 0.8) for c in "ofthe"}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("of the", 0.9),
                           ler_caractere=_ler_char_falso(tabela))

    assert "".join(ch for _b, ch, _c, _f in saida) == "ofthe"


def test_cancelar_devolve_o_que_ja_foi_lido():
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linhas = [_boxes("ab"), _boxes("cd"), _boxes("ef")]
    tabela = {c: (c, 0.8) for c in "abcdef"}
    feitas = []

    def cancelado():
        return len(feitas) >= 1

    def ler_faixa(t):
        feitas.append(1)
        return ("xx", 0.9)

    saida = ldl.ler_pagina(pagina, linhas, ler_faixa=ler_faixa,
                           ler_caractere=_ler_char_falso(tabela),
                           cancelado=cancelado)
    assert len(saida) == 2, "parou na primeira linha, e devolveu o que fez"


def test_o_progresso_conta_linhas():
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linhas = [_boxes("ab"), _boxes("cd")]
    tabela = {c: (c, 0.8) for c in "abcd"}
    passos = []

    ldl.ler_pagina(pagina, linhas, ler_faixa=lambda t: ("ab", 0.9),
                   ler_caractere=_ler_char_falso(tabela),
                   progresso=lambda i, n: passos.append((i, n)))
    assert passos == [(1, 2), (2, 2)]


def test_todos_os_boxes_saem_na_ordem_em_que_entraram():
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linhas = [_boxes("ab"), _boxes("cd")]
    tabela = {c: (c, 0.8) for c in "abcd"}

    saida = ldl.ler_pagina(pagina, linhas, ler_faixa=lambda t: ("", 0.0),
                           ler_caractere=_ler_char_falso(tabela))
    assert [b for b, *_r in saida] == linhas[0] + linhas[1]


# ----------------------------------------------------------------------
# linhas_da_pagina
# ----------------------------------------------------------------------

def test_agrupa_em_linhas():
    de_cima = _boxes("abc", y1=10, y2=30)
    de_baixo = _boxes("de", y1=60, y2=80)
    linhas = ldl.linhas_da_pagina(de_cima + de_baixo)
    assert [len(uma) for uma in linhas] == [3, 2]


def test_sem_boxes():
    assert ldl.linhas_da_pagina([]) == []


# ----------------------------------------------------------------------
# A ação da UI, de ponta a ponta (com o EasyOCR falso)
# ----------------------------------------------------------------------

def test_a_acao_da_ui_preenche_os_boxes(monkeypatch):
    """
    Fecha o caminho que os testes de unidade não tocam: o menu chama
    `auto_fill_characters_linha`, que monta as faixas, roda na thread e escreve
    nos boxes.
    """
    from conftest import raiz_tk
    from tkinter import messagebox
    from PIL import Image

    from ui.main_window import MainWindow

    info, erro = messagebox.showinfo, messagebox.showerror
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None
    raiz = raiz_tk()
    try:
        w = MainWindow(raiz)
        w.image = Image.new("L", (200, 100), color=255)
        w.boxes = _boxes("F0re", y1=10, y2=30)
        for b in w.boxes:
            b.char = ""

        monkeypatch.setattr(w.ocr_service, "easyocr_linha_conf",
                            lambda faixa, *a, **k: ("Fore", 0.9))
        monkeypatch.setattr(w.ocr_service, "easyocr_ocr_conf",
                            lambda crop, *a, **k: ("0", 0.4))

        w.auto_fill_characters_linha()
        # A ação roda fora da thread da UI; o resultado só é aplicado no
        # `update` seguinte.
        for _ in range(200):
            raiz.update()
            if w.boxes[0].char:
                break

        assert "".join(b.char for b in w.boxes) == "Fore", \
            "a linha não chegou aos boxes"
        assert {b.source for b in w.boxes} == {"easyocr_linha"}
    finally:
        messagebox.showinfo, messagebox.showerror = info, erro
        try:
            w.task.shutdown()
            raiz.destroy()
        except Exception:
            pass


# ----------------------------------------------------------------------
# F20 — a trava, para a linha não estragar uma âncora forte
# ----------------------------------------------------------------------

def test_sem_trava_a_linha_manda_sempre():
    """É o certo quando a âncora é o EasyOCR sozinho: 72,9% para 89,5%."""
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("ab")
    tabela = {"a": ("a", 0.99), "b": ("6", 0.99)}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("ab", 0.5),
                           ler_caractere=_ler_char_falso(tabela))
    assert "".join(ch for _b, ch, _c, _f in saida) == "ab"


def test_com_trava_a_linha_nao_encosta_no_que_a_cadeia_sabe():
    """
    A F18: a cadeia acerta 97,6% e a linha 89,5%. Deixá-la mandar em box que a
    rede respondeu com confiança regride 7,3 pontos.
    """
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("ab")
    tabela = {"a": ("a", 0.99), "b": ("6", 0.99)}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("ab", 0.5),
                           ler_caractere=_ler_char_falso(tabela, "neural"),
                           conf_maxima_para_trocar=0.70)
    assert "".join(ch for _b, ch, _c, _f in saida) == "a6", \
        "a linha sobrescreveu o que a rede sabia"
    assert [f for *_r, f in saida] == ["neural", "neural"]


def test_com_trava_a_linha_manda_onde_a_cadeia_nao_soube():
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("ab")
    tabela = {"a": ("a", 0.99), "b": ("6", 0.30)}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("ab", 0.5),
                           ler_caractere=_ler_char_falso(tabela, "neural"),
                           conf_maxima_para_trocar=0.70)
    assert "".join(ch for _b, ch, _c, _f in saida) == "ab"
    assert [f for *_r, f in saida] == ["neural", "easyocr_linha"], \
        "o box trocado tem que dizer que foi a linha"


def test_a_fonte_da_ancora_sobrevive_quando_a_linha_so_confirma():
    """
    O box que a rede acertou continua dizendo `neural`. Que a linha tenha
    corroborado está na confiança, que sobe — não na fonte.
    """
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("ab")
    tabela = {"a": ("a", 0.40), "b": ("b", 0.40)}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("ab", 0.95),
                           ler_caractere=_ler_char_falso(tabela, "neural"),
                           conf_maxima_para_trocar=0.70)
    assert [f for *_r, f in saida] == ["neural", "neural"]
    assert [c for _b, _ch, c, _f in saida] == [0.95, 0.95], \
        "concordaram: a confiança tinha que subir"


def test_a_linha_preenche_o_box_que_a_ancora_deixou_vazio():
    """
    O caminho híbrido zera o box cuja fonte não é `learner` nem `easyocr`, e a
    confiança dele fica em 0,0 — abaixo de qualquer trava. É exatamente onde a
    linha deve entrar.
    """
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("abc")
    tabela = {"a": ("a", 0.99), "b": ("", 0.0), "c": ("c", 0.99)}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("abc", 0.8),
                           ler_caractere=_ler_char_falso(tabela, "learner"),
                           conf_maxima_para_trocar=0.85)

    assert "".join(ch for _b, ch, _c, _f in saida) == "abc"
    assert [f for *_r, f in saida] == ["learner", "easyocr_linha", "learner"]


def test_o_box_vazio_que_a_linha_tambem_nao_le_continua_vazio():
    pagina = np.full((60, 80), 200, dtype=np.uint8)
    linha = _boxes("ab")
    tabela = {"a": ("a", 0.99), "b": ("", 0.0)}

    saida = ldl.ler_pagina(pagina, [linha],
                           ler_faixa=lambda t: ("", 0.0),
                           ler_caractere=_ler_char_falso(tabela, "learner"),
                           conf_maxima_para_trocar=0.85)
    assert [(ch, f) for _b, ch, _c, f in saida] == [("a", "learner"), ("", "vazio")]
