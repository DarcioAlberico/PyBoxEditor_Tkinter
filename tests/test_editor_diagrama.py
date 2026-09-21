"""
Testes do diagrama na janela (ED-05; SPEC_EDITOR §11.1–§11.3, DEC-06): `inserir_diagrama`
com o diálogo injetado grava `lado="b"`, salvar/reabrir mantém tudo e o XHTML leva
`data-lado="b"` (AC-ED05-1); `editar_posicao`, girar, coordenadas, o indicador `marca`
desenha o quadradinho no PNG (pixel conferido) e na tela, lado `""` → sem quadradinho e
aviso (AC-ED05-2); `diagrama_dos_lances` no cursor; `validar_notacao` lista em Resultados
com a tag `notacao-ilegal` (`bgstipple gray25`) e o `✗` na calha (AC-ED05-4); marcar
lances/NAGs, numerar e referência pela janela (AC-ED05-7); a `DialogoDeDiagrama` lê e
devolve; e o AC-ED02-7 repetido sem `cv2` (AC-ED05-9).

Rodar sem pytest:      python tests/test_editor_diagrama.py
"""

import io
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import epub, modelo as m, xhtml
from editor_ambiente import Janela
from ui.editor.calha import ICONES
from ui.editor.diagrama import DialogoDeDiagrama, ObjetoDeDiagrama

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEN_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


def _diagrama_do_teste():
    return m.Diagrama(fen=FEN_E4, lado="b", lado_indicador="marca", numero=None, modo="png")


# ----------------------------------------------------------------------
# AC-ED05-1
# ----------------------------------------------------------------------

def test_ac1_inserir_diagrama_com_o_dialogo_injetado_salva_reabre_e_leva_data_lado(tmp_path):
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.ir_para(texto.ordem[1], 0)
        t.caixas.diagrama_resposta = _diagrama_do_teste()
        bloco_id = j.executar("inserir_diagrama")
        assert bloco_id and t.caixas.chamadas[-1][0] == "diagrama"
        blocos = texto.sincronizar().blocos
        d = next(b for b in blocos if b.id == bloco_id)
        assert isinstance(d, m.Diagrama) and d.fen == FEN_E4 and d.lado == "b" and d.lado_indicador == "marca"
        assert blocos.index(d) == 2                                                    # entrou depois do bloco do cursor
        assert isinstance(texto.widget_do_objeto(bloco_id), ObjetoDeDiagrama)
        assert any("indicador" in texto.widget_do_objeto(bloco_id).canvas.gettags(i)
                   for i in texto.widget_do_objeto(bloco_id).canvas.find_all())            # o quadradinho na tela
        assert 'data-lado="b"' in xhtml.escrever(texto.sincronizar())
        destino = str(tmp_path / "salvo.epub")
        j.executar("salvar_como", destino)
        relido, _r = epub.ler(destino)
        d2 = next(b for b in relido.capitulos[0].blocos if isinstance(b, m.Diagrama) and b.fen == FEN_E4)
        assert d2.lado == "b" and d2.lado_indicador == "marca" and d2.modo == "png"
        # o mesmo comando no modo código insere a <figure>
        j.executar("alternar_modo")
        t.caixas.diagrama_resposta = m.Diagrama(fen="8/8/8/8/8/8/8/K6k w - - 0 1")
        assert j.executar("inserir_diagrama")
        assert 'data-fen="8/8/8/8/8/8/8/K6k w - - 0 1"' in j._codigo().texto_todo()
        # cancelar não insere nada
        t.caixas.diagrama_resposta = None
        assert j.executar("inserir_diagrama") is None


# ----------------------------------------------------------------------
# AC-ED05-2
# ----------------------------------------------------------------------

def test_ac2_editar_posicao_girar_coordenadas_e_o_quadradinho_no_png_e_na_tela():
    from PIL import Image
    from core import render_diagrama as rd

    with Janela() as t:
        j = t.j
        texto = t.texto
        d = next(b for b in texto.sincronizar().blocos if isinstance(b, m.Diagrama))
        texto.selecionar_objeto(d.id)
        # editar posição com o diálogo injetado
        novo = m.Diagrama(fen=FEN_E4, lado="w", lado_indicador="marca")
        t.caixas.diagrama_resposta = novo
        assert j.executar("editar_posicao").fen == FEN_E4
        atual = texto.modelo_de(d.id)
        assert atual.fen == FEN_E4 and atual.lado == "w" and atual.id == d.id
        assert t.caixas.chamadas[-1][0] == "diagrama" and t.caixas.chamadas[-1][1].id == d.id
        # girar e coordenadas
        texto.selecionar_objeto(d.id)
        assert j.executar("girar_diagrama") == "preta" and texto.modelo_de(d.id).orientacao == "preta"
        texto.selecionar_objeto(d.id)
        assert j.executar("coordenadas_do_diagrama") is True and texto.modelo_de(d.id).coordenadas
        widget = texto.widget_do_objeto(d.id)
        assert widget.canvas.find_withtag("coordenada") and widget.canvas.find_withtag("indicador")
        # lado "" → sem quadradinho, com aviso
        texto.selecionar_objeto(d.id)
        assert j.executar("lado_a_jogar", "") == ""
        atual = texto.modelo_de(d.id)
        assert atual.lado == "" and atual.lado_indicador == ""
        widget = texto.widget_do_objeto(d.id)
        assert not widget.canvas.find_withtag("indicador")
        avisos = [w.cget("text") for w in widget.winfo_children() if hasattr(w, "cget") and w is not widget.canvas]
        assert any("lado a jogar desconhecido" in a for a in avisos)
        texto.selecionar_objeto(d.id)
        j.executar("indicador_de_lado", "marca")
        assert "desconhecido" in t.caixas.entradas()[-1]                          # sem lado não há indicador
        # sem diagrama sob o cursor: erro de entrada
        texto.ir_para(texto.ordem[1], 0)
        j.executar("girar_diagrama")
        assert "sobre um diagrama" in t.caixas.entradas()[-1]
    # o PNG: o pixel do quadradinho
    png, largura, altura = rd.desenhar(FEN_E4.split()[0], lado_px=256, lado_a_jogar="w")
    img = Image.open(io.BytesIO(png)).convert("L")
    casa = 256 / 8
    calha = round(casa * rd.GUTTER_INDICADOR)
    quadro = casa * rd.LADO_DO_INDICADOR
    _tracos, margem = rd.filetes("simples", casa)
    x = largura - calha + (calha - quadro) / 2
    y = margem + 256 - quadro                                                          # brancas: embaixo
    ym = int(y + quadro / 2)
    assert img.getpixel((int(x + quadro / 2), ym)) > 200                               # miolo branco
    assert min(img.getpixel((xx, ym)) for xx in range(int(x) - 1, int(x) + 3)) <= 100  # a borda preta (4 tons)
    png_b, largura_b, _a = rd.desenhar(FEN_E4.split()[0], lado_px=256, lado_a_jogar="b")
    img_b = Image.open(io.BytesIO(png_b)).convert("L")
    y_b = margem
    assert img_b.getpixel((int(x + quadro / 2), int(y_b + quadro / 2))) <= 100        # pretas: em cima, preto
    assert img_b.getpixel((int(x + quadro / 2), int(y + quadro / 2))) > 200            # e nada embaixo
    png_sem, largura_sem, _a = rd.desenhar(FEN_E4.split()[0], lado_px=256)
    assert largura_sem == largura - calha                                              # sem lado, sem calha
    assert rd.largura_em_casas(FEN_E4, indicador=True) == rd.largura_em_casas(FEN_E4) + rd.GUTTER_INDICADOR
    d = m.Diagrama(fen=FEN_E4, lado="b", lado_indicador="marca")
    assert epub.png_do_diagrama(d)[1] > epub.png_do_diagrama(m.Diagrama(fen=FEN_E4, lado="b"))[1]


# ----------------------------------------------------------------------
# AC-ED05-3/4 na janela
# ----------------------------------------------------------------------

def _capitulo_de_notacao():
    livro = editor_livros.livro_completo()
    cap = livro.capitulos[0]
    cap.blocos = [m.Titulo(trechos=[m.Trecho(texto="Partida")], nivel=2),
                  m.Paragrafo(trechos=[m.Trecho(texto="1.e4 e5 2.Nf3 Nc6 3.Bb6 a6")], estilo="notacao"),
                  m.Paragrafo(trechos=[m.Trecho(texto="prosa com Nf3")]),
                  m.Paragrafo(trechos=[m.Trecho(texto="4.Ba4 Nf6 (4...d6 5.c3) 5.O-O")], estilo="notacao")]
    return livro


def test_ac3_ac4_diagrama_dos_lances_e_validar_notacao_na_janela(tmp_path):
    caminho = str(tmp_path / "notacao.epub")
    epub.escrever(_capitulo_de_notacao(), caminho)
    with Janela(abrir=False) as t:
        j = t.j
        j.executar("abrir", caminho)
        texto = t.texto
        # validar: Resultados, a tag e o ✗
        resultados = j.executar("validar_notacao")
        assert [r.mensagem for r in resultados] == ["Bb6 não é legal aqui; talvez Bb5"]
        assert j.resultados.itens[0].dados["sugestao"] == "Bb5" and j.resultados.itens[0].onde == "bloco 2"
        assert texto.texto.tag_cget("notacao-ilegal", "bgstipple") == "gray25"
        faixas = texto.texto.tag_ranges("notacao-ilegal")
        assert len(faixas) == 2 and texto.texto.get(faixas[0], faixas[1]) == "Bb6"
        assert texto.calha.icone_de(texto.ordem[1]) == "notacao-ilegal" and ICONES["notacao-ilegal"][0] == "✗"
        assert m.texto_de(texto.sincronizar().blocos[1]) == "1.e4 e5 2.Nf3 Nc6 3.Bb6 a6"   # o texto não muda
        # ativar o resultado seleciona o lance
        j.resultados.ativar(0)
        sel = texto.selecao()
        assert sel and texto.texto.get(*sel) == "Bb6"
        # o livro inteiro
        assert len(j.executar("validar_notacao_livro")) == 1
        # diagrama a partir dos lances: corrigido o Bb6, a posição depois de 3.Bb5 a6
        texto.selecionar(len("1.e4 e5 2.Nf3 Nc6 3."), len("1.e4 e5 2.Nf3 Nc6 3.Bb6"), texto.ordem[1])
        texto.apagar_selecao()
        texto.inserir("Bb5")
        assert j.executar("validar_notacao") == [] and not texto.texto.tag_ranges("notacao-ilegal")
        assert texto.calha.icone_de(texto.ordem[1]) is None
        texto.ir_para(texto.ordem[1], len("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6"))
        novo_id = j.executar("diagrama_dos_lances")
        d = texto.modelo_de(novo_id)
        assert isinstance(d, m.Diagrama) and d.lado == "w"
        assert d.fen.startswith("r1bqkbnr/1ppp1ppp/p1n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w")
        # o cursor numa variante: a posição da variante
        blocos = texto.sincronizar().blocos
        ultimo = blocos[-1].id
        texto.ir_para(ultimo, len("4.Ba4 Nf6 (4...d6 5.c3"))
        j.executar("diagrama_dos_lances")
        d2 = [b for b in texto.sincronizar().blocos if isinstance(b, m.Diagrama)][-1]
        assert "2P2N2" in d2.fen.split()[0] and d2.lado == "b"                        # 5.c3 jogado, pretas
        # fora de uma linha de jogo
        texto.ir_para(texto.ordem[0], 0)
        j.executar("diagrama_dos_lances")
        assert "linha de jogo" in t.caixas.entradas()[-1]


# ----------------------------------------------------------------------
# AC-ED05-7 na janela
# ----------------------------------------------------------------------

def test_ac7_marcar_lances_e_nags_numerar_e_referencia_pela_janela(tmp_path):
    livro = _capitulo_de_notacao()
    livro.capitulos[0].blocos[1].trechos = [m.Trecho(texto="1.e4 e5 2.Nf3± Nc6 = 3.Bb5")]
    caminho = str(tmp_path / "marcar.epub")
    epub.escrever(livro, caminho)
    with Janela(abrir=False) as t:
        j = t.j
        j.executar("abrir", caminho)
        texto = t.texto
        assert j.executar("marcar_lances") == 10
        assert [tr.texto for tr in texto.sincronizar().blocos[1].trechos if tr.papel == "lance"][:3] == ["e4", "e5", "Nf3"]
        n, ambiguos = j.executar("marcar_nags")
        assert n == 1 and ambiguos == ["="]
        assert next(tr for tr in texto.sincronizar().blocos[1].trechos if tr.papel == "nag").nag == 16
        # numerar e referência
        t.caixas.diagrama_resposta = m.Diagrama(fen=FEN_E4, lado="b")
        texto.ir_para(texto.ordem_do_capitulo[-1], 0)
        d_id = j.executar("inserir_diagrama")
        numeros = j.executar("numerar_objetos", "diagrama")
        assert numeros == {f"cap1.xhtml#{d_id}": 1} and texto.modelo_de(d_id).numero == 1
        texto.ir_para(texto.ordem[2], 5)
        assert j.executar("inserir_referencia", f"cap1.xhtml#{d_id}") == "Diagrama 1"
        par = texto.sincronizar().blocos[2]
        ref = next(tr for tr in par.trechos if tr.ref)
        assert ref.texto == "Diagrama 1" and ref.ref == "diagrama" and ref.link == f"#{d_id}"
        # um segundo diagrama antes renumera: a referência vira "Diagrama 2"
        texto.ir_para(texto.ordem[0], 0)
        t.caixas.diagrama_resposta = m.Diagrama(fen="8/8/8/8/8/8/8/K6k w - - 0 1")
        j.executar("inserir_diagrama")
        j.executar("numerar_objetos", "diagrama")
        par = next(b for b in texto.sincronizar().blocos if any(tr.ref for tr in getattr(b, "trechos", [])))
        assert next(tr for tr in par.trechos if tr.ref).texto == "Diagrama 2"
        # marcar jogador/abertura: o h2 "Partida" não é "Nome – Nome"
        j.executar("marcar_jogador")
        assert "nenhum cabeçalho" in t.caixas.entradas()[-1]
        # fonte de diagrama do livro
        assert j.executar("fonte_de_diagrama", "ChessMerida-Diagram") == 2
        assert all(b.fonte == "ChessMerida-Diagram" for b in texto.sincronizar().blocos if isinstance(b, m.Diagrama))
        assert j._preferencia("fonte_diagrama") == "ChessMerida-Diagram"
        # cabeçalho em legenda: o h2 "Partida" é seguido do diagrama K6k → vira a legenda dele e some
        blocos = texto.sincronizar().blocos
        h2 = next(b for b in blocos if isinstance(b, m.Titulo) and b.nivel == 2)
        texto.ir_para(h2.id, 0)
        d = j.executar("cabecalho_em_legenda")
        assert isinstance(d, m.Diagrama) and "".join(tr.texto for tr in d.legenda) == "Partida"
        blocos = texto.sincronizar().blocos
        assert h2.id not in [b.id for b in blocos] and "".join(tr.texto for tr in blocos[0].legenda) == "Partida"
        # a paleta e a barra existem
        assert j.xadrez_controlador.painel is not None and len(j.barra_de_xadrez.simbolos) == 6 + 23


def test_a_caixa_do_diagrama_le_e_devolve_o_diagrama_novo():
    from conftest import raiz_tk

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        d = m.Diagrama(fen=FEN_E4, lado="", numero=3, legenda=[m.Trecho(texto="Depois de 1.e4")], modo="fonte",
                       fonte="SkakNew-Diagram", coordenadas=True, moldura="dupla")
        caixa = DialogoDeDiagrama(raiz, d, idioma="pt")
        caixa.construir()
        assert caixa.var_fen.get() == FEN_E4 and caixa.var_lado.get() == "" and caixa.var_numero.get() == "3"
        assert caixa.var_legenda.get() == "Depois de 1.e4" and caixa.var_modo.get() == "fonte"
        assert "desconhecido" in caixa.lbl_legalidade.cget("text")
        assert caixa.tabuleiro.tabuleiro.casa(4, 4).simbolo == "P"
        # o tabuleiro muda → o FEN acompanha; o lado escolhido entra no FEN
        caixa.tabuleiro.selecionada = (4, 4)
        caixa.tabuleiro.limpar_casa()
        assert caixa.var_fen.get().split()[0] == "rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR"
        caixa.var_lado.set("w")
        caixa._do_lado()
        assert caixa.var_fen.get().split()[1] == "w"
        # o FEN digitado vai ao tabuleiro; um inválido não
        caixa.var_fen.set("8/8/8/8/8/8/8/K6k w - - 0 1")
        caixa._do_fen()
        assert len([c for c in caixa.tabuleiro.tabuleiro.casas if c.simbolo]) == 2
        caixa.var_fen.set("nada")
        caixa._do_fen()
        assert "FEN inválido" in caixa.lbl_legalidade.cget("text")
        caixa.var_fen.set("8/8/8/8/8/8/8/K6k w - - 0 1")
        caixa.var_indicador.set("marca")
        caixa.var_coordenadas.set(False)
        caixa.var_numero.set("")
        novo = caixa.confirmar()
        assert isinstance(novo, m.Diagrama) and novo.id == d.id and novo.fen == "8/8/8/8/8/8/8/K6k w - - 0 1"
        assert novo.lado == "w" and novo.lado_indicador == "marca" and novo.numero is None
        assert novo.modo == "fonte" and novo.moldura == "dupla" and not novo.coordenadas
        assert novo.legenda == d.legenda
        # posição impossível é aviso, não recusa
        caixa2 = DialogoDeDiagrama(raiz, m.Diagrama(fen="8/8/8/8/8/8/8/KK5k w - - 0 1", lado="w"))
        caixa2.construir()
        assert "impossível" in caixa2.lbl_legalidade.cget("text")
        assert caixa2.confirmar().fen.startswith("8/8/8/8/8/8/8/KK5k")
    finally:
        raiz.destroy()


def test_ac9_repetido_o_editor_com_diagramas_abre_sem_cv2_nem_fitz(tmp_path):
    caminho = os.path.join(str(tmp_path), "livro.epub")
    epub.escrever(editor_livros.livro_completo(), caminho)
    ambiente = dict(os.environ, PYBOXEDITOR_SETTINGS=os.path.join(str(tmp_path), "settings.json"))
    saida = subprocess.run([sys.executable, "appy.py", "--editor", caminho, "--fechar-apos", "1",
                            "--diagnostico-modulos"], capture_output=True, text=True, cwd=RAIZ, timeout=180,
                           env=ambiente)
    assert saida.returncode == 0, saida.stderr
    linha = next(li for li in saida.stdout.splitlines() if li.startswith("modulos pesados carregados:"))
    for pesado in ("torch", "easyocr", "cv2", "numpy", "fitz", "ui.main_window", "core.diagrama", "core.notacao"):
        assert f"'{pesado}'" not in linha, linha


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
