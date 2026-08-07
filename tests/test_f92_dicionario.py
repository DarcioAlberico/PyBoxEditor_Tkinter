"""
F9.2 — o dicionário do livro, alimentado pelas correções do usuário.

O risco desta fase é de uma direção só, e é o oposto do da F9.1: lá, sinalizar
demais cansa o revisor; aqui, **aprender demais cala o alarme**. Uma palavra que
entra errada na lista some da triagem para sempre, e some em silêncio — não há
tela que mostre "esta palavra deixou de acender".

Por isso metade destes testes é sobre o que **não** entra: palavra que o usuário
não tocou, palavra com box vazio no meio, palavra com dígito, notação, e
qualquer coisa quando não há lista geral com que comparar.

Rodar sem pytest:      python tests/test_f92_dicionario.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import lexico
from core.box_model import BoxEntry


ALTURA, LARGURA = 20, 12


def _palavra(texto, x=0, y=0, source="", indice_manual=None):
    """
    Uma palavra como a página a entrega: um box por caractere, em linha.

    `indice_manual` marca **um** box como digitado à mão, que é o caso real —
    o revisor corrige a letra errada, não a palavra inteira.
    """
    boxes = []
    for i, c in enumerate(texto):
        origem = source
        if indice_manual is not None and i == indice_manual:
            origem = "manual"
        boxes.append(BoxEntry(c, x + i * LARGURA, y,
                              x + i * LARGURA + LARGURA - 2, y + ALTURA,
                              confidence=1.0, source=origem))
    return boxes


def _pagina(*palavras):
    """Palavras separadas por um vão grande, todas na mesma linha."""
    boxes, x = [], 0
    for p in palavras:
        boxes.extend(_palavra(p[0], x=x, indice_manual=p[1]))
        x += (len(p[0]) + 3) * LARGURA
    return boxes


@pytest.fixture
def lex():
    """Léxico com uma lista geral pequena — o suficiente para haver contraste."""
    return lexico.Lexico(palavras={"the", "with", "black", "white", "play"})


# ----------------------------------------------------------------------
# O que entra
# ----------------------------------------------------------------------

def test_palavra_corrigida_a_mao_entra(lex):
    boxes = _pagina(("Nimzowitsch", 3))
    assert lexico.palavras_confirmadas(boxes, lex) == ["Nimzowitsch"]


def test_basta_um_box_digitado_na_palavra(lex):
    """
    O revisor corrige a letra errada, não a palavra inteira. Exigir que todos
    os boxes fossem manuais não recolheria quase nada.
    """
    for i in range(5):
        assert lexico.palavras_confirmadas(_pagina(("Benko", i)), lex) == ["Benko"]


def test_a_mesma_palavra_nao_entra_duas_vezes(lex):
    boxes = _pagina(("Benko", 0), ("Benko", 0))
    assert lexico.palavras_confirmadas(boxes, lex) == ["Benko"]


def test_palavra_que_a_lista_ja_tem_nao_entra(lex):
    assert lexico.palavras_confirmadas(_pagina(("black", 0)), lex) == []


def test_aprender_grava_e_o_lexico_passa_a_conhecer(tmp_path, lex):
    caminho = str(tmp_path / "livro.lexico.txt")
    novas = lexico.aprender_da_pagina(_pagina(("Benko", 0)), lex, caminho)

    assert novas == ["Benko"]
    assert lex.conhece("benko")
    assert lex.procedencia("Benko") == "usuario"
    assert open(caminho, encoding="utf-8").read().split() == ["benko"]


def test_aprender_de_novo_nao_repete(tmp_path, lex):
    caminho = str(tmp_path / "livro.lexico.txt")
    boxes = _pagina(("Benko", 0))
    lexico.aprender_da_pagina(boxes, lex, caminho)
    assert lexico.aprender_da_pagina(boxes, lex, caminho) == []


# ----------------------------------------------------------------------
# O que NÃO entra — a metade que protege o alarme
# ----------------------------------------------------------------------

def test_palavra_que_o_usuario_nao_tocou_nao_entra(lex):
    """
    Silêncio não é confirmação, a regra da F8.3.

    É o teste central da fase: sem ele, aprender a página inteira ensinaria o
    dicionário a calar justamente os erros que ele existe para apontar.
    """
    boxes = _pagina(("Kdinovsb", None))
    assert lexico.palavras_confirmadas(boxes, lex) == []


def test_palavra_lida_pelo_modelo_com_confianca_alta_tambem_nao_entra(lex):
    """Confiança não é confirmação — a F1.9 mediu que 1,000 é a mediana do erro."""
    boxes = _palavra("Kdinovsb", source="neural")
    for b in boxes:
        b.confidence = 1.0
    assert lexico.palavras_confirmadas(boxes, lex) == []


def test_palavra_com_box_vazio_nao_entra(lex):
    """Palavra com buraco é fragmento: `Kalin` calaria `Kalin` para sempre."""
    boxes = _palavra("Kalinovsky", indice_manual=0)
    boxes[5].char = ""
    assert lexico.palavras_confirmadas(boxes, lex) == []


def test_box_vazio_fora_da_palavra_nao_atrapalha(lex):
    """
    A regra do buraco é geométrica, então precisa ser cobrada nos dois sentidos:
    um box vazio na mesma linha, mas noutra palavra, não pode barrar o
    aprendizado — senão uma página em revisão nunca aprenderia nada.
    """
    boxes = _pagina(("Benko", 0))
    largura_da_palavra = 5 * LARGURA
    boxes.append(BoxEntry("", largura_da_palavra + 60, 0,
                          largura_da_palavra + 70, ALTURA))

    assert lexico.palavras_confirmadas(boxes, lex) == ["Benko"]


def test_palavra_com_digito_no_meio_nao_entra(lex):
    """`p1ay` é o caso canônico da fase; blindá-lo seria o oposto do que a lista faz."""
    assert lexico.palavras_confirmadas(_pagina(("p1ay", 1)), lex) == []


def test_notacao_nao_entra(lex):
    """
    Contrato 1 da SPEC §5.8: o léxico só vê pedaço tipado `outro`.

    Um lance digitado à mão é o caso mais provável de tudo — é o que o revisor
    mais corrige — e ele não pode virar palavra de dicionário.
    """
    assert lexico.palavras_confirmadas(_pagina(("Nf3", 0)), lex) == []
    assert lexico.palavras_confirmadas(_pagina(("Bxf6", 1)), lex) == []


def test_palavra_de_uma_letra_nao_entra(lex):
    assert lexico.palavras_confirmadas(_pagina(("a", 0)), lex) == []


def test_sem_lista_geral_nao_recolhe_nada():
    """
    Sem com que comparar, `the` e `with` também seriam palavras ausentes — e o
    vocabulário do livro nasceria cheio de idioma.
    """
    vazio = lexico.Lexico()
    assert lexico.palavras_confirmadas(_pagina(("Benko", 0)), vazio) == []


# ----------------------------------------------------------------------
# `sinaliza`: a lista do usuário sozinha não acusa ninguém
# ----------------------------------------------------------------------

def test_lista_do_usuario_sozinha_nao_sinaliza():
    """
    O caso que a F9.2 torna alcançável: um livro com `.lexico.txt` ao lado e sem
    `assets/lexico/` instalado. Com `vazio` como critério, a página inteira
    acenderia — centenas de palavras contra dezenas na lista.
    """
    so_usuario = lexico.Lexico(do_usuario={"benko"})

    assert not so_usuario.vazio            # tem conteúdo
    assert not so_usuario.sinaliza         # mas não serve para acusar
    assert lexico.suspeitas_da_pagina(_pagina(("the", None)), so_usuario) == []


def test_com_lista_geral_sinaliza(lex):
    suspeitas = lexico.suspeitas_da_pagina(_pagina(("Benko", None)), lex)
    assert [s.palavra for s in suspeitas] == ["Benko"]


def test_palavra_aprendida_deixa_de_acender(tmp_path, lex):
    """O ciclo inteiro: acende, o usuário corrige, aprende, para de acender."""
    boxes = _pagina(("Benko", 0))
    assert [s.palavra for s in lexico.suspeitas_da_pagina(boxes, lex)] == ["Benko"]

    lexico.aprender_da_pagina(boxes, lex, str(tmp_path / "l.txt"))
    assert lexico.suspeitas_da_pagina(boxes, lex) == []


# ----------------------------------------------------------------------
# Onde o arquivo mora
# ----------------------------------------------------------------------

def test_caminho_ao_lado_do_pdf():
    assert (lexico.caminho_do_usuario(os.path.join("livros", "kasparov.pdf"), True)
            == os.path.join("livros", "kasparov.lexico.txt"))


def test_caminho_de_imagem_solta_e_da_pasta():
    """
    Um livro digitalizado é uma pasta de JPEGs. Uma lista por página não seria
    dicionário de livro nenhum.
    """
    a = lexico.caminho_do_usuario(os.path.join("scans", "pagina-0012.jpg"), False)
    b = lexico.caminho_do_usuario(os.path.join("scans", "pagina-0099.jpg"), False)
    assert a == b == os.path.join("scans", "lexico.txt")


def test_sem_documento_nao_ha_caminho():
    assert lexico.caminho_do_usuario(None) is None
    assert lexico.caminho_do_usuario("") is None


def test_gravar_e_ler_de_volta(tmp_path):
    caminho = str(tmp_path / "l.txt")
    lexico.salvar_do_usuario(caminho, ["Benko", "yusupov", "  ", "Benko"])

    lido = lexico.carregar(caminho_usuario=caminho)
    assert lido.do_usuario == {"benko", "yusupov"}


def test_o_arquivo_sai_ordenado_e_editavel(tmp_path):
    """
    Texto puro, uma por linha, em ordem: é assim que o usuário tira à mão a
    palavra que entrou errada, e sem isso não haveria como tirar.
    """
    caminho = str(tmp_path / "l.txt")
    lexico.salvar_do_usuario(caminho, ["zugzwang", "Benko", "Najdorf"])
    assert open(caminho, encoding="utf-8").read() == "benko\nnajdorf\nzugzwang\n"


def test_gravar_sobre_lista_editada_a_mao_preserva_a_edicao(tmp_path, lex):
    """
    O arquivo é a verdade entre uma página e outra: quem o edita fora do
    programa não pode ver a edição desfeita na próxima palavra aprendida.
    """
    caminho = str(tmp_path / "l.txt")
    lexico.salvar_do_usuario(caminho, ["errada", "benko"])

    # o usuário abre o arquivo e apaga a linha errada
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("benko\n")

    lex2 = lexico.carregar(caminho_usuario=caminho)
    lex2.palavras = set(lex.palavras)
    lexico.aprender_da_pagina(_pagina(("Najdorf", 0)), lex2, caminho)

    assert open(caminho, encoding="utf-8").read().split() == ["benko", "najdorf"]


# ----------------------------------------------------------------------
# A sessão: a lista é do livro aberto, e não do processo
# ----------------------------------------------------------------------

def _janela():
    """MainWindow com os diálogos neutralizados, ou None sem display."""
    import tkinter as tk
    from tkinter import messagebox
    from conftest import raiz_tk

    raiz = raiz_tk()
    if raiz is None:
        return None, None, None
    originais = (messagebox.showinfo, messagebox.showerror, messagebox.askyesno)
    messagebox.showinfo = lambda t, m, **k: None
    messagebox.showerror = lambda t, m, **k: None
    messagebox.askyesno = lambda t, m, **k: True

    from ui.main_window import MainWindow
    return MainWindow(raiz), raiz, originais


def _fechar(raiz, originais):
    import tkinter as tk
    from tkinter import messagebox

    (messagebox.showinfo, messagebox.showerror, messagebox.askyesno) = originais
    try:
        raiz.destroy()
    except tk.TclError:
        pass


def test_o_caminho_segue_o_documento_aberto(tmp_path):
    """
    Trocar de livro tem de trocar de lista. Guardar o léxico por processo daria
    ao Kasparov o vocabulário do Yusupov — o contrário do motivo da fase.
    """
    from core.services.document_service import DocumentSession

    win, raiz, originais = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        assert win._caminho_do_lexico() is None      # nada aberto

        win.session = DocumentSession(str(tmp_path / "kasparov.pdf"),
                                      num_pages=2, is_pdf=True)
        assert win._caminho_do_lexico() == str(tmp_path / "kasparov.lexico.txt")

        win._lexico = lexico.Lexico(palavras={"the"}, do_usuario={"benko"})
        win.session = DocumentSession(str(tmp_path / "yusupov.pdf"),
                                      num_pages=2, is_pdf=True)
        win._esquecer_lexico()

        assert win._lexico is None
        assert win._caminho_do_lexico() == str(tmp_path / "yusupov.lexico.txt")
    finally:
        _fechar(raiz, originais)


def test_aprender_pela_janela_grava_e_para_de_acender(tmp_path):
    """O ciclo da fase pelo caminho que a UI usa."""
    from core.services.document_service import DocumentSession

    win, raiz, originais = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        win.session = DocumentSession(str(tmp_path / "livro.pdf"),
                                      num_pages=1, is_pdf=True)
        win._esquecer_lexico()
        win._lexico = lexico.Lexico(palavras={"the", "with"})
        win.boxes = _pagina(("Benko", 0))

        assert [s.palavra for s in win.suspeitas()] == ["Benko"]

        assert win.aprender_palavras_da_pagina() == ["Benko"]
        assert win.suspeitas() == []
        assert os.path.exists(str(tmp_path / "livro.lexico.txt"))
    finally:
        _fechar(raiz, originais)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
