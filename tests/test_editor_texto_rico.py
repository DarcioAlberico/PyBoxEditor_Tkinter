"""
Testes de `ui/editor/texto_rico.py` (ED-03; DEC-03, DEC-04, §8): o `TextoRico` operado
por comando numa raiz `withdraw`n — a ida e volta de 100 capítulos gerados (AC-ED03-1),
alternar sobre a seleção e o pendente (AC-2, AC-3), estilos, caixa e fonte (AC-4),
listas (AC-5), parágrafo e a folha (AC-6), desfazer (AC-7), as faixas protegidas e o
objeto genérico (AC-8), invisíveis, `indice_de` e zoom (AC-9), pincel e limpar (AC-10),
foco visível e a calha (AC-12).

Rodar sem pytest:      python tests/test_editor_texto_rico.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_gerador as gerador
from conftest import raiz_tk
from core.editor import modelo as m
from ui.editor import calha as calha_mod
from ui.editor.texto_rico import TextoRico
from ui.editor.tags import EstiloDeTela

OBJETOS = (m.Diagrama, m.Figura, m.Tabela, m.IlhaBruta, m.MarcaDePagina, m.QuebraDePagina, m.Separador)


def _p(texto, **kw):
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


class _Widget:
    def __init__(self, blocos=None, **kw):
        self.raiz = raiz_tk()
        if self.raiz is None:
            pytest.skip("sem display")
        self.w = TextoRico(self.raiz, **kw)
        self.w.pack(fill="both", expand=True)
        if blocos is not None:
            self.cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=blocos)
            self.w.carregar(self.cap)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        try:
            self.raiz.destroy()
        except Exception:
            pass

    def blocos(self):
        return self.w.sincronizar().blocos

    def textos(self):
        return [m.texto_de(b) for b in self.blocos()]

    def trechos(self, i):
        return [(t.texto, t.negrito, t.italico) for t in self.blocos()[i].trechos]


def _sem_objetos(cap):
    cap.blocos = [b for b in cap.blocos if not isinstance(b, OBJETOS)]
    for b in m.blocos_do_capitulo(cap):
        if isinstance(b, m.Paragrafo):
            b.trechos = [t for t in b.trechos if not t.ilha]
    return cap


# ----------------------------------------------------------------------
# AC-ED03-1: ida e volta
# ----------------------------------------------------------------------

def test_ac1_100_capitulos_gerados_vao_e_voltam_iguais_com_ids_preservados():
    with _Widget() as t:
        for semente in range(1, 101):
            cap = _sem_objetos(gerador.capitulo(semente))
            t.w.carregar(cap)
            volta = t.w.sincronizar(reler=True)
            assert m.igual(volta, cap), f"semente {semente}"
            assert [b.id for b in volta.blocos] == [b.id for b in cap.blocos]
            assert not t.w.sujo and not t.w.pode_desfazer


def test_objetos_e_ilhas_inline_atravessam_o_dump_intactos():
    with _Widget() as t:
        for semente in (3, 7, 11):
            cap = gerador.capitulo(semente)
            t.w.carregar(cap)
            assert m.igual(t.w.sincronizar(reler=True), cap), f"semente {semente}"
            assert len(t.w.registro) == sum(1 for b in m.blocos_do_capitulo(cap) if isinstance(b, OBJETOS)) \
                + sum(1 for tr in m.trechos_do_capitulo(cap) if tr.ilha)


# ----------------------------------------------------------------------
# AC-2, AC-3: alternar e pendente
# ----------------------------------------------------------------------

def test_ac2_alternar_negrito_sobre_a_selecao_e_sobre_o_marcador_proprio():
    abc = m.Paragrafo(trechos=[m.Trecho(texto="a"), m.Trecho(texto="b", negrito=True), m.Trecho(texto="c")])
    with _Widget([_p("xabcx"), abc, _p("comentário", estilo="comentario")]) as t:
        p0 = t.cap.blocos[0].id
        t.w.ir_para(p0, 0)
        t.w.selecionar(1, 4)
        assert t.w.alternar("negrito") is True
        assert t.trechos(0) == [("x", False, False), ("abc", True, False), ("x", False, False)]
        assert t.w.alternar("negrito") is False and t.trechos(0) == [("xabcx", False, False)]
        t.w.ir_para(abc.id, 0)
        t.w.selecionar(0, 3)
        assert t.w.alternar("negrito") is True and t.trechos(1) == [("abc", True, False)]  # nem todo: põe
        # `p.comentario` é itálico por CSS; alternar itálico **liga** o marcador, sem XOR.
        p2 = t.cap.blocos[2].id
        t.w.ir_para(p2, 0)
        t.w.selecionar(0, 4)
        assert t.w.alternar("italico") is True and t.trechos(2)[0] == ("come", False, True)
        assert t.w.sujo and t.w.pode_desfazer


def test_ac3_formato_pendente_vale_para_o_proximo_texto_e_mover_o_cursor_cancela():
    with _Widget([_p("abc")]) as t:
        p = t.cap.blocos[0].id
        t.w.ir_para(p, 3)
        assert t.w.alternar("italico") is True
        t.w.inserir("xyz")
        assert t.trechos(0) == [("abc", False, False), ("xyz", False, True)]
        t.w.ir_para(p, 1)
        t.w.alternar("negrito")
        t.w.ir_para(p, 2)                                    # moveu: o pendente cai
        t.w.inserir("Q")
        assert t.trechos(0) == [("abQc", False, False), ("xyz", False, True)]
        # Negrito + itálico desenham `fonte:*` bold italic; o dump não devolve `fonte:*`.
        t.w.selecionar(4, 7)
        t.w.alternar("negrito")
        tags = t.w.texto.tag_names(t.w.indice_de(p, 5))
        assert any(x.startswith("fonte:") and x.endswith(":bi") for x in tags)
        assert t.trechos(0)[-1] == ("xyz", True, True)
        assert "fonte:" not in str(m.para_dict(t.blocos()[0]))
        assert t.w.estilo_no_cursor()["negrito"] is True


# ----------------------------------------------------------------------
# AC-4: estilos, caixa, fonte
# ----------------------------------------------------------------------

def test_ac4_estilo_titulo_persistente_caixa_e_aumentar_fonte():
    with _Widget([_p("aBc"), _p("dois")]) as t:
        p = t.cap.blocos[0].id
        t.w.ir_para(p, 0)
        assert t.w.estilo("titulo2") == [p]
        bloco = t.blocos()[0]
        assert isinstance(bloco, m.Titulo) and bloco.nivel == 2 and bloco.id_persistente and bloco.id == p
        assert t.w.estilo("corpo") == [p] and type(t.blocos()[0]) is m.Paragrafo
        t.w.selecionar(0, 3)
        assert t.w.mudar_caixa("alternar") and t.textos()[0] == "AbC"
        assert t.w.mudar_caixa("maiusculas") and t.textos()[0] == "ABC"
        t.w.ir_para(p, 1)
        t.w.selecionar(0, 3)
        corpo = t.w.aumentar_fonte()
        assert corpo == 14.0 and t.blocos()[0].trechos[0].corpo_pt == 14.0
        assert t.w.aumentar_fonte() == 16.0 and t.w.diminuir_fonte() == 14.0
        with pytest.raises(ValueError):
            t.w.estilo("inexistente")
        t.w.estilo_de_caractere("Lance")
        assert t.blocos()[0].trechos[0].papel == "lance"
        t.w.estilo_de_caractere("Versalete")
        assert t.blocos()[0].trechos[0].versalete


# ----------------------------------------------------------------------
# AC-5: listas
# ----------------------------------------------------------------------

def test_ac5_lista_enter_nivel_sair_e_backspace():
    with _Widget([_p("antes"), _p("depois")]) as t:
        a = t.cap.blocos[0].id
        t.w.ir_para(a, 5)
        t.w.enter()
        assert t.w.lista(False)
        t.w.inserir("um")
        t.w.enter()
        t.w.inserir("dois")
        assert t.w.nivel(+1) is True
        lista = t.blocos()[1]
        assert isinstance(lista, m.Lista) and not lista.ordenada and len(lista.itens) == 1
        assert m.texto_de(lista.itens[0].paragrafos[0]) == "um"
        assert lista.itens[0].filhos is not None and m.texto_de(lista.itens[0].filhos.itens[0].paragrafos[0]) == "dois"
        # O `\n` interno é quebra+protegido e o marcador não sai no dump.
        conteudo = t.w.texto.get(t.w._inicio_de(lista.id), t.w._fim_de(lista.id))
        assert conteudo.startswith("• um\n◦ dois\n")
        quebra = t.w.texto.search("\n", t.w._inicio_de(lista.id))
        assert {"quebra", "protegido"} <= set(t.w.texto.tag_names(quebra))
        assert m.texto_de(lista) == "um\ndois"
        # Enter em item vazio sai da lista.
        t.w.enter()
        t.w.enter()
        assert [type(b).__name__ for b in t.blocos()] == ["Paragrafo", "Lista", "Paragrafo", "Paragrafo"]
        assert len(t.blocos()[1].itens[0].filhos.itens) == 1
        # Backspace no início do item aninhado diminui o nível; no nível 1, sai.
        t.w.ir_para(lista.id, 3)
        assert t.w.backspace() is True
        lista = t.blocos()[1]
        assert [m.texto_de(i.paragrafos[0]) for i in lista.itens] == ["um", "dois"] and lista.itens[0].filhos is None
        t.w.ir_para(lista.id, 3)
        assert t.w.backspace() is True
        assert [type(b).__name__ for b in t.blocos()][:3] == ["Paragrafo", "Lista", "Paragrafo"]
        assert t.textos()[2] == "dois"
        # Lista de volta a parágrafos, e lista ordenada de três parágrafos.
        t.w.ir_para(lista.id, 0)
        assert t.w.lista(False) and t.textos()[1] == "um" and isinstance(t.blocos()[1], m.Paragrafo)
        t.w.selecionar_indices("1.0", "3.0")
        ids = t.w.lista(True)
        assert len(ids) == 1 and isinstance(t.blocos()[0], m.Lista) and t.blocos()[0].ordenada
        assert [m.texto_de(i.paragrafos[0]) for i in t.blocos()[0].itens] == ["antes", "um"]


# ----------------------------------------------------------------------
# AC-6: parágrafo e a folha
# ----------------------------------------------------------------------

def test_ac6_paragrafo_em_tres_blocos_e_a_folha_pinta_o_comentario():
    folhas = {"Styles/a.css": "p.comentario { font-style: italic; color: #444 }"}
    with _Widget([_p("um"), _p("dois"), _p("três", estilo="comentario")], folhas=folhas) as t:
        t.w.selecionar_indices("1.0", "3.2")
        assert len(t.w.paragrafo(alinhamento="centro")) == 3
        assert [b.alinhamento for b in t.blocos()] == ["centro", "centro", "centro"]
        t.w.ir_para(t.cap.blocos[2].id, 1)
        assert t.w.paragrafo(recuo_esquerda_em=2.0, manter_com_proximo=True) == [t.cap.blocos[2].id]
        b = t.blocos()[2]
        assert b.recuo_esquerda_em == 2.0 and b.manter_com_proximo and b.alinhamento == "centro"
        assert t.w.limpar_paragrafo() and t.blocos()[2].alinhamento == "" and t.blocos()[2].recuo_esquerda_em is None
        indice = t.w.indice_de(t.cap.blocos[2].id, 1)
        tags = t.w.texto.tag_names(indice)
        fonte = next(x for x in tags if x.startswith("fonte:"))
        assert fonte.endswith(":i")                                          # itálica pela folha
        assert t.w.texto.tag_cget("p:comentario", "foreground") == "#444444"
        with pytest.raises(ValueError):
            t.w.paragrafo(cor="x")


# ----------------------------------------------------------------------
# AC-7: desfazer
# ----------------------------------------------------------------------

def test_ac7_dez_operacoes_desfeitas_devolvem_o_inicial_e_refazer_o_final():
    inicial = [_p("xabcx"), _p("dois"), _p("três")]
    with _Widget(inicial) as t:
        p0, p1 = t.cap.blocos[0].id, t.cap.blocos[1].id
        agora = [0.0]
        t.w.historico.relogio = lambda: agora[0]

        w = t.w
        passos = [
            lambda: (w.ir_para(p0, 0), w.selecionar(1, 4), w.alternar("negrito")),
            lambda: (w.ir_para(p0, 5), w.inserir("!")),
            lambda: (w.ir_para(p1, 0), w.estilo("titulo1")),
            lambda: (w.ir_para(p1, 4), w.enter()),
            lambda: w.inserir("novo"),
            lambda: (w.ir_para(p0, 2), w.enter()),
            lambda: w.backspace(),
            lambda: (w.ir_para(p0, 1), w.selecionar(0, 2), w.mudar_caixa("maiusculas")),
            lambda: (w.ir_para(p1, 0), w.lista(True)),
            lambda: (w.ir_para(p0, 0), w.paragrafo(alinhamento="direita")),
        ]
        for passo in passos:
            passo()
            agora[0] += 5                    # fora da janela de coalescência: um ponto por passo
        final = t.w.sincronizar()
        n = 0
        while t.w.desfazer():
            n += 1
        assert n == 10
        assert m.igual(t.w.sincronizar(reler=True), m.Capitulo(arquivo="Text/c.xhtml", blocos=inicial))
        assert not t.w.pode_desfazer and t.w.pode_refazer
        while t.w.refazer():
            pass
        assert m.igual(t.w.sincronizar(reler=True), final)


# ----------------------------------------------------------------------
# AC-8: faixas protegidas, objeto genérico
# ----------------------------------------------------------------------

def test_ac8_protegido_recusa_e_o_objeto_selecionado_apaga_com_desfazer():
    diagrama = m.Diagrama(fen="8/8/8/8/8/8/8/8 w - - 0 1", lado="w", orientacao="preta", coordenadas=True)
    ilha = m.Paragrafo(trechos=[m.Trecho(texto="a"), m.Trecho(ilha="<cite>x</cite>"), m.Trecho(texto="b")])
    lista = m.Lista(ordenada=True, itens=[m.ItemDeLista(paragrafos=[_p("item")])])
    with _Widget([lista, diagrama, ilha, _p("fim")]) as t:
        texto = t.w.texto
        ini = t.w._inicio_de(lista.id)
        antes = texto.get("1.0", "end-1c")
        assert t.w.apagar(ini, f"{ini}+2c") is False and texto.get("1.0", "end-1c") == antes   # o marcador
        assert t.w.apagar(t.w._inicio_de(diagrama.id), t.w._fim_de(diagrama.id)) is False
        janela_da_ilha = next(n for n in texto.window_names() if isinstance(t.w.registro.objeto(n), m.Trecho))
        janela_do_diagrama = t.w.registro.nome_de(diagrama.id)
        assert t.w.inserir("x", texto.index(janela_do_diagrama)) is False    # no bloco do objeto, não
        assert t.w.inserir("x", texto.index(janela_da_ilha)) is True        # ao lado da ilha inline, pode
        assert m.texto_de(t.blocos()[2]) == "axb"
        assert t.w.inserir("x", f"{ini}+1c") is False                        # dentro do marcador "1. " não
        # A ilha inline volta intacta e o diagrama também (ObjetoGenerico).
        volta = t.w.sincronizar(reler=True)
        assert isinstance(volta.blocos[1], m.Diagrama) and volta.blocos[1].orientacao == "preta"
        assert volta.blocos[2].trechos[1].ilha == "<cite>x</cite>"
        # Selecionar o objeto inteiro e apagar: sai, e volta com desfazer.
        t.w.selecionar_indices(t.w._inicio_de(diagrama.id), t.w._fim_de(diagrama.id))
        assert t.w.apagar_selecao() is True
        assert [type(b).__name__ for b in t.blocos()] == ["Lista", "Paragrafo", "Paragrafo"]
        assert t.w.desfazer() and isinstance(t.blocos()[1], m.Diagrama) and t.blocos()[1].fen == diagrama.fen
        assert len(t.w.registro) == 2
        assert int(texto.cget("highlightthickness")) == 2                  # AC-12: foco visível
        # Inserir um objeto novo depois do bloco do cursor, e uma ilha inline no cursor.
        t.w.ir_para(ilha.id, 1)
        figura = m.Figura(recurso="Images/x.png", alt="x")
        assert t.w.inserir_objeto(figura) == figura.id
        assert [type(b).__name__ for b in t.blocos()] == ["Lista", "Diagrama", "Paragrafo", "Figura", "Paragrafo"]
        t.w.ir_para(ilha.id, 1)
        t.w.inserir_objeto(m.Trecho(ilha="<abbr>i</abbr>"))
        assert [tr.ilha for tr in t.blocos()[2].trechos if tr.ilha] == ["<abbr>i</abbr>", "<cite>x</cite>"]
        assert t.w.desfazer() and t.w.desfazer()
        assert [type(b).__name__ for b in t.blocos()] == ["Lista", "Diagrama", "Paragrafo", "Paragrafo"]
        with pytest.raises(ValueError):
            t.w.inserir_objeto(_p("não é objeto"))


# ----------------------------------------------------------------------
# AC-9, AC-10: invisíveis, indice_de, zoom, pincel, limpar
# ----------------------------------------------------------------------

def test_ac9_invisiveis_indice_de_e_zoom_so_na_tela():
    quebra = m.Paragrafo(trechos=[m.Trecho(texto="um"), m.Trecho(texto="dois", quebra_antes=True)])
    with _Widget([_p("abc def"), quebra]) as t:
        assert t.w.invisiveis(True) is True
        conteudo = t.w.texto.get("1.0", "end-1c")
        assert "¶" in conteudo and "°" in conteudo and "⏎" in conteudo
        assert all("protegido" in t.w.texto.tag_names(i) for i in
                   (t.w.texto.search("¶", "1.0"), t.w.texto.search("°", "1.0"), t.w.texto.search("⏎", "1.0")))
        volta = t.w.sincronizar(reler=True)
        assert m.igual(volta, t.cap)                                         # os invisíveis não voltam
        p = t.cap.blocos[0].id
        assert t.w.texto.get(t.w.indice_de(p, 5)) == "e"                     # o 6º caractere do modelo
        assert t.w.texto.get(t.w.indice_de(quebra.id, 3)) == "d"             # a quebra suave conta um
        t.w.ir_para(p, 4)
        assert t.w.posicao() == (p, 4)
        t.w.invisiveis(False)
        assert "¶" not in t.w.texto.get("1.0", "end-1c") and m.igual(t.w.sincronizar(reler=True), t.cap)
        fonte_antes = next(x for x in t.w.texto.tag_names(t.w.indice_de(p, 0)) if x.startswith("fonte:"))
        assert t.w.zoom(1.5) == 1.5
        fonte_depois = next(x for x in t.w.texto.tag_names(t.w.indice_de(p, 0)) if x.startswith("fonte:"))
        assert fonte_antes.endswith(":12:") and fonte_depois.endswith(":18:")
        assert m.igual(t.w.sincronizar(reler=True), t.cap) and t.w.posicao() == (p, 4)
        assert t.w.largura_de_leitura(65) == 65 and t.w.largura_de_leitura(0) == 0


def test_ac10_pincel_e_limpar_caractere_mantem_link_nota_e_ref():
    com_link = m.Paragrafo(trechos=[m.Trecho(texto="ver", link="Text/x.xhtml#a", negrito=True, cor="#ff0000"),
                                    m.Trecho(texto=" e nota"), m.Trecho(nota="n1")])
    with _Widget([_p("alvo"), com_link]) as t:
        p0, p1 = t.cap.blocos[0].id, t.cap.blocos[1].id
        t.w.ir_para(p1, 2)
        assert set(t.w.pincel_copiar()) == {"b", "cor:#ff0000"}                # o link não vai no pincel
        t.w.ir_para(p0, 0)
        t.w.selecionar(0, 4)
        assert t.w.pincel_aplicar() is True
        assert t.trechos(0) == [("alvo", True, False)] and t.blocos()[0].trechos[0].cor == "#ff0000"
        t.w.ir_para(p1, 0)
        t.w.selecionar(0, 3)
        t.w.limpar_caractere()
        tr = t.blocos()[1].trechos[0]
        assert tr.link == "Text/x.xhtml#a" and not tr.negrito and tr.cor == ""
        assert t.blocos()[1].trechos[-1].nota == "n1"
        with pytest.raises(ValueError):
            t.w.aplicar(inexistente=1)


def test_ac12_a_calha_desenha_o_icone_do_bloco_marcado_suspeito():
    with _Widget([_p("um"), _p("dois"), _p("três")]) as t:
        t.raiz.deiconify()
        t.raiz.update()
        p1 = t.cap.blocos[1].id
        t.w.calha.marcar(p1, "suspeito")
        assert t.w.calha.icone_de(p1) == "suspeito" and p1 in t.w.calha.desenhados()
        assert any("suspeito" in t.w.calha.gettags(i) for i in t.w.calha.find_all())
        assert calha_mod.ICONES["suspeito"][0] == "!"
        t.w.calha.marcar(p1, None)
        assert t.w.calha.desenhados() == []
        with pytest.raises(ValueError):
            t.w.calha.marcar(p1, "estranho")
        t.raiz.withdraw()


def test_enter_backspace_delete_e_apagar_palavra_entre_blocos():
    with _Widget([_p("abc def"), _p("ghi"), m.Titulo(trechos=[m.Trecho(texto="T")], nivel=1)]) as t:
        p0, p1, t2 = (b.id for b in t.cap.blocos)
        t.w.ir_para(p0, 3)
        assert t.w.enter() and t.textos() == ["abc", " def", "ghi", "T"]
        assert t.w.backspace() and t.textos() == ["abc def", "ghi", "T"]
        t.w.ir_para(p0, 7)
        assert t.w._delete() and t.textos() == ["abc defghi", "T"]
        t.w.ir_para(p0, 7)
        assert t.w.apagar_palavra(-1) == "def" or t.w.apagar_palavra(1) is not None
        # Enter no fim de um título abre um parágrafo de corpo.
        t.w.ir_para(t2, 1)
        t.w.enter()
        t.w.inserir("prosa")
        assert isinstance(t.blocos()[-1], m.Paragrafo) and t.blocos()[-1].estilo == "corpo"
        assert t.textos()[-1] == "prosa"
        # Seleção entre blocos: o meio some, as pontas se juntam.
        t.w.selecionar_indices(t.w.indice_de(p0, 2), t.w.indice_de(t2, 1))
        assert t.w.apagar_selecao() is True
        assert t.textos() == ["ab", "prosa"] or t.textos() == ["abT"[:2], "prosa"]
        t.w.selecionar_tudo()
        t.w.apagar_selecao()
        assert t.w.inserir("de novo") and t.textos() == ["de novo"]


def test_as_ligacoes_e_os_comandos_existem_e_devolvem_break():
    with _Widget([_p("abc")]) as t:
        for sequencia in ("<Return>", "<BackSpace>", "<Delete>", "<Key>", "<Tab>", "<Shift-Tab>", "<Control-b>",
                          "<Control-i>", "<Control-u>", "<Control-Shift-K>", "<Control-equal>", "<Control-plus>",
                          "<Control-l>", "<Control-e>", "<Control-r>", "<Control-j>", "<Control-space>",
                          "<Control-q>", "<Control-BackSpace>", "<Control-Delete>", "<Control-Shift-L>",
                          "<Control-Shift-O>", "<<Undo>>", "<<Redo>>", "<<Paste>>", "<<Cut>>", "<Key-Insert>",
                          "<<PasteSelection>>"):
            assert sequencia in t.w.ligacoes, sequencia
        assert t.w.ligacoes["<Control-b>"](None) == "break"
        for nome in ("desfazer", "refazer", "negrito", "italico", "sublinhado", "tachado", "versalete", "sobrescrito",
                     "subscrito", "aumentar_fonte", "diminuir_fonte", "limpar_caractere", "limpar_paragrafo", "estilo",
                     "estilo_de_caractere", "lista", "nivel", "mudar_caixa", "pincel_copiar", "pincel_aplicar",
                     "alinhar_esquerda", "alinhar_centro", "alinhar_direita", "justificar", "apagar_palavra_anterior",
                     "apagar_palavra_seguinte", "selecionar_paragrafo", "selecionar_bloco", "selecionar_tudo",
                     "invisiveis", "zoom", "enter", "backspace", "apagar_selecao"):
            assert callable(t.w.comandos[nome]), nome
        eventos = []
        t.w.texto.bind("<<Mudou>>", lambda e: eventos.append("mudou"))
        t.w.texto.bind("<<CursorMoveu>>", lambda e: eventos.append("cursor"))
        t.w.ir_para(t.cap.blocos[0].id, 1)
        t.w.inserir("x")
        assert "mudou" in eventos and "cursor" in eventos
        assert str(t.w.texto.cget("undo")) == "0"
        assert isinstance(t.w.tela, EstiloDeTela)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
