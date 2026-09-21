"""
Testes da paleta e da barra de xadrez (ED-05; SPEC_EDITOR §7.3, §11.6, §13.2): o botão
`⩲` da paleta (ou da barra) põe no parágrafo um trecho `papel="nag"`, `nag=14`,
`familia="simbolos"`; o `±` (Latin-1) entra sem família; os botões têm ≥ 24 px; as
setas andam entre os botões, `Enter` insere, `Esc` volta ao editor; o menu NAG ▸ e o
Figurina ▸ são dinâmicos; `=` é ambíguo e o código não o adivinha (AC-ED05-6); e no
modo código o símbolo entra como texto.

Rodar sem pytest:      python tests/test_editor_paleta.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m
from editor_ambiente import Janela
from ui.editor.paleta import FIGURINAS, LADO_DO_BOTAO_PX, codigo_do_simbolo, precisa_da_fonte_de_simbolos


def _trechos(t):
    bloco_id, _d = t.texto.posicao()
    return t.texto.modelo_de(bloco_id).trechos


def test_ac6_o_botao_da_paleta_insere_o_nag_com_codigo_e_familia():
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.ir_para(texto.ordem[1], 0)
        painel = j.xadrez_controlador.painel
        assert painel is j.xadrez and painel.botao("⩲") is not None
        painel.botao("⩲").invoke()
        tr = next(tr for tr in _trechos(t) if tr.texto == "⩲")
        assert tr.papel == "nag" and tr.nag == 14 and tr.familia == "simbolos"
        assert j.campos["aviso"].cget("text").startswith("⩲")                       # o eco na barra de status
        # ± é Latin-1: sem família; e o código é 16
        j.barra_de_xadrez.simbolos["±"].invoke()
        tr = next(tr for tr in _trechos(t) if tr.texto == "±")
        assert tr.papel == "nag" and tr.nag == 16 and not tr.familia
        # uma figurina: papel="figurina", sem código
        painel.botao("♘").invoke()
        tr = next(tr for tr in _trechos(t) if tr.texto == "♘")
        assert tr.papel == "figurina" and tr.nag is None
        # o XHTML leva o código
        x = texto.sincronizar()
        codigo = __import__("core.editor.xhtml", fromlist=["escrever"]).escrever(x)
        assert 'data-nag="14"' in codigo and 'data-nag="16"' in codigo
        # = é ambíguo: sem código, e marcar_nags o deixa de fora
        assert codigo_do_simbolo("=") is None and codigo_do_simbolo("∞") is None and codigo_do_simbolo("⩲") == 14
        assert precisa_da_fonte_de_simbolos("⩲") and not precisa_da_fonte_de_simbolos("±")
        assert [s for s, _n in FIGURINAS] == ["♔", "♕", "♖", "♗", "♘", "♙"]


def test_os_botoes_tem_24_px_e_o_teclado_anda_insere_e_sai():
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.ir_para(texto.ordem[1], 0)
        painel = j.xadrez_controlador.painel
        j.update_idletasks()
        for grade in painel.grades:
            for botao in grade.botoes:
                assert botao.winfo_reqwidth() >= LADO_DO_BOTAO_PX and botao.winfo_reqheight() >= LADO_DO_BOTAO_PX
        for botao in j.barra_de_xadrez.simbolos.values():
            assert botao.winfo_reqwidth() >= LADO_DO_BOTAO_PX and botao.winfo_reqheight() >= LADO_DO_BOTAO_PX
        # a paleta de figurinas: o foco no primeiro botão; a seta anda; Enter insere; Esc volta ao editor
        j.executar("paleta_de_figurinas")
        assert j.paineis["xadrez"].visivel
        grade = painel.grades[0]
        assert grade._mover(0, 1) == "break"
        botao = grade.botoes[1]
        assert {"<Key-Return>", "<Key-Escape>", "<Key-Left>", "<Key-Right>", "<Key-Up>", "<Key-Down>"} <= set(botao.bind())
        botao.invoke()                                                    # o que o Enter faz (a janela está oculta)
        assert any(tr.texto == "♕" and tr.papel == "figurina" for tr in _trechos(t))
        assert grade.ao_sair == j.foco_no_editor                          # o Esc volta ao editor
        assert grade._mover(len(grade.botoes) - 1, 1) == "break"          # no fim, fica onde está
        # a paleta de NAGs foca a segunda grade
        j.executar("paleta_de_nags")
        assert len(painel.grades) >= 2
        # os itens dinâmicos dos menus
        itens = j.itens_dinamicos["nags"]()
        assert any(rotulo.startswith("⩲") and "($14)" in rotulo for rotulo, _c in itens)
        assert any(rotulo.startswith("=") and "($" not in rotulo for rotulo, _c in itens)
        figurinas = j.itens_dinamicos["figurinas"]()
        assert [r.split()[0] for r, _c in figurinas] == [s for s, _n in FIGURINAS]
        figurinas[4][1]()
        assert "♕♘" in "".join(tr.texto for tr in _trechos(t) if tr.papel == "figurina")   # juntas num trecho só
        # no modo código o símbolo entra como texto
        j.executar("alternar_modo")
        j.executar("inserir_simbolo_de_xadrez", "⩲")
        assert "⩲" in j._codigo().texto_todo()


def test_a_lista_de_todos_os_nags_insere_pelo_padrao_e_os_menus_de_lado_dependem_do_cursor():
    with Janela() as t:
        j = t.j
        texto = t.texto
        painel = j.xadrez_controlador.painel
        texto.ir_para(texto.ordem[1], 0)
        painel.lista.selection_set(0)
        painel._inserir_da_lista()
        primeiro = painel._da_lista[0]
        assert any(tr.texto == primeiro.simbolo for tr in _trechos(t))
        assert j.itens_dinamicos["lado"]()[0][0].startswith("(o cursor não está num diagrama)")
        d = next(b for b in texto.sincronizar().blocos if isinstance(b, m.Diagrama))
        texto.selecionar_objeto(d.id)
        rotulos = [r for r, _c in j.itens_dinamicos["lado"]()]
        assert len(rotulos) == 6 and rotulos[2].startswith("✓ ") and "Lado desconhecido" in rotulos[2]
        assert any("Indicador: nenhum" in r and r.startswith("✓") for r in rotulos)
        assert len(j.itens_dinamicos["figurinas_letras"]()) == 10
        assert len(j.itens_dinamicos["numerar"]()) == 6


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
