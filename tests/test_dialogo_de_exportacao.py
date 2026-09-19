"""A caixa única de exportação (2026-09-18) e o que ela promete.

Até aqui a exportação era um assistente de até catorze `messagebox` em
sequência, sem memória entre uma exportação e outra. Os testes fixam o
contrato da caixa que os substitui: o que se escolhe vira um
`OpcoesDeExportacao`; o que se escolheu volta preenchido da próxima vez
(`Settings`), de modo que exportar o mesmo livro de novo é abrir a caixa e
confirmar; o formulário só libera o botão quando está consistente; o modelo
de linha só entra se passa no portão; e cancelar é desistir.

A caixa é construída sem `mostrar()` — `wait_window` esperaria um clique que
não vem — e operada pelas variáveis dos widgets, como um usuário faria.
"""

import json
import os
import sys

import pytest
from tkinter import ttk

from conftest import raiz_tk
from config.settings import Settings
from core import livro
from ui.dialogo_de_exportacao import (CHAVE_DAS_OPCOES, FORMATOS_DE_LIVRO,
                                      FORMATOS_EDITORIAIS, DialogoDeExportacao,
                                      OpcoesDeExportacao)
from ui.dialogo_do_diagrama import DialogoDoDiagrama, PainelDoDiagrama


class _Caixa:
    """A caixa construída sobre uma raiz de teste, com `Settings` num tmp."""

    def __init__(self, tmp_path, **kw):
        self.raiz = raiz_tk()
        if self.raiz is None:
            pytest.skip("sem display")
        self.settings = Settings(path=str(tmp_path / "settings.json"))
        entrada = str(tmp_path / "Livro de Teste.pdf")
        argumentos = dict(entrada=entrada, total_paginas=12,
                          formatos=FORMATOS_DE_LIVRO,
                          configuracoes=lambda: self.settings,
                          idioma_detectado="en",
                          motor_de_prosa=(True, "5.5.0"),
                          modelo_de_linha=(False, "o modelo de linha erra 96% dos "
                                                  "caracteres na validação"))
        argumentos.update(kw)
        self.caixa = DialogoDeExportacao(self.raiz, **argumentos)
        self.caixa._construir()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        try:
            if self.caixa.top.winfo_exists():
                self.caixa.top.destroy()
            self.raiz.destroy()
        except Exception:
            pass


def _pronta(caixa) -> bool:
    return "disabled" not in caixa.btn_ok.state()


# ----------------------------------------------------------------------
# O formulário vira opções
# ----------------------------------------------------------------------

def test_a_caixa_abre_pronta_para_exportar_com_o_padrao(tmp_path):
    with _Caixa(tmp_path) as c:
        assert _pronta(c.caixa), c.caixa.lbl_aviso.cget("text")
        opcoes, erro = c.caixa._montar()
        assert erro is None
        assert opcoes.formato == "epub"
        assert opcoes.saida.endswith("Livro de Teste.epub")
        assert opcoes.paginas is None
        assert opcoes.idioma == "en"
        assert opcoes.diagramas == "render"
        assert opcoes.coordenadas is False
        assert opcoes.reparar is False and opcoes.coletar is False
        assert opcoes.modelo_de_linha is False


def test_as_escolhas_atravessam_o_formulario(tmp_path):
    with _Caixa(tmp_path) as c:
        x = c.caixa
        x.var_formato.set("docx")
        x._mudou_o_formato()
        x.var_intervalo.set(True)
        x.var_de.set("3")
        x.var_ate.set("7")
        x.var_idioma.set("pt")
        x.var_coordenadas.set("livro")
        x.var_reparar.set(True)
        x.var_coletar.set(True)
        x.var_teto.set("250")
        x.var_embutir.set(True)
        x.painel.var_moldura.set("dupla")
        x.painel.var_cantos.set(True)
        x.painel.var_corpo.set("20")
        x._validar()
        assert _pronta(x), x.lbl_aviso.cget("text")
        opcoes, _erro = x._montar()
        assert opcoes.formato == "docx" and opcoes.saida.endswith(".docx")
        assert opcoes.paginas == [2, 3, 4, 5, 6]
        assert opcoes.idioma == "pt"
        assert opcoes.coordenadas == livro.COMO_NO_LIVRO
        assert opcoes.reparar and opcoes.coletar and opcoes.teto == 250
        assert opcoes.embutir_fonte and opcoes.diagramas_no_arquivo == "fonte"
        assert opcoes.moldura == "dupla" and opcoes.cantos == "arredondado"
        assert opcoes.corpo_pt == 20.0


def test_sem_redesenho_nao_ha_fonte_embutida(tmp_path):
    """Recorte de scan não vira letra: a caixinha desliga junto com o desenho."""
    with _Caixa(tmp_path) as c:
        x = c.caixa
        x.var_embutir.set(True)
        x.var_desenhar.set(False)
        x._mudou_o_desenho()
        opcoes, _erro = x._montar()
        assert opcoes.diagramas == "recorte"
        assert opcoes.embutir_fonte is False
        assert opcoes.diagramas_no_arquivo == "png"
        assert "disabled" in x.chk_embutir.state()


# ----------------------------------------------------------------------
# O botão só libera com o formulário consistente
# ----------------------------------------------------------------------

@pytest.mark.parametrize("de, ate, motivo", [
    ("0", "5", "entre 1 e 12"), ("7", "3", "entre 1 e 12"),
    ("1", "13", "entre 1 e 12"), ("a", "5", "entre 1 e 12"),
])
def test_intervalo_invalido_trava_o_botao_e_diz_por_que(tmp_path, de, ate, motivo):
    with _Caixa(tmp_path) as c:
        x = c.caixa
        x.var_intervalo.set(True)
        x.var_de.set(de)
        x.var_ate.set(ate)
        x._validar()
        assert not _pronta(x)
        assert motivo in x.lbl_aviso.cget("text")


def test_teto_que_nao_e_numero_trava_o_botao(tmp_path):
    with _Caixa(tmp_path) as c:
        x = c.caixa
        x.var_coletar.set(True)
        x.var_teto.set("l00")
        x._validar()
        assert not _pronta(x)
        x.var_teto.set("")
        x._validar()
        assert _pronta(x), "em branco é sem teto"
        assert x._montar()[0].teto is None


def test_extensao_diferente_do_formato_trava_o_botao(tmp_path):
    with _Caixa(tmp_path) as c:
        x = c.caixa
        x.var_saida.set(str(tmp_path / "saida.txt"))
        x._validar()
        assert not _pronta(x)
        assert ".epub" in x.lbl_aviso.cget("text")


def test_trocar_o_formato_troca_so_a_extensao(tmp_path):
    with _Caixa(tmp_path) as c:
        x = c.caixa
        x.var_saida.set(str(tmp_path / "meu livro.epub"))
        x.var_formato.set("docx")
        x._mudou_o_formato()
        assert x.var_saida.get() == str(tmp_path / "meu livro.docx")


# ----------------------------------------------------------------------
# O que se escolheu volta preenchido
# ----------------------------------------------------------------------

def test_confirmar_guarda_as_preferencias_e_a_proxima_caixa_abre_com_elas(tmp_path):
    with _Caixa(tmp_path) as c:
        x = c.caixa
        x.var_formato.set("docx")
        x._mudou_o_formato()
        x.var_idioma.set("pt")
        x.var_reparar.set(True)
        x.var_coordenadas.set("com")
        x.painel.var_moldura.set("dupla")
        x.painel.var_corpo.set("18")
        x._validar()
        x._confirmar()
        assert x.resultado is not None and x.resultado.formato == "docx"
        gravado = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert gravado[CHAVE_DAS_OPCOES]["reparar"] is True
        assert gravado[CHAVE_DAS_OPCOES]["moldura"] == "dupla"
        assert "saida" not in gravado[CHAVE_DAS_OPCOES], "o caminho é deste livro"

    # A segunda caixa, sobre o mesmo `settings.json`, já vem como a primeira
    # ficou — e pronta para confirmar sem tocar em nada. (O idioma detectado
    # pela camada de texto ganha do guardado: é do livro, não do usuário.)
    with _Caixa(tmp_path, idioma_detectado=None) as c:
        x = c.caixa
        assert _pronta(x)
        opcoes, _erro = x._montar()
        assert opcoes.formato == "docx" and opcoes.saida.endswith(".docx")
        assert opcoes.idioma == "pt"
        assert opcoes.reparar is True
        assert opcoes.coordenadas is True
        assert opcoes.moldura == "dupla" and opcoes.corpo_pt == 18.0


def test_o_idioma_detectado_ganha_do_guardado(tmp_path):
    settings = Settings(path=str(tmp_path / "settings.json"))
    settings.set(CHAVE_DAS_OPCOES, OpcoesDeExportacao(idioma="pt").para_settings())
    settings.save()
    with _Caixa(tmp_path, idioma_detectado="en") as c:
        assert c.caixa.var_idioma.get() == "en"


def test_preferencia_que_nao_e_objeto_nao_derruba_a_caixa(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({CHAVE_DAS_OPCOES: "banana"}), encoding="utf-8")
    with _Caixa(tmp_path) as c:
        assert _pronta(c.caixa)
    assert OpcoesDeExportacao.de_settings(["a", "b"]).formato == "epub"


def test_enter_num_campo_de_texto_nao_exporta(tmp_path):
    """No campo "Salvar em" o Enter é o fim da digitação, não o do formulário."""
    class _Evento:
        def __init__(self, widget):
            self.widget = widget

    with _Caixa(tmp_path) as c:
        x = c.caixa
        campo = _achar(x.top, ttk.Entry)
        assert x._enter(_Evento(campo)) is None
        assert x.resultado is None, "Enter no campo de texto não exporta"
        x._enter(_Evento(x.btn_ok))
        assert x.resultado is not None, "Enter fora do campo confirma"


def _achar(widget, tipo):
    for filho in widget.winfo_children():
        if isinstance(filho, tipo):
            return filho
        achado = _achar(filho, tipo)
        if achado is not None:
            return achado
    return None


def test_preferencia_corrompida_nao_derruba_a_caixa(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({CHAVE_DAS_OPCOES: {"coordenadas": "banana", "corpo_pt": "x",
                                        "formato": "pptx", "teto": "muitos"}}),
        encoding="utf-8")
    with _Caixa(tmp_path) as c:
        assert _pronta(c.caixa)
        opcoes, _erro = c.caixa._montar()
        assert opcoes.coordenadas is False
        assert opcoes.formato == "epub"


# ----------------------------------------------------------------------
# O portão do modelo de linha, e cancelar
# ----------------------------------------------------------------------

def test_o_modelo_de_linha_reprovado_fica_desligado_mesmo_se_estava_guardado(tmp_path):
    settings = Settings(path=str(tmp_path / "settings.json"))
    settings.set(CHAVE_DAS_OPCOES, OpcoesDeExportacao(modelo_de_linha=True).para_settings())
    settings.save()
    with _Caixa(tmp_path, modelo_de_linha=(False, "o modelo de linha erra 96% dos "
                                                  "caracteres na validação")) as c:
        opcoes, _erro = c.caixa._montar()
        assert opcoes.modelo_de_linha is False
    with _Caixa(tmp_path, modelo_de_linha=(True, "modelo de linha com 4,0% de CER "
                                                 "na validação")) as c:
        opcoes, _erro = c.caixa._montar()
        assert opcoes.modelo_de_linha is True


def test_cancelar_e_desistir(tmp_path):
    with _Caixa(tmp_path) as c:
        c.caixa._cancelar()
        assert c.caixa.resultado is None
        assert not (tmp_path / "settings.json").exists()


def test_os_formatos_editoriais_entram_na_mesma_caixa(tmp_path):
    with _Caixa(tmp_path, formatos=FORMATOS_EDITORIAIS,
                titulo="Exportar documento editorial") as c:
        x = c.caixa
        assert x.top.title() == "Exportar documento editorial"
        x.var_formato.set("json")
        x._mudou_o_formato()
        opcoes, _erro = x._montar()
        assert opcoes.formato == "json" and opcoes.saida.endswith(".json")


def test_uma_pagina_so_nao_oferece_intervalo(tmp_path):
    with _Caixa(tmp_path, total_paginas=1,
                entrada=str(tmp_path / "pagina.png")) as c:
        opcoes, _erro = c.caixa._montar()
        assert opcoes.paginas is None


# ----------------------------------------------------------------------
# O painel do diagrama continua sendo a caixa de antes, sozinho
# ----------------------------------------------------------------------

def test_o_painel_do_diagrama_devolve_a_quadrupla_e_recusa_corpo_fora_da_regua():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        painel = PainelDoDiagrama(raiz, moldura="dupla", cantos="arredondado",
                                  corpo_pt=20.0)
        assert painel.valores()[1:] == ("dupla", "arredondado", 20.0)
        painel.var_corpo.set("200")
        assert painel.valores() is None
        painel.var_moldura.set("sem")
        painel.var_corpo.set("16")
        assert painel.valores()[1:] == ("sem", "reto", 16.0), "sem filete não há quina"
    finally:
        raiz.destroy()


def test_a_caixa_do_diagrama_sozinha_ainda_funciona():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        caixa = DialogoDoDiagrama(raiz, moldura="simples", corpo_pt=16.0)
        caixa._construir()
        caixa._confirmar()
        assert caixa.resultado[1:] == ("simples", "reto", 16.0)
    finally:
        raiz.destroy()


def test_os_padroes_das_opcoes_batem_com_os_da_extracao():
    """O padrão da caixa é o padrão de `livro.extrair`, sem cópia divergente."""
    import inspect
    assinatura = inspect.signature(livro.extrair).parameters
    o = OpcoesDeExportacao()
    assert o.fonte == assinatura["fonte"].default
    assert o.moldura == assinatura["moldura"].default
    assert o.cantos == assinatura["cantos"].default
    assert o.coordenadas == assinatura["coordenadas"].default
    assert o.diagramas == assinatura["diagramas"].default
    assert os.path.splitext("x.epub")[1] == ".epub"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
