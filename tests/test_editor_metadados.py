"""
Testes de `ui/editor/metadados.py` e de "Livro → Metadados…" (ED-08; SPEC_EDITOR §5, §9
"Metadata Editor"): a caixa completa aplica título, pessoas (com papel e `file-as`),
idioma, identificador, editora, data, descrição, assuntos, direitos, coleção, capa e
fonte impressa; os `refines`, os `ids` e os extras do OPF ficam como estavam;
`dcterms:modified` sai ao salvar; `epubcheck` limpo (`slow`) — AC-ED08-3.

Rodar sem pytest:      python tests/test_editor_metadados.py
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import epub, modelo as m, validacao
from editor_ambiente import Janela
from ui.editor import metadados as metadados_ui
from ui.editor.metadados import DialogoDeMetadados


def _livro_com_extras():
    livro = editor_livros.livro_completo()
    md = livro.metadados
    md.autores = [m.Pessoa(nome="Autora", papel="aut", file_as="Autora, A.", id="creator-1")]
    md.ids = {"titulo": "title", "identificador": "pub-id"}
    md.extras = [("meta", 'refines="#title" property="title-type"', "main"),
                 ("meta", 'refines="#creator-1" property="display-seq"', "1"),
                 ("meta", 'name="calibre:series" content="Série"', "")]
    md.identificador = "urn:uuid:0d2b2d6e-5cbd-4d3a-9f1c-000000000001"
    return livro


def test_ac3_aplicar_muda_o_que_a_caixa_tem_e_preserva_refines_ids_e_extras():
    livro = _livro_com_extras()
    md = livro.metadados
    valores = metadados_ui.valores_de(md)
    assert valores["autores"] == "Autora | aut | Autora, A." and valores["titulo"] == "Livro completo"
    valores.update(titulo="Novo título", autores="Autora | aut | Autora, A.\nCoautor | ill", colaboradores="Revisor",
                   idioma="pt-BR", editora="Casa", data="2026-09", descricao="Um livro.", assuntos="xadrez\nfinais",
                   direitos="CC BY", colecao="Finais", posicao="3", capa="Images/foto.png", fonte_impressa="ISBN 1")
    metadados_ui.aplicar(md, valores)
    assert md.titulo == "Novo título" and md.idioma == "pt-BR" and md.editora == "Casa" and md.data == "2026-09"
    assert [(p.nome, p.papel, p.file_as, p.id) for p in md.autores] == [("Autora", "aut", "Autora, A.", "creator-1"),
                                                                        ("Coautor", "ill", "", "")]
    assert [(p.nome, p.papel) for p in md.colaboradores] == [("Revisor", "ctb")]
    assert md.assuntos == ["xadrez", "finais"] and md.colecao == ("Finais", 3) and md.capa == "Images/foto.png"
    assert md.fonte_impressa == "ISBN 1" and md.direitos == "CC BY" and md.descricao == "Um livro."
    assert md.ids == {"titulo": "title", "identificador": "pub-id"} and len(md.extras) == 3
    # validação: título vazio, idioma e data inválidos, posição não numérica
    for chave, valor in (("titulo", " "), ("idioma", "portugues!"), ("data", "12/09/2026"), ("posicao", "x")):
        errados = dict(valores)
        errados[chave] = valor
        with pytest.raises(ValueError):
            metadados_ui.validar(errados)


def test_a_caixa_constroi_sem_mostrar_e_devolve_os_valores():
    with Janela(abrir=False) as t:
        livro = _livro_com_extras()
        caixa = DialogoDeMetadados(t.j, livro.metadados, ["Images/foto.png"])
        caixa.construir()
        assert caixa.valores()["titulo"] == "Livro completo" and caixa.valores()["capa"] == ""
        caixa.definir(titulo="Outro", assuntos="a\nb", capa="Images/foto.png")
        valores = caixa.confirmar()
        assert valores["titulo"] == "Outro" and valores["assuntos"] == "a\nb" and valores["capa"] == "Images/foto.png"
        with pytest.raises(KeyError):
            caixa.definir(lua="x")


def test_na_janela_os_metadados_completos_gravam_e_o_opf_sai_com_refines_e_modified():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        livro.metadados.extras = [("meta", 'name="calibre:series" content="Série"', "")]
        j.caixas.metadados_completos = lambda md, imagens: dict(metadados_ui.valores_de(md), titulo="Pela caixa",
                                                                 autores="Autora | aut | Autora, A.",
                                                                 capa=imagens[0], colecao="Coleção", posicao="2")
        md = j.executar("metadados")
        assert md.titulo == "Pela caixa" and md.capa == "Images/foto.png" and md.colecao == ("Coleção", 2)
        assert j.projeto.sujo and j.title().startswith("• ")
        # a forma curta da ED-02 continua valendo (e troca a autora)
        j.executar("metadados", "Curta", "Alguém", "en")
        assert (md.titulo, md.autores[0].nome, md.idioma) == ("Curta", "Alguém", "en") and md.capa == "Images/foto.png"
        # uma capa que não existe é erro de entrada
        j.caixas.metadados_completos = lambda md, imagens: dict(metadados_ui.valores_de(md), capa="Images/nada.png")
        j.executar("metadados")
        assert "não está no livro" in t.caixas.entradas()[-1]
        j.caixas.metadados_completos = lambda md, imagens: dict(metadados_ui.valores_de(md), capa="Images/foto.png",
                                                                 autores="Autora | aut | Autora, A.")
        j.executar("metadados")
        j.executar("salvar")
        with zipfile.ZipFile(t.epub) as z:
            opf = z.read(livro.opf).decode("utf-8")
        assert "<dc:title>Curta</dc:title>" in opf and 'property="dcterms:modified"' in opf
        assert 'name="calibre:series"' in opf and 'property="file-as"' in opf and "Autora, A." in opf
        assert 'property="belongs-to-collection"' in opf and 'property="group-position"' in opf
        relido, _rel = epub.ler(t.epub)
        assert relido.metadados.modificado and relido.metadados.colecao == ("Coleção", 2)
        assert relido.metadados.autores[0].file_as == "Autora, A."


@pytest.mark.slow
def test_ac3_os_metadados_completos_passam_no_epubcheck(tmp_path):
    if validacao.comando_do_epubcheck() is None:
        pytest.skip("sem Java/epubcheck")
    livro = _livro_com_extras()
    valores = metadados_ui.valores_de(livro.metadados)
    valores.update(editora="Casa", data="2026-09-21", descricao="Um livro.", assuntos="xadrez", direitos="CC BY",
                   colecao="Finais", posicao="3", capa="Images/foto.png", fonte_impressa="ISBN 1",
                   colaboradores="Revisor | edt")
    metadados_ui.aplicar(livro.metadados, valores)
    caminho = str(tmp_path / "md.epub")
    epub.escrever(livro, caminho)
    r = validacao.validar(caminho, livro.opf)
    assert r.valido, [str(x) for x in r.erros]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
