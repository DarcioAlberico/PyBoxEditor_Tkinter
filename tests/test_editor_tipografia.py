"""
Testes de `core/editor/tipografia.py` e `ui/editor/tipografia.py` (ED-06b; SPEC_EDITOR
§8.14): `"quoted" 1-0 ... 12.Nf3 O-O +-` → `“quoted” 1–0 … 12. Nf3 O‑O +-` (com o espaço
inseparável), `juntar_hifenizadas` sobre "cava-" / "lo" → "cavalo", e a hifenização que
liga `hyphens: auto` na folha e `w:autoHyphenation` no DOCX (AC-ED06b-1); as exceções de
xadrez; a prévia por ocorrência com desmarcar; o desfazer por capítulo.

Rodar sem pytest:      python tests/test_editor_tipografia.py
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m, tipografia
from core.editor.historico import Historico, aplicar
from core.editor.modelo import Capitulo, Livro, Metadados, Paragrafo, Recurso, Trecho
from editor_ambiente import Janela
from ui.editor.tipografia import DialogoDeTipografia

NBSP = chr(0xA0)
HNB = chr(0x2011)


def _p(*trechos, **kw):
    return Paragrafo(trechos=[t if isinstance(t, Trecho) else Trecho(texto=t) for t in trechos], **kw)


class _LexicoFalso:
    def __init__(self, palavras):
        self.palavras = {p.lower() for p in palavras}
        self.do_usuario = set()
        self.vazio = not palavras
        self.sinaliza = True

    def conhece(self, palavra):
        return palavra.lower() in self.palavras


# ----------------------------------------------------------------------
# AC-ED06b-1
# ----------------------------------------------------------------------

def test_ac1_a_frase_da_spec_e_as_excecoes_de_xadrez():
    texto = '"quoted" 1-0 ... 12.Nf3 O-O +-'
    trocas = tipografia.propor(texto, "en")
    assert tipografia.aplicar(texto, trocas) == f"“quoted” 1–0 … 12.{NBSP}Nf3 O{HNB}O +-"
    assert [t.motivo for t in trocas] == ["aspas", "aspas", "travessao", "reticencias", "espaco_lance", "roque"]
    # `+-` e `-+` são NAGs; `0-0` e `0-0-0` são roques; `0-1` e `½-½` são resultados; `12. Nf3` já com espaço
    assert tipografia.aplicar("+- -+ 0-0 0-0-0 0-1 ½-½ 12. Nf3", tipografia.propor("+- -+ 0-0 0-0-0 0-1 ½-½ 12. Nf3")) \
        == f"+- -+ 0{HNB}0 0{HNB}0{HNB}0 0–1 ½–½ 12.{NBSP}Nf3"
    # "2012. Now" não é número de lance; um intervalo de anos leva meia-risca; " - " também
    assert tipografia.aplicar("em 2012. Now 1990-1995 a - b", tipografia.propor("em 2012. Now 1990-1995 a - b")) \
        == "em 2012. Now 1990–1995 a – b"
    # "Diagrama 12" ganha o inseparável; o apóstrofo vira curvo; aspas simples abrem e fecham
    assert tipografia.aplicar("Diagrama 12 e Black's 'x'", tipografia.propor("Diagrama 12 e Black's 'x'", "en")) \
        == f"Diagrama{NBSP}12 e Black’s ‘x’"
    # aspas por idioma
    assert tipografia.aplicar('"a"', tipografia.propor('"a"', "de")) == "„a“"
    assert tipografia.aplicar('"a"', tipografia.propor('"a"', "fr")) == f"«{NBSP}a{NBSP}»"
    # o que já está certo não gera troca; as regras podem ser escolhidas
    assert tipografia.propor(f"“quoted” 12.{NBSP}Nf3 O{HNB}O") == []
    assert [t.motivo for t in tipografia.propor(texto, "en", regras=("roque",))] == ["roque"]


def test_ac1_juntar_hifenizadas_cava_lo_da_cavalo_dentro_e_entre_paragrafos():
    lex = _LexicoFalso(["cavalo", "o", "salta", "bispo", "dorme", "e"])
    cap = Capitulo(arquivo="c.xhtml", blocos=[
        _p("o cava-", Trecho(texto="lo salta", quebra_antes=True)),
        _p("e o bis-"), _p("po dorme"), _p("well-", Trecho(texto="known", quebra_antes=True))])
    pares = tipografia.propor_juncoes(cap, lex)
    assert [(a.bloco_id == cap.blocos[k].id, t.de, t.para) for (a, t), k in zip(pares, (0, 1, 2))] == [
        (True, "cava-\nlo", "cavalo"), (True, "bis-", "bispo"), (True, "po ", "")]
    n = tipografia.aplicar_no_capitulo(cap, pares)
    assert n == 3 and [m.texto_de(b) for b in cap.blocos] == ["o cavalo salta", "e o bispo", "dorme",
                                                             "well-\nknown"]
    assert tipografia.propor_juncoes(cap, _LexicoFalso([])) == []


def test_ac1_hifenizar_liga_hyphens_auto_na_folha_e_autohyphenation_no_docx(tmp_path):
    pytest.importorskip("docx")
    from core.editor import docx_io

    css = "p { text-indent: 1em; }\n"
    livro = Livro(metadados=Metadados(titulo="T"), capitulos=[Capitulo(arquivo="c.xhtml", blocos=[_p("Texto.")])],
                  folhas=["estilo.css"], recursos={"estilo.css": Recurso(caminho="estilo.css", tipo_mime="text/css",
                                                                          dados=css.encode("utf-8"))})
    livro.pagina.hifenizar = True
    assert tipografia.aplicar_hifenizacao(livro) is True
    folha = livro.recursos["estilo.css"].texto_cru
    assert folha.startswith(css) and "hyphens: auto" in folha and tipografia.MARCA_DA_HIFENIZACAO in folha
    assert tipografia.aplicar_hifenizacao(livro) is False       # idempotente
    livro.pagina.hifenizar = False
    assert tipografia.aplicar_hifenizacao(livro) is True and livro.recursos["estilo.css"].texto_cru == css
    livro.pagina.hifenizar = True
    tipografia.aplicar_hifenizacao(livro)
    caminho = str(tmp_path / "t.docx")
    docx_io.escrever(livro, caminho)
    with zipfile.ZipFile(caminho) as z:
        assert b"w:autoHyphenation" in z.read("word/settings.xml")


# ----------------------------------------------------------------------
# No capítulo e no livro: alvos, código e ilha ficam fora, um ponto por capítulo
# ----------------------------------------------------------------------

def test_propor_capitulo_pula_codigo_e_ilha_e_aplicar_registra_um_ponto_por_capitulo():
    cap = Capitulo(arquivo="c.xhtml", blocos=[
        _p('Ele disse "sim"... ', Trecho(texto='"code"', codigo=True), Trecho(ilha="<cite>x</cite>")),
        m.Lista(ordenada=False, itens=[m.ItemDeLista(paragrafos=[_p("1-0 e O-O")])]),
    ], notas=[m.Nota(id="n1", blocos=[_p("nota 12.Nf3")])], idioma="pt")
    pares = tipografia.propor_capitulo(cap)
    motivos = [(a.caminho[0], t.motivo) for a, t in pares]
    assert motivos == [("bloco", "aspas"), ("bloco", "aspas"), ("bloco", "reticencias"), ("lista", "travessao"),
                       ("lista", "roque"), ("nota", "espaco_lance")]
    historico = Historico()
    assert tipografia.aplicar_no_capitulo(cap, pares, historico) == 6
    assert m.texto_de(cap.blocos[0]) == 'Ele disse “sim”… "code"'
    assert m.texto_de(cap.blocos[1]) == f"1–0 e O{HNB}O" and m.texto_de(cap.notas[0]) == f"nota 12.{NBSP}Nf3"
    ponto = historico.desfazer("c.xhtml")
    assert ponto is not None and set(ponto.ids) == {cap.blocos[0].id, cap.blocos[1].id, "n1"}
    aplicar(cap, ponto, "antes")
    assert m.texto_de(cap.blocos[0]) == 'Ele disse "sim"... "code"'
    livro = Livro(metadados=Metadados(titulo="T", idioma="pt"), capitulos=[cap, Capitulo(arquivo="d.xhtml",
                                                                                         blocos=[_p("nada")])])
    assert list(tipografia.propor_livro(livro)) == ["c.xhtml"]


# ----------------------------------------------------------------------
# Na janela: a prévia por ocorrência, o desfazer, a hifenização
# ----------------------------------------------------------------------

def test_a_caixa_marca_e_desmarca_e_o_comando_aplica_so_o_marcado():
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.carregar(Capitulo(arquivo="cap1.xhtml", blocos=[_p('"um" 1-0'), _p("O-O ... fim")], idioma="pt"))
        propostas = j.tipografo.propostas("capitulo")
        assert [p[3].motivo for p in propostas] == ["aspas", "aspas", "travessao", "roque", "reticencias"]
        caixa = DialogoDeTipografia(j, propostas, tipografia.REGRAS, False)
        caixa.construir()
        assert caixa.arvore.set("0", "ok") == "☑" and "1 de 5" not in caixa.rotulo.cget("text")
        caixa.marcar(2, False)
        caixa.marcar_todas(True)
        caixa.marcar(4, False)
        assert caixa.arvore.set("4", "ok") == "☐" and caixa.rotulo.cget("text").startswith("4 de 5")
        caixa.var_regras["roque"].set(False)
        escolhidas, regras, hifenizar = caixa.confirmar()
        assert escolhidas == [0, 1, 2, 3] and "roque" not in regras and hifenizar is False
        # o comando com a resposta injetada: sem o roque (regra desmarcada) e sem as reticências (desmarcada)
        j.caixas.tipografia = lambda propostas, regras, hifenizar: ([0, 1, 2, 3], tuple(r for r in regras
                                                                                     if r != "roque"), False)
        contagem = j.executar("tipografia", "capitulo")
        assert contagem == {"cap1.xhtml": 3}
        assert [m.texto_de(b) for b in texto.sincronizar().blocos] == ["“um” 1–0", "O-O ... fim"]
        assert t.settings.get("editor")["tipografia"] == [r for r in tipografia.REGRAS if r != "roque"]
        # um desfazer só devolve as três
        assert j.executar("desfazer") and m.texto_de(texto.sincronizar().blocos[0]) == '"um" 1-0'


def test_no_livro_o_capitulo_fechado_muda_pelo_modelo_e_a_hifenizacao_vai_para_a_folha():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        cap2 = livro.capitulo("cap2.xhtml")
        cap2.blocos.append(_p('"aspas" no cap2 ...'))
        # o livro completo não tem folha: uma folha padrão para a hifenização ter onde entrar
        livro.recursos["estilo.css"] = Recurso(caminho="estilo.css", tipo_mime="text/css",
                                               dados=b"p { text-indent: 1em; }\n")
        livro.folhas = ["estilo.css"]
        j._atualizar_painel_de_estilos()
        j.caixas.tipografia = lambda propostas, regras, hifenizar: (list(range(len(propostas))), regras, True)
        contagem = j.executar("tipografia", "livro")
        assert contagem.get("cap2.xhtml", 0) == 3 and j.projeto.historico.pode_desfazer("cap2.xhtml")
        assert m.texto_de(cap2.blocos[-1]) == "“aspas” no cap2 …"
        assert livro.pagina.hifenizar is True
        folha = livro.recurso(livro.folhas[0]).texto_cru
        assert folha and "hyphens: auto" in folha and j.painel_de_estilos.folha_padrao == folha
        assert j.projeto.sujo
        # "Juntar palavras hifenizadas" com o léxico de mentira
        t.texto.carregar(Capitulo(arquivo="cap1.xhtml", blocos=[_p("o cava-"), _p("lo salta")], idioma="pt"))
        lex = _LexicoFalso(["cavalo", "o", "salta"])

        class _Lexicos:
            ignoradas = set()

            def __call__(self, idioma):
                return lex

        j.lexicos = lambda: _Lexicos()
        j.caixas.tipografia = lambda propostas, regras, hifenizar: (list(range(len(propostas))), regras, True)
        assert j.executar("juntar_hifenizadas") == {"cap1.xhtml": 2}
        assert [m.texto_de(b) for b in t.texto.sincronizar().blocos] == ["o cavalo", "salta"]
        # sem nada para juntar, informa
        assert j.executar("juntar_hifenizadas") == {} and any(c[0] == "informar" for c in t.caixas.chamadas)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
