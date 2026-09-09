"""
F118 — a máscara que cobre o núcleo inteiro.

O reparo da F66/F69 apaga o que veio do box largo e **ancora no resto**: `Dmamic`
vira `D` + máscara + `amic`, e o dicionário tem uma palavra só nesse molde. Estes
testes travam o caso em que não há resto.

Sem âncora o molde deixa de ser molde: `_casa` compara pedaço nenhum, toda palavra
daquele comprimento passa, e o `_candidatos` ainda perde a inicial — o trecho
começa em 0 — e vai buscar no balde `(comprimento, None)`, que é o dicionário
inteiro. Medido no `offer.` da página 6 do Aagaard, lido `0ffcx.`: **100.310
candidatos**, cada um cobrado uma varredura de `provar_letras`. A exportação do
livro parava ali.

O `provar` é injetado, como na F69: estes testes não precisam de rede treinada.
"""

import pytest

from core import lexico


#: Pequeno e explícito, como o da F69 — mas com **muitas** palavras de quatro
#: letras: é a população que o núcleo sem âncora arrasta inteira.
PROSA = {"hater", "hammer", "few", "flow", "the", "of", "and", "player",
         "wandering", "ffes", "offs", "ffed", "ofts", "efts", "arts", "ants"}


@pytest.fixture
def lex():
    return lexico.Lexico(palavras=set(PROSA))


def _simbolos(texto):
    """Pares (caractere, índice de box) — um box por caractere, como na F69."""
    return [(c, i) for i, c in enumerate(texto)]


def _provar_que_recusa():
    """Um `provar` que acusa se for consultado."""
    def provar(caixas, letras):
        raise AssertionError("sem âncora, a prova não devia ser consultada")
    return provar


def test_nucleo_todo_mascarado_nao_se_repara(lex):
    """
    O caso da página 6 do Aagaard, reduzido: `ffcx` com os quatro boxes largos.

    Não há uma letra sequer para ancorar, então o dicionário responderia com
    todas as palavras de quatro letras que ele tem — `ffes`, `offs`, `arts`,
    `ants`... A resposta certa é desistir, e é a mesma que o `MAX_TRECHOS` já
    dava quando a máscara sobrava pouca letra conhecida.
    """
    assert lexico.reparar(_simbolos("ffcx"), {0, 1, 2, 3}, lex) is None


def test_sem_ancora_a_prova_nem_e_consultada(lex):
    """
    Desistir **antes** da busca é o ponto da fase: era pagando a prova por cada
    candidato do balde inteiro que a exportação parava. Um `provar` que levanta
    exceção prova que ninguém chegou lá.
    """
    assert lexico.reparar(_simbolos("ffcx"), {0, 1, 2, 3}, lex,
                          _provar_que_recusa()) is None


def test_sem_prova_tambem_desiste(lex):
    """
    A régua é da máscara, e não da prova: o caminho da F66 — que decide por
    comprimento — tem o mesmo nada em que se apoiar, e já desistia no empate
    depois de pagar a busca. Agora desiste antes.
    """
    assert lexico.reparar(_simbolos("ffcx"), {0, 1, 2, 3}, lex) is None


def test_uma_ancora_basta(lex):
    """
    A régua é `todos`, e não `quase todos`: com uma letra fora da máscara o
    molde volta a estreitar, e o reparo continua sendo o da F69. `hamer` com
    três boxes largos ainda tem o `h` para ancorar, e `hammer` é o que o papel
    sustenta.
    """
    def provar(caixas, letras):
        return {"ammer": 0.95}.get(letras, 0.0)

    r = lexico.reparar(_simbolos("hamer"), {1, 2, 3, 4}, lex, provar)
    assert r is not None and r.corrigida == "hammer"


def test_a_ancora_pode_ser_a_ultima_letra(lex):
    """
    Ancorar não é "começar com letra conhecida": o trecho mascarado que vai do
    começo até a penúltima ainda deixa a última, e é ela que separa `hammer` de
    qualquer outra palavra de seis letras.
    """
    def provar(caixas, letras):
        return {"hamme": 0.95}.get(letras, 0.0)

    r = lexico.reparar(_simbolos("hamer"), {0, 1, 2, 3}, lex, provar)
    assert r is not None and r.corrigida == "hammer"


def test_os_reparos_da_pagina_nao_veem_a_palavra_sem_ancora(lex):
    """
    A produção chama `reparos_da_pagina`, e é por ela que a regra precisa
    valer — foi passando por cima dessa função que a F69 ficou montada e
    desligada.
    """
    from core.box_model import BoxEntry

    boxes = [BoxEntry(x1=i * 10, y1=0, x2=i * 10 + 9, y2=10, char=c)
             for i, c in enumerate("ffcx")]
    largos = {0, 1, 2, 3}
    assert lexico.reparos_da_pagina(boxes, largos, lex,
                                    _provar_que_recusa()) == []
