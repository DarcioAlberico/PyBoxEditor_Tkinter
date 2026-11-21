"""O escritor do EPUB não muda o livro aberto (RG-06, R-31).

`verificar` tirava do modelo vivo os marcos sem destino, e a opção `ncx` trocava o
`livro.ncx` antes de gravar — também quando a gravação falhava depois. O escritor passa a
trabalhar numa cópia, como `texto_do_opf` já fazia; do que gravou, só volta ao livro o que
o torna o livro daquele arquivo: a origem, o `ncx` escolhido e o identificador sorteado.
"""

import copy
import zipfile

import pytest

from core.editor import epub
from core.editor.projeto import Projeto
from core.editor.xhtml import ErroDeXhtml


def _livro_com_marco_quebrado():
    livro = epub.novo_livro("Marcos", ncx=False)
    livro.marcos = [("bodymatter", livro.capitulos[0].arquivo), ("toc", "Text/nao-existe.xhtml")]
    return livro


def test_gravar_com_sucesso_nao_muda_marcos_nem_ncx(tmp_path):
    livro = _livro_com_marco_quebrado()
    marcos, ncx = copy.deepcopy(livro.marcos), livro.ncx
    relatorio = epub.escrever(livro, str(tmp_path / "a.epub"))
    assert livro.marcos == marcos, "o escritor podou os marcos do livro aberto"
    assert livro.ncx == ncx
    assert any("marco toc sem destino" in a for a in relatorio.avisos)
    lido, _ = epub.ler(str(tmp_path / "a.epub"))
    assert lido.marcos == [("bodymatter", livro.capitulos[0].arquivo)]      # o arquivo sai podado


def test_gravar_com_falha_nao_muda_marcos_nem_ncx(tmp_path):
    livro = _livro_com_marco_quebrado()
    livro.capitulos[0].texto_cru = "<html><body><p>sem fechar</body></html>"
    marcos, ncx = copy.deepcopy(livro.marcos), livro.ncx
    with pytest.raises(ErroDeXhtml):
        epub.escrever(livro, str(tmp_path / "b.epub"), ncx=True)
    assert livro.marcos == marcos
    assert livro.ncx == ncx, "a gravação que falhou deixou o ncx trocado"


def test_o_que_o_arquivo_gravado_decide_volta_ao_livro(tmp_path):
    livro = _livro_com_marco_quebrado()
    livro.metadados.identificador = ""
    caminho = str(tmp_path / "c.epub")
    epub.escrever(livro, caminho, ncx=True)
    assert livro.ncx, "o ncx escolhido não voltou ao livro"
    assert livro.metadados.identificador, "o identificador sorteado não voltou: cada gravação sortearia outro"
    assert livro.zip_de_origem == caminho
    with zipfile.ZipFile(caminho) as z:
        assert any(n.endswith(livro.ncx) for n in z.namelist())
    lido, _ = epub.ler(caminho)
    assert lido.metadados.identificador == livro.metadados.identificador

    # Uma cópia (o checkpoint, a exportação) não decide nada.
    livro.metadados.identificador = ""
    epub.escrever(livro, str(tmp_path / "copia.epub"), destino=False)
    assert livro.metadados.identificador == "" and livro.zip_de_origem == caminho


def test_o_checkpoint_gravado_abre(tmp_path):
    projeto = Projeto(_livro_com_marco_quebrado(), None)
    ponto = projeto.checkpoint("antes", pasta=str(tmp_path))
    lido, _ = epub.ler(ponto.caminho)
    assert [c.arquivo for c in lido.capitulos] == [c.arquivo for c in projeto.livro.capitulos]
    assert len(projeto.livro.marcos) == 2
