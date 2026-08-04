"""
Split de validação e relatório de treino.

Existe porque o número que o treino exibia não queria dizer nada: a acurácia era
calculada sobre as próprias amostras de treino, já aumentadas, e o "melhor
modelo" era escolhido pela *training loss* — critério que seleciona exatamente o
ponto de maior overfitting.

Duas decisões desta implementação que não estavam na SPEC §5.4 e vieram de olhar
a base:

1. **Classe pequena demais não é dividida.** Tirar 15% de uma classe de 3
   amostras deixa o treino com 2 e a validação com 1: piora o modelo para medir
   mal. Abaixo de `MIN_PARA_DIVIDIR` a classe vai inteira para o treino e entra
   na lista de **não avaliáveis**, que o relatório mostra em primeiro lugar. Uma
   acurácia de validação que ignora 24 das 103 classes em silêncio seria o mesmo
   defeito que esta fase veio corrigir.

2. **O conjunto de teste não tem piso de 1 amostra por classe.** Ele serve para
   um único número final, não para recall por classe; forçar uma amostra por
   classe roubaria do treino justamente as classes que menos têm.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn


SEMENTE_PADRAO = 20260803

# Abaixo disto a classe não é dividida — vai inteira para o treino.
MIN_PARA_DIVIDIR = 5


@dataclass
class Divisao:
    treino: np.ndarray
    validacao: np.ndarray
    teste: np.ndarray
    sem_validacao: List[int] = field(default_factory=list)  # índices de classe

    def __str__(self):
        return (f"treino {len(self.treino)}, validação {len(self.validacao)}, "
                f"teste {len(self.teste)}")


def dividir_estratificado(labels: Sequence[int], num_classes: int,
                          frac_val: float = 0.15, frac_teste: float = 0.05,
                          semente: int = SEMENTE_PADRAO,
                          min_para_dividir: int = MIN_PARA_DIVIDIR) -> Divisao:
    """
    Divide os índices por classe, com semente fixa.

    Estratificado de verdade: a proporção é aplicada **dentro** de cada classe.
    Um sorteio global sobre uma base de 25.075:1 deixaria classes inteiras fora
    da validação por acaso.
    """
    labels = np.asarray(labels, dtype=np.int64)
    rng = np.random.RandomState(semente)

    treino, validacao, teste, sem_val = [], [], [], []
    for k in range(num_classes):
        ids = np.where(labels == k)[0]
        if len(ids) == 0:
            continue
        rng.shuffle(ids)

        if len(ids) < min_para_dividir:
            treino.extend(ids.tolist())
            sem_val.append(k)
            continue

        n_val = max(1, int(round(frac_val * len(ids))))
        n_teste = int(round(frac_teste * len(ids)))   # sem piso: ver docstring
        # O treino nunca fica vazio: min_para_dividir garante folga, mas uma
        # fração exótica passada por quem chama não pode zerá-lo.
        n_val = min(n_val, len(ids) - 1)
        n_teste = min(n_teste, len(ids) - n_val - 1)

        validacao.extend(ids[:n_val].tolist())
        teste.extend(ids[n_val:n_val + n_teste].tolist())
        treino.extend(ids[n_val + n_teste:].tolist())

    return Divisao(np.array(sorted(treino), dtype=np.int64),
                   np.array(sorted(validacao), dtype=np.int64),
                   np.array(sorted(teste), dtype=np.int64),
                   sem_val)


@dataclass
class Avaliacao:
    perda: float
    acuracia: float            # micro, %
    recall_macro: float        # média dos recalls por classe presente, %
    acertos: np.ndarray        # por classe
    totais: np.ndarray         # por classe
    matriz: np.ndarray         # confusão: esperado (linha) x previsto (coluna)
    erros: List[Tuple[int, int, int]]   # (índice da amostra, esperado, previsto)

    def recall_por_classe(self) -> np.ndarray:
        r = np.zeros(len(self.totais), dtype=np.float64)
        presentes = self.totais > 0
        r[presentes] = 100.0 * self.acertos[presentes] / self.totais[presentes]
        return r

    def classes_zeradas(self) -> int:
        return int(((self.totais > 0) & (self.acertos == 0)).sum())


@torch.no_grad()
def avaliar(model, dados: np.ndarray, labels: Sequence[int],
            indices: Sequence[int], num_classes: int,
            device=None, lote: int = 512) -> Avaliacao:
    """
    Roda o modelo sobre `indices` de `dados`, **sem augmentation**.

    Sem augmentation por dois motivos: é imagem limpa que chega na predição, e
    medir sobre imagem aumentada torna o número irreprodutível entre execuções.
    """
    device = device or torch.device("cpu")
    labels = np.asarray(labels, dtype=np.int64)
    indices = np.asarray(indices, dtype=np.int64)

    acertos = np.zeros(num_classes, dtype=np.int64)
    totais = np.zeros(num_classes, dtype=np.int64)
    matriz = np.zeros((num_classes, num_classes), dtype=np.int64)
    erros: List[Tuple[int, int, int]] = []

    if len(indices) == 0:
        return Avaliacao(float("nan"), float("nan"), float("nan"),
                         acertos, totais, matriz, erros)

    criterio = nn.CrossEntropyLoss(reduction="sum")
    estava_treinando = model.training
    model.eval()

    perda_total = 0.0
    for i in range(0, len(indices), lote):
        bloco = indices[i:i + lote]
        x = torch.from_numpy(dados[bloco]).float().div_(255.0).unsqueeze(1).to(device)
        y = torch.from_numpy(labels[bloco]).to(device)
        saida = model(x)
        perda_total += float(criterio(saida, y).item())
        previsto = saida.argmax(1).cpu().numpy()

        for pos, (esperado, prev) in enumerate(zip(labels[bloco], previsto)):
            totais[esperado] += 1
            matriz[esperado, prev] += 1
            if esperado == prev:
                acertos[esperado] += 1
            else:
                erros.append((int(bloco[pos]), int(esperado), int(prev)))

    if estava_treinando:
        model.train()

    presentes = totais > 0
    recall = np.zeros(num_classes)
    recall[presentes] = 100.0 * acertos[presentes] / totais[presentes]

    return Avaliacao(
        perda=perda_total / len(indices),
        acuracia=100.0 * acertos.sum() / totais.sum(),
        recall_macro=float(recall[presentes].mean()),
        acertos=acertos, totais=totais, matriz=matriz, erros=erros)


def piores_classes(av: Avaliacao, idx_to_char: Dict[int, str],
                   quantas: int = 10) -> List[Tuple[str, int, int, float]]:
    """[(caractere, acertos, total, recall%)] das piores classes avaliadas."""
    recall = av.recall_por_classe()
    presentes = [k for k in range(len(av.totais)) if av.totais[k] > 0]
    presentes.sort(key=lambda k: (recall[k], -av.totais[k]))
    return [(idx_to_char.get(k, "?"), int(av.acertos[k]), int(av.totais[k]),
             float(recall[k])) for k in presentes[:quantas]]


def pares_confusos(av: Avaliacao, idx_to_char: Dict[int, str],
                   quantas: int = 15) -> List[Tuple[str, str, int]]:
    """
    [(esperado, previsto, quantas vezes)] — é isto que a matriz de confusão
    serve para mostrar, e não os 10.609 números de uma tabela 103x103.
    """
    m = av.matriz.copy()
    np.fill_diagonal(m, 0)
    pares = [(int(e), int(p), int(m[e, p])) for e, p in zip(*np.nonzero(m))]
    pares.sort(key=lambda t: -t[2])
    return [(idx_to_char.get(e, "?"), idx_to_char.get(p, "?"), n)
            for e, p, n in pares[:quantas]]


def salvar_amostras_erradas(pasta: str, dados: np.ndarray, av: Avaliacao,
                            idx_to_char: Dict[int, str],
                            maximo: int = 200) -> int:
    """
    Grava os erros de validação como PNG, em `esperado_virou_previsto/`.

    Limitado: um treino ruim erra milhares de amostras, e despejar tudo em disco
    transforma o relatório em outro problema. Os erros são ordenados pelos pares
    mais frequentes, que é o que vale a pena olhar.
    """
    import cv2

    from core.learner import char_to_folder as nome

    if not av.erros:
        return 0

    frequencia = {}
    for _, esperado, previsto in av.erros:
        frequencia[(esperado, previsto)] = frequencia.get((esperado, previsto), 0) + 1
    ordenados = sorted(av.erros,
                       key=lambda t: -frequencia[(t[1], t[2])])[:maximo]

    os.makedirs(pasta, exist_ok=True)
    gravados = 0
    for idx, esperado, previsto in ordenados:
        sub = os.path.join(pasta, f"{nome(idx_to_char.get(esperado, '?'))}"
                                  f"_virou_{nome(idx_to_char.get(previsto, '?'))}")
        os.makedirs(sub, exist_ok=True)
        # imencode + write: cv2.imwrite falha em caminho não-ASCII no Windows e
        # devolve False sem levantar (ver core/dataset_check.py).
        ok, buf = cv2.imencode(".png", dados[idx])
        if not ok:
            continue
        with open(os.path.join(sub, f"{idx}.png"), "wb") as f:
            f.write(buf.tobytes())
        gravados += 1
    return gravados


def texto_do_relatorio(av_val: Avaliacao, idx_to_char: Dict[int, str],
                       divisao: Divisao, epochs_rodadas: int,
                       melhor_epoch: int, historico: List[dict],
                       av_teste: Optional[Avaliacao] = None,
                       pasta_erros: Optional[str] = None) -> str:
    linhas: List[str] = []
    a = linhas.append
    a("Relatório de treino — PyBoxEditor")
    a("=" * 60)
    a("")
    a(f"Divisão: {divisao}")
    if divisao.sem_validacao:
        chars = ", ".join(repr(idx_to_char.get(k, "?"))
                          for k in divisao.sem_validacao)
        a(f"Classes SEM validação ({len(divisao.sem_validacao)}): {chars}")
        a(f"  (menos de {MIN_PARA_DIVIDIR} amostras — vão inteiras para o treino;")
        a("   nenhum número abaixo diz nada sobre elas)")
    a("")
    a(f"Melhor epoch: {melhor_epoch} de {epochs_rodadas} rodadas "
      "(escolhida pela perda de validação)")
    a("")
    avaliadas = int((av_val.totais > 0).sum())
    a("VALIDAÇÃO")
    a(f"  acurácia global .... {av_val.acuracia:.2f}%")
    a(f"  recall macro ....... {av_val.recall_macro:.2f}%  "
      f"({avaliadas} classes avaliadas)")
    a(f"  classes zeradas .... {av_val.classes_zeradas()}")
    a(f"  perda .............. {av_val.perda:.4f}")

    # O recall macro é uma média por classe, então classes com pouquíssimas
    # amostras de validação o fazem pular. Sem este aviso é fácil ler uma
    # variação de ruído como se fosse melhora ou piora do modelo.
    escassas = int(((av_val.totais > 0) & (av_val.totais < 5)).sum())
    if escassas and avaliadas:
        a(f"  ATENÇÃO: {escassas} das {avaliadas} classes avaliadas têm menos de")
        a(f"  5 amostras de validação. Uma única amostra que muda de lado mexe")
        a(f"  {100.0 / avaliadas:.2f} ponto(s) no recall macro — compare com cuidado.")
    if av_teste is not None and not np.isnan(av_teste.acuracia):
        a("")
        a("TESTE (não usado em nenhuma decisão do treino)")
        a(f"  acurácia global .... {av_teste.acuracia:.2f}%")
        a(f"  recall macro ....... {av_teste.recall_macro:.2f}%")
    a("")
    a("PIORES CLASSES (validação)")
    for ch, ok, tot, rec in piores_classes(av_val, idx_to_char):
        a(f"  {ch!r:>8}  {ok:>5}/{tot:<5}  {rec:6.1f}%")
    a("")
    a("CONFUSÕES MAIS FREQUENTES")
    for esperado, previsto, n in pares_confusos(av_val, idx_to_char):
        a(f"  {esperado!r:>8} lido como {previsto!r:<8}  {n:>5}x")
    a("")
    a("POR EPOCH")
    a("  ep   perda(treino)  perda(val)  acur(val)  macro(val)")
    for h in historico:
        a(f"  {h['epoch']:>3}  {h['perda_treino']:>12.4f}  "
          f"{h['perda_val']:>10.4f}  {h['acuracia_val']:>8.2f}%  "
          f"{h['macro_val']:>9.2f}%")
    if pasta_erros:
        a("")
        a(f"Amostras erradas gravadas em: {pasta_erros}")
    a("")
    return "\n".join(linhas)


def gravar_relatorio(caminho_txt: str, texto: str, av_val: Avaliacao,
                     idx_to_char: Dict[int, str], divisao: Divisao,
                     historico: List[dict],
                     av_teste: Optional[Avaliacao] = None) -> str:
    """Grava o relatório legível e um .json com os dados. Devolve o caminho .txt."""
    pasta = os.path.dirname(os.path.abspath(caminho_txt))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with open(caminho_txt, "w", encoding="utf-8") as f:
        f.write(texto)

    m = av_val.matriz.copy()
    np.fill_diagonal(m, 0)
    dados = {
        "divisao": {"treino": len(divisao.treino),
                    "validacao": len(divisao.validacao),
                    "teste": len(divisao.teste),
                    "classes_sem_validacao": [idx_to_char.get(k, "?")
                                              for k in divisao.sem_validacao]},
        "validacao": {"acuracia": av_val.acuracia,
                      "recall_macro": av_val.recall_macro,
                      "perda": av_val.perda,
                      "classes_zeradas": av_val.classes_zeradas(),
                      "por_classe": {idx_to_char.get(k, "?"):
                                     [int(av_val.acertos[k]), int(av_val.totais[k])]
                                     for k in range(len(av_val.totais))
                                     if av_val.totais[k] > 0}},
        # A matriz cheia é 103x103 quase toda zero; o que interessa são os pares
        # fora da diagonal, e eles guardam a mesma informação (a diagonal são os
        # acertos, já registrados em por_classe).
        "confusoes": [[idx_to_char.get(int(e), "?"), idx_to_char.get(int(p), "?"),
                       int(m[e, p])] for e, p in zip(*np.nonzero(m))],
        "historico": historico,
    }
    if av_teste is not None and not np.isnan(av_teste.acuracia):
        dados["teste"] = {"acuracia": av_teste.acuracia,
                          "recall_macro": av_teste.recall_macro,
                          "perda": av_teste.perda}

    with open(os.path.splitext(caminho_txt)[0] + ".json", "w",
              encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    return caminho_txt
