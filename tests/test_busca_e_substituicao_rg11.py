"""Busca e substituição (RG-11, R-29): um teste por item da spec.

- O "quantificador mínimo" trocava por regex sobre o regex: `a\\*b` virava `a\\*?b` e
  `(?:x)` virava `(??:x)`, que nem compila.
- Sem NFC: `cafe\\u0301` (NFD) não achava `café` (NFC).
- "Substituir tudo" num capítulo em modo código gravava um ponto de desfazer vazio.
- A caixa por palavra partia a palavra na fronteira de trecho: `nimzo` + **w** + `itsch`
  virava `NimzoWItsch`.
- A aspa depois de um espaço inseparável virava fechamento.
"""

import re

import pytest

from core.editor import busca, historico as historico_mod, modelo as m, tipografia


def _compilar(texto, **k):
    return busca.compilar(busca.Opcoes(texto=texto, regex=True, minimo=True, **k))


@pytest.mark.parametrize("texto, casa, nao_casa", [
    (r"a\*b", "a*b", "ab"),                   # o `*` escapado é literal (e não fica opcional)
    (r"(?:x)+y", "xxy", "y"),                 # o `?` do grupo não é quantificador
    (r"[*+?]z", "*z", "az"),                  # dentro da classe, nada é quantificador
    (r"(?P<n>a)+", "aa", "b"),
    (r"a{2,3}", "aa", "a"),
])
def test_o_quantificador_minimo_so_mexe_no_quantificador(texto, casa, nao_casa):
    padrao = _compilar(texto)
    assert padrao.search(casa) and not padrao.fullmatch(nao_casa)


def test_o_quantificador_minimo_fica_minimo():
    assert _compilar(r"<.+>").search("<a><b>").group(0) == "<a>"
    assert _compilar(r"a{2,3}").search("aaaa").group(0) == "aa"
    assert _compilar(r"x+?y").pattern.count("??") == 0          # já mínimo: não dobra


def test_a_busca_acha_o_que_esta_em_outra_forma_unicode():
    cap = m.Capitulo(arquivo="c.xhtml", blocos=[m.Paragrafo(trechos=[m.Trecho(texto="Um cafe\u0301 forte.")])])
    padrao = busca.compilar(busca.Opcoes(texto="café"))
    [ocorrencia] = busca.procurar_no_capitulo(cap, padrao)
    assert ocorrencia.alvo.texto[ocorrencia.ini:ocorrencia.fim] == "cafe\u0301"
    # E a troca cai no lugar certo: o resto do texto fica.
    n = busca.substituir_tudo_no_capitulo(cap, padrao, "chá", busca.Opcoes(texto="café"))
    assert n == 1 and m.texto_de(cap.blocos[0]) == "Um chá forte."
    padrao_nfd = busca.compilar(busca.Opcoes(texto="cafe\u0301"))
    cap2 = m.Capitulo(arquivo="d.xhtml", blocos=[m.Paragrafo(trechos=[m.Trecho(texto="Um café.")])])
    assert len(busca.procurar_no_capitulo(cap2, padrao_nfd)) == 1


def test_substituir_tudo_no_modo_codigo_grava_o_xhtml_de_antes_e_de_depois():
    antes = "<html><body><p>Lance ruim.</p></body></html>"
    cap = m.Capitulo(arquivo="c.xhtml", texto_cru=antes)
    hist = historico_mod.Historico()
    opcoes = busca.Opcoes(texto="ruim", substituto="bom")
    assert busca.substituir_tudo_no_capitulo(cap, busca.compilar(opcoes), "bom", opcoes, historico=hist) == 1
    assert "Lance bom." in cap.texto_cru
    ponto = hist.desfazer("c.xhtml")
    assert ponto is not None and ponto.antes and ponto.depois, "o ponto de desfazer saiu vazio"
    historico_mod.aplicar(cap, ponto, "antes")
    assert cap.texto_cru == antes
    historico_mod.aplicar(cap, hist.refazer("c.xhtml"), "depois")
    assert "Lance bom." in cap.texto_cru


def test_a_caixa_por_palavra_atravessa_os_trechos():
    p = m.Paragrafo(trechos=[m.Trecho(texto="nimzo"), m.Trecho(texto="w", negrito=True), m.Trecho(texto="itsch defende")])
    m.mudar_caixa(p, 0, len(m.texto_de(p)), "primeira")
    assert m.texto_de(p) == "Nimzowitsch Defende", m.texto_de(p)
    assert any(t.negrito and t.texto == "w" for t in p.trechos), "o negrito do meio se perdeu"


def test_a_aspa_depois_do_espaco_inseparavel_abre():
    texto = "disse\u00a0\"vamos\" e\u00a0'já'"
    trocas = {t.ini: t.para for t in tipografia._aspas(texto, "pt")}
    abre_d, _fecha_d, abre_s, _fecha_s = tipografia.ASPAS["pt"]
    assert trocas[texto.index('"')] == abre_d, "a aspa dupla depois do NBSP virou fechamento"
    assert trocas[texto.index("'")] == abre_s, "a aspa simples depois do NBSP virou fechamento"
    assert re.search("vamos", texto)


def test_na_janela_o_ctrl_z_do_modo_codigo_desfaz_o_substituir_tudo_do_livro():
    from tests.test_editor_janela import _Janela

    with _Janela() as t:
        j = t.j
        assert j.executar("modo_codigo") == "codigo"
        aba = j.aba_ativa()
        cap = j.projeto.livro.capitulo(aba.arquivo)
        cap.texto_cru = aba.widget.texto_todo()
        antes = cap.texto_cru
        opcoes = busca.Opcoes(texto="<body", substituto="<body data-trocado=\"1\"", maiusculas=True)
        n = busca.substituir_tudo_no_capitulo(cap, busca.compilar(opcoes), opcoes.substituto, opcoes,
                                              historico=j.projeto.historico)
        assert n == 1
        aba.widget.carregar(cap.texto_cru)                     # a aba reaberta depois da troca
        assert j._no_editor("desfazer") is True
        assert cap.texto_cru == antes and aba.widget.texto_todo().rstrip("\n") == antes.rstrip("\n")
        assert j._no_editor("refazer") is True and 'data-trocado="1"' in aba.widget.texto_todo()
