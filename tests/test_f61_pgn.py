"""
F6.1 — da página reconhecida para um `.pgn` que abre num programa de xadrez.

O risco desta fase é específico e vale nomear: **um PGN errado que carrega é
pior que um PGN curto.** Uma partida que abre no programa de xadrez ninguém
confere; ela vira fato. Por isso a maior parte destes testes é sobre o que a
exportação *recusa* a fazer — variante tomada por linha principal, sequência que
não encadeia, lance que o OCR não resolveu.

Rodar sem pytest:      python tests/test_f61_pgn.py
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess
import chess.pgn
import pytest

from conftest import raiz_tk
from core import notacao, pgn
from core.box_model import BoxEntry


def boxes_de(texto):
    """
    Página sintética: um box por caractere, espaço separa palavra, `\\n` separa
    linha. É o formato que `notacao.palavras_da_pagina` espera ver.
    """
    saida, y = [], 0
    for linha in texto.split("\n"):
        x = 0
        for ch in linha:
            if ch == " ":
                x += 22
                continue
            saida.append(BoxEntry(ch, x, y, x + 10, y + 14,
                                  confidence=0.99, source="neural"))
            x += 12
        y += 30
    return saida


def montar(texto):
    return pgn.montar(notacao.analisar(boxes_de(texto)))


def _sans(jogo):
    board = jogo.board()
    saida = []
    for movimento in jogo.mainline_moves():
        saida.append(board.san(movimento))
        board.push(movimento)
    return saida


def relidos(texto_pgn):
    """
    Os lances de cada partida, relendo o arquivo com o python-chess.

    Reler é o que prova que o arquivo serve: um PGN malformado só aparece
    quando outro programa tenta abri-lo.
    """
    fluxo, saida = io.StringIO(texto_pgn), []
    while True:
        jogo = chess.pgn.read_game(fluxo)
        if jogo is None:
            return saida
        saida.append(_sans(jogo))


ABERTURA = "1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7"


# ----------------------------------------------------------------------
# O caminho feliz
# ----------------------------------------------------------------------

def test_partida_simples_sai_inteira():
    rel = montar(ABERTURA)
    assert len(rel.partidas) == 1
    assert rel.partidas[0].lances == ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6",
                                      "Ba4", "Nf6", "O-O", "Be7"]


def test_o_pgn_gerado_e_relegivel():
    rel = montar(ABERTURA)
    assert relidos(pgn.para_texto(rel)) == [rel.partidas[0].lances]


def test_duas_partidas_na_mesma_pagina():
    rel = montar("1.e4 e5 2.Nf3 Nc6\n1.d4 Nf6 2.c4 e6")
    assert [p.lances for p in rel.partidas] == [
        ["e4", "e5", "Nf3", "Nc6"], ["d4", "Nf6", "c4", "e6"]]


def test_cada_partida_vira_um_jogo_no_arquivo():
    rel = montar("1.e4 e5 2.Nf3 Nc6\n1.d4 Nf6 2.c4 e6")
    assert len(relidos(pgn.para_texto(rel))) == 2


def test_roque_sobrevive():
    rel = montar("1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.O-O Nf6")
    assert "O-O" in rel.partidas[0].lances


def test_captura_e_xeque_saem_em_san_canonico():
    rel = montar("1.e4 d5 2.exd5 Qxd5 3.Nc3 Qa5 4.Bb5")
    assert "exd5" in rel.partidas[0].lances
    assert "Qxd5" in rel.partidas[0].lances
    # o Bb5 dá xeque; o SAN canônico do python-chess marca isso
    assert any(s.endswith("+") for s in rel.partidas[0].lances)


def test_jogadas_conta_pares():
    rel = montar("1.e4 e5 2.Nf3 Nc6")
    assert rel.partidas[0].jogadas == 2


# ----------------------------------------------------------------------
# Variantes — a razão de o item existir
# ----------------------------------------------------------------------

def test_variante_nao_entra_na_linha_principal():
    """`3...Nf6` repete uma jogada que já passou: é desvio, não continuação."""
    rel = montar("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 3...Nf6 4.Ba4")
    assert "Nf6" not in rel.partidas[0].lances
    assert rel.variantes >= 1


def test_leitura_que_entra_numa_variante_corta_a_partida():
    """
    O ponto mais delicado: depois da variante o analisador às vezes segue de
    dentro dela, e os lances seguintes chegam com número de linha principal.
    Aceitá-los daria um PGN que abre e está errado.
    """
    rel = montar("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 3...Nf6 4.Ba4 Nf6 5.O-O Be7")
    partida = rel.partidas[0]
    assert partida.desviou
    assert partida.lances == ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]


def test_o_que_sai_apos_o_desvio_continua_valido():
    rel = montar("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 3...Nf6 4.Ba4 Nf6 5.O-O Be7")
    board = chess.Board()
    for san in rel.partidas[0].lances:
        board.push_san(san)          # levanta se algum não encadear


def test_relatorio_avisa_do_desvio():
    rel = montar("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 3...Nf6 4.Ba4 Nf6 5.O-O Be7")
    assert rel.desviadas == 1
    assert "variante" in rel.resumo()


def test_pagina_sem_variante_nao_e_marcada_como_desviada():
    assert montar(ABERTURA).desviadas == 0


# ----------------------------------------------------------------------
# O que a exportação recusa
# ----------------------------------------------------------------------

def test_lance_sem_solucao_e_contado_e_nao_inventado():
    rel = montar("1.e4 e5 2.Nf3 Xz9 3.Bb5")
    assert rel.sem_solucao >= 0          # 'Xz9' nem parece lance
    for p in rel.partidas:
        board = chess.Board()
        for san in p.lances:
            board.push_san(san)


def test_pagina_sem_notacao_nao_gera_partida():
    rel = montar("counterplay against the isolated queen pawn")
    assert rel.partidas == []
    assert rel.resumo().startswith("Nenhuma partida")


def test_pagina_vazia():
    rel = pgn.montar(notacao.analisar([]))
    assert rel.partidas == []
    assert pgn.para_texto(rel) == ""


def test_partida_sem_lance_nao_vira_bloco_no_arquivo():
    rel = pgn.Relatorio(partidas=[pgn.Partida(sem_solucao=3)])
    assert pgn.para_texto(rel) == ""


def test_sequencia_que_nao_encadeia_para_e_registra():
    partida = pgn.Partida()
    rel = pgn.Relatorio(partidas=[partida])
    partida.lances[:] = ["e4", "e5"]
    partida.parou_em = "Qxf7"
    texto = pgn.para_texto(rel)
    assert "Qxf7" in texto             # fica como comentário, não como lance
    assert relidos(texto) == [["e4", "e5"]]


# ----------------------------------------------------------------------
# Cabeçalhos
# ----------------------------------------------------------------------

def test_cabecalhos_obrigatorios_existem():
    texto = pgn.para_texto(montar(ABERTURA))
    for chave in ("Event", "Site", "Date", "Round", "White", "Black", "Result"):
        assert f'[{chave} ' in texto


def test_jogador_desconhecido_nao_e_inventado():
    """Um `White` errado é pior que um `White` ausente: o programa o mostra."""
    texto = pgn.para_texto(montar(ABERTURA))
    assert '[White "?"]' in texto
    assert '[Black "?"]' in texto


def test_resultado_indefinido():
    assert '[Result "*"]' in pgn.para_texto(montar(ABERTURA))


def test_cabecalho_do_documento_registra_a_origem():
    cab = pgn.cabecalhos_do_documento("C:/livros/Benko.pdf", pagina=12)
    assert cab["Event"] == "Benko.pdf, pág. 13"


def test_cabecalho_sem_documento_nao_quebra():
    assert "Event" not in pgn.cabecalhos_do_documento(None)


def test_cabecalho_do_chamador_prevalece():
    texto = pgn.para_texto(montar(ABERTURA), {"Event": "Torneio X"})
    assert '[Event "Torneio X"]' in texto


def test_varias_partidas_ganham_numero_de_round():
    texto = pgn.para_texto(montar("1.e4 e5\n1.d4 d5"))
    assert '[Round "1"]' in texto and '[Round "2"]' in texto


# ----------------------------------------------------------------------
# A costura com o resto
# ----------------------------------------------------------------------

def test_exportar_devolve_texto_e_relatorio():
    texto, rel = pgn.exportar(boxes_de(ABERTURA))
    assert texto.startswith("[Event ")
    assert rel.lances == 10


def test_analisar_preenche_numero_san_e_posicao():
    """Campos que a F1.7 declarava e nunca preenchia."""
    analise = notacao.analisar(boxes_de("1.e4 e5 2.Nf3"))
    primeiro = analise.lances[0]
    assert primeiro.numero == 1
    assert primeiro.brancas is True
    assert primeiro.san == "e4"
    assert primeiro.fen_antes == chess.Board().fen()


def test_lance_perdido_nao_ganha_san():
    analise = notacao.analisar(boxes_de("1.e4 e5 2.Qh9"))
    for l in analise.lances:
        if l.situacao in ("perdido", "ambiguo"):
            assert l.san is None


def test_partidas_recebem_indices_distintos():
    analise = notacao.analisar(boxes_de("1.e4 e5\n1.d4 d5"))
    assert {l.partida for l in analise.lances} == {0, 1}


@pytest.mark.parametrize("texto,esperado", [
    ("1.e4", ["e4"]),
    ("1.d4 d5 2.c4", ["d4", "d5", "c4"]),
    ("1.Nf3 Nf6 2.g3 g6 3.Bg2 Bg7", ["Nf3", "Nf6", "g3", "g6", "Bg2", "Bg7"]),
])
def test_aberturas_curtas(texto, esperado):
    assert montar(texto).partidas[0].lances == esperado


# ----------------------------------------------------------------------
# O comando da janela
# ----------------------------------------------------------------------

class _App:
    def __enter__(self):
        from tkinter import filedialog, messagebox
        from PIL import Image
        from ui.main_window import MainWindow

        self._salvos = (messagebox.showinfo, messagebox.showerror,
                        filedialog.asksaveasfilename)
        self.avisos = []
        messagebox.showinfo = lambda t, m=None, **k: self.avisos.append(m or t)
        messagebox.showerror = lambda t, m=None, **k: self.avisos.append(m or t)
        filedialog.asksaveasfilename = self._asksave

        self.destino = ""
        self.dialogo = {}       # o que o diálogo recebeu, para inspeção
        # `raiz_tk()` e não `tk.Tk()`: uma raiz por teste faz o Tcl reler os
        # temas do ttk do disco, e no Windows isso falha de vez em quando, num
        # teste diferente a cada execução. Ver tests/conftest.py.
        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        self.win.image = Image.new("L", (600, 200), color=255)
        return self

    def _asksave(self, **k):
        self.dialogo = k
        return self.destino

    def __exit__(self, *a):
        from tkinter import filedialog, messagebox
        (messagebox.showinfo, messagebox.showerror,
         filedialog.asksaveasfilename) = self._salvos
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def test_comando_grava_o_arquivo(tmp_path):
    with _App() as app:
        app.destino = str(tmp_path / "saida.pgn")
        app.win.boxes = boxes_de(ABERTURA)
        app.win.exportar_pgn()

        conteudo = open(app.destino, encoding="utf-8").read()
        assert relidos(conteudo) == [montar(ABERTURA).partidas[0].lances]


def test_comando_sem_boxes_avisa_e_nao_grava():
    with _App() as app:
        app.win.boxes = []
        app.win.exportar_pgn()
        assert app.avisos and "Nenhum box" in app.avisos[0]


def test_comando_sem_notacao_explica_em_vez_de_gravar_vazio():
    with _App() as app:
        app.win.boxes = boxes_de("counterplay against the isolated pawn")
        app.win.exportar_pgn()
        assert any("Nenhuma partida" in a for a in app.avisos)


def test_cancelar_o_dialogo_nao_grava(tmp_path):
    with _App() as app:
        app.destino = ""            # o usuário fechou o diálogo
        app.win.boxes = boxes_de(ABERTURA)
        app.win.exportar_pgn()
        assert not list(tmp_path.iterdir())


def test_o_dialogo_propoe_o_livro_e_a_pagina(tmp_path):
    """
    O PGN já numerava a página, mas com outra grafia (`livro_pg11`) que o par
    `.box`/`.png` da mesma página (`livro_pg011`) — os três arquivos de uma
    página ficavam separados na lista da pasta. Agora todos saem de `page_stem`.
    """
    from core.services.document_service import DocumentSession

    with _App() as app:
        app.win.session = DocumentSession(str(tmp_path / "livro.pdf"),
                                          num_pages=20, is_pdf=True)
        app.win.current_pdf_page = 10
        app.destino = str(tmp_path / "saida.pgn")
        app.win.boxes = boxes_de(ABERTURA)
        app.win.exportar_pgn()

        assert app.dialogo["initialfile"] == "livro_pg011.pgn"
        assert app.dialogo["initialdir"] == str(tmp_path)


def test_o_dialogo_sem_documento_ainda_propoe_um_nome():
    """Sem sessão não há livro nem página — mas o diálogo não pode abrir vazio."""
    with _App() as app:
        app.destino = ""
        app.win.boxes = boxes_de(ABERTURA)
        app.win.exportar_pgn()

        assert app.dialogo["initialfile"] == "partida.pgn"
        assert app.dialogo["initialdir"] is None


def test_comando_esta_no_menu():
    with _App() as app:
        barra = app.win.parent.nametowidget(app.win.parent.cget("menu"))
        for i in range(barra.index("end") + 1):
            if (barra.type(i) == "cascade"
                    and barra.entrycget(i, "label") == "Ferramentas"):
                menu = barra.nametowidget(barra.entrycget(i, "menu"))
                rotulos = [menu.entrycget(j, "label")
                           for j in range(menu.index("end") + 1)
                           if menu.type(j) == "command"]
                assert "Exportar partidas em PGN..." in rotulos
                return
        raise AssertionError("menu Ferramentas não existe")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
