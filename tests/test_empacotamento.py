"""Contrato barato dos recursos usados pelo bundle desktop."""

from pathlib import Path

from scripts.verificar_empacotamento import RECURSOS_OBRIGATORIOS, verificar_raiz


RAIZ = Path(__file__).resolve().parent.parent


def test_recursos_do_bundle_estao_presentes():
    assert verificar_raiz(RAIZ) == []


def test_spec_preserva_as_arvores_de_recursos_e_nao_embute_pesos_grandes():
    spec = (RAIZ / "pyboxeditor.spec").read_text(encoding="utf-8")
    for diretorio in ("assets", "core/dados", "fonts", "pieces"):
        assert f'_data("{diretorio}")' in spec
    assert "custom_model.pth" not in spec
    assert "exclude_binaries=True" in spec
    assert "COLLECT(" in spec
    assert "PyInstaller" in spec


def test_verificador_detecta_recurso_ausente(tmp_path):
    ausentes = verificar_raiz(tmp_path)
    assert set(ausentes) == set(RECURSOS_OBRIGATORIOS)
