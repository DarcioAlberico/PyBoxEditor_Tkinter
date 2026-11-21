"""O escritor não reescreve o que a editora declarou (RG-10, R-51).

`_acessibilidade` trocava o `schema:accessibilitySummary` de qualquer livro por "Livro em
texto corrido, editado no PyBoxEditor" e afirmava `accessibilityHazard none` — um livro de
terceiro que declarava `flashing` saía declarando que não tinha perigo nenhum. O `none` é
decisão registrada só para o livro criado no editor (SPEC_EDITOR §10.1).
"""

import zipfile

from tests.test_ida_e_volta_do_pacote import _epub

from core.editor import epub


def _opf(caminho):
    with zipfile.ZipFile(caminho) as z:
        return z.read(next(n for n in z.namelist() if n.endswith(".opf"))).decode("utf-8")


def _com_metas(tmp_path, metas: str):
    caminho = _epub(tmp_path)
    with zipfile.ZipFile(caminho) as z:
        entradas = {n: z.read(n) for n in z.namelist()}
    opf = entradas["OEBPS/content.opf"].decode("utf-8").replace("</metadata>", metas + "\n</metadata>")
    entradas["OEBPS/content.opf"] = opf.encode("utf-8")
    novo = str(tmp_path / "declarado.epub")
    with zipfile.ZipFile(novo, "w") as z:
        z.writestr("mimetype", entradas.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for nome, dados in entradas.items():
            z.writestr(nome, dados)
    return novo


def _volta(tmp_path, origem, nome="volta.epub"):
    livro, _ = epub.ler(origem)
    saida = str(tmp_path / nome)
    epub.escrever(livro, saida)
    return _opf(saida), saida


def test_o_que_a_editora_declarou_volta_como_veio(tmp_path):
    origem = _com_metas(tmp_path, '<meta property="schema:accessibilitySummary">Resumo da editora.</meta>\n'
                                  '<meta property="schema:accessibilityHazard">flashing</meta>\n'
                                  '<meta property="dcterms:conformsTo">EPUB-A11Y-11_WCAG-21-AA</meta>\n'
                                  '<meta property="a11y:certifiedBy">Certificadora</meta>')
    opf, saida = _volta(tmp_path, origem)
    assert "accessibilitySummary\">Resumo da editora.<" in opf, "o resumo da editora foi trocado"
    assert "accessibilityHazard\">flashing<" in opf and "accessibilityHazard\">none<" not in opf
    assert "EPUB-A11Y-11_WCAG-21-AA" in opf and "Certificadora" in opf
    assert "accessMode\">textual<" in opf, "o accessMode deixou de ser calculado"
    # E de novo, a partir do salvo.
    opf2, _ = _volta(tmp_path, saida, "segunda.epub")
    assert "accessibilityHazard\">flashing<" in opf2 and "Resumo da editora." in opf2


def test_o_livro_de_terceiro_sem_declaracao_sai_unknown(tmp_path):
    opf, saida = _volta(tmp_path, _epub(tmp_path))
    assert "accessibilityHazard\">unknown<" in opf, "o perigo de um livro de terceiro virou none"
    assert "editado no PyBoxEditor" not in opf
    opf2, _ = _volta(tmp_path, saida, "segunda.epub")
    assert "accessibilityHazard\">unknown<" in opf2, "na segunda volta o livro de terceiro virou do editor"


def test_o_livro_criado_aqui_continua_none(tmp_path):
    livro = epub.novo_livro("Daqui")
    caminho = str(tmp_path / "daqui.epub")
    epub.escrever(livro, caminho)
    opf = _opf(caminho)
    assert "accessibilityHazard\">none<" in opf and "editado no PyBoxEditor" in opf
    opf2, _ = _volta(tmp_path, caminho, "daqui-2.epub")
    assert "accessibilityHazard\">none<" in opf2 and "editado no PyBoxEditor" in opf2
