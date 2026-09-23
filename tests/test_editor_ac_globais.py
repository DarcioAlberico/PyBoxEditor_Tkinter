"""
Os critérios de aceite globais do editor (ED-13; SPEC_EDITOR §12): uma função por AC,
toda ação pelo comando (§14). AC-001 abrir/editar/salvar/reabrir sobre o EPUB de hoje nos
dois modos de diagrama; AC-002 os formatos saem do mesmo livro; AC-003 texto ↔ código
× 10 sem perda; AC-004 nenhuma falha silenciosa; AC-005 desempenho (`slow`, pela
`scripts/medir_editor.py`); AC-006 tudo pelo teclado (os mnemônicos e os itens pelo menu,
o tabuleiro pelo mapa da §11.2, o foco visível — o `F6` está em `test_editor_teclado.py`,
`gui`); AC-007 codificação; AC-008 a ponte; AC-009 o diagrama nunca perde a posição;
AC-010 o rascunho.

Rodar sem pytest:      .venv/Scripts/python.exe tests/test_editor_ac_globais.py
"""

import hashlib
import io
import os
import re
import sys
import tempfile
import tkinter as tk
import zipfile
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import docx_io, epub, html_io, importar_ir, modelo as m, validacao, xhtml
from core.editor.conversao import OpcoesDeConversao
from core.editor.projeto import Rascunho
from editor_ambiente import Janela
from test_editor_importar_ir import documento_sintetico
from test_editor_janela import _Janela as JanelaComRelogio
from ui.editor import menus
from ui.editor.barra import AnelDeFoco
from ui.editor.codigo import EditorDeCodigo
from ui.editor.texto_rico import TextoRico

FEN_NOVO = "8/8/8/8/8/8/8/K6k w - - 0 1"


def _sha1(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def _textos(livro):
    return [m.texto_de(b) for c in livro.capitulos for b in c.blocos if isinstance(b, m.Paragrafo)]


# ----------------------------------------------------------------------
# AC-001
# ----------------------------------------------------------------------

@pytest.mark.parametrize("modo", ["png", "fonte"])
def test_ac001_abrir_editar_salvar_reabrir_o_epub_de_hoje(modo):
    pasta = tempfile.mkdtemp(prefix="pbe-ac001-")
    caminho = editor_livros.epub_de_hoje(pasta, modo)
    with zipfile.ZipFile(caminho) as z:
        nomes_antes = set(z.namelist())
        intocados = {n: z.read(n) for n in nomes_antes if n.rsplit(".", 1)[-1].lower() in ("png", "ttf", "otf", "css")}
    with JanelaComRelogio(abrir=False) as t:
        j = t.j
        j.executar("abrir", caminho)
        texto = j.aba_ativa().widget
        livro = j.projeto.livro
        assert len(livro.capitulos) == 2 and not any(isinstance(b, m.IlhaBruta) for c in livro.capitulos
                                                     for b in c.blocos)
        diagramas = [b for c in livro.capitulos for b in c.blocos if isinstance(b, m.Diagrama)]
        assert len(diagramas) == 3 and all(d.modo == modo for d in diagramas)      # o 4º recorte não tem posição
        # trocar uma palavra
        par = next(b for b in texto.sincronizar().blocos if m.texto_de(b).startswith("Prosa com negrito"))
        texto.selecionar(0, len("Prosa"), par.id)
        texto.apagar_selecao()
        texto.inserir("Verso")
        # mudar a posição de um diagrama (o primeiro do capítulo, recuperado pelo alt no modo png)
        d = next(b for b in texto.sincronizar().blocos if isinstance(b, m.Diagrama))
        assert d.fen != FEN_NOVO
        texto.selecionar_objeto(d.id)
        j.executar("editar_posicao", m.Diagrama(fen=FEN_NOVO, lado="", modo=modo, fonte=d.fonte))
        j.executar("salvar")
        assert not j.projeto.sujo
    relido, relatorio = epub.ler(caminho)
    assert any(m.texto_de(b).startswith("Verso com negrito") for b in relido.capitulos[0].blocos)
    d2 = next(b for b in relido.capitulos[0].blocos if isinstance(b, m.Diagrama))
    assert d2.posicao == FEN_NOVO.split()[0] and d2.lado == ""
    assert not any(isinstance(b, m.IlhaBruta) for c in relido.capitulos for b in c.blocos)
    with zipfile.ZipFile(caminho) as z:
        nomes_depois = set(z.namelist())
        assert nomes_antes <= nomes_depois                                 # nenhuma entrada sumiu
        for nome, dados in intocados.items():
            if nome.endswith(".css"):
                continue                                                  # a folha ganha o bloco pybox:fontes
            assert z.read(nome) == dados, nome                             # recursos não tocados: bytes iguais
    assert epub.validar_estrutura(caminho) == []
    resultado = validacao.validar(caminho)
    if not resultado.sem_java:
        assert resultado.valido, resultado.saida[:800]


# ----------------------------------------------------------------------
# AC-002
# ----------------------------------------------------------------------

def _livro_dos_formatos():
    livro = editor_livros.livro_completo()
    cap = livro.capitulos[0]
    cap.blocos = [m.Titulo(trechos=[m.Trecho(texto="Capítulo um")], nivel=1),
                  m.Paragrafo(trechos=[m.Trecho(texto="Prosa com "), m.Trecho(texto="itálico", italico=True),
                                       m.Trecho(texto=" e ♕.")]),
                  m.Figura(recurso="Images/foto.png", alt="Uma foto"),
                  m.Diagrama(fen=editor_livros.FEN, modo="png"),
                  m.Paragrafo(trechos=[m.Trecho(texto="Segundo parágrafo.")])]
    cap.notas = []
    livro.capitulos[1].blocos = [m.Titulo(trechos=[m.Trecho(texto="Capítulo dois")], nivel=1),
                                 m.Paragrafo(trechos=[m.Trecho(texto="Fim.")])]
    return livro


def test_ac002_epub_html_e_docx_saem_do_mesmo_livro(tmp_path):
    livro = _livro_dos_formatos()
    esperado = _textos(livro)
    epub.escrever(livro, str(tmp_path / "l.epub"))
    html_io.escrever_unico(livro, str(tmp_path / "l.html"))
    docx_io.escrever(livro, str(tmp_path / "l.docx"), OpcoesDeConversao(modo_de_diagrama="png"))
    do_epub, _r = epub.ler(str(tmp_path / "l.epub"))
    do_html, _r = html_io.ler(str(tmp_path / "l.html"))
    do_docx, _r = docx_io.ler(str(tmp_path / "l.docx"))
    assert _textos(do_epub) == esperado and _textos(do_html) == esperado and _textos(do_docx) == esperado
    with zipfile.ZipFile(str(tmp_path / "l.docx")) as z:
        documento = z.read("word/document.xml").decode("utf-8")
    assert 'w:val="Heading1"' in documento and "<w:i/>" in documento and "<w:drawing>" in documento
    html = open(tmp_path / "l.html", encoding="utf-8").read()
    assert f'data-fen="{editor_livros.FEN}"' in html and "<em>itálico</em>" in html


# ----------------------------------------------------------------------
# AC-003
# ----------------------------------------------------------------------

def test_ac003_modo_texto_e_codigo_dez_vezes_sem_perda():
    with Janela() as t:
        j = t.j
        aba = j.aba_ativa()
        livro = j.projeto.livro
        cap = livro.capitulo(aba.arquivo)
        cap.blocos.insert(2, m.Paragrafo(trechos=[m.Trecho(texto="Com espaço" + chr(0xA0) + "duro e "),
                                                    m.Trecho(texto="", ilha="<cite>Obra</cite>"),
                                                    m.Trecho(texto=" e "), m.Trecho(texto="", ilha="<!-- nota -->")]))
        j._recarregar_aba(aba)
        aba = j.aba_ativa()

        def canonico():
            return xhtml.canonico(xhtml.escrever(livro.capitulo(aba.arquivo),
                                                 pasta_de_imagens=epub.pasta_de_imagens(livro)))

        antes = canonico()
        assert "<svg" in antes and "<cite>Obra</cite>" in antes and chr(0xA0) in antes and "<!-- nota -->" in antes
        svg_antes = re.search(r"<svg.*?</svg>", antes, re.S).group(0)
        for _ in range(10):
            j.executar("alternar_modo")
        assert isinstance(aba.widget, TextoRico)                            # dez vezes: volta ao texto
        depois = canonico()
        assert depois == antes
        assert re.search(r"<svg.*?</svg>", depois, re.S).group(0) == svg_antes
        assert "&nbsp;" not in depois and "<!-- nota -->" in depois


# ----------------------------------------------------------------------
# AC-004
# ----------------------------------------------------------------------

def test_ac004_nenhuma_falha_silenciosa():
    with JanelaComRelogio() as t:
        j = t.j
        hash_antes = _sha1(t.epub)
        for estrago in ("<b>", '<span epub:type="noteref">x</span>'):
            aba = j.aba_ativa()
            if aba.modo == "texto":
                j.executar("alternar_modo")
            editor = aba.widget
            texto = editor.texto_todo().replace(' xmlns:epub="http://www.idpf.org/2007/ops"', "")
            editor.carregar(texto)
            linha = next(k for k, li in enumerate(texto.split("\n"), start=1) if "<p" in li)
            editor.texto.insert(f"{linha}.0", estrago)
            editor.ir_para(1)
            assert j.executar("alternar_modo") == "codigo" and isinstance(aba.widget, EditorDeCodigo)
            resultado = j.validacao.itens[0]
            assert resultado.onde.startswith("linha ") and "col" in resultado.onde
            assert "linha" in j.campos["aviso"].cget("text") and j.mensagens.contem("linha ")
            assert editor.posicao[0] == resultado.dados["linha"]                 # o cursor no erro
            j.executar("salvar")
            assert "não foi salvo" in t.caixas.entradas()[-1] and _sha1(t.epub) == hash_antes
            editor.carregar(editor.texto_todo().replace(estrago, "").replace(
                "<html ", '<html xmlns:epub="http://www.idpf.org/2007/ops" ', 1) if "epub" in estrago
                else editor.texto_todo().replace(estrago, ""))
            assert j.executar("alternar_modo") == "texto" and len(j.validacao) == 0


# ----------------------------------------------------------------------
# AC-005 (slow)
# ----------------------------------------------------------------------

@pytest.mark.slow
def test_ac005_desempenho_do_livro_grande_dentro_dos_orcamentos():
    """
    A medida roda num processo só dela, como o `appy.py --editor`: o teto de memória é o do
    editor com o livro grande, e o processo do pytest carrega o que a suíte carrega — o
    `conftest` puxa o cv2, a trava das páginas rotuladas puxa o Torch, e no Linux isso sozinho
    já dava 670 MB. Sozinho, o editor com o livro fica em 90 MB (Windows, 2026-09-23).
    """
    import json
    import subprocess

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    codigo = ("import json, sys; sys.path.insert(0, 'scripts'); import medir_editor; "
              "print(json.dumps(medir_editor.medir_livro(capitulos=300, caracteres=300_000, diagramas=500)))")
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, cwd=raiz, timeout=600)
    if saida.returncode != 0 and "no display" in saida.stderr:
        pytest.skip("sem display")
    assert saida.returncode == 0, saida.stderr
    medidas = json.loads(saida.stdout.strip().splitlines()[-1])
    assert medidas["abrir_s"] <= 3.0, medidas
    assert medidas["capitulo_s"] <= 0.5, medidas
    assert medidas["modo_s"] <= 1.0, medidas
    assert medidas["busca_s"] <= 2.0, medidas
    assert medidas["salvar_s"] <= 5.0, medidas
    assert medidas["rss_mb"] <= 600, medidas


# ----------------------------------------------------------------------
# AC-006
# ----------------------------------------------------------------------

def test_ac006_tudo_pelo_teclado_menus_por_mnemonico_tabuleiro_pelo_mapa_e_foco_visivel():
    from core.tabuleiro_edicao import TabuleiroEdicao
    from ui.editor.diagrama import DialogoDeDiagrama

    with Janela() as t:
        j = t.j
        barra = j.menus.barra
        rotulos = [barra.entrycget(i, "label") for i in range(barra.index("end") + 1)]
        assert rotulos == [r for r, _itens in menus.MENUS]
        for i, rotulo in enumerate(rotulos):
            sublinhado = barra.entrycget(i, "underline")
            assert rotulo[int(sublinhado)].lower() == menus.MNEMONICOS_DOS_MENUS[rotulo].lower(), rotulo
        # cada item habilitado com comando é invocável pelo menu, com o comando trocado por um espião
        invocados = []
        for nome in list(j.menus.itens):
            item = menus.item_de(nome)
            if item is None or not item.comando or j.menus.estado(nome) != "normal":
                continue
            original = j.comandos[nome]
            j.comandos[nome] = lambda *a, n=nome, **k: invocados.append(n)
            try:
                j.menus.invocar(nome)
            finally:
                j.comandos[nome] = original
        assert len(invocados) >= 80 and len(set(invocados)) == len(invocados)
        # o diagrama inserido e a posição editada pelo mapa da §11.2 (setas + letra da peça)
        texto = t.texto
        texto.ir_para(texto.ordem[1], 0)
        t.caixas.diagrama_resposta = m.Diagrama(fen="8/8/8/8/8/8/8/K6k w - - 0 1", lado="w")
        bloco_id = j.executar("inserir_diagrama")
        texto.selecionar_objeto(bloco_id)
        caixa = DialogoDeDiagrama(j, texto.modelo_de(bloco_id), idioma="en")
        caixa.construir()
        tab = caixa.tabuleiro
        tab.selecionada = (7, 0)                                            # a1
        for _ in range(4):
            tab._na_tecla(type("E", (), {"keysym": "Right", "char": "", "state": 0})())
        tab._na_tecla(type("E", (), {"keysym": "q", "char": "q", "state": 0})())          # dama branca em e1
        novo = caixa.confirmar()
        assert TabuleiroEdicao.de_fen(novo.fen).casa(7, 4).simbolo == "Q"
        texto.selecionar_objeto(bloco_id)
        assert j.executar("editar_posicao", novo).fen == novo.fen and texto.modelo_de(bloco_id).fen == novo.fen
        # o foco visível: highlightthickness ≥ 2 nos tk focáveis; os botões ttk da janela num AnelDeFoco
        fracos, sem_anel = [], []

        def varrer(widget):
            for filho in widget.winfo_children():
                try:
                    focavel = str(filho.cget("takefocus")) not in ("0", "")
                except tk.TclError:
                    focavel = False
                if isinstance(filho, (tk.Text, tk.Entry, tk.Listbox, tk.Canvas, tk.Button)) and focavel \
                        and not isinstance(filho, ttk.Widget):
                    if int(filho.cget("highlightthickness")) < 2:
                        fracos.append(str(filho))
                if isinstance(filho, ttk.Button) and focavel and not isinstance(filho.master, AnelDeFoco):
                    sem_anel.append(str(filho))
                varrer(filho)

        varrer(j)
        assert not fracos, fracos[:5]
        assert not sem_anel, sem_anel[:5]


# ----------------------------------------------------------------------
# AC-007
# ----------------------------------------------------------------------

def test_ac007_codificacao_utf8_sem_bom_e_sem_entidade_nomeada(tmp_path):
    livro = editor_livros.livro_completo()
    livro.capitulos[0].blocos.insert(1, m.Paragrafo(trechos=[m.Trecho(texto="ç ♕ ⩲ — fim" + chr(0xA0) + "duro")]))
    caminho = str(tmp_path / "codificacao.epub")
    epub.escrever(livro, caminho)
    with zipfile.ZipFile(caminho) as z:
        for nome in z.namelist():
            if not nome.endswith((".xhtml", ".opf", ".ncx", ".xml", ".css")):
                continue
            dados = z.read(nome)
            assert not dados.startswith(b"\xef\xbb\xbf"), nome                  # sem BOM
            texto = dados.decode("utf-8")                                         # UTF-8 válido
            sem_diagramas = re.sub(r'<div class="diagrama[^"]*".*?</div>', "", texto, flags=re.S)
            assert "Ã" not in sem_diagramas, nome                                  # os glifos da fonte não contam
            if nome.endswith((".xhtml", ".opf", ".ncx", ".xml")):
                assert texto.startswith('<?xml version="1.0" encoding="utf-8"?>'), nome
                nomeadas = set(re.findall(r"&([a-zA-Z][a-zA-Z0-9]*);", texto)) - {"amp", "lt", "gt", "quot", "apos"}
                assert not nomeadas, (nome, nomeadas)
            if nome.endswith(".xhtml") and "cap1" in nome:
                assert "ç ♕ ⩲ — fim&#160;duro" in texto or "ç ♕ ⩲ — fim\xa0duro" in texto
    relido, _r = epub.ler(caminho)
    assert m.texto_de(relido.capitulos[0].blocos[1]) == "ç ♕ ⩲ — fim" + chr(0xA0) + "duro"


# ----------------------------------------------------------------------
# AC-008
# ----------------------------------------------------------------------

def test_ac008_a_ponte(tmp_path):
    doc = documento_sintetico()
    diario = str(tmp_path / "saida.review.jsonl")
    doc.metadata["review_journal_path"] = diario
    livro, _rel = importar_ir.de_documento(doc)

    def bloco(bloco_id):
        return next(b for c in livro.capitulos for b in c.blocos if b.origem is not None
                    and b.origem.bloco_id == bloco_id)

    bloco("block-doc-p0001-b0001").trechos = [m.Trecho(texto="Texto novo.")]
    bloco("block-doc-p0003-b0001").trechos = [m.Trecho(texto="Fim novo.")]
    livro.capitulos[1].blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="Sem origem.")]))
    livro.capitulos[0].blocos.remove(bloco("block-doc-p0002-b0002"))
    from core.editorial_review import ReviewJournal, ReviewSession

    ReviewSession(doc, journal=ReviewJournal(diario)).edit("block-doc-p0001-b0003", "Da fila")
    bloco("block-doc-p0001-b0003").trechos = [m.Trecho(texto="Do editor")]
    ponte = importar_ir.gravar_eventos(livro, doc, diario)
    eventos = ponte.documento.review_events[1:]                                # o primeiro é o da fila
    assert [(e.target_id, e.status, e.reason_codes, e.user, e.before, e.after) for e in eventos] == [
        ("block-doc-p0001-b0001", "reviewed", ("editor",), "editor", "Texto com negrito no meio.", "Texto novo."),
        ("block-doc-p0001-b0003", "reviewed", ("editor",), "editor", "Da fila", "Do editor"),
        ("block-doc-p0002-b0002", "rejected", ("rejected",), "editor", "coisa estranha", "coisa estranha"),
        ("block-doc-p0003-b0001", "reviewed", ("editor",), "editor", "Fim.", "Fim novo."),
    ]
    projetado = ponte.documento
    b1 = next(b for p in projetado.pages for b in p.blocks if b.id == "block-doc-p0001-b0001")
    assert b1.decision.value == "Texto novo." and b1.decision.original_value == "Texto com negrito no meio."
    assert len(open(diario, encoding="utf-8").read().splitlines()) == 5 and ponte.novos


# ----------------------------------------------------------------------
# AC-009
# ----------------------------------------------------------------------

def test_ac009_o_diagrama_nunca_perde_a_posicao(tmp_path):
    livro = editor_livros.livro_completo()
    fens = [b.posicao for c in livro.capitulos for b in c.blocos if isinstance(b, m.Diagrama)]
    assert fens and all(b.lado == "" for c in livro.capitulos for b in c.blocos if isinstance(b, m.Diagrama))
    epub.escrever(livro, str(tmp_path / "d.epub"))
    do_epub, _r = epub.ler(str(tmp_path / "d.epub"))
    assert [b.posicao for c in do_epub.capitulos for b in c.blocos if isinstance(b, m.Diagrama)] == fens
    assert all(b.lado == "" for c in do_epub.capitulos for b in c.blocos if isinstance(b, m.Diagrama))
    for modo in ("fonte", "png"):
        caminho = str(tmp_path / f"d-{modo}.docx")
        docx_io.escrever(livro, caminho, OpcoesDeConversao(modo_de_diagrama=modo))
        relido, _r = docx_io.ler(caminho)
        diagramas = [b for c in relido.capitulos for b in c.blocos if isinstance(b, m.Diagrama)]
        assert [b.posicao for b in diagramas] == fens, modo
        assert all(b.lado == "" for b in diagramas), modo


# ----------------------------------------------------------------------
# AC-010
# ----------------------------------------------------------------------

def test_ac010_o_rascunho_volta_com_o_texto_e_a_imagem_colada():
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), (0, 120, 0)).save(buffer, "PNG")
    png = buffer.getvalue()
    with JanelaComRelogio() as t:
        j = t.j
        texto = j.aba_ativa().widget
        texto.ir_para(texto.ordem[1], 0)
        texto.inserir("rascunho ")
        href = j._colar_imagem(png, alt="colada")
        assert j._tique() is False
        t.relogio.avancar(61)
        assert j._tique() is True
        rascunho = t.epub + ".autosave.json"
        assert os.path.isfile(rascunho)
        pasta, caminho = t.pasta, t.epub
        j.destroy()
    with JanelaComRelogio(abrir=False, pasta=pasta) as t:
        t.caixas.pergunta_resposta = True
        t.j.executar("abrir", caminho)
        assert t.caixas.chamadas[-1][0] == "pergunta" and "rascunho" in t.caixas.chamadas[-1][1]
        livro = t.j.projeto.livro
        assert m.texto_de(livro.capitulos[0].blocos[1]).startswith("rascunho ")
        assert href in livro.recursos and livro.recursos[href].dados == png
        assert any(isinstance(b, m.Figura) and b.recurso == href for b in livro.capitulos[0].blocos)
        assert t.j.projeto.sujo
        t.caixas.pergunta_resposta = False
        t.j.executar("fechar_livro")
        assert not os.path.isfile(rascunho)
    Rascunho.pendentes(caminho)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
