"""
A geometria decide a caixa (F112): o caminho de Baird, que não pede rótulo.

`s` e `S`, `o`, `O` e `0`, `c` e `C` são o mesmo desenho em dois corpos, e o
classificador recebe o recorte já esticado para 32×32 — o que os separa foi
jogado fora antes de ele ver (F14, F19, F107). A F19 e a F37 penduraram a altura
**depois**, como desempate contra a âncora, e mediram que não paga: quando o
canal falava, acertava 0 vezes em 72. A régua delas era a faixa da linha,
`max(y2) − min(y1)` dos boxes, que encolhe na linha sem ascendente ou sem
descendente e desloca todas as frações juntas — o conjunto "âncora e geometria
discordam" era quase todo erro da geometria.

Baird (1992, *Document Image Defect Models and Their Uses*, p. 8) faz o
contrário, e é o que este módulo faz: **cada leitura propõe um corpo de letra**
— um `s` de 20 px diz "a altura de x desta linha é 20", um `S` de 20 px diz
"é 14" —, a linha vota qual é o dela, pela mediana ponderada pela confiança, e o
corpo votado **poda** a leitura que não cabe nele. A linha deixa de ser a faixa
dos boxes e passa a ser uma base e uma altura de x estimadas do que se leu, e a
linha sem ascendente estima as duas tão bem quanto a outra.

## Três escolhas, e cada uma saiu de medida (F112 no ROADMAP)

**A medida é a do corpo de tinta dentro do recorte, e não a da caixa.** Com a
caixa, as quebras reais tinham uma causa só: o pingo do `i` entrava na caixa da
letra anterior (`w|ith`, `v|isão`), e o `w` ficava com o topo de um `W`. O corpo
é a faixa de linhas com tinta de maior massa (`medir`): o pingo e o acento
destacados ficam fora, e a haste do `i` passa a ter o topo na altura de x, o
que separa o `i` do `l` — coisa que a F19 media como impossível (d' = 0,01).

**Só se troca dentro de um grupo de mesmo desenho** (`GRUPOS`). O Baird de 1992
poda toda interpretação que não cabe; aqui a rede já acerta 98% e é melhor que a
geometria em tudo o que não é tamanho. Solta, a poda trocava `)` por `J` e `H`
por `R`, porque a candidata que cabia era outro desenho. A regra é a do veto da
F106 e da máscara da F109: filtra e escolhe entre as candidatas da rede, e
nunca inventa classe que ela não ofereceu.

**O dígito só vira letra dentro de palavra, e a letra só vira dígito dentro de
número** (`_contexto_admite`). O algarismo de texto (`1` e `0` na altura de x)
existe em livro, e sem isto `1.e4` sairia `i.e4`. É o filtro "all-alphabetic or
all-numeric" que o próprio Baird descreve na §5, reduzido ao vizinho de caixa.

## A confiança da troca

A rede não separa os dois lados de um par — é por isso que ele é par —, então a
probabilidade que ela dá a cada um é a do desenho repartida ao acaso. A troca
sai com a **massa do grupo** entre as candidatas, e não com a probabilidade da
substituta sozinha: o `o` que a rede deu 0,08 contra 0,9 do `O` sairia
derrubado pelo piso de confiança do livro, e a troca viraria um buraco. Pelo
mesmo motivo a leitura **confirmada** (`podar(limiar_de_confirmacao=...)`) — a
fraca que cabe na linha enquanto todo o resto do grupo não cabe — sobe para a
massa do grupo: é o `o` repartido entre `o`, `0` e `O`, que nenhum alcançava
0,5 e o livro apagava (F107, "Cmbinatin invlving bihp").

## De onde vem a tabela

`core/dados/geometria_das_classes.json`, gerada por `medir_geometria.py
--gravar` a partir das páginas rotuladas: para cada classe, onde o corpo dela
começa e acaba em relação à base da linha, em alturas de x, e o desvio robusto
(1,4826 × MAD). As páginas de PDF nascido digital dão desvio zero em muita
classe, e é por isso que há `PISO`.

**O limite dela é ser uma só.** A altura da caixa alta sobre a de x é da
fonte — 1,32 no Darcy Lima, 1,67 no *Attacking Manual* —, e a tabela de todos
os livros junta as duas: o `S` fica com desvio 0,15, e o `s` lido `S` cai a
2,8 desvios, abaixo do `VETO`. O mesmo vale para o `P` (0,28); o `l` (0,18)
só cai quando a haste lida fica abaixo da altura votada, que é onde caíram os
23 `l`→`i` medidos. A minúscula de topo em x é estreita em toda fonte, e o
`C`, o `O`, o `W` e o `0` a tabela mede estreitos: esses a poda pega nos dois
sentidos. A tabela por livro, das maiúsculas sem par do próprio livro, é o
passo seguinte (F112 no ROADMAP).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import (Callable, Dict, Iterable, List, Mapping, Optional,
                    Sequence, Tuple)

import numpy as np

from core.avaliacao_pagina import normalizar
from core.box_model import BoxEntry

#: Os grupos de mesmo desenho, que só a geometria separa.
#:
#: A vírgula mora em dois: com o apóstrofo (a mesma marca, embaixo ou em cima) e
#: com o ponto (embaixo os dois, e só o pé os separa). O ponto e o apóstrofo **não**
#: se trocam: o que o recorte de um ponto alto costuma ser é o pingo de um `i`
#: partido (a família A da F109), e trocar `.` por `'` ali não conserta nada.
#: `i`, `l`, `1` e `I` são um grupo porque o corpo da haste do `i` fica na altura
#: de x; entre `l`, `1` e `I` a geometria não decide (os topos ficam a 0,1 altura
#: de x um do outro), e ali vale a ordem da rede.
GRUPOS: Tuple[str, ...] = ("cC", "oO0", "sS", "uU", "vV", "wW", "xX", "zZ",
                           "pP", "9gq", ",'’‘", ".,", "il1I")


def _grupos(grupos: Iterable[str]) -> Dict[str, frozenset]:
    saida: Dict[str, set] = {}
    for grupo in grupos:
        for c in grupo:
            saida.setdefault(c, set()).update(grupo)
    return {c: frozenset(g) for c, g in saida.items()}


_GRUPO_DE: Dict[str, frozenset] = _grupos(GRUPOS)

#: Custo (soma dos dois desvios padronizados ao quadrado) acima do qual a
#: leitura não cabe na linha. Medido nas páginas rotuladas, com a tabela de
#: fora do livro (`medir_geometria.py`): 9 e 4 são o par que dá mais consertos
#: sem quebra que não seja erro de gabarito.
VETO = 9.0

#: Custo abaixo do qual a substituta cabe. Mais estreito que `VETO` de propósito:
#: trocar pede que a outra caiba bem, e não que só caiba menos mal.
ACEITO = 4.0

#: O menor desvio que uma classe pode ter, em alturas de x. As páginas de PDF
#: nascido digital põem todo `a` no mesmo pixel, e o desvio medido é zero; a
#: página escaneada varia um ou dois pixels. 0,12 é o ponto da varredura.
PISO = 0.12

#: Quantas leituras, no mínimo, votam o corpo da linha. Com menos, a linha não
#: tem corpo, e nada é podado nela — é o cabeçalho de duas marcas e o número de
#: página, onde a mediana de dois votos é um dos dois.
APOIO = 4

#: O voto de quem pode estar com a caixa errada vale um quarto: o `S` lido no
#: lugar de `s` propõe o corpo errado, e é justamente dele que a linha precisa
#: discordar.
PESO_DO_GRUPO = 0.25

#: Só vota classe medida e estável: com `n` pequeno ou desvio grande, a classe
#: propõe um corpo que não quer dizer nada (o `P` do corpus mistura a letra e a
#: figurina do peão, e tem desvio 0,28).
MINIMO_PARA_VOTAR = 20
DESVIO_MAXIMO_DO_VOTO = 0.20

#: E só vota quem tem altura: o ponto e o hífen propõem corpo dividindo por
#: quase nada.
ALTURA_MINIMA_DO_VOTO = 0.3

#: Quantas candidatas pedir à rede quando a leitura não cabe. A substituta está
#: entre as 12 primeiras em todos os casos medidos; é o mesmo número do veto da
#: F106 (`proporcao.CANDIDATAS`).
CANDIDATAS = 12

#: Inclinação máxima da base, em pixels por pixel. Uma página torta de meio
#: grau passa por 0,009; 0,05 é quase três graus, e acima disso quem está
#: errado é a reta.
INCLINACAO_MAXIMA = 0.05

#: Contraste mínimo do recorte para haver tinta a medir.
CONTRASTE_MINIMO = 40

#: As letras que se apoiam na base, e as que têm o topo na altura de x — só para
#: estimar a linha **pela verdade**, na hora de montar a tabela.
SENTADAS = frozenset("abcdefhiklmnorstuvwxz" "ABCDEFGHIKLMNOPRSTUVWXYZ")
EM_X = frozenset("acemnorsuvwxz")

CAMINHO_DA_TABELA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "dados", "geometria_das_classes.json")


@dataclass(frozen=True)
class Classe:
    """Onde o corpo de uma classe começa e acaba, em alturas de x acima da base."""

    topo: float
    desvio_topo: float
    base: float
    desvio_base: float
    n: int

    @property
    def vota(self) -> bool:
        return (self.n >= MINIMO_PARA_VOTAR
                and max(self.desvio_topo, self.desvio_base) <= DESVIO_MAXIMO_DO_VOTO
                and self.topo - self.base >= ALTURA_MINIMA_DO_VOTO)


Tabela = Mapping[str, Classe]


@dataclass(frozen=True)
class Glifo:
    """O corpo de tinta de um box, em coordenadas da página."""

    topo: float
    base: float
    x: float


@dataclass(frozen=True)
class Linha:
    """A base da linha, `y = a + b·x`, e a altura de x dela."""

    a: float
    b: float
    altura_de_x: float

    def base_em(self, x: float) -> float:
        return self.a + self.b * x


# ----------------------------------------------------------------------
# A tabela
# ----------------------------------------------------------------------

def tabela_de(dados: Mapping) -> Dict[str, Classe]:
    """A tabela a partir do JSON (`{"classes": {char: [t, dt, b, db, n]}}`)."""
    return {c: Classe(*(float(v) for v in valores[:4]), int(valores[4]))
            for c, valores in dados.get("classes", {}).items()}


@lru_cache(maxsize=4)
def carregar_tabela(caminho: str = CAMINHO_DA_TABELA) -> Dict[str, Classe]:
    """A tabela gravada, ou vazia se não há arquivo — e sem tabela não há poda."""
    try:
        with open(caminho, encoding="utf-8") as f:
            return tabela_de(json.load(f))
    except (OSError, ValueError, TypeError, IndexError):
        return {}


def estimar_tabela(linhas: Iterable[Sequence[Tuple[Glifo, str]]],
                   minimo: int = 8) -> Dict[str, Classe]:
    """
    A tabela medida em linhas **cuja verdade se conhece** — `[(glifo, char)]`.

    A linha é estimada pela verdade: a base pelas letras sentadas e a altura de
    x pelas de topo em x, cada uma com pelo menos três e duas. Classe com menos
    de `minimo` ocorrências fica de fora: sem ela, a poda não tem opinião.
    """
    topos: Dict[str, List[float]] = {}
    bases: Dict[str, List[float]] = {}
    for linha in linhas:
        linha = [(g, c) for g, c in linha if g is not None and c]
        sentadas = [g for g, c in linha if c in SENTADAS]
        em_x = [g for g, c in linha if c in EM_X]
        if len(sentadas) < 3 or len(em_x) < 2:
            continue
        a, b = reta_robusta([g.x for g in sentadas], [g.base for g in sentadas])
        altura = float(np.median([a + b * g.x - g.topo for g in em_x]))
        if altura <= 2:
            continue
        for g, c in linha:
            base = a + b * g.x
            chave = normalizar(c)
            topos.setdefault(chave, []).append((base - g.topo) / altura)
            bases.setdefault(chave, []).append((base - g.base) / altura)
    tabela = {}
    for c, t in topos.items():
        if len(t) < minimo:
            continue
        t_arr, b_arr = np.asarray(t), np.asarray(bases[c])
        mt, mb = float(np.median(t_arr)), float(np.median(b_arr))
        tabela[c] = Classe(
            mt, float(1.4826 * np.median(np.abs(t_arr - mt))),
            mb, float(1.4826 * np.median(np.abs(b_arr - mb))), len(t))
    return tabela


def dados_da_tabela(tabela: Mapping[str, Classe], **extras) -> dict:
    """O inverso de `tabela_de`, com o que mais se quiser registrar junto."""
    return {"versao": 1, **extras,
            "classes": {c: [round(e.topo, 4), round(e.desvio_topo, 4),
                            round(e.base, 4), round(e.desvio_base, 4), e.n]
                        for c, e in sorted(tabela.items())}}


# ----------------------------------------------------------------------
# A medida
# ----------------------------------------------------------------------

def medir(recorte: np.ndarray, caixa: BoxEntry) -> Optional[Glifo]:
    """
    O corpo de tinta do recorte, ou `None` quando não há o que medir.

    O corpo é a faixa de linhas com tinta de **maior massa**: o pingo e o acento
    destacados ficam fora, e a caixa frouxa (a que a segmentação esticou para
    cobrir um pingo vizinho) é aparada à tinta que está dentro dela. Box girado
    (F8.1) não é medido — ali a linha não é horizontal.
    """
    if getattr(caixa, "angulo", 0):
        return None
    cinza = np.asarray(recorte)
    if cinza.ndim == 3:
        cinza = cinza.mean(axis=2)
    if cinza.size == 0:
        return None
    menor, maior = float(cinza.min()), float(cinza.max())
    if maior - menor < CONTRASTE_MINIMO:
        return None
    tinta = cinza < (menor + maior) / 2.0
    por_linha = tinta.sum(axis=1)
    com_tinta = por_linha > 0
    if not com_tinta.any():
        return None
    # Faixas contíguas de linhas com tinta, e a de maior massa.
    bordas = np.flatnonzero(np.diff(np.concatenate(([0], com_tinta.astype(np.int8), [0]))))
    faixas = list(zip(bordas[0::2], bordas[1::2]))
    inicio, fim = max(faixas, key=lambda f: int(por_linha[f[0]:f[1]].sum()))
    return Glifo(topo=float(caixa.y1 + inicio), base=float(caixa.y1 + fim),
                 x=(caixa.x1 + caixa.x2) / 2.0)


# ----------------------------------------------------------------------
# A linha
# ----------------------------------------------------------------------

def mediana_ponderada(valores: Sequence[float], pesos: Sequence[float]) -> float:
    v = np.asarray(valores, float)
    w = np.asarray(pesos, float)
    ordem = np.argsort(v)
    v, w = v[ordem], w[ordem]
    acumulado = np.cumsum(w)
    if acumulado[-1] <= 0:
        return float(np.median(v))
    k = int(np.searchsorted(acumulado, 0.5 * acumulado[-1]))
    return float(v[min(k, len(v) - 1)])


def reta_robusta(xs: Sequence[float], ys: Sequence[float],
                 pesos: Optional[Sequence[float]] = None) -> Tuple[float, float]:
    """
    `(a, b)` de `y = a + b·x`: inclinação de Theil-Sen, intercepto pela mediana.

    Só pares com pelo menos 15% da largura entre eles entram na inclinação —
    dois vizinhos colados dão qualquer inclinação com um pixel de diferença.
    """
    x = np.asarray(xs, float)
    y = np.asarray(ys, float)
    w = np.ones(len(x)) if pesos is None else np.asarray(pesos, float)
    b = 0.0
    if len(x) >= 3:
        dx = x[None, :] - x[:, None]
        dy = y[None, :] - y[:, None]
        vao = float(x.max() - x.min())
        par = np.triu(np.ones(dx.shape, bool), 1) & (np.abs(dx) > max(1.0, 0.15 * vao))
        if par.any():
            b = float(np.clip(np.median(dy[par] / dx[par]),
                              -INCLINACAO_MAXIMA, INCLINACAO_MAXIMA))
    return mediana_ponderada(y - b * x, w), b


def ajustar(glifos: Sequence[Optional[Glifo]],
            leituras: Sequence[Tuple[str, float]],
            tabela: Tabela) -> Optional[Linha]:
    """
    A base e a altura de x que as leituras da linha votam, ou `None`.

    Cada leitura de classe que vota propõe uma altura de x (a altura do corpo
    dividida pela da classe) e uma base; a linha fica com a mediana ponderada
    das alturas e com a reta robusta das bases.
    """
    xs: List[float] = []
    bases: List[float] = []
    alturas: List[float] = []
    pesos: List[float] = []
    for glifo, (char, conf) in zip(glifos, leituras):
        if glifo is None or not char:
            continue
        classe = tabela.get(normalizar(char))
        if classe is None or not classe.vota:
            continue
        altura = (glifo.base - glifo.topo) / (classe.topo - classe.base)
        xs.append(glifo.x)
        bases.append(glifo.base + classe.base * altura)
        alturas.append(altura)
        pesos.append(max(float(conf), 1e-3)
                     * (PESO_DO_GRUPO if char in _GRUPO_DE else 1.0))
    if len(alturas) < APOIO:
        return None
    altura_de_x = mediana_ponderada(alturas, pesos)
    if altura_de_x <= 0:
        return None
    a, b = reta_robusta(xs, bases, pesos)
    return Linha(a, b, altura_de_x)


def custo(glifo: Glifo, char: str, linha: Linha, tabela: Tabela) -> Optional[float]:
    """Quanto o corpo deste glifo destoa do da classe, nesta linha; `None` sem classe."""
    classe = tabela.get(normalizar(char))
    if classe is None:
        return None
    base = linha.base_em(glifo.x)
    zt = ((base - glifo.topo) / linha.altura_de_x - classe.topo) / max(classe.desvio_topo, PISO)
    zb = ((base - glifo.base) / linha.altura_de_x - classe.base) / max(classe.desvio_base, PISO)
    return zt * zt + zb * zb


# ----------------------------------------------------------------------
# A poda
# ----------------------------------------------------------------------

def _cabe(glifo: Glifo, char: str, linha: Linha, tabela: Tabela) -> bool:
    """A classe tem medida, e o glifo cabe nela com folga (`ACEITO`)."""
    valor = custo(glifo, char, linha, tabela)
    return valor is not None and valor <= ACEITO


def _e_digito(c: str) -> bool:
    return bool(c) and c.isdigit()


def _e_letra(c: str) -> bool:
    return bool(c) and c.isalpha()


def _contexto_admite(lida: str, nova: str, letra_ao_lado: bool,
                     digito_ao_lado: bool) -> bool:
    """Dígito vira letra só entre letras, e letra vira dígito só entre dígitos."""
    if _e_digito(lida) and _e_letra(nova):
        return letra_ao_lado and not digito_ao_lado
    if _e_letra(lida) and _e_digito(nova):
        return digito_ao_lado and not letra_ao_lado
    return True


def _vizinhos(i: int, caixas: Sequence[BoxEntry],
              leituras: Sequence[Tuple[str, float]],
              limiar_de_espaco: float) -> Tuple[bool, bool]:
    """`(há letra, há dígito)` entre os vizinhos do box na mesma palavra."""
    vizinhos = []
    if i > 0 and caixas[i].x1 - caixas[i - 1].x2 <= limiar_de_espaco:
        vizinhos.append(leituras[i - 1][0])
    if i + 1 < len(caixas) and caixas[i + 1].x1 - caixas[i].x2 <= limiar_de_espaco:
        vizinhos.append(leituras[i + 1][0])
    return (any(_e_letra(v) for v in vizinhos),
            any(_e_digito(v) for v in vizinhos))


def podar(caixas: Sequence[BoxEntry], recortes: Sequence[np.ndarray],
          leituras: Sequence[Tuple[str, float]],
          candidatas: Callable[[np.ndarray, int], Sequence[Tuple[str, float]]],
          *, limiar_de_espaco: float = float("inf"),
          limiar_de_confirmacao: Optional[float] = None,
          tabela: Optional[Tabela] = None) -> Dict[int, Tuple[str, float]]:
    """
    `{índice do box: (caractere, confiança)}` do que a geometria da linha muda.

    `caixas`, `recortes` e `leituras` são os da linha, alinhados, em ordem de x;
    `candidatas(recorte, k)` é o top-k da rede, e só é chamado para o box que a
    poda examina — a leitura que não cabe e, com `limiar_de_confirmacao`, a
    leitura fraca de um grupo. `limiar_de_espaco` é a régua do espaço da linha
    (`diagrama.limiar_de_espaco`), e diz quem é vizinho na mesma palavra.

    Sem tabela, sem corpo votado na linha, ou sem nada a mudar, devolve `{}` —
    e a linha sai como a rede a leu.
    """
    tabela = carregar_tabela() if tabela is None else tabela
    if not tabela or not caixas:
        return {}
    glifos = [medir(r, b) if r is not None and r.size else None
              for r, b in zip(recortes, caixas)]
    linha = ajustar(glifos, leituras, tabela)
    if linha is None:
        return {}

    trocas: Dict[int, Tuple[str, float]] = {}
    for i, (glifo, (lida, conf)) in enumerate(zip(glifos, leituras)):
        if glifo is None or lida not in _GRUPO_DE:
            continue
        grupo = _GRUPO_DE[lida]
        custo_lido = custo(glifo, lida, linha, tabela)
        if custo_lido is None:
            continue
        if custo_lido <= VETO:
            if (limiar_de_confirmacao is None or conf >= limiar_de_confirmacao
                    or custo_lido > ACEITO):
                continue
            # A leitura fraca que cabe: confirmada quando todo o resto do grupo
            # que a rede oferece não cabe.
            oferta = list(candidatas(recortes[i], CANDIDATAS))
            outros = [custo(glifo, c, linha, tabela)
                      for c, _p in oferta if c != lida and c in grupo]
            if outros and all(o is not None and o > VETO for o in outros):
                massa = sum(p for c, p in oferta if c in grupo)
                if massa > conf:
                    trocas[i] = (lida, float(massa))
            continue

        letra_ao_lado, digito_ao_lado = _vizinhos(i, caixas, leituras,
                                                  limiar_de_espaco)
        oferta = list(candidatas(recortes[i], CANDIDATAS))
        cabem = [char for char, _p in oferta
                 if char != lida and char in grupo
                 and _contexto_admite(lida, char, letra_ao_lado, digito_ao_lado)
                 and _cabe(glifo, char, linha, tabela)]
        if not cabem:
            continue
        # Entre as que cabem, a do tipo dos vizinhos: o `O` e o `0` têm o mesmo
        # corpo, e em `1o.a4` quem decide que é `10.a4` é o `1` ao lado.
        if digito_ao_lado and not letra_ao_lado:
            cabem.sort(key=lambda c: not _e_digito(c))
        elif letra_ao_lado and not digito_ao_lado:
            cabem.sort(key=lambda c: not _e_letra(c))
        massa = sum(p for c, p in oferta if c in grupo)
        trocas[i] = (cabem[0], float(max(conf, massa)))
    return trocas

