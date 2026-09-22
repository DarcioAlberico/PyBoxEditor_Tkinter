from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.ocr_benchmark import assinatura_manifesto, executar_manifesto


def _pagina(path: Path, text: str) -> None:
    path.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")


def test_assinatura_manifesto_muda_com_conteudo(tmp_path: Path):
    _pagina(tmp_path / "ref.json", "correto")
    _pagina(tmp_path / "pred.json", "errado")
    manifesto = tmp_path / "manifest.json"
    manifesto.write_text(json.dumps({"pages": [{"id": "p1", "reference": "ref.json",
                                                  "prediction": "pred.json"}]}),
                         encoding="utf-8")
    primeira = assinatura_manifesto(manifesto)
    _pagina(tmp_path / "pred.json", "corrigido")
    assert assinatura_manifesto(manifesto) != primeira


def test_assinatura_manifesto_rejeita_arquivo_ausente(tmp_path: Path):
    manifesto = tmp_path / "manifest.json"
    manifesto.write_text(json.dumps({"pages": [{"id": "p1", "reference": "nao.json",
                                                  "prediction": "tambem-nao.json"}]}),
                         encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        assinatura_manifesto(manifesto)


def test_relatorio_carrega_assinatura_e_configuracao(tmp_path: Path):
    _pagina(tmp_path / "ref.json", "correto")
    _pagina(tmp_path / "pred.json", "correto")
    manifesto = tmp_path / "manifest.json"
    manifesto.write_text(json.dumps({"pages": [{"id": "p1", "reference": "ref.json",
                                                  "prediction": "pred.json"}]}),
                         encoding="utf-8")
    relatorio = executar_manifesto(manifesto, ignorar_maiusculas=True)
    assert relatorio.metadata["corpus_sha256"] == assinatura_manifesto(manifesto)
    assert relatorio.metadata["ignore_case"] is True
