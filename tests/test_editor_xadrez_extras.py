"""
Testes da ED-05b (SPEC_EDITOR §11.1, §11.7, §11.10): marcas e setas no PNG (pixels),
salvas e reabertas, com o aviso em modo `fonte` e a caixa "Marcas e setas…" (AC-ED05b-1);
a legenda sugerida com o lado proposto e **não** gravado (AC-ED05b-2); a chave de símbolos
com `±`, `⩲` e `!?` marcados e digitados, `epub:type="glossary"`, refeita no lugar
(AC-ED05b-3).

Rodar sem pytest:      python tests/test_editor_xadrez_extras.py
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import epub, modelo as m, xadrez, xhtml
from editor_ambiente import Janela

FEN_LOPEZ = "r1bqkbnr/1ppp1ppp/p1n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4"


def p(texto, **kw):
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


def _cinza(png):
    from PIL import Image

    return Image.open(io.BytesIO(png)).convert("L")


# ----------------------------------------------------------------------
# AC-ED05b-1
# ----------------------------------------------------------------------

def test_ac1_marcas_e_setas_saem_no_png_voltam_do_epub_e_avisam_em_fonte(tmp_path):
    from core import render_diagrama as rd

    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
    png, largura, altura = rd.desenhar(fen, lado_px=256, marcas=["e4"], setas=[("g1", "f3")])
    img = _cinza(png)
    limpo = _cinza(rd.desenhar(fen, lado_px=256)[0])
    assert (largura, altura) == limpo.size
    casa = 32
    _tracos, margem = rd.filetes("simples", casa)
    cx, cy = rd._casa_xy("e4", margem, margem, casa, "branca")
    raio = casa * 0.40
    assert img.getpixel((int(cx + raio), int(cy))) <= 100 < limpo.getpixel((int(cx + raio), int(cy)))  # o anel
    assert img.getpixel((int(cx), int(cy))) == limpo.getpixel((int(cx), int(cy)))                       # o miolo
    ax, ay = rd._casa_xy("g1", margem, margem, casa, "branca")
    bx, by = rd._casa_xy("f3", margem, margem, casa, "branca")
    meio = (int((ax + bx) / 2), int((ay + by) / 2))
    assert img.getpixel(meio) <= 100 < limpo.getpixel(meio)                                             # a seta
    # girado: a marca acompanha a casa
    girado = _cinza(rd.desenhar(fen, lado_px=256, marcas=["e4"], orientacao="preta")[0])
    gx, gy = rd._casa_xy("e4", margem, margem, casa, "preta")
    assert girado.getpixel((int(gx + raio), int(gy))) <= 100
    # o que não é casa é ignorado sem erro
    assert rd.desenhar(fen, lado_px=64, marcas=["z9", "e"], setas=[("a1", "a1"), ("x", "y")])[1:] == rd.desenhar(
        fen, lado_px=64)[1:]

    # o modelo: salvo e reaberto, com o aviso em fonte
    livro = editor_livros.livro_completo()
    cap = livro.capitulos[0]
    cap.blocos = [m.Titulo(trechos=[m.Trecho(texto="T")], nivel=1),
                  m.Diagrama(fen=FEN_LOPEZ, marcas=["e4", "d5"], setas=[("g1", "f3"), ("e2", "e4")], modo="png"),
                  m.Diagrama(fen=FEN_LOPEZ, marcas=["e4"], modo="fonte", fonte="SkakNew-Diagram")]
    xadrez.conferir_marcas(cap.blocos[2])
    assert cap.blocos[2].aviso == xadrez.AVISO_DE_MARCAS == "marcas e setas não saem em fonte"
    assert xadrez.conferir_marcas(cap.blocos[1]).aviso == ""
    caminho = str(tmp_path / "marcas.epub")
    epub.escrever(livro, caminho)
    relido, _r = epub.ler(caminho)
    d1, d2 = [b for b in relido.capitulos[0].blocos if isinstance(b, m.Diagrama)]
    assert d1.marcas == ["e4", "d5"] and [tuple(s) for s in d1.setas] == [("g1", "f3"), ("e2", "e4")]
    assert d2.marcas == ["e4"] and d2.aviso == xadrez.AVISO_DE_MARCAS
    assert 'data-marcas="e4 d5"' in xhtml.escrever(cap) and 'data-setas="g1f3 e2e4"' in xhtml.escrever(cap)
    # o PNG do EPUB leva as marcas: mais tinta que o mesmo diagrama sem elas
    com, _w, _h = epub.png_do_diagrama(d1)
    sem, _w, _h = epub.png_do_diagrama(m.Diagrama(fen=FEN_LOPEZ, modo="png"))
    assert sum(1 for v in _cinza(com).getdata() if v <= 100) > sum(1 for v in _cinza(sem).getdata() if v <= 100)
    # o aviso vai e volta com o modo, sem apagar outro aviso
    d = m.Diagrama(fen=FEN_LOPEZ, modo="fonte", setas=[("a1", "h8")], aviso="posição a revisar")
    assert xadrez.conferir_marcas(d).aviso == "posição a revisar; " + xadrez.AVISO_DE_MARCAS
    d.modo = "png"
    assert xadrez.conferir_marcas(d).aviso == "posição a revisar"
    # o texto das caixas
    assert xadrez.analisar_marcas(" E4, d5 ;f7 e4 zz ") == ["e4", "d5", "f7"]
    assert xadrez.analisar_setas("g1-f3 e2→e4, c6xd4 a1-a1 h8-->h1") == [("g1", "f3"), ("e2", "e4"), ("c6", "d4"),
                                                                        ("h8", "h1")]
    assert xadrez.texto_das_marcas(d1) == "e4 d5" and xadrez.texto_das_setas(d1) == "g1-f3 e2-e4"


def test_ac1_o_comando_e_a_caixa_de_marcas_e_setas_na_janela():
    from ui.editor.diagrama import DialogoDeMarcasESetas

    with Janela() as t:
        j = t.j
        texto = t.texto
        d = next(b for b in texto.sincronizar().blocos if isinstance(b, m.Diagrama))
        texto.selecionar_objeto(d.id)
        # com a caixa injetada
        t.caixas.marcas_resposta = m.Diagrama(fen=d.fen, marcas=["e4"], setas=[("g1", "f3")])
        novo = j.executar("marcas_e_setas")
        assert novo.marcas == ["e4"] and novo.setas == [("g1", "f3")] and t.caixas.chamadas[-1][0] == "marcas_e_setas"
        atual = texto.modelo_de(d.id)
        assert atual.marcas == ["e4"] and atual.setas == [("g1", "f3")] and atual.aviso == ""
        widget = texto.widget_do_objeto(d.id)
        assert len(widget.canvas.find_withtag("marca")) == 1 and len(widget.canvas.find_withtag("seta")) == 1
        # por argumento (o que a caixa devolve), com o que não é casa fora
        texto.selecionar_objeto(d.id)
        novo = j.executar("marcas_e_setas", ["d5", "zz"], [("e2", "e4"), ("a1", "a1")])
        assert novo.marcas == ["d5"] and novo.setas == [("e2", "e4")]
        # num diagrama em fonte fica o aviso, na tela também
        fonte = next(b for b in texto.sincronizar().blocos if isinstance(b, m.Diagrama) and b.modo == "fonte")
        texto.selecionar_objeto(fonte.id)
        novo = j.executar("marcas_e_setas", ["e4"], [])
        assert novo.aviso == xadrez.AVISO_DE_MARCAS
        avisos = [w.cget("text") for w in texto.widget_do_objeto(fonte.id).winfo_children()
                  if hasattr(w, "cget") and w is not texto.widget_do_objeto(fonte.id).canvas]
        assert any(xadrez.AVISO_DE_MARCAS in a for a in avisos)
        texto.selecionar_objeto(fonte.id)
        assert j.executar("marcas_e_setas", [], []).aviso == ""
        # cancelar
        texto.selecionar_objeto(d.id)
        t.caixas.marcas_resposta = None
        assert j.executar("marcas_e_setas") is None and texto.modelo_de(d.id).marcas == ["d5"]
        # sem diagrama sob o cursor
        texto.ir_para(texto.ordem[1], 0)
        j.executar("marcas_e_setas")
        assert "sobre um diagrama" in t.caixas.entradas()[-1]
        # o botão "Editar posição…" do painel Propriedades (o aviso da ED-04 saiu)
        t.caixas.diagrama_resposta = m.Diagrama(fen=d.fen, lado="b", marcas=["d5"], setas=[("e2", "e4")])
        assert j._acao_das_propriedades("editar_posicao", {"id": d.id}).lado == "b"
        assert texto.modelo_de(d.id).lado == "b" and texto.modelo_de(d.id).marcas == ["d5"]
        texto.selecionar_objeto(d.id)
        assert "chega na ED-05" not in j.painel_de_propriedades.aviso.cget("text")

        # a caixa de verdade: clique marca, arrastar faz a seta, o texto manda
        caixa = DialogoDeMarcasESetas(j, texto.modelo_de(d.id), idioma="pt")
        caixa.construir()
        assert caixa.var_marcas.get() == "d5" and caixa.var_setas.get() == "e2-e4"
        assert caixa.alternar_marca("e4") and caixa.marcas == ["d5", "e4"] and caixa.var_marcas.get() == "d5 e4"
        assert not caixa.alternar_marca("d5") and caixa.marcas == ["e4"]
        assert caixa.alternar_seta("g1", "f3") and caixa.setas == [("e2", "e4"), ("g1", "f3")]
        assert not caixa.alternar_seta("e2", "e4") and caixa.var_setas.get() == "g1-f3"
        assert len(caixa.canvas.find_withtag("marca")) == 1 and len(caixa.canvas.find_withtag("seta")) == 1

        class _E:
            def __init__(self, x, y):
                self.x, self.y = x, y

        x0, y0, casa = caixa.x0, caixa.y0, caixa.casa
        caixa._no_clique(_E(x0 + 4 * casa + 2, y0 + 4 * casa + 2))            # e4
        caixa._no_solta(_E(x0 + 4 * casa + 2, y0 + 4 * casa + 2))
        assert caixa.marcas == []                                              # tirou o e4
        caixa._no_clique(_E(x0 + 0 * casa + 2, y0 + 7 * casa + 2))            # a1 →
        caixa._no_solta(_E(x0 + 7 * casa + 2, y0 + 0 * casa + 2))             # h8
        assert caixa.setas == [("g1", "f3"), ("a1", "h8")]
        caixa._no_clique(_E(-5, -5))
        caixa._no_solta(_E(x0 + 2, y0 + 2))                                    # fora → nada
        assert caixa.setas == [("g1", "f3"), ("a1", "h8")]
        caixa.var_marcas.set("b2 c3")
        caixa.var_setas.set("h1-h8")
        caixa._do_texto()
        assert caixa.marcas == ["b2", "c3"] and caixa.setas == [("h1", "h8")]
        novo = caixa.confirmar()
        assert novo.id == d.id and novo.marcas == ["b2", "c3"] and novo.setas == [("h1", "h8")] and novo.aviso == ""
        # em fonte a caixa avisa
        caixa2 = DialogoDeMarcasESetas(j, m.Diagrama(fen=FEN_LOPEZ, modo="fonte", marcas=["e4"]))
        caixa2.construir()
        assert xadrez.AVISO_DE_MARCAS in caixa2.lbl_aviso.cget("text")
        caixa2.limpar()
        assert caixa2.lbl_aviso.cget("text") == "" and caixa2.confirmar().marcas == []
        # girado: o clique acha a casa certa
        caixa3 = DialogoDeMarcasESetas(j, m.Diagrama(fen=FEN_LOPEZ, orientacao="preta"))
        caixa3.construir()
        assert caixa3._casa_em(caixa3.x0 + 2, caixa3.y0 + 2) == "h1"
        caixa3.cancelar()


# ----------------------------------------------------------------------
# AC-ED05b-2
# ----------------------------------------------------------------------

def test_ac2_legenda_sugerida_propoe_o_lado_e_nao_o_grava():
    blocos = [m.Titulo(trechos=[m.Trecho(texto="Partida")], nivel=2),
              p("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6", estilo="notacao"),
              m.Diagrama(fen=FEN_LOPEZ, numero=12),
              p("4.Ba4 Nf6 5.O-O", estilo="notacao")]
    assert xadrez.legenda_sugerida(blocos, 2) == ("Diagrama 12: após 3…a6 — Brancas jogam", "w")
    assert xadrez.legenda_sugerida(blocos, 2, "en") == ("Diagrama 12: after 3…a6 — White to move", "w")
    assert blocos[2].lado == ""                                                # proposto, não gravado
    # o número seguinte manda: "23…" diz pretas depois de um lance de brancas
    b2 = [m.Diagrama(fen="6k1/5ppp/8/8/4r3/8/5PPP/4R1K1 w - - 0 23"), p("23.Rxe4", estilo="notacao"),
          m.Diagrama(fen="6k1/5ppp/8/8/4R3/8/5PPP/6K1 b - - 0 23"), p("23…Kf8", estilo="notacao")]
    assert xadrez.legenda_sugerida(b2, 2) == ("Após 23.♖xe4 — Pretas jogam", "b")
    # a variante não conta: o último lance é o da linha principal
    b3 = [m.Diagrama(fen="6k1/5ppp/8/8/4r3/8/5PPP/4R1K1 w - - 0 23"),
          p("23.Rxe4 (23.Kf1 Rxe1+) Kf8", estilo="notacao"),
          m.Diagrama(fen="5k2/5ppp/8/8/4R3/8/5PPP/6K1 w - - 1 24"), p("24.Rd4", estilo="notacao")]
    assert xadrez.legenda_sugerida(b3, 2) == ("Após 23…♔f8 — Brancas jogam", "w")
    # sem número seguinte, o lado vem da posição; a posição inicial tem nome; um diagrama solto só tem o lado
    b4 = [m.Diagrama(fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", numero=1),
          p("1.e4", estilo="notacao")]
    assert xadrez.legenda_sugerida(b4, 0) == ("Diagrama 1: posição inicial — Brancas jogam", "w")
    b5 = [m.Diagrama(fen="6k1/5ppp/8/8/4R3/8/5PPP/6K1 b - - 0 23")]
    assert xadrez.legenda_sugerida(b5, 0) == ("Pretas jogam", "b")
    b6 = [p("1.e4 e5", estilo="notacao"), m.Diagrama(fen="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")]
    assert xadrez.legenda_sugerida(b6, 1) == ("Após 1…e5 — Brancas jogam", "w")
    with pytest.raises(ValueError):
        xadrez.legenda_sugerida(b6, 0)


def test_ac2_o_comando_legenda_sugerida_na_janela(tmp_path):
    livro = editor_livros.livro_completo()
    cap = livro.capitulos[0]
    cap.blocos = [m.Titulo(trechos=[m.Trecho(texto="Partida")], nivel=2),
                  p("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6", estilo="notacao"),
                  m.Diagrama(fen=FEN_LOPEZ, numero=12, modo="png"),
                  p("4.Ba4 Nf6 5.O-O", estilo="notacao")]
    caminho = str(tmp_path / "legenda.epub")
    epub.escrever(livro, caminho)
    with Janela(abrir=False) as t:
        j = t.j
        j.executar("abrir", caminho)
        texto = t.texto
        d = next(b for b in texto.sincronizar().blocos if isinstance(b, m.Diagrama))
        texto.selecionar_objeto(d.id)
        t.caixas.texto_resposta = None                                          # cancelar
        assert j.executar("legenda_sugerida") is None
        assert t.caixas.chamadas[-1] == ("pedir_texto", "Legenda sugerida", "Legenda:",
                                         "Diagrama 12: após 3…a6 — Brancas jogam")
        assert texto.modelo_de(d.id).legenda == [] and texto.modelo_de(d.id).lado == ""
        texto.selecionar_objeto(d.id)
        t.caixas.texto_resposta = "Diagrama 12: após 3…a6 — Brancas jogam"
        assert j.executar("legenda_sugerida") == "Diagrama 12: após 3…a6 — Brancas jogam"
        atual = texto.modelo_de(d.id)
        assert "".join(tr.texto for tr in atual.legenda) == "Diagrama 12: após 3…a6 — Brancas jogam"
        assert atual.lado == "" and atual.lado_indicador == ""                   # proposto, não gravado
        assert "lado proposto: brancas" in j.campos["aviso"].cget("text")
        assert texto.widget_do_objeto(d.id)._legenda() == "Diagrama 12: após 3…a6 — Brancas jogam"   # sem repetir o número
        # por argumento, e o texto vazio tira a legenda
        texto.selecionar_objeto(d.id)
        assert j.executar("legenda_sugerida", "") == "" and texto.modelo_de(d.id).legenda == []
        # gravar o lado é outro comando
        texto.selecionar_objeto(d.id)
        assert j.executar("lado_a_jogar", "w") == "w" and texto.modelo_de(d.id).lado == "w"
        # sem diagrama sob o cursor
        texto.ir_para(texto.ordem[1], 0)
        j.executar("legenda_sugerida")
        assert "sobre um diagrama" in t.caixas.entradas()[-1]


# ----------------------------------------------------------------------
# AC-ED05b-3
# ----------------------------------------------------------------------

def _livro_com_nags():
    livro = editor_livros.livro_completo()
    cap = livro.capitulos[0]
    cap.blocos = [m.Titulo(trechos=[m.Trecho(texto="T")], nivel=1),
                  m.Paragrafo(trechos=[m.Trecho(texto="1.e4 e5 2.Nf3"), m.Trecho(texto="±", papel="nag", nag=16),
                                       m.Trecho(texto=" Nc6 = 3.Bb5!? a6"),
                                       m.Trecho(texto="⩲", papel="nag", nag=14, familia="simbolos"),
                                       m.Trecho(texto=" 4.Ba4?! Nf6±")], estilo="notacao"),
                  p("prosa com ± que não conta")]
    return livro


def test_ac3_a_chave_de_simbolos_lista_os_marcados_e_os_digitados_como_glossario(tmp_path):
    livro = _livro_com_nags()
    usados = xadrez.nags_usados(livro)
    assert [(u.simbolo, u.codigo, u.quantos) for u in usados] == [("!?", 5, 1), ("?!", 6, 1), ("⩲", 14, 1),
                                                                    ("±", 16, 2), ("=", None, 1)]
    cap = xadrez.chave_de_simbolos(livro)
    assert cap in livro.capitulos and livro.capitulos[-1] is cap and cap.semantica == "glossary"
    assert cap.arquivo == "chave-de-simbolos.xhtml" and cap.titulo == "Chave de símbolos"
    assert m.texto_de(cap.blocos[0]) == "Chave de símbolos" and isinstance(cap.blocos[0], m.Titulo)
    linhas = [m.texto_de(b) for b in cap.blocos[1:]]
    assert linhas == ["!? Interessante ($5)", "?! Duvidoso ($6)", "⩲ Brancas ligeiramente melhor ($14)",
                      "± Brancas melhor ($16)", "= Igualdade"]
    assert all(b.classe == "chave" and b.estilo == "corpo" for b in cap.blocos[1:])
    simbolo = cap.blocos[3].trechos[0]
    assert simbolo.papel == "nag" and simbolo.nag == 14 and simbolo.familia == "simbolos"
    assert cap.blocos[5].trechos[0].nag is None and cap.blocos[4].trechos[0].familia == ""
    x = xhtml.escrever(cap)
    assert '<body epub:type="glossary">' in x and 'data-nag="14"' in x
    # refeita no lugar (o mesmo capítulo, no mesmo arquivo), em inglês
    livro.capitulos[0].blocos[1].trechos.append(m.Trecho(texto=" 5.O-O!!"))
    cap2 = xadrez.chave_de_simbolos(livro, idioma="en")
    assert cap2 is cap and len([c for c in livro.capitulos if c.semantica == "glossary"]) == 1
    assert cap2.titulo == "Key to symbols" and m.texto_de(cap2.blocos[1]) == "!! Excelente ($3)"
    # a própria chave não conta; um livro sem NAGs tem a página com o aviso
    assert [u.codigo for u in xadrez.nags_usados(livro)] == [3, 5, 6, 14, 16, None]
    vazio = m.Livro(metadados=m.Metadados(titulo="Sem xadrez"),
                    capitulos=[m.Capitulo(arquivo="Text/a.xhtml", blocos=[p("prosa com !? e ± fora de linha de jogo")])])
    cap3 = xadrez.chave_de_simbolos(vazio)
    assert cap3.arquivo == "Text/chave-de-simbolos.xhtml"
    assert m.texto_de(cap3.blocos[1]) == "(nenhum símbolo de xadrez no livro)"
    # salva e volta com o epub:type
    caminho = str(tmp_path / "chave.epub")
    epub.escrever(livro, caminho)
    relido, _r = epub.ler(caminho)
    assert relido.capitulos[-1].semantica == "glossary" and m.texto_de(relido.capitulos[-1].blocos[4]).startswith("⩲")
    assert relido.capitulos[-1].blocos[4].classe == "chave" and relido.capitulos[-1].blocos[4].trechos[0].nag == 14


def test_ac3_o_comando_chave_de_simbolos_na_janela(tmp_path):
    caminho = str(tmp_path / "chave.epub")
    epub.escrever(_livro_com_nags(), caminho)
    with Janela(abrir=False) as t:
        j = t.j
        j.executar("abrir", caminho)
        n = len(j.projeto.livro.capitulos)
        arquivo = j.executar("chave_de_simbolos")
        assert arquivo == "chave-de-simbolos.xhtml" and len(j.projeto.livro.capitulos) == n + 1
        aba = j.aba_ativa()
        assert aba.arquivo == arquivo and j.projeto.sujo
        blocos = t.texto.sincronizar().blocos
        assert m.texto_de(blocos[0]) == "Chave de símbolos" and len(blocos) == 6
        assert j.projeto.livro.capitulos[-1].arquivo == arquivo                # no fim da espinha
        # de novo: refeita no lugar, a aba recarregada, sem capítulo a mais
        assert j.executar("chave_de_simbolos") == arquivo and len(j.projeto.livro.capitulos) == n + 1
        assert j.aba_ativa().arquivo == arquivo and len(t.texto.sincronizar().blocos) == 6
        assert "5 símbolo(s)" in j.campos["aviso"].cget("text")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
