"""
F7.3 — o metadado amarrado ao modelo que ele descreve.

`model_meta.json` está no git e `custom_model.pth` não (`*.pth` é ignorado, são
2,5 MB de binário). Quem clona recebe o metadado sem o modelo — e basta aparecer
um `.pth` de outra rodada, com o mesmo número de classes, para o par ficar
trocado.

**O estrago de um par trocado é calado.** `idx_to_char` traduz índice em
caractere; índices de outro treino apontam para as letras erradas. Nada levanta,
nada avisa — o OCR só passa a ler outra coisa. É a família do defeito da F1.4,
em que 127 amostras treinaram a classe errada por meses.

Contagem de classes diferente já falhava alto: `SimpleCNN(num_classes)` recusa
pesos de outro formato. O que faltava era mesma contagem e ordem diferente — o
que acontece ao acrescentar e remover uma pasta na mesma rodada.

Rodar sem pytest:      python tests/test_f73_modelo.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.neural_trainer import (SCHEMA_META, NeuralPredictor,
                                 impressao_das_classes, impressao_do_modelo)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ----------------------------------------------------------------------
# As impressões digitais
# ----------------------------------------------------------------------

def test_impressao_do_modelo_muda_com_o_conteudo(tmp_path):
    a, b = tmp_path / "a.pth", tmp_path / "b.pth"
    a.write_bytes(b"pesos" * 100)
    b.write_bytes(b"pesos" * 100 + b"!")
    assert impressao_do_modelo(str(a)) == impressao_do_modelo(str(a))
    assert impressao_do_modelo(str(a)) != impressao_do_modelo(str(b))


def test_impressao_de_arquivo_ausente_e_vazia(tmp_path):
    """Vazio significa 'não deu para conferir', e é tratado como tal."""
    assert impressao_do_modelo(str(tmp_path / "nao_existe.pth")) == ""


def test_impressao_das_classes_ignora_a_ordem_do_dicionario():
    a = {"0": "a", "1": "b", "2": "c"}
    b = {"2": "c", "0": "a", "1": "b"}
    assert impressao_das_classes(a) == impressao_das_classes(b)


def test_impressao_das_classes_muda_se_a_ordem_dos_indices_muda():
    """É exatamente o caso perigoso: mesma contagem, índices deslocados."""
    a = {"0": "a", "1": "b", "2": "c"}
    b = {"0": "a", "1": "c", "2": "b"}
    assert impressao_das_classes(a) != impressao_das_classes(b)


def test_impressao_das_classes_aceita_chave_int_ou_str():
    assert impressao_das_classes({0: "a", 1: "b"}) == \
           impressao_das_classes({"0": "a", "1": "b"})


# ----------------------------------------------------------------------
# A carga
# ----------------------------------------------------------------------

def _par(tmp_path, **extra):
    """Um par .pth/.json de mentira, com o metadado que se pedir."""
    import torch
    from core.neural_model import SimpleCNN

    pth = tmp_path / "m.pth"
    meta = tmp_path / "m.json"
    idx = {str(i): c for i, c in enumerate("abcde")}
    torch.save(SimpleCNN(len(idx)).state_dict(), str(pth))

    conteudo = {
        "schema_version": SCHEMA_META,
        "label_map": {c: i for i, c in enumerate("abcde")},
        "idx_to_char": idx,
        "num_classes": len(idx),
        # Calibrada de propósito: `temperatura == 1.0` é a ressalva da
        # F26, e um par "coerente" tem de sair sem ressalva nenhuma.
        "temperatura": 2.0,
        "modelo_sha256": impressao_do_modelo(str(pth)),
        "classes_sha256": impressao_das_classes(idx),
    }
    conteudo.update(extra)
    meta.write_text(json.dumps(conteudo), encoding="utf-8")
    return str(pth), str(meta)


def test_par_coerente_carrega_sem_ressalva(tmp_path):
    pth, meta = _par(tmp_path)
    p = NeuralPredictor(pth, meta)
    assert p.load()
    assert p.erro == "" and p.aviso == ""


def test_par_trocado_e_recusado(tmp_path):
    """O ponto do item: mesma contagem de classes, pesos de outra rodada."""
    pth, meta = _par(tmp_path, modelo_sha256="0" * 64)
    p = NeuralPredictor(pth, meta)
    assert not p.load()
    assert not p.loaded
    assert "não é o modelo descrito" in p.erro


def test_a_recusa_diz_o_que_fazer(tmp_path):
    pth, meta = _par(tmp_path, modelo_sha256="0" * 64)
    p = NeuralPredictor(pth, meta)
    p.load()
    assert "Treinar Rede Neural" in p.erro


def test_metadado_antigo_ainda_carrega_com_aviso(tmp_path):
    """
    Recusar modelo anterior à F7.3 quebraria quem já tem um treinado. Ele
    funcionava antes; o que muda é passar a dizer que não dá para conferir.
    """
    pth, meta = _par(tmp_path)
    d = json.loads(open(meta, encoding="utf-8").read())
    del d["modelo_sha256"]
    d.pop("schema_version", None)
    open(meta, "w", encoding="utf-8").write(json.dumps(d))

    p = NeuralPredictor(pth, meta)
    assert p.load()
    assert "formato anterior" in p.aviso


def test_carga_repetida_limpa_o_recado_anterior(tmp_path):
    pth, meta = _par(tmp_path, modelo_sha256="0" * 64)
    p = NeuralPredictor(pth, meta)
    p.load()
    assert p.erro

    d = json.loads(open(meta, encoding="utf-8").read())
    d["modelo_sha256"] = impressao_do_modelo(pth)
    open(meta, "w", encoding="utf-8").write(json.dumps(d))

    assert p.load()
    assert p.erro == ""


def test_arquivo_ausente_nao_inventa_erro(tmp_path):
    p = NeuralPredictor(str(tmp_path / "x.pth"), str(tmp_path / "x.json"))
    assert not p.load()
    assert p.erro == ""


# ----------------------------------------------------------------------
# O que a interface diz
# ----------------------------------------------------------------------

def test_motivo_explica_o_par_trocado(tmp_path):
    from core.services.learning_service import LearningService

    pth, meta = _par(tmp_path, modelo_sha256="0" * 64)
    svc = LearningService(model_path=pth, meta_path=meta)
    assert not svc.load_predictor()
    assert "não é o modelo descrito" in svc.motivo_do_modelo()


def test_motivo_do_modelo_ausente_manda_treinar(tmp_path):
    from core.services.learning_service import LearningService

    svc = LearningService(model_path=str(tmp_path / "nao_existe.pth"),
                          meta_path=str(tmp_path / "nao_existe.json"))
    svc.load_predictor()
    assert "não existe" in svc.motivo_do_modelo()
    assert "Treinar Rede Neural" in svc.motivo_do_modelo()


def test_motivo_do_metadado_ausente_e_especifico(tmp_path):
    from core.services.learning_service import LearningService

    pth, meta = _par(tmp_path)
    os.remove(meta)
    svc = LearningService(model_path=pth, meta_path=meta)
    svc.load_predictor()
    motivo = svc.motivo_do_modelo()
    assert "traduz a saída do modelo" in motivo


# ----------------------------------------------------------------------
# O modelo que está no repositório
# ----------------------------------------------------------------------

def test_o_treino_grava_os_campos_novos():
    """Guarda contra alguém tirar os campos do `gravar_modelo`."""
    import inspect
    from core import neural_trainer

    fonte = inspect.getsource(neural_trainer.NeuralTrainer.train)
    for campo in ("schema_version", "modelo_sha256", "classes_sha256",
                  "treinado_em"):
        assert campo in fonte, f"o treino deixou de gravar {campo}"


def test_o_modelo_do_repositorio_carrega():
    """Se houver um par local, ele tem de continuar utilizável."""
    pth = os.path.join(RAIZ, "custom_model.pth")
    meta = os.path.join(RAIZ, "model_meta.json")
    if not (os.path.exists(pth) and os.path.exists(meta)):
        pytest.skip("sem modelo treinado nesta máquina")

    p = NeuralPredictor(pth, meta)
    assert p.load(), f"o modelo local deixou de carregar: {p.erro}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ----------------------------------------------------------------------
# F26 — o modelo sem calibração deixa de ser calado
# ----------------------------------------------------------------------

def test_modelo_sem_calibracao_carrega_com_ressalva(tmp_path):
    """
    `temperatura: 1.0` é o que todo treino grava, e a escala de confiança dele
    é a não calibrada. Carregar está certo; ficar calado não estava — o modelo
    de 14/08 rodou um dia assim, e só apareceu porque a F25 media outra coisa.
    """
    pth, meta = _par(tmp_path, temperatura=1.0)
    p = NeuralPredictor(pth, meta)
    assert p.load()
    assert p.loaded
    assert "sem calibração" in p.aviso


def test_a_ressalva_diz_o_comando(tmp_path):
    """Aviso que não diz o que fazer é ruído; o remédio é uma linha só."""
    pth, meta = _par(tmp_path, temperatura=1.0)
    p = NeuralPredictor(pth, meta)
    p.load()
    assert "calibrar_modelo.py --gravar" in p.aviso


def test_metadado_sem_o_campo_conta_como_sem_calibracao(tmp_path):
    """Anterior à F1.9: sem campo, a temperatura efetiva é 1,0 do mesmo jeito."""
    pth, meta = _par(tmp_path)
    d = json.loads(open(meta, encoding="utf-8").read())
    del d["temperatura"]
    open(meta, "w", encoding="utf-8").write(json.dumps(d))

    p = NeuralPredictor(pth, meta)
    assert p.load()
    assert "sem calibração" in p.aviso


def test_as_duas_ressalvas_cabem_juntas(tmp_path):
    """
    Formato antigo **e** sem calibração são independentes, e um metadado
    anterior à F7.3 costuma ser os dois. A segunda não pode apagar a primeira.
    """
    pth, meta = _par(tmp_path, temperatura=1.0)
    d = json.loads(open(meta, encoding="utf-8").read())
    del d["modelo_sha256"]
    d.pop("schema_version", None)
    open(meta, "w", encoding="utf-8").write(json.dumps(d))

    p = NeuralPredictor(pth, meta)
    assert p.load()
    assert "formato anterior" in p.aviso
    assert "sem calibração" in p.aviso


def test_modelo_calibrado_nao_reclama(tmp_path):
    pth, meta = _par(tmp_path, temperatura=2.1682)
    p = NeuralPredictor(pth, meta)
    assert p.load()
    assert p.aviso == ""


def test_o_servico_expoe_a_ressalva_de_quem_carregou(tmp_path):
    """
    O canal de aviso existia desde a F7.3 e **não tinha leitor**: só o `erro`
    era consultado, e só quando a carga falhava. Um aviso que ninguém lê é o
    mesmo que não avisar.
    """
    from core.services.learning_service import LearningService

    pth, meta = _par(tmp_path, temperatura=1.0)
    svc = LearningService(model_path=pth, meta_path=meta)
    assert "sem calibração" in svc.aviso_do_modelo()


def test_o_servico_cala_quando_o_modelo_esta_calibrado(tmp_path):
    from core.services.learning_service import LearningService

    pth, meta = _par(tmp_path, temperatura=2.1682)
    svc = LearningService(model_path=pth, meta_path=meta)
    assert svc.aviso_do_modelo() == ""


def _janela():
    """A janela real, ou `None` sem display. Ver `conftest.raiz_tk`."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    from conftest import raiz_tk
    from ui.main_window import MainWindow

    raiz = raiz_tk()
    if raiz is None:
        return None, None
    return raiz, MainWindow(raiz)


def test_a_ressalva_aparece_uma_vez_por_sessao(monkeypatch):
    """
    Uma vez porque a ressalva é sobre o **arquivo**, não sobre a ação. Repetida
    a cada preenchimento, ela treina o usuário a fechá-la sem ler — que é o
    mesmo que não avisar, com mais atrito.
    """
    from tkinter import messagebox

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")

    mostradas = []
    monkeypatch.setattr(messagebox, "showwarning",
                        lambda t, m, **k: mostradas.append(m))
    monkeypatch.setattr(win.learning_service, "aviso_do_modelo",
                        lambda: "sem calibração: rode o comando")

    win._avisar_do_modelo()
    win._avisar_do_modelo()
    win._avisar_do_modelo()

    assert len(mostradas) == 1
    assert "sem calibração" in mostradas[0]
    raiz.destroy()


def test_modelo_sem_ressalva_nao_interrompe(monkeypatch):
    from tkinter import messagebox

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")

    mostradas = []
    monkeypatch.setattr(messagebox, "showwarning",
                        lambda t, m, **k: mostradas.append(m))
    monkeypatch.setattr(win.learning_service, "aviso_do_modelo", lambda: "")

    win._avisar_do_modelo()
    assert mostradas == []
    raiz.destroy()


def test_treinar_de_novo_volta_a_avisar(monkeypatch):
    """
    O treino grava temperatura neutra outra vez, então a ressalva vale de novo
    — e é de **outro arquivo** que a que o usuário já fechou.
    """
    from tkinter import messagebox

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")

    mostradas = []
    monkeypatch.setattr(messagebox, "showwarning",
                        lambda t, m, **k: mostradas.append(m))
    monkeypatch.setattr(win.learning_service, "aviso_do_modelo",
                        lambda: "sem calibração")

    win._avisar_do_modelo()
    win._modelo_avisado = False          # o que `concluir` do treino faz
    win._avisar_do_modelo()

    assert len(mostradas) == 2
    raiz.destroy()
