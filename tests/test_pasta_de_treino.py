"""A base de treino e os recursos saem da raiz do projeto, nunca do cwd (RG-02a, R-43).

`LearningService()`, `CharacterLearner()`, o treino da rede, a promoção de recortes e a
importação de imagens usavam `"training_data"` solto, resolvido no cwd — e a
`MainWindow` constrói o serviço com esse padrão. Aberto por atalho, com o cwd noutra
pasta, o k-NN e o treino liam e gravavam a base de 630 mil PNGs no lugar errado. E
`config.paths._raizes_de_recursos` punha o cwd na frente do projeto: um
`custom_model.pth` ou um `core/dados/*.pth` largado no cwd passava a ser o peso da
leitura.

A base vem de `config.paths.pasta_de_treino()`: a `PYBOXEDITOR_TRAINING_DIR`, se houver
(a suíte a fixa numa pasta temporária no `conftest`, para nunca tocar a base real);
numa árvore do projeto, a `training_data/` ao lado do código; instalada por wheel, onde
o projeto mora no `site-packages` e não se grava, a pasta de dados do usuário.
"""

import os
from pathlib import Path

import pytest

from config import paths


@pytest.fixture
def projeto(tmp_path, monkeypatch):
    """A raiz do projeto numa pasta, o cwd noutra — como no atalho."""
    raiz = tmp_path / "projeto"
    raiz.mkdir()
    (raiz / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    atalho = tmp_path / "atalho"
    atalho.mkdir()
    monkeypatch.setattr(paths, "projeto_dir", lambda: raiz)
    monkeypatch.chdir(atalho)
    monkeypatch.delenv("PYBOXEDITOR_TRAINING_DIR", raising=False)
    return raiz


def test_a_suite_nao_aponta_a_base_real():
    base = Path(os.environ["PYBOXEDITOR_TRAINING_DIR"]).resolve()
    real = (Path(__file__).resolve().parent.parent / "training_data").resolve()
    assert base != real
    assert paths.pasta_de_treino() == base


def test_a_base_e_a_do_projeto_mesmo_com_uma_no_cwd(projeto):
    (Path.cwd() / "training_data").mkdir()
    assert paths.pasta_de_treino() == projeto / "training_data"


def test_a_variavel_de_ambiente_manda(projeto, tmp_path, monkeypatch):
    outra = tmp_path / "base"
    monkeypatch.setenv("PYBOXEDITOR_TRAINING_DIR", str(outra))
    assert paths.pasta_de_treino() == outra


def test_instalado_a_base_fica_na_pasta_de_dados(projeto, tmp_path, monkeypatch):
    (projeto / "pyproject.toml").unlink()          # o que o wheel deixa no site-packages
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path / "dados")
    assert paths.pasta_de_treino() == tmp_path / "dados" / "training_data"


def test_os_padroes_usam_a_base_do_projeto(projeto, tmp_path):
    from core import coleta, learner
    from core.services.learning_service import LearningService

    esperado = str(projeto / "training_data")
    assert LearningService().data_dir == esperado
    assert learner.CharacterLearner(usar_cache=False).data_dir == esperado
    vazia = tmp_path / "revisao"
    vazia.mkdir()
    coleta.promover(str(vazia))
    assert not (Path.cwd() / "training_data").exists(), "a promoção criou a base no cwd"


def test_o_treino_da_rede_usa_a_base_e_o_peso_do_projeto(projeto):
    from core import neural_trainer

    (projeto / "custom_model.pth").write_bytes(b"")
    (projeto / "model_meta.json").write_text("{}", encoding="utf-8")
    treino = neural_trainer.NeuralTrainer()
    assert (treino.data_dir, treino.model_path, treino.meta_path) == (
        str(projeto / "training_data"), str(projeto / "custom_model.pth"),
        str(projeto / "model_meta.json"))
    assert neural_trainer.CharDataset.__init__.__defaults__[0] is None
    predicao = neural_trainer.NeuralPredictor.__new__(neural_trainer.NeuralPredictor)
    assert neural_trainer.NeuralPredictor.__init__.__defaults__ == (None, None)
    del predicao


def test_a_importacao_de_imagens_vai_para_a_base_do_projeto(projeto, tmp_path):
    from PIL import Image

    from core.services.learning_service import LearningService

    origem = tmp_path / "origem" / "lower_a"
    origem.mkdir(parents=True)
    Image.new("L", (20, 20), 0).save(origem / "x.png")
    LearningService.import_character_images(str(origem.parent))
    assert (projeto / "training_data").is_dir()
    assert not (Path.cwd() / "training_data").exists()


def test_peso_no_cwd_nao_sombreia_o_do_projeto(projeto):
    (projeto / "custom_model.pth").write_bytes(b"do projeto")
    (Path.cwd() / "custom_model.pth").write_bytes(b"largado no cwd")
    (Path.cwd() / "core" / "dados").mkdir(parents=True)
    (Path.cwd() / "core" / "dados" / "diagrama_modelo.pth").write_bytes(b"largado")
    pesos = paths.caminhos_dos_pesos()
    assert pesos["glifos"] == projeto / "custom_model.pth"
    assert pesos["diagrama"] == projeto / "core" / "dados" / "diagrama_modelo.pth"


def test_o_dado_do_projeto_nao_vem_do_cwd(projeto):
    (Path.cwd() / "training_data_linhas").mkdir()
    assert paths.dado_do_projeto("training_data_linhas") == projeto / "training_data_linhas"
