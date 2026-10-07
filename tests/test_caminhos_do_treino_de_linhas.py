"""
O treino de linhas não depende mais do cwd (item 9 da `docs/REVISAO_MODOS_OCR.md`).

A base rotulada, a sintética, o relatório, a avaliação, o léxico e o modelo eram
nomes soltos (`Path("training_data_linhas")`, `"text_line_model.pth"`), e o app
aberto por atalho — cujo cwd não é a raiz — rotulava linhas numa pasta, treinava
de outra e abria um relatório que não era o do treino. Agora todos saem de
`config.paths`, com a regra de `caminhos_modelo_linha`: vale o que existe no
cwd, e senão a raiz do projeto. Os testes trocam a raiz por uma pasta
temporária e abrem o "atalho" noutra.
"""

import os
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from config import paths


@pytest.fixture
def projeto(tmp_path, monkeypatch):
    """A raiz do projeto numa pasta, o cwd noutra — como no atalho."""
    raiz = tmp_path / "projeto"
    raiz.mkdir()
    atalho = tmp_path / "atalho"
    atalho.mkdir()
    monkeypatch.setattr(paths, "projeto_dir", lambda: raiz)
    monkeypatch.chdir(atalho)
    return raiz


def _base_de_linhas(pasta, texto="1.e4 e5 2.♘f3"):
    (pasta / "images").mkdir(parents=True)
    Image.new("L", (120, 32), 255).save(pasta / "images" / "p_linha_00001.png")
    (pasta / "rec_gt.txt").write_text(f"images/p_linha_00001.png\t{texto}\n",
                                      encoding="utf-8")


def test_sem_nada_no_cwd_tudo_vai_para_a_raiz_do_projeto(projeto):
    assert paths.pasta_de_linhas() == projeto / "training_data_linhas"
    assert paths.pasta_de_linhas_sinteticas() == projeto / "training_data_linhas_sintetico"
    assert paths.relatorio_de_linhas() == projeto / "text_line_training_report.txt"
    assert paths.relatorio_de_linhas(".json") == projeto / "text_line_training_report.json"
    assert paths.avaliacao_de_linhas() == projeto / "text_line_evaluation.json"
    assert paths.modelo_de_lingua() == projeto / "ocr_language_model.json"
    assert paths.completar_modelo_linha() == (projeto / "text_line_model.pth",
                                              projeto / "text_line_model.json")


def test_o_que_ja_existe_no_cwd_continua_valendo(projeto):
    local = os.path.join(os.getcwd(), "training_data_linhas")
    os.mkdir(local)
    assert str(paths.pasta_de_linhas()) == local
    # o caminho pedido manda, e só o que falta vem do padrão
    modelo, meta = paths.completar_modelo_linha("outro.pth")
    assert (str(modelo), meta) == ("outro.pth", projeto / "text_line_model.json")


def test_os_padroes_do_treino_leem_e_gravam_na_raiz(projeto):
    from core import linha_review, linha_sintetica, linha_trainer, ocr_training

    _base_de_linhas(projeto / "training_data_linhas")
    assert linha_trainer.validar_dataset()["linhas"] == 1
    assert [a.texto for a in linha_review.ler_manifesto()] == ["1.e4 e5 2.♘f3"]
    utilizavel, motivo = linha_trainer.modelo_utilizavel()
    assert utilizavel is False and "não há modelo" in motivo

    assert linha_trainer.salvar_avaliacao({"cer": 0.5}) == projeto / "text_line_evaluation.json"
    assert ocr_training.construir_modelo_linguagem() == projeto / "ocr_language_model.json"
    assert linha_sintetica.gerar(por_linha=1)["pasta"] == str(
        projeto / "training_data_linhas_sintetico")
    # e nada caiu no cwd
    assert os.listdir(os.getcwd()) == []


def test_o_registro_de_motores_le_o_modelo_de_config_paths(projeto):
    from core.ocr_engines import OCRServiceAdapters

    class _Servico:
        def linha_treinada_conf(self, imagem, modelo, meta):
            return "linha", 0.9

    registro = OCRServiceAdapters.registry(_Servico(), trained_line=True)
    treinado = next(a for a in registro.adapters if a.name == "trained_line")
    assert treinado.metadata["model_path"] == str(projeto / "text_line_model.pth")


def test_modelos_principais_sao_localizados_no_data_dir_do_wheel(tmp_path, monkeypatch):
    instalado = tmp_path / "venv" / "share" / "PyBoxEditor"
    instalado.mkdir(parents=True)
    (instalado / "custom_model.pth").write_bytes(b"weights")
    (instalado / "model_meta.json").write_text("{}", encoding="utf-8")
    codigo = tmp_path / "venv" / "Lib" / "site-packages"
    codigo.mkdir(parents=True)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.setattr(paths, "projeto_dir", lambda: codigo)
    monkeypatch.setattr(paths.sys, "prefix", str(tmp_path / "venv"))
    monkeypatch.chdir(cwd)

    modelo, meta = paths.caminhos_modelo_glifos()

    assert modelo == instalado / "custom_model.pth"
    assert meta == instalado / "model_meta.json"


def test_o_menu_abre_o_relatorio_que_o_treino_grava(projeto, monkeypatch):
    from ui import main_window

    relatorio = paths.relatorio_de_linhas()
    relatorio.write_text("Treinamento OCR sequencial\n", encoding="utf-8")
    abertos = []
    monkeypatch.setattr(os, "startfile", abertos.append, raising=False)
    main_window.MainWindow.abrir_relatorio_ocr_linhas(SimpleNamespace())
    assert abertos == [str(relatorio)]


def test_o_que_o_treino_grava_fica_ao_lado_do_modelo(projeto, tmp_path):
    """Relatório, avaliação e léxico acompanham o modelo — e não o cwd, nem a
    raiz, quando o modelo é outro."""
    outro = tmp_path / "experimento" / "m.pth"
    assert paths.relatorio_de_linhas(".json", outro) == outro.with_name(
        "text_line_training_report.json")
    assert paths.modelo_de_lingua(outro) == outro.with_name("ocr_language_model.json")
    assert paths.avaliacao_de_linhas(outro) == outro.with_name("text_line_evaluation.json")


def test_treinar_o_pacote_nao_escreve_fora_da_pasta_pedida(projeto, tmp_path):
    """Item 10 da revisão: o `treinar_pacote` com a base e o modelo numa pasta
    temporária escreve só nela — o relatório e o léxico iam para o cwd (e,
    depois do item 9, para a raiz do projeto)."""
    pytest.importorskip("torch")
    from PIL import ImageDraw

    from core.ocr_training import treinar_pacote

    repositorio = Path(paths.__file__).resolve().parents[1]
    raiz_do_repositorio = sorted(os.listdir(repositorio))
    base = tmp_path / "base"
    (base / "images").mkdir(parents=True)
    textos = ["1.e4 e5", "2.Nf3 Nc6", "3.Bb5 a6", "4.Ba4 Nf6"]
    for i, texto in enumerate(textos, 1):
        imagem = Image.new("L", (160, 32), 255)
        ImageDraw.Draw(imagem).text((4, 8), texto, fill=0)
        imagem.save(base / "images" / f"p_linha_{i:05d}.png")
    (base / "rec_gt.txt").write_text(
        "".join(f"images/p_linha_{i:05d}.png\t{t}\n" for i, t in enumerate(textos, 1)),
        encoding="utf-8")
    modelo = tmp_path / "modelo" / "m.pth"
    modelo.parent.mkdir()

    resumo = treinar_pacote(pasta=base, destino=modelo, meta=modelo.with_suffix(".json"),
                            epocas=1, batch_size=2, paciencia=1, preparar_pesos=False)

    assert resumo.line_model is True
    assert {p.name for p in modelo.parent.iterdir()} >= {
        "m.pth", "m.json", "text_line_training_report.txt",
        "text_line_training_report.json", "ocr_language_model.json",
        "ocr_training_state.json", "m.manifest.json"}
    assert resumo.language_model == str(modelo.with_name("ocr_language_model.json"))
    metadados = json.loads(modelo.with_suffix(".json").read_text(encoding="utf-8"))
    assert metadados["model_sha256"] == hashlib.sha256(modelo.read_bytes()).hexdigest()
    assert metadados["dataset_sha256"]
    assert metadados["validacao_registros"]
    assert os.listdir(os.getcwd()) == [], "o treino escreveu no cwd"
    assert list(projeto.iterdir()) == [], "o treino escreveu na raiz do projeto"
    assert sorted(os.listdir(repositorio)) == raiz_do_repositorio


def test_a_rotulagem_grava_as_linhas_na_base_do_treino(projeto):
    from ui.dialogo_rotulagem import DialogoRotulagem

    status = []
    janela = SimpleNamespace(
        _confirmadas={0}, _salvas=set(), _linhas=["linha"], _ocr={0: "1.e4 e5"},
        _caixa_linha=lambda linha: (0, 0, 40, 20),
        app=SimpleNamespace(current_pdf_page=0, image=Image.new("L", (100, 50), 255)),
        lbl_status=SimpleNamespace(config=lambda text: status.append(text)))
    DialogoRotulagem._salvar_dataset(janela)
    manifesto = projeto / "training_data_linhas" / "rec_gt.txt"
    assert manifesto.read_text(encoding="utf-8").strip().endswith("\t1.e4 e5")
    assert str(projeto / "training_data_linhas") in status[0]
    assert os.listdir(os.getcwd()) == []
