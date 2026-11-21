"""Preferências e buscas salvas não se perdem (RG-05, R-02).

Três perdas, reproduzidas antes do conserto:

- o `settings.json` que não se lia por `PermissionError` (o antivírus, outro processo com
  o arquivo aberto) era tratado como JSON quebrado, e o `save` seguinte gravava por cima o
  que a instância sabia: o arquivo inteiro virava `{"x": 1}`;
- dois editores abertos regravavam a chave `editor` inteira a partir da cópia que cada um
  leu ao nascer, e as buscas salvas de um sumiam quando o outro gravava o layout;
- a busca salva que esta versão não entende (sem `nome`, ou com uma opção desconhecida, de
  uma versão mais nova) era descartada ao carregar, e o próximo `gravar` a apagava do disco.
"""

import json
import logging
from pathlib import Path

import pytest

from config.settings import Settings
from core.editor.buscas_salvas import BuscaSalva, Colecao


def _no_disco(caminho):
    return json.loads(caminho.read_text(encoding="utf-8"))


def _ilegivel_por(monkeypatch, caminho):
    """`read_text` do `caminho` levanta `PermissionError`, como num arquivo preso por outro processo."""
    original = Path.read_text

    def read_text(self, *a, **k):
        if Path(self) == Path(caminho):
            raise PermissionError(13, "Acesso negado", str(caminho))
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", read_text)
    return lambda: monkeypatch.setattr(Path, "read_text", original)


def test_arquivo_que_nao_se_abre_nao_e_regravado(tmp_path, monkeypatch, caplog):
    caminho = tmp_path / "settings.json"
    caminho.write_text(json.dumps({"tema": "claro", "editor": {"zoom": 1.5}}), encoding="utf-8")
    soltar = _ilegivel_por(monkeypatch, caminho)
    settings = Settings(caminho)
    settings.set("x", 1)
    with caplog.at_level(logging.WARNING):
        settings.save()
    soltar()
    assert _no_disco(caminho) == {"tema": "claro", "editor": {"zoom": 1.5}}, \
        "o arquivo que não se abriu foi regravado com o que a instância sabia"
    assert any("não se leu" in r.getMessage() for r in caplog.records)

    # Quando o arquivo volta a abrir, o que se mudou aqui vai — e o resto fica.
    settings.save()
    assert _no_disco(caminho) == {"tema": "claro", "editor": {"zoom": 1.5}, "x": 1}


def test_json_quebrado_fica_guardado_ao_lado(tmp_path, caplog):
    caminho = tmp_path / "settings.json"
    caminho.write_text("{ quebrado", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        settings = Settings(caminho)
    settings.set("idioma", "pt")
    settings.save()
    assert _no_disco(caminho) == {"idioma": "pt"}
    guardado = tmp_path / "settings.json.corrompido"
    assert guardado.read_text(encoding="utf-8") == "{ quebrado"
    assert any("corrompido" in r.getMessage() for r in caplog.records)


def test_dois_editores_nao_apagam_as_buscas_um_do_outro(tmp_path):
    caminho = tmp_path / "settings.json"
    caminho.write_text(json.dumps({"editor": {"recentes": ["a.epub"]}}), encoding="utf-8")
    um, outro = Settings(caminho), Settings(caminho)

    # O primeiro guarda uma busca, do jeito do editor (cópia da chave, uma subchave trocada).
    editor = dict(um.get("editor"))
    editor["buscas_salvas"] = [{"nome": "lance", "grupo": "", "opcoes": {}}]
    um.set("editor", editor)
    um.save()

    # O segundo, que leu a chave antes, grava o layout.
    editor = dict(outro.get("editor"))
    editor["layout"] = {"largura": 900}
    outro.set("editor", editor)
    outro.save()

    assert _no_disco(caminho)["editor"] == {
        "recentes": ["a.epub"],
        "buscas_salvas": [{"nome": "lance", "grupo": "", "opcoes": {}}],
        "layout": {"largura": 900},
    }, "o layout do segundo editor apagou a busca salva do primeiro"

    # A subchave apagada de um lado sai do disco, e a da outra instância fica.
    editor = dict(um.get("editor"))
    del editor["recentes"]
    um.set("editor", editor)
    um.save()
    assert _no_disco(caminho)["editor"] == {
        "buscas_salvas": [{"nome": "lance", "grupo": "", "opcoes": {}}],
        "layout": {"largura": 900},
    }


@pytest.mark.parametrize("ilegivel", [
    {"grupo": "sem nome", "opcoes": {}},
    {"nome": "escopo novo", "grupo": "", "opcoes": {"escopo": "so_nas_notas"}},
    "não é um dicionário",
])
def test_a_busca_que_nao_se_le_volta_intacta_ao_disco(ilegivel):
    gravado = []
    dados = [{"nome": "lance", "grupo": "", "opcoes": {}}, ilegivel]
    colecao = Colecao.carregar(dados, gravador=gravado.append)
    assert colecao.nomes() == ["lance"], "a busca que não se lê foi oferecida"

    colecao.guardar(BuscaSalva("xeque"))
    assert gravado[-1][-1] == ilegivel, "a busca que não se lê sumiu do disco"
    assert [b.get("nome") for b in gravado[-1] if isinstance(b, dict)][:2] == ["lance", "xeque"]


def test_a_opcao_de_uma_versao_mais_nova_volta_ao_disco():
    """A busca com uma opção que esta versão não conhece continua oferecida (ED-06b: roda
    sem ela), mas a opção volta ao disco com ela — a versão que a gravou ainda a entende."""
    gravado = []
    futura = {"nome": "futura", "grupo": "g", "opcoes": {"texto": "x", "so_nas_notas": True}}
    colecao = Colecao.carregar([futura], gravador=gravado.append)
    assert colecao.por_nome("futura").opcoes == {"texto": "x"}
    colecao.guardar(BuscaSalva("xeque"))
    assert gravado[-1][0] == futura, "a opção desconhecida sumiu do disco"

    # Trocada pelo usuário, a busca é a nova, inteira.
    colecao.guardar(BuscaSalva("futura", "g", {"texto": "y"}))
    assert gravado[-1][0] == {"nome": "futura", "grupo": "g", "opcoes": {"texto": "y"}}
