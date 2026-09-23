"""
Testes de `core/editor/projeto.py` (ED-01; SPEC_EDITOR §7.6, §9 "Checkpoints"): o
rascunho a 61 s com relógio injetado, restaurando texto e recurso colado, apagado
ao salvar, e o livro sem caminho em `data_dir()/rascunhos/` (AC-ED01-5); os
recentes, onze → dez e o apagado some (AC-ED01-6); `reverter`, `checkpoint`,
`diferenca` e `restaurar` (AC-ED01-8).

Rodar sem pytest:      python tests/test_editor_projeto.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros as livros
from config.settings import Settings
from core.editor import epub, modelo as m, projeto as pj


class Relogio:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def avancar(self, s):
        self.t += s


def _paragrafo(texto):
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)])


# ----------------------------------------------------------------------
# AC-ED01-5: rascunho
# ----------------------------------------------------------------------

def test_ac5_o_rascunho_grava_a_61s_restaura_texto_e_recurso_colado_e_salvar_apaga(tmp_path):
    caminho = str(tmp_path / "livro.epub")
    epub.escrever(epub.novo_livro("L", "A", "pt"), caminho)
    relogio = Relogio()
    projeto = pj.Projeto.abrir(caminho, relogio=relogio)
    gravados = []

    def gravador(destino, dados):
        gravados.append(destino)
        pj.gravar_json_atomico(destino, dados)

    rascunho = pj.Rascunho(projeto, gravador, relogio=relogio, intervalo_s=60)
    assert rascunho.caminho == caminho + ".autosave.json"
    # Limpo: nada a gravar, por mais que o tempo passe.
    relogio.avancar(61)
    assert rascunho.tique() is False and not gravados
    # Sujo: a edição em modo código e um recurso colado.
    projeto.livro.capitulos[0].texto_cru = "<html><body><p>editado no código</p></body></html>"
    projeto.livro.recursos["Images/colada.png"] = m.Recurso(caminho="Images/colada.png", tipo_mime="image/png",
                                                            dados=livros.PNG_MINIMO)
    projeto.marcar_sujo()
    relogio.avancar(30)
    assert rascunho.tique() is False                                   # ainda não passou o intervalo
    relogio.avancar(31)
    assert rascunho.tique() is True and gravados == [rascunho.caminho]
    assert os.path.isfile(rascunho.caminho)
    relogio.avancar(61)
    assert rascunho.tique() is False                                   # nada mudou desde o último: não regrava
    projeto.marcar_sujo()
    relogio.avancar(61)
    assert rascunho.tique() is True and len(gravados) == 2
    assert pj.Rascunho.pendentes(caminho) == [rascunho.caminho]

    restaurado = pj.Rascunho.restaurar(rascunho.caminho)
    assert restaurado.caminho == caminho and restaurado.sujo is True
    assert restaurado.livro.capitulos[0].texto_cru == "<html><body><p>editado no código</p></body></html>"
    assert restaurado.livro.recursos["Images/colada.png"].dados == livros.PNG_MINIMO
    assert restaurado.livro.recursos["Styles/estilo.css"].dados is None            # continua no zip
    assert epub.dados_de(restaurado.livro, restaurado.livro.recursos["Styles/estilo.css"]).startswith(b"body")

    projeto.salvar()
    assert not os.path.exists(rascunho.caminho) and projeto.sujo is False
    assert pj.Rascunho.pendentes(caminho) == []
    relido, _ = epub.ler(caminho)
    assert relido.capitulos[0].texto_cru is None                        # o gravado foi relido como modelo
    assert m.texto_de(relido.capitulos[0].blocos[0]) == "editado no código"


def test_ac5_livro_sem_caminho_vai_para_a_pasta_de_rascunhos(tmp_path, monkeypatch):
    from config import paths
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path / "dados")
    projeto = pj.Projeto.novo("Sem caminho", "", "pt")
    assert pj.pasta_de_rascunhos() == os.path.join(str(tmp_path / "dados"), "rascunhos")
    rascunho = pj.Rascunho(projeto, intervalo_s=0)
    assert rascunho.caminho == os.path.join(pj.pasta_de_rascunhos(), projeto.uuid + ".json")
    projeto.livro.capitulos[0].blocos.append(_paragrafo("texto novo"))
    projeto.marcar_sujo()
    assert rascunho.tique() is True
    assert pj.Rascunho.pendentes() == [rascunho.caminho]
    dados = json.load(open(rascunho.caminho, encoding="utf-8"))
    assert dados["versao"] == 1 and dados["caminho"] == "" and dados["titulo"] == "Sem caminho"
    restaurado = pj.Rascunho.restaurar(rascunho.caminho)
    assert restaurado.caminho is None and restaurado.uuid == projeto.uuid
    assert m.texto_de(restaurado.livro.capitulos[0].blocos[-1]) == "texto novo"
    # Salvar como dá caminho ao projeto e apaga o rascunho do sem-caminho.
    destino = str(tmp_path / "agora-com-nome.epub")
    restaurado.salvar_como(destino)
    assert restaurado.caminho == destino and not os.path.exists(rascunho.caminho)
    assert pj.Rascunho.pendentes() == []
    # `fechar` também apaga: quem descartou, escolheu.
    projeto2 = pj.Projeto.novo("Outro", "", "pt")
    r2 = pj.Rascunho(projeto2, intervalo_s=0)
    projeto2.marcar_sujo()
    r2.gravar()
    assert os.path.exists(r2.caminho)
    projeto2.fechar()
    assert not os.path.exists(r2.caminho)


# ----------------------------------------------------------------------
# AC-ED01-6: recentes
# ----------------------------------------------------------------------

def test_ac6_recentes_guarda_dez_e_poda_o_que_sumiu(tmp_path):
    settings = Settings(path=str(tmp_path / "settings.json"))
    existentes = set()
    recentes = pj.Recentes(settings, existe=lambda c: c in existentes)
    for i in range(11):
        caminho = os.path.abspath(str(tmp_path / f"livro-{i}.epub"))
        existentes.add(caminho)
        recentes.adicionar(caminho)
    lista = recentes.lista()
    assert len(lista) == 10 and lista[0].endswith("livro-10.epub") and not any(c.endswith("livro-0.epub") for c in lista)
    # O mais recente sobe; repetir não duplica.
    recentes.adicionar(str(tmp_path / "livro-3.epub"))
    assert recentes.lista()[0].endswith("livro-3.epub") and len(recentes.lista()) == 10
    # O apagado some, e a poda é gravada.
    existentes.discard(os.path.abspath(str(tmp_path / "livro-7.epub")))
    assert not any(c.endswith("livro-7.epub") for c in recentes.lista()) and len(recentes.lista()) == 9
    gravado = json.load(open(settings.path, encoding="utf-8"))
    assert len(gravado["editor"]["recentes"]) == 9
    recentes.remover(str(tmp_path / "livro-3.epub"))
    assert len(recentes.lista()) == 8
    # Outras chaves de `editor` ficam.
    editor = settings.get("editor")
    editor["zoom"] = 1.25
    settings.set("editor", editor)
    recentes.adicionar(str(tmp_path / "livro-1.epub"))
    assert settings.get("editor")["zoom"] == 1.25


# ----------------------------------------------------------------------
# AC-ED01-8: reverter, checkpoint, diferença, restaurar
# ----------------------------------------------------------------------

def test_ac8_reverter_checkpoint_diferenca_e_restaurar(tmp_path):
    caminho = str(tmp_path / "livro.epub")
    epub.escrever(epub.novo_livro("L", "A", "pt"), caminho)
    projeto = pj.Projeto.abrir(caminho)
    assert projeto.nome == "livro.epub" and projeto.sujo is False and projeto.relatorio.capitulos == 1
    projeto.livro.capitulos[0].blocos.append(_paragrafo("perdido no reverter"))
    projeto.marcar_sujo()
    projeto.reverter()
    assert projeto.sujo is False and len(projeto.livro.capitulos[0].blocos) == 1

    ponto = projeto.checkpoint("antes")
    assert os.path.isfile(ponto.caminho) and ponto.caminho.startswith(caminho + ".checkpoints")
    assert ponto.rotulo == "antes" and ponto.nome.endswith("-antes.epub")
    assert [c.rotulo for c in projeto.checkpoints()] == ["antes"]
    assert projeto.livro.zip_de_origem == caminho                # o checkpoint é cópia, não destino
    assert projeto.diferenca(ponto) == []

    projeto.livro.capitulos[0].blocos.append(_paragrafo("depois do ponto"))
    projeto.livro.capitulos.append(m.Capitulo(arquivo="Text/cap-0002.xhtml", blocos=[_paragrafo("novo")]))
    projeto.marcar_sujo()
    diferencas = projeto.diferenca(ponto)
    por_arquivo = {d.arquivo: d for d in diferencas}
    assert por_arquivo["OEBPS/Text/cap-0001.xhtml"].estado == "alterado"
    assert "+<p>depois do ponto</p>" in por_arquivo["OEBPS/Text/cap-0001.xhtml"].diff
    assert por_arquivo["OEBPS/Text/cap-0002.xhtml"].estado == "novo"
    assert "OEBPS/package.opf" in por_arquivo and "+<itemref" in por_arquivo["OEBPS/package.opf"].diff
    assert "OEBPS/nav.xhtml" not in por_arquivo                    # sem título novo, o sumário não mudou
    assert str(por_arquivo["OEBPS/Text/cap-0002.xhtml"]) == "novo: OEBPS/Text/cap-0002.xhtml"
    assert projeto.livro.zip_de_origem == caminho

    ponto2 = projeto.checkpoint()
    assert len(projeto.checkpoints()) == 2 and ponto2.rotulo == ""
    projeto.restaurar(ponto)
    assert len(projeto.livro.capitulos) == 1 and len(projeto.livro.capitulos[0].blocos) == 1
    assert projeto.sujo is True and projeto.diferenca(ponto) == []
    assert epub.ler(caminho)[0].capitulos[0].blocos.__len__() == 1        # o disco só muda ao salvar
    projeto.salvar()
    assert projeto.sujo is False
    assert len(epub.ler(caminho)[0].capitulos) == 1
    assert [d.estado for d in projeto.diferenca(ponto2)] and any(d.estado == "removido" for d in projeto.diferenca(ponto2))


def test_a_diferenca_nao_conta_o_carimbo_de_quando_o_livro_foi_gravado(tmp_path, monkeypatch):
    """
    Comparar grava o livro atual, e gravar carimba o `dcterms:modified` com a hora de agora: com o
    relógio virando o segundo entre o ponto e a comparação, o OPF saía "alterado" sem nada ter
    mudado — no uso, sempre (o ponto é de minutos antes); no AC-8, às vezes, e a CI caiu nisso.
    """
    caminho = str(tmp_path / "livro.epub")
    epub.escrever(epub.novo_livro("L", "A", "pt"), caminho)
    projeto = pj.Projeto.abrir(caminho)
    segundos = iter(range(60))
    monkeypatch.setattr(epub, "_agora", lambda: f"2026-09-23T18:27:{next(segundos):02d}Z")
    ponto = projeto.checkpoint("antes")
    assert projeto.diferenca(ponto) == []
    # O que muda de verdade no OPF continua aparecendo — e só isso.
    projeto.livro.capitulos.append(m.Capitulo(arquivo="Text/cap-0002.xhtml", blocos=[_paragrafo("novo")]))
    opf = {d.arquivo: d for d in projeto.diferenca(ponto)}["OEBPS/package.opf"]
    mudadas = [linha for linha in opf.diff.splitlines() if linha[:1] in "+-" and linha[:3] not in ("+++", "---")]
    assert any("<itemref" in linha for linha in mudadas)
    assert not any("dcterms:modified" in linha for linha in mudadas), mudadas


def test_o_projeto_novo_sabe_o_nome_e_recusa_salvar_sem_caminho(tmp_path):
    projeto = pj.Projeto.novo("Meu livro", "Eu")
    assert projeto.nome == "Meu livro" and projeto.caminho is None
    with pytest.raises(ValueError):
        projeto.salvar()
    with pytest.raises(ValueError):
        projeto.reverter()
    ponto = projeto.checkpoint(pasta=str(tmp_path))
    assert ponto.caminho.startswith(os.path.join(str(tmp_path), projeto.uuid + ".checkpoints"))
    relatorio = projeto.salvar_como(str(tmp_path / "meu.epub"))
    assert relatorio.capitulos == 1 and projeto.nome == "meu.epub"
    assert all(r.dados is None for r in projeto.livro.recursos.values())     # soltos depois de gravar


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
