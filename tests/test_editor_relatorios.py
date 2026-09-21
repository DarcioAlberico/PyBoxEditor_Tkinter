"""
Testes de `core/editor/relatorios.py` e dos comandos de relatório na janela (ED-08;
SPEC_EDITOR §9 "Reports", §9.8): imagem não usada, classe usada e não definida, link e
`ref` quebrados, `♕` sem fonte, caracteres com `Ã`, diagrama `revisar` (AC-ED08-5);
"Apagar classes não usadas" preserva o resto byte a byte e "Apagar recursos não usados"
remove só o não referenciado (AC-ED08-6).

Rodar sem pytest:      python tests/test_editor_relatorios.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import modelo as m, relatorios
from core.editor.modelo import Capitulo, Livro, Metadados, Paragrafo, Recurso, Trecho
from editor_ambiente import Janela

FEN = "8/8/8/8/8/8/8/K6k w - - 0 1"
CSS = ("p.legenda { x: 1 }\n/* comentário que fica */\n.nunca, .jamais { y: 2 }\n"
       "@media print { .impresso { z: 3 } p { w: 4 } }\np { a: b }\n.lance { c: d }\n@import url(x.css);\n"
       "h1.titulo-nunca { e: f }\n")


def _p(*trechos, **kw):
    return Paragrafo(trechos=[t if isinstance(t, Trecho) else Trecho(texto=t) for t in trechos], **kw)


def _livro():
    livro = editor_livros.livro_completo()
    livro.recursos["Images/sobra.png"] = Recurso(caminho="Images/sobra.png", tipo_mime="image/png", dados=b"x")
    livro.recursos["Styles/estilo.css"] = Recurso(caminho="Styles/estilo.css", tipo_mime="text/css",
                                                  dados=CSS.encode("utf-8"))
    livro.folhas = ["Styles/estilo.css"]
    livro.capitulos[0].folhas = ["Styles/estilo.css"]
    cap2 = livro.capitulos[1]
    cap2.blocos.append(_p("Ver ", Trecho(texto="Figura 9", ref="figura", link="cap1.xhtml#fig-nada"),
                          " e ", Trecho(texto="fora", link="lua.xhtml#x"), " e a rainha ♕ e pÃ¡gina."))
    cap2.blocos.append(m.Diagrama(fen=FEN, estado="revisar", aviso="OCR duvidoso", lado="w",
                                  legenda=[Trecho(texto="Posição")]))
    cap2.notas.append(m.Nota(id="orfa", blocos=[_p("nota sem referência")]))
    return livro


# ----------------------------------------------------------------------
# AC-ED08-5
# ----------------------------------------------------------------------

def test_ac5_os_relatorios_acham_o_que_a_spec_lista():
    livro = _livro()
    imagens = relatorios.imagens(livro)
    assert [li.arquivo for li in imagens if li.gravidade == "aviso" and "não usada" in li.mensagem] == [
        "Images/sobra.png"]
    classes = relatorios.classes(livro)
    usadas_sem_def = {li.dados["classe"] for li in classes if "não definida" in li.mensagem}
    assert "notacao" in usadas_sem_def and "lance" not in usadas_sem_def
    definidas_sem_uso = {li.dados["classe"] for li in classes if "não usada" in li.mensagem}
    assert {"nunca", "jamais", "impresso", "titulo-nunca"} <= definidas_sem_uso and "legenda" not in definidas_sem_uso
    links = relatorios.links(livro)
    mensagens = [li.mensagem for li in links]
    assert any(li.startswith("ref sem alvo: cap1.xhtml#fig-nada") for li in mensagens)
    assert any(li.startswith("link quebrado: lua.xhtml#x") for li in mensagens)
    assert any("nota sem referência" in li for li in mensagens)
    assert all(li.dados.get("bloco") for li in links if li.gravidade == "erro")
    caracteres = relatorios.caracteres(livro, cobre=lambda c: c != "♕")
    mojibake = [li for li in caracteres if li.gravidade == "erro"]
    assert mojibake and "Ã" in mojibake[0].mensagem and mojibake[0].arquivo == "cap2.xhtml"
    rainha = next(li for li in caracteres if li.dados.get("caractere") == "♕")
    assert rainha.gravidade == "aviso" and "nenhuma fonte embutida desenha" in rainha.mensagem
    assert next(li for li in caracteres if li.dados.get("caractere") == "á").gravidade == "info"
    diagramas = relatorios.diagramas(livro)
    revisar = [li for li in diagramas if "revisar" in li.mensagem]
    assert len(revisar) == 1 and revisar[0].arquivo == "cap2.xhtml" and "OCR duvidoso" in revisar[0].mensagem
    assert all(li.dados["bloco"] for li in diagramas)
    arquivos = relatorios.arquivos(livro)
    assert any(li.arquivo == "Images/sobra.png" and "ninguém" in li.mensagem for li in arquivos)
    assert relatorios.relatorio("diagramas", livro) == diagramas
    with pytest.raises(ValueError):
        relatorios.relatorio("lua", livro)


def test_fontes_e_glifos_com_uma_fonte_embutida_de_verdade(tmp_path):
    pytest.importorskip("fitz")
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts",
                           "SimbolosDeXadrez.ttf")
    if not os.path.exists(caminho):
        pytest.skip("fonte empacotada ausente")
    with open(caminho, "rb") as f:
        dados = f.read()
    livro = Livro(metadados=Metadados(titulo="T"), capitulos=[Capitulo(arquivo="c.xhtml", blocos=[_p("♕ e ⩲ e 漢")])],
                  recursos={"Fonts/x.ttf": Recurso(caminho="Fonts/x.ttf", tipo_mime="font/ttf", dados=dados),
                            "s.css": Recurso(caminho="s.css", tipo_mime="text/css",
                                             dados=b"@font-face { font-family: 'X'; src: url(Fonts/x.ttf); }")})
    linhas = relatorios.fontes(livro, None, str(tmp_path))
    assert any(li.arquivo == "Fonts/x.ttf" and "X" in li.mensagem for li in linhas)
    sem = {li.dados["caractere"] for li in linhas if "nenhuma fonte embutida desenha" in li.mensagem}
    assert "漢" in sem and "♕" not in sem
    cobre = relatorios.cobertura_das_fontes(livro, None, str(tmp_path))
    assert cobre("♕") and not cobre("漢")


# ----------------------------------------------------------------------
# AC-ED08-6
# ----------------------------------------------------------------------

def test_ac6_apagar_classes_nao_usadas_preserva_o_resto_byte_a_byte():
    livro = _livro()
    usadas = relatorios.classes_usadas(livro)
    novo, apagadas = relatorios.apagar_classes_nao_usadas(CSS, usadas)
    assert set(apagadas) == {"nunca", "jamais", "impresso", "titulo-nunca"}
    assert novo == ("p.legenda { x: 1 }\n/* comentário que fica */\n@media print { p { w: 4 } }\np { a: b }\n"
                    ".lance { c: d }\n@import url(x.css);\n")
    # idempotente, e uma folha sem classe sem uso volta igual
    assert relatorios.apagar_classes_nao_usadas(novo, usadas) == (novo, [])
    regras = relatorios.regras_da_folha(CSS)
    assert [(r.seletores, r.aninhada) for r in regras] == [
        (["p.legenda"], False), ([".nunca", ".jamais"], False), ([".impresso"], True), (["p"], True), (["p"], False),
        ([".lance"], False), (["h1.titulo-nunca"], False)]
    # strings e comentários com chaves não confundem o varredor
    dificil = 'a::before { content: "{"; } /* } */ .x { y: z }'
    assert [r.seletores for r in relatorios.regras_da_folha(dificil)] == [["a::before"], [".x"]]


def test_ac6_recursos_nao_usados_lista_so_o_que_nada_referencia():
    livro = _livro()
    assert relatorios.recursos_nao_usados(livro) == ["Images/sobra.png"]
    usos = relatorios.recursos_referenciados(livro)
    assert usos["Images/foto.png"] == {"cap1.xhtml"} and usos["Styles/estilo.css"] >= {"cap1.xhtml", "livro"}
    # o `url()` de uma folha e a capa também contam
    livro.recursos["Images/fundo.png"] = Recurso(caminho="Images/fundo.png", tipo_mime="image/png", dados=b"y")
    livro.recursos["Styles/estilo.css"].texto_cru = CSS + "body { background: url(../Images/fundo.png) }\n"
    livro.metadados.capa = "Images/sobra.png"
    assert relatorios.recursos_nao_usados(livro) == []


# ----------------------------------------------------------------------
# Na janela
# ----------------------------------------------------------------------

def test_na_janela_os_relatorios_vao_a_resultados_e_as_limpezas_perguntam():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        livro.recursos["Images/sobra.png"] = Recurso(caminho="Images/sobra.png", tipo_mime="image/png", dados=b"x")
        livro.recursos["Styles/estilo.css"] = Recurso(caminho="Styles/estilo.css", tipo_mime="text/css",
                                                      dados=CSS.encode("utf-8"))
        livro.folhas = ["Styles/estilo.css"]
        j._atualizar_painel_de_estilos()
        j.atualizar_navegador()
        linhas = j.executar("relatorio_imagens")
        assert any("não usada" in li.mensagem for li in linhas)
        assert len(j.resultados) == len(linhas) and "Imagens" in j.resultados.rotulo.cget("text")
        assert any("⚠" in r.mensagem for r in j.resultados.itens)
        # ativar uma linha de classe não usada abre a folha na linha da regra
        j.executar("relatorio_classes")
        k = next(k for k, r in enumerate(j.resultados.itens) if r.dados.get("classe") == "nunca")
        j.resultados.ativar(k)
        assert j.aba_ativa().arquivo == "Styles/estilo.css" and j.aba_ativa().widget.posicao[0] == 3
        # apagar recursos: só o não usado, com a lista para marcar
        pedidos = []
        j.caixas.marcar_varios = lambda titulo, rotulo, opcoes, marcadas=(), ok="OK": (pedidos.append(list(opcoes)),
                                                                                        list(marcadas))[1]
        assert j.executar("apagar_recursos") == ["Images/sobra.png"]
        assert pedidos == [["Images/sobra.png"]] and "Images/sobra.png" not in livro.recursos
        assert "Images/foto.png" in livro.recursos and j.projeto.sujo
        j.executar("apagar_recursos")
        assert any(c[0] == "informar" and "usados" in c[1] for c in t.caixas.chamadas)
        # apagar classes: pergunta, apaga nas folhas, a folha padrão vai ao painel Estilos e à aba
        t.caixas.pergunta_resposta = True
        resultado = j.executar("apagar_classes")
        assert set(resultado["Styles/estilo.css"]) == {"nunca", "jamais", "impresso", "titulo-nunca"}
        texto = livro.recursos["Styles/estilo.css"].texto_cru
        assert ".nunca" not in texto and "/* comentário que fica */" in texto
        assert j.painel_de_estilos.folha_padrao == texto and ".nunca" not in j.aba_ativa().widget.texto_todo()
        assert j.executar("apagar_classes") == {}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
