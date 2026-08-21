"""
Testes da F94 — a classe que o OCR não consegue criar sozinho.

A propriedade central é a mesma da F2.7, e é de **procedência**: nenhuma amostra
entra na base sem alguém ter olhado. O que muda aqui é de onde ela vem, e por
isso muda também qual é o jeito de ela estar errada.

Na F2.7 o rótulo é o palpite do modelo, e o perigo é treiná-lo no próprio erro.
Aqui o rótulo vem da **camada de texto do PDF** — e nestes livros ela mente:
são fontes Type0/Identity-H com o `ToUnicode` trocado (F2.5), e o que o arquivo
chama de `Å` é o desenho do rei. A primeira versão desta ferramenta colheu 108
ocorrências de `Å` do Aagaard e **as 108 eram ♔**. O `avalizado` é o que fecha
isso, e a metade de cima destes testes é sobre ele — inclusive sobre a versão
frouxa dele, que deixou passar 31 borrões em 58 e foi substituída por medição.

Rodar sem pytest:      python tests/test_f94_letras.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import importar_letras as il


def _glifo(lado=24, marca=0):
    """Um retângulo de tinta com folga em volta — tem o que apertar."""
    img = np.full((lado, lado), 250, dtype=np.uint8)
    img[6:lado - 6, 6:lado - 6] = 20 + marca
    return img


# ----------------------------------------------------------------------
# O portão: o recorte só entra se o modelo o avalizar
# ----------------------------------------------------------------------

def test_a_leitura_plausivel_e_a_letra_base():
    """
    **O modelo nunca vai confirmar a letra nova** — é por não a ter que ela
    está sendo criada. O mais que ele faz é reconhecer a letra-base, e é o que
    ele faz num `š` de verdade: lê `s`.
    """
    assert "A" in il.leituras_plausiveis("Å")
    assert "s" in il.leituras_plausiveis("š")
    assert "S" in il.leituras_plausiveis("Š")
    assert "c" in il.leituras_plausiveis("č")
    assert "n" in il.leituras_plausiveis("ń")
    assert "z" in il.leituras_plausiveis("ž")


def test_a_letra_sem_decomposicao_tem_base_dita_a_mao():
    """
    `Å` decompõe em `A` + anel e o `NFD` resolve. `ø` e `æ` **não decompõem** —
    para o Unicode são letras próprias —, e sem a tabela ficariam sem base: o
    portão recusaria toda amostra delas, que é a falha silenciosa pior.
    """
    for letra, base in (("ø", "o"), ("Ø", "O"), ("æ", "a"), ("ß", "B")):
        assert base in il.leituras_plausiveis(letra), letra


def test_o_rei_chamado_de_A_com_anel_e_recusado():
    """
    **O defeito que esta fase encontrou, fixado.** No Aagaard a camada de texto
    diz `Å` 108 vezes e as 108 são ♔ — o `ToUnicode` da fonte de figurinha está
    trocado (F2.5). Sem este portão, a classe de `Å` nasceria com 54 desenhos de
    rei dentro, e ninguém veria: numa pasta chamada `sym_197`, quem confere que
    aquilo não é um Å?
    """
    assert il.avalizado("Å", "♔", 0.99) is False
    assert il.avalizado("š", "♘", 0.97) is False


def test_ler_a_letra_base_e_o_que_avaliza():
    """A contrapartida: sem ela o portão recusaria toda amostra verdadeira."""
    assert il.avalizado("Å", "A", 0.99) is True
    assert il.avalizado("š", "s", 0.99) is True
    assert il.avalizado("ø", "o", 0.99) is True
    assert il.avalizado("Š", "S", 0.29) is True, "confiança baixa não reprova"


def test_a_hesitacao_reprova_e_a_medicao_e_que_manda():
    """
    **O argumento bonito que a medição derrubou.** A primeira régua presumia a
    favor do recorte: entrava tudo, menos o que o modelo contradissesse com
    confiança >= 0,90. A justificativa era que "hesitação não desmente, e
    recusar por ela jogaria fora o recorte estranho, que é o que a classe nova
    mais precisa".

    Nas 58 amostras colhidas e rotuladas a olho, essa régua manteve os 27 bons
    **e os 31 de lixo**; a estrita manteve 17 e **zero**. O lixo mora justamente
    na hesitação, e tinha de morar: um borrão de trama não pertence a classe
    nenhuma, então o softmax se espalha. O `♗` mais confiante deu 0,871 e
    passava por baixo do limiar — e baixá-lo mataria o `å` lido como `ä` a
    0,590, que é bom.
    """
    assert il.avalizado("Å", "♔", 0.40) is False
    assert il.avalizado("Č", "♗", 0.871) is False, (
        "é o recorte mais confiante da pilha de lixo — nenhum limiar o pega "
        "sem matar amostra boa")
    assert il.avalizado("Å", "", 0.99) is False


def test_o_portao_por_fonte_nao_substitui_o_portao_por_recorte():
    """
    **A trava contra a tentação de voltar atrás.** A primeira versão filtrava
    por fonte: media a concordância da camada nas letras de controle e colhia
    das fontes que passassem. Cinco fontes do Aagaard passaram com 85% a 97% —
    e entregaram 54 reis chamados de `Å`.

    O portão por fonte **não pode** funcionar, e a razão é estrutural: a mesma
    face desenha o texto e a figurinha, mapeia o texto certo e a figurinha
    errado. Concordar no `a` e no `e` não diz nada sobre o glifo que o produtor
    do PDF chamou de `Å`. E a medição fecha: o Yusupov Complete, de onde saíram
    31 dos 31 recortes de lixo, tem **89,9%** de concordância nas letras de
    controle — praticamente a mesma do Dvoretsky (91,2%), de onde saíram os 27
    bons. `conferir_camada` fica como diagnóstico; quem decide é `avalizado`.
    """
    from inspect import signature

    assert "classificar" in signature(il.colher_do_pdf).parameters, (
        "colher_do_pdf tem de exigir o classificador")
    assert "fontes" not in signature(il.colher_do_pdf).parameters, (
        "o filtro por fonte voltou a decidir a colheita — ver F94")


# ----------------------------------------------------------------------
# O recorte justo, que é a convenção da base
# ----------------------------------------------------------------------

def test_apertar_devolve_so_a_tinta():
    """
    A base é de recorte justo: as amostras de `training_data` têm 0 a 2 px de
    margem porque nasceram de componente conexo. O retângulo da camada de texto
    é o do avanço, e promovê-lo esticaria o glifo de um jeito que nenhuma
    amostra de OCR é esticada.
    """
    corte = il.apertar(_glifo(24))
    assert corte is not None
    assert corte.shape == (12, 12), corte.shape


def test_apertar_recusa_o_que_nao_tem_tinta():
    assert il.apertar(np.full((20, 20), 255, dtype=np.uint8)) is None
    assert il.apertar(np.zeros((0, 0), dtype=np.uint8)) is None
    assert il.apertar(None) is None


# ----------------------------------------------------------------------
# A semente de fonte
# ----------------------------------------------------------------------

def test_a_face_so_entra_se_desenhar_de_verdade():
    """
    **`has_glyph` mentiu, e por isso a conferência é por tinta.** Perguntada às
    duas fontes embutidas do Dvoretsky, ela respondeu "sim" para as 16 letras
    pedidas — e a renderização saiu vazia até para o `a`. Uma face que devolve
    `.notdef` entrega um retângulo, e um retângulo promovido para a classe de
    `ń` ensina que `ń` é um retângulo.
    """
    faces = il.faces_disponiveis()
    if not faces:
        return                      # máquina sem as faces do Windows
    for caminho in faces:
        for controle in "aso":
            assert il.desenhar(caminho, controle, 40) is not None, caminho


def test_a_semente_desenha_a_letra_pedida():
    faces = il.faces_disponiveis()
    if not faces:
        return
    saiu = {ch for ch, _face, corte in
            il.semear_da_fonte("Šńž", faces[:2], corpos=(40,))
            if corte is not None}
    assert saiu == set("Šńž"), saiu


# ----------------------------------------------------------------------
# O depósito
# ----------------------------------------------------------------------

def test_nada_vai_para_training_data():
    """
    **A propriedade de segurança da F2.7, herdada inteira.** Os dois modos de
    errar desta ferramenta — o retângulo que pega o vizinho e a face que não é a
    do livro — são invisíveis num CSV e óbvios numa grade de miniaturas. Então
    ela grava onde se olha, não onde se treina.
    """
    from core import coleta

    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "training_data")
        os.makedirs(base)
        d = il.Deposito(os.path.join(tmp, "revisao"))
        d.guardar("š", _glifo(), "fonte-times")

        assert d.gravados["š"] == 1
        assert os.listdir(base) == [], "escreveu na base sem revisão"
        assert coleta.PASTA_PADRAO != "training_data"


def test_a_procedencia_fica_no_nome_do_arquivo():
    """
    Durante a revisão é preciso saber, sem abrir nada, qual amostra é semente e
    qual é livro: `fonte-times_…` no meio de `pdf-dvoretsky_…` diz isso na
    listagem da pasta. O índice guarda o mesmo, e é o único lugar onde a
    procedência sobrevive à promoção — o `learner.learn` renomeia tudo para UUID.
    """
    with tempfile.TemporaryDirectory() as tmp:
        d = il.Deposito(os.path.join(tmp, "revisao"))
        do_livro = d.guardar("š", _glifo(marca=1), "pdf-nunn_p0031", pagina=30)
        da_fonte = d.guardar("š", _glifo(marca=2), "fonte-times")

        assert os.path.basename(do_livro).startswith("pdf-nunn_p0031_")
        assert os.path.basename(da_fonte).startswith("fonte-times_")
        origens = {l["origem"] for l in d.linhas}
        assert origens == {"pdf-nunn_p0031", "fonte-times"}
        assert [l["pagina"] for l in d.linhas] == [31, ""]


def test_a_mesma_imagem_entra_uma_vez_so():
    """Mesma régua da F93: dois recortes com a mesma impressão são o mesmo tensor."""
    with tempfile.TemporaryDirectory() as tmp:
        d = il.Deposito(os.path.join(tmp, "revisao"))
        for _ in range(5):
            d.guardar("š", _glifo(marca=3), "fonte-times")

        assert d.gravados["š"] == 1
        assert d.repetidos == 4


def test_a_pasta_e_a_que_a_base_usa():
    """Promover é mover: se os nomes divergissem, não seria."""
    from core.learner import char_to_folder

    with tempfile.TemporaryDirectory() as tmp:
        pasta = os.path.join(tmp, "revisao")
        d = il.Deposito(pasta)
        for i, ch in enumerate("ŃńŠšŽžČčĆćÅåŞşØø"):
            d.guardar(ch, _glifo(marca=i), "fonte-times")

        for ch in "ŃńŠšŽžČčĆćÅåŞşØø":
            assert os.path.isdir(os.path.join(pasta, char_to_folder(ch))), ch


def test_o_indice_aponta_para_arquivo_que_existe():
    import csv

    with tempfile.TemporaryDirectory() as tmp:
        pasta = os.path.join(tmp, "revisao")
        d = il.Deposito(pasta)
        for i, ch in enumerate("Šš"):
            d.guardar(ch, _glifo(marca=i), "fonte-times")
        caminho = d.gravar_indice()

        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f))
        assert len(linhas) == 2
        for l in linhas:
            assert os.path.exists(os.path.join(pasta, l["arquivo"])), l


# ----------------------------------------------------------------------
# A procedência atravessa a promoção
# ----------------------------------------------------------------------

def test_a_promocao_guarda_o_nome_de_origem():
    """
    **Semente e amostra de livro ensinam coisas diferentes**, e depois de
    promovidas ficavam indistinguíveis: o `learn` renomeava tudo para UUID.

    Isso não é perda cosmética. A semente de fonte existe para a classe existir
    enquanto nenhum livro traz a letra; quando um trouxer, é ela que se troca.
    Sem o nome não há como achar qual trocar — a base tem 130 mil arquivos.

    É a mesma lição que o `dataset_check._nome_livre` já tinha aprendido do
    outro lado: "o nome do arquivo é dado, não enfeite".
    """
    from core import coleta

    with tempfile.TemporaryDirectory() as tmp:
        pasta, base = os.path.join(tmp, "revisao"), os.path.join(tmp, "base")
        d = il.Deposito(pasta)
        d.guardar("š", _glifo(marca=1), "fonte-times")
        d.guardar("š", _glifo(marca=2), "pdf-dvoretsky_p0155")

        coleta.promover(pasta, data_dir=base)

        from core.learner import char_to_folder
        nomes = sorted(os.listdir(os.path.join(base, char_to_folder("š"))))
        assert len(nomes) == 2, nomes
        assert any(n.startswith("fonte-times_") for n in nomes), nomes
        assert any(n.startswith("pdf-dvoretsky_p0155_") for n in nomes), nomes


def test_o_nome_de_origem_nao_escapa_da_pasta_da_classe():
    """
    O nome vem de fora, então é higienizado: `..` ou uma barra escreveriam fora
    da pasta da classe, e caractere não-ASCII faz o `cv2.imwrite` devolver
    `False` calado no Windows — foi assim que a pasta `lower_ä` da base ficou
    vazia. O que não sobrevive à limpeza volta a ser UUID.
    """
    from core.learner import _nome_de_amostra

    assert _nome_de_amostra("fonte-times_ab12.png") == "fonte-times_ab12.png"
    for perigoso in ("../../etc/passwd", "..", "", "  ", "ção", "/",
                     "\\pasta\\x", "C:/absoluto.png"):
        saiu = _nome_de_amostra(perigoso)
        assert saiu.endswith(".png")
        assert os.sep not in saiu and "/" not in saiu and ".." not in saiu
        assert saiu.isascii(), saiu


def test_sem_nome_continua_uuid():
    """O caminho de sempre — a edição de box — não muda."""
    from core.learner import _nome_de_amostra

    a, b = _nome_de_amostra(), _nome_de_amostra()
    assert a != b and a.endswith(".png") and len(a) == 40


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
