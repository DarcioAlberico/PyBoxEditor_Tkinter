"""
Ajusta e grava a temperatura de calibração do modelo (F1.9).

    python calibrar_modelo.py            # mede e mostra, não grava
    python calibrar_modelo.py --gravar   # grava a temperatura em model_meta.json

**Por que nas páginas rotuladas e não no split de validação.** O split sai de
`training_data`, que é recorte já segmentado e limpo: o modelo acerta 99,93% ali
e o ECE é 0,0003 — não há o que calibrar, e a temperatura ajustada dá 0,995. Em
página real a acurácia cai para ~93% e o ECE sobe para ~0,033. É na página que a
confiança é consumida, então é na página que ela tem de estar certa.

A validação é **leave-one-page-out**: a temperatura de cada página sai das outras
sete. Ajustar e medir nas mesmas 8 páginas daria um número bonito e falso.
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np
import torch
from PIL import Image

from core import calibracao
from core.avaliacao_pagina import carregar_box, comparar, normalizar
from core.neural_model import SimpleCNN, get_device
from core.services.box_service import BoxService
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas


def carregar_modelo(model_path="custom_model.pth", meta_path="model_meta.json"):
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    device = get_device()
    model = SimpleCNN(meta["num_classes"]).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()
    return model, meta, device


@torch.no_grad()
def _logits(model, device, recortes, lote=512):
    imgs = np.stack([cv2.resize(r, (32, 32)) for r in recortes])
    x = torch.from_numpy(imgs).float().div_(255.0).unsqueeze(1).to(device)
    saida = [model(x[i:i + lote]).cpu().numpy() for i in range(0, len(x), lote)]
    return np.concatenate(saida)


def coletar(model, meta, device, separar_colados=True):
    """[(nome, logits, máscara de classes aceitáveis)] por página rotulada."""
    idx_to_char = {int(k): v for k, v in meta["idx_to_char"].items()}
    num_classes = meta["num_classes"]

    # caractere normalizado -> classes que contam como leitura correta
    aceitaveis_de = {}
    for k, c in idx_to_char.items():
        aceitaveis_de.setdefault(normalizar(c), []).append(k)

    paginas = []
    for imagem, caminho_box in paginas_rotuladas():
        img = Image.open(imagem).convert("L")
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue

        arr = np.array(img)
        boxes = BoxService.generate_boxes_opencv(
            img, separar_colados=separar_colados)
        lg = _logits(model, device, [arr[b.y1:b.y2, b.x1:b.x2] for b in boxes])
        previsto = lg.argmax(axis=1)
        for i, b in enumerate(boxes):
            b.char = idx_to_char.get(int(previsto[i]), "?")

        linhas, mascaras = [], []
        for i, j in comparar(boxes, rotulados).pares:
            classes = aceitaveis_de.get(normalizar(rotulados[j].char))
            if not classes:
                continue        # rótulo que o modelo nem tem como classe
            m = np.zeros(num_classes, dtype=bool)
            m[classes] = True
            linhas.append(lg[i])
            mascaras.append(m)

        if linhas:
            paginas.append((os.path.basename(imagem), np.stack(linhas),
                            np.stack(mascaras)))
    return paginas


def _mostrar(titulo, r):
    print(f"\n{titulo}")
    print(f"  n {r['n']}   acurácia {100*r['acuracia']:.2f}%   "
          f"confiança média {r['confianca_media']:.4f}")
    print(f"  ECE {r['ece']:.4f}   NLL {r['nll']:.4f}   AUROC {r['auroc']:.4f}   "
          f"confiança mediana de um erro {r['conf_mediana_erro']:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gravar", action="store_true",
                    help="grava a temperatura em model_meta.json")
    ap.add_argument("--criterio", default="ece", choices=("ece", "nll"))
    ap.add_argument("--meta", default="model_meta.json")
    ap.add_argument("--modelo", default="custom_model.pth")
    args = ap.parse_args()

    model, meta, device = carregar_modelo(args.modelo, args.meta)
    paginas = coletar(model, meta, device)
    if not paginas:
        print("nenhuma página rotulada encontrada")
        return 1

    LG = np.concatenate([l for _, l, _ in paginas])
    MA = np.concatenate([m for _, _, m in paginas])
    print(f"{len(paginas)} páginas rotuladas, {len(LG)} caracteres")

    T = calibracao.ajustar_temperatura(LG, MA, criterio=args.criterio)
    antes = calibracao.resumo(LG, MA, 1.0)
    depois = calibracao.resumo(LG, MA, T)

    _mostrar("SEM calibração (T = 1)", antes)
    _mostrar(f"COM calibração (T = {T:.4f}, critério {args.criterio})", depois)

    print("\nA temperatura não muda o poder de separar certo de errado:")
    for t in (0.5, 1.0, 2.0, 4.0, 8.0):
        c, ok = calibracao.confianca_e_acerto(LG, MA, t)
        print(f"  T={t:<5.1f} AUROC {calibracao.auroc(c, ok):.4f}")

    print("\nCurva de triagem (T = 1) — é ela que diz onde pôr o limiar:")
    print(f"  {'corte':>8} {'da página revisada':>19} {'dos erros achados':>19} "
          f"{'erros que escapam':>18}")
    for p in antes["triagem"]:
        print(f"  {p['corte']:>8.3f} {p['revisado_pct']:>18.1f}% "
              f"{p['erros_pegos_pct']:>18.1f}% {p['erros_restantes']:>18}")

    print(f"\nLeave-one-page-out (temperatura ajustada nas outras "
          f"{len(paginas) - 1}):")
    print(f"  {'página':<22} {'T':>6} {'ECE T=1':>9} {'ECE calibrado':>14}")
    soma_1 = soma_c = n = 0.0
    for k, (nome, lg, ma) in enumerate(paginas):
        outros_lg = np.concatenate([p[1] for i, p in enumerate(paginas) if i != k])
        outros_ma = np.concatenate([p[2] for i, p in enumerate(paginas) if i != k])
        t = calibracao.ajustar_temperatura(outros_lg, outros_ma, criterio=args.criterio)
        e1 = calibracao.ece(*calibracao.confianca_e_acerto(lg, ma, 1.0))
        ec = calibracao.ece(*calibracao.confianca_e_acerto(lg, ma, t))
        soma_1 += e1 * len(lg); soma_c += ec * len(lg); n += len(lg)
        print(f"  {nome[-20:]:<22} {t:>6.3f} {e1:>9.4f} {ec:>14.4f}")
    print(f"  {'MÉDIA PONDERADA':<22} {'':>6} {soma_1/n:>9.4f} {soma_c/n:>14.4f}")

    if args.gravar:
        meta["temperatura"] = T
        with open(args.meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        print(f"\nTemperatura {T:.4f} gravada em {args.meta}")
    else:
        print(f"\n(nada gravado — use --gravar para aplicar T={T:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
