"""Orquestração do treino e preparação do pacote OCR do projeto.

As linhas corrigidas treinam o CRNN/CTC local. EasyOCR, PaddleOCR e Tesseract
são engines externos pré-treinados: o pacote registra sua disponibilidade e
prepara seus pesos, mas não afirma que um ``rec_gt.txt`` os retreinou.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from core.ocr_language import LanguageModel, TERMOS_XADREZ


@dataclass
class EngineTrainingStatus:
    name: str
    available: bool
    prepared: bool = False
    mode: str = "pretrained"
    message: str = ""


@dataclass
class OCRTrainingSummary:
    line_model: bool
    language_model: str
    engines: list[EngineTrainingStatus]
    state_path: str
    weight_manifest: str = ""
    dataset_version: str = ""

    def to_dict(self) -> dict:
        return {"line_model": self.line_model,
                "language_model": self.language_model,
                "engines": [asdict(item) for item in self.engines],
                "state_path": self.state_path,
                # A proveniência do pacote: qual manifesto de pesos e qual
                # versão de dataset o geraram. Ficavam fora do dicionário, e o
                # estado gravado não dizia de onde o modelo tinha vindo.
                "weight_manifest": self.weight_manifest,
                "dataset_version": self.dataset_version}


def _textos_dataset(pasta: str | Path) -> list[str]:
    from core.linha_trainer import _ler_manifesto
    return [texto for _caminho, texto in _ler_manifesto(pasta)]


def construir_modelo_linguagem(pastas: tuple[str | Path, ...] =
                               ("training_data_linhas",),
                               destino: str | Path = "ocr_language_model.json") -> Path:
    """Atualiza o léxico estatístico com todas as transcrições confirmadas."""
    textos = []
    for pasta in pastas:
        try:
            textos.extend(_textos_dataset(pasta))
        except (FileNotFoundError, ValueError):
            continue
    if not textos:
        raise ValueError("Nenhuma transcrição de linha disponível para o léxico.")
    modelo = LanguageModel.from_texts(textos, idioma="multi", dominio=TERMOS_XADREZ)
    caminho = Path(destino)
    modelo.save_json(caminho)
    return caminho


def _status_engine(nome: str, modulo: str, *, mode: str = "pretrained") -> EngineTrainingStatus:
    disponivel = importlib.util.find_spec(modulo) is not None
    return EngineTrainingStatus(nome, disponivel, False, mode,
                                "instalado" if disponivel else "não instalado")


def preparar_engines(service=None, *, preparar_pesos: bool = True,
                     callback: Callable[[str], None] | None = None) -> list[EngineTrainingStatus]:
    """Verifica engines e, quando possível, baixa/carrega pesos auxiliares."""
    estados = [
        _status_engine("Tesseract", "pytesseract"),
        _status_engine("EasyOCR", "easyocr"),
        _status_engine("PaddleOCR", "paddleocr"),
    ]
    if shutil.which("tesseract"):
        estados[0].available = True
    if preparar_pesos and service is not None and estados[1].available:
        try:
            if callback:
                callback("Preparando pesos EasyOCR en + pt...")
            service.preparar_easyocr(("en", "pt"))
            estados[1].prepared = True
            estados[1].message = "pesos en + pt preparados"
        except Exception as erro:
            estados[1].message = f"falha ao preparar pesos: {erro}"
    if preparar_pesos and service is not None and estados[2].available:
        preparar_paddle = getattr(service, "preparar_paddleocr", None)
        if preparar_paddle is not None:
            try:
                if callback:
                    callback("Preparando pesos PaddleOCR en + pt...")
                preparar_paddle(("en", "pt"))
                estados[2].prepared = True
                estados[2].message = "pesos en + pt preparados"
            except Exception as erro:
                estados[2].message = f"falha ao preparar pesos: {erro}"
    # Tesseract e PaddleOCR carregam seus dados pelo próprio sistema/API; não
    # há fine-tuning seguro deles dentro do treinador CRNN deste projeto.
    return estados


def salvar_estado(summary: OCRTrainingSummary, caminho: str | Path =
                  "ocr_training_state.json") -> Path:
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    dados = summary.to_dict()
    dados["gerado_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    return destino


def treinar_pacote(*, pasta: str = "training_data_linhas",
                   validacao: str | None = None,
                   destino: str = "text_line_model.pth",
                   meta: str = "text_line_model.json",
                   epocas: int = 20, batch_size: int = 8,
                   paciencia: int = 6, callback=None,
                   should_stop=None, preparar_pesos: bool = True,
                   service=None, dataset_version: str = "",
                   manifest_path: str | Path | None = None) -> OCRTrainingSummary:
    """Treina o modelo local e atualiza o pacote usado pelo botão Executar."""
    from core.linha_trainer import treinar
    ok = treinar(pasta=pasta, validacao=validacao, destino=destino, meta=meta,
                 epocas=epocas, batch_size=batch_size, paciencia=paciencia,
                 callback=callback, should_stop=should_stop)
    if not ok:
        raise RuntimeError("Treinamento cancelado antes de gerar um modelo novo.")
    caminho_lexico = construir_modelo_linguagem((pasta, *(tuple([validacao])
                                                           if validacao else ())))
    estados = preparar_engines(service, callback=callback,
                               preparar_pesos=preparar_pesos)
    caminho_manifesto = ""
    if Path(destino).is_file():
        from core.ocr_phase7 import WeightManifest
        manifesto = WeightManifest.from_file(
            destino, model_id="text-line-crnn", pipeline_version="editorial-pipeline/v4",
            config={"dataset": str(pasta), "batch_size": batch_size,
                    "epochs": epocas, "patience": paciencia},
        )
        alvo = Path(manifest_path) if manifest_path else Path(destino).with_suffix(".manifest.json")
        manifesto.save(alvo)
        caminho_manifesto = str(alvo)
    # O estado vai para o lado do modelo, e não para o diretório de trabalho:
    # `salvar_estado(resumo)` sem caminho gravava `ocr_training_state.json`
    # onde quer que o processo tivesse sido aberto.
    estado = Path(destino).with_name("ocr_training_state.json")
    resumo = OCRTrainingSummary(True, str(caminho_lexico), estados,
                                str(estado), caminho_manifesto,
                                str(dataset_version))
    salvar_estado(resumo, estado)
    return resumo
