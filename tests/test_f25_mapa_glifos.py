"""
Testes da F2.5 — correção do mapeamento de caracteres do PDF.

O defeito que esta fase ataca não é de OCR. Nos livros do projeto a notação
está **certa na tela** — "1...♖xf3! 2.♕xd5" — e sai `l2Jd7` ao copiar: fonte
Identity-H com o `ToUnicode` errado, onde o desenho está bom e a tabela que diz
qual caractere ele representa não está.

Daí a propriedade central que estes testes fixam, e que separa esta operação de
tudo o mais nesta pasta: **a página não muda um pixel**. Se mudasse, a correção
teria virado uma reescrita do documento, e o ganho de copiar certo teria vindo
com um custo que ninguém pediu.

Rodar sem pytest:      python tests/test_f25_mapa_glifos.py
"""

import collections
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

import fitz
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox

from core import mapa_glifos
from core.chess_pdf_processor import resolve_chess_font
from core.mapa_glifos import (Descoberta, Ocorrencia, chave_da_fonte,
                              corrigir_mapeamento, escrever_cmap, ler_cmap,
                              mesmo_arquivo)


def _saida(nome="saida.pdf"):
    return os.path.join(tempfile.mkdtemp(), nome)


# ----------------------------------------------------------------------
# A tabela ToUnicode
# ----------------------------------------------------------------------

def test_ida_e_volta_do_cmap():
    mapa = {0x18: "♘", 0x1A: "♖", 0x41: "A", 0x2665: "♥", 0x30: "fi"}
    assert ler_cmap(escrever_cmap(mapa)) == mapa


def test_o_cmap_escrito_respeita_o_limite_de_100_por_bloco():
    """Mais de 100 entradas num único bfchar é fora do padrão."""
    texto = escrever_cmap({i: chr(0x41 + i % 26) for i in range(250)})
    assert texto.count("beginbfchar") == 3
    for bloco in texto.split("beginbfchar")[1:]:
        assert bloco.count("<") - bloco.count("<<") <= 200   # 100 pares


def test_ler_cmap_entende_bfrange():
    """
    Faixa é lida mesmo os livros do projeto só usarem `bfchar`.

    A tabela é **reescrita inteira** a partir do que se leu; uma faixa que
    passasse batida sumiria do PDF de saída, e a correção apagaria mapeamentos
    certos para consertar os errados.
    """
    texto = """
    begincmap
    1 beginbfrange
    <0010> <0013> <0041>
    endbfrange
    1 beginbfchar
    <0020> <2656>
    endbfchar
    endcmap
    """
    mapa = ler_cmap(texto)
    assert mapa[0x10] == "A" and mapa[0x11] == "B" and mapa[0x13] == "D"
    assert mapa[0x20] == "♖"


def test_a_chave_da_fonte_casa_os_dois_nomes_do_pymupdf():
    """
    `get_texttrace` diz `SegoeUISymbol`, `get_fonts` diz `Segoe UI Symbol
    Regular`, e é a mesma fonte. Sem casar as duas, a descoberta acha os glifos
    e o `aplicar` não acha a tabela de nenhum deles.
    """
    assert chave_da_fonte("SegoeUISymbol") == \
           chave_da_fonte("Segoe UI Symbol Regular")
    assert chave_da_fonte("Fd350139") == chave_da_fonte("Fd350139-Identity-H")
    assert chave_da_fonte("ABCDEF+Fd350139-Identity-H") == chave_da_fonte("Fd350139")
    assert chave_da_fonte("Arial") != chave_da_fonte("Helvetica")


def test_o_cmap_reescrito_nao_perde_o_que_ja_estava_certo():
    original = escrever_cmap({i: chr(0x41 + i) for i in range(20)})
    mapa = ler_cmap(original)
    mapa[5] = "♕"
    novo = ler_cmap(escrever_cmap(mapa))

    assert novo[5] == "♕"
    assert all(novo[i] == chr(0x41 + i) for i in range(20) if i != 5)


# ----------------------------------------------------------------------
# Onde uma figurina pode estar
# ----------------------------------------------------------------------

def test_posicao_de_figurina():
    """`♗e6` sim; o `o` de "Goldenov" não."""
    assert Ocorrencia(0, (0, 0, 1, 1), antes=".", depois="e").parece_notacao
    assert Ocorrencia(0, (0, 0, 1, 1), antes=" ", depois="x").parece_notacao
    assert Ocorrencia(0, (0, 0, 1, 1), antes="", depois="8").parece_notacao
    assert not Ocorrencia(0, (0, 0, 1, 1), antes="G", depois="l").parece_notacao
    assert not Ocorrencia(0, (0, 0, 1, 1), antes=".", depois="").parece_notacao
    assert not Ocorrencia(0, (0, 0, 1, 1), antes=".", depois="z").parece_notacao


def test_recorte_claro_sobre_escuro_e_reconhecido():
    """
    Tarja preta: `B.Goldenov` saiu `B.G♔lden♔v`, com 100% de concordância.

    O modelo só viu preto-sobre-branco; entregar o inverso devolve resposta
    confiante e errada, e nem confiança nem votação separam isso.
    """
    claro_sobre_escuro = np.zeros((20, 20), dtype=np.uint8)
    claro_sobre_escuro[6:14, 6:14] = 255
    escuro_sobre_claro = np.full((20, 20), 255, dtype=np.uint8)
    escuro_sobre_claro[6:14, 6:14] = 0

    assert mapa_glifos.e_negativo(claro_sobre_escuro)
    assert not mapa_glifos.e_negativo(escuro_sobre_claro)


def test_a_linha_e_remontada_pela_geometria():
    """
    O `get_texttrace` entrega um span por troca de fonte, e a figurina está
    numa fonte e o `e6` que a segue está noutra. Pela ordem da fila, o vizinho
    da direita é um caractere do outro lado da página.
    """
    # (fonte, glifo, texto, bbox, origem) — fora de ordem, como viriam de
    # spans distintos. A figurina tem caixa mais alta, e mesma linha de base.
    fila = [
        ("figurina", 1, "♗", (50, 97, 56, 110), (50, 108)),
        ("texto", 2, "e", (56, 100, 61, 110), (56, 108)),
        ("texto", 3, "6", (61, 100, 66, 110), (61, 108)),
        ("texto", 4, "Z", (300, 100, 305, 110), (300, 108)),   # outra coluna
        ("texto", 5, "K", (50, 200, 55, 210), (50, 208)),      # outra linha
    ]
    linhas = mapa_glifos._linhas_da_pagina(fila)

    assert len(linhas) == 2, "não separou as duas linhas"
    primeira = "".join(e[2] for e in linhas[0])
    assert primeira == "♗e6Z", primeira
    # ...mas a outra coluna não encosta na primeira
    assert mapa_glifos._colados(fila[0][3], fila[1][3])
    assert not mapa_glifos._colados(fila[2][3], fila[3][3])


def test_a_linha_nao_se_agrupa_pelo_centro_da_caixa():
    """
    Era: a caixa da figurina é mais alta que a de uma letra, o centro se
    desloca, e a tolerância que isso obriga a usar funde a linha de uma coluna
    com a da coluna vizinha, que tem entrelinha própria. Medido na página 17 do
    Yusupov, três linhas viravam uma só e a figurina acabava ao lado de um
    caractere que na página está a dez linhas dali.
    """
    # Duas colunas, mesma altura de letra, linhas de base 4 pontos afastadas —
    # perto o bastante para o centro fundir as duas, longe o bastante para a
    # linha de base separá-las.
    fila = [
        ("f", 1, "A", (50, 100, 55, 110), (50, 109)),
        ("f", 2, "B", (55, 100, 60, 110), (55, 109)),
        ("f", 3, "X", (300, 104, 305, 114), (300, 113)),
        ("f", 4, "Y", (305, 104, 310, 114), (305, 113)),
    ]
    linhas = mapa_glifos._linhas_da_pagina(fila)

    assert ["".join(e[2] for e in l) for l in linhas] == ["AB", "XY"], (
        "fundiu duas linhas de base distintas numa só")


# ----------------------------------------------------------------------
# PDF de apoio
# ----------------------------------------------------------------------

#: Uma fonte que existe neste sistema — `resolve_chess_font` já garante isso.
#: Precisa ser **embutida**: fonte base-14 não tem `ToUnicode` no PDF, e é
#: justamente essa tabela que estes testes quebram e conferem.
FONTE = resolve_chess_font()


def _pdf_com_tabela_quebrada(caminho, paginas=2, texto="{n}.Nf "):
    """
    PDF cujo glifo do 'N' diz, na tabela, ser `U+FFFD`.

    É o defeito real em miniatura: o desenho na página continua um 'N' — a
    página não muda —, e só a tabela mente. `Nf` passa a extrair como `?f`.

    **`"{n}.Nf "` e não `"{n}.Nf3 Nc6"`**, que seria a linha mais realista. O
    classificador destes testes responde a mesma peça para todo recorte — é o
    que mantém o modelo de verdade fora da suíte —, então quem separa um glifo
    do outro aqui é só o filtro de posição. Em `Nf3` o `f` **também** passa
    nesse filtro: com a tabela quebrada o vizinho da esquerda dele é `U+FFFD`,
    que não é letra, e o da direita é `3`. Num livro de verdade o modelo diz
    "isto é um f" e o caso morre ali; aqui, não haveria como distinguir, e o
    teste passaria a medir o fixture em vez do código.
    """
    doc = fitz.open()
    for _ in range(paginas):
        p = doc.new_page(width=300, height=200)
        p.insert_font(fontname="FX", fontfile=FONTE)
        for i in range(4):
            p.insert_text((40, 50 + i * 30), texto.format(n=i + 1),
                          fontsize=14, fontname="FX")
    doc.save(caminho)
    doc.close()

    return _quebrar_tabela(caminho)


def _quebrar_tabela(caminho, letra="N", valor=None):
    """Faz a tabela dizer `valor` no lugar de `letra`. Só a tabela muda."""
    valor = mapa_glifos.SEM_MAPA if valor is None else valor
    doc = fitz.open(caminho)
    try:
        for xref, _n, _t, _base, *_ in doc[0].get_fonts(full=True):
            chave = doc.xref_get_key(xref, "ToUnicode")
            if not chave or chave[0] != "xref":
                continue
            tu = int(chave[1].split()[0])
            mapa = ler_cmap(doc.xref_stream(tu).decode("latin-1"))
            for codigo, atual in list(mapa.items()):
                if atual == letra:
                    mapa[codigo] = valor
            doc.update_stream(tu, escrever_cmap(mapa).encode("latin-1"))
        doc.save(caminho, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    finally:
        doc.close()

    with fitz.open(caminho) as d:
        assert letra not in d[0].get_text(), "o fixture não quebrou a tabela"
    return caminho


def _pdf_com_notacao_em_tarja(caminho):
    """
    A notação escrita em branco sobre preto — a tarja de nome dos livros.

    Aqui a figurina está **em posição de figurina**, então quem tem de barrá-la
    é a leitura de polaridade, e não o filtro de posição.
    """
    doc = fitz.open()
    p = doc.new_page(width=300, height=200)
    p.insert_font(fontname="FX", fontfile=FONTE)
    for i in range(4):
        y = 50 + i * 30
        p.draw_rect(fitz.Rect(30, y - 13, 200, y + 5), color=(0, 0, 0),
                    fill=(0, 0, 0))
        p.insert_text((40, y), f"{i + 1}.Nf ", fontsize=14, fontname="FX",
                      color=(1, 1, 1))
    doc.save(caminho)
    doc.close()
    return _quebrar_tabela(caminho)


def _pdf_com_notacao_em_duas_fontes(caminho):
    """
    A figurina numa fonte, o `f` que a segue noutra, e o `f` escrito **antes**.

    É a forma do livro real, e a que quebra a busca de vizinho pela ordem da
    fila: o `get_texttrace` corta um span por troca de fonte e os entrega na
    ordem do fluxo de conteúdo, que aqui não é a da leitura.
    """
    medida = fitz.Font(fontfile=FONTE)
    doc = fitz.open()
    p = doc.new_page(width=300, height=200)
    p.insert_font(fontname="FX", fontfile=FONTE)

    inicios = []
    for i in range(4):
        inicios.append(40 + medida.text_length(f"{i + 1}.N", fontsize=14))
    # o que vem DEPOIS na página, escrito primeiro e noutra fonte
    for i, x in enumerate(inicios):
        p.insert_text((x, 50 + i * 30), "f ", fontsize=14)
    for i in range(4):
        p.insert_text((40, 50 + i * 30), f"{i + 1}.N", fontsize=14, fontname="FX")

    doc.save(caminho)
    doc.close()
    return _quebrar_tabela(caminho)


def _classificador(simbolo="♘", confianca=0.99):
    """Diz sempre a mesma coisa — o modelo de verdade não entra em teste."""
    return lambda corte: (simbolo, confianca)


# ----------------------------------------------------------------------
# A propriedade central
# ----------------------------------------------------------------------

def test_a_pagina_nao_muda_um_pixel():
    """
    O que separa esta operação de todas as outras desta pasta.

    Se a página mudasse, copiar certo teria custado uma reescrita do documento
    — e a alternativa que o usuário recusou, de apagar o texto e redesenhar,
    teria entrado pela porta dos fundos.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        corrigir_mapeamento(entrada, saida, classificar=_classificador())

        a, b = fitz.open(entrada), fitz.open(saida)
        try:
            for i in range(len(a)):
                assert a[i].get_pixmap(dpi=110).samples == \
                       b[i].get_pixmap(dpi=110).samples, f"a página {i} mudou"
        finally:
            a.close()
            b.close()


def test_o_texto_passa_a_extrair_certo():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        with fitz.open(entrada) as d:
            antes = d[0].get_text()
        assert "Nf" not in antes, "o PDF de teste não está com a tabela quebrada"

        rel = corrigir_mapeamento(entrada, saida, classificar=_classificador())

        assert rel.aceitas, f"nada foi corrigido: {rel.resumo()}"
        with fitz.open(saida) as d:
            depois = d[0].get_text()
        assert "♘f" in depois, repr(depois)
        # Um por linha, e nada mais: o `f`, o `.` e os dígitos continuam letras.
        assert depois.count("♘") == 4, f"trocou mais do que o 'N': {depois!r}"
        assert depois.count("f") == 4 and depois.count(".") == 4, repr(depois)


def test_o_original_nao_e_tocado():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        antes = open(entrada, "rb").read()

        corrigir_mapeamento(entrada, os.path.join(tmp, "out.pdf"),
                            classificar=_classificador())

        assert open(entrada, "rb").read() == antes, "a correção mexeu na entrada"


def test_gravar_por_cima_do_original_e_recusado():
    """
    O pedido era "salvo uma cópia para não perder o original".

    Sem esta guarda o PyMuPDF só reclama no fim do trabalho, com "save to
    original must be incremental" — uma mensagem que não diz o que fazer.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        try:
            corrigir_mapeamento(entrada, entrada, classificar=_classificador())
        except mapa_glifos.MapeamentoInvalido as e:
            assert "original" in str(e)
        else:
            raise AssertionError("aceitou gravar por cima do original")


def test_mesmo_arquivo_por_caminhos_diferentes():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "x.pdf")
        open(a, "wb").write(b"%PDF-1.4\n")
        assert mesmo_arquivo(a, os.path.join(tmp, ".", "x.pdf"))
        assert not mesmo_arquivo(a, os.path.join(tmp, "y.pdf"))


# ----------------------------------------------------------------------
# O que não é peça não é trocado
# ----------------------------------------------------------------------

def test_glifo_que_nao_e_peca_nao_entra_na_tabela():
    """
    `SIMBOLOS_ACEITOS` é o que impede a ferramenta de reescrever, com base num
    palpite de OCR, o mapeamento de uma letra qualquer.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        rel = corrigir_mapeamento(entrada, saida,
                                  classificar=_classificador("Z", 1.0))

        assert not rel.aceitas
        with fitz.open(entrada) as a, fitz.open(saida) as b:
            assert a[0].get_text() == b[0].get_text(), "mudou o texto assim mesmo"


def test_notacao_em_tarja_preta_nao_e_classificada():
    """
    Era: `B.Goldenov` saiu `B.G♔lden♔v` e `L.Shamkovich` saiu `L.Sham♖♔v♖ch`,
    com 100% de concordância nas duas.

    O modelo só viu preto-sobre-branco. Aqui a figurina está em posição de
    figurina, então o filtro de posição não a barra — quem barra é a leitura de
    polaridade do recorte, e o teste existe para não deixar as duas defesas se
    cobrirem uma à outra.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_notacao_em_tarja(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        rel = corrigir_mapeamento(entrada, saida, classificar=_classificador())

        assert not rel.aceitas, "classificou recorte branco sobre preto"
        assert any("nenhum recorte" in d.motivo for d in rel.descobertas) or \
               not rel.descobertas
        with fitz.open(entrada) as a, fitz.open(saida) as b:
            assert a[0].get_text() == b[0].get_text()


def test_a_figurina_acha_o_vizinho_que_esta_noutra_fonte():
    """
    Em `♗e6` a figurina vem de uma fonte e o `e6` de outra, e o
    `get_texttrace` os entrega em spans distantes. Procurando vizinho pela
    ordem da fila, 110 dos 125 glifos de peça de um trecho real ficavam sem
    vizinho à direita e o filtro de posição derrubava todos.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_notacao_em_duas_fontes(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        rel = corrigir_mapeamento(entrada, saida, classificar=_classificador())

        assert rel.aceitas, (
            f"não achou o vizinho de outra fonte: {rel.resumo()}")
        assert all(d.notacao == 1.0 for d in rel.aceitas), (
            f"achou o vizinho só em parte: {[d.notacao for d in rel.aceitas]}")
        # A ordem do `get_text` aqui é a do fluxo de conteúdo, e este fixture o
        # escreve fora da ordem de leitura de propósito — a asserção é sobre a
        # troca ter acontecido, não sobre como o texto sai agrupado.
        with fitz.open(saida) as d:
            assert d[0].get_text().count("♘") == 4


def test_mapeamento_de_varios_caracteres_nao_esconde_o_vizinho():
    """
    A tabela destes livros manda um glifo para uma **sequência** — `El` para a
    torre, `i.` para o bispo, `l2J` para o cavalo. O `get_texttrace` devolve um
    item por caractere: o primeiro com o glifo e a caixa de verdade, os demais
    com glifo -1 e largura zero.

    Esse fantasma de largura zero se instala entre a figurina e o `f` que a
    segue, e foi o que fez o filtro de posição achar que figurina nenhuma tinha
    vizinho à direita.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = os.path.join(tmp, "in.pdf")
        _pdf_com_tabela_quebrada(entrada)
        _quebrar_tabela(entrada, letra=mapa_glifos.SEM_MAPA, valor="El")

        with fitz.open(entrada) as d:
            assert "El" in d[0].get_text(), "o fixture não criou o mapeamento duplo"

        saida = os.path.join(tmp, "out.pdf")
        rel = corrigir_mapeamento(entrada, saida, classificar=_classificador())

        assert rel.aceitas, f"o fantasma escondeu o vizinho: {rel.resumo()}"
        with fitz.open(saida) as d:
            texto = d[0].get_text()
        assert "♘f" in texto, repr(texto)
        assert "El" not in texto


def test_o_padrao_nao_aceita_votacao_dividida():
    """
    Os limiares padrão são apertados, e o motivo está medido.

    Com 0,6 de concordância e 0,5 de confiança — o ajuste da primeira passada —
    o *Yusupov_Artur_Complete* saiu com ♖ onde a página mostra ♔: um glifo de
    rei com 0,65 de confiança e 67% de concordância. Afrouxar isto de novo é
    uma decisão, não um detalhe, e o teste existe para que ela seja tomada de
    propósito.
    """
    assert mapa_glifos.CONCORDANCIA_MINIMA == 1.0
    assert mapa_glifos.CONFIANCA_MINIMA >= 0.9

    votos = collections.Counter({"♖": 4, "♔": 2})
    confiancas = {"♖": [0.65] * 4, "♔": [0.6] * 2}
    simbolo, _conf, _conc, aceita, motivo = mapa_glifos._decidir(
        votos, confiancas, atual=mapa_glifos.SEM_MAPA, notacao=1.0,
        min_amostras=2, min_concordancia=mapa_glifos.CONCORDANCIA_MINIMA,
        min_confianca=mapa_glifos.CONFIANCA_MINIMA, min_notacao=0.5)

    assert simbolo == "♖" and not aceita
    assert "concordância" in motivo


def test_votacao_fraca_deixa_o_glifo_como_estava():
    """Propõe, marca, não reescreve calado — o contrato da F1.7."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        rel = corrigir_mapeamento(entrada, saida, classificar=_classificador(),
                                  min_confianca=0.999999)

        assert not rel.aceitas
        assert rel.recusadas
        assert any("confiança" in d.motivo for d in rel.recusadas)


def test_o_que_a_tabela_ja_diz_nao_e_reescrito():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        primeira = os.path.join(tmp, "1.pdf")
        segunda = os.path.join(tmp, "2.pdf")

        corrigir_mapeamento(entrada, primeira, classificar=_classificador())
        rel = corrigir_mapeamento(primeira, segunda, classificar=_classificador())

        assert not rel.aceitas, "corrigiu de novo o que já estava corrigido"
        with fitz.open(primeira) as a, fitz.open(segunda) as b:
            assert a[0].get_text() == b[0].get_text()


def test_escopo_sem_mapa_ignora_o_que_tem_mapeamento():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        tudo = corrigir_mapeamento(entrada, os.path.join(tmp, "a.pdf"),
                                   classificar=_classificador(), escopo="tudo")
        restrito = corrigir_mapeamento(entrada, os.path.join(tmp, "b.pdf"),
                                       classificar=_classificador(),
                                       escopo="sem_mapa")
        assert restrito.glifos_examinados < tudo.glifos_examinados


def test_escopo_invalido():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        try:
            corrigir_mapeamento(entrada, os.path.join(tmp, "o.pdf"),
                                classificar=_classificador(), escopo="xpto")
        except ValueError as e:
            assert "escopo" in str(e)
        else:
            raise AssertionError("aceitou um escopo inválido")


# ----------------------------------------------------------------------
# Simulação e relatório
# ----------------------------------------------------------------------

def test_dry_run_nao_grava_o_pdf():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        rel = corrigir_mapeamento(entrada, saida, classificar=_classificador(),
                                  dry_run=True)

        assert rel.aceitas, "a simulação não viu o que a conversão vê"
        assert not os.path.exists(saida)


def test_o_relatorio_mostra_a_troca():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        corrigir_mapeamento(entrada, saida, classificar=_classificador())
        cj, cc = mapa_glifos.caminhos_do_relatorio(saida)

        with open(cj, encoding="utf-8") as f:
            dados = json.load(f)
        assert dados["corrigidos"] >= 1
        assert dados["ocorrencias_corrigidas"] >= 1
        assert dados["por_simbolo"].get("♘")
        aceita = [d for d in dados["descobertas"] if d["aceita"]][0]
        assert aceita["atual"] == mapa_glifos.SEM_MAPA
        assert aceita["simbolo"] == "♘"

        with open(cc, encoding="utf-8-sig") as f:
            csv_texto = f.read()
        assert "atual" in csv_texto.splitlines()[0]
        assert "♘" in csv_texto


def test_o_relatorio_nao_lista_os_milhares_de_glifos_de_prosa():
    """
    Com `escopo="tudo"` o veredito cobre todo glifo do documento — 1.615 num
    trecho de 30 páginas do Yusupov. Despejar isso no CSV faria o relatório
    ilegível justamente para quem foi conferir o que mudou.
    """
    vereditos = [
        Descoberta(fonte="F", glifo=1, simbolo="♘", aceita=True),
        Descoberta(fonte="F", glifo=2, simbolo="♖", aceita=False,
                   motivo="concordância 33%, mínimo 60%"),
        Descoberta(fonte="F", glifo=3, simbolo="a", aceita=False,
                   motivo="o mais votado ('a') não é peça de xadrez"),
        Descoberta(fonte="F", glifo=4, simbolo="♗", aceita=False,
                   motivo="a tabela já diz isso"),
    ]
    ficaram = mapa_glifos.relevantes(vereditos)

    assert [d.glifo for d in ficaram] == [1, 2], (
        "o relatório tem de trazer a troca feita e a que quase foi feita, "
        "e não a prosa nem o que já estava certo")


def test_arquivo_inexistente():
    try:
        corrigir_mapeamento("nao_existe_xyz.pdf", "saida.pdf",
                            classificar=_classificador())
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("deveria reclamar de arquivo inexistente")


# ----------------------------------------------------------------------
# A ação na UI
# ----------------------------------------------------------------------

class _App:
    """MainWindow com os diálogos capturados e o modelo neural fora do caminho."""

    def __init__(self, entrada, simbolo="♘"):
        import ui.main_window as mw
        from ui.main_window import MainWindow

        self.entrada = entrada
        self.saida = os.path.join(os.path.dirname(entrada), "saida.pdf")
        self.infos, self.alertas = [], []

        self._original = (messagebox.showinfo, messagebox.showwarning,
                          messagebox.showerror, filedialog.askopenfilename,
                          filedialog.asksaveasfilename)
        messagebox.showinfo = lambda t, m, **k: self.infos.append((t, m))
        messagebox.showwarning = lambda t, m, **k: self.alertas.append((t, m))
        messagebox.showerror = lambda t, m, **k: self.alertas.append((t, m))
        filedialog.askopenfilename = lambda **k: self.entrada
        filedialog.asksaveasfilename = lambda **k: self.saida

        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        self.win.learning_service.load_predictor = lambda *a, **k: True
        self.win.learning_service.predict_neural = lambda c: (simbolo, 0.99)

    def corrigir(self, limite=60.0):
        self.win.corrigir_mapeamento_action()
        fim = time.time() + limite
        self.root.update()
        while self.win.task.is_running() and time.time() < fim:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        assert not self.win.task.is_running(), "a tarefa não terminou no tempo"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        (messagebox.showinfo, messagebox.showwarning, messagebox.showerror,
         filedialog.askopenfilename, filedialog.asksaveasfilename) = self._original
        try:
            self.win.task.shutdown()
            self.win.status.end_task()
            self.root.update()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def test_a_acao_da_ui_corrige_e_avisa_que_a_pagina_nao_mudou():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        with _App(entrada) as app:
            app.corrigir()

            assert app.infos, f"não concluiu: {app.alertas}"
            texto = app.infos[-1][1]
            assert "página não foi alterada" in texto
            assert "original não foi tocado" in texto
            with fitz.open(app.saida) as d:
                assert "♘f" in d[0].get_text()


def test_a_ui_avisa_quando_nao_identificou_nada():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_com_tabela_quebrada(os.path.join(tmp, "in.pdf"))
        with _App(entrada, simbolo="Z") as app:
            app.corrigir()

            assert app.alertas, "nada identificado saiu como conclusão"
            assert "Nenhuma figurina foi identificada" in app.alertas[-1][1]


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
