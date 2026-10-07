import numpy as np
import pytest


def test_predictor_detalhado_retorna_confianca_por_caractere():
    pytest.importorskip("torch")
    from core.linha_trainer import LinhaPredictor

    # O teste só verifica o contrato e o intervalo; pesos reais são opcionais
    # e não devem ser exigidos pela suíte unitária. Procurados onde o
    # `LinhaPredictor()` os procura (`config.paths`), e não no cwd.
    from config.paths import caminhos_modelo_linha
    if not all(caminho.exists() for caminho in caminhos_modelo_linha()):
        pytest.skip("pesos locais não disponíveis")
    predictor = LinhaPredictor()
    texto, confiancas = predictor.predict_detalhado(
        np.full((40, 120), 255, dtype=np.uint8))
    assert len(texto) == len(confiancas)
    assert all(0.0 <= valor <= 1.0 for valor in confiancas)
