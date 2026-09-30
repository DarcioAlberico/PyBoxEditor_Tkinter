"""
Testes da ED-18: `core/editor/original.py` (a caixa em pontos, a origem na linha do código,
o bloco no ponto da página, a navegação pelas suspeitas, a troca dos blocos de uma página
relida) e, na janela, o painel "Original" (`F9`) que segue o cursor nos dois modos e leva ao
bloco pelo clique, o `F4`, e "Reler a página do PDF…" com um leitor de mentira.

Rodar sem pytest:      python tests/test_editor_original.py
"""

import os
import sys
import textwrap
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import importar_ir, modelo
from core.editor import original as co
from test_editor_importar_ir import documento_sintetico


def _livro():
    livro, _ = importar_ir.de_documento(documento_sintetico(), dividir="pagina")
    return livro


def _bloco(livro, texto):
    return next(b for c in livro.capitulos for b in c.blocos if hasattr(b, "trechos") and texto in modelo.texto_de(b))


# ----------------------------------------------------------------------
# O núcleo
# ----------------------------------------------------------------------

def test_caixa_da_leitura_em_pontos():
    assert co.caixa_em_pontos((0, 100, 800, 140), 300) == pytest.approx((0, 24, 192, 33.6))
    assert co.caixa_em_pontos((72, 72, 144, 144), 72) == (72, 72, 144, 144)
    assert co.caixa_em_pontos((300, 0, 600, 300), 0) == pytest.approx((72, 0, 144, 72))     # sem dpi: 300


def test_origem_na_linha_do_codigo():
    texto = ('<body>\n<p data-origem-pagina="doc-p0002" data-origem-bloco="b1" data-origem-caixa="1,2,3,4">a</p>\n'
             '<p>sem origem</p>\n<p data-origem-bloco="b2" data-origem-pagina="doc-p0003">b</p>\n</body>')
    assert co.origem_na_linha(texto, 1) is None
    origem = co.origem_na_linha(texto, 3)                 # a linha sem origem fica com a de cima
    assert origem.bloco_id == "b1" and origem.pagina == 1 and origem.caixa == (1, 2, 3, 4)
    assert co.origem_na_linha(texto, 4).bloco_id == "b2" and co.origem_na_linha(texto, 99).pagina == 2


def test_bloco_no_ponto_da_pagina():
    livro = _livro()
    achado = co.bloco_no_ponto(livro, 0, 100, 30)          # dentro de (0, 24, 192, 33.6)
    assert achado is not None and modelo.texto_de(achado[1]) == "Texto com negrito no meio."
    assert co.bloco_no_ponto(livro, 0, 100, 200) is None
    diagrama = co.bloco_no_ponto(livro, 0, 5, 5)           # o diagrama (2,4..8,2 pt) é menor que o parágrafo
    assert diagrama is not None and isinstance(diagrama[1], modelo.Diagrama)


def test_vizinha_suspeita_da_a_volta():
    livro = _livro()
    lista = co.suspeitos(livro)
    assert len(lista) == 2 and all(a == "Text/cap-0002.xhtml" for a, _ in lista)
    assert co.vizinha_suspeita(livro, "Text/cap-0001.xhtml", None, 1) == lista[0]
    assert co.vizinha_suspeita(livro, lista[0][0], lista[0][1], 1) == lista[1]
    assert co.vizinha_suspeita(livro, lista[1][0], lista[1][1], 1) == lista[0]          # volta ao começo
    assert co.vizinha_suspeita(livro, lista[0][0], lista[0][1], -1) == lista[1]
    assert co.vizinha_suspeita(livro, "Text/cap-0003.xhtml", None, -1) == lista[1]


def test_trocar_pagina_poe_os_relidos_no_lugar_e_deixa_o_resto():
    livro = _livro()
    cap = livro.capitulos[0]
    meu = modelo.Paragrafo(trechos=[modelo.Trecho(texto="escrito à mão")])
    cap.blocos.insert(3, meu)
    novos = [modelo.MarcaDePagina(pagina=1),
             modelo.Paragrafo(trechos=[modelo.Trecho(texto="relido")],
                              origem=modelo.Origem(page_id="doc-p0001", bloco_id="n1", pagina=0))]
    troca = co.trocar_pagina(livro, 0, novos)
    assert troca.saidos == 4 and troca.entrados == 1 and troca.capitulos == ["Text/cap-0001.xhtml"]
    tipos = [type(b).__name__ for b in cap.blocos]
    assert tipos == ["MarcaDePagina", "Paragrafo", "Paragrafo"]
    assert [modelo.texto_de(b) for b in cap.blocos[1:]] == ["relido", "escrito à mão"]
    # a página sem blocos com origem recebe os relidos depois da marca dela
    livro.capitulos[2].blocos = [b for b in livro.capitulos[2].blocos if isinstance(b, modelo.MarcaDePagina)]
    troca = co.trocar_pagina(livro, 2, [modelo.Paragrafo(trechos=[modelo.Trecho(texto="novo")])])
    assert troca.entrados == 1 and modelo.texto_de(livro.capitulos[2].blocos[1]) == "novo"
    with pytest.raises(ValueError):
        co.trocar_pagina(livro, 40, [modelo.Paragrafo(trechos=[modelo.Trecho(texto="x")])])


# ----------------------------------------------------------------------
# Na janela
# ----------------------------------------------------------------------

def _pdf(caminho, paginas=3):
    import fitz

    doc = fitz.open()
    for n in range(1, paginas + 1):
        pagina = doc.new_page(width=300, height=420)
        pagina.insert_text((20, 40), f"Página {n}", fontsize=12)
    doc.save(str(caminho))
    doc.close()
    return str(caminho)


class _Livro:
    """A `Janela` com o documento sintético aberto como livro, e um PDF de três páginas atrás dele."""

    def __init__(self, tmp_path):
        self.tmp_path = tmp_path

    def __enter__(self):
        from editor_ambiente import Janela

        self.contexto = Janela(abrir=False)
        t = self.contexto.__enter__()
        self.t = t
        documento = documento_sintetico("sint")
        json_ = self.tmp_path / "sint.json"
        documento.save_json(json_)
        t.j.conversoes.abrir_documento_editorial(documento, str(json_), "pagina")
        t.j.projeto.livro.origem.pdf = _pdf(self.tmp_path / "sint.pdf")
        t.j._gravar_preferencia("previa_ms", 0)
        t.j.abrir_capitulo("Text/cap-0001.xhtml")
        return t

    def __exit__(self, *a):
        self.contexto.__exit__(*a)


def _cursor_no_paragrafo(t):
    bloco = t.bloco(lambda b: hasattr(b, "trechos") and modelo.texto_de(b) == "Texto com negrito no meio.")
    t.texto.ir_para(bloco.id, 2)
    t.j.original.seguir(t.j.aba_ativa())
    return bloco


def test_f9_mostra_a_pagina_e_a_caixa_e_segue_o_cursor_nos_dois_modos(tmp_path):
    with _Livro(tmp_path) as t:
        j = t.j
        assert j.menus.estado("painel_original") == "normal"
        painel = j.executar("painel_original")
        aba = j.aba_ativa()
        assert painel is aba.dados["original"] and len(aba.dados["divisao"].panes()) == 2
        _cursor_no_paragrafo(t)
        assert painel.pagina == 0 and painel.caixa == (0, 100, 800, 140)
        assert painel.canvas.find_withtag("pagina") and painel.canvas.find_withtag("caixa")
        # um bloco sem origem: a mensagem, sem página
        titulo = t.bloco(lambda b: isinstance(b, modelo.Titulo))
        titulo.origem = None
        t.texto.ir_para(titulo.id, 0)
        j.original.seguir(aba)
        assert painel.pagina is None and painel.canvas.find_withtag("aviso")
        # no código, pela tag da linha; e o painel atravessa a troca de modo
        j.executar("alternar_modo")
        painel = aba.dados.get("original")
        assert painel is not None and aba.modo == "codigo"
        editor = aba.widget
        linha = int(editor.texto.search("Texto com", "1.0").split(".")[0])
        editor.ir_para(linha)
        j.original.seguir(aba)
        assert painel.pagina == 0 and painel.caixa == (0, 100, 800, 140)
        # prévia e original juntos: três painéis na divisória
        j.executar("previa")
        assert len(aba.dados["divisao"].panes()) == 3
        assert str(aba.dados["divisao"].panes()[1]) == str(aba.dados["previa"])      # a prévia antes do original
        j.executar("painel_original")
        assert "original" not in aba.dados and len(aba.dados["divisao"].panes()) == 2
        j.executar("previa")
        assert "divisao" not in aba.dados and editor.winfo_manager() == "pack"


def test_o_clique_na_pagina_leva_ao_bloco(tmp_path):
    with _Livro(tmp_path) as t:
        j = t.j
        painel = j.executar("painel_original")
        _cursor_no_paragrafo(t)
        painel._clicou = None
        # o ponto (5 pt, 5 pt) é o diagrama
        j.original._clicou(j.aba_ativa(), 0, 5, 5)
        assert isinstance(next(b for b in t.texto.sincronizar().blocos if b.id == t.texto.bloco_atual()),
                          modelo.Diagrama)
        j.original._clicou(j.aba_ativa(), 0, 250, 400)
        assert "Nenhum bloco" in j.campos["aviso"].cget("text")


def test_f4_anda_pelas_suspeitas_e_mostra_o_motivo(tmp_path):
    with _Livro(tmp_path) as t:
        j = t.j
        j.executar("painel_original")
        primeiro = j.executar("proxima_suspeita")
        assert primeiro[0] == "Text/cap-0002.xhtml" and j.aba_ativa().arquivo == "Text/cap-0002.xhtml"
        assert t.texto.bloco_atual() == primeiro[1] and "Suspeita 1 de 2" in j.campos["aviso"].cget("text")
        segundo = j.executar("proxima_suspeita")
        assert segundo != primeiro and "Suspeita 2 de 2" in j.campos["aviso"].cget("text")
        assert j.executar("suspeita_anterior") == primeiro
        painel = j.aba_ativa().dados.get("original")
        assert painel is not None and painel.pagina == 1 and painel.rodape.cget("text").startswith("Suspeito:")


def test_sem_pdf_o_painel_explica(tmp_path):
    with _Livro(tmp_path) as t:
        t.j.projeto.livro.origem.pdf = ""
        t.j.projeto.documento_editorial.metadata.pop("source_path", None)
        t.j.executar("painel_original")
        assert any("não veio de um PDF" in m for m in t.caixas.entradas())
        t.j.projeto.livro.origem.pdf = str(tmp_path / "sumiu.pdf")
        t.j.executar("painel_original")
        assert any("não está mais lá" in m for m in t.caixas.entradas())


def test_reler_a_pagina_troca_os_blocos(tmp_path, monkeypatch):
    from core.editor import abrir_pdf as ap
    from core.editorial_model import EditorialDocument

    # a "releitura": o mesmo documento, com o parágrafo da página 1 corrigido
    relido = documento_sintetico("sint")
    for pagina in relido.pages:
        for bloco in pagina.blocks:
            if getattr(bloco, "text", None) and "negrito" in (bloco.text or ""):
                pass
    json_relido = tmp_path / "relido.json"
    relido.save_json(json_relido)
    texto = json_relido.read_text(encoding="utf-8").replace("Texto com negrito no meio.", "Texto relido pelo OCR.")
    json_relido.write_text(texto, encoding="utf-8")
    EditorialDocument.load_json(json_relido)
    script = tmp_path / "leitor.py"
    script.write_text(textwrap.dedent(f"""
        import json, shutil, sys
        saida = sys.argv[sys.argv.index("-o") + 1]
        assert sys.argv[sys.argv.index("--paginas") + 1] == "1", sys.argv
        shutil.copy({str(json_relido)!r}, saida)
        print(json.dumps({{"evento": "fim", "arquivo": saida, "paginas": 1, "avisos": []}}), flush=True)
    """), encoding="utf-8")
    monkeypatch.setattr(ap, "SCRIPT", str(script))
    with _Livro(tmp_path) as t:
        j = t.j
        j.leitura_de_pdf.mostrar_progresso = False
        resultados = []
        j.leitura_de_pdf.ao_terminar = resultados.append
        _cursor_no_paragrafo(t)
        j.original.reler(camada="nunca")
        fim = time.time() + 20
        while not resultados and time.time() < fim:
            j.update()
            time.sleep(0.03)
        troca = resultados[0]
        assert troca is not None and troca.capitulos == ["Text/cap-0001.xhtml"]
        textos = [modelo.texto_de(b) for b in j.projeto.livro.capitulos[0].blocos if hasattr(b, "trechos")]
        assert "Texto relido pelo OCR." in textos and "Texto com negrito no meio." not in textos
        assert "Texto relido pelo OCR." in [modelo.texto_de(b) for b in t.texto.sincronizar().blocos
                                             if hasattr(b, "trechos")]
        # os outros capítulos não mudaram
        assert "Suspeito por motor." in [modelo.texto_de(b) for b in j.projeto.livro.capitulos[1].blocos
                                         if hasattr(b, "trechos")]
        assert any(c[0] == "pergunta" and "página 1" in c[1] for c in t.caixas.chamadas)


def test_reler_sem_origem_recusa(tmp_path):
    with _Livro(tmp_path) as t:
        titulo = t.bloco(lambda b: isinstance(b, modelo.Titulo))
        titulo.origem = None
        t.texto.ir_para(titulo.id, 0)
        t.j.executar("reler_do_pdf")
        assert any("não veio do PDF" in m for m in t.caixas.entradas())


def test_menus_e_atalhos():
    from ui.editor import atalhos, menus

    comandos = {i.comando for i in menus.EXIBIR} | {i.comando for i in menus.FERRAMENTAS}
    assert {"painel_original", "proxima_suspeita", "suspeita_anterior", "reler_do_pdf"} <= comandos
    teclas = {a.atalho: a.comando for a in atalhos.TABELA}
    assert teclas["F9"] == "painel_original" and teclas["F4"] == "proxima_suspeita"
    assert teclas["Shift+F4"] == "suspeita_anterior"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
