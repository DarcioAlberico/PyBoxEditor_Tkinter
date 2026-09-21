"""
Testes de `core/editor/ortografia.py` e `ui/editor/ortografia.py` (ED-06; SPEC_EDITOR
§8.13): `verificar` acusa só `knigt` em "The knigt plays 12.Nf3 ♘c6 ±" (AC-ED06-3), a
peneira de notação copiada bate com `core.notacao.e_token_de_notacao`, o `lang="pt"`
usa o léxico `pt` (vazio até a ED-06b → nada acusado), "Adicionar" grava em
`livro.lexico.txt`, e o `F7` com respostas injetadas (Ignorar / Ignorar todas /
Adicionar / Trocar) altera só o que deve — mais o sublinhado `orto`, o modo código em
Resultados e a caixa do dicionário.

Rodar sem pytest:      python tests/test_editor_ortografia.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m, ortografia
from core.editor.modelo import Capitulo, Paragrafo, Trecho
from editor_ambiente import Janela
from ui.editor import ortografia as orto_ui


def _p(*trechos, **kw):
    return Paragrafo(trechos=[t if isinstance(t, Trecho) else Trecho(texto=t) for t in trechos], **kw)


class _LexicoFalso:
    """Um léxico de mentira: conhece o que está na lista; `sinaliza` conforme pedido."""

    def __init__(self, palavras, sinaliza=True):
        self.palavras = {p.lower() for p in palavras}
        self.do_usuario = set()
        self.sinaliza = sinaliza
        self.vazio = not palavras

    def conhece(self, palavra):
        b = palavra.lower()
        return b in self.palavras or b in self.do_usuario

    def acrescentar(self, palavra):
        self.do_usuario.add(palavra.lower())
        return True


# ----------------------------------------------------------------------
# AC-ED06-3: o que é palavra e o que fica fora
# ----------------------------------------------------------------------

def test_ac3_verificar_acusa_so_knigt_na_frase_com_notacao_figurina_e_nag():
    cap = Capitulo(arquivo="c.xhtml", blocos=[_p("The knigt plays 12.Nf3 ♘c6 ±")], idioma="en")
    lex = _LexicoFalso(["the", "plays"])
    suspeitas = ortografia.verificar(cap, lambda idioma: lex)
    assert [(s.palavra, s.ini, s.fim, s.idioma) for s in suspeitas] == [("knigt", 4, 9, "en")]
    assert suspeitas[0].contexto.startswith("The knigt plays")
    assert suspeitas[0].alvo.caminho == ("bloco",)


def test_a_peneira_copiada_bate_com_a_de_core_notacao():
    from core import notacao

    tokens = ("12.Nf3", "Nf3", "e4", "exd5", "O-O", "0-0-0", "1-0", "½-½", "+-", "!?", "±", "Nimzowitsch", "12...",
              "3.", "e4!", "Bxf7+", "knight", "a1]d", "hello", "Kb1", "12.Nf3,", "(Nf3)", "♘c6", "=", "Ke2#",
              "e8=Q", "cavalo", "ECO", "1/2-1/2", "12.", "...", "a-b", "Nimzo-Indian", "Black's")
    assert [ortografia.e_notacao(t) for t in tokens] == [notacao.e_token_de_notacao(t) for t in tokens]


def test_ficam_fora_numeros_maiusculas_codigo_ilha_e_os_papeis_de_xadrez():
    cap = Capitulo(arquivo="c.xhtml", blocos=[_p(
        "FIDE 2024 abc123 ", Trecho(texto="xyzzy", papel="lance"), " ", Trecho(texto="qqq", papel="nag"),
        " ", Trecho(texto="Karpov", papel="jogador"), " ", Trecho(texto="printf", codigo=True), " ",
        Trecho(ilha="<cite>zzz</cite>"), " normalword badwrd")], idioma="en")
    lex = _LexicoFalso(["normalword"])
    assert [s.palavra for s in ortografia.verificar(cap, lambda i: lex)] == ["badwrd"]
    # a legenda de uma figura e as células de uma tabela também são verificadas
    cap2 = Capitulo(arquivo="c.xhtml", blocos=[
        m.Figura(recurso="Images/x.png", legenda=[Trecho(texto="A legnda")]),
        m.Tabela(filas=[[m.Celula(blocos=[_p("celula errda")])]])])
    assert [s.palavra for s in ortografia.verificar(cap2, lambda i: _LexicoFalso(["a", "celula"]))] == ["legnda",
                                                                                                     "errda"]


def test_conhecida_aceita_hifen_e_apostrofo_por_partes():
    lex = _LexicoFalso(["black", "nimzo", "indian", "don"])
    assert ortografia.conhecida("Black's", lex) and ortografia.conhecida("Nimzo-Indian", lex)
    assert ortografia.conhecida("don't", lex) and not ortografia.conhecida("Nimzo-Indiann", lex)
    assert not ortografia.conhecida("blacks", lex)


def test_o_lang_do_trecho_escolhe_o_lexico_e_o_pt_vazio_nao_acusa_nada(tmp_path):
    cap = Capitulo(arquivo="c.xhtml", blocos=[_p(Trecho(texto="palavra errrada ", lang="pt"), "and wrng")],
                   idioma="en")
    pedidos = []

    def lexico_de(idioma):
        pedidos.append(idioma)
        return _LexicoFalso(["and"]) if idioma == "en" else _LexicoFalso([], sinaliza=False)

    assert [(s.palavra, s.idioma) for s in ortografia.verificar(cap, lexico_de)] == [("wrng", "en")]
    assert set(pedidos) == {"pt", "en"}
    # os léxicos de verdade: o `en` sinaliza; o `pt` (sem `assets/lexico/pt.txt.gz`) fica vazio e quieto
    lexicos = ortografia.Lexicos(str(tmp_path / "livro.epub"))
    assert lexicos("en").sinaliza
    if ortografia.caminho_do_lexico("pt") is None:
        assert not lexicos("pt").sinaliza
        assert [s.palavra for s in ortografia.verificar(cap, lexicos)] == ["wrng"]


def test_adicionar_grava_em_livro_lexico_txt_e_remover_tira(tmp_path):
    lexicos = ortografia.Lexicos(str(tmp_path / "livro.epub"))
    assert lexicos.adicionar("Nimzowitsch") is True
    caminho = tmp_path / "livro.lexico.txt"
    assert caminho.exists() and caminho.read_text(encoding="utf-8").strip() == "nimzowitsch"
    assert lexicos("en").conhece("Nimzowitsch") and lexicos.palavras_do_livro() == ["nimzowitsch"]
    # um léxico novo do mesmo livro lê o arquivo
    outros = ortografia.Lexicos(str(tmp_path / "livro.epub"))
    assert outros("en").conhece("nimzowitsch")
    assert outros.remover("nimzowitsch") is True and caminho.read_text(encoding="utf-8").strip() == ""
    # sem caminho do livro, não há onde gravar
    with pytest.raises(ValueError, match="salve o livro"):
        ortografia.Lexicos(None).adicionar("x")
    assert ortografia.caminho_do_dicionario(None) is None
    assert ortografia.caminho_do_dicionario("/tmp/a.epub").replace("\\", "/").endswith("/tmp/a.lexico.txt")


def test_sugestoes_do_lexico_en_dao_knight_para_knigt():
    lexicos = ortografia.Lexicos(None)
    assert lexicos.sugestoes("knigt", "en")[0] == "knight"
    assert lexicos.sugestoes("Knigt", "en")[0] == "Knight"


# ----------------------------------------------------------------------
# O F7 na janela, com respostas injetadas
# ----------------------------------------------------------------------

def _janela_com_lexico_falso(t, palavras):
    j = t.j
    lex = _LexicoFalso(palavras)

    class _Lexicos:
        caminho_do_livro = j.projeto.caminho
        ignoradas = set()

        def __call__(self, idioma):
            return lex

        def carregar(self, idioma):
            return lex

        def sugestoes(self, palavra, idioma, n=5):
            return {"errda": ["errada", "errado"], "Ideeia": ["Ideia"]}.get(palavra, [])

        def ignorar(self, palavra):
            self.ignoradas.add(palavra.lower())

        def adicionar(self, palavra):
            return lex.acrescentar(palavra)

        def palavras_do_livro(self):
            return sorted(lex.do_usuario)

        def remover(self, palavra):
            lex.do_usuario.discard(palavra.lower())
            return True

    lexicos = _Lexicos()
    j.lexicos = lambda: lexicos
    return lexicos


def test_f7_com_respostas_injetadas_altera_so_o_que_deve():
    with Janela() as t:
        j = t.j
        texto = t.texto
        # um capítulo só com o que interessa: quatro parágrafos, cinco palavras desconhecidas
        cap = Capitulo(arquivo="cap1.xhtml", blocos=[
            _p("Uma frase errda aqui."), _p("A mesma errda de novo, e Ideeia."),
            _p("Nimzowitsch venceu."), _p("Tudo certo neste.")], idioma="pt")
        texto.carregar(cap)
        conhecidas = ["uma", "frase", "aqui", "a", "mesma", "de", "novo", "e", "venceu", "tudo", "certo", "neste",
                      "errada", "ideia"]
        lexicos = _janela_com_lexico_falso(t, conhecidas)
        respostas = iter([("trocar", "errada"), ("ignorar", ""), ("trocar_todas", "Ideia"), ("adicionar", "")])
        perguntadas = []

        def perguntar(suspeita, sugestoes):
            perguntadas.append((suspeita.palavra, list(sugestoes)))
            return next(respostas)

        j.caixas.ortografia = perguntar
        j.caixas.ortografia_fim = lambda: None
        contagem = j.executar("ortografia")
        assert [p[0] for p in perguntadas] == ["errda", "errda", "Ideeia", "Nimzowitsch"]
        assert perguntadas[0][1] == ["errada", "errado"]
        assert contagem == {"suspeitas": 4, "trocadas": 2, "adicionadas": 1, "ignoradas": 1}
        textos = [m.texto_de(b) for b in texto.sincronizar().blocos]
        assert textos == ["Uma frase errada aqui.", "A mesma errda de novo, e Ideia.", "Nimzowitsch venceu.",
                          "Tudo certo neste."]
        assert lexicos("pt").conhece("Nimzowitsch") and texto.sujo
        # o sublinhado `orto` fica só na palavra ignorada
        faixas = texto.texto.tag_ranges("orto")
        assert len(faixas) == 2 and texto.texto.get(faixas[0], faixas[1]) == "errda"
        # o desfazer devolve uma troca de cada vez
        assert j.executar("desfazer") and [m.texto_de(b) for b in texto.sincronizar().blocos][1].endswith("Ideeia.")


def test_f7_ignorar_todas_trocar_todas_e_fechar():
    with Janela() as t:
        j = t.j
        texto = t.texto
        cap = Capitulo(arquivo="cap1.xhtml", blocos=[_p("xpto e xpto e zzz e zzz."), _p("xpto de novo e zzz.")],
                       idioma="pt")
        texto.carregar(cap)
        lexicos = _janela_com_lexico_falso(t, ["e", "de", "novo"])
        respostas = iter([("ignorar_todas", ""), ("trocar_todas", "ZZZ"), ("fechar", "")])
        perguntadas = []

        def perguntar(suspeita, sugestoes):
            perguntadas.append(suspeita.palavra)
            return next(respostas)

        j.caixas.ortografia = perguntar
        j.caixas.ortografia_fim = lambda: None
        contagem = j.executar("ortografia")
        assert perguntadas == ["xpto", "zzz"]
        assert contagem["trocadas"] == 3 and "xpto" in lexicos.ignoradas
        assert [m.texto_de(b) for b in texto.sincronizar().blocos] == ["xpto e xpto e ZZZ e ZZZ.",
                                                                        "xpto de novo e ZZZ."]
        # a segunda passada, com tudo ignorado, informa que não há nada
        respostas = iter([("fechar", "")])
        contagem = j.executar("ortografia")
        assert contagem["suspeitas"] == 0 and any(c[0] == "informar" for c in t.caixas.chamadas)


def test_no_codigo_as_suspeitas_vao_a_resultados_com_a_linha():
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.carregar(Capitulo(arquivo="cap1.xhtml", blocos=[_p("Tudo certo."), _p("Palavra errda.")],
                                idioma="pt"))
        _janela_com_lexico_falso(t, ["tudo", "certo", "palavra"])
        j.executar("alternar_modo")
        contagem = j.executar("ortografia")
        assert contagem["suspeitas"] == 1 and len(j.resultados) == 1
        item = j.resultados.itens[0]
        assert item.onde.startswith("linha ") and "errda" in item.mensagem and item.dados["linha"] > 1


def test_marcar_poe_a_tag_orto_e_a_caixa_do_dicionario_acrescenta_e_remove():
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.carregar(Capitulo(arquivo="cap1.xhtml", blocos=[_p("Uma errda e outra errda.")], idioma="pt"))
        lexicos = _janela_com_lexico_falso(t, ["uma", "e", "outra"])
        suspeitas = ortografia.verificar(texto.sincronizar(), lexicos, "pt")
        assert orto_ui.marcar(texto, suspeitas) == 2
        faixas = texto.texto.tag_ranges("orto")
        assert [texto.texto.get(faixas[i], faixas[i + 1]) for i in range(0, 4, 2)] == ["errda", "errda"]
        orto_ui.desmarcar(texto)
        assert not texto.texto.tag_ranges("orto")
        # a caixa do dicionário, construída sem mostrar
        caixa = orto_ui.DialogoDoDicionario(j, lexicos)
        caixa.construir()
        assert caixa.recarregar() == []
        assert caixa.adicionar("errda") is True and caixa.recarregar() == ["errda"]
        assert caixa.remover("errda") is True and caixa.recarregar() == []
        caixa.cancelar()
        # e o comando do menu chama `caixas.dicionario` com os léxicos
        chamadas = []
        j.caixas.dicionario = lambda lex: chamadas.append(lex)
        assert j.executar("dicionario") is lexicos and chamadas == [lexicos]


def test_a_caixa_do_f7_responde_sem_esperar():
    with Janela() as t:
        j = t.j
        caixa = orto_ui.DialogoDeOrtografia(j)
        cap = Capitulo(arquivo="c.xhtml", blocos=[_p("The knigt plays")])
        s = ortografia.verificar(cap, lambda i: _LexicoFalso(["the", "plays"]))[0]
        caixa.mostrar_suspeita(s, ["knight", "knit"])
        assert caixa.var_palavra.get() == "knigt" and caixa.var_troca.get() == "knight"
        assert caixa.responder("trocar") == ("trocar", "knight")
        assert caixa.responder("trocar", "knights") == ("trocar", "knights")
        with pytest.raises(ValueError):
            caixa.responder("lua")
        caixa.fechar()
        assert caixa.top is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
