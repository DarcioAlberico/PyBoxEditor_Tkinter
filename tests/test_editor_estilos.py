"""
Testes de `ui/editor/estilos.py` (ED-03; §8.4, AC-ED03-11): o painel lista os estilos
da §6.3 e os da folha, aplica, grava `p.destaque { … }` na folha padrão ao criar um
estilo a partir da seleção, e "selecionar tudo com este estilo" seleciona os três.

Rodar sem pytest:      python tests/test_editor_estilos.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from core.editor import css_minima, dialeto, modelo as m
from ui.editor.estilos import PainelDeEstilos
from ui.editor.texto_rico import TextoRico


def _p(texto, **kw):
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


def test_ac11_novo_estilo_grava_na_folha_o_painel_lista_e_seleciona_tudo_com_ele():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        folha = "p { text-indent: 1.2em; }\np.epigrafe { font-style: italic }\n.minha { color: #123456 }\n"
        gravacoes = []
        texto = TextoRico(raiz, folhas={"Styles/estilo.css": folha})
        texto.pack()
        texto.carregar(m.Capitulo(arquivo="Text/c.xhtml", blocos=[_p("um"), _p("dois"), _p("três"), _p("quatro")]))
        painel = PainelDeEstilos(raiz, texto, folha_padrao=folha, ao_gravar=gravacoes.append)
        painel.pack()
        nomes = painel.estilos()
        assert nomes[: len(dialeto.ESTILOS_DE_PARAGRAFO)] == list(dialeto.ESTILOS_DE_PARAGRAFO)
        assert "minha" in nomes and "epigrafe" in nomes and nomes.count("epigrafe") == 1
        assert painel.lista.size() == len(nomes) and int(painel.lista.cget("highlightthickness")) == 2
        # Aplicar um estilo da §6.3 pelo painel.
        p0 = texto.ordem[0]
        texto.ir_para(p0, 0)
        painel.escolher("titulo2")
        assert painel.escolhido() == "titulo2" and painel.aplicar() == [p0]
        assert isinstance(texto.sincronizar().blocos[0], m.Titulo)
        # Novo estilo a partir da seleção: negrito e cor no cursor → `p.destaque { … }` na folha padrão.
        p1 = texto.ordem[1]
        texto.ir_para(p1, 0)
        texto.selecionar(0, 4)
        texto.alternar("negrito")
        texto.aplicar(cor="#c00000")
        texto.ir_para(p1, 2)
        nova_folha = painel.novo_estilo_da_selecao("destaque")
        assert gravacoes == [nova_folha]
        regra = css_minima.ler(nova_folha).regra("p.destaque")
        assert regra is not None and regra.declaracoes["font-weight"] == "bold" and regra.declaracoes["color"] == "#c00000"
        assert nova_folha.startswith(folha)                                   # o resto da folha ficou como estava
        assert "destaque" in painel.estilos() and painel.escolhido() == "destaque"
        assert texto.sincronizar().blocos[1].classe == "destaque"
        assert painel.regra_de("destaque").startswith("p.destaque {")
        # Aplicar o estilo da folha a mais dois blocos e selecionar tudo com ele: três.
        for bloco_id in texto.ordem[2:4]:
            texto.ir_para(bloco_id, 0)
            painel.aplicar("destaque")
        assert painel.selecionar_tudo_com("destaque") == 3
        selecao = texto.texto.tag_ranges("sel")
        assert len(selecao) == 6                                              # três intervalos
        assert painel.selecionar_tudo_com("titulo2") == 1 and painel.selecionar_tudo_com("legenda") == 0
        with pytest.raises(ValueError):
            painel.novo_estilo_da_selecao("nome inválido!")
        with pytest.raises(ValueError):
            painel.escolher("nada")
    finally:
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
