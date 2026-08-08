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

## O número é medido em diagramas que ficaram fora do treino

Era leave-one-out — tirar uma amostra por vez e classificá-la com as demais — e
o relatório avisava que aquilo era otimista. **A F7.4 mediu o quanto**: com o
classificador antigo, o leave-one-out solto dava 93,5% e a mesma base separada
por diagrama dava 93,8%, mas um livro inteiro deixado de fora derrubava para
86,9%. A distância entre os dois números é o que o gêmeo escondia — duas casas
do mesmo diagrama saíram do mesmo recorte, com a mesma fonte e o mesmo fundo
estimado.

Agora `separar_por_diagrama` põe 20% dos **diagramas** de lado, treina sem eles
e mede neles. Continua otimista para um livro novo, que traz outra fonte de
peças, e o relatório continua dizendo isso — é a lição da F1.3, a acurácia que
não diz em que dados foi medida vale zero.

**Duas redes por rodada, não uma.** A que dá o número não viu os diagramas de
teste; a que vai para o disco viu tudo. Medir na segunda seria medir a memória
dela.

## O que uma correção faz, agora que é uma rede

Com o k-NN a resposta era aritmética e exata: a amostra nova virava o vizinho
mais próximo (similaridade 0,990) e mesmo assim perdia para dois vizinhos
antigos (1,876), então uma correção não virava a casa e duas viravam.

Com a rede não há vizinho: o gradiente de uma amostra entre 833 é diluído por 80
épocas de todas as outras. Uma correção isolada muda a leitura quando a casa já
estava em dúvida, e não muda quando a rede estava confiante e errada. O que
move o ponteiro é conferir **diagramas inteiros**, sobretudo das classes magras
— e é isso que o relatório passou a dizer, porque é depois de treinar que a
expectativa se forma.
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
from core.diagrama import CLASSES, LADO, OCUPADA, SIMBOLOS, VAZIA


#: Onde as amostras de PEÇA moram. `<pasta>/<cor>/<LETRA>/<procedencia>.png`.
PASTA_PADRAO = "training_data_diagrama"

#: Onde as amostras de OCUPAÇÃO moram, `<pasta>/{vazia,ocupada}/*.png`.
#:
#: **Base separada, e não uma classe a mais na de peças** — foi a medição que
#: separou, não o gosto. As duas perguntas precisam de amostras diferentes:
#: identidade se aprende com peças recortadas de onde o leitor já as achou;
#: ocupação se aprende com **tabuleiros inteiros**, incluindo as casas que o
#: leitor errou. Treinar a rede de ocupação com as peças da base de identidade
#: dá 91,88% — quase o Otsu que ela veio substituir —, porque aquelas peças são
#: justamente as que o Otsu já achava fáceis. Com as casas transcritas, 99,31%.
PASTA_OCUPACAO = "training_data_ocupacao"

#: Passadas pela base. Com 833 amostras são ~20 s em CPU; 40 e 160 dão o mesmo
#: acerto no livro deixado de fora, então 80 é meio do platô.
EPOCAS = 80

#: Amostras por passo.
LOTE = 32

#: Semente do treino. Fixa porque duas rodadas seguidas na mesma base têm de dar
#: o mesmo modelo — sem isso, "retreinei e mudou" nunca distingue a amostra nova
#: do sorteio.
SEMENTE = 20260807

#: Fração de **diagramas** (não de amostras) que fica fora do treino para medir.
FRACAO_DE_TESTE = 0.2

#: Com menos diagramas que isto não há conjunto de teste que se sustente, e o
#: relatório diz isso em vez de inventar um número.
MIN_DIAGRAMAS_PARA_MEDIR = 5

#: Abaixo disto a classe é magra: são as que mais erram (medido na F7.1).
MIN_POR_CLASSE = 12


# ----------------------------------------------------------------------
# A base: ler, gravar, conferir
# ----------------------------------------------------------------------

def _pasta_da_classe(pasta: str, simbolo: str) -> str:
    if simbolo in (VAZIA, OCUPADA):
        # As duas classes da ocupação moram noutra base e não têm cor: a pasta
        # reflete isso em vez de fingir que casa vazia é branca ou preta.
        return os.path.join(pasta, "vazia" if simbolo == VAZIA else "ocupada")
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
    if simbolo not in CLASSES + (OCUPADA,):
        return None
    nome = _nome_de_arquivo(origem, casa or "x")

    for outro in CLASSES + (OCUPADA,):
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
           tudo: bool = False, pasta: Optional[str] = None,
           pasta_ocupacao: Optional[str] = None) -> List[str]:
    """
    As amostras de um diagrama conferido. Devolve os caminhos gravados.

    `tudo=False` grava só o que a mão mexeu; `tudo=True` grava todas as casas,
    e é o que o "conferi este diagrama inteiro" liga.

    **Casa esvaziada virou amostra na F7.5**, e antes não era. O motivo de não
    ser está registrado e deixou de valer: "o modelo tem 12 classes de peça e
    nenhuma de casa vazia — quem decide vazia/ocupada é o limiar de Otsu, antes
    do classificador; corrigir um falso positivo conserta o FEN e não tem onde
    ser aprendido". Agora tem, e não é uma classe a mais: é a base de ocupação,
    onde apagar uma peça que a rede inventou é exatamente o exemplo que falta.

    **É o buraco mais caro que o ciclo da F8.3 tinha.** Medido no gabarito, o
    Otsu punha 38 peças onde não havia nenhuma e perdia 86 que havia — e nenhuma
    dessas 124 correções tinha onde ser aprendida. Com o diagrama conferido
    inteiro, as 64 casas entram na base de ocupação, ocupadas e vazias, que é a
    única forma de ela ver as casas que o leitor **errou**.
    """
    pasta = PASTA_PADRAO if pasta is None else pasta
    pasta_ocupacao = PASTA_OCUPACAO if pasta_ocupacao is None else pasta_ocupacao
    residuos, _ = diag.residuos(imagem, leitura.caixa)
    if not residuos:
        return []

    gravados = []
    for casa in tabuleiro.casas:
        if not (tudo or casa.corrigida):
            continue
        residuo = residuos.get((casa.linha, casa.coluna))
        if residuo is None:
            continue
        if casa.simbolo:
            caminho = gravar(residuo, casa.simbolo, origem, casa.nome, pasta)
            if caminho:
                gravados.append(caminho)
        # A ocupação leva as duas classes, e leva sempre: é a base cuja graça é
        # cobrir o tabuleiro inteiro.
        caminho = gravar(residuo, OCUPADA if casa.simbolo else VAZIA,
                         origem, casa.nome, pasta_ocupacao)
        if caminho:
            gravados.append(caminho)
    return gravados


def carregar_amostras(pasta: Optional[str] = None
                      ) -> List[Tuple[str, np.ndarray, str]]:
    """[(símbolo, resíduo, caminho)] das pastas de classe que existirem.

    Serve às duas bases: a de peças tem `<cor>/<LETRA>/`, a de ocupação tem
    `vazia/` e `ocupada/`. Pasta que não existe simplesmente não contribui.
    """
    pasta = PASTA_PADRAO if pasta is None else pasta
    saida = []
    for simbolo in CLASSES + (OCUPADA,):
        base = _pasta_da_classe(pasta, simbolo)
        if not os.path.isdir(base):
            continue
        for nome in sorted(os.listdir(base)):
            if not nome.endswith(".png"):
                continue
            caminho = os.path.join(base, nome)
            img = cv2.imread(caminho, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                saida.append((simbolo, img.astype(np.float32) - 128.0, caminho))
    return saida


def contagem(pasta: Optional[str] = None) -> Dict[str, int]:
    """Quantas amostras por classe, sem ler os PNGs. Só as classes que existem."""
    pasta = PASTA_PADRAO if pasta is None else pasta
    saida = {}
    for simbolo in CLASSES + (OCUPADA,):
        base = _pasta_da_classe(pasta, simbolo)
        if simbolo in (VAZIA, OCUPADA) and not os.path.isdir(base):
            # Classe de outra base: ausente é o normal, e listá-la em zero
            # poluiria a impressão digital e o relatório.
            continue
        saida[simbolo] = (sum(1 for n in os.listdir(base) if n.endswith(".png"))
                          if os.path.isdir(base) else 0)
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
    # As classes que se espera nesta pasta: as da base que ela é.
    esperadas = ((VAZIA, OCUPADA) if conta[VAZIA] or conta[OCUPADA]
                 else SIMBOLOS)
    for simbolo in esperadas:
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
    casas_de_teste: int = 0
    diagramas_de_teste: int = 0
    temperatura: float = 1.0
    # A segunda rede, medida em separado (F7.5). Num número só, um avanço na
    # ocupação esconderia uma queda na identidade — e as duas têm bases de
    # origem diferentes: a ocupação vem de tabuleiro inteiro transcrito, a
    # identidade vem do fluxo de correção da F8.3.
    total_ocupacao: int = 0
    acerto_ocupacao: float = 0.0
    casas_de_ocupacao: int = 0
    diagramas_de_ocupacao: int = 0
    destino_ocupacao: str = ""
    bytes_ocupacao: int = 0
    problemas: List[Problema] = field(default_factory=list)
    destino: str = ""
    bytes_gravados: int = 0

    @property
    def magras(self) -> List[str]:
        return [s for s in CLASSES if 0 < self.contagem.get(s, 0) < MIN_POR_CLASSE]

    def texto(self) -> str:
        linhas = [f"{self.total} amostras de peça",
                  "  " + "  ".join(f"{s}:{self.contagem.get(s, 0)}"
                                   for s in "PNBRQKpnbrqk"),
                  f"{self.total_ocupacao} amostras de ocupação"]
        if self.casas_de_teste:
            linhas.append("em diagramas que ficaram fora do treino:")
            linhas.append(
                f"  qual peça é    {self.acerto:.1%}  "
                f"({self.casas_de_teste} casas de {self.diagramas_de_teste} "
                f"diagramas)")
            if self.casas_de_ocupacao:
                linhas.append(
                    f"  há peça?       {self.acerto_ocupacao:.1%}  "
                    f"({self.casas_de_ocupacao} casas de "
                    f"{self.diagramas_de_ocupacao} diagramas)")
            piores = sorted(self.acerto_por_classe.items(), key=lambda kv: kv[1])
            linhas.append("  piores classes: " + "  ".join(
                f"{s}:{v:.0%}" for s, v in piores[:4]))
            # O número que engana é pior que o que falta (F1.3). Este separa
            # diagramas inteiros, então não é o leave-one-out otimista de antes
            # — mas ainda mistura livros, e livro novo traz fonte nova.
            linhas.append(
                "  nenhuma casa desses diagramas entrou no treino; ainda assim "
                "é otimista para um livro novo, que traz outra fonte de peças.")
        elif self.total:
            linhas.append(
                f"sem medição: são precisos {MIN_DIAGRAMAS_PARA_MEDIR} diagramas "
                f"de procedências diferentes para separar um conjunto de teste.")
        if self.destino:
            linhas.append(
                f"gravado em {self.destino} ({self.bytes_gravados / 1e3:.0f} KB)")
        if self.destino_ocupacao:
            linhas.append(
                f"gravado em {self.destino_ocupacao} "
                f"({self.bytes_ocupacao / 1e3:.0f} KB)")
        if self.magras:
            linhas.append(f"classes com menos de {MIN_POR_CLASSE} amostras: "
                          + " ".join(self.magras))
            linhas.append("são as que mais erram; conferir mais diagramas "
                          "ajuda essas primeiro.")
        if self.total:
            # O usuário corrige uma casa, retreina, relê e não vê mudança — e
            # conclui que não funcionou. O aviso vem junto do número porque é
            # aqui que a expectativa se forma. Era a aritmética do voto de três
            # vizinhos (F8.3); com a rede é outra coisa, e continua sendo
            # medida e não estimada: ver o cabeçalho do módulo.
            linhas.append(
                "A rede aprende a base inteira de uma vez: uma correção só "
                "muda a leitura se a casa já estivesse em dúvida. O que faz "
                "diferença é conferir diagramas inteiros das classes magras.")
        for p in self.problemas:
            linhas.append(str(p))
        return "\n".join(linhas)


# ----------------------------------------------------------------------
# Medir: separar por diagrama, nunca por amostra
# ----------------------------------------------------------------------

def grupo_da_amostra(caminho: str) -> str:
    """
    De que diagrama esta amostra veio, lido do nome do arquivo.

    **Sem isto não há medição honesta.** Duas casas do mesmo diagrama saíram do
    mesmo recorte, com a mesma fonte, a mesma digitalização e o mesmo fundo
    estimado: deixar uma no treino e a outra no teste mede memorização. Era
    justamente o que inflava o leave-one-out da F8.3, e ele avisava.

    Dois formatos de nome, porque a base tem duas gerações: `diag_07_c1.png` é
    da leva recortada à mão na F7.1, e `<livro>_<marca>_<casa>.png` é o que
    `_nome_de_arquivo` grava desde a F8.3 — a marca é o resumo da procedência,
    que é página e diagrama. Nome que não bate com nenhum dos dois vira grupo de
    um: é o palpite conservador, porque nunca junta o que devia estar separado.
    """
    nome = os.path.basename(caminho)
    m = re.match(r"(diag_\d+)_", nome)
    if m:
        return m.group(1)
    m = re.search(r"_([0-9a-f]{6})_[a-h][1-8]\.png$", nome)
    return m.group(1) if m else nome


def separar_por_diagrama(caminhos: Sequence[str],
                         fracao: float = FRACAO_DE_TESTE,
                         semente: int = SEMENTE) -> Tuple[List[int], List[int]]:
    """
    (índices de treino, índices de teste), sem partir um diagrama entre os dois.

    Devolve `([], [])` quando não há diagramas suficientes — quem chama decide o
    que dizer, e o relatório diz que não mediu em vez de medir mal.
    """
    grupos = collections.OrderedDict()
    for i, c in enumerate(caminhos):
        grupos.setdefault(grupo_da_amostra(c), []).append(i)
    if len(grupos) < MIN_DIAGRAMAS_PARA_MEDIR:
        return [], []

    nomes = list(grupos)
    np.random.default_rng(semente).shuffle(nomes)
    quantos = max(1, int(round(len(nomes) * fracao)))
    teste = {n for n in nomes[:quantos]}
    return ([i for n in nomes[quantos:] for i in grupos[n]],
            [i for n in nomes[:quantos] for i in grupos[n]])


# ----------------------------------------------------------------------
# A rede
# ----------------------------------------------------------------------

def _pesos_das_classes(y, num_classes):
    """
    Peso inverso à frequência: a classe magra não pode sumir na média.

    O peão preto tem 205 amostras e a dama branca 26. Sem peso, errar todas as
    damas custa 3% da perda e a rede aceita o negócio — e são justamente as
    classes magras que a F7.1 apontou como as que mais erram.
    """
    import torch

    contagem = torch.bincount(y, minlength=num_classes).float()
    peso = torch.where(contagem > 0, contagem.sum() / (contagem + 1e-6), 0.0)
    return peso / peso.mean()


def _deslocar(X):
    """Aumento de dados: ±2 px em cada eixo.

    Só translação. **Espelhar seria estragar a base**: peça preta não é peça
    branca virada, e um cavalo espelhado não existe no material — o modelo
    aprenderia uma variação que a página nunca traz, gastando capacidade.
    """
    import torch

    n = X.shape[0]
    dx = torch.randint(-2, 3, (n,))
    dy = torch.randint(-2, 3, (n,))
    saida = torch.empty_like(X)
    for i in range(n):
        saida[i] = torch.roll(X[i], (int(dy[i]), int(dx[i])), dims=(1, 2))
    return saida


def treinar_rede(X, y, num_classes: int, epocas: int = EPOCAS,
                 semente: int = SEMENTE, progresso=None):
    """Uma `RedeDiagrama` treinada, em modo de leitura."""
    import torch
    import torch.nn as nn
    from core.neural_model import RedeDiagrama

    torch.manual_seed(semente)
    rede = RedeDiagrama(num_classes)
    otimizador = torch.optim.Adam(rede.parameters(), lr=1e-3, weight_decay=1e-4)
    perda_fn = nn.CrossEntropyLoss(weight=_pesos_das_classes(y, num_classes))

    rede.train()
    for epoca in range(epocas):
        ordem = torch.randperm(len(X))
        for i in range(0, len(ordem), LOTE):
            idx = ordem[i:i + LOTE]
            otimizador.zero_grad()
            perda_fn(rede(_deslocar(X[idx])), y[idx]).backward()
            otimizador.step()
        if progresso is not None and (epoca + 1) % 20 == 0:
            progresso(f"treinando: época {epoca + 1} de {epocas}")
    rede.eval()
    return rede


def _lote(amostras, simbolos: Sequence[str], indices=None):
    """(entrada da rede, rótulos) para as amostras pedidas."""
    import torch

    indices = range(len(amostras)) if indices is None else indices
    residuos = [amostras[i][1] for i in indices]
    y = torch.tensor([simbolos.index(amostras[i][0]) for i in indices],
                     dtype=torch.long)
    return diag.entrada_da_rede(residuos), y


@dataclass
class Medida:
    """O que uma rodada de avaliação apurou."""

    acerto: float = 0.0
    por_classe: Dict[str, float] = field(default_factory=dict)
    temperatura: float = 1.0
    casas: int = 0
    diagramas: int = 0


def _treinar_e_gravar(amostras, simbolos, destino, pasta, medir, progresso):
    """Mede (se pedido), treina com tudo e grava. Devolve a `Medida`."""
    import torch

    medida = Medida()
    if medir:
        treino, teste = separar_por_diagrama([c for _, _, c in amostras])
        if teste:
            medida = avaliar(amostras, simbolos, treino, teste, progresso)

    X, y = _lote(amostras, simbolos)
    rede = treinar_rede(X, y, len(simbolos), progresso=progresso)

    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    torch.save({"pesos": rede.state_dict(),
                "simbolos": list(simbolos),
                "lado": diag.LADO_REDE,
                "temperatura": float(medida.temperatura),
                "impressao": impressao(pasta),
                "treinado_em": datetime.datetime.now().isoformat(
                    timespec="seconds")},
               destino)
    return medida


def avaliar(amostras, simbolos: Sequence[str], treino: Sequence[int],
            teste: Sequence[int], progresso=None) -> Medida:
    """
    O que a rede acerta nos diagramas que ficaram de fora.

    **A temperatura sai daqui e não do modelo final**, e é a F1.9 aplicada a
    esta base: a rede acerta 98% e diz 99,9% de confiança em quase tudo, e é
    dessa confiança que a janela de diagramas tira o laranja de "duvidoso". Sem
    calibrar, o laranja pararia de aparecer justamente quando fosse útil.
    Calibrar não muda nenhuma leitura — a temperatura divide todos os logitos,
    então a ordem das classes é a mesma; muda só o número exibido.
    """
    import torch
    from core import calibracao

    Xtr, ytr = _lote(amostras, simbolos, treino)
    Xte, yte = _lote(amostras, simbolos, teste)
    rede = treinar_rede(Xtr, ytr, len(simbolos), progresso=progresso)
    with torch.no_grad():
        logitos = rede(Xte).numpy()

    verdade = yte.numpy()
    certo = logitos.argmax(axis=1) == verdade
    por_classe = {}
    for k, s in enumerate(simbolos):
        m = verdade == k
        if m.any():
            por_classe[s] = float(certo[m].mean())

    aceitaveis = np.zeros(logitos.shape, dtype=bool)
    aceitaveis[np.arange(len(verdade)), verdade] = True
    return Medida(
        acerto=float(certo.mean()),
        por_classe=por_classe,
        temperatura=calibracao.ajustar_temperatura(logitos, aceitaveis),
        casas=len(teste),
        diagramas=len({grupo_da_amostra(amostras[i][2]) for i in teste}))


def treinar(pasta: Optional[str] = None, destino: Optional[str] = None,
            medir: bool = True, progresso=None,
            pasta_ocupacao: Optional[str] = None,
            destino_ocupacao: Optional[str] = None) -> Relatorio:
    """
    Refaz os dois modelos do diagrama. Devolve o relatório.

    **Dois, e não um**: a rede que diz *qual peça é* (F7.4) e a que diz *se há
    peça* (F7.5). Cada uma tem base própria e é medida em separado, porque as
    duas perguntas se aprendem com dados de origem diferente — ver
    `PASTA_OCUPACAO`.

    Com `medir` ligado, cada modelo custa duas redes e não uma: a primeira sem
    os diagramas de teste, para dar o número; a segunda com tudo, que é a que
    vai para o disco. Medir na que usa todas as amostras seria medir a memória
    dela.

    O `.pth` leva a impressão da base que o gerou (F7.3 aplicada aqui): sem ela,
    acrescentar amostras e esquecer de treinar é indistinguível de ter treinado,
    e o programa segue lendo com o modelo velho sem dizer nada.

    **Apontar `pasta` para outro lugar desliga a ocupação**, a menos que
    `pasta_ocupacao` venha junto. São duas bases independentes, e adivinhar onde
    está a segunda faria um teste com base própria treinar — e regravar — o
    modelo de verdade.
    """
    if pasta is not None and pasta_ocupacao is None:
        pasta_ocupacao = ""
    pasta = PASTA_PADRAO if pasta is None else pasta
    pasta_ocupacao = (PASTA_OCUPACAO if pasta_ocupacao is None
                      else pasta_ocupacao)
    destino = diag.CAMINHO_MODELO if destino is None else destino
    amostras = carregar_amostras(pasta)
    relatorio = Relatorio(total=len(amostras),
                          contagem=dict(collections.Counter(
                              s for s, _, _ in amostras)),
                          problemas=(conferir(pasta)
                                     + (conferir(pasta_ocupacao)
                                        if pasta_ocupacao else [])))
    if not amostras:
        return relatorio

    # --- a rede das peças: só as casas ocupadas, doze classes (F7.4) ---
    pecas = [a for a in amostras if a[0] != VAZIA]
    if pecas:
        # A ordem das saídas é fixada aqui e viaja no arquivo: sem isso, uma base
        # que ganha a primeira dama muda o significado de todas as colunas.
        simbolos = [s for s in SIMBOLOS if any(a[0] == s for a in pecas)]
        m = _treinar_e_gravar(pecas, simbolos, destino, pasta, medir, progresso)
        relatorio.acerto = m.acerto
        relatorio.acerto_por_classe = m.por_classe
        relatorio.temperatura = m.temperatura
        relatorio.casas_de_teste = m.casas
        relatorio.diagramas_de_teste = m.diagramas
        relatorio.destino = destino
        relatorio.bytes_gravados = os.path.getsize(destino)

    # --- a rede da ocupação: base própria, duas classes (F7.5) ---
    ocupacao = carregar_amostras(pasta_ocupacao) if pasta_ocupacao else []
    if ocupacao:
        alvo = destino_ocupacao or diag.CAMINHO_OCUPACAO
        m = _treinar_e_gravar(ocupacao, [VAZIA, OCUPADA], alvo,
                              pasta_ocupacao, medir, progresso)
        relatorio.total_ocupacao = len(ocupacao)
        relatorio.acerto_ocupacao = m.acerto
        relatorio.casas_de_ocupacao = m.casas
        relatorio.diagramas_de_ocupacao = m.diagramas
        relatorio.destino_ocupacao = alvo
        relatorio.bytes_ocupacao = os.path.getsize(alvo)
    if os.path.abspath(destino) == os.path.abspath(diag.CAMINHO_MODELO):
        diag.esquecer_modelo()
    return relatorio
