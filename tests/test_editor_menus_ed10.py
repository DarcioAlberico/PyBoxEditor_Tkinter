"""
Testes dos itens de menu da ED-10 na janela (SPEC_EDITOR §7.3 "Importar ▸", "Exportar…",
§9.5): cada item da seção ED-10 chama o seu comando (espião + `invoke`) e "Importar ▸
EPUB para dentro do livro…" anexa renomeando colisões (AC-ED10-5); "Exportar…" escreve
HTML único, HTML em pasta e TXT pela caixa de conclusão (DOCX, PDF e PGN são da ED-12);
"Importar ▸ HTML/TXT" anexa ao livro aberto, e sem livro aberto vira o livro (como
"Abrir…" com um `.html`/`.txt`); "Dividir em capítulos por título…", "Dividir nos
marcadores" e "Juntar em capítulos por título…" pelo comando, com as abas e o sumário
refeitos.

Rodar sem pytest:      python tests/test_editor_menus_ed10.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import epub, livro_ops, modelo as m
from editor_ambiente import Janela
from ui.editor import menus

ITENS_DA_ED10 = ("importar_html", "importar_txt", "importar_epub", "exportar", "juntar_por_titulo",
                 "dividir_por_titulo", "dividir_nos_marcadores")


def test_ac5_cada_item_da_secao_ed10_chama_o_comando_pelo_menu():
    with Janela() as t:
        j = t.j
        for nome in ITENS_DA_ED10:
            item = menus.item_de(nome)
            assert item is not None and item.fase in ("ED-02", "ED-10"), nome
            assert nome in j.comandos and j.menus.estado(nome) == "normal", nome
            chamadas = []
            original = j.comandos[nome]
            j.comandos[nome] = lambda *a, n=nome, **k: chamadas.append(n)
            try:
                j.menus.invocar(nome)
            finally:
                j.comandos[nome] = original
            assert chamadas == [nome], nome
        # o submenu Importar mora em Arquivo e a caixa Exportar lista os formatos com a fase
        arquivo = [i for r, i in menus.MENUS if r == "Arquivo"][0]
        importar = next(i for i in arquivo if i.rotulo == "Importar")
        assert [f.comando for f in importar.filhos][:3] == ["importar_html", "importar_txt", "importar_epub"]
        t.caixas.escolha_resposta = None
        assert j.executar("exportar") is None


def test_ac5_importar_epub_anexa_renomeando_colisoes_e_reescrevendo_os_links(tmp_path):
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        antes = [c.arquivo for c in livro.capitulos]
        outro = editor_livros.livro_completo()          # os mesmos nomes: cap1.xhtml, cap2.xhtml, Images/foto.png
        caminho = str(tmp_path / "outro.epub")
        epub.escrever(outro, caminho)
        anexados = j.executar("importar_epub", caminho)
        assert len(anexados) == 2 and all(a not in antes for a in anexados)
        assert [c.arquivo for c in livro.capitulos] == antes + anexados
        novo1, novo2 = anexados
        assert novo1 != "cap1.xhtml" and novo2 != "cap2.xhtml"
        links = [t_.link for t_ in m.trechos_do_capitulo(livro.capitulo(novo1)) if t_.link]
        assert f"{novo2}#alvo" in links and "cap2.xhtml#alvo" not in links       # reescrito para o anexado
        assert "Images/foto.png" in livro.recursos                                   # igual byte a byte: compartilhado
        assert j.projeto.sujo and j.navegador.exists(novo1) and j.aba_ativa().arquivo == novo1
        assert any(e.destino.startswith(novo1) for e in livro.sumario)
        # um arquivo que não existe é erro de entrada; uma extensão desconhecida também
        j.executar("importar_epub", str(tmp_path / "nada.epub"))
        assert "não existe" in t.caixas.entradas()[-1]
        with open(str(tmp_path / "x.zzz"), "w") as f:
            f.write("x")
        j.executar("importar_html", str(tmp_path / "x.zzz"))
        assert "não sei importar" in t.caixas.entradas()[-1]


def test_exportar_html_unico_pasta_e_txt_pela_caixa_de_conclusao(tmp_path):
    with Janela() as t:
        j = t.j
        unico = str(tmp_path / "livro.html")
        assert j.executar("exportar", "html", unico) == unico and os.path.isfile(unico)
        conclusao = t.caixas.chamadas[-1]
        assert conclusao[0] == "conclusao" and conclusao[3] == unico
        assert any("Capítulos: 2" in li for li in conclusao[2]) and any("Fontes embutidas" in li for li in conclusao[2])
        texto = open(unico, encoding="utf-8").read()
        assert '<section role="doc-chapter" id="cap1.xhtml">' in texto and "data:image/png;base64," in texto
        pasta = str(tmp_path / "pasta")
        indice = j.executar("exportar", "html-pasta", pasta)
        assert indice == os.path.join(pasta, "index.html") and os.path.isfile(os.path.join(pasta, "cap1.html"))
        assert t.caixas.chamadas[-1][3] == indice
        txt = str(tmp_path / "livro")                                   # sem extensão: ganha a do formato
        assert j.executar("exportar", "txt", txt) == txt + ".txt"
        assert f"[Diagrama 1: {editor_livros.FEN}]" in open(txt + ".txt", encoding="utf-8").read()
        assert not j.projeto.sujo                                       # nada mudou no livro
        # as fontes que a exportação embute ficam no livro (ele ganhou recursos: sujo, navegador refeito)
        livro = j.projeto.livro
        for href in [h for h in livro.recursos if h.startswith("Fonts/")]:
            del livro.recursos[href]
        j.atualizar_navegador()
        assert not j.navegador.exists("Fonts/SkakNew-Diagram.otf")
        assert j.executar("exportar", "html", str(tmp_path / "de-novo.html"))
        assert "Fonts/SkakNew-Diagram.otf" in livro.recursos and j.projeto.sujo
        assert j.navegador.exists("Fonts/SkakNew-Diagram.otf")
        assert livro.zip_de_origem == t.epub                            # o projeto continua no seu arquivo
        j.executar("exportar", "zzz", str(tmp_path / "x"))
        assert "formato desconhecido" in t.caixas.entradas()[-1]
        # a caixa de formato: o índice escolhido é o formato; cancelar não faz nada
        t.caixas.escolha_resposta = 1
        j.caixas.salvar_como = lambda *a, **k: str(tmp_path / "pela-caixa.html")
        assert j.executar("exportar") == str(tmp_path / "pela-caixa.html")


def _html_solto(pasta):
    caminho = os.path.join(pasta, "solto.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("<html lang=\"pt\"><head><title>Solto</title></head><body><h1>Um</h1><p>Texto <b>forte</b>.</p>"
                "<h1>Dois</h1><p>Mais.</p></body></html>")
    return caminho


def test_importar_html_e_txt_anexam_ao_livro_aberto_e_sem_livro_viram_o_livro(tmp_path):
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        caminho = _html_solto(str(tmp_path))
        anexados = j.executar("importar_html", caminho)
        assert len(anexados) == 2 and all(livro.capitulo(a) is not None for a in anexados)
        assert m.texto_de(livro.capitulo(anexados[0]).blocos[0]) == "Um"
        assert any(t_.negrito for t_ in m.trechos_do_capitulo(livro.capitulo(anexados[0])))
        with open(str(tmp_path / "solto.txt"), "w", encoding="utf-8") as f:
            f.write(f"# Três\n\nParágrafo.\n\n[Diagrama 1: {editor_livros.FEN}]\n")
        anexados_txt = j.executar("importar_txt", str(tmp_path / "solto.txt"))
        assert len(anexados_txt) == 1
        cap = livro.capitulo(anexados_txt[0])
        assert isinstance(cap.blocos[2], m.Diagrama) and cap.blocos[2].fen == editor_livros.FEN
        assert j.aba_ativa().arquivo == anexados_txt[0]
    with Janela(abrir=False) as t:
        j = t.j
        assert j.projeto is None
        projeto = j.executar("importar_html", _html_solto(str(tmp_path)))
        assert projeto is j.projeto and projeto.caminho is None and projeto.sujo
        assert [c.arquivo for c in projeto.livro.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml"]
        assert projeto.livro.metadados.titulo == "Solto" and j.aba_ativa().arquivo == "Text/cap-0001.xhtml"
        assert "Solto" in j.title()
        # "Abrir…" com um .txt: vira livro também
        with open(str(tmp_path / "outro.txt"), "w", encoding="utf-8") as f:
            f.write("# Outro\n\nTexto.\n")
        t.caixas.pergunta_resposta = False                 # descarta o sujo
        projeto2 = j.executar("abrir", str(tmp_path / "outro.txt"))
        assert projeto2 is j.projeto and projeto2.livro.metadados.titulo == "Outro"
        # salvar pede o caminho (o projeto não tem um): com a caixa cancelada, nada acontece
        assert j.executar("salvar") is None and projeto2.caminho is None
        destino = str(tmp_path / "outro.epub")
        assert j.executar("salvar_como", destino) is not None and projeto2.caminho == destino
        assert epub.validar_estrutura(destino) == []


def test_dividir_por_titulo_nos_marcadores_e_juntar_por_titulo_pelo_comando():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        j.painel_navegador.selecionar("cap2.xhtml")           # tem h1 + h2 + h3 + h4
        t.caixas.inteiro_resposta = 2
        partes = j.executar("dividir_por_titulo")
        assert partes[0] == "cap2.xhtml" and len(partes) == 2 and livro.capitulo(partes[1]) is not None
        assert isinstance(livro.capitulo(partes[1]).blocos[0], m.Titulo)
        assert m.texto_de(livro.capitulo(partes[1]).blocos[0]) == "Seção" and j.navegador.exists(partes[1])
        from core.editor import sumario as sumario_mod
        assert any(e.destino.startswith(partes[1]) for e in sumario_mod._todos(livro.sumario))
        # nada a dividir no nível 1 nesta parte: fica como está, sem erro
        j.painel_navegador.selecionar(partes[1])
        assert j.executar("dividir_por_titulo", 1) == [partes[1]]
        # marcadores: um <hr class="divisao"/> no capítulo ativo
        j.painel_navegador.selecionar("cap1.xhtml")
        cap1 = livro.capitulo("cap1.xhtml")
        cap1.blocos.insert(3, m.Separador(classe="divisao"))
        j._recarregar_aba(j.abas.por_arquivo("cap1.xhtml")) if j.abas.por_arquivo("cap1.xhtml") else None
        partes = j.executar("dividir_nos_marcadores")
        assert len(partes) == 2 and not any(isinstance(b, m.Separador) and "divisao" in b.classe.split()
                                            for b in livro.capitulo(partes[1]).blocos)
        assert j.projeto.sujo
        # juntar por título (nível 1) refaz o livro: as partes de cap1 e cap2 voltam a dois capítulos
        t.caixas.pergunta_resposta = True
        cabecas = j.executar("juntar_por_titulo", 1)
        assert len(cabecas) == 2 and [c.arquivo for c in livro.capitulos] == cabecas
        assert j.aba_ativa() is not None and j.aba_ativa().arquivo == cabecas[0]
        t.caixas.pergunta_resposta = False
        assert j.executar("juntar_por_titulo", 1) == []


def test_o_livro_de_paginas_do_impresso_junta_se_por_titulo_pela_janela(tmp_path):
    with Janela(abrir=False) as t:
        j = t.j
        caminho = editor_livros.epub_de_hoje(str(tmp_path), "png")
        j.executar("abrir", caminho)
        livro = j.projeto.livro
        assert len(livro.capitulos) == 2 and livro_ops.pagina_do_arquivo(livro.capitulos[1]) == 2
        t.caixas.pergunta_resposta = True
        cabecas = j.executar("juntar_por_titulo", 1)
        assert cabecas == [livro.capitulos[0].arquivo] and len(livro.capitulos) == 1
        marcas = [b.pagina for b in livro.capitulos[0].blocos if isinstance(b, m.MarcaDePagina)]
        assert marcas == [1, 2]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
