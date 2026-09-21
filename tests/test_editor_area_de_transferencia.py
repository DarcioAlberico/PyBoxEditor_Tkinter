"""
Testes da área de transferência (ED-04; SPEC_EDITOR §8.11, AC-ED04-7): o módulo puro
(`core/editor/area_de_transferencia.py`) com o sistema injetado — copiar grava só o
texto plano, colar é interno quando o texto do sistema é o do último copiar, texto de
fora vira parágrafos, imagem quando não há texto, `Ctrl+Shift+V` força texto, "colar
como XHTML" conserta e lê — e, pela janela, o colar interno que preserva negrito,
figura e ilha, as notas que nascem de novo ao colar, o texto de fora que vira
parágrafos e a imagem que vira recurso do livro.

Rodar sem pytest:      python tests/test_editor_area_de_transferencia.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m
from core.editor.area_de_transferencia import (AreaDeTransferencia, Fragmento, blocos_do_texto, blocos_do_xhtml,
                                               texto_plano)
from editor_ambiente import Janela, Widget, p


class _Sistema:
    def __init__(self, texto="", imagem=None):
        self.texto, self.imagem, self.gravado = texto, imagem, []

    def area(self):
        return AreaDeTransferencia(lambda: self.texto, self.gravado.append, lambda: self.imagem)


# ----------------------------------------------------------------------
# O módulo puro
# ----------------------------------------------------------------------

def test_copiar_grava_so_texto_plano_e_colar_e_interno_quando_o_sistema_tem_o_mesmo_texto():
    sistema = _Sistema()
    area = sistema.area()
    fragmento = Fragmento(blocos=[m.Paragrafo(trechos=[m.Trecho(texto="ne", negrito=True), m.Trecho(texto="gro")]),
                                  m.Figura(recurso="Images/x.png", alt="x")], inline=False)
    assert area.copiar(fragmento) == "negro\n" and sistema.gravado == ["negro\n"]
    assert area.ultimo is not fragmento and area.ultimo.blocos[0].trechos[0].negrito
    sistema.texto = "negro\n"
    colagem = area.colar()
    assert colagem.tipo == "interno" and colagem.fragmento.blocos[0].trechos[0].negrito
    assert colagem.fragmento is not area.ultimo                                    # uma cópia por colagem
    colagem.fragmento.blocos[0].trechos[0].texto = "mudei"
    assert area.colar().fragmento.blocos[0].trechos[0].texto == "ne"
    sistema.texto = "negro\r\n"
    assert area.colar().tipo == "interno"                                        # o \\r\\n do Windows não engana
    # Outro programa escreveu no sistema: a colagem é o texto de fora.
    sistema.texto = "veio de fora"
    colagem = area.colar()
    assert colagem.tipo == "texto" and colagem.texto == "veio de fora"
    assert area.colar(forcar_texto=True).tipo == "texto"
    sistema.texto = "negro\n"
    assert area.colar(forcar_texto=True).texto == "negro\n"                      # Ctrl+Shift+V: sempre texto
    assert area.copiar(Fragmento()) == "" and len(sistema.gravado) == 1           # nada a copiar, nada gravado


def test_sem_texto_a_colagem_e_a_imagem_quando_ha_quem_a_leia():
    sistema = _Sistema(texto="", imagem=b"\x89PNG...")
    area = sistema.area()
    colagem = area.colar()
    assert colagem.tipo == "imagem" and colagem.imagem == b"\x89PNG..."
    assert area.colar(forcar_texto=True) is None
    sistema.imagem = None
    assert area.colar() is None
    sem_imagem = AreaDeTransferencia(lambda: "", lambda t: None)
    assert sem_imagem.colar() is None
    falha = AreaDeTransferencia(lambda: (_ for _ in ()).throw(RuntimeError("sem sistema")), lambda t: None,
                                lambda: (_ for _ in ()).throw(RuntimeError("sem imagem")))
    assert falha.colar() is None


def test_texto_de_fora_vira_paragrafos_e_colar_como_xhtml_conserta_e_le():
    blocos = blocos_do_texto("linha um\r\n\r\n  linha dois  \n\nlinha tres")
    assert [m.texto_de(b) for b in blocos] == ["linha um", "  linha dois", "linha tres"]
    assert all(isinstance(b, m.Paragrafo) for b in blocos) and blocos_do_texto("  \n\n") == []
    assert texto_plano(blocos) == "linha um\n  linha dois\nlinha tres"
    lidos, avisos = blocos_do_xhtml("<p>um <b>dois</p><p>tr&ecirc;s</p>")
    assert [m.texto_de(b) for b in lidos] == ["um dois", "três"] and lidos[0].trechos[1].negrito
    assert avisos                                                                  # o <b> sem fechar foi consertado
    inline, _ = blocos_do_xhtml("<em>só</em> inline")
    assert len(inline) == 1 and isinstance(inline[0], m.Paragrafo) and inline[0].trechos[0].italico
    ilha, _ = blocos_do_xhtml('<svg xmlns="http://www.w3.org/2000/svg"/>')
    assert isinstance(ilha[0], m.IlhaBruta)


# ----------------------------------------------------------------------
# AC-ED04-7: pelo widget e pela janela
# ----------------------------------------------------------------------

def test_ac7_colar_interno_preserva_negrito_figura_e_ilha_e_copiar_deixa_so_texto_plano_no_sistema():
    with Janela() as t:
        j, texto, sistema = t.j, t.texto, t.sistema
        negrito = t.bloco(lambda b: isinstance(b, m.Paragrafo) and any(tr.negrito for tr in b.trechos))
        texto.ir_para(negrito.id, 0)
        texto.selecionar(0, 8)
        assert j.executar("copiar") == "neg ita " and sistema.texto == "neg ita "
        assert j.area.ultimo.inline and j.area.ultimo.blocos[0].trechos[0].negrito
        alvo = t.bloco(lambda b: isinstance(b, m.Paragrafo) and b.estilo == "primeira")
        texto.ir_para(alvo.id, 0)
        j.executar("colar")
        colado = t.bloco(lambda b: b.id == alvo.id)
        assert [(tr.texto, tr.negrito, tr.italico) for tr in colado.trechos[:2]] == [("neg", True, False),
                                                                                     (" ita", False, True)]
        assert m.texto_de(colado).startswith("neg ita Primeira")
        assert texto.desfazer() and m.texto_de(t.bloco(lambda b: b.id == alvo.id)).startswith("Primeira")
        # Vários blocos: figura e ilha no meio atravessam a cópia; a seleção que cruza objetos é o modelo deles.
        figura = t.bloco(lambda b: isinstance(b, m.Figura))
        ilha = t.bloco(lambda b: isinstance(b, m.IlhaBruta))
        ordem = texto.ordem_do_capitulo
        i_fig, i_ilha = ordem.index(figura.id), ordem.index(ilha.id)
        primeiro, ultimo = min(i_fig, i_ilha), max(i_fig, i_ilha)
        texto.selecionar_indices(texto._inicio_de(ordem[primeiro]), texto._fim_de(ordem[ultimo]))
        copiado = j.executar("copiar")
        assert "\n" in copiado and not copiado.startswith("<")                    # texto plano, sem XHTML
        assert any(isinstance(b, m.Figura) for b in j.area.ultimo.blocos)
        assert any(isinstance(b, m.IlhaBruta) for b in j.area.ultimo.blocos)
        j.abrir_capitulo("cap2.xhtml")
        texto2 = t.texto
        fim = texto2.ordem_do_capitulo[-1]
        texto2.ir_para(fim, len(m.texto_de(texto2.modelo_de(fim))))
        n = len(texto2.ordem_do_capitulo)
        j.executar("colar")
        blocos2 = texto2.sincronizar().blocos
        assert len(blocos2) > n
        assert any(isinstance(b, m.Figura) and b.recurso == figura.recurso for b in blocos2)
        assert any(isinstance(b, m.IlhaBruta) and b.xhtml == ilha.xhtml for b in blocos2)
        assert len({b.id for b in blocos2}) == len(blocos2)                           # ids únicos (INV-01)
        assert texto2.desfazer() and len(texto2.sincronizar().blocos) == n            # um desfazer só


def test_ac7_texto_de_fora_vira_paragrafos_e_a_imagem_vira_recurso_e_figura():
    with Janela() as t:
        j, texto, sistema = t.j, t.texto, t.sistema
        alvo = t.bloco(lambda b: isinstance(b, m.Paragrafo) and b.estilo == "primeira")
        texto.ir_para(alvo.id, len(m.texto_de(alvo)))
        sistema.texto = "um\r\ndois\r\n\r\ntres"
        j.executar("colar")
        blocos = texto.sincronizar().blocos
        i = [b.id for b in blocos].index(alvo.id)
        assert [m.texto_de(b) for b in blocos[i:i + 3]] == [m.texto_de(alvo) + "um", "dois", "tres"]
        assert all(isinstance(b, m.Paragrafo) and b.estilo in ("primeira", "corpo") for b in blocos[i:i + 3])
        texto.desfazer()
        # Ctrl+Shift+V com o texto do último copiar: texto plano, sem formato.
        negrito = t.bloco(lambda b: isinstance(b, m.Paragrafo) and any(tr.negrito for tr in b.trechos))
        texto.ir_para(negrito.id, 0)
        texto.selecionar(0, 3)
        j.executar("copiar")
        texto.ir_para(alvo.id, 0)
        j.executar("colar_sem_formatacao")
        assert t.bloco(lambda b: b.id == alvo.id).trechos[0].negrito is False
        assert m.texto_de(t.bloco(lambda b: b.id == alvo.id)).startswith("negPrimeira")
        # Uma imagem no sistema (sem texto) vira Images/colada-1.png e uma figura no cursor, com o alt avisado.
        from PIL import Image
        import io as _io

        buffer = _io.BytesIO()
        Image.new("RGB", (8, 6), (0, 0, 255)).save(buffer, "PNG")
        sistema.texto, sistema.imagem = "", buffer.getvalue()
        texto.ir_para(alvo.id, 0)
        j.executar("colar")
        assert "Images/colada-1.png" in j.projeto.livro.recursos
        figura = t.bloco(lambda b: isinstance(b, m.Figura) and b.recurso == "Images/colada-1.png")
        assert figura.alt == "" and "sem alt" in j.campos["aviso"].cget("text")
        assert texto.widget_do_objeto(figura.id).imagem.width() == 8
        j.executar("colar")
        assert "Images/colada-2.png" in j.projeto.livro.recursos
        # "Colar como XHTML" pelo comando, com o texto do sistema.
        sistema.texto = "<p>um <em>dois</em></p><p>três</p>"
        texto.ir_para(alvo.id, 0)
        ids = j.executar("colar_como_xhtml")
        assert len(ids) >= 1
        blocos = texto.sincronizar().blocos                 # o ultimo <p> colado funde-se com o paragrafo do cursor
        assert any(m.texto_de(b) == "um dois" for b in blocos)
        assert any(m.texto_de(b).startswith("trêsneg") for b in blocos)
        assert not t.caixas.falhas()


def test_as_notas_referenciadas_nascem_de_novo_ao_colar_com_id_novo():
    notas = [m.Nota(id="n1", blocos=[p("a nota", estilo="nota")])]
    ref = m.Paragrafo(trechos=[m.Trecho(texto="x"), m.Trecho(nota="n1"), m.Trecho(texto="y")])
    with Widget([ref, p("destino")], notas=notas) as t:
        w = t.w
        w.ir_para(ref.id, 0)
        w.selecionar(0, 2)
        fragmento = w.fragmento_da_selecao()
        assert fragmento.inline and [n.id for n in fragmento.notas] == ["n1"]
        assert fragmento.texto == "xy"
        w.ir_para(t.cap.blocos[1].id, 3)
        assert w.colar_fragmento(fragmento)
        cap = w.sincronizar()
        assert [n.id for n in cap.notas][0] == "n1" and len(cap.notas) == 2
        nova = cap.notas[1]
        assert nova.id != "n1" and m.texto_de(nova) == "a nota"
        assert [tr.nota for tr in cap.blocos[1].trechos if tr.nota] == [nova.id]
        assert m.texto_de(cap.blocos[1]) == "desxytino"
        assert w.desfazer() and len(w.sincronizar().notas) == 1 and m.texto_de(w.sincronizar().blocos[1]) == "destino"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
