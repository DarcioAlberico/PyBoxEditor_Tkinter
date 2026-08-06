"""F9.1 — léxico do texto corrido.

Os casos de fronteira de palavra não são inventados: são os que `medir_lexico.py`
encontrou nas 10 páginas rotuladas, incluindo os que **não** devem ser mexidos
(`Xue-Fierro`, `some`, `opening`). Um teste que só cobre o caso que funciona não
trava nada — foi o que deixou o separador da F1.5 passar.
"""

import gzip
import os

import pytest

from core import lexico


PROSA = {"of", "the", "a", "in", "to", "so", "me", "some", "open", "ing",
         "opening", "play", "plans", "following", "chess", "pieces", "square",
         "only", "if", "we", "black", "promised", "compromised", "barrassment",
         "embarrassment", "clude", "conclude", "con", "well", "known",
         "counterplay", "terplay", "coun"}


@pytest.fixture
def lex():
    return lexico.Lexico(palavras=set(PROSA))


# ----------------------------------------------------------------- Lexico

def test_conhece_ignora_caixa(lex):
    assert lex.conhece("the") and lex.conhece("The") and lex.conhece("THE")


def test_lexico_vazio_e_vazio():
    assert lexico.Lexico().vazio
    assert not lexico.Lexico(palavras={"a"}).vazio
    assert not lexico.Lexico(do_usuario={"benko"}).vazio


def test_procedencia_separa_as_duas_listas():
    lex = lexico.Lexico(palavras={"the"}, do_usuario={"benko"})
    assert lex.procedencia("the") == "idioma"
    assert lex.procedencia("Benko") == "usuario"
    assert lex.procedencia("tromso") is None


def test_acrescentar_so_aceita_palavra(lex):
    assert lex.acrescentar("Benko") is True
    assert lex.conhece("benko")
    assert lex.acrescentar("Benko") is False        # já estava
    assert lex.acrescentar("a") is False            # curta demais
    assert lex.acrescentar("f7") is False           # não é palavra
    assert lex.acrescentar("...") is False


def test_acrescentar_nao_polui_a_lista_do_idioma(lex):
    antes = set(lex.palavras)
    lex.acrescentar("Tromso")
    assert lex.palavras == antes
    assert "tromso" in lex.do_usuario


def test_carregar_arquivo_ausente_devolve_vazio(tmp_path):
    lex = lexico.carregar(str(tmp_path / "nao-existe.txt"))
    assert lex.vazio          # contrato 6: sem dicionário, nada acontece


def test_carregar_le_e_normaliza(tmp_path):
    p = tmp_path / "en.txt"
    p.write_text("The\nOF\n\n  play  \n", encoding="utf-8")
    lex = lexico.carregar(str(p))
    assert lex.conhece("the") and lex.conhece("of") and lex.conhece("PLAY")
    assert len(lex) == 3


def test_carregar_lista_do_usuario_separada(tmp_path):
    (tmp_path / "en.txt").write_text("the\n", encoding="utf-8")
    (tmp_path / "meu.txt").write_text("Benko\n", encoding="utf-8")
    lex = lexico.carregar(str(tmp_path / "en.txt"), str(tmp_path / "meu.txt"))
    assert lex.procedencia("benko") == "usuario"
    assert lex.procedencia("the") == "idioma"


# ----------------------------------------------------------------- nucleo

def test_nucleo_tira_das_pontas_nao_do_meio():
    assert lexico.nucleo("counterplay,") == ("counterplay", 0)
    assert lexico.nucleo("(see") == ("see", 1)
    # O erro que a medida da F9 quase perdeu: dígito no meio fica.
    assert lexico.nucleo("p1ay") == ("p1ay", 0)
    assert lexico.nucleo("Mov6") == ("Mov", 0)


def test_nucleo_sem_letra_nenhuma():
    assert lexico.nucleo("2010") == ("", 4)
    assert lexico.nucleo("") == ("", 0)


# ------------------------------------------------------- hífen de fim de linha

def test_junta_palavra_partida_pelo_hifen(lex):
    linhas = [["and", "em-"], ["barrassment", "for"]]
    js = lexico.juntar_hifenizadas(linhas, lex)
    assert [j.texto for j in js] == ["embarrassment"]
    assert js[0].linha == 0 and js[0].palavra == 1


def test_junta_ignorando_pontuacao_da_direita(lex):
    linhas = [["com-"], ["promised."]]
    assert [j.texto for j in lexico.juntar_hifenizadas(linhas, lex)] \
        == ["compromised"]


def test_nao_junta_quando_o_resultado_nao_e_palavra(lex):
    """`Xue-Fierro` tem hífen de verdade — é nome próprio, medido na página."""
    linhas = [["Xue-"], ["Fierro"]]
    assert lexico.juntar_hifenizadas(linhas, lex) == []


def test_nao_junta_composto_cuja_esquerda_ja_e_palavra(lex):
    """"well-" + "known": o hífen é do composto, não quebra de linha."""
    linhas = [["well-"], ["known"]]
    assert lexico.juntar_hifenizadas(linhas, lex) == []


def test_nao_junta_sem_dicionario():
    linhas = [["em-"], ["barrassment"]]
    assert lexico.juntar_hifenizadas(linhas, lexico.Lexico()) == []


def test_hifen_na_ultima_linha_nao_estoura(lex):
    assert lexico.juntar_hifenizadas([["con-"]], lex) == []
    assert lexico.juntar_hifenizadas([["con-"], []], lex) == []


# ------------------------------------------------------------ palavra colada

def test_parte_palavra_colada(lex):
    """"ofthe" com a lacuna do corte maior que as internas — medido 7 de 7."""
    lacunas = [0.05, 0.44, 0.11, 0.09]      # o|f|t|h|e -> corte em 2
    assert lexico.partir_colada("ofthe", lacunas, lex) == 2


def test_nao_parte_palavra_que_esta_no_dicionario(lex):
    """`some` decompõe em `so`+`me` e é palavra. A 1ª condição já a salva."""
    lacunas = [0.05, 0.27, 0.09]
    assert lexico.partir_colada("some", lacunas, lex) is None


def test_nao_parte_quando_a_lacuna_do_corte_nao_se_destaca(lex):
    """Sem o teste de lacuna, nome próprio cujas partes existem seria partido."""
    lacunas = [0.05, 0.10, 0.11, 0.30]      # a maior NÃO está no corte (pos 2)
    assert lexico.partir_colada("ofthe", lacunas, lex) is None


def test_nao_parte_o_que_nao_decompoe(lex):
    assert lexico.partir_colada("tromso", [0.4] * 5, lex) is None


def test_nao_parte_sem_dicionario():
    assert lexico.partir_colada("ofthe", [0.05, 0.44, 0.11, 0.09],
                                lexico.Lexico()) is None


def test_lacunas_de_tamanho_errado_nao_partem(lex):
    """Contrato do vetor: um valor por par de vizinhos. Errado é não agir."""
    assert lexico.partir_colada("ofthe", [0.44], lex) is None


def test_cortes_possiveis_respeita_o_minimo(lex):
    # "a" é palavra da lista, mas parte de 1 letra não conta.
    assert 1 not in lexico.cortes_possiveis("aplay", lex)


# --------------------------------------------------------------- sinalização

def _sim(texto, base=0):
    """Palavra como pares (caractere, índice do box), um box por caractere."""
    return [(c, base + k) for k, c in enumerate(texto)]


def test_sinaliza_palavra_fora_do_dicionario(lex):
    s = lexico.sinalizar([_sim("follow1ng")], lex)
    assert [x.palavra for x in s] == ["follow1ng"]


def test_sinaliza_palavra_com_digito_no_meio(lex):
    """O caso canônico da fase: `1`↔`l`, a confusão que a F1.3 mediu.

    A primeira versão exigia núcleo todo alfabético e pulava exatamente estes.
    """
    assert [x.palavra for x in lexico.sinalizar([_sim("p1ay")], lex)] == ["p1ay"]
    assert [x.palavra for x in lexico.sinalizar([_sim("Mov6")], lex)] == ["Mov"]


def test_nao_sinaliza_palavra_conhecida(lex):
    assert lexico.sinalizar([_sim("following")], lex) == []


def test_nao_sinaliza_pontuacao_nem_numero(lex):
    assert lexico.sinalizar([_sim("2010"), _sim(","), _sim("a")], lex) == []


def test_nao_sinaliza_sem_dicionario():
    assert lexico.sinalizar([_sim("follow1ng")], lexico.Lexico()) == []


def test_indices_apontam_so_o_nucleo(lex):
    s = lexico.sinalizar([_sim("(plyas,")], lex)
    assert len(s) == 1
    # "(plyas," -> núcleo "plyas" nos boxes 1..5
    assert s[0].indices == [1, 2, 3, 4, 5]


def test_indices_com_box_de_ligadura(lex):
    """Um box que devolve dois caracteres não pode deslocar o destaque.

    É o caso das 16 classes da SPEC §5.2 item 6: cortar a lista de boxes por
    deslocamento de caractere apontaria o box errado.
    """
    simbolos = [("(", 0), ("f", 1), ("fi", 2), ("x", 3), (",", 4)]
    nuc, indices = lexico.boxes_do_nucleo(simbolos)
    assert nuc == "ffix"
    assert indices == [1, 2, 3]


def test_palavra_do_usuario_deixa_de_ser_suspeita(lex):
    assert lexico.sinalizar([_sim("Benko")], lex)[0].palavra == "Benko"
    lex.acrescentar("Benko")
    assert lexico.sinalizar([_sim("Benko")], lex) == []


def test_caminho_padrao_e_relativo_ao_projeto():
    assert lexico.CAMINHO_PADRAO.endswith(os.path.join("lexico", "en.txt.gz"))
    assert lexico.CAMINHO_NOMES.endswith(os.path.join("lexico", "nomes.txt.gz"))


# ------------------------------------------- carga das listas empacotadas

def _grava(caminho, palavras):
    if str(caminho).endswith(".gz"):
        with gzip.open(caminho, "wt", encoding="utf-8") as f:
            f.write("\n".join(palavras))
    else:
        caminho.write_text("\n".join(palavras), encoding="utf-8")
    return str(caminho)


def test_carregar_le_gz_e_texto(tmp_path):
    """As listas vão comprimidas no repositório, mas texto puro continua valendo.

    São 0,94 MB contra 3,01, e o tamanho era a objeção registrada contra
    empacotá-las (ROADMAP F9.1, medida 2).
    """
    for nome in ("lista.txt.gz", "lista.txt"):
        lex = lexico.carregar(_grava(tmp_path / nome, ["The", "opening"]))
        assert lex.conhece("the") and lex.conhece("OPENING")


def test_carregar_junta_nomes_ao_idioma(tmp_path, monkeypatch):
    """`nomes=True` traz as Capitalizadas do ABBYY, e elas entram em `palavras`.

    Em `do_usuario` elas apagariam a pergunta que `procedencia` responde: se o
    acerto veio da lista deste usuário ou de uma lista de prateleira.
    """
    monkeypatch.setattr(lexico, "CAMINHO_PADRAO",
                        _grava(tmp_path / "en.txt.gz", ["the", "opening"]))
    monkeypatch.setattr(lexico, "CAMINHO_NOMES",
                        _grava(tmp_path / "nomes.txt.gz", ["benko", "tromso"]))

    com = lexico.carregar()
    assert len(com) == 4 and com.conhece("Benko")
    assert com.procedencia("Benko") == "idioma" and not com.do_usuario

    sem = lexico.carregar(nomes=False)
    assert len(sem) == 2 and not sem.conhece("Benko")


def test_carregar_sem_arquivo_nenhum_nao_levanta(tmp_path, monkeypatch):
    """Contrato 6 da SPEC §5.8: sem dicionário, nada acontece — e nada quebra."""
    monkeypatch.setattr(lexico, "CAMINHO_PADRAO", str(tmp_path / "nao-existe.gz"))
    monkeypatch.setattr(lexico, "CAMINHO_NOMES", str(tmp_path / "nem-esta.gz"))
    assert lexico.carregar().vazio
