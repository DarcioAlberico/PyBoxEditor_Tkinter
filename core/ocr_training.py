"""Orquestração do treino e preparação do pacote OCR do projeto.

As linhas corrigidas treinam o CRNN/CTC local. EasyOCR, PaddleOCR e Tesseract
são engines externos pré-treinados: o pacote registra sua disponibilidade e
prepara seus pesos, mas não afirma que um ``rec_gt.txt`` os retreinou.
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from core.ocr_language import LanguageModel, TERMOS_XADREZ


CALIBRATION_SCHEMA = "pyboxeditor.ocr-line-calibration/v1"


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
    production_eligible: bool = False
    production_gate_reason: str = ""
    holdout_evaluated: bool = False
    holdout_cer: float | None = None
    holdout_before_cer: float | None = None
    holdout_improved: bool | None = None
    holdout_corpus_sha256: str = ""
    dataset_provenance_sha256: str = ""
    calibration_report: str = ""
    calibration_dataset_sha256: str = ""
    calibration_domains: tuple[str, ...] = ()
    split_manifest: str = ""
    split_manifest_sha256: str = ""
    line_binding: str = ""
    line_binding_sha256: str = ""

    def to_dict(self) -> dict:
        return {"line_model": self.line_model,
                "language_model": self.language_model,
                "engines": [asdict(item) for item in self.engines],
                "state_path": self.state_path,
                # A proveniência do pacote: qual manifesto de pesos e qual
                # versão de dataset o geraram. Ficavam fora do dicionário, e o
                # estado gravado não dizia de onde o modelo tinha vindo.
                "weight_manifest": self.weight_manifest,
                "dataset_version": self.dataset_version,
                "production_eligible": self.production_eligible,
                "production_gate_reason": self.production_gate_reason,
                "holdout_evaluated": self.holdout_evaluated,
                "holdout_cer": self.holdout_cer,
                "holdout_before_cer": self.holdout_before_cer,
                "holdout_improved": self.holdout_improved,
                "holdout_corpus_sha256": self.holdout_corpus_sha256,
                "dataset_provenance_sha256": self.dataset_provenance_sha256,
                "calibration_report": self.calibration_report,
                "calibration_dataset_sha256": self.calibration_dataset_sha256,
                "calibration_domains": list(self.calibration_domains),
                "split_manifest": self.split_manifest,
                "split_manifest_sha256": self.split_manifest_sha256,
                "line_binding": self.line_binding,
                "line_binding_sha256": self.line_binding_sha256}


def carregar_proveniencia_dataset(caminho: str | Path) -> dict[str, object]:
    """Valida e identifica o manifesto JSON usado como origem do treino."""
    alvo = Path(caminho).resolve()
    if not alvo.is_file():
        raise FileNotFoundError(f"proveniÃªncia do dataset ausente: {alvo}")
    try:
        dados = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ValueError(f"proveniÃªncia do dataset invÃ¡lida: {erro}") from erro
    if not isinstance(dados, Mapping):
        raise ValueError("proveniÃªncia do dataset deve ser um objeto JSON")
    metadata = dados.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    source = str(metadata.get("source", "unknown") or "unknown")
    review = metadata.get("review_provenance")
    verified = isinstance(review, Mapping) and review.get("verified") is True
    if source == "ocr14" and not verified:
        raise ValueError(
            "dataset OCR-14 sem proveniÃªncia de revisÃ£o verificada")
    digest = hashlib.sha256(alvo.read_bytes()).hexdigest()
    return {
        "verified": verified,
        "source": source,
        "path": str(alvo),
        "sha256": digest,
        "dataset_checksum": str(dados.get("checksum", "")),
    }


def _sha256_arquivo(caminho: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _textos_dataset(pasta: str | Path) -> list[str]:
    from core.linha_trainer import _ler_manifesto
    return [texto for _caminho, texto in _ler_manifesto(pasta)]


def construir_modelo_linguagem(pastas: tuple[str | Path, ...] | None = None,
                               destino: str | Path | None = None) -> Path:
    """Atualiza o léxico estatístico com todas as transcrições confirmadas.

    Sem argumentos, a base de linhas e o léxico são os de `config.paths`.
    """
    from config.paths import modelo_de_lingua, pasta_de_linhas
    if pastas is None:
        pastas = (pasta_de_linhas(),)
    if destino is None:
        destino = modelo_de_lingua()
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


def treinar_pacote(*, pasta: str | Path | None = None,
                   validacao: str | Path | None = None,
                   calibracao: str | Path | None = None,
                   holdout: str | Path | None = None,
                   holdout_provenance: str | Path | None = None,
                   destino: str | Path | None = None,
                   meta: str | Path | None = None,
                   epocas: int = 20, batch_size: int = 8,
                   paciencia: int = 6, callback=None,
                   should_stop=None, preparar_pesos: bool = True,
                   service=None, dataset_version: str = "",
                   dataset_provenance: str | Path | None = None,
                   exigir_proveniencia_dataset: bool = False,
                   split_manifest: str | Path | None = None,
                   exigir_split: bool = False,
                   line_binding: str | Path | None = None,
                   exigir_line_binding: bool = False,
                   manifest_path: str | Path | None = None,
                   semente: int = 42, taxa_aprendizado: float = 1e-3,
                   dispositivo: str = "auto", retomar: bool = True,
                   alfabeto_automatico: bool = True) -> OCRTrainingSummary:
    """Treina o modelo local e atualiza o pacote usado pelo botão Executar.

    Os caminhos que faltarem são os de `config.paths` — a base de linhas e o
    modelo ao lado do código, e não no cwd de quem abriu o programa.
    """
    from config.paths import completar_modelo_linha, pasta_de_linhas
    from core.linha_trainer import (CER_MAXIMO_EM_PRODUCAO, fingerprint_dataset,
                                    modelo_utilizavel, treinar, validar_dataset,
                                    validar_datasets_disjuntos)
    from core.ocr_phase7 import (CalibrationObservation, calibrate_domains,
                                 evaluate_holdout, load_split_manifest)
    from core.ocr_line_binding import load_line_binding
    if exigir_proveniencia_dataset and dataset_provenance is None:
        raise ValueError(
            "exigir_proveniencia_dataset requer um manifesto de dataset")
    proveniencia_dataset = (
        carregar_proveniencia_dataset(dataset_provenance)
        if dataset_provenance is not None else None)
    if exigir_split and split_manifest is None:
        raise ValueError("exigir_split requer um manifesto de split")
    if exigir_line_binding and line_binding is None:
        raise ValueError("exigir_line_binding requer um vínculo de linhas")
    split = None
    split_manifest_path = ""
    split_manifest_sha256 = ""
    if split_manifest is not None:
        split_path = Path(split_manifest).resolve()
        split = load_split_manifest(split_path)
        if exigir_split and (not split.train or not split.holdout):
            raise ValueError("manifesto de split precisa conter treino e holdout reais")
        split_manifest_path = str(split_path)
        split_manifest_sha256 = _sha256_arquivo(split_path)
    line_binding_path = ""
    line_binding_sha256 = ""
    if line_binding is not None:
        line_binding_file = Path(line_binding).resolve()
        expected_line_datasets = {"train": pasta}
        if validacao is not None:
            expected_line_datasets["validation"] = validacao
        if calibracao is not None:
            expected_line_datasets["calibration"] = calibracao
        if holdout is not None:
            expected_line_datasets["holdout"] = holdout
        load_line_binding(line_binding_file,
                          expected_datasets=expected_line_datasets,
                          require_holdout=exigir_line_binding)
        line_binding_path = str(line_binding_file)
        line_binding_sha256 = _sha256_arquivo(line_binding_file)
    holdout_selection = None
    holdout_line_provenance = None
    if holdout_provenance is not None:
        if holdout is None:
            raise ValueError("proveniência de holdout exige um dataset --holdout")
        from core.ocr_holdout import (carregar_selecao,
                                      validar_proveniencia_de_linhas)
        holdout_selection = carregar_selecao(holdout_provenance)
        holdout_line_provenance = validar_proveniencia_de_linhas(
            holdout, holdout_selection)
    if pasta is None:
        pasta = pasta_de_linhas()
    pasta_real = Path(pasta).resolve()
    if calibracao is not None:
        calibracao_real = Path(calibracao).resolve()
        if calibracao_real == pasta_real:
            raise ValueError("dataset de calibração precisa ser independente do treino")
        if holdout is not None and calibracao_real == Path(holdout).resolve():
            raise ValueError("dataset de calibração precisa ser independente do holdout")
        diagnostico_calibracao = validar_dataset(calibracao)
        if any(diagnostico_calibracao.get(chave) for chave in
               ("vazias", "ilegiveis", "ausentes", "malformadas")):
            raise ValueError("dataset de calibração inválido")
    if holdout is not None:
        holdout_real = Path(holdout).resolve()
        if pasta_real == holdout_real:
            raise ValueError("holdout real precisa ser diferente do dataset de treino")
        diagnostico_holdout = validar_dataset(holdout)
        if any(diagnostico_holdout.get(chave) for chave in
               ("vazias", "ilegiveis", "ausentes", "malformadas")):
            raise ValueError("dataset de holdout invÃ¡lido")
    datasets_para_validar = {"treino": pasta}
    if validacao is not None:
        datasets_para_validar["validacao"] = validacao
    if calibracao is not None:
        datasets_para_validar["calibracao"] = calibracao
    if holdout is not None:
        datasets_para_validar["holdout"] = holdout
    if all((Path(caminho) / "rec_gt.txt").is_file()
           for caminho in datasets_para_validar.values()):
        validar_datasets_disjuntos(datasets_para_validar)
    destino, meta = completar_modelo_linha(destino, meta)
    holdout_anterior = None
    if holdout is not None and Path(destino).is_file() and Path(meta).is_file():
        from core.linha_trainer import avaliar
        try:
            holdout_anterior = avaliar(destino, meta, holdout)
        except (OSError, RuntimeError, ValueError, KeyError):
            # Peso anterior incompatível não é um baseline válido; o novo
            # ainda terá de passar pelo holdout absoluto.
            holdout_anterior = None
    ok = treinar(pasta=pasta, validacao=validacao, destino=destino, meta=meta,
                 epocas=epocas, batch_size=batch_size, paciencia=paciencia,
                 semente=semente, taxa_aprendizado=taxa_aprendizado,
                 dispositivo=dispositivo, retomar=retomar,
                 alfabeto_automatico=alfabeto_automatico,
                 callback=callback, should_stop=should_stop)
    if not ok:
        raise RuntimeError("Treinamento cancelado antes de gerar um modelo novo.")
    # O léxico vai para o lado do modelo, como o estado e o manifesto abaixo:
    # sem destino, ele caía no padrão, e um treino apontado para outra pasta
    # escrevia o léxico na raiz do projeto.
    from config.paths import modelo_de_lingua
    caminho_lexico = construir_modelo_linguagem(
        (pasta, *(tuple([validacao]) if validacao else ())),
        destino=modelo_de_lingua(destino))
    estados = preparar_engines(service, callback=callback,
                               preparar_pesos=preparar_pesos)
    metadados_modelo = {}
    try:
        metadados_modelo = json.loads(Path(meta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # O portão já explica a falha; o manifesto não deve esconder o
        # resultado do treino por causa de uma leitura apenas informativa.
        metadados_modelo = {}
    metadados_modelo["holdout_required"] = True
    for chave in (
            "dataset_provenance_verified", "dataset_provenance_path",
            "dataset_provenance_sha256", "dataset_provenance_source",
            "dataset_provenance_checksum"):
        metadados_modelo.pop(chave, None)
    metadados_modelo["dataset_provenance_required"] = bool(
        exigir_proveniencia_dataset)
    if proveniencia_dataset is not None:
        metadados_modelo.update({
            "dataset_provenance_verified": bool(proveniencia_dataset["verified"]),
            "dataset_provenance_path": proveniencia_dataset["path"],
            "dataset_provenance_sha256": proveniencia_dataset["sha256"],
            "dataset_provenance_source": proveniencia_dataset["source"],
            "dataset_provenance_checksum": proveniencia_dataset["dataset_checksum"],
        })
    for chave in (
            "split_manifest", "split_manifest_sha256", "split_schema",
            "split_counts", "split_required"):
        metadados_modelo.pop(chave, None)
    metadados_modelo["split_required"] = bool(exigir_split)
    if split is not None:
        metadados_modelo.update({
            "split_manifest": split_manifest_path,
            "split_manifest_sha256": split_manifest_sha256,
            "split_schema": "pyboxeditor.ocr-split/v1",
            "split_counts": {
                nome: len(getattr(split, nome))
                for nome in ("train", "validation", "test", "holdout", "synthetic")
            },
        })
    for chave in (
            "line_binding", "line_binding_sha256", "line_binding_schema",
            "line_binding_required"):
        metadados_modelo.pop(chave, None)
    metadados_modelo["line_binding_required"] = bool(exigir_line_binding)
    if line_binding_path:
        metadados_modelo.update({
            "line_binding": line_binding_path,
            "line_binding_sha256": line_binding_sha256,
            "line_binding_schema": "pyboxeditor.ocr-line-binding/v1",
        })
    holdout_resultado = None
    holdout_comparacao = None
    if holdout is not None:
        from core.linha_trainer import avaliar
        holdout_resultado = avaliar(destino, meta, holdout)
        if holdout_anterior is not None:
            holdout_comparacao = evaluate_holdout(
                [holdout_anterior["cer"]], [holdout_resultado["cer"]],
                higher_is_better=False, minimum_delta=0.0)
        metadados_modelo.update({
            "holdout_evaluated": True,
            "holdout_cer": float(holdout_resultado["cer"]),
            "holdout_wer": float(holdout_resultado["wer"]),
            "holdout_exact_lines": int(holdout_resultado["exatas"]),
            "holdout_lines": int(holdout_resultado["linhas"]),
            "holdout_before_cer": (float(holdout_anterior["cer"])
                                   if holdout_anterior is not None else None),
            "holdout_baseline_available": holdout_anterior is not None,
            "holdout_improved": (holdout_comparacao.improved
                                 if holdout_comparacao is not None else None),
            "holdout_sha256": fingerprint_dataset(holdout),
        })
        if holdout_selection is not None:
            metadados_modelo.update({
                "holdout_provenance": str(Path(holdout_provenance).resolve()),
                "holdout_corpus_sha256": holdout_selection.corpus_sha256,
                "holdout_source_documents": list(holdout_selection.document_ids),
                "holdout_source_pages": [
                    page.page_id for page in holdout_selection.pages
                ],
            })
        if holdout_line_provenance is not None:
            metadados_modelo.update({
                "holdout_line_provenance_schema": holdout_line_provenance["schema"],
                "holdout_line_dataset_sha256": holdout_line_provenance[
                    "dataset_sha256"],
                "holdout_line_count": int(holdout_line_provenance["lines"]),
                "holdout_line_source_pages": list(holdout_line_provenance["page_ids"]),
            })
    else:
        for chave in (
                "holdout_provenance", "holdout_corpus_sha256",
                "holdout_source_documents", "holdout_source_pages",
                "holdout_line_provenance_schema",
                "holdout_line_dataset_sha256", "holdout_line_count",
                "holdout_line_source_pages"):
            metadados_modelo.pop(chave, None)
        metadados_modelo.update({"holdout_evaluated": False,
                                 "holdout_cer": None,
                                 "holdout_before_cer": None,
                                 "holdout_baseline_available": False,
                                 "holdout_improved": None})
    calibration_report_path = ""
    calibration_dataset_sha256 = ""
    calibration_domains: tuple[str, ...] = ()
    if calibracao is not None:
        from core.linha_trainer import avaliar
        calibration_resultado = avaliar(destino, meta, calibracao)
        observacoes = [
            CalibrationObservation(item["domain"], item["confidence"],
                                   item["correct"])
            for item in calibration_resultado.get("calibration_observations", ())
        ]
        if not observacoes:
            raise ValueError("dataset de calibração não produziu observações")
        reliability = calibrate_domains(observacoes)
        calibration_dataset_sha256 = fingerprint_dataset(calibracao)
        report_payload = {
            "schema": CALIBRATION_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dataset_sha256": calibration_dataset_sha256,
            "lines": len(observacoes),
            "domains": reliability.to_dict(),
        }
        caminho_calibracao = Path(destino).with_name(
            f"{Path(destino).stem}_calibration.json")
        caminho_calibracao.parent.mkdir(parents=True, exist_ok=True)
        caminho_calibracao.write_text(
            json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        calibration_report_path = str(caminho_calibracao.resolve())
        calibration_domains = reliability.domains
        metadados_modelo.update({
            "calibration_evaluated": True,
            "calibration_dataset_sha256": calibration_dataset_sha256,
            "calibration_lines": len(observacoes),
            "calibration_domains": list(calibration_domains),
            "calibration_report": calibration_report_path,
            "calibration_report_sha256": _sha256_arquivo(caminho_calibracao),
        })
    else:
        for chave in (
                "calibration_evaluated", "calibration_dataset_sha256",
                "calibration_lines", "calibration_domains",
                "calibration_report", "calibration_report_sha256"):
            metadados_modelo.pop(chave, None)
    if Path(meta).is_file():
        Path(meta).write_text(json.dumps(metadados_modelo, ensure_ascii=False,
                                         indent=2) + "\n", encoding="utf-8")
    production_eligible, production_gate_reason = modelo_utilizavel(meta, destino)
    if production_eligible and holdout is None:
        production_eligible = False
        production_gate_reason = "holdout real nÃ£o informado; pacote nÃ£o pode ser promovido"
    elif (production_eligible and holdout_resultado is not None
          and holdout_resultado["cer"] > CER_MAXIMO_EM_PRODUCAO):
        production_eligible = False
        production_gate_reason = (
            f"holdout real com CER {holdout_resultado['cer']:.0%} "
            f"(limite para produÃ§Ã£o: {CER_MAXIMO_EM_PRODUCAO:.0%})")
    if (production_eligible and holdout_comparacao is not None
            and not holdout_comparacao.improved):
        production_eligible = False
        production_gate_reason = "regressão no holdout real em relação ao peso anterior"
    caminho_manifesto = ""
    if Path(destino).is_file():
        from core.ocr_phase7 import WeightManifest
        manifesto = WeightManifest.from_file(
            destino, model_id="text-line-crnn", pipeline_version="editorial-pipeline/v4",
            config={"dataset": str(pasta), "dataset_version": str(dataset_version),
                    "batch_size": batch_size, "epochs": epocas,
                    "patience": paciencia, "seed": semente,
                    "learning_rate": taxa_aprendizado,
                    "device": dispositivo,
                    "model_sha256": metadados_modelo.get("model_sha256", ""),
                    "dataset_sha256": metadados_modelo.get("dataset_sha256", ""),
                    "validation_sha256": metadados_modelo.get("validacao_sha256", ""),
                    "validation_groups": metadados_modelo.get("validacao_grupos", []),
                    "holdout_required": True,
                    "holdout_evaluated": bool(holdout_resultado is not None),
                    "holdout_cer": (holdout_resultado["cer"]
                                    if holdout_resultado is not None else None),
                    "holdout_before_cer": (holdout_anterior["cer"]
                                           if holdout_anterior is not None else None),
                    "holdout_improved": (holdout_comparacao.improved
                                         if holdout_comparacao is not None else None),
                    "holdout_sha256": metadados_modelo.get("holdout_sha256", ""),
                    "holdout_provenance": metadados_modelo.get("holdout_provenance", ""),
                    "holdout_corpus_sha256": metadados_modelo.get(
                        "holdout_corpus_sha256", ""),
                    "holdout_source_pages": metadados_modelo.get(
                        "holdout_source_pages", []),
                    "holdout_line_provenance_schema": metadados_modelo.get(
                        "holdout_line_provenance_schema", ""),
                    "holdout_line_dataset_sha256": metadados_modelo.get(
                        "holdout_line_dataset_sha256", ""),
                    "holdout_line_count": metadados_modelo.get(
                        "holdout_line_count", 0),
                    "holdout_line_source_pages": metadados_modelo.get(
                        "holdout_line_source_pages", []),
                    "calibration_evaluated": metadados_modelo.get(
                        "calibration_evaluated", False),
                    "calibration_dataset_sha256": metadados_modelo.get(
                        "calibration_dataset_sha256", ""),
                    "calibration_domains": metadados_modelo.get(
                        "calibration_domains", []),
                    "calibration_report_sha256": metadados_modelo.get(
                        "calibration_report_sha256", ""),
                    "split_required": metadados_modelo.get(
                        "split_required", False),
                    "split_manifest": metadados_modelo.get(
                        "split_manifest", ""),
                    "split_manifest_sha256": metadados_modelo.get(
                        "split_manifest_sha256", ""),
                    "split_counts": metadados_modelo.get(
                        "split_counts", {}),
                    "line_binding_required": metadados_modelo.get(
                        "line_binding_required", False),
                    "line_binding": metadados_modelo.get(
                        "line_binding", ""),
                    "line_binding_sha256": metadados_modelo.get(
                        "line_binding_sha256", ""),
                    "dataset_provenance_verified": metadados_modelo.get(
                        "dataset_provenance_verified", False),
                    "dataset_provenance_sha256": metadados_modelo.get(
                        "dataset_provenance_sha256", ""),
                    "dataset_provenance_source": metadados_modelo.get(
                        "dataset_provenance_source", ""),
                    "production_eligible": production_eligible,
                    "production_gate_reason": production_gate_reason},
        )
        alvo = Path(manifest_path) if manifest_path else Path(destino).with_suffix(".manifest.json")
        manifesto.save(alvo)
        caminho_manifesto = str(alvo)
    # O estado vai para o lado do modelo, e não para o diretório de trabalho:
    # `salvar_estado(resumo)` sem caminho gravava `ocr_training_state.json`
    # onde quer que o processo tivesse sido aberto.
    estado = Path(destino).with_name("ocr_training_state.json")
    resumo = OCRTrainingSummary(
        True, str(caminho_lexico), estados, str(estado), caminho_manifesto,
        str(dataset_version), production_eligible, production_gate_reason)
    resumo.holdout_evaluated = holdout_resultado is not None
    resumo.holdout_cer = (float(holdout_resultado["cer"])
                          if holdout_resultado is not None else None)
    resumo.holdout_before_cer = (float(holdout_anterior["cer"])
                                 if holdout_anterior is not None else None)
    resumo.holdout_improved = (holdout_comparacao.improved
                               if holdout_comparacao is not None else None)
    resumo.holdout_corpus_sha256 = (
        holdout_selection.corpus_sha256 if holdout_selection is not None else "")
    resumo.dataset_provenance_sha256 = (
        str(proveniencia_dataset["sha256"])
        if proveniencia_dataset is not None else "")
    resumo.calibration_report = calibration_report_path
    resumo.calibration_dataset_sha256 = calibration_dataset_sha256
    resumo.calibration_domains = calibration_domains
    resumo.split_manifest = split_manifest_path
    resumo.split_manifest_sha256 = split_manifest_sha256
    resumo.line_binding = line_binding_path
    resumo.line_binding_sha256 = line_binding_sha256
    salvar_estado(resumo, estado)
    return resumo
