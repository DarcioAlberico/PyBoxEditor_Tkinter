"""
Testes dos itens de menu da ED-12 na janela (SPEC_EDITOR §7.3, §10.3–§10.5, §11.8–§11.9,
AC-ED12-4): cada item da seção ED-12 chama o seu comando; "Exportar…" escreve DOCX, PDF e
PGN pela caixa de conclusão com as oito contagens; "Imprimir…" gera o PDF e o abre;
"Importar ▸ DOCX…" anexa (e "Abrir…" com `.docx` vira o livro); "Formato de página…"
grava o `FormatoDePagina`; "Xadrez → Índice ▸" gera a página; "Exportar PGN do
capítulo…" pelo comando.

Rodar sem pytest:      .venv/Scripts/python.exe tests/test_editor_menus_ed12.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import docx_io, modelo as m
from editor_ambiente import Janela
from ui.editor import menus

ITENS_DA_ED12 = ("importar_docx", "imprimir", "exportar_pgn", "formato_de_pagina")
CONTAGENS = ("Capítulos:", "Blocos:", "Diagramas:", "Figuras:", "Notas:", "Ilhas:", "Tempo:")


def test_ac4_cada_item_da_secao_ed12_chama_o_comando_pelo_menu():
    with Janela() as t:
        j = t.j
        for nome in ITENS_DA_ED12:
            item = menus.item_de(nome)
            assert item is not None and item.fase == "ED-12", nome
            assert nome in j.comandos and j.menus.estado(nome) == "normal", nome
            chamadas = []
            original = j.comandos[nome]
            j.comandos[nome] = lambda *a, n=nome, **k: chamadas.append(n)
            try:
                j.menus.invocar(nome)
            finally:
                j.comandos[nome] = original
            assert chamadas == [nome], nome
        # o submenu Índice é dinâmico, com os três índices
        itens = j.itens_dinamicos["indice"]()
        assert [r for r, _c in itens] == ["Jogadores", "Partidas", "Aberturas"]
        assert "gerar_indice" in j.comandos


def test_ac4_exportar_docx_pdf_e_pgn_pela_caixa_de_conclusao_com_as_contagens(tmp_path):
    with Janela() as t:
        j = t.j
        docx = str(tmp_path / "livro.docx")
        assert j.executar("exportar", "docx", docx) == docx and os.path.isfile(docx)
        conclusao = t.caixas.chamadas[-1]
        assert conclusao[0] == "conclusao" and conclusao[3] == docx
        assert all(any(c in li for li in conclusao[2]) for c in CONTAGENS)
        livro, _rel = docx_io.ler(docx)
        assert any(isinstance(b, m.Diagrama) for c in livro.capitulos for b in c.blocos)
        pdf = str(tmp_path / "livro.pdf")
        assert j.executar("exportar", "pdf", pdf) == pdf and os.path.isfile(pdf)
        conclusao = t.caixas.chamadas[-1]
        assert conclusao[3] == pdf and any(li.startswith("Páginas:") for li in conclusao[2])
        assert all(any(c in li for li in conclusao[2]) for c in CONTAGENS)
        import fitz

        with fitz.open(pdf) as doc:
            assert doc.page_count >= 3 and doc.metadata["title"] == "Livro completo"
        # PGN: o capítulo ativo
        texto = t.texto
        notacao = next(b for b in texto.sincronizar().blocos if isinstance(b, m.Paragrafo) and b.estilo == "notacao")
        texto.ir_para(notacao.id, 0)
        texto.inserir("1.e4 e5 2.Nf3 Nc6 ")
        pgn = str(tmp_path / "cap")
        assert j.executar("exportar", "pgn", pgn) == pgn + ".pgn"
        conteudo = open(pgn + ".pgn", encoding="utf-8").read()
        assert "[Event " in conteudo and "1. e4 e5 2. Nf3 Nc6" in conteudo
        conclusao = t.caixas.chamadas[-1]
        assert conclusao[3] == pgn + ".pgn" and any(li.startswith("Partidas: ") for li in conclusao[2])
        assert j.executar("exportar_pgn", str(tmp_path / "direto.pgn")) == str(tmp_path / "direto.pgn")
        # a caixa de formato lista DOCX, PDF e PGN sem "chega na"
        rotulos = [rotulo + (f"  (chega na {fase})" if fase not in ("ED-02", "ED-10", "ED-12") else "")
                   for _f, rotulo, fase, _e, _t in __import__("ui.editor.conversoes", fromlist=["FORMATOS"]).FORMATOS]
        assert not any("chega na" in r for r in rotulos)


def test_imprimir_gera_o_pdf_e_abre_no_sistema(tmp_path):
    with Janela() as t:
        j = t.j
        abertos = []
        j.conversoes.abrir_no_sistema = abertos.append
        caminho = str(tmp_path / "imprimir.pdf")
        assert j.executar("imprimir", caminho) == caminho and os.path.isfile(caminho) and abertos == [caminho]
        assert "PDF gerado" in j.campos["aviso"].cget("text")
        gerado = j.executar("imprimir")
        assert gerado.endswith(".pdf") and os.path.isfile(gerado) and abertos[-1] == gerado


def test_importar_docx_anexa_e_abrir_docx_vira_o_livro(tmp_path):
    with Janela() as t:
        j = t.j
        docx = str(tmp_path / "fonte.docx")
        j.executar("exportar", "docx", docx)
        antes = len(j.projeto.livro.capitulos)
        anexados = j.executar("importar_docx", docx)
        assert anexados and len(j.projeto.livro.capitulos) == antes + len(anexados) and j.projeto.sujo
        t.caixas.pergunta_resposta = False
        projeto = j.executar("abrir", docx)
        assert projeto is j.projeto and projeto.caminho is None and projeto.livro.capitulos


def test_formato_de_pagina_grava_no_livro_e_valida(tmp_path):
    with Janela() as t:
        j = t.j
        valores = {"largura_mm": "148", "altura_mm": "210", "superior": "18", "externa": "15", "inferior": "18",
                   "interna": "22", "espelhadas": "não", "cabecalho_par": "nenhum", "cabecalho_impar": "capitulo",
                   "numerar_paginas": "sim", "hifenizar": "sim"}
        novo = j.executar("formato_de_pagina", valores)
        pagina = j.projeto.livro.pagina
        assert pagina is novo and pagina.largura_mm == 148 and pagina.margens_mm == (18, 15, 18, 22)
        assert not pagina.espelhadas and pagina.cabecalho_par == "" and pagina.cabecalho_impar == "capitulo"
        assert pagina.numerar_paginas and pagina.hifenizar and j.projeto.sujo
        # pela caixa de formulário
        t.caixas.formulario_resposta = {**valores, "largura_mm": "120", "espelhadas": "sim"}
        assert j.executar("formato_de_pagina").largura_mm == 120 and j.projeto.livro.pagina.espelhadas
        t.caixas.formulario_resposta = None
        assert j.executar("formato_de_pagina") is None
        j.executar("formato_de_pagina", {**valores, "largura_mm": "abc"})
        assert "medida inválida" in t.caixas.entradas()[-1]
        j.executar("formato_de_pagina", {**valores, "externa": "80", "interna": "80"})
        assert "não deixam lugar" in t.caixas.entradas()[-1]
        # o formato vai ao PDF e volta do EPUB
        pdf = str(tmp_path / "f.pdf")
        j.executar("exportar", "pdf", pdf)
        import fitz

        with fitz.open(pdf) as doc:
            assert abs(doc[0].rect.width - 120 * 72 / 25.4) < 0.5
        destino = str(tmp_path / "f.epub")
        j.executar("salvar_como", destino)
        from core.editor import epub

        relido, _r = epub.ler(destino)
        assert relido.pagina.largura_mm == 120 and relido.pagina.hifenizar


def test_gerar_indice_pela_janela_abre_a_pagina_e_recarrega_as_abas(tmp_path):
    with Janela() as t:
        j = t.j
        texto = t.texto
        h2 = next(b for b in texto.sincronizar().blocos if isinstance(b, m.Titulo) and b.nivel == 2)
        texto.ir_para(h2.id, 0)
        texto.inserir("Kasparov – Karpov: ")
        texto.selecionar(0, len("Kasparov"), h2.id)
        texto.aplicar(papel="jogador", chave="Kasparov, Garry")
        n = len(j.projeto.livro.capitulos)
        arquivo = j.executar("gerar_indice", "jogadores")
        assert arquivo == "indice-jogadores.xhtml" and len(j.projeto.livro.capitulos) == n + 1
        assert j.aba_ativa().arquivo == arquivo
        blocos = t.texto.sincronizar().blocos
        assert m.texto_de(blocos[0]) == "Índice de jogadores" and any("Kasparov, Garry" in m.texto_de(b) for b in blocos)
        assert "Índice de jogadores: " in j.campos["aviso"].cget("text")
        assert j.executar("gerar_indice", "jogadores") == arquivo and len(j.projeto.livro.capitulos) == n + 1
        assert j.executar("gerar_indice", "partidas") == "indice-partidas.xhtml"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
