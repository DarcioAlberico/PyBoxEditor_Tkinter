"""Treina o OCR sequencial sem abrir a interface gráfica."""

import argparse

from core.linha_trainer import avaliar, salvar_avaliacao, treinar, validar_dataset


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
    parser.add_argument("--destino", default="text_line_model.pth")
    parser.add_argument("--meta", default="text_line_model.json")
    parser.add_argument("--manifesto-pesos", default=None,
                        help="grava checksum e compatibilidade do modelo gerado")
    parser.add_argument("--versao-dataset", default="",
                        help="versão do dataset registrada no treino")
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
    ok = treinar(pasta=args.dataset, destino=args.destino, meta=args.meta,
                 epocas=args.epocas,
                 batch_size=args.batch_size, retomar=not args.novo,
                 paciencia=args.paciencia, semente=args.semente,
                 taxa_aprendizado=args.lr, dispositivo=args.device,
                 callback=print, validacao=args.validacao,
                 alfabeto_automatico=not args.sem_alfabeto_automatico)
    if ok and args.manifesto_pesos:
        from core.ocr_phase7 import WeightManifest
        manifesto = WeightManifest.from_file(
            args.destino, model_id="text-line-crnn",
            pipeline_version="editorial-pipeline/v4",
            config={"dataset": args.dataset, "dataset_version": args.versao_dataset,
                    "batch_size": args.batch_size, "epochs": args.epocas,
                    "patience": args.paciencia, "seed": args.semente},
        )
        manifesto.save(args.manifesto_pesos)
        print(f"Manifesto de pesos: {args.manifesto_pesos}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
