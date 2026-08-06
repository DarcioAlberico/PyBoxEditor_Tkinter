"""
A base de amostras dos diagramas, e o modelo que sai dela (F7.1, F8.3).

A F7.1 construiu o banco de peças com 361 amostras recortadas à mão e um script
para refazê-lo. Faltava o ciclo: **corrijo, e vai melhorando.** A correção do
tabuleiro morria na tela, e a única forma de crescer a base era voltar a
recortar casa por casa.

## A amostra é o resíduo, não a casa

O modelo lê `casa - fundo` (ver `core/diagrama.py`): a mediana das casas da
mesma cor é o fundo, e a peça é o que sobra. Guardar o recorte cru traria o
papel do livro junto, e o modelo aprenderia a digitalização em vez da peça. Por
isso a amostra é gravada como resíduo deslocado de 128 — que é o formato que a
F7.1 já usava, e que dá para olhar como imagem.

## Silêncio não é confirmação

Casa que o usuário não tocou **não** vira amostra por não ter sido tocada. Ela
entra por um "conferi este diagrama inteiro" explícito, e a razão é a mesma da
F2.3, que pergunta antes de reescrever o PDF: o que tem consequência pede ato,
não omissão. Sem isso a base cresceria enviesada para o que o modelo já acerta —
as casas que ele erra são exatamente as que o usuário mexe.

## O mesmo nome de amostra não pode viver em duas classes

Uma casa corrigida duas vezes (bispo, depois cavalo) grava com o mesmo nome de
procedência. Se a gravação só escrevesse na pasta nova, a antiga ficaria lá com
o rótulo desmentido — a mesma imagem em duas classes, que é o defeito da F1.4 e
o que a F7.2 encontrou na base de caracteres. `gravar` apaga a procedência das
outras classes antes de escrever.

## O número que mostra progresso é leave-one-out

Com 361 amostras não há conjunto de teste que se sustente: separar 20% deixaria
uma classe magra com uma amostra. A medida honesta é tirar **uma** amostra por
vez e classificá-la com as demais — é o que `avaliar` faz, com o mesmo voto de 3
vizinhos que a leitura usa.

**Ele é otimista, e o relatório diz isso.** Duas coisas o inflam: a base do PCA é
calculada com todas as amostras (refazê-la a cada uma custaria ~30 s), e amostras
quase idênticas — a mesma peça do mesmo diagrama — deixam o vizinho mais próximo
ser um gêmeo. O número serve para comparar rodadas, não para prometer acerto em
livro novo.

## Uma correção é um voto em três

Medido numa página real: a casa f7 era lida como `p`; guardada a correção `Q` e
retreinado, ela **continuou** saindo `p`. A amostra nova é o vizinho mais
próximo (similaridade 0,990), mas a leitura soma a similaridade dos **três**
mais próximos, e dois vizinhos `p` antigos somam 1,876 contra 0,990. Com duas
correções parecidas a soma vira, e a casa passa a ler `Q`.

Não é defeito, é a aritmética do classificador da F7.1 — e é o que faz o
"corrijo e vai progredindo" ser progressivo de verdade em vez de uma amostra
mandar sozinha. O relatório de treino diz isso, porque é depois de treinar que
a expectativa se forma.
"""

import collections
import datetime
import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from core import diagrama as diag
from core.diagrama import LADO, SIMBOLOS


#: Onde as amostras moram. `<pasta>/<cor>/<LETRA>/<procedencia>.png`.
PASTA_PADRAO = "training_data_diagrama"

#: Componentes do PCA. Com 64 e 128 o acerto é o mesmo e o arquivo cresce.
COMPONENTES = 32

#: Vizinhos no voto — o mesmo número que `diagrama._pontuar` usa.
VIZINHOS = 3

#: Abaixo disto a classe é magra: são as que mais erram (medido na F7.1).
MIN_POR_CLASSE = 12

_CORES = {"branca": str.upper, "preta": str.lower}


# ----------------------------------------------------------------------
# A base: ler, gravar, conferir
# ----------------------------------------------------------------------

def _pasta_da_classe(pasta: str, simbolo: str) -> str:
    cor = "branca" if simbolo.isupper() else "preta"
    return os.path.join(pasta, cor, simbolo.upper())


def _nome_de_arquivo(origem: str, casa: str) -> str:
    """
    Procedência -> nome de arquivo, sem nada que o sistema recuse.

    O nome é **determinístico**: conferir o mesmo diagrama duas vezes regrava
    os mesmos arquivos em vez de duplicar a base. E leva uma marca curta da
    procedência inteira, porque o texto é truncado para o nome não ficar
    impossível — sem a marca, duas páginas de nome parecido colidiriam e uma
    apagaria as amostras da outra.
    """
    limpo = re.sub(r"[^A-Za-z0-9_.-]+", "_", origem).strip("_")[:40]
    marca = hashlib.sha256(origem.encode("utf-8")).hexdigest()[:6]
    return f"{limpo or 'manual'}_{marca}_{casa}.png"


def gravar(residuo: np.ndarray, simbolo: str, origem: str = "", casa: str = "",
           pasta: Optional[str] = None) -> Optional[str]:
    """
    Grava uma amostra. Devolve o caminho, ou None se o símbolo não for peça.

    Apaga antes a mesma procedência das outras classes: a casa corrigida duas
    vezes não pode acabar rotulada das duas maneiras (ver o cabeçalho).

    A pasta é lida **na chamada**, e não como valor padrão: `def f(p=CONST)`
    congela a constante na definição, e quem aponta o módulo para outra base
    mexeria numa variável que ninguém mais lê. Foi a armadilha que a F8.1
    documentou.
    """
    pasta = PASTA_PADRAO if pasta is None else pasta
    if simbolo not in SIMBOLOS:
        return None
    nome = _nome_de_arquivo(origem, casa or "x")

    for outro in SIMBOLOS:
        antigo = os.path.join(_pasta_da_classe(pasta, outro), nome)
        if outro != simbolo and os.path.isfile(antigo):
            os.remove(antigo)

    destino = _pasta_da_classe(pasta, simbolo)
    os.makedirs(destino, exist_ok=True)
    imagem = np.clip(np.asarray(residuo, dtype=np.float32) + 128.0, 0, 255)
    if imagem.shape[:2] != (LADO, LADO):
        imagem = cv2.resize(imagem, (LADO, LADO), interpolation=cv2.INTER_AREA)
    caminho = os.path.join(destino, nome)
    cv2.imwrite(caminho, imagem.astype(np.uint8))
    return caminho


def colher(imagem, leitura, tabuleiro, origem: str = "",
           tudo: bool = False, pasta: Optional[str] = None) -> List[str]:
    """
    As amostras de um diagrama conferido. Devolve os caminhos gravados.

    `tudo=False` grava só o que a mão mexeu; `tudo=True` grava todas as casas
    ocupadas, e é o que o "conferi este diagrama inteiro" liga.

    **Casa esvaziada não vira amostra**, e não é esquecimento: o modelo tem 12
    classes de peça e nenhuma de casa vazia — quem decide vazia/ocupada é o
    limiar de Otsu da F7.1, antes do classificador. Corrigir um falso positivo
    conserta o FEN e não tem onde ser aprendido.
    """
    pasta = PASTA_PADRAO if pasta is None else pasta
    residuos, _ = diag.residuos(imagem, leitura.caixa)
    if not residuos:
        return []

    gravados = []
    for casa in tabuleiro.casas:
        if not casa.simbolo:
            continue
        if not (tudo or casa.corrigida):
            continue
        residuo = residuos.get((casa.linha, casa.coluna))
        if residuo is None:
            continue
        caminho = gravar(residuo, casa.simbolo, origem, casa.nome, pasta)
        if caminho:
            gravados.append(caminho)
    return gravados


def carregar_amostras(pasta: Optional[str] = None
                      ) -> List[Tuple[str, np.ndarray, str]]:
    """[(símbolo, resíduo, caminho)] a partir de `<pasta>/<cor>/<LETRA>/*.png`."""
    pasta = PASTA_PADRAO if pasta is None else pasta
    saida = []
    for cor, caixa in _CORES.items():
        base = os.path.join(pasta, cor)
        if not os.path.isdir(base):
            continue
        for letra in sorted(os.listdir(base)):
            simbolo = caixa(letra)
            if simbolo not in SIMBOLOS:
                continue
            for nome in sorted(os.listdir(os.path.join(base, letra))):
                if not nome.endswith(".png"):
                    continue
                caminho = os.path.join(base, letra, nome)
                img = cv2.imread(caminho, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    saida.append((simbolo, img.astype(np.float32) - 128.0,
                                  caminho))
    return saida


def contagem(pasta: Optional[str] = None) -> Dict[str, int]:
    """Quantas amostras por símbolo, sem ler os PNGs."""
    pasta = PASTA_PADRAO if pasta is None else pasta
    saida = {s: 0 for s in SIMBOLOS}
    for cor, caixa in _CORES.items():
        base = os.path.join(pasta, cor)
        if not os.path.isdir(base):
            continue
        for letra in sorted(os.listdir(base)):
            simbolo = caixa(letra)
            if simbolo in saida:
                saida[simbolo] = sum(
                    1 for n in os.listdir(os.path.join(base, letra))
                    if n.endswith(".png"))
    return saida


def impressao(pasta: Optional[str] = None) -> str:
    """
    Impressão digital da base, pela contagem por classe.

    É a escolha da F7.2, pelo mesmo motivo: contar arquivos custa nada e pega
    tudo que muda a base na prática. Trocar uma amostra por outra sem mexer na
    contagem só acontece de propósito.
    """
    corpo = ";".join(f"{s}:{n}" for s, n in sorted(contagem(pasta).items()))
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16]


def modelo_desatualizado(pasta: Optional[str] = None) -> bool:
    """A base mudou depois do último treino? (F7.3 aplicada aqui.)"""
    gravada = diag.impressao_do_modelo()
    return bool(gravada) and gravada != impressao(pasta)


@dataclass
class Problema:
    tipo: str          # rotulo_contraditorio | classe_vazia | tamanho | classe_magra
    detalhe: str
    grave: bool = True

    def __str__(self):
        return f"[{'ERRO ' if self.grave else 'aviso'}] {self.detalhe}"


def conferir(pasta: Optional[str] = None) -> List[Problema]:
    """
    O que está errado na base de diagramas. Vazio = pode treinar.

    A conferência da F1.4 aplicada aqui, com uma diferença deliberada: imagem
    idêntica com rótulos diferentes é **erro grave**, e não aviso. Na base de
    caracteres a F7.2 concluiu que os dois rótulos podiam estar certos para
    ocorrências diferentes ('1' e 'l' viram o mesmo desenho depois do recorte);
    num diagrama não há esse contexto — um bispo é um bispo.
    """
    pasta = PASTA_PADRAO if pasta is None else pasta
    problemas = []
    amostras = carregar_amostras(pasta)

    porto = collections.defaultdict(set)
    for simbolo, residuo, caminho in amostras:
        if residuo.shape[:2] != (LADO, LADO):
            problemas.append(Problema(
                "tamanho", f"{caminho}: {residuo.shape[1]}x{residuo.shape[0]}, "
                           f"esperado {LADO}x{LADO}", grave=False))
        chave = hashlib.sha256(
            np.ascontiguousarray(residuo.astype(np.float32)).tobytes()).hexdigest()
        porto[chave].add(simbolo)

    for chave, simbolos in porto.items():
        if len(simbolos) > 1:
            problemas.append(Problema(
                "rotulo_contraditorio",
                f"a mesma imagem está rotulada como {' e '.join(sorted(simbolos))}"))

    conta = collections.Counter(s for s, _, _ in amostras)
    for simbolo in SIMBOLOS:
        if conta[simbolo] == 0:
            problemas.append(Problema(
                "classe_vazia", f"a classe '{simbolo}' não tem amostra nenhuma",
                grave=False))
        elif conta[simbolo] < MIN_POR_CLASSE:
            problemas.append(Problema(
                "classe_magra",
                f"'{simbolo}' tem {conta[simbolo]} amostras (mínimo saudável: "
                f"{MIN_POR_CLASSE}) — são as que mais erram", grave=False))
    return problemas


# ----------------------------------------------------------------------
# O modelo
# ----------------------------------------------------------------------

@dataclass
class Relatorio:
    """O que uma rodada de treino tem a dizer."""

    total: int = 0
    contagem: Dict[str, int] = field(default_factory=dict)
    acerto: float = 0.0
    acerto_por_classe: Dict[str, float] = field(default_factory=dict)
    problemas: List[Problema] = field(default_factory=list)
    destino: str = ""
    bytes_gravados: int = 0

    @property
    def magras(self) -> List[str]:
        return [s for s in SIMBOLOS if 0 < self.contagem.get(s, 0) < MIN_POR_CLASSE]

    def texto(self) -> str:
        linhas = [f"{self.total} amostras, {COMPONENTES} dimensões",
                  "  " + "  ".join(f"{s}:{self.contagem.get(s, 0)}"
                                   for s in "PNBRQKpnbrqk")]
        if self.total:
            linhas.append(
                f"acerto leave-one-out: {self.acerto:.1%}  "
                f"(otimista: PCA com todas as amostras, e amostras quase "
                f"idênticas se ajudam)")
            piores = sorted(self.acerto_por_classe.items(), key=lambda kv: kv[1])
            linhas.append("  piores classes: " + "  ".join(
                f"{s}:{v:.0%}" for s, v in piores[:4]))
        if self.destino:
            linhas.append(
                f"gravado em {self.destino} ({self.bytes_gravados / 1e3:.0f} KB)")
        if self.magras:
            linhas.append(f"classes com menos de {MIN_POR_CLASSE} amostras: "
                          + " ".join(self.magras))
            linhas.append("são as que mais erram; conferir mais diagramas "
                          "ajuda essas primeiro.")
        if self.total:
            # O usuário corrige uma casa, retreina, relê e não vê mudança —
            # e conclui que não funcionou. O aviso vem junto do número porque
            # é aqui que a expectativa se forma. Medido, não estimado.
            linhas.append(
                "A leitura é o voto dos 3 vizinhos mais próximos: medido, uma "
                "correção sozinha não vira uma casa (0,99 contra 1,88 de dois "
                "vizinhos antigos) e duas viram.")
        for p in self.problemas:
            linhas.append(str(p))
        return "\n".join(linhas)


def avaliar(reduzido: np.ndarray, simbolos: Sequence[str],
            vizinhos: int = VIZINHOS) -> Tuple[float, Dict[str, float]]:
    """
    Acerto leave-one-out, com o mesmo voto que a leitura usa.

    Repete `diagrama._pontuar` de propósito — soma da similaridade positiva
    dos `vizinhos` mais próximos, por classe — porque medir com outro
    critério mediria outro classificador.
    """
    n = len(simbolos)
    if n < 2:
        return 0.0, {}

    similaridade = reduzido @ reduzido.T
    np.fill_diagonal(similaridade, -np.inf)

    certos = collections.Counter()
    totais = collections.Counter(simbolos)
    for i in range(n):
        pontos = collections.Counter()
        for j in np.argsort(similaridade[i])[::-1][:vizinhos]:
            pontos[simbolos[j]] += max(0.0, float(similaridade[i, j]))
        if pontos and max(pontos, key=pontos.get) == simbolos[i]:
            certos[simbolos[i]] += 1

    por_classe = {s: certos[s] / totais[s] for s in totais}
    return sum(certos.values()) / n, por_classe


def treinar(pasta: Optional[str] = None, destino: Optional[str] = None,
            avaliar_loo: bool = True) -> Relatorio:
    """
    Refaz o banco de vizinhos a partir das amostras. Devolve o relatório.

    O `.npz` leva a impressão da base que o gerou (F7.3 aplicada aqui): sem
    ela, acrescentar amostras e esquecer de treinar é indistinguível de ter
    treinado, e o programa segue lendo com o banco velho sem dizer nada.
    """
    pasta = PASTA_PADRAO if pasta is None else pasta
    destino = diag.CAMINHO_MODELO if destino is None else destino
    amostras = carregar_amostras(pasta)
    relatorio = Relatorio(total=len(amostras),
                          contagem=dict(collections.Counter(
                              s for s, _, _ in amostras)),
                          problemas=conferir(pasta))
    if not amostras:
        return relatorio

    simbolos = [s for s, _, _ in amostras]
    X = np.stack([diag.descritor(r) for _, r, _ in amostras]).astype(np.float32)

    media = X.mean(axis=0)
    # SVD e não uma lib de PCA: numpy já está aqui e são 361 x 1764.
    _, _, Vt = np.linalg.svd(X - media, full_matrices=False)
    base = Vt[:COMPONENTES].astype(np.float32)

    reduzido = (X - media) @ base.T
    reduzido /= np.linalg.norm(reduzido, axis=1, keepdims=True) + 1e-6

    if avaliar_loo:
        relatorio.acerto, relatorio.acerto_por_classe = avaliar(reduzido, simbolos)

    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    np.savez_compressed(
        destino, media=media, base=base,
        amostras=reduzido.astype(np.float32), simbolos=np.array(simbolos),
        impressao=np.array(impressao(pasta)),
        treinado_em=np.array(datetime.datetime.now().isoformat(timespec="seconds")))

    relatorio.destino = destino
    relatorio.bytes_gravados = os.path.getsize(destino)
    if os.path.abspath(destino) == os.path.abspath(diag.CAMINHO_MODELO):
        diag.esquecer_modelo()
    return relatorio
