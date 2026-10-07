"""Treina o OCR sequencial sem abrir a interface gráfica."""

import argparse

from core.linha_trainer import (avaliar, modelo_utilizavel, salvar_avaliacao,
                                validar_dataset)
from core.ocr_training import treinar_pacote


def main():
    parser = argparse.ArgumentParser(description="Treino CRNN/CTC de OCR por linhas")
    parser.add_argument("--epocas", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--paciencia", type=int, default=6)
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--lr", type=float, default=1e-3,
                        help="taxa de aprendizado")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--dataset", default="training_data_linhas")
    parser.add_argument("--validacao", default=None,
                        help="manifesto separado para medir generalização real")
    parser.add_argument("--calibracao", default=None,
                        help="dataset independente para calibrar confianca por dominio")
    parser.add_argument("--holdout", default=None,
                        help="dataset real independente exigido para promoção")
    parser.add_argument("--holdout-proveniencia", default=None,
                        help="seleção JSON validada pelo corpus de holdout")
    parser.add_argument("--destino", default="text_line_model.pth")
    parser.add_argument("--meta", default="text_line_model.json")
    parser.add_argument("--manifesto-pesos", default=None,
                        help="grava checksum e compatibilidade do modelo gerado")
    parser.add_argument("--exigir-portao", action="store_true",
                        help="falha se o CER do modelo não passar o limite de produção")
    parser.add_argument("--versao-dataset", default="",
                        help="versão do dataset registrada no treino")
    parser.add_argument("--dataset-proveniencia", default=None,
                        help="manifesto JSON que prova a origem do dataset")
    parser.add_argument("--exigir-proveniencia-dataset", action="store_true",
                        help="bloqueia o treino sem proveniência verificada")
    parser.add_argument("--split-manifest", default=None,
                        help="manifesto Fase 7 que registra a separacao por fonte")
    parser.add_argument("--exigir-split", action="store_true",
                        help="exige manifesto com treino e holdout reais")
    parser.add_argument("--line-binding", default=None,
                        help="vinculo humano entre grupos do rec_gt e o split")
    parser.add_argument("--exigir-line-binding", action="store_true",
                        help="exige vinculo verificavel dos datasets de linhas")
    parser.add_argument("--novo", action="store_true",
                        help="ignora o checkpoint existente")
    parser.add_argument("--sem-alfabeto-automatico", action="store_true",
                        help="recusa caracteres presentes só na validação")
    parser.add_argument("--avaliar", action="store_true",
                        help="mede CER/WER usando as linhas do manifesto")
    parser.add_argument("--saida-avaliacao", default="text_line_evaluation.json",
                        help="JSON do benchmark e das amostras prioritárias")
    parser.add_argument("--gerar-sintetico", action="store_true",
                        help="gera imagens sintéticas a partir do manifesto")
    parser.add_argument("--sintetico-destino", default="training_data_linhas_sintetico")
    parser.add_argument("--sintetico-por-linha", type=int, default=4)
    args = parser.parse_args()
    resumo = validar_dataset(args.dataset)
    print(f"Dataset: {resumo['linhas']} linhas, {resumo['caracteres']} caracteres")
    if (resumo["vazias"] or resumo["ilegiveis"] or resumo.get("ausentes")
            or resumo.get("malformadas")):
        raise SystemExit("Dataset inválido: corrija os arquivos antes do treino.")
    if args.avaliar:
        resultado = avaliar(args.destino, args.meta, args.dataset)
        salvar_avaliacao(resultado, args.saida_avaliacao)
        print(f"Avaliacao: CER={resultado['cer']:.2%}, "
              f"WER={resultado['wer']:.2%}, "
              f"linhas exatas={resultado['exatas']}/{resultado['linhas']}")
        elegivel, motivo_portao = modelo_utilizavel(args.meta, args.destino)
        print(f"Portão de produção: {'aprovado' if elegivel else 'reprovado'}"
              + (f" — {motivo_portao}" if motivo_portao else ""))
        for item in resultado["piores"][:5]:
            print(f"  {item['imagem']}: {item['previsto']!r} "
                  f"(esperado {item['esperado']!r}, CER={item['cer']:.2%})")
        return
    if args.gerar_sintetico:
        from core.linha_sintetica import gerar
        resultado = gerar(args.dataset, args.sintetico_destino,
                          args.sintetico_por_linha, args.semente)
        print(f"Sintetico: {resultado['linhas_geradas']} linhas em {resultado['pasta']}")
        return
    resumo = treinar_pacote(
        pasta=args.dataset, destino=args.destino, meta=args.meta,
        calibracao=args.calibracao,
        holdout=args.holdout,
        holdout_provenance=args.holdout_proveniencia,
        epocas=args.epocas, batch_size=args.batch_size,
        retomar=not args.novo, paciencia=args.paciencia,
        semente=args.semente, taxa_aprendizado=args.lr,
        dispositivo=args.device, callback=print, validacao=args.validacao,
        alfabeto_automatico=not args.sem_alfabeto_automatico,
        dataset_version=args.versao_dataset,
        dataset_provenance=args.dataset_proveniencia,
        exigir_proveniencia_dataset=args.exigir_proveniencia_dataset,
        split_manifest=args.split_manifest,
        exigir_split=args.exigir_split,
        line_binding=args.line_binding,
        exigir_line_binding=args.exigir_line_binding,
        manifest_path=args.manifesto_pesos,
    )
    print(f"Modelo: {args.destino}")
    print(f"Estado: {resumo.state_path}")
    elegivel = bool(getattr(resumo, "production_eligible", False))
    motivo_portao = str(getattr(resumo, "production_gate_reason", "") or "")
    print(f"Portão de produção: {'aprovado' if elegivel else 'reprovado'}"
          + (f" — {motivo_portao}" if motivo_portao else ""))
    if resumo.weight_manifest:
        print(f"Manifesto de pesos: {resumo.weight_manifest}")
    if args.exigir_portao and not elegivel:
        raise SystemExit(2)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
