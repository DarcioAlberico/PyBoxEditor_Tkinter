"""
Testes da F2.4 — perfis de mapeamento por fonte (SPEC §4.5).

O que motivou a fase, além do "nem toda fonte usa KQRBNP" do roadmap, foi um
defeito que a simulação da F2.3 mediu: `Bb5` saía como `♗♝5`. O `B` é o bispo,
certo — mas o `b`, que ali é a **coluna b**, também estava no perfil único
(minúscula = peça preta) e virava bispo preto.

Não dá para resolver por heurística: nas fontes figurinas de verdade as
minúsculas **são** peças pretas, e num livro que use as duas caixas mapear só as
maiúsculas perderia as peças pretas. É decisão por livro — que é o que um perfil
é. `test_perfil_de_figurina_unica_conserta_a_coluna` é o teste que fixa isso.

Rodar sem pytest:      python tests/test_f24_perfis.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import perfis
from core.perfis import Perfil, PerfilInvalido


def _escrever(pasta, nome, dados):
    caminho = os.path.join(pasta, nome)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    return caminho


def _perfil_minimo(**extra):
    base = {"name": "Teste", "mapping": {"K": "♔"}, "font_patterns": ["teste"]}
    base.update(extra)
    return base


# ----------------------------------------------------------------------
# Os perfis que acompanham o projeto
# ----------------------------------------------------------------------

def test_perfis_do_projeto_carregam():
    lista = perfis.carregar_todos()
    assert lista, "nenhum perfil em config/profiles"
    assert all(isinstance(p, Perfil) for p in lista)


def test_perfil_de_figurina_unica_conserta_a_coluna():
    """
    O defeito que a F2.3 mediu: 'Bb5' virava '♗♝5'.

    Nestes livros existe um conjunto só de figurinas para os dois lados (F1.1) —
    quem diz a cor é a paridade do lance. Então minúscula é COLUNA, não peça, e o
    perfil não pode mapeá-la.
    """
    unico = next(p for p in perfis.carregar_todos() if "nica" in p.nome)

    assert "B" in unico.mapeamento, "perdeu o bispo"
    assert "b" not in unico.mapeamento, "a coluna 'b' voltou a virar peça"

    traduzido = "".join(unico.mapeamento.get(c, c) for c in "Bb5")
    assert traduzido == "♗b5", f"saiu {traduzido!r}"


def test_perfil_de_duas_caixas_preserva_o_comportamento_antigo():
    """Para diagrama, 'rnbqkbnr' é a fileira inteira e as minúsculas são peças."""
    duas = next(p for p in perfis.carregar_todos() if "caixas" in p.nome)

    for letra in "kqrbnp":
        assert letra in duas.mapeamento, f"perdeu a peça preta {letra!r}"
    traduzido = "".join(duas.mapeamento.get(c, c) for c in "rnbq")
    assert traduzido == "♜♞♝♛", f"saiu {traduzido!r}"


def test_precedencia_e_a_ordem_do_nome_do_arquivo():
    """`10_` antes de `20_`: numa fonte que case com os dois, o primeiro ganha."""
    lista = perfis.carregar_todos()
    nomes = [os.path.basename(p.origem) for p in lista]
    assert nomes == sorted(nomes)


# ----------------------------------------------------------------------
# Seleção por font_patterns
# ----------------------------------------------------------------------

def test_escolhe_pelo_padrao_de_fonte():
    a = Perfil("A", {"K": "♔"}, padroes_de_fonte=["merida"])
    b = Perfil("B", {"K": "♔"}, padroes_de_fonte=["leipzig"])

    assert perfis.escolher("ABCD+MeridaNew", [a, b]) is a
    assert perfis.escolher("Leipzig-Bold", [a, b]) is b
    assert perfis.escolher("Times New Roman", [a, b]) is None


def test_casamento_ignora_caixa_e_e_por_trecho():
    p = Perfil("A", {"K": "♔"}, padroes_de_fonte=["MERIDA"])
    assert p.casa_com_fonte("abcd+meridanew")
    assert p.casa_com_fonte("Merida")
    assert not p.casa_com_fonte("")


def test_perfil_sem_padrao_nunca_e_escolhido_sozinho():
    """Um perfil sem `font_patterns` só serve como override manual."""
    p = Perfil("Manual", {"K": "♔"}, padroes_de_fonte=[])
    assert perfis.escolher("qualquer", [p]) is None


# ----------------------------------------------------------------------
# Validação — perfil quebrado não pode passar em silêncio
# ----------------------------------------------------------------------

def _recusa(dados, trecho_do_erro):
    try:
        perfis.de_dicionario(dados, origem="teste.json")
    except PerfilInvalido as e:
        assert trecho_do_erro in str(e), f"mensagem inesperada: {e}"
    else:
        raise AssertionError(f"aceitou perfil inválido: {dados}")


def test_recusa_perfil_sem_nome():
    _recusa({"mapping": {"K": "♔"}}, "name")


def test_recusa_perfil_sem_mapeamento():
    _recusa({"name": "X"}, "mapping")
    _recusa({"name": "X", "mapping": {}}, "mapping")


def test_recusa_chave_de_mais_de_um_caractere():
    """
    `process_span` traduz caractere a caractere: uma chave de dois caracteres
    nunca casaria, e o perfil ficaria inerte sem ninguém perceber.
    """
    _recusa(_perfil_minimo(mapping={"KQ": "♔"}), "1")


def test_recusa_mapeamento_que_nao_e_texto():
    _recusa(_perfil_minimo(mapping={"K": 9}), "texto")


def test_recusa_modo_desconhecido():
    _recusa(_perfil_minimo(mode="ascii"), "modo")


def test_recusa_padroes_que_nao_sao_lista_de_texto():
    _recusa(_perfil_minimo(font_patterns="merida"), "font_patterns")
    _recusa(_perfil_minimo(font_patterns=[1, 2]), "font_patterns")


def test_recusa_limiares_de_diagrama_absurdos():
    _recusa(_perfil_minimo(diagram_detection={"min_lines": 0}), "min_lines")
    _recusa(_perfil_minimo(diagram_detection={"chess_span_ratio": 0}), "chess_span_ratio")
    _recusa(_perfil_minimo(diagram_detection={"chess_span_ratio": 1.5}), "chess_span_ratio")


def test_json_quebrado_diz_o_arquivo():
    pasta = tempfile.mkdtemp()
    caminho = os.path.join(pasta, "ruim.json")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("{ isto nao e json")
    try:
        perfis.carregar(caminho)
    except PerfilInvalido as e:
        assert "ruim.json" in str(e)
    else:
        raise AssertionError("aceitou JSON quebrado")


def test_perfil_quebrado_interrompe_a_carga():
    """
    Pular o perfil quebrado faria a conversão cair no padrão em silêncio, e o
    usuário veria o livro convertido com o mapeamento errado sem nenhum aviso.
    """
    pasta = tempfile.mkdtemp()
    _escrever(pasta, "01_bom.json", _perfil_minimo())
    _escrever(pasta, "02_ruim.json", {"name": "sem mapeamento"})

    try:
        perfis.carregar_todos(pasta)
    except PerfilInvalido:
        pass
    else:
        raise AssertionError("carregou uma pasta com perfil inválido")


def test_pasta_inexistente_devolve_lista_vazia():
    assert perfis.carregar_todos(os.path.join(tempfile.gettempdir(), "nao_ha_1")) == []


# ----------------------------------------------------------------------
# Limiares de diagrama vindos do perfil
# ----------------------------------------------------------------------

def test_limiares_de_diagrama_saem_do_perfil():
    from core.chess_pdf_processor import CHESS_FONT_KEYWORDS, is_block_a_diagram

    bloco = {"lines": [{"spans": [{"font": "Merida"}]} for _ in range(5)]}
    original = CHESS_FONT_KEYWORDS[:]
    CHESS_FONT_KEYWORDS[:] = ["merida"]
    try:
        assert is_block_a_diagram(bloco) is True

        exigente = Perfil("X", {"K": "♔"}, min_linhas_diagrama=9)
        assert is_block_a_diagram(bloco, exigente) is False, \
            "o perfil não mudou o mínimo de linhas"

        frouxo = Perfil("Y", {"K": "♔"}, min_linhas_diagrama=2)
        assert is_block_a_diagram(bloco, frouxo) is True
    finally:
        CHESS_FONT_KEYWORDS[:] = original


def test_sem_perfil_usa_os_limiares_de_sempre():
    from core.chess_pdf_processor import is_block_a_diagram

    assert is_block_a_diagram({"lines": [{"spans": []}] * 3}) is False
    assert is_block_a_diagram({}) is False


# ----------------------------------------------------------------------
# Aceita as chaves em inglês (SPEC) e em português
# ----------------------------------------------------------------------

def test_aceita_as_chaves_da_spec_e_as_traduzidas():
    ingles = perfis.de_dicionario({
        "name": "A", "mode": "unicode", "font_patterns": ["m"],
        "mapping": {"K": "♔"},
        "diagram_detection": {"min_lines": 6, "chess_span_ratio": 0.5},
    })
    portugues = perfis.de_dicionario({
        "nome": "A", "modo": "unicode", "padroes_de_fonte": ["m"],
        "mapeamento": {"K": "♔"},
        "deteccao_de_diagrama": {"min_linhas": 6, "razao_span_xadrez": 0.5},
    })
    assert ingles == portugues


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
