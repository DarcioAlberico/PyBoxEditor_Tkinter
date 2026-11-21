"""O EPUB salvo não perde recurso (RG-06, R-03).

- O recurso que não se lia na gravação (o EPUB de origem apagado ou movido depois de
  aberto) virava aviso, e o `os.replace` acontecia mesmo assim: o livro salvo saía sem as
  imagens, por cima do arquivo do usuário.
- `renomear` trocava `recurso.caminho` sem carregar os bytes, e `dados_de` procurava o
  nome novo no zip antigo: renomear `Images/fé.png` e salvar perdia a imagem.
"""

import os
import zipfile

import pytest

from core.editor import epub, livro_ops
from core.editor.epub import RecursosIlegiveis
from core.editor.modelo import Recurso
from core.editor.projeto import Projeto

_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15"
        b"\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def _epub_com_imagem(tmp_path, nome="Images/fé.png"):
    livro = epub.novo_livro("Com imagem")
    livro.recursos[nome] = Recurso(caminho=nome, tipo_mime="image/png", dados=_PNG)
    caminho = str(tmp_path / "origem.epub")
    epub.escrever(livro, caminho)
    return caminho, nome


def _nomes(caminho):
    with zipfile.ZipFile(caminho) as z:
        return set(z.namelist())


def test_origem_apagada_falha_com_a_lista_e_o_destino_nao_muda(tmp_path):
    origem, nome = _epub_com_imagem(tmp_path)
    projeto = Projeto.abrir(origem)
    assert projeto.livro.recursos[nome].dados is None           # ainda no zip
    destino = tmp_path / "destino.epub"
    destino.write_bytes(b"o arquivo do usuario")
    os.remove(origem)

    with pytest.raises(RecursosIlegiveis) as erro:
        projeto.salvar_como(str(destino))
    assert nome in erro.value.recursos
    assert nome in str(erro.value)
    assert destino.read_bytes() == b"o arquivo do usuario", "o destino foi trocado"
    assert projeto.caminho == origem, "o projeto passou a apontar para o que não se gravou"

    # Com a opção explícita, salva sem ele — e o livro aberto deixa de pedi-lo.
    relatorio = projeto.salvar_como(str(destino), sem_ilegiveis=True)
    assert "OEBPS/" + nome not in _nomes(destino)
    assert any(nome in a for a in relatorio.avisos)
    assert nome not in projeto.livro.recursos
    projeto.salvar()                                             # sem levantar de novo


def test_o_checkpoint_e_a_diferenca_seguem_a_mesma_regra(tmp_path):
    origem, nome = _epub_com_imagem(tmp_path)
    projeto = Projeto.abrir(origem)
    os.remove(origem)
    pasta = str(tmp_path / "pontos")
    with pytest.raises(RecursosIlegiveis):
        projeto.checkpoint("antes", pasta=pasta)
    assert not os.path.isdir(pasta) or not os.listdir(pasta), "o checkpoint incompleto ficou no disco"


def test_renomear_a_imagem_e_salvar_leva_a_imagem(tmp_path):
    origem, nome = _epub_com_imagem(tmp_path)
    projeto = Projeto.abrir(origem)
    livro_ops.renomear(projeto.livro, nome, "Images/fe-2.png")
    destino = str(tmp_path / "renomeado.epub")
    projeto.salvar_como(destino)
    with zipfile.ZipFile(destino) as z:
        assert z.read("OEBPS/Images/fe-2.png") == _PNG, "a imagem renomeada sumiu do zip"

    # E de novo, a partir do zip novo: o nome de origem acompanhou a gravação.
    livro_ops.renomear(projeto.livro, "Images/fe-2.png", "Images/fe-3.png")
    projeto.salvar()
    with zipfile.ZipFile(destino) as z:
        assert z.read("OEBPS/Images/fe-3.png") == _PNG


def test_renomear_varios_e_salvar_com_a_origem_presente(tmp_path):
    origem, nome = _epub_com_imagem(tmp_path, nome="Images/a.png")
    projeto = Projeto.abrir(origem)
    livro_ops.renomear(projeto.livro, "Images/a.png", "Images/b.png")
    livro_ops.renomear_varios(projeto.livro, "parte-%02d")
    destino = str(tmp_path / "varios.epub")
    projeto.salvar_como(destino)
    with zipfile.ZipFile(destino) as z:
        assert z.read("OEBPS/Images/b.png") == _PNG


def test_na_janela_salvar_pergunta_e_o_nao_nao_grava_nada(tmp_path):
    from tests.test_editor_janela import _Janela

    origem, nome = _epub_com_imagem(tmp_path)
    with _Janela(abrir=False, pasta=str(tmp_path)) as t:
        t.j.executar("abrir", origem)
        os.remove(origem)
        t.caixas.pergunta_resposta = False
        assert t.j.salvar() is None
        pergunta = [c for c in t.caixas.chamadas if c[0] == "pergunta"][-1][1]
        assert nome in pergunta and "Salvar sem eles" in pergunta
        assert not os.path.exists(origem), "o 'Não' gravou o livro"

        t.caixas.pergunta_resposta = True
        assert t.j.salvar() is not None
        assert "OEBPS/" + nome not in _nomes(origem)
