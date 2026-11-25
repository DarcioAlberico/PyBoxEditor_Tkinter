"""A limpeza da trama por tabela de consulta (RG-16, R-24): a mesma máscara do laço que
comparava a página com cada componente, byte a byte, sem pagar a página por componente."""

import cv2
import numpy as np

from core.services.ocr_service import AREA_DO_COMPONENTE_DA_TRAMA, _sem_miudezas


def _pelo_laco(mascara, labels, stats, n):
    """O código de antes da RG-16, como referência."""
    limpa = np.zeros_like(mascara)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 8:
            limpa[labels == i] = 255
    return limpa


def test_a_tabela_da_a_mesma_mascara_do_laco():
    sorteio = np.random.default_rng(7)
    for densidade in (0.05, 0.2, 0.45):
        mascara = np.where(sorteio.random((160, 220)) < densidade, 255, 0).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mascara, connectivity=8)
        nova = _sem_miudezas(labels, stats, AREA_DO_COMPONENTE_DA_TRAMA)
        velha = _pelo_laco(mascara, labels, stats, n)
        assert nova.dtype == velha.dtype and nova.tobytes() == velha.tobytes()


def test_a_mascara_sem_componente_nenhum():
    mascara = np.zeros((10, 10), np.uint8)
    _n, labels, stats, _ = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    assert not _sem_miudezas(labels, stats, 8).any()


def test_a_borda_da_area():
    mascara = np.zeros((20, 40), np.uint8)
    mascara[2, 2:9] = 255            # 7 pixels: sai
    mascara[10, 2:10] = 255          # 8 pixels: fica
    _n, labels, stats, _ = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    limpa = _sem_miudezas(labels, stats, AREA_DO_COMPONENTE_DA_TRAMA)
    assert not limpa[2].any() and limpa[10, 2:10].all()


def test_a_trama_nao_paga_a_pagina_por_componente(monkeypatch):
    """Nenhuma comparação da página com um rótulo: é o que custava 146 s em 24 mil componentes."""
    class Contada(np.ndarray):
        comparacoes = 0

        def __eq__(self, outro):
            Contada.comparacoes += 1
            return super().__eq__(outro)

    labels = np.arange(400 * 400, dtype=np.int32).reshape(400, 400) // 8
    stats = np.full((int(labels.max()) + 1, 5), 8, np.int32)
    _sem_miudezas(labels.view(Contada), stats, 8)
    assert Contada.comparacoes == 0
