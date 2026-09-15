import cv2
import numpy as np
import pytest

from core import preprocess
from core.ocr_result import OCRTrace


def _pagina():
    img = np.full((160, 320), 245, np.uint8)
    cv2.putText(img, "OCR texto", (15, 75), cv2.FONT_HERSHEY_SIMPLEX,
                1.2, 30, 2, cv2.LINE_AA)
    return img


def test_config_rejeita_dpi_e_metodo_invalidos():
    with pytest.raises(ValueError):
        preprocess.PreprocessConfig(target_dpi=0)
    with pytest.raises(ValueError):
        preprocess.PreprocessConfig(methods=("inexistente",))


def test_normalizar_iluminacao_devolve_gray_uint8():
    img = _pagina().astype(np.float32)
    img *= np.linspace(0.55, 1.0, img.shape[1], dtype=np.float32)
    corrigida = preprocess.normalizar_iluminacao(img.astype(np.uint8))
    assert corrigida.ndim == 2
    assert corrigida.dtype == np.uint8
    assert corrigida.shape == img.shape


def test_perspectiva_sem_pontos_e_com_quatro_pontos():
    img = _pagina()
    assert preprocess.corrigir_perspectiva(img) is img
    pontos = ((5, 5), (314, 8), (317, 154), (3, 150))
    retificada = preprocess.corrigir_perspectiva(img, pontos)
    assert retificada.ndim == 2
    assert retificada.shape[0] > 2 and retificada.shape[1] > 2
    with pytest.raises(ValueError):
        preprocess.corrigir_perspectiva(img, ((0, 0), (1, 1)))


def test_gerar_variantes_produz_metadados_e_nao_muta_entrada():
    img = _pagina()
    antes = img.copy()
    variantes = preprocess.gerar_variantes(
        img, preprocess.PreprocessConfig(methods=("otsu", "adaptive")))
    assert len(variantes) == 4
    assert {item.method for item in variantes} == {"otsu", "adaptive"}
    assert all(item.evidence is not None for item in variantes)
    assert all(item.binary.ndim == 2 for item in variantes)
    assert np.array_equal(img, antes)


def test_selecionar_variante_e_pipeline_adaptativo():
    variantes = [
        preprocess.ImageVariant("a", np.zeros((2, 2), np.uint8),
                                np.zeros((2, 2), np.uint8), score=0.2),
        preprocess.ImageVariant("b", np.zeros((2, 2), np.uint8),
                                np.zeros((2, 2), np.uint8), score=0.8),
    ]
    assert preprocess.selecionar_variante(variantes).name == "b"
    with pytest.raises(ValueError):
        preprocess.selecionar_variante([])
    escolhida = preprocess.preparar_adaptativo(_pagina())
    assert isinstance(escolhida, preprocess.ImageVariant)
    assert escolhida.evidence is not None


def test_pipeline_adaptativo_registra_variantes_no_trace(tmp_path):
    trace = OCRTrace(tmp_path)
    escolhida = preprocess.preparar_adaptativo(_pagina(), trace=trace)
    caminho = trace.close()
    assert escolhida.name
    assert caminho is not None
    eventos = [item["name"] for item in trace.events]
    assert eventos[0] == "preprocess_start"
    assert "variant" in eventos
    assert "variant_selected" in eventos
    assert list((tmp_path / "variants").glob("*.png"))
