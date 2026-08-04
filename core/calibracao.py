"""
Calibração da confiança do modelo (F1.9).

A confiança é consumida em três lugares — a cor da F3.2, o filtro "só pendentes"
da F3.3 e a ponderação de custo da F1.7 — e em todos eles o que se quer é que o
número **signifique** alguma coisa.

Duas medidas foram feitas antes de escrever este módulo, e as duas mudaram o
desenho proposto no ROADMAP:

1. **No split de validação não há o que calibrar.** ECE de 0,0003 e acurácia de
   99,93%; a temperatura ajustada ali dá 0,995, isto é, não faz nada. A
   miscalibração aparece só em **página real**, onde a acurácia cai para ~93% e o
   ECE sobe para ~0,033. O split é tirado de `training_data`, que é recorte já
   segmentado e limpo — não é a distribuição em que o modelo trabalha.

2. **Calibrar não faz o filtro achar mais erro.** Qualquer temperatura é uma
   transformação da mesma pontuação: a AUROC entre certo e errado fica em 0,89
   para T de 0,5 a 4,0. O que a temperatura muda é a **escala**, não a ordem —
   move o ponto de operação de um limiar, não o poder de separar. Medido nas 8
   páginas rotuladas:

       T      0,5     1,0     2,0     4,0     8,0
       AUROC  0,874   0,890   0,895   0,891   0,860

   Então o ganho de "pegar mais erros" que aparece ao subir T é o mesmo que se
   obteria mexendo no limiar com T=1. É por isso que `curva_de_triagem` existe: é
   ela, e não o ECE, que responde onde pôr o corte.

O que a temperatura entrega de verdade é o número exibido ser honesto — a UI
mostra "95%" para o revisor, e convém que 95% queira dizer 95%.
"""

from typing import Dict, List, Sequence, Tuple

import numpy as np


# Bins do ECE. 15 é o usual da literatura (Guo et al., 2017); com menos, faixas
# largas escondem o desvio, com muito mais cada bin fica com poucas amostras.
BINS_PADRAO = 15


def ece(confiancas: Sequence[float], acertos: Sequence[bool],
        bins: int = BINS_PADRAO) -> float:
    """
    Expected Calibration Error: desvio médio entre confiança dita e acerto real.

    Zero é calibração perfeita. Pesa cada faixa pela quantidade de amostras, o
    que importa aqui: quase 90% dos caracteres saem com confiança acima de 0,999,
    e um erro nessa faixa vale muito mais que o mesmo erro numa faixa vazia.
    """
    conf = np.asarray(confiancas, dtype=np.float64)
    ok = np.asarray(acertos, dtype=bool)
    if len(conf) == 0:
        return float("nan")

    limites = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for lo, hi in zip(limites, limites[1:]):
        na_faixa = (conf > lo) & (conf <= hi)
        if na_faixa.any():
            total += na_faixa.mean() * abs(ok[na_faixa].mean() - conf[na_faixa].mean())
    return float(total)


def auroc(confiancas: Sequence[float], acertos: Sequence[bool]) -> float:
    """
    P(confiança de um acerto > confiança de um erro). 0,5 = não separa nada.

    É a medida que **não** muda com a temperatura, e por isso é ela que diz se um
    reescalonamento pode ou não melhorar a triagem.
    """
    conf = np.asarray(confiancas, dtype=np.float64)
    ok = np.asarray(acertos, dtype=bool)
    n1, n0 = int(ok.sum()), int((~ok).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")

    ordem = np.argsort(conf, kind="mergesort")
    ranks = np.empty(len(conf), dtype=np.float64)
    ranks[ordem] = np.arange(1, len(conf) + 1)
    # empates recebem o rank médio, senão a medida depende da ordem de entrada
    for valor in np.unique(conf):
        iguais = conf == valor
        if iguais.sum() > 1:
            ranks[iguais] = ranks[iguais].mean()

    return float((ranks[ok].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def curva_de_triagem(confiancas: Sequence[float], acertos: Sequence[bool],
                     cortes: Sequence[float] = (0.5, 0.7, 0.9, 0.99, 0.999)
                     ) -> List[Dict[str, float]]:
    """
    Para cada corte: quanto da página o revisor olha e que fração dos erros acha.

    É a pergunta prática por trás da F3.2 e da F3.3, e a única que responde onde
    pôr `ui.confidence.LIMIAR_ALTO`. O ECE não responde: um modelo pode estar
    perfeitamente calibrado e ainda assim não distinguir certo de errado.
    """
    conf = np.asarray(confiancas, dtype=np.float64)
    ok = np.asarray(acertos, dtype=bool)
    n_erros = int((~ok).sum())
    n_certos = int(ok.sum())

    saida = []
    for corte in cortes:
        marcados = conf < corte
        erros_pegos = int((marcados & ~ok).sum())
        saida.append({
            "corte": float(corte),
            "revisado_pct": 100.0 * marcados.mean() if len(conf) else 0.0,
            "erros_pegos_pct": 100.0 * erros_pegos / n_erros if n_erros else 0.0,
            "certos_marcados_pct": (100.0 * int((marcados & ok).sum()) / n_certos
                                    if n_certos else 0.0),
            "erros_restantes": n_erros - erros_pegos,
        })
    return saida


def _log_softmax(logits: np.ndarray, T: float) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64) / T
    z = z - z.max(axis=1, keepdims=True)
    return z - np.log(np.exp(z).sum(axis=1, keepdims=True))


def nll(logits: np.ndarray, aceitaveis: np.ndarray, T: float) -> float:
    """
    Log-verossimilhança negativa da massa sobre as classes **aceitáveis**.

    Aceitáveis, no plural, porque o livro imprime figurina e quem rotulou à mão
    escreveu a letra do lance: para um `N` rotulado, tanto a classe da letra
    quanto a da figurina ♘ são leitura correta. Tratar só uma como certa
    marcaria leitura boa como erro e puxaria a temperatura para cima.
    """
    logp = _log_softmax(logits, T)
    massa = np.where(aceitaveis, logp, -np.inf)
    maior = massa.max(axis=1, keepdims=True)
    somado = maior[:, 0] + np.log(np.exp(massa - maior).sum(axis=1))
    return float(-somado.mean())


def confianca_e_acerto(logits: np.ndarray, aceitaveis: np.ndarray,
                       T: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """(confiança, acertou) para uma temperatura."""
    logp = _log_softmax(logits, T)
    previsto = logp.argmax(axis=1)
    conf = np.exp(logp[np.arange(len(previsto)), previsto])
    return conf, aceitaveis[np.arange(len(previsto)), previsto]


def ajustar_temperatura(logits: np.ndarray, aceitaveis: np.ndarray,
                        criterio: str = "ece",
                        limites: Tuple[float, float] = (0.4, 10.0),
                        passos: int = 300) -> float:
    """
    Temperatura que melhor calibra, por busca em grade log-uniforme.

    `criterio`:
      - "ece" (padrão): minimiza o desvio entre confiança e acerto. É o número
        que a UI mostra, então é ele que deve estar certo.
      - "nll": minimiza a log-verossimilhança. **Mede outra coisa** e dá uma
        temperatura bem mais alta (2,61 contra 1,67 nas páginas rotuladas),
        porque a NLL é dominada por poucos erros catastroficamente confiantes;
        amaciar todo o resto para acomodá-los piora o ECE de 0,033 para 0,039.

    Grade em vez de gradiente: é um parâmetro só, num intervalo conhecido, e a
    busca fica reprodutível — LBFGS sobre ECE não serviria de qualquer modo,
    porque o ECE é constante por partes e tem gradiente zero quase em todo ponto.
    """
    if criterio not in ("ece", "nll"):
        raise ValueError(f"critério desconhecido: {criterio!r}")

    grade = np.exp(np.linspace(np.log(limites[0]), np.log(limites[1]), passos))
    melhor_T, melhor_valor = 1.0, float("inf")
    for T in grade:
        if criterio == "nll":
            valor = nll(logits, aceitaveis, float(T))
        else:
            conf, ok = confianca_e_acerto(logits, aceitaveis, float(T))
            valor = ece(conf, ok)
        if valor < melhor_valor:
            melhor_T, melhor_valor = float(T), valor
    return melhor_T


def resumo(logits: np.ndarray, aceitaveis: np.ndarray, T: float = 1.0) -> Dict:
    """Tudo que o relatório de calibração precisa, para uma temperatura."""
    conf, ok = confianca_e_acerto(logits, aceitaveis, T)
    errados = conf[~ok]
    return {
        "temperatura": T,
        "n": int(len(conf)),
        "acuracia": float(ok.mean()) if len(ok) else float("nan"),
        "confianca_media": float(conf.mean()) if len(conf) else float("nan"),
        "ece": ece(conf, ok),
        "nll": nll(logits, aceitaveis, T),
        "auroc": auroc(conf, ok),
        "conf_mediana_erro": float(np.median(errados)) if len(errados) else float("nan"),
        "triagem": curva_de_triagem(conf, ok),
    }
