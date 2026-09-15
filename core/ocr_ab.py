"""Comparação A/B de modos OCR sobre o mesmo corpus.

O módulo não conhece engines. Isso é deliberado: o benchmark precisa comparar
o modo antigo e o candidato usando exatamente as mesmas páginas, referências e
normalização. Os callbacks podem devolver um ``dict`` de página, ``PageResult``
ou qualquer objeto que exponha ``to_dict``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from core.notacao import e_token_de_notacao
from core.ocr_benchmark import (AggregateMetrics, PageMetrics, agregar,
                                distancia_edicao, medir_pagina, normalizar_texto)


def _page_dict(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    raise TypeError("predição A/B precisa ser mapping ou possuir to_dict()")


@dataclass(frozen=True)
class ABCase:
    """Uma página avaliada nos dois modos."""

    page_id: str
    reference: Mapping[str, Any]
    input: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ABReport:
    baseline: AggregateMetrics
    candidate: AggregateMetrics
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def delta_cer(self) -> float | None:
        if self.baseline.text is None or self.candidate.text is None:
            return None
        return self.candidate.text.cer - self.baseline.text.cer

    @property
    def delta_wer(self) -> float | None:
        if self.baseline.words is None or self.candidate.words is None:
            return None
        return self.candidate.words.cer - self.baseline.words.cer

    @property
    def candidate_improved(self) -> bool | None:
        delta = self.delta_cer
        return None if delta is None else delta < 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline.to_dict(),
            "candidate": self.candidate.to_dict(),
            "delta": {"cer": self.delta_cer, "wer": self.delta_wer,
                       "candidate_improved": self.candidate_improved},
            "metadata": self.metadata,
        }


def comparar_modos(
    casos: Iterable[ABCase],
    baseline: Callable[[Any], Any],
    candidate: Callable[[Any], Any],
    *,
    ignorar_maiusculas: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> ABReport:
    """Executa os dois callbacks e calcula métricas micro agregadas.

    Cada callback recebe o mesmo ``case.input``. Exceções não são engolidas:
    uma falha em uma página invalida a comparação, evitando um resultado A/B
    artificialmente favorável ao modo que processou menos páginas.
    """
    casos = list(casos)
    resultados_a: list[PageMetrics] = []
    resultados_b: list[PageMetrics] = []
    for case in casos:
        referencia = _page_dict(case.reference)
        pred_a = _page_dict(baseline(case.input))
        pred_b = _page_dict(candidate(case.input))
        info = {**dict(case.metadata), "mode": "baseline"}
        resultados_a.append(medir_pagina(case.page_id, referencia, pred_a,
                                         ignorar_maiusculas=ignorar_maiusculas,
                                         metadata=info))
        info = {**dict(case.metadata), "mode": "candidate"}
        resultados_b.append(medir_pagina(case.page_id, referencia, pred_b,
                                         ignorar_maiusculas=ignorar_maiusculas,
                                         metadata=info))
    return ABReport(agregar(resultados_a), agregar(resultados_b),
                    metadata={**dict(metadata or {}), "cases": len(casos)})


# ----------------------------------------------------------------------
# CER/WER por domínio (OCR-11): prosa e notação medidas cada uma por si
# ----------------------------------------------------------------------
#
# A revisão das páginas 30–31 mostrou por que a conta junta engana: os glifos
# do DOCX não tinham erro perceptível, e a prosa tinha erro sistemático — a
# mesma página dá um CER só, e ele não diz de qual dos dois leitores é o
# defeito. Aqui o token da referência é classificado por `e_token_de_notacao`,
# e o erro de cada token alinhado vai para o domínio dele. A inserção, que não
# tem token de referência, vai para o domínio do vizinho de trás.

_TIPOGRAFIA = str.maketrans({
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2020": "+", "\u2026": "...", "\u00a0": " ",
})


def normalizar_tipografia(texto: str) -> str:
    """Dobra o que é escolha tipográfica, e não leitura: traço, aspa, xeque.

    A impressão usa travessão entre os nomes e `†` no xeque; o programa
    escreve `+` (ver `notacao.SINONIMOS_DE_SAIDA`) e o Tesseract devolve o
    traço que lhe der na telha. Contar isso como erro mediria a convenção, e
    não o reconhecimento — e os dois lados passam pela mesma dobra.
    """
    return normalizar_texto(str(texto or "").translate(_TIPOGRAFIA))


def _dominio_do_token(token: str) -> str:
    return "notation" if e_token_de_notacao(token) else "prose"


def alinhar_tokens(referencia: Sequence[str],
                   predicao: Sequence[str]) -> list[tuple[str | None, str | None]]:
    """Alinhamento de Levenshtein entre duas sequências de tokens.

    Devolve pares `(referência, predição)`; `None` de um lado é remoção ou
    inserção. É o alinhamento que a distância usa, e não uma reimplementação
    dela: o custo é 1 por operação, como em `distancia_edicao`.
    """
    n, m = len(referencia), len(predicao)
    custo = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        custo[i][0] = i
    for j in range(1, m + 1):
        custo[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            custo[i][j] = min(custo[i - 1][j] + 1, custo[i][j - 1] + 1,
                              custo[i - 1][j - 1]
                              + (referencia[i - 1] != predicao[j - 1]))
    pares: list[tuple[str | None, str | None]] = []
    i, j = n, m
    while i or j:
        if (i and j and custo[i][j] == custo[i - 1][j - 1]
                + (referencia[i - 1] != predicao[j - 1])):
            pares.append((referencia[i - 1], predicao[j - 1]))
            i, j = i - 1, j - 1
        elif i and custo[i][j] == custo[i - 1][j] + 1:
            pares.append((referencia[i - 1], None))
            i -= 1
        else:
            pares.append((None, predicao[j - 1]))
            j -= 1
    pares.reverse()
    return pares


def medir_por_dominio(referencia: str, predicao: str) -> dict[str, dict[str, float]]:
    """WER e CER de `prose` e `notation`, mais o `total`, entre dois textos.

    Os tokens são separados por espaço depois de `normalizar_tipografia`, e
    não pelo tokenizador do benchmark, que separa a pontuação: `27.♕xh6` é um
    token de notação inteiro, e `check.` uma palavra de prosa com o ponto.
    O CER é o de dentro dos tokens alinhados — a remoção custa o token da
    referência inteiro, a inserção custa o token inserido.
    """
    ref = normalizar_tipografia(referencia).split()
    pred = normalizar_tipografia(predicao).split()
    contas = {dominio: {"tokens": 0, "erros": 0, "caracteres": 0,
                        "erros_de_caractere": 0}
              for dominio in ("prose", "notation", "total")}
    ultimo = "prose"
    for esperado, lido in alinhar_tokens(ref, pred):
        if esperado is not None:
            dominio = ultimo = _dominio_do_token(esperado)
            tokens, chars = 1, len(esperado)
            erro = int(esperado != lido)
            erro_chars = (len(esperado) if lido is None
                          else distancia_edicao(esperado, lido))
        else:
            dominio, tokens, chars = ultimo, 0, 0
            erro, erro_chars = 1, len(lido or "")
        for chave in (dominio, "total"):
            contas[chave]["tokens"] += tokens
            contas[chave]["caracteres"] += chars
            contas[chave]["erros"] += erro
            contas[chave]["erros_de_caractere"] += erro_chars
    for conta in contas.values():
        conta["wer"] = conta["erros"] / conta["tokens"] if conta["tokens"] else 0.0
        conta["cer"] = (conta["erros_de_caractere"] / conta["caracteres"]
                        if conta["caracteres"] else 0.0)
    return contas
