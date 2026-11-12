"""PD-23: o peso novo só fica no lugar do anterior se não ler pior o corpus.

A medida de verdade (`medir_par`, o leitor inteiro sobre os PDFs do corpus) não
roda aqui: os PDFs não são versionados e ela leva minutos. O que se prende é a
decisão — que par fica onde, com que nome — com medidas fabricadas, e a ligação
com o treino.
"""

import datetime
import json

import pytest

from core import portao_do_modelo as portao

DIA = datetime.date(2026, 11, 12)


def _par(pasta, nome, conteudo):
    pth = pasta / f"{nome}.pth"
    meta = pasta / ("model_meta.json" if nome == "custom_model" else f"{nome}.json")
    pth.write_bytes(conteudo)
    meta.write_text(json.dumps({"de": conteudo.decode()}), encoding="utf-8")
    return pth, meta


def _medida(pid, erros, caracteres=1000):
    contas = {"caracteres": caracteres, "erros_de_caractere": erros,
              "tokens": 100, "erros": 0, "cer": erros / caracteres, "wer": 0.0}
    return {"id": pid, "metricas": {"prose": dict(contas), "notation": dict(contas),
                                    "total": dict(contas)}}


@pytest.fixture
def producao(tmp_path):
    pth, meta = _par(tmp_path, "custom_model", b"velho")
    manifesto = tmp_path / "corpus.json"
    manifesto.write_text("{}", encoding="utf-8")
    return tmp_path, pth, meta, manifesto


def _medidor(por_conteudo):
    """`medir` falso: devolve as medidas conforme os bytes do peso medido."""
    vistos = []

    def medir(model_path, _meta_path, _manifesto):
        conteudo = model_path.read_bytes()
        vistos.append(conteudo)
        return por_conteudo[conteudo]
    medir.vistos = vistos
    return medir


def test_guardar_anterior_copia_o_par_com_a_data_e_nao_pisa_em_outro(producao):
    pasta, pth, meta, _ = producao
    primeiro = portao.guardar_anterior(pth, meta, quando=DIA)
    segundo = portao.guardar_anterior(pth, meta, quando=DIA)

    assert primeiro == (pasta / "custom_model_2026-11-12_antes_do_retreino.pth",
                        pasta / "model_meta_2026-11-12_antes_do_retreino.json")
    assert segundo[0].name == "custom_model_2026-11-12_antes_do_retreino_2.pth"
    assert primeiro[0].read_bytes() == b"velho"
    assert pth.read_bytes() == b"velho"           # copiado, não movido


def test_guardar_anterior_sem_modelo_de_producao_nao_guarda_nada(tmp_path):
    assert portao.guardar_anterior(tmp_path / "custom_model.pth",
                                   tmp_path / "model_meta.json") is None


def test_peso_que_le_pior_e_recusado_e_o_anterior_volta(producao):
    pasta, pth, meta, manifesto = producao
    anterior = portao.guardar_anterior(pth, meta, quando=DIA)
    _par(pasta, "custom_model", b"novo")          # o treino gravou por cima
    medir = _medidor({b"velho": [_medida("p1", 10), _medida("p2", 10)],
                      b"novo": [_medida("p1", 10), _medida("p2", 25)]})

    v = portao.avaliar(pth, meta, anterior, manifesto=manifesto, medir=medir, quando=DIA)

    assert v.situacao == portao.RECUSADO
    assert medir.vistos == [b"velho", b"novo"]
    assert pth.read_bytes() == b"velho"
    assert json.loads(meta.read_text(encoding="utf-8")) == {"de": "velho"}
    assert v.recusado == pasta / "custom_model_2026-11-12_recusado.pth"
    assert v.recusado.read_bytes() == b"novo"
    assert json.loads((pasta / "model_meta_2026-11-12_recusado.json")
                      .read_text(encoding="utf-8")) == {"de": "novo"}
    assert any(p.startswith("p2:") for p in v.pioras)
    assert "RECUSADO" in v.mensagem() and "custom_model_2026-11-12_recusado.pth" in v.mensagem()


def test_peso_que_nao_le_pior_fica(producao):
    pasta, pth, meta, manifesto = producao
    anterior = portao.guardar_anterior(pth, meta, quando=DIA)
    _par(pasta, "custom_model", b"novo")
    medir = _medidor({b"velho": [_medida("p1", 10)], b"novo": [_medida("p1", 8)]})

    v = portao.avaliar(pth, meta, anterior, manifesto=manifesto, medir=medir)

    assert v.situacao == portao.PROMOVIDO
    assert pth.read_bytes() == b"novo"
    assert v.recusado is None and v.pioras == []
    assert "1.00% → 0.80%" in v.mensagem()


def test_dentro_da_tolerancia_por_pagina_mas_o_corpus_inteiro_piora(producao):
    # Cada página sobe 0,09 ponto (abaixo do 0,1 da rodada), mas são muitas.
    antes = [_medida(f"p{i}", 100, 10000) for i in range(3)]
    depois = [_medida(f"p{i}", 109, 10000) for i in range(3)]
    assert portao.comparar(antes, depois) == []
    depois[0] = _medida("p0", 140, 10000)
    assert portao.comparar(antes, depois) != []


@pytest.mark.parametrize("medidas_novas, motivo", [
    ([{"id": "p1", "metricas": None, "erro": "PDF ausente: x.pdf"}], "PDF ausente"),
    ([], "não tem página"),
])
def test_corpus_que_nao_se_mede_deixa_o_novo_sem_medida(producao, medidas_novas, motivo):
    pasta, pth, meta, manifesto = producao
    anterior = portao.guardar_anterior(pth, meta, quando=DIA)
    _par(pasta, "custom_model", b"novo")
    medir = _medidor({b"velho": medidas_novas, b"novo": medidas_novas})

    v = portao.avaliar(pth, meta, anterior, manifesto=manifesto, medir=medir)

    assert v.situacao == portao.SEM_MEDIDA and motivo in v.motivo
    assert pth.read_bytes() == b"novo"


def test_sem_manifesto_sem_anterior_ou_medida_quebrada_nao_recusa(producao):
    pasta, pth, meta, manifesto = producao
    anterior = portao.guardar_anterior(pth, meta, quando=DIA)

    def quebra(*_a):
        raise RuntimeError("Tesseract ausente")

    assert portao.avaliar(pth, meta, None, manifesto=manifesto).situacao == portao.SEM_MEDIDA
    assert portao.avaliar(pth, meta, anterior,
                          manifesto=pasta / "nao_ha.json").situacao == portao.SEM_MEDIDA
    v = portao.avaliar(pth, meta, anterior, manifesto=manifesto, medir=quebra)
    assert v.situacao == portao.SEM_MEDIDA and "Tesseract ausente" in v.motivo
    assert pth.read_bytes() == b"velho"


def test_o_treino_com_portao_guarda_antes_e_avalia_depois(tmp_path, monkeypatch):
    from core.services.learning_service import LearningService

    dados = tmp_path / "dados"
    (dados / "lower_a").mkdir(parents=True)
    pth, meta = _par(tmp_path, "custom_model", b"velho")
    chamadas = []

    class Treino:
        def __init__(self, _dados, model_path, meta_path):
            self.model_path = model_path

        def train(self, **_kw):
            # o par anterior já tem de estar guardado quando o treino escreve
            chamadas.append(sorted(p.name for p in tmp_path.glob("*_antes_do_retreino*")))
            with open(self.model_path, "wb") as f:
                f.write(b"novo")
            return True

    def avaliar(model_path, meta_path, anterior, callback=None):
        chamadas.append(anterior)
        return portao.Veredito(portao.PROMOVIDO)

    monkeypatch.setattr("core.neural_trainer.NeuralTrainer", Treino)
    monkeypatch.setattr(portao, "avaliar", avaliar)
    servico = LearningService(str(dados), str(pth), str(meta))
    linhas = []

    assert servico.train_neural(validar=False, portao=True, callback=linhas.append)
    hoje = datetime.date.today().isoformat()
    assert chamadas[0] == [f"custom_model_{hoje}_antes_do_retreino.pth",
                           f"model_meta_{hoje}_antes_do_retreino.json"]
    assert chamadas[1][0].read_bytes() == b"velho"
    assert servico.ultimo_veredito.situacao == portao.PROMOVIDO
    assert any("passou no corpus" in linha for linha in linhas)


def test_o_treino_sem_portao_nao_guarda_nem_mede(tmp_path, monkeypatch):
    from core.services.learning_service import LearningService

    dados = tmp_path / "dados"
    (dados / "lower_a").mkdir(parents=True)
    pth, meta = _par(tmp_path, "custom_model", b"velho")

    class Treino:
        def __init__(self, *_a):
            pass

        def train(self, **_kw):
            return True

    monkeypatch.setattr("core.neural_trainer.NeuralTrainer", Treino)
    monkeypatch.setattr(portao, "avaliar", lambda *a, **k: pytest.fail("mediu"))
    servico = LearningService(str(dados), str(pth), str(meta))

    assert servico.train_neural(validar=False)
    assert servico.ultimo_veredito is None
    assert list(tmp_path.glob("*_antes_do_retreino*")) == []
