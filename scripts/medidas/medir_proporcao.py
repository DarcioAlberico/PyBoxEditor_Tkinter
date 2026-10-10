"""
Mede o veto geométrico da F106 — a régua de `core/proporcao.py`.

**Por que existe.** Os dois elos que classificam esticam o recorte para 32×32
sem preservar proporção, então uma barra de tinta em pé e uma deitada chegam a
eles como a mesma imagem. Enquanto o glifo tem branco por dentro isso não custa
nada; num recorte que é só tinta — um ponto, um `I` de haste grossa, um
travessão — não sobra sinal nenhum, e a rede responde pela frequência de treino
das classes. `core/proporcao.py` devolve ao veto o que o esticão jogou fora.

Este script responde às duas perguntas que decidem se a regra entra:

    segurança   na página como ela é, quantas leituras ela mexe — e quantas
                delas estavam certas antes
    ganho       na mesma página com a tinta engrossada, quanto ela recupera

O engrossamento é `cv2.erode` com kernel 2×2, de 1 a 4 iterações, e é o que uma
digitalização pesada faz com o traço. Não é sujeira sintética: é o mesmo eixo
em que o `I` de *Introduction* do Aagaard deixa de ser lido.

    python medir_proporcao.py                 # as duas tabelas, só a rede
    python medir_proporcao.py --elo cadeia    # com o k-NN atrás da rede
    python medir_proporcao.py --engrossa 0 2  # só esses níveis
    python medir_proporcao.py --exemplos      # cada leitura que a regra mexeu

**O EasyOCR fica de fora, e não é economia de tempo.** Ele é o último elo e não
oferece candidatas, então a regra não tem o que escolher ali — a cadeia medida
aqui é a que a regra alcança. As leituras que chegariam nele aparecem na coluna
`ao easyocr`, e entram nas duas colunas de acerto do mesmo jeito nos dois lados
da comparação: elas não mudam, e é por isso que podem ser contadas.
"""

import argparse
import collections
import os
import statistics
import sys

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from core import proporcao
from core.avaliacao_pagina import carregar_box
from core.calibracao_de_pagina import paginas_rotuladas
from core.neural_trainer import NeuralPredictor
from core.services.learning_service import LearningService

#: Os limiares de produção — `NEURAL_THRESHOLD` e `LEARNER_THRESHOLD_NEURAL` de
#: `ui/main_window`. Medir com outros mediria outra cadeia.
LIMIAR_DA_REDE = 0.70
LIMIAR_DO_KNN = 0.9


def _console_em_utf8():
    """O mesmo de `medir_altura.py`: sem isto, o `■` derruba o script no cp1252."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def paginas(raiz="."):
    """[(imagem em cinza, rotulados, altura de referência)] das páginas rotuladas."""
    saida = []
    for imagem, caminho in paginas_rotuladas(raiz):
        img = Image.open(imagem).convert("L")
        rotulados = [b for b in carregar_box(caminho, img.size[1])
                     if b.x2 > b.x1 and b.y2 > b.y1]
        if not rotulados:
            continue
        saida.append((np.array(img), rotulados,
                      proporcao.altura_de_referencia(rotulados),
                      os.path.basename(caminho)))
    return saida


def engrossar(crop, vezes):
    """Tinta mais pesada, como a de um scan escuro. `erode` porque tinta é preta."""
    if not vezes:
        return crop
    return cv2.erode(crop, np.ones((2, 2), np.uint8), iterations=vezes)


@torch.no_grad()
def probabilidades(predictor, crops, lote=512):
    """O softmax da rede para muitos recortes — a conta de `_probabilidades`, em lote."""
    x = np.stack([cv2.resize(c, (32, 32)) for c in crops]).astype(np.float32) / 255.0
    t = torch.from_numpy(x).unsqueeze(1).to(predictor.device)
    saida = [F.softmax(predictor.model(t[i:i + lote]) / predictor.temperatura,
                       dim=1).cpu().numpy()
             for i in range(0, len(t), lote)]
    return np.concatenate(saida)


def _candidatas_da_rede(predictor, probs, ordem, j, quantas):
    return [(predictor.idx_to_char.get(int(k), "?"), float(probs[j][k]))
            for k in ordem[j][:quantas]]


def ler(predictor, learner, crops, boxes, referencia):
    """
    `[(antes, depois, chegou_ao_easyocr)]` por recorte — a cadeia com e sem veto.

    "Antes" é a cadeia como estava; "depois" é a mesma cadeia com o veto. As duas
    saem da **mesma** consulta a cada elo, para nenhuma diferença vir de ruído de
    execução.
    """
    probs = probabilidades(predictor, crops)
    ordem = np.argsort(-probs, axis=1)
    saida = []
    for j, b in enumerate(boxes):
        largura, altura = b.x2 - b.x1, b.y2 - b.y1
        char = predictor.idx_to_char.get(int(ordem[j][0]), "?")
        conf = float(probs[j][ordem[j][0]])

        vetado = char
        if not proporcao.cabe(char, largura, altura, referencia):
            escolhida = proporcao.escolher(
                _candidatas_da_rede(predictor, probs, ordem, j,
                                    proporcao.CANDIDATAS),
                largura, altura, referencia)
            if escolhida is not None:
                vetado, conf_vetado = escolhida
            else:
                conf_vetado = conf
        else:
            conf_vetado = conf

        if conf > LIMIAR_DA_REDE and conf_vetado > LIMIAR_DA_REDE:
            saida.append((char, vetado, False))
            continue
        if learner is None:
            # Sem o k-NN, a medida é da rede: quem não passou o limiar dela
            # entra assim mesmo, e entra igual dos dois lados.
            saida.append((char, vetado, False))
            continue

        antes = char if conf > LIMIAR_DA_REDE else None
        depois = vetado if conf_vetado > LIMIAR_DA_REDE else None
        if antes is None or depois is None:
            k_char, k_conf, _m = learner.predict_e_margem(crops[j])
            k_vetado = k_char
            if not proporcao.cabe(k_char, largura, altura, referencia):
                escolhida = proporcao.escolher(
                    learner.candidatas(crops[j], n=proporcao.CANDIDATAS),
                    largura, altura, referencia)
                if escolhida is not None:
                    k_vetado, k_conf_vetado = escolhida
                else:
                    k_conf_vetado = k_conf
            else:
                k_conf_vetado = k_conf
            if antes is None:
                antes = k_char if k_conf > LIMIAR_DO_KNN else None
            if depois is None:
                depois = k_vetado if k_conf_vetado > LIMIAR_DO_KNN else None

        # Quem não passou em nenhum dos dois elos iria ao EasyOCR, que não é
        # medido aqui: fica com a leitura da rede, igual dos dois lados.
        ao_easyocr = antes is None or depois is None
        saida.append((antes or char, depois or vetado, ao_easyocr))
    return saida


def medir(predictor, learner, dados, vezes, exemplos=False):
    conta = collections.Counter()
    mudou = collections.Counter()
    tintas = []
    for arr, boxes, referencia, nome in dados:
        crops = [engrossar(arr[b.y1:b.y2, b.x1:b.x2], vezes) for b in boxes]
        tintas += [float((c < 128).mean()) for c in crops if c.size]
        for b, (antes, depois, ao_easyocr) in zip(
                boxes, ler(predictor, learner, crops, boxes, referencia)):
            conta["total"] += 1
            conta["easyocr"] += ao_easyocr
            conta["antes"] += antes == b.char
            conta["depois"] += depois == b.char
            familia = b.char in proporcao.ENVELOPE
            conta["familia"] += familia
            conta["familia_antes"] += familia and antes == b.char
            conta["familia_depois"] += familia and depois == b.char
            if antes != depois:
                conta["mexidas"] += 1
                if antes == b.char:
                    conta["quebrou"] += 1
                elif depois == b.char:
                    conta["consertou"] += 1
                else:
                    conta["nem_nem"] += 1
                if exemplos:
                    mudou[(b.char, antes, depois)] += 1
    conta["tinta"] = statistics.median(tintas) if tintas else 0.0
    return conta, mudou


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--elo", choices=("rede", "cadeia"), default="rede",
                    help="'rede' mede só a CNN; 'cadeia' põe o k-NN atrás dela")
    ap.add_argument("--engrossa", type=int, nargs="+", default=[0, 1, 2, 3, 4],
                    help="níveis de engrossamento da tinta (0 = a página como é)")
    ap.add_argument("--exemplos", action="store_true",
                    help="lista cada leitura que o veto mexeu")
    ap.add_argument("--raiz", default=".")
    args = ap.parse_args()
    _console_em_utf8()

    predictor = NeuralPredictor()
    if not predictor.load():
        print(f"Modelo não carregou: {predictor.erro or 'motivo não informado'}")
        return 1

    learner = None
    if args.elo == "cadeia":
        print("Carregando a base do k-NN...")
        servico = LearningService()
        learner = servico._get_learner()
        print(f"  {learner.total} referências")

    dados = paginas(args.raiz)
    if not dados:
        print("Nenhuma página rotulada encontrada.")
        return 1
    total = sum(len(b) for _a, b, _r, _n in dados)
    familia = sum(1 for _a, boxes, _r, _n in dados for b in boxes
                  if b.char in proporcao.ENVELOPE)
    print(f"{len(dados)} páginas rotuladas, {total} caracteres, "
          f"{familia} deles de uma classe do envelope\n")

    print(f"{'eng':>4} {'tinta':>6} | {'todos antes':>11} {'depois':>8} | "
          f"{'família antes':>13} {'depois':>8} | {'mexidas':>7} "
          f"{'consertou':>9} {'quebrou':>7} {'nem-nem':>7} | {'ao easyocr':>10}")
    for vezes in args.engrossa:
        c, mudou = medir(predictor, learner, dados, vezes, args.exemplos)
        n, f = c["total"], max(1, c["familia"])
        print(f"{vezes:>4} {c['tinta']:6.2f} | "
              f"{c['antes'] / n:11.4f} {c['depois'] / n:8.4f} | "
              f"{c['familia_antes'] / f:13.4f} {c['familia_depois'] / f:8.4f} | "
              f"{c['mexidas']:>7} {c['consertou']:>9} {c['quebrou']:>7} "
              f"{c['nem_nem']:>7} | {c['easyocr']:>10}")
        if args.exemplos and mudou:
            for (rotulo, antes, depois), quantas in mudou.most_common():
                marca = ("consertou" if depois == rotulo
                         else "QUEBROU" if antes == rotulo else "")
                print(f"        {quantas:5d}x  {rotulo!r} lido {antes!r} "
                      f"-> {depois!r}  {marca}")

    print("\nA coluna que decide é 'quebrou': leitura que estava certa e o veto "
          "estragou.\nEla tem de ser zero — o veto só fala sobre resposta que o "
          "envelope diz\nser impossível, e leitura certa cabe no envelope por "
          "construção.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
